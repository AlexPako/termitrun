"""Генераторы данных трека «Данные»: выгрузки заказов, логи приложений, журнал доступа,
кусочки выгрузки по дням, «экселевский» CSV и сводка JSON.

Правила (бриф P1, глобальные ограничения п. 6):
- всё случайно по зерну rng и одинаково во всех темах: слова бытовые, транслитом;
- CSV без кавычек и без запятых внутри полей — BSD awk кавычек не понимает (tasks/sheets.py);
- в конце каждого файла — \\n;
- у каждого лидера и топа есть запас: ничьих нет (ensure_leader, _untie);
- ловушки строятся данными, а не удачей зерна; ответ задача считает тем же предикатом,
  каким работает BSD-утилита (grep, cut, awk).

Генераторы возвращают текст файла и разобранные записи: задача записывает текст в
песочницу и по записям считает ответ."""
import json
import math
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from termit_app.tasks import kit

# --- orders.csv ------------------------------------------------------------------------------

ORDER_COLUMNS = ("id", "date", "city", "product", "amount", "status", "note")
ORDER_HEADER = ",".join(ORDER_COLUMNS)
CITIES = ("moscow", "kazan", "tver", "omsk", "perm", "ufa", "samara", "sochi", "tula",
          "kursk", "orel", "vologda", "kaluga", "chita", "tomsk", "penza")
STATUSES = ("paid", "refund", "pending", "cancel")
STATUS_WEIGHTS = (60, 12, 18, 10)
NOTES = ("", "gift", "urgent", "call back")
NOTE_WEIGHTS = (80, 7, 7, 6)
REFUND_NOTE = "refund requested"
MONTH = "2726-09"


def render_orders(rows: Sequence[dict]) -> str:
    """Текст orders.csv по записям (в их порядке): заголовок, строки, \\n в конце."""
    body = [",".join(str(r[c]) for c in ORDER_COLUMNS) for r in rows]
    return "\n".join([ORDER_HEADER] + body) + "\n"


def orders(rng, n: int, *, refund_notes: int = 3, day: Optional[int] = None,
           first_id: Optional[int] = None) -> Tuple[str, List[dict]]:
    """Выгрузка заказов за сентябрь 2726: (текст, записи). Записи — словари с ключами
    ORDER_COLUMNS, amount — int. id растут с пропусками (A-1003, A-1004, A-1007…), даты
    отсортированы. day — все заказы одного дня (кусочки parts), first_id — с какого номера.
    Не меньше refund_notes оплаченных (paid) строк получают заметку «refund requested»:
    grep refund ловит их вместе с настоящими возвратами (ловушка)."""
    cities = rng.sample(CITIES, rng.randint(8, 16))
    products = rng.sample(kit.LATIN, rng.randint(8, 12))
    nid = rng.randint(1000, 1999) if first_id is None else first_id
    days = ([day] * n if day is not None else sorted(rng.choices(range(1, 31), k=n)))
    rows = []
    for d, city, product, amount, status, note in zip(
            days, rng.choices(cities, k=n), rng.choices(products, k=n),
            rng.choices(range(100, 10000), k=n),
            rng.choices(STATUSES, STATUS_WEIGHTS, k=n),
            rng.choices(NOTES, NOTE_WEIGHTS, k=n)):
        rows.append({"id": f"A-{nid}", "date": f"{MONTH}-{d:02d}", "city": city,
                     "product": product, "amount": amount, "status": status, "note": note})
        nid += rng.choice((1, 1, 1, 2, 3))
    paid = [r for r in rows if r["status"] == "paid"]
    while len(paid) < refund_notes:          # на маленьких n оплаченных может не хватить
        r = rng.choice([x for x in rows if x["status"] != "paid"])
        r["status"] = "paid"
        paid.append(r)
    for r in rng.sample(paid, refund_notes):
        r["note"] = REFUND_NOTE
    return render_orders(rows), rows


def lead(counts: Counter, key) -> int:
    """На сколько key опережает лучшего из остальных (отрицательное — отстаёт)."""
    rest = [v for k, v in counts.items() if k != key]
    return counts.get(key, 0) - (max(rest) if rest else 0)


def leader(counts: Counter):
    """Самое частое значение; при равенстве — меньшее по алфавиту (детерминированно)."""
    return max(sorted(counts), key=lambda k: counts[k])


def ensure_leader(rows: List[dict], col: str, margin: int, rng=None, value=None):
    """Переставить значения колонки col так, чтобы у лидера (value или текущего) был запас
    не меньше margin над вторым: строки второго по частоте переписываются на лидера.
    Строки с заметкой «refund requested» не трогаем — их статус paid держит ловушку.
    Возвращает лидера; текст файла после этого собрать заново: render_orders(rows)."""
    counts = Counter(r[col] for r in rows)
    top = leader(counts) if value is None else value
    pool: Dict[object, List[dict]] = {}
    for r in rows:
        if r.get("note") != REFUND_NOTE:
            pool.setdefault(r[col], []).append(r)
    if rng is not None:
        for bucket in pool.values():
            rng.shuffle(bucket)
    while lead(counts, top) < margin:
        second = max(sorted(k for k in counts if k != top and pool.get(k)),
                     key=lambda k: counts[k])
        r = pool[second].pop()
        r[col] = top
        counts[second] -= 1
        counts[top] += 1
        if not counts[second]:
            del counts[second]
    return top


# --- app.log ---------------------------------------------------------------------------------

SERVICES = ("auth", "orders", "payments", "search", "mailer", "billing")
LEVELS = ("INFO", "WARN", "ERROR")
LEVEL_WEIGHTS = (75, 15, 10)
# В msg нет слов error/info/warn ни в каком регистре: они живут только в теге уровня.
MSGS = {
    "INFO": ("request ok in {ms}ms", "user login ok", "cache hit ratio {n}",
             "sent {n} items to {other}", "sync with {other} done", "health check passed"),
    "WARN": ("slow response from {other} {ms}ms", "retry {n} calling {other}",
             "queue depth {n}", "cache miss rate high", "disk usage {n} percent"),
    "ERROR": ("timeout calling {other}", "connection refused by {other}",
              "bad reply from {other}", "disk full on /var", "panic in worker {n}"),
}
LOG_START = date(2726, 9, 26)
MIXED_MIN = 5           # mixed_case: не меньше стольких [error] и стольких [Error]


def _msg(rng, level: str, svc: str, services: Sequence[str]) -> str:
    others = [s for s in services if s != svc] or [svc]
    return rng.choice(MSGS[level]).format(ms=rng.randint(20, 5000), n=rng.randint(2, 99),
                                          other=rng.choice(others))


def _entry(when: datetime, level: str, svc: str, msg: str) -> dict:
    return {"ts": when.strftime("%Y-%m-%d %H:%M:%S"), "level": level, "tag": f"[{level}]",
            "svc": svc, "msg": msg}


def log_line(e: dict) -> str:
    return f"{e['ts']} {e['tag']} svc={e['svc']} msg={e['msg']}"


def app_log(rng, *, days: int = 1, per_day: int = 1500, services: Sequence[str] = SERVICES,
            mixed_case: bool = False, start: date = LOG_START,
            mention_traps: Optional[Tuple[str, int]] = None,
            minute_traps: Optional[Tuple[object, object, int]] = None,
            avoid_hours: Sequence[object] = ()) -> Tuple[str, List[dict]]:
    """Лог приложения: (текст, записи). Строка — «2726-09-28 14:05:31 [ERROR] svc=payments
    msg=timeout calling orders», строки по времени. Запись — словарь ts, level, tag, svc,
    msg и text (сама строка).

    mixed_case — у части ERROR тег [error] или [Error] (каждой формы не меньше 5).
    mention_traps=(svc, k) — k строк ERROR чужих сервисов с именем svc в msg: grep svc без
    метки svc= их цепляет. minute_traps=(h1, h2, k) — каждый день k строк ERROR в других
    часах, где минуты равны h1 или h2: голое «14:» цепляет каждую. avoid_hours —
    ещё часы, куда строки-ловушки не ложатся (окно из нескольких часов: ловушка не станет
    частью ответа)."""
    services = tuple(services)
    base = datetime(start.year, start.month, start.day)
    entries = []
    for d in range(days):
        day0 = base + timedelta(days=d)
        secs = sorted(rng.choices(range(86400), k=per_day))
        levels = rng.choices(LEVELS, LEVEL_WEIGHTS, k=per_day)
        svcs = rng.choices(services, k=per_day)
        for s, lv, svc in zip(secs, levels, svcs):
            entries.append(_entry(day0 + timedelta(seconds=s), lv, svc,
                                  _msg(rng, lv, svc, services)))
    if mention_traps:
        svc, k = mention_traps
        others = [s for s in services if s != svc]
        for _ in range(k):
            when = base + timedelta(days=rng.randrange(days), seconds=rng.randrange(86400))
            entries.append(_entry(when, "ERROR", rng.choice(others),
                                  rng.choice(MSGS["ERROR"][:3]).format(other=svc)))
    if minute_traps:
        h1, h2, k = int(minute_traps[0]), int(minute_traps[1]), minute_traps[2]
        skip = {h1, h2} | {int(h) for h in avoid_hours}
        hours = [h for h in range(24) if h not in skip]
        for d in range(days):
            day0 = base + timedelta(days=d)
            for i in range(k):
                hit = (h1, h2)[i % 2]
                # ловушка — только минуты: после секунд двоеточия нет, «(h1|h2):» их не цепляет
                sec = rng.randrange(60)         # порядок вызовов rng — прежний
                when = day0.replace(hour=rng.choice(hours), minute=hit, second=sec)
                svc = rng.choice(services)
                entries.append(_entry(when, "ERROR", svc, _msg(rng, "ERROR", svc, services)))
    if mixed_case:      # каждой формы тега — не меньше MIXED_MIN: ERROR не хватает — дописать
        while sum(e["level"] == "ERROR" for e in entries) < 2 * MIXED_MIN:
            when = base + timedelta(days=rng.randrange(days), seconds=rng.randrange(86400))
            svc = rng.choice(services)
            entries.append(_entry(when, "ERROR", svc, _msg(rng, "ERROR", svc, services)))
    entries.sort(key=lambda e: e["ts"])         # устойчиво: порядок внутри секунды — как был
    if mixed_case:
        errs = [e for e in entries if e["level"] == "ERROR"]
        k = max(MIXED_MIN, len(errs) // 6)
        picked = rng.sample(errs, min(len(errs), 2 * k))
        for i, e in enumerate(picked):
            e["tag"] = "[error]" if i % 2 == 0 else "[Error]"
    for e in entries:
        e["text"] = log_line(e)
    return "\n".join(e["text"] for e in entries) + "\n", entries


# --- parts/day_N.csv -------------------------------------------------------------------------

def parts(rng, days: int = 7) -> Dict[str, str]:
    """Выгрузка, нарезанная по дням: {"day_1.csv": текст, …}. У каждого кусочка свой
    заголовок и 20–60 строк формата orders; id растут сквозь все дни."""
    out = {}
    nid = rng.randint(1000, 1999)
    for d in range(1, days + 1):
        text, rows = orders(rng, rng.randint(20, 60), refund_notes=0, day=d, first_id=nid)
        nid = int(rows[-1]["id"][2:]) + rng.randint(1, 3)
        out[f"day_{d}.csv"] = text
    return out


# --- excel.csv -------------------------------------------------------------------------------

def excel(rng, n: int) -> Tuple[str, str]:
    """«Экселевская» выгрузка: (src, want). src — «id;date;product;amount», даты ДД.ММ.ГГГГ;
    want — то же с запятыми и датами ГГГГ-ММ-ДД. Суммы целые: других кусков вида
    dd.dd.dddd, кроме дат, в файле нет."""
    products = rng.sample(kit.LATIN, rng.randint(6, 10))
    nid = rng.randint(1000, 1999)
    src, want = ["id;date;product;amount"], ["id,date,product,amount"]
    for d in sorted(rng.choices(range(1, 31), k=n)):
        prod, amount = rng.choice(products), rng.randint(100, 9999)
        src.append(f"A-{nid};{d:02d}.09.2726;{prod};{amount}")
        want.append(f"A-{nid},2726-09-{d:02d},{prod},{amount}")
        nid += rng.choice((1, 1, 2))
    return "\n".join(src) + "\n", "\n".join(want) + "\n"


# --- exchange.json ---------------------------------------------------------------------------

LOT_STATUSES = ("open", "sold", "closed")


def exchange(rng) -> Tuple[str, List[dict]]:
    """Сводка лотов одной строкой JSON: (текст, лоты в порядке файла). 20–40 лотов; у одного
    (exchange_target) есть двойники по id: на цифру короче (L-104) и на цифру длиннее
    (L-10427) — grep -o по id цепляет и их. Цены трёх похожих лотов разные."""
    n = rng.randint(20, 40)
    target = rng.randint(1000, 9999)
    short, longer = f"L-{target // 10}", f"L-{target}{rng.randint(0, 9)}"
    ids = {f"L-{target}", short, longer}
    while len(ids) < n:
        x = f"L-{rng.randint(1000, 9999)}"
        if x[:-1] != short:          # второй «L-104x» запутал бы ловушку
            ids.add(x)
    order = sorted(ids)
    rng.shuffle(order)
    prices = rng.sample(range(100, 10000), n)
    lots = [{"id": i, "item": rng.choice(kit.LATIN), "price": p,
             "status": rng.choice(LOT_STATUSES)} for i, p in zip(order, prices)]
    doc = {"updated": f"2726-09-{rng.randint(20, 30):02d}T{rng.randint(0, 23):02d}:00:00",
           "lots": lots}
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", lots


def exchange_target(lots: Sequence[dict]) -> str:
    """id лота с двойниками: есть id на цифру короче и id, который с него начинается."""
    ids = {lot["id"] for lot in lots}
    for i in sorted(ids):
        if i[:-1] in ids and any(o != i and o.startswith(i) for o in ids):
            return i
    raise ValueError("в сводке нет лота с двойниками")


# --- market.json (jq_deep, часть 7) ----------------------------------------------------------

META_KEYS = ("source", "updated", "currency", "region", "version", "owner", "format",
             "author", "license", "batch")
MARKET_STATUSES = ("open", "sold", "closed")
LOOSE_OPEN = ("opened", "open ")       # select(.status=="open") их не берёт, contains — берёт


def market(rng) -> dict:
    """market.json одной строкой: {"market": {"lots": [...]}, "meta": {...}}. 12–20 лотов
    (id, item, price, qty, status), meta — 6–9 полей. Постройкой: первые два товара разные;
    есть открытые, «почти open» (opened, «open » с пробелом) и прочие статусы; qty = 0 хотя бы
    у одного, null — у одного-двух. Возвращает {"text", "lots", "meta", "open_sum",
    "loose_sum", "total", "zeros", "nulls"}."""
    n = rng.randint(12, 20)
    items = [rng.choice(kit.LATIN) for _ in range(n)]
    if items[1] == items[0]:
        items[1] = rng.choice([w for w in kit.LATIN if w != items[0]])
    statuses = [rng.choice(MARKET_STATUSES) for _ in range(n)]
    slots = rng.sample(range(n), 5)
    statuses[slots[0]] = statuses[slots[1]] = "open"
    statuses[slots[2]] = rng.choice(LOOSE_OPEN)
    statuses[slots[3]] = rng.choice(("sold", "closed"))
    if rng.random() < 0.5:
        statuses[slots[4]] = rng.choice(LOOSE_OPEN)
    qty = [rng.randint(1, 40) for _ in range(n)]
    spots = rng.sample(range(n), 6)
    nulls = rng.randint(1, 2)
    for i in spots[:nulls]:
        qty[i] = None
    for i in spots[nulls:nulls + rng.randint(1, 4)]:
        qty[i] = 0
    if sum(q is None or q == 0 for q in qty) == n:      # при n ≥ 12 не бывает — на всякий
        qty[spots[-1]] = 1
    prices = rng.sample(range(100, 5000), n)
    lots = [{"id": f"M-{100 + i}", "item": items[i], "price": prices[i], "qty": qty[i],
             "status": statuses[i]} for i in range(n)]
    keys = rng.sample(META_KEYS, rng.randint(6, 9))
    values = {"source": "exchange", "updated": f"2726-10-{rng.randint(1, 12):02d}",
              "currency": rng.choice(("RUB", "USD", "EUR")), "region": rng.choice(kit.LATIN),
              "version": rng.randint(2, 9), "owner": rng.choice(kit.LATIN),
              "format": "json", "author": rng.choice(kit.LATIN), "license": "internal",
              "batch": rng.randint(100, 999)}
    meta = {k: values[k] for k in keys}
    doc = {"market": {"lots": lots}, "meta": meta}
    return {"text": json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n",
            "lots": lots, "meta": meta,
            "open_sum": sum(x["price"] for x in lots if x["status"] == "open"),
            "loose_sum": sum(x["price"] for x in lots if "open" in x["status"]),
            "total": sum(x["price"] for x in lots),
            "zeros": sum(x["qty"] == 0 for x in lots),
            "nulls": sum(x["qty"] is None for x in lots)}


# --- access.log (страж) ----------------------------------------------------------------------

ACCESS_START = date(2726, 9, 21)
ACCESS_DAYS = 7
CRAWLER = "10.0.0.2"
CRAWLER_PER_HOUR = 30
NIGHT_IP = "10.0.0.8"
POOL_SIZE = 150
WEEK_MARGIN = 100       # запас краулера над вторым адресом недели
BG_PATHS = (("GET", "/", 200), ("GET", "/index.html", 200), ("GET", "/api/rates", 200),
            ("GET", "/api/lots", 200), ("GET", "/static/app.js", 200),
            ("GET", "/static/style.css", 304), ("POST", "/login", 200),
            ("POST", "/login", 401), ("GET", "/favicon.ico", 404), ("GET", "/api/lots", 304))
BG_WEIGHTS = (14, 10, 18, 18, 8, 8, 6, 3, 3, 12)
USERS = ("-", "-", "-", "ann", "bob", "kim", "lee", "max", "zoe")


def _curve(hour: int) -> int:
    """Суточная кривая запросов в час: ночью ~20, днём к 16 часам до ~220."""
    return int(20 + 200 * (1 - math.cos(2 * math.pi * (hour - 4) / 24)) / 2)


def access_line(ts: str, ip: str, method: str, path: str, code: int, size: int,
                user: str) -> str:
    return f"{ts} {ip} {method} {path} {code} {size} user={user}"


def _stamp(day: date, hour: int, sec: int) -> str:
    return f"{day.isoformat()}T{hour:02d}:{sec // 60:02d}:{sec % 60:02d}"


def _bg_line(rng, day: date, hour: int, ip: str) -> Tuple[str, str]:
    method, path, code = rng.choices(BG_PATHS, BG_WEIGHTS)[0]
    size = 0 if code == 304 else rng.randint(150, 9000)
    ts = _stamp(day, hour, rng.randrange(3600))
    return ts, access_line(ts, ip, method, path, code, size, rng.choice(USERS))


def _ip_pool(rng, k: int, banned) -> List[str]:
    out, seen = [], set(banned)
    while len(out) < k:
        ip = f"10.{rng.randint(1, 4)}.{rng.randint(0, 9)}.{rng.randint(1, 254)}"
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out


def _strict_top(counts: Counter, k: int) -> bool:
    top = counts.most_common(k + 1)
    return all(top[i][1] > top[i + 1][1] for i in range(min(k, len(top) - 1)))


def access_log(rng) -> Tuple[str, dict]:
    """Журнал доступа за неделю 2726-09-21…27 со спрятанной атакой: (текст, facts).
    Строка: «2726-09-24T14:05:31 10.3.7.1 POST /login 401 118 user=-», поля awk: $1 время,
    $2 ip, $3 метод, $4 путь, $5 код, $6 байты, $7 user.

    Фон — суточная кривая 20–220 запросов в час от ~150 адресов (веса по Ципфу); краулер
    10.0.0.2 — 30 в час, лидер недели (ловушка «топ за неделю»). Каждую ночь в 03:00:00 —
    10.0.0.8 GET /vault/check 200 64 user=nol. Атака — один час дня 2–7 (не 03): 7 адресов,
    лидер 380–520 запросов, каждый следующий меньше на 25–60, пятый ≥ 120, шестой меньше
    пятого на 20+ и больше любого фонового адреса часа. У лидера последний октет 1–9, и в
    часе атаки есть 3+ строки адреса «лидер + цифра» (grep 10.3.7.1 цепляет 10.3.7.17).

    facts: hour «2726-09-24T14», top5 и week_top5 — адреса по убыванию, leader, leader_lines
    (строки лидера за час атаки, отсортированы), bytes200 — сумма байт его ответов 200,
    bytes_all — сумма байт всех его строк за час, collision — адрес-двойник."""
    days = [ACCESS_START + timedelta(days=i) for i in range(ACCESS_DAYS)]
    attack_day = days[rng.randint(1, ACCESS_DAYS - 1)]
    attack_hour = rng.choice([h for h in range(24) if h != 3])
    attack_stamp = f"{attack_day.isoformat()}T{attack_hour:02d}"
    leader_ip = f"10.{rng.randint(1, 4)}.{rng.randint(0, 9)}.{rng.randint(1, 9)}"
    collision = f"{leader_ip}{rng.randint(0, 9)}"
    attackers = [leader_ip] + _ip_pool(rng, 6, {leader_ip, collision})
    pool = _ip_pool(rng, POOL_SIZE, set(attackers) | {collision})
    weights = [1 / (i + 1) for i in range(POOL_SIZE)]

    lines: List[Tuple[str, str]] = []           # (время, строка) — сортируем в конце
    hour_bg = Counter()                          # фон часа атаки по адресам
    for day in days:
        for hour in range(24):
            n = max(20, min(220, _curve(hour) + rng.randint(-10, 10)))
            for ip in rng.choices(pool, weights, k=n):
                lines.append(_bg_line(rng, day, hour, ip))
                if day == attack_day and hour == attack_hour:
                    hour_bg[ip] += 1
            for _ in range(CRAWLER_PER_HOUR):
                ts = _stamp(day, hour, rng.randrange(3600))
                page = rng.randint(1, 400)
                lines.append((ts, access_line(ts, CRAWLER, "GET", f"/api/lots?page={page}", 200,
                                              rng.randint(800, 4000), "-")))
            if day == attack_day and hour == attack_hour:
                hour_bg[CRAWLER] += CRAWLER_PER_HOUR
        ts = f"{day.isoformat()}T03:00:00"
        lines.append((ts, access_line(ts, NIGHT_IP, "GET", "/vault/check", 200, 64, "nol")))

    # двойник лидера: 3–6 строк в часе атаки (фон, но адрес не из пула)
    for _ in range(rng.randint(3, 6)):
        lines.append(_bg_line(rng, attack_day, attack_hour, collision))
        hour_bg[collision] += 1

    # атака: число запросов по адресам
    counts = [rng.randint(380, 520)]
    for _ in range(4):
        counts.append(counts[-1] - rng.randint(25, 60))
    bg_max = max(hour_bg.values())
    # Гарантия с запасом: фон часа ≤ 220 строк, Ципф отдаёт лидеру пула ~18 % (≈40) плюс
    # краулер 30, а пятый атакующий ≥ 140. Нарушится — громко, а не тихо неверным ответом.
    if bg_max + 3 > counts[4] - 20:
        raise ValueError(f"фон часа атаки слишком плотный: {bg_max} строк у одного адреса")
    counts.append(rng.randint(bg_max + 3, counts[4] - 20))
    counts.append(rng.randint(max(3, bg_max // 2), counts[5] - 3))
    leader_lines = []
    for ip, k in zip(attackers, counts):
        kinds = ["export" if rng.random() < 0.2 else "login" for _ in range(k)]
        if ip == leader_ip:          # у лидера есть и 200, и 401: bytes200 ≠ bytes_all
            kinds[0], kinds[1] = "export", "login"
        for kind in kinds:
            ts = _stamp(attack_day, attack_hour, rng.randrange(3600))
            if kind == "export":
                line = access_line(ts, ip, "GET", "/api/export", 200,
                                   rng.randint(2000, 90000), "-")
            else:
                line = access_line(ts, ip, "POST", "/login", 401, rng.randint(90, 140), "-")
            lines.append((ts, line))
            if ip == leader_ip:
                leader_lines.append(line)

    # краулер — лидер недели с запасом: лишние строки соперника уходят хвосту пула
    week = Counter(line.split(" ", 2)[1] for _, line in lines)
    while lead(week, CRAWLER) < WEEK_MARGIN:
        rival = leader(Counter({k: v for k, v in week.items() if k != CRAWLER}))
        tail = pool[-1 - rng.randrange(POOL_SIZE // 2)]
        for i, (ts, line) in enumerate(lines):
            if line.split(" ", 2)[1] == rival and not ts.startswith(attack_stamp):
                lines[i] = (ts, line.replace(f" {rival} ", f" {tail} ", 1))
                week[rival] -= 1
                week[tail] += 1
                break

    # топ недели — без ничьих в первой шестёрке: равных добавляем по строке в другие часы
    while not _strict_top(week, 6):
        top = week.most_common(7)
        for i in range(6):
            if top[i][1] == top[i + 1][1]:
                ip = top[i][0]
                break
        day = rng.choice(days)
        hour = rng.choice([h for h in range(24) if (day, h) != (attack_day, attack_hour)])
        lines.append(_bg_line(rng, day, hour, ip))
        week[ip] += 1

    lines.sort()
    hour = f"{attack_day.isoformat()}T{attack_hour:02d}"
    leader_lines.sort()
    facts = {
        "hour": hour,
        "top5": attackers[:5],
        "leader": leader_ip,
        "collision": collision,
        "leader_lines": leader_lines,
        "bytes200": sum(int(x.split()[5]) for x in leader_lines if x.split()[4] == "200"),
        "bytes_all": sum(int(x.split()[5]) for x in leader_lines),
        "week_top5": [ip for ip, _ in week.most_common(5)],
    }
    return "\n".join(line for _, line in lines) + "\n", facts
