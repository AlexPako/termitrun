"""Терминальная графика без зависимостей: уровни возможностей, рамки, бары, спарклайн, цвет.

Модуль ничего не знает про игру: функции получают строки и возвращают строки, печатает ui/cli.
Три уровня (caps().level):
  rich  — UTF-8 рамки ╭─╮ ╔═╗, бары ▰▱, спарклайн ▁▂▃▅▇, цвет 16/256, лёгкая анимация;
  basic — ASCII-рамки +-|, бары [##..], цвет по возможности (не-UTF-8 локаль);
  plain — голый текст, как до графики: не tty, TERM=dumb, окно уже 60, TERMIT_PLAIN=1.
Смысл никогда не живёт только в графике: бар всегда идёт с числом «2 из 4».
Палитра — токенами в теме (раздел palette), коды выбираются по глубине цвета терминала."""
import os
import random
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass, replace
from typing import Iterable, List, Optional, Sequence, Tuple, Union

MAX_WIDTH = 100                         # FB17: вывод — по окну, но не шире 100 знаков
MIN_WIDTH = 20
NARROW = 60
NBSP = "\u00a0"
ANIM_LIMIT = 0.6                        # вся анимация одного экрана — не дольше, с
GLITCH_LIMIT = 0.3                      # глитч заголовка итога (04-graphics: 3–4 кадра, 0,3 с)
RAIN_LIMIT = 0.8                        # дождь кода над итогом
ANSI = re.compile(r"\033\[[0-9;]*m")


@dataclass(frozen=True)
class Caps:
    level: str          # "rich" | "basic" | "plain"
    colors: int         # 0 | 8 | 256
    unicode: bool
    width: int          # min(MAX_WIDTH, колонки окна), не меньше MIN_WIDTH
    anim: bool


PLAIN = Caps("plain", 0, False, MAX_WIDTH, False)


def _on(env, key: str) -> bool:
    """Свой переключатель: пусто или «0» — выключен (TERMIT_PLAIN=0 не включает plain)."""
    return env.get(key, "") not in ("", "0")


def detect(env=None, stream=None, columns: Optional[int] = None) -> Caps:
    """Возможности терминала. env/stream/columns подменяются в тестах."""
    env = os.environ if env is None else env
    stream = sys.stdout if stream is None else stream
    try:
        tty = stream.isatty()
    except (AttributeError, ValueError):
        tty = False
    term = env.get("TERM", "")
    if columns is None:
        columns = shutil.get_terminal_size((80, 24)).columns
    width = max(MIN_WIDTH, min(MAX_WIDTH, columns))
    if not tty or term == "dumb":
        return replace(PLAIN, width=width)
    colors = 0 if env.get("NO_COLOR") else (256 if "256" in term or env.get("COLORTERM") else 8)
    enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
    locale = env.get("LC_ALL") or env.get("LC_CTYPE") or env.get("LANG") or ""
    unicode = "utf8" in enc and locale not in ("C", "POSIX")
    if _on(env, "TERMIT_PLAIN") or columns < NARROW:
        return Caps("plain", colors, unicode, width, False)
    level = "rich" if unicode else "basic"
    anim = level == "rich" and not _on(env, "TERMIT_NO_ANIM") and not env.get("SSH_CONNECTION")
    return Caps(level, colors, unicode, width, anim)


def caps() -> Caps:
    """Считается на каждый экран: дёшево, а stdout в тестах подменяется."""
    return detect()


def width(c: Caps = None) -> int:
    """FB17: ширина вывода игры — единый источник: min(100, колонки окна), не меньше 20."""
    return (c or caps()).width


def text_width(c: Caps = None) -> int:
    """Текст карточек, уроков и разборов: на клетку уже окна (курсор в последней колонке
    иначе переносит строку)."""
    return width(c) - 1


def story_width(c: Caps = None) -> int:
    """Абзацы с эмодзи и реплики: на две клетки уже окна — запас на двойную ширину эмодзи."""
    return width(c) - 2


# --- Ширина --------------------------------------------------------------------------------

def vlen(s: str) -> int:
    """Ширина на экране: без ANSI-кодов, эмодзи и иероглифы (W/F) — две клетки."""
    s = ANSI.sub("", s)
    return sum(0 if unicodedata.combining(ch) or ch in "‍️" else
               2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s: str, n: int) -> str:
    return s + " " * max(0, n - vlen(s))


def trunc(s: str, n: int) -> str:
    """Строка не шире n клеток; лишнее — «…» (цвет при обрезке снимается)."""
    if vlen(s) <= n:
        return s
    out = ""
    for ch in ANSI.sub("", s):
        if vlen(out + ch) > n - 1:
            break
        out += ch
    return out + "…"


def fill(text: str, width: int, first: str = "", rest: str = "") -> List[str]:
    """Абзац по ширине экрана (с учётом эмодзи): слова не рвутся, два последних склеены —
    одно слово не висит на строке, ./termit не отрывается от команды."""
    words = [w for w in re.split(r"[ \t\n]+", text) if w]     # неразрывный пробел держит
    if len(words) >= 2:
        words[-2:] = [words[-2] + NBSP + words[-1]]
    glued = " ".join(words).replace("./termit ", "./termit" + NBSP).split(" ")
    lines, cur, empty = [], first, True
    for w in glued:
        cand = cur + w if empty else cur + " " + w
        if empty or vlen(cand) <= width:
            cur, empty = cand, False
        else:
            lines.append(cur)
            cur = rest + w
    lines.append(cur)
    return [line.replace(NBSP, " ") for line in lines]


# --- Цвет ----------------------------------------------------------------------------------

DEFAULT_PALETTE = {
    "bold": {"16": "1"},
    "dim": {"16": "2"},
    "italic": {"16": "3"},
    "accent": {"16": "35;1", "256": "38;5;199;1"},
    "neon": {"16": "36", "256": "38;5;51"},
    "code": {"16": "33;1", "256": "38;5;221;1"},     # команды в уроках: тёплый жёлтый
    "ok": {"16": "32", "256": "38;5;118"},
    "warn": {"16": "33", "256": "38;5;214"},
    "bad": {"16": "33", "256": "38;5;208"},          # мягко: оранжевый, не красный
    "frame": {"16": "35", "256": "38;5;93"},
    "boss": {"16": "31;1", "256": "38;5;196;1"},
}
DEFAULT_CHARS = {"bar_on": "▰", "bar_off": "▱"}


def _theme_section(key: str) -> dict:
    try:
        from termit_app import theme
        return theme.load(theme.current()).get(key) or {}
    except Exception:            # tui не должен падать из-за темы
        return {}


# --- Скин (купленная косметика, K4) ---------------------------------------------------------
# Переопределения токенов и вида рамок плюс выбранная анимация итога. Ставит
# cosmetics.activate(p) один раз за запуск. В plain скин не действует (вывод байт в байт
# прежний); токен boss не перекрашивается никогда — красный остаётся цветом стража;
# двойная рамка — «событие»: её вид не меняется, только цвет.
LOCKED_TOKENS = frozenset({"boss"})
_SKIN = {"tokens": {}, "kinds": {}, "anim": None}


def set_skin(tokens: Optional[dict] = None, kinds: Optional[dict] = None,
             anim: Optional[str] = None) -> None:
    """Без аргументов — сброс к виду по умолчанию."""
    _SKIN["tokens"] = {k: dict(v) for k, v in (tokens or {}).items()
                       if k not in LOCKED_TOKENS and isinstance(v, dict)}
    _SKIN["kinds"] = {k: v for k, v in (kinds or {}).items()
                      if k != "double" and v in BOXES and v != "double"}
    _SKIN["anim"] = anim or None


def anim_name() -> Optional[str]:
    """Выбранная анимация итога рана (glitch, scan, rain) или None."""
    return _SKIN["anim"]


def pick(tok: dict, c: Caps) -> str:
    """Код цвета токена {"16": …, "256": …} под глубину цвета терминала."""
    if c.colors >= 256 and "256" in tok:
        return tok["256"]
    return tok.get("16", "")


def code(name: str, c: Caps) -> str:
    tok = (_SKIN["tokens"].get(name) if c.level != "plain" else None) \
        or _theme_section("palette").get(name) or DEFAULT_PALETTE.get(name) or {}
    return pick(tok, c)


def style(text: str, *names: str, c: Caps = None) -> str:
    """Текст в цветах токенов темы; без цвета (NO_COLOR, не tty) — как есть."""
    c = c or caps()
    if not c.colors or not text:
        return text
    codes = ";".join(x for x in (code(n, c) for n in names) if x)
    return f"\033[{codes}m{text}\033[0m" if codes else text


def chars() -> dict:
    return {**DEFAULT_CHARS, **_theme_section("chars")}


# --- Рамки, разделители, бары --------------------------------------------------------------

BOXES = {   # tl, tr, bl, br, h, v, ml, mr
    "single": "┌┐└┘─│├┤",
    "round": "╭╮╰╯─│├┤",
    "double": "╔╗╚╝═║╠╣",
    "heavy": "┏┓┗┛━┃┣┫",
}
ASCII_BOXES = {"single": "++++-|++", "round": "++++-|++", "double": "++++=|++",
               "heavy": "++++-|++"}
SEP = object()          # строка-разделитель внутри рамки


class Raw(str):
    """Готовая строка для рамки: не переносится и не схлопывает пробелы (карта, колонки)."""
Row = Union[str, Tuple[str, str, str], object]


def _glyphs(kind: str, c: Caps) -> str:
    if kind != "double":
        kind = _SKIN["kinds"].get(kind, kind)
    return (BOXES if c.level == "rich" else ASCII_BOXES)[kind]


def rule(c: Caps = None, width: int = None, indent: str = "   ") -> str:
    c = c or caps()
    n = (width or c.width) - len(indent)
    if c.level == "plain":
        return ""
    return indent + style(("─" if c.level == "rich" else "-") * n, "dim", c=c)


def box(rows: Sequence[Row], title: str = "", right: str = "", kind: str = "single",
        c: Caps = None, width: int = None, color: str = "frame") -> List[str]:
    """Рамка шириной width (по умолчанию caps.width - 2, с отступом в один пробел).
    rows: строка (переносится с отступом 2), (текст, отступ первой, отступ остальных)
    или SEP. В plain рамки нет: заголовок строкой, строки с отступом в два пробела."""
    c = c or caps()
    width = min(width or c.width - 1, c.width - 1)
    inner = width - 4                       # "│ " + текст + " │"
    body: List[str] = []
    for row in rows:
        if row is SEP or isinstance(row, Raw):
            body.append(row)
            continue
        text, first, rest = (row, "", "  ") if isinstance(row, str) else row
        if not text:
            body.append("")
            continue
        body.extend(fill(text, inner, first, rest))
    if c.level == "plain":
        out = [f"  {title}" + (f" · {right}" if right else "")] if title or right else []
        return out + [("  " + line) if line else "" for line in body if line is not SEP]
    tl, tr, bl, br, h, v, ml, mr = _glyphs(kind, c)
    fr = lambda s: style(s, color, c=c)          # noqa: E731
    top = f"{h} " + style(title, "bold", c=c) + " " if title else ""
    tail = (f" {right} {h}{h}") if right else ""
    used = vlen(top) + vlen(tail)
    if used > width - 2 and right:               # не влезло справа — справа ничего
        body[0:0] = fill(right, inner, "", "  ")
        tail, used = "", vlen(top)
    if used > width - 2:                         # длинный заголовок — в тело, по словам
        body[0:0] = [style(x, "bold", c=c) for x in fill(title, inner, "", "  ")] + [SEP]
        top, used = "", 0
    head = fr(tl) + _frame_title(top, h, fr) + fr(h * (width - 2 - used)) + fr(tail) + fr(tr)
    out = [" " + head]
    for line in body:
        if line is SEP:
            out.append(" " + fr(ml + h * (width - 2) + mr))
        else:
            out.append(" " + fr(v) + " " + pad(trunc(line, inner), inner) + " " + fr(v))
    out.append(" " + fr(bl + h * (width - 2) + br))
    return out


def _frame_title(top: str, h: str, fr) -> str:
    """Черта рамки в цвете рамки, текст заголовка — в своём."""
    if not top.startswith(h):
        return top
    lead = h * (len(top) - len(top.lstrip(h)))
    return fr(lead) + top[len(lead):]


def bar(done: int, total: int, width: int = None, c: Caps = None) -> str:
    """▰▰▱▱ (rich) / [##..] (basic) / пусто (plain): число «из» всегда пишет вызывающий."""
    c = c or caps()
    if c.level == "plain" or total <= 0:
        return ""
    width = width or total
    on = round(width * max(0, min(done, total)) / total)
    if c.level == "rich":
        ch = chars()
        return style(ch["bar_on"] * on, "accent", c=c) + style(ch["bar_off"] * (width - on),
                                                                  "dim", c=c)
    return "[" + "#" * on + "." * (width - on) + "]"


SPARK = "▁▂▃▄▅▆▇█"
SPARK_ASCII = "_.-=+*#"


def spark(values: Iterable[float], c: Caps = None) -> str:
    """Спарклайн: ноль — самая низкая ступень, максимум — самая высокая."""
    c = c or caps()
    values = list(values)
    if c.level == "plain" or not values:
        return ""
    steps = SPARK if c.level == "rich" else SPARK_ASCII
    top = max(values) or 1
    idx = [0 if v <= 0 else max(1, round(v / top * (len(steps) - 1))) for v in values]
    return style("".join(steps[i] for i in idx), "neon", c=c)


def label(text: str, c: Caps = None) -> str:
    """Плашка ▌ТЕКСТ▐ (rich) / [ТЕКСТ] (basic) / текст (plain)."""
    c = c or caps()
    if c.level == "rich":
        return style(f"▌{text}▐", "accent", c=c)
    return f"[{text}]" if c.level == "basic" else text


def columns(cells: Sequence[str], width: int) -> str:
    """Ячейки по центру равных колонок (для карты)."""
    n = len(cells) or 1
    col = width // n
    out = ""
    for cell in cells:
        room = col - vlen(cell)
        left = room // 2
        out += " " * left + cell + " " * (room - left)
    return out.rstrip()


# --- Анимация ------------------------------------------------------------------------------

def typewriter(text: str, *names: str, c: Caps = None, stream=None, sleep=time.sleep,
               limit: float = ANIM_LIMIT) -> None:
    """Печать строки по символам — только rich + tty + без TERMIT_NO_ANIM; вся печать ≤ limit с.
    Никаких очисток экрана и курсорных кодов: строка просто дописывается слева направо.
    names — токены цвета всей строки."""
    c = c or caps()
    stream = stream or sys.stdout
    if not c.anim or not text:
        stream.write(style(text, *names, c=c) + "\n")
        stream.flush()
        return
    text = style(text, *names, c=c)
    parts = re.split(r"(\033\[[0-9;]*m)", text)          # коды пишем сразу, без пауз
    visible = sum(1 for part in parts if not ANSI.fullmatch(part) for ch in part if ch != " ")
    delay = min(0.02, limit / max(1, visible))
    done = False
    try:
        for part in parts:
            if ANSI.fullmatch(part):
                stream.write(part)
                continue
            for ch in part:
                stream.write(ch)
                stream.flush()
                if ch != " ":
                    sleep(delay)
        done = True
    finally:
        if not done and c.colors:        # Ctrl+C посреди строки: zsh не останется в цвете
            stream.write("\033[0m")
        stream.write("\n")
        stream.flush()


# --- Анимации итога рана (косметика K5) ----------------------------------------------------
# Все три — только при c.anim (rich + tty + без TERMIT_NO_ANIM и SSH). Без очистки экрана и
# курсорных кодов: глитч перерисовывает одну короткую строку через \r, развёртка и дождь
# просто печатают строки с паузами. Ctrl+C посреди анимации сбрасывает цвет (как typewriter).
# sleep=None — time.sleep в момент вызова (тесты подменяют tui.time.sleep).

GLITCH = "█▓▒░#@%"
RAIN = "01<>/\\|=+*#$%&"


def _corrupt(parts: List[str], frame: int) -> str:
    """Кадр глитча: каждая ~третья видимая клетка шириной 1 — знак помех; коды цвета на месте."""
    out, k = [], 0
    for part in parts:
        if ANSI.fullmatch(part):
            out.append(part)
            continue
        for ch in part:
            if ch != " " and vlen(ch) == 1:
                k += 1
                if (k * 7 + frame * 5) % 3 == 0:
                    ch = GLITCH[(k + frame) % len(GLITCH)]
            out.append(ch)
    return "".join(out)


def _finish(stream, c: Caps, done: bool, end: str = "") -> None:
    """Хвост анимации: прервана (Ctrl+C, OSError) — сброс цвета, чтобы zsh не остался в цвете;
    сломанный поток при этом не роняет игру второй ошибкой."""
    try:
        if not done and c.colors:
            stream.write("\033[0m")
        stream.write(end)
        stream.flush()
    except OSError:
        pass


def glitch(line: str, c: Caps = None, stream=None, sleep=None, frames: int = 3,
           limit: float = GLITCH_LIMIT) -> None:
    """Строка (уже в цвете) печатается с frames кадрами помех через \r; итог — сама строка."""
    c = c or caps()
    stream = stream or sys.stdout
    if not c.anim or not line:
        stream.write(line + "\n")
        stream.flush()
        return
    sleep = sleep or time.sleep
    parts = re.split(r"(\033\[[0-9;]*m)", line)
    delay = min(0.08, limit / max(1, frames))
    done = False
    try:
        for f in range(frames):
            stream.write("\r" + _corrupt(parts, f))
            stream.flush()
            sleep(delay)
        stream.write("\r" + line)
        done = True
    except OSError:                  # терминал закрылся посреди анимации — молча дальше
        pass
    finally:
        _finish(stream, c, done, "\n")


def scan(lines: Sequence[str], c: Caps = None, stream=None, sleep=None,
         limit: float = ANIM_LIMIT) -> None:
    """ЭЛТ-развёртка: строки рамки по одной, вся печать ≤ limit с."""
    c = c or caps()
    stream = stream or sys.stdout
    if not c.anim or not lines:
        stream.write("".join(line + "\n" for line in lines))
        stream.flush()
        return
    sleep = sleep or time.sleep
    delay = min(0.04, limit / len(lines))
    done = False
    try:
        for line in lines:
            stream.write(line + "\n")
            stream.flush()
            sleep(delay)
        done = True
    except OSError:                  # терминал закрылся посреди анимации — молча дальше
        pass
    finally:
        _finish(stream, c, done)


def rain(width: int, c: Caps = None, stream=None, sleep=None, rows: int = 5,
         limit: float = RAIN_LIMIT, seed: Optional[int] = None) -> None:
    """Дождь кода: rows коротких строк «капель» шириной ≤ width; без anim — ничего."""
    c = c or caps()
    if not c.anim or width < 8:
        return
    stream = stream or sys.stdout
    sleep = sleep or time.sleep
    rng = random.Random(seed)
    cols = rng.sample(range(2, width - 1), max(4, width // 6))
    drops = {x: (rng.randrange(rows), rng.randint(1, 3)) for x in cols}
    delay = min(0.12, limit / rows)
    done = False
    try:
        for r in range(rows):
            cells = [" "] * width
            for x, (start, length) in drops.items():
                if start <= r < start + length:
                    head = r == min(rows, start + length) - 1
                    cells[x] = style(rng.choice(RAIN), "ok" if head else "dim", c=c)
            stream.write("".join(cells).rstrip() + "\n")
            stream.flush()
            sleep(delay)
        done = True
    except OSError:                  # терминал закрылся посреди анимации — молча дальше
        pass
    finally:
        _finish(stream, c, done)
