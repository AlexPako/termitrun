"""Трек «Аналитика», FB21: регулярки в pandas — .str.contains (отбор строк по шаблону, case),
.str.extract (кусок из скобок) и .nunique. Знаки шаблонов — из блока «Регулярки» трека
«Данные».

Правила — как у pdmore.py: запас full, ответ считает чистый Python у родителя по строкам
генератора, код игрока родитель не исполняет. В memo нет пустых ячеек: .str.contains на NaN
дал бы NaN, и отбор df[…] упал бы. В memo не больше одного номера счёта: .str.extract берёт
первое совпадение строки. Совпадение с настоящим pandas — живой тест
tests/test_pydata_live.py (нужен склад колёс)."""
import re
from typing import List

from termit_app.tasks import pdkit, pydata
from termit_app.tasks.base import Variant
from termit_app.tasks.pydata import PdAnswer, _pd

PAYMENTS = "payments.csv"
HEADER = ["id", "date", "city", "memo", "amount"]
INVOICE = re.compile(r"INV-[0-9]{4}")
MEMOS = ("pay {inv}", "Refund for {inv}", "refund {inv}", "REFUND {inv} late", "hold {inv}",
         "no invoice", "INV-{short} typo", "inv-{n} lowercase", "cash at desk")

_CONTAINS = 'print(len(df[df["memo"].str.contains(r"INV-[0-9]{{4}}")]))'
_CASE = 'print(df["memo"].str.contains("refund", case=False).sum())'
_EXTRACT = 'print(df["memo"].str.extract(r"(INV-[0-9]{{4}})")[0].nunique())'


def payments(rng) -> List[dict]:
    """Строки payments.csv: memo — из MEMOS, номеров счетов немного — они повторяются."""
    pool = [f"INV-{n}" for n in rng.sample(range(1000, 9999), rng.randint(5, 9))]
    rows = pdkit.transfers(rng, rng.randint(30, 50), rng.sample(pdkit.CITIES, 5))
    forms = list(MEMOS) + [rng.choice(MEMOS) for _ in range(len(rows) - len(MEMOS))]
    rng.shuffle(forms)
    for r, form in zip(rows, forms):
        r["memo"] = form.format(inv=rng.choice(pool), short=rng.randint(10, 99),
                                n=rng.randint(1000, 9999))
    return rows


class PdRegex(PdAnswer):
    """.str.contains(r"…") — отбор по регулярке, case=False — без регистра; .str.extract —
    кусок из скобок, .nunique — сколько разных."""
    id = "pd_regex"
    title = "Шаблоны в колонке"
    par = 75
    scroll = ("Текстовая колонка: df[\"note\"].str — приёмы для каждой ячейки. "
              ".str.contains(r\"шаблон\") — True там, где регулярка нашлась: "
              "df[df[\"note\"].str.contains(r\"ID-[0-9]+\")]; .str.contains(r\"ID\", case=False) — "
              "без учёта регистра.\n"
              ".str.extract(r\"(шаблон)\") — вынуть кусок из скобок, [0] — первая группа; "
              ".nunique() — сколько разных, пустые не в счёт.")
    variants = (
        Variant("В payments.csv у части платежей в memo — номер счёта: INV- и ровно четыре "
                "цифры. Сколько строк с таким номером? Обрывки вроде INV-12 не в счёт. "
                "ans ЧИСЛО",
                hints=("Отбор по регулярке — .str.contains(r\"…\") у колонки memo.",
                       "Шаблон — INV-, потом четыре цифры: [0-9]{{4}}; len(…) вокруг отбора. "
                       "Не забудь .venv.",
                       _pd(PAYMENTS, _CONTAINS) + " → ans ЧИСЛО"),
                solution=_pd(PAYMENTS, _CONTAINS),
                wrong=(_pd(PAYMENTS, 'print(len(df[df["memo"].str.contains("INV")]))'),),
                alternatives=("df[\"memo\"].str.contains(r\"INV-\\d{{4}}\").sum() — \\d тоже "
                              "цифра, True считается как 1",),
                key="contains"),
        Variant("Сколько платежей в payments.csv — возвраты: в memo есть слово refund в любом "
                "регистре — refund, Refund, REFUND? ans ЧИСЛО",
                hints=("Слово в колонке ищет .str.contains; регистр отключает case=False.",
                       ".str.contains(\"refund\", case=False) — True и False; .sum() сосчитает "
                       "True.",
                       _pd(PAYMENTS, _CASE) + " → ans ЧИСЛО"),
                solution=_pd(PAYMENTS, _CASE),
                wrong=(_pd(PAYMENTS, 'print(df["memo"].str.contains("refund").sum())'),),
                alternatives=("df[\"memo\"].str.lower().str.contains(\"refund\").sum() — "
                              "сначала всё в маленькие",),
                key="case"),
        Variant("Сколько разных номеров счетов (INV- и четыре цифры) упомянуто в memo "
                "payments.csv? Один счёт встречается по нескольку раз. ans ЧИСЛО",
                hints=("Номер из memo вынет .str.extract с группой ( ) в шаблоне.",
                       ".str.extract(r\"(…)\")[0] — колонка номеров; .nunique() — сколько "
                       "разных.",
                       _pd(PAYMENTS, _EXTRACT) + " → ans ЧИСЛО"),
                solution=_pd(PAYMENTS, _EXTRACT),
                wrong=(_pd(PAYMENTS, 'print(df["memo"].str.extract(r"(INV-[0-9]{{4}})")[0]'
                                     '.count())'),),
                alternatives=("set(df[\"memo\"].str.findall(r\"INV-[0-9]{{4}}\").sum()) и "
                              "len — то же через списки",),
                key="extract"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = (".str у колонки — те же регулярки, что в grep, только для каждой ячейки: "
               ".str.contains отбирает строки, case=False снимает регистр, .str.extract "
               "вынимает кусок из скобок, а .nunique считает разные.")
    spell = "df[\"c\"].str.contains(r\"…\"); case=False; .str.extract(r\"(…)\")[0].nunique()"
    trap_messages = {
        "typo": "Сюда попали обрывки вроде INV-12: «INV» — не номер. Номер — INV- и четыре "
                "цифры: r\"INV-[0-9]{{4}}\".",
        "case": "Это только refund маленькими: Refund и REFUND остались за бортом — "
                "case=False.",
        "repeats": "Это все упоминания, с повторами: .count() считает непустые. Разные — "
                   ".nunique().",
    }
    FALLBACKS = (
        "Не то. Отбери строки по шаблону номера: .str.contains(r\"…\") — и len(…).",
        "Не то. Слово refund в любом регистре: .str.contains(…, case=False).sum().",
        "Не то. Вынь номера .str.extract(r\"(…)\")[0] и посчитай разные: .nunique().",
    )

    def gen(self, rng, variant: int) -> dict:
        rows = payments(rng)
        memos = [r["memo"] for r in rows]
        if variant == 1:
            answer = sum("refund" in m.lower() for m in memos)
            traps = [["case", sum("refund" in m for m in memos)]]
        elif variant == 2:
            found = [INVOICE.search(m).group() for m in memos if INVOICE.search(m)]
            answer = len(set(found))
            traps = [["repeats", len(found)]]
        else:
            answer = sum(bool(INVOICE.search(m)) for m in memos)
            traps = [["typo", sum("INV" in m for m in memos)]]
        return {"rows": rows, "answer": answer, "traps": traps}

    def files(self, box, data: dict, variant: int) -> list:
        pdkit.write_csv(box, PAYMENTS, data["rows"], HEADER)
        return [PAYMENTS]


pydata.add_tasks([PdRegex()])
