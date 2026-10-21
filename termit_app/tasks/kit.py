"""Мелкие помощники для setup и check поручений."""
import csv
import difflib
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

# Слова для случайных данных — бытовые, без сеттинга: файлы одинаковы во всех темах.
# По-английски (FB12-data, п. 42: в терминале всё как в настоящем) и НЕ из LATIN: LATIN идёт
# в имена файлов и папок, а слово-ответ внутри файла не должно совпадать с именем рядом.
WORDS = ["maple", "falcon", "harbor", "pepper", "violin", "comet", "magnet", "candle",
         "teapot", "walnut", "otter", "scooter", "thunder", "lily", "glacier",
         "marble", "trumpet", "pebble", "acorn", "domino"]
# Латинские имена — понятные английские слова (не транслит: имя должно читаться на любом языке)
LATIN = ["orange", "lighthouse", "coffee", "lemon", "guitar", "rocket", "compass", "lantern",
         "kettle", "cactus", "penguin", "bicycle", "rainbow", "tulip", "volcano",
         "globe", "drum", "anchor", "clover", "chess"]


def word(rng) -> str:
    return rng.choice(WORDS)


def latin(rng) -> str:
    return rng.choice(LATIN)


def home(box) -> Path:
    """Домашняя папка внутри песочницы (туда ведёт ~)."""
    return Path(box) / ".termit" / "home"


def write(path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_random(path, size: int, rng) -> Path:
    """Файл со случайными байтами (нули APFS может хранить «дырой» и врать о размере)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rng.randbytes(size))
    return path


def sha(path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


BOX_READ_CAP = 1 << 20      # проверки у родителя (судья) читают файлы задачи не больше 1 МБ


def sha_in_box(box, path) -> Optional[str]:
    """sha файла задачи для проверки у родителя: внутри песочницы, без симлинков и FIFO, не
    больше BOX_READ_CAP (sandbox.read_in_box). Не обычный файл — None."""
    from termit_app import sandbox
    raw = sandbox.read_in_box(box, path, BOX_READ_CAP)
    return None if raw is None else hashlib.sha1(raw).hexdigest()


RESET_TAIL = "Набери reset — соберу задачу заново, с теми же данными."


def _walk_shas(root: Path, skip_termit: bool) -> set:
    out = set()
    for cur, dirs, files in os.walk(root):
        if skip_termit and Path(cur) == root and ".termit" in dirs:
            dirs.remove(".termit")
        dirs[:] = [d for d in dirs if not d.startswith(".venv")]   # готовые venv (часть 7)
        for name in files:
            f = Path(cur) / name
            try:
                st = os.lstat(f)
                if stat.S_ISREG(st.st_mode) and st.st_size <= BOX_READ_CAP:
                    out.add(sha(f))
            except OSError:
                pass
    return out


def tree_shas(box) -> set:
    """sha всех обычных файлов песочницы и её дома ~ (служебная .termit — мимо). Для
    проверок в хуке, внутри песочницы: по симлинкам не ходит, гигантов не читает."""
    box = Path(box)
    return _walk_shas(box, True) | (_walk_shas(home(box), False) if home(box).is_dir() else set())


def lost(box, shas) -> set:
    """Какого содержимого (sha) больше нет нигде в песочнице: стёрто или испорчено —
    командами не вернуть, остаётся reset (Н3.1 приёмки-1)."""
    want = set(shas)
    return want - tree_shas(box) if want else set()


def names_line(names, limit: int = 3) -> str:
    names = sorted(names)
    return ", ".join(names[:limit]) + ("…" if len(names) > limit else "")


def _ps(pid: int, field: str):
    """Поле ps для процесса; None — ps запустить нельзя (в sandbox-exec setuid-программы
    вроде /bin/ps не запускаются: Operation not permitted)."""
    try:
        return subprocess.run(["/bin/ps", "-p", str(pid), "-o", f"{field}="],
                              capture_output=True, text=True).stdout.strip()
    except OSError:
        return None


def alive(pid: int) -> bool:
    if pid <= 0:     # метка отложенного запуска, которую не заменили: не «убит», а не запущен
        return True
    out = _ps(pid, "stat")
    if out is None:                 # внутри песочницы: спрашиваем ядро сигналом 0
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:     # процесс есть, но чужой
            return True
        return True
    return bool(out) and not out.startswith("Z")


def gone(pid: int) -> bool:
    """Процесс завершён (с короткой паузой — kill доходит не мгновенно)."""
    for _ in range(3):
        if not alive(pid):
            return True
        time.sleep(0.05)
    return False


# Метки отложенного запуска: отрицательные «PID», которые termit_app.launch заменит настоящими.
SPAWN_TOKEN = -1_000_000


def _queue(box) -> Path:
    return Path(box) / ".termit" / "spawn.json"


def spawn_detached(box, command: str) -> int:
    """Запустить процесс поручения отвязанно и запомнить PID.
    Если песочница ждёт запуска (есть .termit/spawn.json, его создаёт sandbox.create для
    настоящей игры), команда откладывается: её запустит termit_app.launch уже ВНУТРИ
    sandbox-exec — родитель никогда не исполняет то, что лежит в box (А1 отчёта 07).
    Тогда возвращается метка, которую launch заменит в task.json настоящим PID."""
    q = _queue(box)
    if q.exists() and not os.environ.get("TERMIT_LAUNCHED"):
        try:
            items = json.loads(q.read_text("utf-8") or "[]")
        except ValueError:
            items = []
        token = SPAWN_TOKEN - len(items)
        items.append({"token": token, "cmd": command})
        from termit_app import sandbox      # родитель пишет в .termit только заменой (В1)
        sandbox.write_box_file(box, ".termit/spawn.json", json.dumps(items, ensure_ascii=False))
        return token
    return spawn_now(box, command)


def spawn_now(box, command: str) -> int:
    """Запустить сразу (родителем станет launchd — без зомби); процесс наследует песочницу
    вызывающего."""
    out = subprocess.run(["/bin/sh", "-c", f"{command} >/dev/null 2>&1 & echo $!"],
                         cwd=str(box), capture_output=True, text=True, check=True).stdout
    pid = int(out.strip())
    with open(Path(box) / ".termit" / "pids", "a") as f:
        f.write(f"{pid}\n")
    return pid


def replace_tokens(value, mapping: dict):
    """Подставить настоящие PID вместо меток отложенного запуска (в словарях и списках)."""
    if isinstance(value, dict):
        return {k: replace_tokens(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_tokens(v, mapping) for v in value]
    if isinstance(value, int) and not isinstance(value, bool) and value in mapping:
        return mapping[value]
    return value


def kill_registered(box) -> None:
    """Убить процессы, запущенные поручением (только если в их командной строке путь песочницы).
    .termit открывается без ссылок (Н5): подменённая изнутри ссылкой папка — мимо, чужой
    файл pids снаружи не читаем и не удаляем."""
    from termit_app import sandbox
    try:
        dfd = sandbox._open_dirs(box, [".termit"])
    except OSError:
        return
    try:
        raw = _read_pids_at(dfd)
        if raw is None:
            return
        for line in raw.split():
            try:
                pid = int(line)
            except ValueError:      # файл в песочнице — игрок мог его испортить
                continue
            if pid <= 0:
                continue
            if _mentions(pid, str(box)) or _sandboxed_self():
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        try:
            os.unlink("pids", dir_fd=dfd)
        except OSError:
            pass
    finally:
        os.close(dfd)


def _sandboxed_self() -> bool:
    """Мы сами под sandbox-exec (reset изнутри): ps там не запускается и «своих» по командной
    строке не узнать, зато профиль пускает сигналы только процессам этой же песочницы —
    чужого kill не заденет (P2 fix2: иначе reset оставлял старый процесс задачи живым)."""
    from termit_app import sandbox
    f = sandbox._checker()
    try:
        return f is not None and f(os.getpid(), None, 0) == 1
    except (OSError, Exception):        # noqa: BLE001
        return False


def _read_pids_at(dfd: int):
    """pids в открытой .termit: None — файла нет (или это не файл и не ссылка)."""
    try:
        os.lstat("pids", dir_fd=dfd)
    except OSError:
        return None
    try:
        fd = os.open("pids", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    except OSError:
        return ""
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > PIDS_CAP:
            return ""
        return os.read(fd, PIDS_CAP).decode("ascii", errors="replace")
    except OSError:
        return ""
    finally:
        os.close(fd)


PIDS_CAP = 64 * 1024


def _mentions(pid: int, text: str) -> bool:
    """В командной строке процесса есть text (путь песочницы) — значит, он наш."""
    cmd = _ps(pid, "command")
    if cmd is not None:
        return text in cmd
    out = subprocess.run(["/usr/bin/pgrep", "-f", "--", text],
                         capture_output=True, text=True).stdout
    return str(pid) in out.split()


KILLERS = ("kill", "pkill", "killall")


def used_kill(cmds) -> bool:
    """Игрок сам набирал kill/pkill/killall: слово ищется по границам оболочки, так что
    «ls;kill 1», «(kill 1)» и «true&&kill 1» тоже в счёт."""
    return any(w in KILLERS for c in cmds for w in re.split(r"[\s;&|()`]+", c.line))


def read_clipboard(box) -> str:
    """Буфер обмена; в тестах заглушка pbcopy пишет его в .termit/fakeclip."""
    fake = Path(box) / ".termit" / "fakeclip"
    if fake.exists():
        return fake.read_text("utf-8", errors="replace")
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout


def diff_text(got: str, want: str, limit: int = 6) -> str:
    """Разница по-человечески (Н3.10 приёмки-1): «строка N: ждали …, сейчас …»."""
    out = []
    sm = difflib.SequenceMatcher(a=want.splitlines(), b=got.splitlines(), autojunk=False)
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal":
            continue
        want_part, got_part = sm.a[a1:a2], sm.b[b1:b2]
        if len(want_part) == len(got_part):         # строка на строку — пара «ждали/сейчас»
            out += [f"   строка {b1 + k + 1}: ждали «{w}», сейчас «{g}»"
                    for k, (w, g) in enumerate(zip(want_part, got_part))]
            continue
        out += [f"   строка {a1 + k + 1}: не хватает «{w}»" for k, w in enumerate(want_part)]
        out += [f"   строка {b1 + k + 1}: лишняя — «{g}»" for k, g in enumerate(got_part)]
    return "\n".join(out[:limit] + (["   …"] if len(out) > limit else []))


def quote(path) -> str:
    return shlex.quote(str(path))


# --- venv из запаса (часть 7, A4) --------------------------------------------------------
# Готовый .venv задачи — клон эталона из box/.termit/stock (его кладёт sandbox.create, reset
# не трогает): cp -c -R -p и правка путей. Пути к venv живут только в bin/activate*
# (VIRTUAL_ENV=…) и в shebang консольных скриптов bin/*; pyvenv.cfg (home — базовый
# интерпретатор) и RECORD пакетов не трогаем (спайк S0, решение 6). Клон — честный venv: в
# нём работают activate, pip, pip list и freeze.
_VENV_LINE = re.compile(rb"""^VIRTUAL_ENV=(["'])(.+?)\1\s*$""", re.M)
ACTIVATE_FILES = ("activate", "activate.csh", "activate.fish")


def venv_prefix(venv) -> Optional[str]:
    """Путь, под которым venv создан (VIRTUAL_ENV= в bin/activate); нет — None."""
    try:
        data = (Path(venv) / "bin" / "activate").read_bytes()
    except OSError:
        return None
    m = _VENV_LINE.search(data)
    return m.group(2).decode("utf-8", "surrogateescape") if m else None


def _rewrite(path: Path, old: bytes, new: bytes, first_line_only: bool) -> bool:
    """Заменить old на new в файле (только в первой строке — для shebang): без ссылок,
    только обычный файл, права те же, запись — временный файл рядом и rename."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if not stat.S_ISREG(st.st_mode):
        return False
    data = path.read_bytes()
    if first_line_only:
        if not data.startswith(b"#!"):
            return False
        first, nl, rest = data.partition(b"\n")
        out = first.replace(old, new) + nl + rest
    else:
        out = data.replace(old, new)
    if out == data:
        return False
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 stat.S_IMODE(st.st_mode))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(out)
        os.chmod(tmp, stat.S_IMODE(st.st_mode))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return True


def clone_venv(src, dst) -> int:
    """Клон venv src в dst (dst не должно быть): cp -c -R -p и правка путей src → dst в
    bin/activate* и shebang скриптов bin/*. Вернуть число исправленных файлов."""
    src, dst = Path(src), Path(dst)
    if os.path.lexists(dst):
        raise FileExistsError(str(dst))
    old = venv_prefix(src)
    if old is None:
        raise ValueError(f"не venv: {src}")
    r = subprocess.run(["/bin/cp", "-c", "-R", "-p", str(src), str(dst)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise OSError(f"cp: {r.stderr.strip()[:200]}")
    old_b, new_b = old.encode("utf-8", "surrogateescape"), os.fsencode(os.path.abspath(dst))
    fixed = 0
    bindir = dst / "bin"
    for name in sorted(os.listdir(bindir)):
        p = bindir / name
        if name in ACTIVATE_FILES:
            fixed += _rewrite(p, old_b, new_b, first_line_only=False)
        else:
            fixed += _rewrite(p, old_b, new_b, first_line_only=True)
    return fixed


def venv_from_stock(box, kind: str = "light", dst: str = ".venv") -> Path:
    """Готовый venv задачи из запаса песочницы: box/.termit/stock/<kind> → box/<dst>. Зовёт
    setup задачи (при create — родитель, при reset — хук внутри песочницы)."""
    target = Path(box) / dst
    clone_venv(Path(box) / ".termit" / "stock" / kind, target)
    return target


def site_packages(venv) -> Optional[Path]:
    """lib/python3.X/site-packages venv (первая по имени); нет — None."""
    lib = Path(venv) / "lib"
    try:
        names = sorted(n for n in os.listdir(lib) if re.match(r"^python3\.\d+$", n))
    except OSError:
        return None
    for n in names:
        p = lib / n / "site-packages"
        if p.is_dir() and not p.is_symlink():
            return p
    return None


def venv_drop(venv, name: str) -> int:
    """Убрать пакет name из venv так же, как pip uninstall: файлы из RECORD его dist-info (и
    консольные скрипты в bin/), потом опустевшие папки и сам dist-info. Только то, что лежит
    внутри venv, только обычные файлы и ссылки. Зовёт setup задачи (родитель при create, хук
    при reset) на свежем клоне запаса. Вернуть число удалённых файлов."""
    venv = Path(os.path.abspath(venv))
    site = site_packages(venv)
    if site is None:
        return 0
    removed = 0
    for info in sorted(site.glob(f"{name}-*.dist-info")):
        try:
            rows = list(csv.reader((info / "RECORD").read_text("utf-8").splitlines()))
        except OSError:
            rows = []
        dirs = set()
        for row in rows:
            if not row or not row[0]:
                continue
            p = os.path.normpath(os.path.join(site, row[0]))
            if not p.startswith(str(venv) + os.sep):
                continue                    # pyc Apple-кэша сборки и прочее вне venv
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                os.unlink(p)
                removed += 1
                dirs.add(os.path.dirname(p))
        for d in sorted(dirs, key=len, reverse=True):
            while d.startswith(str(site) + os.sep) and d != str(info):
                try:
                    os.rmdir(d)             # только пустую
                except OSError:
                    break
                d = os.path.dirname(d)
        if info.is_dir() and not info.is_symlink():
            shutil.rmtree(info)
    return removed


def venv_put(venv, files: Dict[str, bytes]) -> int:
    """Положить в venv пакет так, как его кладёт pip install колеса: файлы колеса
    (wheelmake.wheel_files) — в site-packages, в dist-info — INSTALLER «pip» и его строка в
    RECORD (pip uninstall уберёт и его). Только внутрь site-packages этого venv. Зовёт setup
    задачи (родитель при create, хук при reset). Вернуть число файлов."""
    site = site_packages(Path(os.path.abspath(venv)))
    if site is None:
        raise FileNotFoundError(f"нет site-packages в {venv}")
    files = dict(files)
    record = next(k for k in files if k.endswith(".dist-info/RECORD"))
    dist = record.rsplit("/", 1)[0]
    files[f"{dist}/INSTALLER"] = b"pip\n"
    files[record] = files[record] + f"{dist}/INSTALLER,,\n".encode()
    for rel, data in files.items():
        p = Path(os.path.normpath(os.path.join(site, rel)))
        if not str(p).startswith(str(site) + os.sep):
            raise ValueError(f"путь вне site-packages: {rel}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        os.chmod(p, 0o644)
    return len(files)


def venv_foreign(venv, prefix: str, home: str) -> None:
    """Сделать venv «перенесённым с чужой машины»: в bin/activate* и shebang скриптов — путь
    prefix вместо своего, в pyvenv.cfg — home чужого Python, ссылка bin/python3.X — на его
    интерпретатор (его здесь нет). Сам venv в песочнице — как был, только пути чужие."""
    venv = Path(venv)
    old = venv_prefix(venv)
    if old is None:
        raise ValueError(f"не venv: {venv}")
    old_b, new_b = old.encode("utf-8", "surrogateescape"), prefix.encode("utf-8")
    bindir = venv / "bin"
    for n in sorted(os.listdir(bindir)):
        _rewrite(bindir / n, old_b, new_b, first_line_only=n not in ACTIVATE_FILES)
    cfg = venv / "pyvenv.cfg"
    lines = cfg.read_text("utf-8").splitlines()
    cfg.write_text("".join((f"home = {home}" if x.startswith("home =") else x) + "\n"
                           for x in lines), encoding="utf-8")
    for n in sorted(os.listdir(bindir)):
        p = bindir / n
        if re.match(r"^python3\.\d+$", n) and os.path.islink(p) and os.path.isabs(os.readlink(p)):
            os.unlink(p)
            os.symlink(f"{home}/{n}", p)
