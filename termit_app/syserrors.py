"""FB12 (N6): перевод частых системных ошибок — при первой встрече игрока с каждой.

Вывод команды игра не перехватывает (он идёт прямо в терминал), поэтому ошибку угадываем по
тому, что видно хуку после команды: код возврата и сама строка. 127 — команды нет, 126 —
запустить нельзя; для cat, cd, ls, cp, mv, rm и др. — смотрим аргументы: пути нет — «No such
file or directory», папка там, где ждут файл, — «Is a directory», файл есть, а прочесть
нельзя — «Permission denied». Ошибся в догадке — промолчим: лучше без перевода, чем с чужим.

Какие ошибки игрок уже видел с переводом, помнит прогресс (p["errors_seen"]): родитель кладёт
список в песочницу (BOX_KNOWN), хук дописывает новые в BOX_SEEN, родитель после задачи
забирает их обратно (collect)."""
import os
import re
import shlex
from pathlib import Path
from typing import Iterable, List, Optional

BOX_KNOWN = ".termit/errors_known"
BOX_SEEN = ".termit/errors_seen"

KINDS = ("not_found", "no_such_file", "is_dir", "permission", "root_walk", "two_paths")

TEXT = {
    "not_found": ("command not found", "такой команды нет: опечатка в имени или программа не "
                                       "установлена. Слова игры (ans, hint) — только в задании."),
    "no_such_file": ("No such file or directory", "нет такого файла или папки. Проверь имя "
                                                  "(ls покажет, что есть) и где стоишь (pwd)."),
    "is_dir": ("Is a directory", "это папка, а не файл. Внутрь папки смотрит ls, войти — cd; "
                                 "папку целиком копирует и удаляет только -r."),
    "permission": ("Permission denied", "нет прав: файлу не разрешено то, что ты просишь. "
                                        "Запуск разрешает chmod +x."),
    # владелец 21.10: ls /**/plan_final.txt — простыня «operation not permitted»
    "root_walk": ("operation not permitted", "/ в начале — корень всего Mac, а песочница "
                                             "пускает только в папку задания. Отсюда вглубь — "
                                             "без /: ls **/имя"),
    # владелец 21.10: cp **/plan_final.txt(D) без «куда» — cp печатает свою справку
    "two_paths": ("usage: cp / mv", "команде нужны два адреса: что и куда. «Сюда, в эту "
                                    "папку» — точка: cp notes/**/plan.txt ."),
}

# команды, чьи аргументы — пути (у grep первый аргумент — шаблон)
PATH_CMDS = ("cat", "cd", "ls", "cp", "mv", "rm", "head", "tail", "less", "wc", "file", "nano",
             "open", "grep", "sort", "uniq", "chmod", "rmdir")
READERS = ("cat", "head", "tail", "less", "wc", "sort", "uniq", "file", "grep")
# в строке есть приёмы оболочки, которые наш простой разбор не повторит: молчим
_SHELLY = set("*?[]{}$`|;&<>()!\\")


def line_text(kind: str) -> str:
    word, meaning = TEXT[kind]
    return f"📎 «{word}» — это значит: {meaning}"


# флаги, за которыми идёт значение, а не путь (head -n 3, sort -k 2, grep -e шаблон)
VALUE_FLAGS = {"head": ("-n", "-c"), "tail": ("-n", "-c"), "sort": ("-k", "-t", "-o"),
               "grep": ("-e", "-f", "-m", "-A", "-B", "-C"), "uniq": ("-f", "-s"),
               "wc": (), "less": ("-p",)}
_NUMBER = re.compile(r"^[+-]?\d+$")


def _args(cmd: str, words: List[str]) -> List[str]:
    """Аргументы-пути: без флагов, без значений флагов (-n 3, -k2 слитно — сам флаг), без
    чисел и +N; у chmod первый аргумент — права, не путь."""
    out, flags, skip = [], True, False
    takes = VALUE_FLAGS.get(cmd, ())
    mode = cmd == "chmod"                   # первый не-флаг chmod — права (600, +x, u+w)
    for w in words:
        if skip:
            skip = False
            continue
        if flags and w == "--":
            flags = False
            continue
        if flags and w.startswith("-") and len(w) > 1:
            skip = w in takes
            continue
        if mode:
            mode = False
            continue
        if _NUMBER.match(w):
            continue
        out.append(w)
    return out


# обход от корня диска: ls /**/x, ls /*/x, find / -name x, ls -R /
_ROOT_CMDS = ("ls", "find", "cat", "grep", "du", "tree", "head", "wc")


def _root_walk(line: str) -> bool:
    words = line.split()
    if not words or words[0] not in _ROOT_CMDS:
        return False
    args = words[1:]
    if any(w.startswith("/") and "*" in w for w in args):
        return True
    deep = words[0] in ("find", "du", "tree") or any(
        w.startswith("-") and "r" in w.lower() for w in args)
    return deep and "/" in args


def _one_path(line: str) -> bool:
    """cp или mv с одним адресом (маска — тоже один): «что» есть, «куда» — нет."""
    words = line.split()
    if not words or words[0] not in ("cp", "mv") or any(ch in line for ch in "|;&<>`$"):
        return False
    return len([w for w in words[1:] if not w.startswith("-")]) == 1


def detect(line: str, rc, pwd, home: Optional[str] = None) -> Optional[str]:
    """Какая ошибка, скорее всего, была у этой команды (None — не знаем или ошибки нет)."""
    try:
        code = int(str(rc).split()[-1])
    except (ValueError, IndexError):
        return None
    if _root_walk(line):        # простыня «operation not permitted» бывает и при успехе
        return "root_walk"
    if code == 0:
        return None
    if _one_path(line):
        return "two_paths"
    if code == 127:
        from termit_app import layout
        first = line.split()[0] if line.split() else ""
        if layout.hint(first):
            return None     # «ды» вместо ls — про раскладку уже сказал command_not_found_handler
        return "not_found"
    if code == 126:
        return "permission"
    if any(ch in _SHELLY for ch in line):
        return None
    try:
        words = shlex.split(line)
    except ValueError:
        return None
    if not words or words[0] not in PATH_CMDS:
        return None
    cmd, flags = words[0], [w for w in words[1:] if w.startswith("-")]
    args = _args(cmd, words[1:])
    if cmd == "grep" and not any(w in ("-e", "-f") for w in flags):
        args = args[1:]                     # первый аргумент — шаблон, а не путь
    if cmd == "cd" and len(args) == 1 and args[0] == "-":
        return None
    base = Path(pwd)
    recursive = any("r" in f.lower() for f in flags if not f.startswith("--"))
    for i, arg in enumerate(args):
        last = i == len(args) - 1
        if arg.startswith("~"):
            if not home:
                return None
            arg = home + arg[1:]
        path = base / arg
        if not os.path.lexists(path):
            if cmd in ("cp", "mv") and last and len(args) > 1:
                continue            # цель копии или переноса может ещё не существовать
            return "no_such_file"
        if path.is_dir():
            if cmd in READERS and not (cmd == "grep" and recursive):
                return "is_dir"
            if not recursive and (cmd == "rm" or (cmd == "cp" and not last)):
                return "is_dir"
        elif cmd == "cd":
            return None             # cd в файл — «not a directory», не наш случай
        elif cmd in READERS and not os.access(path, os.R_OK):
            return "permission"
    return None


def known(text: str) -> List[str]:
    return [k for k in text.split() if k in KINDS]


def box_text(kinds: Iterable[str]) -> str:
    return "\n".join(k for k in kinds if k in KINDS) + "\n"


def collect(p: dict, box) -> List[str]:
    """Новые переводы из песочницы — в прогресс (p["errors_seen"]); вернуть новые."""
    from termit_app import sandbox
    seen = known(sandbox._read(box, Path(BOX_SEEN).name) or "")
    have = p.setdefault("errors_seen", [])
    new = [k for k in seen if k not in have]
    have.extend(new)
    return new


def explain_once(box, rc, pwd, line: str) -> Optional[str]:
    """Хук: ошибка этой команды впервые у игрока — строка перевода (и пометка в BOX_SEEN)."""
    from termit_app import sandbox
    kind = detect(line, rc, pwd, os.environ.get("HOME"))
    if kind is None:
        return None
    seen = known(sandbox._read(box, Path(BOX_SEEN).name) or "")
    if kind in seen or kind in known(sandbox._read(box, Path(BOX_KNOWN).name) or ""):
        return None
    try:
        sandbox.write_box_file(box, BOX_SEEN, box_text(seen + [kind]))
    except (OSError, ValueError):
        return None             # некуда записать — переводить каждый раз не будем
    return line_text(kind)
