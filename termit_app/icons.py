"""Значки треков и инструментов: узнать место и программу с одного взгляда.

Сами значки — в теме (раздел icons: tracks — трек → значок, tools — инструмент → значок),
код задач их не знает. Здесь — нейтральная часть: какой инструмент у задачи (по первым словам
команд эталона, потом шпаргалки) и когда значок вообще показывать.

Значок показывается только в rich: в basic (не-UTF-8) и plain (не tty, TERM=dumb, узкое
окно, TERMIT_PLAIN=1) его нет вовсе — строка такая же, как без значков. Каждый значок —
один символ шириной 2 (east_asian_width W/F), без вариационного селектора U+FE0F и без
склеек ZWJ: их ширина в терминалах гуляет, и рамки съезжают."""
import re
import unicodedata
from typing import Optional

from termit_app import implants, theme, tui

# слово команды → инструмент (ключ раздела icons.tools темы)
TOOL_WORDS = {
    "git": "git",
    "python3": "python", "python": "python", "pip": "python", "pip3": "python",
    "sqlite3": "sqlite",
    "psql": "postgres", "pg_dump": "postgres", "pg_restore": "postgres",
    "jq": "jq",
    "grep": "grep",
    "find": "find",
    "curl": "curl",
    "nano": "nano",
    "vim": "vim",
    "man": "man", "tldr": "man",
    "less": "less",
    "awk": "awk",
    "sed": "sed",
    "clamscan": "clamscan",
    implants.STUB_NAME: "homebrew",      # «brew» строкой — только в implants.py (I-2)
    "ps": "proc", "kill": "proc", "top": "proc",
    "zip": "archive", "tar": "archive",
    "open": "open",
    "pbcopy": "clipboard", "pbpaste": "clipboard",
}

# Где первое известное слово команды говорит не о том, чему учит задача (нейтрально, без
# значков; None — у задачи нет инструмента, остаётся значок трека): shebang_run правит первую
# строку через sed, а урок — про #!; env_vars ищет через grep, а урок — про переменные;
# constraints_fk сравнивает с sqlite3 в шпаргалке, а работает в PostgreSQL.
TASK_TOOL = {
    "shebang_run": None,
    "env_vars": None,
    "constraints_fk": "postgres",
}

# Слово в позиции команды: начало, после ; | && || ( $( → и пробелов.
_CMD = re.compile(r"(?:^|[;|&(→]|\$\()\s*(?:sudo\s+)?([a-z][a-z0-9_]*)\b")


def tool_words(text: str):
    """Слова команд строки по порядку."""
    return _CMD.findall(text or "")


def tool_of(task) -> Optional[str]:
    """Инструмент задачи: явная поправка, иначе поле tool задачи (PyEditTask — python),
    иначе первое известное слово команды эталона, иначе шпаргалки; нет такого — None (у задачи значка нет, хватает значка трека)."""
    if task.id in TASK_TOOL:
        return TASK_TOOL[task.id]
    if getattr(task, "tool", None):         # метаданные задачи (PyEditTask: эталона нет)
        return task.tool
    for text in (task.solution, task.spell):
        for w in tool_words(text):
            if w in TOOL_WORDS:
                return TOOL_WORDS[w]
    return None


def single_wide(icon: str) -> bool:
    """Один символ шириной 2, не составной: ширина в терминале предсказуема."""
    return len(icon) == 1 and unicodedata.east_asian_width(icon) in "WF"


def shown(c: tui.Caps = None) -> bool:
    c = c or tui.caps()
    return c.level == "rich"


def _section(name: str, own_only: bool) -> dict:
    cur = theme.load(theme.current()).get("icons", {}).get(name) or {}
    if own_only:
        return cur
    return {**(theme.load(theme.DEFAULT).get("icons", {}).get(name) or {}), **cur}


def track(key: str, c: tui.Caps = None) -> str:
    """Значок трека (только из выбранной темы: место — часть сеттинга) или пусто."""
    if not shown(c):
        return ""
    return _section("tracks", own_only=True).get(key, "")


def tool(name: Optional[str], c: tui.Caps = None) -> str:
    """Значок инструмента: тема, иначе нейтральный набор темы по умолчанию; или пусто."""
    if not name or not shown(c):
        return ""
    return _section("tools", own_only=False).get(name, "")


def of_task(task, c: tui.Caps = None) -> str:
    """Значок инструмента задачи; нет — значок трека; в plain/basic — пусто."""
    return tool(tool_of(task), c) or track(task.track, c)


def mark(icon: str) -> str:
    """Значок с пробелом после или пусто."""
    return f"{icon} " if icon else ""
