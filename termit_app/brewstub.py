"""Учебный brew песочницы: python -m termit_app.brewstub АРГУМЕНТЫ.

Настоящий brew в песочнице бесполезен (сети нет, писать вне песочницы нельзя) и опасен
(ставит программы на машину владельца). Этот — честная эмуляция по образцу учебных ps/top:
ведёт себя как настоящий brew на маленьком каталоге, «ставит» понарошку, ничего не качает и
ничего не запускает. Своего поведения, которого нет у настоящего, у него нет: search ищет
подстроку в именах формул (с --desc — в описаниях), info печатает описание и, у отключённой
формулы, замену, which-formula называет формулу по команде. Сверено с man brew и исходниками
Homebrew (cmd/search.rb, cmd/info.rb, deprecate_disable.rb, cmd/which-formula.sh); описания
формул — настоящие, из каталога Homebrew.

Честная пометка «учебный» и пояснения — в stderr: stdout такой же, как у настоящего, и пайпы
(brew list | head, $(brew which-formula rg)) работают как в жизни. Каждый вызов пишется в
.termit/brew.log — по нему задача проверяет, как именно его звали. Настоящий brew запускает
только termit_app/implants.py, в родителе, после явного y."""
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional

from termit_app import implants

NOTE = "(учебный brew: песочница без сети)"
LOG = "brew.log"


@dataclass(frozen=True)
class Formula:
    name: str
    bins: tuple                 # какие команды ставит (как executables.txt Homebrew)
    desc: str                   # описание из каталога Homebrew, слово в слово
    disabled: str = ""          # причина отключения (как в deprecate_disable.rb)
    disabled_on: str = ""
    replacement: str = ""


# Описания и команды — из каталога Homebrew (descriptions.json, executables.txt).
_DESC = {
    "tlrc": "Official tldr client written in Rust",
    "ripgrep": "Search tool like grep and The Silver Searcher",
    "fd": "Simple, fast and user-friendly alternative to find",
    "bat": "Clone of cat(1) with syntax highlighting and Git integration",
    "qsv": "Ultra-fast CSV data-wrangling toolkit",
    "duckdb": "Embeddable SQL OLAP Database Management System",
    "litecli": "CLI for SQLite Databases with auto-completion and syntax highlighting",
    "postgresql@18": "Object-relational database system",
    "pgcli": "CLI for Postgres with auto-completion and syntax highlighting",
    "fzf": "Command-line fuzzy finder written in Go",
    "zoxide": "Shell extension to navigate your filesystem faster",
}
_EXTRA = (
    Formula("tree", ("tree",), "Display directories as trees (with optional color/HTML output)"),
    Formula("jq", ("jq",), "Lightweight and flexible command-line JSON processor"),
    Formula("wget", ("wget",), "Internet file retriever"),
    Formula("htop", ("htop",), "Improved top (interactive process viewer)"),
    Formula("httpie", ("http", "httpie", "https"),
            "User-friendly cURL replacement (command-line HTTP client)"),
    Formula("gnu-sed", ("gsed",), "GNU implementation of the famous stream editor"),
    Formula("git-delta", ("delta",), "Syntax-highlighting pager for git and diff output"),
    Formula("tealdeer", ("tldr",), "Very fast implementation of tldr in Rust"),
    # настоящая история: формулу tldr (клиент на C) отключили, замена — tlrc
    Formula("tldr", (), "Simplified and community-driven man pages",
            disabled="is not maintained upstream", disabled_on="2025-10-24",
            replacement="tlrc"),
)


def formulas() -> List[Formula]:
    out = [Formula(imp.formula, (imp.binary,), _DESC[imp.formula]) for imp in implants.CATALOG]
    return sorted(out + list(_EXTRA), key=lambda f: f.name)


def find(name: str) -> Optional[Formula]:
    for f in formulas():
        if f.name == name:
            return f
    return None


def _simplify(text: str) -> str:
    """Как Search.simplify_string: маленькими буквами, только a-z, цифры, @ и +."""
    return re.sub(r"[^a-z\d@+]", "", text.lower())


def _matcher(text: str):
    """Как search.rb: /…/ — регулярка (с учётом регистра, // тоже регулярка), иначе
    упрощённая подстрока: регистр, дефисы и пробелы не важны (gnu sed найдёт gnu-sed)."""
    m = re.fullmatch(r"/(.*)/", text, re.S)
    if m:
        try:
            rx = re.compile(m.group(1))
        except re.error:            # как search.rb: raise "#{query} is not a valid regex."
            raise ValueError(f"{text} is not a valid regex.") from None
        return lambda s: bool(rx.search(s))
    want = _simplify(text)
    return lambda s: want in _simplify(s)


def search(text: str) -> List[str]:
    """brew search: подстрока в ИМЕНАХ формул (по командам настоящий brew не ищет)."""
    m = _matcher(text)
    return [f.name for f in formulas() if m(f.name)]


def search_desc(text: str) -> List[Formula]:
    """brew search --desc: подстрока в описаниях."""
    m = _matcher(text)
    return [f for f in formulas() if m(f.desc)]


def which_formula(cmd: str) -> List[str]:
    """brew which-formula: какие формулы ставят команду (точное имя)."""
    return [f.name for f in formulas() if cmd in f.bins]


def _box() -> Optional[str]:
    return os.environ.get("TERMIT_BOX") or None


def _state() -> dict:
    box = _box()
    if not box:
        return {}
    try:
        from termit_app import sandbox
        return sandbox.read_task_json(box).get("state") or {}
    except (OSError, ValueError, AttributeError):
        return {}


def _judge_receipt() -> Optional[str]:
    """Квитанция — ответ задачи: в task.json её нет, её знает судья родителя."""
    box = _box()
    if not box:
        return None
    try:
        from termit_app import judge
        reply = judge.ask(box, {"op": "receipt"}) or {}
    except Exception:       # noqa: BLE001 — учебный brew работает и без квитанции
        return None
    r = reply.get("receipt")
    return str(r) if r else None


def _log(argv: List[str], no_update: bool) -> None:
    """Строка JSON на вызов. Ссылку вместо журнала не открываем (O_NOFOLLOW)."""
    box = _box()
    if not box:
        return
    line = json.dumps({"argv": argv, "no_auto_update": no_update}, ensure_ascii=False) + "\n"
    try:
        fd = os.open(os.path.join(box, ".termit", LOG),
                     os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o644)
    except OSError:
        return
    try:
        os.write(fd, line.encode("utf-8"))
    except OSError:
        pass
    finally:
        os.close(fd)


def read_log(box) -> List[dict]:
    """Родитель читает журнал учебного brew: только обычный файл, без ссылок и FIFO."""
    from termit_app import sandbox
    raw = sandbox.read_in_box(box, os.path.join(".termit", LOG), sandbox.SMALL_CAP)
    out = []
    for line in (raw or b"").decode("utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("argv"), list):
            out.append(rec)
    return out


def installed_with_flag(box, formula: str) -> bool:
    """Была ли учебная установка formula с HOMEBREW_NO_AUTO_UPDATE."""
    for rec in read_log(box):
        argv = [str(a) for a in rec["argv"]]
        if (argv[:1] == ["install"] and rec.get("no_auto_update") is True
                and formula in [a for a in argv[1:] if not a.startswith("-")]):
            return True
    return False


def _install_note() -> str:
    """Строка темы (TERMIT_THEME песочницы) или нейтральная — из implants.text."""
    try:
        from termit_app import theme
        theme.use()
    except Exception:       # noqa: BLE001 — тема не нужна, чтобы ответить
        pass
    return implants.text("stub_install")


USAGE = """Учебный brew умеет (как настоящий, на маленьком каталоге):
  brew search ТЕКСТ           формулы, в имени которых есть ТЕКСТ (/…/ — регулярка)
  brew search --desc ТЕКСТ    формулы, в описании которых есть ТЕКСТ
  brew info ФОРМУЛА           карточка: описание; у отключённой — чем заменить
  brew which-formula КОМАНДА  какая формула ставит команду
  brew list                   что уже стоит
  brew install ФОРМУЛА        учебная установка (с HOMEBREW_NO_AUTO_UPDATE=1)"""


def _out(*lines: str) -> None:
    for line in lines:
        print(line)


def _err(*lines: str) -> None:
    for line in lines:
        print(line, file=sys.stderr)


def _disabled(f: Formula) -> str:
    """Как DeprecateDisable.message в Homebrew."""
    msg = f"disabled because it {f.disabled}! It was disabled on {f.disabled_on}."
    if f.replacement:
        msg += f"\nReplacement:\n  brew install {f.replacement}"
    return msg


def _names(args: List[str]) -> List[str]:
    return [a for a in args if not a.startswith("-")]


def cmd_search(args: List[str]) -> int:
    words = _names(args)
    if not words:
        _err("Error: This command requires at least 1 text or regex argument.")
        return 1
    try:
        return _search(args, words[0])
    except ValueError as e:
        _err(f"Error: {e}")
        return 1


def _search(args: List[str], word: str) -> int:
    if "--desc" in args:
        found = search_desc(word)
        _out("==> Formulae", *(f"{f.name}: {f.desc}" for f in found))
        return 0
    found = search(word)
    if not found:
        _err(f'Error: No formulae or casks found for "{word}".')
        return 1
    if sys.stdout.isatty():         # как у brew: заголовок — только на экран, в пайп — имена
        _out("==> Formulae")
    _out(*found)
    return 0


def cmd_info(args: List[str]) -> int:
    names = _names(args)
    if not names:
        _out(f"{len(formulas())} formulae (учебный каталог)")
        return 0
    code = 0
    for i, name in enumerate(names):
        f = find(name)
        if f is None:
            _err(f'Error: No available formula with the name "{name}".')
            code = 1
            continue
        if i:
            _out("")
        _out(f"==> {f.name}: stable", f.desc)
        if f.disabled:
            text = _disabled(f)
            _out(text[0].upper() + text[1:])
        _out("Installed" if any(implants.which(b) for b in f.bins) else "Not installed")
    return code


def cmd_which_formula(args: List[str]) -> int:
    cmds = _names(args)
    if not cmds:
        _out(USAGE)
        return 1
    code = 0
    for cmd in cmds:
        found = which_formula(cmd)
        if not found:
            code = 1
        _out(*found)
    return code


def cmd_list(args: List[str]) -> int:
    st = _state()
    if isinstance(st.get("brew_list"), list):       # учебная задача: детерминированно
        names = [str(x) for x in st["brew_list"]]
    else:
        names = [f.name for f in formulas() if any(implants.which(b) for b in f.bins)]
    _out(*sorted(names))
    return 0


def cmd_install(args: List[str], no_update: bool) -> int:
    names = _names(args)
    if not names:
        _err("Error: Invalid usage: This command requires at least 1 formula or cask argument.")
        return 1
    if not no_update:
        _out("==> Auto-updating Homebrew...")
        _err("Сначала обновлю каталог формул… в песочнице сети нет — прервано.",
             "Без обновления: HOMEBREW_NO_AUTO_UPDATE=1 brew install ФОРМУЛА")
        return 1
    code = 0
    for name in names:
        f = find(name)
        if f is None:
            _err(f'Error: No available formula with the name "{name}".')
            code = 1
            continue
        if f.disabled:
            _err(f"Error: {f.name} has been {_disabled(f)}")
            code = 1
            continue
        _out(f"==> Installing {f.name}")
        _err(f"Учебная установка {f.name}: ничего не качаю и не ставлю.", _install_note())
        receipt = _state().get("receipt") or _judge_receipt()
        if receipt:
            _out(f"Квитанция: {receipt}")
    return code


COMMANDS = {"search": cmd_search, "-S": cmd_search, "info": cmd_info, "abv": cmd_info,
            "which-formula": cmd_which_formula, "list": cmd_list, "ls": cmd_list}


def main(argv: List[str]) -> int:
    no_update = bool(os.environ.get("HOMEBREW_NO_AUTO_UPDATE"))
    _log(list(argv), no_update)
    _err(NOTE)              # честная пометка — в stderr: stdout как у настоящего brew
    if not argv or argv[0] in ("help", "-h", "--help"):
        _out(USAGE)
        return 0 if argv else 1
    cmd, args = argv[0], argv[1:]
    if cmd in ("--version", "-v"):
        _out("Homebrew 4 (учебный)")
        return 0
    if cmd in COMMANDS:
        return COMMANDS[cmd](args)
    if cmd == "install":
        return cmd_install(args, no_update)
    if cmd in ("update", "upgrade"):
        _err("Нужна сеть, а в песочнице сети нет — прервано.")
        return 1
    _err(f"Учебный brew не знает команду {cmd!r}.", USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
