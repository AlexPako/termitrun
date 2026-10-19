"""Временные папки прогонов (тесты, линтер) с PID в имени и их уборка.

Имя — «<вид>-<PID>-<8 знаков mkdtemp>», вид — из KINDS. Обычно папку убирает её процесс
(finally, atexit). Если процесс погиб раньше (воркер пула, убитый прогон), уборка подбирает
её по имени: известный вид + PID процесса, которого уже нет (sweep) или который был воркером
только что закрытого пула (pool_map). Убираются только обычные папки нашего пользователя, не
симлинки; песочницы внутри — через sandbox.cleanup_stale (процессы песочницы гасятся), затем
rmtree с возвратом прав. Чужие и «похожие» имена не трогаются никогда."""
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

KINDS = ("termit-lint-stock-light", "termit-lint-stock-wheels", "termit-lint-stock-full",
         "termit-lint-stock-third",
         "termit-lint", "termit-test",
         "termit-fuzz", "termit-test-cache", "termit-test-run")
_NAME = re.compile(r"^(?P<kind>" + "|".join(sorted(map(re.escape, KINDS), key=len, reverse=True))
                   + r")-(?P<pid>[1-9][0-9]{0,9})-[A-Za-z0-9_]{8}$")


def default_dirs() -> List[str]:
    """Где прогоны создают свои папки: /private/tmp и системная временная папка."""
    out = []
    for d in ("/private/tmp", tempfile.gettempdir()):
        real = os.path.realpath(d)
        if real not in out:
            out.append(real)
    return out


def mkdtemp(kind: str, dir: Optional[str] = None) -> str:
    """tempfile.mkdtemp с именем «вид-PID-…»; вид — только из KINDS."""
    if kind not in KINDS:
        raise ValueError(f"неизвестный вид временной папки: {kind}")
    return tempfile.mkdtemp(prefix=f"{kind}-{os.getpid()}-", dir=dir)


def owner_pid(name: str) -> Optional[int]:
    """PID из имени папки нашей схемы, иначе None."""
    m = _NAME.match(name)
    return int(m.group("pid")) if m else None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:         # процесс есть, просто чужой
        return True
    return True


def _remove(path: Path) -> bool:
    from termit_app import sandbox
    try:
        sandbox.cleanup_stale(path)
    except (OSError, RuntimeError):
        pass                        # песочница с живыми процессами — rmtree заберёт остальное
    sandbox._unlock(path)
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.lexists(path)


def sweep(pids: Optional[Iterable[int]] = None,
          dirs: Optional[Sequence[str]] = None) -> List[str]:
    """Убрать папки нашей схемы: pids=None — тех процессов, которых уже нет; иначе — ровно этих
    PID (воркеры закрытого пула), если они уже завершились. Вернуть убранные пути."""
    want = None if pids is None else set(pids)
    uid = os.getuid()
    gone = []
    for base in (dirs if dirs is not None else default_dirs()):
        try:
            entries = list(os.scandir(base))
        except OSError:
            continue
        for e in entries:
            pid = owner_pid(e.name)
            if pid is None or pid == os.getpid() or (want is not None and pid not in want):
                continue
            try:
                st = os.lstat(e.path)
            except OSError:
                continue
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != uid or _alive(pid):
                continue
            if _remove(Path(e.path)):
                gone.append(e.path)
    return gone


def pool_map(fn: Callable, items: Sequence, jobs: int,
             extra_dirs: Sequence[str] = ()) -> list:
    """list(ProcessPoolExecutor.map(fn, items)) и после закрытия пула — уборка папок его
    воркеров (по их PID) в default_dirs() и extra_dirs: воркер, погибший без atexit, их не
    оставит."""
    from concurrent.futures import ProcessPoolExecutor
    pids = set()
    try:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            try:
                return list(ex.map(fn, items))
            finally:
                pids = set(getattr(ex, "_processes", None) or ())
    finally:
        if pids:
            sweep(pids, list(default_dirs()) + [d for d in extra_dirs
                                                if os.path.realpath(d) not in default_dirs()])
