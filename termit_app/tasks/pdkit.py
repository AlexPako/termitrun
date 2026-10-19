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
from typing import Dict, List, Sequence, Tuple

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
