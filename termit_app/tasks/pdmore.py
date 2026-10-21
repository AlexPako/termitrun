"""Трек «Аналитика», вторая половина pandas (FB15, FB5 п. 37 и 49): даты, склейка таблиц,
сводные, map и apply, сохранение в CSV, SQL из pandas (SQLite игры).

Правила те же, что у задач 1–5 (pydata.py): запас full, ответ считает чистый Python у
родителя по строкам генератора (pdkit), код игрока родитель не исполняет. Файлы, которые
пишет pandas игрока (pd_save, pd_sql C), родитель разбирает модулем csv и снимком базы
(dbread) — как данные. Совпадение с настоящим pandas — живой тест tests/test_pydata_live.py."""
import csv
import io
from pathlib import Path
from typing import List, Optional

from termit_app.tasks import envkit, kit, pdkit, pydata, pykit
from termit_app.tasks.base import Task, Variant, Verdict
from termit_app.tasks.pydata import PdAnswer, _pd, _v, full_venv, last_pandas


# --- 7. pd_dates ------------------------------------------------------------------------------

_TO_DT = 'df["date"] = pd.to_datetime(df["date"]); '
_TO_DMY = 'd = pd.to_datetime(df["date"], format="%d.%m.%Y"); '
_MONTH = 'df[df["date"].dt.month == {month}]["amount"].sum()'
_BY_MONTH = 'df.resample("ME", on="date")["amount"].sum()'
_WINDOW = 'df[(d >= "{start}") & (d <= "{end}")]'


class PdDates(PdAnswer):
    """pd.to_datetime, .dt.month; B — resample("ME", on=…); C — format="%d.%m.%Y" и
    сравнение дат с датой ISO. Ловушки — день вместо месяца, наименьший месяц, итог дня,
    сравнение строк ДД.ММ.ГГГГ, границы без «=»."""
    id = "pd_dates"
    title = "Даты в таблице"
    par = 90
    scroll = ("Даты из файла — текст. Сделать их датами: df[\"date\"] = "
              "pd.to_datetime(df[\"date\"]).\n"
              "Части даты — через .dt: df[\"date\"].dt.month — месяц, df[\"date\"].dt.day — "
              "число месяца.\n"
              "Месяц и число не путай: ответ выйдет правдоподобный, но чужой.")
    variants = (
        Variant("Сколько переведено в transfers.csv за {month_name} (месяц {month})? ans "
                "ЧИСЛО",
                hints=("Даты в файле — текст. Сначала pd.to_datetime, потом .dt.month у "
                       "колонки date.",
                       "Отбери строки месяца {month} и сложи amount: df[… == {month}][\"amount\"]"
                       ".sum().",
                       _pd("transfers.csv", _TO_DT + "print(" + _MONTH + ")")),
                solution=_pd("transfers.csv", _TO_DT + "print(" + _MONTH + ")"),
                wrong=(_pd("transfers.csv", _TO_DT + 'print(df[df["date"].dt.day == {month}]'
                                            '["amount"].sum())'),),
                alternatives=("df[df[\"date\"].str.startswith(\"2026-0{month}\")] — по тексту "
                              "даты, без to_datetime",),
                key="month"),
        Variant("Помесячные итоги transfers.csv — df.resample(\"ME\", on=\"date\") и сумма "
                "amount; наибольший из них найдёт s.max(). Какой итог у самого сильного месяца? "
                "ans ЧИСЛО",
                hints=("Сначала pd.to_datetime у колонки date — resample понимает только даты.",
                       "df.resample(\"ME\", on=\"date\")[\"amount\"].sum() — по строке на месяц; "
                       "наибольшую найдёт .max().",
                       _pd("transfers.csv", _TO_DT + "print(" + _BY_MONTH + ")")),
                solution=_pd("transfers.csv", _TO_DT + "print(" + _BY_MONTH + ")"),
                solution_script=_pd("transfers.csv", _TO_DT + "print(" + _BY_MONTH + ".max())"),
                wrong=(_pd("transfers.csv", _TO_DT + 'print(df.groupby("date")["amount"]'
                                            '.sum().max())'),),
                alternatives=("df.groupby(df[\"date\"].dt.month)[\"amount\"].sum() — то же по "
                              "номерам месяцев",),
                key="resample"),
        Variant("В transfers.csv даты записаны как 14.03.2026 — день, месяц, год; такой формат "
                "объясняют так: pd.to_datetime(df[\"date\"], format=\"%d.%m.%Y\"). "
                "Сколько переводов с {start_name} по {end_name} 2026 года включительно? ans "
                "ЧИСЛО",
                hints=("Формат дат подскажи pandas сам: pd.to_datetime(df[\"date\"], "
                       "format=\"%d.%m.%Y\").",
                       "Даты сравнивают с датой ISO: df[\"date\"] >= \"{start}\" — и не забудь «=» "
                       "у обеих границ.",
                       _pd("transfers.csv", _TO_DMY + "print(len(" + _WINDOW + "))")),
                solution=_pd("transfers.csv", _TO_DMY + "print(len(" + _WINDOW + "))"),
                wrong=(_pd("transfers.csv", 'print(len(df[(df["date"] >= "{start_dmy}") & '
                                            '(df["date"] <= "{end_dmy}")]))'),
                       _pd("transfers.csv", _TO_DMY + 'print(len(df[(d > "{start}") & '
                                            '(d < "{end}")]))')),
                alternatives=("df[\"date\"].between(\"{start}\", \"{end}\") — обе границы "
                              "включительно",),
                key="format"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Из CSV даты приходят текстом. pd.to_datetime делает их датами: тогда работают "
               ".dt.month, сравнение с \"2026-03-01\" и resample. Текст «14.03.2026» сравнивается "
               "по буквам, с дня, — поэтому сначала формат и to_datetime.")
    spell = ("pd.to_datetime(df[\"d\"], format=\"%d.%m.%Y\"); .dt.month; "
             "df.resample(\"ME\", on=\"d\")[\"a\"].sum()")
    trap_messages = {
        "day": "Это переводы по числу месяца: .dt.day. Месяц — .dt.month.",
        "min": "Это самый слабый месяц. Нужен самый сильный — .max().",
        "text": "Это сравнение текста: «14.03.2026» идёт по буквам, с дня. Сначала "
                "pd.to_datetime(…, format=\"%d.%m.%Y\").",
        "daily": "Это итог одного дня: groupby(\"date\"). Помесячно — resample(\"ME\", "
                 "on=\"date\").",
        "edge": "Это без переводов ровно на границах. «Включительно» — >= и <=.",
    }
    FALLBACKS = (
        "Не то. Даты — в pd.to_datetime, потом месяц — .dt.month, и сумма amount.",
        "Не то. Помесячно — resample(\"ME\", on=\"date\"), сумма amount, наибольшая — .max().",
        "Не то. to_datetime с format=\"%d.%m.%Y\", потом отбор между датами и len(…).",
    )

    def gen(self, rng, variant: int) -> dict:
        return pdkit.dates_data(rng, variant)

    def public(self, data: dict) -> dict:
        keys = ("month", "month_name", "start", "end", "start_dmy", "end_dmy", "start_name",
                "end_name")
        return {k: data[k] for k in keys if k in data}


# --- 8. pd_merge ------------------------------------------------------------------------------

_ACC = 'a = pd.read_csv("accounts.csv"); '
_JOIN = 'm = pd.merge(a, df, on="account"); '
_LEFT = 'm = pd.merge(a, df, on="account", how="left"); '


class PdMerge(PdAnswer):
    """pd.merge(on=…), how="left" + .isna(); склейка по имени (тёзки) — ловушка."""
    id = "pd_merge"
    title = "Две таблицы в одну"
    par = 105
    practice_variant = 2            # тёзки и склейка по номеру — шаг стража boss_pylib
    scroll = ("Склеить две таблицы по общей колонке: m = pd.merge(a, b, on=\"account\") — к "
              "строкам a добавятся колонки b.\n"
              "Строки без пары пропадут. Оставить все строки a: pd.merge(a, b, on=\"account\", "
              "how=\"left\") — у кого пары нет, там NaN.\n"
              "Склеивай по номеру счёта, а не по имени: у тёзок имена одинаковые.")
    variants = (
        Variant("Переводы — в transfers.csv (колонка account — номер счёта), владельцы счетов — "
                "в accounts.csv. Сколько всего перевёл {owner}? ans ЧИСЛО",
                hints=("Имён в transfers.csv нет — их надо подклеить из accounts.csv по колонке "
                       "account: pd.merge.",
                       "После склейки отбери строки {owner} и сложи amount.",
                       _pd("transfers.csv", _ACC + _JOIN + 'print(m[m["name"] == "{owner}"]'
                                                           '["amount"].sum())')),
                solution=_pd("transfers.csv", _ACC + _JOIN + 'print(m[m["name"] == "{owner}"]'
                                                             '["amount"].sum())'),
                wrong=(_pd("transfers.csv", 'print(df["amount"].sum())'),),
                alternatives=("номер счёта {owner} — из accounts.csv, а потом отбор по account "
                              "без склейки",),
                key="merge"),
        Variant("Сколько счетов из accounts.csv ни разу не переводили денег — их номеров нет в "
                "transfers.csv? Склейка, которая оставляет все счета, — how=\"left\". ans ЧИСЛО",
                hints=("Слева — счета: pd.merge(a, df, on=\"account\", how=\"left\") оставит "
                       "все, даже без переводов.",
                       "У счёта без переводов amount после склейки — NaN: .isna().sum().",
                       _pd("transfers.csv", _ACC + _LEFT + 'print(m["amount"].isna().sum())')),
                solution=_pd("transfers.csv", _ACC + _LEFT + 'print(m["amount"].isna().sum())'),
                wrong=(_pd("transfers.csv", _ACC + 'm = pd.merge(a, df, on="account"); '
                                            'print(m["amount"].isna().sum())'),),
                alternatives=("(~a[\"account\"].isin(df[\"account\"])).sum() — без склейки, "
                              "через isin",),
                key="left"),
        Variant("В transfers.csv есть и номер счёта, и имя владельца; уровень счёта (tier) — в "
                "accounts.csv. Сколько переведено со счетов уровня {tier}? ans ЧИСЛО",
                hints=("Уровень подклей из accounts.csv склейкой pd.merge — но по какой колонке?",
                       "Имена бывают одинаковыми — у {twin} есть тёзка. Склеивай по номеру: "
                       "on=\"account\".",
                       _pd("transfers.csv", _ACC + _JOIN + 'print(m[m["tier"] == "{tier}"]'
                                                           '["amount"].sum())')),
                solution=_pd("transfers.csv", _ACC + _JOIN + 'print(m[m["tier"] == "{tier}"]'
                                                             '["amount"].sum())'),
                wrong=(_pd("transfers.csv", _ACC + 'm = pd.merge(a, df, on="name"); '
                                            'print(m[m["tier"] == "{tier}"]["amount"].sum())'),),
                alternatives=("pd.merge без on — склеит по всем общим колонкам: account и name",),
                key="twins"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("pd.merge подставляет к строке данные из другой таблицы по общей колонке. "
               "Обычная склейка теряет строки без пары, how=\"left\" их оставляет с NaN. "
               "Склеивать надо по номеру: имя у тёзок одно, и строки размножатся.")
    spell = "pd.merge(df, a, on=\"id\"); how=\"left\" → NaN у строк без пары"
    trap_messages = {
        "all": "Это сумма всех переводов. Нужен только {owner}: склей с accounts.csv и отбери "
               "его строки.",
        "inner": "Ноль — потому что обычная склейка выкинула счета без переводов. Оставь их: "
                 "how=\"left\".",
        "name": "Сумма раздута: склейка по имени размножила строки {twin} — тёзок двое. "
                "Склеивай по номеру: on=\"account\".",
    }
    FALLBACKS = (
        "Не то. Склей переводы с accounts.csv по account и сложи amount строк {owner}.",
        "Не то. pd.merge(a, df, on=\"account\", how=\"left\") и посчитай NaN в amount.",
        "Не то. Склей по account, отбери уровень {tier} и сложи amount.",
    )

    def gen(self, rng, variant: int) -> dict:
        return pdkit.merge_data(rng, variant)

    def files(self, box: Path, data: dict, variant: int) -> list:
        pdkit.write_csv(box, pdkit.DATA, data["rows"], data["header"])
        kit.write(Path(box) / pdkit.ACCOUNTS, pdkit.accounts_csv(data["accounts"]))
        return [pdkit.DATA, pdkit.ACCOUNTS]

    def public(self, data: dict) -> dict:
        return {k: data[k] for k in ("owner", "tier", "twin") if k in data}


# --- 9. pd_pivot ------------------------------------------------------------------------------

_PIVOT = 'pt = df.pivot_table(index="city", columns="channel", values="amount", '


class PdPivot(PdAnswer):
    """pivot_table(index, columns, values, aggfunc); B — aggfunc="count"; C — fill_value=0.
    Ловушки — aggfunc по умолчанию (mean), сумма вместо числа строк, наименьший мимо NaN."""
    id = "pd_pivot"
    title = "Сводная таблица"
    par = 105
    kinds = ("number", "number", "text")
    scroll = ("Сводная — как в Excel: pt = df.pivot_table(index=\"city\", columns=\"channel\", "
              "values=\"amount\", aggfunc=\"sum\").\n"
              "Строки — по index=, колонки — по columns=, что считать — values=, как — aggfunc=: "
              "\"sum\" или \"count\"; без него — среднее.\n"
              "Ячейка — pt[\"card\"][\"Omsk\"]: сначала колонка, потом строка.")
    variants = (
        Variant("Сводная по transfers.csv: города — строки, каналы (channel) — колонки, в "
                "ячейке — сумма amount. Сколько в ячейке {city} × {channel}? ans ЧИСЛО",
                hints=("Сводную строит df.pivot_table: index — город, columns — канал, values — "
                       "amount.",
                       "Сумма — aggfunc=\"sum\": без него в ячейке будет среднее. Ячейка — "
                       "pt[\"{channel}\"][\"{city}\"].",
                       _pd("transfers.csv", _PIVOT + 'aggfunc="sum"); print(pt)')),
                solution=_pd("transfers.csv", _PIVOT + 'aggfunc="sum"); print(pt)'),
                solution_script=_pd("transfers.csv", _PIVOT + 'aggfunc="sum"); '
                                    'print(pt["{channel}"]["{city}"])'),
                wrong=(_pd("transfers.csv", 'pt = df.pivot_table(index="city", columns="channel", '
                                            'values="amount"); print(pt.loc["{city}", '
                                            '"{channel}"])'),),
                alternatives=("df[(df[\"city\"] == \"{city}\") & (df[\"channel\"] == "
                              "\"{channel}\")][\"amount\"].sum() — одну ячейку и без сводной",),
                key="sum"),
        Variant("Та же сводная по transfers.csv, но в ячейке — число переводов: "
                "aggfunc=\"count\". Сколько переводов в ячейке {city} × {channel}? ans ЧИСЛО",
                hints=("Та же сводная, но aggfunc=\"count\" — сколько строк попало в ячейку.",
                       "Ячейка — pt[\"{channel}\"][\"{city}\"]: сначала колонка-канал, потом "
                       "строка-город.",
                       _pd("transfers.csv", _PIVOT + 'aggfunc="count"); print(pt)')),
                solution=_pd("transfers.csv", _PIVOT + 'aggfunc="count"); print(pt)'),
                solution_script=_pd("transfers.csv", _PIVOT + 'aggfunc="count"); '
                                    'print(pt["{channel}"]["{city}"])'),
                wrong=(_pd("transfers.csv", _PIVOT + 'aggfunc="sum"); '
                                            'print(pt["{channel}"]["{city}"])'),),
                alternatives=("len(df[(df[\"city\"] == \"{city}\") & (df[\"channel\"] == "
                              "\"{channel}\")]) — одну ячейку и без сводной",),
                key="count"),
        Variant("Сводная по transfers.csv: города × каналы, сумма amount. Каким каналом город "
                "{city} заработал меньше всего — считая каналы, где переводов не было вовсе? "
                "Пустая ячейка станет нулём от df.pivot_table(…, fill_value=0), строка города — "
                "pt.loc[\"{city}\"]. Каналы: " + ", ".join(pdkit.PIVOT_CHANNELS) + ". ans КАНАЛ",
                hints=("Сводная с aggfunc=\"sum\" и fill_value=0 — пустые ячейки станут нулями.",
                       "Строка города — pt.loc[\"{city}\"]: напечатай её и найди наименьшее "
                       "глазами.",
                       _pd("transfers.csv", _PIVOT + 'aggfunc="sum", fill_value=0); '
                                            'print(pt.loc["{city}"])')),
                solution=_pd("transfers.csv", _PIVOT + 'aggfunc="sum", fill_value=0); '
                                              'print(pt.loc["{city}"])'),
                solution_script=_pd("transfers.csv", _PIVOT + 'aggfunc="sum", fill_value=0); '
                                    'print(pt.loc["{city}"].sort_values().index[0])'),
                wrong=(_pd("transfers.csv", _PIVOT + 'aggfunc="sum"); '
                                            'print(pt.loc["{city}"].sort_values().index[0])'),),
                alternatives=("pt.loc[\"{city}\"].sort_values() — все каналы города от "
                              "меньшего",),
                key="fill"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("pivot_table раскладывает строки по ячейкам «строка × колонка» и считает "
               "каждую: aggfunc говорит как, а без него pandas берёт среднее. Пустая ячейка — "
               "NaN, её пропускают и min, и сортировка; fill_value=0 делает её нулём.")
    spell = ("df.pivot_table(index=\"a\", columns=\"b\", values=\"v\", aggfunc=\"sum\", "
             "fill_value=0); pt[\"колонка\"][\"строка\"]")
    trap_messages = {
        "mean": "Это среднее: pivot_table без aggfunc считает mean. Нужна сумма — "
                "aggfunc=\"sum\".",
        "sum": "Это сумма денег в ячейке. Нужно число переводов: aggfunc=\"count\".",
        "skipna": "Этот канал у {city} есть. А один канал там пуст — NaN, и min его не видит. "
                  "Сделай пустое нулём: fill_value=0.",
    }
    FALLBACKS = (
        "Не то. Сводная с aggfunc=\"sum\", ячейка — pt[\"{channel}\"][\"{city}\"].",
        "Не то. Сводная с aggfunc=\"count\", ячейка — pt[\"{channel}\"][\"{city}\"].",
        "Не то. Сводная с fill_value=0, строка {city} и её наименьший канал.",
    )

    def gen(self, rng, variant: int) -> dict:
        return pdkit.pivot_data(rng, variant)

    def public(self, data: dict) -> dict:
        return {k: data[k] for k in ("city", "channel") if k in data}


# --- 10. pd_apply -----------------------------------------------------------------------------

class PdApply(PdAnswer):
    """.map(словарь), .apply(функция); C — .map и .fillna для ключей, которых нет в словаре."""
    id = "pd_apply"
    title = "Своё правило к колонке"
    par = 90
    scroll = ("Значения по словарю: df[\"channel\"].map({\"card\": 0.02, \"cash\": 0}) — "
              "каждое слово заменится числом.\n"
              "Слова нет в словаре — будет NaN: .fillna(0.01) поставит запасное.\n"
              "Своя функция к каждому значению: df[\"amount\"].apply(math.ceil); модуль math "
              "подключает строка import math в начале кода.")
    variants = (
        Variant("Банк берёт комиссию по каналу (channel): {rates_text} от суммы. Сколько всего "
                "комиссий по transfers.csv? Округли до 2 знаков — .round(2): ans ЧИСЛО",
                hints=("Ставку каждой строки даст .map со словарём «канал → доля»: 2 % — это "
                       "0.02.",
                       "Комиссия строки — amount, умноженный на ставку; потом .sum() и "
                       ".round(2).",
                       _pd("transfers.csv", 'df["fee"] = df["amount"] * df["channel"].map('
                                            '{rates_code}); print(df["fee"].sum().round(2))')),
                solution=_pd("transfers.csv", 'df["fee"] = df["amount"] * df["channel"].map('
                                              '{rates_code}); print(df["fee"].sum().round(2))'),
                wrong=(_pd("transfers.csv", 'df["fee"] = df["amount"] * df["channel"].map('
                                            '{rates_pct}); print(df["fee"].sum().round(2))'),),
                alternatives=("по каналу отдельно: groupby(\"channel\")[\"amount\"].sum(), "
                              "потом умножить на ставки",),
                key="map"),
        Variant("Бухгалтерия округляет каждый перевод вверх до целого: 12.01 → 13. Это "
                "math.ceil. Сколько выйдет всего по transfers.csv после такого округления? "
                "ans ЧИСЛО",
                hints=("Функцию к каждому значению колонки применяет .apply: "
                       "df[\"amount\"].apply(math.ceil).",
                       "math — модуль Python: import math в начале кода; дальше — .sum().",
                       _pd("transfers.csv", 'import math; print(df["amount"].apply(math.ceil)'
                                            '.sum())')),
                solution=_pd("transfers.csv", 'import math; print(df["amount"].apply(math.ceil)'
                                              '.sum())'),
                wrong=(_pd("transfers.csv", 'print(df["amount"].round().sum())'),
                       _pd("transfers.csv", 'print(df["amount"].astype(int).sum())')),
                alternatives=("import numpy as np; np.ceil(df[\"amount\"]).sum() — то же сразу "
                              "на всю колонку",),
                key="apply"),
        Variant("Ставки комиссии: {rates_text}; у остальных каналов ({unknown}) ставки нет в "
                "таблице — им {default} %. Сколько всего комиссий по transfers.csv? Округли до 2 "
                "знаков: ans ЧИСЛО",
                hints=("Ставку даст .map со словарём; канала нет в словаре — map вернёт NaN.",
                       "NaN в сумме молча пропадёт. Поставь запасную ставку: "
                       ".fillna({default_share}).",
                       _pd("transfers.csv", 'df["fee"] = df["amount"] * df["channel"].map('
                                            '{rates_code}).fillna({default_share}); '
                                            'print(df["fee"].sum().round(2))')),
                solution=_pd("transfers.csv", 'df["fee"] = df["amount"] * df["channel"].map('
                                              '{rates_code}).fillna({default_share}); '
                                              'print(df["fee"].sum().round(2))'),
                wrong=(_pd("transfers.csv", 'df["fee"] = df["amount"] * df["channel"].map('
                                            '{rates_code}); print(df["fee"].sum().round(2))'),),
                alternatives=("df[\"channel\"].map(lambda c: …) — своя функция вместо словаря",),
                key="fillna"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = (".map подставляет значение из словаря по ключу, а ключа нет — пишет NaN, и сумма "
               "его молча теряет: .fillna ставит запасное. .apply вызывает функцию на каждом "
               "значении — math.ceil, round или свою.")
    spell = "df[\"c\"].map({\"k\": 0.02}).fillna(0); df[\"a\"].apply(math.ceil)"
    trap_messages = {
        "percent": "В сто раз больше: 2 % — это доля 0.02, а не 2. В словаре — доли.",
        "round": "Это обычное округление: round. Вверх до целого — math.ceil через .apply.",
        "int": "Это отбрасывание копеек: astype(int) режет вниз. Вверх — math.ceil.",
        "nan": "Комиссии каналов {unknown} пропали: map дал им NaN. Поставь им ставку — "
               ".fillna({default_share}).",
    }
    FALLBACKS = (
        "Не то. Ставка — .map со словарём долей (2 % = 0.02), комиссия — amount × ставка, "
        "потом .sum().",
        "Не то. df[\"amount\"].apply(math.ceil).sum() — каждую сумму вверх, потом сложить.",
        "Не то. .map со словарём и .fillna({default_share}) для остальных каналов, потом сумма.",
    )

    def gen(self, rng, variant: int) -> dict:
        d = pdkit.apply_data(rng, variant)
        if "rates" in d:
            rates = d["rates"]
            d["rates_text"] = pdkit.rates_text(rates)
            d["rates_code"] = pdkit.rates_dict(rates)
            d["rates_pct"] = "{" + ", ".join(f'"{k}": {rates[k]}' for k in sorted(rates)) + "}"
            if "default" in d:
                d["default_share"] = f"0.0{d['default']}"
            del d["rates"]
        return d

    def public(self, data: dict) -> dict:
        keys = ("rates_text", "rates_code", "rates_pct", "default", "default_share", "unknown")
        return {k: data[k] for k in keys if k in data}


# --- 11. pd_save ------------------------------------------------------------------------------

CSV_CAP = 256 * 1024


def _pandas_wrote(box, name: str) -> Optional[bool]:
    """Последний python3 -c с to_csv и именем файла: исход (None — такого не было)."""
    jour = envkit.journal(box)
    for line, ok in reversed(jour):
        if "to_csv" in line and name in line and any(envkit.py_inline(s)
                                                     for s in envkit.segments(line)):
            return ok is not False
    return None


def read_rows(box, rel: str, sep: str = ","):
    """Строки CSV файла rel: (шапка, строки, сообщение). Файл — данные: модуль csv."""
    kind, text = envkit.box_text(box, rel, CSV_CAP)
    bad = envkit.file_problem(kind, rel)
    if bad:
        return None, None, bad
    if text is None:
        return None, None, None
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=sep))
    except csv.Error:
        return None, None, PdSave.MSG_BROKEN.format(out=rel)
    rows = [r for r in rows if r]
    if not rows:
        return None, None, PdSave.MSG_EMPTY.format(out=rel)
    return rows[0], rows[1:], None


class PdSave(Task):
    """df.to_csv(файл, index=False); B — sep=";"; C — колонки и sort_values перед записью.
    Файл разбирает родитель (csv), запись — python3 -c с pandas из .venv (журнал)."""
    id = "pd_save"
    track = "pydata"
    title = "Таблицу — в файл"
    par = 90
    pinned_python = True
    stock = "full"
    scroll = ("Таблицу — в файл: df.to_csv(\"out.csv\", index=False) — без index=False первой "
              "колонкой ляжут номера строк.\n"
              "Свой разделитель — df.to_csv(\"out.csv\", sep=\";\", index=False): так CSV "
              "ждёт Excel с русскими настройками.\n"
              "Только часть колонок — df[[\"city\", \"amount\"]]; порядок строк — "
              ".sort_values(\"amount\", ascending=False).")
    variants = (
        Variant("Сохрани переводы города {city} из transfers.csv в {out} — те же колонки, без "
                "номеров строк.",
                hints=("Отбери строки города, как в задаче про отбор строк, и запиши их: "
                       ".to_csv(\"{out}\").",
                       "Номера строк слева в файл не нужны — индекс pandas убирает "
                       "index=False.",
                       _pd("transfers.csv", 'df[df["city"] == "{city}"].to_csv("{out}", '
                                            'index=False)')),
                solution=_pd("transfers.csv", 'df[df["city"] == "{city}"].to_csv("{out}", '
                                              'index=False)'),
                wrong=(_pd("transfers.csv", 'df[df["city"] == "{city}"].to_csv("{out}")'),),
                alternatives=("head -n 1 transfers.csv > {out}; grep ,{city}, transfers.csv >> "
                              "{out} — без pandas, но задача про него",),
                key="index"),
        Variant("Бухгалтерия открывает CSV в Excel, а он ждёт разделитель «;». Сохрани весь "
                "transfers.csv в excel.csv с разделителем «;», без номеров строк.",
                hints=("Записать таблицу — .to_csv(\"excel.csv\", index=False).",
                       "Свой разделитель — sep=\";\", как у read_csv.",
                       _pd("transfers.csv", 'df.to_csv("excel.csv", sep=";", index=False)')),
                solution=_pd("transfers.csv", 'df.to_csv("excel.csv", sep=";", index=False)'),
                wrong=(_pd("transfers.csv", 'df.to_csv("excel.csv", index=False)'),),
                alternatives=("tr , \\; < transfers.csv > excel.csv — без pandas, но запятая в "
                              "кавычках сломается",),
                key="sep"),
        Variant("Сделай top.csv: только колонки city и amount, строки — от большей суммы к "
                "меньшей, без номеров строк.",
                hints=("Две колонки — df[[\"city\", \"amount\"]]: список имён в квадратных "
                       "скобках.",
                       "От большей — .sort_values(\"amount\", ascending=False), потом "
                       ".to_csv(\"top.csv\", index=False).",
                       _pd("transfers.csv", 'df[["city", "amount"]].sort_values("amount", '
                                            'ascending=False).to_csv("top.csv", index=False)')),
                solution=_pd("transfers.csv", 'df[["city", "amount"]].sort_values("amount", '
                                              'ascending=False).to_csv("top.csv", index=False)'),
                wrong=(_pd("transfers.csv", 'df[["city", "amount"]].sort_values("amount")'
                                            '.to_csv("top.csv", index=False)'),),
                alternatives=("сначала сортировка всей таблицы, потом выбор колонок — то же",),
                key="top"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("to_csv пишет таблицу в файл. Индекс — номера строк pandas — по умолчанию идёт "
               "первой колонкой без имени: index=False его убирает. sep меняет разделитель, а "
               "отбор и сортировка делаются до записи.")
    spell = "df.to_csv(\"f.csv\", index=False, sep=\";\"); df[[\"a\", \"b\"]].sort_values(\"b\")"
    MSG_NO_VENV = "Окружения .venv нет — набери reset, соберу задачу заново."
    MSG_BROKEN = "{out} не читается как CSV — запиши его заново через .to_csv(…)."
    MSG_EMPTY = "{out} пуст — запиши таблицу заново: .to_csv(…)."
    MSG_INDEX = ("Первая колонка {out} — без имени, это номера строк pandas (индекс). Запиши "
                 "без них: .to_csv(\"{out}\", index=False).")
    MSG_SEP = ("В {out} разделитель — запятая, а нужен «;»: .to_csv(\"{out}\", sep=\";\", "
               "index=False).")
    MSG_HEAD = "Шапка {out} не та: нужна {head}."
    MSG_ORDER = "Строки top.csv — от меньшей суммы к большей. Нужно наоборот: ascending=False."
    MSG_ROWS = "В {out} не те строки: {hint}"
    MSG_NOT_PANDAS = ("{out} похож на правду, но его писал не pandas. Задача — про to_csv: "
                      "python3 -c '… .to_csv(\"{out}\", index=False)'.")
    MSG_CRASH = ("Команда упала — файл не записан. Прочти последнюю строку ошибки, поправь и "
                 "запусти снова.")
    ROWS_HINT = ("только переводы {city}, все колонки как в transfers.csv.",
                 "все переводы transfers.csv.",
                 "все переводы, город и сумма.")

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        d = pdkit.save_data(rng, variant)
        pdkit.write_csv(box, pdkit.DATA, d["rows"], d["header"])
        full_venv(box)
        by_id = {r["id"]: r for r in d["rows"]}
        head = d["want_header"]
        want = [[pdkit.render([by_id[i]], head).splitlines()[1]] for i in d["want"]]
        return {"city": d.get("city", ""), "out": d["out"], "head": head,
                "want": [w[0] for w in want]}

    def _same_row(self, got: List[str], want: List[str], head: List[str]) -> bool:
        if len(got) != len(want):
            return False
        for h, g, w in zip(head, got, want):
            if h == "amount":
                if not pykit.same_num(g, w):
                    return False
            elif g != w:
                return False
        return True

    def check(self, ctx) -> Verdict:
        box, st = ctx.box, ctx.state
        v = _v(self, st)
        out, head = st["out"], list(st["head"])
        kind, _ = envkit.box_file(box, out)
        if kind == "missing":
            last = last_pandas(box)
            if last is not None and last[1] is False:
                return Verdict(False, self.MSG_CRASH)
            return Verdict(False, None if ctx.answer is None else self.stray_answer)
        sep = ";" if v == 1 else ","
        got_head, rows, msg = read_rows(box, out, sep)
        if msg:
            return Verdict(False, msg)
        if got_head is None:
            return Verdict(False, self.MSG_EMPTY.format(out=out))
        if v == 1 and len(got_head) == 1 and "," in got_head[0]:
            return Verdict(False, self.MSG_SEP.format(out=out))
        if got_head and got_head[0] in ("", "Unnamed: 0") and got_head[1:] == head:
            return Verdict(False, self.MSG_INDEX.format(out=out))
        if got_head != head:
            return Verdict(False, self.MSG_HEAD.format(out=out, head=sep.join(head)))
        want = [next(csv.reader([w])) for w in st["want"]]
        same = len(rows) == len(want) and all(self._same_row(g, w, head)
                                              for g, w in zip(rows, want))
        if not same:
            if v == 2 and len(rows) == len(want) and all(
                    self._same_row(g, w, head) for g, w in zip(rows, reversed(want))):
                return Verdict(False, self.MSG_ORDER)
            hint = self.ROWS_HINT[v].format(**st)
            return Verdict(False, self.MSG_ROWS.format(out=out, hint=hint))
        wrote = _pandas_wrote(box, out)
        if not wrote:
            return Verdict(False, self.MSG_NOT_PANDAS.format(out=out))
        return Verdict(True)


# --- 12. pd_sql -------------------------------------------------------------------------------

_CON = 'import sqlite3; con = sqlite3.connect("bank.db"); '
_TOP_SQL = ("SELECT a.name, SUM(t.amount) AS total FROM transfers t JOIN accounts a ON "
            "a.account = t.account GROUP BY a.name ORDER BY total DESC")


def _sql(tail: str) -> str:
    """python3 -c 'import sqlite3; import pandas as pd; con = …; …' — из .venv."""
    return ("source .venv/bin/activate; python3 -c 'import pandas as pd; " + _CON + tail
            + "'")


class PdSql(PdAnswer):
    """sqlite3.connect + pd.read_sql(запрос, con); B — JOIN и GROUP BY в самом SQL; C —
    df.to_sql("payments", con, index=False): новую таблицу родитель читает снимком (dbread)."""
    id = "pd_sql"
    title = "SQL из pandas"
    par = 90
    kinds = ("number", "text", "none")
    scroll = ("Связь с файлом базы SQLite: con = sqlite3.connect(\"bank.db\"), а модуль "
              "sqlite3 подключает import sqlite3.\n"
              "Запрос в таблицу pandas: df = pd.read_sql(\"SELECT * FROM transfers\", "
              "con=con): считает SQL, а ответ приходит таблицей.\n"
              "Обратно, таблицу в базу: df.to_sql(\"payments\", con=con, index=False); "
              "con=con можно писать и просто con.")
    variants = (
        Variant("В bank.db — таблица transfers. Сколько в ней переводов дороже {limit}? Строго "
                "больше. Запрос — через pandas: pd.read_sql. ans ЧИСЛО",
                hints=("Открой базу: con = sqlite3.connect(\"bank.db\") — и передай запрос в "
                       "pd.read_sql(…, con).",
                       "Порог — в самом SQL: WHERE amount > {limit}; строк в ответе — len(df).",
                       _sql('df = pd.read_sql("SELECT * FROM transfers WHERE amount > {limit}", '
                            'con); print(len(df))')),
                solution=_sql('df = pd.read_sql("SELECT * FROM transfers WHERE amount > {limit}"'
                              ', con); print(len(df))'),
                wrong=(_sql('df = pd.read_sql("SELECT * FROM transfers WHERE amount >= {limit}"'
                            ', con); print(len(df))'),),
                alternatives=("sqlite3 bank.db 'SELECT COUNT(*) FROM transfers WHERE amount > "
                              "{limit}' — без pandas",),
                key="read"),
        Variant("Кто перевёл больше всех — с учётом всех своих счетов? Таблицы bank.db: "
                "transfers (account) и accounts (account, name). Склей и сложи прямо в SQL, "
                "pandas — прочесть ответ. ans ИМЯ",
                hints=("JOIN accounts по account, GROUP BY a.name, SUM(t.amount), ORDER BY … DESC "
                       "— всё в одном запросе.",
                       "Запрос — в pd.read_sql(…, con); первая строка ответа — лидер.",
                       "source .venv/bin/activate; python3 -c с pd.read_sql(\"" + _TOP_SQL
                       + "\", con) — первая строка и есть лидер"),
                solution=_sql('df = pd.read_sql("' + _TOP_SQL + '", con); print(df.head(3))'),
                solution_script=_sql('df = pd.read_sql("' + _TOP_SQL + '", con); '
                                     'print(df["name"][0])'),
                wrong=(_sql('df = pd.read_sql("' + _TOP_SQL.replace("GROUP BY a.name",
                                                                    "GROUP BY t.account")
                            + '", con); print(df["name"][0])'),),
                alternatives=("pd.read_sql обеих таблиц целиком и pd.merge — то же, но "
                              "склейку делает pandas",),
                key="join"),
        Variant("Новые платежи — в payments.csv. Залей их в bank.db новой таблицей payments — "
                "те же колонки, без номеров строк.",
                hints=("Прочти файл в таблицу: pd.read_csv(\"payments.csv\") — и открой базу "
                       "sqlite3.connect.",
                       "Таблицу в базу пишет .to_sql(\"payments\", con, index=False) — без "
                       "index=False ляжет лишняя колонка index.",
                       _sql('df = pd.read_csv("payments.csv"); df.to_sql("payments", con, '
                            'index=False)')),
                solution=_sql('df = pd.read_csv("payments.csv"); df.to_sql("payments", con, '
                              'index=False)'),
                wrong=(_sql('df = pd.read_csv("payments.csv"); df.to_sql("payments", con)'),),
                alternatives=("df.to_sql(\"payments\", con=con, index=False) — то же, имя "
                              "параметра названо явно",),
                key="to_sql"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("pd.read_sql отдаёт SQL базе, а ответ принимает таблицей pandas: считать можно и "
               "там, и там. to_sql — обратная дорога: таблица pandas становится таблицей базы; "
               "index=False — без колонки с номерами строк.")
    spell = ("con = sqlite3.connect(\"f.db\"); pd.read_sql(\"SELECT …\", con); "
             "df.to_sql(\"t\", con, index=False)")
    trap_messages = {
        "edge": "Это вместе с переводами ровно на {limit}. «Дороже» — это >, а >= берёт и "
                "порог.",
        "account": "Это хозяин самого крупного одного счёта. А счетов у людей бывает два: "
                   "GROUP BY a.name, а не по счёту.",
    }
    FALLBACKS = (
        "Не то. pd.read_sql с WHERE amount > {limit} и len(df).",
        "Не то. JOIN по account, GROUP BY a.name, сумма по убыванию — первая строка.",
        "",
    )
    MSG_NO_TABLE = ("В bank.db ещё нет таблицы payments: df.to_sql(\"payments\", con, "
                    "index=False).")
    MSG_INDEX_COL = ("В payments лишняя колонка index — номера строк pandas. Пересоздай без "
                     "неё: df.to_sql(\"payments\", con, index=False, if_exists=\"replace\").")
    MSG_COLS = "У payments колонки {got}, а нужны id, account, amount — как в payments.csv."
    MSG_ROWS = "В payments {n} строк из {m}: залей весь payments.csv."
    MSG_VALUES = "В payments не те строки — сверь с payments.csv и залей заново."

    def gen(self, rng, variant: int) -> dict:
        d = pdkit.sql_data(rng, variant)
        if variant == 2:
            d["answer"], d["traps"] = "", []
        return d

    def files(self, box: Path, data: dict, variant: int) -> list:
        from termit_app.tasks import dbkit
        dbkit.put(box, pdkit.BANK, pdkit.bank_bytes(data["accounts"], data["rows"]))
        if variant == 2:
            kit.write(Path(box) / pdkit.PAYMENTS, pdkit.payments_csv(data["payments"]))
            return [pdkit.PAYMENTS]
        return [pdkit.BANK]

    def public(self, data: dict) -> dict:
        out = {k: data[k] for k in ("limit",) if k in data}
        if "payments" in data:
            out["payments"] = [[p["id"], p["account"], p["amount"]] for p in data["payments"]]
        return out

    def takes_answer(self, state: dict) -> bool:
        return _v(self, state) != 2

    def matches(self, given: str, ctx) -> bool:
        return _v(self, ctx.state) != 2 and super().matches(given, ctx)

    def check(self, ctx) -> Verdict:
        if _v(self, ctx.state) != 2:
            return super().check(ctx)
        verdict = self._loaded(ctx)
        if verdict.solved or ctx.answer is None:
            return verdict
        return Verdict(False, self.stray_answer)       # ответ здесь не сдают — сначала это

    def _loaded(self, ctx) -> Verdict:
        from termit_app import dbread
        want = ctx.state["payments"]
        try:
            with dbread.SqliteSnapshot(ctx.box, pdkit.BANK) as snap:
                names = [c["name"] for c in snap.columns("payments")]
                if not names:
                    return Verdict(False, self._crash(ctx) or self.MSG_NO_TABLE)
                if names and names[0] in ("index", "level_0"):
                    return Verdict(False, self.MSG_INDEX_COL)
                if names != ["id", "account", "amount"]:
                    return Verdict(False, self.MSG_COLS.format(got=", ".join(names)))
                rows = snap.rows("payments", ("id", "account", "amount"), order=("id",))
        except dbread.Broken as e:
            if "payments" in str(e):
                return Verdict(False, self._crash(ctx) or self.MSG_NO_TABLE)
            return Verdict(False, str(e))
        got = sorted([list(r) for r in rows], key=lambda r: str(r[0]))
        exp = sorted(want, key=lambda r: str(r[0]))
        if len(got) != len(exp):
            return Verdict(False, self.MSG_ROWS.format(n=len(got), m=len(exp)))
        for g, w in zip(got, exp):
            if (str(g[0]) != str(w[0]) or str(g[1]) != str(w[1])
                    or not pykit.same_num(g[2], w[2] / 100)):
                return Verdict(False, self.MSG_VALUES)
        return Verdict(True)

    def _crash(self, ctx) -> Optional[str]:
        last = last_pandas(ctx.box)
        if last is not None and last[1] is False:
            from termit_app.tasks.pydata import MSG_CRASH
            return MSG_CRASH
        return None


TASKS = [PdDates(), PdMerge(), PdPivot(), PdApply(), PdSave(), PdSql()]


# --- 13. rq_get: requests к учебному API ------------------------------------------------------

_RQ_RUN = "source .venv/bin/activate && python3 fetch.py"


class RqGet(pykit.PyEditTask):
    """requests через sockhttp.session(): s.get(…, timeout=5), r.raise_for_status(), r.json()
    → pd.DataFrame → rates.csv. B — params=, C — headers= с ключом из переменной окружения.
    Засчитывается по rates.csv (разбор csv у родителя) и журналу API: запрос от requests
    (User-Agent python-requests/…) — судья."""
    id = "rq_get"
    track = "pydata"
    title = "requests к API"
    par = 105
    practice_variant = 2            # ключ в заголовке из окружения — шаг стража boss_pylib
    script = "fetch.py"
    run = _RQ_RUN
    outputs = ("rates.csv",)
    stock = "full"
    venv_modules = ("sockhttp", "requests", "pandas")
    needs_judge = True
    secret_keys = ("expect", "traps", "rates")
    scroll = ("Запросы HTTP из Python — пакет requests: r = s.get(\"http://api/rates\", "
              "timeout=5) — ответ, а timeout=5 — сколько секунд ждать.\n"
              "r.raise_for_status() — ответ с ошибкой (404, 401) остановит скрипт; r.json() — "
              "тело ответа словарём, pd.DataFrame(список) — таблица.\n"
              "s = sockhttp.session() — сессия requests к серверу игры; в жизни вместо неё — "
              "requests.get(адрес сайта), дальше всё то же.")
    variants = (
        Variant("Учебный API отдаёт курсы валют по адресу http://api/rates. Допиши fetch.py: "
                "запрос через requests (сессия s уже есть), ждать не больше 5 секунд — курсы "
                "лягут в rates.csv. Запуск — " + _RQ_RUN,
                hints=("Открой fetch.py: nano fetch.py — одна строка # TODO.",
                       "Запрос — s.get с адресом из задания; сколько ждать — timeout=5 в тех же "
                       "скобках."),
                wrong=(_RQ_RUN,),
                alternatives=("curl --unix-socket api.sock http://api/rates — посмотреть ответ "
                              "глазами",),
                key="get"),
        Variant("Нужны курсы только к валюте {base}: API фильтрует сам — параметр base. "
                "Параметры requests передают словарём: s.get(адрес, params={{\"base\": "
                "\"{base}\"}}, timeout=5). Допиши fetch.py — курсы в rates.csv.",
                hints=("Открой fetch.py: nano fetch.py — одна строка # TODO.",
                       "params= сам допишет к адресу ?base={base}; timeout=5 — в тех же "
                       "скобках."),
                wrong=(_RQ_RUN,),
                alternatives=("s.get(\"http://api/rates?base={base}\", timeout=5) — то же, "
                              "параметр прямо в адресе",),
                key="params"),
        Variant("API курсов теперь пускает только с ключом: заголовок X-Api-Key, а сам ключ — в "
                "переменной окружения " + pdkit.KEY_VAR + " (в код его не пишут). Заголовки "
                "requests передают словарём: s.get(адрес, headers={{\"X-Api-Key\": "
                "os.environ[\"" + pdkit.KEY_VAR + "\"]}}, timeout=5). Допиши fetch.py — курсы "
                "в rates.csv.",
                hints=("Запусти fetch.py как есть и прочти последнюю строку: 401 — сервер "
                       "не узнал тебя.",
                       "Ключ — os.environ[\"" + pdkit.KEY_VAR + "\"], а import os уже стоит "
                       "вверху."),
                wrong=(_RQ_RUN,),
                alternatives=("echo $" + pdkit.KEY_VAR + " — посмотреть ключ в оболочке",),
                key="headers"),
    )
    hints = variants[0].hints
    explain = ("requests делает запрос HTTP: s.get отдаёт ответ, r.raise_for_status() "
               "превращает код ошибки в исключение, r.json() — тело в словарь. Параметры "
               "(params=) и заголовки (headers=) — словари. timeout не даёт скрипту висеть "
               "вечно, а ключ живёт в окружении, не в коде.")
    spell = ("s.get(url, params={…}, headers={…}, timeout=5); r.raise_for_status(); r.json() "
             "→ pd.DataFrame")
    trap_messages = {
        "all": "Здесь курсы ко всем базам: запрос ушёл без params — добавь params={{\"base\": "
               "\"{base}\"}}.",
    }
    MSG_HEAD = "Шапка rates.csv не та: нужна base,currency,rate — как в ответе API."
    MSG_PARTIAL = "Есть {n} курсов из {m}: эти верные, но не все."
    MSG_WRONG = "Не те курсы. Сверь адрес и параметры запроса с заданием — и запусти снова."
    MSG_NOT_REQUESTS = ("В журнале API нет нужного запроса от requests — rates.csv пишет "
                        "fetch.py: " + _RQ_RUN)
    MSG_NO_LOG = "Журнал учебного API не читается — набери reset."
    MSG_401 = ("Сервер ответил 401: нет ключа. Добавь в s.get headers={\"X-Api-Key\": "
               "os.environ[\"" + pdkit.KEY_VAR + "\"]}.")
    MSG_HTTP = ("Сервер ответил ошибкой, и raise_for_status остановил скрипт — код в последней "
                "строке. Сверь адрес с заданием.")

    def prepare(self, box, rng, variant):
        from termit_app import apiserver
        apiserver.link(box)
        full_venv(box)
        return pdkit.rates_data(rng, variant)

    def service(self, box, state):
        from termit_app import apiserver
        return apiserver.open_server(box, pdkit.rates_routes(state))

    def env_for(self, state: dict) -> dict:
        return {pdkit.KEY_VAR: state["key"]} if state.get("key") else {}

    def skeleton(self, state: dict) -> str:
        v = _v(self, state)
        what = {0: "for http://api/rates, wait 5 seconds at most (timeout)",
                1: f"for http://api/rates, only base {state.get('base')} (params), timeout 5",
                2: "for http://api/rates with the header X-Api-Key from " + pdkit.KEY_VAR
                   + ", timeout 5"}[v]
        head = ["# fetch.py: exchange rates from the training API into rates.csv"]
        head += ["import os"] if v == 2 else []
        head += ["", "import pandas as pd", "import sockhttp", "",
                 "# requests.Session for the game server in api.sock;",
                 "# in real life: requests.get(\"https://...\"), the rest is the same",
                 "s = sockhttp.session()"]
        if v == 2:
            head.append('r = s.get("http://api/rates", timeout=5)  # TODO 1: ' + what)
        else:
            head.append("# TODO 1: r = s.get(...) " + what)
        body = ["r.raise_for_status()  # an error code from the server stops the script here",
                'df = pd.DataFrame(r.json()["items"])',
                'df.to_csv("rates.csv", index=False)',
                'print(len(df), "rates saved to rates.csv")']
        return "\n".join(head + body) + "\n"

    def edits(self, state: dict):
        v = _v(self, state)
        if v == 0:
            return [("# TODO 1", 'r = s.get("http://api/rates", timeout=5)')]
        if v == 1:
            return [("# TODO 1", 'r = s.get("http://api/rates", params={"base": "'
                                 + state["base"] + '"}, timeout=5)')]
        return [("# TODO 1", 'r = s.get("http://api/rates", headers={"X-Api-Key": '
                             'os.environ["' + pdkit.KEY_VAR + '"]}, timeout=5)')]

    def _hits(self, ctx) -> List[dict]:
        svc = ctx.service
        if svc is None or not hasattr(svc, "journal"):
            return []
        return [e for e in svc.journal()
                if e.get("path") == "/rates" and e.get("method") == "GET"
                and str(e.get("user_agent") or "").startswith(pdkit.REQUESTS_AGENT)]

    def _fetched(self, ctx) -> bool:
        st = ctx.state
        v = _v(self, st)
        for e in self._hits(ctx):
            if e.get("code") != 200:
                continue
            if v == 1 and e["query"].get("base") != [st["base"]]:
                continue
            return True
        return False

    def crash_message(self, ctx) -> Optional[str]:
        msg = super().crash_message(ctx)
        if pykit.out_type(ctx.box) == "HTTPError":
            got_401 = any(e.get("code") == 401 for e in self._hits(ctx))
            return self.MSG_401 if got_401 else self.MSG_HTTP
        return msg

    def first_problem(self, ctx) -> Optional[str]:
        """C: скрипт как есть падает с 401 — это и есть первый шаг (подсказка 1): отклик про
        ключ важнее «скрипт не тронут»."""
        crash = self.crash_message(ctx)
        if crash in (self.MSG_401, self.MSG_HTTP):
            return crash
        return super().first_problem(ctx)

    @staticmethod
    def _same(rows: List[List[str]], want: List[dict]) -> bool:
        if len(rows) != len(want):
            return False
        try:
            got = sorted((b, c, float(r)) for b, c, r in rows)
        except ValueError:
            return False
        return got == sorted((x["base"], x["currency"], float(x["rate"])) for x in want)

    def check_outputs(self, ctx) -> Verdict:
        st = ctx.state
        rows, msg = pykit.read_csv(ctx.box, "rates.csv", self.run)
        if msg:
            return Verdict(False, msg)
        if rows[0] != pdkit.RATES_HEADER:
            return Verdict(False, self.MSG_HEAD)
        body = [r for r in rows[1:]]
        if any(len(r) != 3 for r in body):
            return Verdict(False, self.MSG_WRONG)
        want = st["expect"]
        if self._same(body, want):
            if ctx.service is None:
                return Verdict(False, self.MSG_NO_LOG)
            if not self._fetched(ctx):
                return Verdict(False, self.MSG_NOT_REQUESTS)
            return Verdict(True)
        for key, trap in st.get("traps") or ():
            if key in self.trap_messages and self._same(body, trap):
                return Verdict(False, self.trap_messages[key].format(**st))
        keyed = {(x["base"], x["currency"]): float(x["rate"]) for x in want}
        ok = [r for r in body if keyed.get((r[0], r[1])) == pykit.as_num(r[2])]
        if body and len(ok) == len(body) < len(want):
            return Verdict(False, self.MSG_PARTIAL.format(n=len(body), m=len(want)))
        return Verdict(False, self.MSG_WRONG)


TASKS.append(RqGet())

# в общий список трека — после задач 1–5 (pydata.py); повторный импорт не дублирует
pydata.add_tasks(TASKS)
