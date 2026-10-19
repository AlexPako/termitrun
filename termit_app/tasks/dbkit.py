"""Генераторы трека «Базы данных» (часть 9а, «Картотека»): учебная база records.db.

Правила (план части 9, «Генераторы»):
- данные — строки Python, детерминированные по rng; одинаковы во всех темах при заданном
  движке (state["_engine"], см. «Движок»). Имена и города — латиница, регистр в Картотеке чистый: LIKE,
  ORDER BY и DISTINCT одинаковы в SQLite (BINARY) и PostgreSQL (--locale=C);
- деньги — целые кредиты, без float; даты — ISO-текст «YYYY-MM-DD HH:MM:SS»: строковое
  сравнение совпадает с хронологическим;
- ловушки гарантирует сама постройка, а не удача зерна (tests/test_dbkit.py, 50 зёрен):
  тёзки, NULL и '' в почте, люди без счетов, значения ровно на концах BETWEEN, переводы
  последнего дня месяца после полуночи, лидер с запасом, средние без случая «.xx5»;
- ответ задачи — Python-предикат по этим строкам (like, sql_round, …), а не SQL: от версии
  sqlite3 в Python он не зависит.

Сборка базы — build_sqlite: во временной папке процесса (у родителя — системная, в песочнице
TMPDIR = box/.termit/tmp), одна транзакция, без now(); байты детерминированы — reset в
песочнице собирает ту же базу, что родитель (судья держит своё состояние и не перечитывает).
В песочницу база кладётся через put (sandbox.write_box_file: безопасная замена)."""
import contextvars
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

# --- Движок -------------------------------------------------------------------------------
# Движок задачи выбирает родитель до sandbox.create (choose_engine) и передаёт его ЯВНО:
# Task.make_state(…, engine=) кладёт его в state["_engine"] (открытая часть task.json —
# reset в песочнице берёт его оттуда же, sandbox.rebuild), а на время setup задачи он виден
# через engine_scope. Окружение процесса не трогается (долг A1 M4): engine_scope живёт в
# contextvars — у каждого потока свой (tests/refrun.pool гоняет задачи в потоках).
# ENGINE_ENV — только справка для zsh и скриптов эталонов, сборка данных её не читает.

ENGINE_ENV = "TERMIT_DB_ENGINE"
ENGINES = ("sqlite", "pg")
DEFAULT_ENGINE = "sqlite"
ENGINE_KEY = "_engine"

_ENGINE = contextvars.ContextVar("termit_db_engine", default=None)


def current_engine() -> str:
    """Движок этой сборки: значение engine_scope текущего потока, иначе SQLite."""
    value = _ENGINE.get()
    return value if value in ENGINES else DEFAULT_ENGINE


@contextmanager
def engine_scope(engine: str) -> Iterator[str]:
    """На время блока движок сборки данных = engine (только в этом потоке); после — как
    было (и при исключении). os.environ не меняется."""
    if engine not in ENGINES:
        raise ValueError(f"нет такого движка: {engine!r}")
    token = _ENGINE.set(engine)
    try:
        yield engine
    finally:
        _ENGINE.reset(token)


DB_TRACKS = ("db", "sql")
PG_GATE = "psql_pipe"          # общие задачи трека sql — на PostgreSQL после неё (там -At)


def choose_engine(task, p: Optional[dict] = None, pg_ok: Optional[bool] = None) -> Optional[str]:
    """Движок задачи — выбирает родитель до sandbox.create. Не задача БД — None (в state
    ничего не добавляется). Картотека (трек db) — всегда SQLite. Трек sql: задача стенда
    (stand = "pg") — PostgreSQL; общая и страж — PostgreSQL, если стенд годен И решена
    psql_pipe, иначе SQLite. pg_ok — годен ли стенд (None — спросить pgkit.usable)."""
    track = getattr(task, "track", "")
    if track not in DB_TRACKS:
        return None
    if track == "db":
        return DEFAULT_ENGINE
    if getattr(task, "stand", None) == "pg":
        return "pg"
    if pg_ok is None:
        from termit_app import pgkit
        pg_ok = pgkit.usable()
    rec = ((p or {}).get("tasks") or {}).get(PG_GATE) or {}
    solved = isinstance(rec, dict) and (rec.get("solved") or 0) > 0
    return "pg" if pg_ok and solved else DEFAULT_ENGINE


# --- Предикаты ответов: то, что делает SQL, но на Python ------------------------------------

def like(value, pattern: str) -> bool:
    """LIKE SQLite: % — любая строка, _ — один символ, латиница без учёта регистра (как
    в SQLite по умолчанию), NULL — не совпадает ни с чем."""
    if value is None:
        return False
    v, pat = str(value).casefold(), pattern.casefold()

    def match(i: int, j: int) -> bool:
        while j < len(pat):
            c = pat[j]
            if c == "%":
                return any(match(k, j + 1) for k in range(i, len(v) + 1))
            if i >= len(v) or (c != "_" and c != v[i]):
                return False
            i, j = i + 1, j + 1
        return i == len(v)
    return match(0, 0)


def sql_round(x, digits: int = 0):
    """ROUND(x, n) SQLite: половина — от нуля. Целое при n = 0 — как float, так и печатает
    sqlite3 (ROUND(2.5) = 3.0)."""
    q = Decimal(1).scaleb(-digits)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def avg(values: Sequence) -> Optional[float]:
    """AVG без NULL; пусто — None (как SQL)."""
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def between(value, lo, hi) -> bool:
    """BETWEEN: обе границы включены; NULL — нет."""
    return value is not None and lo <= value <= hi


def blank(value) -> bool:
    """Почты нет: NULL или пустая строка ('' — не NULL, но графа пуста)."""
    return value is None or value == ""


# --- Данные Картотеки -----------------------------------------------------------------------

FIRST = ("Anna", "Boris", "Vera", "Gleb", "Daria", "Egor", "Zoya", "Ilya", "Kira", "Lev",
         "Mila", "Oleg", "Pavel", "Rita", "Semen", "Tanya", "Uma", "Fedor", "Yana", "Igor",
         "Nina", "Roman", "Sonya", "Timur")
LAST = ("Volkov", "Orlov", "Sokolov", "Lebedev", "Kozlov", "Novikov", "Morozov", "Popov",
        "Zaitsev", "Belov", "Gusev", "Titov", "Kuznets", "Frolov", "Markov", "Bykov")
CITIES = ("moscow", "kazan", "tver", "omsk", "perm", "ufa", "samara", "sochi", "tula",
          "kursk", "orel", "vologda")
DOMAINS = ("mail.example", "post.example", "corp.example", "free.example")
PEOPLE_STATUSES = ("active", "inactive", "archived")
PEOPLE_STATUS_WEIGHTS = (75, 15, 10)
ACCOUNT_STATUSES = ("active", "frozen", "closed")
ACCOUNT_STATUS_WEIGHTS = (70, 12, 18)
ACCOUNT_NOTES = ("", "", "", "payroll", "savings", "joint", "old card", "vip")
TRANSFER_NOTES = ("", "", "", "rent", "gift", "loan", "salary", "fee", "refund")
TEST_NOTE, DECOY_NOTE = "test", "contest"       # tx_delete: = 'test' против LIKE '%test%'
ACTORS = ("clerk_a", "clerk_b", "clerk_c", "night_desk")

MONTH = "2026-09"                  # «переводы за месяц»
MONTH_LAST = "2026-09-30"          # последний день: BETWEEN '…-01' AND '…-30' его теряет
NEXT_MONTH = "2026-10-01"
TRANSFER_SPAN = ("2026-08-10", "2026-10-12")
AMOUNT_LO, AMOUNT_HI = 500, 1500   # концы BETWEEN по сумме: на каждом — строки ровно на нём
BORN_LO, BORN_HI = "1980-01-01", "1989-12-31"   # концы BETWEEN по дате рождения

# гарантии постройки (tests/test_dbkit.py проверяет каждую на 50 зёрнах)
MIN_NAMESAKES = 3        # пар одинаковых name в разных городах
MIN_NULL_EMAIL = 5
MIN_EMPTY_EMAIL = 3
MIN_NO_ACCOUNTS = 5      # людей без счетов
MIN_IDLE_ACCOUNTS = 3    # счетов без переводов
MIN_IDLE_CLOSED = 3      # закрытых счетов без переводов (и есть закрытые с переводами)
MIN_EDGE = 2             # строк ровно на концах BETWEEN (на обоих концах вместе)
MIN_LATE_LAST_DAY = 3    # переводов последнего дня месяца после 00:00
MIN_TEST_NOTES = 2       # переводов с заметкой ровно test (и столько же contest)
MIN_AUDIT_DUPS = 3       # пар строк журнала правок с тем же detail и ts
LEAD_MARGIN = 2          # запас лидера над вторым в «единственном» ответе
ROUND_GAP = 0.01         # |дробная часть ×100 − 0,5| больше этого у ROUND(AVG(…), 2)

COLUMNS: Dict[str, Tuple[str, ...]] = {
    "people": ("id", "name", "city", "born", "email", "phone", "status"),
    "accounts": ("id", "person_id", "opened", "balance", "status", "note"),
    "transfers": ("id", "from_acc", "to_acc", "amount", "ts", "note"),
    "badges": ("person_id", "code"),
    "audit_log": ("id", "ts", "actor", "action", "tbl", "row_id", "detail"),
}

# что пишет триггер журнала правок: какие графы людей он сторожит
AUDITED = ("name", "city", "email", "phone", "status")


def _audit_detail_sql() -> str:
    parts = [f"CASE WHEN OLD.{c} IS NOT NEW.{c} THEN '{c}:' || IFNULL(OLD.{c}, '') || '>' || "
             f"IFNULL(NEW.{c}, '') || ' ' ELSE '' END" for c in AUDITED]
    return "TRIM(" + " || ".join(parts) + ")"


SCHEMA: Tuple[str, ...] = (
    "CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL, "
    "born TEXT, email TEXT, phone TEXT, status TEXT NOT NULL)",
    "CREATE TABLE accounts (id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL REFERENCES "
    "people(id), opened TEXT NOT NULL, balance INTEGER NOT NULL, status TEXT NOT NULL, "
    "note TEXT NOT NULL DEFAULT '')",
    "CREATE TABLE transfers (id INTEGER PRIMARY KEY, from_acc INTEGER NOT NULL REFERENCES "
    "accounts(id), to_acc INTEGER NOT NULL REFERENCES accounts(id), amount INTEGER NOT NULL, "
    "ts TEXT NOT NULL, note TEXT NOT NULL DEFAULT '')",
    "CREATE TABLE badges (person_id INTEGER NOT NULL REFERENCES people(id), "
    "code TEXT NOT NULL UNIQUE)",
    "CREATE TABLE audit_log (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL, "
    "action TEXT NOT NULL, tbl TEXT NOT NULL, row_id INTEGER, detail TEXT NOT NULL)",
    # журнал правок: каждая правка людей — строка в audit_log (время — момента правки игрока)
    "CREATE TRIGGER people_audit AFTER UPDATE ON people BEGIN INSERT INTO audit_log "
    "(ts, actor, action, tbl, row_id, detail) VALUES (strftime('%Y-%m-%d %H:%M:%S', 'now'), "
    "'termit', 'update', 'people', OLD.id, " + _audit_detail_sql() + "); END",
)


@dataclass
class Records:
    """Учебная база Картотеки: строки таблиц (словари по COLUMNS) и метки ловушек."""
    tables: Dict[str, List[dict]]
    meta: dict = field(default_factory=dict)

    def rows(self) -> Dict[str, Tuple[Tuple[str, ...], List[tuple]]]:
        return {t: (COLUMNS[t], [tuple(r[c] for c in COLUMNS[t]) for r in rows])
                for t, rows in self.tables.items()}

    def sqlite(self) -> bytes:
        return build_sqlite(SCHEMA, self.rows())

    # помощники предикатов
    def person(self, pid: int) -> dict:
        return next(p for p in self.tables["people"] if p["id"] == pid)

    def accounts_of(self, pid: int) -> List[dict]:
        return [a for a in self.tables["accounts"] if a["person_id"] == pid]

    def city_of_account(self, acc: dict) -> str:
        return self.person(acc["person_id"])["city"]


def _phone(rng, used: set) -> str:
    while True:
        p = "+79" + "".join(str(rng.randrange(10)) for _ in range(9))
        if p not in used:
            used.add(p)
            return p


def _date(rng, lo: str, hi: str) -> str:
    """Дата ISO между lo и hi (включая) — по дням от lo."""
    from datetime import date, timedelta
    a, b = date.fromisoformat(lo), date.fromisoformat(hi)
    return (a + timedelta(days=rng.randrange((b - a).days + 1))).isoformat()


def _ts(rng, day: str, after_midnight: bool = False) -> str:
    h = rng.randrange(1 if after_midnight else 0, 24)
    return f"{day} {h:02d}:{rng.randrange(60):02d}:{rng.randrange(60):02d}"


def _people(rng, n: int) -> List[dict]:
    cities = list(rng.sample(CITIES, rng.randint(8, len(CITIES))))
    used_names, used_phones, out = set(), set(), []
    # тёзки: одно имя — в двух разных городах (не меньше MIN_NAMESAKES пар)
    pairs = []
    while len(pairs) < MIN_NAMESAKES + rng.randint(0, 1):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name not in used_names:
            used_names.add(name)
            pairs.append((name, rng.sample(cities, 2)))
    plan = [(name, c) for name, cs in pairs for c in cs]
    while len(plan) < n:
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name not in used_names:
            used_names.add(name)
            plan.append((name, rng.choice(cities)))
    rng.shuffle(plan)
    for i, (name, city) in enumerate(plan, start=1):
        first, last = name.lower().split()
        email = f"{first}.{last}{rng.randrange(10, 99)}@{rng.choice(DOMAINS)}"
        out.append({"id": i, "name": name, "city": city, "born": _date(rng, "1955-01-01",
                                                                         "2006-12-31"),
                    "email": email, "phone": _phone(rng, used_phones),
                    "status": rng.choices(PEOPLE_STATUSES, PEOPLE_STATUS_WEIGHTS)[0]})
    # почты нет: NULL и пустая строка — у не-тёзок (цель задач среди тёзок)
    namesakes = {name for name, _ in pairs}
    plain = [p for p in out if p["name"] not in namesakes]
    picked = rng.sample(plain, MIN_NULL_EMAIL + MIN_EMPTY_EMAIL + rng.randint(0, 3))
    for k, p in enumerate(picked):            # выборка случайна: первые — пустые строки
        p["email"] = "" if k < MIN_EMPTY_EMAIL else None
    # концы BETWEEN по дате рождения: по человеку ровно на каждом конце
    edge = rng.sample(plain, 2)
    edge[0]["born"], edge[1]["born"] = BORN_LO, BORN_HI
    return out


def _accounts(rng, people: List[dict]) -> List[dict]:
    no_acc = set(p["id"] for p in rng.sample(people, MIN_NO_ACCOUNTS + rng.randint(0, 3)))
    out, aid = [], rng.randint(100, 400)
    for p in people:
        if p["id"] in no_acc:
            continue
        for _ in range(rng.choices((1, 2, 3, 4), (45, 30, 17, 8))[0]):
            out.append({"id": aid, "person_id": p["id"],
                        "opened": _date(rng, "2015-01-01", "2026-08-31"),
                        "balance": rng.randrange(0, 90000),
                        "status": rng.choices(ACCOUNT_STATUSES, ACCOUNT_STATUS_WEIGHTS)[0],
                        "note": rng.choice(ACCOUNT_NOTES)})
            aid += rng.choice((1, 1, 2, 3))
    return out


def _transfers(rng, accounts: List[dict], n: int) -> List[dict]:
    ids = [a["id"] for a in accounts]
    out = []
    for i in range(1, n + 1):
        a, b = rng.sample(ids, 2)
        day = _date(rng, *TRANSFER_SPAN)
        out.append({"id": i, "from_acc": a, "to_acc": b, "amount": rng.randrange(10, 20000),
                    "ts": _ts(rng, day), "note": rng.choice(TRANSFER_NOTES)})
    return out


def _audit(rng, people: List[dict]) -> List[dict]:
    out, base = [], []
    for _ in range(rng.randint(18, 26)):
        p = rng.choice(people)
        col = rng.choice(("status", "phone", "city"))
        day = _date(rng, "2025-01-01", "2026-08-31")
        ts, actor = _ts(rng, day), rng.choice(ACTORS)
        # было > стало — словами, как пишет триггер (аудит новичка A7); два числа из rng — как
        # и раньше, чтобы остальные данные зерна не сдвинулись
        was, now = _audit_values(col, rng.randrange(1000), rng.randrange(1000))
        base.append({"ts": ts, "actor": actor, "action": "update", "tbl": "people",
                     "row_id": p["id"], "detail": f"{col}:{was}>{now}"})
    # дубли: та же правка записана дважды (тот же detail и ts), у копии id больше
    for e in rng.sample(base, MIN_AUDIT_DUPS + rng.randint(0, 2)):
        base.append(dict(e))
    base.sort(key=lambda e: (e["ts"], e["detail"]))
    for i, e in enumerate(base, start=1):
        out.append(dict(e, id=i))
    return out


def _audit_values(col: str, a: int, b: int) -> Tuple[str, str]:
    """Старое и новое значение графы для журнала правок по двум числам 0–999: статус и город
    — из своих списков, телефон — +79 и девять цифр; старое и новое всегда разные."""
    if col == "status":
        pool = PEOPLE_STATUSES
    elif col == "city":
        pool = CITIES
    else:
        was = f"+79{a:03d}{b:03d}{(a * 7 + b) % 1000:03d}"
        now = f"+79{b:03d}{a:03d}{(a + b * 3) % 1000:03d}"
        if now == was:
            now = now[:-1] + str((int(now[-1]) + 1) % 10)
        return was, now
    i = a % len(pool)
    return pool[i], pool[(i + 1 + b % (len(pool) - 1)) % len(pool)]


def _distinct_top(values: List[int], k: int, gap: int) -> bool:
    top = sorted(values, reverse=True)[:k + 1]
    return all(top[i] - top[i + 1] >= gap for i in range(min(k, len(top) - 1)))


def _ensure_traps(rng, recs: Records) -> None:
    """Довести данные до гарантий, не трогая уже выставленных меток."""
    people, accounts, transfers = (recs.tables[t] for t in ("people", "accounts", "transfers"))
    acc_ids = [a["id"] for a in accounts]
    # концы BETWEEN по сумме, последний день месяца после полуночи, test/contest
    special = rng.sample(transfers, 2 + MIN_LATE_LAST_DAY + 2 * MIN_TEST_NOTES + 2)
    special[0]["amount"], special[1]["amount"] = AMOUNT_LO, AMOUNT_HI
    for t in special[2:2 + MIN_LATE_LAST_DAY]:
        t["ts"] = _ts(rng, MONTH_LAST, after_midnight=True)
    rest = special[2 + MIN_LATE_LAST_DAY:]
    for t in rest[:MIN_TEST_NOTES]:
        t["note"] = TEST_NOTE
    for t in rest[MIN_TEST_NOTES:2 * MIN_TEST_NOTES]:
        t["note"] = DECOY_NOTE
    for t in rest[2 * MIN_TEST_NOTES:]:          # начало следующего месяца — тоже рядом
        t["ts"] = f"{NEXT_MONTH} 00:00:00" if t is rest[-1] else _ts(rng, NEXT_MONTH)
    # счета без переводов: часть закрытых и пара прочих
    used = {t["from_acc"] for t in transfers} | {t["to_acc"] for t in transfers}
    closed = [a for a in accounts if a["status"] == "closed"]
    while len(closed) < 2 * MIN_IDLE_CLOSED + 2:
        a = rng.choice([x for x in accounts if x["status"] != "closed"])
        a["status"] = "closed"
        closed.append(a)
    idle_closed = {a["id"] for a in rng.sample(closed, MIN_IDLE_CLOSED)}
    other = [a for a in accounts if a["status"] != "closed"]
    idle = idle_closed | {a["id"] for a in rng.sample(other, 2)}
    busy = [i for i in acc_ids if i not in idle]
    for t in transfers:
        if t["from_acc"] in idle or t["to_acc"] in idle:
            t["from_acc"], t["to_acc"] = rng.sample(busy, 2)
    used = {t["from_acc"] for t in transfers} | {t["to_acc"] for t in transfers}
    for a in closed:                              # закрытые с переводами — тоже есть
        if a["id"] not in idle and a["id"] not in used:
            t = rng.choice([x for x in transfers if x["from_acc"] != a["id"]])
            t["to_acc"] = a["id"]
            used.add(a["id"])
    # лидер по числу счетов среди городов — с запасом LEAD_MARGIN
    by_city = Counter(recs.city_of_account(a) for a in accounts)
    lead_city = max(sorted(by_city), key=lambda c: by_city[c])
    with_acc = {a["person_id"] for a in accounts}
    hosts = [p for p in people if p["city"] == lead_city and p["id"] in with_acc]
    while True:
        rest_max = max((v for c, v in by_city.items() if c != lead_city), default=0)
        if by_city[lead_city] - rest_max >= LEAD_MARGIN:
            break
        p = rng.choice(hosts)
        nid = max(a["id"] for a in accounts) + rng.choice((1, 2))
        accounts.append({"id": nid, "person_id": p["id"], "opened": _date(rng, "2015-01-01",
                                                                         "2026-08-31"),
                         "balance": rng.randrange(0, 90000), "status": "active", "note": ""})
        by_city[lead_city] += 1
        # новый счёт без переводов портит MIN_IDLE только в плюс — гарантии целы
    # балансы: четыре верхних — разные с запасом; самый свежий открытый — один
    top = sorted(accounts, key=lambda a: -a["balance"])[:4]
    # накопительно (fix1 I2): каждый следующий ниже предыдущего на свой шаг ≥ LEAD_MARGIN + 5;
    # четвёртый всё равно выше 90000 — выше любого случайного баланса
    bal = 95000 + rng.randrange(0, 4000)
    for a in top:
        a["balance"] = bal
        bal -= rng.randint(LEAD_MARGIN + 5, 900)
    newest = max(a["opened"] for a in accounts)
    for a in [a for a in accounts if a["opened"] == newest][1:]:
        a["opened"] = _date(rng, "2015-01-01", "2026-01-31")
    # суммы переводов: три самых мелких и самый крупный — без ничьих (метки ловушек целы)
    marked = {id(t) for t in special}
    plain = [t for t in transfers if id(t) not in marked]
    for k, t in enumerate(sorted(plain, key=lambda t: t["amount"])[:4]):
        t["amount"] = 1 + k * 2
    big = max(plain, key=lambda t: t["amount"])
    big["amount"] = max(t["amount"] for t in transfers if t is not big) + LEAD_MARGIN + \
        rng.randrange(50, 500)
    # ROUND(AVG(balance), 2) по городу — без случая «.xx5»
    for _ in range(200):
        bad = [c for c in by_city if round_risk(avg([a["balance"] for a in accounts
                                                      if recs.city_of_account(a) == c]))]
        if not bad:
            break
        for c in bad:
            low = min((a for a in accounts if recs.city_of_account(a) == c
                       and a not in top), key=lambda a: a["balance"])
            low["balance"] += 1
    recs.meta.update(lead_city=lead_city, idle_closed=sorted(idle_closed),
                     amount_edges=(AMOUNT_LO, AMOUNT_HI), born_edges=(BORN_LO, BORN_HI))


def round_risk(x: Optional[float]) -> bool:
    """ROUND(x, 2) рядом с «.xx5»: дробная часть ×100 ближе ROUND_GAP к половине."""
    if x is None:
        return False
    frac = (x * 100) % 1
    return abs(frac - 0.5) <= ROUND_GAP


def records(rng, *, people: int = 110, transfers: int = 360) -> Records:
    """Учебная база Картотеки по зерну: люди, счета, переводы, пропуска, журнал правок.
    Все гарантии ловушек (см. MIN_*) выполняются при любом rng."""
    ppl = _people(rng, people)
    accs = _accounts(rng, ppl)
    trs = _transfers(rng, accs, transfers)
    recs = Records({"people": ppl, "accounts": accs, "transfers": trs, "badges": [],
                    "audit_log": _audit(rng, ppl)})
    _ensure_traps(rng, recs)
    used = set()
    for p in rng.sample(ppl, len(ppl) * 3 // 4) + [p for p in ppl if namesake(recs, p)]:
        if p["id"] in used:
            continue
        used.add(p["id"])
        code = f"B-{rng.randrange(10000, 99999)}"
        while any(b["code"] == code for b in recs.tables["badges"]):
            code = f"B-{rng.randrange(10000, 99999)}"
        recs.tables["badges"].append({"person_id": p["id"], "code": code})
    recs.tables["badges"].sort(key=lambda b: b["person_id"])
    recs.tables["accounts"].sort(key=lambda a: a["id"])
    return recs


def having_threshold(rng, counts: Counter) -> int:
    """Порог HAVING «больше n» из самих данных (fix1 M3): n — размер какой-то группы, и есть
    группа больше n. Значит, «>» и «>=» дают разный ответ, и ответ не пустой. Гарантия
    генератора не нужна: при двух и более разных размерах групп такой n есть всегда (лидер
    городов с запасом LEAD_MARGIN это обеспечивает)."""
    sizes = sorted(set(counts.values()))
    if len(sizes) < 2:
        raise ValueError("все группы одного размера — порога с краем нет")
    return rng.choice(sizes[:-1])


def add_account(rng, recs: Records, pid: int, balance: int, status: str = "active") -> dict:
    """Ещё один счёт человеку (задачи A3 доводят данные своего варианта): id — после
    последнего, открыт до 2026-02 (самый свежий счёт остаётся одним)."""
    accs = recs.tables["accounts"]
    acc = {"id": max(a["id"] for a in accs) + rng.choice((1, 2)), "person_id": pid,
           "opened": _date(rng, "2015-01-01", "2026-01-31"), "balance": balance,
           "status": status, "note": ""}
    accs.append(acc)
    return acc


def namesake(recs: Records, person: dict) -> bool:
    """У человека есть тёзка (то же name) в другом городе."""
    return any(p["name"] == person["name"] and p["id"] != person["id"]
               for p in recs.tables["people"])


def namesakes(recs: Records) -> List[Tuple[dict, dict]]:
    """Пары тёзок (по возрастанию id первого)."""
    by: Dict[str, List[dict]] = {}
    for p in recs.tables["people"]:
        by.setdefault(p["name"], []).append(p)
    return [(g[0], g[1]) for g in by.values() if len(g) > 1]


# --- Каталог таблиц для первой базы (sqlite_open) ------------------------------------------

EXTRA_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "districts": ("id", "title", "chief", "phones"),
    "offices": ("id", "district_id", "address", "opened"),
    "forms": ("code", "caption", "pages"),
}
EXTRA_SCHEMA: Dict[str, str] = {
    "districts": "CREATE TABLE districts (id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
                 "chief TEXT, phones INTEGER)",
    "offices": "CREATE TABLE offices (id INTEGER PRIMARY KEY, district_id INTEGER REFERENCES "
               "districts(id), address TEXT NOT NULL, opened TEXT)",
    "forms": "CREATE TABLE forms (code TEXT PRIMARY KEY, caption TEXT NOT NULL, pages INTEGER)",
}
STREETS = ("lenina", "sadovaya", "mira", "polevaya", "lesnaya", "shkolnaya", "rechnaya")


def table_columns(table: str) -> Tuple[str, ...]:
    return COLUMNS.get(table) or EXTRA_COLUMNS[table]


def catalog(rng) -> Tuple[bytes, List[str]]:
    """Первая база: 4–6 таблиц из пула (пять таблиц Картотеки и три справочника), строк по
    нескольку. (байты, имена таблиц в порядке .tables — по алфавиту)."""
    recs = records(rng, people=40, transfers=60)
    pool = sorted(list(COLUMNS) + list(EXTRA_COLUMNS))
    names = sorted(rng.sample(pool, rng.randint(4, 6)))
    schema, rows = [], {}
    for t in names:
        if t == "offices" and "districts" not in names:
            # ссылки на справочник, которого в этой базе нет, не показываем (аудит A7)
            schema.append(EXTRA_SCHEMA[t].replace(" REFERENCES districts(id)", ""))
            rows[t] = (EXTRA_COLUMNS[t], _extra_rows(rng, t))
        elif t in COLUMNS:
            schema.append(next(d for d in SCHEMA if d.startswith(f"CREATE TABLE {t} ")))
            rows[t] = (COLUMNS[t], [tuple(r[c] for c in COLUMNS[t]) for r in recs.tables[t]])
        else:
            schema.append(EXTRA_SCHEMA[t])
            rows[t] = (EXTRA_COLUMNS[t], _extra_rows(rng, t))
    if "people" in names and "audit_log" in names:
        schema.append(SCHEMA[-1])           # триггер журнала правок — только при обеих
    return build_sqlite(schema, rows), names


def _extra_rows(rng, table: str) -> List[tuple]:
    n = rng.randint(4, 9)
    if table == "districts":
        return [(i, f"district_{i}", rng.choice(LAST), rng.randint(2, 40))
                for i in range(1, n + 1)]
    if table == "offices":
        return [(i, rng.randint(1, 9), f"{rng.choice(STREETS)} {rng.randint(1, 90)}",
                 _date(rng, "2001-01-01", "2026-01-01")) for i in range(1, n + 1)]
    return [(f"F-{k}", f"form {k}", rng.randint(1, 12))
            for k in rng.sample(range(10, 99), n)]


# --- CSV для импорта ------------------------------------------------------------------------

def csv_text(cols: Sequence[str], rows: Sequence[dict], header: bool = True) -> str:
    """CSV без кавычек и без запятых в полях; NULL — пустое поле; в конце — \\n."""
    lines = [",".join(cols)] if header else []
    for r in rows:
        cells = ["" if r[c] is None else str(r[c]) for c in cols]
        if any("," in c or '"' in c or "\n" in c for c in cells):
            raise ValueError(f"поле с запятой или кавычкой: {cells}")
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def extra_people(rng, recs: Records, n: int, dups: int = 2) -> List[dict]:
    """Новые люди для импорта: id после последнего, dups строк повторены (дубли выгрузки)."""
    start = max(p["id"] for p in recs.tables["people"]) + 1
    used = {p["phone"] for p in recs.tables["people"]}
    out = []
    for i in range(n):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        out.append({"id": start + i, "name": f"{first} {last}", "city": rng.choice(CITIES),
                    "born": _date(rng, "1955-01-01", "2006-12-31"),
                    "email": f"{first.lower()}.{last.lower()}{rng.randrange(10, 99)}@"
                             f"{rng.choice(DOMAINS)}",
                    "phone": _phone(rng, used), "status": "active"})
    for r in rng.sample(out, min(dups, len(out))):
        out.insert(rng.randrange(len(out) + 1), dict(r))
    return out


# --- Сборка SQLite --------------------------------------------------------------------------

def build_sqlite(schema: Sequence[str], rows: Dict[str, Tuple[Sequence[str], List[tuple]]]) \
        -> bytes:
    """Байты файла базы: CREATE TABLE, строки, затем триггеры и индексы — одной транзакцией,
    journal_mode=DELETE, page_size=4096. Во временной папке процесса, убирается всегда."""
    tmp = tempfile.mkdtemp(prefix="termit-dbkit-")
    try:
        path = os.path.join(tmp, "build.db")
        con = sqlite3.connect(path, isolation_level=None)
        try:
            con.execute("PRAGMA page_size=4096")
            con.execute("PRAGMA journal_mode=DELETE")
            con.execute("BEGIN")
            tables = [s for s in schema if s.lstrip().upper().startswith("CREATE TABLE")]
            for ddl in tables:
                con.execute(ddl)
            for table, (cols, data) in rows.items():
                marks = ", ".join("?" for _ in cols)
                con.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({marks})",
                                data)
            for ddl in schema:
                if ddl not in tables:
                    con.execute(ddl)
            con.execute("COMMIT")
        finally:
            con.close()
        with open(path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def put(box, rel: str, data: bytes) -> None:
    """Положить базу в песочницу безопасной заменой (без перехода по ссылкам)."""
    from termit_app import sandbox
    sandbox.write_box_file(box, rel, data, mode=0o644)


# --- Хранилище (часть 9б): учебная база vault для PostgreSQL и SQLite ------------------------
# Одни и те же строки Python — в оба движка: SQLite-файл vault.db (build_sqlite) или сид
# PostgreSQL (pg_seed, держит только родитель). Время — ISO-текст «YYYY-MM-DD HH:MM:SS»: так
# его печатают и sqlite3, и psql (timestamp без долей секунды). JSON событий — в той записи,
# в какой его печатает jsonb (ключи по длине, затем по алфавиту; «, » и «: »), поэтому
# вывод payload целиком одинаков в обоих движках. Гарантии ловушек здесь — базовые (регистр
# районов, NULL и '' в почте, клиенты без счетов, платежи без счёта); остальные (порог CASE,
# ничьи окон, пересечение UNION) добавят задачи B2–B4 вместе с проверками на 50 зёрнах.

VAULT_DB = "vault.db"
DISTRICTS = ("kazan", "tver", "omsk", "perm", "ufa", "samara", "sochi", "tula")
DIRTY_DISTRICT = ("Kazan", "kazan", "KAZAN")     # pg_dialect: LIKE различает регистр
MIN_DIRTY_EACH = 2           # клиентов на каждую форму «грязного» района
MIN_ORPHAN_PAYMENTS = 3      # платежей без счёта (invoice_id NULL) — для FULL JOIN
MIN_NO_INVOICES = 3          # клиентов без единого счёта
INVOICE_STATUSES = ("open", "paid", "overdue")
INVOICE_WEIGHTS = (35, 45, 20)
LEDGER_KINDS = ("charge", "payment", "write_off")
DEPTS = ("risk", "audit", "ops", "sales")
EVENT_TYPES = ("login", "transfer", "alert", "export")
EVENT_TAGS = ("x", "vip", "night", "manual", "api")
VAULT_SPAN = ("2026-06-01", "2026-09-30")
ACTORS_VAULT = ("teller_a", "teller_b", "night_desk", "audit_bot")

VAULT_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "customers": ("id", "name", "district", "email", "created_at"),
    "invoices": ("id", "customer_id", "amount", "issued_at", "status"),
    "payments": ("id", "invoice_id", "paid_at", "amount"),
    "employees": ("id", "name", "dept", "manager_id"),
    "rates": ("code", "rate", "note"),
    "events": ("id", "ts", "payload"),
    "ledger": ("id", "customer_id", "amount", "kind"),
    "audit_log": ("id", "ts", "actor", "action", "tbl", "row_id", "detail"),
    "ops.duty": ("id", "name", "district"),          # только PostgreSQL: схема ops
}
PG_ONLY = ("ops.duty",)

_KINDS = "'" + "', '".join(LEDGER_KINDS) + "'"
VAULT_SCHEMA_SQLITE: Tuple[str, ...] = (
    "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, district TEXT NOT "
    "NULL, email TEXT, created_at TEXT NOT NULL)",
    "CREATE TABLE invoices (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES "
    "customers(id), amount INTEGER NOT NULL, issued_at TEXT NOT NULL, status TEXT NOT NULL)",
    "CREATE TABLE payments (id INTEGER PRIMARY KEY, invoice_id INTEGER REFERENCES "
    "invoices(id), paid_at TEXT NOT NULL, amount INTEGER NOT NULL)",
    "CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT NOT NULL, dept TEXT NOT NULL, "
    "manager_id INTEGER REFERENCES employees(id))",
    "CREATE TABLE rates (code TEXT NOT NULL UNIQUE, rate INTEGER NOT NULL, note TEXT NOT NULL "
    "DEFAULT '')",
    "CREATE TABLE events (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, payload TEXT NOT NULL)",
    "CREATE TABLE ledger (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES "
    f"customers(id), amount INTEGER NOT NULL, kind TEXT NOT NULL CHECK (kind IN ({_KINDS})))",
    "CREATE TABLE audit_log (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL, "
    "action TEXT NOT NULL, tbl TEXT NOT NULL, row_id INTEGER, detail TEXT NOT NULL)",
    "CREATE TRIGGER invoices_audit AFTER UPDATE ON invoices BEGIN INSERT INTO audit_log (ts, "
    "actor, action, tbl, row_id, detail) VALUES (strftime('%Y-%m-%d %H:%M:%S', 'now'), "
    "'termit', 'update', 'invoices', OLD.id, 'status:' || OLD.status || '>' || NEW.status); END",
    "CREATE TRIGGER ledger_audit AFTER INSERT ON ledger BEGIN INSERT INTO audit_log (ts, actor, "
    "action, tbl, row_id, detail) VALUES (strftime('%Y-%m-%d %H:%M:%S', 'now'), 'termit', "
    "'insert', 'ledger', NEW.id, 'amount:' || NEW.amount); END",
)
VAULT_SCHEMA_PG: Tuple[str, ...] = (
    "CREATE TABLE customers (id integer PRIMARY KEY, name text NOT NULL, district text NOT "
    "NULL, email text, created_at timestamp NOT NULL)",
    "CREATE TABLE invoices (id integer PRIMARY KEY, customer_id integer NOT NULL REFERENCES "
    "customers(id), amount integer NOT NULL, issued_at timestamp NOT NULL, status text NOT NULL)",
    "CREATE TABLE payments (id integer PRIMARY KEY, invoice_id integer REFERENCES "
    "invoices(id), paid_at timestamp NOT NULL, amount integer NOT NULL)",
    "CREATE TABLE employees (id integer PRIMARY KEY, name text NOT NULL, dept text NOT NULL, "
    "manager_id integer REFERENCES employees(id))",
    "CREATE TABLE rates (code text NOT NULL UNIQUE, rate integer NOT NULL, note text NOT NULL "
    "DEFAULT '')",
    "CREATE TABLE events (id integer PRIMARY KEY, ts timestamp NOT NULL, payload jsonb NOT NULL)",
    "CREATE TABLE ledger (id integer PRIMARY KEY, customer_id integer NOT NULL REFERENCES "
    f"customers(id), amount integer NOT NULL, kind text NOT NULL CHECK (kind IN ({_KINDS})))",
    "CREATE TABLE audit_log (id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, ts "
    "timestamp NOT NULL, actor text NOT NULL, action text NOT NULL, tbl text NOT NULL, row_id "
    "integer, detail text NOT NULL)",
    "CREATE TABLE ops.duty (id integer PRIMARY KEY, name text NOT NULL, district text NOT NULL)",
    # имена в функциях правил — со схемой (финал I1): search_path роли или базы не подменит
    # журнал своей audit_log в другой схеме
    "CREATE FUNCTION invoices_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO "
    "public.audit_log (ts, actor, action, tbl, row_id, detail) VALUES "
    "(pg_catalog.date_trunc('second', localtimestamp), 'termit', 'update', 'invoices', OLD.id, "
    "'status:' || OLD.status || '>' || NEW.status); RETURN NEW; END $$",
    "CREATE TRIGGER invoices_audit AFTER UPDATE ON invoices FOR EACH ROW EXECUTE FUNCTION "
    "invoices_audit()",
    "CREATE FUNCTION ledger_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO "
    "public.audit_log (ts, actor, action, tbl, row_id, detail) VALUES "
    "(pg_catalog.date_trunc('second', localtimestamp), 'termit', 'insert', 'ledger', NEW.id, "
    "'amount:' || NEW.amount); RETURN NEW; END $$",
    "CREATE TRIGGER ledger_audit AFTER INSERT ON ledger FOR EACH ROW EXECUTE FUNCTION "
    "ledger_audit()",
)
# графы с IDENTITY: после COPY с явными id счётчик — на максимум (иначе INSERT без id упадёт)
PG_IDENTITY = (("audit_log", "id"),)


def jsonb_text(obj) -> str:
    """JSON так, как его печатает jsonb: ключи по длине, затем по байтам; «, » и «: »."""
    import json
    if isinstance(obj, dict):
        items = sorted(obj.items(), key=lambda kv: (len(kv[0].encode()), kv[0].encode()))
        return "{" + ", ".join(json.dumps(k, ensure_ascii=False) + ": " + jsonb_text(v)
                               for k, v in items) + "}"
    if isinstance(obj, list):
        return "[" + ", ".join(jsonb_text(v) for v in obj) + "]"
    return json.dumps(obj, ensure_ascii=False)


@dataclass
class Extra:
    """Своя таблица задачи сверх общей схемы vault (B2: psql_nav — разное число таблиц):
    графы и CREATE TABLE для каждого движка; строки — в Vault.tables под тем же именем."""
    cols: Tuple[str, ...]
    sqlite: str
    pg: str


@dataclass
class Vault:
    """Учебная база Хранилища: строки таблиц (словари по VAULT_COLUMNS и Extra.cols) и метки
    ловушек; extra — таблицы задачи сверх общей схемы."""
    tables: Dict[str, List[dict]]
    meta: dict = field(default_factory=dict)
    extra: Dict[str, Extra] = field(default_factory=dict)
    # лишние пустые базы сервера (только PostgreSQL; ревью B2, M3 — psql_nav: число баз в \l
    # от зерна): их заводит суперпользователь до сида, в SQLite их нет
    databases: List[str] = field(default_factory=list)

    def columns(self, table: str) -> Tuple[str, ...]:
        return self.extra[table].cols if table in self.extra else VAULT_COLUMNS[table]

    def rows(self, engine: str = "sqlite") -> Dict[str, Tuple[Tuple[str, ...], List[tuple]]]:
        return {t: (self.columns(t), [tuple(r[c] for c in self.columns(t)) for r in rows])
                for t, rows in self.tables.items()
                if engine == "pg" or (t not in PG_ONLY and not t.startswith("ops."))}

    def sqlite(self) -> bytes:
        # таблицы схемы ops (B4: ops.intake у copy_dump) — только PostgreSQL
        schema = VAULT_SCHEMA_SQLITE + tuple(e.sqlite for k, e in self.extra.items()
                                             if not k.startswith("ops."))
        return build_sqlite(schema, self.rows("sqlite"))

    def pg_seed(self) -> str:
        schema = VAULT_SCHEMA_PG + tuple(e.pg for e in self.extra.values())
        return pg_seed(schema, self.rows("pg"), identity=PG_IDENTITY, databases=self.databases)


def _vault_ts(rng, lo: str = VAULT_SPAN[0], hi: str = VAULT_SPAN[1]) -> str:
    return _ts(rng, _date(rng, lo, hi))


def vault(rng, *, customers: int = 60, invoices: int = 200, payments: int = 180) -> Vault:
    """Учебная база Хранилища по зерну. Гарантии (MIN_*) выполняются при любом rng."""
    used_names, cust = set(), []
    plan = [DIRTY_DISTRICT[k % 3] for k in range(3 * MIN_DIRTY_EACH)]
    while len(plan) < customers:
        plan.append(rng.choice(DISTRICTS))
    rng.shuffle(plan)
    for i, district in enumerate(plan, start=1):
        while True:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if name not in used_names:
                used_names.add(name)
                break
        first, last = name.lower().split()
        cust.append({"id": i, "name": name, "district": district,
                     "email": f"{first}.{last}@{rng.choice(DOMAINS)}",
                     "created_at": _ts(rng, _date(rng, "2024-01-01", "2026-05-31"))})
    for k, c in enumerate(rng.sample(cust, MIN_NULL_EMAIL + MIN_EMPTY_EMAIL)):
        c["email"] = "" if k < MIN_EMPTY_EMAIL else None
    idle = {c["id"] for c in rng.sample(cust, MIN_NO_INVOICES + rng.randint(0, 2))}
    payers = [c["id"] for c in cust if c["id"] not in idle]
    inv = []
    for i in range(1, invoices + 1):
        inv.append({"id": 1000 + i, "customer_id": rng.choice(payers),
                    "amount": rng.randrange(100, 9000), "issued_at": _vault_ts(rng),
                    "status": rng.choices(INVOICE_STATUSES, INVOICE_WEIGHTS)[0]})
    paid = [x for x in inv if x["status"] != "open"]
    pay = []
    for i in range(1, payments + 1):
        x = rng.choice(paid)
        pay.append({"id": 5000 + i, "invoice_id": x["id"], "paid_at": _vault_ts(rng),
                    "amount": max(1, x["amount"] - rng.choice((0, 0, 0, rng.randrange(1, 90))))})
    for p in rng.sample(pay, MIN_ORPHAN_PAYMENTS + rng.randint(0, 2)):
        p["invoice_id"] = None
    emp = []
    for i in range(1, 21):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        emp.append({"id": i, "name": name, "dept": DEPTS[(i - 1) % len(DEPTS)] if i <= 4
                    else rng.choice(DEPTS), "manager_id": None if i <= 4 else
                    rng.choice([e["id"] for e in emp[:max(4, i // 2)]])})
    rates = [{"code": code, "rate": rng.randrange(50, 2500),
              "note": rng.choice(("", "", "base", "promo", "legacy"))}
             for code in sorted(rng.sample(("USD", "EUR", "CNY", "GBP", "JPY", "TRY", "KZT",
                                            "INR", "AED", "CHF"), 8))]
    events = []
    for i in range(1, 81):
        payload = {"type": rng.choice(EVENT_TYPES), "who": rng.choice(payers),
                   "tags": sorted(rng.sample(EVENT_TAGS, rng.randint(0, 3)))}
        events.append({"id": i, "ts": _vault_ts(rng), "payload": jsonb_text(payload)})
    ledger = []
    for i in range(1, 101):
        kind = rng.choices(LEDGER_KINDS, (60, 35, 5))[0]
        amt = rng.randrange(100, 5000)
        ledger.append({"id": i, "customer_id": rng.choice(payers),
                       "amount": -amt if kind != "charge" else amt, "kind": kind})
    audit = []
    for i in range(1, rng.randint(15, 22)):
        x = rng.choice(inv)
        was, now = rng.sample(INVOICE_STATUSES, 2)
        audit.append({"id": i, "ts": _ts(rng, _date(rng, "2026-01-01", "2026-05-31")),
                      "actor": rng.choice(ACTORS_VAULT), "action": "update", "tbl": "invoices",
                      "row_id": x["id"], "detail": f"status:{was}>{now}"})
    audit.sort(key=lambda e: (e["ts"], e["id"]))
    for i, e in enumerate(audit, start=1):
        e["id"] = i
    duty = [{"id": i, "name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
             "district": rng.choice(DISTRICTS)} for i in range(1, rng.randint(5, 9))]
    return Vault({"customers": cust, "invoices": inv, "payments": pay, "employees": emp,
                  "rates": rates, "events": events, "ledger": ledger, "audit_log": audit,
                  "ops.duty": duty}, meta={"idle": sorted(idle)})


def engine_fields(engine: str) -> Dict[str, str]:
    """Поля текстов общих задач Хранилища ({db}, {run}, {month}): после format эталон
    исполним как есть (D005). {month} — месяц платежа текстом «YYYY-MM»: так он одинаков в
    обоих движках (to_char в PostgreSQL, strftime в SQLite)."""
    if engine == "pg":
        return {"db": "базе vault", "run": "psql -At -c",
                "month": "to_char(paid_at, 'YYYY-MM')"}
    return {"db": f"файле {VAULT_DB}", "run": f"sqlite3 {VAULT_DB}",
            "month": "strftime('%Y-%m', paid_at)"}


# --- Сид PostgreSQL -----------------------------------------------------------------------------

def copy_escape(value) -> str:
    """Значение для текстового COPY FROM stdin: NULL — \\N, обратная косая, табуляция,
    переводы строк — экранами."""
    if value is None:
        return "\\N"
    if isinstance(value, bool):
        return "t" if value else "f"
    s = str(value)
    return (s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
            .replace("\r", "\\r"))


# граница сида: выше — команды суперпользователя (CREATE DATABASE вне транзакции), ниже —
# от runner (pgkit._load_seed ставит SET ROLE на её место)
SEED_AS_RUNNER = "-- termit: as runner"
_DB_NAME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")


def pg_seed(schema: Sequence[str], rows: Dict[str, Tuple[Sequence[str], List[tuple]]],
            identity: Sequence[Tuple[str, str]] = (), databases: Sequence[str] = ()) -> str:
    """Текст сида: CREATE TABLE, затем строки (COPY … FROM stdin), затем остальное (функции,
    триггеры, индексы) — одной транзакцией. Держит только родитель (pgkit.PgService);
    psql исполняет его под профилем-читателем от имени runner (SET ROLE — в pgkit). databases
    — лишние пустые базы: их до сида заводит суперпользователь (выше SEED_AS_RUNNER)."""
    tables = [s for s in schema if s.lstrip().upper().startswith("CREATE TABLE")]
    out = []
    for name in databases:
        if not _DB_NAME.match(name):
            raise ValueError(f"имя базы: {name!r}")
        out.append(f"CREATE DATABASE {name};")
    out += [SEED_AS_RUNNER, "BEGIN;"]
    out += [ddl + ";" for ddl in tables]
    for table, (cols, data) in rows.items():
        out.append(f"COPY {table} ({', '.join(cols)}) FROM stdin;")
        out += ["\t".join(copy_escape(v) for v in row) for row in data]
        out.append("\\.")
    for table, col in identity:
        out.append(f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                   f"COALESCE((SELECT max({col}) FROM {table}), 0) + 1, false);")
    out += [ddl + ";" for ddl in schema if ddl not in tables]
    out.append("COMMIT;")
    return "\n".join(out) + "\n"
