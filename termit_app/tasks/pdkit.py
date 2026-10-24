"""Данные трека «Аналитика» (часть 10, Q4): переводы transfers.csv и их родня, ответы и
ловушки — чистым Python у родителя, по строкам генератора (правило 2 «Уроков ревью»): pandas
здесь нет, код игрока не исполняется и не импортируется. Совпадение ответов с pandas проверяет
только живой тест tests/test_pydata_live.py (со складом колёс).

Деньги — целые копейки (центы) внутри генератора: никаких сумм с плавающей ошибкой; в файл
они идут строкой «1234.50». Единственность ответа и отличие ловушек — постройкой: генератор
сам доводит данные (разводит суммы городов, ставит строку ровно на порог), а не надеется на
удачное зерно. Латиница в данных, даты ISO, в конце файлов — перевод строки."""
import csv
import io
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from termit_app.tasks import kit

CITIES = ("Kazan", "Omsk", "Perm", "Tula", "Sochi", "Ufa", "Tver", "Kursk", "Samara", "Orel")
DEPTS = ("sales", "ops", "it", "hr", "legal")
CHANNELS = ("card", "cash", "app")
STATUSES = ("done", "hold", "back")
EXTRA_COLS = ("dept", "channel", "status")
DATA = "transfers.csv"
GAP = 200                       # запас лидера и разлёт сумм городов — 2.00 (правило 2)
NUM_GAP = Fraction(2, 100)      # ловушки-числа дальше ответа хотя бы на 0.02 (допуск 0.005)


def money(cents: int) -> str:
    """Копейки → «1234.50»."""
    return f"{cents // 100}.{cents % 100:02d}"


def csv_text(header: Sequence[str], rows: Sequence[Sequence[str]], sep: str = ",") -> str:
    """CSV через модуль csv (поле с разделителем — в кавычках), концы строк — \\n."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=sep, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _date(rng) -> str:
    return f"2026-{rng.randint(1, 9):02d}-{rng.randint(1, 28):02d}"


def transfers(rng, n: int, cities: Sequence[str], extra: Sequence[str] = ()) -> List[dict]:
    """Строки переводов: id по порядку, дата, город, сумма в копейках и колонки extra. Каждый
    город встречается хотя бы раз (постройкой: первые строки — по городу, потом вперемешку)."""
    names = list(cities) + [rng.choice(cities) for _ in range(max(0, n - len(cities)))]
    rng.shuffle(names)
    rows = []
    for i, city in enumerate(names):
        r = {"id": 101 + i, "date": _date(rng), "city": city,
             "amount": rng.randint(5, 900) * 100 + rng.randint(0, 99)}
        if "dept" in extra:
            r["dept"] = rng.choice(DEPTS)
        if "channel" in extra:
            r["channel"] = rng.choice(CHANNELS)
        if "status" in extra:
            r["status"] = rng.choice(STATUSES)
        rows.append(r)
    return rows


def header_of(extra: Sequence[str]) -> List[str]:
    """Порядок колонок: id, date, city, extra…, amount."""
    return ["id", "date", "city"] + [c for c in EXTRA_COLS if c in extra] + ["amount"]


def render(rows: List[dict], header: Sequence[str], sep: str = ",") -> str:
    out = []
    for r in rows:
        line = []
        for c in header:
            v = r.get(c)
            if c == "amount":
                line.append(v if isinstance(v, str) else ("" if v is None else money(v)))
            else:
                line.append("" if v is None else str(v))
        out.append(line)
    return csv_text(header, out, sep)


def write_csv(box, name: str, rows: List[dict], header: Sequence[str], sep: str = ",") -> str:
    text = render(rows, header, sep)
    kit.write(Path(box) / name, text)
    return text


# --- суммы по группам ------------------------------------------------------------------------

def sums(rows: List[dict], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        if r.get(key) is not None and isinstance(r.get("amount"), int):
            out[r[key]] = out.get(r[key], 0) + r["amount"]
    return out


def spread(rows: List[dict], key: str, gap: int = GAP) -> None:
    """Развести суммы групп: после неё соседние по сумме группы отличаются хотя бы на gap
    (единственный лидер, единственный последний, однозначный топ). Постройкой: к самой
    крупной строке группы добавляется недостающее, снизу вверх."""
    s = sums(rows, key)
    order = sorted(s, key=lambda k: (s[k], k))
    prev = None
    for k in order:
        if prev is not None and s[k] < prev + gap:
            need = prev + gap - s[k]
            big = max((r for r in rows if r.get(key) == k), key=lambda r: (r["amount"], r["id"]))
            big["amount"] += need
            s[k] += need
        prev = s[k]


def ranked(rows: List[dict], key: str) -> List[str]:
    """Группы по сумме — от большей к меньшей (после spread ничьих нет)."""
    s = sums(rows, key)
    return sorted(s, key=lambda k: -s[k])


def frac_str(x: Fraction) -> str:
    """Точное значение дроби для ответа: до 6 знаков (сверка — с допуском 0.005)."""
    return f"{float(x):.6f}".rstrip("0").rstrip(".")


def far(a: Fraction, b: Fraction) -> bool:
    return abs(a - b) >= NUM_GAP


# --- 2. pd_read ----------------------------------------------------------------------------------

DTYPES = {"amount": "float64", "id": "int64", "city": "object"}


# ещё колонки выгрузки с «;» (pd_read C, M4 ревью Q4): колонок 4–13 — ответ не угадать за
# пару попыток. Значения без запятых и «;»: без sep pandas обязан увидеть ровно одну колонку
MORE_COLS = {
    "bank": lambda rng: rng.choice(("alfa", "sber", "tink", "vtb")),
    "agent": lambda rng: f"a{rng.randint(1, 30)}",
    "fee": lambda rng: str(rng.randint(0, 50)),
    "region": lambda rng: rng.choice(("north", "south", "east", "west")),
    "ref": lambda rng: f"R{rng.randint(1000, 9999)}",
    "kind": lambda rng: rng.choice(("in", "out")),
}


def read_data(rng, variant: int) -> dict:
    """A — строк данных (шапка не строка); B — колонок и тип одной (индекс не колонка);
    C — колонок в файле с «;» (без sep — одна): лишних колонок 0–9, поровну."""
    n = rng.randint(18, 60)
    if variant == 2:
        pool = list(EXTRA_COLS) + list(MORE_COLS)
        chosen = set(rng.sample(pool, rng.randint(0, len(pool))))
        extra = tuple(c for c in EXTRA_COLS if c in chosen)
        rows = transfers(rng, n, rng.sample(CITIES, 5), extra)
        more = [c for c in MORE_COLS if c in chosen]
        for r in rows:
            for c in more:
                r[c] = MORE_COLS[c](rng)
        header = ["id", "date", "city"] + [c for c in pool if c in chosen] + ["amount"]
    else:
        extra = tuple(c for c in EXTRA_COLS if rng.random() < 0.5)
        rows = transfers(rng, n, rng.sample(CITIES, 5), extra)
        header = header_of(extra)
    out = {"rows": rows, "header": header, "n": n, "ncols": len(header)}
    if variant == 0:
        out["answer"] = str(n)
        out["traps"] = [["header", str(n + 1)]]
    elif variant == 1:
        col = rng.choice(sorted(DTYPES))
        out["col"] = col
        out["answer"] = f"{len(header)} {DTYPES[col]}"
        out["traps"] = [["index", f"{len(header) + 1} {DTYPES[col]}"]]
    else:
        out["answer"] = str(len(header))
        out["traps"] = [["sep", "1"]]
    return out


# --- 3. pd_filter --------------------------------------------------------------------------------

def filter_data(rng, variant: int) -> dict:
    """A — больше порога (строка ровно на пороге есть всегда); B — города из списка (каждый
    из них есть); C — город и порог вместе (and против or разводится постройкой)."""
    cities = rng.sample(CITIES, 6)
    rows = transfers(rng, rng.randint(28, 50), cities)
    out = {"rows": rows, "header": header_of(())}
    if variant == 0:
        # порог — целые рубли из середины; одна строка ровно на нём
        mid = sorted(rows, key=lambda r: (r["amount"], r["id"]))[len(rows) // 2]
        limit = mid["amount"] // 100
        mid["amount"] = limit * 100
        gt = sum(r["amount"] > limit * 100 for r in rows)
        ge = sum(r["amount"] >= limit * 100 for r in rows)
        out.update(limit=limit, answer=str(gt), traps=[["edge", str(ge)]])
    elif variant == 1:
        a, b = rng.sample(cities, 2)
        na = sum(r["city"] == a for r in rows)
        nb = sum(r["city"] == b for r in rows)
        out.update(c1=a, c2=b, answer=str(na + nb),
                   traps=[["one", str(na)], ["one", str(nb)]])
    else:
        city = rng.choice(cities)
        mid = sorted(rows, key=lambda r: (r["amount"], r["id"]))[len(rows) // 2]
        limit = mid["amount"] // 100
        mine = [r for r in rows if r["city"] == city]
        other = [r for r in rows if r["city"] != city]
        # постройкой: у города есть строка выше порога и строка не выше; у других — выше
        mine[0]["amount"] = limit * 100 + rng.randint(1, 50000)
        if len(mine) > 1:
            mine[-1]["amount"] = min(mine[-1]["amount"], limit * 100)
        else:
            other[0]["city"] = city
            other[0]["amount"] = limit * 100 - rng.randint(0, 300)
            other = other[1:]
        other[-1]["amount"] = max(other[-1]["amount"], limit * 100 + rng.randint(1, 9999))
        both = sum(r["city"] == city and r["amount"] > limit * 100 for r in rows)
        either = sum(r["city"] == city or r["amount"] > limit * 100 for r in rows)
        out.update(city=city, limit=limit, answer=str(both), traps=[["or", str(either)]])
    return out


# --- 4. pd_groupby -------------------------------------------------------------------------------

def groupby_data(rng, variant: int) -> dict:
    """A — город с наибольшей суммой (ловушка — наименьшая: sort_values без ascending=False);
    B — средний перевод отдела, до 2 знаков (ловушки — сумма отдела и среднее по всем);
    C — три города с наибольшей суммой по убыванию (ловушка — три наименьших)."""
    cities = rng.sample(CITIES, rng.randint(6, 8))
    rows = transfers(rng, rng.randint(30, 60), cities, ("dept",))
    out = {"header": header_of(("dept",))}
    if variant == 1:
        dept = rng.choice(DEPTS)
        mine = [r for r in rows if r["dept"] == dept]
        while len(mine) < 2:
            r = rng.choice([x for x in rows if x["dept"] != dept])
            r["dept"] = dept
            mine.append(r)
        others = [r for r in rows if r["dept"] != dept]
        mean = Fraction(sum(r["amount"] for r in mine), 100 * len(mine))
        allm = Fraction(sum(r["amount"] for r in rows), 100 * len(rows))
        if not far(mean, allm):         # постройкой: среднее всех — дальше 0.02
            others[0]["amount"] += 500
            allm = Fraction(sum(r["amount"] for r in rows), 100 * len(rows))
        total = Fraction(sum(r["amount"] for r in mine), 100)
        out.update(dept=dept, answer=frac_str(mean),
                   traps=[["sum", frac_str(total)], ["all", frac_str(allm)]])
    else:
        spread(rows, "city")
        order = ranked(rows, "city")
        if variant == 0:
            out.update(answer=order[0], traps=[["min", order[-1]]])
        else:
            out.update(answer=" ".join(order[:3]),
                       traps=[["asc", " ".join(list(reversed(order))[:3])]])
    out["rows"] = rows
    return out


# --- 5. pd_missing -------------------------------------------------------------------------------

# «грязные» суммы: не числа для pandas. Пустые строки, n/a, NA, null и прочие из списка
# пропусков read_csv сюда НЕ входят — их pandas сам делает NaN (тогда isna их видит)
DIRTY = ("1 200", "12,5", "—", "3 400.50", "?", "1.200,00")


def missing_data(rng, variant: int) -> dict:
    """A — пропуски в amount (ловушка — во всей таблице); B — среднее amount, где пропуск —
    0 (ловушки — без пропусков и dropna по всей строке); C — значения amount, что не читаются
    числом (ловушка — только пустые)."""
    rows = transfers(rng, rng.randint(20, 40), rng.sample(CITIES, 5), ("dept",))
    out = {"header": header_of(("dept",))}
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    if variant in (0, 1):
        # A: пустых 2–11 (M4 ревью Q4: перебор за пару попыток не проходит)
        k, m = rng.randint(2, 11 if variant == 0 else 5), rng.randint(1, 4)
        for i in idx[:k]:
            rows[i]["amount"] = None
        for i in idx[k:k + m]:
            rows[i]["dept"] = None
        if variant == 0:
            out.update(answer=str(k), traps=[["all", str(k + m)]])
        else:
            n = len(rows)

            def means():
                known = [r["amount"] for r in rows if r["amount"] is not None]
                full = [r["amount"] for r in rows
                        if r["amount"] is not None and r["dept"] is not None]
                return (Fraction(sum(known), 100 * n), Fraction(sum(known), 100 * len(known)),
                        Fraction(sum(full), 100 * len(full)))
            zero, skip, drop = means()
            if not (far(drop, skip) and far(drop, zero)):
                rows[idx[k]]["amount"] += 900       # строка без отдела: dropna её теряет
                zero, skip, drop = means()
            out.update(answer=frac_str(zero),
                       traps=[["skipna", frac_str(skip)], ["dropna", frac_str(drop)]])
    else:
        b, d = rng.randint(1, 4), rng.randint(2, 8)        # ответ b + d: 3–12
        for i in idx[:b]:
            rows[i]["amount"] = None
        for i in idx[b:b + d]:
            rows[i]["amount"] = rng.choice(DIRTY)
        out.update(answer=str(b + d), traps=[["isna", str(b)]])
    out["rows"] = rows
    return out


# --- FB15: вторая половина pandas — даты, склейка, сводные, map/apply, сохранение, SQL -----
# Годы — 2026, как у остальных данных трека: pandas хранит время в наносекундах и знает даты
# только до 2262 года (pd.Timestamp.max), а «год мира» ~2726 он прочесть не смог бы.

MONTHS_RU = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",
             "сентябрь")
MONTHS_GEN = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября")


def _parts(row: dict) -> Tuple[int, int, int]:
    y, m, d = row["date"].split("-")
    return int(y), int(m), int(d)


def _set_date(row: dict, month: int, day: int) -> None:
    row["date"] = f"2026-{month:02d}-{day:02d}"


def month_sums(rows: List[dict]) -> Dict[int, int]:
    out: Dict[int, int] = {}
    for r in rows:
        m = _parts(r)[1]
        out[m] = out.get(m, 0) + r["amount"]
    return out


def money_frac(cents: int) -> str:
    return frac_str(Fraction(cents, 100))


def dates_data(rng, variant: int) -> dict:
    """A — сумма за месяц m (ловушка — день месяца m: .dt.day вместо .dt.month); B —
    наибольший помесячный итог (ловушки — наименьший месяц и итог дня — daily); C — даты
    DD.MM.YYYY: переводов с первого числа месяца a по 28-е месяца a+2 включительно (ловушки —
    сравнение строк без to_datetime и границы без «=»)."""
    rows = transfers(rng, rng.randint(32, 56), rng.sample(CITIES, 5))
    out = {"header": header_of(()), "rows": rows}
    if variant == 0:
        m = rng.randint(2, 9)
        mine = [r for r in rows if _parts(r)[1] == m]
        others = [r for r in rows if _parts(r)[1] != m]
        while len(mine) < 3:                 # в месяце m — хотя бы три перевода
            r = others.pop()
            _set_date(r, m, rng.randint(1, 28))
            mine.append(r)
        # постройкой: в других месяцах есть дни с номером m — ловушка .dt.day не пуста
        for r in others[:2]:
            _set_date(r, _parts(r)[1], m)
        want = sum(r["amount"] for r in mine)
        day = sum(r["amount"] for r in rows if _parts(r)[2] == m)
        if not far(Fraction(want, 100), Fraction(day, 100)):
            others[0]["amount"] += 700
            day = sum(r["amount"] for r in rows if _parts(r)[2] == m)
        out.update(month=m, month_name=MONTHS_RU[m - 1], answer=money_frac(want),
                   traps=[["day", money_frac(day)]])
    elif variant == 1:
        for r in rows:                       # месяц — ключ для spread
            r["month"] = _parts(r)[1]
        spread(rows, "month")
        for r in rows:
            del r["month"]
        s = month_sums(rows)
        daily: Dict[str, int] = {}
        for r in rows:
            daily[r["date"]] = daily.get(r["date"], 0) + r["amount"]
        best, low = max(s.values()), min(s.values())
        out.update(answer=money_frac(best),
                   traps=[["min", money_frac(low)], ["daily", money_frac(max(daily.values()))]])
    else:
        a = rng.randint(1, 6)
        b = a + 2
        lo, hi = f"2026-{a:02d}-01", f"2026-{b:02d}-28"
        # постройкой: строки ровно на обеих границах — «без =» их теряет
        inside = [r for r in rows if lo < r["date"] < hi]
        outside = [r for r in rows if not lo <= r["date"] <= hi]
        _set_date(outside.pop(), a, 1)
        _set_date(outside.pop(), b, 28)
        # постройкой: строка, которую сравнение строк «DD.MM.YYYY» берёт зря: день между
        # 01 и 28, а месяц — вне окна (строки сравниваются с дня)
        _set_date(outside.pop(), 9 if b < 9 else 1, rng.randint(2, 27))
        del inside
        dmy = {r["id"]: f"{_parts(r)[2]:02d}.{_parts(r)[1]:02d}.2026" for r in rows}
        want = sum(lo <= r["date"] <= hi for r in rows)
        strict = sum(lo < r["date"] < hi for r in rows)
        d_lo, d_hi = f"01.{a:02d}.2026", f"28.{b:02d}.2026"
        text = sum(d_lo <= dmy[r["id"]] <= d_hi for r in rows)
        for r in rows:
            r["date"] = dmy[r["id"]]
        out.update(start=lo, end=hi, start_dmy=d_lo, end_dmy=d_hi,
                   start_name=f"1 {MONTHS_GEN[a - 1]}", end_name=f"28 {MONTHS_GEN[b - 1]}",
                   answer=str(want), traps=[["text", str(text)], ["edge", str(strict)]])
    return out


# --- 8. pd_merge -------------------------------------------------------------------------------

# имена — без совпадений с кусками кода запаса venv и заглушек (охрана test_judge: ответа нет в
# служебных файлах песочницы): «Ada», «Max», «Yan» там встречаются как части слов
NAMES = ("Aino", "Bram", "Cleo", "Dagny", "Elio", "Fenna", "Greta", "Hana", "Ines", "Juno",
         "Kira", "Leif", "Mira", "Noor", "Otto", "Quinn", "Rosa", "Sven", "Tess", "Ulla", "Vera",
         "Wren", "Yara", "Zoe")
TIERS = ("gold", "silver", "basic")
ACCOUNTS = "accounts.csv"
ACC_HEADER = ["account", "name", "tier"]
TR_HEADER = ["id", "date", "account", "amount"]
TR_NAMED = ["id", "date", "account", "name", "amount"]


def _accounts(rng, n: int) -> List[dict]:
    names = rng.sample(NAMES, n)
    return [{"account": 201 + i, "name": names[i], "tier": rng.choice(TIERS)} for i in range(n)]


def _account_transfers(rng, accounts: List[dict], n: int, used: Sequence[dict]) -> List[dict]:
    """Переводы со счетов used (каждый — хотя бы раз), id по порядку."""
    picks = list(used) + [rng.choice(list(used)) for _ in range(max(0, n - len(used)))]
    rng.shuffle(picks)
    rows = []
    for i, acc in enumerate(picks):
        rows.append({"id": 101 + i, "date": _date(rng), "account": acc["account"],
                     "name": acc["name"],
                     "amount": rng.randint(5, 900) * 100 + rng.randint(0, 99)})
    return rows


def merge_data(rng, variant: int) -> dict:
    """A — сколько перевёл владелец (имена — в accounts.csv; ловушка — сумма всех переводов);
    B — счетов без переводов (how="left" + isna; ловушка — склейка без how: 0); C — сумма со
    счетов уровня tier, у владельца есть тёзка другого уровня (ловушка — склейка по имени
    размножает строки тёзок)."""
    accounts = _accounts(rng, rng.randint(8, 12))
    out = {"accounts": accounts}
    if variant == 1:
        k = rng.randint(2, min(7, len(accounts) - 3))
        idle = rng.sample(accounts, k)
        used = [a for a in accounts if a not in idle]
        rows = _account_transfers(rng, accounts, rng.randint(24, 40), used)
        out.update(answer=str(k), traps=[["inner", "0"]])
    elif variant == 2:
        twin, other = rng.sample(accounts, 2)
        other["name"] = twin["name"]
        tier = twin["tier"]
        if other["tier"] == tier:
            other["tier"] = rng.choice([t for t in TIERS if t != tier])
        rows = _account_transfers(rng, accounts, rng.randint(28, 44), accounts)
        tiers = {a["account"]: a["tier"] for a in accounts}
        want = sum(r["amount"] for r in rows if tiers[r["account"]] == tier)
        by_name: Dict[str, List[dict]] = {}
        for a in accounts:
            by_name.setdefault(a["name"], []).append(a)
        wrong = sum(r["amount"] for r in rows for a in by_name[r["name"]] if a["tier"] == tier)
        out.update(tier=tier, twin=twin["name"], answer=money_frac(want),
                   traps=[["name", money_frac(wrong)]])
    else:
        owner = rng.choice(accounts)
        rows = _account_transfers(rng, accounts, rng.randint(24, 40), accounts)
        want = sum(r["amount"] for r in rows if r["account"] == owner["account"])
        total = sum(r["amount"] for r in rows)
        out.update(owner=owner["name"], answer=money_frac(want),
                   traps=[["all", money_frac(total)]])
    out["rows"] = rows
    out["header"] = TR_NAMED if variant == 2 else TR_HEADER
    return out


def accounts_csv(accounts: List[dict]) -> str:
    return csv_text(ACC_HEADER, [[a["account"], a["name"], a["tier"]] for a in accounts])


# --- 9. pd_pivot -------------------------------------------------------------------------------

PIVOT_CHANNELS = ("card", "cash", "app", "wire", "qr")


def _cells(rows: List[dict]) -> Dict[Tuple[str, str], List[int]]:
    out: Dict[Tuple[str, str], List[int]] = {}
    for r in rows:
        out.setdefault((r["city"], r["channel"]), []).append(r["amount"])
    return out


def pivot_data(rng, variant: int) -> dict:
    """A — сумма в ячейке город × канал (ловушка — среднее: aggfunc по умолчанию mean); B —
    сколько переводов в ячейке (aggfunc="count"; ловушка — сумма ячейки); C — канал с
    наименьшей суммой у города, где одного канала нет вовсе (fill_value=0; ловушка —
    наименьший среди непустых)."""
    cities = rng.sample(CITIES, rng.randint(4, 5))
    rows = transfers(rng, rng.randint(40, 60), cities)
    for r in rows:
        r["channel"] = rng.choice(PIVOT_CHANNELS)
    out = {"header": ["id", "date", "city", "channel", "amount"]}
    if variant == 0:
        city, ch = rng.choice(cities), rng.choice(PIVOT_CHANNELS)
        mine = [r for r in rows if r["city"] == city and r["channel"] == ch]
        spare = [r for r in rows if r not in mine]
        while len(mine) < 3:
            r = spare.pop()
            r["city"], r["channel"] = city, ch
            mine.append(r)
        total = sum(r["amount"] for r in mine)
        mean = Fraction(total, 100 * len(mine))
        out.update(city=city, channel=ch, answer=money_frac(total),
                   traps=[["mean", frac_str(mean)]])
    elif variant == 1:
        # постройкой: в клетке city × channel — 4–13 переводов (ответ не угадать), а их сумма
        # (ловушка aggfunc="sum") — деньги, не число строк
        city, ch = rng.choice(cities), rng.choice(PIVOT_CHANNELS)
        k = rng.randint(4, 13)
        mine = [r for r in rows if r["city"] == city and r["channel"] == ch]
        spare = [r for r in rows if r not in mine]
        rng.shuffle(spare)
        while len(mine) < k:
            r = spare.pop()
            r["city"], r["channel"] = city, ch
            mine.append(r)
        for r in mine[k:]:
            r["channel"] = rng.choice([c for c in PIVOT_CHANNELS if c != ch])
        total = sum(r["amount"] for r in rows if r["city"] == city and r["channel"] == ch)
        out.update(city=city, channel=ch, answer=str(k), traps=[["sum", money_frac(total)]])
    else:
        city = rng.choice(cities)
        gone = rng.choice(PIVOT_CHANNELS)
        others = [c for c in cities if c != city]
        for r in rows:
            if r["city"] == city and r["channel"] == gone:
                r["city"] = rng.choice(others)
        # постройкой: у города есть все остальные каналы
        mine = {r["channel"] for r in rows if r["city"] == city}
        spare = [r for r in rows if r["city"] != city]
        for ch in PIVOT_CHANNELS:
            if ch != gone and ch not in mine:
                r = spare.pop()
                r["city"], r["channel"] = city, ch
        # и у канала gone есть переводы в других городах (иначе колонки не будет вовсе)
        if not any(r["channel"] == gone for r in rows):
            spare[0]["channel"] = gone
        cells = _cells(rows)
        mine = {ch: sum(cells[(city, ch)]) for ch in PIVOT_CHANNELS if (city, ch) in cells}
        low = min(mine, key=lambda ch: (mine[ch], ch))
        out.update(city=city, answer=gone, traps=[["skipna", low]])
    out["rows"] = rows
    return out


# --- 10. pd_apply ------------------------------------------------------------------------------

APPLY_CHANNELS = ("card", "cash", "app")


def _half_even(x: Fraction) -> int:
    """Округление до целого «к чётному» — как round в pandas и numpy."""
    import math
    lo = math.floor(x)
    rest = x - lo
    if rest > Fraction(1, 2) or (rest == Fraction(1, 2) and lo % 2):
        return lo + 1
    return lo


def apply_data(rng, variant: int) -> dict:
    """A — комиссии по ставкам канала (.map со словарём; ловушка — ставки в процентах без
    деления на 100); B — суммы, округлённые вверх (.apply(math.ceil); ловушки — round и
    отбрасывание дробной части); C — .map, где у части каналов ставки нет (fillna; ловушка —
    пустые комиссии молча выпали из суммы)."""
    rows = transfers(rng, rng.randint(24, 40), rng.sample(CITIES, 5))
    out = {"header": ["id", "date", "city", "channel", "amount"]}
    if variant == 1:
        for r in rows:
            r["channel"] = rng.choice(APPLY_CHANNELS)
        # постройкой: есть сумма с копейками меньше 50 и сумма ровно .50 — ceil, round и
        # отбрасывание расходятся
        rows[0]["amount"] = rows[0]["amount"] // 100 * 100 + rng.randint(1, 40)
        rows[1]["amount"] = rows[1]["amount"] // 100 * 100 + 50
        import math
        up = sum(math.ceil(Fraction(r["amount"], 100)) for r in rows)
        near = sum(_half_even(Fraction(r["amount"], 100)) for r in rows)
        down = sum(r["amount"] // 100 for r in rows)
        out.update(answer=str(up), traps=[["round", str(near)], ["int", str(down)]])
        out["rows"] = rows
        return out
    rates = dict(zip(APPLY_CHANNELS, rng.sample((0, 1, 2, 3), 3)))
    if variant == 2:
        rates = {k: v for k, v in rates.items() if v}       # без нулевой ставки
        rates = dict(list(rates.items())[:2])
        known = sorted(rates)
        extra = [c for c in APPLY_CHANNELS + ("wire", "qr") if c not in rates][:2]
        default = rng.choice([v for v in (1, 2, 3, 4) if v not in rates.values()])
        for r in rows:
            r["channel"] = rng.choice(known + extra)
        rows[0]["channel"], rows[1]["channel"] = extra[0], known[0]
        fee = sum(Fraction(r["amount"] * rates.get(r["channel"], default), 10000) for r in rows)
        known_only = sum(Fraction(r["amount"] * rates[r["channel"]], 10000) for r in rows
                         if r["channel"] in rates)
        out.update(rates=rates, default=default, unknown=" и ".join(extra),
                   answer=frac_str(fee), traps=[["nan", frac_str(known_only)]])
    else:
        for r in rows:
            r["channel"] = rng.choice(APPLY_CHANNELS)
        rows[0]["channel"] = max(rates, key=lambda c: rates[c])     # ставка не 0 есть всегда
        fee = sum(Fraction(r["amount"] * rates[r["channel"]], 10000) for r in rows)
        out.update(rates=rates, answer=frac_str(fee), traps=[["percent", frac_str(fee * 100)]])
    out["rows"] = rows
    return out


def rates_dict(rates: Dict[str, int]) -> str:
    """Ставки в процентах → словарь Python для кода: {"card": 0.02, "cash": 0}."""
    def share(v):
        return "0" if v == 0 else f"0.0{v}"
    return "{" + ", ".join(f'"{k}": {share(rates[k])}' for k in sorted(rates)) + "}"


def rates_text(rates: Dict[str, int]) -> str:
    """Ставки словами для условия: card — 2 %, cash — 0 %."""
    return ", ".join(f"{k} — {rates[k]} %" for k in sorted(rates))


# --- 11. pd_save -------------------------------------------------------------------------------

def save_data(rng, variant: int) -> dict:
    """A — переводы города в свой файл без индекса; B — весь файл с разделителем «;»; C — только
    city и amount, от большей суммы к меньшей (суммы разные — порядок однозначен)."""
    rows = transfers(rng, rng.randint(18, 30), rng.sample(CITIES, 4), ("channel",))
    seen = set()
    for r in rows:                      # суммы без повторов: порядок сортировки однозначен
        while r["amount"] in seen:
            r["amount"] += 1
        seen.add(r["amount"])
    header = header_of(("channel",))
    out = {"rows": rows, "header": header}
    if variant == 0:
        city = rng.choice(sorted({r["city"] for r in rows}))
        out.update(city=city, out=f"{city.lower()}.csv",
                   want_header=header, want=[r["id"] for r in rows if r["city"] == city])
    elif variant == 1:
        out.update(out="excel.csv", want_header=header, want=[r["id"] for r in rows])
    else:
        order = sorted(rows, key=lambda r: -r["amount"])
        out.update(out="top.csv", want_header=["city", "amount"], want=[r["id"] for r in order])
    return out


# --- 12. pd_sql --------------------------------------------------------------------------------

BANK = "bank.db"
BANK_SCHEMA = (
    "CREATE TABLE accounts (account INTEGER PRIMARY KEY, name TEXT NOT NULL, tier TEXT)",
    "CREATE TABLE transfers (id INTEGER PRIMARY KEY, date TEXT, account INTEGER, amount REAL)",
)
PAYMENTS = "payments.csv"


def bank_bytes(accounts: List[dict], rows: List[dict]) -> bytes:
    from termit_app.tasks import dbkit
    return dbkit.build_sqlite(BANK_SCHEMA, {
        "accounts": (ACC_HEADER, [(a["account"], a["name"], a["tier"]) for a in accounts]),
        "transfers": (TR_HEADER, [(r["id"], r["date"], r["account"], r["amount"] / 100)
                                  for r in rows])})


def sql_data(rng, variant: int) -> dict:
    """A — переводов дороже порога (read_sql; строка ровно на пороге — ловушка >=); B — кто
    перевёл больше всех со всех своих счетов (JOIN и GROUP BY в SQL; ловушка — хозяин самого
    крупного одного счёта); C — payments.csv в новую таблицу payments (to_sql, index=False)."""
    accounts = _accounts(rng, rng.randint(8, 11))
    rows = _account_transfers(rng, accounts, rng.randint(26, 44), accounts)
    out = {"accounts": accounts, "rows": rows}
    if variant == 0:
        mid = sorted(rows, key=lambda r: (r["amount"], r["id"]))[len(rows) // 2]
        limit = mid["amount"] // 100
        mid["amount"] = limit * 100
        gt = sum(r["amount"] > limit * 100 for r in rows)
        ge = sum(r["amount"] >= limit * 100 for r in rows)
        out.update(limit=limit, answer=str(gt), traps=[["edge", str(ge)]])
    elif variant == 1:
        # постройкой: у лидера два счёта, у другого — самый крупный один счёт
        lead, solo, extra = rng.sample(accounts, 3)
        extra["name"] = lead["name"]
        for r in rows:
            r["name"] = next(a["name"] for a in accounts if a["account"] == r["account"])
        per_acc: Dict[int, int] = {}
        for r in rows:
            per_acc[r["account"]] = per_acc.get(r["account"], 0) + r["amount"]
        big = max(per_acc.values())
        bump = big + 5000 - per_acc[solo["account"]]
        next(r for r in rows if r["account"] == solo["account"])["amount"] += bump
        per_acc[solo["account"]] += bump
        # оба счёта лидера — меньше одного счёта solo, а вместе — больше
        target = per_acc[solo["account"]] * 3 // 5 + 3000
        for acc in (lead, extra):
            have = per_acc.get(acc["account"], 0)
            if have < target:
                next(r for r in rows if r["account"] == acc["account"])["amount"] += target - have
                per_acc[acc["account"]] = target
        per_name: Dict[str, int] = {}
        for a in accounts:
            per_name[a["name"]] = per_name.get(a["name"], 0) + per_acc.get(a["account"], 0)
        top = max(per_name.values())
        for name, s in per_name.items():
            assert name == lead["name"] or s < top
        assert max(per_acc.values()) == per_acc[solo["account"]]
        out.update(answer=lead["name"], traps=[["account", solo["name"]]])
    else:
        pays = [{"id": 501 + i, "account": rng.choice(accounts)["account"],
                 "amount": rng.randint(5, 400) * 100 + rng.randint(0, 99)}
                for i in range(rng.randint(6, 12))]
        out.update(payments=pays)
    return out


def payments_csv(pays: List[dict]) -> str:
    return csv_text(["id", "account", "amount"],
                    [[p["id"], p["account"], money(p["amount"])] for p in pays])


# --- 13. rq_get: курсы валют с учебного API --------------------------------------------------

BASES = ("USD", "EUR")
CURRENCIES = ("GBP", "JPY", "CHF", "CNY", "INR", "BRL", "SEK", "PLN", "NOK", "CAD")
RATES_HEADER = ["base", "currency", "rate"]
REQUESTS_AGENT = "python-requests/"     # User-Agent запросов requests (версия — после «/»)
KEY_VAR = "RATES_KEY"


def rates_items(rng) -> List[dict]:
    """Курсы: [{"base", "currency", "rate"}] — у каждой базы свои 3–5 валют, курс — до 4 знаков."""
    out = []
    for b in BASES:
        for c in rng.sample(CURRENCIES, rng.randint(3, 5)):
            out.append({"base": b, "currency": c,
                        "rate": round(rng.randint(500, 1600000) / 10000, 4)})
    rng.shuffle(out)
    return out


def rates_data(rng, variant: int) -> dict:
    """A — все курсы (GET с timeout); B — только база base (params; ловушка — все базы); C —
    ключ в заголовке X-Api-Key из переменной окружения (без ключа — 401)."""
    items = rates_items(rng)
    out = {"rates": items, "expect": items, "traps": []}
    if variant == 1:
        base = rng.choice(BASES)
        out.update(base=base, expect=[x for x in items if x["base"] == base],
                   traps=[["all", items]])
    elif variant == 2:
        out["key"] = "k-" + "".join(rng.choice("abcdefghjkmnpqrstuvwxyz23456789")
                                    for _ in range(12))
    return out


def rates_handler(items: List[dict], key: Optional[str]):
    """GET /rates учебного API: ?base=USD — фильтр; key — нужен заголовок X-Api-Key (иначе 401).
    Данные — из state задачи, из песочницы сервер ничего не читает."""
    def handle(req):
        if key is not None and req.headers.get("x-api-key") != key:
            return 401, {"error": "no key: send it in the X-Api-Key header"}
        base = (req.query.get("base") or [None])[0]
        if base is not None and base not in BASES:
            return 404, {"error": "no such base", "bases": list(BASES)}
        return 200, {"items": [x for x in items if base is None or x["base"] == base]}
    return handle


def rates_routes(state: dict) -> dict:
    return {"/": (200, {"routes": ["/rates", "/rates?base=USD"]}),
            "/rates": rates_handler(state["rates"], state.get("key"))}


# --- страж boss_pylib: мини-конвейер API → проверка → таблица → отчёт -------------------------

CLIENTS_KEY = "CLIENTS_KEY"
CLIENTS_HEADER = ["client", "name", "city", "tier"]
BOSS_TR_HEADER = ["id", "date", "client", "name", "amount"]
BOSS_DIRTY = ("1 200", "?", "12,5", "n/a?", "—")
# группа и мера отчёта у варианта: A — сумма по городам, B — число переводов по городам,
# C — сумма по уровню клиента
BOSS_REPORT = (("city", "sum"), ("city", "count"), ("tier", "sum"))


def _boss_clients(rng) -> List[dict]:
    """Клиенты: номера 301…, у одного имени — тёзка из другого города и другого уровня."""
    n = rng.randint(8, 11)
    names = rng.sample(NAMES, n)
    out = [{"client": 301 + i, "name": names[i], "city": rng.choice(CITIES[:6]),
            "tier": rng.choice(TIERS)} for i in range(n)]
    a, b = rng.sample(out, 2)
    b["name"] = a["name"]
    if b["city"] == a["city"]:
        b["city"] = rng.choice([c for c in CITIES[:6] if c != a["city"]])
    if b["tier"] == a["tier"]:
        b["tier"] = rng.choice([t for t in TIERS if t != a["tier"]])
    return out


def _report(clients: List[dict], rows: List[dict], variant: int, by_name: bool) -> Dict[str, int]:
    """Отчёт по группам: суммы в копейках (A, C) или число переводов (B). by_name — склейка по
    имени (ловушка): перевод тёзки идёт во все совпавшие строки клиентов."""
    key, how = BOSS_REPORT[variant]
    out: Dict[str, int] = {}
    for r in rows:
        if not isinstance(r["amount"], int):
            continue
        if by_name:
            match = [c for c in clients if c["name"] == r["name"]]
        else:
            match = [c for c in clients if c["client"] == r["client"]]
        for c in match:
            out[c[key]] = out.get(c[key], 0) + (1 if how == "count" else r["amount"])
    return out


def boss_pylib_data(rng, variant: int) -> dict:
    """Клиенты на API двумя страницами (с ключом), transfers.csv с битыми суммами. Ответы —
    объекты для сравнения: все клиенты, чистые переводы (битые суммы — пусто), отчёт по
    группам (без ничьих: соседние итоги разведены) и ловушки — первая страница, склейка по
    имени."""
    clients = _boss_clients(rng)
    rows = []
    for i in range(rng.randint(30, 46)):
        c = rng.choice(clients)
        rows.append({"id": 101 + i, "date": _date(rng), "client": c["client"], "name": c["name"],
                     "amount": rng.randint(5, 900) * 100 + rng.randint(0, 99)})
    for c in clients:                       # у каждого клиента хотя бы один перевод
        if not any(r["client"] == c["client"] for r in rows):
            rows[rng.randrange(len(rows))].update(client=c["client"], name=c["name"])
    twin = next(c["name"] for c in clients if sum(x["name"] == c["name"] for x in clients) > 1)
    for c in clients:                       # и у тёзок тоже — постройкой, а не удачей
        if c["name"] == twin and not any(r["client"] == c["client"] for r in rows):
            rows.append({"id": 101 + len(rows), "date": _date(rng), "client": c["client"],
                         "name": c["name"], "amount": rng.randint(5, 900) * 100})
    dirty = rng.sample(range(len(rows)), rng.randint(2, 5))
    for k, i in enumerate(dirty):
        rows[i]["amount"] = BOSS_DIRTY[0] if k == 0 else rng.choice(BOSS_DIRTY)
    key, how = BOSS_REPORT[variant]
    # развести итоги групп: соседние отличаются хотя бы на 2.00 (сумма) или на 1 (число)
    for _ in range(50):
        rep = _report(clients, rows, variant, False)
        order = sorted(rep, key=lambda g: (rep[g], g))
        clash = [(a, b) for a, b in zip(order, order[1:])
                 if rep[b] - rep[a] < (1 if how == "count" else GAP)]
        if not clash:
            break
        hi = clash[0][1]
        donor = next(r for r in rows if isinstance(r["amount"], int)
                     and next(c for c in clients if c["client"] == r["client"])[key] == hi)
        if how == "count":
            extra = dict(donor, id=101 + len(rows))
            rows.append(extra)
        else:
            donor["amount"] += GAP
    rep = _report(clients, rows, variant, False)
    wrong = _report(clients, rows, variant, True)
    per = (len(clients) + 1) // 2

    def value(v: int) -> str:
        return str(v) if how == "count" else money(v)
    report = [[g, value(rep[g])] for g in sorted(rep, key=lambda g: -rep[g])]
    clean = [[str(r["id"]), r["date"], str(r["client"]), r["name"],
              money(r["amount"]) if isinstance(r["amount"], int) else ""] for r in rows]
    return {"clients": clients, "per_page": per, "rows": rows, "clean": clean,
            "report_head": [key, "amount"], "report": report,
            "key": "c-" + "".join(rng.choice("abcdefghjkmnpqrstuvwxyz23456789")
                                  for _ in range(12)),
            "traps": [["first", clients[:per]],
                      ["name", [[g, value(wrong[g])]
                                for g in sorted(wrong, key=lambda g: -wrong[g])]],
                      ["asc", list(reversed(report))]]}


def boss_transfers_csv(rows: List[dict]) -> str:
    return csv_text(BOSS_TR_HEADER, [[r["id"], r["date"], r["client"], r["name"],
                                      money(r["amount"]) if isinstance(r["amount"], int)
                                      else r["amount"]] for r in rows])


def clients_handler(clients: List[dict], per_page: int, key: str):
    """GET /clients?page=N учебного API: ключ — заголовок X-Api-Key (иначе 401); ответ
    {"page", "next", "items"}; чужая страница — 404."""
    import math

    def handle(req):
        if req.headers.get("x-api-key") != key:
            return 401, {"error": "no key: send it in the X-Api-Key header"}
        raw = (req.query.get("page") or ["1"])[0]
        if not raw.isdigit():
            return 400, {"error": "page must be a page number: ?page=1"}
        page, pages = int(raw), max(1, math.ceil(len(clients) / per_page))
        if not 1 <= page <= pages:
            return 404, {"error": "no such page", "pages": pages}
        chunk = clients[(page - 1) * per_page:page * per_page]
        return 200, {"page": page, "next": page + 1 if page < pages else None, "items": chunk}
    return handle


def clients_routes(state: dict) -> dict:
    return {"/": (200, {"routes": ["/clients?page=N"]}),
            "/clients": clients_handler(state["clients"], state["per_page"], state["key"])}
