"""Учебный shellcheck песочницы: python -I … termit_app.shellstub АРГУМЕНТЫ (FB14).

Настоящего shellcheck на Mac обычно нет (ставится brew install shellcheck), а сети в песочнице
нет совсем. Обёртка .termit/bin/shellcheck есть только у задач с uses_shellcheck = True.
Вывод — как у настоящего ShellCheck 0.10 (по-английски, п. 42), но знает он немного:
- SC2148 (error) — нет первой строки #!: непонятно, какой это шелл;
- SC1071 (error) — #! на zsh: shellcheck понимает только sh/bash/dash/ksh;
- SC2086 (info) — $переменная без двойных кавычек в аргументах команды;
- SC2164 (warning) — cd без «|| exit»: не зашёл — следующие команды пойдут не там;
- SC2006 (style) — `команда` в обратных кавычках вместо $(команда).
Форматы: обычный (tty) и -f gcc (файл:строка:колонка: уровень: текст [SCxxxx]). Коды выхода:
0 — замечаний нет, 1 — есть, 2 — файл не прочесть, 3 — неверные ключи. Ничего не исполняет:
только читает файлы (до 1 МБ). Пометка «учебный» — в stderr, stdout как у настоящего.
Разбор (analyze) общий с проверкой задачи у родителя: тот же, что видит игрок."""
import re
import sys
from dataclasses import dataclass
from typing import List, Optional

NOTE = ("(termit learning shellcheck: knows a few checks; the real one installs with "
        "brew install shellcheck)")
VERSION = """ShellCheck - shell script analysis tool
version: 0.10.0 (termit learning copy)
license: GNU General Public License, version 3
website: https://www.shellcheck.net"""
USAGE = """Usage: shellcheck [OPTIONS...] FILES...
  -f FORMAT  --format=FORMAT  Output format (gcc, tty)
  -V         --version        Print version information
  -h         --help           Show this help"""
MAX_FILE = 1 << 20
WIKI = "https://www.shellcheck.net/wiki/"
MESSAGES = {
    "SC2148": ("error", "Tips depend on target shell and yours is unknown. Add a shebang or "
                        "a 'shell' directive."),
    "SC1071": ("error", "ShellCheck only supports sh/bash/dash/ksh scripts. Sorry!"),
    "SC2086": ("info", "Double quote to prevent globbing and word splitting."),
    "SC2164": ("warning", "Use 'cd ... || exit' or 'cd ... || return' in case cd fails."),
    "SC2006": ("style", "Use $(...) notation instead of legacy backticks `...`."),
}
GCC_LEVEL = {"error": "error", "warning": "warning", "info": "note", "style": "note"}
SHELLS = ("sh", "bash", "dash", "ksh")
_SHEBANG = re.compile(r"^#!\s*(\S+)(?:\s+(\S+))?")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ASSIGN_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_SAFE_SPECIAL = "?#$!-"


@dataclass(frozen=True)
class Issue:
    line: int           # с 1
    col: int            # с 1
    end: int            # колонка последнего символа (включительно)
    code: str
    fix: Optional[str] = None   # строка целиком после правки (для «Did you mean»)

    @property
    def level(self) -> str:
        return MESSAGES[self.code][0]

    @property
    def message(self) -> str:
        return MESSAGES[self.code][1]


def shell_of(text: str) -> Optional[str]:
    """Шелл из первой строки #! (имя без пути; у env — следующее слово) или None."""
    first = text.split("\n", 1)[0]
    m = _SHEBANG.match(first)
    if not m:
        return None
    prog = m.group(1).rsplit("/", 1)[-1]
    if prog == "env" and m.group(2):
        prog = m.group(2).rsplit("/", 1)[-1]
    return prog


def _code_part(line: str) -> str:
    """Строка без комментария: # вне кавычек в начале слова."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == "\\" and quote == '"':
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t;"):
            return line[:i]
    return line


def _unquoted_vars(code: str):
    """(начало, конец) голых $имя / ${…} / $1 вне кавычек, вне [[ ]] и $(( )), не в
    присваивании ИМЯ=$x. Конец — индекс последнего символа."""
    out = []
    quote = None
    i, n = 0, len(code)
    word_start = 0
    depth_test = 0
    while i < n:
        ch = code[i]
        if quote == "'":
            if ch == "'":
                quote = None
            i += 1
            continue
        if quote == '"':
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                quote = None
            i += 1
            continue
        if ch in " \t;|&()":
            word_start = i + 1
        if code.startswith("[[", i):
            depth_test += 1
            i += 2
            continue
        if code.startswith("]]", i) and depth_test:
            depth_test -= 1
            i += 2
            continue
        if code.startswith("$((", i):
            close = code.find("))", i)
            i = n if close < 0 else close + 2
            continue
        if ch in "'\"":
            quote = ch
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch == "$" and i + 1 < n and not depth_test:
            nxt = code[i + 1]
            end = None
            if nxt == "{":
                close = code.find("}", i)
                end = close if close > 0 else None
            elif nxt.isdigit() or nxt in "@*":
                end = i + 1
            elif nxt not in _SAFE_SPECIAL:
                m = _NAME.match(code, i + 1)
                end = m.end() - 1 if m else None
            if end is not None:
                word = code[word_start:i]
                if not _ASSIGN_WORD.fullmatch(word):
                    out.append((i, end))
                i = end + 1
                continue
        i += 1
    return out


def _cd_unchecked(code: str) -> Optional[int]:
    """Начало голого «cd …» без || и && после него (индекс) или None."""
    stripped = code.lstrip()
    if not re.match(r"cd(\s|$)", stripped):
        return None
    if "||" in code or "&&" in code:
        return None
    return len(code) - len(stripped)


def analyze(text: str) -> List[Issue]:
    """Замечания к тексту скрипта — по порядку строк."""
    shell = shell_of(text)
    if shell == "zsh":
        return [Issue(1, 1, 2, "SC1071")]
    issues: List[Issue] = []
    lines = text.split("\n")
    if shell is None:
        issues.append(Issue(1, 1, 1, "SC2148"))
    for no, raw in enumerate(lines, 1):
        if no == 1 and raw.startswith("#!"):
            continue
        code = _code_part(raw).rstrip()
        if not code.strip():
            continue
        start = _cd_unchecked(code)
        if start is not None:
            issues.append(Issue(no, start + 1, len(code), "SC2164",
                                fix=code + " || exit"))
        tick = code.find("`")
        if tick >= 0 and code.find("`", tick + 1) > tick:
            issues.append(Issue(no, tick + 1, code.find("`", tick + 1) + 1, "SC2006"))
        for a, b in _unquoted_vars(code):
            fix = raw[:a] + '"' + raw[a:b + 1] + '"' + raw[b + 1:]
            issues.append(Issue(no, a + 1, b + 1, "SC2086", fix=fix))
    issues.sort(key=lambda x: (x.line, x.col))
    return issues


def _caret(issue: Issue) -> str:
    width = max(1, issue.end - issue.col + 1)
    mark = "^" if width == 1 else "^" + "-" * (width - 2) + "^"
    return " " * (issue.col - 1) + mark


def _short(message: str, limit: int = 40) -> str:
    return message if len(message) <= limit else message[:limit - 3].rstrip() + " ..."


def render_tty(name: str, text: str, issues: List[Issue]) -> str:
    lines = text.split("\n")
    out = []
    for issue in issues:
        src = lines[issue.line - 1] if issue.line - 1 < len(lines) else ""
        out += ["", f"In {name} line {issue.line}:", src,
                f"{_caret(issue)} {issue.code} ({issue.level}): {issue.message}"]
        if issue.fix is not None:
            out += ["", "Did you mean:", issue.fix]
    if issues:
        out += ["", "For more information:"]
        seen = []
        for issue in issues:
            if issue.code not in seen:
                seen.append(issue.code)
                out.append(f"  {WIKI}{issue.code} -- {_short(issue.message)}")
    return "\n".join(out)


def render_gcc(name: str, issues: List[Issue]) -> str:
    return "\n".join(f"{name}:{x.line}:{x.col}: {GCC_LEVEL[x.level]}: {x.message} [{x.code}]"
                     for x in issues)


def _read(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_FILE + 1)
    except OSError:
        return None
    if len(data) > MAX_FILE:
        return None
    return data.decode("utf-8", errors="replace")


def main(argv: List[str]) -> int:
    fmt = "tty"
    files: List[str] = []
    it = iter(argv)
    for a in it:
        if a in ("-h", "--help"):
            print(USAGE)
            return 0
        if a in ("-V", "--version"):
            print(VERSION)
            return 0
        if a == "-f":
            fmt = next(it, "")
        elif a.startswith("--format="):
            fmt = a.split("=", 1)[1]
        elif a.startswith("-f") and len(a) > 2:
            fmt = a[2:]
        elif a.startswith("-") and a != "-":
            print(f"shellcheck: unrecognized option `{a}'", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            return 3
        else:
            files.append(a)
    if fmt not in ("tty", "gcc"):
        print(f"shellcheck: unknown format {fmt}", file=sys.stderr)
        return 3
    if not files:
        print("No files specified.", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 3
    print(NOTE, file=sys.stderr)
    rc = 0
    chunks = []
    for name in files:
        text = _read(name)
        if text is None:
            print(f"{name}: {name}: openBinaryFile: does not exist (No such file or directory)",
                  file=sys.stderr)
            rc = 2
            continue
        issues = analyze(text)
        if issues:
            rc = max(rc, 1)
            chunks.append(render_tty(name, text, issues) if fmt == "tty"
                          else render_gcc(name, issues))
    if chunks:
        print("\n".join(chunks))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
