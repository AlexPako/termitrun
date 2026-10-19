"""Учебный сервер PostgreSQL задачи (часть 9б «Хранилище»): свой кластер в песочнице задачи.

Решение по итогам спайка B0 (проверка подхода до кода):
- двоичные файлы — только из доверенных папок Homebrew (find_bin), PATH не используется;
- шаблон кластера `.sandbox/pgtpl-<major>-<hash>/data` делает один раз родитель: initdb под
  sandbox-exec с записью только в папку шаблона, роли runner и база vault со схемой ops;
- на задачу (`PgService`, через Task.service) — APFS-клон шаблона в box/.termit/pg/data и
  postgres под `shell_run.server_profile` (профиль песочницы + запуск только самого postgres),
  только unix-сокет в box/.termit (listen_addresses='', своё имя сокета — не 5432), сид от
  имени runner, затем суперпользователь закрыт через pg_hba.conf и SIGHUP;
- psql родителя (сид, снимок для проверки) — под `shell_run.reader_profile` (записи нет, запуск
  только psql);
- остановка: SIGINT → SIGQUIT → SIGKILL, затем подметание SysV — ТОЛЬКО своих сегмента и
  семафоров (владелец — мы, создатель мёртв и он — наш postmaster, ключ из диапазона нашего
  каталога данных, у семафоров GETVAL 537 и GETPID нашего postmaster). Лимит shmmni=32 общий
  на всю машину, утечки ударили бы и по рабочему серверу владельца;
- без sandbox-exec postgres не запускается никогда (usable/why_not, PgService.start).

Рабочий PostgreSQL владельца (brew services, /tmp/.s.PGSQL.5432) этот модуль не знает и не
трогает: ни соединений, ни сигналов. Его семафоры и сегмент не проходят ни одной сверки выше."""
import ctypes
import fcntl
import hashlib
import json
import os
import pwd
import re
import select
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from termit_app import paths

# --- Где искать и как называть ----------------------------------------------------------------

BIN_DIRS = ("/opt/homebrew/opt/postgresql@18/bin", "/opt/homebrew/bin", "/usr/local/bin")
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
IPCS, IPCRM = "/usr/bin/ipcs", "/usr/bin/ipcrm"
NEEDED = ("postgres", "initdb", "psql")

PORT = 54329                     # только имя сокета (.s.PGSQL.<PORT>): TCP закрыт, и не 5432
SOCK_NAME = f".s.PGSQL.{PORT}"
PG_DIR = ".termit/pg"            # то же, что shell_run.PG_DIR: zsh писать сюда не может
# сокет — в той же папке (ревью B1, M1): подменить его из zsh нельзя ни записью в папку, ни
# переименованием box/.termit (оба запрета — shell_run._pg_guard); подключаться можно
SOCK_REL = PG_DIR + "/" + SOCK_NAME
MAX_SOCK_PATH = 100              # sun_path на macOS — 104 байта, берём с запасом
SUPERUSER, RUNNER, DATABASE = "termit", "runner", "vault"
NOPGPASS = ".termit/nopgpass"    # PGPASSFILE: путь, которого нет (B0: /dev/null шумит)

# Ключи старта (план «PostgreSQL в песочнице», п. 2; B0: DSM в файлах data/pg_dynshmem, а не
# объекты /PostgreSQL.* вне box, — иначе после SIGKILL они живут до перезагрузки)
SERVER_OPTS = (
    ("listen_addresses", ""), ("port", str(PORT)), ("unix_socket_permissions", "0700"),
    ("max_connections", "12"), ("shared_buffers", "16MB"), ("fsync", "off"),
    ("synchronous_commit", "off"), ("full_page_writes", "off"), ("autovacuum", "off"),
    ("jit", "off"), ("huge_pages", "off"), ("logging_collector", "off"),
    ("dynamic_shared_memory_type", "mmap"), ("timezone", "UTC"), ("log_timezone", "UTC"),
)
INITDB_ARGS = ("-U", SUPERUSER, "-A", "trust", "-E", "UTF8", "--locale=C", "-N",
               "--wal-segsize=1", "--no-instructions")
TEMPLATE_SQL = (
    f"CREATE ROLE {RUNNER} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;\n"
    f"CREATE DATABASE {DATABASE} OWNER {RUNNER};\n"
    f"\\connect {DATABASE}\n"
    f"CREATE SCHEMA ops AUTHORIZATION {RUNNER};\n"
)
# после сида: runner — только в свою базу, остальное (и termit) — отказ
HBA_SEALED = f"local {DATABASE} {RUNNER} trust\nlocal all all reject\n"
TEMPLATE_VERSION = 1             # меняется — шаблон пересобирается (hash конфигурации)

START_WAIT = 10.0
STOP_INT, STOP_QUIT = 5.0, 2.0
SEAL_WAIT = 3.0
PSQL_TIMEOUT = 5.0
PSQL_CAP = 8 * 1024 * 1024
RESET_EVERY = 2.0                # service_reset — не чаще (судья)

PGSEMAMAGIC = 537                # PostgreSQL: значение последнего семафора набора
GETPID, GETVAL = 4, 5            # sys/sem.h на macOS
SEM_KEY_SPAN = 64                # ключи семафоров — сразу после ключа сегмента (+1, +2, …)

# время старта postmaster: снимок сверяет его с запомненным (тот ли сервер ответил)
STAMP_SQL = "SELECT pg_catalog.pg_postmaster_start_time()::text"

MSG_BROKEN = "База повреждена — набери reset, соберу её заново."
MSG_DOWN = "Сервер базы не отвечает — набери reset, подниму его заново."


class PgError(RuntimeError):
    """Сервер не поднять, сид не прошёл, psql не запустить: текст — для журнала и игрока."""


# --- Двоичные файлы и годность ------------------------------------------------------------------

def _inside(path: str, root) -> bool:
    root = os.path.realpath(str(root))
    return path == root or path.startswith(root.rstrip("/") + "/")


def find_bin(name: str) -> Optional[str]:
    """Настоящий путь программы PostgreSQL — ТОЛЬКО из BIN_DIRS, по порядку (как
    implants.brew_path): обычный исполняемый файл, владелец — пользователь или root, ни путь,
    ни то, куда ведёт ссылка, не в проекте и не в песочнице. Иначе None."""
    for d in BIN_DIRS:
        cand = os.path.join(d, name)
        real = os.path.realpath(cand)
        try:
            st = os.stat(real)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode) or not os.access(real, os.X_OK):
            continue
        if st.st_uid not in (os.getuid(), 0):
            continue
        if any(_inside(x, r) for x in (os.path.abspath(cand), real)
               for r in (paths.ROOT, paths.SANDBOX_ROOT)) or "/.termit/" in real + "/":
            continue
        return real
    return None


def sock_dir(box) -> Path:
    """Папка сокета сервера задачи (PGHOST): box/.termit/pg."""
    return Path(box) / PG_DIR


def sock_path(box) -> Path:
    return Path(box) / SOCK_REL


def path_fits(box) -> bool:
    """Влезает ли путь сокета (и его .lock) в sun_path."""
    return len(os.fsencode(str(sock_path(box)))) < MAX_SOCK_PATH


MSG_NO_PG = "нужен учебный сервер PostgreSQL: ./termit implants install pg"
MSG_OFF = "учебный сервер PostgreSQL выключен (TERMIT_NO_PG)"
MSG_NO_SANDBOX = "учебный сервер PostgreSQL живёт только в песочнице (sandbox-exec)"
MSG_LONG = "путь к игре слишком длинный для сокета учебного сервера: перенеси папку игры повыше"


def why_not(root=None, box=None) -> Optional[str]:
    """Почему учебный сервер недоступен (текст для missing()) или None — годен. Без
    sandbox-exec, под TERMIT_NO_PG (и --no-sandbox: cli ставит его сам) — недоступен. Длина
    сокета — для box, если он дан, иначе для образца песочницы в root."""
    if os.environ.get("TERMIT_NO_PG"):
        return MSG_OFF
    if not os.path.isfile(SANDBOX_EXEC):
        return MSG_NO_SANDBOX
    if any(find_bin(n) is None for n in NEEDED):
        return MSG_NO_PG
    from termit_app import sandbox
    if not path_fits(box if box is not None else sandbox.sample_box(root)):
        return MSG_LONG
    return None


def usable(root=None) -> bool:
    return why_not(root) is None


# --- Окружение и запуск под песочницей ---------------------------------------------------------

def _base_env(box) -> Dict[str, str]:
    """Минимальное окружение сервера и psql родителя: без переменных владельца (PGHOST,
    PGPASSWORD и т.п. из его оболочки сюда не попадают), часовой пояс и язык — фиксированы."""
    box = Path(box)
    return {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C", "TZ": "UTC",
            "HOME": str(box / PG_DIR), "TMPDIR": str(box / ".termit" / "tmp") + "/",
            "PGPASSFILE": str(box / NOPGPASS), "PGSYSCONFDIR": str(box / NOPGPASS),
            "PSQLRC": "/dev/null", "PSQL_HISTORY": "/dev/null"}


def _home() -> Path:
    return Path.home()


def _start_postgres(box, data: Path, log_fd: int, postgres: str,
                    sockdir: Optional[Path] = None) -> subprocess.Popen:
    from termit_app import shell_run
    argv = [SANDBOX_EXEC, "-p", shell_run.server_profile(Path(box), _home(), postgres),
            postgres, "-D", str(data), "-k", str(sockdir or sock_dir(box))]
    for k, v in SERVER_OPTS:
        argv += ["-c", f"{k}={v}"]
    return subprocess.Popen(argv, cwd=str(data), env=_base_env(box), stdin=subprocess.DEVNULL,
                            stdout=log_fd, stderr=log_fd, start_new_session=True)


def _read_pid_file(data: Path) -> Optional[List[str]]:
    """Строки postmaster.pid (обычный файл, не ссылка, не больше 4 КБ) или None."""
    from termit_app import sandbox
    raw = sandbox.read_box_file(data / "postmaster.pid", 4096)
    if raw is None:
        return None
    return raw.decode("utf-8", errors="replace").splitlines()


def _wait_ready(proc: subprocess.Popen, data: Path, timeout: float = START_WAIT) -> List[str]:
    """Ждать «ready» в postmaster.pid ВМЕСТЕ с pid нашего ребёнка в строке 1 (B0: после
    падения там остаётся старое «ready»). Сервер вышел или срок истёк — PgError."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise PgError(f"postgres вышел при старте (код {proc.returncode})")
        lines = _read_pid_file(data)
        if lines and len(lines) >= 8 and lines[0].strip() == str(proc.pid) \
                and lines[7].strip() == "ready":
            return lines
        time.sleep(0.01)
    raise PgError("postgres так и не поднялся — время вышло")


def _shm_of(lines: Sequence[str]) -> Tuple[Optional[int], Optional[int]]:
    """(ключ, id) сегмента из строки 7 postmaster.pid."""
    try:
        key, sid = lines[6].split()
        return int(key), int(sid)
    except (IndexError, ValueError):
        return None, None


def psql(box, psql_bin: str, args: Sequence[str], stdin: Optional[bytes] = None,
         env_extra: Optional[Dict[str, str]] = None, timeout: float = PSQL_TIMEOUT,
         cap: int = PSQL_CAP, sockdir: Optional[Path] = None) -> Tuple[int, bytes, bytes]:
    """Доверенный psql под профилем-читателем: (код, stdout, stderr). Вывод больше cap или
    дольше timeout — процесс убит, код -1. Хост — только сокет box (-h), настроек владельца
    (~/.psqlrc, ~/.pgpass, сервисы) нет."""
    from termit_app import shell_run
    if not os.path.isfile(SANDBOX_EXEC):
        raise PgError(MSG_NO_SANDBOX)
    argv = [SANDBOX_EXEC, "-p", shell_run.reader_profile(Path(box), _home(), psql_bin),
            psql_bin, "-X", "-q", "-w", "-h", str(sockdir or sock_dir(box)), "-p", str(PORT)]
    argv += list(args)
    env = _base_env(box)
    env.update(env_extra or {})
    try:
        proc = subprocess.Popen(argv, cwd="/", env=env,
                                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
    except OSError as e:
        raise PgError(f"psql не запустился: {e}") from None
    out, err = _collect(proc, stdin, timeout, cap)
    return (proc.returncode if proc.returncode is not None else -1), out, err


def _collect(proc: subprocess.Popen, stdin: Optional[bytes], timeout: float,
             cap: int) -> Tuple[bytes, bytes]:
    """Вывод процесса с пределом размера и времени (сервер — наш, но таблицы в нём — игрока)."""
    end = time.monotonic() + timeout
    out, err = bytearray(), bytearray()
    pending = memoryview(stdin) if stdin else None
    if proc.stdin is not None and not pending:
        proc.stdin.close()
    streams = {proc.stdout.fileno(): out, proc.stderr.fileno(): err}
    for fd in streams:
        os.set_blocking(fd, False)
    if proc.stdin is not None and pending:
        os.set_blocking(proc.stdin.fileno(), False)
    killed = False
    while streams or (pending is not None and len(pending)):
        left = end - time.monotonic()
        if left <= 0:
            killed = True
            break
        wfds = [proc.stdin.fileno()] if pending is not None and len(pending) else []
        r, w, _ = select.select(list(streams), wfds, [], min(left, 0.5))
        if w:
            try:
                n = os.write(w[0], pending[:65536])
                pending = pending[n:]
            except (BrokenPipeError, OSError):
                pending = None
            if pending is None or not len(pending):
                proc.stdin.close()
                pending = None
        for fd in r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                streams.pop(fd)
                continue
            streams[fd].extend(chunk)
            if len(out) > cap or len(err) > cap:
                killed = True
                break
        if killed:
            break
    if killed:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    for f in (proc.stdout, proc.stderr, proc.stdin):
        try:
            if f is not None:
                f.close()
        except OSError:
            pass
    if killed:
        proc.returncode = -1
    return bytes(out), bytes(err)


# --- Подметание SysV (B0, поправка 1) ----------------------------------------------------------

def _me() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def _ipcs(kind: str) -> List[List[str]]:
    """Строки `ipcs -<m|s> -a` нужного вида (поля через пробелы); ошибка — пусто."""
    try:
        out = subprocess.run([IPCS, "-" + kind, "-a"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=5, env={"PATH": "/usr/bin:/bin",
                                                                        "LC_ALL": "C"}).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.split() for line in out.decode("utf-8", "replace").splitlines()
            if line.split()[:1] == [kind]]


def _key(text: str) -> Optional[int]:
    try:
        return int(text, 16 if text.lower().startswith("0x") else 10) & 0xFFFFFFFF
    except ValueError:
        return None


_libc = None


def _semctl(semid: int, num: int, cmd: int) -> int:
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        _libc.semctl.restype = ctypes.c_int
    return int(_libc.semctl(ctypes.c_int(semid), ctypes.c_int(num), ctypes.c_int(cmd)))


def alive(pid: int) -> bool:
    """Процесс есть (свой, чужой или зомби) — да; ESRCH — нет."""
    if not isinstance(pid, int) or pid <= 1:
        return True                     # плохой pid — считаем живым: подметать нельзя
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def owned_ipc(pid: int, shmkey: int, shmid: Optional[int] = None) -> Tuple[List[int], List[int]]:
    """(id сегментов, id наборов семафоров), созданных НАШИМ postmaster pid: владелец — мы;
    сегмент — с этим ключом (и id, если он известен), создатель (CPID) = pid, NATTCH 0;
    семафоры — ключ сразу после ключа сегмента, у последнего семафора набора GETVAL = 537
    (PGSemaMagic) и GETPID = pid. Пока pid жив — пусто всегда: живому серверу ничего не
    подметаем (так же решает сам PostgreSQL).
    Принятый остаток (ревью B1, M2): между «pid мёртв» и semctl/ipcrm pid может достаться
    новому процессу. Чтобы этим задеть чужое, новый владелец pid должен ещё и создать набор с
    ключом из диапазона нашей data и GETVAL 537 — практически недостижимо."""
    if shmkey is None or alive(pid):
        return [], []
    me, base = _me(), shmkey & 0xFFFFFFFF
    shm, sems = [], []
    for f in _ipcs("m"):
        # T ID KEY MODE OWNER GROUP CREATOR CGROUP NATTCH SEGSZ CPID LPID …
        if len(f) < 11:
            continue
        try:
            sid, nattch, cpid = int(f[1]), int(f[8]), int(f[10])
        except ValueError:
            continue
        if (_key(f[2]) == base and (shmid is None or sid == shmid) and f[4] == me
                and f[6] == me and cpid == pid and nattch == 0):
            shm.append(sid)
    for f in _ipcs("s"):
        # T ID KEY MODE OWNER GROUP CREATOR CGROUP NSEMS OTIME CTIME
        if len(f) < 9:
            continue
        try:
            semid, nsems = int(f[1]), int(f[8])
        except ValueError:
            continue
        k = _key(f[2])
        if k is None or f[4] != me or f[6] != me or nsems < 1:
            continue
        if not 0 < (k - base) & 0xFFFFFFFF <= SEM_KEY_SPAN:
            continue
        if _semctl(semid, nsems - 1, GETVAL) == PGSEMAMAGIC and \
                _semctl(semid, nsems - 1, GETPID) == pid:
            sems.append(semid)
    return shm, sems


def sweep(pid: int, shmkey: Optional[int], shmid: Optional[int] = None) -> Tuple[int, int]:
    """Убрать утёкшие сегмент и семафоры нашего мёртвого postmaster (owned_ipc). Вернуть
    (сколько сегментов, сколько наборов) удалено."""
    shm, sems = owned_ipc(pid, shmkey, shmid)
    done_m = done_s = 0
    for kind, ids in (("-m", shm), ("-s", sems)):
        for i in ids:
            try:
                rc = subprocess.run([IPCRM, kind, str(i)], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=5,
                                    env={"PATH": "/usr/bin:/bin"}).returncode
            except (OSError, subprocess.SubprocessError):
                rc = 1
            if rc == 0:
                if kind == "-m":
                    done_m += 1
                else:
                    done_s += 1
    return done_m, done_s


def _wait_detached(shmkey: Optional[int], shmid: Optional[int], timeout: float = 3.0) -> None:
    """После гибели postmaster его дети выходят сами (B0: <0,5 с): ждём NATTCH 0 сегмента."""
    if shmkey is None:
        return
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        busy = [f for f in _ipcs("m") if len(f) > 8 and _key(f[2]) == shmkey & 0xFFFFFFFF
                and (shmid is None or f[1] == str(shmid)) and f[8] != "0"]
        if not busy:
            return
        time.sleep(0.05)


# --- Шаблон кластера ----------------------------------------------------------------------------

def _major(postgres: str) -> str:
    m = re.search(r"postgresql@(\d+)", postgres) or re.search(r"/(\d+)(?:\.\d+)*/bin/", postgres)
    return m.group(1) if m else "x"


def template_key(bins: Dict[str, str]) -> str:
    """Имя шаблона: pgtpl-<major>-<hash>; hash — от версии конфигурации, настоящих путей и
    отметок файлов программ: после brew upgrade (другой Cellar/…/18.x) шаблон новый."""
    parts = [TEMPLATE_VERSION, list(INITDB_ARGS), TEMPLATE_SQL, list(SERVER_OPTS)]
    for name in sorted(bins):
        st = os.stat(bins[name])
        parts.append([name, bins[name], st.st_size, st.st_mtime_ns])
    digest = hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()[:12]
    return f"pgtpl-{_major(bins['postgres'])}-{digest}"


_BUILD_NAME = re.compile(r"^pgtpl-build-[A-Za-z0-9_]{8}$")
READY_MARK = "termit-template"


def _bins() -> Dict[str, str]:
    out = {}
    for n in NEEDED:
        b = find_bin(n)
        if b is None:
            raise PgError(MSG_NO_PG)
        out[n] = b
    return out


def template(root=None) -> Path:
    """Папка готового шаблона (в ней data/). Нет — собрать под блокировкой flock."""
    root = Path(root if root is not None else paths.SANDBOX_ROOT)
    bins = _bins()
    final = root / template_key(bins)
    if (final / READY_MARK).is_file() and not final.is_symlink():
        return final
    root.mkdir(parents=True, exist_ok=True)
    lock = os.open(str(root / "pgtpl.lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (final / READY_MARK).is_file() and not final.is_symlink():
            return final
        _drop_builds(root)
        build = Path(tempfile.mkdtemp(prefix="pgtpl-build-", dir=str(root)))
        try:
            _build_template(build, bins)
            os.rename(build, final)
        except BaseException:
            shutil.rmtree(build, ignore_errors=True)
            raise
        return final
    finally:
        os.close(lock)


def _drop_builds(root: Path) -> None:
    """Недостроенные шаблоны прошлых запусков (упали посреди сборки): только точное имя
    pgtpl-build-XXXXXXXX и только настоящая папка, под той же блокировкой."""
    for e in os.scandir(root):
        if _BUILD_NAME.match(e.name) and e.is_dir(follow_symlinks=False):
            shutil.rmtree(root / e.name, ignore_errors=True)


def _build_template(build: Path, bins: Dict[str, str]) -> None:
    from termit_app import shell_run
    (build / ".termit" / "tmp").mkdir(parents=True)
    # сокет сборки — короткий путь build/s: имя папки сборки длиннее box-XXXXXXXX, а sun_path
    # ограничен (путь задачи проверяет why_not, путь сборки — нет)
    sockdir = build / "s"
    sockdir.mkdir(mode=0o700)
    data = build / "data"
    prof = shell_run.sandbox_profile(build, _home(), clipboard=False, gui=False, ttys=())
    env = _base_env(build)
    rc = subprocess.run([SANDBOX_EXEC, "-p", prof, bins["initdb"], "-D", str(data)]
                        + list(INITDB_ARGS), cwd=str(build), env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
    if rc.returncode != 0:
        raise PgError("initdb не прошёл: " + rc.stderr.decode("utf-8", "replace")[-300:])
    srv = _Server(build, data, bins, sockdir=sockdir)
    srv.launch()
    try:
        code, _, err = psql(build, bins["psql"], ["-U", SUPERUSER, "-d", "postgres",
                                                  "-v", "ON_ERROR_STOP=1", "-f", "-"],
                            stdin=TEMPLATE_SQL.encode("utf-8"), sockdir=sockdir)
        if code != 0:
            raise PgError("шаблон: " + err.decode("utf-8", "replace")[-300:])
    finally:
        srv.halt()
    if (data / "postmaster.pid").exists():
        raise PgError("шаблон: сервер не остановился штатно")
    shutil.rmtree(build / ".termit", ignore_errors=True)
    shutil.rmtree(sockdir, ignore_errors=True)
    (build / READY_MARK).write_text("ok\n")


# --- Сервер ---------------------------------------------------------------------------------------

class _Server:
    """Один запуск postgres над папкой данных (без сида и печати): старт, остановка, подметание.
    box — корень песочницы (в нём сокет и профиль), data — папка кластера внутри box."""

    def __init__(self, box: Path, data: Path, bins: Dict[str, str],
                 sockdir: Optional[Path] = None):
        self.box, self.data, self.bins = Path(box), Path(data), bins
        self.sockdir = Path(sockdir) if sockdir else sock_dir(box)
        self.proc: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.shmkey: Optional[int] = None
        self.shmid: Optional[int] = None
        self.sock_ino: Optional[Tuple[int, int]] = None
        self.clean = True               # последняя остановка — штатная (SIGINT)

    def launch(self) -> None:
        if not os.path.isfile(SANDBOX_EXEC):
            raise PgError(MSG_NO_SANDBOX)
        log = self.data.parent / "server.log"
        fd = os.open(str(log), os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            self.proc = _start_postgres(self.box, self.data, fd, self.bins["postgres"],
                                        self.sockdir)
        finally:
            os.close(fd)
        self.pid = self.proc.pid
        try:
            lines = _wait_ready(self.proc, self.data)
        except PgError:
            self.halt()
            raise
        self.shmkey, self.shmid = _shm_of(lines)
        try:
            st = os.lstat(self.sockdir / SOCK_NAME)
            if stat.S_ISSOCK(st.st_mode):
                self.sock_ino = (st.st_dev, st.st_ino)
        except OSError:
            self.sock_ino = None

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def halt(self) -> None:
        """SIGINT (быстрая остановка) → SIGQUIT → SIGKILL; затем подметание своего SysV и
        своего сокета. Повторный вызов безопасен."""
        proc, self.proc = self.proc, None
        if proc is None:
            return
        self.clean = True
        for sig, wait in ((signal.SIGINT, STOP_INT), (signal.SIGQUIT, STOP_QUIT),
                          (signal.SIGKILL, 5.0)):
            if proc.poll() is not None:
                break
            if sig != signal.SIGINT:
                self.clean = False
            try:
                proc.send_signal(sig)
            except OSError:
                pass
            try:
                proc.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                continue
        if proc.returncode is None or proc.returncode != 0:
            self.clean = False
        if not self.clean:
            _wait_detached(self.shmkey, self.shmid)
        if self.pid is not None:
            sweep(self.pid, self.shmkey, self.shmid)
        self._drop_socket()

    def _drop_socket(self) -> None:
        """Удалить только свой сокет (по inode) и его .lock; чужое на этом месте не трогаем."""
        if self.sock_ino is None:
            return
        path = self.sockdir / SOCK_NAME
        try:
            st = os.lstat(path)
            if stat.S_ISSOCK(st.st_mode) and (st.st_dev, st.st_ino) == self.sock_ino:
                os.unlink(path)
        except OSError:
            pass
        lock = Path(str(path) + ".lock")
        try:
            if stat.S_ISREG(os.lstat(lock).st_mode) and self._lock_ours(lock):
                os.unlink(lock)
        except OSError:
            pass
        self.sock_ino = None

    def _lock_ours(self, lock: Path) -> bool:
        from termit_app import sandbox
        raw = sandbox.read_box_file(lock, 4096)
        return bool(raw) and raw.split(b"\n", 1)[0].strip() == str(self.pid).encode()


def _clone(src: Path, dst: Path) -> None:
    """APFS-клон папки (cp -c -R); не вышло — обычная копия."""
    try:
        rc = subprocess.run(["/bin/cp", "-c", "-R", str(src), str(dst)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=60, env={"PATH": "/usr/bin:/bin"}).returncode
    except (OSError, subprocess.SubprocessError):
        rc = 1
    if rc != 0:
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, symlinks=True)
    os.chmod(dst, 0o700)


def _pg_dir(box) -> Path:
    """box/.termit/pg — настоящая папка (не ссылка), создаётся родителем."""
    box = Path(box)
    t = box / ".termit"
    if not stat.S_ISDIR(os.lstat(t).st_mode):
        raise PgError("служебная папка песочницы не папка")
    pg = box / PG_DIR
    try:
        os.mkdir(pg, 0o700)
    except FileExistsError:
        pass
    st = os.lstat(pg)
    if not stat.S_ISDIR(st.st_mode):
        raise PgError("box/.termit/pg — не папка")
    return pg


class PgService:
    """Сервер PostgreSQL задачи — сервис родителя (Task.service): start() до zsh, stop() — в
    finally (и до sandbox.reap), reset() — по просьбе судьи (reset в песочнице). seed — текст
    SQL (dbkit.pg_seed): держит только родитель, в песочницу он не пишется."""

    def __init__(self, box, seed: str, root=None):
        self.box = Path(box)
        self.seed = seed
        self.root = root
        self._srv: Optional[_Server] = None
        self.bins: Optional[Dict[str, str]] = None
        self.last_reset = 0.0
        self.started = False
        # время старта своего postmaster (pg_postmaster_start_time) — запомнено сразу после
        # старта: снимок сверяет его в том же соединении (ревью B1, M1)
        self.stamp: Optional[str] = None
        # reset идёт в потоке судьи, stop — в главном (zsh закрыли посреди reset): по очереди
        self._lock = threading.RLock()

    # --- жизнь ---

    @property
    def data(self) -> Path:
        return self.box / PG_DIR / "data"

    @property
    def pid(self) -> Optional[int]:
        return self._srv.pid if self._srv else None

    def start(self) -> None:
        with self._lock:
            self._start()

    def _start(self) -> None:
        why = why_not(self.root, self.box)
        if why:
            raise PgError(why)
        self.bins = _bins()
        tpl = template(self.root)
        _pg_dir(self.box)
        if os.path.lexists(self.data):
            self._drop_data()
        _clone(tpl / "data", self.data)
        srv = _Server(self.box, self.data, self.bins)
        self._srv = srv
        srv.launch()
        try:
            self._load_seed()
            self._seal()
            self.stamp = self._stamp()
        except BaseException:
            srv.halt()
            raise
        self.started = True

    def stop(self) -> None:
        with self._lock:
            srv = self._srv
            if srv is not None:
                srv.halt()
            self.started = False
            self.stamp = None

    def reset(self) -> None:
        """Стоп, данные — заново из шаблона, старт, сид (судья: op service_reset)."""
        with self._lock:
            self.last_reset = time.monotonic()
            self.stop()
            self._start()

    def _drop_data(self) -> None:
        pg = self.box / PG_DIR
        if not stat.S_ISDIR(os.lstat(pg).st_mode):
            raise PgError("box/.termit/pg — не папка")
        st = os.lstat(self.data)
        if stat.S_ISDIR(st.st_mode):
            shutil.rmtree(self.data)        # Python 3.9 на macOS: по дескрипторам, без ссылок
        else:
            os.unlink(self.data)

    def _load_seed(self) -> None:
        """Сид — от runner (SET ROLE); строки до метки SEED_AS_RUNNER (лишние пустые базы,
        CREATE DATABASE вне транзакции) — от суперпользователя. Сид пишет только родитель."""
        from termit_app.tasks.dbkit import SEED_AS_RUNNER
        head, mark, tail = self.seed.partition(SEED_AS_RUNNER + "\n")
        if not mark:
            head, tail = "", self.seed
        body = head + f"SET ROLE {RUNNER};\n" + tail + "\n"
        code, _, err = self.run_psql(["-U", SUPERUSER, "-d", DATABASE, "-v", "ON_ERROR_STOP=1",
                                      "-f", "-"], stdin=body.encode("utf-8"), timeout=30)
        if code != 0:
            raise PgError("сид не загрузился: " + err.decode("utf-8", "replace")[-300:])

    def _seal(self) -> None:
        """Суперпользователь закрыт: pg_hba.conf — только runner в vault, SIGHUP своему
        postmaster, ждём первого отказа termit."""
        from termit_app import sandbox
        sandbox.write_box_file(self.box, f"{PG_DIR}/data/pg_hba.conf", HBA_SEALED, mode=0o600)
        os.kill(self._srv.pid, signal.SIGHUP)
        end = time.monotonic() + SEAL_WAIT
        while time.monotonic() < end:
            code, _, err = self.run_psql(["-U", SUPERUSER, "-d", "postgres", "-c", "SELECT 1"])
            if code != 0 and b"pg_hba.conf" in err:
                return
            time.sleep(0.01)
        raise PgError("суперпользователь не закрылся")

    def _stamp(self) -> str:
        code, out, err = self.run_psql(["-U", RUNNER, "-d", DATABASE, "-At", "-c",
                                        STAMP_SQL])
        stamp = out.decode("utf-8", "replace").strip()
        if code != 0 or not stamp:
            raise PgError("время старта сервера не прочитать: "
                          + err.decode("utf-8", "replace")[-200:])
        return stamp

    # --- запросы родителя ---

    def socket_ok(self) -> bool:
        """Сокет на месте и это тот самый, что поднял наш сервер (по inode)."""
        srv = self._srv
        if srv is None or srv.sock_ino is None or not srv.running():
            return False
        try:
            st = os.lstat(sock_path(self.box))
        except OSError:
            return False
        return stat.S_ISSOCK(st.st_mode) and (st.st_dev, st.st_ino) == srv.sock_ino

    def run_psql(self, args: Sequence[str], stdin: Optional[bytes] = None,
                 env_extra: Optional[Dict[str, str]] = None,
                 timeout: float = PSQL_TIMEOUT) -> Tuple[int, bytes, bytes]:
        if self.bins is None or self._srv is None:
            raise PgError(MSG_DOWN)
        return psql(self.box, self.bins["psql"], args, stdin=stdin, env_extra=env_extra,
                    timeout=timeout)


# --- Брошенный сервер (игра упала): sandbox.destroy / cleanup_stale ----------------------------

def stale_info(box) -> Optional[Tuple[int, Optional[int], Optional[int]]]:
    """(pid, ключ, id сегмента) из postmaster.pid брошенного кластера box или None. Ключ
    принимается, только если он из диапазона inode НАШЕЙ папки data (PostgreSQL берёт ключ
    от неё): подложенный postmaster.pid с чужим ключом (рабочего сервера владельца) — мимо."""
    data = Path(box) / PG_DIR / "data"
    try:
        st = os.lstat(data)
    except OSError:
        return None
    if not stat.S_ISDIR(st.st_mode):
        return None
    lines = _read_pid_file(data)
    if not lines:
        return None
    try:
        pid = int(lines[0].strip())
    except (ValueError, IndexError):
        return None
    key, sid = _shm_of(lines)
    if key is not None and not 0 <= (key - st.st_ino) & 0xFFFFFFFF <= SEM_KEY_SPAN:
        key, sid = None, None
    return pid, key, sid


def stop_stale(box) -> Optional[Tuple[int, Optional[int], Optional[int]]]:
    """Перед sandbox.reap: брошенному postmaster этой песочницы (заперт в её профиле) —
    SIGINT и ожидание, чтобы он сам убрал SysV. Вернуть stale_info для sweep_stale."""
    from termit_app import sandbox
    info = stale_info(box)
    if info is None:
        return None
    pid = info[0]
    if pid > 1 and sandbox.caged_in(pid, box):
        try:
            os.kill(pid, signal.SIGINT)
        except OSError:
            pass
        end = time.monotonic() + STOP_INT
        while time.monotonic() < end and alive(pid):
            time.sleep(0.05)
    return info


def sweep_stale(info) -> Tuple[int, int]:
    """После sandbox.reap: подмести SysV брошенного сервера (только если его pid мёртв)."""
    if not info:
        return 0, 0
    pid, key, sid = info
    if key is None:
        return 0, 0
    _wait_detached(key, sid)
    return sweep(pid, key, sid)


