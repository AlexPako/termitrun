"""Трек «Базы данных» (часть 9а, «Картотека»): поручения на встроенном /usr/bin/sqlite3.

Данные и сборка базы — tasks/dbkit.py (ответ считает Python-предикат по строкам генератора),
чтение копии базы при проверке — termit_app/dbread.py (задачи «сделай», A4). Порядок в TASKS
— порядок обучения. Все задачи со скрытым ответом (AnswerTask.secret_keys): вердикт считает
судья у родителя, в песочнице ответа нет.

Отклики новичку — только по ФОРМЕ сделанного, без оракула ответа: пустой *.db рядом (опечатка
в имени — sqlite3 молча завёл новую базу), запрос без двойных кавычек, строка в двойных
кавычках внутри запроса, «ans sqlite3 …» вместо вывода. Незакрытая «;» и повисшее sqlite> —
в карточках и уроках: интерактив sqlite3 хук не видит."""
import contextvars
import math
import re
import shlex
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

from termit_app import dbread, sandbox, textnorm
from termit_app.tasks import base, dbkit, kit
from termit_app.tasks.base import AnswerTask, Variant, Verdict

DB = "records.db"

MSG_EMPTY_DB = ("Файла {name} не было — sqlite3 молча завёл новую пустую базу с этим именем. "
                "Опечатка? ls *.db покажет, как зовут настоящую.")
MSG_UNQUOTED = ("Запрос бери целиком в двойные кавычки: sqlite3 файл.db \"SELECT …\". Без них "
                "zsh режет его на слова, а * пробует раскрыть в имена файлов.")
MSG_DQ_VALUE = ("Строки внутри запроса — в одинарных кавычках: city = 'значение'. Двойные уже "
                "держат весь запрос, вторая пара его разрывает.")
MSG_CMD_ANSWER = ("Сдаётся не команда, а то, что она напечатала: запусти запрос, потом ans и "
                  "его вывод (или ans $(sqlite3 …)).")
MSG_MANY_ROWS = ("Запрос вернул несколько строк — условию подходят несколько человек. Сдай "
                 "одно значение, а условие уточни ещё одним: AND …")
MSG_EMPTY_TABLES = ("0 таблиц — значит, открыта пустая база: sqlite3 завёл новую по опечатке в "
                    "имени. Проверь ls.")

MSG_LIST_NOT_COUNT = ("Нужно число, а это сами строки вывода — спрашивали, сколько их. "
                      "Сосчитай: | wc -l после закрывающей кавычки.")
MSG_AGG_WHERE = ("COUNT, SUM и AVG в WHERE не бывают — sqlite3 ответит misuse of aggregate. "
                 "WHERE отбирает строки до группировки, условие на группу — HAVING после GROUP BY.")
MSG_COUNT_NULLS = ("COUNT(графа) пропускает NULL — среди одних NULL он всегда 0. Считай строки: "
                   "COUNT(*).")
MSG_EQ_NULL = ("= NULL не бывает истинным никогда: NULL — это «не знаю». Проверка — IS NULL "
               "(или IS NOT NULL).")

MSG_BARE_WORD = ("{word} без кавычек sqlite3 принял за имя графы — отсюда no such column. "
                 "Строки — целиком в одинарных кавычках: = '{word}'.")
MSG_BARE_IN = ("{word} без кавычек sqlite3 принял за имя графы — отсюда no such column. Каждое "
               "значение списка — в одинарных кавычках: IN ({fixed}).")
MSG_BARE_DATE = ("Дата без кавычек для sqlite3 — вычитание: {date} он считает как число. Даты "
                 "здесь — строки, в одинарных кавычках: '{date}'.")
MSG_SUB_TWO = ("Подзапрос в IN даёт один список — значит, одну графу: IN (SELECT from_acc FROM "
               "…). Две графы — два условия: … NOT IN (SELECT a …) AND … NOT IN (SELECT b …).")
MSG_QUERY_EMPTY = ("Пусто: запрос ничего не вернул или упал. Запусти его без ans и посмотри: "
                   "ошибку sqlite3 печатает сам (Error или Parse error — причина в ней); "
                   "ошибки нет — условие не нашло ни одной строки.")
MSG_QUERY_ZERO = ("Ноль: запрос ничего не нашёл — или упал, а | wc -l от пустоты тоже 0. "
                  "Запусти его без ans и без счёта и посмотри, что печатает sqlite3.")
MSG_PIPE_INSIDE = ("| {cmd} попал внутрь кавычек — sqlite3 принял его за часть запроса (near "
                   "\"|\": syntax error). Труба — команда zsh: ставь её после закрывающей "
                   "кавычки: sqlite3 records.db \"SELECT …\" | {cmd}.")
MSG_CSV_AS_DB = ("{name} — не база, а CSV: sqlite3 откроет его как базу и скажет file is not a "
                 "database. CSV сначала загружают: sqlite3 :memory: -cmd \".import --csv {name} "
                 "t\" \"SELECT … FROM t\".")
MSG_NO_TABLE = ("Таблицы {name} в этой базе нет — sqlite3 скажет no such table. Какие есть, "
                "покажет sqlite3 {db} \".tables\"; таблицы из примеров урока — только примеры.")
MSG_DOT_UNQUOTED = ("Точечную команду бери в кавычки вместе с её словами: sqlite3 {db} "
                    "\"{example}\". Без кавычек zsh отдаёт слова по одному, и {word} sqlite3 "
                    "принял за запрос.")
MSG_BACKUP_NO_DIR = ("Папки {dir} нет — .backup её не создаёт (cannot open). Сначала mkdir -p "
                     "{dir}, потом копия.")
MSG_AND_OR = ("AND сильнее OR: a AND b OR c — это (a AND b) OR c, второе условие OR берёт "
              "строки мимо остальных. Нужен «a и (b или c)» — ставь скобки: a AND (b OR c).")

_KNOWN_NAMES = ({c for cols in dbkit.COLUMNS.values() for c in cols} | set(dbkit.COLUMNS)
                | {c for cols in dbkit.EXTRA_COLUMNS.values() for c in cols}
                | {"n", "total", "NULL", "null", "place", "minutes", "reason", "title", "color",
                   "body", "date", "customer", "amount", "t"})
_EXTRA_NAMES = contextvars.ContextVar("termit_sql_names", default=frozenset())


@contextmanager
def known_names(names) -> Iterator[None]:
    """На время блока — ещё и эти графы и псевдонимы (Хранилище, 9б B3: другая база): справа
    от = они не «строка без кавычек». Только в этом потоке; Картотеку не задевает."""
    token = _EXTRA_NAMES.set(frozenset(names))
    try:
        yield
    finally:
        _EXTRA_NAMES.reset(token)


_SQ_LITERAL = re.compile(r"'[^']*'")
_COMMON_FORMS = (
    (re.compile(r"\bWHERE\b(?:(?!\bGROUP\s+BY\b|\bHAVING\b|\bORDER\s+BY\b)[^\"])*?"
                r"\b(?:COUNT|SUM|AVG|MIN|MAX)\s*\(", re.I), MSG_AGG_WHERE),
    (re.compile(r"(?:=|<>)\s*NULL\b", re.I), MSG_EQ_NULL),
    (re.compile(r"\bCOUNT\(\s*(?:\w+\.)?(\w+)\s*\)[^\"]*\bWHERE\b[^\"]*?(?:\w+\.)?\1\s+IS\s+NULL",
                re.I), MSG_COUNT_NULLS),
)

_UNQUOTED_SQL = {w.lower() for w in ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "FROM",
                                     "WHERE")}
# строка в двойных кавычках внутри запроса — и из двух слов («"Nina Novikov"», аудит A7 п. 6)
_DQ_VALUE = re.compile(r"(?:=|<>|\bLIKE|\blike|\bIN\s*\(|,)\s*\"[^\"]*\"")


_SUBQUERY = re.compile(r"\(\s*SELECT\b[^()]*(?:\([^()]*\)[^()]*)*\)", re.I)


def _drop_subqueries(body: str) -> str:
    """Подзапросы «(SELECT …)» (до одного уровня вложенных скобок внутри) — заменить на ()."""
    prev = None
    while prev != body:
        prev, body = body, _SUBQUERY.sub("()", body)
    return body


MSG_BARE_VALUES = ("{word} в VALUES без кавычек sqlite3 принял за имя графы — отсюда no such "
                   "column. Текст — целиком в одинарных кавычках: '{word}'.")
_VALUES = re.compile(r"\bVALUES\b(.*)", re.I | re.S)
# конец значения справа от = / <>: следующее слово SQL, скобка, запятая, «;» или кавычка
_VALUE_END = re.compile(r"\s+(?:AND|OR|ORDER|GROUP|LIMIT|HAVING|WHERE|JOIN|LEFT|INNER|ON|SET|"
                        r"THEN|ELSE|END|WHEN|UNION|OFFSET|BETWEEN|IS|NOT|IN|LIKE|DESC|ASC)\b"
                        r"|[;(),\"]|$", re.I)
_DATE = re.compile(r"(?<![\w'./-])(\d{4}-\d{2}-\d{2})(?![\w'./-])")
_SUB_TWO = re.compile(r"\w\s+(?:NOT\s+)?IN\s*\(\s*SELECT\s+(?:DISTINCT\s+)?[^()]*?,[^()]*?"
                      r"\bFROM\b", re.I)


def _is_name(word: str) -> bool:
    """Графа, таблица, псевдоним.графа, число или слово SQL — не строка без кавычек."""
    w = word.strip()
    if not w or textnorm.as_number(w) is not None or w.upper() in lint_kw():
        return True
    if "@" in w:
        return False
    known = _KNOWN_NAMES | _EXTRA_NAMES.get()
    if re.fullmatch(r"[A-Za-z_]\w*\.[A-Za-z_]\w*", w):     # p.city, a.id — графа с псевдонимом
        return w.split(".")[1] in known
    return w in known


def _bare_value(sql: str) -> Optional[str]:
    """Первое значение без кавычек справа от = / <> — целиком (два слова, почта с @ и
    точкой). Функция «x(» и выражение с числом — не значение."""
    for m in re.finditer(r"(?:=|<>)\s*", sql):
        rest = sql[m.end():]
        if not rest[:1] or not (rest[0].isalpha() or rest[0] == "_"):
            continue
        end = _VALUE_END.search(rest)
        value = rest[:end.start()].strip()
        if rest[end.start():end.start() + 1] == "(" and " " not in value:
            continue                                        # COUNT( … ) — функция
        if value and re.fullmatch(r"[\w.@+-]+(?: [\w.@+-]+)*", value) and not all(
                _is_name(w) for w in value.split()):
            return value
    return None


def _bare_in(sql: str) -> Optional[tuple]:
    """Список IN (…) со словом без кавычек: (слово, список целиком в кавычках)."""
    for m in re.finditer(r"\bIN\s*\(([^()]*)\)", sql, re.I):
        items = [x.strip() for x in m.group(1).split(",") if x.strip()]
        bare = [x for x in items if x[:1] != "'" and not _is_name(x)]
        if bare:
            fixed = ", ".join(x if x[:1] == "'" or _is_name(x) else f"'{x}'" for x in items)
            return bare[0], fixed
    return None


def _bare_in_values(sql: str) -> Optional[str]:
    """Значение VALUES (…) без кавычек — целиком: N-802, call back."""
    vals = _VALUES.search(sql)
    if not vals:
        return None
    for tup in re.findall(r"\(([^()]*)\)", vals.group(1).split(";")[0]):
        for x in (x.strip() for x in tup.split(",")):
            if x and x[:1] != "'" and re.search(r"[A-Za-z]", x) and not all(
                    _is_name(w) for w in x.split()):
                return x
    return None


MSG_SQL_PLACEHOLDER = ("{word} — место для номера из подсказки, а не значение: подставь "
                       "настоящий id (его покажет SELECT … ORDER BY id DESC LIMIT 3), без "
                       "кавычек.")
# другие заглушки подсказок (B5, страж Хранилища: <id>, <минус долг>) — без совета про журнал
MSG_SQL_PLACEHOLDER_ANY = ("{word} — место из подсказки, а не значение: подставь туда настоящее "
                           "число (его даёт твой же запрос), без кавычек и без < >.")
# заглушка подсказки, набранная буквально: <номер> или одиночная N / M (финал M3)
# (B5: и после > — «id > <номер>» в подсказке стража Хранилища)
_SQL_PLACEHOLDER = re.compile(r"(?:=|>|\bIN\s*\(|,)\s*(<[^<>'\"]+>|[NM])(?![\w.(])")


def common_form_hint(line: str) -> Optional[str]:
    """Ошибка в самой форме запроса (она неверна всегда): агрегат в WHERE, = NULL, COUNT(графа)
    … IS NULL, строка без кавычек после =, в IN (…) или в VALUES (значение — целиком), дата
    без кавычек, подзапрос с двумя графами в IN. Подзапрос «(SELECT AVG(…) …)» — законное
    место агрегата (A3 M3): его тело не смотрим. Ответ здесь не нужен."""
    lit = _SQ_LITERAL.sub("''", line)
    if _SUB_TWO.search(lit):
        return MSG_SUB_TWO
    body = _drop_subqueries(lit)
    for rx, msg in _COMMON_FORMS:
        if rx.search(body):
            return msg
    sql = body.split('"', 1)[1] if '"' in body else ""
    # заглушки — только внутри SQL в кавычках: «… " > N» — перенаправление в файл (ревью B5, M2)
    ph = _SQL_PLACEHOLDER.search(" ".join(re.findall(r'"([^"]*)"', body)))
    if ph:
        if ph.group(1) in ("<номер>", "N", "M"):
            return MSG_SQL_PLACEHOLDER.format(word=ph.group(1))
        return MSG_SQL_PLACEHOLDER_ANY.format(word=ph.group(1))
    date = _DATE.search(sql)
    if date:
        return MSG_BARE_DATE.format(date=date.group(1))
    word = _bare_value(sql)
    if word:
        return MSG_BARE_WORD.format(word=word)
    raw = _drop_subqueries(line)
    hit = _bare_in(raw.split('"', 1)[1] if '"' in raw else "")
    if hit:
        return MSG_BARE_IN.format(word=hit[0], fixed=hit[1])
    word = _bare_in_values(sql)
    if word:
        return MSG_BARE_VALUES.format(word=word)
    return None


def same_num(given, expected) -> bool:
    """Число как ответ (fix A3 M1): дробное — с допуском полкопейки (0.005): ROUND(…, 2) и
    неокруглённое среднее засчитаны, соседнее 0.01 — нет (textnorm.same_number берёт < 0.01,
    и по погрешности float сосед иногда проходил). Целое — как textnorm.same_number."""
    g = textnorm.as_number(str(given))
    if g is None or not math.isfinite(g):       # inf, nan, 1e400 — не число ответа (финал M1)
        return False
    e = float(expected)
    if e != int(e) or g != int(g):
        return abs(g - e) <= 0.005 + 1e-9
    return textnorm.same_number(str(given), expected)


def same_parts_num(given, want) -> bool:
    """Ответ из частей (порядок любой, регистр не важен): часть-число равна части-числу по
    same_num (A7: «472 75560.0» = «472 75560», соседнее число — нет), слово — слову. Частей
    ровно столько же: лишняя или недостающая часть — не ответ (fix1 I1)."""
    got = textnorm.parts(given)
    want = [str(w) for w in want]
    if not want or len(got) != len(want):
        return False
    left = list(got)
    # сначала слова и точные совпадения, потом числа с допуском
    for w in sorted(want, key=lambda x: textnorm.as_number(x) is not None):
        hit = next((g for g in left if g == w.casefold()), None)
        if hit is None and textnorm.as_number(w) is not None:
            hit = next((g for g in left if textnorm.as_number(g) is not None
                        and same_num(g, w)), None)
        if hit is None:
            return False
        left.remove(hit)
    return True


def lint_kw():
    """Ключевые слова SQL (NULL, TRUE…) — не «строка без кавычек»."""
    from termit_app.tasks import lint
    return lint.SQL_KEYWORDS


def _last_line(ctx) -> str:
    return ctx.cmds[-1].line if ctx.cmds else ""


def _last_sql(ctx) -> str:
    """Последняя команда с sqlite3 (в том числе ans $(sqlite3 …))."""
    for c in reversed(ctx.cmds or ()):
        if "sqlite3" in c.line:
            return c.line
    return ""


def _empty_dbs(box) -> List[str]:
    """Пустые *.db в корне песочницы (sqlite3 создаёт файл при открытии несуществующего)."""
    import os
    out = []
    for name in sandbox.files_in_box(box, ".") or ():
        if not name.endswith(".db") or name == DB:
            continue
        fd = sandbox.open_in_box(box, name, 1 << 20)
        if fd is None:
            continue
        try:
            if os.fstat(fd).st_size == 0:
                out.append(name)
        finally:
            os.close(fd)
    return sorted(out)


def shape_hint(ctx) -> Optional[str]:
    """Отклик по форме последней команды sqlite3 (или None): только что видно на экране и в
    файлах песочницы — без сравнения с ответом."""
    return line_shape(ctx.box, _last_line(ctx))


# ключи sqlite3 со своим значением следом (-cmd ".import …", -separator ,)
_SQLITE_ARG_OPTS = {"-cmd", "-separator", "-newline", "-nullvalue", "-init"}
_DOT_WITH_ARGS = re.compile(r"(?:^|\s)\.(schema|import|backup|output|once|mode|headers|read)"
                            r"\s+([^\s\"'|;&>]+)")
_PIPE_INSIDE = re.compile(r"(?<!\|)\|\s*(wc|grep|sort|head|tail|uniq|cut)\b(?:\s+-\w+)?")
_TABLE_REF = re.compile(r"\b(FROM|JOIN|INTO|UPDATE)\s+([A-Za-z_]\w*)\b(\s*\()?", re.I)
_SYSTEM_TABLES = {"sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_sequence"}


def _db_arg(words) -> Optional[str]:
    """Файл базы в команде sqlite3: первое слово после ключей (у -cmd и др. — своё значение)."""
    i = 1
    while i < len(words):
        w = words[i]
        if w in _SQLITE_ARG_OPTS:
            i += 2
            continue
        if w.startswith("-"):
            i += 1
            continue
        return w
    return None


def _missing_table(box, line: str, words, db: Optional[str]) -> Optional[str]:
    """Таблица из FROM/JOIN/INTO/UPDATE, которой нет в базе команды (A7 п. 8: staff, orders
    из примеров урока). Свои CREATE TABLE/VIEW, .import и WITH той же строки — не в счёт."""
    sql = _SQ_LITERAL.sub("''", " ".join(words[1:]))
    refs = []
    for m in _TABLE_REF.finditer(sql):
        kind, name = m.group(1).upper(), m.group(2)
        if kind in ("FROM", "JOIN") and m.group(3):
            continue                                # pragma_table_info(…) — функция
        if name.upper() in lint_kw() or name.upper() == "OF" or name.lower() in _SYSTEM_TABLES:
            continue                                # UPDATE OF city — графа правила (финал M2)
        refs.append(name)
    if not refs:
        return None
    made = {n.lower() for n in re.findall(r"\bCREATE\s+(?:TEMP\s+)?(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+"
                                          r"EXISTS\s+)?([A-Za-z_]\w*)", sql, re.I)}
    made |= {n.lower() for n in re.findall(r"\.import\s+(?:--\w+\s+(?:\d+\s+)?)*\S+\s+(\w+)",
                                           sql)}
    made |= {n.lower() for n in re.findall(r"\b([A-Za-z_]\w*)\s+AS\s*\(", sql, re.I)}
    if db == ":memory:" or db is None:
        have = set()
    else:
        if not _exists(box, db):
            return None
        try:
            with dbread.SqliteSnapshot(box, db) as snap:
                have = set(snap.tables()) | {v.lower() for v in snap.views()}
        except dbread.Broken:
            return None
    for name in refs:
        if name.lower() not in have | made:
            return MSG_NO_TABLE.format(name=name, db=db or DB)
    return None


def line_shape(box, line: str) -> Optional[str]:
    """То же по строке команды: sqlite3 — первое слово (или начало подстановки $(sqlite3 …)
    в ans — тогда берём хвост с него)."""
    if not line.startswith("sqlite3") and "$(sqlite3" in line:
        line = line[line.index("$(sqlite3") + 2:]
    try:
        words = shlex.split(line)
    except ValueError:
        words = line.split()
    if not words or words[0] != "sqlite3":
        return None
    for name in _empty_dbs(box):
        if name in words or any(w.endswith("/" + name) for w in words):
            return MSG_EMPTY_DB.format(name=name)
    if any(w.lower() in _UNQUOTED_SQL for w in words[1:]):
        return MSG_UNQUOTED
    if _DQ_VALUE.search(line.split('"', 1)[1] if '"' in line else ""):
        return MSG_DQ_VALUE
    db = _db_arg(words)
    if db and db.lower().endswith(".csv"):
        return MSG_CSV_AS_DB.format(name=db)
    quoted = re.findall(r'"([^"]*)"', line)
    for body in quoted:
        m = _PIPE_INSIDE.search(_SQ_LITERAL.sub("''", body))
        if m:
            return MSG_PIPE_INSIDE.format(cmd=m.group(0).lstrip("| ").strip())
    blank = re.sub(r'"[^"]*"', lambda m: '"' + " " * (len(m.group(0)) - 2) + '"', line)
    unq = _DOT_WITH_ARGS.search(blank)
    if unq:
        word = unq.group(2)
        rest = line[unq.start():].split()
        example = " ".join(rest[:2 if unq.group(1) != "import" else 4]).strip()
        return MSG_DOT_UNQUOTED.format(db=db or DB, example=example, word=word)
    for m in re.finditer(r"\.backup\s+(?:--\w+\s+)?(\S+?)[\"\s]", line + " "):
        path = m.group(1).strip("'\"")
        if "/" in path and not _exists(box, path):
            folder = path.rsplit("/", 1)[0]
            if folder and sandbox.files_in_box(box, folder) is None:
                return MSG_BACKUP_NO_DIR.format(dir=folder)
    return _missing_table(box, line, words, db)


MSG_PARTS_EXTRA = ("Лишнее в ответе: задание просит {form} — оставь в SELECT только эти графы "
                   "и проверь, что строк столько, сколько нужно.")
MSG_PARTS_MISSING = "Ответ неполный: задание просит {form} — сдай всё это через пробел."
MSG_NEED_ID = ("Нужен только id — номер, без даты и других граф: оставь в SELECT одну графу "
               "id.")
_FORM = re.compile(r"Ответ:\s*ans\s+(.+?)\s*$")


def _and_or(line: str) -> bool:
    """AND и OR на одном уровне, без скобок (BETWEEN a AND b — не в счёт)."""
    body = _drop_subqueries(_SQ_LITERAL.sub("''", line))
    body = body.split('"', 1)[1] if '"' in body else ""
    body = re.sub(r"\bBETWEEN\s+\S+\s+AND\s+\S+", " ", body, flags=re.I)
    prev = None
    while prev != body:
        prev, body = body, re.sub(r"\([^()]*\)", " ", body)
    return bool(re.search(r"\bOR\b", body, re.I) and re.search(r"\bAND\b", body, re.I))


class _DbAnswer(AnswerTask):
    """«Найди в базе и назови»: число, текст или несколько частей в любом порядке
    (вывод sqlite3 «kazan|57» тоже годится; часть-число — как число: 75560.0 = 75560).
    Ловушки — state["traps"]: [ключ, значение], значение — число, строка или список частей;
    оно названо, если сданное по частям ему равно. Итоги без GROUP BY — state["totals"].
    Пустой вывод и 0 — отклик по форме последнего запроса (form_hint, line_shape,
    empty_hint), а не ловушка: ноль от другой ошибки чужой ловушкой не объясняем (A7)."""
    track = "db"
    trap_messages = {}
    fallback = "Мимо. Глянь запрос ещё раз: та ли таблица, колонка, условие? Застрял — hint."
    # totals — итоги «без GROUP BY» (total_message): у родителя, как ответ и ловушки (A3 M2)
    secret_keys = AnswerTask.secret_keys + ("totals",)

    def expected(self, state: dict) -> str:
        exp = state["answer"]
        return " ".join(map(str, exp)) if isinstance(exp, list) else str(exp)

    def answer_kind(self, state: dict) -> str:
        exp = state["answer"]
        return ("number" if isinstance(exp, (int, float)) and not isinstance(exp, bool)
                else "text")

    def matches(self, given, ctx):
        exp = ctx.state["answer"]
        if isinstance(exp, list):       # часть из двух слов («Anna Orlov») — тоже по словам
            return same_parts_num(given, textnorm.parts(" ".join(map(str, exp))))
        if self.answer_kind(ctx.state) == "number":
            return same_num(given, exp)
        return textnorm.same_text(given, str(exp)) or textnorm.same_words(given, str(exp))

    def trap_message(self, given, ctx):
        """Ловушка — только если сданное по частям РАВНО её значению (fix1 I1: подмножество
        выдавало ответ перебором «все кандидаты разом»). Подписи вокруг значения («ID 427»,
        «телефон: …») прощаются, только если они другого вида, чем части ответа (base._shape):
        слово при числовом ответе, число при словесном — нет. Числа — как числа (A7).
        Остальное — common_mistake."""
        st = ctx.state
        kinds = {base._shape(w) for w in textnorm.parts(self.expected(st))}
        got = " ".join(w for w in textnorm.parts(given) if base._shape(w) in kinds)
        for key, value in st.get("traps") or ():
            if key not in self.trap_messages:
                continue
            want = textnorm.parts(" ".join(map(str, value)) if isinstance(value, list)
                                  else str(value))
            if want and same_parts_num(got, want):
                return self.trap_messages[key].format(**st)
        return self.total_message(given, ctx)

    def total_message(self, given, ctx):
        """Итог по всей таблице (state["totals"]: [ключ, число]) — так выглядит агрегат без
        GROUP BY: одна строка на всё. Срабатывает, если среди сданного (частей не больше, чем
        в ответе) есть это число; оно ответом не бывает — об ответе отклик ничего не говорит."""
        st = ctx.state
        got = textnorm.parts(given)
        if not got or len(got) > len(textnorm.parts(self.expected(st))):
            return None
        for key, value in st.get("totals") or ():
            if key in self.trap_messages and any(
                    textnorm.as_number(w) is not None and textnorm.same_number(w, value)
                    for w in got):
                return self.trap_messages[key].format(**st)
        return None

    def empty_hint(self, line: str) -> Optional[str]:
        """Отклик на ПУСТОЙ вывод или 0 по форме запроса (ничего не нашлось — почему так
        бывает). Только по форме: ноль от другой ошибки чужой ловушкой не объясняем."""
        return None

    def form_hint(self, line: str) -> Optional[str]:
        """Отклик по форме запроса, без сравнения с ответом: и после команды без ans, и когда
        сдан пустой вывод или 0 (запрос упал или ничего не нашёл). Подзапрос в скобках
        «(SELECT AVG(…) …)» — законное место агрегата (A3 M3): его тело не смотрим."""
        return common_form_hint(line)

    def _form(self, st) -> Optional[str]:
        """Что просит задание после «Ответ: ans» — NAME CITY, ID ID ID (по тексту варианта)."""
        m = _FORM.search(self._task_text(st))
        return m.group(1).rstrip(".") if m else None

    def wrong_message(self, given, ctx):
        g = textnorm.clean(given)
        if g.split()[:1] == ["sqlite3"]:
            return MSG_CMD_ANSWER
        line = _last_sql(ctx)
        # ошибка в самой форме запроса (агрегат в WHERE, = NULL, строка без кавычек…) неверна
        # всегда — её объяснение надёжнее ловушки, совпавшей по значению
        hint = self.form_hint(line)
        if hint:
            return hint
        zero = len(textnorm.parts(g)) == 1 and textnorm.as_number(g) == 0
        if not g or zero:   # пусто или 0 (| wc -l от пустого): запрос упал или ничего не нашёл
            hint = line_shape(ctx.box, line) or self.empty_hint(line)
            if hint:
                return hint
            if not g and "sqlite3" in _last_line(ctx):      # сдан вывод именно этого запроса
                return MSG_QUERY_EMPTY
            if zero and line:
                return MSG_QUERY_ZERO
        trap = self.trap_message(given, ctx)
        if trap:
            return trap
        common = self.common_mistake(given, ctx)
        st = ctx.state
        form = self._form(st)
        want = textnorm.parts(self.expected(st))
        if common == base.MSG_NOT_NUMBER:
            if re.search(r"\bсколь", self._task_text(st), re.I):    # сколько, в скольких
                return MSG_LIST_NOT_COUNT   # слова без чисел — строки вывода, их не сосчитали
            if form == "ID":
                return MSG_NEED_ID
        if form and len(want) > 1 and common in (base.MSG_ONE, base.MSG_EXTRA):
            return MSG_PARTS_EXTRA.format(form=form)
        if form and common == base.MSG_PARTIAL.format(n=len(want)):
            return MSG_PARTS_MISSING.format(form=form)
        if common:
            return common
        if line and _and_or(line):
            return MSG_AND_OR
        return self.fallback.format(**st)

    def check(self, ctx):
        v = super().check(ctx)
        if v.solved or v.message or ctx.answer is not None:
            return v
        hint = shape_hint(ctx)
        if not hint and "sqlite3" in _last_line(ctx):
            hint = self.form_hint(_last_line(ctx))
        return Verdict(False, hint) if hint else v


class _RecordsAnswer(_DbAnswer):
    """Задачи на records.db (A3): данные варианта — чистая функция data_state(rng, recs,
    variant) -> state без песочницы. Её же гоняет гарантия «единственного ответа» на 2000
    зёрнах (tests/test_db_traps.py): ответ не совпадает ни с одной ловушкой, у лидера запас."""

    def data_state(self, rng, recs: dbkit.Records, variant: int) -> dict:
        raise NotImplementedError

    def setup_variant(self, box, rng, variant):
        recs = dbkit.records(rng)
        st = self.data_state(rng, recs, variant)
        dbkit.put(box, DB, recs.sqlite())
        return dict(st, sources=_sources(box))


def _put_records(box, rng, **kw) -> dbkit.Records:
    recs = dbkit.records(rng, **kw)
    dbkit.put(box, DB, recs.sqlite())
    return recs


def _sources(box) -> dict:
    return base.sources(box, DB)


# --- 1. sqlite_open --------------------------------------------------------------------------

# что хранит таблица — по одной её особой колонке (вариант C)
_WHAT = {"people": ("даты рождения людей", "born"), "accounts": ("балансы счетов", "balance"),
         "transfers": ("суммы переводов", "amount"), "badges": ("коды пропусков", "code"),
         "audit_log": ("кто правил записи (исполнитель правки)", "actor"),
         "districts": ("начальники районов", "chief"), "offices": ("адреса контор", "address"),
         "forms": ("подписи бланков", "caption")}
_COUNT_TABLES = "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
_TABLE_OF = ("SELECT m.name FROM sqlite_master m, pragma_table_info(m.name) p "
             "WHERE m.type = 'table' AND p.name = '{col}'")


class SqliteOpen(_DbAnswer):
    """База, таблица, строка, колонка: .tables, .schema, sqlite3 без захода внутрь."""
    id = "sqlite_open"
    title = "Первая база"
    par = 45
    scroll = ("sqlite3 records.db — открыть базу (sqlite>): .tables — таблицы, .schema people — "
              "колонки. Выход — .quit или Ctrl+D, повисло — Ctrl+C.\n"
              "Без захода: sqlite3 records.db \".tables\". Нет файла — sqlite3 молча заведёт пустую базу: "
              "сначала ls.\n"
              "Застрял на ...> (нет ;) — ; и Enter или Ctrl+D. ans и hint в sqlite> не работают.")
    variants = (
        # FB12 (N21): первая задача места — один вопрос (сколько таблиц); колонки (.schema)
        # — повторы 1 и 2
        Variant("В папке — учебная база records.db. Сколько в ней таблиц? Ответ: ans NUMBER",
                hints=("Таблицы перечислит .tables — прямо из оболочки, без захода в базу.",
                       "sqlite3 records.db \".tables\" печатает имена таблиц — пересчитай их.",
                       "sqlite3 records.db \".tables\" — и сдай число имён: ans NUMBER"),
                solution='sqlite3 records.db ".tables"',
                solution_script='sqlite3 records.db "' + _COUNT_TABLES + '"',
                wrong=('sqlite3 record.db ".tables" | wc -w',),
                alternatives=("sqlite3 records.db, а внутри .tables и .quit — то же изнутри",
                              "| wc -w после .tables — пересчитать имена командой: wc -w "
                              "считает слова")),
        Variant("Сколько колонок в таблице {table} базы records.db? Ответ: ans NUMBER",
                hints=("Колонки таблицы показывает .schema с её именем.",
                       "В скобках после CREATE TABLE {table} — колонки через запятую.",
                       "sqlite3 records.db \".schema {table}\""),
                solution='sqlite3 records.db ".schema {table}"',
                solution_script="sqlite3 records.db \"SELECT COUNT(*) FROM "
                                "pragma_table_info('{table}')\"",
                wrong=('sqlite3 records.db "SELECT COUNT(*) FROM {table}"',
                       'sqlite3 record.db ".tables" | wc -w'),
                alternatives=("sqlite3 records.db, а внутри .headers on, затем SELECT * FROM {table} "
                              "LIMIT 1; — шапка и есть колонки",)),
        Variant("В учебной базе records.db где-то хранятся {what}. В какой таблице? Ответ: "
                "ans ТАБЛИЦА",
                hints=(".schema покажет все таблицы с их колонками.",
                       "Найди колонку {col}: таблица — та, что после CREATE TABLE.",
                       "sqlite3 records.db \".schema\""),
                solution='sqlite3 records.db ".schema"',
                solution_script='sqlite3 records.db "' + _TABLE_OF + '"',
                wrong=("print -r -- {col}", 'sqlite3 record.db ".tables" | wc -w'),
                alternatives=("sqlite3 records.db \".tables\" — имена, затем .schema NAME по "
                              "одной",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("База — файл с таблицами; таблица — строки (записи) и колонки (графы). Не знаешь, "
               "что внутри, — не гадай: .tables и .schema покажут всё ещё до первого запроса.")
    spell = ("sqlite3 файл.db — открыть; .tables — таблицы; .schema т — колонки; .quit — "
             "выйти; sqlite3 файл.db \".tables\" — без захода")
    trap_messages = {
        "rows": "Это число строк таблицы, а нужны колонки — смотри .schema {table}.",
        "column": "Это колонка, а спрашивали таблицу — её имя стоит после CREATE TABLE.",
    }
    # goal — таблица-ответ (варианты A и C): нужна неверным решениям, в task.json её нет
    secret_keys = _DbAnswer.secret_keys + ("goal",)

    def wrong_message(self, given, ctx):
        nums = [w for w in textnorm.parts(given) if textnorm.as_number(w) is not None]
        if nums and all(textnorm.as_number(w) == 0 for w in nums) and len(nums) == 1:
            return MSG_EMPTY_TABLES             # таблиц и колонок здесь всегда не меньше трёх
        return super().wrong_message(given, ctx)

    def setup_variant(self, box, rng, variant):
        data, names = dbkit.catalog(rng)
        dbkit.put(box, DB, data)
        cols = {t: dbkit.table_columns(t) for t in names}
        # fix1 M1: .schema печатает и триггер (графы people и audit_log рядом с ON people) —
        # колонку-примету из его текста не берём
        busy = (set(re.findall(r"[a-z_]+", dbkit.SCHEMA[-1]))
                if {"people", "audit_log"} <= set(names) else set())
        st = {"sources": _sources(box)}
        if variant == 1:
            rows = _catalog_rows(data, names)
            fit = [t for t in names if rows[t] != len(cols[t])]
            t = rng.choice(fit)
            return dict(st, table=t, answer=len(cols[t]),
                        traps=[["rows", rows[t]]])
        if variant == 2:            # особая колонка — только у этой таблицы (code есть и у forms)
            t = rng.choice([x for x in names if _WHAT[x][1] not in busy
                            and sum(_WHAT[x][1] in cols[y] for y in names) == 1])
            what, col = _WHAT[t]
            return dict(st, goal=t, what=what, col=col, answer=t, traps=[["column", col]])
        return dict(st, answer=len(names), traps=[])


def _catalog_rows(data: bytes, names) -> dict:
    """Строк в каждой таблице первой базы — из её же байтов (временная копия)."""
    import os
    import shutil
    import sqlite3
    import tempfile
    tmp = tempfile.mkdtemp(prefix="termit-dbcount-")
    try:
        path = os.path.join(tmp, "c.db")
        with open(path, "wb") as f:
            f.write(data)
        con = sqlite3.connect(path)
        try:
            return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in names}
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 2. select_where -------------------------------------------------------------------------

class SelectWhere(_DbAnswer):
    """SELECT … FROM … WHERE: =, <>, AND; строки — в одинарных, запрос — в двойных."""
    id = "select_where"
    title = "Найти человека"
    par = 50
    scroll = ("sqlite3 records.db \"SELECT name FROM people WHERE city = 'город'\" — запрос "
              "без захода внутрь: весь он в двойных кавычках, строки в нём — в одинарных.\n"
              "SELECT колонки FROM таблица WHERE условие; = — равно, <> — не равно, AND — оба "
              "условия сразу.\n"
              "Внутри sqlite> запрос кончается ; — без неё приглашение станет ...> и ждёт: "
              "допиши ; и Enter (или Ctrl+D). ans и hint — только снаружи sqlite>.")
    variants = (
        Variant("В учебной базе records.db есть тёзки. Какой телефон у {name} из города {city}? "
                "Ответ: ans ТЕЛЕФОН",
                hints=("Нужна колонка phone таблицы people, условие — по имени и городу.",
                       "Два условия сразу: WHERE name = '…' AND city = '…', строки — в одинарных "
                       "кавычках.",
                       "sqlite3 records.db \"SELECT phone FROM people WHERE name = '{name}' AND "
                       "city = '{city}'\""),
                solution="sqlite3 records.db \"SELECT phone FROM people WHERE name = '{name}' "
                         "AND city = '{city}'\"",
                wrong=("sqlite3 records.db \"SELECT phone FROM people WHERE name = '{name}'\"",
                       "sqlite3 records.db \"SELECT phone FROM people WHERE name = '{name}' AND "
                       "city <> '{city}'\""),
                alternatives=("sqlite3 records.db, а внутри .headers on, .mode column, затем SELECT "
                              "name, city, phone FROM people WHERE name = '{name}'; — видно обоих",)),
        Variant("Почта {email} всплыла в чужом письме. В каком городе живёт её хозяин? Ответ: "
                "ans CITY",
                hints=("Почта — колонка email, город — city, обе в таблице people.",
                       "Условие по почте: WHERE email = '…' — целиком, в одинарных кавычках.",
                       "sqlite3 records.db \"SELECT city FROM people WHERE email = '{email}'\""),
                solution="sqlite3 records.db \"SELECT city FROM people WHERE email = '{email}'\"",
                wrong=("sqlite3 records.db \"SELECT name FROM people WHERE email = '{email}'\"",
                       "sqlite3 records.db \"SELECT city FROM people WHERE email <> '{email}'\""),
                alternatives=("sqlite3 records.db \"SELECT name, city FROM people WHERE email = "
                              "'{email}'\" — заодно и кто это",)),
        Variant("В таблице people у каждого свой номер — колонка id. Кто записан под номером "
                "{pid} и где живёт? Ответ: ans NAME CITY",
                hints=("Две колонки сразу: SELECT name, city — через запятую.",
                       "Номер — число, кавычки ему не нужны: WHERE id = {pid}.",
                       "sqlite3 records.db \"SELECT name, city FROM people WHERE id = {pid}\""),
                solution="sqlite3 records.db \"SELECT name, city FROM people WHERE id = {pid}\"",
                wrong=("sqlite3 records.db \"SELECT name, city FROM people WHERE id = {pid} + 1\"",
                       "sqlite3 records.db \"SELECT name FROM people WHERE id = {pid}\""),
                alternatives=("sqlite3 -header records.db \"SELECT * FROM people WHERE id = "
                              "{pid}\" — вся строка с подписями: -header печатает шапку с именами колонок",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("WHERE оставляет только строки, где условие верно; AND хочет оба сразу. Тёзки — "
               "обычное дело: уточни вторым условием или ищи по id.")
    spell = ("sqlite3 файл.db \"SELECT кол FROM т WHERE a = 'x' AND b <> 'y'\" — строки по "
             "условию")
    trap_messages = {
        "namesake": "Тёзок двое — это телефон второго. Уточни город: AND city = '{city}'.",
        "name": "Это имя хозяина, а спрашивали город: SELECT city.",
        "next": "Это соседняя строка — нужен ровно id = {pid}.",
    }

    def wrong_message(self, given, ctx):
        """Несколько телефонов разом — запрос нашёл не одного человека: по форме (сколько
        значений сдано), без сравнения с ответом."""
        if ctx.state.get("_variant") == 0:
            shape = base._shape(self.expected(ctx.state))
            if sum(1 for w in textnorm.parts(given) if base._shape(w) == shape) > 1:
                return MSG_MANY_ROWS
        return super().wrong_message(given, ctx)

    def setup_variant(self, box, rng, variant):
        recs = _put_records(box, rng)
        st = {"sources": _sources(box)}
        ppl = recs.tables["people"]
        if variant == 1:
            p = rng.choice([x for x in ppl if not dbkit.blank(x["email"])
                            and not dbkit.namesake(recs, x)])
            return dict(st, email=p["email"], answer=p["city"], traps=[["name", p["name"]]])
        if variant == 2:
            p = rng.choice([x for x in ppl if 1 < x["id"] < len(ppl)])
            nxt = next(x for x in ppl if x["id"] == p["id"] + 1)
            return dict(st, pid=p["id"], answer=[p["name"], p["city"]],
                        traps=[["next", [nxt["name"], nxt["city"]]]])
        a, b = rng.choice(dbkit.namesakes(recs))
        if rng.random() < 0.5:
            a, b = b, a
        return dict(st, name=a["name"], city=a["city"], answer=a["phone"],
                    traps=[["namesake", b["phone"]]])


# --- 3. order_limit --------------------------------------------------------------------------

class OrderLimit(_DbAnswer):
    """ORDER BY … DESC/ASC, LIMIT, LIMIT 1 OFFSET 2."""
    id = "order_limit"
    title = "Самые-самые"
    par = 50
    scroll = ("ORDER BY колонка — по возрастанию (ASC, так и по умолчанию), ORDER BY колонка "
              "DESC — по убыванию.\n"
              "LIMIT 3 — только первые три строки; LIMIT 1 OFFSET 2 — пропусти две, возьми одну "
              "(третью).\n"
              "Даты вида 2726-08-31 сортируются по порядку: при ASC свежие — внизу.")
    variants = (
        Variant("Какой счёт в records.db третий по величине баланса (таблица accounts, колонка "
                "balance)? Ответ: ans ID БАЛАНС",
                hints=("Отсортируй по balance от большего к меньшему и пропусти двух первых.",
                       "ORDER BY balance DESC, затем LIMIT 1 OFFSET 2 — третья строка.",
                       "sqlite3 records.db \"SELECT id, balance FROM accounts ORDER BY balance "
                       "DESC LIMIT 1 OFFSET 2\""),
                solution="sqlite3 records.db \"SELECT id, balance FROM accounts ORDER BY balance "
                         "DESC LIMIT 1 OFFSET 2\"",
                wrong=("sqlite3 records.db \"SELECT id, balance FROM accounts ORDER BY balance "
                       "LIMIT 1 OFFSET 2\"",
                       "sqlite3 records.db \"SELECT id, balance FROM accounts ORDER BY balance "
                       "DESC LIMIT 1\""),
                alternatives=("sqlite3 records.db \"SELECT id, balance FROM accounts ORDER BY "
                              "balance DESC LIMIT 3\" — тройка, третья строка снизу",)),
        Variant("Какой счёт открыли позже всех? Дата открытия — колонка opened таблицы accounts. "
                "Ответ: ans ID",
                hints=("Самая поздняя дата — первая при сортировке по убыванию.",
                       "ORDER BY opened DESC LIMIT 1.",
                       "sqlite3 records.db \"SELECT id FROM accounts ORDER BY opened DESC "
                       "LIMIT 1\""),
                solution="sqlite3 records.db \"SELECT id FROM accounts ORDER BY opened DESC "
                         "LIMIT 1\"",
                wrong=("sqlite3 records.db \"SELECT id FROM accounts ORDER BY opened LIMIT 1\"",
                       "sqlite3 records.db \"SELECT id FROM accounts ORDER BY id DESC LIMIT 1\""),
                alternatives=("sqlite3 records.db \"SELECT id, opened FROM accounts ORDER BY "
                              "opened DESC LIMIT 3\" — с датами, для проверки",)),
        Variant("Назови id трёх самых мелких переводов (таблица transfers, сумма — amount). "
                "Ответ: ans ID ID ID",
                hints=("Мелкие — сверху при сортировке по возрастанию.",
                       "ORDER BY amount — по возрастанию и так, LIMIT 3 — три строки.",
                       "sqlite3 records.db \"SELECT id FROM transfers ORDER BY amount LIMIT 3\""),
                solution="sqlite3 records.db \"SELECT id FROM transfers ORDER BY amount LIMIT 3\"",
                wrong=("sqlite3 records.db \"SELECT id FROM transfers ORDER BY amount DESC "
                       "LIMIT 3\"",
                       "sqlite3 records.db \"SELECT id FROM transfers LIMIT 3\""),
                alternatives=("sqlite3 records.db \"SELECT id, amount FROM transfers ORDER BY "
                              "amount ASC LIMIT 3\" — с суммами",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("ORDER BY решает порядок, LIMIT — сколько взять, OFFSET — сколько пропустить. "
               "Без подсказки база сортирует по возрастанию — за «самым большим» иди с DESC.")
    spell = ("ORDER BY к DESC — по убыванию; LIMIT n — первые n; LIMIT 1 OFFSET 2 — третья "
             "строка")
    trap_messages = {
        "asc": "Это с другого края — сортировка по умолчанию идёт по возрастанию: нужен DESC.",
        "desc": "Это самые крупные — DESC развернул порядок, а мелкие сверху без него.",
        "first": "Это первый, а нужен третий: пропусти двух — LIMIT 1 OFFSET 2.",
        "offset": "Это четвёртый: OFFSET — сколько строк пропустить. Третий — пропусти двух: "
                  "LIMIT 1 OFFSET 2.",
        "plain": "Это просто первые строки таблицы — без ORDER BY порядок никакой.",
    }

    def setup_variant(self, box, rng, variant):
        recs = _put_records(box, rng)
        st = {"sources": _sources(box)}
        accs = recs.tables["accounts"]
        if variant == 1:
            new = max(accs, key=lambda a: a["opened"])
            old = min(accs, key=lambda a: (a["opened"], a["id"]))
            return dict(st, answer=new["id"], traps=[["asc", old["id"]]])
        if variant == 2:
            trs = recs.tables["transfers"]
            low = sorted(trs, key=lambda t: (t["amount"], t["id"]))[:3]
            high = sorted(trs, key=lambda t: (-t["amount"], t["id"]))[:3]
            first = sorted(trs, key=lambda t: t["id"])[:3]
            return dict(st, answer=[t["id"] for t in low],
                        traps=[["desc", [t["id"] for t in high]],
                               ["plain", [t["id"] for t in first]]])
        desc = sorted(accs, key=lambda a: -a["balance"])
        asc = sorted(accs, key=lambda a: (a["balance"], a["id"]))
        third = desc[2]
        return dict(st, answer=[third["id"], third["balance"]],
                    traps=[["first", [desc[0]["id"], desc[0]["balance"]]],
                           ["offset", [desc[3]["id"], desc[3]["balance"]]],
                           ["asc", [asc[2]["id"], asc[2]["balance"]]]])


# --- 4. distinct_like ------------------------------------------------------------------------

class DistinctLike(_DbAnswer):
    """DISTINCT, LIKE с % и _; в SQLite LIKE не различает регистр латиницы."""
    id = "distinct_like"
    title = "Шаблоны"
    par = 60
    scroll = ("SELECT DISTINCT city FROM people — каждый город по разу, без повторов.\n"
              "LIKE — по шаблону: 'an%' — начинается на an, '%ov' — кончается на ov, '%car%' — "
              "содержит car; _ — ровно один любой символ. Регистр латиницы LIKE в SQLite не "
              "различает.\n"
              "Сколько строк вышло — допиши | wc -l после закрывающей кавычки.")
    variants = (
        Variant("Почты людей — в колонке email таблицы people. Из скольких разных городов люди "
                "с почтой на @{domain}? Ответ: ans NUMBER",
                hints=("Города без повторов даст DISTINCT, почту по концу — LIKE с % в начале.",
                       "WHERE email LIKE '%@{domain}' — всё, что кончается на @{domain}.",
                       "sqlite3 records.db \"SELECT DISTINCT city FROM people WHERE email LIKE "
                       "'%@{domain}'\" | wc -l"),
                solution="sqlite3 records.db \"SELECT DISTINCT city FROM people WHERE email "
                         "LIKE '%@{domain}'\" | wc -l",
                wrong=("sqlite3 records.db \"SELECT city FROM people WHERE email LIKE "
                       "'%@{domain}'\" | wc -l",
                       "sqlite3 records.db \"SELECT DISTINCT city FROM people WHERE email = "
                       "'{domain}'\" | wc -l"),
                alternatives=("sqlite3 records.db \"SELECT DISTINCT city FROM people WHERE email "
                              "LIKE '%@{domain}'\" — список глазами, без счёта",)),
        Variant("В колонке name таблицы people — имя с фамилией целиком. Сколько разных "
                "значений name начинается на {pref}? Ответ: ans NUMBER",
                hints=("Значения name без повторов — DISTINCT name, начало — LIKE с % в конце.",
                       "WHERE name LIKE '{pref}%'. У тёзок name одинаковый — его считают раз.",
                       "sqlite3 records.db \"SELECT DISTINCT name FROM people WHERE name LIKE "
                       "'{pref}%'\" | wc -l"),
                solution="sqlite3 records.db \"SELECT DISTINCT name FROM people WHERE name "
                         "LIKE '{pref}%'\" | wc -l",
                wrong=("sqlite3 records.db \"SELECT name FROM people WHERE name LIKE "
                       "'{pref}%'\" | wc -l",
                       "sqlite3 records.db \"SELECT DISTINCT name FROM people WHERE name = "
                       "'{pref}'\" | wc -l"),
                alternatives=("sqlite3 records.db \"SELECT DISTINCT name FROM people WHERE name "
                              "LIKE '{pref}%'\" — сами имена",)),
        Variant("У счетов есть заметки — колонка note таблицы accounts. Сколько счетов с "
                "заметкой, где встречается слово {word}? Ответ: ans NUMBER",
                hints=("«Встречается где угодно» — LIKE с % с обеих сторон.",
                       "WHERE note LIKE '%{word}%'; каждый счёт — своя строка, DISTINCT не нужен.",
                       "sqlite3 records.db \"SELECT id FROM accounts WHERE note LIKE "
                       "'%{word}%'\" | wc -l"),
                solution="sqlite3 records.db \"SELECT id FROM accounts WHERE note LIKE "
                         "'%{word}%'\" | wc -l",
                wrong=("sqlite3 records.db \"SELECT id FROM accounts WHERE note LIKE "
                       "'{word}%'\" | wc -l",
                       "sqlite3 records.db \"SELECT id FROM accounts WHERE note = '{word}'\" "
                       "| wc -l"),
                alternatives=("sqlite3 records.db \"SELECT DISTINCT note FROM accounts WHERE "
                              "note LIKE '%{word}%'\" — какие заметки попались",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("DISTINCT выкидывает повторы из вывода, LIKE сверяет с шаблоном: % — любой хвост, "
               "_ — один символ. А = ловит только точное совпадение, целиком.")
    spell = ("SELECT DISTINCT к FROM т — без повторов; LIKE 'a%' / '%a' / '%a%'; _ — один "
             "символ")
    trap_messages = {
        "rows": "Это все строки — с повторами. Без повторов: SELECT DISTINCT.",
        "prefix": "Это только заметки, что начинаются с {word}. Где угодно — '%{word}%'.",
        "whole": "Это только заметки, где {word} — вся заметка целиком (=). Где угодно — "
                 "LIKE '%{word}%'.",
    }

    def empty_hint(self, line):
        """Ноль по форме (A7): шаблон со * — в LIKE звёздочки нет; = вместо LIKE."""
        body = line.split('"', 1)[1] if '"' in line else ""
        if re.search(r"\bLIKE\s+'[^']*\*", body, re.I):
            return MSG_LIKE_STAR
        lit = _SQ_LITERAL.sub("''", body)
        if re.search(r"\bWHERE\b", lit, re.I) and not re.search(r"\bLIKE\b", lit, re.I) \
                and re.search(r"=\s*''", lit):
            return MSG_EQ_NOT_LIKE
        return None

    def setup_variant(self, box, rng, variant):
        recs = dbkit.records(rng)
        ppl = recs.tables["people"]
        st = {}
        if variant == 1:
            name = rng.choice(dbkit.namesakes(recs))[0]["name"]
            pref = name[:rng.choice((2, 3))]
            hit = [p["name"] for p in ppl if dbkit.like(p["name"], pref + "%")]
            st = dict(pref=pref, answer=len(set(hit)), traps=[["rows", len(hit)]])
        elif variant == 2:
            word = rng.choice(("card", "savings"))
            _mix_notes(rng, recs.tables["accounts"], word)
            notes = [a["note"] for a in recs.tables["accounts"]]
            n = sum(1 for x in notes if dbkit.like(x, f"%{word}%"))
            pre = sum(1 for x in notes if dbkit.like(x, f"{word}%"))
            st = dict(word=word, answer=n, traps=[["prefix", pre], ["whole", notes.count(word)]])
        else:
            for domain in rng.sample(dbkit.DOMAINS, len(dbkit.DOMAINS)):
                hit = [p for p in ppl if dbkit.like(p["email"], "%@" + domain)]
                cities = {p["city"] for p in hit}
                if len(hit) > len(cities):
                    break
            st = dict(domain=domain, answer=len(cities), traps=[["rows", len(hit)]])
        dbkit.put(box, DB, recs.sqlite())
        return dict(st, sources=_sources(box))


MSG_LIKE_STAR = ("Ноль: в LIKE звёздочки нет — * там обычный символ. Шаблон SQL — %: LIKE "
                 "'an%' — начинается на an, _ — один любой символ.")
MSG_EQ_NOT_LIKE = "Ноль: = ищет точное совпадение целиком. По шаблону — LIKE и %."


def _mix_notes(rng, accounts, word: str) -> None:
    """Слово встречается в начале, в середине и в конце заметок и отдельно — каждое по разу
    хотя бы: ответ «где угодно» отличается и от «начинается с», и от «=»."""
    forms = {"card": ("card lost", "old card", "new card", "card"),
             "savings": ("savings plus", "joint savings", "savings", "kid savings")}[word]
    plain = [a for a in accounts if a["note"] == ""]
    for form, a in zip(forms, rng.sample(plain, len(forms))):
        a["note"] = form


# --- 5. in_between ---------------------------------------------------------------------------

class InBetween(_DbAnswer):
    """IN (…), BETWEEN a AND b (обе границы включены), даты-строки и «< начала следующего»."""
    id = "in_between"
    title = "Диапазоны"
    par = 60
    scroll = ("Из списка: city IN ('omsk', 'tver'). От и до, ОБЕ границы включены: amount "
              "BETWEEN 500 AND 1500.\n"
              "Время здесь — текст вида 2726-09-30 14:05:00, сравнивается как строка, по порядку.\n"
              "Весь месяц: ts >= 'первое число' AND ts < 'первое следующего'. BETWEEN по "
              "последний день потеряет его часы после полуночи.")
    variants = (
        Variant("Сколько людей родились с {lo} по {hi} включительно и живут в одном из городов: "
                "{cities}? Дата рождения — колонка born. Ответ: ans NUMBER",
                hints=("Два условия: дата в промежутке и город из списка.",
                       "born BETWEEN '{lo}' AND '{hi}' — с обеими границами; city IN (…) — "
                       "список в скобках, через запятую.",
                       "sqlite3 records.db \"SELECT id FROM people WHERE born BETWEEN '{lo}' AND "
                       "'{hi}' AND city IN ({in_list})\" | wc -l"),
                solution="sqlite3 records.db \"SELECT id FROM people WHERE born BETWEEN '{lo}' "
                         "AND '{hi}' AND city IN ({in_list})\" | wc -l",
                wrong=("sqlite3 records.db \"SELECT id FROM people WHERE born > '{lo}' AND born "
                       "< '{hi}' AND city IN ({in_list})\" | wc -l",
                       "sqlite3 records.db \"SELECT id FROM people WHERE born BETWEEN '{lo}' AND "
                       "'{hi}'\" | wc -l"),
                alternatives=("born >= '{lo}' AND born <= '{hi}' — то же, что BETWEEN",)),
        Variant("Сколько переводов на сумму от {lo} до {hi} включительно? Сумма — колонка "
                "amount таблицы transfers. Ответ: ans NUMBER",
                hints=("«От и до включительно» — ровно BETWEEN.",
                       "amount BETWEEN {lo} AND {hi}: числа — без кавычек, границы входят.",
                       "sqlite3 records.db \"SELECT id FROM transfers WHERE amount BETWEEN {lo} "
                       "AND {hi}\" | wc -l"),
                solution="sqlite3 records.db \"SELECT id FROM transfers WHERE amount BETWEEN {lo} "
                         "AND {hi}\" | wc -l",
                wrong=("sqlite3 records.db \"SELECT id FROM transfers WHERE amount > {lo} AND "
                       "amount < {hi}\" | wc -l",
                       "sqlite3 records.db \"SELECT id FROM transfers WHERE amount >= {lo}\" "
                       "| wc -l"),
                alternatives=("amount >= {lo} AND amount <= {hi} — то же длиннее",)),
        Variant("Сколько переводов было в сентябре 2726 года? Время — колонка ts таблицы "
                "transfers, вида 2726-09-14 18:03:11. Ответ: ans NUMBER",
                hints=("Время — строка: «весь сентябрь» — от его первого дня до первого дня "
                       "октября, не включая его.",
                       "ts >= '2726-09-01' AND ts < '2726-10-01'. BETWEEN по '2726-09-30' "
                       "потеряет 30-е после 00:00.",
                       "sqlite3 records.db \"SELECT id FROM transfers WHERE ts >= '2726-09-01' "
                       "AND ts < '2726-10-01'\" | wc -l"),
                solution="sqlite3 records.db \"SELECT id FROM transfers WHERE ts >= '2726-09-01' "
                         "AND ts < '2726-10-01'\" | wc -l",
                wrong=("sqlite3 records.db \"SELECT id FROM transfers WHERE ts BETWEEN "
                       "'2726-09-01' AND '2726-09-30'\" | wc -l",
                       "sqlite3 records.db \"SELECT id FROM transfers WHERE ts >= '2726-09-01' "
                       "AND ts <= '2726-09-30'\" | wc -l"),
                alternatives=("sqlite3 records.db \"SELECT id FROM transfers WHERE ts LIKE "
                              "'2726-09%'\" | wc -l — шаблоном по началу строки",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("BETWEEN берёт обе границы, > и < — нет. Время-строку база сравнивает по буквам: "
               "'2726-09-30 10:00' больше '2726-09-30'. Вот и ставь конец периода как «< начала "
               "следующего».")
    spell = ("к IN ('a', 'b') — из списка; к BETWEEN a AND b — с границами; ts >= 'начало' AND "
             "ts < 'начало следующего'")
    trap_messages = {
        "strict": "Границы потерялись: > и < их не включают, а BETWEEN — включает обе.",
        "lastday": "Потерялось 30-е после полуночи: '2726-09-30 10:00' больше '2726-09-30'. "
                   "Конец — ts < '2726-10-01'.",
        "nocity": "Это люди из всех городов — забыто условие city IN (…).",
    }

    def setup_variant(self, box, rng, variant):
        recs = _put_records(box, rng)
        st = {"sources": _sources(box)}
        if variant == 1:
            lo, hi = dbkit.AMOUNT_LO, dbkit.AMOUNT_HI
            am = [t["amount"] for t in recs.tables["transfers"]]
            n = sum(1 for a in am if lo <= a <= hi)
            return dict(st, lo=lo, hi=hi, answer=n,
                        traps=[["strict", sum(1 for a in am if lo < a < hi)]])
        if variant == 2:
            ts = [t["ts"] for t in recs.tables["transfers"]]
            n = sum(1 for x in ts if "2726-09-01" <= x < "2726-10-01")
            late = sum(1 for x in ts if dbkit.between(x, "2726-09-01", "2726-09-30"))
            return dict(st, answer=n, traps=[["lastday", late]])
        lo, hi = dbkit.BORN_LO, dbkit.BORN_HI
        ppl = recs.tables["people"]
        edge = sorted({p["city"] for p in ppl if p["born"] in (lo, hi)})
        rest = sorted({p["city"] for p in ppl} - set(edge))
        cities = sorted(edge + rng.sample(rest, min(len(rest), rng.randint(1, 2))))
        n = sum(1 for p in ppl if lo <= p["born"] <= hi and p["city"] in cities)
        strict = sum(1 for p in ppl if lo < p["born"] < hi and p["city"] in cities)
        every = sum(1 for p in ppl if lo <= p["born"] <= hi)
        return dict(st, lo=lo, hi=hi, cities=", ".join(cities),
                    in_list=", ".join(f"'{c}'" for c in cities), answer=n,
                    traps=[["strict", strict], ["nocity", every]])


# --- 6. null_coalesce ------------------------------------------------------------------------

MSG_BOTH_BLANK = ("Ноль: AND требует обоих условий сразу, а графа не бывает и NULL, и '' "
                  "одновременно. «Или то, или другое» — OR.")
_BOTH_BLANK = re.compile(r"IS\s+NULL\s+AND\s+(?:\w+\.)?\w+\s*=\s*''|=\s*''\s+AND\s+"
                         r"(?:\w+\.)?\w+\s+IS\s+NULL", re.I)


class NullCoalesce(_RecordsAnswer):
    """IS NULL / IS NOT NULL, «= NULL» не истинно никогда, '' — не NULL, COUNT(*) против
    COUNT(графа), COALESCE."""
    id = "null_coalesce"
    title = "Пустоты"
    par = 60
    scroll = ("NULL — «не знаю»: email IS NULL, IS NOT NULL; = NULL не истинно никогда. '' — "
              "не NULL: нет почты — это email IS NULL OR email = ''.\n"
              "\"SELECT COUNT(*) FROM people\" — сколько строк, \"SELECT COUNT(email) FROM "
              "people\" — сколько из них с email не NULL.\n"
              "\"SELECT COALESCE(email, 'none') FROM people\" ставит none вместо NULL, а строки "
              "с ним сосчитает grep -c none.")
    variants = (
        Variant("Сколько людей в people без почты — графа email у них NULL или пустая строка? "
                "Ответ: ans NUMBER",
                hints=("Пусто бывает двух видов: NULL и ''. Нужны оба, через OR.",
                       "WHERE email IS NULL OR email = '' — а = NULL не сработает никогда.",
                       "sqlite3 records.db \"SELECT COUNT(*) FROM people WHERE email IS NULL OR "
                       "email = ''\""),
                solution="sqlite3 records.db \"SELECT COUNT(*) FROM people WHERE email IS NULL "
                         "OR email = ''\"",
                wrong=("sqlite3 records.db \"SELECT COUNT(*) FROM people WHERE email = NULL\"",
                       "sqlite3 records.db \"SELECT COUNT(*) FROM people WHERE email IS NULL\""),
                alternatives=("sqlite3 records.db \"SELECT id FROM people WHERE email IS NULL OR "
                              "email = ''\" | wc -l — списком и счётом",)),
        Variant("Сколько строк в people, где email — именно NULL? Посчитай без WHERE: COUNT(*) "
                "считает все строки, COUNT(email) — те, где email не NULL. Ответ: ans NUMBER",
                hints=("Разница двух счётчиков: все строки минус строки, где почта записана.",
                       "SELECT COUNT(*) - COUNT(email): пустая строка '' — тоже значение, "
                       "COUNT(email) её считает.",
                       "sqlite3 records.db \"SELECT COUNT(*) - COUNT(email) FROM people\""),
                solution="sqlite3 records.db \"SELECT COUNT(*) - COUNT(email) FROM people\"",
                wrong=("sqlite3 records.db \"SELECT COUNT(email) FROM people\"",
                       "sqlite3 records.db \"SELECT COUNT(*) FROM people WHERE email = NULL\""),
                alternatives=("sqlite3 records.db \"SELECT COUNT(*) FROM people WHERE email IS "
                              "NULL\" — то же через WHERE",)),
        Variant("Нужен список почт города {city}: графа email, а где она NULL — слово none. "
                "Сколько none будет в этом списке? Ответ: ans NUMBER",
                hints=("COALESCE(графа, 'запасное') ставит запасное там, где NULL.",
                       "SELECT COALESCE(email, 'none') … WHERE city = '{city}', а строки с none "
                       "сосчитает grep -c none.",
                       "sqlite3 records.db \"SELECT COALESCE(email, 'none') FROM people WHERE "
                       "city = '{city}'\" | grep -c none"),
                solution="sqlite3 records.db \"SELECT COALESCE(email, 'none') FROM people WHERE "
                         "city = '{city}'\" | grep -c none",
                wrong=("sqlite3 records.db \"SELECT COALESCE(email, 'none') FROM people\" | "
                       "grep -c none",
                       "sqlite3 records.db \"SELECT COALESCE(email, 'none') FROM people WHERE "
                       "city = '{city}'\" | wc -l"),
                alternatives=("sqlite3 records.db \"SELECT name, COALESCE(email, 'none') FROM "
                              "people WHERE city = '{city}'\" — с именами, глазами",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("NULL — «значения нет, не знаю»: любое = с ним даёт «не знаю», вот и придумали "
               "IS NULL. Пустая строка '' — уже значение: её ловит = '', а COUNT(email) и "
               "COALESCE её не трогают.")
    spell = ("к IS NULL / IS NOT NULL; = NULL — никогда; COUNT(*) — строки, COUNT(к) — не NULL; "
             "COALESCE(к, 'none')")
    trap_messages = {
        "onlynull": "Это только NULL. Пустая строка '' — не NULL, её тоже считай: OR email = ''.",
        "onlyempty": "Это только пустые строки ''. NULL так не поймать — нужен ещё IS NULL.",
        "all": "Это все строки: COUNT(*) считает и те, где email NULL.",
        "have": "Это строки, где почта есть: COUNT(email) пропускает NULL. Вычти его из "
                "COUNT(*).",
        "blank": "Сюда попали и пустые строки '': они не NULL — COUNT(email) их считает, "
                 "COALESCE не заменяет.",
        "allcities": "Это none по всем городам — забыто WHERE city = '{city}'.",
        "rows": "Это все строки города: wc -l считает и почты. Нужны только none — grep -c none.",
    }

    def empty_hint(self, line):
        if _BOTH_BLANK.search(_SQ_LITERAL.sub("''", line)):
            return MSG_BOTH_BLANK
        return None

    def data_state(self, rng, recs, variant):
        ppl = recs.tables["people"]
        if variant == 2:
            city, inside = _null_city(rng, ppl)
            nulls = sum(1 for p in inside if p["email"] is None)
            return dict(city=city, answer=nulls,
                        traps=[["allcities", sum(1 for p in ppl if p["email"] is None)],
                               ["rows", len(inside)],
                               ["blank", sum(1 for p in inside if dbkit.blank(p["email"]))]])
        nulls = sum(1 for p in ppl if p["email"] is None)
        empty = sum(1 for p in ppl if p["email"] == "")
        if variant == 1:
            return dict(answer=nulls, traps=[["all", len(ppl)], ["have", len(ppl) - nulls],
                                             ["blank", nulls + empty]])
        # «= NULL» и «IS NULL AND = ''» дают 0 — их различает форма запроса (form_hint,
        # empty_hint), а не значение: ловушки «0» нет
        return dict(answer=nulls + empty, traps=[["onlynull", nulls], ["onlyempty", empty]])


def _null_city(rng, ppl):
    """Город для COALESCE: у него есть и NULL, и '' в email, и NULL есть в других городах;
    ответ, «все строки города», «NULL и ''» и «все города» — четыре разных числа. Доводим
    постройкой: в городе не меньше трёх записанных почт (так бывает всегда: записанных ≥ 99
    на ≤ 12 городов), одна остаётся записанной."""
    cities = sorted({p["city"] for p in ppl})
    fit = [c for c in cities if sum(1 for p in ppl if p["city"] == c
                                    and not dbkit.blank(p["email"])) >= 3]
    city = rng.choice(fit)
    inside = [p for p in ppl if p["city"] == city]
    filled = [p for p in inside if not dbkit.blank(p["email"])]
    rng.shuffle(filled)
    if not any(p["email"] is None for p in inside):
        filled.pop()["email"] = None
    if not any(p["email"] == "" for p in inside):
        filled.pop()["email"] = ""
    outside = [p for p in ppl if p["city"] != city and not dbkit.blank(p["email"])]
    rng.shuffle(outside)
    if not any(p["email"] is None for p in ppl if p["city"] != city):
        outside.pop()["email"] = None
    # «все none по таблице» не равно «все строки города»: ещё один NULL снаружи
    if sum(1 for p in ppl if p["email"] is None) == len(inside):
        outside.pop()["email"] = None
    return city, inside


# --- 7. group_count --------------------------------------------------------------------------

class GroupCount(_RecordsAnswer):
    """COUNT/SUM/AVG/MIN/MAX, ROUND(x, 2), GROUP BY, AS, сортировка по агрегату."""
    id = "group_count"
    title = "Сводка"
    par = 75
    scroll = ("Агрегат сворачивает много строк в одно число: COUNT(*) — сколько строк (уже "
              "знаком), SUM(x) — сумма.\n"
              "GROUP BY city — по строке на город: SELECT city, COUNT(*) AS n FROM people GROUP "
              "BY city. AS даёт графе имя.\n"
              "ORDER BY n DESC LIMIT 1 — самая большая группа. Без GROUP BY агрегат сворачивает "
              "всю таблицу в одну строку.")
    variants = (
        Variant("В каком городе живёт больше всего людей из people и сколько их там? Ответ: ans "
                "CITY NUMBER",
                hints=("По строке на город — GROUP BY city, в каждой COUNT(*).",
                       "Дай счётчику имя — COUNT(*) AS n — и отсортируй: ORDER BY n DESC LIMIT 1.",
                       "sqlite3 records.db \"SELECT city, COUNT(*) AS n FROM people GROUP BY city "
                       "ORDER BY n DESC LIMIT 1\""),
                solution="sqlite3 records.db \"SELECT city, COUNT(*) AS n FROM people GROUP BY "
                         "city ORDER BY n DESC LIMIT 1\"",
                wrong=("sqlite3 records.db \"SELECT city, COUNT(*) FROM people\"",
                       "sqlite3 records.db \"SELECT city, COUNT(*) AS n FROM people GROUP BY city "
                       "ORDER BY n LIMIT 1\""),
                alternatives=("sqlite3 records.db \"SELECT city, COUNT(*) FROM people GROUP BY "
                              "city\" — все города, глазами",)),
        Variant("Какой средний баланс у счетов со статусом {status} (таблица accounts)? Среднее "
                "считает AVG(balance), а ROUND(x, 2) округлит до двух знаков после точки. Ответ: "
                "ans NUMBER",
                hints=("Среднее — AVG(balance), отбор строк — WHERE status = '{status}'.",
                       "ROUND(AVG(balance), 2) — два знака; ROUND без второго числа округлит до "
                       "целого.",
                       "sqlite3 records.db \"SELECT ROUND(AVG(balance), 2) FROM accounts WHERE "
                       "status = '{status}'\""),
                solution="sqlite3 records.db \"SELECT ROUND(AVG(balance), 2) FROM accounts WHERE "
                         "status = '{status}'\"",
                wrong=("sqlite3 records.db \"SELECT ROUND(AVG(balance), 2) FROM accounts\"",
                       "sqlite3 records.db \"SELECT ROUND(AVG(balance)) FROM accounts WHERE "
                       "status = '{status}'\""),
                alternatives=("sqlite3 records.db \"SELECT AVG(balance) FROM accounts WHERE "
                              "status = '{status}'\" — без округления, для сверки",)),
        Variant("Какой счёт отправил больше всего денег — по сумме всех своих переводов? В "
                "transfers отправитель — from_acc, сумма — amount. Ответ: ans ACCOUNT SUM",
                hints=("По строке на отправителя — GROUP BY from_acc, в ней SUM(amount).",
                       "SUM(amount) AS total, затем ORDER BY total DESC LIMIT 1.",
                       "sqlite3 records.db \"SELECT from_acc, SUM(amount) AS total FROM transfers "
                       "GROUP BY from_acc ORDER BY total DESC LIMIT 1\""),
                solution="sqlite3 records.db \"SELECT from_acc, SUM(amount) AS total FROM "
                         "transfers GROUP BY from_acc ORDER BY total DESC LIMIT 1\"",
                wrong=("sqlite3 records.db \"SELECT from_acc, SUM(amount) FROM transfers\"",
                       "sqlite3 records.db \"SELECT from_acc, COUNT(*) AS n FROM transfers GROUP "
                       "BY from_acc ORDER BY n DESC LIMIT 1\""),
                alternatives=("sqlite3 records.db \"SELECT from_acc, SUM(amount) AS total FROM "
                              "transfers GROUP BY from_acc ORDER BY total DESC LIMIT 3\" — "
                              "тройка с отрывом",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Агрегат сворачивает кучу строк в одно число. GROUP BY режет таблицу на группы, и "
               "агрегат считает каждую; без GROUP BY группа одна — вся таблица.")
    spell = ("SELECT к, COUNT(*) AS n FROM т GROUP BY к ORDER BY n DESC; SUM, AVG, MIN, MAX; "
             "ROUND(x, 2)")
    trap_messages = {
        "nogroup": "Это итог по всей таблице: без GROUP BY агрегат сворачивает её в одну строку.",
        "asc": "Это самая маленькая группа: по умолчанию сортировка по возрастанию — нужен DESC.",
        "nowhere": "Это среднее по всем счетам — забыто WHERE status = '{status}'.",
        "whole": "Это округлено до целого, а нужно два знака после точки: ROUND(AVG(balance), "
                 "2).",
        "count": "Это число переводов, а не деньги: сумма — SUM(amount), не COUNT(*).",
        "to": "Это получатель: деньги уходят со счёта from_acc, а не to_acc.",
    }

    def data_state(self, rng, recs, variant):
        if variant == 1:
            return _avg_state(rng, recs)
        if variant == 2:
            return _sender_state(rng, recs)
        by = _lead_cities(rng, recs)
        lead = by.most_common(1)[0]
        low = min(by.values())
        return dict(answer=[lead[0], lead[1]], totals=[["nogroup", len(recs.tables["people"])]],
                    traps=[["asc", [c, n]] for c, n in sorted(by.items()) if n == low])


def _lead_cities(rng, recs) -> Counter:
    """Люди по городам; у лидера запас не меньше LEAD_MARGIN — переселяем не-тёзок из других
    городов (данные этого варианта; тёзки остаются в разных городах)."""
    ppl = recs.tables["people"]
    while True:
        by = Counter(p["city"] for p in ppl)
        (lead, a), (_, b) = sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
        if a - b >= dbkit.LEAD_MARGIN:
            return by
        p = rng.choice([p for p in ppl if p["city"] != lead and by[p["city"]] > 1
                        and not dbkit.namesake(recs, p)])
        p["city"] = lead


def _avg_state(rng, recs) -> dict:
    """Средний баланс по статусу: ROUND(…, 2) не на «.xx5», отличается от ROUND(…) до целого и
    от среднего по всем счетам больше чем на 0,01 — доводим балансы по одному кредиту."""
    accs = recs.tables["accounts"]
    status = rng.choice([s for s in dbkit.ACCOUNT_STATUSES
                         if sum(1 for a in accs if a["status"] == s) >= 3])
    mine = [a for a in accs if a["status"] == status]
    while True:
        x = dbkit.avg([a["balance"] for a in mine])
        every = dbkit.avg([a["balance"] for a in accs])
        frac = x % 1
        if (not dbkit.round_risk(x) and 0.02 < frac < 0.98
                and abs(dbkit.sql_round(every, 2) - dbkit.sql_round(x, 2)) > 0.02):
            break
        rng.choice(mine)["balance"] += 1
    ans = dbkit.sql_round(x, 2)
    return dict(status=status, answer=ans,
                traps=[["nowhere", dbkit.sql_round(every, 2)], ["whole", dbkit.sql_round(x)]])


def _sender_state(rng, recs) -> dict:
    """Счёт с наибольшей суммой отправленного: запас не меньше LEAD_MARGIN (добавляем лидеру к
    его крупнейшему переводу)."""
    trs = recs.tables["transfers"]
    sums, cnt, got = Counter(), Counter(), Counter()
    for t in trs:
        sums[t["from_acc"]] += t["amount"]
        cnt[t["from_acc"]] += 1
        got[t["to_acc"]] += t["amount"]
    (lead, a), (_, b) = sorted(sums.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
    if a - b < dbkit.LEAD_MARGIN:
        bump = dbkit.LEAD_MARGIN - (a - b) + rng.randint(0, 40)
        t = max((t for t in trs if t["from_acc"] == lead), key=lambda t: (t["amount"], t["id"]))
        t["amount"] += bump
        sums[lead] += bump
        got[t["to_acc"]] += bump
    top_n = max(cnt.values())
    traps = [["count", [acc, n]] for acc, n in sorted(cnt.items()) if n == top_n]
    top_got = max(got.values())
    traps += [["to", [acc, v]] for acc, v in sorted(got.items()) if v == top_got]
    return dict(answer=[lead, sums[lead]], totals=[["nogroup", sum(t["amount"] for t in trs)]],
                traps=traps)


# --- 8. group_having -------------------------------------------------------------------------

MSG_GROUPS_NOT_COUNTED = ("Это строки отчёта, по одной на группу, а спрашивали, сколько групп. "
                          "Сосчитай их: | wc -l после закрывающей кавычки.")
MSG_HAVING_ROW = ("Статус — свойство строки, а не группы: его место в WHERE, до GROUP BY. В "
                  "HAVING — только условие на группу: COUNT(*), SUM(…).")


class GroupHaving(_RecordsAnswer):
    """HAVING против WHERE: условие на строки — до группировки, на группу — после."""
    id = "group_having"
    title = "Фильтр после группировки"
    par = 75
    scroll = ("WHERE отбирает строки до группировки, HAVING — группы после неё: GROUP BY city HAVING "
              "COUNT(*) > 5. Края группы — MIN(x) и MAX(x).\n"
              "Агрегат в WHERE нельзя — sqlite3 ответит misuse of aggregate.\n"
              "> 5 — строго больше, пять не входит; «пять и больше» — >= 5. Сколько групп вышло — | wc -l.")
    variants = (
        Variant("В скольких городах из people живёт больше {n} человек? Ответ: ans NUMBER",
                hints=("Группы — города; условие на размер группы — после GROUP BY, в HAVING.",
                       "GROUP BY city HAVING COUNT(*) > {n}: «больше {n}» — строго, ровно {n} не "
                       "входит.",
                       "sqlite3 records.db \"SELECT city FROM people GROUP BY city HAVING "
                       "COUNT(*) > {n}\" | wc -l"),
                solution="sqlite3 records.db \"SELECT city FROM people GROUP BY city HAVING "
                         "COUNT(*) > {n}\" | wc -l",
                wrong=("sqlite3 records.db \"SELECT city FROM people GROUP BY city HAVING "
                       "COUNT(*) >= {n}\" | wc -l",
                       "sqlite3 records.db \"SELECT city FROM people GROUP BY city\" | wc -l"),
                alternatives=("sqlite3 records.db \"SELECT city, COUNT(*) FROM people GROUP BY "
                              "city HAVING COUNT(*) > {n}\" — с числами, глазами",)),
        Variant("Сколько людей владеют двумя счетами или больше? Владелец счёта — person_id в "
                "accounts. Ответ: ans NUMBER",
                hints=("Группа — человек: GROUP BY person_id, размер группы — COUNT(*).",
                       "«Два и больше» — HAVING COUNT(*) >= 2: строгое > 2 потеряет тех, у кого "
                       "ровно два.",
                       "sqlite3 records.db \"SELECT person_id FROM accounts GROUP BY person_id "
                       "HAVING COUNT(*) >= 2\" | wc -l"),
                solution="sqlite3 records.db \"SELECT person_id FROM accounts GROUP BY person_id "
                         "HAVING COUNT(*) >= 2\" | wc -l",
                wrong=("sqlite3 records.db \"SELECT person_id FROM accounts GROUP BY person_id "
                       "HAVING COUNT(*) > 2\" | wc -l",
                       "sqlite3 records.db \"SELECT person_id FROM accounts GROUP BY person_id\" "
                       "| wc -l"),
                alternatives=("sqlite3 records.db \"SELECT person_id, COUNT(*) AS n FROM accounts "
                              "GROUP BY person_id HAVING n >= 2\" | wc -l — по имени графы",)),
        Variant("Считаем только активные счета (status = 'active'). У скольких людей сумма "
                "балансов таких счетов больше {limit}? Ответ: ans NUMBER",
                hints=("Сначала отбор строк — WHERE по статусу, потом группы по person_id и "
                       "условие на сумму — HAVING.",
                       "WHERE status = 'active' GROUP BY person_id HAVING SUM(balance) > {limit}: "
                       "WHERE до GROUP BY, HAVING после.",
                       "sqlite3 records.db \"SELECT person_id FROM accounts WHERE status = "
                       "'active' GROUP BY person_id HAVING SUM(balance) > {limit}\" | wc -l"),
                solution="sqlite3 records.db \"SELECT person_id FROM accounts WHERE status = "
                         "'active' GROUP BY person_id HAVING SUM(balance) > {limit}\" | wc -l",
                wrong=("sqlite3 records.db \"SELECT person_id FROM accounts GROUP BY person_id "
                       "HAVING SUM(balance) > {limit}\" | wc -l",
                       "sqlite3 records.db \"SELECT person_id FROM accounts WHERE status = "
                       "'active' AND balance > {limit}\" | wc -l"),
                alternatives=("sqlite3 records.db \"SELECT person_id, SUM(balance) FROM accounts "
                              "WHERE status = 'active' GROUP BY person_id HAVING SUM(balance) > "
                              "{limit}\" — с суммами",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Порядок такой: WHERE отсеивает строки, GROUP BY собирает группы, HAVING бракует "
               "группы. Агрегату нужна готовая группа — вот его условие и живёт только в HAVING.")
    spell = ("SELECT к FROM т WHERE строки GROUP BY к HAVING COUNT(*) > n; > — строго, >= — с "
             "границей")
    trap_messages = {
        "ge": "Группа ровно на границе попала: «больше {n}» — это >, а >= берёт и {n}.",
        "nohaving": "Это все группы — условие HAVING потерялось.",
        "gt": "Потерялись владельцы ровно двух счетов: «два и больше» — это >= 2.",
        "owners": "Это все владельцы счетов — без HAVING группы не отсеяны.",
        "nostatus": "Сюда попали и замороженные с закрытыми: отбор строк WHERE status = 'active' "
                    "— до GROUP BY.",
        "limit_ge": "Человек ровно с суммой {limit} попал: «больше» — это >, без границы.",
        "rows": "Это счета по одному, а не суммы по людям: GROUP BY person_id и HAVING "
                "SUM(balance).",
    }

    def wrong_message(self, given, ctx):
        """Несколько частей из запроса с GROUP BY без | wc -l — строки отчёта, не их число (по
        форме: сколько частей сдано и как выглядел запрос)."""
        line = _last_sql(ctx)
        if (len(textnorm.parts(given)) > 1 and re.search(r"GROUP\s+BY", line, re.I)
                and "wc" not in line):
            return MSG_GROUPS_NOT_COUNTED
        return super().wrong_message(given, ctx)

    def form_hint(self, line):
        body = _SQ_LITERAL.sub("''", line)
        if re.search(r"\bHAVING\b[^\"]*\bstatus\b", body, re.I):
            return MSG_HAVING_ROW
        return super().form_hint(line)

    def data_state(self, rng, recs, variant):
        if variant == 1:
            return _owners_state(rng, recs)
        if variant == 2:
            return _active_sum_state(rng, recs)
        by = _spread_cities(rng, recs)
        sizes = sorted(set(by.values()))
        # порог — размер группы, и есть группа больше; не самый малый, чтобы >= не совпал
        # с «все города»
        n = rng.choice(sizes[1:-1] or sizes[:-1])
        return dict(n=n, answer=sum(1 for v in by.values() if v > n),
                    traps=[["ge", sum(1 for v in by.values() if v >= n)],
                           ["nohaving", len(by)]])


def _spread_cities(rng, recs) -> Counter:
    """Люди по городам; размеров групп не меньше двух (иначе порога с краем нет) — переселяем
    одного не-тёзку (так бывает, только если все города ровно одного размера)."""
    ppl = recs.tables["people"]
    by = Counter(p["city"] for p in ppl)
    if len(set(by.values())) < 2:
        a, b = sorted(by)[:2]
        next(p for p in ppl if p["city"] == a and not dbkit.namesake(recs, p))["city"] = b
        by = Counter(p["city"] for p in ppl)
    return by


def _owners_state(rng, recs) -> dict:
    """Владельцы «двух и больше»: постройкой есть и владельцы ровно одного, и ровно двух, и трёх+
    счетов — ответ отличается и от «> 2», и от «все владельцы»."""
    accs = recs.tables["accounts"]

    def per():
        return Counter(a["person_id"] for a in accs)
    have = per()
    idle = [p["id"] for p in recs.tables["people"] if p["id"] not in have]
    if not any(v == 1 for v in have.values()):
        dbkit.add_account(rng, recs, idle.pop(rng.randrange(len(idle))), rng.randrange(90000))
    have = per()
    if not any(v == 2 for v in have.values()):
        pid = rng.choice(sorted(k for k, v in have.items() if v == 1))
        dbkit.add_account(rng, recs, pid, rng.randrange(90000))
    have = per()
    if not any(v >= 3 for v in have.values()):
        pid = rng.choice(sorted(k for k, v in have.items() if v == 2))
        dbkit.add_account(rng, recs, pid, rng.randrange(90000))
    have = per()
    return dict(answer=sum(1 for v in have.values() if v >= 2),
                traps=[["gt", sum(1 for v in have.values() if v > 2)], ["owners", len(have)]])


def _active_sum_state(rng, recs) -> dict:
    """WHERE + HAVING: порог — сумма активных счетов одного из людей (ровно на границе — есть),
    из середины ряда. Человеку без счетов даём замороженный счёт выше порога: без WHERE он
    попадает в ответ — «без WHERE» всегда больше. «Счета по одному» (balance > порога) тоже
    не совпадает с ответом: при равенстве — ещё один крупный счёт тому, кто уже выше."""
    accs = recs.tables["accounts"]
    sums = Counter()
    for a in accs:
        if a["status"] == "active":
            sums[a["person_id"]] += a["balance"]
    ranked = sorted(set(sums.values()))
    limit = rng.choice(ranked[len(ranked) // 3: 2 * len(ranked) // 3])
    owners = {a["person_id"] for a in accs}
    idle = sorted(p["id"] for p in recs.tables["people"] if p["id"] not in owners)
    dbkit.add_account(rng, recs, rng.choice(idle), limit + 1 + rng.randrange(5000), "frozen")
    answer = sum(1 for v in sums.values() if v > limit)

    def rows():
        return sum(1 for a in accs if a["status"] == "active" and a["balance"] > limit)
    if rows() == answer:        # «счета по одному» = ответ: ещё крупный счёт тому, кто уже выше
        rich = rng.choice(sorted(pid for pid, v in sums.items() if v > limit))
        dbkit.add_account(rng, recs, rich, limit + 1 + rng.randrange(5000))
    every = Counter()
    for a in accs:
        every[a["person_id"]] += a["balance"]
    return dict(limit=limit, answer=answer,
                traps=[["nostatus", sum(1 for v in every.values() if v > limit)],
                       ["limit_ge", sum(1 for v in sums.values() if v >= limit)],
                       ["rows", rows()]])


# --- 9. join_inner ---------------------------------------------------------------------------

MSG_NEED_JOIN = ("Ничего не нашлось: в одной таблице этого нет — имена в people, счета в "
                 "accounts, переводы в transfers, и id у каждой свои. Склей их: JOIN … ON.")
MSG_AMBIGUOUS = ("{col} есть в обеих таблицах — sqlite3 скажет ambiguous column name: {col}. "
                 "Пиши с псевдонимом таблицы: a.{col} или p.{col}.")
_BARE_COL = re.compile(r"(?<![\w.'])(id|status|note)\b")
MSG_JOIN_EMPTY = ("Склейка ничего не нашла — проверь ON: ссылка одной таблицы равна id другой "
                  "(a.person_id = p.id, t.from_acc = a.id). id людей, счетов и переводов — "
                  "разные номера, id = id не совпадёт.")


class _JoinAnswer(_RecordsAnswer):
    """Общее у склеек: графа без псевдонима, которая есть в обеих таблицах, — ambiguous."""

    def form_hint(self, line):
        body = _SQ_LITERAL.sub("''", line)
        if re.search(r"\bJOIN\b", body, re.I):
            m = _BARE_COL.search(body.split('"', 1)[1] if '"' in body else body)
            if m:
                return MSG_AMBIGUOUS.format(col=m.group(1))
        return super().form_hint(line)

    def empty_hint(self, line):
        if "sqlite3" not in line:
            return None
        if not re.search(r"\bJOIN\b", line, re.I):
            return MSG_NEED_JOIN
        return MSG_JOIN_EMPTY


class JoinInner(_JoinAnswer):
    """JOIN … ON a.x = b.y, псевдонимы p и a, p.name; ambiguous column."""
    id = "join_inner"
    title = "Склейка таблиц"
    par = 90
    scroll = ("JOIN склеивает строки двух таблиц по условию: FROM people p JOIN accounts a ON "
              "a.person_id = p.id. p и a — псевдонимы. JOIN — он же INNER JOIN.\n"
              "Графы — с псевдонимом: p.name, a.balance. id есть в обеих: без p. или a. sqlite3 "
              "скажет ambiguous column name.\n"
              "Третья таблица — ещё один JOIN … ON. Склеивай по id, а не по имени: у тёзок "
              "имя одно на двоих.")
    variants = (
        Variant("Сколько денег на всех счетах у {name} из города {city}? Имя и город — в people, "
                "балансы — в accounts. Ответ: ans NUMBER",
                hints=("Счета связаны с людьми через person_id: склей people и accounts.",
                       "people p JOIN accounts a ON a.person_id = p.id, затем SUM(a.balance) и "
                       "WHERE по имени и городу.",
                       "sqlite3 records.db \"SELECT SUM(a.balance) FROM people p JOIN accounts a "
                       "ON a.person_id = p.id WHERE p.name = '{name}' AND p.city = '{city}'\""),
                solution="sqlite3 records.db \"SELECT SUM(a.balance) FROM people p JOIN accounts "
                         "a ON a.person_id = p.id WHERE p.name = '{name}' AND p.city = '{city}'\"",
                wrong=("sqlite3 records.db \"SELECT SUM(a.balance) FROM people p JOIN accounts a "
                       "ON a.person_id = p.id WHERE p.name = '{name}'\"",
                       "sqlite3 records.db \"SELECT SUM(a.balance) FROM people p JOIN accounts a "
                       "ON a.person_id = p.id WHERE p.name = '{name}' AND p.city <> '{city}'\""),
                alternatives=("sqlite3 records.db \"SELECT a.id, a.balance FROM people p JOIN "
                              "accounts a ON a.person_id = p.id WHERE p.name = '{name}' AND "
                              "p.city = '{city}'\" — по счетам, глазами",)),
        Variant("Чей счёт номер {acc}? Номер — id в accounts, владелец — в people. Ответ: ans "
                "NAME SURNAME",
                hints=("В accounts только person_id — имя ищи в people, склеив по нему.",
                       "accounts a JOIN people p ON p.id = a.person_id WHERE a.id = {acc}; просто "
                       "id — ambiguous.",
                       "sqlite3 records.db \"SELECT p.name FROM accounts a JOIN people p ON p.id "
                       "= a.person_id WHERE a.id = {acc}\""),
                solution="sqlite3 records.db \"SELECT p.name FROM accounts a JOIN people p ON "
                         "p.id = a.person_id WHERE a.id = {acc}\"",
                wrong=("sqlite3 records.db \"SELECT person_id FROM accounts WHERE id = {acc}\"",
                       "sqlite3 records.db \"SELECT name FROM accounts a JOIN people p ON p.id = "
                       "a.person_id WHERE id = {acc}\""),
                alternatives=("sqlite3 records.db \"SELECT p.name, p.city FROM accounts a JOIN "
                              "people p ON p.id = a.person_id WHERE a.id = {acc}\" — и город",)),
        Variant("Кто отправил самый крупный перевод? Отправитель — владелец счёта from_acc из "
                "transfers. Ответ: ans NAME SURNAME CITY",
                hints=("Три таблицы: transfers → accounts (по from_acc) → people (по person_id).",
                       "transfers t JOIN accounts a ON a.id = t.from_acc JOIN people p ON p.id = "
                       "a.person_id, затем ORDER BY t.amount DESC LIMIT 1.",
                       "sqlite3 records.db \"SELECT p.name, p.city FROM transfers t JOIN accounts "
                       "a ON a.id = t.from_acc JOIN people p ON p.id = a.person_id ORDER BY "
                       "t.amount DESC LIMIT 1\""),
                solution="sqlite3 records.db \"SELECT p.name, p.city FROM transfers t JOIN "
                         "accounts a ON a.id = t.from_acc JOIN people p ON p.id = a.person_id "
                         "ORDER BY t.amount DESC LIMIT 1\"",
                wrong=("sqlite3 records.db \"SELECT p.name, p.city FROM transfers t JOIN accounts "
                       "a ON a.id = t.to_acc JOIN people p ON p.id = a.person_id ORDER BY "
                       "t.amount DESC LIMIT 1\"",
                       "sqlite3 records.db \"SELECT p.name, p.city FROM transfers t JOIN accounts "
                       "a ON a.id = t.from_acc JOIN people p ON p.id = a.person_id ORDER BY "
                       "t.amount LIMIT 1\""),
                alternatives=("sqlite3 records.db \"SELECT from_acc FROM transfers ORDER BY amount "
                              "DESC LIMIT 1\" — сначала счёт, потом его владелец вторым "
                              "запросом",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("JOIN ставит рядом строки двух таблиц, где сходится ON, — обычно ссылка равна id. "
               "По имени не клей: тёзок двое, и чужие счета прилипнут к обоим.")
    spell = ("FROM т1 x JOIN т2 y ON y.ссылка = x.id — склейка; x.графа — с псевдонимом; ещё JOIN "
             "— третья таблица")
    trap_messages = {
        "both": "Тут счета обоих тёзок — уточни город: AND p.city = '{city}'.",
        "other": "Это счета второго {name} — того, что не из {city}.",
        "to": "Это получатель: деньги уходят со счёта from_acc, а не to_acc.",
        "small": "Это отправитель самого мелкого перевода — нужен DESC.",
    }
    MSG_NUMBER = ("Это номер, а нужно имя: в accounts лежит только person_id — склей accounts с "
                  "people и возьми p.name.")

    def wrong_message(self, given, ctx):
        nums = [w for w in textnorm.parts(given) if textnorm.as_number(w) is not None]
        if ctx.state.get("_variant") == 1 and len(nums) == 1 and len(textnorm.parts(given)) == 1:
            return self.MSG_NUMBER       # одно число вместо имени — по форме
        return super().wrong_message(given, ctx)

    def data_state(self, rng, recs, variant):
        if variant == 1:
            return _owner_state(rng, recs)
        if variant == 2:
            return _big_sender_state(rng, recs)
        return _namesake_sum_state(rng, recs)


def _namesake_sum_state(rng, recs) -> dict:
    """Сумма балансов тёзки: у обоих тёзок есть счета, у второго сумма не ноль и не равна
    первой — «без города» и «другой город» никогда не совпадают с ответом."""
    a, b = rng.choice(dbkit.namesakes(recs))
    if rng.random() < 0.5:
        a, b = b, a
    for p in (a, b):
        if not recs.accounts_of(p["id"]):
            dbkit.add_account(rng, recs, p["id"], rng.randrange(1, 90000))
    mine, theirs = recs.accounts_of(a["id"]), recs.accounts_of(b["id"])
    if sum(x["balance"] for x in mine) == 0:
        mine[0]["balance"] += 1 + rng.randrange(500)
    while sum(x["balance"] for x in theirs) in (0, sum(x["balance"] for x in mine)):
        theirs[0]["balance"] += 1
    s_a, s_b = (sum(x["balance"] for x in g) for g in (mine, theirs))
    return dict(name=a["name"], city=a["city"], answer=s_a,
                traps=[["both", s_a + s_b], ["other", s_b]])


def _owner_state(rng, recs) -> dict:
    """Владелец счёта: номер счёта больше любого id людей — спутать с people.id не выйдет."""
    top = max(p["id"] for p in recs.tables["people"])
    acc = rng.choice([a for a in recs.tables["accounts"] if a["id"] > top])
    return dict(acc=acc["id"], answer=recs.person(acc["person_id"])["name"], traps=[])


def _big_sender_state(rng, recs) -> dict:
    """Отправитель крупнейшего перевода: получатель и отправитель самого мелкого — другие люди
    (доводим постройкой: меняем счёт на чужой)."""
    trs, accs = recs.tables["transfers"], recs.tables["accounts"]
    big = max(trs, key=lambda t: t["amount"])
    small = min(trs, key=lambda t: (t["amount"], t["id"]))
    owner = {a["id"]: a["person_id"] for a in accs}
    who = owner[big["from_acc"]]
    others = sorted(a["id"] for a in accs if a["person_id"] != who)
    if owner[big["to_acc"]] == who:
        big["to_acc"] = rng.choice(others)
    if owner[small["from_acc"]] == who:
        small["from_acc"] = rng.choice([x for x in others if x != small["to_acc"]])

    def pc(acc_id):
        p = recs.person(owner[acc_id])
        return [p["name"], p["city"]]
    return dict(answer=pc(big["from_acc"]),
                traps=[["to", pc(big["to_acc"])], ["small", pc(small["from_acc"])]])


# --- 10. join_left ---------------------------------------------------------------------------

MSG_INNER_EMPTY = ("Ничего не нашлось: простой JOIN (INNER) выкидывает тех, у кого пары нет, — "
                   "а их-то и ищем. Нужен LEFT JOIN.")
MSG_COUNT_STAR = ("Ничего не нашлось: у человека без счетов COUNT(*) — 1, а не 0, строка "
                  "склейки-то есть. Считай пары: COUNT(a.id).")


MSG_LEFT_ORDER = ("Ноль: LEFT JOIN оставляет всех из ЛЕВОЙ таблицы — той, что сразу после FROM; "
                  "пропавших ищут в ней. Проверь, что она первая, а IS NULL стоит у графы "
                  "правой таблицы.")


class JoinLeft(_JoinAnswer):
    """LEFT JOIN, NULL справа, анти-склейка WHERE a.id IS NULL, COUNT(a.id) против COUNT(*)."""
    id = "join_left"
    title = "Кого нет"
    par = 90
    scroll = ("LEFT JOIN оставляет все строки левой таблицы, даже без пары, — справа у них NULL. "
              "Простой JOIN (INNER) таких выкидывает.\n"
              "Кто без пары: FROM people p LEFT JOIN accounts a ON a.person_id = p.id WHERE a.id "
              "IS NULL.\n"
              "COUNT(a.id) считает найденные пары, COUNT(*) — строки склейки: у человека без "
              "счетов он даст 1, а не 0.")
    variants = (
        Variant("Сколько людей из people без единого счёта в accounts? Ответ: ans NUMBER",
                hints=("Нужны люди без пары в accounts: LEFT JOIN оставит их, справа будет NULL.",
                       "people p LEFT JOIN accounts a ON a.person_id = p.id WHERE a.id IS NULL — "
                       "и COUNT(*).",
                       "sqlite3 records.db \"SELECT COUNT(*) FROM people p LEFT JOIN accounts a "
                       "ON a.person_id = p.id WHERE a.id IS NULL\""),
                solution="sqlite3 records.db \"SELECT COUNT(*) FROM people p LEFT JOIN accounts "
                         "a ON a.person_id = p.id WHERE a.id IS NULL\"",
                wrong=("sqlite3 records.db \"SELECT COUNT(*) FROM people p JOIN accounts a ON "
                       "a.person_id = p.id WHERE a.id IS NULL\"",
                       "sqlite3 records.db \"SELECT COUNT(*) FROM people p LEFT JOIN accounts a "
                       "ON a.person_id = p.id\""),
                alternatives=("sqlite3 records.db \"SELECT p.name FROM people p LEFT JOIN "
                              "accounts a ON a.person_id = p.id WHERE a.id IS NULL\" — сами "
                              "люди",)),
        Variant("Со скольких счетов в accounts не ушло ни одного перевода — в transfers их нет "
                "в графе from_acc? Ответ: ans NUMBER",
                hints=("Счета без пары в transfers по from_acc: LEFT JOIN и NULL справа.",
                       "accounts a LEFT JOIN transfers t ON t.from_acc = a.id WHERE t.id IS NULL.",
                       "sqlite3 records.db \"SELECT COUNT(*) FROM accounts a LEFT JOIN transfers "
                       "t ON t.from_acc = a.id WHERE t.id IS NULL\""),
                solution="sqlite3 records.db \"SELECT COUNT(*) FROM accounts a LEFT JOIN "
                         "transfers t ON t.from_acc = a.id WHERE t.id IS NULL\"",
                wrong=("sqlite3 records.db \"SELECT COUNT(*) FROM accounts a JOIN transfers t ON "
                       "t.from_acc = a.id WHERE t.id IS NULL\"",
                       "sqlite3 records.db \"SELECT COUNT(*) FROM accounts a LEFT JOIN transfers "
                       "t ON t.to_acc = a.id WHERE t.id IS NULL\""),
                alternatives=("sqlite3 records.db \"SELECT a.id FROM accounts a LEFT JOIN "
                              "transfers t ON t.from_acc = a.id WHERE t.id IS NULL\" | wc -l — "
                              "списком",)),
        Variant("В городе {city} у одного жителя нет ни одного счёта. Кто это? Ответ: ans NAME "
                "SURNAME",
                hints=("Жители со счетами и без: LEFT JOIN, затем GROUP BY p.id и число пар.",
                       "У человека без счетов COUNT(a.id) — 0, а COUNT(*) — 1. Отбор групп — "
                       "HAVING COUNT(a.id) = 0.",
                       "sqlite3 records.db \"SELECT p.name FROM people p LEFT JOIN accounts a ON "
                       "a.person_id = p.id WHERE p.city = '{city}' GROUP BY p.id HAVING "
                       "COUNT(a.id) = 0\""),
                solution="sqlite3 records.db \"SELECT p.name FROM people p LEFT JOIN accounts a "
                         "ON a.person_id = p.id WHERE p.city = '{city}' GROUP BY p.id HAVING "
                         "COUNT(a.id) = 0\"",
                wrong=("sqlite3 records.db \"SELECT p.name FROM people p LEFT JOIN accounts a ON "
                       "a.person_id = p.id WHERE p.city = '{city}' GROUP BY p.id HAVING COUNT(*) "
                       "= 0\"",
                       "sqlite3 records.db \"SELECT p.name FROM people p JOIN accounts a ON "
                       "a.person_id = p.id WHERE p.city = '{city}' GROUP BY p.id HAVING "
                       "COUNT(a.id) = 0\""),
                alternatives=("sqlite3 records.db \"SELECT p.name FROM people p LEFT JOIN "
                              "accounts a ON a.person_id = p.id WHERE p.city = '{city}' AND a.id "
                              "IS NULL\" — анти-склейка, как в первом способе",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("LEFT JOIN — «все слева, а справа что найдётся». Кому пары нет, у того справа "
               "NULL — по нему одиночек и ловят. COUNT(графа справа) NULL не считает.")
    spell = ("FROM л LEFT JOIN п ON … WHERE п.id IS NULL — без пары; COUNT(п.id) — пары, "
             "COUNT(*) — строки")
    trap_messages = {
        "rows": "Это все строки склейки — оставь только без пары: WHERE a.id IS NULL.",
        "to": "Это счета без входящих: отправитель в transfers — from_acc, а не to_acc.",
        "idle": "Это счета совсем без переводов, а спрашивали только про исходящие: ON "
                "t.from_acc = a.id.",
        "one": "У этого жителя счёт есть. Если у всех в отчёте не меньше одного — либо INNER "
               "выкинул пустых, либо COUNT(*) посчитал строку склейки: COUNT(a.id).",
        "away": "Этот человек без счетов, но живёт не в {city}: WHERE p.city = '{city}'.",
    }

    def empty_hint(self, line):
        body = _SQ_LITERAL.sub("''", line)
        if re.search(r"\bJOIN\b", body, re.I):
            if not re.search(r"\bLEFT\s+JOIN\b", body, re.I):
                return MSG_INNER_EMPTY
            if re.search(r"HAVING\s+COUNT\(\*\)", body, re.I):
                return MSG_COUNT_STAR
            return MSG_LEFT_ORDER
        return super().empty_hint(line)

    def data_state(self, rng, recs, variant):
        if variant == 1:
            return _idle_senders_state(rng, recs)
        if variant == 2:
            return _lonely_state(rng, recs)
        ppl, accs = recs.tables["people"], recs.tables["accounts"]
        owners = {a["person_id"] for a in accs}
        alone = sum(1 for p in ppl if p["id"] not in owners)
        return dict(answer=alone, traps=[["rows", len(accs) + alone]])


def _idle_senders_state(rng, recs) -> dict:
    """Счета без исходящих: «без входящих» постройкой отличается — счёту без единого перевода
    добавляем входящий (тогда без входящих на один меньше, без исходящих — столько же)."""
    accs, trs = recs.tables["accounts"], recs.tables["transfers"]

    def counts():
        out = {t["from_acc"] for t in trs}
        inc = {t["to_acc"] for t in trs}
        return (sum(1 for a in accs if a["id"] not in out),
                sum(1 for a in accs if a["id"] not in inc))
    no_out, no_in = counts()
    if no_out == no_in:
        senders = {t["from_acc"] for t in trs}
        used = senders | {t["to_acc"] for t in trs}
        idle = rng.choice(sorted(a["id"] for a in accs if a["id"] not in used))
        src = rng.choice(sorted(senders))       # у отправителя исходящие уже были
        trs.append({"id": max(t["id"] for t in trs) + 1, "from_acc": src, "to_acc": idle,
                    "amount": rng.randrange(10, 20000), "ts": "2726-08-20 12:00:00",
                    "note": ""})
        no_out, no_in = counts()
    used = {t["from_acc"] for t in trs} | {t["to_acc"] for t in trs}
    return dict(answer=no_out, traps=[["to", no_in],
                                      ["rows", len(trs) + no_out],
                                      ["idle", sum(1 for a in accs if a["id"] not in used)]])


def _lonely_state(rng, recs) -> dict:
    """Ровно один житель города без счетов: берём человека без счетов, его город — условие;
    другим бессчётным в этом городе даём по счёту."""
    ppl, accs = recs.tables["people"], recs.tables["accounts"]
    owners = {a["person_id"] for a in accs}
    who = rng.choice([p for p in ppl if p["id"] not in owners])
    for p in ppl:
        if p["city"] == who["city"] and p["id"] not in owners and p is not who:
            dbkit.add_account(rng, recs, p["id"], rng.randrange(90000))
    per = Counter(a["person_id"] for a in accs)
    traps = [["one", p["name"]] for p in ppl if p["city"] == who["city"] and per[p["id"]] == 1]
    traps += [["away", p["name"]] for p in ppl if p["city"] != who["city"] and not per[p["id"]]
              and p["name"] != who["name"]]
    return dict(city=who["city"], answer=who["name"], traps=traps)


# --- A4: задачи «сделай» — проверка по состоянию базы и файлов ------------------------------

FILE_CAP = 4 * 1024 * 1024       # отчёт игрока больше 4 МБ — точно не то, что просили


def rows_sha(rows) -> str:
    """Отпечаток набора строк без учёта порядка; значения — строкой (NULL — отдельно): так
    одинаковы и int из генератора, и то, что .import положил в графу ANY."""
    import hashlib
    norm = sorted(tuple("\x00NULL" if v is None else str(v) for v in r) for r in rows)
    return hashlib.sha1(repr(norm).encode("utf-8")).hexdigest()


class _DbTask(base.Task):
    """«Сделай» на records.db: проверка читает базу копией (dbread, у родителя или в
    recheck) и файлы — через sandbox.read_in_box. Ожидание — отпечатки строк (want_sha) и
    метки для объяснений, всё в secret_keys: у родителя, в task.json их нет. Данные варианта
    — чистая функция data_state(rng, recs, variant) -> state; файлы задачи — в state["_files"]
    (их пишет setup, в state они не остаются). reset в песочнице собирает то же байт в байт."""
    track = "db"
    secret_keys = ("want", "want_sha", "orig_sha", "traps", "marks")

    def data_state(self, rng, recs: dbkit.Records, variant: int) -> dict:
        raise NotImplementedError

    def setup_variant(self, box, rng, variant):
        recs = dbkit.records(rng)
        st = self.data_state(rng, recs, variant)
        dbkit.put(box, DB, recs.sqlite())
        for rel, text in sorted((st.pop("_files", None) or {}).items()):
            kit.write(Path(box) / rel, text)
        return st

    def judge(self, ctx, snap) -> Verdict:
        raise NotImplementedError

    def check(self, ctx):
        if sqlite_err():
            return Verdict(False, sqlite_err())
        try:
            with dbread.SqliteSnapshot(ctx.box, DB) as snap:
                v = self.judge(ctx, snap)
        except dbread.Broken as e:
            return Verdict(False, str(e))
        if v.solved or v.message:
            return v
        line = _last_line(ctx)              # молчим — но команда, может, упала по форме
        if "sqlite3" in line:
            hint = line_shape(ctx.box, line) or common_form_hint(line) or self.form_hint(ctx, line)
            if hint:
                return Verdict(False, hint)
        return v

    def form_hint(self, ctx, line: str) -> Optional[str]:
        """Свой отклик задачи по форме последней команды, пока проверка молчит."""
        return None


def sqlite_err() -> Optional[str]:
    return dbread.sqlite_ok()


def _trap(st: dict, key_sha: str) -> Optional[str]:
    """Ключ ловушки, чей отпечаток равен key_sha (state["traps"]: [[ключ, sha], …])."""
    for key, sha in st.get("traps") or ():
        if sha == key_sha:
            return key
    return None


# --- 11. sql_pipe ----------------------------------------------------------------------------

def _csv_cell(v) -> str:
    """Ячейка, как её печатает sqlite3 -csv: NULL — пусто, строка в кавычках, если в ней есть
    пробел, управляющий символ, кавычка (любая) или запятая, или она пустая."""
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s == "" or any(c in "\"',\n\r" or ord(c) <= 32 for c in s):
        return '"' + s.replace('"', '""') + '"'
    return s


def _csv_line(row) -> str:
    return ",".join(_csv_cell(v) for v in row)


MSG_PIPE_HEADER = ("Шапки нет. Нужен -header — и после -csv: «sqlite3 -csv -header …». Перед "
                   "-csv он не держится: -csv выставляет свой вид вывода и шапку сбрасывает.")
MSG_PIPE_LIST = ("Разделитель | — это обычный режим вывода (list). Для CSV нужен флаг -csv: "
                 "«sqlite3 -csv …».")
MSG_PIPE_NO_HEADER = "Шапка тут не нужна: без -header в файле будут одни строки."


class SqlPipe(_DbTask):
    """sqlite3 -csv -header … > файл, вывод в конвейер (| sort | head), режим list с |."""
    id = "sql_pipe"
    title = "Запрос в конвейере"
    par = 75
    scroll = ("sqlite3 -csv -header records.db \"SELECT …\" > report.csv — отчёт в файл: -csv — "
              "через запятую, -header — шапка; ставь его после -csv.\n"
              "Без флагов вывод — режим list: графы через |. Он идёт в трубу, как любой: | sort "
              "| head -3 или | sort | uniq -c.\n"
              "sort -t, -k2 -rn — по второй графе CSV (t — separator, разделитель; k — key, "
              "поле), числами, от большего. cat файл — проверить.")
    variants = (
        Variant("Сделай report.csv — имя и телефон всех людей из города {city}, по алфавиту "
                "имён: через запятую, первой строкой — шапка name,phone.",
                hints=("Отчёт — тот же SELECT, только с флагами вывода и > в файл.",
                       "-csv — через запятую, -header — шапка, после -csv; ORDER BY name — по "
                       "алфавиту.",
                       "sqlite3 -csv -header records.db \"SELECT name, phone FROM people WHERE "
                       "city = '{city}' ORDER BY name\" > report.csv; cat report.csv"),
                solution="sqlite3 -csv -header records.db \"SELECT name, phone FROM people WHERE "
                         "city = '{city}' ORDER BY name\" > report.csv",
                wrong=("sqlite3 -header -csv records.db \"SELECT name, phone FROM people WHERE "
                       "city = '{city}' ORDER BY name\" > report.csv",
                       "sqlite3 -header records.db \"SELECT name, phone FROM people WHERE city = "
                       "'{city}' ORDER BY name\" > report.csv"),
                alternatives=("sqlite3 records.db \".mode csv\" \".headers on\" \"SELECT name, "
                              "phone FROM people WHERE city = '{city}' ORDER BY name\" > "
                              "report.csv — то же точечными командами",)),
        Variant("Сделай top.csv: три счёта с самым большим балансом — id,balance через запятую, "
                "без шапки, от большего. Отсортируй не в запросе, а sort'ом в трубе.",
                hints=("Пусть sqlite3 выдаст все счета в CSV, а сортирует и режет труба.",
                       "sort -t, -k2 -rn — по второй графе, числами, по убыванию; head -3 — три "
                       "первые строки.",
                       "sqlite3 -csv records.db \"SELECT id, balance FROM accounts\" | sort -t, "
                       "-k2 -rn | head -3 > top.csv; cat top.csv"),
                solution="sqlite3 -csv records.db \"SELECT id, balance FROM accounts\" | sort -t, "
                         "-k2 -rn | head -3 > top.csv",
                wrong=("sqlite3 -csv records.db \"SELECT id, balance FROM accounts\" | sort -t, "
                       "-k2 -n | head -3 > top.csv",
                       "sqlite3 -csv records.db \"SELECT id, balance FROM accounts\" | head -3 > "
                       "top.csv"),
                alternatives=("sqlite3 -csv records.db \"SELECT id, balance FROM accounts ORDER "
                              "BY balance DESC LIMIT 3\" > top.csv — сортирует сама база",)),
        Variant("Выпиши в emails.txt почты людей из города {city}: одна почта — одна строка, по "
                "алфавиту, без пустых строк (у кого почты нет — того пропусти).",
                hints=("Одна графа — без флагов, обычный вывод; > пишет его в файл.",
                       "Пустые строки — это '' и NULL: AND email <> '' отсеет обе. ORDER BY email "
                       "— по алфавиту.",
                       "sqlite3 records.db \"SELECT email FROM people WHERE city = '{city}' AND "
                       "email <> '' ORDER BY email\" > emails.txt; cat emails.txt"),
                solution="sqlite3 records.db \"SELECT email FROM people WHERE city = '{city}' AND "
                         "email <> '' ORDER BY email\" > emails.txt",
                wrong=("sqlite3 records.db \"SELECT email FROM people WHERE city = '{city}' ORDER "
                       "BY email\" > emails.txt",
                       "sqlite3 records.db \"SELECT email FROM people WHERE city = '{city}' AND "
                       "email <> ''\" > emails.txt"),
                alternatives=("sqlite3 records.db \"SELECT email FROM people WHERE city = "
                              "'{city}' AND email <> ''\" | sort > emails.txt — по алфавиту "
                              "трубой",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("sqlite3 печатает в stdout, как любая команда: > — в файл, | — в трубу. Флаги "
               "-csv и -header меняют только то, как вывод выглядит, — запрос они не трогают.")
    spell = ("sqlite3 -csv -header ф.db \"SELECT …\" > отчёт.csv; без флагов — графы через |; "
             "| sort -t, -k2 -rn | head -3")

    def form_hint(self, ctx, line):
        if (">" not in line and re.search(r"\bSELECT\b", line, re.I)
                and not _exists(ctx.box, ctx.state["out"])):
            return (f"Вывод — на экране, а задание ждёт файл: допиши > {ctx.state['out']} в "
                    "конце команды.")
        return None

    def data_state(self, rng, recs, variant):
        ppl = recs.tables["people"]
        if variant == 1:
            top = sorted(recs.tables["accounts"], key=lambda a: -a["balance"])[:3]
            return dict(out="top.csv", header=None,
                        want=[_csv_line((a["id"], a["balance"])) for a in top])
        if variant == 2:
            city, mine = _email_city(rng, ppl)
            return dict(out="emails.txt", header=None, city=city, mode="list",
                        want=sorted(p["email"] for p in mine if not dbkit.blank(p["email"])),
                        marks={"raw": ["" if p["email"] is None else p["email"] for p in mine]})
        by = Counter(p["city"] for p in ppl)
        city = rng.choice(sorted(c for c, n in by.items() if n >= 3))
        mine = sorted((p for p in ppl if p["city"] == city), key=lambda p: p["name"])
        return dict(out="report.csv", header="name,phone", city=city,
                    want=["name,phone"] + [_csv_line((p["name"], p["phone"])) for p in mine])

    def check(self, ctx):
        """Только выгрузка: records.db здесь не нужна — испорченная после отчёта база не
        мешает засчитать сделанное (ревью A4 M3)."""
        v = self.judge(ctx, None)
        if v.solved or v.message:
            return v
        line = _last_line(ctx)
        if "sqlite3" in line:
            hint = line_shape(ctx.box, line) or common_form_hint(line) or self.form_hint(ctx, line)
            if hint:
                return Verdict(False, hint)
        return v

    def judge(self, ctx, snap):
        st = ctx.state
        data = sandbox.read_in_box(ctx.box, st["out"], FILE_CAP)
        if data is None:
            return Verdict(False)
        got = data.decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
        while got and got[-1] == "":
            got.pop()
        want = st["want"]
        if got == want:
            return Verdict(True)
        if not got:
            return Verdict(False)
        return Verdict(False, self._why(got, st))

    @staticmethod
    def _why(got, st) -> str:
        want, header = st["want"], st.get("header")
        rows = want[1:] if header else want
        if any("|" in x for x in got):
            return MSG_PIPE_LIST
        if header and got and got[0] != header:
            if re.fullmatch(r"[a-z_]+(?:,[a-z_]+)*", got[0]):
                return (f"Шапка другая: {got[0]}. Нужны ровно графы {header} и в этом порядке — "
                        f"SELECT {header.replace(',', ', ')}.")
            return MSG_PIPE_HEADER
        if not header and got and got[0] in ("id,balance", "email"):
            return MSG_PIPE_NO_HEADER
        if st.get("mode") == "list" and "" in got:
            return ("Пустые строки — это почты '' и NULL (sqlite3 печатает NULL пустым): добавь "
                    "AND email <> ''.")
        body = got[1:] if header else got
        if sorted(body) == sorted(rows):
            if st["out"] == "top.csv":
                return "Строки те, порядок не тот: от большего — sort -t, -k2 -rn."
            return ("Строки те, порядок не тот: по алфавиту — ORDER BY "
                    f"{'name' if header else 'email'}.")
        if st["out"] == "top.csv":
            if len(got) != len(want):
                return f"Строк {len(got)}, а нужно три: | head -3 в конце трубы."
            return ("Это не три самых больших: сортируй по второй графе числами и от большего — "
                    "sort -t, -k2 -rn.")
        return "Строки не те: сверь WHERE с условием задания и перезапиши файл через >."


def _email_city(rng, ppl):
    """Город для emails.txt: у кого-то почты нет ('' или NULL — пустая строка в выводе), а
    порядок строк в таблице не алфавитный — «без ORDER BY» и «без <> ''» не совпадут с
    ответом. Доводим постройкой (данные этого варианта)."""
    by = Counter(p["city"] for p in ppl)
    city = rng.choice(sorted(c for c, n in by.items() if n >= 4 and sum(
        1 for p in ppl if p["city"] == c and not dbkit.blank(p["email"])) >= 3))
    mine = [p for p in ppl if p["city"] == city]
    filled = [p for p in mine if not dbkit.blank(p["email"])]
    if len(filled) == len(mine):
        filled.pop(rng.randrange(len(filled)))["email"] = ""
        filled = [p for p in mine if not dbkit.blank(p["email"])]
    emails = [p["email"] for p in filled]
    if emails == sorted(emails):            # строки таблицы уже по алфавиту — сдвинем первую
        filled[0]["email"] = "zz." + filled[0]["email"]
    return city, mine


# --- 12. import_csv --------------------------------------------------------------------------

MSG_IMPORT_HEADER_ROW = ("Заголовок лёг строкой данных: в существующую таблицу шапка CSV идёт "
                         "как обычная строка — нужен --skip 1. Набери reset и загрузи заново.")
MSG_IMPORT_NO_CSV = ("Без --csv sqlite3 читает файл не как CSV: делит строки по |, запятых не "
                     "видит. Нужно .import --csv …")
MSG_IMPORT_SKIPPED = ("Колонки названы первой строкой данных, а она сама пропала: в НОВУЮ таблицу "
                      "шапка сама становится именами колонок, --skip 1 там лишний. Набери reset "
                      "и загрузи заново.")


class ImportCsv(_DbTask):
    """.import --csv файл таблица: в новую — шапка в имена колонок, в существующую — строкой,
    её убирает --skip 1; проверка — SELECT COUNT(*)."""
    id = "import_csv"
    title = "Загрузка CSV"
    par = 90
    scroll = ("sqlite3 records.db \".import --csv файл.csv таблица\" — загрузить CSV. Таблицы нет — sqlite3 "
              "её создаст, шапка станет именами колонок.\n"
              "Таблица есть — шапка ляжет строкой данных: \".import --csv --skip 1 файл.csv таблица\".\n"
              "Проверить: \"SELECT COUNT(*) FROM таблица\" и \".schema таблица\" — CREATE TABLE с типами: "
              "INTEGER — целое, TEXT — текст.")
    variants = (
        Variant("В new_badges.csv — новые пропуска с шапкой person_id,code. Догрузи их в "
                "существующую таблицу badges базы records.db.",
                hints=("Таблица badges уже есть — её колонки заданы, шапка CSV станет лишней "
                       "строкой.",
                       "В существующую таблицу — .import --csv --skip 1: первую строку файла "
                       "sqlite3 пропустит.",
                       "sqlite3 records.db \".import --csv --skip 1 new_badges.csv badges\" "
                       "\"SELECT COUNT(*) FROM badges\""),
                solution="sqlite3 records.db \".import --csv --skip 1 new_badges.csv badges\"",
                wrong=("sqlite3 records.db \".import --csv new_badges.csv badges\"",
                       "sqlite3 records.db \".import --csv new_badges.csv new_badges\""),
                alternatives=("sqlite3 records.db, а внутри .import --csv --skip 1 new_badges.csv "
                              "badges, затем SELECT COUNT(*) FROM badges; — то же изнутри",)),
        Variant("Загрузи visits.csv (шапка person_id,place,ts) в новую таблицу visits базы "
                "records.db — колонки пусть называются как в шапке.",
                hints=("Таблицы visits ещё нет — sqlite3 создаст её сам.",
                       "В новую таблицу — .import --csv без --skip: шапка станет именами колонок.",
                       "sqlite3 records.db \".import --csv visits.csv visits\" \".schema visits\""),
                solution="sqlite3 records.db \".import --csv visits.csv visits\"",
                wrong=("sqlite3 records.db \".import --csv --skip 1 visits.csv visits\"",
                       "sqlite3 records.db \".import --csv visits.csv visit\""),
                alternatives=("sqlite3 records.db \".import --csv visits.csv visits\" \"SELECT "
                              "COUNT(*) FROM visits\" — и сразу проверка",)),
        Variant("Звонки пришли двумя выгрузками — calls1.csv и calls2.csv, у обеих шапка "
                "person_id,ts,minutes. Сложи обе в одну новую таблицу calls базы records.db.",
                hints=("Первая выгрузка создаёт таблицу, вторая ложится в уже существующую.",
                       "Первая — .import --csv, вторая — .import --csv --skip 1, иначе её шапка "
                       "станет строкой.",
                       "sqlite3 records.db \".import --csv calls1.csv calls\" \".import --csv "
                       "--skip 1 calls2.csv calls\""),
                solution="sqlite3 records.db \".import --csv calls1.csv calls\" \".import --csv "
                         "--skip 1 calls2.csv calls\"",
                wrong=("sqlite3 records.db \".import --csv calls1.csv calls\" \".import --csv "
                       "calls2.csv calls\"",
                       "sqlite3 records.db \".import --csv --skip 1 calls1.csv calls\" \".import "
                       "--csv --skip 1 calls2.csv calls\""),
                alternatives=("sqlite3 records.db \"SELECT COUNT(*) FROM calls\" — после загрузки: "
                              "строк должно быть столько, сколько в обеих без шапок",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = (".import читает CSV строка за строкой. Новой таблице первая строка даёт имена "
               "колонок, а в готовую каждая ляжет данными — вот шапку и пропускают --skip 1.")
    spell = ("sqlite3 ф.db \".import --csv f.csv t\" — в новую; \".import --csv --skip 1 f.csv "
             "t\" — в существующую")

    def form_hint(self, ctx, line):
        for m in re.finditer(r"\.import\s+((?:--\w+\s+(?:\d+\s+)?)*)(\S+)\s+\w+", line):
            if not _exists(ctx.box, m.group(2)):
                return (f"Файла {m.group(2)} нет — .import ничего не загрузил. Как зовут "
                        "выгрузки, покажет ls *.csv.")
            if "--csv" not in m.group(1):
                return MSG_IMPORT_NO_CSV
        return None

    def data_state(self, rng, recs, variant):
        ppl = recs.tables["people"]
        if variant == 0:
            have = {b["person_id"] for b in recs.tables["badges"]}
            codes = {b["code"] for b in recs.tables["badges"]}
            free = sorted(p["id"] for p in ppl if p["id"] not in have)
            new = []
            for pid in rng.sample(free, min(len(free), rng.randint(4, 6))):
                code = f"B-{rng.randrange(10000, 99999)}"
                while code in codes:
                    code = f"B-{rng.randrange(10000, 99999)}"
                codes.add(code)
                new.append({"person_id": pid, "code": code})
            old = [(b["person_id"], b["code"]) for b in recs.tables["badges"]]
            rows = [(b["person_id"], b["code"]) for b in new]
            text = dbkit.csv_text(("person_id", "code"), new)
            return dict(table="badges", cols=["person_id", "code"], new_table=False,
                        want_sha=rows_sha(old + rows), orig_sha=rows_sha(old),
                        traps=[["header", rows_sha(old + rows + [("person_id", "code")])]],
                        marks={"files": ["new_badges.csv"], "n": len(old) + len(rows)},
                        _files={"new_badges.csv": text})
        cols = ("person_id", "place", "ts") if variant == 1 else ("person_id", "ts", "minutes")
        made = _visits(rng, ppl, cols, rng.randint(7, 11))
        if variant == 1:
            files = {"visits.csv": dbkit.csv_text(cols, made)}
            parts = [made]
            table = "visits"
        else:
            cut = rng.randint(3, len(made) - 3)
            parts = [made[:cut], made[cut:]]
            files = {"calls1.csv": dbkit.csv_text(cols, parts[0]),
                     "calls2.csv": dbkit.csv_text(cols, parts[1])}
            table = "calls"
        rows = [tuple(r[c] for c in cols) for r in made]
        traps = [["header", rows_sha(rows + [cols])]]
        return dict(table=table, cols=list(cols), new_table=True, want_sha=rows_sha(rows),
                    traps=traps, marks={"files": sorted(files), "n": len(rows),
                                        "first": [str(v) for v in rows[0]],
                                        "part1": rows_sha([tuple(r[c] for c in cols)
                                                           for r in parts[0]])
                                        if len(parts) > 1 else None},
                    _files=files)

    def judge(self, ctx, snap):
        st = ctx.state
        table, cols = st["table"], st["cols"]
        stray = [t for t in snap.tables() if t not in _BASE_TABLES and t != table.lower()]
        if stray:
            return Verdict(False, f"Загружено в таблицу {stray[0]}, а нужна {table}: имя таблицы "
                                  "— последнее слово после .import. Набери reset.")
        if table.lower() not in snap.tables():
            return Verdict(False)
        have = [c["name"] for c in snap.columns(table)]
        if len(have) == 1 and "," in have[0]:
            return Verdict(False, MSG_IMPORT_NO_CSV + " Набери reset и загрузи заново.")
        if [c.lower() for c in have] != cols:
            if st["new_table"] and [c.lower() for c in have] == [
                    str(v).lower() for v in st["marks"]["first"]]:
                return Verdict(False, MSG_IMPORT_SKIPPED)
            return Verdict(False, f"Колонки таблицы {table} — {', '.join(have)}, а в шапке CSV "
                                  f"— {', '.join(cols)}. Набери reset и загрузи заново.")
        got = rows_sha(snap.rows(table, cols))
        if got == st["want_sha"]:
            return Verdict(True)
        if got in (st.get("orig_sha"), st["marks"].get("part1")):
            return Verdict(False)               # ещё не загружено (или только первая часть)
        if _trap(st, got) == "header":
            return Verdict(False, MSG_IMPORT_HEADER_ROW)
        n = snap.count(table)
        rows = snap.rows(table, cols)
        if len(set(rows)) < len(rows):
            return Verdict(False, "Строки повторяются: одну выгрузку загрузили дважды. Набери "
                                  "reset и загрузи каждую по разу.")
        if n > st["marks"]["n"]:
            return Verdict(False, f"Строк {n} — больше, чем должно быть ({st['marks']['n']}): "
                                  "выгрузка легла дважды или с шапкой. Набери reset и загрузи "
                                  "по одному разу.")
        return Verdict(False, f"Строк {n}, а должно быть {st['marks']['n']}: загрузилось не всё. "
                              "Набери reset и загрузи заново.")


_BASE_TABLES = set(dbkit.COLUMNS)


def _visits(rng, ppl, cols, n):
    """Строки CSV для импорта: без запятых и кавычек, без ведущих нулей (в графе ANY число
    так и останется числом)."""
    out = []
    for _ in range(n):
        day = f"2726-09-{rng.randint(1, 28):02d}"
        r = {"person_id": rng.choice(ppl)["id"], "ts": dbkit._ts(rng, day),
             "place": f"{rng.choice(dbkit.STREETS)} {rng.randint(1, 90)}",
             "minutes": rng.randint(1, 59)}
        out.append(r)
    return out


# --- 13. create_insert -----------------------------------------------------------------------

# вариант: таблица, графы (имя, тип, NOT NULL, PRIMARY KEY, UNIQUE), какие графы заполняет INSERT
_FORMS = {
    0: ("watchlist", (("id", "INTEGER", False, True, False), ("person_id", "INTEGER", True,
                                                               False, False),
                      ("reason", "TEXT", True, False, False)), ("person_id", "reason")),
    1: ("tags", (("code", "TEXT", True, False, True), ("title", "TEXT", True, False, False),
                 ("color", "TEXT", False, False, False)), ("code", "title", "color")),
    2: ("notes", (("id", "INTEGER", False, True, False), ("code", "TEXT", False, False, True),
                  ("body", "TEXT", True, False, False)), ("code", "body")),
}
_REASONS = ("namesake", "debt", "lost badge", "late", "audit")
_TAGS = (("red", "urgent"), ("blue", "archive"), ("green", "checked"), ("gray", "draft"),
         ("gold", "vip"))


class CreateInsert(_DbTask):
    """CREATE TABLE с типами, PRIMARY KEY, NOT NULL, UNIQUE; INSERT INTO t (графы) VALUES."""
    id = "create_insert"
    title = "Своя табличка"
    par = 120
    scroll = ("\"CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT NOT NULL)\" — своя таблица: PRIMARY "
              "KEY — номер строки, NOT NULL — графа обязательная.\n"
              "\"INSERT INTO t (name) VALUES ('a'), ('b')\" — строки, номер база ставит сама; команды — "
              "через ;.\n"
              "NOT NULL constraint failed — база бережёт данные.")
    variants = (
        Variant("Заведи в records.db таблицу watchlist: id — целый первичный ключ, person_id — "
                "целое, обязательное, reason — текст, обязательный. Внеси две строки: человек "
                "{p1} с причиной {r1}, человек {p2} с причиной {r2}.",
                hints=("Сначала CREATE TABLE с графами, потом INSERT INTO; можно одной строкой "
                       "через ;.",
                       "Обязательное — NOT NULL, первичный ключ — INTEGER PRIMARY KEY; id в "
                       "INSERT не пиши — база поставит сама.",
                       "sqlite3 records.db \"CREATE TABLE watchlist (id INTEGER PRIMARY KEY, "
                       "person_id INTEGER NOT NULL, reason TEXT NOT NULL); INSERT INTO watchlist "
                       "(person_id, reason) VALUES ({p1}, '{r1}'), ({p2}, '{r2}')\""),
                solution="sqlite3 records.db \"CREATE TABLE watchlist (id INTEGER PRIMARY KEY, "
                         "person_id INTEGER NOT NULL, reason TEXT NOT NULL); INSERT INTO "
                         "watchlist (person_id, reason) VALUES ({p1}, '{r1}'), ({p2}, '{r2}')\"",
                wrong=("sqlite3 records.db \"CREATE TABLE watchlist (id INTEGER PRIMARY KEY, "
                       "person_id INTEGER, reason TEXT); INSERT INTO watchlist (person_id, "
                       "reason) VALUES ({p1}, '{r1}'), ({p2}, '{r2}')\"",
                       "sqlite3 records.db \"CREATE TABLE watchlist (id INTEGER PRIMARY KEY, "
                       "person_id INTEGER NOT NULL, reason TEXT NOT NULL); INSERT INTO watchlist "
                       "(person_id, reason) VALUES ({p1}, '{r1}')\""),
                alternatives=("sqlite3 records.db, а внутри CREATE TABLE …; INSERT INTO …; и SELECT * "
                              "FROM watchlist; — то же изнутри, с проверкой",)),
        Variant("Заведи в records.db таблицу tags: code — текст, обязательный и без повторов, "
                "title — текст, обязательный, color — текст, можно пустым. «Без повторов» — "
                "ограничение UNIQUE после типа графы. Внеси две строки: {t1} и {t2} (код, "
                "название, цвет).",
                hints=("Без повторов — UNIQUE, обязательное — NOT NULL; у color ограничений нет.",
                       "code TEXT NOT NULL UNIQUE; строки — INSERT INTO tags (code, title, color) "
                       "VALUES (…), (…).",
                       "sqlite3 records.db \"CREATE TABLE tags (code TEXT NOT NULL UNIQUE, title "
                       "TEXT NOT NULL, color TEXT); INSERT INTO tags (code, title, color) VALUES "
                       "{values}\""),
                solution="sqlite3 records.db \"CREATE TABLE tags (code TEXT NOT NULL UNIQUE, "
                         "title TEXT NOT NULL, color TEXT); INSERT INTO tags (code, title, color) "
                         "VALUES {values}\"",
                wrong=("sqlite3 records.db \"CREATE TABLE tags (code TEXT NOT NULL, title TEXT "
                       "NOT NULL, color TEXT); INSERT INTO tags (code, title, color) VALUES "
                       "{values}\"",
                       "sqlite3 records.db \"CREATE TABLE tags (code TEXT UNIQUE, title TEXT, "
                       "color TEXT); INSERT INTO tags (code, title, color) VALUES {values}\""),
                alternatives=("sqlite3 records.db \".schema tags\" — после CREATE: видно, все ли "
                              "ограничения на месте",)),
        Variant("Заведи в records.db таблицу notes: id — целый первичный ключ, code — текст без "
                "повторов (ограничение UNIQUE после типа), body — текст, обязательный. Внеси две "
                "строки: код {c1} с текстом {b1}, код {c2} с текстом {b2}.",
                hints=("Первичный ключ — INTEGER PRIMARY KEY, без повторов — UNIQUE, обязательное "
                       "— NOT NULL.",
                       "id в INSERT не нужен: INSERT INTO notes (code, body) VALUES ('…', '…'), "
                       "('…', '…').",
                       "sqlite3 records.db \"CREATE TABLE notes (id INTEGER PRIMARY KEY, code "
                       "TEXT UNIQUE, body TEXT NOT NULL); INSERT INTO notes (code, body) VALUES "
                       "('{c1}', '{b1}'), ('{c2}', '{b2}')\""),
                solution="sqlite3 records.db \"CREATE TABLE notes (id INTEGER PRIMARY KEY, code "
                         "TEXT UNIQUE, body TEXT NOT NULL); INSERT INTO notes (code, body) VALUES "
                         "('{c1}', '{b1}'), ('{c2}', '{b2}')\"",
                wrong=("sqlite3 records.db \"CREATE TABLE notes (id INTEGER PRIMARY KEY, code "
                       "TEXT, body TEXT NOT NULL); INSERT INTO notes (code, body) VALUES ('{c1}', "
                       "'{b1}'), ('{c2}', '{b2}')\"",
                       "sqlite3 records.db \"CREATE TABLE notes (id INTEGER, code TEXT UNIQUE, "
                       "body TEXT NOT NULL); INSERT INTO notes (code, body) VALUES ('{c1}', "
                       "'{b1}'), ('{c2}', '{b2}')\""),
                alternatives=("sqlite3 records.db \"SELECT * FROM notes\" — после INSERT: id "
                              "проставлены сами",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Ограничения — правила, за которыми база следит сама: NOT NULL не пустит пустое, "
               "UNIQUE — повтор, PRIMARY KEY даст каждой строке свой номер. «constraint failed» — "
               "это база тебя прикрыла, а не сломалась.")
    spell = ("CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT NOT NULL UNIQUE); INSERT INTO t (a) "
             "VALUES ('x'), ('y')")

    def form_hint(self, ctx, line):
        body = _SQ_LITERAL.sub("''", line)
        if re.search(r"\bCREATE\s+TABLE\b[^;]*\bINSERT\b", body, re.I):
            return ("Две команды SQL в одной строке — через ;: CREATE TABLE …; INSERT INTO …. "
                    "Без ; sqlite3 не понял, где кончается первая.")
        if re.search(r"\bINSERT\s+INTO\s+\w+\s+VALUES\b", body, re.I):
            return ("INSERT без списка граф ждёт значения для всех граф, и для id тоже. Назови "
                    "графы: INSERT INTO таблица (графа, графа) VALUES …")
        return None

    def data_state(self, rng, recs, variant):
        table, cols, fill = _FORMS[variant]
        ppl = recs.tables["people"]
        if variant == 0:
            p1, p2 = rng.sample([p["id"] for p in ppl], 2)
            r1, r2 = rng.sample(_REASONS, 2)
            rows, extra = [(p1, r1), (p2, r2)], dict(p1=p1, p2=p2, r1=r1, r2=r2)
        elif variant == 1:
            picked = rng.sample(_TAGS, 2)
            rows = [(f"T{rng.randint(10, 99)}{i}", title, color)
                    for i, (color, title) in enumerate(picked)]
            extra = dict(values=", ".join(f"('{a}', '{b}', '{c}')" for a, b, c in rows),
                         **{f"t{i + 1}": f"{a} {b} {c}" for i, (a, b, c) in enumerate(rows)})
        else:
            c1, c2 = (f"N-{x}" for x in rng.sample(range(100, 999), 2))
            b1, b2 = rng.sample(("call back", "check id", "new phone", "moved", "paid"), 2)
            rows, extra = [(c1, b1), (c2, b2)], dict(c1=c1, c2=c2, b1=b1, b2=b2)
        return dict(extra, table=table, want_sha=rows_sha(rows),
                    marks={"cols": [list(c) for c in cols], "fill": list(fill), "n": len(rows)})

    def judge(self, ctx, snap):
        st = ctx.state
        table, marks = st["table"], st["marks"]
        if table in snap.views():
            return Verdict(False, f"{table} — представление (VIEW), а нужна таблица: sqlite3 "
                                  f"records.db \"DROP VIEW {table}\", потом CREATE TABLE.")
        if table not in snap.tables():
            return Verdict(False)
        problem = _schema_problem(snap, table, marks["cols"])
        if problem:
            return Verdict(False, problem + " Поправь: sqlite3 records.db \"DROP TABLE "
                                            f"{table}\" — и CREATE заново (или reset).")
        rows = snap.rows(table, marks["fill"])
        if not rows:
            return Verdict(False)               # таблица есть, строк ещё нет — работа идёт
        if rows_sha(rows) == st["want_sha"]:
            return Verdict(True)
        if len(rows) < marks["n"]:
            return Verdict(False, f"Строк {len(rows)}, а нужно {marks['n']}: внеси остальные "
                                  "INSERT INTO.")
        if len(rows) > marks["n"]:
            return Verdict(False, f"Строк {len(rows)}, а нужно {marks['n']}: лишние убери "
                                  f"(DELETE FROM {table} WHERE …) или начни заново (reset).")
        return Verdict(False, "Строки не те: сверь значения с заданием — текст в одинарных "
                              "кавычках, графы в INSERT в том же порядке, что и значения.")


def _schema_problem(snap, table: str, spec) -> Optional[str]:
    """Чего не хватает в CREATE TABLE (графы, типы, ограничения) — или None."""
    have = {c["name"].lower(): c for c in snap.columns(table)}
    names = [c[0] for c in spec]
    for name in names:
        if name not in have:
            return f"В таблице {table} нет графы {name}."
    extra = sorted(set(have) - set(names))
    if extra:
        return f"В таблице {table} лишняя графа {extra[0]}."
    unique = {tuple(i["columns"]) for i in snap.indexes(table) if i["unique"]}
    for name, typ, notnull, pk, uniq in spec:
        c = have[name]
        if typ == "INTEGER" and "INT" not in c["type"]:
            return f"Графа {name} — целое: тип INTEGER, а у тебя {c['type'] or 'без типа'}."
        if typ == "TEXT" and not any(k in c["type"] for k in ("TEXT", "CHAR", "CLOB")):
            return f"Графа {name} — текст: тип TEXT, а у тебя {c['type'] or 'без типа'}."
        if pk and not c["pk"]:
            return f"Графа {name} — первичный ключ: нужен PRIMARY KEY."
        if not pk and c["pk"]:
            return f"PRIMARY KEY стоит на {name}, а в задании его там нет."
        if notnull and not c["notnull"]:
            return (f"Графа {name} без NOT NULL: база молча примет пустое значение, а в задании "
                    "графа обязательная.")
        if uniq and (name,) not in unique:
            return f"Графа {name} без UNIQUE: повтор пройдёт молча, а в задании — без повторов."
    return None


# --- 14. backup_update -----------------------------------------------------------------------

PEOPLE = dbkit.COLUMNS["people"]
BACKUP = "backup/records.db"
MSG_NO_BACKUP = ("Правка сделана, а копии нет: сначала копия, потом правка. Набери reset — и по "
                 "порядку: mkdir -p backup, .backup, потом UPDATE.")
MSG_LATE_BACKUP = ("Копия уже с правкой — её сделали после UPDATE, вернуть по ней нечего. Набери "
                   "reset и сделай копию до правки.")
MSG_ALL_ROWS = ("Задеты все {n} строк: UPDATE без WHERE. Верни базу из копии: cp backup/records.db "
                "records.db (или reset) — и сначала SELECT с тем же WHERE.")
MSG_ALL_NO_COPY = "Задеты все {n} строк: UPDATE без WHERE, а копии нет — только reset."


def _people_sha(rows) -> str:
    return rows_sha(rows)


def _snap_people(box, rel):
    """Строки people файла rel песочницы (None — файла нет, Broken — не база)."""
    if not _exists(box, rel):
        return None
    with dbread.SqliteSnapshot(box, rel) as snap:
        return snap.rows("people", PEOPLE)


MSG_BACKUP_BROKEN = ("Копия backup/records.db повреждена — это не база, по ней ничего не "
                     "вернуть. Набери reset и сделай копию заново: .backup или cp, до правки.")
MSG_BACKUP_FILE = ("backup — это файл, а не папка: cp без папки назвал копию «backup». Убери "
                   "его (rm backup), потом mkdir -p backup и копию — в неё.")


def _is_file(box, rel) -> bool:
    """rel — обычный файл (не папка) внутри песочницы."""
    return _exists(box, rel)


def _exists(box, rel) -> bool:
    import os
    fd = sandbox.open_in_box(box, rel, dbread.DB_CAP)
    if fd is None:
        return False
    os.close(fd)
    return True


class BackupUpdate(_DbTask):
    """Копия до правки (.backup или cp), SELECT с тем же WHERE, UPDATE … SET … WHERE, changes();
    UPDATE без WHERE меняет всё — вернуть из копии; журнал правок пишет триггер."""
    id = "backup_update"
    title = "Правка с копией"
    par = 120
    scroll = ("Сначала копия: mkdir -p backup и sqlite3 records.db \".backup backup/records.db\" "
              "(или cp records.db backup/).\n"
              "Потом SELECT с тем же WHERE — кого заденет. Правка: UPDATE people SET графа = "
              "'значение' WHERE …; SELECT changes() — сколько строк задето.\n"
              "UPDATE без WHERE меняет ВСЕ строки; вернуть — cp backup/records.db records.db. "
              "Каждую правку людей пишет журнал audit_log.")
    variants = (
        Variant("Всех людей из города {city} со статусом inactive переведи в archived (графа "
                "status таблицы people). Правка — только с копией: backup/records.db, до неё.",
                hints=("Порядок: копия, проверочный SELECT, правка. Копия — .backup в папку "
                       "backup.",
                       "Два условия — WHERE city = '{city}' AND status = 'inactive'; сначала "
                       "посмотри их SELECT'ом.",
                       "mkdir -p backup && sqlite3 records.db \".backup backup/records.db\" && "
                       "sqlite3 records.db \"UPDATE people SET status = 'archived' WHERE city = "
                       "'{city}' AND status = 'inactive'\""),
                solution="mkdir -p backup && sqlite3 records.db \".backup backup/records.db\" && "
                         "sqlite3 records.db \"UPDATE people SET status = 'archived' WHERE city = "
                         "'{city}' AND status = 'inactive'\"",
                wrong=("sqlite3 records.db \"UPDATE people SET status = 'archived' WHERE city = "
                       "'{city}' AND status = 'inactive'\"",
                       "mkdir -p backup && sqlite3 records.db \".backup backup/records.db\" && "
                       "sqlite3 records.db \"UPDATE people SET status = 'archived' WHERE status = "
                       "'inactive'\""),
                alternatives=("sqlite3 records.db \"SELECT id, name FROM people WHERE city = "
                              "'{city}' AND status = 'inactive'\" — до правки: кого заденет",)),
        Variant("У {name} из города {city} новый телефон — {phone}. Исправь графу phone в "
                "people. Тёзки есть; копия до правки — backup/records.db.",
                hints=("Копия, потом SELECT — один ли человек под условием, потом UPDATE.",
                       "Тёзку отсечёт второе условие: WHERE name = '{name}' AND city = '{city}'.",
                       "mkdir -p backup && cp records.db backup/ && sqlite3 records.db \"UPDATE "
                       "people SET phone = '{phone}' WHERE name = '{name}' AND city = '{city}'\""),
                solution="mkdir -p backup && cp records.db backup/ && sqlite3 records.db \"UPDATE "
                         "people SET phone = '{phone}' WHERE name = '{name}' AND city = '{city}'\"",
                wrong=("mkdir -p backup && cp records.db backup/ && sqlite3 records.db \"UPDATE "
                       "people SET phone = '{phone}' WHERE name = '{name}'\"",
                       "sqlite3 records.db \"UPDATE people SET phone = '{phone}' WHERE name = "
                       "'{name}' AND city = '{city}'\" && mkdir -p backup && cp records.db "
                       "backup/"),
                alternatives=("sqlite3 records.db \"UPDATE people SET phone = '{phone}' WHERE "
                              "id = {pid}\" — после копии; по id ещё надёжнее (id найди SELECT'ом)",)),
        Variant("Город {old} переименован в {new}: перепиши графу city у всех, кто записан в "
                "{old}. Копию — до правки, в backup/records.db.",
                hints=("Копия, SELECT — сколько их, потом UPDATE с тем же WHERE.",
                       "UPDATE people SET city = '{new}' WHERE city = '{old}'; без WHERE "
                       "переедут все.",
                       "mkdir -p backup && sqlite3 records.db \".backup backup/records.db\" && "
                       "sqlite3 records.db \"UPDATE people SET city = '{new}' WHERE city = "
                       "'{old}'\""),
                solution="mkdir -p backup && sqlite3 records.db \".backup backup/records.db\" && "
                         "sqlite3 records.db \"UPDATE people SET city = '{new}' WHERE city = "
                         "'{old}'\"",
                wrong=("mkdir -p backup && sqlite3 records.db \".backup backup/records.db\" && "
                       "sqlite3 records.db \"UPDATE people SET city = '{new}'\"",
                       "mkdir -p backup && sqlite3 records.db \"UPDATE people SET city = '{new}' "
                       "WHERE city = '{old}'\" \".backup backup/records.db\""),
                alternatives=("sqlite3 records.db \"SELECT COUNT(*) FROM people WHERE city = "
                              "'{old}'\" — до правки; changes() после должен совпасть",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("UPDATE меняет все строки, что подошли под WHERE, — и не переспрашивает. Так что "
               "сначала копия (будет откуда вернуть), потом SELECT с тем же WHERE (глянь, кого "
               "заденет) — и только потом правка.")
    spell = ("mkdir -p backup; sqlite3 ф.db \".backup backup/ф.db\"; UPDATE t SET к = 'x' WHERE "
             "…; cp backup/ф.db ф.db — вернуть")

    def data_state(self, rng, recs, variant):
        ppl = recs.tables["people"]
        if variant == 1:
            a, b = rng.choice(dbkit.namesakes(recs))
            if rng.random() < 0.5:
                a, b = b, a
            used = {p["phone"] for p in ppl}
            phone = dbkit._phone(rng, used)
            targets, col, value = [a["id"]], "phone", phone
            extra = dict(name=a["name"], city=a["city"], phone=phone, pid=a["id"])
            traps = {"namesake": [a["id"], b["id"]]}
        elif variant == 2:
            by = Counter(p["city"] for p in ppl)
            old = rng.choice(sorted(c for c, n in by.items() if n >= 2))
            new = rng.choice(sorted(set(dbkit.CITIES + ("tomsk", "kirov", "penza")) - set(by)))
            targets, col, value = [p["id"] for p in ppl if p["city"] == old], "city", new
            extra, traps = dict(old=old, new=new), {}
        else:
            city, inactive = _inactive_city(rng, ppl)
            targets, col, value = [p["id"] for p in inactive], "status", "archived"
            extra = dict(city=city)
            traps = {"allcities": [p["id"] for p in ppl if p["status"] == "inactive"],
                     "allstatus": [p["id"] for p in ppl if p["city"] == city
                                   and p["status"] != "archived"]}
        orig = [tuple(p[c] for c in PEOPLE) for p in ppl]      # после доводки варианта
        k = PEOPLE.index(col)
        want = [r[:k] + (value,) + r[k + 1:] if r[0] in targets else r for r in orig]
        return dict(extra, col=col, value=value, orig_sha=_people_sha(orig),
                    want_sha=_people_sha(want),
                    marks={"targets": sorted(targets), "n": len(orig), "traps": traps,
                           "orig": {str(r[0]): r[k] for r in orig}})

    def judge(self, ctx, snap):
        st = ctx.state
        cur = snap.rows("people", PEOPLE)
        now = _people_sha(cur)
        try:
            back = _snap_people(ctx.box, BACKUP)
            broken = False
        except dbread.Broken:
            back, broken = None, True
        back_sha = _people_sha(back) if back is not None else None
        if back is None and _is_file(ctx.box, "backup"):
            return Verdict(False, MSG_BACKUP_FILE)
        if broken and now != st["orig_sha"]:
            return Verdict(False, MSG_BACKUP_BROKEN)
        if now == st["orig_sha"]:
            return Verdict(False)                   # правки ещё нет (или база возвращена)
        if now == st["want_sha"]:
            if back_sha == st["orig_sha"]:
                return Verdict(True)
            return Verdict(False, MSG_LATE_BACKUP if back_sha == st["want_sha"] else MSG_NO_BACKUP)
        return Verdict(False, self._why(cur, st, back_sha == st["orig_sha"]))

    @staticmethod
    def _why(cur, st, have_copy: bool) -> str:
        marks, col, value = st["marks"], st["col"], st["value"]
        k = PEOPLE.index(col)
        orig = marks["orig"]
        changed = sorted(r[0] for r in cur if str(r[0]) in orig and r[k] != orig[str(r[0])])
        back = (" Верни базу из копии: cp backup/records.db records.db." if have_copy else
                " Копии нет — только reset.")
        if len(cur) == marks["n"] and all(r[k] == value for r in cur):
            return (MSG_ALL_ROWS if have_copy else MSG_ALL_NO_COPY).format(n=marks["n"])
        targets = set(marks["targets"])
        if set(changed) > targets:
            if set(changed) == set(marks["traps"].get("namesake", ())):
                return "Задет и тёзка из другого города: уточни AND city = '{}'.".format(
                    st.get("city")) + back
            if set(changed) == set(marks["traps"].get("allcities", ())):
                return ("Задеты inactive из всех городов: забыто AND city = '{}'.".format(
                    st.get("city")) + back)
            if set(changed) == set(marks["traps"].get("allstatus", ())):
                return ("Задеты все жители {} — и не только inactive: забыто AND status = "
                        "'inactive'.".format(st.get("city")) + back)
            return f"Задеты лишние строки ({len(changed) - len(targets)}): WHERE шире нужного." + back
        if set(changed) < targets or not changed:
            return ("Задеты не все нужные строки: сверь WHERE с условием (SELECT с тем же WHERE "
                    "покажет, кого он берёт).")
        if any(r[k] != value for r in cur if r[0] in targets):
            return f"Значение не то: нужно {col} = '{value}' — ровно так, в одинарных кавычках."
        return "Изменено не то: правится только графа " + col + "." + back


def _inactive_city(rng, ppl):
    """Город, где не меньше двух inactive, есть не-inactive жители, и inactive есть в других
    городах — «без города» и «без статуса» задевают лишнее. Доводим постройкой."""
    by = Counter(p["city"] for p in ppl)
    city = rng.choice(sorted(c for c, n in by.items() if n >= 4))
    mine = [p for p in ppl if p["city"] == city]
    rng.shuffle(mine)
    while sum(1 for p in mine if p["status"] == "inactive") < 2:
        next(p for p in mine if p["status"] != "inactive")["status"] = "inactive"
    if all(p["status"] == "inactive" for p in mine):
        mine[0]["status"] = "active"
    if not any(p["status"] == "inactive" for p in ppl if p["city"] != city):
        rng.choice([p for p in ppl if p["city"] != city])["status"] = "inactive"
    return city, [p for p in ppl if p["city"] == city and p["status"] == "inactive"]


# --- 15. tx_delete ---------------------------------------------------------------------------

MSG_DELETED_ALL = ("Удалено всё: DELETE без WHERE. Вот зачем BEGIN — до COMMIT такое отменяет "
                   "ROLLBACK. Набери reset и начни с BEGIN.")
MSG_TX_INSIDE = ("Таблица не изменилась. Если внутри sqlite> был BEGIN — без COMMIT; при выходе "
                 "всё откатилось само. Зайди снова: BEGIN; DELETE …; SELECT changes(); и COMMIT; "
                 "до .quit.")
_TX = {0: ("transfers", dbkit.COLUMNS["transfers"]), 1: ("accounts", dbkit.COLUMNS["accounts"]),
       2: ("audit_log", dbkit.COLUMNS["audit_log"])}


class TxDelete(_DbTask):
    """BEGIN; DELETE … WHERE …; SELECT changes(); ROLLBACK или COMMIT. Подзапрос IN (SELECT …)."""
    id = "tx_delete"
    title = "Транзакция"
    par = 120
    scroll = ("BEGIN; DELETE FROM t WHERE …; SELECT changes(); — сколько удалено. Не то — ROLLBACK;, то — "
              "COMMIT;.\n"
              "Подзапрос — SELECT в скобках вместо списка: \"DELETE FROM t WHERE id NOT IN (SELECT …)\".\n"
              "Одной строкой: sqlite3 records.db \"BEGIN; …; COMMIT;\". Внутри sqlite> COMMIT; — до .quit.")
    variants = (
        Variant("В transfers затесались проверочные переводы — с заметкой ровно test (графа "
                "note). Удали их, и только их, одной транзакцией.",
                hints=("Ровно test — это =, а не LIKE: шаблон зацепит и похожие заметки.",
                       "BEGIN; DELETE FROM transfers WHERE note = 'test'; SELECT changes(); — "
                       "число сошлось — COMMIT;.",
                       "sqlite3 records.db \"BEGIN; DELETE FROM transfers WHERE note = 'test'; "
                       "SELECT changes(); COMMIT;\""),
                solution="sqlite3 records.db \"BEGIN; DELETE FROM transfers WHERE note = 'test'; "
                         "SELECT changes(); COMMIT;\"",
                wrong=("sqlite3 records.db \"BEGIN; DELETE FROM transfers WHERE note LIKE "
                       "'%test%'; SELECT changes(); COMMIT;\"",
                       "sqlite3 records.db \"BEGIN; DELETE FROM transfers; SELECT changes(); "
                       "COMMIT;\""),
                alternatives=("sqlite3 records.db, а внутри по строке: BEGIN; DELETE …; SELECT "
                              "changes(); COMMIT; — по шагам, с правом на ROLLBACK",)),
        Variant("Удали из accounts закрытые счета (status = 'closed'), по которым не было ни "
                "одного перевода — ни исходящего, ни входящего. Одной транзакцией.",
                hints=("Счёт без переводов — его id нет ни в from_acc, ни в to_acc таблицы "
                       "transfers.",
                       "id NOT IN (SELECT from_acc FROM transfers) AND id NOT IN (SELECT to_acc "
                       "FROM transfers), плюс status.",
                       "sqlite3 records.db \"BEGIN; DELETE FROM accounts WHERE status = 'closed' "
                       "AND id NOT IN (SELECT from_acc FROM transfers) AND id NOT IN (SELECT "
                       "to_acc FROM transfers); SELECT changes(); COMMIT;\""),
                solution="sqlite3 records.db \"BEGIN; DELETE FROM accounts WHERE status = "
                         "'closed' AND id NOT IN (SELECT from_acc FROM transfers) AND id NOT IN "
                         "(SELECT to_acc FROM transfers); SELECT changes(); COMMIT;\"",
                wrong=("sqlite3 records.db \"BEGIN; DELETE FROM accounts WHERE status = "
                       "'closed'; SELECT changes(); COMMIT;\"",
                       "sqlite3 records.db \"BEGIN; DELETE FROM accounts WHERE status = "
                       "'closed' AND id NOT IN (SELECT from_acc FROM transfers); SELECT "
                       "changes(); COMMIT;\""),
                alternatives=("sqlite3 records.db \"SELECT COUNT(*) FROM accounts WHERE status = "
                              "'closed' AND id NOT IN (SELECT from_acc FROM transfers) AND id NOT "
                              "IN (SELECT to_acc FROM transfers)\" — сначала сосчитать",)),
        Variant("В журнале правок audit_log некоторые записи задвоились: тот же detail и тот же "
                "ts. Удали лишние копии, у каждой пары оставь запись с меньшим id. Одной "
                "транзакцией. Наименьший id каждой пары даёт SELECT MIN(id) FROM audit_log "
                "GROUP BY detail, ts — это те, кто остаётся.",
                hints=("Оставить надо по одной записи на пару detail и ts — с наименьшим id; "
                       "остальные удалить.",
                       "Наименьший id каждой группы — SELECT MIN(id) … GROUP BY detail, ts; "
                       "удаляй всех, кого нет в этом списке: NOT IN.",
                       "sqlite3 records.db \"BEGIN; DELETE FROM audit_log WHERE id NOT IN (SELECT "
                       "MIN(id) FROM audit_log GROUP BY detail, ts); SELECT changes(); COMMIT;\""),
                solution="sqlite3 records.db \"BEGIN; DELETE FROM audit_log WHERE id NOT IN "
                         "(SELECT MIN(id) FROM audit_log GROUP BY detail, ts); SELECT changes(); "
                         "COMMIT;\"",
                wrong=("sqlite3 records.db \"BEGIN; DELETE FROM audit_log WHERE id NOT IN (SELECT "
                       "MAX(id) FROM audit_log GROUP BY detail, ts); SELECT changes(); COMMIT;\"",
                       "sqlite3 records.db \"BEGIN; DELETE FROM audit_log WHERE id IN (SELECT "
                       "MIN(id) FROM audit_log GROUP BY detail, ts); SELECT changes(); COMMIT;\""),
                alternatives=("sqlite3 records.db \"SELECT detail, ts, COUNT(*) FROM audit_log GROUP "
                              "BY detail, ts HAVING COUNT(*) > 1\" — сначала посмотреть пары",
                              "склейка журнала с самим собой: audit_log a JOIN audit_log b ON "
                              "b.detail = a.detail AND b.ts = a.ts AND b.id > a.id — b.id и есть "
                              "копии")),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Транзакция — черновик: всё между BEGIN и COMMIT отменяет ROLLBACK. changes() "
               "скажет, сколько строк задето, — глянул и решил: COMMIT или ROLLBACK.")
    spell = ("BEGIN; DELETE FROM t WHERE …; SELECT changes(); ROLLBACK; или COMMIT; — id IN "
             "(SELECT …)")

    def form_hint(self, ctx, line):
        body = _SQ_LITERAL.sub("''", line)
        if (re.search(r"\bBEGIN\b", body, re.I)
                and not re.search(r"\b(?:COMMIT|ROLLBACK|END)\b", body, re.I)):
            return ("BEGIN без COMMIT: sqlite3 закрылся, и транзакция откатилась сама — ничего не "
                    "удалено. Допиши COMMIT; в конце, когда changes() сошлось.")
        try:
            words = shlex.split(line)
        except ValueError:
            words = []
        # A7 п. 9: работали внутри sqlite> (голый sqlite3 файл.db), а таблица цела — проверка
        # молчит только так (правки нет); BEGIN без COMMIT при выходе откатился сам
        if words[:1] == ["sqlite3"] and len([w for w in words[1:] if not w.startswith("-")]) == 1:
            return MSG_TX_INSIDE
        return None

    def data_state(self, rng, recs, variant):
        table, cols = _TX[variant]
        rows = recs.tables[table]
        if variant == 0:
            gone = {r["id"] for r in rows if r["note"] == dbkit.TEST_NOTE}
            traps = {"like": {r["id"] for r in rows if dbkit.like(r["note"], "%test%")}}
        elif variant == 1:
            trs = recs.tables["transfers"]
            out = {t["from_acc"] for t in trs}
            inc = {t["to_acc"] for t in trs}
            closed = [a for a in rows if a["status"] == "closed"]
            if not any(a["id"] in inc and a["id"] not in out for a in closed):
                _only_incoming(rng, recs, closed, out, inc)
                out = {t["from_acc"] for t in trs}
                inc = {t["to_acc"] for t in trs}
            gone = {a["id"] for a in closed if a["id"] not in out and a["id"] not in inc}
            traps = {"closed": {a["id"] for a in closed},
                     "from_only": {a["id"] for a in closed if a["id"] not in out}}
        else:
            _same_detail_later(rng, rows)
            first = {}
            for r in sorted(rows, key=lambda r: r["id"]):
                first.setdefault((r["detail"], r["ts"]), r["id"])
            gone = {r["id"] for r in rows if first[(r["detail"], r["ts"])] != r["id"]}
            keys = {(r["detail"], r["ts"]) for r in rows if r["id"] in gone}
            last = {}
            for r in sorted(rows, key=lambda r: r["id"]):
                last[(r["detail"], r["ts"])] = r["id"]
            by_detail = {}
            for r in sorted(rows, key=lambda r: r["id"]):
                by_detail.setdefault(r["detail"], r["id"])
            traps = {"both": {r["id"] for r in rows if (r["detail"], r["ts"]) in keys},
                     "detail_only": {r["id"] for r in rows if by_detail[r["detail"]] != r["id"]},
                     "max": {r["id"] for r in rows if last[(r["detail"], r["ts"])] != r["id"]},
                     "in": set(first.values())}
        tup = [tuple(r[c] for c in cols) for r in rows]
        return dict(table=table, orig_sha=rows_sha(tup),
                    want_sha=rows_sha([t for t in tup if t[0] not in gone]),
                    marks={"gone": sorted(gone), "ids": sorted(t[0] for t in tup),
                           "cols": list(cols),
                           "traps": {k: sorted(v) for k, v in traps.items()}})

    def judge(self, ctx, snap):
        st = ctx.state
        marks = st["marks"]
        cur = snap.rows(st["table"], marks["cols"])
        sha = rows_sha(cur)
        if sha == st["want_sha"]:
            return Verdict(True)
        if sha == st["orig_sha"]:
            return Verdict(False)                   # ещё не удаляли (или откатили ROLLBACK)
        if not cur:
            return Verdict(False, MSG_DELETED_ALL)
        have = {r[0] for r in cur}
        gone = set(marks["gone"])
        removed = set(marks["ids"]) - have
        traps = {k: set(v) for k, v in marks["traps"].items()}
        if removed == traps.get("like"):
            return Verdict(False, "Удалено больше нужного: LIKE '%test%' цепляет и contest. "
                                  "Ровно test — это note = 'test'. Набери reset.")
        if removed == traps.get("closed"):
            return Verdict(False, "Удалены и закрытые счета с переводами: нужны только те, чьих "
                                  "id нет в transfers — NOT IN (SELECT …). Набери reset.")
        if removed == traps.get("from_only"):
            return Verdict(False, "Удалены и счета, которые только получали: проверь и to_acc — "
                                  "второй NOT IN (SELECT to_acc FROM transfers). Набери reset.")
        if removed == traps.get("both"):
            return Verdict(False, "Удалены обе записи пары: у каждой оставь меньший id — его даёт "
                                  "MIN(id) … GROUP BY detail, ts. Набери reset.")
        if removed == traps.get("detail_only"):
            return Verdict(False, "Удалена и правка с тем же detail, но в другое время — это не "
                                  "копия. Группируй по обоим: GROUP BY detail, ts. Набери reset.")
        if removed == traps.get("max"):
            return Verdict(False, "Удалены оригиналы, а копии остались: оставить нужно меньший "
                                  "id — MIN(id), а не MAX(id). Набери reset.")
        if removed == traps.get("in"):
            return Verdict(False, "Удалено ровно то, что надо было оставить: по одной записи на "
                                  "группу. Список MIN(id) — тех, кто остаётся, удаляй всех, кого "
                                  "в нём нет: NOT IN. Набери reset.")
        if removed > gone:
            return Verdict(False, f"Удалено больше нужного ({len(removed)} строк): WHERE шире, чем "
                                  "надо. Набери reset — и сначала SELECT changes() до COMMIT.")
        if removed < gone:
            return Verdict(False, "Удалено не всё нужное: сверь WHERE с условием.")
        return Verdict(False, "Удалено не то: сверь WHERE с условием. Набери reset.")


def _same_detail_later(rng, rows) -> None:
    """Та же правка (detail), но в другое время — не копия: одной записи без пары даём detail
    другой такой же. Тогда «GROUP BY detail» без ts удалит лишнее (данные этого варианта)."""
    pairs = Counter((r["detail"], r["ts"]) for r in rows)
    single = [r for r in sorted(rows, key=lambda r: r["id"]) if pairs[(r["detail"], r["ts"])] == 1]
    a, b = rng.sample(single, 2)
    b["detail"] = a["detail"]


def _only_incoming(rng, recs, closed, out, inc):
    """Есть закрытый счёт, который только получал: «NOT IN только from_acc» удалит лишнее.
    Берём закрытый без переводов вовсе и направляем на него один перевод (их хватает:
    MIN_IDLE_CLOSED ≥ 3, после этого без переводов остаётся ≥ 2)."""
    idle = sorted(a["id"] for a in closed if a["id"] not in out and a["id"] not in inc)
    acc = rng.choice(idle)
    t = rng.choice([t for t in recs.tables["transfers"] if t["to_acc"] != acc
                    and t["from_acc"] != acc])
    t["to_acc"] = acc


# --- страж: boss_db ---------------------------------------------------------------------------

AUDIT = dbkit.COLUMNS["audit_log"]
BOSS_FIELDS = ("status", "phone", "city")
OLD_TXT = "report/old.txt"
# переезд журнал правок пишет ещё и отдельным правилом: правка города — две строки журнала
MOVE_TRIGGER = ("CREATE TRIGGER people_move AFTER UPDATE OF city ON people BEGIN INSERT INTO "
                "audit_log (ts, actor, action, tbl, row_id, detail) VALUES (strftime("
                "'%Y-%m-%d %H:%M:%S', 'now'), 'termit', 'move', 'people', OLD.id, OLD.city || "
                "'>' || NEW.city); END")
BOSS_HISTORY = 2            # столько старых строк журнала о цели (чужие правки, их не трогать)
# правила журнала в базе стража (во всех вариантах): удалить их — не замести след, а выключить журнал
BOSS_TRIGGERS = (("people_audit", "people"), ("people_move", "people"))


def _sql_shape(sql: str) -> str:
    """Текст правила для сравнения: пробелы схлопнуты, регистр и «;» в конце не важны."""
    return re.sub(r"\s+", " ", str(sql or "")).strip().rstrip(";").strip().casefold()


# исходные тексты правил журнала: пустое правило под тем же именем — тоже выключенный журнал
BOSS_TRIGGER_SQL = {"people_audit": _sql_shape(dbkit.SCHEMA[-1]),
                    "people_move": _sql_shape(MOVE_TRIGGER)}

MSG_BOSS_NAMESAKE = ("Правка ушла тёзке — склеивай по id пропуска: имя у владельца {code} не "
                     "одно на базу. Правь WHERE id = …, тёзку верни из копии или reset.")
MSG_BOSS_ALL = ("Задеты все строки — UPDATE без WHERE, копия тебя спасёт: cp backup/records.db "
                "records.db, потом правка WHERE id = ….")
MSG_BOSS_ALL_NO_COPY = "Задеты все строки — UPDATE без WHERE, а копии нет: только reset."
MSG_BOSS_EXTRA = ("Задеты лишние строки people ({n}): правка шире одного владельца пропуска. "
                  "Верни из копии (cp backup/records.db records.db) или reset.")
MSG_BOSS_VALUE = ("У владельца пропуска {code} поле {field} не то: нужно {field} = '{new}' — "
                  "ровно так, в одинарных кавычках.")
MSG_BOSS_OTHER_FIELD = ("Изменена не та графа: подменить нужно только {field}. Верни из копии "
                        "или reset.")
MSG_BOSS_NO_COPY = ("Правка сделана, а копии нет: сначала копия, потом правка. Набери reset — и "
                    "по порядку: mkdir -p backup, .backup backup/records.db, потом UPDATE.")
MSG_BOSS_LATE = ("Копия сделана после правки — в ней уже не исходные данные, вернуть по ней "
                 "нечего. Набери reset и сделай копию первой.")
MSG_BOSS_FOREIGN = ("Ты стёр и чужие строки журнала — так и палятся: удалять можно только то, "
                    "что дописала твоя правка (они последние, ORDER BY id DESC). Набери reset.")
MSG_BOSS_TRIGGER = ("Журнал выключен — это заметнее строки: без правила журнала (DROP TRIGGER) "
                    "пропажу увидят сразу. Верни базу из копии (cp backup/records.db records.db) "
                    "или reset, и убери только свои строки журнала.")
MSG_BOSS_OLD_NEW = ("В report/old.txt новое значение, а нужно старое — то, что было до правки. "
                    "Его помнит копия: SELECT из backup/records.db.")
MSG_BOSS_OLD_NAMESAKE = ("В report/old.txt значение тёзки, а нужно владельца пропуска {code}: "
                         "ищи его через badges, по id.")
MSG_BOSS_LEFT = ("В журнале ещё есть строки о твоей правке ({n}): одна правка может дописать не "
                 "одну. Посмотри последние — ORDER BY id DESC LIMIT 3.")
MSG_BOSS_OLD = ("В report/old.txt нужно старое значение графы {field} владельца пропуска {code} "
                "— одно значение, как в базе до правки.")


class BossDb(_DbTask):
    """Страж Картотеки: тихо подменить одну запись. Цель — по коду пропуска (JOIN badges →
    people, у цели есть тёзка), копия до правки, UPDATE по id, строки журнала правок о своей
    правке — удалить (чужие — не трогать), старое значение — в report/old.txt.
    A — status, B — phone, C — city (журнал пишет две строки: people_audit и people_move).
    Всё уже было: JOIN — join_inner, .backup и UPDATE — backup_update, DELETE — tx_delete,
    ORDER BY … DESC LIMIT — order_limit, IN (…) — in_between, > файл и mkdir -p — раньше.
    Проверка — по состоянию базы, копии и файла; ответы и отпечатки — в secret_keys."""
    id = "boss_db"
    title = "Подмена записи"
    boss = True
    par = 480
    secret_keys = _DbTask.secret_keys + ("pid", "name", "aid", "aid2", "nid", "old", "audit_sha")
    scroll = ("Чей пропуск — JOIN по id: \"SELECT p.id FROM people p JOIN badges b ON b.person_id "
              "= p.id\" и WHERE по коду. Копия — .backup backup/records.db.\n"
              "Правь по id: \"UPDATE people SET графа = 'x' WHERE id = N\". Старое — SELECT до "
              "правки > report/old.txt.\n"
              "Журнал: \"SELECT * FROM audit_log ORDER BY id DESC LIMIT 3\"; свои строки — "
              "\"DELETE FROM audit_log WHERE id IN (N, M)\".")
    steps = ("backup/records.db — копия базы до правки",
             "Запись подменена: у владельца пропуска из задания нужное поле — новое, у остальных "
             "ничего не изменилось",
             "Следы заметены: строк журнала о твоей правке нет, чужие строки журнала целы",
             "report/old.txt — старое значение поля (до правки)")
    # те же шаги с кодом и графой рана (steps_for); поля — только открытые ключи state
    STEP_TEMPLATES = (steps[0],
                      "Запись подменена: у владельца пропуска {code} поле {field} = {new}, у "
                      "остальных ничего не изменилось",
                      steps[2],
                      "report/old.txt — старое значение поля {field} (до правки)")
    _COPY = "mkdir -p backup report && sqlite3 records.db \".backup backup/records.db\" && "
    _OLD = ("sqlite3 records.db \"SELECT p.{field} FROM people p JOIN badges b ON b.person_id = "
            "p.id WHERE b.code = '{code}'\" > report/old.txt && ")
    _SET = "sqlite3 records.db \"UPDATE people SET {field} = '{new}' WHERE id = {pid}\" && "
    _ONE = "sqlite3 records.db \"DELETE FROM audit_log WHERE id = {aid}\""
    _TWO = "sqlite3 records.db \"DELETE FROM audit_log WHERE id IN ({aid}, {aid2})\""
    _HINT_FIND = ("Сначала копия: mkdir -p backup report и .backup backup/records.db. Владельца "
                  "пропуска найдёт JOIN people и badges: ON b.person_id = p.id.")
    _HINT_SET = ("Старое значение — SELECT до правки, > report/old.txt. Правь по id, не по "
                 "имени: тёзки. Потом — SELECT id, row_id, detail FROM audit_log ORDER BY id DESC "
                 "LIMIT 3.")
    # последняя подсказка — без готового номера строки, как у других стражей (аудит A7)
    _HINT_ONE = ("Твоя строка журнала — последняя: sqlite3 records.db \"DELETE FROM audit_log "
                 "WHERE id = <номер>\", вместо <номер> — её id из ORDER BY id DESC LIMIT 3")
    _HINT_TWO = ("Переезд пишет две строки, обе последние: \"DELETE FROM audit_log WHERE id IN "
                 "(<номер>, <номер>)\" — их id покажет ORDER BY id DESC LIMIT 3")
    variants = (
        Variant("Нужно тихо подменить запись в records.db: владельцу пропуска {code} (таблица "
                "badges) поставь status = '{new}'. Остальных не трогай. Сначала копия, "
                "старое значение — в отчёт; правку пишет журнал audit_log — убери из него свой "
                "след, чужой не тронь.",
                hints=(_HINT_FIND, _HINT_SET,
                       _HINT_ONE),
                solution=_COPY + _OLD + _SET + _ONE,
                wrong=(_OLD + _SET + _ONE,
                       _COPY + _OLD + "sqlite3 records.db \"UPDATE people SET status = '{new}' "
                       "WHERE name = '{name}'\" && " + _ONE,
                       _COPY + _OLD + _SET + "sqlite3 records.db \"DELETE FROM audit_log WHERE "
                       "row_id = {pid}\"",
                       _COPY + _SET + _OLD + _ONE),
                alternatives=("sqlite3 records.db \"DELETE FROM audit_log WHERE actor = "
                              "'termit'\" — твои правки журнал пишет от имени termit",)),
        Variant("В records.db надо подменить телефон: у владельца пропуска {code} (таблица "
                "badges) phone должен стать {new}. Тёзки есть — не перепутай. Копия до правки, "
                "старый номер — в отчёт, а след правки в журнале audit_log — убрать, не задев "
                "чужих строк.",
                hints=(_HINT_FIND, _HINT_SET,
                       _HINT_ONE),
                solution=_COPY + _OLD + _SET + _ONE,
                wrong=(_COPY + _OLD + "sqlite3 records.db \"UPDATE people SET phone = '{new}'\" "
                       "&& " + _ONE,
                       _COPY + _OLD + "sqlite3 records.db \"UPDATE people SET phone = '{new}' "
                       "WHERE name = '{name}'\" && " + _ONE,
                       _COPY + _OLD + _SET + "sqlite3 records.db \"DELETE FROM audit_log WHERE "
                       "tbl = 'people'\"",
                       _SET + _COPY + _OLD + _ONE),
                alternatives=("sqlite3 backup/records.db \"SELECT phone FROM people WHERE id = "
                              "{pid}\" > report/old.txt — старое значение и после правки помнит "
                              "копия",)),
        Variant("Владелец пропуска {code} (таблица badges) по бумагам должен жить в городе "
                "{new}: подмени ему city в records.db, остальных не трогай. Копия до правки, "
                "старый город — в отчёт. Переезд журнал audit_log пишет не одной строкой — "
                "убери все свои, чужие оставь.",
                hints=(_HINT_FIND, _HINT_SET,
                       _HINT_TWO),
                solution=_COPY + _OLD + _SET + _TWO,
                wrong=(_COPY + _OLD + _SET + _ONE,
                       _COPY + _OLD + "sqlite3 records.db \"UPDATE people SET city = '{new}' "
                       "WHERE name = '{name}'\" && " + _TWO,
                       _COPY + _OLD + _SET + "sqlite3 records.db \"DELETE FROM audit_log WHERE "
                       "row_id = {pid}\"",
                       _COPY + _SET + _OLD + _TWO),
                alternatives=("sqlite3 records.db \"DELETE FROM audit_log WHERE id > {nid}\" — "
                              "всё, что дописано после последней старой строки",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Подмена по правилам: нашёл цель по ключу (код пропуска → id, а не имя), снял "
               "копию, сохранил старое значение, правил по id и вычистил из журнала ровно то, что "
               "дописала твоя правка. Честная правка идёт тем же порядком: копия, SELECT, UPDATE.")
    spell = ("JOIN по id → UPDATE … WHERE id = N; SELECT … FROM audit_log ORDER BY id DESC LIMIT "
             "3 → DELETE … WHERE id = N")

    def steps_for(self, state):
        try:
            return [s.format(**state) for s in self.STEP_TEMPLATES]
        except (KeyError, IndexError):
            return list(self.steps)

    def setup_variant(self, box, rng, variant):
        recs = dbkit.records(rng)
        st = self.data_state(rng, recs, variant)
        dbkit.put(box, DB, dbkit.build_sqlite(dbkit.SCHEMA + (MOVE_TRIGGER,), recs.rows()))
        return st

    def data_state(self, rng, recs, variant):
        field = BOSS_FIELDS[variant % len(BOSS_FIELDS)]
        a, b = rng.choice(dbkit.namesakes(recs))
        if rng.random() < 0.5:
            a, b = b, a
        ppl = recs.tables["people"]
        if field == "status":
            new = rng.choice(sorted(set(dbkit.PEOPLE_STATUSES) - {a["status"], b["status"]}))
        elif field == "phone":
            new = dbkit._phone(rng, {p["phone"] for p in ppl})
        else:
            new = rng.choice(sorted(set(dbkit.CITIES) - {a["city"], b["city"]}))
        code = next(x["code"] for x in recs.tables["badges"] if x["person_id"] == a["id"])
        audit = recs.tables["audit_log"]
        pairs = Counter((r["detail"], r["ts"]) for r in audit)
        plain = [r for r in sorted(audit, key=lambda r: r["id"])
                 if pairs[(r["detail"], r["ts"])] == 1 and r["row_id"] != a["id"]]
        for r in rng.sample(plain, BOSS_HISTORY):        # чужие правки о цели: row_id — не след
            r["row_id"] = a["id"]
        orig = [tuple(p[c] for c in PEOPLE) for p in ppl]
        k = PEOPLE.index(field)
        want = [r[:k] + (new,) + r[k + 1:] if r[0] == a["id"] else r for r in orig]
        nid = max(r["id"] for r in audit)
        return dict(code=code, field=field, new=new, name=a["name"], pid=a["id"], old=a[field],
                    nid=nid, aid=nid + 1, aid2=nid + 2,
                    orig_sha=_people_sha(orig), want_sha=_people_sha(want),
                    audit_sha=rows_sha([tuple(r[c] for c in AUDIT) for r in audit]),
                    marks={"n": len(orig), "namesake": b["id"], "nold": b[field],
                           "history": sum(1 for r in audit if r["row_id"] == a["id"]),
                           "audit_ids": sorted(r["id"] for r in audit),
                           "orig": {str(r[0]): list(r) for r in orig}})

    # --- шаги: (готово, ключ отклика или None) -----------------------------------------------

    def _step_copy(self, ctx, edited: bool):
        st = ctx.state
        try:
            back = _snap_people(ctx.box, BACKUP)
        except dbread.Broken:
            return False, MSG_BACKUP_BROKEN
        if back is None:
            if _is_file(ctx.box, "backup"):
                return False, MSG_BACKUP_FILE
            return False, MSG_BOSS_NO_COPY if edited else None
        if _people_sha(back) == st["orig_sha"]:
            return True, None
        return False, MSG_BOSS_LATE

    def _step_edit(self, cur, st, have_copy: bool):
        sha = _people_sha(cur)
        if sha == st["want_sha"]:
            return True, None
        if sha == st["orig_sha"]:
            return False, None
        marks, field, new = st["marks"], st["field"], st["new"]
        k = PEOPLE.index(field)
        orig = marks["orig"]
        if len(cur) == marks["n"] and all(r[k] == new for r in cur):
            return False, MSG_BOSS_ALL if have_copy else MSG_BOSS_ALL_NO_COPY
        changed = {r[0] for r in cur if list(r) != orig.get(str(r[0]))}
        changed |= {int(i) for i in orig} - {r[0] for r in cur}
        if marks["namesake"] in changed:
            return False, MSG_BOSS_NAMESAKE
        if changed - {st["pid"]}:
            return False, MSG_BOSS_EXTRA.format(n=len(changed - {st["pid"]}))
        mine = next((r for r in cur if r[0] == st["pid"]), None)
        if mine is not None and mine[k] != new:
            return False, MSG_BOSS_VALUE
        return False, MSG_BOSS_OTHER_FIELD

    @staticmethod
    def _step_traces(audit, triggers, st, edited: bool, bodies=None):
        """Исходные строки журнала — все на месте и как были (id — ключ, повторов нет);
        дописанных правкой не осталось; оба правила журнала (people_audit, people_move) на
        месте и с исходным текстом — удалить их или подменить пустыми значит выключить
        журнал, а не замести след (A5-review M1, A7). До правки шаг не засчитан."""
        ids = set(st["marks"]["audit_ids"])
        if rows_sha([r for r in audit if r[0] in ids]) != st["audit_sha"]:
            return False, MSG_BOSS_FOREIGN
        have = {(str(n).lower(), str(t).lower()) for n, t in triggers}
        if not set(BOSS_TRIGGERS) <= have:
            return False, MSG_BOSS_TRIGGER
        if bodies is not None and any(_sql_shape(bodies.get(name)) != sql
                                      for name, sql in BOSS_TRIGGER_SQL.items()):
            return False, MSG_BOSS_TRIGGER
        if not edited:
            return False, None
        return rows_sha(audit) == st["audit_sha"], None

    def _step_old(self, ctx):
        raw = sandbox.read_in_box(ctx.box, OLD_TXT, FILE_CAP)
        if raw is None:
            return False, None
        text, st = raw.decode("utf-8", errors="replace"), ctx.state
        if textnorm.same_text(text, str(st["old"]), case_sensitive=True):
            return True, None
        if textnorm.same_text(text, str(st["new"]), case_sensitive=True):
            return False, MSG_BOSS_OLD_NEW
        if st["marks"]["nold"] != st["old"] and textnorm.same_text(
                text, str(st["marks"]["nold"]), case_sensitive=True):
            return False, MSG_BOSS_OLD_NAMESAKE
        return False, MSG_BOSS_OLD

    def _steps(self, ctx, snap):
        st = ctx.state
        cur = snap.rows("people", PEOPLE)
        audit = snap.rows("audit_log", AUDIT)
        edited = _people_sha(cur) != st["orig_sha"]
        copy = self._step_copy(ctx, edited)
        edit = self._step_edit(cur, st, copy[0])
        traces = self._step_traces(audit, snap.triggers(), st, edit[0], snap.trigger_sql())
        return [copy, edit, traces, self._step_old(ctx)]

    def progress(self, ctx):
        try:
            with dbread.SqliteSnapshot(ctx.box, DB) as snap:
                return [ok for ok, _ in self._steps(ctx, snap)]
        except dbread.Broken:
            return [False] * len(self.steps)

    def judge(self, ctx, snap):
        steps = self._steps(ctx, snap)
        base.memo_marks(ctx, [ok for ok, _ in steps])
        if all(ok for ok, _ in steps):
            return Verdict(True)
        copy, edit, traces, old = steps
        for ok, msg in (edit, copy, traces, old):       # правка шире цели — важнее всего
            if not ok and msg:
                return Verdict(False, msg.format(**ctx.state))
        if edit[0] and not traces[0] and re.search(r"\bDELETE\b.*\baudit_log\b",
                                                   _last_line(ctx), re.I):
            # чистил журнал, но не всё: сколько дописанных правкой строк ещё на месте
            ids = set(ctx.state["marks"]["audit_ids"])
            left = sum(1 for r in snap.rows("audit_log", ("id",)) if r[0] not in ids)
            return Verdict(False, MSG_BOSS_LEFT.format(n=left))
        return Verdict(False)


# --- пара csv_sql (duckdb) ---------------------------------------------------------------------

SALES = "sales.csv"
SALES_COLS = ("id", "date", "city", "customer", "amount", "status")
SALES_STATUSES = ("paid", "new", "refund")
_IMPORT = "sqlite3 :memory: -cmd \".import --csv sales.csv t\" "


def _sales(rng) -> List[dict]:
    """Выгрузка продаж: латиница, целые суммы, без кавычек и запятых в полях."""
    cities = rng.sample(dbkit.CITIES, rng.randint(6, 8))
    out = []
    for i in range(1, rng.randint(90, 140) + 1):
        out.append({"id": i, "date": dbkit._date(rng, "2726-04-01", "2726-09-30"),
                    "city": rng.choice(cities), "customer": f"c-{rng.randint(100, 399)}",
                    "amount": rng.randint(100, 9000),
                    "status": rng.choices(SALES_STATUSES, (70, 20, 10))[0]})
    return out


def _sums(rows) -> Counter:
    c = Counter()
    for r in rows:
        c[r["city"]] += r["amount"]
    return c


class CsvSql(_DbAnswer):
    """Пара к duckdb (после import_csv и стража): вопрос к CSV на SQL. Встроенный путь —
    база в памяти: sqlite3 :memory: -cmd ".import --csv f t" "SELECT …"; утилита —
    duckdb -c "SELECT … FROM 'f.csv'" (CSV читает сама, графы с типами)."""
    id = "csv_sql"
    title = "Запрос к таблице"
    implant = "duckdb"
    after = ("import_csv", "boss_db")
    par = 90
    scroll = ("sqlite3 :memory: — база в памяти, без файла. Флаг -cmd (command) выполнит "
              "команду до запроса: -cmd \".import --csv sales.csv t\" — CSV в таблицу t, шапка "
              "— графы.\n"
              "Целиком: sqlite3 :memory: -cmd \".import --csv f.csv t\" \"SELECT …\".\n"
              "Утилита duckdb спрашивает CSV сама, как таблицу: duckdb -c \"SELECT SUM(amount) "
              "FROM 'sales.csv'\"")
    variants = (
        Variant("В sales.csv — продажи за полгода. Сколько денег принесли продажи в городе "
                "{city}? Сложи колонку amount по всем его строкам, статус не важен. Ответ: ans "
                "NUMBER",
                hints=("Базы нет — есть CSV. sqlite3 :memory: заведёт базу в памяти, а -cmd "
                       "\".import --csv sales.csv t\" загрузит файл.",
                       "Дальше обычный запрос к t: SUM(amount) и WHERE city = '{city}'.",
                       _IMPORT + "\"SELECT SUM(amount) FROM t WHERE city = '{city}'\" — "
                       "утилитой: duckdb -c \"SELECT SUM(amount) FROM 'sales.csv' WHERE city = "
                       "'{city}'\""),
                solution=_IMPORT + "\"SELECT SUM(amount) FROM t WHERE city = '{city}'\"",
                implant_script="duckdb -noheader -list -c \"SELECT SUM(amount) FROM "
                               "'sales.csv' WHERE city = '{city}'\"",
                wrong=(_IMPORT + '"SELECT SUM(amount) FROM t"',),
                alternatives=("sqlite3 sales.db \".import --csv sales.csv t\" — то же в файл: "
                              "база останется на диске",)),
        Variant("По sales.csv: из какого города больше всего денег — по сумме amount всех его "
                "продаж? Ответ — город, как в таблице: ans CITY",
                hints=("Загрузи CSV в базу в памяти: sqlite3 :memory: -cmd \".import --csv "
                       "sales.csv t\".",
                       "Сводка по городам: GROUP BY city, сортировка по SUM(amount) — DESC, "
                       "сверху самый денежный; LIMIT 1.",
                       _IMPORT + "\"SELECT city FROM t GROUP BY city ORDER BY SUM(amount) DESC "
                       "LIMIT 1\" — утилитой: duckdb, тот же запрос к 'sales.csv'"),
                solution=_IMPORT + "\"SELECT city FROM t GROUP BY city ORDER BY SUM(amount) DESC "
                         "LIMIT 1\"",
                implant_script="duckdb -noheader -list -c \"SELECT city FROM 'sales.csv' GROUP BY "
                               "city ORDER BY SUM(amount) DESC LIMIT 1\"",
                wrong=(_IMPORT + '"SELECT city FROM t GROUP BY city ORDER BY SUM(amount) LIMIT 1"',
                       _IMPORT + '"SELECT city FROM t GROUP BY city ORDER BY COUNT(*) DESC LIMIT '
                       '1"'),
                alternatives=("duckdb -c \"SELECT city, SUM(amount) FROM 'sales.csv' GROUP BY "
                              "city ORDER BY 2 DESC\" — вся сводка сразу; ORDER BY 2 — по второй графе",)),
        Variant("Сколько в sales.csv продаж со статусом {status} на сумму больше {limit}? Сумма "
                "— колонка amount, статус — status. Ответ: ans NUMBER",
                hints=("CSV — в базу в памяти: sqlite3 :memory: -cmd \".import --csv sales.csv "
                       "t\", потом запрос.",
                       "Два условия: status = '{status}' AND amount > {limit} — «больше», не «не "
                       "меньше». Считает COUNT(*).",
                       _IMPORT + "\"SELECT COUNT(*) FROM t WHERE status = '{status}' AND amount "
                       "> {limit}\" — утилитой: duckdb, тот же запрос к 'sales.csv'"),
                solution=_IMPORT + "\"SELECT COUNT(*) FROM t WHERE status = '{status}' AND "
                         "amount > {limit}\"",
                implant_script="duckdb -noheader -list -c \"SELECT COUNT(*) FROM 'sales.csv' "
                               "WHERE status = '{status}' AND amount > {limit}\"",
                wrong=(_IMPORT + "\"SELECT COUNT(*) FROM t WHERE status = '{status}' AND amount "
                       ">= {limit}\"",
                       _IMPORT + '"SELECT COUNT(*) FROM t WHERE amount > {limit}"'),
                alternatives=("duckdb -c \"SELECT COUNT(*) FROM 'sales.csv' WHERE status = "
                              "'{status}' AND amount > {limit}\"",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    implant_script = variants[0].implant_script
    explain = ("SQL годится и для CSV: sqlite3 :memory: держит файл в базе, пока идёт одна "
               "команда, а -cmd запускает .import до запроса. duckdb читает CSV сам и сам "
               "угадывает типы граф — запрос короче, файл цел.")
    spell = "sqlite3 :memory: -cmd \".import --csv f.csv t\" \"SELECT …\" — SQL к CSV без базы"
    trap_messages = {
        "all": "Это сумма по всем городам — забыто условие WHERE city = '{city}'.",
        "low": "Это город с самой маленькой суммой: по умолчанию сортировка по возрастанию — "
               "нужен DESC.",
        "count": "Это город, где больше всего продаж, а спрашивали деньги: сортируй по "
                 "SUM(amount), а не по COUNT(*).",
        "max": "Это город самой крупной продажи (MAX), а спрашивали все деньги города: "
               "сортируй по сумме — SUM(amount).",
        "ge": "Попали продажи ровно на {limit}: «больше» — это >, а не >=.",
        "nostatus": "Это продажи всех статусов — забыто status = '{status}'.",
    }

    def setup_variant(self, box, rng, variant):
        rows = self.data_rows(rng, variant)
        st = rows.pop()
        kit.write(Path(box) / SALES, dbkit.csv_text(SALES_COLS, rows))
        return dict(st, sources=base.sources(box, SALES))

    def data_rows(self, rng, variant):
        """Строки CSV и (последним элементом) state варианта — чистая функция зерна."""
        rows = _sales(rng)
        if variant == 1:
            # лидер по деньгам (lead) и лидер по числу продаж (busy) — разные города
            lead, busy = rng.sample(sorted({r["city"] for r in rows}), 2)
            counts = Counter(r["city"] for r in rows)
            while counts[busy] - max(v for c, v in counts.items() if c != busy) < 2:
                r = rng.choice([r for r in rows if r["city"] not in (lead, busy)])
                counts[r["city"]] -= 1
                r["city"], r["amount"] = busy, rng.randint(100, 600)
                counts[busy] += 1
            sums = _sums(rows)
            while sums[lead] - max(v for c, v in sums.items() if c != lead) < 500:
                r = rng.choice([r for r in rows if r["city"] == lead])
                bump = rng.randint(300, 2000)
                r["amount"] += bump
                sums[lead] += bump
            # A7 (аудит п. 10): самая крупная продажа — в третьем городе, не у лидера, не у
            # самого бедного и не у лидера по числу; ORDER BY MAX(amount) лидера не даст
            poor = min(sorted(sums), key=lambda c: sums[c])
            big = rng.choice(sorted(c for c in sums if c not in (lead, busy, poor)))
            peak_row = rng.choice([r for r in rows if r["city"] == big])
            peak_row["amount"] = max(r["amount"] for r in rows) + rng.randint(50, 400)
            sums = _sums(rows)
            # запас лидера вернём, срезая продажи второго города (не саму крупную): так ни
            # счёт продаж, ни самая крупная продажа не меняются
            while True:
                second = max(sorted(c for c in sums if c != lead), key=lambda c: sums[c])
                need = 500 - (sums[lead] - sums[second])
                if need <= 0:
                    break
                r = max((r for r in rows if r["city"] == second and r is not peak_row
                         and r["amount"] > 100), key=lambda r: (r["amount"], r["id"]))
                cut = min(r["amount"] - 100, need)
                r["amount"] -= cut
                sums[second] -= cut
            low = min(sorted(sums), key=lambda c: sums[c])
            if sorted(sums.values())[1] - sums[low] < 2:  # самый бедный — тоже один
                rng.choice([r for r in rows if r["city"] == low])["amount"] -= 2
            sums = _sums(rows)
            low = min(sorted(sums), key=lambda c: sums[c])
            traps = ([["low", low]] + ([["count", busy]] if busy != low else []) +
                     [["max", big]])
            return rows + [{"answer": lead, "traps": traps}]
        if variant == 2:
            status = rng.choice(("paid", "new"))
            limit = rng.choice((3000, 4000, 5000))
            mine = [r for r in rows if r["status"] == status]
            rng.choice(mine)["amount"] = limit             # ровно на границе — есть
            others = [r for r in rows if r["status"] != status and r["amount"] <= limit]
            rng.shuffle(others)
            while True:                    # чужой статус выше границы: «без status» — больше,
                others.pop()["amount"] = limit + rng.randint(1, 900)   # и не равно «>=»
                n = sum(1 for r in rows if r["status"] == status and r["amount"] > limit)
                ge = sum(1 for r in rows if r["status"] == status and r["amount"] >= limit)
                every = sum(1 for r in rows if r["amount"] > limit)
                if every != ge:
                    break
            return rows + [{"status": status, "limit": limit, "answer": n,
                            "traps": [["ge", ge], ["nostatus", every]]}]
        sums = _sums(rows)
        city = rng.choice(sorted(sums))
        return rows + [{"city": city, "answer": sums[city],
                        "traps": [["all", sum(sums.values())]]}]


TASKS = [SqliteOpen(), SelectWhere(), OrderLimit(), DistinctLike(), InBetween(),
         NullCoalesce(), GroupCount(), GroupHaving(), JoinInner(), JoinLeft(),
         SqlPipe(), ImportCsv(), CreateInsert(), BackupUpdate(), TxDelete(), CsvSql(), BossDb()]
