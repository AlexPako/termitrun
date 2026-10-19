"""Трио «Вместо Excel» (часть 5, I8): выгрузка заказов orders.csv. csv_by_hand — руками
(близнец qsv), csv_top — пара к qsv (и близнец duckdb), csv_sum — пара к duckdb. Временно
в треке finder (журнал решений, п. 7): часть 6 может перенести их в data без смены id.

Честная ловушка из жизни: адрес в кавычках с запятой внутри ("ul. Mira, 5") — одна ячейка,
а cut и awk на macOS (BSD awk 20200816, без --csv) режут по КАЖДОЙ запятой. Всё правее
адреса съезжает, левее — нет. Капризная колонка одна (адрес), поэтому встроенный путь
честный и надёжный: левые колонки (date, customer) — cut, правые (city, status, amount) —
awk со счётом справа: $NF, $(NF-1), $(NF-2). Решение «в лоб» (cut -d, -f5, awk $7)
гарантированно неверно: данные строятся так, что ловушка срабатывает при любом seed
(проверка — tests/test_sheets.py моделью тех же конвейеров). Утилиты читают кавычки сами —
это и есть «точность», которую они дают."""
import random
from collections import Counter
from pathlib import Path
from typing import Dict, List, Sequence

from termit_app import textnorm
from termit_app.tasks import kit
from termit_app.tasks.base import AnswerTask, Variant, variant_index

FILE = "orders.csv"
COLUMNS = ("order_id", "date", "customer", "address", "city", "status", "amount")
# Улица с именем города внутри (Kazanskaya ⊃ Kazan): grep без запятых по краям ловит и её.
# Omsk сидит и внутри Tomsk — ещё одна причина искать ячейку целиком.
CITY_STREET = {"Kazan": "Kazanskaya", "Perm": "Permskaya", "Omsk": "Omskaya",
               "Tver": "Tverskaya", "Sochi": "Sochinskaya", "Kursk": "Kurskaya",
               "Tomsk": "Tomskaya"}
CITIES = tuple(CITY_STREET)
STREETS = ("Lenina", "Mira", "Sadovaya", "Lesnaya", "Shkolnaya", "Zarechnaya", "Polevaya")
STATUSES = ("delivered", "shipped", "paid", "cancelled", "refunded", "cancelled_by_bank")
STATUS_WEIGHTS = (40, 20, 15, 10, 8, 7)
MONTHS = tuple(f"2026-{m:02d}" for m in range(1, 7))
# лишние колонки варианта «какая по счёту»: значения без запятых и не похожи на суммы
EXTRA = {"channel": ("web", "app", "phone", "shop"),
         "manager": ("ivanova", "petrov", "sidorova", "orlov", "kim"),
         "promo": ("", "", "", "SPRING10", "VIP5"),
         "courier": ("cdek", "boxberry", "pochta", "self")}
MARGIN = 25         # отрыв верного ответа и провала «в лоб» в задачах «самое частое»


# --- данные ------------------------------------------------------------------------------

def address(rng, quoted: bool, street: str = "") -> str:
    """Адрес: с запятой внутри (в CSV уйдёт в кавычках) или без неё."""
    street = street or rng.choice(STREETS + tuple(CITY_STREET.values()))
    n = rng.randint(1, 99)
    if not quoted:
        return f"{street} {n}"
    if rng.random() < 0.7:
        return f"ul. {street}, {n}"
    return f"pr. {street}, {n}, kv. {rng.randint(1, 200)}"


def quoted(row: dict) -> bool:
    return "," in row["address"]


def orders(rng, n: int = 0) -> List[dict]:
    """Заказы за полгода без order_id (его даёт finish). 20–24 тыс. строк: разница в скорости
    честная, а песочница собирается быстро. Около трети адресов — с запятой, 12 % пустые
    (самовывоз), 3 % заказов без клиента (гость). Случайное — пачками rng.choices: setup
    гоняют сотни раз (fuzz, линтер), построчные randint здесь — главная цена."""
    n = n or rng.randint(20000, 24000)
    pool = [f"C{x}" for x in rng.sample(range(1000, 10000), rng.randint(900, 1400))]

    def pick(seq, k=n, weights=None):
        return rng.choices(seq, weights, k=k)
    kinds = pick(("", "q", "p"), weights=(12, 33, 55))
    streets = pick(STREETS + tuple(CITY_STREET.values()))
    houses, flats = pick(range(1, 100)), pick(range(1, 201))
    forms = pick((1, 2), weights=(7, 3))
    addresses = [("" if kd == "" else f"{st} {h}" if kd == "p" else
                  f"ul. {st}, {h}" if f == 1 else f"pr. {st}, {h}, kv. {fl}")
                 for kd, st, h, fl, f in zip(kinds, streets, houses, flats, forms)]
    guests = pick((True, False), weights=(3, 97))
    custs = pick(pool)
    dates = [f"{m}-{d:02d}" for m, d in zip(pick(MONTHS), pick(range(1, 29)))]
    # пример карточки ',Kazan,' / Kazanskaya и ',Omsk,' / Tomsk — в любом файле
    addresses[0], cities = "Kazanskaya 3", pick(CITIES)
    cities[0], cities[1] = "Perm", "Tomsk"
    rows = [{"date": dt, "customer": "" if g else c, "address": ad, "city": ct,
             "status": stt, "amount": am}
            for dt, g, c, ad, ct, stt, am in zip(dates, guests, custs, addresses, cities,
                                                pick(STATUSES, weights=STATUS_WEIGHTS),
                                                pick(range(300, 10000)))]
    return rows


def finish(rows: List[dict]) -> List[dict]:
    """Как настоящая выгрузка: по дате, номера заказов подряд."""
    rows.sort(key=lambda r: r["date"])
    for i, r in enumerate(rows):
        r["order_id"] = 100001 + i
    return rows


def cell(value) -> str:
    s = str(value)
    if any(ch in s for ch in ',"\n'):
        return '"' + s.replace('"', '""') + '"'
    return s


def _addr(text: str) -> str:
    return f'"{text}"' if "," in text else text


def lines(rows: Sequence[dict], columns: Sequence[str] = COLUMNS) -> List[str]:
    if tuple(columns) == COLUMNS:   # быстрый путь: запятые бывают только в адресе
        body = [f'{r["order_id"]},{r["date"]},{r["customer"]},{_addr(r["address"])},'
                f'{r["city"]},{r["status"]},{r["amount"]}' for r in rows]
    else:
        body = [",".join(cell(r.get(c, "")) for c in columns) for r in rows]
    return [",".join(columns)] + body


def write(box: Path, rows: Sequence[dict], columns: Sequence[str] = COLUMNS) -> List[str]:
    out = lines(rows, columns)
    kit.write(Path(box) / FILE, "\n".join(out) + "\n")
    return out


def naive(line: str, k: int) -> str:
    """Поле k (с 1), как его видят cut -d, -fk и awk -F, '$k': по каждой запятой."""
    parts = line.split(",")
    return parts[k - 1] if k <= len(parts) else ""


def naive_row(row: dict, k: int) -> str:
    """То же поле k, но прямо по строке данных (колонки COLUMNS), без сборки файла."""
    fields = ([str(row.get("order_id", "")), row["date"], row["customer"]] +
              _addr(row["address"]).split(",") + [row["city"], row["status"], str(row["amount"])])
    return fields[k - 1] if k <= len(fields) else ""


def awk_number(text: str) -> int:
    """Как awk превращает поле в число для s+=: цифры в начале (после пробелов), иначе 0."""
    head = text.lstrip(" ")
    digits = ""
    for ch in head:
        if not ch.isdigit():
            break
        digits += ch
    return int(digits) if digits else 0


def requote(row: dict, rng, want: bool) -> None:
    if quoted(row) != want:
        row["address"] = address(rng, want)


def lead(counts: Counter, key) -> int:
    """На сколько key опережает лучшего из остальных (отрицательное — отстаёт)."""
    rest = [v for k, v in counts.items() if k != key]
    return counts.get(key, 0) - (max(rest) if rest else 0)


def push_top(rows: List[dict], field: str, value: str, rng, margin: int = MARGIN) -> None:
    """Сделать value самым частым в field с отрывом margin: забирать строки у лидера."""
    counts = Counter(r[field] for r in rows)
    by: Dict[str, List[dict]] = {}
    for r in rows:
        by.setdefault(r[field], []).append(r)
    for bucket in by.values():
        rng.shuffle(bucket)
    while lead(counts, value) < margin:
        leader = max((k for k in counts if k != value), key=lambda k: (counts[k], k))
        r = by[leader].pop()
        r[field] = value
        counts[leader] -= 1
        counts[value] += 1


def sink_naive(rows: List[dict], candidates: List[dict], key, rng, seen,
               margin: int = MARGIN) -> None:
    """Кавычками утопить key в подсчёте «в лоб»: адреса строк-кандидатов — с запятой, пока
    key не отстанет от лучшего из остальных на margin. seen(row) — что видит неверный
    конвейер в строке: (ключ, вес) или None (строку он отбросил)."""
    counts = Counter()
    for r in rows:
        got = seen(r)
        if got:
            counts[got[0]] += got[1]
    plain = [r for r in candidates if not quoted(r)]
    rng.shuffle(plain)
    while lead(counts, key) > -margin:
        r = plain.pop()
        old = seen(r)
        requote(r, rng, True)
        new = seen(r)
        if old:
            counts[old[0]] -= old[1]
        if new:
            counts[new[0]] += new[1]


# --- задачи ------------------------------------------------------------------------------

class _Sheet(AnswerTask):
    track = "finder"
    # fuzz (T001, B001, «без действий») — 8 seed, а не TERMIT_FUZZ: setup строит 20+ тыс.
    # строк, а ловушки на 8 seed строже проверяет tests/test_sheets.py
    fuzz_seeds = 8
    kinds: Sequence[str] = ("number", "number", "number")    # как сверять ответ по варианту

    def matches(self, given, ctx):
        kind = self.kinds[variant_index(ctx.state.get("_variant"), len(self.variants))]
        if kind == "number":
            return textnorm.same_number(given, ctx.state["answer"])
        return textnorm.same_text(given, str(ctx.state["answer"]))

    fallback = ("Не то. Кавычки с запятой внутри — одна ячейка, а cut и awk режут по каждой "
                "запятой. Проверь, не съехали ли колонки, и набери hint.")

    def answer_kind(self, state):
        return self.kinds[variant_index(state.get("_variant"), len(self.variants))]


class CsvByHand(_Sheet):
    """Новая карточка «выгрузка без Excel»: head, tr, cut, tail, grep -c по ячейке целиком."""
    id = "csv_by_hand"
    title = "Выгрузка без Excel"
    after = ("boss_finder",)
    scroll = ("head -3 orders.csv — заголовок и первые строки; head -1 orders.csv | tr , '\\n' "
              "| grep -n city — какая по счёту колонка city.\n"
              "cut -d, -f3 orders.csv — третья колонка (d — delimiter, f — fields); tail -n +2 "
              "— без заголовка (n — number).\n"
              "grep -c ',Kazan,' orders.csv — count строк с ячейкой ровно Kazan (не "
              "Kazanskaya). \"ul. Mira, 5\" в кавычках — одна ячейка, а cut режет и её.")
    variants = (
        Variant("Выгрузка заказов orders.csv — десятки тысяч строк, глазами не пересчитать. "
                "Сколько в ней заказов из города {city}? Ответ — число: ans ЧИСЛО",
                wrong=("grep -c '{city}' orders.csv",
                       "cut -d, -f5 orders.csv | grep -c '{city}'"),
                alternatives=("grep ',{city},' orders.csv | wc -l — то же через подсчёт строк",)),
        Variant("В выгрузку orders.csv добавили колонок, и порядок поехал. Какая по счёту "
                "колонка amount (сумма заказа)? Считай слева, первая — 1. Ответ — число: "
                "ans ЧИСЛО",
                hints=("Имена колонок — в первой строке: head -1 orders.csv.",
                       "tr , '\\n' поставит каждое имя на свою строку, а grep -n пронумерует "
                       "найденное.",
                       "head -1 orders.csv | tr , '\\n' | grep -n amount — номер перед "
                       "двоеточием"),
                solution="head -1 orders.csv | tr , '\\n' | grep -n amount",
                solution_script="head -1 orders.csv | tr , '\\n' | grep -nx amount | "
                                "cut -d: -f1",
                wrong=("sed -n 2p orders.csv | tr , '\\n' | grep -nx '{amount2}' | cut -d: -f1",
                       "head -1 orders.csv | tr , '\\n' | wc -l"),
                alternatives=("head -1 orders.csv | tr , '\\n' | cat -n — cat -n пронумерует "
                              "строки: все имена разом",)),
        Variant("Сколько заказов в orders.csv со статусом ровно cancelled? Похожие статусы — "
                "например cancelled_by_bank — это другое, их не считай. Ответ — число: "
                "ans ЧИСЛО",
                hints=("Статус — одна из колонок; head -3 orders.csv покажет, какие бывают.",
                       "grep -c 'cancelled' зацепит и cancelled_by_bank. Ищи ячейку целиком — "
                       "с запятыми по краям.",
                       "grep -c ',cancelled,' orders.csv"),
                solution="grep -c ',cancelled,' orders.csv",
                wrong=("grep -c cancelled orders.csv",
                       "cut -d, -f6 orders.csv | grep -cx cancelled"),
                alternatives=("grep ',cancelled,' orders.csv | wc -l — то же через подсчёт "
                              "строк",)),
    )
    par = 60
    hints = ("Сначала посмотри, что внутри: head -3 orders.csv — заголовок и пара строк.",
             "grep -c считает строки с текстом. Но {city} бывает и в названии улицы — ищи "
             "ячейку целиком, с запятыми по краям.",
             "grep -c ',{city},' orders.csv")
    solution = "grep -c ',{city},' orders.csv"
    explain = ("CSV — текст, где ячейки разделены запятыми. Запятые по краям ',Kazan,' "
               "находят ячейку целиком. Но ячейка в кавычках может прятать свою запятую — "
               "тогда cut считает колонки неверно, и всё правее съезжает.")
    spell = "grep -c ',ячейка,' файл.csv — сколько строк с ячейкой ровно такой"

    def setup_variant(self, box, rng, variant):
        rows = orders(rng)
        if variant == 1:
            return self._columns(box, rng, rows)
        if variant == 2:
            rng.choice([r for r in rows if r["status"] != "cancelled"])["status"] = \
                "cancelled_by_bank"
            requote(rng.choice([r for r in rows if r["status"] == "cancelled"]), rng, True)
            write(box, finish(rows))
            return {"answer": sum(r["status"] == "cancelled" for r in rows)}
        city = rng.choice(CITIES)
        mine = [r for r in rows if r["city"] == city]
        requote(rng.choice(mine), rng, True)            # cut -f5 его теряет
        other = rng.choice([r for r in rows if r["city"] != city])
        other["address"] = address(rng, rng.random() < 0.5, CITY_STREET[city])  # grep ловит
        write(box, finish(rows))
        return {"city": city, "answer": len(mine)}

    @staticmethod
    def _columns(box, rng, rows):
        """Лишние колонки в случайных местах; amount никогда не последняя (иначе число колонок
        совпало бы с ответом). В первой строке данных адрес — с запятой: счёт по ней врёт."""
        cols = list(COLUMNS)
        extra = rng.sample(sorted(EXTRA), rng.randint(1, 3))
        for name in extra:
            cols.insert(rng.randint(0, len(cols)), name)
        if cols[-1] == "amount":
            cols.remove(extra[0])
            cols.append(extra[0])
        for r in rows:
            for name in extra:
                r[name] = rng.choice(EXTRA[name])
        finish(rows)
        requote(rows[0], rng, True)
        write(box, rows, cols)
        return {"answer": cols.index("amount") + 1, "amount2": rows[0]["amount"]}


class CsvTop(_Sheet):
    """Пара к qsv: самое частое и уникальное. Встроенный путь — sort | uniq -c | sort -n."""
    id = "csv_top"
    title = "Самое частое"
    implant = "qsv"
    after = ("csv_by_hand", "boss_finder")
    kinds = ("text", "number", "text")
    scroll = ("sort | uniq -c | sort -n | tail -1 — самое частое: uniq -c (count) считает "
              "одинаковые строки подряд, поэтому сначала sort; sort -n — numeric, sort -u — "
              "unique.\n"
              "Кавычки с запятой ломают cut — считай справа: awk -F, '{ print $NF }' — "
              "последнее поле (F — Field separator), $(NF-1) — предпоследнее. Утилита qsv "
              "понимает кавычки сама: qsv frequency -s city orders.csv (s — select)")
    variants = (
        Variant("В orders.csv — заказы за полгода. Из какого города заказывают чаще всего? "
                "Ответ — название, как в таблице: ans ГОРОД",
                wrong=("cut -d, -f5 orders.csv | tail -n +2 | sort | uniq -c | sort -n | "
                       "tail -1 | awk '{{print $2}}'",),
                alternatives=("qsv frequency -s city orders.csv — частоты колонки с учётом "
                              "кавычек",)),
        Variant("Сколько разных клиентов в orders.csv? Клиент — код в колонке customer. Гостевой "
                "заказ без кода (пустая ячейка) — не клиент, заголовок — тоже. Ответ — число: "
                "ans ЧИСЛО",
                hints=("customer — третья колонка, левее адреса с кавычками: тут cut -d, -f3 не "
                       "врёт.",
                       "sort -u оставит каждого по разу; заголовок срежет tail -n +2, а grep -c . "
                       "посчитает только непустые строки.",
                       "cut -d, -f3 orders.csv | tail -n +2 | sort -u | grep -c . — утилитой: "
                       "qsv search -s customer . orders.csv | qsv select customer | qsv dedup | "
                       "qsv count"),
                solution="cut -d, -f3 orders.csv | tail -n +2 | sort -u | grep -c .",
                solution_script="cut -d, -f3 orders.csv | tail -n +2 | sort -u | grep -c .",
                implant_script="qsv search -s customer . orders.csv | qsv select customer | "
                               "qsv dedup | qsv count",
                wrong=("cut -d, -f3 orders.csv | sort -u | wc -l",
                       "cut -d, -f3 orders.csv | tail -n +2 | sort -u | wc -l"),
                alternatives=("qsv select customer orders.csv | qsv dedup | qsv count — и "
                              "вычесть пустую ячейку, если она есть",)),
        Variant("Какой статус чаще всего у заказов за {month}? Дата — в колонке date, вид "
                "ГГГГ-ММ-ДД. Ответ — статус, как в таблице: ans СТАТУС",
                hints=("Заказы месяца оставит grep ',{month}-': дата — вторая колонка, перед ней "
                       "запятая.",
                       "Статус правее адреса с кавычками — считай справа: awk -F, "
                       "'{{print $(NF-1)}}' печатает второе поле с конца.",
                       "grep ',{month}-' orders.csv | awk -F, '{{print $(NF-1)}}' | sort | "
                       "uniq -c | sort -n | tail -1 — утилитой: qsv search -s date '^{month}' "
                       "orders.csv | qsv frequency -s status"),
                solution="grep ',{month}-' orders.csv | awk -F, '{{print $(NF-1)}}' | sort | "
                         "uniq -c | sort -n | tail -1",
                solution_script="grep ',{month}-' orders.csv | awk -F, '{{print $(NF-1)}}' | "
                                "sort | uniq -c | sort -n | tail -1 | awk '{{print $2}}'",
                implant_script="qsv search -s date '^{month}' orders.csv | qsv frequency -s "
                               "status | sed -n 2p | cut -d, -f2",
                wrong=("grep ',{month}-' orders.csv | cut -d, -f6 | sort | uniq -c | sort -n | "
                       "tail -1 | awk '{{print $2}}'",
                       "awk -F, 'NR>1 {{print $(NF-1)}}' orders.csv | sort | uniq -c | sort -n | "
                       "tail -1 | awk '{{print $2}}'"),
                alternatives=("qsv search -s date '^{month}' orders.csv | qsv frequency -s "
                              "status",)),
    )
    par = 90
    hints = ("Самое частое значение колонки: вырезать её, sort | uniq -c посчитает одинаковые, "
             "sort -n поставит самое частое в конец.",
             "cut тут врёт: в адресах кавычки с запятыми, всё правее адреса съезжает. Город — "
             "третье поле с конца: awk -F, '{{print $(NF-2)}}'.",
             "awk -F, '{{print $(NF-2)}}' orders.csv | tail -n +2 | sort | uniq -c | sort -n | "
             "tail -1 — утилитой: qsv frequency -s city orders.csv")
    solution = ("awk -F, '{{print $(NF-2)}}' orders.csv | tail -n +2 | sort | uniq -c | "
                "sort -n | tail -1")
    solution_script = solution + " | awk '{{print $2}}'"
    # без --limit: значений меньше 10 (лимит по умолчанию), строки Other нет; вывод — по
    # убыванию, вторая строка (после шапки field,value,count,…) — лидер
    implant_script = "qsv frequency -s city orders.csv | sed -n 2p | cut -d, -f2"
    explain = ("sort | uniq -c | sort -n — частотный словарь из трёх команд. awk -F, режет по "
               "каждой запятой и кавычек не понимает; спасает счёт справа ($NF), пока капризная "
               "колонка одна. Проверь это: awk -F, '{print NF}' f | sort | uniq -c — без "
               "кавычек 7 полей, с ними 8–9. Лишние запятые в двух колонках — справа тоже врёт, "
               "нужен разборщик CSV: qsv или duckdb.")
    spell = "sort | uniq -c | sort -n | tail -1 — самое частое значение"

    def setup_variant(self, box, rng, variant):
        rows = orders(rng)
        if variant == 1:
            rng.choice(rows)["customer"] = ""
            write(box, finish(rows))
            return {"answer": len({r["customer"] for r in rows} - {""})}
        if variant == 2:
            return self._month(box, rng, rows)
        city = rng.choice(CITIES)
        push_top(rows, "city", city, rng)
        # cut -d, -f5 | sort | uniq -c: у строк с кавычками в поле 5 — кусок адреса
        sink_naive(rows, [r for r in rows if r["city"] == city], city, rng,
                   lambda r: (naive_row(r, 5), 1))
        write(box, finish(rows))
        return {"answer": city}

    @staticmethod
    def _month(box, rng, rows):
        """В месяце лидирует shipped или paid (за полгода — delivered: без фильтра месяца —
        мимо); в подсчёте «в лоб» (cut -f6) лидер месяца тонет под кавычками."""
        month = rng.choice(MONTHS)
        status = rng.choice(("shipped", "paid"))
        inside = [r for r in rows if r["date"].startswith(month)]
        push_top(inside, "status", status, rng)
        # без фильтра месяца лидер другой — построением, а не весами статусов
        overall = Counter(r["status"] for r in rows)
        outside = [r for r in rows if r["status"] == status and not r["date"].startswith(month)]
        rng.shuffle(outside)
        while lead(overall, status) > -MARGIN:
            r = outside.pop()
            r["status"] = "delivered"
            overall[status] -= 1
            overall["delivered"] += 1
        # grep месяца | cut -d, -f6: у строк с кавычками в поле 6 — город или кусок адреса
        sink_naive(inside, [r for r in inside if r["status"] == status], status, rng,
                   lambda r: (naive_row(r, 6), 1))
        write(box, finish(rows))
        return {"month": month, "answer": status}


class CsvSum(_Sheet):
    """Пара к duckdb: суммы и средние awk-ом со счётом справа."""
    id = "csv_sum"
    title = "Подбить кассу"
    implant = "duckdb"
    after = ("csv_top", "boss_finder")
    kinds = ("number", "text", "number")
    scroll = ("awk -F, '$(NF-2)==\"Kazan\" { s += $NF } END { print s }' f — отбор строк, "
              "копилка, итог в END; $NF у нас — amount, сумма заказа.\n"
              "s[ключ] += $NF — копилка на ключ, END { for (k in s) print s[k], k } — обход. "
              "NR>1 — без заголовка, substr($2,1,7) — 7 знаков.\n"
              "Утилита duckdb спрашивает файл на SQL: duckdb -c \"SELECT sum(amount) FROM "
              "'orders.csv'\" (c — command)")
    variants = (
        Variant("Сколько денег принесли заказы из города {city}? Сложи колонку amount по всем "
                "его заказам, статус не важен. Ответ — число: ans ЧИСЛО",
                wrong=("awk -F, '$5==\"{city}\" {{s+=$7}} END {{print s}}' orders.csv",
                       "grep '{city}' orders.csv | awk -F, '{{s+=$NF}} END {{print s}}'"),
                implant_script="duckdb -noheader -list -c \"SELECT sum(amount) FROM "
                               "'orders.csv' WHERE city = '{city}'\"",
                alternatives=("duckdb -c \"SELECT sum(amount) FROM 'orders.csv' WHERE "
                              "city = '{city}'\"",)),
        Variant("В каком месяце выручка — сумма amount всех заказов месяца — была больше всего? "
                "Ответ — месяц, как в датах: ans ГГГГ-ММ",
                hints=("Копилка на каждый месяц — массив awk: s[ключ]+=$NF. Месяц — первые 7 "
                       "знаков даты: substr($2,1,7).",
                       "В END обойди копилки: for (m in s) print s[m], m — а sort -n поставит "
                       "самую большую в конец. Заголовок пропустит NR>1.",
                       "awk -F, 'NR>1 {{s[substr($2,1,7)]+=$NF}} END {{for (m in s) print s[m], "
                       "m}}' orders.csv | sort -n | tail -1 — утилитой: duckdb, GROUP BY месяц"),
                solution="awk -F, 'NR>1 {{s[substr($2,1,7)]+=$NF}} END {{for (m in s) print "
                         "s[m], m}}' orders.csv | sort -n | tail -1",
                solution_script="awk -F, 'NR>1 {{s[substr($2,1,7)]+=$NF}} END {{for (m in s) "
                                "print s[m], m}}' orders.csv | sort -n | tail -1 | "
                                "awk '{{print $2}}'",
                implant_script="duckdb -noheader -list -c \"SELECT left(CAST(date AS VARCHAR), "
                               "7) FROM 'orders.csv' GROUP BY 1 ORDER BY sum(amount) DESC "
                               "LIMIT 1\"",
                wrong=("awk -F, 'NR>1 {{s[substr($2,1,7)]+=$7}} END {{for (m in s) print s[m], "
                       "m}}' orders.csv | sort -n | tail -1 | awk '{{print $2}}'",),
                alternatives=("duckdb -c \"SELECT left(CAST(date AS VARCHAR), 7) m, "
                              "sum(amount) FROM 'orders.csv' GROUP BY m ORDER BY 2\"",)),
        Variant("Какой средний чек у клиента {cust}? Средний чек — сумма amount его заказов, "
                "делённая на их число. Ответ — число: ans ЧИСЛО",
                hints=("Клиент — третья колонка: условие $3==\"{cust}\" отберёт его строки.",
                       "Копи сумму и счётчик: {{s+=$NF; n++}}, а в END подели: print s/n. "
                       "amount — последнее поле, $NF.",
                       "awk -F, '$3==\"{cust}\" {{s+=$NF; n++}} END {{print s/n}}' orders.csv — "
                       "утилитой: duckdb -c \"SELECT avg(amount) FROM 'orders.csv' WHERE "
                       "customer='{cust}'\""),
                solution="awk -F, '$3==\"{cust}\" {{s+=$NF; n++}} END {{print s/n}}' orders.csv",
                implant_script="duckdb -noheader -list -c \"SELECT avg(amount)::INT FROM "
                               "'orders.csv' WHERE customer = '{cust}'\"",
                wrong=("awk -F, '$3==\"{cust}\" {{s+=$7; n++}} END {{print s/n}}' orders.csv",
                       "awk -F, '$3==\"{cust}\" {{s+=$NF}} END {{print s}}' orders.csv"),
                alternatives=("duckdb -c \"SELECT avg(amount) FROM 'orders.csv' WHERE "
                              "customer = '{cust}'\"",)),
    )
    par = 90
    hints = ("Складывает awk: s+=$NF копит последнее поле, END {{print s}} печатает итог.",
             "Свои строки отбери условием перед действием: $(NF-2)==\"{city}\" — город третий "
             "с конца, правее кавычек адреса.",
             "awk -F, '$(NF-2)==\"{city}\" {{s+=$NF}} END {{print s}}' orders.csv — утилитой: "
             "duckdb -c \"SELECT sum(amount) FROM 'orders.csv' WHERE city='{city}'\"")
    solution = "awk -F, '$(NF-2)==\"{city}\" {{s+=$NF}} END {{print s}}' orders.csv"
    explain = ("awk — маленький язык для колонок: условие { действие }, END — в конце. "
               "Копилка s[ключ] даёт итоги по группам. Кавычек BSD awk не понимает — считай "
               "справа. duckdb читает CSV по правилам и отвечает на SQL.")
    spell = "awk -F, '{s+=$NF} END {print s}' f.csv — сумма последней колонки"

    def setup_variant(self, box, rng, variant):
        rows = orders(rng)
        if variant == 1:
            return self._month(box, rng, rows)
        if variant == 2:
            return self._average(box, rng, rows)
        city = rng.choice(CITIES)
        requote(rng.choice([r for r in rows if r["city"] == city]), rng, True)    # $5 теряет
        other = rng.choice([r for r in rows if r["city"] != city])
        other["address"] = address(rng, rng.random() < 0.5, CITY_STREET[city])     # grep лишний
        write(box, finish(rows))
        return {"city": city, "answer": sum(r["amount"] for r in rows if r["city"] == city)}

    @staticmethod
    def _month(box, rng, rows):
        """Лидер по выручке — с отрывом; в сумме «в лоб» ($7: у строк с кавычками там статус
        или город, то есть 0) он тонет."""
        month = rng.choice(MONTHS)
        sums = Counter()
        for r in rows:
            sums[r["date"][:7]] += r["amount"]
        others = [r for r in rows if not r["date"].startswith(month)]
        rng.shuffle(others)
        while lead(sums, month) < 50000:
            r = others.pop()
            sums[r["date"][:7]] -= r["amount"]
            r["date"] = month + r["date"][7:]
            sums[month] += r["amount"]

        # s[месяц]+=$7: у строк с кавычками в поле 7 — статус или город, для awk это 0
        sink_naive(rows, [r for r in rows if r["date"].startswith(month)], month, rng,
                   lambda r: (r["date"][:7], awk_number(naive_row(r, 7))), margin=50000)
        write(box, finish(rows))
        return {"answer": month}

    @staticmethod
    def _average(box, rng, rows):
        """Клиент с 3+ заказами; среди них есть адрес с кавычками; сумма делится на число
        заказов — средний чек целый, без споров об округлении."""
        counts = Counter(r["customer"] for r in rows if r["customer"])
        cust = rng.choice(sorted(c for c, n in counts.items() if n >= 3))
        mine = [r for r in rows if r["customer"] == cust]
        requote(rng.choice(mine), rng, True)
        total = sum(r["amount"] for r in mine)
        mine[0]["amount"] -= total % len(mine)
        write(box, finish(rows))
        return {"cust": cust, "answer": sum(r["amount"] for r in mine) // len(mine)}


TASKS = [CsvByHand(), CsvTop(), CsvSum()]
