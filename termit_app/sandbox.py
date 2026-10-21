"""Песочница поручения: папка с файлами задачи и служебная папка .termit/."""
import base64
import contextvars
import ctypes
import fcntl
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from termit_app import box_names, paths
from termit_app.tasks import kit
from termit_app.tasks.base import Cmd, Ctx

# Обёртки зовут модули игры через paths.py_line: python -I -B с явным корнем (решение 12).
OPEN_STUB = """#!/bin/sh
# Trainer wrapper around open: lets through only the lesson forms (task files and folders in
# Finder, TextEdit, Preview), logs the call and hands it to the real open.
{run}
"""

MKTEMP_STUB = """#!/bin/sh
# On macOS mktemp without a template (and with -t) uses the system temp folder, not $TMPDIR,
# and the sandbox cannot write there. Send it to the sandbox $TMPDIR.
skip=
for a in "$@"; do
  if [ -n "$skip" ]; then skip=; continue; fi
  case $a in
    -p*) exec /usr/bin/mktemp "$@" ;;
    -t) skip=1 ;;
    -*) ;;
    *) exec /usr/bin/mktemp "$@" ;;
  esac
done
exec /usr/bin/mktemp -p "${TMPDIR:-$TERMIT_BOX/.termit/tmp}" "$@"
"""


PROCVIEW_STUB = """#!/bin/sh
# Training {name}: the real one (setuid) does not run under sandbox-exec.
{run}
"""


BREW_STUB = """#!/bin/sh
# Training brew: the sandbox has no network and cannot install programs on the machine.
# Searches and shows formulae, "installs" for pretend, logs the call to .termit/brew.log.
{run}
"""


AV_STUB = """#!/bin/sh
# Training clamscan: trimmed ClamAV databases, runs and downloads nothing,
# logs the call to .termit/av.log.
{run}
"""


SHELLCHECK_STUB = """#!/bin/sh
# Training shellcheck: knows a few checks, runs and downloads nothing.
{run}
"""


CRONTAB_STUB = """#!/bin/sh
# Training crontab: the schedule lives in the sandbox .termit/crontab, the owner's real
# crontab is never touched.
{run}
"""


def _stubs() -> dict:
    """Обёртки в .termit/bin — она в PATH песочницы впереди системных."""
    from termit_app import implants
    out = {"open": OPEN_STUB.format(run=paths.py_line("termit_app.openwrap")),
           "mktemp": MKTEMP_STUB}
    for name in ("ps", "top"):
        out[name] = PROCVIEW_STUB.format(name=name,
                                         run=paths.py_line("termit_app.procview", name))
    out[implants.STUB_NAME] = BREW_STUB.format(run=paths.py_line("termit_app.brewstub"))
    return out


def pin_python(box, task) -> None:
    """Задаче с pinned_python (часть 7, A1) — python3 и python3.X в .termit/bin: симлинки на
    настоящий путь интерпретатора треков. .termit/bin первым в PATH песочницы, а reset его не
    трогает — venv игрока (pyvenv.cfg: home = .termit/bin) переживает reset."""
    if not getattr(task, "pinned_python", False):
        return
    from termit_app import pyenvs
    info = pyenvs.track_python()
    if info is None:
        return
    fd = _open_dirs(box, [".termit", "bin"])
    try:
        for name in pyenvs.pin_names(info):
            os.symlink(info.path, name, dir_fd=fd)
    finally:
        os.close(fd)
    # python, pip и pip3 вне venv — тот же интерпретатор (I1 ревью P1): иначе pip3 из PATH
    # (Homebrew, conda, шим CLT без Command Line Tools) ставил бы не туда. pip — не бинарник,
    # поэтому sh-обёртка «python3 -m pip», а не ссылка; в venv впереди его собственные.
    py3 = shlex.quote(str(Path(box) / ".termit" / "bin" / "python3"))
    for name, body in pin_wrappers(py3).items():
        write_box_file(box, f".termit/bin/{name}", body, mode=0o755)
    if getattr(task, "track", "") in OUT_LOG_TRACKS:
        site = user_site(info.short)
        os.close(_open_dirs(box, site.split("/"), create=True))
        write_box_file(box, site + "/usercustomize.py", OUT_LOG_HOOK)


# Треки Python (часть 10): хвост ошибки скрипта — в .termit/out.log, родитель берёт оттуда
# только тип ошибки из белого списка (pykit.TRACEBACK_TYPES)
OUT_LOG_TRACKS = ("py", "pydata")


def user_site(short: str) -> str:
    """Пользовательский site закреплённого python3 в доме песочницы (сборка-framework macOS:
    ~/Library/Python/X.Y/lib/python/site-packages) — путь от корня песочницы."""
    return f".termit/home/Library/Python/{short}/lib/python/site-packages"


# usercustomize.py в пользовательском site песочницы: Python игрока сам грузит его при старте
# (вне venv; хук, обёртки и recheck идут с -I и его не видят). Только для запуска
# «python3 файл.py»: REPL (argv ['']), -c и -m не трогаются. stderr остаётся как есть —
# ошибка печатается обычным путём, затем последние 4 КБ traceback пишутся в out.log.
OUT_LOG_HOOK = '''"""termit: последняя ошибка скрипта (python3 файл.py) — в $TERMIT_BOX/.termit/out.log.

Тренажёр читает оттуда только тип ошибки (NameError, KeyError…), чтобы подсказать, где
смотреть. Скрипт и его вывод это не меняет. Файл можно удалить — подсказки станут общими."""


def _termit_out_log():
    import os
    import sys
    box = os.environ.get("TERMIT_BOX")
    first = sys.argv[0] if sys.argv else ""
    if not box or not first.endswith(".py"):
        return
    path = os.path.join(box, ".termit", "out.log")
    previous = sys.excepthook

    def hook(kind, value, tb):
        previous(kind, value, tb)
        try:
            import traceback
            # последняя строка (тип: суть) — целиком, но не длиннее 500 знаков; над ней —
            # хвост стека, всего не больше 4 КБ
            last = "".join(line[:500].rstrip("\\n") + "\\n" for line in
                           traceback.format_exception_only(kind, value))
            head = "Traceback (most recent call last):\\n" + "".join(traceback.format_tb(tb))
            room = max(0, 4096 - len(last))
            text = head[len(head) - room:] + last
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
    sys.excepthook = hook


_termit_out_log()
del _termit_out_log
'''


PIN_STUB = """#!/bin/sh
# {name} outside a venv: the pinned python3 of the tracks: {what}
exec {py3} {args}"$@"
"""


def pin_wrappers(py3: str) -> dict:
    """Обёртки python, pip, pip3 для .termit/bin (py3 — путь к закреплённому python3)."""
    return {"python": PIN_STUB.format(name="python", what="python is python3", py3=py3,
                                      args=""),
            "pip": PIN_STUB.format(name="pip", what="python3 -m pip", py3=py3, args="-m pip "),
            "pip3": PIN_STUB.format(name="pip3", what="python3 -m pip", py3=py3, args="-m pip ")}


def _t(box) -> Path:
    return Path(box) / ".termit"


def _owned(box) -> Path:
    """Метка владения СНАРУЖИ песочницы: папку можно убрать, даже если .termit удалили изнутри."""
    box = Path(box)
    return box.parent / (box.name + ".owned")


# В1 приёмки-1: у каждой задачи своя папка в .sandbox со случайной частью имени. Профиль
# sandbox-exec привязан к пути песочницы, поэтому процесс, переживший прошлую задачу,
# в новую песочницу писать не может. FB3 (9): имя — по заданию, «тема-3f2a» (box_names);
# прежние box-XXXXXXXX и «box» без хвоста — старые имена, уборка убирает и их.
BOX_PREFIX = "box-"
_BOX_NAME = re.compile(r"^(box(-[A-Za-z0-9_]{8})?|[a-z][a-z0-9-]{0,%d}-[0-9a-f]{%d})$"
                       % (box_names.TOPIC_MAX - 1, box_names.SUFFIX_LEN))


# Один экземпляр игры (Fix round 1): иначе create второй игры убрал бы песочницу первой
# (cleanup_stale) и погасил её zsh (reap). Замок — flock на .sandbox/termit.lock; ядро
# снимает его само, когда процесс умирает. Дескриптор не наследуется (PEP 446): zsh и его
# фоновые процессы замок не держат.
LOCK_NAME = "termit.lock"
_lock_fd: Optional[int] = None


def lock_instance(root=None) -> Optional[int]:
    """Взять замок игры. Дескриптор — пока игра идёт; None — его держит другая игра."""
    global _lock_fd
    root = Path(root if root is not None else paths.SANDBOX_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(root / LOCK_NAME), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    _lock_fd = fd
    return fd


def unlock_instance(fd: Optional[int]) -> None:
    global _lock_fd
    if fd is None:
        return
    if _lock_fd == fd:
        _lock_fd = None
    try:
        os.close(fd)        # закрытие снимает flock
    except OSError:
        pass


_RUN_ROOT = contextvars.ContextVar("termit_run_root", default=None)


@contextmanager
def run_root(root) -> Iterator[None]:
    """На время рана корень песочниц — root (session: opts.sandbox_root): по нему меряют
    длину пути сокета проверки доступности (missing() задач со своим сервером), даже когда
    root не передан явно (ревью B2, M5). После блока — как было."""
    if root is None:            # корня нет — остаётся внешний
        yield
        return
    token = _RUN_ROOT.set(Path(root))
    try:
        yield
    finally:
        _RUN_ROOT.reset(token)


def current_root() -> Path:
    """Корень песочниц текущего рана (run_root), иначе — корень игры."""
    root = _RUN_ROOT.get()
    return root if root is not None else Path(paths.SANDBOX_ROOT)


def sample_box(root=None) -> Path:
    """Путь той же длины, что у настоящей песочницы, — для проверок до create (сокет). Без
    root — в корне текущего рана (current_root)."""
    return Path(root if root is not None else current_root()) / ("x" * box_names.NAME_MAX)


def _new_box(root, task=None) -> Path:
    """Новая папка песочницы «тема-хвост» (box_names): mkdir сам отказывает, если имя занято,
    — тогда другой хвост. Права 0700 при создании, как у mkdtemp, затем 0755."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    base = box_names.topic(task)
    for _ in range(100):
        box = root / f"{base}-{secrets.token_hex(box_names.SUFFIX_LEN // 2)}"
        try:
            os.mkdir(box, 0o700)
        except FileExistsError:
            continue
        os.chmod(box, 0o755)
        return box
    raise FileExistsError(f"нет свободного имени песочницы {base}-…")


def create(task, seed: int, root=None, defer_spawn: bool = True,
           variant: Optional[int] = None, engine: Optional[str] = None):
    """defer_spawn (по умолчанию) — процессы поручения не запускать сейчас (родителем, вне
    песочницы), а отложить: их поднимет termit_app.launch внутри sandbox-exec перед zsh.
    defer_spawn=False — только для тестов без песочницы.
    Песочница каждый раз новая (В1): прошлые убираются, процессы в них гасятся. Пока zsh не
    запущен, в свежую папку не может писать никто, кроме родителя, — поэтому setup задачи
    пишет обычными средствами, а служебные файлы — всё равно через write_box_file."""
    root = root if root is not None else paths.SANDBOX_ROOT
    cleanup_stale(root)
    box = _new_box(root, task)
    fd = os.open(str(_owned(box)), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        os.write(fd, b"termit\n")
    finally:
        os.close(fd)
    (box / ".termit" / "bin").mkdir(parents=True)
    (box / ".termit" / "tmp").mkdir()
    if defer_spawn:
        write_box_file(box, ".termit/spawn.json", "[]")
    kit.home(box).mkdir()
    for name, body in _stubs().items():
        write_box_file(box, f".termit/bin/{name}", body, mode=0o755)
    pin_python(box, task)
    if getattr(task, "uses_av", False):
        write_box_file(box, ".termit/bin/clamscan",
                       AV_STUB.format(run=paths.py_line("termit_app.avstub")), mode=0o755)
    if getattr(task, "uses_crontab", False):
        write_box_file(box, ".termit/bin/crontab",
                       CRONTAB_STUB.format(run=paths.py_line("termit_app.cronstub")), mode=0o755)
    if getattr(task, "uses_shellcheck", False):
        write_box_file(box, ".termit/bin/shellcheck",
                       SHELLCHECK_STUB.format(run=paths.py_line("termit_app.shellstub")),
                       mode=0o755)
    if getattr(task, "stock", None):       # запас готовых venv/колёс (A4) — до setup задачи
        from termit_app import pyenvs
        pyenvs.stock_into(box, task.stock)
    # движок задачи БД (dbkit.choose_engine) — явно, не через окружение процесса (B1 п. 7)
    state = task.make_state(box, seed, variant=variant, engine=engine)
    write_public(box, task, state)
    write_env(box, task, state)
    _write_start_dir(box, task, state)
    return box, state


# --- Окружение задачи (часть 7, A7) ---------------------------------------------------------
# Task.env_for → .termit/env.zsh: строки «export ИМЯ=<shlex.quote>». Пишет родитель при create
# и хук при reset (rebuild); песочный .zshrc подключает файл после своих настроек и чистки
# секретов. Служебные переменные игры и песочницы задача не переопределяет.
ENV_FILE = ".termit/env.zsh"
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_ENV_PATH = re.compile(r"^\$HOME/([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*):\$PATH$")
# Служебное оболочки, Python, pip, загрузчика и локали задача не переопределяет (M1 ревью P1):
# по префиксам и по именам. PATH — отдельно, только префиксом.
ENV_RESERVED_PREFIX = ("TERMIT_", "PYTHON", "PIP_", "DYLD_", "LD_", "LC_", "ZSH", "HIST",
                       "PS", "PROMPT", "RPROMPT", "BASH_")
ENV_RESERVED = frozenset({"HOME", "TMPDIR", "TMPPREFIX", "ZDOTDIR", "SHELL", "PWD", "OLDPWD",
                          "USER", "LOGNAME", "LANG", "IFS", "FPATH", "CDPATH", "MANPATH",
                          "MODULE_PATH", "ENV", "VIRTUAL_ENV", "TERM", "SHLVL", "EDITOR",
                          "VISUAL", "PAGER", "LESS", "NULLCMD", "READNULLCMD", "WORDCHARS"})
SECRET_MIN = 4          # секрет-строку короче этого ищем только точным совпадением


def _secret_values(task, state: dict) -> List[str]:
    """Строки секретной части состояния (Task.secret_keys), вглубь списков и словарей."""
    out = []

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            out.append(str(v))
    for k in getattr(task, "secret_keys", ()) or ():
        if k in state:
            walk(state[k])
    return [x for x in out if x.strip()]


_ENV_CLEAR = re.compile(r"^[A-Z][A-Z0-9]*_$")


def env_lines(env: dict, clear=()) -> str:
    """Текст env.zsh. Плохое имя, служебная переменная, PATH не префиксом $HOME/…:$PATH
    (без «..»), значение не строка или с нулевым байтом — ValueError: это ошибка задачи.
    clear — префиксы (Task.env_clear, вида «APP_»): до своих export файл снимает все
    переменные с ними, чтобы такие же из ~/.zshrc владельца не мешали уроку."""
    out = []
    for prefix in clear:
        if (not isinstance(prefix, str) or not _ENV_CLEAR.match(prefix)
                or prefix.startswith(ENV_RESERVED_PREFIX) or prefix in ENV_RESERVED):
            raise ValueError(f"плохой префикс для unset: {prefix!r}")
        out.append(f"unset -m '{prefix}*'")
    for name in sorted(env):
        value = env[name]
        if not isinstance(name, str) or not _ENV_NAME.match(name):
            raise ValueError(f"плохое имя переменной: {name!r}")
        if name in ENV_RESERVED or name.startswith(ENV_RESERVED_PREFIX):
            raise ValueError(f"служебная переменная песочницы: {name}")
        if not isinstance(value, str) or "\0" in value:
            raise ValueError(f"плохое значение {name}")
        if name == "PATH":
            m = _ENV_PATH.match(value)
            if not m or any(x in (".", "..") for x in m.group(1).split("/")):
                raise ValueError("PATH — только префиксом $HOME/…:$PATH")
            out.append(f'export PATH="$HOME/{m.group(1)}:$PATH"')
        else:
            out.append(f"export {name}={shlex.quote(value)}")
    return "".join(line + "\n" for line in out)


def write_env(box, task, state: dict) -> None:
    """Записать env.zsh задачи (или убрать файл, если окружения у задачи нет)."""
    env = task.env_for(state) or {}
    secrets_ = _secret_values(task, state)
    for name, value in env.items():
        for sec in secrets_:
            if value == sec or (len(sec) >= SECRET_MIN and sec in str(value)):
                raise ValueError(f"{name}: в окружении задачи — секрет состояния (M2)")
    body = env_lines(env, getattr(task, "env_clear", ()) or ()) if env else ""
    if body:
        write_box_file(box, ENV_FILE, body)
    else:
        _remove(Path(box) / ENV_FILE)


# --- Открытая и секретная части состояния (Н приёмки-1) ---------------------------------
# В .termit/task.json — только открытая часть: без Task.secret_keys. Полное состояние —
# у родителя (session, judge). Флаг "hidden" говорит хуку: проверка — через судью.

def public_state(task, state: dict) -> dict:
    secret = set(getattr(task, "secret_keys", ()) or ())
    return {k: v for k, v in state.items() if k not in secret}


def write_public(box, task, state: dict) -> None:
    pub = public_state(task, state)
    write_task_json(box, task.id, pub, hidden=len(pub) != len(state))


def unhide(box, task, state: dict) -> None:
    """Судья не поднялся (длинный путь сокета и т.п.): полный task.json, как раньше, —
    игра должна работать, хоть ответ и виден изнутри."""
    write_task_json(box, task.id, state)


def merge_state(task, full: dict, public) -> dict:
    """Полное состояние родителя, поверх — открытая часть из task.json (PID процессов,
    подставленные launch или reset); секретные ключи — всегда родителя."""
    out = dict(full)
    if isinstance(public, dict):
        secret = set(getattr(task, "secret_keys", ()) or ())
        out.update({k: v for k, v in public.items() if k not in secret})
    return out


def _has_token(value) -> bool:
    from termit_app.tasks import kit
    if isinstance(value, dict):
        return any(_has_token(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_token(v) for v in value)
    return isinstance(value, int) and not isinstance(value, bool) and value <= kit.SPAWN_TOKEN


def live_state(full: dict, public) -> dict:
    """Состояние для повторной проверки у родителя (P2 А3): всё — родителя, из task.json
    песочницы берутся только живые ключи — те, где у родителя стоит метка отложенного
    запуска (настоящий PID подставляет launch или reset изнутри). Остальное изнутри
    подменить нельзя: пустой список «нужных папок» не делает задачу решённой."""
    out = dict(full)
    if isinstance(public, dict):
        out.update({k: public[k] for k, v in full.items() if k in public and _has_token(v)})
    return out


def _write_start_dir(box, task, state: dict) -> None:
    d = Path(box) / task.start_dir.format(**state) if task.start_dir else Path(box)
    write_box_file(box, ".termit/start_dir", str(d))


def start_dir(box) -> Path:
    """Где стартует zsh (и куда возвращает reset)."""
    v = _read(box, "start_dir")
    return Path(v.strip()) if v and v.strip() else Path(box)


def rebuild(box, task) -> dict:
    """reset: всё, кроме журналов .termit, — заново с тем же зерном случайности."""
    box = Path(box)
    kit.kill_registered(box)
    for child in box.iterdir():
        if child.name != ".termit":
            _remove(child)
    _remove(kit.home(box))
    kit.home(box).mkdir()
    for name in ("answer", "boss", "open.log", "fakeclip"):
        (_t(box) / name).unlink(missing_ok=True)
    data = read_task_json(box)
    old = data["state"]
    # вариант читается из task.json: make_state приведёт его по модулю, мусор — к 0;
    # нет ключа — None, тогда тот же seed вытянет тот же вариант
    # движок — тот же, что выбрал родитель (_engine в открытой части; мусор — как без него)
    engine = old.get("_engine")
    from termit_app.tasks import dbkit
    state = task.make_state(box, old["_seed"], variant=old.get("_variant"),
                            engine=engine if engine in dbkit.ENGINES else None)
    if data.get("hidden"):          # секреты — только в памяти: в файл открытая часть
        write_public(box, task, state)
    else:
        write_task_json(box, task.id, state)
    write_env(box, task, state)
    _write_start_dir(box, task, state)
    apply_extras(box)
    return state


# --- Подкладка файлов (extras) ------------------------------------------------------------
# Родитель вычисляет файлы рана (осколок, хабар, купленное) и пишет их список в
# .termit/extras.json ДО запуска zsh; reset раскладывает их заново. Запись — только внутрь
# песочницы: путь относительный, без «..», ни одна часть пути не симлинк (открываем по
# одному звену через O_NOFOLLOW), файл с чужими жёсткими ссылками не трогаем.
# Плохая запись молча пропускается: хук и ран из-за неё не падают.

_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW


EXTRAS_CAP = 8 * 1024 * 1024      # список extras больше этого — подделка, не читаем
CMDS_CAP = 16 * 1024 * 1024       # журнал команд задачи; больше — не читаем
TASK_JSON_CAP = 4 * 1024 * 1024   # task.json: состояние задачи
SMALL_CAP = 64 * 1024             # ответ, результат, счётчики, pwd, start_dir, замечания


def read_box_file(path, cap: int) -> Optional[bytes]:
    """Родитель читает файл песочницы: последнее звено не симлинк (O_NOFOLLOW), FIFO не
    вешает (O_NONBLOCK), только обычный файл и не больше cap байт. Иначе — None."""
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            return None
        chunks, left = [], cap + 1
        while left > 0:
            chunk = os.read(fd, min(left, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        data = b"".join(chunks)
        return data if len(data) <= cap else None
    except OSError:
        return None
    finally:
        os.close(fd)


def _box_parts(box, rel) -> Optional[List[str]]:
    """Звенья пути внутри песочницы. rel — относительный (или абсолютный, но лексически под
    box): без «..», без пустых звеньев. Вне песочницы — None (родитель туда не читает)."""
    p = Path(rel)
    if p.is_absolute():
        try:
            p = p.relative_to(Path(box))
        except ValueError:
            return None
    parts = [x for x in p.parts if x not in ("", ".")]
    if not parts or any(x == ".." for x in parts):
        return None
    return parts


def read_in_box(box, rel, cap: int) -> Optional[bytes]:
    """Родитель читает файл ВНУТРИ песочницы (судья, проверки, служебные файлы): папки —
    по одному звену через O_NOFOLLOW (ни одно звено не симлинк), сам файл — O_NOFOLLOW и
    O_NONBLOCK (FIFO не вешает), только обычный файл не больше cap. Иначе — None."""
    parts = _box_parts(box, rel)
    if parts is None:
        return None
    try:
        dfd = _open_dirs(box, parts[:-1])
    except OSError:
        return None
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    except OSError:
        return None
    finally:
        os.close(dfd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            return None
        chunks, left = [], cap + 1
        while left > 0:
            chunk = os.read(fd, min(left, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        data = b"".join(chunks)
        return data if len(data) <= cap else None
    except OSError:
        return None
    finally:
        os.close(fd)


def open_in_box(box, rel, cap: int) -> Optional[int]:
    """Дескриптор обычного файла ВНУТРИ песочницы (не больше cap) — те же правила, что у
    read_in_box: звенья через O_NOFOLLOW, сам файл O_NOFOLLOW|O_NONBLOCK. Иначе — None.
    Закрыть дескриптор — забота вызывающего (dbread открывает базу через /dev/fd/N)."""
    parts = _box_parts(box, rel)
    if parts is None:
        return None
    try:
        dfd = _open_dirs(box, parts[:-1])
    except OSError:
        return None
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    except OSError:
        return None
    finally:
        os.close(dfd)
    try:
        st = os.fstat(fd)
        if stat.S_ISREG(st.st_mode) and st.st_size <= cap:
            return fd
    except OSError:
        pass
    os.close(fd)
    return None


def files_in_box(box, rel) -> Optional[List[str]]:
    """Имена обычных файлов папки внутри песочницы (симлинки, FIFO, папки — мимо); папка —
    по звеньям без симлинков. Нет такой папки или путь вне песочницы — None."""
    parts = _box_parts(box, rel) if str(rel) not in ("", ".") else []
    if parts is None:
        return None
    try:
        dfd = _open_dirs(box, parts)
    except OSError:
        return None
    try:
        out = []
        for name in os.listdir(dfd):
            try:
                if stat.S_ISREG(os.stat(name, dir_fd=dfd, follow_symlinks=False).st_mode):
                    out.append(name)
            except OSError:
                continue
        return sorted(out)
    except OSError:
        return None
    finally:
        os.close(dfd)


def write_extras(box, extras: list) -> None:
    try:
        body = json.dumps(list(extras), ensure_ascii=False).encode("utf-8")
        fd = os.open(str(_t(box) / "extras.json"),
                     os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o644)
    except (OSError, TypeError, ValueError):
        return
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return
        view = memoryview(body)
        while view:
            view = view[os.write(fd, view):]
    except OSError:
        return
    finally:
        os.close(fd)
    apply_extras(box)


def apply_extras(box) -> None:
    raw = read_in_box(box, ".termit/extras.json", EXTRAS_CAP)
    try:
        items = json.loads(raw.decode("utf-8")) if raw is not None else None
    except ValueError:
        return
    if not isinstance(items, list):
        return
    for e in items:
        try:
            _put_extra(Path(box), e)
        except Exception:       # одна кривая запись не мешает остальным
            continue


def _extra_parts(rel) -> Optional[List[str]]:
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\0" in rel:
        return None
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    return parts


def _open_dirs(box, names, create: bool = False) -> int:
    """Открыть папку box/names[0]/… по одному звену через O_NOFOLLOW: ни одно звено не
    симлинк, иначе OSError. create — недостающие папки создать. Вернуть дескриптор."""
    fd = os.open(str(box), _DIR_FLAGS)
    try:
        for name in names:
            try:
                nfd = os.open(name, _DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(name, 0o755, dir_fd=fd)
                nfd = os.open(name, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = nfd
    except BaseException:
        os.close(fd)
        raise
    return fd


def write_box_file(box, rel: str, data, mode: int = 0o644) -> None:
    """Родитель (и хук) пишет файл песочницы безопасной заменой (В1 приёмки-1): папки — по
    звену с O_NOFOLLOW, данные — во временный файл рядом (O_CREAT|O_EXCL|O_NOFOLLOW), затем
    rename поверх имени. rename заменяет саму запись каталога: симлинк или чужая жёсткая
    ссылка на месте файла просто исчезает, а файл, на который они вели, не меняется.
    rel — путь от корня песочницы без «..»; плохой путь — ValueError, симлинк в пути — OSError."""
    parts = _extra_parts(rel)
    if parts is None:
        raise ValueError(f"плохой путь в песочнице: {rel!r}")
    body = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    fd = _open_dirs(box, parts[:-1])
    try:
        tmp = f".{parts[-1]}.{secrets.token_hex(6)}.tmp"
        wfd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                      dir_fd=fd)
        try:
            try:
                view = memoryview(body)
                while view:
                    view = view[os.write(wfd, view):]
                os.fchmod(wfd, mode & 0o777)
            finally:
                os.close(wfd)
            os.replace(tmp, parts[-1], src_dir_fd=fd, dst_dir_fd=fd)
        except BaseException:
            try:
                os.unlink(tmp, dir_fd=fd)
            except OSError:
                pass
            raise
    finally:
        os.close(fd)


def _put_extra(box: Path, e) -> None:
    if not isinstance(e, dict):
        return
    roots = {"box": [], "home": [".termit", "home"]}
    if e.get("root", "box") not in roots:
        return
    parts = _extra_parts(e.get("path"))
    if parts is None:
        return
    data = base64.b64decode(e.get("b64", ""), validate=True)
    target = box.joinpath(*roots[e.get("root", "box")], *parts)
    if not inside(target.parent, box):
        return
    fd = _open_dirs(box, roots[e.get("root", "box")] + parts[:-1], create=True)
    try:
        mode = e.get("mode")
        wfd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                      0o644 if mode is None else int(mode) & 0o777, dir_fd=fd)
        try:
            st = os.fstat(wfd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink > 1:
                return              # чужая жёсткая ссылка: перезапись ушла бы наружу
            os.ftruncate(wfd, 0)
            view = memoryview(data)
            while view:
                view = view[os.write(wfd, view):]
            if mode is not None:
                os.fchmod(wfd, int(mode) & 0o777)
        finally:
            os.close(wfd)
        if e.get("mtime") is not None:
            t = float(e["mtime"])
            os.utime(parts[-1], (t, t), dir_fd=fd, follow_symlinks=False)
    finally:
        os.close(fd)


# флаги, с которыми rmtree не справится: uchg/uappnd ставит хозяин (игрок изнутри — chflags
# uchg), schg/sappnd — только root, но снять попробуем (P2 А5, security В-Н3)
_LOCK_FLAGS = (getattr(stat, "UF_IMMUTABLE", 0) | getattr(stat, "UF_APPEND", 0)
               | getattr(stat, "SF_IMMUTABLE", 0) | getattr(stat, "SF_APPEND", 0))


def _unflag(p, st) -> None:
    """Снять неизменяемость с самого звена (lchflags): по ссылке не идём никогда."""
    flags = getattr(st, "st_flags", 0)
    if flags & _LOCK_FLAGS:
        try:
            os.chflags(p, flags & ~_LOCK_FLAGS, follow_symlinks=False)
        except (OSError, NotImplementedError, AttributeError):
            pass


def _unlock(path: Path) -> None:
    """Вернуть себе права на папки песочницы и снять флаги uchg (chflags -R nouchg,noschg),
    чтобы rmtree смог её убрать. Ни одна операция не идёт по ссылке: lstat, chmod и chflags с
    follow_symlinks=False — даже если папку подменили симлинком между обходом и chmod,
    поменяются права самой ссылки, а не цели."""
    def grant(p) -> None:
        try:
            st = os.lstat(p)
            _unflag(p, st)
            if stat.S_ISDIR(st.st_mode):
                os.chmod(p, st.st_mode | stat.S_IRWXU, follow_symlinks=False)
        except (OSError, NotImplementedError):
            pass
    grant(path)
    for dirpath, dirnames, filenames in os.walk(path):     # os.walk по симлинкам не ходит
        for d in dirnames:
            p = os.path.join(dirpath, d)
            if os.path.islink(p):       # ссылка на папку: флаг — с самой ссылки, цель не
                try:                    # трогаем и внутрь не идём (P2 fix1 I2)
                    _unflag(p, os.lstat(p))
                except OSError:
                    pass
                continue
            grant(p)
        for name in filenames:      # файлы (и сами ссылки): только флаги, права не трогаем
            p = os.path.join(dirpath, name)
            try:
                _unflag(p, os.lstat(p))
            except OSError:
                pass


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        _unlock(path)
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        path.unlink()
    if os.path.lexists(path):
        raise OSError(f"не удалось удалить {path} — удали вручную")


def _marked(box) -> bool:
    return _t(box).is_dir() or _owned(box).is_file()


def destroy(box) -> None:
    box = Path(box)
    if not os.path.lexists(box):
        _owned(box).unlink(missing_ok=True)
        return
    if box.is_symlink() or not box.is_dir():
        raise RuntimeError(f"отказываюсь удалять: это не папка песочницы: {box}")
    if not _marked(box):
        raise RuntimeError(f"отказываюсь удалять папку без метки тренажёра: {box}")
    # брошенный сервер PostgreSQL задачи (игра упала): сначала SIGINT и ожидание — он сам
    # уберёт свой SysV; после reap — подметание только его сегмента и семафоров (часть 9б)
    from termit_app import pgkit
    pg = pgkit.stop_stale(box)
    left = reap(box)
    pgkit.sweep_stale(pg)
    if left:
        # папку не удаляем: без неё процесс уже не узнать (caged_in), а следующий
        # cleanup_stale попробует снова
        print(f"[тренажёр] процессы песочницы не гаснут: {', '.join(map(str, left))} — "
              "песочница оставлена до следующего запуска", file=sys.stderr)
        return
    kit.kill_registered(box)
    _remove(box)
    _owned(box).unlink(missing_ok=True)


def cleanup_stale(root=None) -> None:
    """Убрать все прошлые песочницы в root: «тема-хвост», box-XXXXXXXX и старую box. Симлинк
    или папку без метки тренажёра не трогаем; осиротевшие метки владения удаляем."""
    root = Path(root if root is not None else paths.SANDBOX_ROOT)
    try:
        entries = list(os.scandir(root))
    except FileNotFoundError:
        return
    for e in entries:
        if _BOX_NAME.match(e.name) and e.is_dir(follow_symlinks=False):
            box = root / e.name
            if _marked(box):
                destroy(box)
    for e in entries:
        if e.name.endswith(".owned") and _BOX_NAME.match(e.name[:-len(".owned")]):
            if not os.path.lexists(root / e.name[:-len(".owned")]):
                (root / e.name).unlink(missing_ok=True)


# --- Процессы песочницы (В1) --------------------------------------------------------------
# Процесс, оставленный игроком в фоне (nohup … &!, setsid, двойной fork), переживает zsh.
# Узнаём «свои» не по PID из файла (его пишет песочница) и не по командной строке (её можно
# подменить), а по самому профилю sandbox-exec: ядро отвечает через sandbox_check, разрешено
# ли процессу писать в box и в папку над ней. Только профиль ЭТОЙ песочницы даёт «в box —
# да, рядом — нет»: процесс без песочницы может писать и туда, приложение App Store или
# процесс прошлой песочницы — не может в box. Чужих не трогаем никогда.

_SANDBOX_FILTER_PATH = 1
_SANDBOX_CHECK_NO_REPORT = 0x40000000
_sandbox_check = None


def _checker():
    global _sandbox_check
    if _sandbox_check is None:
        try:
            f = ctypes.CDLL("/usr/lib/libSystem.B.dylib").sandbox_check
            f.restype = ctypes.c_int
            f.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]   # путь — вариадик
            _sandbox_check = f
        except (OSError, AttributeError):
            _sandbox_check = False
    return _sandbox_check or None


def caged_in(pid: int, box) -> bool:
    """Процесс pid заперт профилем именно этой песочницы (см. выше). box должен существовать."""
    f = _checker()
    if f is None:
        return False
    rbox = os.fsencode(str(Path(box).resolve()))
    flags = _SANDBOX_FILTER_PATH | _SANDBOX_CHECK_NO_REPORT
    try:
        if f(pid, None, 0) != 1:            # не под песочницей вовсе
            return False
        for op in (b"file-write-create", b"file-write-data"):
            if f(pid, op, flags, ctypes.c_char_p(rbox)) != 0:
                return False
            if f(pid, op, flags, ctypes.c_char_p(os.path.dirname(rbox))) != 1:
                return False
    except (OSError, ctypes.ArgumentError):
        return False
    return True


def box_pids(box) -> List[int]:
    """PID живых процессов этой песочницы (своего пользователя, кроме себя)."""
    from termit_app import procview
    box = Path(box)
    if not box.is_dir():
        return []
    me, uid = os.getpid(), os.getuid()
    out = []
    for pid in procview.list_pids():
        if pid == me:
            continue
        info = procview.taskinfo(pid)
        if info is None or info["uid"] != uid:
            continue
        if caged_in(pid, box):
            out.append(pid)
    return out


def reap(box, rounds: int = 20) -> List[int]:
    """После выхода из zsh — погасить всё, что осталось в песочнице. В каждом раунде сначала
    SIGSTOP всем найденным (замороженный процесс больше не ветвится), потом повторный поиск
    (дети, успевшие родиться) и SIGKILL всем. Вернуть выживших после всех раундов."""
    pids: List[int] = []
    for _ in range(rounds):
        pids = box_pids(box)
        if not pids:
            return []
        for sig in (signal.SIGSTOP, signal.SIGKILL):
            for pid in (pids if sig == signal.SIGSTOP else sorted(set(pids) | set(box_pids(box)))):
                if not caged_in(pid, box):      # перепроверка прямо перед сигналом
                    continue
                try:
                    os.kill(pid, sig)
                except (ProcessLookupError, PermissionError):
                    pass
        time.sleep(0.02)
    return box_pids(box)


def write_task_json(box, task_id: str, state: dict, hidden: bool = False) -> None:
    data = {"id": task_id, "state": state}
    if hidden:
        data["hidden"] = True
    write_box_file(box, ".termit/task.json", json.dumps(data, ensure_ascii=False))


def read_task_json(box) -> dict:
    """task.json — через read_in_box: симлинк на любом звене, FIFO или гигант — как будто
    файла нет."""
    raw = read_in_box(box, ".termit/task.json", TASK_JSON_CAP)
    if raw is None:
        raise FileNotFoundError(str(_t(box) / "task.json"))
    return json.loads(raw.decode("utf-8"))


def read_cmds(box) -> List[Cmd]:
    raw_log = read_in_box(box, ".termit/cmds.log", CMDS_CAP)    # FIFO, симлинк — мимо
    if raw_log is None:
        return []
    out = []
    for raw in raw_log.decode("utf-8", errors="replace").splitlines():
        parts = raw.split("\t", 2)
        if len(parts) != 3:
            continue
        try:
            t = float(parts[0].replace(",", "."))   # EPOCHREALTIME с запятой при русской локали
        except ValueError:
            t = 0.0
        out.append(Cmd(t, parts[1], parts[2]))
    return out


def read_cmd_codes(box) -> List[Tuple[str, Optional[List[str]]]]:
    """Команды из cmds.log с кодами звеньев конвейера из rc.log (пишет precmd по той же
    метке времени); None — кода нет (автозапуск, журнал испорчен или не записался). Читает
    родитель, теми же безопасными чтениями."""
    raw_log = read_in_box(box, ".termit/cmds.log", CMDS_CAP)
    if raw_log is None:
        return []
    codes = {}
    raw_rc = read_in_box(box, ".termit/rc.log", CMDS_CAP)
    for raw in (raw_rc or b"").decode("utf-8", errors="replace").splitlines():
        stamp, _, rest = raw.partition("\t")
        codes[stamp] = rest.split()
    out = []
    for raw in raw_log.decode("utf-8", errors="replace").splitlines():
        parts = raw.split("\t", 2)
        if len(parts) == 3:
            out.append((parts[2], codes.get(parts[0])))
    return out


def read_cmd_status(box) -> List[Tuple[str, Optional[bool]]]:
    """Команды с исходом: True — все звенья конвейера вернули 0, False — нет, None — кода
    нет (read_cmd_codes)."""
    return [(line, None if nums is None else (bool(nums) and all(x == "0" for x in nums)))
            for line, nums in read_cmd_codes(box)]


def _read(box, name: str, cap: int = SMALL_CAP) -> Optional[str]:
    """Служебный файл .termit: только обычный файл не больше cap, без симлинков и FIFO."""
    raw = read_in_box(box, f".termit/{name}", cap)
    return raw.decode("utf-8", errors="replace") if raw is not None else None


def read_feedback(box) -> List[str]:
    """Замечания бета-тестера из .termit/feedback (родитель переносит их в feedback.jsonl)."""
    v = _read(box, "feedback")
    return [line.strip() for line in v.splitlines() if line.strip()] if v else []


def write_answer(box, text: str) -> None:
    write_box_file(box, ".termit/answer", text)


def read_answer(box) -> Optional[str]:
    return _read(box, "answer")


def clear_answer(box) -> None:
    (_t(box) / "answer").unlink(missing_ok=True)


def write_pwd(box, pwd: str) -> None:
    write_box_file(box, ".termit/pwd", str(pwd))


def read_pwd(box) -> Optional[Path]:
    v = _read(box, "pwd")
    return Path(v.strip()) if v else None


def result(box) -> Optional[str]:
    v = _read(box, "result")
    return v.strip() if v else None


def set_result(box, value: str) -> None:
    write_box_file(box, ".termit/result", value)


def counter(box, name: str) -> int:
    v = _read(box, name)
    try:
        return int(v) if v else 0
    except ValueError:
        return 0


def bump(box, name: str) -> int:
    n = counter(box, name) + 1
    write_box_file(box, f".termit/{name}", str(n))
    return n


def inside(path, box) -> bool:
    try:
        p, b = Path(path).resolve(), Path(box).resolve()
    except OSError:
        return False
    return p == b or b in p.parents


def make_ctx(box, state: dict, service=None) -> Ctx:
    """Что видит проверка. service — сервис родителя задачи (учебный API, сервер БД) или
    None: судья и tests/refrun передают свой, проверка в песочнице — без него."""
    return Ctx(box=Path(box), state=state, answer=read_answer(box),
               cmds=read_cmds(box), pwd=read_pwd(box), service=service)
