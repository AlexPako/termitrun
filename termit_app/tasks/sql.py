"""Трек «SQL и PostgreSQL» (часть 9б, «Хранилище»): поручения на учебной базе vault.

Движок задачи (план части 9, «Два трека, два движка»; dbkit.choose_engine): задачи стенда
(stand = "pg") — только PostgreSQL, без него недоступны (missing, без штрафа); общие задачи и
страж — PostgreSQL, если стенд годен и решена psql_pipe, иначе SQLite (файл vault.db).

Основа трека (пачка B1): данные кладутся по движку (put_vault), сервер PostgreSQL — сервис
родителя (Task.service → pgkit.PgService, сид — секрет состояния: в task.json его нет),
снимок для проверки — dbread.snapshot (SQLite-файл или текстовый снимок PostgreSQL).

Поручения (B2 — задачи 1–5): данные варианта — чистая функция data_state(rng, data, variant)
→ state без песочницы (её же гоняют гарантии «единственного ответа» на 2000 зёрнах,
tests/test_sql_traps.py). Отклики — по ФОРМЕ сделанного (команда psql или sqlite3, запрос в
кавычках, схема таблицы, сравнение времени с полночью), ловушка — только при точном равенстве
сданного её значению. Порядок в TASKS — порядок обучения."""
import dataclasses
import re
import shlex
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from termit_app import dbread, pgkit, sandbox, textnorm
from termit_app.tasks import base, db, dbkit, kit
from termit_app.tasks.base import Variant, Verdict

DB = dbkit.VAULT_DB
SEED_KEY = "seed_sql"          # сид PostgreSQL в состоянии — только у родителя (secret_keys)


class VaultMixin:
    """Общее у задач Хранилища: движок, данные, сервер, снимок."""
    track = "sql"
    stand: Optional[str] = None

    def missing(self, root=None) -> Optional[str]:
        """Задаче стенда без годного PostgreSQL — причина (pgkit.why_not: сокет меряется в
        корне рана root, без него — в корне текущего рана); общим — ничего."""
        if self.stand == "pg":
            return pgkit.why_not(root)
        return None

    @staticmethod
    def engine_of(state: dict) -> str:
        e = (state or {}).get(dbkit.ENGINE_KEY)
        return e if e in dbkit.ENGINES else dbkit.DEFAULT_ENGINE

    def put_vault(self, box: Path, data: "dbkit.Vault") -> dict:
        """Положить базу по движку этой сборки (dbkit.current_engine — его задаёт make_state):
        SQLite — файл vault.db в песочнице; PostgreSQL — сид в состояние (сервер поднимет
        родитель). Вернуть поля текстов ({db}, {run}, {month}) и сид."""
        engine = dbkit.current_engine()
        st = dict(dbkit.engine_fields(engine))
        if engine == "pg":
            st[SEED_KEY] = data.pg_seed()
        else:
            dbkit.put(box, DB, data.sqlite())
        return st

    def service(self, box: Path, state: dict):
        """PostgreSQL — свой сервер задачи (pgkit.PgService); SQLite — без сервиса."""
        if self.engine_of(state) != "pg":
            return None
        return pgkit.PgService(box, str(state[SEED_KEY]))

    def snapshot(self, ctx: base.Ctx):
        """Снимок базы для проверки (with): по движку из состояния родителя."""
        return dbread.snapshot(ctx, DB)



class VaultData:
    """Данные варианта поручений B2+: общая база vault, свои таблицы задачи (extend), затем
    data_state — чистая функция зерна; база кладётся по движку уже после неё."""

    def data_state(self, rng, data: "dbkit.Vault", variant: int) -> dict:
        """Состояние варианта по строкам базы (их можно доправить здесь же: база строится
        после). Чистая функция зерна — без песочницы."""
        return {}

    def vault_of(self, rng) -> "dbkit.Vault":
        return self.extend(rng, dbkit.vault(rng))

    def extend(self, rng, data: "dbkit.Vault") -> "dbkit.Vault":
        """Свои таблицы задачи поверх общей базы (по умолчанию — ничего)."""
        return data

    def engine_texts(self, engine: str, state: dict) -> dict:
        """Поля текстов задачи, разные для движков (B4: {load} — загрузка файла командами,
        {explain}) — сверх общих {db}, {run}, {month}."""
        return {}

    def setup_variant(self, box, rng, variant):
        data = self.vault_of(rng)
        st = self.data_state(rng, data, variant)
        files = st.pop("_files", None) or {}
        st.update(self.put_vault(Path(box), data))
        st.update(self.engine_texts(dbkit.current_engine(), st))
        for rel, text in sorted(files.items()):     # файлы задачи (B4) — reset пишет те же
            kit.write(Path(box) / rel, text)
        if dbkit.current_engine() != "pg" and isinstance(self, base.AnswerTask):
            st["sources"] = base.sources(box, DB)      # файл с ответом стёрли — reset
        return st


class VaultAnswer(VaultMixin, base.AnswerTask):
    """«Найди и назови» на базе vault: ответ и сид — у родителя."""
    secret_keys = base.AnswerTask.secret_keys + ("totals", SEED_KEY)


class VaultTask(VaultMixin, base.Task):
    """«Сделай» на базе vault: ожидание и сид — у родителя, проверка — по снимку."""
    secret_keys = ("want", "want_sha", "orig_sha", "traps", "marks", SEED_KEY)


# --- Отклики по форме команды (psql и sqlite3) ----------------------------------------------

CLIENTS = ("psql", "sqlite3")

MSG_CMD_ANSWER = ("Сдаётся не команда, а то, что она напечатала: запусти запрос, потом ans и "
                  "его вывод (или ans $({run} …)).")
MSG_QUERY_EMPTY = ("Пусто: запрос ничего не вернул или упал. Запусти его без ans и посмотри: "
                   "ошибку база печатает сама (у psql — ERROR:, у sqlite3 — Error), причина — "
                   "в ней; ошибки нет — условие не нашло ни одной строки.")
MSG_ANS_FRAMES = ("Это вывод с рамками psql: шапка, черта и (N rows). Сдаются одни данные — psql "
                  "-At -c \"…\" печатает их без рамок.")
MSG_QUERY_ZERO = ("Ноль: запрос ничего не нашёл — или упал, а | wc -l от пустоты тоже 0. "
                  "Запусти его без ans и без счёта и посмотри, что печатает база.")
MSG_PSQL_UNQUOTED = ("Запрос после -c — целиком в двойных кавычках: psql -c \"SELECT …\". Без "
                     "них zsh режет его на слова, а * пробует раскрыть в имена файлов.")
MSG_PSQL_META_BARE = ("Мета-команду бери в кавычки: psql -c \"\\dt\". Без них zsh съедает "
                      "обратную косую черту, и psql получает просто «{word}».")
MSG_PSQL_DQ = ("Строки внутри запроса — в одинарных кавычках: = 'значение'. В PostgreSQL "
               "двойные кавычки — это имя графы (column … does not exist), да и весь запрос "
               "уже в двойных.")
MSG_PSQL_HOST = ("Адрес учебного сервера уже задан — psql без -h и -p сам идёт куда надо. "
                 "До чужих серверов из песочницы не достучаться.")
MSG_PSQL_PIPE = ("| {cmd} попал внутрь кавычек — psql принял его за часть запроса (syntax "
                 "error at or near \"|\"). Труба — команда zsh: ставь её после закрывающей "
                 "кавычки.")
MSG_NEED_PSQL = ("Здесь база — на учебном сервере PostgreSQL, файла {name} нет (sqlite3 молча "
                 "завёл пустой). Спрашивай через psql: psql -At -c \"SELECT …\".")
MSG_NEED_SQLITE = ("Здесь база — файл vault.db, сервера PostgreSQL в этой задаче нет. "
                   "Спрашивай так: sqlite3 vault.db \"SELECT …\".")

_PSQL_HOST_OPTS = {"-h", "--host", "-p", "--port"}
_PSQL_ARG_OPTS = {"-c", "--command", "-F", "--field-separator", "-R", "--record-separator",
                  "-d", "--dbname", "-U", "--username", "-o", "--output", "-f", "--file",
                  "-v", "--set", "-P", "--pset"} | _PSQL_HOST_OPTS
_UNQUOTED_SQL = {w.lower() for w in ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "FROM",
                                     "WHERE")}
_DQ_VALUE = re.compile(r"(?:=|<>|\bI?LIKE|\bIN\s*\(|,)\s*\\?\"[^\"]*\"", re.I)
_PIPE_INSIDE = re.compile(r"(?<!\|)\|\s*(wc|grep|sort|head|tail|uniq|cut)\b(?:\s+-\w+)?")


def client_line(line: str) -> Optional[str]:
    """Команда клиента базы из строки: с её начала или с подстановки $(psql …)/$(sqlite3 …)
    (хвост строки с неё); не клиент — None."""
    for c in CLIENTS:
        if line.startswith(c + " ") or line == c:
            return line
    for c in CLIENTS:
        k = line.find("$(" + c)
        if k >= 0:
            return line[k + 2:]
    return None


def last_client_line(ctx) -> str:
    """Последняя команда с psql или sqlite3 (в том числе ans $(psql …))."""
    for c in reversed(ctx.cmds or ()):
        if client_line(c.line) is not None:
            return c.line
    return ""


def _words(line: str) -> List[str]:
    try:
        return shlex.split(line)
    except ValueError:
        return line.split()


# аудит 9б, п. 7: приёмы из интернета стучатся не в vault — сервер отвечает сырым FATAL
MSG_PSQL_LIST = ("psql -l стучится в служебную базу postgres, а учебный сервер пускает только в "
                 "vault — отсюда FATAL … pg_hba.conf. Сервер цел. Список баз — изнутри vault: psql "
                 "-c \"\\l\".")
MSG_PSQL_DB = ("Учебный сервер пускает только в базу vault, а «{db}» — чужая: отсюда FATAL … "
               "pg_hba.conf. Сервер цел. Пиши просто psql — база vault уже задана.")
MSG_PSQL_USER = ("Учебный сервер пускает только пользователя runner — он и так задан, -U не "
                 "нужен. FATAL … pg_hba.conf — отказ во входе, сервер цел.")
MSG_PSQL_SECOND_C = ("Второй запрос — со своим -c: psql -c \"\\dt\" -c \"\\d invoices\". Без -c "
                     "psql принял «{arg}» за имя базы — отсюда FATAL … database. Сервер цел.")
_PSQL_VALUE_SHORT = "cFRdUofvPhp"        # короткие ключи psql со значением


def psql_target(words: List[str]) -> Optional[str]:
    """Куда стучится psql: -l/--list, чужая база (-d, первый аргумент), чужой пользователь (-U,
    второй аргумент), запрос без своего -c (psql примет его за имя базы). Слова — до первого
    оператора оболочки (|, &&, ;, >): дальше уже другая команда."""
    cut = next((i for i, w in enumerate(words) if w in ("|", "||", "&&", ";", "&") or
                w.startswith((">", "<", "2>", "|"))), len(words))
    words = words[:cut]
    opts, pos, k = {}, [], 1
    while k < len(words):
        w = words[k]
        if w in _PSQL_ARG_OPTS:
            if k + 1 < len(words):
                opts.setdefault(w, []).append(words[k + 1])
            k += 2
            continue
        if w.startswith("--") and "=" in w:
            name, val = w.split("=", 1)
            opts.setdefault(name, []).append(val)
        elif w == "--list":
            opts["-l"] = [""]
        elif w.startswith("-") and len(w) > 1 and not w.startswith("--"):
            if w[1] in _PSQL_VALUE_SHORT:
                opts.setdefault("-" + w[1], []).append(w[2:])
            elif "l" in w[1:]:
                opts["-l"] = [""]
        elif not w.startswith("-"):
            pos.append(w)
        k += 1
    if "-l" in opts:
        return MSG_PSQL_LIST
    for arg in pos:
        if arg.startswith("\\") or " " in arg or arg.lower() in _UNQUOTED_SQL:
            return MSG_PSQL_SECOND_C.format(arg=arg)
    for db_ in opts.get("-d", []) + opts.get("--dbname", []) + pos[:1]:
        if db_ != pgkit.DATABASE:
            return MSG_PSQL_DB.format(db=db_)
    for user in opts.get("-U", []) + opts.get("--username", []) + pos[1:2]:
        if user != pgkit.RUNNER:
            return MSG_PSQL_USER
    return None


def psql_shape(line: str) -> Optional[str]:
    """Отклик по форме команды psql (или None): запрос без кавычек, мета-команда без кавычек,
    строка в двойных кавычках внутри запроса, труба внутри кавычек, чужой адрес."""
    words = _words(line)
    if not words or words[0] != "psql":
        return None
    # слова вне кавычек: то, что zsh отдал psql по одному (в кавычках — один аргумент)
    raw = re.sub(r'"[^"]*"|\'[^\']*\'', " \x00 ", line).split()
    if any(w in _PSQL_HOST_OPTS or w.startswith(("--host=", "--port=")) for w in words[1:]):
        return MSG_PSQL_HOST
    for i, w in enumerate(raw[1:], start=1):
        prev = raw[i - 1]
        if prev in ("-c", "--command") and w.startswith("\\") and w != "\x00":
            return MSG_PSQL_META_BARE.format(word=w.lstrip("\\"))
    # без -c запрос идёт не аргументом (here-doc, < файл, -f): кавычки ему не нужны (аудит 9б, п. 6)
    has_c = any(w in ("-c", "--command") or w.startswith("--command=") for w in words[1:])
    if has_c and any(w.lower() in _UNQUOTED_SQL for w in raw[1:]):
        return MSG_PSQL_UNQUOTED
    hint = psql_target(words)
    if hint:
        return hint
    # тело запроса — с кавычки после -c (у -F "," своя кавычка — не запрос)
    m = re.search(r'(?:^|\s)(?:-c|--command)\s+"', line)
    body = line[m.end():] if m else (line.split('"', 1)[1] if '"' in line else "")
    if _DQ_VALUE.search(body):
        return MSG_PSQL_DQ
    for q in re.findall(r'"([^"]*)"', line):
        m = _PIPE_INSIDE.search(db._SQ_LITERAL.sub("''", q))
        if m:
            return MSG_PSQL_PIPE.format(cmd=m.group(0).lstrip("| ").strip())
    return None


def shape(box, state: dict, line: str) -> Optional[str]:
    """Отклик по форме последней команды клиента: не тот клиент для движка задачи, затем
    форма psql или sqlite3 (db.line_shape — пустая база от опечатки, кавычки, CSV вместо
    базы…). Только видимое: команда и файлы песочницы, без сравнения с ответом."""
    cmd = client_line(line)
    if cmd is None:
        return None
    engine = VaultMixin.engine_of(state)
    words = _words(cmd)
    if not words:
        return None
    if words[0] == "sqlite3" and engine == "pg":
        name = db._db_arg(words) or DB
        return MSG_NEED_PSQL.format(name=name)
    if words[0] == "psql" and engine != "pg":
        return MSG_NEED_SQLITE
    if words[0] == "psql":
        return psql_shape(cmd)
    return db.line_shape(box, cmd)


# фразы откликов 9а про sqlite3 — для PostgreSQL свои слова (ошибки там звучат иначе)
_PG_WORDS = (("sqlite3 ответит misuse of aggregate", "psql ответит aggregate functions are not "
              "allowed in WHERE"),
             ("sqlite3 принял за имя графы — отсюда no such column",
              "PostgreSQL принял за имя графы — отсюда column … does not exist"),
             ("Дата без кавычек для sqlite3 — вычитание", "Дата без кавычек для базы — "
              "вычитание"))


_DECLARED = (
    re.compile(r"\bAS\s+([A-Za-z_]\w*)", re.I),                       # графа или WITH: AS top
    re.compile(r"\b([A-Za-z_]\w*)\s+AS\s*\(", re.I),                    # WITH mm AS (
    re.compile(r"\b(?:FROM|JOIN)\s+[A-Za-z_][\w.]*\s+([A-Za-z_]\w*)", re.I),   # FROM kpi best
    re.compile(r"\)\s+([A-Za-z_]\w*)"),                                  # (SELECT …) t
)


def declared_names(line: str) -> set:
    """Имена, которые запрос заводит сам: псевдонимы граф (AS top), имена WITH, клички таблиц
    и подзапросов. Справа от = это графы, а не «строка без кавычек» (ревью B3, I1)."""
    from termit_app.tasks import lint
    body = db._SQ_LITERAL.sub("''", line)
    out = set()
    for rx in _DECLARED:
        out |= {m.group(1) for m in rx.finditer(body)
                if m.group(1).upper() not in lint.SQL_KEYWORDS}
    return out


# аудит 9б, п. 2: частые ошибки, на которых PostgreSQL (и SQLite) падает, — по форме запроса
MSG_GROUP_BY = ("Графа рядом с {agg}(…) без GROUP BY: PostgreSQL ответит must appear in the GROUP "
                "BY clause. Нужна группа — добавь графу в GROUP BY; нужна строка с максимумом — "
                "найди его подзапросом: WHERE amount = (SELECT MAX(amount) …).")
MSG_WIN_ALIAS = ("Номер окна ({alias}) в WHERE того же SELECT не виден — база считает окно уже "
                 "после WHERE (column … does not exist, у sqlite3 — misuse of aliased window "
                 "function). Окно — в подзапросе, снаружи WHERE: SELECT … FROM (SELECT …, … OVER "
                 "(…) AS {alias} FROM …) t WHERE {alias} = ….")
MSG_WIN_WHERE = ("Окно в WHERE нельзя: оно считается после WHERE (window functions are not allowed "
                 "in WHERE, у sqlite3 — misuse of window function). Сначала посчитай его в "
                 "подзапросе: SELECT … FROM (SELECT …, LAG(…) OVER (…) AS prev FROM …) t WHERE … "
                 "prev.")
_AGG = re.compile(r"\b(MAX|MIN|SUM|AVG|COUNT)\s*\(", re.I)
_BARE_ITEM = re.compile(r"(?:DISTINCT\s+)?([A-Za-z_][\w.]*)(?:\s+(?:AS\s+)?[A-Za-z_]\w*)?", re.I)
_CLAUSE_END = re.compile(r"\b(?:GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING|WINDOW|UNION|OFFSET)\b", re.I)


def _flat(sql: str, start: int) -> str:
    """Текст запроса с позиции start на его уровне скобок: вложенные скобки — «(…)»; конец —
    закрывающая скобка уровня (конец подзапроса) или конец текста."""
    out, depth = [], 0
    for ch in sql[start:]:
        if ch == "(":
            if depth == 0:
                out.append("(")
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
            if depth == 0:
                out.append("…)")
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _select_scopes(sql: str):
    """(список граф, остаток после FROM) каждого SELECT запроса на его уровне скобок."""
    for m in re.finditer(r"\bSELECT\b", sql, re.I):
        parts = re.split(r"\bFROM\b", _flat(sql, m.end()), maxsplit=1, flags=re.I)
        yield parts[0], (parts[1] if len(parts) > 1 else "")


def _split_items(head: str) -> List[str]:
    return [x.strip() for x in head.split(",") if x.strip()]


def pg_error_shape(line: str) -> Optional[str]:
    """Отклик на запрос, который база не выполнит (MSG_WIN_WHERE, MSG_WIN_ALIAS — оба движка;
    MSG_GROUP_BY — только PostgreSQL: SQLite такой запрос молча выполняет), или None."""
    sql = " ".join(re.findall(r'"([^"]*)"', db._SQ_LITERAL.sub("''", line)))
    if not re.search(r"\bSELECT\b", sql, re.I):
        return None
    for head, rest in _select_scopes(sql):
        where = re.split(r"\bWHERE\b", rest, maxsplit=1, flags=re.I)
        where = _CLAUSE_END.split(where[1], maxsplit=1)[0] if len(where) > 1 else ""
        if re.search(r"\bOVER\s*\(", where, re.I):
            return MSG_WIN_WHERE
        for item in _split_items(head):
            a = re.search(r"\bOVER\s*\(…\)\s+(?:AS\s+)?([A-Za-z_]\w*)\s*$", item, re.I)
            if a and re.search(rf"(?<![\w.]){a.group(1)}\b", where):
                return MSG_WIN_ALIAS.format(alias=a.group(1))
    return None


def group_by_shape(line: str) -> Optional[str]:
    """Графа рядом с агрегатом в одном SELECT без GROUP BY (окна — не агрегаты) — MSG_GROUP_BY."""
    sql = " ".join(re.findall(r'"([^"]*)"', db._SQ_LITERAL.sub("''", line)))
    for head, rest in _select_scopes(sql):
        if re.search(r"\bGROUP\s+BY\b", rest, re.I):
            continue
        items = _split_items(head)
        aggs = [_AGG.search(x) for x in items if _AGG.search(x) and not re.search(
            r"\bOVER\b", x, re.I)]
        bare = [x for x in items if _BARE_ITEM.fullmatch(x) and x.upper() not in (
            "NULL", "TRUE", "FALSE", "*")]
        if aggs and bare:
            return MSG_GROUP_BY.format(agg=aggs[0].group(1).upper())
    return None


def form_hint(state: dict, line: str) -> Optional[str]:
    """Ошибка в самой форме запроса (агрегат в WHERE, = NULL, строка без кавычек…) — как в 9а
    (db.common_form_hint), со словами того движка, на котором идёт задача; графы Хранилища и
    псевдонимы эталонов — имена, а не значения. Затем — запросы, которые база не выполнит
    (окно в WHERE, номер окна в WHERE, в PostgreSQL — графа рядом с агрегатом без GROUP BY)."""
    with db.known_names(VAULT_NAMES | declared_names(line)):
        hint = db.common_form_hint(line)
    pg = VaultMixin.engine_of(state) == "pg"
    if hint and pg:
        for old, new in _PG_WORDS:
            hint = hint.replace(old, new)
    if hint:
        return hint
    if client_line(line) is None and "psql" not in line and "sqlite3" not in line:
        return None
    return pg_error_shape(line) or (group_by_shape(line) if pg else None)


class SqlAnswer(VaultData, VaultAnswer, db._DbAnswer):
    """«Найди и назови» в Хранилище: сравнение ответа, ловушки и итоги — как в 9а
    (db._DbAnswer: части в любом порядке, числа как числа, ловушка только при равенстве), а
    отклики по форме — для psql и sqlite3 (shape, form_hint)."""
    track = "sql"
    secret_keys = VaultAnswer.secret_keys
    fallback = "Не то. Сверь запрос с условием: таблица, графа, условие. Застрял — hint."
    msg_parts_extra = db.MSG_PARTS_EXTRA
    ans_frames = True          # сданный вывод с рамками — отклик про -At (кроме psql_nav)

    def form_hint(self, line: str, state: Optional[dict] = None) -> Optional[str]:
        return form_hint(state or {}, line)

    def task_hint(self, line: str, state: dict) -> Optional[str]:
        """Свой отклик задачи по форме запроса (и после команды без ans, и на пустой/0)."""
        return None

    def empty_hint(self, line: str, state: Optional[dict] = None) -> Optional[str]:
        return None

    def wrong_message(self, given, ctx):
        st = ctx.state
        g = textnorm.clean(given)
        if g.split()[:1] and g.split()[0] in CLIENTS:
            return MSG_CMD_ANSWER.format(**st)
        if self.ans_frames and (re.search(r"\(\d+ rows?\)", g) or re.search(r"-{3,}", g)):
            return MSG_ANS_FRAMES      # B7 (мелочи аудита): сдан вывод с рамками psql
        line = last_client_line(ctx)
        hint = self.task_hint(line, st) or self.form_hint(line, st)
        if hint:
            return hint
        zero = len(textnorm.parts(g)) == 1 and textnorm.as_number(g) == 0
        if not g or zero:
            hint = shape(ctx.box, st, line) or self.empty_hint(line, st)
            if hint:
                return hint
            if not g and client_line(ctx.cmds[-1].line if ctx.cmds else "") is not None:
                return MSG_QUERY_EMPTY
            if zero and line:
                return MSG_QUERY_ZERO
        trap = self.trap_message(given, ctx)
        if trap:
            return trap
        common = self.common_mistake(given, ctx)
        form = self._form(st)
        want = textnorm.parts(self.expected(st))
        if common == base.MSG_NOT_NUMBER and re.search(r"\bсколь", self._task_text(st), re.I):
            return db.MSG_LIST_NOT_COUNT
        if form and len(want) > 1 and common in (base.MSG_ONE, base.MSG_EXTRA):
            return self.msg_parts_extra.format(form=form)
        if common == base.MSG_PARTIAL.format(n=len(want)):
            # «ЧИСЛО ТИП» — назвать недостающее; одна заготовка («ИМЯ» из двух слов) — нет:
            # число частей ответа отклик не выдаёт
            if form and len(form.split()) > 1:
                return db.MSG_PARTS_MISSING.format(form=form)
            return self.fallback.format(**st)
        if common:
            return common
        return self.fallback.format(**st)

    def check(self, ctx):
        v = base.AnswerTask.check(self, ctx)
        if v.solved or v.message or ctx.answer is not None:
            return v
        line = ctx.cmds[-1].line if ctx.cmds else ""
        if client_line(line) is None:
            return v
        hint = (shape(ctx.box, ctx.state, line) or self.task_hint(line, ctx.state)
                or self.form_hint(line, ctx.state))
        return Verdict(False, hint) if hint else v


FILE_CAP = db.FILE_CAP


def read_lines(box, rel: str) -> Optional[List[str]]:
    """Строки файла игрока (без хвостовых пустых, \\r\\n — как \\n) или None — файла нет."""
    data = sandbox.read_in_box(box, rel, FILE_CAP)
    if data is None:
        return None
    got = data.decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    while got and got[-1] == "":
        got.pop()
    return got


class SqlTask(VaultData, VaultTask):
    """«Сделай» в Хранилище: проверка — judge(ctx) (файлы и/или снимок базы); пока она молчит,
    отклик по форме последней команды клиента."""

    def judge(self, ctx) -> Verdict:
        raise NotImplementedError

    def check(self, ctx):
        try:
            v = self.judge(ctx)
        except dbread.Broken as e:
            return Verdict(False, str(e))
        if v.solved or v.message:
            return v
        line = ctx.cmds[-1].line if ctx.cmds else ""
        if client_line(line) is not None:
            hint = (shape(ctx.box, ctx.state, line) or form_hint(ctx.state, line)
                    or self.task_hint(ctx, line))
            if hint:
                return Verdict(False, hint)
        return v

    def task_hint(self, ctx, line: str) -> Optional[str]:
        return None


# --- 1. psql_nav ---------------------------------------------------------------------------------

# свои таблицы задачи (сверх общей схемы): сколько их — от зерна, у граф — разные типы
_NAV_EXTRA = {
    "archive_2025": dbkit.Extra(
        ("id", "customer_id", "amount", "closed_on"),
        "CREATE TABLE archive_2025 (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, "
        "amount INTEGER NOT NULL, closed_on TEXT NOT NULL)",
        "CREATE TABLE archive_2025 (id integer PRIMARY KEY, customer_id integer NOT NULL, "
        "amount integer NOT NULL, closed_on date NOT NULL)"),
    "flags": dbkit.Extra(
        ("id", "code", "active"),
        "CREATE TABLE flags (id INTEGER PRIMARY KEY, code TEXT NOT NULL, active INTEGER NOT "
        "NULL)",
        "CREATE TABLE flags (id integer PRIMARY KEY, code text NOT NULL, active boolean NOT "
        "NULL)"),
    "limits": dbkit.Extra(
        ("code", "cap", "comment"),
        "CREATE TABLE limits (code TEXT PRIMARY KEY, cap REAL NOT NULL, comment TEXT)",
        "CREATE TABLE limits (code text PRIMARY KEY, cap numeric NOT NULL, comment text)"),
    "branches": dbkit.Extra(
        ("id", "district", "opened_on", "meta"),
        "CREATE TABLE branches (id INTEGER PRIMARY KEY, district TEXT NOT NULL, opened_on TEXT "
        "NOT NULL, meta TEXT NOT NULL)",
        "CREATE TABLE branches (id integer PRIMARY KEY, district text NOT NULL, opened_on date "
        "NOT NULL, meta jsonb NOT NULL)"),
}
# тип графы, как его печатает \d (PostgreSQL): только однословные — их и спрашиваем
NAV_TYPES = {
    ("customers", "district"): "text", ("customers", "email"): "text",
    ("invoices", "amount"): "integer", ("invoices", "status"): "text",
    ("payments", "invoice_id"): "integer", ("employees", "dept"): "text",
    ("employees", "manager_id"): "integer", ("rates", "rate"): "integer",
    ("rates", "note"): "text", ("events", "payload"): "jsonb", ("ledger", "kind"): "text",
    ("audit_log", "actor"): "text",
    ("archive_2025", "closed_on"): "date", ("archive_2025", "amount"): "integer",
    ("flags", "active"): "boolean", ("flags", "code"): "text",
    ("limits", "cap"): "numeric", ("branches", "opened_on"): "date",
    ("branches", "meta"): "jsonb",
}
# таблицы общей схемы, где ровно одна графа разрешает NULL (вариант B)
NAV_NULLABLE = {"customers": "email", "payments": "invoice_id", "employees": "manager_id",
                "audit_log": "row_id"}
NAV_BASE_TABLES = 8                      # таблиц общей схемы в public (ops.duty — в своей схеме)
NAV_DATABASES = 4                        # postgres, template0, template1, vault
# лишние пустые базы сервера задачи (от 1 до 3, ревью B2 M3): число баз в \l — от зерна
NAV_EXTRA_DBS = ("archive", "reports", "staging", "legacy")
NAV_DT_FRAME = 5                         # строк рамки у psql -c "\dt": заголовок, шапка, черта, итог, пустая

_NAV_TYPES_SQL = ("SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = "
                  "'{table}'::regclass AND attname = '{col}'")


def _nav_extra_rows(rng, table: str, n: int) -> List[dict]:
    out = []
    for i in range(1, n + 1):
        if table == "archive_2025":
            out.append({"id": i, "customer_id": rng.randrange(1, 60),
                        "amount": rng.randrange(100, 9000),
                        "closed_on": f"2025-{rng.randrange(1, 13):02d}-{rng.randrange(1, 28):02d}"})
        elif table == "flags":
            out.append({"id": i, "code": f"f{i}{rng.choice('abcxyz')}",
                        "active": rng.random() < 0.5})
        elif table == "limits":
            out.append({"code": f"L{i:02d}", "cap": f"{rng.randrange(10, 900)}.{rng.randrange(100):02d}",
                        "comment": rng.choice((None, "base", "vip"))})
        else:
            out.append({"id": i, "district": rng.choice(dbkit.DISTRICTS),
                        "opened_on": f"2024-{rng.randrange(1, 13):02d}-{rng.randrange(1, 28):02d}",
                        "meta": dbkit.jsonb_text({"floor": rng.randrange(1, 9)})})
    return out


class PsqlNav(SqlAnswer):
    """psql: вход и выход, \\dt, \\d таблица, \\l, \\x, пейджер; psql -c без захода."""
    id = "psql_nav"
    title = "Вход в Хранилище"
    par = 60
    stand = "pg"
    # B7 (аудит 9б, разгрузка): not null — текст варианта 1, \\l — текст варианта 2, пейджер и
    # \\x — карточка psql_pipe, vault-> и vault(> — голос задачи
    scroll = ("psql — войти в учебную базу (vault=>): \\dt — таблицы, \\d invoices — графы и их "
              "типы.\n"
              "Выход — \\q или Ctrl+D; ans и hint — только в zsh.\n"
              "Без захода — флаг -c (command): psql -c \"\\dt\"; два запроса — два -c: psql -c "
              "\"\\dt\" -c \"\\d invoices\".")
    variants = (
        Variant("Учебная база vault уже ждёт: psql — и ты внутри. Сколько в ней таблиц (\\dt) и "
                "какого типа графа {col} в таблице {table}? Ответ: ans ЧИСЛО ТИП",
                hints=("Таблицы перечислит \\dt, графы одной таблицы и их типы — \\d с её "
                       "именем.",
                       "Таблиц столько, сколько написано внизу: (N rows). Тип — во второй "
                       "колонке вывода \\d, напротив {col}.",
                       "psql -c \"\\dt\" -c \"\\d {table}\""),
                solution='psql -c "\\dt" -c "\\d {table}"',
                solution_script=('print -r -- $(psql -At -c "SELECT COUNT(*) FROM pg_tables '
                                 "WHERE schemaname = 'public'\") $(psql -At -c \"" +
                                 _NAV_TYPES_SQL + '")'),
                wrong=('print -r -- $(psql -c "\\dt" | wc -l) {ctype}',
                       'psql -At -c "\\dt" | wc -l'),
                alternatives=("psql, внутри \\dt и \\d {table}, выход \\q — то же изнутри",)),
        Variant("В таблице {table} учебной базы одна графа может остаться пустой: у остальных "
                "в \\d стоит not null — графа обязательна. Какая это графа? Ответ: ans ГРАФА",
                hints=("Графы таблицы с пометками покажет \\d и имя таблицы.",
                       "Колонка Nullable: у всех граф там not null, кроме одной — она и есть "
                       "ответ.",
                       "psql -c \"\\d {table}\""),
                solution='psql -c "\\d {table}"',
                solution_script=("psql -At -c \"SELECT attname FROM pg_attribute WHERE attrelid "
                                 "= '{table}'::regclass AND attnum > 0 AND NOT attnotnull\""),
                wrong=("print -r -- id", "print -r -- {table}"),
                alternatives=("psql, внутри \\d {table}, выход \\q — то же изнутри",)),
        Variant("Сколько баз данных на учебном сервере и кто владелец (Owner) базы vault? Все "
                "базы сервера с владельцами перечислит \\l. Ответ: ans ЧИСЛО ВЛАДЕЛЕЦ",
                hints=("Все базы сервера с владельцами показывает \\l.",
                       "Баз столько, сколько в (N rows); владелец vault — в колонке Owner её "
                       "строки.",
                       "psql -c \"\\l\""),
                solution='psql -c "\\l"',
                solution_script=('print -r -- $(psql -At -c "SELECT COUNT(*) FROM '
                                 "pg_database\") $(psql -At -c \"SELECT "
                                 "pg_get_userbyid(datdba) FROM pg_database WHERE datname = "
                                 "'vault'\")"),
                wrong=("print -r -- {ndb} termit",
                       'print -r -- $(psql -c "\\l" | wc -l) runner'),
                alternatives=("psql, внутри \\l, выход \\q — то же изнутри",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("psql — клиент сервера PostgreSQL. Мета-команды с \\ (\\dt, \\d, \\l) с порога "
               "показывают, что на сервере лежит, — ещё до первого запроса. Внутри psql понимают "
               "только их и SQL, а ans и hint — команды zsh: сначала выйди.")
    spell = ("psql — войти; \\dt — таблицы; \\d т — графы и типы; \\l — базы; \\q — выйти; "
             "psql -c \"\\dt\" — без захода")
    trap_messages = {
        "lines": "Это строки вывода вместе с шапкой, чертой и итогом. Таблиц столько, сколько "
                 "написано внизу: (N rows).",
        "pk": "id — первичный ключ: он not null всегда. Ищи графу, у которой в колонке "
              "Nullable пусто.",
        "owner": "termit — владелец служебных и лишних баз, а спрашивали про vault: смотри "
                 "Owner в её строке.",
    }
    # ctype и ndb — тип-ответ варианта A и число баз варианта C: нужны неверным решениям, в
    # task.json их нет
    secret_keys = SqlAnswer.secret_keys + ("ctype", "ndb")
    fallback = "Не то. Сверь с выводом \\dt, \\d или \\l — то ли место смотришь. Застрял — hint."
    ans_frames = False         # ответ здесь читают глазами из вывода с рамками
    msg_parts_extra = ("Лишнее в ответе: задание просит {form} — сдай только это через пробел, а "
                       "не весь вывод.")
    MSG_LIST_LINES = ("wc -l считает строки вывода \\l вместе с шапкой, чертой, итогом и "
                      "переносами в Access privileges. Баз столько, сколько написано внизу: "
                      "(N rows).")

    def task_hint(self, line, state):
        # FB7: в варианте C базы считают | wc -l, как таблицы в варианте A
        if "\\l" in line and "wc -l" in line:
            return self.MSG_LIST_LINES
        return None

    def extend(self, rng, data):
        names = sorted(rng.sample(sorted(_NAV_EXTRA), rng.randint(1, 3)))
        for t in names:
            data.extra[t] = _NAV_EXTRA[t]
            data.tables[t] = _nav_extra_rows(rng, t, rng.randint(2, 4))
        data.databases = sorted(rng.sample(NAV_EXTRA_DBS, rng.randint(1, 3)))
        return data

    def data_state(self, rng, data, variant):
        tables = [t for t in data.tables if t not in dbkit.PG_ONLY]
        if variant == 1:
            table = rng.choice(sorted(NAV_NULLABLE))
            return {"table": table, "answer": NAV_NULLABLE[table], "traps": [["pk", "id"]]}
        if variant == 2:
            n = NAV_DATABASES + len(data.databases)
            return {"ndb": n, "answer": [n, pgkit.RUNNER],
                    "traps": [["owner", [n, pgkit.SUPERUSER]]]}
        pick = sorted(k for k in NAV_TYPES if k[0] in tables)
        table, col = rng.choice(pick)
        ctype = NAV_TYPES[(table, col)]
        n = len(tables)
        return {"table": table, "col": col, "ctype": ctype, "answer": [n, ctype],
                "traps": [["lines", [n + NAV_DT_FRAME, ctype]]]}


# --- 2. psql_pipe ---------------------------------------------------------------------------------

MSG_PIPE_FRAMES = ("В файле рамки psql: шапка, черта и (N rows) — это для глаз. Только данные "
                   "— -At: -A снимает выравнивание, -t — шапку и итог.")
MSG_PIPE_ALIGN = ("Пробелы вокруг | — выравнивание для глаз: без -A psql добивает графы "
                  "пробелами. Нужен -A (вместе с -t — -At).")
MSG_PIPE_BAR = ("Графы через | — разделитель -A по умолчанию. Через запятую — -F ','.")
MSG_PIPE_NO_HEADER = ("Шапки нет: она нужна первой строкой. --csv печатает её сам, а -t "
                      "её убирает.")
MSG_PIPE_NOT_CSV = "Графы через | — это не CSV. Настоящий CSV с шапкой — psql --csv -c \"…\"."
MSG_PIPE_SCREEN = ("Вывод — на экране, а задание ждёт файл: допиши > {out} в конце команды (файл "
                   "от прошлой попытки перезапишется).")
MSG_PIPE_SEP_SPACE = ("Разделитель — ровно запятая, без пробела: -F ','. С -F ', ' в каждой строке "
                      "лишний пробел после запятой.")
MSG_PIPE_COLS = ("В строке {n} граф(ы), а нужны две — {cols}: перечисли их в SELECT через "
                 "запятую.")
MSG_PIPE_ALIEN_HEADER = ("Шапка есть, но не та: {got}. Нужна {header} — перечисли в SELECT ровно "
                         "эти графы, а не *.")
MSG_PIPE_HAS_HEADER = "Шапка тут не нужна: -t убирает её вместе с итогом (N rows)."


class PsqlPipe(SqlTask):
    """psql -At -c (только данные), -F ',', --csv, > файл, | sort | head."""
    id = "psql_pipe"
    title = "Выгрузка без рамок"
    par = 75
    stand = "pg"
    scroll = ("psql -At -c \"SELECT code, rate FROM rates WHERE rate > 100 ORDER BY code\" — "
              "только данные: -A — unaligned, без выравнивания, -t — tuples only, без шапки и "
              "(N rows). psql -A -F ',' -c \"…\" — Field separator: графы через запятую; psql --csv "
              "-c \"…\" — CSV с шапкой. "
              "Дальше: > файл, | sort | head; sort -t '|' -k2 -rn — по второй графе, числами.\n"
              "Для глаз: пейджер (Пробел, q — выход), \\x — запись столбиком.")
    variants = (
        Variant("Сделай out.csv: id и сумма (amount) всех счетов со статусом {status}, по "
                "возрастанию id — только данные, через запятую, без шапки и рамок.",
                hints=("Выгрузка — тот же SELECT, только с флагами вывода psql и > в файл.",
                       "-At — только данные, -F ',' — запятая вместо |; ORDER BY id — по "
                       "возрастанию.",
                       "psql -At -F ',' -c \"SELECT id, amount FROM invoices WHERE status = "
                       "'{status}' ORDER BY id\" > out.csv; cat out.csv"),
                solution="psql -At -F ',' -c \"SELECT id, amount FROM invoices WHERE status = "
                         "'{status}' ORDER BY id\" > out.csv",
                wrong=("psql -c \"SELECT id, amount FROM invoices WHERE status = '{status}' "
                       "ORDER BY id\" > out.csv",
                       "psql -At -c \"SELECT id, amount FROM invoices WHERE status = '{status}' "
                       "ORDER BY id\" > out.csv"),
                alternatives=("psql --csv -t -c \"SELECT id, amount FROM invoices WHERE status = "
                              "'{status}' ORDER BY id\" > out.csv — CSV без шапки",)),
        Variant("Сделай report.csv — имя и почта всех клиентов района {district}, по алфавиту "
                "имён: настоящий CSV, первой строкой — шапка name,email.",
                hints=("CSV с шапкой psql печатает сам — нужен флаг --csv и > в файл.",
                       "SELECT name, email … WHERE district = '{district}' ORDER BY name — по "
                       "алфавиту.",
                       "psql --csv -c \"SELECT name, email FROM customers WHERE district = "
                       "'{district}' ORDER BY name\" > report.csv; cat report.csv"),
                solution="psql --csv -c \"SELECT name, email FROM customers WHERE district = "
                         "'{district}' ORDER BY name\" > report.csv",
                wrong=("psql -At -F ',' -c \"SELECT name, email FROM customers WHERE district = "
                       "'{district}' ORDER BY name\" > report.csv",
                       "psql --csv -c \"SELECT name, email FROM customers WHERE district = "
                       "'{district}'\" > report.csv"),
                alternatives=("psql --csv -c \"SELECT name, email FROM customers WHERE "
                              "district = '{district}' ORDER BY 1\" > report.csv — ORDER BY 1: "
                              "по первой графе",)),
        Variant("Сделай top.txt: три самых крупных счёта — id|amount, как печатает psql -At, "
                "от большего. Сортируй не в запросе, а sort'ом в трубе.",
                hints=("Пусть psql выдаст все счета одними данными, а сортирует и режет труба.",
                       "sort -t '|' -k2 -rn — по второй графе, числами, от большего; head -3 — "
                       "три первые строки.",
                       "psql -At -c \"SELECT id, amount FROM invoices\" | sort -t '|' -k2 -rn | "
                       "head -3 > top.txt; cat top.txt"),
                solution="psql -At -c \"SELECT id, amount FROM invoices\" | sort -t '|' -k2 -rn "
                         "| head -3 > top.txt",
                wrong=("psql -At -c \"SELECT id, amount FROM invoices\" | sort -t '|' -k2 -n | "
                       "head -3 > top.txt",
                       "psql -At -c \"SELECT id, amount FROM invoices\" | head -3 > top.txt"),
                alternatives=("psql -At -c \"SELECT id, amount FROM invoices ORDER BY amount "
                              "DESC LIMIT 3\" > top.txt — сортирует сама база",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Рамки psql — шапка, выравнивание и (N rows) — это для глаз. Файлу и трубе "
               "нужны голые данные: -At срезает всё лишнее, -F меняет разделитель, а --csv "
               "сразу печатает CSV с шапкой.")
    spell = ("psql -At -c \"SELECT …\" > ф — только данные; -F ',' — запятая; --csv — CSV с "
             "шапкой; | sort -t '|' -k2 -rn | head -3")

    def data_state(self, rng, data, variant):
        inv = data.tables["invoices"]
        if variant == 1:
            district = _pipe_district(rng, data)
            mine = sorted((c for c in data.tables["customers"] if c["district"] == district),
                          key=lambda c: (c["name"], c["id"]))
            return {"out": "report.csv", "header": "name,email", "district": district,
                    "want": ["name,email"] + [_pg_csv_line((c["name"], c["email"]))
                                              for c in mine]}
        if variant == 2:
            top = _distinct_top(rng, inv, 4)
            return {"out": "top.txt", "header": None,
                    "want": [f"{x['id']}|{x['amount']}" for x in top[:3]]}
        status = rng.choice(("open", "overdue"))
        mine = sorted((x for x in inv if x["status"] == status), key=lambda x: x["id"])
        return {"out": "out.csv", "header": None, "status": status,
                "want": [f"{x['id']},{x['amount']}" for x in mine]}

    def judge(self, ctx):
        st = ctx.state
        got = read_lines(ctx.box, st["out"])
        if got is None or not got:
            return Verdict(False)
        if got == st["want"]:
            return Verdict(True)
        # аудит 9б, п. 9: последний запрос вывел на экран, а не в файл — файл остался от
        # прошлой попытки, и разбирать его не к чему
        line = ctx.cmds[-1].line if ctx.cmds else ""
        if _screen_only(line):
            return Verdict(False, MSG_PIPE_SCREEN.format(out=st["out"]))
        return Verdict(False, self._why(got, st))

    @staticmethod
    def _why(got, st) -> str:
        want, header, out = st["want"], st.get("header"), st["out"]
        if any(re.fullmatch(r"\(\d+ rows?\)", x.strip()) for x in got) or \
                any(re.fullmatch(r"[-+]+", x.strip()) for x in got):
            return MSG_PIPE_FRAMES
        if any(re.search(r" \| |^ \S", x) for x in got):
            return MSG_PIPE_ALIGN
        sep = "|" if out == "top.txt" else ","
        if out != "top.txt" and all(", " in x for x in got) and not any("|" in x for x in got):
            return MSG_PIPE_SEP_SPACE
        body = got[1:] if header else got
        if body and not any("|" in x for x in got) or out == "top.txt":
            n = {len(x.split(sep)) for x in body}
            if body and n != {2}:
                cols = (header or "id,amount").replace(",", ", ")
                return MSG_PIPE_COLS.format(n=max(n), cols=cols)
        if out == "report.csv":
            if any("|" in x for x in got):
                return MSG_PIPE_NOT_CSV
            if got[0] != header and re.fullmatch(r"[a-z_]+(?:,[a-z_]+)*", got[0]):
                return MSG_PIPE_ALIEN_HEADER.format(got=got[0], header=header)
            if got[0] != header:
                return MSG_PIPE_NO_HEADER
            if sorted(got[1:]) == sorted(want[1:]):
                return "Строки те, порядок не тот: по алфавиту имён — ORDER BY name."
            return ("Строки не те: сверь WHERE с заданием (district = '…') и перезапиши файл "
                    "через >.")
        if got[0] in ("id,amount", "id|amount"):
            return MSG_PIPE_HAS_HEADER
        if out == "out.csv":
            if any("|" in x for x in got):
                return MSG_PIPE_BAR
            if sorted(got) == sorted(want):
                return "Строки те, порядок не тот: по возрастанию id — ORDER BY id."
            return ("Строки не те: сверь WHERE с заданием (status = '…') и перезапиши файл "
                    "через >.")
        if len(got) != len(want):
            return f"Строк {len(got)}, а нужно три: | head -3 в конце трубы."
        return ("Это не три самых крупных: сортируй по второй графе числами и от большего — "
                "sort -t '|' -k2 -rn.")

    def task_hint(self, ctx, line):
        if _screen_only(line) and read_lines(ctx.box, ctx.state["out"]) is None:
            return MSG_PIPE_SCREEN.format(out=ctx.state["out"])
        return None


def _screen_only(line: str) -> bool:
    """Команда psql с запросом, вывод которой ушёл на экран: без > и без -o."""
    words = _words(line)
    return bool(words) and words[0] == "psql" and ">" not in line and \
        re.search(r"\bSELECT\b", line, re.I) is not None and \
        not any(w in ("-o", "--output") or w.startswith(("-o", "--output=")) for w in words[1:])


def _pg_csv_cell(v) -> str:
    """Ячейка, как её печатает psql --csv: NULL и '' — пусто; в кавычки — только если есть
    запятая, кавычка или перевод строки."""
    if v is None:
        return ""
    s = str(v)
    if any(c in s for c in ',"\n\r'):
        return '"' + s.replace('"', '""') + '"'
    return s


def _pg_csv_line(row) -> str:
    return ",".join(_pg_csv_cell(v) for v in row)


def _pipe_district(rng, data) -> str:
    """Район для report.csv: не меньше 3 клиентов, не «грязный» (Kazan/kazan/KAZAN) и такой,
    где порядок строк таблицы (по id) — не алфавитный: «без ORDER BY» с ответом не совпадёт.
    Нет такого — меняем местами имена двух клиентов района (данные этого варианта)."""
    cust = data.tables["customers"]
    by = Counter(c["district"] for c in cust)
    pool = sorted(d for d, n in by.items() if n >= 3 and d.lower() != "kazan")
    district = rng.choice(pool)
    mine = sorted((c for c in cust if c["district"] == district), key=lambda c: c["id"])
    names = [c["name"] for c in mine]
    if names == sorted(names):
        mine[0]["name"], mine[-1]["name"] = mine[-1]["name"], mine[0]["name"]
    return district


def _distinct_top(rng, rows, k: int) -> List[dict]:
    """k самых крупных строк по amount — без ничьих: равные суммы у верхушки раздвигаем
    (данные варианта), чтобы sort и ORDER BY давали один порядок."""
    rows_sorted = sorted(rows, key=lambda x: (-x["amount"], x["id"]))
    for i in range(1, k):
        if rows_sorted[i]["amount"] >= rows_sorted[i - 1]["amount"]:
            rows_sorted[i]["amount"] = rows_sorted[i - 1]["amount"] - 1
    top = rows_sorted[:k]
    rest = max((x["amount"] for x in rows_sorted[k:]), default=0)
    if rest >= top[-1]["amount"]:
        top[-1]["amount"] = rest + 1
        for i in range(k - 2, -1, -1):
            if top[i]["amount"] <= top[i + 1]["amount"]:
                top[i]["amount"] = top[i + 1]["amount"] + 1
    return top


# --- 3. pg_dialect --------------------------------------------------------------------------------

MSG_TS_MIDNIGHT = ("Ноль: issued_at — дата со временем, и '{day}' для неё — полночь, "
                   "{day} 00:00:00. День целиком — приведи к дате: issued_at::date = '{day}'.")
MSG_TS_LIKE = ("LIKE — для строк, а issued_at — дата со временем (timestamp): psql скажет "
               "operator does not exist. Приведи тип: issued_at::date = '{day}'.")
MSG_NO_SCHEMA = ("Таблица duty лежит не в public, а в схеме ops — psql скажет relation "
                 "\"duty\" does not exist. Пиши со схемой: ops.duty (\\dn — схемы, \\dt ops.* — "
                 "их таблицы).")
MSG_LIKE_CASE = ("В PostgreSQL LIKE и = различают регистр: так найдётся только одно написание "
                 "района. Без учёта регистра — ILIKE.")


class PgDialect(SqlAnswer):
    """Отличия PostgreSQL: ILIKE, приведение ::, схемы (ops.таблица, \\dn, \\dt ops.*)."""
    id = "pg_dialect"
    title = "Свой диалект"
    par = 75
    stand = "pg"
    scroll = ("В PostgreSQL LIKE различает регистр, ILIKE — нет: \"SELECT COUNT(*) FROM staff "
              "WHERE city ILIKE 'omsk'\" найдёт и Omsk, и omsk.\n"
              "Приведение :: меняет тип: x::date — дата без времени, '7'::numeric — число.\n"
              "Таблица не в public — пиши со схемой: ops.duty. \\dn — схемы, \\dt ops.* — "
              "таблицы схемы ops.")
    variants = (
        Variant("Сколько клиентов из района kazan? В базе район записан как попало: Kazan, "
                "kazan, KAZAN. Ответ: ans ЧИСЛО",
                hints=("В PostgreSQL LIKE и = различают регистр — нужен поиск без него.",
                       "ILIKE 'kazan' найдёт все три написания; COUNT(*) — сколько строк.",
                       "psql -At -c \"SELECT COUNT(*) FROM customers WHERE district ILIKE "
                       "'kazan'\""),
                solution="psql -At -c \"SELECT COUNT(*) FROM customers WHERE district ILIKE "
                         "'kazan'\"",
                wrong=("psql -At -c \"SELECT COUNT(*) FROM customers WHERE district LIKE "
                       "'kazan'\"",
                       "psql -At -c \"SELECT COUNT(*) FROM customers WHERE district = "
                       "'Kazan'\""),
                alternatives=("psql -At -c \"SELECT COUNT(*) FROM customers WHERE "
                              "lower(district) = 'kazan'\" — всё к строчным",)),
        Variant("Сколько счетов выписано {day}? issued_at хранит дату вместе со временем. "
                "Ответ: ans ЧИСЛО",
                hints=("Время мешает: '{day}' для timestamp — только полночь.",
                       "Приведи к дате: issued_at::date = '{day}' — и посчитай COUNT(*).",
                       "psql -At -c \"SELECT COUNT(*) FROM invoices WHERE issued_at::date = "
                       "'{day}'\""),
                solution="psql -At -c \"SELECT COUNT(*) FROM invoices WHERE issued_at::date = "
                         "'{day}'\"",
                wrong=("psql -At -c \"SELECT COUNT(*) FROM invoices WHERE issued_at = "
                       "'{day}'\"",
                       "psql -At -c \"SELECT COUNT(*) FROM invoices WHERE issued_at < '{day}'\""),
                alternatives=("psql -At -c \"SELECT COUNT(*) FROM invoices WHERE issued_at >= "
                              "'{day}' AND issued_at < '{next_day}'\" — полуоткрытый день",)),
        Variant("В схеме ops учебной базы — таблица дежурных. Кто дежурит в районе {district}? "
                "Ответ: ans ИМЯ ФАМИЛИЯ",
                hints=("Схемы покажет \\dn, таблицы схемы ops — \\dt ops.*.",
                       "Таблица не в public — пиши её со схемой: FROM ops.duty WHERE district = "
                       "'{district}'.",
                       "psql -At -c \"SELECT name FROM ops.duty WHERE district = "
                       "'{district}'\""),
                solution="psql -At -c \"SELECT name FROM ops.duty WHERE district = "
                         "'{district}'\"",
                wrong=("psql -At -c \"SELECT name FROM duty WHERE district = '{district}'\"",
                       "psql -At -c \"SELECT district FROM ops.duty WHERE district = "
                       "'{district}'\""),
                alternatives=("psql -c \"\\dt ops.*\", потом psql -c \"SELECT * FROM ops.duty\" — "
                              "сначала посмотреть",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("PostgreSQL придирчивее SQLite: LIKE и = различают регистр (без него — ILIKE), "
               "типы сами не смешиваются (переводи через ::), а таблицы живут в схемах — без "
               "имени схемы он заглянет только в public.")
    spell = ("ILIKE — без регистра; x::date, '7'::numeric — приведение; ops.таблица — схема; "
             "\\dn, \\dt ops.*")
    trap_messages = {
        "like": MSG_LIKE_CASE,
        "before": "Это счета ДО {day}, а спрашивали выписанные в сам день: issued_at::date = "
                  "'{day}'.",
        "district": "Это район, а спрашивали, кто там дежурит: в SELECT нужна графа name.",
    }

    def data_state(self, rng, data, variant):
        cust, inv = data.tables["customers"], data.tables["invoices"]
        if variant == 1:
            return _day_state(rng, inv)
        if variant == 2:
            return _duty_state(rng, data.tables["ops.duty"])
        forms = Counter(c["district"] for c in cust if c["district"].lower() == "kazan")
        n = sum(forms.values())
        return {"answer": n, "traps": [["like", forms[f]] for f in dbkit.DIRTY_DISTRICT]}

    def task_hint(self, line, state):
        body = db._SQ_LITERAL.sub("''", line)
        if re.search(r"\bFROM\s+duty\b", body, re.I):
            return MSG_NO_SCHEMA
        if "day" in state and re.search(r"\bissued_at\s+(?:I?LIKE)\b", body, re.I):
            return MSG_TS_LIKE.format(**state)
        return None

    def empty_hint(self, line, state=None):
        st = state or {}
        body = db._SQ_LITERAL.sub("''", line)
        if "day" in st and re.search(r"\bissued_at\s*(?:=|BETWEEN)\s*''", body, re.I):
            return MSG_TS_MIDNIGHT.format(**st)
        return None


def _next_day(day: str) -> str:
    from datetime import date, timedelta
    y, m, d = map(int, day.split("-"))
    return (date(y, m, d) + timedelta(days=1)).isoformat()


def _day_state(rng, inv) -> dict:
    """День для «счета за день»: не меньше двух счетов, ни один — не ровно в полночь (иначе
    «= '{day}'» нашёл бы его), и до дня счета есть (ловушка «до»). Доводим постройкой."""
    days = Counter(x["issued_at"][:10] for x in inv)
    pool = sorted(d for d, n in days.items() if n >= 2 and any(
        y["issued_at"][:10] < d for y in inv))
    day = rng.choice(pool)
    for x in inv:
        if x["issued_at"] == f"{day} 00:00:00":
            x["issued_at"] = f"{day} 00:00:01"
    n = days[day]
    before = sum(1 for x in inv if x["issued_at"][:10] < day)
    return {"day": day, "next_day": _next_day(day), "answer": n,
            "traps": [["before", before]] if before != n else []}


def _duty_state(rng, duty) -> dict:
    """Район, где дежурит ровно один человек (иначе ответ — не одно имя); нет такого —
    переводим одного дежурного в район, где никого нет (данные варианта)."""
    by = Counter(d["district"] for d in duty)
    alone = sorted(k for k, n in by.items() if n == 1)
    if not alone:
        free = sorted(set(dbkit.DISTRICTS) - set(by))
        row = rng.choice(duty)
        row["district"] = rng.choice(free)
        alone = [row["district"]]
    district = rng.choice(alone)
    name = next(d["name"] for d in duty if d["district"] == district)
    return {"district": district, "answer": name, "traps": [["district", district]]}


# --- 4. pg_identity -------------------------------------------------------------------------------

# Спецификация таблицы варианта: графы (имя, тип в каталоге PostgreSQL — format_type
# заглавными), какая — номер (IDENTITY или SERIAL), какая — время вставки (DEFAULT now()).
IDENT_SPECS = (
    {"table": "ops.watch", "cols": (("customer_id", "INTEGER"), ("limit_sum", "NUMERIC(10,2)")),
     "time": "added_at"},
    {"table": "ops.tickets", "cols": (("title", "TEXT"), ("urgent", "BOOLEAN")),
     "time": "opened_at"},
    {"table": "ops.notes", "cols": (("customer_id", "INTEGER"), ("body", "TEXT"),
                                    ("amount", "NUMERIC(10,2)")),
     "time": "created_at"},
)
TZ_TYPE = "TIMESTAMP WITH TIME ZONE"
NOW_DEFAULTS = ("now()", "CURRENT_TIMESTAMP", "transaction_timestamp()",
                "statement_timestamp()", "clock_timestamp()")
TYPE_HINT = {
    "NUMERIC(10,2)": "деньги с копейками — NUMERIC(10,2): INTEGER копейки отрежет, а NUMERIC "
                     "без (10,2) не держит два знака",
    "INTEGER": "номер клиента — целое: INTEGER",
    "TEXT": "текст — TEXT",
    "BOOLEAN": "да или нет — BOOLEAN (TRUE и FALSE)",
    TZ_TYPE: "время с поясом — TIMESTAMPTZ (timestamp with time zone)",
}
TICKET_TITLES = ("vault door", "night alarm", "lost card", "slow export", "audit request",
                 "printer jam", "badge reset", "late report")
NOTE_BODIES = ("call back", "asked for limit", "paid in cash", "new address", "vip check",
               "dispute open")


def _money(rng) -> str:
    return f"{rng.randrange(100, 9000)}.{rng.choice((0, 5, 25, 50, 75, 99)):02d}"


class PgIdentity(SqlTask):
    """Типы PostgreSQL, номер от базы (IDENTITY или SERIAL), DEFAULT now(), INSERT … RETURNING."""
    id = "pg_identity"
    title = "Своя таблица в схеме"
    par = 120
    stand = "pg"
    # B7 (аудит 9б, разгрузка): TEXT — тексты вариантов 1 и 2, SERIAL — разбор, RETURNING —
    # карточка upsert; NOT NULL знаком с Картотеки
    scroll = ("psql -c \"CREATE TABLE ops.t (id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY "
              "KEY, …)\" — номер ставит база.\n"
              "NUMERIC(10,2) — деньги с копейками; TIMESTAMPTZ — время с поясом.\n"
              "DEFAULT now() — время вставки ставит база: в INSERT номер и время не перечисляй.")
    variants = (
        Variant("Заведи в схеме ops таблицу watch: id — номер, его ставит база; customer_id — "
                "целое; limit_sum — деньги с копейками (NUMERIC(10,2)); added_at — время с "
                "поясом, по умолчанию now(). Внеси три строки (customer_id, limit_sum): "
                "{rows_text}.",
                hints=("Сначала CREATE TABLE ops.watch с типами, потом INSERT без id и без "
                       "времени — их поставит база.",
                       "id INTEGER GENERATED ALWAYS AS IDENTITY, limit_sum NUMERIC(10,2), "
                       "added_at TIMESTAMPTZ DEFAULT now().",
                       "psql -c \"CREATE TABLE ops.watch (id INTEGER GENERATED ALWAYS AS "
                       "IDENTITY PRIMARY KEY, customer_id INTEGER NOT NULL, limit_sum "
                       "NUMERIC(10,2) NOT NULL, added_at TIMESTAMPTZ NOT NULL DEFAULT now())\""),
                solution="psql -c \"CREATE TABLE ops.watch (id INTEGER GENERATED ALWAYS AS "
                         "IDENTITY PRIMARY KEY, customer_id INTEGER NOT NULL, limit_sum "
                         "NUMERIC(10,2) NOT NULL, added_at TIMESTAMPTZ NOT NULL DEFAULT now())\" "
                         "-c \"INSERT INTO ops.watch (customer_id, limit_sum) VALUES "
                         "{values}\"",
                wrong=("psql -c \"CREATE TABLE ops.watch (id INTEGER GENERATED ALWAYS AS "
                       "IDENTITY PRIMARY KEY, customer_id INTEGER NOT NULL, limit_sum INTEGER "
                       "NOT NULL, added_at TIMESTAMPTZ NOT NULL DEFAULT now())\" -c \"INSERT "
                       "INTO ops.watch (customer_id, limit_sum) VALUES {values}\"",
                       "psql -c \"CREATE TABLE watch (id INTEGER GENERATED ALWAYS AS IDENTITY "
                       "PRIMARY KEY, customer_id INTEGER NOT NULL, limit_sum NUMERIC(10,2) NOT "
                       "NULL, added_at TIMESTAMPTZ NOT NULL DEFAULT now())\" -c \"INSERT INTO "
                       "watch (customer_id, limit_sum) VALUES {values}\""),
                alternatives=("id SERIAL PRIMARY KEY — старый способ: тоже номер от базы",)),
        Variant("Заведи в схеме ops таблицу tickets: id — номер, его ставит база; title — "
                "текст (TEXT); urgent — да или нет (BOOLEAN: TRUE или FALSE), по умолчанию FALSE; "
                "opened_at — время с поясом, по умолчанию now(). Внеси заявки: {rows_text}.",
                hints=("CREATE TABLE ops.tickets с типами, потом INSERT без id и без времени.",
                       "urgent BOOLEAN NOT NULL DEFAULT FALSE, opened_at TIMESTAMPTZ DEFAULT "
                       "now(); срочная — TRUE в VALUES.",
                       "psql -c \"CREATE TABLE ops.tickets (id INTEGER GENERATED ALWAYS AS "
                       "IDENTITY PRIMARY KEY, title TEXT NOT NULL, urgent BOOLEAN NOT NULL "
                       "DEFAULT FALSE, opened_at TIMESTAMPTZ NOT NULL DEFAULT now())\""),
                solution="psql -c \"CREATE TABLE ops.tickets (id INTEGER GENERATED ALWAYS AS "
                         "IDENTITY PRIMARY KEY, title TEXT NOT NULL, urgent BOOLEAN NOT NULL "
                         "DEFAULT FALSE, opened_at TIMESTAMPTZ NOT NULL DEFAULT now())\" -c "
                         "\"INSERT INTO ops.tickets (title, urgent) VALUES {values}\"",
                wrong=("psql -c \"CREATE TABLE ops.tickets (id INTEGER, title TEXT NOT NULL, "
                       "urgent BOOLEAN NOT NULL DEFAULT FALSE, opened_at TIMESTAMPTZ NOT NULL "
                       "DEFAULT now())\" -c \"INSERT INTO ops.tickets (title, urgent) VALUES "
                       "{values}\"",
                       "psql -c \"CREATE TABLE ops.tickets (id INTEGER GENERATED ALWAYS AS "
                       "IDENTITY PRIMARY KEY, title TEXT NOT NULL, urgent BOOLEAN NOT NULL "
                       "DEFAULT FALSE, opened_at TIMESTAMP NOT NULL DEFAULT now())\" -c "
                       "\"INSERT INTO ops.tickets (title, urgent) VALUES {values}\""),
                alternatives=("id SERIAL PRIMARY KEY — старый способ: тоже номер от базы",)),
        Variant("Заведи в схеме ops таблицу notes: id — номер, его ставит база; customer_id — "
                "целое; body — текст (TEXT); amount — деньги с копейками (NUMERIC(10,2)); created_at "
                "— время с поясом, по умолчанию now(). Внеси заметки: {rows_text}.",
                hints=("CREATE TABLE ops.notes с типами, потом INSERT без id и без времени.",
                       "amount NUMERIC(10,2), created_at TIMESTAMPTZ DEFAULT now(); id — "
                       "GENERATED ALWAYS AS IDENTITY.",
                       "psql -c \"CREATE TABLE ops.notes (id INTEGER GENERATED ALWAYS AS "
                       "IDENTITY PRIMARY KEY, customer_id INTEGER NOT NULL, body TEXT NOT NULL, "
                       "amount NUMERIC(10,2), created_at TIMESTAMPTZ NOT NULL DEFAULT now())\""),
                solution="psql -c \"CREATE TABLE ops.notes (id INTEGER GENERATED ALWAYS AS "
                         "IDENTITY PRIMARY KEY, customer_id INTEGER NOT NULL, body TEXT NOT NULL, "
                         "amount NUMERIC(10,2), created_at TIMESTAMPTZ NOT NULL DEFAULT now())\" "
                         "-c \"INSERT INTO ops.notes (customer_id, body, amount) VALUES "
                         "{values}\"",
                wrong=("psql -c \"CREATE TABLE ops.notes (id INTEGER GENERATED ALWAYS AS "
                       "IDENTITY PRIMARY KEY, customer_id INTEGER NOT NULL, body TEXT NOT NULL, "
                       "amount NUMERIC(10,2), created_at TIMESTAMPTZ)\" -c \"INSERT INTO "
                       "ops.notes (customer_id, body, amount) VALUES {values}\"",
                       "psql -c \"CREATE TABLE ops.notes (id INTEGER GENERATED ALWAYS AS "
                       "IDENTITY PRIMARY KEY, customer_id INTEGER NOT NULL, body TEXT NOT NULL, "
                       "amount NUMERIC(10,2), created_at TIMESTAMPTZ NOT NULL DEFAULT now())\" "
                       "-c \"INSERT INTO ops.notes (customer_id, body, amount) VALUES {values}\" "
                       "-c \"INSERT INTO ops.notes (customer_id, body, amount) VALUES "
                       "{values}\""),
                alternatives=("id SERIAL PRIMARY KEY — старый способ: тоже номер от базы",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Тип графы — уговор с базой: NUMERIC(10,2) держит копейки точно, TIMESTAMPTZ "
               "помнит пояс, BOOLEAN — только да или нет. Номер и время вставки база ставит "
               "сама (IDENTITY, DEFAULT now()) — в INSERT их не пиши.")
    spell = ("id INTEGER GENERATED ALWAYS AS IDENTITY; NUMERIC(10,2); TIMESTAMPTZ DEFAULT now(); "
             "INSERT без id и времени")

    def data_state(self, rng, data, variant):
        spec = IDENT_SPECS[variant]
        if variant == 1:
            titles = rng.sample(TICKET_TITLES, 3)
            urgent = rng.randrange(3)
            rows = [[t, i == urgent] for i, t in enumerate(titles)]
            values = ", ".join(f"('{t}', {'TRUE' if u else 'FALSE'})" for t, u in rows)
            text = ", ".join(f"«{t}»" + (" — срочная" if u else "") for t, u in rows)
        else:
            ids = rng.sample(range(1, 61), 3 if variant == 0 else 2)
            if variant == 0:
                rows = [[c, _money(rng)] for c in ids]
                values = ", ".join(f"({c}, {m})" for c, m in rows)
                text = ", ".join(f"({c}, {m})" for c, m in rows)
            else:
                bodies = rng.sample(NOTE_BODIES, len(ids))
                rows = [[c, b, _money(rng)] for c, b in zip(ids, bodies)]
                values = ", ".join(f"({c}, '{b}', {m})" for c, b, m in rows)
                text = "; ".join(f"клиент {c}, «{b}», {m}" for c, b, m in rows)
        return {"values": values, "rows_text": text,
                "want": [[str(v) for v in r] for r in rows], "spec": variant}

    def judge(self, ctx):
        st = ctx.state
        spec = IDENT_SPECS[int(st["spec"])]
        schema, name = dbread.split_table(spec["table"])
        with self.snapshot(ctx) as snap:
            tables = snap.tables()
            if spec["table"] not in tables:
                if name in tables:
                    return Verdict(False, f"Таблица {name} легла в public, а нужна в схеме ops: "
                                          f"имя пиши со схемой — {spec['table']}. Набери reset "
                                          "и заведи заново.")
                return Verdict(False)
            cols = {c["name"]: c for c in snap.columns(spec["table"])}
            why = _ident_columns(spec, cols)
            if why:
                return Verdict(False, why)
            names = [c for c, _ in spec["cols"]]
            got = [[_norm(v) for v in r] for r in snap.rows(spec["table"], names)]
            times = snap.rows(spec["table"], [spec["time"]])
        if not got:
            return Verdict(False)
        want = [list(r) for r in st["want"]]
        if sorted(got) == sorted(want):
            if any(t[0] is None for t in times):
                return Verdict(False, f"У строк нет времени {spec['time']}: его ставит DEFAULT "
                                      "now() — в INSERT эту графу не перечисляй.")
            return Verdict(True)
        if len(got) > len(want) and all(r in got for r in want):
            return Verdict(False, "Строк больше, чем нужно — INSERT ушёл дважды? Набери reset и "
                                  "внеси один раз.")
        # аудит 9б, п. 5: вносят по одной строке — пока каждая внесённая из задания, это ход
        rest = list(want)
        if len(got) < len(want) and all(r in rest and not rest.remove(r) for r in got):
            return Verdict(False, MSG_IDENT_PART.format(n=len(got), m=len(want)))
        return Verdict(False, "Строки не те: сверь VALUES с заданием — порядок граф как в "
                              "скобках после имени таблицы.")

    def task_hint(self, ctx, line):
        return None


MSG_IDENT_PART = "Внесено {n} из {m} строк — докинь остальные (можно и все разом, через запятую)."


def _norm(v) -> str:
    """Значение снимка — к строке ожидания: Decimal('12.50') → «12.50», True → «True»."""
    if isinstance(v, Decimal):
        return f"{v:.2f}"
    return str(v)


def _ident_columns(spec: dict, cols: dict) -> Optional[str]:
    """Что не так с графами таблицы (или None): номер не от базы, типы, DEFAULT времени."""
    idc = cols.get("id")
    if idc is None:
        return "В таблице нет графы id — номер строки, его ставит база."
    auto = idc["identity"] in ("a", "d") or (idc["default"] or "").startswith("nextval(")
    if not auto:
        return ("id ставит база: id INTEGER GENERATED ALWAYS AS IDENTITY (или по-старому "
                "SERIAL). Набери reset и заведи таблицу заново.")
    for col, typ in tuple(spec["cols"]) + ((spec["time"], TZ_TYPE),):
        c = cols.get(col)
        if c is None:
            return f"Нет графы {col} — проверь имена граф по заданию."
        if c["type"] != typ:
            return (f"У {col} тип {c['type'].lower()}, а нужен другой: {TYPE_HINT[typ]}. Набери "
                    "reset и заведи таблицу заново.")
    tdef = cols[spec["time"]]["default"] or ""
    if not any(tdef.startswith(d) for d in NOW_DEFAULTS):
        return (f"У {spec['time']} нет DEFAULT now(): время вставки должна ставить база. Набери "
                "reset и заведи таблицу заново.")
    return None


# --- 5. case_when ---------------------------------------------------------------------------------

MSG_CASE_EDGE = ("Строка ровно на границе ушла не в ту корзину: «от … включительно» — это >= и "
                 "<=, а < и > границу теряют.")
CASE_LO = (1000, 1500, 2000)
CASE_HI = (5000, 6000, 7000)
CASE_EDGE_MIN = 1        # строк ровно на каждой границе — не меньше


class CaseWhen(SqlAnswer):
    """CASE WHEN … THEN … ELSE … END и группировка по метке; граница — < против <=."""
    id = "case_when"
    title = "Корзины"
    par = 75
    scroll = ("\"SELECT CASE WHEN rate < 100 THEN 'low' WHEN rate <= 500 THEN 'mid' ELSE 'high' "
              "END AS band, COUNT(*), SUM(rate) FROM rates GROUP BY band\" — итог по меткам.\n"
              "Метку даёт первое подходящее WHEN, иначе ELSE (нет ELSE — NULL). Граница: < и > её "
              "теряют, <= и >= берут.\n"
              "Запрос — как скажет задание: psql -At -c \"…\" или sqlite3 vault.db \"…\".")
    variants = (
        Variant("Разложи счета (invoices) в {db} по корзинам: small — дешевле {lo}, mid — от {lo} "
                "до {hi} включительно, big — дороже {hi}. Сколько счетов в корзине mid? Ответ: "
                "ans ЧИСЛО",
                hints=("Метку каждой строке даёт CASE WHEN … THEN … ELSE … END, итог по меткам "
                       "— GROUP BY.",
                       "«От {lo} до {hi} включительно»: small — amount < {lo}, mid — amount <= "
                       "{hi}, остальное — big.",
                       "{run} \"SELECT CASE WHEN amount < {lo} THEN 'small' WHEN amount <= {hi} "
                       "THEN 'mid' ELSE 'big' END AS bucket, COUNT(*) FROM invoices GROUP BY "
                       "bucket\""),
                solution="{run} \"SELECT CASE WHEN amount < {lo} THEN 'small' WHEN amount <= {hi} "
                         "THEN 'mid' ELSE 'big' END AS bucket, COUNT(*) FROM invoices GROUP BY "
                         "bucket\"",
                solution_script="{run} \"SELECT COUNT(*) FROM invoices WHERE amount >= {lo} AND "
                                "amount <= {hi}\"",
                wrong=("{run} \"SELECT COUNT(*) FROM invoices WHERE amount > {lo} AND amount <= "
                       "{hi}\"",
                       "{run} \"SELECT COUNT(*) FROM invoices WHERE amount >= {lo} AND amount < "
                       "{hi}\""),
                alternatives=("{run} \"SELECT COUNT(*) FROM invoices WHERE amount BETWEEN {lo} "
                              "AND {hi}\" — одна корзина и без CASE",)),
        Variant("Платежи (payments) в {db}: big — от {hi} и больше, остальные — small. Сколько "
                "денег (сумма amount) в корзине big? Ответ: ans ЧИСЛО",
                hints=("Метка — CASE WHEN … THEN … ELSE … END, деньги по меткам — SUM(amount) и "
                       "GROUP BY.",
                       "«От {hi} и больше» — amount >= {hi}: платёж ровно на {hi} — тоже big.",
                       "{run} \"SELECT CASE WHEN amount >= {hi} THEN 'big' ELSE 'small' END AS "
                       "bucket, SUM(amount) FROM payments GROUP BY bucket\""),
                solution="{run} \"SELECT CASE WHEN amount >= {hi} THEN 'big' ELSE 'small' END AS "
                         "bucket, SUM(amount) FROM payments GROUP BY bucket\"",
                solution_script="{run} \"SELECT SUM(amount) FROM payments WHERE amount >= {hi}\"",
                wrong=("{run} \"SELECT SUM(amount) FROM payments WHERE amount > {hi}\"",
                       "{run} \"SELECT COUNT(*) FROM payments WHERE amount >= {hi}\""),
                alternatives=("{run} \"SELECT SUM(amount) FROM payments WHERE amount >= {hi}\" "
                              "— одна корзина и без CASE",)),
        Variant("Метки счетов (invoices) в {db}: paid — done, все остальные статусы — debt. "
                "Сколько денег (сумма amount) в метке debt? Ответ: ans ЧИСЛО",
                hints=("Метка — CASE WHEN status = 'paid' THEN … ELSE … END: ELSE соберёт все "
                       "остальные статусы.",
                       "SUM(amount) по метке — GROUP BY метке; нужна строка debt.",
                       "{run} \"SELECT CASE WHEN status = 'paid' THEN 'done' ELSE 'debt' END AS "
                       "label, SUM(amount) FROM invoices GROUP BY label\""),
                solution="{run} \"SELECT CASE WHEN status = 'paid' THEN 'done' ELSE 'debt' END "
                         "AS label, SUM(amount) FROM invoices GROUP BY label\"",
                solution_script="{run} \"SELECT SUM(amount) FROM invoices WHERE status <> "
                                "'paid'\"",
                wrong=("{run} \"SELECT SUM(amount) FROM invoices WHERE status = 'open'\"",
                       "{run} \"SELECT SUM(amount) FROM invoices\""),
                alternatives=("{run} \"SELECT SUM(amount) FROM invoices WHERE status <> 'paid'\" "
                              "— одна метка и без CASE",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("CASE — это if для каждой строки: метку даёт первое подходящее WHEN, ELSE "
               "достаётся всем остальным. GROUP BY по метке ссыпает строки в корзины, а судьбу "
               "границы решает знак: < её теряет, <= забирает.")
    spell = ("CASE WHEN x < a THEN 'p' WHEN x <= b THEN 'q' ELSE 'r' END AS m … GROUP BY m")
    trap_messages = {
        "edge": MSG_CASE_EDGE,
        "count": "Это число платежей, а спрашивали деньги: SUM(amount), а не COUNT(*).",
        "one": "Это только один статус, а в метку debt входят все, кроме paid: ELSE соберёт "
               "остальные.",
        "done": "Это метка done (оплаченные), а спрашивали debt — всё, кроме paid.",
        "all": "Это итог по всем строкам сразу — без меток. Нужна одна корзина: CASE и GROUP BY "
               "(или условие WHERE).",
    }

    def data_state(self, rng, data, variant):
        if variant == 1:
            pay = data.tables["payments"]
            hi = rng.choice(CASE_HI)
            for p in rng.sample(pay, CASE_EDGE_MIN + rng.randint(0, 1)):
                p["amount"] = hi
            big = sum(p["amount"] for p in pay if p["amount"] >= hi)
            strict = sum(p["amount"] for p in pay if p["amount"] > hi)
            count = sum(1 for p in pay if p["amount"] >= hi)
            return {"hi": hi, "answer": big, "traps": [["edge", strict], ["count", count]],
                    "totals": [["all", sum(p["amount"] for p in pay)]]}
        inv = data.tables["invoices"]
        if variant == 2:
            sums = Counter()
            for x in inv:
                sums[x["status"]] += x["amount"]
            if sums["open"] == sums["overdue"]:       # две ловушки «один статус» — разные
                x = next(y for y in inv if y["status"] == "open")
                x["amount"] += 1
                sums["open"] += 1
            debt = sums["open"] + sums["overdue"]
            if sums["paid"] == debt:                  # ловушка «done» не равна ответу
                x = next(y for y in inv if y["status"] == "paid")
                x["amount"] += 1
                sums["paid"] += 1
            return {"answer": debt,
                    "traps": [["one", sums["open"]], ["one", sums["overdue"]],
                              ["done", sums["paid"]]],
                    "totals": [["all", debt + sums["paid"]]]}
        lo, hi = rng.choice(CASE_LO), rng.choice(CASE_HI)
        n_lo, n_hi = CASE_EDGE_MIN + rng.randint(0, 1), CASE_EDGE_MIN + rng.randint(0, 1)
        picked = rng.sample(inv, n_lo + n_hi)        # разные строки: границы не затирают друг друга
        for i, x in enumerate(picked):
            x["amount"] = lo if i < n_lo else hi
        amounts = [x["amount"] for x in inv]
        mid = sum(1 for a in amounts if lo <= a <= hi)
        edges = {sum(1 for a in amounts if lo < a <= hi), sum(1 for a in amounts if lo <= a < hi),
                 sum(1 for a in amounts if lo < a < hi)} - {mid}
        return {"lo": lo, "hi": hi, "answer": mid,
                "traps": [["edge", n] for n in sorted(edges)],
                "totals": [["all", len(inv)]]}


# --- B3: подзапросы, WITH, окна, склейки — общее ------------------------------------------------

UNPAID = ("open", "overdue")
# графы Хранилища и псевдонимы, имена WITH из эталонов B3: справа от = это не строка без
# кавычек (db.common_form_hint) — только в откликах Хранилища (db.known_names)
VAULT_NAMES = frozenset({c for cols in dbkit.VAULT_COLUMNS.values() for c in cols}
                        | {t.split(".")[-1] for t in dbkit.VAULT_COLUMNS}
                        | {"s", "t", "m", "r", "u", "g", "d", "share", "prev", "mon", "up",
                           "points", "employee_id", "email", "n", "k", "total"}
                        | {"contracts", "limits", "reviews", "code", "cap", "mark", "big_open",
                           "district_debt", "late_customers", "debt", "excluded", "intake",
                           "limit_sum", "tags", "type", "who", "rate", "note"})


def _clean_districts(data) -> None:
    """Районы одним регистром: «грязный» Kazan/kazan/KAZAN — урок pg_dialect, здесь он
    раздробил бы один район на три группы (данные варианта)."""
    for c in data.tables["customers"]:
        c["district"] = c["district"].lower()


def _pays_of(data) -> dict:
    """invoice_id → суммы его платежей (платежи без счёта — не в счёт)."""
    out = {}
    for p in data.tables["payments"]:
        if p["invoice_id"] is not None:
            out.setdefault(p["invoice_id"], []).append(p["amount"])
    return out


def _distinct_traps(answer, traps) -> list:
    """Ловушки, чьё значение не равно ответу (как части: «kazan 57» = «57 kazan»)."""
    def key(v):
        items = v if isinstance(v, list) else [v]
        return sorted(str(x).casefold() for x in items)
    want = key(answer)
    return [[k, v] for k, v in traps if key(v) != want]


# --- 6. subquery ----------------------------------------------------------------------------------

MSG_NOT_IN_NULL = ("Ноль: у части платежей invoice_id пуст (NULL), а NOT IN со списком, где "
                   "есть NULL, не находит ничего — «а вдруг равно». В подзапросе отсей пустые: "
                   "WHERE invoice_id IS NOT NULL.")
_NOT_IN_NULLABLE = re.compile(r"\bNOT\s+IN\s*\(\s*SELECT\s+(?:DISTINCT\s+)?(?:\w+\.)?invoice_id\s+"
                              r"FROM\s+payments\b(?:(?!\bIS\s+NOT\s+NULL\b)[^)])*\)", re.I)
_UNPAID_SQL = "status IN ('open', 'overdue')"


def _above(rows, ref) -> int:
    """Сколько строк rows дороже среднего по ref (целыми: a·n > сумма — без дробей)."""
    n, tot = len(ref), sum(x["amount"] for x in ref)
    return sum(1 for x in rows if x["amount"] * n > tot)


def _avg_free(groups) -> None:
    """Ни одна сумма не равна среднему своей группы ровно: > и >= дают одно (данные)."""
    for _ in range(100):
        hit = None
        for rows in groups:
            n, tot = len(rows), sum(x["amount"] for x in rows)
            hit = next((x for x in rows if x["amount"] * n == tot), None)
            if hit:
                break
        if hit is None:
            return
        hit["amount"] += 1


def _avg_split(rng, inv, unpaid) -> None:
    """Между средним неоплаченных и средним всех счетов есть неоплаченный счёт: иначе
    «среднее по всем» дало бы тот же счёт, что ответ (данные варианта). Средние далеко —
    оплаченный счёт дорожает; затем неоплаченный встаёт между ними; ни одна сумма не равна
    среднему ровно (_avg_free)."""
    paid = [x for x in inv if x["status"] not in UNPAID]
    for _ in range(50):
        _avg_free((unpaid, inv))
        if _above(unpaid, unpaid) != _above(unpaid, inv):
            return
        au = sum(x["amount"] for x in unpaid) / len(unpaid)
        aa = sum(x["amount"] for x in inv) / len(inv)
        lo, hi = sorted((au, aa))
        if hi - lo < 6:
            rng.choice(paid)["amount"] += 2000
            continue
        x = min(unpaid, key=lambda y: abs(y["amount"] - (lo + hi) / 2))
        x["amount"] = int((lo + hi) / 2)


class Subquery(SqlAnswer):
    """Подзапрос: WHERE x > (SELECT AVG(x) …), IN и NOT IN (SELECT …), NULL в NOT IN."""
    id = "subquery"
    title = "Запрос в запросе"
    par = 75
    scroll = ("Подзапрос — SELECT в скобках внутри другого: \"SELECT COUNT(*) FROM orders WHERE "
              "total > (SELECT AVG(total) FROM orders)\" — дороже среднего.\n"
              "IN (SELECT staff_id FROM visits) — есть в списке, NOT IN — нет. Есть в списке "
              "NULL — NOT IN не найдёт ничего: в скобках WHERE … IS NOT NULL.\n"
              "\"SELECT id FROM orders WHERE total = (SELECT MAX(total) FROM orders)\" — самый "
              "большой.")
    variants = (
        Variant("Неоплаченные счета (invoices) в {db} — со статусом open или overdue. Сколько "
                "из них дороже среднего неоплаченного счёта? Ответ: ans ЧИСЛО",
                hints=("Среднее — подзапрос в скобках: (SELECT AVG(amount) FROM invoices WHERE "
                       "…); снаружи — сравнение с ним.",
                       "Условие на статус нужно дважды: и снаружи, и в скобках — иначе среднее "
                       "посчитано не по тем счетам.",
                       "{run} \"SELECT COUNT(*) FROM invoices WHERE " + _UNPAID_SQL + " AND "
                       "amount > (SELECT AVG(amount) FROM invoices WHERE " + _UNPAID_SQL + ")\""),
                solution="{run} \"SELECT COUNT(*) FROM invoices WHERE " + _UNPAID_SQL + " AND "
                         "amount > (SELECT AVG(amount) FROM invoices WHERE " + _UNPAID_SQL + ")\"",
                wrong=("{run} \"SELECT COUNT(*) FROM invoices WHERE " + _UNPAID_SQL + " AND "
                       "amount > (SELECT AVG(amount) FROM invoices)\"",
                       "{run} \"SELECT COUNT(*) FROM invoices WHERE amount > (SELECT AVG(amount) "
                       "FROM invoices WHERE " + _UNPAID_SQL + ")\""),
                alternatives=("{run} \"SELECT COUNT(*) FROM invoices WHERE status <> 'paid' AND "
                              "amount > (SELECT AVG(amount) FROM invoices WHERE status <> "
                              "'paid')\" — «не paid» — то же самое",)),
        Variant("Сколько счетов (invoices) в {db} не получили ни одного платежа? Платежи — в "
                "payments, счёт платежа — invoice_id (у части платежей он пуст). Ответ: ans "
                "ЧИСЛО",
                hints=("Счета, которых нет в списке invoice_id из payments, — это NOT IN "
                       "(SELECT …).",
                       "В списке есть NULL — с ним NOT IN не найдёт ничего: в скобках отсей "
                       "пустые, WHERE invoice_id IS NOT NULL.",
                       "{run} \"SELECT COUNT(*) FROM invoices WHERE id NOT IN (SELECT invoice_id "
                       "FROM payments WHERE invoice_id IS NOT NULL)\""),
                solution="{run} \"SELECT COUNT(*) FROM invoices WHERE id NOT IN (SELECT "
                         "invoice_id FROM payments WHERE invoice_id IS NOT NULL)\"",
                wrong=("{run} \"SELECT COUNT(*) FROM invoices WHERE id NOT IN (SELECT invoice_id "
                       "FROM payments)\"",
                       "{run} \"SELECT COUNT(*) FROM invoices WHERE status = 'open'\""),
                alternatives=("{run} \"SELECT COUNT(*) FROM invoices i LEFT JOIN payments p ON "
                              "p.invoice_id = i.id WHERE p.id IS NULL\" — через LEFT JOIN",)),
        Variant("Кто из клиентов в {db} выписал самый крупный счёт? Найди сумму подзапросом, а "
                "по ней — счёт и клиента. Ответ: ans ИМЯ ФАМИЛИЯ",
                hints=("Самая крупная сумма — (SELECT MAX(amount) FROM invoices); клиент счёта — "
                       "customer_id.",
                       "Подзапрос в подзапросе: id клиента IN (SELECT customer_id … WHERE amount "
                       "= (SELECT MAX(amount) …)).",
                       "{run} \"SELECT name FROM customers WHERE id IN (SELECT customer_id FROM "
                       "invoices WHERE amount = (SELECT MAX(amount) FROM invoices))\""),
                solution="{run} \"SELECT name FROM customers WHERE id IN (SELECT customer_id FROM "
                         "invoices WHERE amount = (SELECT MAX(amount) FROM invoices))\"",
                wrong=("{run} \"SELECT customer_id FROM invoices WHERE amount = (SELECT "
                       "MAX(amount) FROM invoices)\"",
                       "{run} \"SELECT name FROM customers WHERE id IN (SELECT customer_id FROM "
                       "invoices WHERE amount = (SELECT MAX(amount) FROM payments))\""),
                alternatives=("{run} \"SELECT c.name FROM customers c JOIN invoices i ON "
                              "i.customer_id = c.id ORDER BY i.amount DESC LIMIT 1\" — склейкой "
                              "и сортировкой",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Подзапрос база считает первым и подставляет итог во внешний запрос: среднее, "
               "максимум или список. Один NULL в списке ломает NOT IN: с «не знаю» сравнение "
               "никогда не бывает ложным наверняка.")
    spell = ("x > (SELECT AVG(x) FROM t); id IN (SELECT …); NOT IN (SELECT … WHERE … IS NOT "
             "NULL); = (SELECT MAX(x) …)")
    trap_messages = {
        "avg_all": "Среднее посчитано по всем счетам, а нужно по неоплаченным: условие на статус "
                   "— и в скобках тоже.",
        "all_rows": "Посчитаны все счета, а нужны неоплаченные: условие на статус — и снаружи, "
                    "не только в скобках.",
        "both_all": "Это все счета дороже общего среднего; нужны неоплаченные — условие на "
                    "статус и снаружи, и в скобках.",
        "all_unpaid": "Это все неоплаченные счета — без сравнения со средним: amount > (SELECT "
                      "AVG(amount) …).",
        "open": "Это только открытые (open); без платежа бывают и другие — спроси саму payments: "
                "NOT IN (SELECT invoice_id …).",
        "with": "Это счета С платежами (IN), а спрашивали те, у кого нет ни одного, — NOT IN.",
        "pay_max": "Максимум взят из payments, а нужен самый крупный счёт: (SELECT MAX(amount) "
                   "FROM invoices).",
        "unpaid": "Статус — не то же, что платежи: у просроченного платёж бывает, а «без платежа» "
                  "знает только payments — NOT IN (SELECT invoice_id …).",
        "all_inv": "Это все счета — без условия NOT IN (SELECT …).",
        "sum": "Это клиент с самой большой суммой всех счетов вместе (SUM); спрашивали один самый "
               "крупный счёт — MAX(amount).",
    }
    fallback = "Не то. Сверь подзапрос в скобках: что он возвращает и с чем сравнивается. Застрял — hint."
    MSG_CUST_ID = ("Это номер клиента (customer_id), а спрашивают имя: оно в customers — SELECT "
                   "name FROM customers WHERE id IN (SELECT customer_id …).")

    def task_hint(self, line, state):
        # FB7: вариант «кто выписал»: ответ — имя, а запрос отдаёт голый customer_id
        if (isinstance(state.get("answer"), str) and "customers" not in line
                and re.search(r"SELECT\s+customer_id\b", line, re.I)):
            return self.MSG_CUST_ID
        return None

    def empty_hint(self, line, state=None):
        body = db._SQ_LITERAL.sub("''", line)
        if _NOT_IN_NULLABLE.search(body):
            return MSG_NOT_IN_NULL
        return None

    def data_state(self, rng, data, variant):
        inv = data.tables["invoices"]
        if variant == 1:
            return _nopay_state(rng, data)
        if variant == 2:
            return _max_owner_state(rng, data)
        unpaid = [x for x in inv if x["status"] in UNPAID]
        _avg_split(rng, inv, unpaid)
        ans = _above(unpaid, unpaid)
        traps = [["avg_all", _above(unpaid, inv)], ["all_rows", _above(inv, unpaid)],
                 ["both_all", _above(inv, inv)]]
        return {"answer": ans, "traps": _distinct_traps(ans, traps),
                "totals": [["all_unpaid", len(unpaid)]]}


def _nopay_state(rng, data) -> dict:
    """Счета без платежа: открытые (у них платежей нет вовсе) и не меньше двух прочих — иначе
    «status = 'open'» совпал бы с ответом. Не хватает — платежи двух счетов переводим на
    другие счета (данные варианта)."""
    inv, pay = data.tables["invoices"], data.tables["payments"]
    paid = {p["invoice_id"] for p in pay if p["invoice_id"] is not None}
    closed = [x for x in inv if x["status"] != "open"]
    need = 2 - sum(1 for x in closed if x["id"] not in paid)
    if need > 0:
        withp = [x for x in closed if x["id"] in paid]
        gone = {x["id"] for x in rng.sample(withp, need)}
        keep = [x["id"] for x in withp if x["id"] not in gone]
        for p in pay:
            if p["invoice_id"] in gone:
                p["invoice_id"] = rng.choice(keep)
        paid = {p["invoice_id"] for p in pay if p["invoice_id"] is not None}
    unpaid = sum(1 for x in inv if x["status"] in UNPAID)
    if sum(1 for x in inv if x["id"] not in paid) == unpaid:     # «open или overdue» ≠ ответ
        withp = sorted((x for x in inv if x["id"] in paid), key=lambda x: x["id"])
        x = rng.choice(withp)
        keep = [y["id"] for y in withp if y is not x]
        for p in pay:
            if p["invoice_id"] == x["id"]:
                p["invoice_id"] = rng.choice(keep)
        paid = {p["invoice_id"] for p in pay if p["invoice_id"] is not None}
    ans = sum(1 for x in inv if x["id"] not in paid)
    traps = [["open", sum(1 for x in inv if x["status"] == "open")],
             ["unpaid", unpaid], ["with", len(inv) - ans]]
    return {"answer": ans, "traps": _distinct_traps(ans, traps),
            "totals": [["all_inv", len(inv)]]}


def _max_owner_state(rng, data) -> dict:
    """Самый крупный счёт — один, с запасом над вторым (данные варианта); его клиент — ответ.
    Ловушка — клиент с наибольшей суммой всех счетов, если это другой человек."""
    inv = sorted(data.tables["invoices"], key=lambda x: (-x["amount"], x["id"]))
    pay = data.tables["payments"]
    floor = max(inv[1]["amount"], max(p["amount"] for p in pay))
    if inv[0]["amount"] - floor < 2:
        inv[0]["amount"] = floor + 2 + rng.randrange(40)
    names = {c["id"]: c["name"] for c in data.tables["customers"]}
    for _ in range(30):
        sums = Counter()
        for x in inv:
            sums[x["customer_id"]] += x["amount"]
        top = sorted(sums.items(), key=lambda kv: (-kv[1], kv[0]))
        if top[0][1] > top[1][1] and top[0][0] != inv[0]["customer_id"]:
            break
        # лидер по сумме — тот же клиент (или ничья): крупный счёт уходит самому «лёгкому»
        inv[0]["customer_id"] = top[-1][0] if top[-1][0] != inv[0]["customer_id"] else top[-2][0]
    # «MAX по платежам»: самый крупный счёт дороже любого платежа, а счёта ровно на
    # наибольший платёж у клиента-ответа нет — тот запрос его не назовёт
    for _ in range(200):
        top_pay = max(p["amount"] for p in pay)
        if not any(x["amount"] == top_pay and x["customer_id"] == inv[0]["customer_id"]
                   for x in inv):
            break
        max(pay, key=lambda p: (p["amount"], p["id"]))["amount"] -= 1
    ans = names[inv[0]["customer_id"]]
    traps = [["sum", names[top[0][0]]]]
    top_pay = max(p["amount"] for p in pay)
    by_pay = sorted({names[x["customer_id"]] for x in inv if x["amount"] == top_pay})
    if len(by_pay) == 1:
        traps.append(["pay_max", by_pay[0]])
    return {"answer": ans, "traps": _distinct_traps(ans, traps)}


# --- 7. cte_with ----------------------------------------------------------------------------------

_GOT = "g AS (SELECT invoice_id, SUM(amount) AS s FROM payments GROUP BY invoice_id)"
_LATE = ("t AS (SELECT district, AVG(CASE WHEN status = 'overdue' THEN 1 ELSE 0 END) AS share "
         "FROM invoices i JOIN customers c ON c.id = i.customer_id GROUP BY district)")
_LEDGER = ("t AS (SELECT c.district, SUM(l.amount) AS s FROM ledger l JOIN customers c ON c.id = "
           "l.customer_id GROUP BY c.district)")
CTE_X = (300, 500, 800, 1000, 1200, 1500)
MSG_INT_DIV = ("Целое на целое делится нацело: 3 / 4 — это 0, и у всех районов доля 0. Доля — "
               "AVG(CASE WHEN … THEN 1 ELSE 0 END) или 1.0 * часть / всего.")
_DIVISION = re.compile(r"[\w)]\s*/\s*[\w(]")
_FLOATY = re.compile(r"\b1\.0\b|\d\.\d|::\s*(?:numeric|float|real|decimal|double)|\bCAST\s*\(",
                     re.I)


def _top3(values: dict) -> Optional[List[str]]:
    """Три ключа с наибольшими значениями — или None, если третье и четвёртое равны."""
    order = sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(order) > 3 and order[2][1] == order[3][1]:
        return None
    return sorted(k for k, _ in order[:3])


class CteWith(SqlAnswer):
    """WITH имя AS (…) SELECT …; несколько WITH через запятую; LEFT JOIN итога и COALESCE."""
    id = "cte_with"
    title = "Именованные итоги"
    par = 90
    scroll = ("\"WITH t AS (SELECT staff_id, SUM(total) AS s FROM orders GROUP BY staff_id) "
              "SELECT COUNT(*) FROM t WHERE s > 100\" — итог с именем, запрос к нему.\n"
              "Несколько через запятую: WITH a AS (…), b AS (…) SELECT … FROM a LEFT JOIN b ON …; "
              "нет пары — COALESCE(b.s, 0).\n"
              "Склейка размножает строки и суммы: сначала сложи в WITH, потом клей.")
    variants = (
        Variant("Долг по счёту — сумма счёта (invoices) минус все платежи по нему (payments). "
                "Сколько счетов в {db} с долгом больше {x}? Ответ: ans ЧИСЛО",
                hints=("Платежи одного счёта сначала сложи — в WITH по invoice_id, потом приклей "
                       "этот итог к счетам.",
                       "У счёта без платежей пары нет: LEFT JOIN и COALESCE(g.s, 0). Долг — "
                       "i.amount - COALESCE(g.s, 0).",
                       "{run} \"WITH " + _GOT + " SELECT COUNT(*) FROM invoices i LEFT JOIN g ON "
                       "g.invoice_id = i.id WHERE i.amount - COALESCE(g.s, 0) > {x}\""),
                solution="{run} \"WITH " + _GOT + " SELECT COUNT(*) FROM invoices i LEFT JOIN g "
                         "ON g.invoice_id = i.id WHERE i.amount - COALESCE(g.s, 0) > {x}\"",
                wrong=("{run} \"WITH " + _GOT + " SELECT COUNT(*) FROM invoices i JOIN g ON "
                       "g.invoice_id = i.id WHERE i.amount - g.s > {x}\"",
                       "{run} \"SELECT COUNT(*) FROM invoices i LEFT JOIN payments p ON "
                       "p.invoice_id = i.id WHERE i.amount - p.amount > {x}\""),
                alternatives=("{run} \"SELECT COUNT(*) FROM invoices i WHERE amount - "
                              "COALESCE((SELECT SUM(amount) FROM payments WHERE invoice_id = "
                              "i.id), 0) > {x}\" — подзапросом на каждый счёт",)),
        Variant("Доля просрочки района — какая часть счетов (invoices) его клиентов имеет статус "
                "overdue. В каком районе в {db} доля наибольшая? Ответ: ans РАЙОН",
                hints=("Итог по районам — в WITH: склей счета с клиентами и сгруппируй по "
                       "district.",
                       "Доля — AVG(CASE WHEN status = 'overdue' THEN 1 ELSE 0 END): среднее из "
                       "единиц и нулей. Потом ORDER BY … DESC LIMIT 1.",
                       "{run} \"SELECT district FROM invoices i JOIN customers c ON c.id = "
                       "i.customer_id GROUP BY district ORDER BY AVG(CASE WHEN status = 'overdue' "
                       "THEN 1 ELSE 0 END) DESC LIMIT 1\""),
                solution="{run} \"WITH " + _LATE + " SELECT district FROM t ORDER BY share "
                         "DESC LIMIT 1\"",
                solution_script="{run} \"WITH " + _LATE + " SELECT district FROM t ORDER BY "
                                "share DESC LIMIT 1\"",
                wrong=("{run} \"SELECT district FROM invoices i JOIN customers c ON c.id = "
                       "i.customer_id WHERE status = 'overdue' GROUP BY district ORDER BY "
                       "COUNT(*) DESC LIMIT 1\"",
                       "{run} \"SELECT district FROM invoices i JOIN customers c ON c.id = "
                       "i.customer_id GROUP BY district ORDER BY COUNT(*) DESC LIMIT 1\""),
                alternatives=("{run} \"WITH " + _LATE + " SELECT district, share FROM t ORDER "
                              "BY share DESC\" — все доли списком",)),
        Variant("В ledger строки клиентов: начисления (charge) — с плюсом, оплаты и списания — с "
                "минусом. Чистый долг района — сумма amount строк его клиентов. Какие три района "
                "в {db} с наибольшим чистым долгом? Ответ: ans РАЙОН РАЙОН РАЙОН",
                hints=("Итог по районам — в WITH: склей ledger с customers и сложи amount по "
                       "district.",
                       "Из итога — три первых: ORDER BY s DESC LIMIT 3. Знак уже в amount — "
                       "условие на kind не нужно.",
                       "{run} \"WITH " + _LEDGER + " SELECT district FROM t ORDER BY s DESC LIMIT "
                       "3\""),
                solution="{run} \"WITH " + _LEDGER + " SELECT district FROM t ORDER BY s DESC "
                         "LIMIT 3\"",
                solution_script="{run} \"WITH " + _LEDGER + " SELECT district FROM t ORDER BY s "
                                "DESC LIMIT 3\"",
                wrong=("{run} \"WITH " + _LEDGER.replace("GROUP BY", "WHERE l.kind = 'charge' "
                                                         "GROUP BY") + " SELECT district FROM t "
                       "ORDER BY s DESC LIMIT 3\"",
                       "{run} \"WITH " + _LEDGER + " SELECT district FROM t ORDER BY s LIMIT 3\""),
                alternatives=("WITH c AS (… WHERE kind = 'charge' …), p AS (… WHERE kind <> "
                              "'charge' …) — два итога через запятую и c.s + COALESCE(p.s, 0)",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("WITH даёт промежуточному итогу имя — дальше зови его, как таблицу. Сумму из "
               "другой таблицы сперва сложи в своём WITH и только потом приклеивай — иначе "
               "склейка размножит строки и деньги поплывут.")
    spell = ("WITH g AS (SELECT k, SUM(x) AS s … GROUP BY k) SELECT … FROM t LEFT JOIN g ON …; "
             "COALESCE(g.s, 0); AVG(CASE WHEN … THEN 1 ELSE 0 END) — доля")
    trap_messages = {
        "status": "По статусу долг не узнать: paid бывает оплачен не полностью, а у "
                  "просроченного платёж бывает. Сложи платежи счёта в WITH и вычти.",
        "inner": "Пропали счета без единого платежа: простой JOIN выкидывает тех, у кого пары "
                 "нет. LEFT JOIN и COALESCE(g.s, 0).",
        "rows": "Платежи не сложены: у счёта с двумя платежами — две строки склейки, и каждая "
                "сравнивает долг с одним платежом. Сначала SUM платежей по счёту — в WITH.",
        "all": "Это все счета — условие на долг (WHERE … > {x}) потерялось.",
        "count": "Это район, где просрочек больше всего штук; спрашивали долю — часть от всех "
                 "счетов района: AVG(CASE WHEN … THEN 1 ELSE 0 END).",
        "count_all": "Это район, где больше всего счетов вообще — просрочки тут ни при чём; "
                     "спрашивали долю просроченных: AVG(CASE WHEN status = 'overdue' THEN 1 "
                     "ELSE 0 END).",
        "charge": "Это районы с самыми большими начислениями (charge); чистый долг — сумма всех "
                  "строк ledger: оплаты и списания там с минусом.",
        "least": "Это три района с НАИМЕНЬШИМ долгом: от большего — ORDER BY s DESC.",
    }
    fallback = ("Не то. Проверь WITH отдельно: что он считает и по какой графе приклеен. Застрял "
                "— hint.")

    def task_hint(self, line, state):
        body = db._SQ_LITERAL.sub("''", line)
        sql_body = " ".join(re.findall(r'"([^"]*)"', body))
        if _DIVISION.search(sql_body) and not _FLOATY.search(sql_body):
            return MSG_INT_DIV
        return None

    def data_state(self, rng, data, variant):
        if variant == 1:
            return _late_state(rng, data)
        if variant == 2:
            return _ledger_state(rng, data)
        inv = data.tables["invoices"]
        _underpay(rng, data)
        pays = _pays_of(data)
        debts = [x["amount"] - sum(pays.get(x["id"], [])) for x in inv]
        good = []
        for x in CTE_X:
            if x in debts:
                continue
            ans = sum(1 for d in debts if d > x)
            status = [y for y in inv if y["status"] != "paid"]
            if ans in (len(status), sum(1 for y in status if y["amount"] > x)):
                continue
            rows = sum(1 for y in inv for p in pays.get(y["id"], []) if y["amount"] - p > x)
            free = sum(1 for y in inv if not pays.get(y["id"]) and y["amount"] > x)
            traps = [["inner", sum(1 for y, d in zip(inv, debts) if pays.get(y["id"]) and d > x)],
                     ["rows", rows], ["rows", rows + free], ["status", len(status)],
                     ["status", sum(1 for y in status if y["amount"] > x)]]
            good.append((len(_distinct_traps(ans, traps)), x, ans, traps))
        best = max(n for n, *_ in good)
        _, x, ans, traps = rng.choice([g for g in good if g[0] == best])
        return {"x": x, "answer": ans, "traps": _distinct_traps(ans, traps),
                "totals": [["all", len(inv)]]}


def _underpay(rng, data) -> None:
    """3–6 счетов со статусом paid оплачены не полностью (30–60 %): долг по ним — сотни и
    тысячи, и «по статусу» (status <> 'paid') ответ не получить (данные варианта, fix1 M2)."""
    inv = data.tables["invoices"]
    by = {}
    for p in data.tables["payments"]:
        by.setdefault(p["invoice_id"], []).append(p)
    pool = sorted((x for x in inv if x["status"] == "paid" and x["amount"] >= 3000
                   and x["id"] in by), key=lambda x: x["id"])
    for x in rng.sample(pool, min(len(pool), rng.randint(3, 6))):
        part = x["amount"] * rng.randint(30, 60) // 100
        ps = by[x["id"]]
        for i, p in enumerate(ps):
            p["amount"] = max(1, part // len(ps) + (part % len(ps) if i == 0 else 0))


PG_TIE_FIRST = "samara"       # район, который PostgreSQL отдаёт первым при равных долях (хеш)


def _late_state(rng, data) -> dict:
    """Район с наибольшей долей просрочки — один из маленьких, с запасом 0,02 над вторым, и
    ни просрочек штуками, ни счетов у него не больше всех: «больше всего overdue» и «больше
    всего счетов» с ответом не совпадут (данные варианта: статусы счетов доводим)."""
    _clean_districts(data)
    district = {c["id"]: c["district"] for c in data.tables["customers"]}
    inv = data.tables["invoices"]

    def stats():
        n, late = Counter(), Counter()
        for x in inv:
            d = district[x["customer_id"]]
            n[d] += 1
            late[d] += x["status"] == "overdue"
        return n, late

    def flip(d, to):
        pool = [x for x in inv if district[x["customer_id"]] == d and
                (x["status"] != "overdue" if to == "overdue" else x["status"] == "overdue")]
        if not pool:
            return False
        x = next((y for y in pool if y["status"] == "open"), pool[0])
        x["status"] = to
        return True
    n, late = stats()
    # не первый по алфавиту: доли «целым делением» все 0, и LIMIT 1 взял бы первый (fix1 M1);
    # и не первый в порядке хеш-группировки PostgreSQL (аудит 9б, п. 3: там при ничьей нулей
    # всегда выходит PG_TIE_FIRST — проверено на 40 зёрнах, NullTieTest)
    pool = sorted((d for d in n if n[d] >= 3 and d not in (min(n), PG_TIE_FIRST)),
                  key=lambda d: (n[d], d))
    target = rng.choice(pool[:3])
    for _ in range(500):
        n, late = stats()
        share = {d: late[d] / n[d] for d in n}
        rival = max((d for d in n if d != target), key=lambda d: (share[d], d))
        if share[target] - share[rival] < 0.02:
            if not flip(target, "overdue"):
                flip(rival, "open")
            continue
        if late[target] >= max(late[d] for d in n if d != target):
            big = max((d for d in n if d != target), key=lambda d: (n[d], d))
            flip(big, "overdue")
            continue
        break
    traps = []
    for key, counts in (("count", late), ("count_all", n)):
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if top[0][1] > top[1][1]:
            traps.append([key, top[0][0]])
    return {"answer": target, "traps": _distinct_traps(target, traps)}


def _ledger_state(rng, data) -> dict:
    """Три района с наибольшим чистым долгом по ledger — с запасом над четвёртым (не меньше 2):
    не хватает — начисление третьего района растёт (данные варианта)."""
    _clean_districts(data)
    district = {c["id"]: c["district"] for c in data.tables["customers"]}
    led = data.tables["ledger"]
    for _ in range(10):
        net, charge = Counter(), Counter()
        for r in led:
            d = district[r["customer_id"]]
            net[d] += r["amount"]
            charge[d] += r["amount"] if r["kind"] == "charge" else 0
        order = sorted(net, key=lambda d: (-net[d], d))
        gap = net[order[2]] - net[order[3]]
        if gap >= 2:
            break
        r = next(y for y in led if district[y["customer_id"]] == order[2] and y["kind"] == "charge")
        r["amount"] += 2 - gap + rng.randrange(30)
    ans = sorted(order[:3])
    # «только начисления» не должны дать ту же тройку: району вне ответа — начисление и
    # оплата на одну сумму D (чистый долг тот же, начислений больше третьего в ответе)
    if _top3(dict(charge)) in (None, ans):
        for d in sorted((d for d in net if d not in ans), key=lambda d: (-charge[d], d)):
            rows = [r for r in led if district[r["customer_id"]] == d]
            ch = next((r for r in rows if r["kind"] == "charge"), None)
            pay = next((r for r in rows if r["kind"] != "charge"), None)
            if ch is None or pay is None:
                continue
            gap = max(charge[a] for a in ans) - charge[d] + 2 + rng.randrange(30)
            ch["amount"] += gap
            pay["amount"] -= gap
            charge[d] += gap
            break
    traps = []
    top = _top3(dict(charge))
    if top:
        traps.append(["charge", top])
    low = sorted(net, key=lambda d: (net[d], d))
    if len(low) > 3 and net[low[2]] != net[low[3]]:
        traps.append(["least", sorted(low[:3])])
    return {"answer": ans, "traps": _distinct_traps(ans, traps)}


# --- 8. window_rank -------------------------------------------------------------------------------

_KPI = dbkit.Extra(
    ("employee_id", "points"),
    "CREATE TABLE kpi (employee_id INTEGER PRIMARY KEY REFERENCES employees(id), points INTEGER "
    "NOT NULL)",
    "CREATE TABLE kpi (employee_id integer PRIMARY KEY REFERENCES employees(id), points integer "
    "NOT NULL)")
MSG_RANK_TIE = ("RANK() даёт равным одно место — на месте бывает и двое. Здесь нужен ровно один "
                "на место: ROW_NUMBER() и id вторым ключом.")
_RANK_OVER = re.compile(r"\bRANK\s*\(\s*\)\s*OVER\s*\(([^()]*)\)", re.I)
MSG_ROWNUM_TIE = ("Ноль: ROW_NUMBER ничьих не знает — номера всегда разные. Равным один номер "
                  "даёт RANK().")
MSG_TIE_LUCK = ("Ничья не решена: без второго ключа порядок равных база выбирает сама — sqlite3 "
                "берёт их в порядке чтения, PostgreSQL — как выйдет, и ответ держится на удаче. "
                "Правило ничьей пиши явно: ORDER BY … DESC, id.")
_ROWNUM_OVER = re.compile(r"\bROW_NUMBER\s*\(\s*\)\s*OVER\s*\(([^()]*)\)", re.I)


def no_tiebreak(line: str, outer: bool) -> bool:
    """ROW_NUMBER() OVER (… ORDER BY x DESC) без второго ключа; outer — и сортировка запроса
    ORDER BY x DESC LIMIT … без второго ключа (место через LIMIT/OFFSET). Аудит 9б, п. 4:
    в SQLite равные идут в порядке чтения (по id), и такой запрос «угадывает» меньший id."""
    body = db._SQ_LITERAL.sub("''", line)
    for m in _ROWNUM_OVER.finditer(body):
        order = re.search(r"\bORDER\s+BY\b(.*)", m.group(1), re.I)
        if order and "," not in order.group(1):
            return True
    return outer and bool(re.search(r"\bORDER\s+BY\s+[\w.]+\s+DESC\s+LIMIT\b",
                                    _OVER_BODY.sub(" ", body), re.I))


_RANKED = ("SELECT customer_id, RANK() OVER (PARTITION BY customer_id ORDER BY amount DESC) AS r "
           "FROM invoices")
_KPI_RN = ("SELECT e.id, ROW_NUMBER() OVER (PARTITION BY e.dept ORDER BY k.points DESC, e.id) AS "
           "n FROM employees e JOIN kpi k ON k.employee_id = e.id")


class WindowRank(SqlAnswer):
    """ROW_NUMBER() OVER (PARTITION BY … ORDER BY …, id), RANK(), ничьи."""
    id = "window_rank"
    title = "Места в очереди"
    par = 90
    scroll = ("Окно — номер рядом с каждой строкой: \"SELECT ROW_NUMBER() OVER (PARTITION BY "
              "dept ORDER BY score DESC, id) AS n FROM staff\" — место внутри отдела.\n"
              "Ничья: ROW_NUMBER режет её вторым ключом по id, а RANK() даёт равным одно место и "
              "следующее пропускает: 1, 1, 3.\n"
              "Место в WHERE того же SELECT не видно: окно — в подзапросе, снаружи WHERE n = 1.")
    variants = (
        Variant("Счета клиентов района {district} в {db}: какой из них второй по сумме? При "
                "равных суммах выше тот, у кого меньше id. Ответ: ans ID",
                hints=("Номер по порядку суммы — ROW_NUMBER() OVER (ORDER BY …) среди счетов "
                       "района (склейка с customers).",
                       "Ничья решается вторым ключом: ORDER BY i.amount DESC, i.id. Окно — в "
                       "подзапросе, снаружи WHERE n = 2.",
                       "{run} \"SELECT id FROM (SELECT i.id, ROW_NUMBER() OVER (ORDER BY "
                       "i.amount DESC, i.id) AS n FROM invoices i JOIN customers c ON c.id = "
                       "i.customer_id WHERE c.district = '{district}') t WHERE n = 2\""),
                solution="{run} \"SELECT id FROM (SELECT i.id, ROW_NUMBER() OVER (ORDER BY "
                         "i.amount DESC, i.id) AS n FROM invoices i JOIN customers c ON c.id = "
                         "i.customer_id WHERE c.district = '{district}') t WHERE n = 2\"",
                wrong=("{run} \"SELECT id FROM (SELECT i.id, RANK() OVER (ORDER BY i.amount "
                       "DESC) AS n FROM invoices i JOIN customers c ON c.id = i.customer_id "
                       "WHERE c.district = '{district}') t WHERE n = 2\"",
                       "{run} \"SELECT id FROM (SELECT i.id, ROW_NUMBER() OVER (ORDER BY "
                       "i.amount DESC, i.id DESC) AS n FROM invoices i JOIN customers c ON c.id "
                       "= i.customer_id WHERE c.district = '{district}') t WHERE n = 2\""),
                alternatives=("{run} \"SELECT i.id FROM invoices i JOIN customers c ON c.id = "
                              "i.customer_id WHERE c.district = '{district}' ORDER BY i.amount "
                              "DESC, i.id LIMIT 1 OFFSET 1\" — без окна",)),
        Variant("Первое место клиента — его самый крупный счёт (invoices) в {db}. У скольких "
                "клиентов первое место делят два счёта с равной суммой? Ответ: ans ЧИСЛО",
                hints=("Равным одно место даёт RANK() OVER (PARTITION BY customer_id ORDER BY "
                       "amount DESC).",
                       "Снаружи — строки с r = 1, по клиентам: GROUP BY и HAVING COUNT(*) = 2; "
                       "клиентов сосчитает | wc -l.",
                       "{run} \"SELECT customer_id FROM (" + _RANKED + ") t WHERE r = 1 GROUP BY "
                       "customer_id HAVING COUNT(*) = 2\" | wc -l"),
                solution="{run} \"SELECT customer_id FROM (" + _RANKED + ") t WHERE r = 1 GROUP "
                         "BY customer_id HAVING COUNT(*) = 2\" | wc -l",
                wrong=("{run} \"SELECT COUNT(*) FROM (" + _RANKED + ") t WHERE r = 1\"",
                       "{run} \"SELECT customer_id FROM (" + _RANKED.replace(
                           "RANK()", "ROW_NUMBER()") + ") t WHERE r = 1 GROUP BY customer_id "
                       "HAVING COUNT(*) = 2\" | wc -l"),
                alternatives=("{run} \"SELECT customer_id, COUNT(*) FROM (" + _RANKED + ") t "
                              "WHERE r = 1 GROUP BY customer_id\" — все клиенты: где 2, там "
                              "ничья",)),
        Variant("Баллы сотрудников (employees) — в таблице kpi. Лучший в отделе — с наибольшими "
                "баллами, при равных — с меньшим id. Назови id лучших всех отделов. Ответ: ans "
                "ID ID ID ID",
                hints=("Место внутри отдела — ROW_NUMBER() OVER (PARTITION BY e.dept ORDER BY "
                       "k.points DESC, e.id).",
                       "Склей employees и kpi по id сотрудника; окно — в подзапросе, снаружи WHERE "
                       "n = 1.",
                       "{run} \"SELECT id FROM (" + _KPI_RN + ") t WHERE n = 1\""),
                solution="{run} \"SELECT id FROM (" + _KPI_RN + ") t WHERE n = 1\"",
                wrong=("{run} \"SELECT id FROM (" + _KPI_RN.replace(
                           "ROW_NUMBER()", "RANK()").replace(", e.id)", ")") + ") t WHERE n = "
                       "1\"",
                       "{run} \"SELECT e.id FROM employees e JOIN kpi k ON k.employee_id = e.id "
                       "ORDER BY k.points DESC LIMIT 4\""),
                alternatives=("{run} \"SELECT e.dept, e.id, k.points FROM employees e JOIN kpi k "
                              "ON k.employee_id = e.id ORDER BY e.dept, k.points DESC, e.id\" — "
                              "глазами по отделам",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Окно нумерует строки и, в отличие от GROUP BY, их не сворачивает: PARTITION BY "
               "делит на группы, ORDER BY задаёт порядок. При ничьей ROW_NUMBER всё равно "
               "раздаёт разные номера (решает второй ключ), а RANK — один на всех равных.")
    spell = ("ROW_NUMBER() OVER (PARTITION BY g ORDER BY x DESC, id); RANK() — ничьи вместе; окно "
             "в подзапросе, снаружи WHERE n = 1")
    trap_messages = {
        "first": "Это первый по сумме, а нужен второй: снаружи WHERE n = 2.",
        "tie_hi": "Ничья: из двух равных выше тот, у кого id меньше, — ORDER BY … DESC, id (id по "
                  "возрастанию).",

        "rows": "Это строки с первым местом, а не клиенты: клиенты с ничьей — группы, где таких "
                "строк две (GROUP BY и HAVING COUNT(*) = 2).",
        "all": "Это все клиенты со счетами: ничья у первого места — не у каждого.",
        "global": "Это четыре лучших всего Хранилища, а нужен лучший в каждом отделе: PARTITION BY "
                  "e.dept.",
    }
    fallback = "Не то. Проверь окно: чем делит (PARTITION BY), как сортирует и какое место берёшь. Застрял — hint."

    def extend(self, rng, data):
        pts = rng.sample(range(10, 300), len(data.tables["employees"]))
        data.extra["kpi"] = _KPI
        data.tables["kpi"] = [{"employee_id": e["id"], "points": p}
                              for e, p in zip(data.tables["employees"], pts)]
        return data

    def empty_hint(self, line, state=None):
        if re.search(r"\bROW_NUMBER\s*\(", line, re.I) and re.search(r"COUNT\(\*\)\s*=\s*2", line):
            return MSG_ROWNUM_TIE
        return None

    def task_hint(self, line, state):
        """Варианты A и C просят одного на место: RANK там — по форме запроса, без ответа
        (ловушка «двое разом» выдавала бы, что ответ среди сданных)."""
        v = base.variant_index(state.get("_variant", 0), len(self.variants))
        if v == 1:
            return None
        for m in _RANK_OVER.finditer(line):
            order = re.search(r"\bORDER\s+BY\b(.*)", m.group(1), re.I)
            if order is None or "," not in order.group(1):    # без второго ключа (ревью I2)
                return MSG_RANK_TIE
        if no_tiebreak(line, outer=v == 0):
            return MSG_TIE_LUCK
        return None

    def check(self, ctx):
        """Аудит 9б, п. 4: ответ запросом без второго ключа — тот же отклик, верен он или нет
        (равные база ставит как придётся): ни засчёта на удачу, ни подсказки ответа."""
        v = base.variant_index(ctx.state.get("_variant", 0), len(self.variants))
        if ctx.answer is not None and v != 1 and no_tiebreak(last_client_line(ctx), v == 0):
            return Verdict(False, MSG_TIE_LUCK)
        return super().check(ctx)

    def data_state(self, rng, data, variant):
        if variant == 2:
            return _kpi_state(rng, data)
        if variant == 1:
            mine = {}
            for x in data.tables["invoices"]:
                mine.setdefault(x["customer_id"], []).append(x)
            return _tied_tops_state(rng, mine)
        _clean_districts(data)
        district = {c["id"]: c["district"] for c in data.tables["customers"]}
        by = {}
        for x in data.tables["invoices"]:
            by.setdefault(district[x["customer_id"]], []).append(x)
        d = rng.choice(sorted(k for k, v in by.items() if len(v) >= 4))
        rows = sorted(by[d], key=lambda x: (-x["amount"], x["id"]))
        top, a, b = rows[0], rows[1], rows[2]
        a["amount"] = b["amount"]
        top["amount"] = max(top["amount"], b["amount"] + 2)
        for z in rows[3:]:
            z["amount"] = min(z["amount"], b["amount"] - 1)
        lo, hi = sorted((a["id"], b["id"]))
        traps = [["first", top["id"]], ["tie_hi", hi]]
        return {"district": d, "answer": lo, "traps": traps}


def _tied_tops_state(rng, by) -> dict:
    """У k клиентов (1–3) первое место делят два счёта, у остальных самый крупный счёт один
    (данные варианта)."""
    pool = sorted(d for d, v in by.items() if len(v) >= 3)
    tied = set(rng.sample(pool, rng.randint(1, 3)))
    for d, rows in by.items():
        rows = sorted(rows, key=lambda x: (-x["amount"], x["id"]))
        top = rows[0]
        if d in tied:
            rows[1]["amount"] = top["amount"]
            rest = rows[2:]
        else:
            rest = rows[1:]
        for z in rest:
            z["amount"] = min(z["amount"], top["amount"] - 1)
    k = len(tied)
    return {"answer": k, "traps": [["rows", len(by) + k]], "totals": [["all", len(by)]]}


def _kpi_state(rng, data) -> dict:
    """Лучший каждого отдела (ничья — меньший id); в одном отделе первое место делят двое."""
    pts = {r["employee_id"]: r for r in data.tables["kpi"]}
    by = {}
    for e in data.tables["employees"]:
        by.setdefault(e["dept"], []).append(e["id"])
    dept = rng.choice(sorted(d for d, ids in by.items() if len(ids) >= 3))
    order = sorted(by[dept], key=lambda i: -pts[i]["points"])
    pts[order[1]]["points"] = pts[order[0]]["points"]
    for i in order[2:]:
        pts[i]["points"] = min(pts[i]["points"], pts[order[0]]["points"] - 1)
    best, other = {}, None
    for d, ids in by.items():
        ids = sorted(ids, key=lambda i: (-pts[i]["points"], i))
        best[d] = ids[0]
        if d == dept:
            other = ids[1]
    ans = sorted(best.values())
    traps = [["tie_hi", sorted([v for k, v in best.items() if k != dept] + [other])]]
    ranked = sorted(pts.values(), key=lambda r: (-r["points"], r["employee_id"]))
    if ranked[3]["points"] != ranked[4]["points"]:
        traps.append(["global", sorted(r["employee_id"] for r in ranked[:4])])
    return {"answer": ans, "traps": _distinct_traps(ans, traps)}


# --- 9. window_lag --------------------------------------------------------------------------------

# аудит 9б, п. 1: в PostgreSQL NULL при DESC встаёт первым — рост первого месяца (LAG там NULL)
MSG_NULL_FIRST = ("В PostgreSQL пустое (NULL) при DESC встаёт первым, а у первого месяца роста "
                  "нет: LAG там NULL. Отсей его — WHERE … IS NOT NULL — или сортируй ORDER BY … "
                  "DESC NULLS LAST.")
MSG_NULL_MONTH = ("Рядом с месяцем пусто — это первый месяц: прошлого у него нет, и рост (s - "
                  "LAG(s)) там NULL. В PostgreSQL NULL при DESC встаёт первым: WHERE … IS NOT "
                  "NULL или NULLS LAST.")
_OVER_BODY = re.compile(r"\bOVER\s*\([^()]*\)", re.I)
_NULL_GUARD = re.compile(r"\bIS\s+NOT\s+NULL\b|\bNULLS\s+LAST\b|\bCOALESCE\s*\(", re.I)


def null_first_desc(line: str) -> bool:
    """LAG и сортировка DESC снаружи окна без защиты от NULL (IS NOT NULL, NULLS LAST,
    COALESCE): в PostgreSQL первой строкой встанет пустой рост первого месяца."""
    body = db._SQ_LITERAL.sub("''", line)
    if not re.search(r"\bLAG\s*\(", body, re.I) or _NULL_GUARD.search(body):
        return False
    return bool(re.search(r"\bDESC\b", _OVER_BODY.sub(" ", body), re.I))

_MONTHLY = "m AS (SELECT {month} AS mon, SUM(amount) AS s FROM payments GROUP BY mon)"
# месяц, сданный датой первого дня (date_trunc, ::date): 2026-08-01 [00:00:00] — это 2026-08
_MONTH_DAY1 = re.compile(r"(?<![\d-])(\d{4}-\d{2})-01(?:[ T]00:00:00(?:\+00(?::00)?)?)?(?![\d:])")


class WindowLag(SqlAnswer):
    """LAG(x) OVER (ORDER BY …), SUM(x) OVER (ORDER BY …) — накопительный итог; месяц текстом
    (strftime, to_char) или первым днём (date_trunc)."""
    id = "window_lag"
    title = "Сверка по месяцам"
    par = 90
    scroll = ("LAG(s) — значение прошлой строки: s - LAG(s) OVER (ORDER BY mon) — рост к "
              "прошлому месяцу (у первого — NULL; в PostgreSQL при DESC он первый — NULLS LAST).\n"
              "SUM(s) OVER (ORDER BY mon) — накопительный итог до этой строки.\n"
              "Месяц: \"SELECT strftime('%Y-%m', t)\" в SQLite, \"SELECT to_char(t, 'YYYY-MM')\" "
              "в PostgreSQL; \"SELECT date_trunc('month', t)\" — первый день.")
    variants = (
        Variant("Оплаты (payments) в {db} по месяцам — месяц: {month}. В каком месяце рост к "
                "прошлому месяцу наибольший и какой он? Ответ: ans ГГГГ-ММ ЧИСЛО",
                hints=("Сначала итог по месяцам — WITH m AS (SELECT {month} AS mon, SUM(amount) "
                       "AS s … GROUP BY mon).",
                       "Рост — s - LAG(s) OVER (ORDER BY mon); у первого месяца он NULL. Выбери "
                       "наибольший.",
                       "{run} \"WITH " + _MONTHLY + " SELECT mon, s - LAG(s) OVER (ORDER BY mon) "
                       "FROM m\""),
                solution="{run} \"WITH " + _MONTHLY + " SELECT mon, s - LAG(s) OVER (ORDER BY "
                         "mon) FROM m\"",
                solution_script="{run} \"WITH " + _MONTHLY + ", d AS (SELECT mon, s - LAG(s) "
                                "OVER (ORDER BY mon) AS up FROM m) SELECT mon, up FROM d WHERE up "
                                "IS NOT NULL ORDER BY up DESC LIMIT 1\"",
                wrong=("{run} \"WITH " + _MONTHLY + " SELECT mon, s FROM m ORDER BY s DESC LIMIT "
                       "1\"",
                       "{run} \"WITH " + _MONTHLY + ", d AS (SELECT mon, LAG(s) OVER (ORDER BY "
                       "mon) - s AS up FROM m) SELECT mon, up FROM d WHERE up IS NOT NULL ORDER "
                       "BY up DESC LIMIT 1\""),
                alternatives=("в PostgreSQL — date_trunc('month', paid_at) вместо {month}: "
                              "месяц первым днём, ответ вида ГГГГ-ММ-01 тоже примут",)),
        Variant("Накопительный итог оплат (payments) в {db} по месяцам — месяц: {month}. Сколько "
                "всего заплачено к концу {mon}? Ответ: ans ЧИСЛО",
                hints=("Итог по месяцам — в WITH, накопительный — SUM(s) OVER (ORDER BY mon).",
                       "Накопительный итог месяца — все месяцы до него включительно; нужна строка "
                       "{mon}.",
                       "{run} \"WITH " + _MONTHLY + " SELECT mon, SUM(s) OVER (ORDER BY mon) "
                       "FROM m\""),
                solution="{run} \"WITH " + _MONTHLY + " SELECT mon, SUM(s) OVER (ORDER BY mon) "
                         "FROM m\"",
                solution_script="{run} \"WITH " + _MONTHLY + ", r AS (SELECT mon, SUM(s) OVER "
                                "(ORDER BY mon) AS total FROM m) SELECT total FROM r WHERE mon = "
                                "'{mon}'\"",
                wrong=("{run} \"WITH " + _MONTHLY + " SELECT s FROM m WHERE mon = '{mon}'\"",
                       "{run} \"SELECT SUM(amount) FROM payments\""),
                alternatives=("{run} \"SELECT SUM(amount) FROM payments WHERE {month} <= "
                              "'{mon}'\" — одной суммой, без окна",)),
        Variant("Платежи (payments) в {db} по порядку времени (paid_at): сколько раз платёж "
                "оказался крупнее предыдущего? Ответ: ans ЧИСЛО",
                hints=("Прошлый платёж рядом с нынешним — LAG(amount) OVER (ORDER BY paid_at).",
                       "Окно — в подзапросе, снаружи считай строки, где amount больше прошлого; у "
                       "первого прошлого нет (NULL).",
                       "{run} \"SELECT COUNT(*) FROM (SELECT amount, LAG(amount) OVER (ORDER BY "
                       "paid_at) AS prev FROM payments) t WHERE amount > prev\""),
                solution="{run} \"SELECT COUNT(*) FROM (SELECT amount, LAG(amount) OVER (ORDER BY "
                         "paid_at) AS prev FROM payments) t WHERE amount > prev\"",
                wrong=("{run} \"SELECT COUNT(*) FROM (SELECT amount, LAG(amount) OVER (ORDER BY "
                       "id) AS prev FROM payments) t WHERE amount > prev\"",
                       "{run} \"SELECT COUNT(*) FROM (SELECT amount, LAG(amount) OVER (ORDER BY "
                       "paid_at) AS prev FROM payments) t WHERE amount < prev\""),
                alternatives=("{run} \"SELECT amount, LAG(amount) OVER (ORDER BY paid_at) FROM "
                              "payments\" — сначала посмотреть пары",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("LAG подглядывает в прошлую строку окна, SUM(…) OVER копит итог от первой строки "
               "до этой — без GROUP BY и без склейки таблицы с собой. Что тут «прошлое», решает "
               "ORDER BY внутри OVER.")
    spell = ("s - LAG(s) OVER (ORDER BY mon) — рост; SUM(s) OVER (ORDER BY mon) — накопительно; "
             "strftime('%Y-%m', t) или to_char(t, 'YYYY-MM')")
    trap_messages = {
        "sum": "Это месяц с наибольшей суммой; спрашивали рост к прошлому месяцу — s - LAG(s).",
        "sign": "Знак наоборот: рост — нынешний минус прошлый, s - LAG(s), а не LAG(s) - s.",
        "one": "Это сумма одного {mon}; накопительный итог — все месяцы до него включительно: "
               "SUM(s) OVER (ORDER BY mon).",
        "before": "Это итог на конец прошлого месяца; {mon} — включительно.",
        "all": "Это итог за всё время, а нужен на конец {mon}.",
        "by_id": "LAG берёт прошлую строку в порядке OVER: «по времени» — ORDER BY paid_at, а не "
                 "id.",
        "ge": "Равные платежи «крупнее» не считаются: amount > prev, а не >=.",
        "down": "Это сколько раз платёж был МЕНЬШЕ прошлого: знак наоборот, amount > prev.",
        "all_pay": "Это все платежи — без сравнения с прошлым (WHERE amount > prev).",
    }
    fallback = "Не то. Проверь порядок в OVER (ORDER BY …) и что из чего вычитаешь. Застрял — hint."

    def check(self, ctx):
        if ctx.answer is not None:
            ctx = dataclasses.replace(ctx, answer=_MONTH_DAY1.sub(r"\1", ctx.answer))
        return super().check(ctx)

    def task_hint(self, line, state):
        if (base.variant_index(state.get("_variant", 0), len(self.variants)) == 0
                and self.engine_of(state) == "pg" and null_first_desc(line)):
            return MSG_NULL_FIRST
        return None

    def wrong_message(self, given, ctx):
        # сдан один первый месяц (рост пуст) — это строка NULL, а не неполный ответ
        if ctx.state.get("m0") and textnorm.parts(textnorm.clean(given)) == [ctx.state["m0"]]:
            return MSG_NULL_MONTH
        return super().wrong_message(given, ctx)

    def data_state(self, rng, data, variant):
        pay = data.tables["payments"]
        if variant == 2:
            return _ups_state(rng, pay)
        months = sorted({p["paid_at"][:7] for p in pay})
        s = Counter()
        for p in pay:
            s[p["paid_at"][:7]] += p["amount"]
        if variant == 1:
            mon = rng.choice(months[1:-1])
            run = sum(s[m] for m in months if m <= mon)
            traps = [["one", s[mon]], ["before", run - s[mon]]]
            return {"mon": mon, "answer": run, "traps": _distinct_traps(run, traps),
                    "totals": [["all", sum(s.values())]]}
        d = {i: s[months[i]] - s[months[i - 1]] for i in range(1, len(months))}
        j = max(d, key=lambda i: (d[i], rng.random()))
        boost = max(0, max(v for i, v in d.items() if i != j) - d[j] + 2, 1 - d[j])
        if boost:
            _add_payments(rng, data, months[j], boost)
            s[months[j]] += boost
            d = {i: s[months[i]] - s[months[i - 1]] for i in range(1, len(months))}
        ans = [months[j], d[j]]
        top = max(months, key=lambda m: (s[m], m))
        first = months[0]           # первый месяц — его рост NULL (открыто: месяцы видны всем)
        traps = [["sum", [top, s[top]]]]
        low = min(d, key=lambda i: (d[i], i))
        if d[low] < 0:
            traps.append(["sign", [months[low], -d[low]]])
        return {"answer": ans, "traps": _distinct_traps(ans, traps), "m0": first}


def _add_payments(rng, data, month: str, total: int) -> None:
    """Добавить в месяц платежи на сумму total — обычного размера (до 8000 каждый), к
    случайным оплаченным счетам (данные варианта: рост месяца без одного гигантского платежа)."""
    pay = data.tables["payments"]
    paid = [x["id"] for x in data.tables["invoices"] if x["status"] != "open"]
    lo = f"{month}-01"
    hi = f"{month}-28"
    while total > 0:
        part = min(total, rng.randrange(2000, 8000))
        pay.append({"id": max(p["id"] for p in pay) + 1, "invoice_id": rng.choice(paid),
                    "paid_at": dbkit._vault_ts(rng, lo, hi), "amount": part})
        total -= part


def _ups_state(rng, pay) -> dict:
    """Время платежей без повторов (иначе порядок ORDER BY paid_at не определён); счёт
    «крупнее прошлого» по времени и ловушки: по id, >=, «меньше»."""
    seen = set()
    for p in sorted(pay, key=lambda p: p["id"]):
        while p["paid_at"] in seen:
            p["paid_at"] = dbkit._vault_ts(rng)
        seen.add(p["paid_at"])

    def count(rows, sign=1):
        a = [p["amount"] for p in rows]
        return sum(1 for x, y in zip(a, a[1:]) if (y - x) * sign > 0)
    by_id = count(sorted(pay, key=lambda p: p["id"]))
    for _ in range(200):         # «по id» и «меньше прошлого» не совпадут с ответом: соседей
        by_time = sorted(pay, key=lambda p: p["paid_at"])     # по времени меняем местами
        up = count(by_time)
        if up not in (by_id, count(by_time, -1)):
            break
        i = rng.randrange(len(by_time) - 1)
        a, b = by_time[i], by_time[i + 1]
        if a["amount"] != b["amount"] and abs(a["id"] - b["id"]) > 1:
            a["paid_at"], b["paid_at"] = b["paid_at"], a["paid_at"]

    def ups(rows, op):
        a = [p["amount"] for p in rows]
        return sum(1 for x, y in zip(a, a[1:]) if op(y, x))
    by_time = sorted(pay, key=lambda p: p["paid_at"])
    ans = ups(by_time, lambda y, x: y > x)
    traps = [["by_id", ups(sorted(pay, key=lambda p: p["id"]), lambda y, x: y > x)],
             ["ge", ups(by_time, lambda y, x: y >= x)],
             ["down", ups(by_time, lambda y, x: y < x)]]
    return {"answer": ans, "traps": _distinct_traps(ans, traps),
            "totals": [["all_pay", len(pay)]]}


# --- 10. joins_more -------------------------------------------------------------------------------

_LISTS = {
    "leads": dbkit.Extra(("id", "email"),
                         "CREATE TABLE leads (id INTEGER PRIMARY KEY, email TEXT NOT NULL)",
                         "CREATE TABLE leads (id integer PRIMARY KEY, email text NOT NULL)"),
    "subscribers": dbkit.Extra(("id", "email"),
                               "CREATE TABLE subscribers (id INTEGER PRIMARY KEY, email TEXT NOT "
                               "NULL)",
                               "CREATE TABLE subscribers (id integer PRIMARY KEY, email text NOT "
                               "NULL)"),
}
MIN_UNION_SHARED = 3          # общих адресов у двух списков — не меньше (план: пересечение UNION)


class JoinsMore(SqlAnswer):
    """FULL JOIN (непарные с обеих сторон), таблица с собой (сотрудник → начальник), UNION
    против UNION ALL."""
    id = "joins_more"
    title = "Обе стороны"
    par = 90
    scroll = ("FULL JOIN — все строки обеих таблиц; нет пары — NULL с той стороны. Непарные: "
              "WHERE a.id IS NULL OR b.id IS NULL.\n"
              "Таблица сама с собой: FROM staff s JOIN staff boss ON boss.id = s.boss_id — "
              "рядом с каждым его начальник.\n"
              "UNION — строки двух SELECT без повторов, UNION ALL — все подряд, с повторами.")
    variants = (
        Variant("Непарные строки в {db}: счета (invoices) без единого платежа и платежи "
                "(payments) без счёта — invoice_id пуст. Сколько их всего вместе? Ответ: ans "
                "ЧИСЛО",
                hints=("Обе стороны разом вытащит FULL JOIN invoices и payments по invoice_id.",
                       "Непарная строка — та, где с одной стороны NULL: WHERE i.id IS NULL OR "
                       "p.id IS NULL.",
                       "{run} \"SELECT COUNT(*) FROM invoices i FULL JOIN payments p ON "
                       "p.invoice_id = i.id WHERE i.id IS NULL OR p.id IS NULL\""),
                solution="{run} \"SELECT COUNT(*) FROM invoices i FULL JOIN payments p ON "
                         "p.invoice_id = i.id WHERE i.id IS NULL OR p.id IS NULL\"",
                wrong=("{run} \"SELECT COUNT(*) FROM invoices i LEFT JOIN payments p ON "
                       "p.invoice_id = i.id WHERE p.id IS NULL\"",
                       "{run} \"SELECT COUNT(*) FROM invoices i FULL JOIN payments p ON "
                       "p.invoice_id = i.id\""),
                alternatives=("{run} \"SELECT COUNT(*) FROM invoices WHERE id NOT IN (SELECT "
                              "invoice_id FROM payments WHERE invoice_id IS NOT NULL)\" плюс "
                              "{run} \"SELECT COUNT(*) FROM payments WHERE invoice_id IS NULL\" — "
                              "двумя запросами",)),
        Variant("У сотрудника (employees) в {db} manager_id — id его начальника. У кого больше "
                "всего прямых подчинённых? Ответ: ans ИМЯ ФАМИЛИЯ",
                hints=("Таблица сама с собой: employees e JOIN employees m ON m.id = "
                       "e.manager_id — рядом с каждым его начальник m.",
                       "Подчинённых считает GROUP BY m.id, m.name и COUNT(*); первый — ORDER BY "
                       "COUNT(*) DESC LIMIT 1.",
                       "{run} \"SELECT m.name FROM employees e JOIN employees m ON m.id = "
                       "e.manager_id GROUP BY m.id, m.name ORDER BY COUNT(*) DESC LIMIT 1\""),
                solution="{run} \"SELECT m.name FROM employees e JOIN employees m ON m.id = "
                         "e.manager_id GROUP BY m.id, m.name ORDER BY COUNT(*) DESC LIMIT 1\"",
                wrong=("{run} \"SELECT e.name FROM employees e JOIN employees m ON m.id = "
                       "e.manager_id GROUP BY e.id, e.name ORDER BY COUNT(*) DESC LIMIT 1\"",
                       "{run} \"SELECT manager_id FROM employees GROUP BY manager_id ORDER BY "
                       "COUNT(*) DESC LIMIT 1\""),
                alternatives=("{run} \"SELECT name FROM employees WHERE id = (SELECT manager_id "
                              "FROM employees GROUP BY manager_id ORDER BY COUNT(manager_id) DESC "
                              "LIMIT 1)\" — подзапросом",)),
        Variant("Два списка почт в {db} — leads и subscribers (графа email). Сколько разных "
                "адресов в них вместе? Ответ: ans ЧИСЛО",
                hints=("Строки двух SELECT в один столбик сложит UNION.",
                       "UNION убирает повторы, UNION ALL — нет. Строки склейки сосчитай: SELECT "
                       "COUNT(*) FROM (… UNION …) t.",
                       "{run} \"SELECT COUNT(*) FROM (SELECT email FROM leads UNION SELECT email "
                       "FROM subscribers) t\""),
                solution="{run} \"SELECT COUNT(*) FROM (SELECT email FROM leads UNION SELECT "
                         "email FROM subscribers) t\"",
                wrong=("{run} \"SELECT COUNT(*) FROM (SELECT email FROM leads UNION ALL SELECT "
                       "email FROM subscribers) t\"",
                       "{run} \"SELECT COUNT(DISTINCT email) FROM leads\""),
                alternatives=("{run} \"SELECT email FROM leads UNION SELECT email FROM "
                              "subscribers\" | wc -l — строки считает wc",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("FULL JOIN не бросает непарных ни с одной стороны, LEFT — только слева. Ссылка "
               "ведёт в ту же таблицу — склей её с собой под двумя кличками. UNION сливает два "
               "списка и выкидывает повторы, UNION ALL берёт всё.")
    spell = ("FULL JOIN … WHERE a.id IS NULL OR b.id IS NULL; FROM t a JOIN t b ON b.id = a.ref; "
             "UNION — без повторов, UNION ALL — с ними")
    trap_messages = {
        "left": "Это только счета без платежей (LEFT JOIN); платежи без счёта — с другой стороны: "
                "FULL JOIN.",
        "orphans": "Это только платежи без счёта; счета без платежей — тоже непарные: FULL JOIN.",
        "all_rows": "Это все строки склейки; непарные — где с одной стороны NULL: WHERE … IS NULL "
                    "OR … IS NULL.",
        "union_all": "С повторами: UNION ALL склеивает всё подряд. Разные адреса — UNION.",
        "one": "Это один список, а нужны оба вместе — UNION двух SELECT.",
        "both": "Общие адреса посчитаны дважды: списки сливает UNION, и повтор между ними — один "
                "адрес.",
    }
    fallback = "Не то. Проверь склейку: какие строки она оставляет и что считаешь. Застрял — hint."

    def task_hint(self, line, state):
        """Аудит 9б, п. 8: «начальник» — по форме запроса (имя подчинённого, номер вместо имени,
        перевёрнутый ON); ответ не нужен."""
        if base.variant_index(state.get("_variant", 0), len(self.variants)) != 1:
            return None
        return boss_join_shape(line)

    def wrong_message(self, given, ctx):
        if base.variant_index(ctx.state.get("_variant", 0), len(self.variants)) == 1 and \
                textnorm.as_number(textnorm.clean(given)) is not None:
            return MSG_BOSS_NUM
        return super().wrong_message(given, ctx)

    def extend(self, rng, data):
        own = [c["email"] for c in data.tables["customers"] if c["email"]]
        shared = rng.sample(own, MIN_UNION_SHARED + rng.randint(0, 2))
        rest = [e for e in own if e not in shared]
        extra = rng.sample(rest, rng.randint(4, 7))
        leads = shared + extra[:len(extra) // 2] + [f"lead{i}@new.example" for i in range(
            rng.randint(1, 3))]
        subs = shared + extra[len(extra) // 2:] + [f"sub{i}@new.example" for i in range(
            rng.randint(1, 3))]
        leads += rng.sample(leads, rng.randint(1, 2))          # повторы внутри списка
        rng.shuffle(leads)
        rng.shuffle(subs)
        for name, emails in (("leads", leads), ("subscribers", subs)):
            data.extra[name] = _LISTS[name]
            data.tables[name] = [{"id": i, "email": e} for i, e in enumerate(emails, start=1)]
        return data

    def data_state(self, rng, data, variant):
        if variant == 1:
            return _boss_state(rng, data)
        if variant == 2:
            a = [r["email"] for r in data.tables["leads"]]
            b = [r["email"] for r in data.tables["subscribers"]]
            ans = len(set(a) | set(b))
            traps = [["union_all", len(a) + len(b)], ["one", len(set(a))], ["one", len(a)],
                     ["one", len(b)], ["both", len(set(a)) + len(set(b))]]
            return {"answer": ans, "traps": _distinct_traps(ans, traps)}
        return _unpaired_state(rng, data)


MSG_BOSS_SUB = ("Это имя подчинённого. Начальник в склейке — тот, чей id стоит в manager_id "
                "другого: ON m.id = e.manager_id, и его имя — m.name (группируй по m).")
MSG_BOSS_NUM = ("Это номер начальника, а нужно имя: склей таблицу с собой — employees e JOIN "
                "employees m ON m.id = e.manager_id — и возьми m.name.")
_SELF_JOIN = re.compile(r"\bemployees\s+(?:AS\s+)?(\w+)\s+(?:INNER\s+|LEFT\s+)?JOIN\s+employees\s+"
                        r"(?:AS\s+)?(\w+)\s+ON\s+(\w+)\.(id|manager_id)\s*=\s*(\w+)\.(id|manager_id)\b",
                        re.I)


def boss_join_shape(line: str) -> Optional[str]:
    """Отклик на запрос «у кого больше подчинённых» по его форме или None."""
    sql = " ".join(re.findall(r'"([^"]*)"', db._SQ_LITERAL.sub("''", line)))
    if not re.search(r"\bSELECT\b", sql, re.I):
        return None
    head = next(_select_scopes(sql))[0]
    m = _SELF_JOIN.search(sql)
    if m is None:
        if re.search(r"\bmanager_id\b", head, re.I) and not re.search(r"\bname\b", head, re.I):
            return MSG_BOSS_NUM
        return None
    a1, c1, a2, c2 = m.group(3), m.group(4).lower(), m.group(5), m.group(6).lower()
    if {c1, c2} != {"id", "manager_id"}:
        return None
    sub = a1 if c1 == "manager_id" else a2
    boss = a2 if sub == a1 else a1
    if re.search(rf"\b{sub}\.name\b", head, re.I) and not re.search(rf"\b{boss}\.name\b", head,
                                                                     re.I):
        return MSG_BOSS_SUB
    if re.search(r"\bmanager_id\b", head, re.I) and not re.search(r"\bname\b", head, re.I):
        return MSG_BOSS_NUM
    return None


def _unpaired_state(rng, data) -> dict:
    """Непарные: счета без платежа и платежи без счёта; двух чисел-ловушек поровну быть не
    должно — иначе лишний платёж теряет счёт (у счёта остаётся другой платёж)."""
    inv, pay = data.tables["invoices"], data.tables["payments"]

    def counts():
        paid = Counter(p["invoice_id"] for p in pay if p["invoice_id"] is not None)
        return paid, sum(1 for x in inv if x["id"] not in paid), sum(
            1 for p in pay if p["invoice_id"] is None)
    paid, nopay, orph = counts()
    if nopay == orph:
        p = next(p for p in pay if paid.get(p["invoice_id"], 0) >= 2)
        p["invoice_id"] = None
        paid, nopay, orph = counts()
    ans = nopay + orph
    traps = [["left", nopay], ["orphans", orph]]
    return {"answer": ans, "traps": _distinct_traps(ans, traps),
            "totals": [["all_rows", len(pay) + nopay]]}


def _boss_state(rng, data) -> dict:
    """Начальник с наибольшим числом прямых подчинённых — один, с запасом 2 над вторым, сам
    без начальника (иначе «по подчинённому» запрос мог бы случайно назвать его), и имя у него
    в employees своё (данные варианта: подчинённых переводим к нему)."""
    emp = data.tables["employees"]
    tops = [e["id"] for e in emp if e["manager_id"] is None]

    def subs():
        return Counter(e["manager_id"] for e in emp if e["manager_id"] is not None)
    lead = max(tops, key=lambda i: (subs()[i], -i))
    for _ in range(40):
        c = subs()
        rival = max((v for k, v in c.items() if k != lead), default=0)
        if c[lead] - rival >= 2:
            break
        moves = [e for e in emp if e["manager_id"] not in (None, lead)]
        busiest = max(moves, key=lambda e: (c[e["manager_id"]], -e["id"]))
        busiest["manager_id"] = lead
    boss = next(e for e in emp if e["id"] == lead)
    names = {e["name"] for e in emp if e is not boss}
    while boss["name"] in names:
        boss["name"] = f"{rng.choice(dbkit.FIRST)} {rng.choice(dbkit.LAST)}"
    return {"answer": boss["name"], "traps": []}


# --- B4: ограничения, upsert, представления, JSON, COPY и pg_dump — общее ----------------------

MSG_REDO_TABLE = (" Поправь: {run} \"DROP TABLE {table}\" — и CREATE заново (или reset).")


# --- 11. constraints_fk ---------------------------------------------------------------------------

FK_DDL = (
    "CREATE TABLE contracts (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, customer_id "
    "INTEGER NOT NULL REFERENCES customers(id), amount INTEGER NOT NULL CHECK (amount > 0))",
    "CREATE TABLE limits (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL UNIQUE "
    "REFERENCES customers(id), cap INTEGER NOT NULL CHECK (cap BETWEEN 100 AND 5000))",
    "CREATE TABLE reviews (id INTEGER PRIMARY KEY, invoice_id INTEGER UNIQUE REFERENCES "
    "invoices(id), employee_id INTEGER REFERENCES employees(id), mark INTEGER CHECK (mark "
    "BETWEEN 1 AND 5))",
)
FK_SPECS = (
    {"table": "contracts", "cols": ("id", "code", "customer_id", "amount"),
     "fks": (("customer_id", "customers"),), "check": "amount", "unique": "code"},
    {"table": "limits", "cols": ("id", "customer_id", "cap"),
     "fks": (("customer_id", "customers"),), "check": "cap", "unique": "customer_id"},
    {"table": "reviews", "cols": ("id", "invoice_id", "employee_id", "mark"),
     "fks": (("invoice_id", "invoices"), ("employee_id", "employees")), "check": "mark",
     "unique": "invoice_id"},
)
_NO_FK = {0: " REFERENCES customers(id)", 1: " REFERENCES customers(id)",
          2: " REFERENCES employees(id)"}
_NO_CHECK = {0: " CHECK (amount > 0)", 1: " CHECK (cap BETWEEN 100 AND 5000)",
             2: " CHECK (mark BETWEEN 1 AND 5)"}
MSG_FK_PRAGMA = ("Прошла строка со ссылкой в никуда ({col} = {val}): в SQLite REFERENCES "
                 "проверяется, только если в той же сессии включено PRAGMA foreign_keys = ON — "
                 "оно живёт до выхода из sqlite3. Убери таблицу (DROP TABLE {table}) и загрузи "
                 "заново с PRAGMA — или reset.")
MSG_FK_CHECK = ("Прошла строка, которую CHECK должен был отвергнуть ({col} = {val}): условие "
                "в CHECK шире, чем в задании. DROP TABLE {table}, CREATE заново — или reset.")
MSG_FK_PARTIAL = ("Легли не все годные строки ({n} из файла, а должно больше). Плохая строка "
                  "не должна тормозить остальные: файл — целиком "
                  "({load}), без -bail и ON_ERROR_STOP. И сверь CHECK с заданием — не строже ли он.")
MSG_FK_ROWS = ("Строки не те, что в файле {file}: загружай его как есть ({load}), а не "
               "вручную.")
MSG_ONE_TX = ("psql -c с несколькими командами — одна транзакция: первая же ошибка отменила все "
              "вставки. Каждая строка — отдельно: файл целиком через psql -f.")
MSG_ONE_TX_FLAG = ("-1 (--single-transaction) делает весь файл одной транзакцией: первая же "
                   "ошибка отменила все вставки. Без -1: psql -f {file} — каждая строка отдельно.")


def _fk_schema(snap, spec: dict) -> Optional[str]:
    """Чего не хватает в CREATE TABLE: графы, ссылки (REFERENCES), CHECK, UNIQUE — или None."""
    table = spec["table"]
    have = {c["name"].lower(): c for c in snap.columns(table)}
    for col in spec["cols"]:
        if col not in have:
            return f"В таблице {table} нет графы {col} — имена граф по заданию."
    fks = snap.fks(table)
    for col, target in spec["fks"]:
        if not any(f["from"].lower() == col and str(f["table"]).lower() == target
                   and (f["to"] is None or str(f["to"]).lower() == "id") for f in fks):
            return (f"У {col} нет ссылки на {target}: без REFERENCES {target}(id) база примет "
                    "любой номер.")
    col = spec["check"]
    if not any(re.search(rf"\b{col}\b", c, re.I) for c in snap.checks(table)):
        return f"У {col} нет CHECK (…): без него база примет любое число."
    col = spec["unique"]
    unique = {tuple(c.lower() for c in i["columns"]) for i in snap.indexes(table)
              if i["unique"] and not i["partial"]}
    if (col,) not in unique and not have[col]["pk"]:
        return f"Графа {col} без UNIQUE: повтор пройдёт молча, а в задании — без повторов."
    return None


def _fk_rows(rng, data, variant: int):
    """Строки файла: допустимые и по одной-две на каждое ограничение (ссылка в никуда, CHECK,
    повтор UNIQUE — повтор идёт после оригинала). Каждая плохая нарушает ровно одно правило."""
    cust = [c["id"] for c in data.tables["customers"]]
    inv = [x["id"] for x in data.tables["invoices"]]
    emp = [e["id"] for e in data.tables["employees"]]
    n_ok = rng.randint(4, 6)
    ok, fk, chk, dup = [], [], [], []
    if variant == 0:
        codes = [f"K-{c}" for c in rng.sample(range(100, 1000), n_ok + 4)]
        for code in codes[:n_ok]:
            ok.append([code, rng.choice(cust), rng.randrange(200, 9000)])
        ok[rng.randrange(n_ok)][2] = rng.randint(1, 99)     # мелкий, но больше нуля — годится
        fk.append(([codes[n_ok], max(cust) + rng.randint(1, 30), rng.randrange(200, 9000)],
                   "customer_id"))
        chk.append([codes[n_ok + 1], rng.choice(cust), 0])
        chk.append([codes[n_ok + 2], rng.choice(cust), -rng.randrange(50, 900)])
        dup.append([rng.choice(ok)[0], rng.choice(cust), rng.randrange(200, 9000)])
    elif variant == 1:
        ids = rng.sample(cust, n_ok + 3)
        for c in ids[:n_ok]:
            ok.append([c, rng.randrange(100, 5001)])
        ok[rng.randrange(n_ok)][1] = rng.choice((100, 5000))      # ровно на границе — годится
        fk.append(([max(cust) + rng.randint(1, 30), rng.randrange(100, 5001)], "customer_id"))
        chk.append([ids[n_ok], rng.randrange(10, 100)])
        chk.append([ids[n_ok + 1], rng.randrange(5001, 9000)])
        dup.append([rng.choice(ok)[0], rng.randrange(100, 5001)])
    else:
        ids = rng.sample(inv, n_ok + 4)
        for x in ids[:n_ok]:
            ok.append([x, rng.choice(emp), rng.randint(1, 5)])
        ok[rng.randrange(n_ok)][2] = rng.choice((1, 5))
        fk.append(([max(inv) + rng.randint(1, 30), rng.choice(emp), rng.randint(1, 5)],
                   "invoice_id"))
        fk.append(([ids[n_ok], max(emp) + rng.randint(1, 20), rng.randint(1, 5)], "employee_id"))
        chk.append([ids[n_ok + 1], rng.choice(emp), rng.choice((0, 6, 7))])
        dup.append([rng.choice(ok)[0], rng.choice(emp), rng.randint(1, 5)])
    chk_col = {0: "amount", 1: "cap", 2: "mark"}[variant]
    tagged = ([("ok", r, None) for r in ok] + [("fk", r, c) for r, c in fk]
              + [("check", r, chk_col) for r in chk])
    rng.shuffle(tagged)
    first = max(i for i, (_, r, _c) in enumerate(tagged) if r[0] == dup[0][0])
    tagged.insert(rng.randint(first + 1, len(tagged)), ("dup", dup[0], None))
    return [(kind, [i] + r, c) for i, (kind, r, c) in enumerate(tagged, start=1)]


class ConstraintsFk(SqlTask):
    """REFERENCES (FK), CHECK, UNIQUE — правила, которые держит база; файл со строками, где
    часть недопустима; в SQLite FK — только с PRAGMA foreign_keys = ON в той же сессии."""
    id = "constraints_fk"
    title = "Правила таблицы"
    par = 120
    scroll = ("\"CREATE TABLE t (s INTEGER REFERENCES staff(id), q INTEGER CHECK (q > 0))\" — "
              "ссылку в никуда и q ≤ 0 база не примет; UNIQUE — без повторов.\n"
              "Файл: psql -f ф.sql (f — file) или sqlite3 vault.db \".read ф.sql\" — плохие "
              "строки дают ошибку, прочие идут.\n"
              "SQLite проверяет ссылки только с PRAGMA foreign_keys = ON в той же сессии: "
              "sqlite3 vault.db \"PRAGMA foreign_keys = ON\" \".read ф.sql\".")
    variants = (
        Variant("Заведи в {db} таблицу contracts: id — целый первичный ключ; code — текст, "
                "обязательный и без повторов; customer_id — ссылка на клиента (customers.id); "
                "amount — целое, строго больше нуля. Потом загрузи строки из файла "
                "contracts.sql — плохие строки база должна отбить сама.",
                hints=("Правила ставь в CREATE TABLE сразу после типа графы: REFERENCES "
                       "customers(id), CHECK (…), UNIQUE.",
                       "Файл — целиком одной командой: {load}. Ошибки на плохих строках — так "
                       "и задумано.",
                       "{run} \"" + FK_DDL[0] + "\""),
                solution="{run} \"" + FK_DDL[0] + "\" && {load}",
                wrong=("{run} \"" + FK_DDL[0].replace(_NO_FK[0], "") + "\" && {load}",
                       "{run} \"" + FK_DDL[0].replace(_NO_CHECK[0], "") + "\" && {load}"),
                alternatives=("{run} \"SELECT COUNT(*) FROM contracts\" — после загрузки: "
                              "сколько строк прошло",)),
        Variant("Заведи в {db} таблицу limits: id — целый первичный ключ; customer_id — "
                "ссылка на клиента (customers.id), у клиента не больше одного лимита; cap — "
                "целое от 100 до 5000 включительно. Потом загрузи строки из файла limits.sql — "
                "плохие строки база должна отбить сама.",
                hints=("Один лимит на клиента — UNIQUE у customer_id; «от и до» — CHECK (cap "
                       "BETWEEN 100 AND 5000).",
                       "Файл — целиком одной командой: {load}.",
                       "{run} \"" + FK_DDL[1] + "\""),
                solution="{run} \"" + FK_DDL[1] + "\" && {load}",
                wrong=("{run} \"" + FK_DDL[1].replace(_NO_FK[1], "") + "\" && {load}",
                       "{run} \"" + FK_DDL[1].replace(_NO_CHECK[1], " CHECK (cap > 100)") +
                       "\" && {load}"),
                alternatives=("{run} \"SELECT * FROM limits\" — после загрузки: границы 100 и "
                              "5000 прошли",)),
        Variant("Заведи в {db} таблицу reviews: id — целый первичный ключ; invoice_id — ссылка "
                "на счёт (invoices.id), не больше одного отзыва на счёт; employee_id — ссылка "
                "на сотрудника (employees.id); mark — целое от 1 до 5. Потом загрузи строки "
                "из файла reviews.sql — плохие строки база должна отбить сама.",
                hints=("Ссылок две: REFERENCES invoices(id) и REFERENCES employees(id); оценка "
                       "— CHECK с BETWEEN.",
                       "Файл — целиком одной командой: {load}.",
                       "{run} \"" + FK_DDL[2] + "\""),
                solution="{run} \"" + FK_DDL[2] + "\" && {load}",
                wrong=("{run} \"" + FK_DDL[2].replace(_NO_FK[2], "") + "\" && {load}",
                       "{run} \"" + FK_DDL[2].replace(" UNIQUE", "") + "\" && {load}"),
                alternatives=("{run} \"SELECT COUNT(*) FROM reviews\" — после загрузки",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Ограничения — правила, которые база сама сверяет на каждой строке: ссылка "
               "(REFERENCES) не пустит номер в никуда, CHECK — значение вне правила, UNIQUE — "
               "повтор. В SQLite ссылки проверяются, только если в этом сеансе включено PRAGMA "
               "foreign_keys = ON; в PostgreSQL — всегда.")
    spell = ("x INTEGER REFERENCES t(id); CHECK (x > 0); UNIQUE; sqlite3 ф.db \"PRAGMA "
             "foreign_keys = ON\" \".read ф.sql\"; psql -f ф.sql")

    def engine_texts(self, engine, st):
        f = f"{FK_SPECS[int(st['spec'])]['table']}.sql"
        if engine == "pg":
            return {"load": f"psql -f {f}", "file": f}
        return {"load": f"sqlite3 {DB} \"PRAGMA foreign_keys = ON\" \".read {f}\"", "file": f}

    def data_state(self, rng, data, variant):
        spec = FK_SPECS[variant]
        rows = _fk_rows(rng, data, variant)
        cols = ", ".join(spec["cols"])
        text = "".join(f"INSERT INTO {spec['table']} ({cols}) VALUES ("
                       + ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in r)
                       + ");\n" for _, r, _c in rows)
        return {"spec": variant, "table": spec["table"],
                "want": sorted(r for kind, r, _c in rows if kind == "ok"),
                "marks": {"bad": [[kind, r, c] for kind, r, c in rows
                                  if kind in ("fk", "check")],
                          "dup": [r for kind, r, _c in rows if kind == "dup"]},
                "_files": {f"{spec['table']}.sql": text}}

    def judge(self, ctx):
        st = ctx.state
        spec = FK_SPECS[int(st["spec"])]
        table = spec["table"]
        with self.snapshot(ctx) as snap:
            if table in snap.views():
                return Verdict(False, f"{table} — представление (VIEW), а нужна таблица: DROP "
                                      f"VIEW {table}, потом CREATE TABLE.")
            if table not in snap.tables():
                return Verdict(False)
            why = _fk_schema(snap, spec)
            if why:
                return Verdict(False, why + MSG_REDO_TABLE.format(**st))
            rows = sorted(list(r) for r in snap.rows(table, spec["cols"]))
        if not rows:
            return Verdict(False)
        want = [list(r) for r in st["want"]]
        if rows == want:
            return Verdict(True)
        for kind, row, col in st["marks"]["bad"]:
            if list(row) in rows:
                msg = MSG_FK_PRAGMA if kind == "fk" else MSG_FK_CHECK
                return Verdict(False, msg.format(col=col, val=row[spec["cols"].index(col)],
                                                 table=table))
        # повтор UNIQUE проходит, только если оригинал не прошёл (CHECK строже задания)
        if all(r in want or r in [list(d) for d in st["marks"]["dup"]] for r in rows):
            return Verdict(False, MSG_FK_PARTIAL.format(n=len(rows), **st))
        return Verdict(False, MSG_FK_ROWS.format(**st))

    def task_hint(self, ctx, line):
        if self.engine_of(ctx.state) != "pg":
            return None
        body = db._SQ_LITERAL.sub("''", line)
        words = _words(line)
        # аудит 9б, п. 10: -1 и "$(cat файл)" — тоже одна транзакция на весь файл
        if words[:1] == ["psql"] and any(w in ("-1", "--single-transaction") or (
                re.fullmatch(r"-[A-Za-z]*1[A-Za-z]*", w)) for w in words[1:]):
            return MSG_ONE_TX_FLAG.format(**ctx.state)
        if re.search(r"(?:^|\s)-c\b", body) and (
                len(re.findall(r"\bINSERT\b", body, re.I)) > 1 or re.search(r"\$\(\s*cat\b|\$\(<",
                                                                         line)):
            return MSG_ONE_TX
        return None


# --- 12. upsert -----------------------------------------------------------------------------------

RATE_CODES = ("USD", "EUR", "CNY", "GBP", "JPY", "TRY", "KZT", "INR", "AED", "CHF", "XAU", "SEK",
              "NOK", "PLN")
RATE_COLS = ("code", "rate", "note")
MSG_UPS_PLAIN = ("Простой INSERT упал на повторе: code — UNIQUE, а такой код уже есть (UNIQUE "
                 "constraint failed / duplicate key), и вся команда отменилась. Есть — обнови, "
                 "нет — вставь: INSERT … ON CONFLICT (code) DO ….")
MSG_UPS_OR_PG = ("INSERT OR REPLACE — только в SQLite, PostgreSQL его не знает (syntax error). "
                 "Да и там он стирает строку целиком: нужен INSERT … ON CONFLICT (code) DO UPDATE "
                 "SET rate = excluded.rate.")
MSG_UPS_REPLACE = ("У {code} пропал note: REPLACE удаляет строку целиком и вставляет новую — всё, "
                   "чего нет во вставке, теряется. Нужен ON CONFLICT (code) DO UPDATE SET rate = "
                   "excluded.rate: он меняет только названное. Набери reset.")
MSG_UPS_NOT_UPDATED = ("Курс {code} не обновился: DO NOTHING оставляет старую строку. Обновить "
                       "— DO UPDATE SET rate = excluded.rate (excluded — то, что пришло во "
                       "вставке). Набери reset.")
MSG_UPS_TOUCHED = ("Курс {code} уже был, а его переписали: в задании существующие не трогать — "
                   "ON CONFLICT (code) DO NOTHING. Набери reset.")
MSG_UPS_NOTE_NEW = ("У {code} note стал «new»: excluded.note — это то, что пришло во вставке. У "
                    "обновлённых note ставь прямо: DO UPDATE SET rate = excluded.rate, note = "
                    "'checked'. Набери reset.")
MSG_UPS_NOTE_OLD = ("У {code} курс новый, а note прежний: в DO UPDATE SET перечисли обе графы — "
                    "rate = excluded.rate, note = 'checked'. Набери reset.")
MSG_UPS_MISSING = "Нового кода {code} в rates нет: ON CONFLICT вставляет то, чего ещё нет."
MSG_UPS_OTHERS = ("Задеты курсы, которых нет в задании ({code}): правится только названное. "
                  "Набери reset.")
MSG_UPS_WRONG = "Курс {code} не тот: сверь VALUES с заданием. Набери reset."
MSG_UPS_NOTE_KEEP = ("Курс {code} верный, а note изменился: в задании note у существующих не "
                     "трогать — в DO UPDATE SET только rate = excluded.rate. Набери reset.")
MSG_UPS_REPLACE_PG = ("REPLACE INTO — только в SQLite, PostgreSQL его не знает (syntax error). Да и "
                      "там он стирает строку целиком: нужен INSERT … ON CONFLICT (code) DO UPDATE "
                      "SET rate = excluded.rate.")
MSG_UPS_NO_TARGET = ("ON CONFLICT DO UPDATE без (code): PostgreSQL не знает, по какой графе "
                     "конфликт (ON CONFLICT DO UPDATE requires inference specification). Назови её: "
                     "ON CONFLICT (code) DO UPDATE ….")
MSG_UPS_SELF = ("SET rate = rate — это старое значение (PostgreSQL ещё и спросит, какой rate: "
                "column reference is ambiguous). Пришедшее — excluded.rate.")


class Upsert(SqlTask):
    """INSERT … ON CONFLICT (code) DO UPDATE SET rate = excluded.rate, DO NOTHING, RETURNING;
    REPLACE стирает строку целиком (note)."""
    id = "upsert"
    title = "Вставить или обновить"
    par = 90
    scroll = ("Есть — обнови, нет — вставь: INSERT INTO t (k, v) VALUES ('a', 1) ON CONFLICT "
              "(k) DO UPDATE SET v = excluded.v — excluded. это пришедшая строка.\n"
              "ON CONFLICT (k) DO NOTHING — существующие не трогать. Простой INSERT на повторе "
              "UNIQUE упадёт весь.\n"
              "RETURNING k — что вставлено или обновлено. INSERT OR REPLACE (SQLite) стирает "
              "строку целиком — графы, которых нет во вставке, пропадут.")
    variants = (
        Variant("Пришли свежие курсы (таблица rates в {db}, code — без повторов): {listing}. "
                "Есть код — обнови rate, нет — вставь. note у существующих не трогай.",
                hints=("Одной командой: INSERT … ON CONFLICT (code) DO UPDATE — есть код, "
                       "обновит; нет — вставит.",
                       "В DO UPDATE SET пришедшее значение — excluded.rate; note не называй — "
                       "он останется.",
                       "{run} \"INSERT INTO rates (code, rate) VALUES {values} ON CONFLICT "
                       "(code) DO UPDATE SET rate = excluded.rate\""),
                solution="{run} \"INSERT INTO rates (code, rate) VALUES {values} ON CONFLICT "
                         "(code) DO UPDATE SET rate = excluded.rate\"",
                wrong=("{run} \"INSERT OR REPLACE INTO rates (code, rate) VALUES {values}\"",
                       "{run} \"INSERT INTO rates (code, rate) VALUES {values} ON CONFLICT "
                       "(code) DO NOTHING\""),
                alternatives=("{run} \"INSERT INTO rates (code, rate) VALUES {values} ON "
                              "CONFLICT (code) DO UPDATE SET rate = excluded.rate RETURNING "
                              "code, rate\" — заодно покажет, что легло",)),
        Variant("Пришёл список курсов (таблица rates в {db}, code — без повторов): {listing}. "
                "Внеси только новые коды; курсы, которые уже есть, оставь как были.",
                hints=("Повтор кода не должен ни падать, ни обновлять: ON CONFLICT (code) DO "
                       "NOTHING.",
                       "Простой INSERT на первом же повторе упадёт весь — новые тоже не лягут.",
                       "{run} \"INSERT INTO rates (code, rate) VALUES {values} ON CONFLICT "
                       "(code) DO NOTHING\""),
                solution="{run} \"INSERT INTO rates (code, rate) VALUES {values} ON CONFLICT "
                         "(code) DO NOTHING\"",
                wrong=("{run} \"INSERT INTO rates (code, rate) VALUES {values} ON CONFLICT "
                       "(code) DO UPDATE SET rate = excluded.rate\"",
                       "{run} \"INSERT INTO rates (code, rate) VALUES {values}\""),
                alternatives=("{run} \"INSERT INTO rates (code, rate) VALUES {values} ON "
                              "CONFLICT (code) DO NOTHING RETURNING code\" — покажет только "
                              "вставленные",)),
        Variant("Курсы после сверки (таблица rates в {db}, code — без повторов): {listing}. "
                "Новые коды внеси с note «new»; у кодов, что уже есть, обнови rate и поставь "
                "note «checked».",
                hints=("Вставка несёт note 'new'; при повторе — DO UPDATE SET с двумя графами.",
                       "rate = excluded.rate берёт пришедший курс, а note = 'checked' — прямо "
                       "значение: excluded.note был бы «new».",
                       "{run} \"INSERT INTO rates (code, rate, note) VALUES {values} ON CONFLICT "
                       "(code) DO UPDATE SET rate = excluded.rate, note = 'checked'\""),
                solution="{run} \"INSERT INTO rates (code, rate, note) VALUES {values} ON "
                         "CONFLICT (code) DO UPDATE SET rate = excluded.rate, note = 'checked'\"",
                wrong=("{run} \"INSERT INTO rates (code, rate, note) VALUES {values} ON CONFLICT "
                       "(code) DO UPDATE SET rate = excluded.rate, note = excluded.note\"",
                       "{run} \"INSERT INTO rates (code, rate, note) VALUES {values} ON CONFLICT "
                       "(code) DO UPDATE SET rate = excluded.rate\""),
                alternatives=("{run} \"SELECT * FROM rates ORDER BY code\" — после правки: "
                              "checked у старых, new у новых",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("UNIQUE не пускает второй такой же код, и простой INSERT на повторе падает "
               "целиком. ON CONFLICT решает по каждой строке: DO UPDATE меняет только названные "
               "графы (excluded — пришедшая строка), DO NOTHING проходит мимо. REPLACE сносит "
               "строку и кладёт новую — остальные графы пропадают.")
    spell = ("INSERT INTO t (k, v) VALUES ('a', 1) ON CONFLICT (k) DO UPDATE SET v = excluded.v; "
             "… DO NOTHING; … RETURNING k")

    def data_state(self, rng, data, variant):
        rates = data.tables["rates"]
        have = [r["code"] for r in rates]
        upd = rng.sample(rates, 2)
        if variant == 0 and not any(r["note"] for r in upd):
            upd[0]["note"] = rng.choice(("base", "promo", "legacy"))
        if variant == 2 and all(r["note"] in ("", "new") for r in upd):
            upd[0]["note"] = "legacy"
        orig = sorted([r[c] for c in RATE_COLS] for r in rates)
        fresh = rng.sample(sorted(set(RATE_CODES) - set(have)), rng.randint(1, 2))
        incoming = []
        for r in upd:
            rate = r["rate"]
            while rate == r["rate"]:
                rate = rng.randrange(50, 2500)
            incoming.append([r["code"], rate])
        incoming += [[c, rng.randrange(50, 2500)] for c in fresh]
        rng.shuffle(incoming)
        want = {r["code"]: [r["code"], r["rate"], r["note"]] for r in rates}
        for code, rate in incoming:
            if code in fresh:
                want[code] = [code, rate, "new" if variant == 2 else ""]
            elif variant == 0:
                want[code] = [code, rate, want[code][2]]
            elif variant == 2:
                want[code] = [code, rate, "checked"]
        if variant == 2:
            values = ", ".join(f"('{c}', {r}, 'new')" for c, r in incoming)
        else:
            values = ", ".join(f"('{c}', {r})" for c, r in incoming)
        return {"spec": variant, "values": values,
                "listing": ", ".join(f"{c} — {r}" for c, r in incoming),
                "want": sorted(want.values()),
                "marks": {"orig": orig, "fresh": fresh,
                          "upd": [c for c, _ in incoming if c not in fresh]}}

    def judge(self, ctx):
        st = ctx.state
        with self.snapshot(ctx) as snap:
            rows = sorted(list(r) for r in snap.rows("rates", RATE_COLS))
        want = [list(r) for r in st["want"]]
        marks = st["marks"]
        if rows == want:
            return Verdict(True)
        if rows == [list(r) for r in marks["orig"]]:
            return Verdict(False)
        cur = {r[0]: r for r in rows}
        orig = {r[0]: r for r in marks["orig"]}
        exp = {r[0]: r for r in want}
        kind = int(st["spec"])
        # ревью B4, I1: работа в несколько шагов (INSERT новых, потом UPDATE старых — или
        # наоборот): каждая строка либо исходная, либо уже нужная — молчим, пока не закончено.
        # «Не обновился» — только если сам ход был DO NOTHING.
        if all(cur.get(c) in (orig.get(c), exp.get(c)) for c in set(cur) | set(orig) | set(exp)):
            line = ctx.cmds[-1].line if ctx.cmds else ""
            stale = [c for c in marks["upd"] if cur.get(c) == orig[c] and orig[c] != exp[c]]
            if kind != 1 and stale and re.search(r"\bDO\s+NOTHING\b", line, re.I):
                return Verdict(False, MSG_UPS_NOT_UPDATED.format(code=stale[0]))
            return Verdict(False)                # частичный ход — работа идёт
        for code in marks["upd"]:
            c, o, w = cur.get(code), orig[code], exp[code]
            if c is None:
                return Verdict(False, MSG_UPS_OTHERS.format(code=code))
            if kind == 1:
                if c != o:
                    return Verdict(False, MSG_UPS_TOUCHED.format(code=code))
                continue
            if c[1] == o[1]:
                return Verdict(False, MSG_UPS_NOT_UPDATED.format(code=code))
            if kind == 0 and o[2] and c[2] == "":
                return Verdict(False, MSG_UPS_REPLACE.format(code=code))
            if kind == 2 and c[2] == "new":
                return Verdict(False, MSG_UPS_NOTE_NEW.format(code=code))
            if kind == 2 and c[2] == o[2] and c[1] == w[1]:
                return Verdict(False, MSG_UPS_NOTE_OLD.format(code=code))
            if kind == 0 and c[1] == w[1] and c[2] != o[2]:
                return Verdict(False, MSG_UPS_NOTE_KEEP.format(code=code))
            if c != w:
                return Verdict(False, MSG_UPS_WRONG.format(code=code))
        for code in marks["fresh"]:
            if code not in cur:
                return Verdict(False, MSG_UPS_MISSING.format(code=code))
            if cur[code] != exp[code]:
                return Verdict(False, MSG_UPS_WRONG.format(code=code))
        for code in sorted(set(orig) | set(cur)):
            if code not in exp or cur.get(code) != exp[code]:
                return Verdict(False, MSG_UPS_OTHERS.format(code=code))
        return Verdict(False, MSG_UPS_WRONG.format(code=marks["upd"][0]))

    def task_hint(self, ctx, line):
        body = db._SQ_LITERAL.sub("''", line)
        pg = self.engine_of(ctx.state) == "pg"
        if re.search(r"\bSET\s+rate\s*=\s*rate\b", body, re.I):
            return MSG_UPS_SELF
        if pg and re.search(r"\bON\s+CONFLICT\s+DO\s+UPDATE\b", body, re.I):
            return MSG_UPS_NO_TARGET
        if pg and re.search(r"(?<!\bOR\s)\bREPLACE\s+INTO\b", body, re.I) and not re.search(
                r"\bINSERT\s+OR\s+REPLACE\b", body, re.I):
            return MSG_UPS_REPLACE_PG
        if not re.search(r"\bINSERT\b", body, re.I) or re.search(r"\bON\s+CONFLICT\b", body, re.I):
            return None
        if re.search(r"\bINSERT\s+OR\s+REPLACE\b", body, re.I):
            return MSG_UPS_OR_PG if pg else None
        # простой INSERT падает, только если в нём есть уже существующий код (ревью B4, I1:
        # вставка одних новых кодов — честный первый шаг)
        have = {r[0] for r in ctx.state["marks"]["orig"]}
        if re.search(r"\bINSERT\s+INTO\s+rates\b", body, re.I) and \
                set(re.findall(r"'([A-Z]{3})'", line)) & have:
            return MSG_UPS_PLAIN
        return None


# --- 13. view_index -------------------------------------------------------------------------------

VIEW_SPECS = (
    {"view": "big_open", "cols": ("id", "customer_id", "amount"), "itable": "invoices",
     "icol": "customer_id"},
    {"view": "district_debt", "cols": ("district", "debt"), "itable": "customers",
     "icol": "district"},
    {"view": "late_customers", "cols": ("id", "name"), "itable": "invoices", "icol": "status"},
)
VIEW_X = (3000, 4000, 5000, 6000)
_DEBT_SQL = ("SELECT c.district, SUM(i.amount) AS debt FROM invoices i JOIN customers c ON c.id "
             "= i.customer_id WHERE i.status IN ('open', 'overdue') GROUP BY c.district")
_LATE_SQL = ("SELECT DISTINCT c.id, c.name FROM customers c JOIN invoices i ON i.customer_id = "
             "c.id WHERE i.status = 'overdue'")
MSG_VIEW_IS_TABLE = ("{view} — таблица-копия (CREATE TABLE … AS), а нужно представление: оно "
                     "пересчитывается само при каждом запросе. DROP TABLE {view}, потом CREATE "
                     "VIEW {view} AS SELECT ….")
MSG_VIEW_COLS = ("У представления {view} нет графы {col}: графы называй как в задании (… AS "
                 "{col}). DROP VIEW {view} и CREATE заново.")
MSG_VIEW_ROWS = ("Представление {view} даёт не те строки: сверь условие с заданием. Посмотри, "
                 "что оно отдаёт: {run} \"SELECT * FROM {view}\". Поправить — DROP VIEW {view} и "
                 "CREATE заново.")
MSG_VIEW_DUPS = ("В {view} клиенты повторяются — у кого несколько просроченных счетов, тот "
                 "встречается несколько раз. Каждого по разу — SELECT DISTINCT. DROP VIEW {view} "
                 "и CREATE заново.")
MSG_VIEW_NEED_INDEX = ("Представление верно. Осталось ускорить поиск: CREATE INDEX имя ON "
                       "{itable} ({icol}).")
MSG_VIEW_INDEX_COL = ("Индекс на {itable} есть, но не на той графе: нужен на {icol} — CREATE "
                      "INDEX имя ON {itable} ({icol}).")


def _view_index_ok(snap, spec) -> Optional[str]:
    """None — индекс на {itable}({icol}) есть; иначе — отклик."""
    idx = [i for i in snap.indexes(spec["itable"]) if not i["partial"] and i["columns"]]
    if any(i["columns"][0].lower() == spec["icol"] for i in idx):
        return None
    mine = [i for i in idx if i.get("origin") == "c"]
    return (MSG_VIEW_INDEX_COL if mine else MSG_VIEW_NEED_INDEX).format(**spec)


class ViewIndex(SqlTask):
    """CREATE VIEW (сохранённый запрос), CREATE INDEX, EXPLAIN / EXPLAIN QUERY PLAN. Проверка
    структурная: представление даёт нужные строки, индекс — на нужной графе; план не
    проверяем (на маленькой таблице PostgreSQL вправе выбрать Seq Scan)."""
    id = "view_index"
    title = "Сохранённый запрос"
    par = 120
    scroll = ("CREATE VIEW v AS SELECT … — сохранённый запрос: SELECT * FROM v считает его "
              "заново, копии данных нет.\n"
              "CREATE INDEX staff_dept ON staff (dept) — индекс (оглавление по графе): WHERE dept = … "
              "ищет без перебора.\n"
              "Как база ищет: EXPLAIN SELECT … (PostgreSQL: Seq Scan — перебор, Index Scan — по "
              "индексу), в SQLite — EXPLAIN QUERY PLAN SELECT … (SCAN против SEARCH).")
    variants = (
        Variant("Заведи в {db} представление big_open: открытые счета (status open) дороже "
                "{x} — графы id, customer_id, amount. И индекс на invoices по customer_id.",
                hints=("Представление — CREATE VIEW имя AS и тот SELECT, что ты бы набрал "
                       "руками.",
                       "Индекс — CREATE INDEX имя ON invoices (customer_id); обе команды — через "
                       "; в одной строке.",
                       "{run} \"CREATE VIEW big_open AS SELECT id, customer_id, amount FROM "
                       "invoices WHERE status = 'open' AND amount > {x}\""),
                solution="{run} \"CREATE VIEW big_open AS SELECT id, customer_id, amount FROM "
                         "invoices WHERE status = 'open' AND amount > {x}; CREATE INDEX "
                         "invoices_customer ON invoices (customer_id)\"",
                wrong=("{run} \"CREATE VIEW big_open AS SELECT id, customer_id, amount FROM "
                       "invoices WHERE amount > {x}; CREATE INDEX invoices_customer ON invoices "
                       "(customer_id)\"",
                       "{run} \"CREATE VIEW big_open AS SELECT id, customer_id, amount FROM "
                       "invoices WHERE status = 'open' AND amount >= {x}; CREATE INDEX "
                       "invoices_customer ON invoices (customer_id)\""),
                alternatives=("{run} \"{explain} SELECT * FROM invoices WHERE customer_id = "
                              "7\" — до и после индекса: как база ищет",)),
        Variant("Заведи в {db} представление district_debt: по каждому району (district у "
                "customers) сумма неоплаченных счетов (status open или overdue) — графы district и "
                "debt. "
                "И индекс на customers по district.",
                hints=("Внутри — склейка invoices с customers, WHERE status IN ('open', "
                       "'overdue'), GROUP BY district и SUM(…) AS debt.",
                       "Индекс — CREATE INDEX имя ON customers (district).",
                       "{run} \"CREATE VIEW district_debt AS " + _DEBT_SQL + "\""),
                solution="{run} \"CREATE VIEW district_debt AS " + _DEBT_SQL + "; CREATE INDEX "
                         "customers_district ON customers (district)\"",
                wrong=("{run} \"CREATE VIEW district_debt AS " + _DEBT_SQL.replace(
                    "i.status IN ('open', 'overdue')", "i.status = 'open'") + "; CREATE INDEX "
                    "customers_district ON customers (district)\"",
                       "{run} \"CREATE VIEW district_debt AS " + _DEBT_SQL + "; CREATE INDEX "
                       "customers_name ON customers (name)\""),
                alternatives=("{run} \"SELECT * FROM district_debt ORDER BY debt DESC\" — "
                              "представление читается, как таблица",)),
        Variant("Заведи в {db} представление late_customers: клиенты, у кого есть хоть один "
                "просроченный счёт (status overdue), — графы id и name, каждый по разу. И "
                "индекс на invoices по status.",
                hints=("Склейка customers с invoices и WHERE status = 'overdue'; повторы убирает "
                       "DISTINCT.",
                       "Индекс — CREATE INDEX имя ON invoices (status).",
                       "{run} \"CREATE VIEW late_customers AS " + _LATE_SQL + "\""),
                solution="{run} \"CREATE VIEW late_customers AS " + _LATE_SQL + "; CREATE "
                         "INDEX invoices_status ON invoices (status)\"",
                wrong=("{run} \"CREATE VIEW late_customers AS " + _LATE_SQL.replace(
                    "DISTINCT ", "") + "; CREATE INDEX invoices_status ON invoices (status)\"",
                       "{run} \"CREATE TABLE late_customers AS " + _LATE_SQL + "; CREATE INDEX "
                       "invoices_status ON invoices (status)\""),
                alternatives=("{run} \"SELECT id, name FROM customers WHERE id IN (SELECT "
                              "customer_id FROM invoices WHERE status = 'overdue')\" — то же "
                              "подзапросом, внутри CREATE VIEW",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Представление — запрос с именем: данных не держит, при каждом чтении считает "
               "заново — и потому всегда свежее. Индекс — оглавление по графе: по ней база ищет, "
               "не перебирая всю таблицу. EXPLAIN выдаёт, как база собралась искать.")
    spell = ("CREATE VIEW v AS SELECT …; CREATE INDEX i ON t (графа); EXPLAIN SELECT … (SQLite: "
             "EXPLAIN QUERY PLAN)")

    def engine_texts(self, engine, st):
        return {"explain": "EXPLAIN" if engine == "pg" else "EXPLAIN QUERY PLAN"}

    def data_state(self, rng, data, variant):
        spec = VIEW_SPECS[variant]
        inv = data.tables["invoices"]
        if variant == 0:
            x = rng.choice(VIEW_X)
            opens = [r for r in inv if r["status"] == "open"]
            rng.choice(opens)["amount"] = x                 # ровно на пороге: >= его возьмёт
            if not any(r["status"] == "open" and r["amount"] > x for r in inv):
                rng.choice([r for r in opens if r["amount"] != x])["amount"] = x + 1
            want = [[r["id"], r["customer_id"], r["amount"]] for r in inv
                    if r["status"] == "open" and r["amount"] > x]
            return {"spec": variant, "x": x, "want": sorted(want)}
        _clean_districts(data)
        by_id = {c["id"]: c for c in data.tables["customers"]}
        if variant == 1:
            debt = Counter()
            for r in inv:
                if r["status"] != "paid":
                    debt[by_id[r["customer_id"]]["district"]] += r["amount"]
            return {"spec": variant, "want": sorted([d, s] for d, s in debt.items())}
        late = Counter(r["customer_id"] for r in inv if r["status"] == "overdue")
        if not any(n >= 2 for n in late.values()):          # повтор есть — DISTINCT нужен
            who = rng.choice(sorted(late))
            other = sorted((r for r in inv if r["status"] != "overdue"),
                           key=lambda r: (r["customer_id"] != who, r["id"]))[0]
            other["customer_id"], other["status"] = who, "overdue"
            late = Counter(r["customer_id"] for r in inv if r["status"] == "overdue")
        want = sorted([i, by_id[i]["name"]] for i in late)
        return {"spec": variant, "want": want}

    def judge(self, ctx):
        st = ctx.state
        spec = VIEW_SPECS[int(st["spec"])]
        view = spec["view"]
        with self.snapshot(ctx) as snap:
            if view in snap.tables():
                return Verdict(False, MSG_VIEW_IS_TABLE.format(view=view))
            if view not in snap.views():
                return Verdict(False)
            have = {c.lower() for c in snap.view_columns(view)}
            for col in spec["cols"]:
                if col not in have:
                    return Verdict(False, MSG_VIEW_COLS.format(view=view, col=col))
            rows = sorted(list(r) for r in snap.view_rows(view, spec["cols"]))
            index = _view_index_ok(snap, spec)
        want = [list(r) for r in st["want"]]
        if rows != want:
            if sorted(set(map(tuple, rows))) == sorted(map(tuple, want)):
                return Verdict(False, MSG_VIEW_DUPS.format(view=view))
            return Verdict(False, MSG_VIEW_ROWS.format(view=view, **st))
        if index:
            return Verdict(False, index)
        return Verdict(True)


# --- 14. jsonb_query ------------------------------------------------------------------------------

JSON_TAGS = ("x", "vip", "night", "manual")       # тег варианта B (api — первый по алфавиту)
MSG_JSON_ARROW = ("-> отдаёт JSON, а не текст: сравнивать его со 'строкой' PostgreSQL не умеет "
                  "(invalid input syntax for type json). Текст — ->>: payload->>'type' = '…'.")


def _payloads(data) -> List[dict]:
    import json
    return [json.loads(e["payload"]) for e in data.tables["events"]]


def _put_payloads(data, objs) -> None:
    for e, obj in zip(data.tables["events"], objs):
        obj["tags"] = sorted(set(obj["tags"]))
        e["payload"] = dbkit.jsonb_text(obj)


MSG_JSON_KEY = ("Ключ JSON — строка в одинарных кавычках: payload->>'{key}'. Без кавычек база "
                "ищет графу {key} (column … does not exist).")
MSG_JSON_ARRAY_TEXT = ("->> у массива отдаёт весь массив текстом — [\"x\", \"vip\"], и с "
                       "одним тегом он не равен. Тег в массиве ищи @>: payload @> "
                       "'{\"tags\": [\"…\"]}'.")


class JsonbQuery(SqlAnswer):
    """JSON в PostgreSQL: -> (JSON), ->> (текст), @> (содержит), jsonb_array_elements_text."""
    id = "jsonb_query"
    title = "Поля внутри JSON"
    par = 90
    stand = "pg"
    scroll = ("payload->'who' — значение JSON, payload->>'who' — оно же текстом: со 'строкой' "
              "сравнивают только ->>.\n"
              "payload @> '{\\\"vip\\\": true}' — JSON содержит этот кусок; кавычки JSON "
              "внутри \"…\" пиши с косой: \\\".\n"
              "jsonb_array_elements_text(payload->'tags') — элементы массива строками, как .[] "
              "у jq.")
    variants = (
        Variant("События (events) в базе vault: payload — JSON вида {{\"type\": …, \"who\": …, "
                "\"tags\": […]}}. Сколько событий типа {etype}? Ответ: ans ЧИСЛО",
                hints=("Поле JSON текстом даёт ->>: payload->>'type'.",
                       "-> вернёт JSON, и сравнение со строкой упадёт; нужен ->> и = '{etype}'.",
                       "psql -At -c \"SELECT COUNT(*) FROM events WHERE payload->>'type' = "
                       "'{etype}'\""),
                solution="psql -At -c \"SELECT COUNT(*) FROM events WHERE payload->>'type' = "
                         "'{etype}'\"",
                wrong=("psql -At -c \"SELECT COUNT(*) FROM events WHERE payload->'type' = "
                       "'{etype}'\"",
                       "psql -At -c \"SELECT COUNT(*) FROM events\""),
                alternatives=("psql -At -c \"SELECT payload->>'type', COUNT(*) FROM events "
                              "GROUP BY 1\" — все типы разом",)),
        Variant("События (events) в базе vault: в payload есть массив tags. У скольких событий "
                "среди тегов есть {tag}? Ответ: ans ЧИСЛО",
                hints=("«Содержит» в JSON — @>: payload @> '{{\\\"tags\\\": [\\\"{tag}\\\"]}}'; "
                       "кавычки JSON внутри \"…\" — с косой.",
                       "= сравнит массив целиком — найдутся только те, где тег единственный.",
                       "psql -At -c \"SELECT COUNT(*) FROM events WHERE payload @> "
                       "'{{\\\"tags\\\": [\\\"{tag}\\\"]}}'\""),
                solution="psql -At -c \"SELECT COUNT(*) FROM events WHERE payload @> "
                         "'{{\\\"tags\\\": [\\\"{tag}\\\"]}}'\"",
                wrong=("psql -At -c \"SELECT COUNT(*) FROM events WHERE payload->'tags' = "
                       "'[\\\"{tag}\\\"]'\"",
                       "psql -At -c \"SELECT COUNT(*) FROM events WHERE payload->>'tags' = "
                       "'{tag}'\""),
                alternatives=("psql -At -c \"SELECT COUNT(*) FROM events WHERE payload->'tags' "
                              "? '{tag}'\" — ? : есть ли такая строка в массиве",)),
        Variant("События (events) в базе vault: в payload есть массив tags. Какой тег "
                "встречается чаще всех и сколько раз? Ответ: ans ТЕГ ЧИСЛО",
                hints=("Элементы массива строками — jsonb_array_elements_text(payload->'tags') "
                       "во FROM, рядом с events.",
                       "Дальше как всегда: GROUP BY тег, ORDER BY COUNT(*) DESC LIMIT 1.",
                       "psql -At -c \"SELECT t, COUNT(*) FROM events, "
                       "jsonb_array_elements_text(payload->'tags') AS t GROUP BY t ORDER BY "
                       "COUNT(*) DESC LIMIT 1\""),
                solution="psql -At -c \"SELECT t, COUNT(*) FROM events, "
                         "jsonb_array_elements_text(payload->'tags') AS t GROUP BY t ORDER BY "
                         "COUNT(*) DESC LIMIT 1\"",
                wrong=("psql -At -c \"SELECT t, COUNT(*) FROM events, "
                       "jsonb_array_elements_text(payload->'tags') AS t GROUP BY t ORDER BY t "
                       "LIMIT 1\"",
                       "psql -At -c \"SELECT COUNT(*) FROM events WHERE payload->'tags' <> "
                       "'[]'\""),
                alternatives=("jsonb_array_elements(payload->'tags') — то же, но элементы JSON, "
                              "в кавычках: \"vip\"",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Поле из JSON-графы PostgreSQL достаёт стрелкой: -> отдаёт JSON, ->> — текст, а "
               "со строкой сравнишь только текст. @> спрашивает «есть ли в JSON такой кусок», а "
               "jsonb_array_elements_text разворачивает массив в строки — как .[] у jq.")
    spell = ("payload->>'k' = 'v'; payload @> '{\"tags\": [\"x\"]}'; "
             "jsonb_array_elements_text(payload->'tags')")
    trap_messages = {
        "all": "Это все события подряд: условие на тип — WHERE payload->>'type' = '…'.",
        "exact": "Это события, где тег — единственный: = сравнивает массив целиком. «Содержит» — "
                 "@>.",
        "like": "LIKE по тексту JSON цепляет и чужие слова (буквы тега бывают в типе и в других "
                "тегах). Искать в массиве — @>.",
        "events": "Это события, у которых вообще есть теги; а нужен один тег — разверни массив: "
                  "jsonb_array_elements_text.",
        "all_tags": "Это все упоминания тегов вместе; нужен самый частый — GROUP BY тег.",
        "alpha": "Это первый тег по алфавиту (ORDER BY t); самый частый — ORDER BY COUNT(*) "
                 "DESC.",
    }

    def matches(self, given, ctx):
        """Элемент JSON печатается в кавычках ("vip") — это тот же тег (jsonb_array_elements)."""
        return super().matches(given.replace('"', ""), ctx)

    def task_hint(self, line, state):
        # B7 (мелочи аудита): ключ JSON без кавычек — payload->>type, payload.type
        body = db._SQ_LITERAL.sub("''", line)
        m = re.search(r"->>?\s*([A-Za-z_]\w*)\b|\bpayload\.([A-Za-z_]\w*)", body)
        if m:
            return MSG_JSON_KEY.format(key=m.group(1) or m.group(2))
        # -> 'ключ' = 'слово': справа не JSON ([…], {…}, "…") — сравнение JSON со строкой
        if re.search(r"(?<!-)->(?!>)\s*'\w+'\s*(?:=|<>)\s*'(?![\s\[{\\\"0-9]|true|false|null)",
                     line):
            return MSG_JSON_ARROW
        if re.search(r"->>\s*'tags'\s*=", line):
            return MSG_JSON_ARRAY_TEXT
        return None

    def data_state(self, rng, data, variant):
        objs = _payloads(data)
        if variant == 0:
            etype = rng.choice(dbkit.EVENT_TYPES)
            n = sum(1 for o in objs if o["type"] == etype)
            return {"etype": etype, "answer": n, "traps": [], "totals": [["all", len(objs)]]}
        if variant == 1:
            tag = rng.choice(JSON_TAGS)
            # тег среди других — у двух и больше (= массиву целиком их не найдёт), и один раз
            # он единственный (= найдёт хоть что-то)
            mixed = [o for o in objs if tag in o["tags"] and len(o["tags"]) > 1]
            for o in rng.sample([o for o in objs if tag not in o["tags"] and o["tags"]],
                                max(0, 2 - len(mixed))):
                o["tags"].append(tag)
            if not any(o["tags"] == [tag] for o in objs):
                rng.choice([o for o in objs if not o["tags"]]
                           or [o for o in objs if tag not in o["tags"]])["tags"] = [tag]
            _put_payloads(data, objs)
            ans = sum(1 for o in objs if tag in o["tags"])
            exact = sum(1 for o in objs if o["tags"] == [tag])
            like = sum(1 for e in data.tables["events"] if tag in e["payload"])
            return {"tag": tag, "answer": ans,
                    "traps": _distinct_traps(ans, [["exact", exact], ["like", like]])}
        lead = rng.choice(JSON_TAGS)            # не api: «ORDER BY t LIMIT 1» берёт его первым
        if not any("api" in o["tags"] for o in objs):
            rng.choice(objs)["tags"].append("api")
        for _ in range(80):
            c = Counter(t for o in objs for t in o["tags"])
            rival = max(v for k, v in c.items() if k != lead) if len(c) > 1 else 0
            if c[lead] - rival >= dbkit.LEAD_MARGIN:
                break
            rng.choice([o for o in objs if lead not in o["tags"]])["tags"].append(lead)
        _put_payloads(data, objs)
        c = Counter(t for o in objs for t in o["tags"])
        with_tags = sum(1 for o in objs if o["tags"])
        first = min(c)
        return {"answer": [lead, c[lead]],
                "traps": _distinct_traps([lead, c[lead]], [["events", with_tags],
                                                           ["alpha", [first, c[first]]]]),
                "totals": [["all_tags", sum(c.values())]]}


# --- 15. copy_dump --------------------------------------------------------------------------------

_INTAKE = dbkit.Extra(
    cols=("id", "name", "district", "limit_sum"),
    sqlite="CREATE TABLE intake (id INTEGER PRIMARY KEY, name TEXT NOT NULL, district TEXT NOT "
           "NULL, limit_sum INTEGER NOT NULL)",
    pg="CREATE TABLE ops.intake (id integer PRIMARY KEY, name text NOT NULL, district text NOT "
       "NULL, limit_sum integer NOT NULL)")
DUMP_TABLES = ("rates", "ledger", "employees", "events")
MSG_COPY_SERVER = ("COPY без \\ читает и пишет файлы на стороне сервера, а учебному серверу "
                   "это запрещено (permission denied … pg_read_server_files). Файл в твоей папке "
                   "читает сам psql: \\copy … FROM 'файл' CSV HEADER.")
MSG_COPY_SERVER_TO = ("COPY без \\ пишет файл на стороне сервера, а учебному серверу это "
                      "запрещено (permission denied … pg_write_server_files). Файл в твою папку "
                      "пишет сам psql: \\copy (SELECT …) TO 'файл' CSV HEADER.")
MSG_COPY_NO_SCHEMA = ("Таблица intake лежит в схеме ops, а без имени схемы psql ищет в public — "
                      "relation \"intake\" does not exist. Пиши со схемой: \\copy ops.intake ….")
MSG_COPY_NO_HEADER_IN = ("Первая строка файла — шапка (id,name,…), и без HEADER psql пробует "
                         "вставить её как данные — invalid input syntax. Допиши CSV HEADER.")
MSG_COPY_ROWS = ("В ops.intake не те строки: загружай файл как есть — \\copy ops.intake FROM "
                 "'intake.csv' CSV HEADER. Лишнее убери: DELETE FROM ops.intake (или reset).")
MSG_COPY_NO_HEADER_OUT = ("В файле нет шапки: нужна первая строка id,amount. CSV HEADER в "
                          "\\copy … TO допишет её сам.")
MSG_COPY_NOT_CSV = ("Графы через | — это не CSV. \\copy (SELECT …) TO 'файл' CSV HEADER пишет "
                    "через запятую.")
MSG_COPY_ORDER = "Строки те, но порядок не тот: по возрастанию id — ORDER BY id внутри скобок."
MSG_COPY_WRONG = ("В {out} не те строки: сверь SELECT в скобках с заданием (статус, графы, "
                  "порядок).")
MSG_DUMP_CUSTOM = ("Это двоичный формат pg_dump (-Fc): его читает только pg_restore. Нужен "
                   "обычный текст — pg_dump без -F.")
MSG_DUMP_FULL = ("В копии вся база, а нужна одна таблица {table}: pg_dump -t {table} vault > "
                 "{out}.")
MSG_DUMP_SCHEMA = ("В копии только схема, без строк (-s): строк таблицы {table} в ней нет — "
                   "вернуть по ней нечего. pg_dump без -s.")
MSG_DUMP_DATA = ("В копии только строки (-a), без CREATE TABLE: на пустом сервере её не "
                 "восстановить. pg_dump -t {table} без -a.")
MSG_DUMP_ROWS = ("В копии {got} строк {table}, а в базе их {n}: копию снимай с нетронутой "
                 "таблицы (reset — и снова pg_dump).")
MSG_DUMP_ALIEN = ("Строки в копии не те, что в таблице {table}: копию пишет pg_dump с нетронутой "
                  "таблицы, руками её не собрать. reset — и pg_dump -t {table} vault > {out}.")
MSG_DUMP_EMPTY = ("В {out} нет данных таблицы {table}: копию одной таблицы даёт pg_dump -t "
                  "{table} vault > {out}.")


_SQL_TOKEN = re.compile(r"[^,]+")


def _sql_values(body: str) -> Optional[List[Optional[str]]]:
    """Значения из «(…)» строки INSERT дампа: 'текст' ('' внутри — кавычка), числа, NULL —
    текстом, как их печатает COPY (NULL — None); не разобралось — None."""
    out, i, n = [], 0, len(body)
    while i < n:
        while i < n and body[i] in " ,":
            i += 1
        if i >= n:
            break
        if body[i] == "'":
            j, buf = i + 1, []
            while j < n:
                if body[j] == "'":
                    if j + 1 < n and body[j + 1] == "'":
                        buf.append("'")
                        j += 2
                        continue
                    break
                buf.append(body[j])
                j += 1
            if j >= n:
                return None
            out.append("".join(buf))
            i = j + 1
        else:
            m = _SQL_TOKEN.match(body, i)              # без среза хвоста: разбор линейный
            tok = m.group(0).strip()
            out.append(None if tok.upper() == "NULL" else tok)
            i = m.end()
    return out


def dump_rows(text: str) -> dict:
    """Строки текстового дампа по таблицам: {«схема.таблица»: [строка, …]}, строка — список
    значений текстом (NULL — None). Блоки COPY … FROM stdin и строки INSERT INTO (pg_dump
    --inserts и --column-inserts)."""
    out, cur = {}, None
    for line in text.split("\n"):
        if cur is not None:
            if line == "\\.":
                cur = None
            else:
                out[cur].append([dbread.copy_unescape(f) for f in line.split("\t")])
            continue
        m = re.match(r"COPY (\S+) \(.*\) FROM stdin;$", line)
        if m:
            cur = m.group(1)
            out[cur] = []
            continue
        m = re.match(r"INSERT INTO (\S+) (?:\([^)]*\) )?VALUES \((.*)\);$", line)
        if m:
            vals = _sql_values(m.group(2))
            out.setdefault(m.group(1), []).append(vals if vals is not None else ["?"])
    return out


def _dump_value(v) -> Optional[str]:
    """Значение строки генератора — как его пишет дамп (текстом; NULL — None)."""
    return None if v is None else str(v)


class CopyDump(SqlTask):
    """\\copy FROM/TO на стороне клиента (CSV HEADER), COPY на стороне сервера — нет прав;
    pg_dump vault > backup/…sql, pg_dump -t."""
    id = "copy_dump"
    title = "Файлы и копии"
    par = 120
    stand = "pg"
    # B7 (аудит 9б, разгрузка): \\copy FROM — текст варианта 1, \\copy TO — варианта 2, COPY на
    # сервере — их тексты и отклик MSG_COPY_SERVER; карточке — копия pg_dump (вариант 0)
    scroll = ("mkdir -p backup; pg_dump vault > backup/vault.sql — копия базы текстом: CREATE "
              "TABLE и строки.\n"
              "pg_dump -t staff vault — копия одной таблицы; > — в файл, как всегда.\n"
              "Файлы в таблицы и обратно возит сам psql — как именно, скажет поручение.")
    variants = (
        Variant("Сними текстовую копию одной таблицы {table} базы vault в backup/{table}.sql — "
                "схема и строки, остальные таблицы не нужны.",
                hints=("Копию базы текстом делает pg_dump; одну таблицу — флаг -t (table).",
                       "Папку — mkdir -p backup, вывод pg_dump — > в файл.",
                       "mkdir -p backup && pg_dump -t {table} vault > backup/{table}.sql"),
                solution="mkdir -p backup && pg_dump -t {table} vault > backup/{table}.sql",
                wrong=("mkdir -p backup && pg_dump vault > backup/{table}.sql",
                       "mkdir -p backup && pg_dump -s -t {table} vault > backup/{table}.sql"),
                alternatives=("grep -c . backup/{table}.sql — после копии: файл не пуст",)),
        Variant("В папке лежит intake.csv (с шапкой) — новые заявки. Загрузи его в таблицу "
                "ops.intake базы vault. Файл в таблицу грузит сам psql: \\copy таблица FROM "
                "'файл' CSV HEADER (HEADER — первая строка файла шапка); COPY без \\ ищет файл "
                "на сервере, а учебному это нельзя.",
                hints=("Файл в таблицу на стороне клиента — \\copy таблица FROM 'файл' CSV "
                       "HEADER, внутри psql -c \"…\".",
                       "HEADER — первая строка файла шапка, а не данные; COPY без \\ ищет файл "
                       "на сервере.",
                       "psql -c \"\\copy ops.intake FROM 'intake.csv' CSV HEADER\""),
                solution="psql -c \"\\copy ops.intake FROM 'intake.csv' CSV HEADER\"",
                wrong=("psql -c \"COPY ops.intake FROM 'intake.csv' CSV HEADER\"",
                       "psql -c \"\\copy ops.intake FROM 'intake.csv' CSV\""),
                alternatives=("psql -At -c \"SELECT COUNT(*) FROM ops.intake\" — после "
                              "загрузки: сколько легло",)),
        Variant("Выгрузи в overdue.csv id и сумму (amount) просроченных счетов (status "
                "overdue) по возрастанию id — CSV с шапкой. Запрос в файл пишет сам psql: "
                "\\copy (SELECT …) TO 'файл' CSV HEADER.",
                hints=("Запрос в файл — \\copy (SELECT …) TO 'файл' CSV HEADER.",
                       "Внутри скобок — обычный SELECT с WHERE и ORDER BY id.",
                       "psql -c \"\\copy (SELECT id, amount FROM invoices WHERE status = "
                       "'overdue' ORDER BY id) TO 'overdue.csv' CSV HEADER\""),
                solution="psql -c \"\\copy (SELECT id, amount FROM invoices WHERE status = "
                         "'overdue' ORDER BY id) TO 'overdue.csv' CSV HEADER\"",
                wrong=("psql -c \"\\copy (SELECT id, amount FROM invoices WHERE status = "
                       "'overdue' ORDER BY id) TO 'overdue.csv' CSV\"",
                       "psql -c \"\\copy (SELECT id, amount FROM invoices ORDER BY id) TO "
                       "'overdue.csv' CSV HEADER\""),
                alternatives=("psql --csv -c \"SELECT id, amount FROM invoices WHERE status = "
                              "'overdue' ORDER BY id\" > overdue.csv — то же через --csv",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("\\copy — команда psql: файл читает и пишет сам клиент, ему твоя папка видна, а "
               "данные бегут через соединение. COPY без \\ лезет в файлы сервера, и такое право "
               "дают не всем. pg_dump пишет базу текстом — CREATE TABLE и строки в блоках COPY, "
               "— и по нему базу можно поднять заново.")
    spell = ("\\copy t FROM 'f.csv' CSV HEADER; \\copy (SELECT …) TO 'f.csv' CSV HEADER; pg_dump "
             "-t t vault > backup/t.sql")

    def extend(self, rng, data):
        data.extra["ops.intake"] = _INTAKE
        data.tables["ops.intake"] = []
        return data

    # вариант → разновидность (spec): копия pg_dump — первой (B5: страж Хранилища в
    # PostgreSQL снимает копию pg_dump, а экзамен — только на отработанном в варианте 0)
    SPEC_OF = (2, 0, 1)

    def data_state(self, rng, data, variant):
        spec = self.SPEC_OF[variant % len(self.SPEC_OF)]
        if spec == 0:
            rows = []
            for i in rng.sample(range(100, 900), rng.randint(4, 7)):
                rows.append([i, f"{rng.choice(dbkit.FIRST)} {rng.choice(dbkit.LAST)}",
                             rng.choice(dbkit.DISTRICTS), rng.randrange(500, 9000)])
            text = ",".join(_INTAKE.cols) + "\n" + "".join(
                ",".join(str(v) for v in r) + "\n" for r in rows)
            return {"spec": 0, "want": sorted(rows), "_files": {"intake.csv": text}}
        if spec == 1:
            inv = sorted(data.tables["invoices"], key=lambda x: x["id"])
            body = [f"{x['id']},{x['amount']}" for x in inv if x["status"] == "overdue"]
            return {"spec": 1, "out": "overdue.csv", "want": ["id,amount"] + body}
        table = rng.choice(DUMP_TABLES)
        cols = data.columns(table)
        rows = sorted(([_dump_value(r[c]) for c in cols] for r in data.tables[table]),
                      key=repr)
        return {"spec": 2, "table": table, "out": f"backup/{table}.sql", "want": rows}

    def judge(self, ctx):
        st = ctx.state
        spec = int(st["spec"])
        if spec == 0:
            with self.snapshot(ctx) as snap:
                rows = sorted(list(r) for r in snap.rows("ops.intake", _INTAKE.cols))
            if not rows:
                return Verdict(False)
            if rows == [list(r) for r in st["want"]]:
                return Verdict(True)
            return Verdict(False, MSG_COPY_ROWS)
        if spec == 1:
            got = read_lines(ctx.box, st["out"])
            if got is None:
                return Verdict(False)
            want = list(st["want"])
            if got == want:
                return Verdict(True)
            if got and "|" in got[0]:
                return Verdict(False, MSG_COPY_NOT_CSV)
            if got == want[1:]:
                return Verdict(False, MSG_COPY_NO_HEADER_OUT)
            if sorted(got) == sorted(want):
                return Verdict(False, MSG_COPY_ORDER)
            return Verdict(False, MSG_COPY_WRONG.format(**st))
        raw = sandbox.read_in_box(ctx.box, st["out"], FILE_CAP)
        if raw is None:
            return Verdict(False)
        if raw.startswith(b"PGDMP"):
            return Verdict(False, MSG_DUMP_CUSTOM)
        text = raw.decode("utf-8", errors="replace")
        table = st["table"]
        copies = dump_rows(text)
        mine = f"public.{table}"
        if len(copies) > 1:
            return Verdict(False, MSG_DUMP_FULL.format(**st))
        if mine not in copies:
            if f"CREATE TABLE {mine} (" in text:
                return Verdict(False, MSG_DUMP_SCHEMA.format(**st))
            return Verdict(False, MSG_DUMP_EMPTY.format(**st))
        if f"CREATE TABLE {mine} (" not in text:
            return Verdict(False, MSG_DUMP_DATA.format(**st))
        want = [list(r) for r in st["want"]]
        got = copies[mine]
        if len(got) != len(want):
            return Verdict(False, MSG_DUMP_ROWS.format(got=len(got), n=len(want), **st))
        # M1 (ревью B4): строки копии — те, что в таблице (порядок любой), а не «N строк чего-то»
        if sorted(got, key=repr) != want:
            return Verdict(False, MSG_DUMP_ALIEN.format(**st))
        return Verdict(True)

    def task_hint(self, ctx, line):
        m = re.search(r"(?<!\\)\bCOPY\b[^\"]*\b(FROM|TO)\s+'", line)
        if m and "\\copy" not in line:
            return MSG_COPY_SERVER_TO if m.group(1).upper() == "TO" else MSG_COPY_SERVER
        if re.search(r"\\copy\s+intake\b", line):
            return MSG_COPY_NO_SCHEMA
        if int(ctx.state.get("spec", 0)) == 0 and "\\copy" in line and \
                not re.search(r"\bHEADER\b", line, re.I):
            return MSG_COPY_NO_HEADER_IN
        return None


# --- страж: boss_sql ------------------------------------------------------------------------------

INV_COLS = ("id", "customer_id", "amount", "status")
LED_COLS = ("id", "customer_id", "amount", "kind")
AUD_COLS = ("id", "actor", "action", "tbl", "row_id", "detail")
WRITTEN_OFF = "written_off"          # статус счёта после списания
WRITE_OFF = "write_off"              # вид строки ledger (CHECK на kind его знает)
TARGET_TXT = "report/target.txt"
BOSS_SQL_HISTORY = 2                 # чужих старых строк журнала о счетах цели (их не трогать)
BOSS_SQL_TRIGGERS = (("invoices_audit", "invoices"), ("ledger_audit", "ledger"))
VAULT_BACKUP = {"sqlite": "backup/vault.db", "pg": "backup/vault.sql"}


def _trigger_shapes(engine: str) -> dict:
    """Исходные тексты правил журнала (форма db._sql_shape) так, как их отдаёт снимок движка:
    SQLite — CREATE TRIGGER из схемы; PostgreSQL — pg_get_triggerdef и тело функции."""
    if engine != "pg":
        return {re.match(r"CREATE TRIGGER (\w+)", d).group(1): db._sql_shape(d)
                for d in dbkit.VAULT_SCHEMA_SQLITE if d.startswith("CREATE TRIGGER")}
    bodies = {}
    for d in dbkit.VAULT_SCHEMA_PG:
        m = re.match(r"CREATE FUNCTION (\w+)\(\).*?\$\$(.*)\$\$", d, re.S)
        if m:
            bodies[m.group(1)] = m.group(2)
    out = {}
    for d in dbkit.VAULT_SCHEMA_PG:
        m = re.match(r"CREATE TRIGGER (\w+) (AFTER \w+) ON (\w+) FOR EACH ROW EXECUTE FUNCTION "
                     r"(\w+)\(\)", d)
        if m:
            name, ev, table, fn = m.groups()
            out[name] = db._sql_shape(f"CREATE TRIGGER {name} {ev} ON public.{table} FOR EACH "
                                      f"ROW EXECUTE FUNCTION {fn}() {bodies[fn]}")
    return out


def _norm_rows(rows) -> List[tuple]:
    return sorted(tuple(None if v is None else str(v) for v in r) for r in rows)


def _ledger_nets(data):
    net, charge = Counter(), Counter()
    for r in data.tables["ledger"]:
        net[r["customer_id"]] += r["amount"]
        if r["kind"] == "charge":
            charge[r["customer_id"]] += r["amount"]
    return net, charge


def _add_ledger(data, cid: int, amount: int, kind: str) -> None:
    led = data.tables["ledger"]
    led.append({"id": max(r["id"] for r in led) + 1, "customer_id": cid, "amount": amount,
                "kind": kind})


def _add_invoice(rng, data, cid: int, month: str, amount: int, status: str) -> dict:
    inv = data.tables["invoices"]
    x = {"id": max(r["id"] for r in inv) + 1, "customer_id": cid, "amount": amount,
         "issued_at": dbkit._vault_ts(rng, f"{month}-01", f"{month}-28"), "status": status}
    inv.append(x)
    return x


def _payers(data, but=()) -> List[int]:
    idle = set(data.meta.get("idle", ()))
    return [c["id"] for c in data.tables["customers"] if c["id"] not in idle and c["id"] not in but]


def _ensure_invoices(rng, data, pid: int, month: str, lo: int = 100, hi: int = 600) -> None:
    """У цели есть и неоплаченный счёт, и оплаченный (иначе «без статуса» списал бы то же):
    чего нет — добавить небольшой счёт в месяц month (только добавить — порядок старых
    счетов и выбор цели не трогаются)."""
    mine = [x for x in data.tables["invoices"] if x["customer_id"] == pid]
    if not any(x["status"] in UNPAID for x in mine):
        _add_invoice(rng, data, pid, month, rng.randint(lo, hi), "overdue")
    if not any(x["status"] == "paid" for x in mine):
        _add_invoice(rng, data, pid, month, rng.randint(lo, hi), "paid")


def _boss_rank_state(rng, data) -> dict:
    """A: второй по чистому долгу (сумма ledger) клиент района; второе место делят двое —
    выше меньший id. Первый — с запасом; ниже ничьей — строго меньше. По всей базе первые
    два — не из района, по одним начислениям цель не вторая (данные варианта)."""
    _clean_districts(data)
    dist = {c["id"]: c["district"] for c in data.tables["customers"]}
    net, _ = _ledger_nets(data)
    by = {}
    for cid in sorted(net):
        by.setdefault(dist[cid], []).append(cid)
    pool = sorted(d for d, v in by.items() if len(v) >= 4)
    if pool:
        d = rng.choice(pool)
    else:                                  # мало строк ledger в районах — заводим начисления
        d = max(sorted(by), key=lambda k: len(by[k]))
        fresh = [c for c in _payers(data) if dist[c] == d and c not in net]
        for cid in fresh[:4 - len(by[d])]:
            _add_ledger(data, cid, rng.randint(500, 3000), "charge")
    net, _ = _ledger_nets(data)

    def add(cid, amount, kind):
        _add_ledger(data, cid, amount, kind)
        net[cid] += amount
    ids = sorted((c for c in net if dist[c] == d), key=lambda c: (-net[c], c))
    top, a, b = ids[0], ids[1], ids[2]
    if net[a] <= 0:
        add(a, 1 - net[a] + rng.randint(500, 2000), "charge")
    if net[b] != net[a]:
        add(b, net[a] - net[b], "charge")
    v = net[a]
    if net[top] < v + 2:
        add(top, v + 2 - net[top] + rng.randrange(30), "charge")
    for c in ids[3:]:
        if net[c] >= v:
            add(c, -(net[c] - v + 1 + rng.randrange(30)), "payment")
    ans, hi = min(a, b), max(a, b)
    # по всей базе (без района) первые двое — из других районов
    out = sorted((c for c in net if dist[c] != d), key=lambda c: (-net[c], c))[:2]
    for c in out:
        if net[c] <= net[top] + 2:
            add(c, net[top] + 2 - net[c] + rng.randint(1, 300), "charge")
    # по одним начислениям цель не вторая: первому и соседу по ничьей — начисление и оплата на
    # одну сумму (чистый долг тот же, начислений больше, чем у цели)
    _, charge = _ledger_nets(data)
    for c in (top, hi):
        if charge[c] <= charge[ans] + 2:
            x = charge[ans] + 2 - charge[c] + rng.randint(1, 300)
            add(c, x, "charge")
            add(c, -x, "payment")
    net, charge = _ledger_nets(data)
    glob = sorted(net, key=lambda c: (-net[c], c))
    in_d = sorted((c for c in net if dist[c] == d), key=lambda c: (-charge[c], c))
    _ensure_invoices(rng, data, ans, "2026-09")
    traps = [["first", top], ["tie_hi", hi], ["all", glob[1]], ["charge", in_d[1]]]
    return {"district": d, "pid": ans, "traps": _distinct_traps(ans, traps)}


def _ts_shift(ts: str, minutes: int) -> str:
    from datetime import datetime, timedelta
    t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%d %H:%M:%S")


def _boss_growth_state(rng, data) -> dict:
    """B: месяц наибольшего роста суммы выставленных счетов (LAG) — третий или четвёртый, с
    запасом; цель — клиент самого крупного счёта этого месяца. Месяц с наибольшей суммой —
    первый (в нём и самый крупный счёт вообще, чужой); у месяца наибольшего падения свой
    крупнейший счёт — тоже чужой (данные варианта: счета добавляем и правим)."""
    inv = data.tables["invoices"]

    def mon(x):
        return x["issued_at"][:7]
    months = sorted({mon(x) for x in inv})
    m0, top_month = months[0], rng.choice(months[2:])
    t = rng.choice(sorted((x for x in inv if mon(x) == top_month), key=lambda x: x["id"]))
    pid = t["customer_id"]
    t["status"] = rng.choice(UNPAID)
    # оплаченный счёт цели — в том же месяце: чужим «знаку наоборот» передают счёт из другого
    # месяца, и он у цели не пропадёт
    if not any(x["customer_id"] == pid and x["status"] == "paid" and mon(x) == top_month
               for x in inv):
        _add_invoice(rng, data, pid, top_month, rng.randint(100, 600), "paid")
    others = _payers(data, but=(pid,))

    def sums():
        s = Counter()
        for x in inv:
            s[mon(x)] += x["amount"]
        return s

    def growth(s):
        return {months[i]: s[months[i]] - s[months[i - 1]] for i in range(1, len(months))}
    t["amount"] = max(x["amount"] for x in inv if mon(x) == top_month and x is not t) + \
        rng.randint(50, 400)
    while True:
        g = growth(sums())
        if g[top_month] >= max(v for m, v in g.items() if m != top_month) + 2:
            break
        hi = min(8000, t["amount"] - 1)
        _add_invoice(rng, data, rng.choice(others), top_month, rng.randint(min(1000, hi), hi),
                     rng.choices(dbkit.INVOICE_STATUSES, dbkit.INVOICE_WEIGHTS)[0])
    while True:
        s = sums()
        if s[m0] >= max(v for m, v in s.items() if m != m0) + 2:
            break
        _add_invoice(rng, data, rng.choice(others), m0, rng.randint(2000, 8000),
                     rng.choices(dbkit.INVOICE_STATUSES, dbkit.INVOICE_WEIGHTS)[0])
    big = rng.choice(sorted((x for x in inv if mon(x) == m0 and x["customer_id"] != pid),
                            key=lambda x: x["id"]))
    big["amount"] = max(x["amount"] for x in inv) + rng.randint(50, 400)
    g = growth(sums())
    low = min(sorted(g), key=lambda m: g[m])       # «знак наоборот»: наибольшее падение

    def biggest(m):
        rows = sorted((x for x in inv if mon(x) == m), key=lambda x: (-x["amount"], x["id"]))
        if len(rows) > 1 and rows[0]["amount"] == rows[1]["amount"]:
            rows[0]["amount"] += 1                   # крупнейший счёт месяца — один
        return rows[0]
    worst = biggest(low)
    if worst["customer_id"] == pid:
        worst["customer_id"] = rng.choice(others)
    traps = [["sum", big["customer_id"]], ["sign", worst["customer_id"]]]
    # «сумма счетов ≠ долг» доправляет крупнейший счёт месяца: он и так крупнее всех в месяце
    return {"mon": top_month, "pid": pid, "traps": _distinct_traps(pid, traps),
            "_bump": t["id"]}


def _boss_oldest_state(rng, data) -> dict:
    """C: клиент самого старого неоплаченного (open, overdue) счёта: он overdue и раньше всех
    неоплаченных. Самый старый счёт вообще — оплаченный и чужой; самый старый open, самый
    новый неоплаченный и неоплаченный с меньшим id — тоже чужие (данные варианта)."""
    inv = data.tables["invoices"]

    def unpaid():
        return sorted((x for x in inv if x["status"] in UNPAID),
                      key=lambda x: (x["issued_at"], x["id"]))
    rows = unpaid()
    first_id = min(x["id"] for x in rows)
    o = rng.choice([x for x in rows[:10] if x["id"] != first_id])
    pid = o["customer_id"]
    others = _payers(data, but=(pid,))
    o["status"] = "overdue"
    o["issued_at"] = _ts_shift(rows[0]["issued_at"], -rng.randint(30, 600))
    paid = sorted((x for x in inv if x["status"] == "paid" and x["customer_id"] != pid),
                  key=lambda x: x["id"])
    early = rng.choice(paid)
    early["issued_at"] = _ts_shift(min(x["issued_at"] for x in inv), -rng.randint(30, 600))
    for pick in (lambda: min((x for x in inv if x["status"] == "open"),
                             key=lambda x: (x["issued_at"], x["id"])),
                 lambda: max(unpaid(), key=lambda x: (x["issued_at"], x["id"])),
                 lambda: min(unpaid(), key=lambda x: x["id"])):
        x = pick()
        if x["customer_id"] == pid and x is not o:
            x["customer_id"] = rng.choice(others)
    _ensure_invoices(rng, data, pid, "2026-09")
    opened = min((x for x in inv if x["status"] == "open"), key=lambda x: (x["issued_at"],
                                                                           x["id"]))
    traps = [["all", early["customer_id"]], ["open", opened["customer_id"]],
             ["desc", max(unpaid(), key=lambda x: (x["issued_at"], x["id"]))["customer_id"]],
             ["by_id", min(unpaid(), key=lambda x: x["id"])["customer_id"]]]
    return {"pid": pid, "traps": _distinct_traps(pid, traps)}


MSG_SQLB_TARGET = ("В report/target.txt не тот id. Сверь запрос цели с заданием: что считаешь, "
                   "в каком порядке, какое место берёшь.")
MSG_SQLB_NULL_FIRST = ("Рост посчитан, но взят первый месяц: у него прошлого нет, LAG там NULL, а "
                       "в PostgreSQL NULL при DESC встаёт первым. Отсей его — WHERE … IS NOT NULL — "
                       "или ORDER BY … DESC NULLS LAST.")
MSG_SQLB_TARGET_PARTS = ("В report/target.txt нужен один id — только число, без шапки и других "
                         "граф: {run} \"SELECT id …\" > report/target.txt.")
MSG_SQLB_NO_COPY = ("Правишь без страховки: копии нет. Сначала копия, потом правка. Набери "
                    "reset — и по порядку: mkdir -p backup, {copy}, потом правки.")
MSG_SQLB_LATE = ("Копия {backup} снята после правки — в ней уже не исходные данные, вернуть по "
                 "ней нечего. Набери reset и сделай копию первой.")
MSG_SQLB_BROKEN = ("Копия {backup} повреждена — по ней ничего не вернуть. Набери reset и сделай "
                   "копию заново, до правки: {copy}.")
MSG_SQLB_FILE = ("backup — это файл, а не папка. Убери его (rm backup), потом mkdir -p backup и "
                 "копию — в неё.")
MSG_SQLB_DUMP_BIN = ("Это двоичный формат pg_dump (-Fc): его читает только pg_restore. Нужна "
                     "текстовая копия: pg_dump vault > backup/vault.sql.")
MSG_SQLB_DUMP_PART = ("В {backup} не вся база: нет строк таблиц invoices, ledger или audit_log "
                      "(-t, -s?). Копия всей базы — pg_dump vault > backup/vault.sql.")
MSG_SQLB_ALL = ("Списаны счета всех клиентов: UPDATE без условия на цель. Верни базу ({undo}) и "
                "правь WHERE customer_id = … AND status IN ('open', 'overdue').")
MSG_SQLB_EXTRA = ("Задеты счета других клиентов ({n}): правка шире одной цели. Верни базу "
                  "({undo}) и сверь WHERE.")
MSG_SQLB_OTHER = ("Списан долг не цели, а клиенту {who}: сверь запрос цели. Верни базу ({undo}) "
                  "и спиши по id из report/target.txt.")
MSG_SQLB_PAID = ("Оплаченные счета списывать не надо: только open и overdue — AND status IN "
                 "('open', 'overdue'). Верни базу ({undo}).")
MSG_SQLB_STATUS = "Статус счёта после списания — ровно 'written_off', в одинарных кавычках."
MSG_SQLB_PART = ("Списаны не все неоплаченные счета цели: и open, и overdue — status IN ('open', "
                 "'overdue').")
MSG_SQLB_INV_EDIT = ("В invoices изменилось не только status (или пропали строки): списание "
                     "меняет один статус. Верни базу ({undo}).")
MSG_SQLB_LED_OLD = ("Старые строки ledger трогать нельзя: списание — новая строка, а прошлое "
                    "остаётся как было. Верни базу ({undo}).")
MSG_SQLB_LED_MANY = ("В ledger новых строк больше одной: списание — одна строка на весь долг. "
                     "Лишние убери: DELETE FROM ledger WHERE id = ….")
MSG_SQLB_LED_WHO = ("Новая строка ledger — не на цель: customer_id в ней должен быть id из "
                    "report/target.txt.")
MSG_SQLB_LED_KIND = ("Вид строки списания — 'write_off' (так его знает CHECK на kind), а "
                     "'written_off' — статус счёта.")
MSG_SQLB_LED_SIGN = ("Сумма списания — с минусом: долг уменьшается. amount = -долг, а не +долг.")
MSG_SQLB_LED_INV = ("Это сумма неоплаченных счетов, а долг — по ledger: SUM(amount) строк цели "
                    "(начисления с плюсом, оплаты и списания с минусом).")
MSG_SQLB_LED_SUM = ("Сумма строки списания не равна минус долгу цели. Долг — SUM(amount) её строк "
                    "ledger до списания.")
MSG_SQLB_CONSTRAINT = ("Ограничения таблицы сломаны (CHECK на kind или ссылка на customers) — "
                       "это след заметнее строки. Верни базу ({undo}).")
MSG_SQLB_FOREIGN = ("Ты стёр и чужие строки audit_log — так и палятся: удалять можно только то, "
                    "что дописали твои правки (они последние, ORDER BY id DESC). Набери reset.")
MSG_SQLB_TRIGGER = ("audit_log заглушён — это заметнее строки: его правила (триггеры) должны работать как "
                    "были (без DROP, DISABLE, своих триггеров и RULE, подставной audit_log и "
                    "search_path роли или базы). Верни базу "
                    "({undo}) и убери только свои строки audit_log.")
MSG_SQLB_LEFT = ("В audit_log ещё есть строки о твоих правках ({n}): каждый списанный счёт и "
                 "строка ledger пишут по строке. Посмотри последние — ORDER BY id DESC LIMIT 5.")
MSG_SQLB_KIND_FORM = ("В ledger вид строки — 'write_off': CHECK на kind отверг 'written_off', "
                      "строка не легла. 'written_off' — статус счёта в invoices.")
MSG_SQLB_NO_COMMIT = ("BEGIN без COMMIT: на выходе клиент откатил всю транзакцию — в базе ничего "
                      "не изменилось. Допиши COMMIT; в конце.")
MSG_SQLB_BARE = ("В базе правок нет. Если внутри {client} был BEGIN — без COMMIT при выходе всё "
                 "откатилось, а после ошибки в транзакции COMMIT молча становится ROLLBACK. "
                 "Повтори правки и закончи COMMIT; — до выхода.")
MSG_SQLB_LEDGER_ID = ("id у ledger сам не ставится: впиши его в INSERT — (id, customer_id, "
                      "amount, kind), id новой строки — {lid}.")


class BossSql(SqlTask):
    """Страж Хранилища: тихо списать долг одному клиенту. Цель — CTE и окно (A — второй по
    чистому долгу района, ничья — меньший id; B — месяц наибольшего роста через LAG и его
    самый крупный счёт; C — самый старый неоплаченный, ROW_NUMBER), id — в report/target.txt;
    копия до правок (.backup или pg_dump); списание одной транзакцией — неоплаченные счета в
    written_off и строка ledger write_off на минус долг (CHECK на kind и ссылки целы); строки
    журнала audit_log о своих правках — убрать, чужие не трогать, правила журнала — на месте.
    Движок — PostgreSQL после psql_pipe при годном стенде, иначе SQLite с той же сутью (R004).
    Всё уже было: WITH — cte_with, окно — window_rank и window_lag, транзакция и журнал —
    tx_delete и backup_update (Картотека), pg_dump — copy_dump (вариант 0), .backup —
    backup_update. Проверка — по состоянию базы, копии и файла; ответы — в secret_keys."""
    id = "boss_sql"
    title = "Списание долга"
    boss = True
    par = 600
    secret_keys = VaultTask.secret_keys + ("pid", "debt", "mon", "nid", "led_sha", "audit_sha")
    scroll = ("Цель — WITH и окно: \"SELECT ROW_NUMBER() OVER (ORDER BY s DESC, id) AS n …\" в подзапросе; "
              "рост — \"s - LAG(s) OVER (ORDER BY mon)\".\n"
              "Копия до правок: .backup или pg_dump vault > backup/vault.sql. Правки — \"BEGIN; "
              "UPDATE …; INSERT INTO …; COMMIT;\"; ошибка в PostgreSQL — ROLLBACK;.\n"
              "audit_log: \"SELECT * FROM audit_log ORDER BY id DESC LIMIT 5\", свои строки — \"DELETE FROM audit_log WHERE "
              "id > N\".")
    # финал M3: без PostgreSQL игрок pg_dump не встречал (copy_dump — задача стенда) — в
    # SQLite карточка называет только .backup
    SCROLL_SQLITE = scroll.replace("Копия до правок: .backup или pg_dump vault > backup/vault.sql.",
                                   "Копия до правок: sqlite3 vault.db \".backup backup/vault.db\".")
    assert SCROLL_SQLITE != scroll
    steps = ("report/target.txt — id цели",
             "Копия базы до правок",
             "Долг цели списан одной транзакцией: неоплаченные счета (open, overdue) — "
             "written_off, в ledger — строка write_off на минус долг; у остальных ничего не "
             "изменилось, ограничения целы",
             "Следы заметены: строк audit_log о твоих правках нет, чужие строки целы")
    # те же шаги с полями рана (steps_for): только открытые ключи state
    STEP_TEMPLATES = (steps[0], "Копия базы до правок: {backup}",
                      "Долг цели списан одной транзакцией: неоплаченные счета (open, overdue) — "
                      "written_off, в ledger — строка id {lid}, kind write_off, amount = минус "
                      "долг (SUM(amount) её строк ledger); у остальных ничего не изменилось, "
                      "ограничения целы",
                      steps[3])
    _COPY = "mkdir -p backup report && {copy} && "
    _A = ("{run} \"WITH t AS (SELECT l.customer_id AS id, SUM(l.amount) AS s FROM ledger l JOIN "
          "customers c ON c.id = l.customer_id WHERE c.district = '{district}' GROUP BY "
          "l.customer_id) SELECT id FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY s DESC, {order}) "
          "AS n FROM t) x WHERE n = {place}\" > report/target.txt && ")
    _B_GROW = ("{run} \"WITH m AS (SELECT {imonth} AS mon, SUM(amount) AS s FROM invoices GROUP "
               "BY mon) SELECT mon, s - LAG(s) OVER (ORDER BY mon) FROM m\" && ")
    _B = ("{run} \"SELECT customer_id FROM invoices WHERE {imonth} = '{mon}' ORDER BY amount "
          "DESC LIMIT 1\" > report/target.txt && ")
    _C = ("{run} \"SELECT customer_id FROM (SELECT customer_id, ROW_NUMBER() OVER (ORDER BY "
          "issued_at, id) AS n FROM invoices WHERE status IN ('open', 'overdue')) t WHERE n = 1\" "
          "> report/target.txt && ")
    _WO = ("{run} \"BEGIN; UPDATE invoices SET status = 'written_off' WHERE customer_id = {pid} "
           "AND status IN ('open', 'overdue'); INSERT INTO ledger (id, customer_id, amount, kind) "
           "VALUES ({lid}, {pid}, -{debt}, 'write_off'); COMMIT;\" && ")
    _CLEAN = "{run} \"DELETE FROM audit_log WHERE id > {nid}\""
    _HINT_DO = ("Копия — mkdir -p backup report и {copy}. Потом BEGIN; UPDATE invoices …; INSERT "
                "INTO ledger …; COMMIT;, а свой след — DELETE FROM audit_log WHERE id > <номер>.")
    # последняя подсказка — без готовых чисел (аудит A7): <id>, <минус долг>
    _HINT_LAST = ("{run} \"BEGIN; UPDATE invoices SET status = 'written_off' WHERE customer_id = "
                  "<id> AND status IN ('open', 'overdue'); INSERT INTO ledger VALUES ({lid}, "
                  "<id>, <минус долг>, 'write_off'); COMMIT;\"")
    _TERMITE = ("{run} \"DELETE FROM audit_log WHERE actor = 'termit'\" — твои правки audit_log "
                "пишет от имени termit")
    variants = (
        Variant("Тихо спиши долг одному клиенту в {db}. Долг клиента — сумма amount его строк "
                "ledger (оплаты и списания там с минусом). Цель — второй по долгу клиент района "
                "{district}; при равном долге выше тот, у кого меньше id. Её id запиши в "
                "report/target.txt, остальное — по шагам схватки.",
                hints=("Долги района — в WITH: SUM(amount) ledger по клиенту, склейка с customers, "
                       "WHERE district. Место — ROW_NUMBER() OVER (ORDER BY s DESC, id), снаружи "
                       "WHERE n = 2.",
                       _HINT_DO, _HINT_LAST),
                solution=_COPY + _A.replace("{order}", "id").replace("{place}", "2") + _WO
                + _CLEAN,
                wrong=(_COPY + _A.replace("{order}", "id").replace("{place}", "1") + _WO + _CLEAN,
                       _COPY + _A.replace("{order}", "id DESC").replace("{place}", "2") + _WO
                       + _CLEAN,
                       "mkdir -p report && " + _A.replace("{order}", "id").replace(
                           "{place}", "2") + _WO + _CLEAN,
                       _COPY + _A.replace("{order}", "id").replace("{place}", "2")
                       + _WO.replace("-{debt}", "{debt}") + _CLEAN),
                alternatives=("{run} \"WITH t AS (…) SELECT id FROM t ORDER BY s DESC, id LIMIT 1 "
                              "OFFSET 1\" — без окна: пропустить первого", _TERMITE)),
        Variant("Счета (invoices) в {db} сложи по месяцам выставления — месяц: {imonth}. В месяц, "
                "когда эта сумма выросла к прошлому сильнее всего, пришёл самый крупный счёт; "
                "его клиент — цель, её id — в report/target.txt. Долг цели — сумма amount её "
                "строк ledger; дальше — шаги схватки.",
                hints=("Итог по месяцам — WITH m AS (SELECT {imonth} AS mon, SUM(amount) AS s … "
                       "GROUP BY mon); рост — s - LAG(s) OVER (ORDER BY mon). В том месяце — ORDER "
                       "BY amount DESC LIMIT 1.",
                       _HINT_DO, _HINT_LAST),
                solution=_COPY + _B_GROW + _B + _WO + _CLEAN,
                wrong=(_COPY + _B_GROW + "{run} \"SELECT customer_id FROM invoices ORDER BY amount "
                       "DESC LIMIT 1\" > report/target.txt && " + _WO + _CLEAN,
                       _COPY + _B + _WO + "{run} \"DELETE FROM audit_log WHERE tbl = 'invoices' OR "
                       "tbl = 'ledger'\"",
                       "mkdir -p report && " + _B + _WO + _COPY + _CLEAN),
                alternatives=("в PostgreSQL — date_trunc('month', issued_at) вместо {imonth}: месяц "
                              "первым днём",
                              _TERMITE)),
        Variant("Найди в {db} самый старый неоплаченный счёт: status open или overdue, время — "
                "issued_at. Его клиент — цель; id цели — в report/target.txt. Её долг (сумма "
                "amount строк ledger) спиши и прибери за собой — как велят шаги схватки.",
                hints=("Неоплаченные — WHERE status IN ('open', 'overdue'). Номер по времени — "
                       "ROW_NUMBER() OVER (ORDER BY issued_at, id) в подзапросе, снаружи WHERE n "
                       "= 1.",
                       _HINT_DO, _HINT_LAST),
                solution=_COPY + _C + _WO + _CLEAN,
                wrong=(_COPY + _C.replace(" WHERE status IN ('open', 'overdue')", "") + _WO
                       + _CLEAN,
                       _COPY + _C.replace("ORDER BY issued_at, id", "ORDER BY id") + _WO + _CLEAN,
                       _COPY + _C + _WO.replace(" AND status IN ('open', 'overdue')", "")
                       + _CLEAN),
                alternatives=("{run} \"SELECT customer_id FROM invoices WHERE status IN ('open', "
                              "'overdue') ORDER BY issued_at, id LIMIT 1\" — без окна", _TERMITE)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Списание по правилам: цель нашёл запросом (итог в WITH, место — окном), снял копию "
               "до правок, правки сделал одной транзакцией — счета и строка ledger вместе или "
               "никак, — и убрал из audit_log ровно то, что дописали твои правки. CHECK и ссылки "
               "не тронуты: ограничение, которое мешает, — подсказка, а не препятствие.")
    spell = ("WITH t AS (…) + ROW_NUMBER() OVER (ORDER BY s DESC, id); BEGIN; UPDATE …; INSERT "
             "INTO ledger …; COMMIT; DELETE FROM audit_log WHERE id > N")
    trap_messages = {
        "first": "Это первый по долгу, а нужен второй: снаружи WHERE n = 2.",
        "tie_hi": "Ничья: из двух равных по долгу выше тот, у кого id меньше — ORDER BY s DESC, id.",
        "all": "Это второй по всей базе, а нужен второй в районе {district}: WHERE c.district.",
        "charge": "Это второй по начислениям (charge), а долг — сумма всех строк ledger клиента: "
                  "оплаты и списания там с минусом.",
        "sum": "Это клиент самого крупного счёта месяца с наибольшей суммой (или всей базы), а "
               "нужен месяц наибольшего РОСТА: s - LAG(s) OVER (ORDER BY mon), без пустого роста "
               "первого месяца (IS NOT NULL).",
        "sign": "Знак наоборот: рост — нынешний месяц минус прошлый, s - LAG(s), а не LAG(s) - s.",
        "c_all": "Это самый старый счёт вообще, а он оплачен: нужны только open и overdue.",
        "open": "Это самый старый open, а overdue тоже не оплачен: status IN ('open', 'overdue').",
        "desc": "Это самый новый неоплаченный счёт: старый — ORDER BY issued_at по возрастанию.",
        "by_id": "Порядок по id — не порядок времени: самый старый — ORDER BY issued_at.",
    }

    def steps_for(self, state):
        try:
            return [s.format(**state) for s in self.STEP_TEMPLATES]
        except (KeyError, IndexError):
            return list(self.steps)

    def scroll_for(self, state):
        if (state or {}).get(dbkit.ENGINE_KEY) == "sqlite":
            return self.SCROLL_SQLITE
        return self.scroll

    def engine_texts(self, engine, state):
        if engine == "pg":
            return {"copy": "pg_dump vault > backup/vault.sql", "backup": VAULT_BACKUP["pg"],
                    "imonth": "to_char(issued_at, 'YYYY-MM')",
                    "undo": "reset — сервер поднимется с исходной базой"}
        return {"copy": "sqlite3 vault.db \".backup backup/vault.db\"",
                "backup": VAULT_BACKUP["sqlite"], "imonth": "strftime('%Y-%m', issued_at)",
                "undo": "cp backup/vault.db vault.db или reset"}

    def extend(self, rng, data):
        """Сюжетные таблицы темы поверх общей базы (слой 4, шаг 2): rng не тратится, проверка
        их не читает — данные варианта те же в любой теме."""
        from termit_app import story
        for t in story.vault_tables(self.id):
            cols = tuple(t["cols"])
            data.extra[t["name"]] = dbkit.Extra(cols, t["sqlite"], t["pg"])
            data.tables[t["name"]] = [dict(zip(cols, r)) for r in t["rows"]]
        return data

    def data_state(self, rng, data, variant):
        if variant == 1:
            st = _boss_growth_state(rng, data)
        elif variant == 2:
            st = _boss_oldest_state(rng, data)
            st["traps"] = [["c_all" if k == "all" else k, v] for k, v in st["traps"]]
        else:
            st = _boss_rank_state(rng, data)
        pid = st["pid"]
        net, _ = _ledger_nets(data)
        if net[pid] <= 0:                     # долг цели — положительный (A — уже по постройке)
            _add_ledger(data, pid, 1 - net[pid] + rng.randint(500, 3000), "charge")
            net, _ = _ledger_nets(data)
        debt = net[pid]
        inv = data.tables["invoices"]
        unpaid = [x for x in inv if x["customer_id"] == pid and x["status"] in UNPAID]
        bump = st.pop("_bump", None)
        if sum(x["amount"] for x in unpaid) == debt:     # «сумма счетов» ≠ долг по ledger
            x = next((x for x in unpaid if x["id"] == bump), None)
            (x or max(unpaid, key=lambda x: (x["amount"], x["id"])))["amount"] += 1
        mine = sorted(x["id"] for x in inv if x["customer_id"] == pid)
        audit = data.tables["audit_log"]
        for r in rng.sample(sorted(audit, key=lambda r: r["id"]), BOSS_SQL_HISTORY):
            r["row_id"] = rng.choice(mine)    # чужие правки о счетах цели: row_id — не след
        led = data.tables["ledger"]
        unpaid_ids = sorted(x["id"] for x in unpaid)
        inv_rows = [tuple(x[c] for c in INV_COLS) for x in inv]
        want = [r[:3] + (WRITTEN_OFF,) if r[0] in unpaid_ids else r for r in inv_rows]
        return dict(st, debt=debt, lid=max(r["id"] for r in led) + 1,
                    nid=max(r["id"] for r in audit),
                    orig_sha=db.rows_sha(inv_rows), want_sha=db.rows_sha(want),
                    led_sha=db.rows_sha([tuple(r[c] for c in LED_COLS) for r in led]),
                    audit_sha=db.rows_sha([tuple(r[c] for c in AUD_COLS) for r in audit]),
                    marks={"unpaid": unpaid_ids,
                           "sum_unpaid": sum(x["amount"] for x in unpaid),
                           "inv": {str(r[0]): list(r[1:]) for r in inv_rows},
                           "led": {str(r["id"]): [r["customer_id"], r["amount"], r["kind"]]
                                   for r in led},
                           "audit_ids": sorted(r["id"] for r in audit)})

    # --- шаги: (готово, отклик или None) -------------------------------------------------------

    def _target_ids(self, st) -> dict:
        return {str(v): k for k, v in st.get("traps") or []}

    def _step_target(self, ctx):
        raw = sandbox.read_in_box(ctx.box, TARGET_TXT, FILE_CAP)
        if raw is None:
            return False, None
        words = re.findall(r"[^\s|,;]+", raw.decode("utf-8", errors="replace"))
        st = ctx.state
        if not words:
            return False, None
        if len(words) > 1:
            return False, MSG_SQLB_TARGET_PARTS
        if base.variant_index(st.get("_variant", 0), len(self.variants)) == 0:
            # аудит 9б, п. 4: цель записана запросом без второго ключа — удача, а не правило
            src = next((c.line for c in reversed(ctx.cmds or ()) if TARGET_TXT in c.line), "")
            if no_tiebreak(src, outer=True):
                return False, MSG_TIE_LUCK
        if words[0] == str(st["pid"]):
            return True, None
        trap = self._target_ids(st).get(words[0])
        if trap == "sum" and self.engine_of(st) == "pg" and any(
                null_first_desc(c.line) for c in ctx.cmds or ()):
            # аудит 9б, п. 1: LAG у игрока есть, а первым при DESC встал пустой рост
            return False, MSG_SQLB_NULL_FIRST
        if trap:
            return False, self.trap_messages[trap]
        return False, MSG_SQLB_TARGET

    def _backup_rows(self, ctx):
        """(invoices, ledger, audit_log) копии в проекциях проверки; None — копии нет;
        строка — отклик (копия не та по форме)."""
        st = ctx.state
        rel = VAULT_BACKUP[self.engine_of(st)]
        if self.engine_of(st) != "pg":
            if not db._exists(ctx.box, rel):
                return None
            try:
                with dbread.SqliteSnapshot(ctx.box, rel) as snap:
                    return (snap.rows("invoices", INV_COLS), snap.rows("ledger", LED_COLS),
                            snap.rows("audit_log", AUD_COLS))
            except dbread.Broken:
                return MSG_SQLB_BROKEN
        raw = sandbox.read_in_box(ctx.box, rel, FILE_CAP)
        if raw is None:
            return None
        if raw.startswith(b"PGDMP"):
            return MSG_SQLB_DUMP_BIN
        dump = dump_rows(raw.decode("utf-8", errors="replace"))
        cols = dbkit.VAULT_COLUMNS
        out = []
        for table, want in (("invoices", INV_COLS), ("ledger", LED_COLS),
                            ("audit_log", AUD_COLS)):
            rows = dump.get(f"public.{table}")
            if not rows:
                return MSG_SQLB_DUMP_PART
            idx = [cols[table].index(c) for c in want]
            if any(len(r) != len(cols[table]) for r in rows):
                return MSG_SQLB_DUMP_PART
            out.append([tuple(r[i] for i in idx) for r in rows])
        return tuple(out)

    def _step_copy(self, ctx, edited: bool):
        st = ctx.state
        got = self._backup_rows(ctx)
        if isinstance(got, str):
            return False, got
        if got is None:
            if db._is_file(ctx.box, "backup"):
                return False, MSG_SQLB_FILE
            return False, MSG_SQLB_NO_COPY if edited else None
        inv, led, aud = got
        if (db.rows_sha(inv), db.rows_sha(led), db.rows_sha(aud)) == (
                st["orig_sha"], st["led_sha"], st["audit_sha"]):
            return True, None
        return False, MSG_SQLB_LATE

    def _constraints_ok(self, snap) -> bool:
        checks = " ".join(snap.checks("ledger"))
        if not all(f"'{k}'" in checks for k in dbkit.LEDGER_KINDS):
            return False
        ref = {"from": "customer_id", "table": "customers", "to": "id"}
        return ref in snap.fks("ledger") and ref in snap.fks("invoices")

    def _step_invoices(self, inv, st):
        sha = db.rows_sha(inv)
        if sha == st["want_sha"]:
            return True, None
        if sha == st["orig_sha"]:
            return False, None
        marks = st["marks"]
        orig = marks["inv"]
        now = {str(r[0]): list(r[1:]) for r in _norm_rows(inv)}
        if set(now) != set(orig) or any(now[k][:2] != [str(v) for v in orig[k][:2]]
                                        for k in orig):
            return False, MSG_SQLB_INV_EDIT
        changed = {k for k in orig if now[k][2] != orig[k][2]}
        unpaid_all = {k for k, r in orig.items() if r[2] in UNPAID}
        mine = {str(i) for i in marks["unpaid"]}
        if unpaid_all - mine and unpaid_all <= changed:
            return False, MSG_SQLB_ALL
        owners = {str(orig[k][0]) for k in changed}
        if str(st["pid"]) not in owners and len(owners) == 1:
            who = owners.pop()
            trap = self._target_ids(st).get(who)
            return False, (self.trap_messages[trap] if trap else
                           MSG_SQLB_OTHER.replace("{who}", who))
        if owners - {str(st["pid"])}:
            return False, MSG_SQLB_EXTRA.replace("{n}", str(len(owners - {str(st["pid"])})))
        if changed - mine:
            return False, MSG_SQLB_PAID
        if any(now[k][2] != WRITTEN_OFF for k in changed):
            return False, MSG_SQLB_STATUS
        return False, MSG_SQLB_PART

    def _step_ledger(self, led, st):
        marks = st["marks"]
        orig = marks["led"]
        now = {str(r[0]): list(r[1:]) for r in _norm_rows(led)}
        if any(now.get(k) != [str(v) for v in r] for k, r in orig.items()):
            return False, MSG_SQLB_LED_OLD
        new = [r for k, r in sorted(now.items()) if k not in orig]
        if not new:
            return False, None
        if len(new) > 1:
            return False, MSG_SQLB_LED_MANY
        cid, amount, kind = new[0]
        if cid != str(st["pid"]):
            return False, MSG_SQLB_LED_WHO
        if kind != WRITE_OFF:
            return False, MSG_SQLB_LED_KIND
        if amount == str(-st["debt"]):
            return True, None
        if amount == str(st["debt"]):
            return False, MSG_SQLB_LED_SIGN
        if amount in (str(-marks["sum_unpaid"]), str(marks["sum_unpaid"])):
            return False, MSG_SQLB_LED_INV
        return False, MSG_SQLB_LED_SUM

    def _step_traces(self, snap, aud, st, done: bool):
        """Исходные строки журнала — все на месте и как были; дописанных правками нет; правила
        журнала — на месте, с исходным текстом и не выключены (A5-review M1, A7)."""
        ids = set(st["marks"]["audit_ids"])
        if db.rows_sha([r for r in aud if int(r[0]) in ids]) != st["audit_sha"]:
            return False, MSG_SQLB_FOREIGN
        if not self._journal_ok(snap, self.engine_of(st)):
            return False, MSG_SQLB_TRIGGER
        if not done:
            return False, None
        return db.rows_sha(aud) == st["audit_sha"], None

    @staticmethod
    def _journal_ok(snap, engine: str) -> bool:
        """Журнал работает (ревью B5, I1): триггеры базы — ровно правила журнала, белым
        списком (своё BEFORE INSERT на audit_log, RAISE(IGNORE) — лишнее), с исходными телами,
        в обычном режиме (не D, R, A); правил CREATE RULE на таблицах журнала и правок нет; у
        функций правил нет своего SET (search_path на подставную ops.audit_log) и SECURITY
        DEFINER; нет настроек роли и базы (ALTER ROLE/DATABASE … SET) и своих audit_log вне
        public (финал I1). Временное выключение с возвратом (DISABLE → правки → ENABLE, DROP →
        тот же CREATE, временная audit_log в сессии правок) по состоянию не отличить от честной
        чистки — допустимо (спека, страж)."""
        state = snap.journal_state()
        trig = state["triggers"]
        if {(n, t) for n, (t, _) in trig.items()} != set(BOSS_SQL_TRIGGERS):
            return False
        if any(mode != "O" for _, mode in trig.values()):
            return False
        if any(state["rules"].get(t) for t in ("audit_log", "invoices", "ledger")):
            return False
        if any(cfg or secdef for cfg, secdef in state["funcs"].values()):
            return False
        # финал I1: search_path роли или базы (ALTER ROLE/DATABASE … SET) и своя audit_log в
        # другой схеме — журнал заглушён и после правок; временная — до конца своей сессии
        if state.get("settings") or state.get("shadows"):
            return False
        bodies = snap.trigger_sql()
        return all(db._sql_shape(bodies.get(n)) == shape
                   for n, shape in _trigger_shapes(engine).items())

    def _steps(self, ctx, snap):
        st = ctx.state
        inv = snap.rows("invoices", INV_COLS)
        led = snap.rows("ledger", LED_COLS)
        aud = snap.rows("audit_log", AUD_COLS)
        edited = db.rows_sha(inv) != st["orig_sha"] or db.rows_sha(led) != st["led_sha"]
        copy = self._step_copy(ctx, edited)
        wo = (False, None)
        if edited and not self._constraints_ok(snap):
            wo = (False, MSG_SQLB_CONSTRAINT)
        else:
            i_ok, i_msg = self._step_invoices(inv, st)
            l_ok, l_msg = self._step_ledger(led, st)
            wo = (i_ok and l_ok, i_msg or l_msg)
        traces = self._step_traces(snap, aud, st, wo[0])
        return [self._step_target(ctx), copy, wo, traces], aud, edited

    def progress(self, ctx):
        try:
            with self.snapshot(ctx) as snap:
                return [ok for ok, _ in self._steps(ctx, snap)[0]]
        except dbread.Broken:
            return [False] * len(self.steps)

    def judge(self, ctx):
        with self.snapshot(ctx) as snap:
            steps, aud, edited = self._steps(ctx, snap)
        base.memo_marks(ctx, [ok for ok, _ in steps])
        if all(ok for ok, _ in steps):
            return Verdict(True)
        target, copy, wo, traces = steps
        for ok, msg in (wo, copy, target, traces):          # правка шире цели — важнее всего
            if not ok and msg:
                return Verdict(False, msg.format(**ctx.state))
        if wo[0] and not traces[0] and re.search(r"\bDELETE\b.*\baudit_log\b",
                                                 last_client_line(ctx), re.I):
            ids = set(ctx.state["marks"]["audit_ids"])
            left = sum(1 for r in aud if int(r[0]) not in ids)
            return Verdict(False, MSG_SQLB_LEFT.format(n=left))
        # аудит 9б, п. 6: правили внутри клиента и вышли — а в базе ничего (BEGIN без COMMIT
        # или ошибка в транзакции); цель и копия готовы, последняя команда — голый клиент
        last = ctx.cmds[-1].line.strip() if ctx.cmds else ""
        if target[0] and copy[0] and not edited and last in ("psql", f"sqlite3 {DB}"):
            return Verdict(False, MSG_SQLB_BARE.format(client=last.split()[0]))
        return Verdict(False)

    def task_hint(self, ctx, line):
        body = line.replace("\\'", "'")
        if re.search(r"\bINSERT\s+INTO\s+ledger\b[^;\"]*'written_off'", body, re.I):
            return MSG_SQLB_KIND_FORM
        if re.search(r"\bBEGIN\b", body, re.I) and not re.search(r"\b(?:COMMIT|ROLLBACK|END)\b",
                                                                 body, re.I):
            return MSG_SQLB_NO_COMMIT
        if self.engine_of(ctx.state) == "pg" and re.search(
                r"\bINSERT\s+INTO\s+ledger\s*\((?![^)]*\bid\b)[^)]*\)", body, re.I):
            return MSG_SQLB_LEDGER_ID.format(**ctx.state)
        return None


TASKS = [PsqlNav(), PsqlPipe(), PgDialect(), PgIdentity(), CaseWhen(), Subquery(), CteWith(),
         WindowRank(), WindowLag(), JoinsMore(), ConstraintsFk(), Upsert(), ViewIndex(),
         JsonbQuery(), CopyDump(), BossSql()]
