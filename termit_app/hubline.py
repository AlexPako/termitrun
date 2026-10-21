"""Строка ввода убежища: история (свой файл в .cache), readline (на этом Mac — libedit),
режим терминала после рана, сигналы закрытия окна, лог ошибок хаба (спека 2.1, 2.8)."""
import os
import re
import signal
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from termit_app import paths

try:
    import termios
except ImportError:          # не Unix — режим терминала не трогаем
    termios = None

HISTORY_MAX = 300
LINE_MAX = 200
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def history_path() -> Path:
    return paths.CACHE_DIR / "hub_history"


def load_history(path) -> List[str]:
    """Битый или чужой файл — пустая история, без ошибки."""
    try:
        raw = Path(path).read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    lines = [_CTRL.sub("", x) for x in raw.splitlines()]
    return [x for x in lines if x.strip() and len(x) <= LINE_MAX][-HISTORY_MAX:]


def add_line(history: List[str], line: str) -> List[str]:
    """Строка в историю: без управляющих символов, без пустых и длинных, повтор подряд —
    один раз; держим последние HISTORY_MAX."""
    line = _CTRL.sub("", line).strip()
    if not line or len(line) > LINE_MAX or (history and history[-1] == line):
        return list(history)
    return (list(history) + [line])[-HISTORY_MAX:]


def save_history(path, history: List[str]) -> None:
    """Атомарно (tmp + replace); не вышло записать — молча: история не главное."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".hub_history-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in history))
        os.replace(tmp, path)
    except OSError:
        pass


def is_libedit(module) -> bool:
    doc = module.__doc__ or ""
    return getattr(module, "backend", "") == "editline" or "libedit" in doc or "EditLine" in doc


def setup_readline(completer, module=None):
    """Tab и дополнение; цвет в приглашение не кладём - libedit его ломает (eng 2.1)."""
    if module is None:
        try:
            import readline as module
        except ImportError:
            return None
    if is_libedit(module):
        module.parse_and_bind("bind ^I rl_complete")
    else:
        module.parse_and_bind("tab: complete")
    module.set_completer_delims(" ")     # id с _ и - дописываются целиком
    module.set_completer(completer)
    return module


class LineEditor:
    """Строка убежища. readline - только в настоящем терминале; в трубе и тестах - input().
    История - свой список: ответы «y» и строки рана в ↑ убежища не попадают."""

    def __init__(self, path, complete: Optional[Callable[[str], List[str]]] = None,
                 tty: Optional[bool] = None, module=None):
        self.path = Path(path)
        self.history = load_history(self.path)
        self.complete = complete
        self._matches: List[str] = []
        if tty is None:
            tty = sys.stdin.isatty() and sys.stdout.isatty()
        self.tty = tty
        self.rl = setup_readline(self._completer, module) if tty else None

    def _completer(self, text, state):
        if state == 0:
            before = self.rl.get_line_buffer()[:self.rl.get_endidx()]
            self._matches = self.complete(before) if self.complete else []
        return self._matches[state] if state < len(self._matches) else None

    def _sync(self) -> None:
        self.rl.clear_history()
        for line in self.history:
            self.rl.add_history(line)

    def read(self, prompt: str) -> str:
        if self.rl is not None:
            self._sync()
        return input(prompt)

    def remember(self, line: str) -> None:
        self.history = add_line(self.history, line)
        save_history(self.path, self.history)


def term_save() -> Optional[list]:
    if termios is None or not os.isatty(0):
        return None
    try:
        return termios.tcgetattr(0)
    except Exception:       # noqa: BLE001 - не терминал, не беда
        return None


def term_restore(saved) -> None:
    """После рана: режим терминала как при входе (убитый zsh мог оставить без эха), набитые
    во время итога Enter - прочь, курсор - видимый."""
    if saved is None or termios is None or not os.isatty(0):
        return
    try:
        termios.tcsetattr(0, termios.TCSANOW, saved)
        termios.tcflush(0, termios.TCIFLUSH)
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
    except Exception:       # noqa: BLE001
        pass


def drop_typeahead() -> None:
    if termios is None or not os.isatty(0):
        return
    try:
        termios.tcflush(0, termios.TCIFLUSH)
    except Exception:       # noqa: BLE001
        pass


def install_signals() -> dict:
    """Закрыли окно (SIGHUP) или прислали SIGTERM - штатный выход: срабатывают finally
    (песочница рана, музыка, история)."""
    def stop(signum, frame):
        raise SystemExit(128 + signum)

    old = {}
    for sig in (signal.SIGHUP, signal.SIGTERM):
        old[sig] = signal.signal(sig, stop)
    return old


def restore_signals(old: dict) -> None:
    for sig, handler in old.items():
        signal.signal(sig, handler)


def log_error(exc: BaseException) -> Path:
    path = paths.CACHE_DIR / "hub-errors.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"--- {datetime.now().isoformat(timespec='seconds')}\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except OSError:
        pass
    return path
