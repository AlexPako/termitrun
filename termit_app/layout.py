"""FB5 п. 40: русская раскладка. Набрал «ды» вместо ls — подсказать, что включена русская.

Перевод — по положению клавиш: та же клавиша в ЙЦУКЕН и в QWERTY (Mac, стандартные
раскладки «Русская — ПК» и «ABC»). В песочнице его зовёт command_not_found_handler
(.zshrc → _termit_layout_hint → hook layout)."""
from typing import Optional

from termit_app.implants import STUB_NAME     # «brew» — только из implants (охрана I-2)

RU = "йцукенгшщзхъфывапролджэячсмитьбю.ё"
EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,./`"
_MAP = {**dict(zip(RU, EN)), **dict(zip(RU.upper(), EN.upper()))}

# что новичок набирает в игре чаще всего: перевод в одну из них — почти наверняка раскладка
KNOWN = frozenset((
    "ls", "cd", "pwd", "cat", "echo", "mkdir", "cp", "mv", "rm", "touch", "file", "chmod",
    "clear", "history", "less", "head", "tail", "grep", "find", "man", "nano", "vim", "open",
    "which", "sort", "uniq", "wc", "cut", "awk", "sed", "jq", "curl", "zip", "unzip", "tar",
    "du", "ps", "kill", "top", "jobs", "fg", "bg", "sqlite3", "psql", "python3", "pip", STUB_NAME,
    "export", "source", "ans", "hint", "task", "lesson", "keys", "book", "skip", "quit",
    "reset", "giveup", "bug", "ext", "next", "more", "dirs", "exit",
))

# памятка для keys, keys iterm и первого урока (название пункта настроек в разных macOS
# немного разное — говорим осторожно)
NOTE_SHORT = ("Хоткеи и команды — в английской раскладке: переключение — Ctrl+Пробел или "
              "клавиша 🌐 (Fn).")
NOTE = (NOTE_SHORT + " Чтобы Mac сам помнил раскладку для каждого окна: Системные настройки "
        "→ Клавиатура → Источники ввода (кнопка «Изменить…») → пункт вроде «Автоматически "
        "переключаться на источник ввода документа» (в твоей версии macOS название может "
        "чуть отличаться).")

HINT = ("похоже, включена русская раскладка: ты набрал {typed} — это {cmd}. Переключись: "
        "Ctrl+Пробел или клавиша 🌐 (Fn).")


def to_qwerty(text: str) -> str:
    """Те же клавиши в английской раскладке: «ды» → «ls», «св» → «cd»."""
    return "".join(_MAP.get(ch, ch) for ch in text)


def has_cyrillic(text: str) -> bool:
    return any("а" <= ch.lower() <= "я" or ch in "ёЁ" for ch in text)


def hint(word: str) -> Optional[str]:
    """Подсказка для набранного слова или None (не кириллица, перевод — не команда)."""
    if not word or not has_cyrillic(word):
        return None
    cmd = to_qwerty(word)
    if cmd.lower() not in KNOWN:
        return None
    return HINT.format(typed=word, cmd=cmd.lower())
