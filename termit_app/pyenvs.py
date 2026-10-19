"""Python треков «Окружение», «Python» и «Аналитика» (части 7 и 10): интерпретатор треков
(A1), эталонные venv и запас песочницы (A4).

A1 — интерпретатор треков: track_python() выбирает Python, за которым в песочнице закреплён
python3 (симлинки в .termit/bin кладёт sandbox.create задачам с pinned_python). Порядок:
1. sys.executable игры, если это 3.9;
2. иначе /usr/bin/python3 из Command Line Tools, если xcode-select -p ответил 0 и это 3.9.
   Без проверки xcode-select шим /usr/bin/python3 не трогаем: он открывает окно установки CLT;
3. иначе sys.executable (3.10+): треки env и py работают, pydata — нет (склад под cp39).
Берётся настоящий путь (os.path.realpath), а не шим: venv игрока ссылается на симлинк
.termit/bin/python3 (pyvenv.cfg: home), и шим путал бы xcrun (спайк S0, решение 2).
Выбор кэшируется в .cache/pytrack.json (paths.CACHE_DIR) по пути интерпретатора игры."""
import fcntl
import hashlib
import json
import os
import platform
import re
import secrets
import stat
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from termit_app import paths

TRACK_VERSION = (3, 9)            # склад колёс собран под cp39 (план, A3)
CACHE_NAME = "pytrack.json"
SHIM = "/usr/bin/python3"
XCODE_SELECT = "/usr/bin/xcode-select"
PROBE_TIMEOUT = 10
NO_PYTHON = "нужен Python из Command Line Tools: xcode-select --install"
# что печатает интерпретатор о себе: настоящий путь, версия, архитектура
_PROBE = ("import json, os, platform, sys; print(json.dumps([os.path.realpath(sys.executable), "
          "list(sys.version_info[:3]), platform.machine()]))")


@dataclass(frozen=True)
class PyInfo:
    path: str                       # настоящий путь интерпретатора (realpath)
    version: Tuple[int, int, int]
    arch: str

    @property
    def short(self) -> str:
        """3.9 — для имени симлинка python3.9."""
        return f"{self.version[0]}.{self.version[1]}"

    def to_json(self) -> dict:
        return {"path": self.path, "version": list(self.version), "arch": self.arch}


def _info(raw) -> Optional[PyInfo]:
    """PyInfo из [путь, версия, архитектура] (вывод _PROBE или кэш); мусор — None."""
    try:
        path, ver, arch = raw
        ver = tuple(int(x) for x in ver)
        if not isinstance(path, str) or not os.path.isabs(path) or len(ver) != 3:
            return None
        if not os.path.isfile(path) or not os.access(path, os.X_OK):
            return None
        return PyInfo(path, ver, str(arch))
    except (TypeError, ValueError):
        return None


def _self_info() -> Optional[PyInfo]:
    """Интерпретатор самой игры."""
    if not sys.executable:
        return None
    return _info([os.path.realpath(sys.executable), list(sys.version_info[:3]),
                  platform.machine()])


def _xcode_ok() -> bool:
    """Command Line Tools стоят (xcode-select -p ответил 0): только тогда шим безопасен."""
    try:
        r = subprocess.run([XCODE_SELECT, "-p"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def _probe(exe: str) -> Optional[PyInfo]:
    """Спросить интерпретатор о себе (-I: без окружения и пользовательского site)."""
    try:
        r = subprocess.run([exe, "-I", "-c", _PROBE], capture_output=True, text=True,
                           timeout=PROBE_TIMEOUT, env={"PATH": "/usr/bin:/bin", "LANG": "C"})
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        return _info(json.loads(r.stdout.strip().splitlines()[-1]))
    except (ValueError, IndexError):
        return None


def choose() -> Optional[PyInfo]:
    """Выбор интерпретатора треков по порядку A1 (без кэша)."""
    me = _self_info()
    if me is not None and me.version[:2] == TRACK_VERSION:
        return me
    if _xcode_ok():
        clt = _probe(SHIM)
        if clt is not None and clt.version[:2] == TRACK_VERSION:
            return clt
    return me


def _cache_path() -> Path:
    return Path(paths.CACHE_DIR) / CACHE_NAME


def _read_cache(key: str) -> Optional[PyInfo]:
    try:
        data = json.loads(_cache_path().read_text("utf-8"))
        if data.get("key") != key:
            return None
        i = data["info"]
        return _info([i["path"], i["version"], i["arch"]])
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def _write_cache(key: str, info: PyInfo) -> None:
    p = _cache_path()
    tmp = p.with_name(f".{p.name}.{secrets.token_hex(4)}.tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"key": key, "info": info.to_json()}), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def track_python(refresh: bool = False) -> Optional[PyInfo]:
    """Интерпретатор треков (A1), из кэша, если игра запущена тем же Python. None — нет ни
    одного годного (sys.executable пуст или не исполняется)."""
    key = os.path.realpath(sys.executable) if sys.executable else ""
    if not refresh:
        hit = _read_cache(key)
        if hit is not None:
            return hit
    info = choose()
    if info is not None:
        _write_cache(key, info)
    return info


SPACE_IN_PATH = ("в пути к папке игры есть пробел — команды из venv (pip, datapeek) так не "
                 "запускаются: перенеси игру в папку без пробелов")


def why_not(root=None) -> Optional[str]:
    """Почему задаче с python3 треков или запасом venv нельзя начаться (None — можно). root —
    корень песочниц рана (None — текущий). pip 21 пишет в консольные скрипты venv shebang с
    полным путём, а ядро режет его по пробелу (M5 ревью P1)."""
    from termit_app import sandbox
    box_root = Path(root) if root is not None else sandbox.current_root()
    if " " in str(paths.ROOT) or " " in str(box_root):
        return SPACE_IN_PATH
    return None if track_python() is not None else NO_PYTHON


def pin_names(info: PyInfo) -> Tuple[str, str]:
    """Имена симлинков в .termit/bin: python3 и python3.X."""
    return ("python3", f"python{info.short}")


# --- Эталонные venv и запас песочницы (A4) ------------------------------------------------
# Эталон light — venv интерпретатора треков с pip и учебными пакетами (sockhttp, tabprint
# 1.0.0, datapeek). Строит родитель один раз: python -m venv, затем pip install только из
# своих колёс (--no-index, --only-binary) — под sandbox-exec с записью лишь в папку сборки и
# без сети; HOME и TMPDIR — внутри неё (иначе pip Python от Apple пишет pyc в настоящий
# ~/Library/Caches/com.apple.python), PIP_NO_CACHE_DIR=1 (спайк S0, решение 6). Готовый venv
# атомарно переименовывается в .cache/pylab/light-<хэш>; хэш — от интерпретатора, версии
# сборки и байтов колёс. Задаче со stock = "light" sandbox.create клонирует эталон в
# box/.termit/stock/light (cp -c: APFS clonefile), reset его не трогает, а setup задачи
# берёт из запаса свой .venv (kit.venv_from_stock → kit.clone_venv).
LAB_DIR = "pylab"                       # в paths.CACHE_DIR
STOCK_DIR = ".termit/stock"
LIGHT_PKGS = ("sockhttp", "tabprint==1.0.0", "datapeek")
BUILD_VERSION = "1"                     # сменить — эталоны пересоберутся
BUILD_TIMEOUT = 300
_build_lock = threading.Lock()


class StockError(RuntimeError):
    """Эталон не собрать (нет интерпретатора, pip упал, нет sandbox-exec)."""


NO_SANDBOX = ("нужен sandbox-exec: готовые окружения Python собираются только в песочнице "
              "macOS")
# неудачные сборки эталона в этом процессе: хэш → причина. missing() задачи с запасом говорит
# её сразу и не собирает снова (M7 ревью P1: иначе каждый ран падал бы в sandbox.create)
_failed = {}


def lab_dir() -> Path:
    return Path(paths.CACHE_DIR) / LAB_DIR


def _light_wheels():
    from termit_app.pylibs import wheelmake
    names = {wheelmake.get(x).name for x in LIGHT_PKGS}
    # в папку сборки — все версии нужных пакетов: pip сам выберет по LIGHT_PKGS
    return [p for p in wheelmake.PKGS.values() if p.name in names]


def light_hash(info: Optional[PyInfo] = None) -> str:
    """Хэш эталона light: интерпретатор, версия сборки, список пакетов и байты их колёс."""
    from termit_app.pylibs import wheelmake
    info = info or track_python()
    h = hashlib.sha256()
    h.update(json.dumps([BUILD_VERSION, info.to_json() if info else None,
                         list(LIGHT_PKGS)]).encode())
    for pkg in sorted(_light_wheels(), key=lambda p: p.key):
        h.update(pkg.wheel_name.encode() + b"\0" + wheelmake.wheel_bytes(pkg))
    return h.hexdigest()[:16]


def light_path(info: Optional[PyInfo] = None) -> Path:
    return lab_dir() / f"light-{light_hash(info)}"


def _build_env(build: Path) -> dict:
    return {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "HOME": str(build / "home"),
            "TMPDIR": str(build / "tmp") + "/", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_RETRIES": "0", "PIP_TIMEOUT": "3", "PIP_CONFIG_FILE": "/dev/null",
            "PIP_NO_CACHE_DIR": "1", "PYTHONDONTWRITEBYTECODE": "1"}


def build_light(refresh: bool = False) -> Path:
    """Эталон light в кэше (собрать, если его нет). Ошибка сборки — StockError."""
    from termit_app import shell_run
    from termit_app.pylibs import wheelmake
    info = track_python()
    if info is None:
        raise StockError(NO_PYTHON)
    final = light_path(info)
    if final.is_dir() and not refresh:
        return final
    if not shutil.which("sandbox-exec"):
        raise StockError(NO_SANDBOX)
    try:
        return _build_light(info, final, refresh)
    except StockError as e:
        _failed[final.name] = str(e)
        raise


def _build_light(info: PyInfo, final: Path, refresh: bool) -> Path:
    from termit_app.pylibs import wheelmake

    def prepare(build: Path) -> None:
        for pkg in _light_wheels():
            wheelmake.build_wheel(pkg, build / "wheels")
    return _build_venv(info, final, refresh, prepare, LIGHT_SCRIPT)


LIGHT_SCRIPT = ('"$1" -m venv venv && venv/bin/python -m pip install --no-index '
                "--find-links wheels --only-binary=:all: " + " ".join(LIGHT_PKGS))


def _build_venv(info: PyInfo, final: Path, refresh: bool, prepare, script: str,
                finish=None) -> Path:
    """Сборка эталона под замком: prepare(build) кладёт колёса в папку сборки, script (sh,
    $1 — интерпретатор треков) строит build/venv — под sandbox-exec с записью только в папку
    сборки и без сети; finish(build/venv) доводит его, и готовое атомарно переименовывается
    в final."""
    from termit_app import shell_run
    lab = lab_dir()
    lab.mkdir(parents=True, exist_ok=True)
    with _build_lock:
        fd = os.open(str(lab / ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            if final.is_dir() and not refresh:
                return final            # собрал соседний поток или процесс
            build = lab / f".build-{final.name}-{secrets.token_hex(4)}"
            try:
                for d in ("home", "tmp", "wheels"):
                    (build / d).mkdir(parents=True)
                prepare(build)
                prof = shell_run.task_profile(build, Path.home(), ttys=())
                try:
                    r = subprocess.run(["sandbox-exec", "-p", prof, "/bin/sh", "-c", script,
                                        "sh", info.path], cwd=str(build),
                                       env=_build_env(build), capture_output=True, text=True,
                                       timeout=BUILD_TIMEOUT)
                except (OSError, subprocess.SubprocessError) as e:
                    raise StockError(f"сборка эталона: {e}") from None
                if r.returncode != 0 or not (build / "venv" / "pyvenv.cfg").is_file():
                    tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
                    raise StockError("сборка эталона: " + " / ".join(tail))
                if finish is not None:
                    finish(build / "venv")
                if refresh and final.is_dir():
                    shutil.rmtree(final)
                os.rename(build / "venv", final)
            finally:
                shutil.rmtree(build, ignore_errors=True)
            _sweep(lab, final.name)
        finally:
            os.close(fd)
    return final


# Уборка кэша (M3 ревью P1): брошенные сборки (.build-* после SIGKILL) и прежние эталоны —
# только по точному шаблону имени, только папки (не ссылки) прямо в pylab.
# Эталоны разных видов (light, full) живут рядом: убираются только прежние эталоны того же вида.
_STALE = re.compile(r"^(?:\.build-(?:light|full)-[0-9a-f]{16}-[0-9a-f]{8}"
                    r"|(light|full)-[0-9a-f]{16})$")
_STALE_RESTORE = re.compile(r"^\.restore-(?:light|full)-[0-9a-f]{8}$")


def _sweep(lab: Path, keep: str) -> None:
    """Зовётся под замком сборки: другой сборки сейчас нет, все .build-* — брошенные."""
    try:
        names = os.listdir(lab)
    except OSError:
        return
    kind = keep.split("-", 1)[0]
    for name in names:
        if _STALE_RESTORE.match(name):
            # временный клон reset (_restore) — свой убирает сам; брошенный (SIGKILL) живёт
            # не дольше суток: идущий сейчас reset в чужом процессе моложе
            try:
                st = os.lstat(lab / name)
                if stat.S_ISDIR(st.st_mode) and time.time() - st.st_mtime > 86400:
                    shutil.rmtree(lab / name, ignore_errors=True)
            except OSError:
                pass
            continue
        m = _STALE.match(name)
        if name == keep or not m or (m.group(1) and m.group(1) != kind):
            continue
        p = lab / name
        try:
            if not stat.S_ISDIR(os.lstat(p).st_mode):
                continue
        except OSError:
            continue
        shutil.rmtree(p, ignore_errors=True)


def _clone(src: Path, dst: Path) -> None:
    """cp -c -R -p: APFS clonefile (почти мгновенно), права и время — как у источника."""
    r = subprocess.run(["/bin/cp", "-c", "-R", "-p", str(src), str(dst)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise StockError(f"копия запаса: {r.stderr.strip()[:200]}")


STOCK_KINDS = ("light", "wheels", "full", "third")
# что лежит в запасе каждого вида: light — клон эталона; wheels — колёса учебных пакетов и
# тот же light (из него задачи pip берут свой .venv: kit.venv_from_stock и venv_drop); full
# (часть 10, «Аналитика») — эталон с pandas и requests; third — колёса склада и light
# (pd_install ставит pandas сам: ему не нужен эталон full и его сборка, M2 ревью Q4)
STOCK_PARTS = {"light": ("light",), "wheels": ("wheels", "light"), "full": ("full",),
               "third": ("third", "light")}
# виды запаса, которым нужен склад колёс (./termit wheels get)
WAREHOUSE_KINDS = ("full", "third")


def stock_problem(kind: str) -> Optional[str]:
    """Почему запас kind в песочницу не положить (None — можно): для missing() задачи, до
    sandbox.create (M7 ревью P1). Дёшево: собранный эталон — только проверка папки; склад
    колёс (full) — наличие и размеры файлов (sha256 — один раз за процесс, verify)."""
    if kind not in STOCK_KINDS:
        return f"нет такого запаса: {kind}"
    info = track_python()
    if info is None:
        return NO_PYTHON
    if kind in WAREHOUSE_KINDS:
        why = warehouse_problem(info)
        if why:
            return why
    finals = [light_path(info)] + ([full_path(info)] if kind == "full" else [])
    if all(f.is_dir() for f in finals):
        return None
    for f in finals:
        if f.name in _failed:
            return _failed[f.name]
    if not shutil.which("sandbox-exec"):
        return NO_SANDBOX
    return None


STANDIN_ENV = "TERMIT_FULL_STANDIN"


def standin() -> bool:
    """Запас full без склада — на подмене (light вместо full, склад пуст): только для тестов
    и статического линтера (TERMIT_FULL_STANDIN=1), чтобы тексты и state задач «Аналитики»
    проверялись без pandas. В игре задача без склада до sandbox.create не доходит: missing()
    честно отказывает (stock_problem подмену не учитывает)."""
    return os.environ.get(STANDIN_ENV) == "1" and warehouse_problem() is not None


def _wheel_files():
    from termit_app.pylibs import wheelmake
    return sorted(wheelmake.build_all().values())


def _third_files():
    """Колёса склада под эту машину (по пинам), по алфавиту."""
    return sorted(third_dir() / f for _, f, _ in warehouse_files())


def stock_into(box, kind: str) -> Path:
    """Запас задачи в box/.termit/stock (родитель, до zsh): части STOCK_PARTS[kind]. Вернуть
    путь первой части (box/.termit/stock/<kind>)."""
    if kind not in STOCK_KINDS:
        raise StockError(f"нет такого запаса: {kind}")
    root = Path(box) / STOCK_DIR
    root.mkdir(parents=True, exist_ok=True)
    for part in STOCK_PARTS[kind]:
        dst = root / part
        how, src = _sources(part)
        if how == "tree":
            _clone(src, dst)
        else:
            dst.mkdir()
            for p in src:
                _clone(p, dst / p.name)
    return root / kind


# --- Сверка запаса при reset (M7 ревью P1) ------------------------------------------------
# Запас лежит в песочнице, и игрок может его испортить: pip install в «не тот» venv, правка,
# rm, подмена ссылкой. reset клонирует .venv задачи из запаса, поэтому хук до rebuild
# спрашивает судью (op stock), а родитель сверяет запас с кэшем — по списку записей: путь,
# вид, размер, время и права файлов (cp -p их сохраняет), цель ссылок — и испорченную часть
# кладёт заново. Запись — под профилем этой песочницы (sandbox-exec): ссылка, подложенная
# вместо папки запаса, наружу не уведёт. Обход — без перехода по ссылкам и с пределом записей.
MANIFEST_CAP = 60000             # full: pandas и numpy с pyc — около 10 тысяч записей


def manifest(root, cap: Optional[int] = None) -> Optional[list]:
    """Список записей дерева root (без перехода по ссылкам); root не папка или записей больше
    cap (по умолчанию MANIFEST_CAP) — None."""
    cap = MANIFEST_CAP if cap is None else cap
    root = Path(root)
    try:
        if not stat.S_ISDIR(os.lstat(root).st_mode):
            return None
    except OSError:
        return None
    out, stack = [], [""]
    while stack:
        rel = stack.pop()
        try:
            with os.scandir(root / rel if rel else root) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            return None
        for e in entries:
            if len(out) >= cap:
                return None
            sub = f"{rel}/{e.name}" if rel else e.name
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                return None
            mode = stat.S_IMODE(st.st_mode)
            if stat.S_ISLNK(st.st_mode):
                try:
                    out.append((sub, "l", os.readlink(root / sub)))
                except OSError:
                    return None
            elif stat.S_ISDIR(st.st_mode):
                out.append((sub, "d", mode))
                stack.append(sub)
            elif stat.S_ISREG(st.st_mode):
                out.append((sub, "f", mode, st.st_size, int(st.st_mtime)))
            else:
                out.append((sub, "?", mode))
    return sorted(out)


def _sources(part: str):
    """Откуда часть запаса: ("tree", папка) или ("files", [файлы])."""
    if part == "light":
        return "tree", build_light()
    if part == "full":
        return "tree", (build_light() if standin() else build_full())
    if part == "third":
        return "files", ([] if standin() else _third_files())
    return "files", _wheel_files()


def _want(part: str) -> Optional[list]:
    how, src = _sources(part)
    if how == "tree":
        return manifest(src)
    out = []
    for p in src:
        st = os.lstat(p)
        out.append((p.name, "f", stat.S_IMODE(st.st_mode), st.st_size, int(st.st_mtime)))
    return sorted(out)


RESTORE_TREE = 'rm -rf -- "$1" && mkdir -p -- "${1%/*}" && cp -c -R -p -- "$2" "$1"'
RESTORE_FILES = ('dst=$1; shift; rm -rf -- "$dst" && mkdir -p -- "$dst" && '
                 'cp -c -p -- "$@" "$dst"/')


def _restore(box: Path, part: str) -> None:
    """Часть запаса заново — под профилем песочницы box (запись только в неё). Файлы с именами
    секретов профиля (certifi/cacert.pem у requests, pip/_vendor/certifi у любого venv) профиль
    из кэша прочесть не даёт: дерево копируется из временного клона кэша без них, а их кладёт
    родитель сам (_put_secret: по звеньям без перехода по ссылкам, только новый файл)."""
    from termit_app import shell_run
    how, src = _sources(part)
    if not shutil.which("sandbox-exec"):
        # без профиля rm -rf и cp шли бы по пути, который мог подменить игрок (M5 ревью P4)
        raise StockError(NO_SANDBOX)
    dst = str(box / STOCK_DIR / part)
    hidden = _secret_rel(src) if how == "tree" else []
    stage = None
    try:
        if how == "tree":
            if hidden:
                stage = lab_dir() / f".restore-{part}-{secrets.token_hex(4)}"
                _clone(src, stage)
                for rel in hidden:
                    _remove_exact(stage / rel)
            argv = ["/bin/sh", "-c", RESTORE_TREE, "sh", dst, str(stage or src)]
        else:
            argv = ["/bin/sh", "-c", RESTORE_FILES, "sh", dst] + [str(p) for p in src]
        argv = ["sandbox-exec", "-p", shell_run.task_profile(box, Path.home(), ttys=())] + argv
        try:
            r = subprocess.run(argv, cwd=str(box), env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                               capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as e:
            raise StockError(f"запас заново: {e}") from None
        if r.returncode != 0:
            raise StockError("запас заново: " + (r.stderr.strip()[-200:] or str(r.returncode)))
        for rel in hidden:
            _put_secret(box, f"{STOCK_DIR}/{part}/{rel}", src / rel)
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


# пути (относительно эталона) файлов с именами секретов: эталон в кэше не меняется, поэтому
# список один на процесс для каждой папки
_secret_seen = {}


def _secret_rel(src: Path) -> List[str]:
    key = str(src)
    if key not in _secret_seen:
        _secret_seen[key] = [p.relative_to(src).as_posix() for p in _secret_like(src)]
    return _secret_seen[key]


def _put_secret(box: Path, rel: str, src: Path) -> None:
    """Файл src — в box/rel родителем, вне профиля. Песочницу мог перестроить игрок, поэтому
    путь проходится по звеньям через openat с O_NOFOLLOW (ссылка вместо папки наружу не
    уведёт), а файл создаётся только новым (O_EXCL); права и время файла и его папки — как
    в кэше (сверка манифеста)."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        st = os.stat(src)
        fd = os.open(str(box), flags)
        try:
            for name in rel.split("/")[:-1]:
                nxt = os.open(name, flags, dir_fd=fd)
                os.close(fd)
                fd = nxt
            out = os.open(rel.rsplit("/", 1)[-1],
                          os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                          dir_fd=fd)
            try:
                with open(src, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 16), b""):
                        os.write(out, chunk)
                os.fchmod(out, stat.S_IMODE(st.st_mode))
                os.utime(out, ns=(st.st_atime_ns, st.st_mtime_ns))
            finally:
                os.close(out)
            up = os.stat(src.parent)            # и время папки — как у клона (cp -p)
            os.utime(fd, ns=(up.st_atime_ns, up.st_mtime_ns))
        finally:
            os.close(fd)
    except OSError as e:
        raise StockError(f"запас заново: {rel}: {e.strerror}") from None


def refresh_stock(box, kind: str) -> str:
    """Сверить запас песочницы с кэшем: "same" — цел, "restored" — испорченные части положены
    заново. Не вышло — StockError (судья отдаёт причину хуку)."""
    if kind not in STOCK_KINDS:
        raise StockError(f"нет такого запаса: {kind}")
    box = Path(box)
    fixed = False
    for part in STOCK_PARTS[kind]:
        want = _want(part)
        if want is not None and manifest(box / STOCK_DIR / part) == want:
            continue
        _restore(box, part)
        if manifest(box / STOCK_DIR / part) != want:
            raise StockError(f"запас {part} не сходится с кэшем после восстановления")
        fixed = True
    return "restored" if fixed else "same"


# --- Склад колёс сторонних пакетов (A3) ------------------------------------------------------
# pandas и requests с зависимостями — колёса по пинам pylibs/lock.py (sha256 из PyPI) в
# .cache/wheels/third. Качает ТОЛЬКО родитель и только по явному «y» владельца
# (./termit wheels get или вопрос в конце рана): pip download --no-deps --only-binary=:all:
# --require-hashes -r <пины этой архитектуры> с PIP_CONFIG_FILE=/dev/null и явным PyPI.
# --only-binary — sdist не собирается, ничей setup.py не исполняется. Хэш не сошёлся — файл
# удаляется по точному пути, всё прерывается. Тесты не качают никогда: TERMIT_NO_NET (вызов
# падает) и сторож pip download в tests/__init__.py.
THIRD_DIR = ("wheels", "third")         # в paths.CACHE_DIR
INDEX_URL = "https://pypi.org/simple"
GET_TIMEOUT = 900
NO_WAREHOUSE = "нужен склад пакетов: ./termit wheels get (скачает один раз, нужна сеть)"
BAD_WAREHOUSE = "склад пакетов повреждён: ./termit wheels verify, потом ./termit wheels get"
NEED_39 = ("склад пакетов собран под Python 3.9, а у игры {ver}: трек «Аналитика» "
           "пока закрыт (нужен Python из Command Line Tools: xcode-select --install)")
NO_ARCH = "склад пакетов есть только для Mac на arm64 и x86_64, а здесь {arch}"


class WarehouseError(RuntimeError):
    """Склад не скачать или не проверить (нет сети, хэш не сошёлся, не та машина)."""


def third_dir() -> Path:
    return Path(paths.CACHE_DIR).joinpath(*THIRD_DIR)


def warehouse_files(info: Optional[PyInfo] = None):
    """[(пин, файл, sha256)] склада под интерпретатор треков. Не 3.9 или чужая архитектура
    — WarehouseError с понятной причиной."""
    from termit_app.pylibs import lock
    info = info or track_python()
    if info is None:
        raise WarehouseError(NO_PYTHON)
    if info.version[:2] != TRACK_VERSION:
        raise WarehouseError(NEED_39.format(ver=info.short))
    if info.arch not in lock.ARCHES:
        raise WarehouseError(NO_ARCH.format(arch=info.arch))
    return lock.files_for(info.arch)


# проверенные sha256 в этом процессе: путь → (размер, mtime_ns); файл сменился — проверим снова
_verified = {}


def _file_sha(path: Path) -> Optional[str]:
    """sha256 обычного файла (не ссылки); нет файла — None."""
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        h = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    finally:
        os.close(fd)


def _stamp(path: Path):
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    return (st.st_size, st.st_mtime_ns)


def verify(info: Optional[PyInfo] = None, remove_bad: bool = False):
    """Сверка склада с пинами: (годные, недостающие, испорченные) — списки имён файлов.
    remove_bad — испорченные удаляются по точному пути (только обычные файлы и ссылки)."""
    good, absent, bad = [], [], []
    d = third_dir()
    for _, fname, sha in warehouse_files(info):
        p = d / fname
        stamp = _stamp(p)
        if stamp is None and not os.path.lexists(p):
            absent.append(fname)
            continue
        if stamp is not None and _verified.get(str(p)) == stamp:
            good.append(fname)
            continue
        if stamp is not None and _file_sha(p) == sha:
            _verified[str(p)] = stamp
            good.append(fname)
            continue
        bad.append(fname)
        _verified.pop(str(p), None)
        if remove_bad:
            _remove_exact(p)
    return good, absent, bad


def _remove_exact(p: Path) -> None:
    """Удалить один файл (или ссылку) по точному пути; папку не трогаем."""
    try:
        st = os.lstat(p)
    except OSError:
        return
    if stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
        os.unlink(p)


def warehouse_problem(info: Optional[PyInfo] = None) -> Optional[str]:
    """Почему склада нет (None — есть и проверен): не та машина, нет файлов, порча."""
    try:
        _, absent, bad = verify(info)
    except WarehouseError as e:
        return str(e)
    except ValueError as e:
        return str(e)
    if bad:
        return BAD_WAREHOUSE
    if absent:
        return NO_WAREHOUSE
    return None


def warehouse_ready(info: Optional[PyInfo] = None) -> bool:
    return warehouse_problem(info) is None


def download_argv(info: PyInfo, req: Path, dest: Path):
    """Ровно то, что запустит get_wheels (./termit wheels status показывает правду)."""
    return [info.path, "-m", "pip", "download", "--no-deps", "--only-binary=:all:",
            "--require-hashes", "--index-url", INDEX_URL, "-r", str(req), "-d", str(dest)]


def _download_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PIP_", "PYTHON"))}
    env.update({"PIP_CONFIG_FILE": "/dev/null", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_NO_INPUT": "1"})
    return env


def get_wheels(info: Optional[PyInfo] = None, runner=None) -> Tuple[bool, str]:
    """ЕДИНСТВЕННОЕ место скачивания склада (родитель, после явного «y»). Вернуть (успех,
    строка для игрока). Под TERMIT_NO_NET (все тесты) — WarehouseError до любого запуска;
    runner — подмена subprocess.run для тестов (тогда сеть не нужна и не трогается)."""
    if os.environ.get("TERMIT_NO_NET") and runner is None:
        raise WarehouseError("сеть в тестах запрещена: pip download не запускается")
    from termit_app.pylibs import lock
    info = info or track_python()
    files = warehouse_files(info)
    d = third_dir()
    d.mkdir(parents=True, exist_ok=True)
    req = d.parent / f".third-{secrets.token_hex(4)}.txt"
    try:
        req.write_text(lock.requirements(info.arch), encoding="utf-8")
        try:
            r = (runner or subprocess.run)(download_argv(info, req, d), env=_download_env(),
                                           timeout=GET_TIMEOUT)
            code = r.returncode
        except (OSError, subprocess.SubprocessError) as e:
            reason = str(e)[:200]
        else:
            reason = f"pip download: код {code}"
    finally:
        _remove_exact(req)
    good, absent, bad = verify(info, remove_bad=True)
    if bad:
        return False, f"хэш не сошёлся — удалил: {', '.join(bad)}. Скачивание прервано."
    if absent:
        return False, f"склад не собран ({reason}): нет {len(absent)} из {len(files)} колёс"
    return True, f"склад на месте: {len(good)} колёс в {d}"


def clean() -> List[str]:
    """./termit wheels clean: удалить склад и эталоны full — только свои папки по точным
    путям, без масок. Вернуть список удалённого."""
    out = []
    d = third_dir()
    try:
        if stat.S_ISDIR(os.lstat(d).st_mode):
            shutil.rmtree(d)
            out.append(str(d))
    except OSError:
        pass
    info = track_python()
    if info is not None:
        try:
            f = full_path(info)
        except (WarehouseError, ValueError):
            f = None
        if f is not None and f.is_dir() and not f.is_symlink():
            shutil.rmtree(f)
            out.append(str(f))
    _verified.clear()
    return out


# --- Эталон full (A4, часть 10) ----------------------------------------------------------------
# light плюс pandas и requests с зависимостями — из склада по пинам: pip install --no-index
# --find-links third --require-hashes --only-binary=:all: -r <пины>, затем compileall
# --invalidation-mode unchecked-hash (иначе import pandas каждый раз компилирует модули). Всё
# под sandbox-exec, как light; колёса склада родитель клонирует в папку сборки (cp -c).
# Файлы с именами секретов профиля (certifi/cacert.pem) в эталоне ОСТАЮТСЯ: без него не
# импортируется requests (requests/utils.py берёт certifi.where() на уровне модуля, 2.32.x ещё и
# читает PEM). В песочницу их кладёт родитель (stock_into, а при reset — _put_secret): профиль
# не даёт песочнице читать их из кэша, а внутри box они читаются.
# Python от Apple кладёт pyc не рядом с модулем, а в $HOME/Library/Caches/com.apple.python/<полный
# путь> (sys.pycache_prefix): у клона в песочнице путь другой, и import pandas компилировал бы всё
# заново в каждой задаче. Поэтому в site-packages эталона — PTH_NAME: при старте venv он
# выключает префикс, и годятся pyc из __pycache__ рядом с модулями (их и собирает compileall).
PTH_NAME = "termit-pyc.pth"
PTH_TEXT = "import sys; sys.pycache_prefix = None\n"
FULL_SCRIPT = (LIGHT_SCRIPT + " && venv/bin/python -m pip install --no-index --find-links third "
               "--require-hashes --only-binary=:all: -r third.txt && for d in "
               "venv/lib/python3.*/site-packages; do printf '%s\\n' "
               "'import sys; sys.pycache_prefix = None' > \"$d/" + PTH_NAME + "\"; done && "
               "venv/bin/python -X pycache_prefix= -m compileall -q --invalidation-mode "
               "unchecked-hash venv/lib")


def full_hash(info: Optional[PyInfo] = None) -> str:
    """Хэш эталона full: эталон light (его хэш) и пины склада этой машины."""
    info = info or track_python()
    h = hashlib.sha256()
    h.update(json.dumps([BUILD_VERSION, light_hash(info),
                         [list(x) for x in warehouse_files(info)]]).encode())
    return h.hexdigest()[:16]


def full_path(info: Optional[PyInfo] = None) -> Path:
    return lab_dir() / f"full-{full_hash(info)}"


def _secret_like(venv: Path) -> List[Path]:
    """Файлы эталона, чьи пути профиль песочницы считает секретами (SECRET_REGEX)."""
    from termit_app import shell_run
    rx = [re.compile(r"(?:^|/)" + r) for r in shell_run.SECRET_REGEX]
    out = []
    for dirpath, _, names in os.walk(venv):
        for n in names:
            p = os.path.join(dirpath, n)
            rel = os.path.relpath(p, venv)
            if any(r.search(rel) for r in rx):
                out.append(Path(p))
    return sorted(out)


def build_full(refresh: bool = False) -> Path:
    """Эталон full в кэше (собрать, если его нет). Нет склада или сборка упала — StockError."""
    from termit_app.pylibs import lock, wheelmake
    info = track_python()
    if info is None:
        raise StockError(NO_PYTHON)
    why = warehouse_problem(info)
    if why:
        raise StockError(why)
    final = full_path(info)
    if final.is_dir() and not refresh:
        return final
    if not shutil.which("sandbox-exec"):
        raise StockError(NO_SANDBOX)

    def prepare(build: Path) -> None:
        for pkg in _light_wheels():
            wheelmake.build_wheel(pkg, build / "wheels")
        (build / "third").mkdir()
        for p in _third_files():
            _clone(p, build / "third" / p.name)
        (build / "third.txt").write_text(lock.requirements(info.arch), encoding="utf-8")

    try:
        return _build_venv(info, final, refresh, prepare, FULL_SCRIPT)
    except StockError as e:
        _failed[final.name] = str(e)
        raise
