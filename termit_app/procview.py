"""Учебные ps и top тренажёра: python3 -m termit_app.procview ps|top [ключи].

Настоящие /bin/ps и /usr/bin/top — setuid-программы, а sandbox-exec их не запускает. Эти
работают без особых прав: список процессов и их данные берут из libproc (proc_listpids,
proc_pidinfo с PROC_PIDTASKALLINFO), командную строку — из sysctl KERN_PROCARGS2. %CPU —
по двум замерам процессорного времени с коротким промежутком, как у top.

Видно только то, что видно песочнице: свои процессы, которым можно послать сигнал. Под
sandbox-exec это процессы той же песочницы — то есть процессы игры; вне песочницы — все
процессы пользователя."""
import ctypes
import os
import pwd
import select
import shutil
import signal
import struct
import sys
import time

SANDBOX_ENV = "TERMIT_SANDBOXED"     # ставит игра, когда zsh запущен под sandbox-exec


def note(tool: str = "ps") -> str:
    """Пометка внизу: «только процессы игры» — правда лишь под профилем песочницы."""
    if os.environ.get(SANDBOX_ENV) == "1":
        return "training version: only game processes are visible"
    return f"training version of {tool}: your processes are visible"


def safe(text: str) -> str:
    """Управляющие символы в командной строке — как у настоящего ps: вместо них «?»."""
    return "".join("?" if ord(ch) < 32 or 127 <= ord(ch) < 160 else ch for ch in text)


_libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
_libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)

PROC_ALL_PIDS = 1
PROC_PIDTASKALLINFO = 2
TASKALLINFO_SIZE = 232          # proc_bsdinfo (136) + proc_taskinfo (96)
CTL_KERN, KERN_PROCARGS2 = 1, 49
CTL_HW, HW_MEMSIZE = 6, 24
NODEV = 0xFFFFFFFF


class _Timebase(ctypes.Structure):
    _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]


def _tick_ns() -> float:
    """Время процессора в proc_taskinfo — в «тиках» mach (на Apple Silicon это не наносекунды)."""
    tb = _Timebase()
    try:
        _libc.mach_timebase_info(ctypes.byref(tb))
        return tb.numer / tb.denom if tb.denom else 1.0
    except (AttributeError, OSError):
        return 1.0


TICK_NS = _tick_ns()


def memsize() -> int:
    mib = (ctypes.c_int * 2)(CTL_HW, HW_MEMSIZE)
    v, sz = ctypes.c_uint64(0), ctypes.c_size_t(8)
    if _libc.sysctl(mib, 2, ctypes.byref(v), ctypes.byref(sz), None, 0) == 0:
        return v.value
    return 0


def list_pids():
    n = _libproc.proc_listpids(PROC_ALL_PIDS, 0, None, 0)
    if n <= 0:
        return []
    buf = (ctypes.c_int * (n // 4 + 256))()
    n = _libproc.proc_listpids(PROC_ALL_PIDS, 0, buf, ctypes.sizeof(buf))
    return sorted({p for p in buf[:max(n, 0) // 4] if p > 0})


def _cstr(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace")


def _mem(pid: int, rss: int) -> int:
    fp = footprint(pid)
    return rss if fp is None else fp


def taskinfo(pid: int):
    """proc_bsdinfo + proc_taskinfo одного процесса; None — нет такого или чужой."""
    b = ctypes.create_string_buffer(TASKALLINFO_SIZE)
    if _libproc.proc_pidinfo(pid, PROC_PIDTASKALLINFO, ctypes.c_uint64(0), b,
                             TASKALLINFO_SIZE) != TASKALLINFO_SIZE:
        return None
    raw = b.raw
    (flags, status, _xst, ppid_pid, ppid, uid, gid, ruid, rgid, svuid, svgid, _rfu
     ) = struct.unpack_from("12I", raw, 0)
    comm, name = _cstr(raw[48:64]), _cstr(raw[64:96])
    nfiles, pgid, pjobc, tdev, tpgid, nice = struct.unpack_from("5Ii", raw, 96)
    start_s, start_us = struct.unpack_from("2Q", raw, 120)
    (vsize, rss, total_user, total_sys, _tu, _ts) = struct.unpack_from("6Q", raw, 136)
    ints = struct.unpack_from("12i", raw, 184)
    return {
        "pid": ppid_pid, "ppid": ppid, "uid": uid, "flags": flags, "status": status,
        "comm": comm, "name": name or comm, "pgid": pgid, "tdev": tdev, "tpgid": tpgid,
        "nice": nice, "start": start_s + start_us / 1e6, "vsz": vsize, "rss": rss,
        "mem": _mem(pid, rss),
        "cpu_ns": (total_user + total_sys) * TICK_NS,
        "threads": ints[9], "running": ints[10],
    }


RUSAGE_INFO_V2 = 2
RUSAGE_SIZE = 512               # с запасом: rusage_info_v2 занимает меньше
PHYS_FOOTPRINT_AT = 72          # uuid (16) + 7 полей uint64 до ri_phys_footprint


def footprint(pid: int):
    """Физический след памяти (ri_phys_footprint) — то, что настоящий top показывает в MEM.
    В нём учтена и сжатая память: процесс, чьи страницы ужал компрессор macOS, не «худеет»,
    как по RSS. None — вызов недоступен (тогда берётся RSS)."""
    b = ctypes.create_string_buffer(RUSAGE_SIZE)
    try:
        if _libproc.proc_pid_rusage(pid, RUSAGE_INFO_V2, b) != 0:
            return None
    except (AttributeError, OSError):
        return None
    return struct.unpack_from("Q", b.raw, PHYS_FOOTPRINT_AT)[0]


def procargs(pid: int):
    """Командная строка процесса (argv) из KERN_PROCARGS2; None — недоступна."""
    mib = (ctypes.c_int * 3)(CTL_KERN, KERN_PROCARGS2, pid)
    size = ctypes.c_size_t(0)
    if _libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0 or size.value < 4:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if _libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
        return None
    raw = buf.raw[:size.value]
    argc = struct.unpack_from("i", raw, 0)[0]
    rest = raw[4:]
    _exe, _, rest = rest.partition(b"\0")      # путь программы, потом выравнивание нулями
    rest = rest.lstrip(b"\0")
    args = rest.split(b"\0")[:argc]
    return [a.decode("utf-8", "replace") for a in args] or None


def visible(pid: int, uid: int, me: int) -> bool:
    """Свой процесс, которому можно послать сигнал: под песочницей — только её процессы."""
    if uid != me:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    return True


def _ttys():
    out = {}
    try:
        names = os.listdir("/dev")
    except OSError:
        return out
    for n in names:
        if n.startswith("tty") or n == "console":
            try:
                out[os.stat("/dev/" + n).st_rdev] = n
            except OSError:
                pass
    return out


def snapshot(self_argv=None, self_name=None):
    """Видимые процессы: словарь pid -> сведения. Свой процесс показываем под именем,
    которым его вызвали (ps, top), а не как python."""
    me, mine = os.getuid(), os.getpid()
    out = {}
    for pid in list_pids():
        info = taskinfo(pid)
        if info is None or not visible(pid, info["uid"], me):
            continue
        if pid == mine and self_argv:
            info["args"] = list(self_argv)
            info["name"] = info["comm"] = self_name or self_argv[0]
        else:
            info["args"] = procargs(pid) or [info["comm"]]
        out[pid] = info
    return out


def measure(interval: float, prev=None, self_argv=None, self_name=None):
    """%CPU каждого процесса — доля процессорного времени между прошлым снимком (или замером
    interval секунд назад) и нынешним, как у top."""
    if prev is None:
        prev = snapshot(self_argv, self_name)
        prev["_t"] = time.monotonic()
        time.sleep(interval)
    now = snapshot(self_argv, self_name)
    t = time.monotonic()
    dt_ns = max((t - prev["_t"]) * 1e9, 1.0)
    for pid, p in now.items():
        old = prev.get(pid)
        d = p["cpu_ns"] - old["cpu_ns"] if old and old["start"] == p["start"] else 0
        p["pcpu"] = max(0.0, d * 100.0 / dt_ns)
    now["_t"] = t
    return now


def procs_of(snap):
    return [p for k, p in snap.items() if k != "_t"]


def user_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def fmt_time(ns: float, top: bool = False) -> str:
    cs = int(ns / 1e7)
    m, rem = divmod(cs, 6000)
    if top:
        return f"{m:02d}:{rem // 100:02d}.{rem % 100:02d}"
    return f"{m}:{rem // 100:02d}.{rem % 100:02d}"


def fmt_started(t: float, now: float = None) -> str:
    now = time.time() if now is None else now
    lt, ln = time.localtime(t), time.localtime(now)
    if lt[:3] == ln[:3]:
        return time.strftime("%I:%M%p", lt).lstrip("0")
    if now - t < 7 * 86400:
        return time.strftime("%a%I%p", lt)
    return time.strftime("%d%b%y", lt).lstrip("0")


def fmt_mem(n: int) -> str:
    for unit, size in (("G", 1 << 30), ("M", 1 << 20), ("K", 1 << 10)):
        if n >= size * 10 or (unit == "K" and n >= size):
            return f"{n // size}{unit}"
    return f"{n}B"


def stat_of(p) -> str:
    s = {1: "I", 4: "T", 5: "Z"}.get(p["status"])
    if s is None:
        s = "R" if p.get("running", 0) > 0 or p.get("pcpu", 0) >= 50 else "S"
    if p["tdev"] != NODEV and p["pgid"] == p["tpgid"]:
        s += "+"
    return s


# ----------------------------------------------------------------------- ps

class Usage(Exception):
    pass


PS_USAGE = ("usage: ps [aux] [-e|-A] [-f] [-r|-m] [-p PID[,PID]] [-o field,field]\n"
            "  ps aux: all processes in detail; ps aux -r: hungriest first; "
            "ps -p PID: one process\n")

PS_FIELDS = {   # ключ: (заголовок, ширина; отрицательная — по левому краю)
    "user": ("USER", -16), "uid": ("UID", 5), "pid": ("PID", 5), "ppid": ("PPID", 5),
    "%cpu": ("%CPU", 5), "%mem": ("%MEM", 4), "vsz": ("VSZ", 8), "rss": ("RSS", 6),
    "tt": ("TT", 4), "tty": ("TTY", -8), "stat": ("STAT", -4), "started": ("STARTED", 7),
    "time": ("TIME", 9), "command": ("COMMAND", 0), "comm": ("COMM", 0), "c": ("C", 3),
    "stime": ("STIME", 6), "cmd": ("CMD", 0), "pgid": ("PGID", 5), "nice": ("NI", 3),
}
ALIASES = {"pcpu": "%cpu", "pmem": "%mem", "args": "command", "state": "stat",
           "start": "started", "ucomm": "comm", "user": "user", "ruser": "user",
           "rsz": "rss", "ni": "nice"}
FMT_AUX = ["user", "pid", "%cpu", "%mem", "vsz", "rss", "tt", "stat", "started", "time",
           "command"]
FMT_EF = ["uid", "pid", "ppid", "c", "stime", "tty", "time", "cmd"]
FMT_DEFAULT = ["pid", "tty", "time", "cmd"]


def parse_ps(args):
    o = {"all": False, "x": False, "user": False, "full": False, "sort": None, "pids": [],
         "fmt": [], "wide": False}

    def flags(s, it):
        for i, ch in enumerate(s):
            if ch == "a":
                o["all"] = True
            elif ch == "x":
                o["x"] = True
            elif ch in "eA":
                o["all"] = o["x"] = True
            elif ch == "u":
                o["user"] = True
            elif ch == "f":
                o["full"] = True
            elif ch == "r":
                o["sort"] = "cpu"
            elif ch == "m":
                o["sort"] = "mem"
            elif ch == "w":
                o["wide"] = True
            elif ch in "po":
                rest = s[i + 1:] or next(it, None)
                if rest is None:
                    raise Usage(f"ps: option requires an argument -- {ch}")
                if ch == "p":
                    for x in rest.replace(",", " ").split():
                        if not x.isdigit():
                            raise Usage(f"ps: illegal process id: {x}")
                        o["pids"].append(int(x))
                else:
                    for f in rest.replace(",", " ").split():
                        o["fmt"].append(f)
                return
            elif ch == "h":
                raise Usage(PS_USAGE + note("ps"))
            else:
                raise Usage(f"ps: training version does not know option -{ch}\n"
                            f"{PS_USAGE}{note('ps')}")

    it = iter(args)
    for a in it:
        if a in ("--help", "-h"):
            raise Usage(PS_USAGE + note("ps"))
        if a.startswith("-"):
            flags(a[1:], it)
        elif a.isdigit():
            o["pids"].append(int(a))
        else:
            flags(a, it)     # BSD-стиль без дефиса: ps aux
    return o


def _field(key):
    key = key.lower()
    head = None
    if "=" in key:
        key, head = key.split("=", 1)
    key = ALIASES.get(key, key)
    if key not in PS_FIELDS:
        raise Usage(f"ps: {key}: keyword not found (training version)\n{PS_USAGE}{note('ps')}")
    title, width = PS_FIELDS[key]
    return key, (title if head is None else head), width


def _value(key, p, ttys, mem, now):
    tdev = p["tdev"]
    tty = ttys.get(tdev) if tdev != NODEV else None
    if key == "user":
        return user_name(p["uid"])
    if key in ("uid", "pid", "ppid", "pgid", "nice"):
        return str(p[key])
    if key == "%cpu":
        return f"{p.get('pcpu', 0.0):.1f}"
    if key == "%mem":
        return f"{p['rss'] * 100.0 / mem:.1f}" if mem else "0.0"
    if key == "vsz":
        return str(p["vsz"] // 1024)
    if key == "rss":
        return str(p["rss"] // 1024)
    if key == "tt":
        return tty[3:] if tty and tty.startswith("tty") else (tty or "??")
    if key == "tty":
        return tty or "??"
    if key == "stat":
        return stat_of(p)
    if key in ("started", "stime"):
        return fmt_started(p["start"], now)
    if key == "time":
        return fmt_time(p["cpu_ns"])
    if key == "c":
        return str(min(int(p.get("pcpu", 0)), 99))
    if key in ("command", "cmd"):
        return safe(" ".join(p["args"]))
    if key == "comm":
        return safe(p["args"][0] if p["args"] else p["comm"])
    return ""


def render_ps(procs, fmt, columns=None):
    ttys, mem, now = _ttys(), memsize(), time.time()
    fields = [_field(f) for f in fmt]
    rows = [[_value(k, p, ttys, mem, now) for k, _, _ in fields] for p in procs]
    lines = []
    show_head = any(h for _, h, _ in fields)
    for i, row in enumerate(([[h for _, h, _ in fields]] if show_head else []) + rows):
        cells = []
        for j, ((_, _, width), cell) in enumerate(zip(fields, row)):
            last = j == len(fields) - 1
            if width == 0 or (last and width < 0):
                cells.append(cell)
            elif width < 0:
                cells.append(cell.ljust(-width))
            else:
                cells.append(cell.rjust(width))
        line = " ".join(cells).rstrip()
        if columns:
            line = line[:columns]
        lines.append(line)
    return lines


def select_ps(snap, o, me_pid):
    procs = procs_of(snap)
    if o["pids"]:
        procs = [p for p in procs if p["pid"] in o["pids"]]
    elif not o["all"]:
        procs = [p for p in procs if o["x"] or p["tdev"] != NODEV]
    elif not o["x"]:
        procs = [p for p in procs if p["tdev"] != NODEV]
    if o["sort"] == "cpu":
        procs.sort(key=lambda p: (-p.get("pcpu", 0.0), p["pid"]))
    elif o["sort"] == "mem":
        procs.sort(key=lambda p: (-p["mem"], p["pid"]))     # как MEM у top: след памяти
    elif o["user"] and not o["fmt"]:
        procs.sort(key=lambda p: (-p.get("pcpu", 0.0), p["pid"]))   # ps u — так и у настоящего
    else:
        procs.sort(key=lambda p: p["pid"])
    return procs


def ps_main(args, out=None) -> int:
    out = out or sys.stdout
    try:
        o = parse_ps(args)
    except Usage as e:
        print(str(e), file=sys.stderr)
        return 1
    if o["fmt"]:
        fmt = o["fmt"]
    elif o["user"]:
        fmt = FMT_AUX
    elif o["full"]:
        fmt = FMT_EF
    else:
        fmt = FMT_DEFAULT
    try:
        [_field(f) for f in fmt]
    except Usage as e:
        print(str(e), file=sys.stderr)
        return 1
    snap = measure(0.25, self_argv=["ps"] + list(args), self_name="ps")
    if os.getpid() in snap:
        snap[os.getpid()]["pcpu"] = 0.0     # сам ps почти не ест процессор — как у настоящего
    procs = select_ps(snap, o, os.getpid())
    tty = out.isatty()
    columns = None
    if tty and not o["wide"]:
        columns = shutil.get_terminal_size((80, 24)).columns
    for line in render_ps(procs, fmt, columns):
        out.write(line + "\n")
    if tty:
        out.write(note("ps") + "\n")
    out.flush()
    return 0 if procs or not o["pids"] else 1


# ---------------------------------------------------------------------- top

TOP_USAGE = ("usage: top [-o cpu|mem|pid|time|command] [-n NUMBER] [-l SAMPLES] "
             "[-s SECONDS]\n  top -o cpu: hungriest first; q or Ctrl+C to quit\n")
TOP_KEYS = {"cpu": lambda p: -p.get("pcpu", 0.0), "mem": lambda p: -p["mem"],
            "rsize": lambda p: -p["rss"], "pid": lambda p: -p["pid"],
            "time": lambda p: -p["cpu_ns"], "command": lambda p: p["name"].lower(),
            "th": lambda p: -p["threads"], "threads": lambda p: -p["threads"]}


def parse_top(args):
    o = {"sort": "pid", "n": None, "l": None, "s": 1.0}
    it = iter(args)
    for a in it:
        if a in ("-h", "--help"):
            raise Usage(TOP_USAGE + note("top"))
        if a == "-u":
            o["sort"] = "cpu"
            continue
        if a in ("-o", "-n", "-l", "-s", "-O") or (a[:2] in ("-o", "-n", "-l", "-s", "-O")
                                                     and len(a) > 2):
            key, val = a[:2], (a[2:] or next(it, None))
            if val is None:
                raise Usage(f"top: option {key} requires an argument")
            if key == "-o":
                val = val.lower().lstrip("+-")
                if val not in TOP_KEYS:
                    raise Usage(f"top: training version cannot sort by {val}\n"
                                f"{TOP_USAGE}{note('top')}")
                o["sort"] = val
            elif key == "-O":
                pass        # вторичная сортировка — молча принимаем
            else:
                try:
                    num = float(val) if key == "-s" else int(val)
                except ValueError:
                    raise Usage(f"top: {key} expects a number, not {val}")
                o[{"-n": "n", "-l": "l", "-s": "s"}[key]] = num
            continue
        raise Usage(f"top: training version does not know option {a}\n{TOP_USAGE}{note('top')}")
    return o


def render_top(snap, o, rows=None):
    procs = procs_of(snap)
    procs.sort(key=lambda p: (TOP_KEYS[o["sort"]](p), p["pid"]))
    running = sum(1 for p in procs if stat_of(p).startswith("R"))
    threads = sum(max(p["threads"], 0) for p in procs)
    la = os.getloadavg()
    mem = memsize()
    used = sum(p["mem"] for p in procs)
    head = [
        f"Processes: {len(procs)} total, {running} running, {len(procs) - running} sleeping, "
        f"{threads} threads {time.strftime('%H:%M:%S'):>10}",
        f"Load Avg: {la[0]:.2f}, {la[1]:.2f}, {la[2]:.2f}",
        f"PhysMem: {fmt_mem(mem)} total, visible processes use {fmt_mem(used)}.",
        note("top"),
        "",
        f"{'PID':<7}{'COMMAND':<17}{'%CPU':<6}{'TIME':<10}{'#TH':<5}{'MEM':<7}{'PPID':<7}"
        f"{'STATE':<9}USER",
    ]
    limit = o["n"]
    if rows is not None:
        room = max(rows - len(head) - 1, 1)
        limit = room if limit is None else min(limit, room)
    lines = list(head)
    for p in procs[:limit] if limit is not None else procs:
        st = stat_of(p)[0]
        state = {"R": "running", "S": "sleeping", "T": "stopped", "Z": "zombie",
                 "I": "idle"}.get(st, "sleeping")
        lines.append(f"{p['pid']:<7}{safe(p['name'])[:16]:<17}{p.get('pcpu', 0.0):<6.1f}"
                     f"{fmt_time(p['cpu_ns'], top=True):<10}{p['threads']:<5}"
                     f"{fmt_mem(p['mem']):<7}{p['ppid']:<7}{state:<9}{user_name(p['uid'])}")
    return lines


def top_main(args, out=None, inp=None) -> int:
    out = out or sys.stdout
    inp = inp or sys.stdin
    try:
        o = parse_top(args)
    except Usage as e:
        print(str(e), file=sys.stderr)
        return 1
    me = ["top"] + list(args)
    interactive = o["l"] is None and out.isatty() and inp.isatty()
    if not interactive:
        samples = o["l"] if o["l"] is not None else 1
        snap = None
        for i in range(max(samples, 1)):
            if i:
                time.sleep(max(o["s"], 0.1))
            snap = measure(0.5 if snap is None else o["s"], prev=snap, self_argv=me,
                           self_name="top")
            for line in render_top(snap, o):
                out.write(line + "\n")
            out.write("\n")
            out.flush()
        return 0
    return _top_loop(o, out, inp, me)


def _top_loop(o, out, inp, me) -> int:
    import termios
    import tty
    fd = inp.fileno()
    old = termios.tcgetattr(fd)
    stop = []
    def _term(*_):          # kill PID_top: всё равно вернуть терминал (finally ниже)
        raise SystemExit(143)

    old_int = signal.signal(signal.SIGINT, lambda *_: stop.append(1))
    old_term = signal.signal(signal.SIGTERM, _term)
    try:
        tty.setcbreak(fd)
        out.write("\033[?1049h\033[?25l")           # отдельный экран, без курсора
        snap = measure(0.5, self_argv=me, self_name="top")
        while not stop:
            size = shutil.get_terminal_size((80, 24))
            lines = [l[:size.columns] for l in render_top(snap, o, rows=size.lines)]
            out.write("\033[H\033[2J" + "\n".join(lines))
            out.write("\n\033[7m q to quit \033[0m")
            out.flush()
            end = time.monotonic() + max(o["s"], 0.2)
            while not stop and time.monotonic() < end:
                try:
                    r, _, _ = select.select([fd], [], [], max(end - time.monotonic(), 0))
                except InterruptedError:
                    continue
                if r:
                    ch = os.read(fd, 1)
                    if ch in (b"q", b"Q", b"\x03", b"\x04"):
                        stop.append(1)
            if not stop:
                snap = measure(o["s"], prev=snap, self_argv=me, self_name="top")
    finally:
        out.write("\033[?25h\033[?1049l")
        out.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
    return 0


def main(argv) -> int:
    if not argv or argv[0] not in ("ps", "top"):
        print("usage: python3 -m termit_app.procview ps|top [options]", file=sys.stderr)
        return 2
    try:
        if argv[0] == "ps":
            return ps_main(argv[1:])
        return top_main(argv[1:])
    except BrokenPipeError:          # ps aux | head закрыл трубу раньше времени
        try:
            sys.stdout = open(os.devnull, "w")
        except OSError:
            pass
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
