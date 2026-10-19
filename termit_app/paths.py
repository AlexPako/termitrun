"""Где что лежит: корень проекта, песочница, прогресс, настройки zsh, кэш звука."""
import os
import shlex
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
SANDBOX_ROOT = ROOT / ".sandbox"
PROGRESS_FILE = ROOT / "progress.json"
SHELL_DIR = Path(__file__).resolve().parent / "shell"
FEEDBACK_FILE = ROOT / "feedback.jsonl"
# кэш сгенерированного звука (synth → WAV) и PID-файл деки: в проекте и в .gitignore, в дом
# ничего не пишется. TERMIT_CACHE_DIR — только для тестов (временная папка на весь прогон) и
# принимается, только если лежит во временной папке системы: в дом её не направить.
DEFAULT_CACHE_DIR = ROOT / ".cache"


def _cache_dir(raw) -> Path:
    import tempfile
    if not raw:
        return DEFAULT_CACHE_DIR
    real = os.path.realpath(raw)
    tmp = os.path.realpath(tempfile.gettempdir())
    home = os.path.realpath(str(Path.home()))
    if tmp == home or tmp.startswith(home.rstrip("/") + "/"):
        return DEFAULT_CACHE_DIR        # TMPDIR в доме — так в дом не направить
    return Path(real) if real.startswith(tmp.rstrip("/") + "/") else DEFAULT_CACHE_DIR


CACHE_DIR = _cache_dir(os.environ.get("TERMIT_CACHE_DIR"))


# Запуск модулей игры из песочницы — хук (.zshrc, _tr), обёртки .termit/bin, launch (решение 12
# журнала, спайк S0 п. 8): python -I -B -c BOOT КОРЕНЬ МОДУЛЬ АРГУМЕНТЫ. -I — без cwd и папки
# скрипта в sys.path, без PYTHON* окружения и пользовательского site: подложенные игроком
# termit_app/, json.py, sitecustomize.py, PYTHONPATH, PYTHONHOME и PYTHONSTARTUP не действуют
# (с -m и PYTHONPATH=ROOT пакет termit_app/ в cwd перехватывал хук). -B — pyc не пишутся (под -I
# PYTHONDONTWRITEBYTECODE не читается). Корень — аргументом, не из окружения игрока. В BOOT нет
# одинарных кавычек: песочный .zshrc держит его в '…' (_tr_boot).
BOOT = ("import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); "
        "runpy.run_module(sys.argv.pop(1), run_name=\"__main__\", alter_sys=True)")


def py_argv(module: str, *args, py: str = None) -> List[str]:
    """argv запуска модуля игры через BOOT (py — интерпретатор, по умолчанию игры)."""
    return [py or sys.executable, "-I", "-B", "-c", BOOT, str(ROOT), module] + [str(a) for a in args]


def py_line(module: str, *args, py: str = None) -> str:
    """Строка для sh-обёртки: exec … "$@" (аргументы игрока — как есть)."""
    return "exec " + " ".join(shlex.quote(a) for a in py_argv(module, *args, py=py)) + ' "$@"'
