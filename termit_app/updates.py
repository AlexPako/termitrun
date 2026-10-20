"""Проверка «вышло обновление» и команда update.

Работает только в публичной копии, которая лежит git-клоном репозитория игры. Спрашивает у
git один раз в сутки, ничего своего в сеть не шлёт; нет сети или git — молчит."""
import json
import os
import re
import subprocess
import threading
import time
from typing import Callable, Optional, Tuple

from termit_app import edition, paths

DAY = 86400
TIMEOUT = 3
REPO = "AlexPako/termitrun"
OFF_VARS = ("TERMIT_NO_NET", "TERMIT_NO_UPDATE_CHECK")

NOTICE = "📦 Вышло обновление игры. Обнови: update (или git pull в папке игры). Прогресс не пропадёт."
DONE = "Готово, игра обновлена. Перезапусти её: выйди (quit) и запусти ./termit снова."
UP_TO_DATE = "У тебя последняя версия игры."
PRIVATE = "В этой копии игры обновлений нет: она не из публичного репозитория."
NOT_A_CLONE = ("Эта копия игры не скачана через git, поэтому сама обновиться не может. "
               "Скачай свежую: git clone https://github.com/AlexPako/termitrun.git")
DIRTY = ("В папке игры есть твои правки файлов, поэтому я ничего не трогаю — "
         "чтобы они не пропали. Верни их (git checkout -- .) или сохрани отдельно "
         "(git stash) и набери update ещё раз. Прогресс (progress.json) лежит вне git и цел.")
DIVERGED = ("Твоя копия разошлась с репозиторием: в ней есть свои коммиты, и обновиться "
            "без склейки нельзя. Проще всего скачать игру заново: git clone "
            "https://github.com/AlexPako/termitrun.git — а progress.json перенеси в новую папку.")
NO_GIT = "Не получилось запустить git. Проверь, что он установлен (git --version)."

Runner = Callable[..., Tuple[int, str]]


def run_git(argv, timeout=TIMEOUT) -> Tuple[int, str]:
    """Настоящий запуск git: без вопросов в терминале, с таймаутом."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND="ssh -o BatchMode=yes")
    done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env,
                          stdin=subprocess.DEVNULL)
    return done.returncode, done.stdout


def _git(runner: Runner, *args, timeout=TIMEOUT) -> Tuple[int, str]:
    return runner(["git", "-C", str(paths.ROOT)] + list(args), timeout=timeout)


def _off(env) -> bool:
    return any(env.get(name) for name in OFF_VARS)


def _is_clone() -> bool:
    return (paths.ROOT / ".git").exists()


def _ours(runner: Runner) -> bool:
    code, out = _git(runner, "remote", "get-url", "origin")
    return code == 0 and re.search(rf"github\.com[:/]{REPO}(\.git)?\s*$", out, re.I) is not None


def _load() -> dict:
    try:
        data = json.loads((paths.CACHE_DIR / "update.json").read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    try:
        paths.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (paths.CACHE_DIR / "update.json").write_text(json.dumps(data))
    except OSError:
        pass


def _newer(data: dict, local: str) -> bool:
    return bool(data.get("newer")) and data.get("local") == local


def check(runner: Runner = run_git, now: float = None, env=None) -> bool:
    """Есть ли новее. Не чаще раза в сутки: между проверками отвечает кэш. Любая ошибка — False."""
    env = os.environ if env is None else env
    if not edition.ISSUES_URL or _off(env) or not _is_clone():
        return False
    now = time.time() if now is None else now
    try:
        code, out = _git(runner, "rev-parse", "HEAD")
        local = out.strip()
        if code != 0 or not local:
            return False
        data = _load()
        if data.get("local") == local and now - data.get("checked", 0) < DAY:
            return _newer(data, local)
        if not _ours(runner):
            return False
        code, out = _git(runner, "ls-remote", "origin", "refs/heads/main")
        remote = out.split()[0] if code == 0 and out.split() else ""
        if not remote:
            return False
        newer = remote != local
        if newer:
            # если удалённый коммит уже у нас в истории, мы впереди, а не позади
            ahead, _ = _git(runner, "merge-base", "--is-ancestor", remote, "HEAD")
            newer = ahead != 0
        data = {"checked": now, "local": local, "remote": remote, "newer": newer,
                "shown": data.get("shown", "")}
        _save(data)
        return newer
    except (OSError, subprocess.SubprocessError):
        return False


def start(runner: Runner = run_git, env=None) -> Optional[threading.Thread]:
    """Проверка в фоне при старте игры: игру не тормозит. None — проверка выключена."""
    env = os.environ if env is None else env
    if not edition.ISSUES_URL or _off(env):
        return None
    thread = threading.Thread(target=check, args=(runner,), kwargs={"env": env}, daemon=True)
    thread.start()
    return thread


def notice(env=None, today: str = None) -> Optional[str]:
    """Сообщение «вышло обновление» — раз в день, только если проверка нашла новее."""
    env = os.environ if env is None else env
    if not edition.ISSUES_URL or _off(env):
        return None
    data = _load()
    today = today or time.strftime("%Y-%m-%d")
    if not data.get("newer") or data.get("shown") == today:
        return None
    data["shown"] = today
    _save(data)
    return NOTICE


def pull(runner: Runner = run_git) -> Tuple[bool, str]:
    """Команда update: git pull --ff-only, но только если правок нет. Возвращает (успех, текст)."""
    if not edition.ISSUES_URL:
        return False, PRIVATE
    if not _is_clone():
        return False, NOT_A_CLONE
    try:
        code, out = _git(runner, "status", "--porcelain", "--untracked-files=no")
        if code != 0:
            return False, NO_GIT
        if out.strip():
            return False, DIRTY
        code, _ = _git(runner, "pull", "--ff-only", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False, NO_GIT
    if code != 0:
        return False, DIVERGED
    _save({})
    return True, DONE


def update_text(runner: Runner = run_git) -> Tuple[bool, str]:
    """То же, что pull(), для вызова из cli и хаба."""
    return pull(runner)
