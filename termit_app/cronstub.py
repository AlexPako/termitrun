"""Учебный crontab песочницы: python -I … termit_app.cronstub АРГУМЕНТЫ (FB14).

Настоящий crontab -e правит расписание владельца на его Mac — из игры его трогать нельзя.
Обёртка .termit/bin/crontab есть только у задач с uses_crontab = True и хранит «расписание»
в файле песочницы .termit/crontab (по нему и проверяет задача). Ничего не запускает по
времени: только принимает, проверяет и показывает строки.

Ключи как у настоящего: crontab ФАЙЛ (или - — со входа) — поставить расписание из файла,
crontab -l — показать, crontab -r — убрать, crontab -e — открыть в $EDITOR (nano). Строка:
«минута час день_месяца месяц день_недели команда»; поля — *, числа, a-b, a,b, */n, a-b/n,
имена месяцев и дней (jan, mon). Ошибка в строке — как у cron на macOS: «"файл":N: bad
minute» и «crontab: errors in crontab file, can't install» (код 1). Вывод — по-английски
(FB5 п. 42), пометка «учебный» — в stderr."""
import os
import re
import subprocess
import sys
import tempfile
from typing import List, Optional, Set, Tuple

NOTE = "(termit learning crontab: kept inside the game, nothing runs on schedule)"
STORE = os.path.join(".termit", "crontab")
MAX_FILE = 64 * 1024
FIELDS = (("minute", 0, 59, ()), ("hour", 0, 23, ()), ("day of month", 1, 31, ()),
          ("month", 1, 12, ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                            "oct", "nov", "dec")),
          ("day of week", 0, 7, ("sun", "mon", "tue", "wed", "thu", "fri", "sat")))
_ENV_LINE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=")
USAGE = """usage: crontab [-u user] file
       crontab [-u user] { -l | -r | -e }"""


def _value(text: str, lo: int, hi: int, names: Tuple[str, ...]) -> Optional[int]:
    if text.isdigit():
        n = int(text)
        return n if lo <= n <= hi else None
    low = text.lower()
    if low in names:
        return names.index(low) + (1 if lo == 1 else 0)
    return None


def field_set(text: str, lo: int, hi: int, names: Tuple[str, ...] = ()) -> Optional[Set[int]]:
    """Множество значений поля cron или None — поле с ошибкой. День недели 7 — то же, что 0."""
    out: Set[int] = set()
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, _, raw = part.partition("/")
            if not raw.isdigit() or int(raw) == 0:
                return None
            step = int(raw)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            x, _, y = part.partition("-")
            a, b = _value(x, lo, hi, names), _value(y, lo, hi, names)
            if a is None or b is None or a > b:
                return None
        else:
            a = _value(part, lo, hi, names)
            if a is None:
                return None
            b = hi if step > 1 else a
        out |= set(range(a, b + 1, step))
    if hi == 7 and 7 in out:            # воскресенье — и 0, и 7
        out = (out - {7}) | {0}
    return out


def parse_line(line: str) -> Tuple[Optional[list], Optional[str], Optional[str]]:
    """(множества пяти полей, команда, ошибка). Пустая строка, комментарий и ИМЯ=значение —
    (None, None, None)."""
    s = line.strip()
    if not s or s.startswith("#") or _ENV_LINE.match(s):
        return None, None, None
    parts = s.split(None, 5)
    if len(parts) < 6:
        return None, None, "bad command" if len(parts) == 5 else f"bad {FIELDS[len(parts)][0]}"
    sets = []
    for raw, (name, lo, hi, names) in zip(parts[:5], FIELDS):
        got = field_set(raw, lo, hi, names)
        if got is None:
            return None, None, f"bad {name}"
        sets.append(got)
    return sets, parts[5], None


def check_text(text: str, name: str) -> List[str]:
    out = []
    for no, line in enumerate(text.split("\n"), 1):
        _, _, err = parse_line(line)
        if err:
            out.append(f'"{name}":{no}: {err}')
    return out


def _store(box: str) -> str:
    return os.path.join(box, STORE)


def _read(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_FILE + 1)
    except OSError:
        return None
    if len(data) > MAX_FILE:
        return None
    return data.decode("utf-8", errors="replace")


def _install(box: str, text: str, name: str) -> int:
    errors = check_text(text, name)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print("crontab: errors in crontab file, can't install", file=sys.stderr)
        return 1
    path = _store(box)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") or not text else text + "\n")
    return 0


def main(argv: List[str], box: Optional[str] = None) -> int:
    box = box or os.environ.get("TERMIT_BOX") or os.getcwd()
    args = [a for a in argv]
    if args[:1] == ["-u"]:
        args = args[2:]                     # -u пользователь — у нас одно расписание
    print(NOTE, file=sys.stderr)
    user = os.environ.get("USER", "you")
    if args == ["-l"]:
        text = _read(_store(box))
        if not text:
            print(f"crontab: no crontab for {user}", file=sys.stderr)
            return 1
        sys.stdout.write(text)
        return 0
    if args == ["-r"]:
        try:
            os.unlink(_store(box))
        except FileNotFoundError:
            print(f"crontab: no crontab for {user}", file=sys.stderr)
            return 1
        return 0
    if args == ["-e"]:
        fd, tmp = tempfile.mkstemp(prefix="crontab.", dir=os.path.join(box, ".termit", "tmp"))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_read(_store(box)) or "")
        editor = os.environ.get("EDITOR") or "nano"
        subprocess.call([editor, tmp])
        text = _read(tmp) or ""
        os.unlink(tmp)
        return _install(box, text, tmp)
    if len(args) == 1 and not args[0].startswith("-") or args == ["-"]:
        if args[0] == "-":
            text = sys.stdin.read(MAX_FILE)
            name = "(stdin)"
        else:
            text = _read(args[0])
            name = args[0]
            if text is None:
                print(f"crontab: {name}: No such file or directory", file=sys.stderr)
                return 1
        return _install(box, text, name)
    print(USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
