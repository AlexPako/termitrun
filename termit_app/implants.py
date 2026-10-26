"""Утилиты-подарки (часть 5): каталог, поиск программ, предложение и установка с согласием.

Правило: любую задачу можно решить встроенными командами, утилита даёт только скорость и
точность. Настоящий brew запускается только отсюда (brew_install), только после явного y,
под TERMIT_NO_BREW (весь прогон тестов) — никогда. Слова сеттинга — в теме (раздел
implants), здесь только нейтральные запасные тексты."""
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from termit_app.textnorm import NO, YES

BREW_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")
# Имя обёртки учебного brew в .termit/bin песочницы (termit_app/brewstub.py). Строку «brew»
# держит только этот файл (тест NoBrewLiteralTest), sandbox берёт имя отсюда.
STUB_NAME = "brew"


@dataclass(frozen=True)
class Implant:
    id: str              # "rg"
    formula: str         # формула Homebrew из ядра: "ripgrep"
    binary: str          # программа, по которой видно, что поставлено: "rg"
    what: str            # нейтрально: что даёт
    builtin: str         # чем обойтись на чужой машине
    twin: str            # задача, сделанная руками, после которой дарят
    shell: bool = False  # нужна интеграция в оболочку (fzf, zoxide)
    command: str = ""    # что набирает игрок, если не binary (zoxide → z)
    # "tool" — утилита-подарок; "stand" — учебный стенд (часть 9б: PostgreSQL для задач
    # Хранилища). Стенд — по согласию так же, но сам по себе ничего не запускает: сервер
    # поднимает игра внутри песочницы задачи (termit_app/pgkit)
    kind: str = "tool"
    probe: Tuple[str, ...] = ()     # ещё где искать binary (формула бывает keg-only)
    needs_stand: str = ""           # предлагать, только когда годен этот стенд (pgcli → pg)

    @property
    def cmd(self) -> str:
        return self.command or self.binary


CATALOG: Tuple[Implant, ...] = (
    Implant("tldr", "tlrc", "tldr",
            "короткие живые примеры к команде вместо длинного man",
            "man COMMAND и поиск /слово внутри", "tldr_tar"),
    Implant("rg", "ripgrep", "rg",
            "поиск текста в папках, быстрее grep -r, пропускает .git",
            "grep -rn 'текст' .", "grep_r"),
    Implant("fd", "fd", "fd",
            "поиск файлов по имени, короче find и без мусора из .git",
            "find . -name 'имя'", "find_name"),
    Implant("bat", "bat", "bat",
            "просмотр файла с подсветкой и номерами строк",
            "less -N файл, внутри /слово", "less_search"),
    Implant("qsv", "qsv", "qsv",
            "таблицы CSV: столбцы, сортировка, сводки одной командой",
            "cut -d, -f3 файл.csv | sort | uniq -c; правее кавычек — awk и $NF", "csv_by_hand"),
    Implant("duckdb", "duckdb", "duckdb",
            "SQL-запросы прямо к файлу CSV",
            "awk -F, '{s+=$NF} END {print s}' файл.csv", "csv_top"),
    Implant("litecli", "litecli", "litecli",
            "sqlite3 с подсказками: дописывает таблицы и графы, раскрашивает вывод",
            "sqlite3 файл.db, .headers on и .mode column", "sqlite_open"),
    Implant("pg", "postgresql@18", "postgres",
            "учебный сервер PostgreSQL для Хранилища: он живёт внутри игры, сам сервер на "
            "Маке не запускается, brew services не нужен",
            "sqlite3 vault.db — общие задачи Хранилища идут и без сервера", "boss_db",
            kind="stand", probe=("/opt/homebrew/opt/postgresql@18/bin",)),
    Implant("pgcli", "pgcli", "pgcli",
            "psql с подсказками: дописывает таблицы и графы, раскрашивает вывод",
            "psql, \\dt и \\d таблица", "psql_nav", needs_stand="pg"),
    Implant("fzf", "fzf", "fzf",
            "нечёткий выбор из списка: файлы, история, папки",
            "ls, Tab и стрелки; история — Ctrl+R", "climb_down", shell=True),
    Implant("zoxide", "zoxide", "zoxide",
            "прыжок в частую папку по куску имени: z proj",
            "cd -, pushd и popd, dirs -v", "back_up", shell=True, command="z"),
)

# Задачи части 5, которых ещё нет в реестре: близнецы и пары каталога могут на них ссылаться.
# После I8 (трио CSV) — все на месте.
FUTURE_TASKS: Tuple[str, ...] = ()     # близнецы, чьих задач ещё нет (psql_nav — с B2)


def get(imp_id: str) -> Implant:
    for imp in CATALOG:
        if imp.id == imp_id:
            return imp
    raise KeyError(f"нет утилиты {imp_id!r}")


def which(binary: str) -> Optional[str]:
    """PATH, затем папки Homebrew: termit могли запустить из урезанного окружения."""
    found = shutil.which(binary)
    if found:
        return found
    for d in BREW_DIRS:
        cand = os.path.join(d, binary)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def installed(imp_id: str) -> bool:
    return locate(get(imp_id)) is not None


def locate(imp: Implant) -> Optional[str]:
    """Где программа утилиты: which, затем папки probe (keg-only формула)."""
    found = which(imp.binary)
    if found:
        return found
    for d in imp.probe:
        cand = os.path.join(d, imp.binary)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def stand_ok(stand: str) -> bool:
    """Годен ли стенд (часть 9б): pg — pgkit.usable()."""
    if stand == "pg":
        from termit_app import pgkit
        return pgkit.usable()
    return False


def _inside(path: str, root) -> bool:
    root = os.path.realpath(str(root))
    return path == root or path.startswith(root.rstrip("/") + "/")


def brew_path() -> Optional[str]:
    """Настоящий brew — ТОЛЬКО из доверенных папок, в фиксированном порядке, и никогда из
    PATH: первый попавшийся «brew» в PATH мог подложить кто угодно (в том числе учебный brew
    песочницы). Файл обычный, исполняемый, чей-то из (текущий пользователь, root), и ни сам
    путь, ни то, куда ведёт ссылка, не лежат в проекте или песочнице."""
    from termit_app import paths
    for d in BREW_DIRS:
        cand = os.path.join(d, "brew")
        real = os.path.realpath(cand)
        try:
            st = os.stat(real)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode) or not os.access(real, os.X_OK):
            continue
        if st.st_uid not in (os.getuid(), 0):
            continue
        if any(_inside(x, r) for x in (os.path.abspath(cand), real)
               for r in (paths.ROOT, paths.SANDBOX_ROOT)) or "/.termit/" in real + "/":
            continue
        return cand
    return None


LATER_DAYS = 3

# Нейтральные тексты: тема без раздела implants (фэнтези, новая тема) говорит ими.
NEUTRAL = {
    "card": "🎁 В подарок утилита {name}: {what}.",
    "builtin": "   На чужой машине без неё: {builtin}",
    "command": "   Поставлю так: {command}",
    "zshrc": "   ~/.zshrc не меняется.",
    "ask": "Поставить? y — да, n — не надо, l — позже [y/n/l] ",
    "installing": "   Ставлю {formula}, это займёт минуту…",
    "installed": "✓ {binary} на месте: {path}",
    "failed": "brew не справился — не страшно, задача решается и без утилиты.",
    "declined": "   Понял, больше не предложу. Поставить самому: ./termit implants",
    "later": "   Ладно, спрошу через пару дней.",
    "interrupted": "   Прервал — ничего страшного, спрошу через пару дней.",
    "no_brew": "brew не найден — утилиты подождут; см. ./termit implants",
    "shell_hint": "   Подключить к своему zsh (сам, одной строкой): ./termit implants shell",
    "stub_install": "Учебно. Настоящие утилиты предлагают потом, после рана, — по одной и только "
                    "с твоего согласия.",
    "list_title": "Утилиты-подарки. Любая задача решается и без них — они дают скорость и "
                  "точность.",
    "st_installed": "стоит: {path}",
    "st_missing": "не стоит",
    "st_declined": "отказ — передумал? ./termit implants install ID",
    "st_later": "позже: спрошу после {date}",
    "builtin_short": "без неё: {builtin}",
    "command_short": "поставить: {command}",
    "list_hint": "Поставить с согласием: ./termit implants install ID · fzf и zoxide в своём "
                 "zsh: ./termit implants shell",
    "ask_yn": "Поставить? [y/n] ",
    "already": "✓ {binary} уже стоит: {path}",
    "not_now": "   Не ставлю.",
    "shell_title": "fzf и zoxide в твоём zsh: отдельный файл, подключаешь сам.",
    "shell_ask": "Записать {path}? ~/.zshrc не меняется [y/n] ",
    "shell_written": "✓ Записал {path}. Осталось вставить строку в ~/.zshrc: {line}",
    "shell_refused": "Не пишу: {path} — ссылка или не файл. Разберись с ним сам.",
}


def shown_name(imp: "Implant") -> str:
    """Владелец 26.10: «сначала имя, а в скобках кличка» — zoxide («Крот»)."""
    nick = (text("names") or {}).get(imp.id)
    real = imp.binary if imp.id != "pg" else "PostgreSQL"
    return f"{real} («{nick}»)" if nick else real


def find_implant(word: str) -> Optional["Implant"]:
    """Имплант по id, программе, формуле или имени из темы («zoxide», «z», «Крот»)."""
    w = word.strip().lower()
    names = {v.lower(): k for k, v in (text("names") or {}).items()}
    for imp in CATALOG:
        if w in (imp.id, imp.binary, imp.formula, (imp.command or "").lower()) or \
                names.get(w) == imp.id:
            return imp
    return None


def guide_lines(imp_id: str) -> List[str]:
    """Руководство к импланту: что делает, как пользоваться, без него, как убрать."""
    from termit_app import ui
    rows = (text("guide") or {}).get(imp_id)
    if not rows:
        return []
    name = shown_name(get(imp_id))
    out = [text("guide_head").format(name=name) if text("guide_head") else name]
    for para in rows:
        out += ui.story_fill(para, "   ", "     ").splitlines()
    return out


def text(key: str):
    """Строка (или словарь names/pitch) раздела implants выбранной темы; нет — нейтральная.
    Словари без темы пустые: имя утилиты тогда — её программа."""
    from termit_app import theme
    val = (theme.story("implants") or {}).get(key)
    if val:
        return val
    return NEUTRAL.get(key, {} if key in ("names", "pitch") else "")


def brew_args(formula: str) -> List[str]:
    """Аргументы установки после пути к brew: --formula закрывает подмену каском с тем же
    именем; формула — только из каталога (ядро Homebrew)."""
    return ["install", "--formula", formula]


def command_line(imp: Implant) -> str:
    """Ровно то, что запустит brew_install (карточка показывает правду)."""
    return "HOMEBREW_NO_AUTO_UPDATE=1 brew " + " ".join(brew_args(imp.formula))


def _state(p: dict) -> dict:
    st = p.setdefault("implants", {})
    for key, empty in (("declined", list), ("later", dict), ("offered", dict),
                       ("seen_installed", list), ("compare", dict)):
        if not isinstance(st.get(key), empty):
            st[key] = empty()
    return st


def _solved(p: dict, task_id: str) -> bool:
    rec = p.get("tasks", {}).get(task_id)
    return isinstance(rec, dict) and (rec.get("solved") or 0) > 0


def _later_passed(st: dict, imp_id: str, today: date) -> bool:
    when = st["later"].get(imp_id)
    if not when:
        return True
    try:
        return date.fromisoformat(str(when)) <= today
    except ValueError:
        return True


def eligible(p: dict, today: Optional[date] = None) -> List[Implant]:
    """Кому пора подарить: урок установки и близнец решены, не стоит, не отказано,
    «позже» истекло. Порядок — порядок каталога."""
    today = today or date.today()
    st = _state(p)
    if not _solved(p, "brew_lesson"):
        return []
    return [imp for imp in CATALOG
            if _solved(p, imp.twin) and imp.id not in st["declined"]
            and _later_passed(st, imp.id, today) and not installed(imp.id)
            and (not imp.needs_stand or stand_ok(imp.needs_stand))]


def _ask(ask: Callable, prompt: str) -> str:
    try:
        return (ask(prompt) or "").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _card(imp: Implant) -> None:
    """Карточка подарка: имя из темы, что даёт, встроенный двойник, ровно запускаемая команда."""
    from termit_app import ui
    name = shown_name(imp)
    ui.say()
    ui.say(ui.story_fill(text("card").format(name=name, what=imp.what, binary=imp.binary),
                         "", "   "))
    pitch = text("pitch").get(imp.id)
    if pitch:
        ui.say(ui.story_fill(pitch, "   ", "   "))
    ui.say(text("builtin").format(builtin=imp.builtin))
    ui.say(text("command").format(command=command_line(imp)))
    ui.say(text("zshrc"))


def _install(st: dict, imp: Implant, installer: Optional[Callable], today: date) -> Optional[str]:
    """После явного y: installer (по умолчанию brew_install), затем проверка which. Не вышло
    или Ctrl+C — «позже» на LATER_DAYS дней. Вернуть id, если программа на месте."""
    from termit_app import ui
    ui.say(text("installing").format(formula=imp.formula))
    try:
        (installer or brew_install)(imp.formula)
    except KeyboardInterrupt:
        print()
        st["later"][imp.id] = (today + timedelta(days=LATER_DAYS)).isoformat()
        ui.say(text("interrupted"))
        return None
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        pass
    path = locate(imp)
    if path:
        st["later"].pop(imp.id, None)
        ui.ok(text("installed").format(binary=imp.binary, path=path))
        for row in guide_lines(imp.id):     # владелец 25.10: подробно, как пользоваться
            ui.say(row)
        if imp.shell:
            ui.say(text("shell_hint"))
        return imp.id
    st["later"][imp.id] = (today + timedelta(days=LATER_DAYS)).isoformat()
    ui.say(ui.story_fill(text("failed"), "   ", "   "))
    return None


def would_ask(p: dict, today: date) -> bool:
    """offer сегодня задаст вопрос (есть кому подарить, сегодня ещё не спрашивали, brew есть):
    конец рана — не больше одного вопроса на всех (M1 ревью Q4, warehouse.goes_first)."""
    if not eligible(p, today):
        return False
    st = _state(p)
    return today.isoformat() not in st["offered"].values() and bool(brew_path())




def post_offer(p: dict, today: date) -> Optional[str]:
    """Карточка утилиты без вопроса (в убежище вопрос живёт на деке): id утилиты или None.
    Те же правила, что у offer: раз в день, без brew — одна строка и молчание."""
    from termit_app import ui
    cands = eligible(p, today)
    if not cands:
        return None
    st = _state(p)
    if today.isoformat() in st["offered"].values():
        return None             # раз в день: три ./termit train подряд — не три карточки
    if not brew_path():
        if not st.get("no_brew_told"):
            st["no_brew_told"] = True
            ui.say()
            ui.say(ui.story_fill(text("no_brew"), "", "   "))
        return None
    imp = cands[0]
    _card(imp)
    st["offered"][imp.id] = today.isoformat()
    return imp.id


def answer(p: dict, imp_id: str, reply: str, today: date,
           installer: Optional[Callable] = None) -> Optional[str]:
    """y — ставим (installer, по умолчанию brew_install), n — отказ навсегда,
    l/пусто/прочее — спросим через LATER_DAYS дней. Вернуть id, если поставили."""
    from termit_app import ui
    imp = find(imp_id)
    if imp is None:
        return None
    st = _state(p)
    reply = (reply or "").strip().lower()
    if reply in YES:
        return _install(st, imp, installer, today)
    if reply in NO:
        if imp.id not in st["declined"]:
            st["declined"].append(imp.id)
        ui.say(text("declined"))
        return None
    st["later"][imp.id] = (today + timedelta(days=LATER_DAYS)).isoformat()
    ui.say(text("later"))
    return None


def offer(p: dict, ask: Callable, today: date,
          installer: Optional[Callable] = None) -> Optional[str]:
    """Конец рана в разовом режиме: не больше ОДНОГО предложения, карточка и вопрос сразу.
    Вернуть id, если поставили."""
    imp_id = post_offer(p, today)
    if imp_id is None:
        return None
    return answer(p, imp_id, _ask(ask, text("ask")), today, installer)


def find(key: str) -> Optional[Implant]:
    """Утилита по id, формуле или программе (rg, ripgrep); нет — None."""
    for imp in CATALOG:
        if key in (imp.id, imp.formula, imp.binary, imp.command):
            return imp
    return None


def status(p: dict, imp: Implant, today: Optional[date] = None) -> Tuple[str, str]:
    """(installed|declined|later|missing, подробность): путь к программе или дата «позже»."""
    today = today or date.today()
    path = locate(imp)
    if path:
        return "installed", path
    st = _state(p)
    if imp.id in st["declined"]:
        return "declined", ""
    if not _later_passed(st, imp.id, today):
        return "later", str(st["later"][imp.id])
    return "missing", ""


def listing(p: dict, today: Optional[date] = None) -> List[str]:
    """./termit implants: каталог с именами из темы, статусом, двойником и командой."""
    out = [text("list_title"), ""]
    for imp in CATALOG:
        key, detail = status(p, imp, today)
        name = shown_name(imp)
        out.append(f"  {imp.id:<7} {name} — {imp.what}")
        out.append("          " + text("st_" + key).format(path=detail, date=detail))
        out.append("          " + text("builtin_short").format(builtin=imp.builtin))
        out.append("          " + text("command_short").format(command=command_line(imp)))
    out += ["", text("list_hint")]
    return out


def install_cmd(p: dict, imp: Implant, ask: Callable, today: Optional[date] = None,
                installer: Optional[Callable] = None) -> int:
    """./termit implants install ID: карточка и [y/n]. Отказ снимается только по y.
    Нет доверенного brew — не спрашиваем. Код: 0 — стоит, поставлено или «не надо»;
    1 — нет brew или установка не удалась (программы после неё нет)."""
    from termit_app import ui
    today = today or date.today()
    path = locate(imp)
    if path:
        ui.ok(text("already").format(binary=imp.binary, path=path))
        return 0
    if not brew_path():
        ui.say(ui.story_fill(text("no_brew"), "", "   "))
        return 1
    st = _state(p)
    _card(imp)
    if _ask(ask, text("ask_yn")) not in YES:
        ui.say(text("not_now"))
        return 0
    if imp.id in st["declined"]:
        st["declined"].remove(imp.id)
    return 0 if _install(st, imp, installer, today) else 1


def brew_install(formula: str) -> int:
    """ЕДИНСТВЕННОЕ место запуска настоящего brew: только формула ядра из каталога, без tap,
    sudo и curl | sh, без автообновления. Под TERMIT_NO_BREW (все тесты) — ошибка."""
    if os.environ.get("TERMIT_NO_BREW"):
        raise RuntimeError("brew в тестах запрещён")
    if formula not in {imp.formula for imp in CATALOG}:
        raise ValueError(f"формулы {formula!r} нет в каталоге")
    brew = brew_path()
    if not brew:
        return 127
    env = {**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ENV_HINTS": "1"}
    return subprocess.run([brew] + brew_args(formula), env=env).returncode


# --- fzf и zoxide в своём zsh (I5) ------------------------------------------------------
# Игра НИКОГДА не пишет в ~/.zshrc. Свой файл — только по явной команде
# ./termit implants shell write; строку source владелец ставит сам.
SHELL_FILE = Path.home() / ".config" / "termit" / "shell.zsh"
ZSHRC = Path.home() / ".zshrc"
SHELL_LINE = "source ~/.config/termit/shell.zsh"
_SOURCED = re.compile(r"""^\s*(?:source|\.)\s+["']?(?:~|\$HOME|\$\{HOME\})/\.config/termit/"""
                      r"""shell\.zsh["']?\s*(?:#.*)?$""", re.M)


def shell_text() -> str:
    return (
        "# TermitRun: интеграция имплантов. Подключи сам ОДНОЙ строкой в ~/.zshrc —\n"
        f"# до строки с zsh-syntax-highlighting:   {SHELL_LINE}\n"
        "[[ -n $TERMIT_BOX ]] && return 0      # внутри игры — штатные Ctrl+R, Ctrl+T и cd\n"
        "(( $+commands[fzf] ))    && source <(fzf --zsh 2>/dev/null)\n"
        "(( $+commands[zoxide] )) && eval \"$(zoxide init zsh)\"\n")


def write_shell(path=None) -> bool:
    """Атомарно записать shell_text() в path (по умолчанию SHELL_FILE), права 0644. Отказ
    (False), если path — символическая ссылка или не обычный файл: ссылку не перезаписываем
    и по ней не пишем."""
    path = Path(path or SHELL_FILE)
    if os.path.islink(path) or (os.path.lexists(path) and not path.is_file()):
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".shell.", suffix=".tmp", dir=str(path.parent))
    except OSError:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(shell_text())
        os.chmod(tmp, 0o644)
        if os.path.islink(path):        # подменили, пока писали
            return False
        os.replace(tmp, path)
        tmp = None
        return True
    except OSError:
        return False
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def sourced_in_zshrc(zshrc=None) -> bool:
    """Подключил ли владелец файл: только ЧТЕНИЕ ~/.zshrc (по умолчанию ZSHRC)."""
    try:
        with open(str(zshrc or ZSHRC), encoding="utf-8", errors="replace") as f:
            body = f.read(1024 * 1024)
    except OSError:
        return False
    return bool(_SOURCED.search(body))


def shell_lines() -> List[str]:
    """./termit implants shell: путь, содержимое, строка для ~/.zshrc и где её ставить."""
    exists = SHELL_FILE.is_file() and not SHELL_FILE.is_symlink()
    out = [text("shell_title"), "",
           f"  Файл: {SHELL_FILE} — " + ("есть" if exists else
                                         "ещё нет: ./termit implants shell write"), ""]
    out += ["  " + line for line in shell_text().splitlines()]
    out += ["", "  Строка для ~/.zshrc (вставь сам):", f"    {SHELL_LINE}",
            "  Где: после строки с oh-my-zsh.sh, но ДО zsh-syntax-highlighting — он должен "
            "грузиться последним.",
            "  Если zsh-syntax-highlighting стоит в plugins=(…) внутри oh-my-zsh — просто в "
            "конец ~/.zshrc: современный zsh-syntax-highlighting это переживает.",
            "  " + ("✓ Подключено в ~/.zshrc." if sourced_in_zshrc()
                    else "Пока не подключено: игра в ~/.zshrc не пишет никогда."),
            "  fzf --zsh есть в fzf 0.48 и новее; со старым fzf строка просто молчит.",
            "  Внутри игры файл сразу выходит: там Ctrl+R, Ctrl+T и cd — штатные."]
    return out


# --- «до/после» (I9): честное сравнение времени --------------------------------------
# Показ — только при настоящем выигрыше: утилита в журнале, решено без подсказок и Совы,
# у близнеца есть время первого решения руками, и оно больше в GAIN_RATIO раз и на
# GAIN_SECONDS секунд. Иначе тишина: цифр не выдумываем.
GAIN_RATIO = 2.0
GAIN_SECONDS = 15

NEUTRAL.update({
    "compare": "⏱ Руками («{twin}»): {hand} → с {name}: {now} — в {ratio} раза быстрее.",
    "teaser": "С утилитой {binary} — {what}. Подробнее: ./termit implants",
    "nudge": "С утилитой {binary} это быстрее — ./termit implants",
})

# границы команд в строке журнала: | ; & && || перевод строки ` $( ( )
_CMD_SPLIT = re.compile(r"\|\||&&|[|;&\n`()]|\$\(")
_PREFIXES = ("time", "command", "builtin", "noglob", "nocorrect", "exec", "nice", "sudo", "env")
_ASSIGN = re.compile(r"^[A-Za-z_]\w*=")


def _skip_dq(line: str, i: int) -> Tuple[List[str], int]:
    """Текст в "…" с позиции i (сразу за открывающей кавычкой): подстановки $(…) и `…`
    внутри (уже без своих кавычек) и позиция за закрывающей кавычкой. \" — не кавычка."""
    subs, n = [], len(line)
    while i < n:
        c = line[i]
        if c == "\\":
            i += 2
        elif c == '"':
            return subs, i + 1
        elif line.startswith("$(", i):
            inner, i = _skip_paren(line, i + 2)
            subs.append(_code(inner))
        elif c == "`":
            j = line.find("`", i + 1)
            j = n if j < 0 else j
            subs.append(_code(line[i + 1:j]))
            i = j + 1
        else:
            i += 1
    return subs, n


def _skip_paren(line: str, i: int) -> Tuple[str, int]:
    """Тело $(…) с позиции i (за «$(») до парной скобки — с учётом кавычек и вложенных
    скобок — и позиция за ней. Незакрытая — до конца строки."""
    depth, n, start = 1, len(line), i
    while i < n:
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = line.find("'", i + 1)
            i = n if j < 0 else j + 1
            continue
        if c == '"':
            i = _skip_dq(line, i + 1)[1]
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return line[start:i], i + 1
        i += 1
    return line[start:], n


def _code(line: str) -> str:
    """Строка без текста в кавычках и без комментария: «echo "a|qsv"» и «ls # ; qsv» утилиту
    не запускают. Подстановки $(…) и `…` внутри "…" — запускают, их оставляем (без их
    собственных кавычек). Разбор — слева направо, как у оболочки: апостроф внутри "…" —
    просто буква (ревью P10)."""
    out, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\":                     # \" \' \# — буква, не кавычка и не комментарий
            out.append(" ")
            i += 2
        elif c == "'":
            j = line.find("'", i + 1)
            out.append(" ")
            i = n if j < 0 else j + 1
        elif c == '"':
            subs, i = _skip_dq(line, i + 1)
            out.append("".join(f" ; {x} ; " for x in subs) or " ")
        elif c == "#" and (i == 0 or line[i - 1].isspace()):
            break
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _commands(line: str):
    """Программы, которые строка запускает: первое слово каждой команды (без VAR=, time,
    command и т.п. впереди), путь /…/rg — как rg."""
    for seg in _CMD_SPLIT.split(_code(line)):
        words = seg.replace('"', " ").replace("'", " ").split()
        while words and (words[0] in _PREFIXES or _ASSIGN.match(words[0])):
            words = words[1:]
        if words:
            yield os.path.basename(words[0])


def used(cmds: List[str], imp: Implant) -> bool:
    """Набирал ли игрок утилиту (строки cmds.log): первое слово команды — её программа;
    у zoxide ещё z и zi, fzf засчитывается где угодно в строке (… | fzf, $(fzf))."""
    names = {imp.binary, imp.cmd} | ({"z", "zi"} if imp.id == "zoxide" else set())
    for line in cmds:
        if imp.id == "fzf" and re.search(r"(?<![\w.-])fzf(?![\w.-])", _code(line)):
            return True
        if any(name in names for name in _commands(line)):
            return True
    return False


def _number(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value)


def _twin_title(twin: str) -> str:
    from termit_app import theme
    from termit_app.tasks import registry
    tasks = registry.all_tasks()
    return theme.title(tasks[twin]) if twin in tasks else twin


def tools_used(cmds: List[str]) -> List[str]:
    """id утилит каталога, которые набирались в cmds (для честной ручной базы близнеца)."""
    return [imp.id for imp in CATALOG if used(cmds, imp)]


def hand_time(rec) -> Optional[float]:
    """Время первого решения, если оно руками: при нём не запускалась ни одна утилита
    (rec["first_tools"] пуст, см. session._first_tools) и не было подсказок и вопросов Сове
    (rec["first_hints"] — 0; нет ключа — записи до этого учёта, считаем без них). Нет ключа (запись до учёта утилит)
    или утилиты были — None."""
    if not isinstance(rec, dict) or rec.get("first_tools") != []:
        return None
    hints = rec.get("first_hints", 0)
    if not isinstance(hints, int) or isinstance(hints, bool) or hints != 0:
        return None             # с подсказками или Совой — время раздуто чтением
    return _number(rec.get("first_time"))


def compare(task, p: dict, elapsed: float, cmds: List[str], hints_used: int) -> Optional[str]:
    """Строка «до/после» для решённой задачи-пары или None. cmds — только команды, которые
    отработали с кодом 0 (sandbox.read_cmd_status), плюс решившая задачу ans (session._ok_cmds),
    а программа утилиты есть у родителя на момент разбора: «command not found» и упавший
    запуск выигрышем не считаются. База —
    первое решение близнеца руками (hand_time). Лучшая пара — в p["implants"]["compare"];
    строка — при первом настоящем выигрыше и при новом рекорде. hints_used — подсказки и
    вопросы Сове за эту задачу."""
    imp_id = getattr(task, "implant", None)
    if not imp_id or hints_used:
        return None
    try:
        imp = get(imp_id)
    except KeyError:
        return None
    if not installed(imp.id) or not used(cmds, imp):
        return None
    hand = hand_time((p.get("tasks") or {}).get(imp.twin))
    now = _number(elapsed)
    if hand is None or now is None:
        return None
    if hand / now < GAIN_RATIO or hand - now < GAIN_SECONDS:
        return None
    st = _state(p)
    best = st["compare"].get(task.id)
    if isinstance(best, dict) and _number(best.get("after")) and now >= best["after"]:
        return None
    st["compare"][task.id] = {"twin": imp.twin, "hand": hand, "after": round(now, 1)}
    from termit_app import ui
    return text("compare").format(twin=_twin_title(imp.twin), hand=ui.fmt_time(hand),
                                  name=shown_name(imp),
                                  now=ui.fmt_time(now),
                                  ratio=f"{hand / now:.1f}".replace(".", ","))


def _pitchable(task, p: Optional[dict]) -> Optional[Implant]:
    """Утилита задачи, о которой уместно напомнить: не стоит и от неё не отказывались.
    Сначала руками, потом подарок (финальное ревью части 5): на задаче-близнеце — только
    когда близнец уже решён (без прогресса — молчим); при известном прогрессе — только после
    урока установки brew_lesson, как и сами подарки (eligible)."""
    imp_id = getattr(task, "implant", None)
    if not imp_id:
        return None
    try:
        imp = get(imp_id)
    except KeyError:
        return None
    if installed(imp.id) or (p is not None and imp.id in _state(p)["declined"]):
        return None
    if task.id == imp.twin and (p is None or not _solved(p, imp.twin)):
        return None
    if p is not None and not _solved(p, "brew_lesson"):
        return None
    return imp


def _pitch(key: str, task, p: Optional[dict]) -> Optional[str]:
    imp = _pitchable(task, p)
    if imp is None:
        return None
    return text(key).format(name=shown_name(imp), binary=imp.binary,
                            what=imp.what)


def teaser(task, p: Optional[dict] = None) -> Optional[str]:
    """Строка под разбором задачи-пары: что даст утилита, если её нет (и не было отказа)."""
    return _pitch("teaser", task, p)


def nudge(task, p: Optional[dict] = None) -> Optional[str]:
    """Строка на карточке задачи-пары в тренировке: утилиты нет — есть ./termit implants."""
    return _pitch("nudge", task, p)
