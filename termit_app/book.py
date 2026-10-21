"""Книга выученных команд: ./termit book и команда book внутри задачи (FB3).

Внутри песочницы хук не читает progress.json, поэтому перед задачей сессия кладёт снимок
книги в box (BOX_FILE).

FB6: в строке, где команда встречается в книге впервые, — расшифровка её имени из origins
(«pwd — где я стою · 🔤 pwd: «print working directory»»). Механизмом при выводе, а не правкой
spell: в progress.json лежат строки, записанные при решении, — так расшифровки появятся и в
уже собранной книге, а spell остаются короткими и под своими охранами."""
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from termit_app import origins, theme
from termit_app.implants import STUB_NAME
from termit_app.tasks import registry

BOX_FILE = ".termit/book.json"

Sections = List[Tuple[str, List[str]]]


def sections(p: dict) -> Sections:
    """Разделы книги по трекам: (название места, строки решённых задач)."""
    result = []
    for tr in registry.shown_tracks():
        spells = [p["grimoire"][t.id] for t in registry.tasks_of(tr.key) if t.id in p["grimoire"]]
        if spells:
            result.append((theme.place(tr.key), spells))
    return decoded(result)


# Короткая расшифровка для книги, где слово из origins не годится: русское слово-перевод
# (head — «голова») или зацепка, которой без истории не понять (nano — «Pine composer»).
# None — в книге не расшифровываем: история длиннее строки, она звучит в уроке.
BOOK_WORDS: Dict[str, Optional[str]] = {
    "echo": "эхо",
    "head": "голова",
    "tail": "хвост",
    "top": "верхушка",
    "tee": "тройник, как у труб",
    "source": "источник",
    "grep": "global / regular expression / print",
    "rg": "ripgrep",
    "uniq": "unique",
    STUB_NAME: "от Homebrew, домашнее пиво",
    "nano": None,
    "bat": None,
    "fd": None,
    "zip": None,
    "kill": None,
    "export": None,
    "python3": None,
    "duckdb": None,
    "sqlite3": "SQL + lite, лёгкий",
    "psql": None,
    "pg_dump": None,
}

_LATIN = re.compile(r"^[A-Za-z][A-Za-z ;,'/.-]*$")


def book_word(name: str) -> Optional[str]:
    """Расшифровка имени для книги или None, если она не поможет запомнить: слово совпадает
    с именем (find — «find») или это русская зацепка без истории."""
    if name in BOOK_WORDS:
        return BOOK_WORDS[name]
    word = origins.COMMANDS[name].word
    if not _LATIN.match(word) or word.casefold() in name.casefold():
        return None
    return word


def _names(spell: str) -> List[str]:
    """Команды из origins в строке книги — по порядку, без повторов. Имя — отдельным словом:
    не кусок пути (.venv), не переменная ($PATH) и не часть имени файла (ls.txt)."""
    out = []
    for m in re.finditer(r"(?<![\w./$-])[\w.-]+(?![\w/-])", spell):
        name = m.group().rstrip(".")
        if name in origins.COMMANDS and name not in out:
            out.append(name)
    return out


def command_names(spell: str) -> List[str]:
    """Команды строки книги — для train ТЕМА (отработка по команде)."""
    return _names(spell or "")


def decoded(parts: Sections) -> Sections:
    """В строке, где команда в книге впервые, — «· 🔤 cd: «change directory»», если такой
    расшифровки в строке ещё нет."""
    seen = set()
    result = []
    for place, spells in parts:
        lines_out = []
        for spell in spells:
            notes = []
            for name in _names(spell):
                if name in seen:
                    continue
                seen.add(name)
                word = book_word(name)
                if word and word.casefold() not in spell.casefold():
                    notes.append(f"{name}: «{word}»")
            lines_out.append(spell + (f" · {origins.MARK}" + ", ".join(notes) if notes else ""))
        result.append((place, lines_out))
    return result


def lines(parts: Sections, query: str) -> List[str]:
    """Строки для вывода с отбором по слову (без учёта регистра); пусто — ничего не нашлось."""
    q = query.casefold()
    out = []
    for place, spells in parts:
        found = [s for s in spells if q in s.casefold()]
        if found:
            out.append(f"\n{place}")
            out.extend(f"  • {s}" for s in found)
    return out


def empty_text(parts: Sections) -> str:
    return f"{theme.word('book')} пуст." if not parts else "Ничего не нашлось."


def box_text(parts: Iterable[Tuple[str, List[str]]]) -> str:
    return json.dumps([[place, list(spells)] for place, spells in parts], ensure_ascii=False)


def read_box(box) -> Sections:
    try:
        data = json.loads((Path(box) / BOX_FILE).read_text("utf-8"))
        return [(str(place), [str(s) for s in spells]) for place, spells in data]
    except (OSError, ValueError, TypeError):
        return []


def show(parts: Sections, query: str) -> str:
    found = lines(parts, query)
    return "\n".join(found) if found else empty_text(parts)
