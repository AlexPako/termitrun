"""Нормализация ответов, сданных через ans: пробелы, регистр, числа, пути."""
import os
import re
from pathlib import Path
from typing import Optional


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip())


# Типографские кавычки, которыми новичок «оборачивает» ответ: снимаются только парой, по
# краям. Прямые " и ' в ans снимает сам zsh; дошли до ответа — значит, их напечатала
# программа (jq без -r), и это ловушка урока, а не упаковка.
_QUOTES = (("«", "»"), ("“", "”"), ("„", "“"))
_TAIL = ".,;"      # хвостовая точка (или запятая) после слова — не часть ответа


def unquote(s: str) -> str:
    """Снять парные кавычки по краям (несколько слоёв). Для путей — только это."""
    s = norm(s)
    changed = True
    while changed and len(s) >= 2:
        changed = False
        for a, b in _QUOTES:
            if s.startswith(a) and s.endswith(b) and len(s) >= len(a) + len(b):
                s, changed = norm(s[len(a):len(s) - len(b)]), True
                break
    return s


def clean(s: str) -> str:
    """Ответ без «упаковки»: пробелы по краям, парные кавычки, точка или запятая в конце.
    Ответ из одних точек («.», «..») — путь, его не трогаем. Общая нормализация для
    текста, чисел и частей ответа (Н приёмки-1: «маяк.» и «"гитара"» — верные ответы)."""
    s = norm(s)
    for _ in range(3):
        before = s
        if s.rstrip(_TAIL).strip(".") and s[-1:] in _TAIL:
            s = s.rstrip(_TAIL).rstrip()
        s = unquote(s)
        if s == before:
            break
    return s


def as_number(s: str) -> Optional[float]:
    try:
        return float(clean(s).replace(",", "."))
    except ValueError:
        return None


def same_number(given: str, expected) -> bool:
    g = as_number(given)
    return g is not None and abs(g - float(expected)) < 0.01


def same_text(given: str, expected: str, case_sensitive: bool = False) -> bool:
    g, e = clean(given), clean(str(expected))
    if not case_sensitive:
        g, e = g.casefold(), e.casefold()
    return g == e


def parts(s: str) -> list:
    """Части ответа: слова через пробелы, запятые, точку с запятой или | (вывод sqlite3 и
    psql -At: «kazan|57»), без регистра."""
    out = (clean(x) for x in re.split(r"[\s,;|]+", clean(str(s)).casefold()))
    return [x for x in out if x]


def same_words(given: str, expected: str) -> bool:
    """Несколько частей в том же порядке: «6568, lighthouse» = «6568 lighthouse», регистр не важен."""
    want = parts(expected)
    return bool(want) and parts(given) == want


def same_parts(given: str, expected) -> bool:
    """Ответ из нескольких частей: порядок любой, регистр не важен. Строка uniq -c вида
    «57 coffee» засчитывается как «coffee 57»."""
    want = sorted(clean(str(x).casefold()) for x in expected)
    return bool(want) and sorted(parts(given)) == want


def same_path(given: str, expected: Path, base: Path) -> bool:
    """Путь можно сдать относительно base (с ./ или без, с / на конце) или абсолютным,
    в кавычках и с точкой в конце предложения («anchor.conf.»): у точки-хвоста — вторая
    попытка без неё (имена «.» и «..» не трогаем)."""
    g = unquote(given)
    if not g:
        return False
    tries = [g]
    last = g.rstrip("/").rsplit("/", 1)[-1]
    if g.endswith(".") and last.strip("."):
        tries.append(g.rstrip("."))
    return any(_same_path(t, expected, base) for t in tries)


# Системные синонимы путей macOS: /var → /private/var, /tmp → /private/tmp. Сравнение
# лексическое, поэтому эти пары сводим к одному виду сами.
_ALIASES = (("/private/var/", "/var/"), ("/private/tmp/", "/tmp/"), ("/private/etc/", "/etc/"))


def _canon(p: str) -> str:
    s = os.path.normpath(p)
    for long_, short in _ALIASES:
        if (s + "/").startswith(long_):
            s = short.rstrip("/") + s[len(long_) - 1:]
            break
    return s


def _same_path(g: str, expected: Path, base: Path) -> bool:
    """Лексически: без обращения к диску (resolve ходил бы по симлинкам игрока — путь
    проверяет судья у родителя, ему туда нельзя). «..», «.» и хвостовой / — сводятся."""
    p = g if os.path.isabs(g) else os.path.join(str(base), g)
    return _canon(p) == _canon(str(expected))
