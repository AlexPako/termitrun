"""Трек «Данные»: логи, выгрузки и учебный сервер API. Порядок TASKS — порядок обучения.

Данные строит termit_app/tasks/datakit.py: одинаковые во всех темах, случайные по зерну,
ловушки — построением, а ответ считается тем же предикатом, каким работает BSD-утилита.
Учебный API (termit_app/apiserver.py) поднимает родитель на время задачи через
Task.service: песочница говорит с ним curl --unix-socket api.sock, сети в ней по-прежнему нет.

Ответ из нескольких частей — список в state["answer"] (textnorm.same_parts: порядок любой).
Ловушки ответа — state["traps"]: пары [ключ, значение неверного пути]; сданное значение
неверного пути получает объяснение trap_messages[ключ] вместо «Не то» (тесты-модели —
tests/test_data_tasks.py, настоящий zsh — tests/test_data_traps.py)."""
import hashlib
import json
import os
import re
import shlex
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from termit_app import apiserver, sandbox, textnorm
from termit_app.tasks import datakit, kit
from termit_app.tasks.base import AnswerTask, Task, Variant, Verdict, variant_index

ORDERS = "orders.csv"
LOG = "app.log"
READ_CAP = 4 * 1024 * 1024      # отчёт игрока больше 4 МБ — точно не то, что просили


class _DataAnswer(AnswerTask):
    """Поручение «посчитай и назови»: число или несколько частей в любом порядке."""
    track = "data"
    trap_messages: Dict[str, str] = {}
    fallback = "Не то. Попробуй ещё или набери hint."

    def expected(self, state: dict) -> str:
        exp = state["answer"]
        return " ".join(map(str, exp)) if isinstance(exp, list) else str(exp)

    def answer_kind(self, state: dict) -> str:
        """Одно число — «number»: карточка скажет «сдаёшь одно число», а не «одно слово»
        (FB7: в «Данных» просили ans ЧИСЛО, а форма звала сдать слово)."""
        exp = state["answer"]
        return ("number" if isinstance(exp, (int, float)) and not isinstance(exp, bool)
                else "text")

    def matches(self, given, ctx):
        exp = ctx.state["answer"]
        if isinstance(exp, list):
            return textnorm.same_parts(given, exp)
        return textnorm.same_number(given, exp)

    def wrong_message(self, given, ctx):
        """Ловушки задачи, потом типовые промахи формы (пусто, подписи вокруг числа, не все
        части ответа — FB7: раньше их глушил общий fallback), и только потом fallback."""
        st = ctx.state
        got = textnorm.parts(given)
        exp = st["answer"]
        want = [str(x).casefold() for x in (exp if isinstance(exp, list) else [exp])]
        for key, value in st.get("traps", ()):
            v = str(value).casefold()
            if v in got and v not in want:
                return self.trap_messages[key].format(**st)
        return self.common_mistake(given, ctx) or self.fallback.format(**st)


def _orders(box: Path, rng, **kw):
    text, rows = datakit.orders(rng, rng.randint(300, 900), **kw)
    kit.write(Path(box) / ORDERS, text)
    return rows


# --- D5 ------------------------------------------------------------------------------------

class HeadTail(_DataAnswer):
    """Края файла и счёт строк: заголовок CSV — не данные."""
    id = "head_tail"
    title = "Голова и хвост"
    par = 45
    scroll = ("head -n 5 файл — первые 5 строк, tail -n 3 файл — последние 3. wc -l файл — "
              "сколько в файле строк; wc -l a.csv b.csv — по строке на файл и общий итог total.\n"
              "В CSV первая строка — заголовок с названиями колонок, это не данные: wc -l "
              "посчитает и её. Колонки разделены запятыми; первая здесь — id.")
    variants = (
        Variant("В orders.csv выгрузка заказов. Сколько в ней заказов — строк данных без "
                "заголовка? Ответ: ans ЧИСЛО",
                wrong=("print -r -- $(wc -l < orders.csv)",),
                alternatives=("tail -n +2 orders.csv | wc -l — строки без заголовка сразу, "
                              "вычитать не нужно",)),
        Variant("Глянь на края orders.csv: какой id у самого первого заказа — первой строки под "
                "заголовком? И какая дата у самого последнего? Дата — вторая колонка, вида "
                "ГГГГ-ММ-ДД. Ответ: ans ID ДАТА",
                hints=("Начало файла показывает head, конец — tail.",
                       "Первая строка — заголовок, первый заказ — вторая: head -n 2. Последний "
                       "заказ — tail -n 1, дата в нём — после первой запятой.",
                       "head -n 2 orders.csv — во второй строке первое поле; tail -n 1 "
                       "orders.csv — дата. Сдай: ans ID ДАТА"),
                solution="head -n 2 orders.csv; tail -n 1 orders.csv",
                solution_script="print -r -- $(head -n 2 orders.csv | tail -n 1 | cut -d, -f1) "
                                "$(tail -n 1 orders.csv | cut -d, -f2)",
                wrong=("print -r -- $(head -n 1 orders.csv | cut -d, -f1) "
                       "$(tail -n 1 orders.csv | cut -d, -f2)",
                       "print -r -- $(head -n 2 orders.csv | tail -n 1 | cut -d, -f1) "
                       "$(head -n 2 orders.csv | tail -n 1 | cut -d, -f2)"),
                alternatives=("sed -n 2p orders.csv — ровно вторая строка файла",)),
        Variant("Выгрузку прислали кусками: day_1.csv, day_2.csv и day_3.csv, у каждого куска "
                "свой заголовок. Сколько в трёх файлах заказов всего? Ответ: ans ЧИСЛО",
                hints=("Строки считает wc -l, и ему можно дать сразу несколько файлов.",
                       "wc -l day_1.csv day_2.csv day_3.csv напечатает итог total — в нём и три "
                       "заголовка, по одному на файл.",
                       "wc -l day_1.csv day_2.csv day_3.csv — из итога вычти 3. Сдай: ans ЧИСЛО"),
                solution="wc -l day_1.csv day_2.csv day_3.csv",
                solution_script="print -r -- $(( $(cat day_1.csv day_2.csv day_3.csv | wc -l) "
                                "- 3 ))",
                wrong=("cat day_1.csv day_2.csv day_3.csv | wc -l",
                       "print -r -- $(( $(cat day_*.csv | wc -l) - 1 ))"),
                alternatives=("cat day_*.csv | wc -l — то же число, что total; заголовки вычти "
                              "сам",)),
    )
    hints = ("Строки файла считает wc -l, а начало файла покажет head.",
             "wc -l orders.csv считает и заголовок — первую строку с названиями колонок. "
             "Вычти 1.",
             "wc -l orders.csv → минус 1. Сдай: ans ЧИСЛО")
    solution = "wc -l orders.csv"
    solution_script = "print -r -- $(( $(wc -l < orders.csv) - 1 ))"
    explain = ("Любую выгрузку первым делом меряй: head — что за колонки, tail — чем кончается, wc "
               "-l — сколько строк. Только помни: заголовок wc -l тоже считает. Заказов в файле на "
               "строку меньше, чем строк, а в total сидит по заголовку на каждый файл — вычти их "
               "все.")
    spell = "head -n N / tail -n N файл — первые/последние строки; wc -l файл — сколько строк"
    trap_messages = {
        "header": "Похоже, ты посчитал и заголовок: wc -l считает все строки, а первая — "
                  "названия колонок.",
        "headers": "В итог попали заголовки — по одному в каждом файле, их три.",
        "first": "Это начало файла, а нужен его конец: последнюю строку покажет tail -n 1.",
        "name": "id — это имя колонки из заголовка. Первый заказ — вторая строка файла.",
    }
    fallback = ("Не то. Сдай только сами значения через пробел — без имени файла и лишних "
                "слов. Не уверен — набери hint.")

    def setup_variant(self, box, rng, variant):
        if variant == 2:
            parts = datakit.parts(rng, 3)
            for name, text in parts.items():
                kit.write(Path(box) / name, text)
            total = sum(len(text.splitlines()) for text in parts.values())
            n = total - 3
            return {"answer": n, "traps": [["headers", total], ["headers", total - 1]]}
        rows = _orders(box, rng)
        first, last = rows[0], rows[-1]
        if variant == 1:
            # края дат случайны по зерну и различаются построением (ловушка «head вместо
            # tail»): дни прижаты к [lo, hi], порядок строк сохранён
            lo, hi = rng.randint(1, 5), rng.randint(24, 29)
            for r in rows:
                day = min(max(int(r["date"][-2:]), lo), hi)
                r["date"] = f"{datakit.MONTH}-{day:02d}"
            first["date"], last["date"] = f"{datakit.MONTH}-{lo:02d}", f"{datakit.MONTH}-{hi:02d}"
            kit.write(Path(box) / ORDERS, datakit.render_orders(rows))
            return {"answer": [first["id"], last["date"]],
                    "traps": [["name", "id"], ["first", first["date"]]]}
        # FB12 (N21): первая задача места — один вопрос: только число заказов
        return {"answer": len(rows), "traps": [["header", len(rows) + 1]]}


# --- D6 ------------------------------------------------------------------------------------

def _grep_counts(lines: List[str]) -> dict:
    """Счёт строк, как его дают grep -c, -ic, -vc и -vic на этих строках."""
    return {
        "ci": sum("error" in x.lower() for x in lines),
        "cs": sum("ERROR" in x for x in lines),
        "low": sum("error" in x for x in lines),
        "noninfo": sum("INFO" not in x for x in lines),
        "warn": sum("WARN" in x for x in lines),
        "noerr_cs": sum("ERROR" not in x for x in lines),
        "total": len(lines),
    }


class GrepCount(_DataAnswer):
    """grep -c, -i, -v и склейка ключей; в логе ERROR пишут и как error, Error."""
    id = "grep_count"
    title = "Счётчик ошибок"
    par = 50
    scroll = ("grep СЛОВО файл — строки, где есть слово; -c — count, не печатать, а сосчитать; "
              "-i — не различать большие и маленькие буквы; -v — invert, наоборот: строки БЕЗ "
              "слова.\n"
              "Флаги склеиваются: grep -ic warn server.log, а ещё -vc и -vic. Без -i grep "
              "различает WARN и Warn: для него это разные слова.")
    variants = (
        Variant("В app.log ночь была тяжёлой. Сколько строк с ошибками — слово error любым "
                "регистром: ERROR, Error, error? И сколько строк — НЕ уровня INFO? "
                "Ответ: ans ЧИСЛО ЧИСЛО",
                wrong=("print -r -- $(grep -c ERROR app.log) $(grep -vc INFO app.log)",
                       "print -r -- $(grep -ic error app.log) $(grep -vc info app.log)"),
                alternatives=("grep -i error app.log | wc -l — то же первое число через "
                              "подсчёт строк",)),
        Variant("Сколько строк в app.log обошлись без ошибки — в них нет слова error ни в каком "
                "регистре (ни ERROR, ни Error, ни error)? Ответ: ans ЧИСЛО",
                hints=("Строки без слова даёт -v, регистр отключает -i, счёт — -c.",
                       "Флаги склеиваются в один: grep -vic — без слова, любым регистром, "
                       "числом.",
                       "grep -vic error app.log → ans ЧИСЛО"),
                solution="grep -vic error app.log",
                wrong=("grep -vc ERROR app.log", "grep -ic error app.log"),
                alternatives=("grep -vi error app.log | wc -l — то же через подсчёт строк",)),
        Variant("Два числа по app.log: сколько строк уровня WARN (его пишут только большими) и "
                "сколько строк упоминают error в любом регистре — ERROR, Error или error. "
                "Ответ: ans WARN ОШИБКИ",
                hints=("Строки считает grep -c, регистр отключает -i.",
                       "WARN всегда большими — хватит grep -c. Для error нужен ещё -i: флаги "
                       "склеиваются, grep -ic.",
                       "grep -c WARN app.log → первое; grep -ic error app.log → второе. "
                       "ans ПЕРВОЕ ВТОРОЕ"),
                solution="grep -c WARN app.log; grep -ic error app.log",
                wrong=("print -r -- $(grep -c WARN app.log) $(grep -c ERROR app.log)",
                       "print -r -- $(grep -c WARN app.log) $(grep -c error app.log)"),
                alternatives=("grep -i error app.log | wc -l — второе число через подсчёт "
                              "строк",)),
    )
    hints = ("Строки считает grep -c, регистр отключает -i, «без слова» — -v.",
             "Флаги склеиваются: grep -ic … и grep -vc … — каждый даёт одно число.",
             "grep -ic error app.log → первое число; grep -vc INFO app.log → второе. "
             "ans ПЕРВОЕ ВТОРОЕ")
    solution = "grep -ic error app.log; grep -vc INFO app.log"
    explain = ("grep -c отвечает на «сколько?» за секунду — хоть на миллионе строк. -i плюёт на "
               "регистр, -v переворачивает отбор, а флаги склеиваются в один: -vic.")
    spell = "grep -c слово файл — сколько строк; -i — без регистра; -v — строки без слова"
    trap_messages = {
        "case": "ERROR и error для grep — разные слова: добавь -i, и он сочтёт все написания.",
        "info": "Это все строки лога: info маленькими нет ни в одной, уровень пишется INFO.",
        "no_v": "Это строки С error, а нужны строки без него: переверни отбор флагом -v.",
    }
    fallback = ("Не то. Проверь регистр (-i) и что считаешь: строки со словом или без него "
                "(-v).")
    brackets = ("Скобки в шаблоне — не буквы лога: [INFO] для grep значит «одна из букв I, N, F, "
                "O». Ищи само слово, без скобок: grep -vc INFO.")
    _BRACKET_WORD = re.compile(r"\bgrep\b[^|;]*\[(?:INFO|WARN|ERROR|error|Error)\]", re.I)

    def wrong_message(self, given, ctx):
        if any(self._BRACKET_WORD.search(c.line) for c in ctx.cmds[-3:]):
            return self.brackets
        return super().wrong_message(given, ctx)

    def setup_variant(self, box, rng, variant):
        text, _ = datakit.app_log(rng, days=1, per_day=rng.randint(2000, 5000), mixed_case=True)
        kit.write(Path(box) / LOG, text)
        c = _grep_counts(text.splitlines())
        if variant == 1:
            return {"answer": c["total"] - c["ci"],
                    "traps": [["case", c["noerr_cs"]], ["case", c["total"] - c["low"]],
                              ["no_v", c["ci"]]]}
        if variant == 2:
            return {"answer": [c["warn"], c["ci"]],
                    "traps": [["case", c["cs"]], ["case", c["low"]]]}
        return {"answer": [c["ci"], c["noninfo"]],
                "traps": [["case", c["cs"]], ["case", c["low"]], ["info", c["total"]]]}


# --- D7 ------------------------------------------------------------------------------------

class PipeCount(_DataAnswer):
    """Конвейер из двух grep; сервис ищут по метке поля, а не по имени в тексте."""
    id = "pipe_count"
    title = "Конвейер"
    par = 50
    scroll = ("Палка | — конвейер: вывод левой команды идёт на вход правой. grep A файл | grep "
              "B — строки, где есть и A, и B; … | wc -l или grep -c — сосчитать (wc -c — "
              "characters, байты).\n"
              "Имя бывает и в тексте чужих строк — ищи вместе с меткой поля: user=ann, а не "
              "просто ann.")
    variants = (
        Variant("Сколько ошибок ERROR за ночь выдал сервис {svc}? Его строки в app.log помечены "
                "svc={svc}. Ответ: ans ЧИСЛО",
                wrong=("grep ERROR app.log | grep -c {svc}", "grep -c svc={svc} app.log"),
                alternatives=("grep svc={svc} app.log | grep ERROR | wc -l — тот же счёт, "
                              "звенья в другом порядке",)),
        Variant("Сервис {svc} (метка svc={svc} в app.log) шумел всю ночь. Сколько его строк — НЕ "
                "уровня INFO, то есть всё, кроме обычной болтовни? Ответ: ans ЧИСЛО",
                hints=("Два условия сразу — два grep через палку |; «не INFO» даёт -v.",
                       "Сначала строки сервиса — ищи с меткой svc=, иначе попадут чужие "
                       "упоминания. Потом из них — без INFO: grep -vc.",
                       "grep svc={svc} app.log | grep -vc INFO → ans ЧИСЛО"),
                solution="grep svc={svc} app.log | grep -vc INFO",
                wrong=("grep {svc} app.log | grep -vc INFO", "grep -c svc={svc} app.log"),
                alternatives=("grep svc={svc} app.log | grep -v INFO | wc -l — то же через "
                              "подсчёт строк",)),
        Variant("Два числа про сервис {svc}: сколько всего строк он написал в app.log (они "
                "помечены svc={svc}) и сколько из них ERROR. Соседи тоже поминают {svc} в "
                "тексте — их строки не его. Ответ: ans ВСЕГО ОШИБКИ",
                hints=("Строки сервиса — по метке svc=, ошибки среди них — вторым grep через |.",
                       "grep -c svc={svc} app.log — все его строки. Для ошибок добавь звено: "
                       "… | grep -c ERROR.",
                       "grep -c svc={svc} app.log → первое; grep svc={svc} app.log | grep -c "
                       "ERROR → второе. ans ВСЕГО ОШИБКИ"),
                solution="grep -c svc={svc} app.log; grep svc={svc} app.log | grep -c ERROR",
                wrong=("print -r -- $(grep -c {svc} app.log) $(grep {svc} app.log | grep -c ERROR)",
                       "print -r -- $(grep -c {svc} app.log) "
                       "$(grep svc={svc} app.log | grep -c ERROR)"),
                alternatives=("grep svc={svc} app.log | wc -l — первое число через подсчёт "
                              "строк",)),
    )
    hints = ("Два условия сразу — два grep через палку |.",
             "Сначала оставь строки ERROR, потом из них — сервис. Ищи с меткой svc=, иначе "
             "попадут чужие упоминания.",
             "grep ERROR app.log | grep -c svc={svc} → ans ЧИСЛО")
    solution = "grep ERROR app.log | grep -c svc={svc}"
    explain = ("Конвейер — главный фокус терминала: мелкие команды, сцепленные палкой, раскалывают "
               "вопрос, который ни одна не осилит в одиночку. Имя ищи с меткой поля — иначе в счёт "
               "налезут строки, где его просто помянули.")
    spell = "команда | команда — конвейер; grep A файл | grep -c B — строки с A и B"
    trap_messages = {
        "mention": "В цифру попали строки, где {svc} только упомянут: ищи с меткой svc={svc}.",
        "all": "Это все строки {svc}, а нужны не все: добавь второе звено конвейера.",
    }
    fallback = "Не то. Строки {svc} ищи по метке svc={svc}, второе условие — вторым grep через |."

    def setup_variant(self, box, rng, variant):
        svc = rng.choice(datakit.SERVICES)
        text, _ = datakit.app_log(rng, days=1, per_day=rng.randint(1500, 3000),
                                  mention_traps=(svc, rng.randint(3, 6)))
        kit.write(Path(box) / LOG, text)
        lines = text.splitlines()
        own = [x for x in lines if f"svc={svc}" in x]
        naive = [x for x in lines if svc in x]
        err, nerr = (sum("ERROR" in x for x in own), sum("ERROR" in x for x in naive))
        if variant == 1:
            return {"svc": svc, "answer": sum("INFO" not in x for x in own),
                    "traps": [["mention", sum("INFO" not in x for x in naive)],
                              ["all", len(own)]]}
        if variant == 2:
            return {"svc": svc, "answer": [len(own), err],
                    "traps": [["mention", len(naive)], ["mention", nerr]]}
        return {"svc": svc, "answer": err, "traps": [["mention", nerr], ["all", len(own)]]}


# --- D8 ------------------------------------------------------------------------------------

class RedirectReport(Task):
    """> и >>: заголовок — через >, строки — через >>; поле CSV ищут с запятыми по краям."""
    id = "redirect_report"
    track = "data"
    title = "Отчёт в файл"
    par = 60
    scroll = ("команда > файл — записать вывод в файл (если файл был — он стирается!); "
              "команда >> файл — дописать в конец. cat файл — проверить, что вышло.\n"
              "head -1 файл — только первая строка, заголовок. Поле CSV ищи с запятыми по "
              "краям: ',paid,' не спутать с paid в заметке.")
    variants = (
        Variant("Сделай refunds.csv: первой строкой — заголовок из orders.csv, дальше — все "
                "заказы со статусом refund, в том же порядке. Заметки «refund requested» у "
                "оплаченных — не возвраты.",
                wrong=("head -1 orders.csv > refunds.csv; grep ',refund,' orders.csv > refunds.csv",
                       "head -1 orders.csv > refunds.csv; grep refund orders.csv >> refunds.csv"),
                alternatives=("grep -e ^id, -e ,refund, orders.csv > refunds.csv — одной "
                              "командой",)),
        Variant("Нужен файл {out}: сверху заголовок orders.csv, под ним — заказы из города {city} "
                "со статусом {status}, только они и в исходном порядке. Город — третья колонка, "
                "статус — шестая.",
                hints=("Две команды: одна пишет заголовок в файл, вторая дописывает строки.",
                       "Заголовок — head -1 с >. Два условия — два grep через |, оба с запятыми "
                       "по краям; дописывает >>.",
                       "head -1 orders.csv > {out}; grep ',{city},' orders.csv | grep "
                       "',{status},' >> {out}; cat {out}"),
                solution="head -1 orders.csv > {out}; grep ',{city},' orders.csv | grep "
                         "',{status},' >> {out}",
                wrong=("head -1 orders.csv > {out}; grep ',{status},' orders.csv >> {out}",
                       "head -1 orders.csv > {out}; grep ',{city},' orders.csv | grep "
                       "',{status},' > {out}"),
                alternatives=("grep ',{status},' orders.csv | grep ',{city},' >> {out} — "
                              "звенья можно поменять местами",)),
        Variant("В report.csv уже лежит отчёт о возвратах: заголовок и старые строки. Допиши в "
                "конец все заказы со статусом refund из orders.csv, в их порядке. Старое не "
                "трогай, второй заголовок не нужен; заметка «refund requested» — не возврат.",
                hints=("Старое в файле должно остаться: дописывают, а не записывают.",
                       "> стёр бы report.csv целиком, >> дописывает в конец. Статус ищи с "
                       "запятыми по краям, заголовок уже есть.",
                       "grep ',refund,' orders.csv >> report.csv; cat report.csv"),
                solution="grep ',refund,' orders.csv >> report.csv",
                wrong=("grep ',refund,' orders.csv > report.csv",
                       "head -1 orders.csv >> report.csv; grep ',refund,' orders.csv >> "
                       "report.csv"),
                alternatives=("tail -n 3 report.csv — проверить хвост после дописывания",)),
    )
    hints = ("Нужны две команды: одна пишет заголовок в файл, вторая дописывает строки.",
             "Первая — head -1 с >, вторая — grep с >>. Статус ищи с запятыми по краям, иначе "
             "зацепишь заметки.",
             "head -1 orders.csv > refunds.csv; grep ',refund,' orders.csv >> refunds.csv; "
             "cat refunds.csv")
    solution = "head -1 orders.csv > refunds.csv; grep ',refund,' orders.csv >> refunds.csv"
    explain = ("> начинает файл с чистого листа, >> дописывает в конец. Новый отчёт — шапку через "
               ">, строки через >>. В готовый файл — только >>, а то старое улетит без следа.")
    spell = "> файл — записать вывод (старое стирается); >> файл — дописать в конец"

    def setup_variant(self, box, rng, variant):
        rows = _orders(box, rng, refund_notes=rng.randint(3, 6))
        if variant == 1:
            return self._city(box, rng, rows)
        if variant == 2:
            return self._append(box, rng, rows)
        want = [datakit.ORDER_HEADER] + self._lines([r for r in rows if r["status"] == "refund"])
        return {"out": "refunds.csv", "want": want, "base": [datakit.ORDER_HEADER]}

    @staticmethod
    def _lines(rows) -> List[str]:
        return datakit.render_orders(rows).splitlines()[1:]

    def _city(self, box, rng, rows):
        status = rng.choice(("pending", "cancel"))
        by = Counter(r["city"] for r in rows if r["status"] == status)
        city = rng.choice(sorted(c for c, n in by.items() if n >= 2))
        pick = [r for r in rows if r["city"] == city and r["status"] == status]
        return {"out": f"{city}_{status}.csv", "city": city, "status": status,
                "want": [datakit.ORDER_HEADER] + self._lines(pick),
                "base": [datakit.ORDER_HEADER]}

    def _append(self, box, rng, rows):
        """Старый отчёт за август: заголовок и 2–5 возвратов с id ниже сентябрьских."""
        first = int(rows[0]["id"][2:])
        k = rng.randint(2, 5)
        ids = sorted(rng.sample(range(first - 400, first - 1), k))
        old = [{"id": f"A-{i}", "date": f"2726-08-{d:02d}", "city": rng.choice(datakit.CITIES),
                "product": kit.latin(rng), "amount": rng.randint(100, 9999), "status": "refund",
                "note": ""} for i, d in zip(ids, sorted(rng.choices(range(1, 32), k=k)))]
        base = datakit.render_orders(old).splitlines()
        kit.write(Path(box) / "report.csv", "\n".join(base) + "\n")
        want = base + self._lines([r for r in rows if r["status"] == "refund"])
        return {"out": "report.csv", "want": want, "base": base}

    def check(self, ctx):
        st = ctx.state
        data = sandbox.read_in_box(ctx.box, st["out"], READ_CAP)
        if data is None:
            return Verdict(False)
        got = data.decode("utf-8", errors="replace").splitlines()
        want, base = st["want"], st["base"]
        if got == want:
            return Verdict(True)
        if got == base or not got:
            return Verdict(False)           # работа идёт: заголовок на месте, строк ещё нет
        return Verdict(False, self._why(got, st))

    @staticmethod
    def _why(got: List[str], st: dict) -> str:
        header = datakit.ORDER_HEADER
        want, base = st["want"], st["base"]
        rows = want[len(base):]
        old = len(base) > 1         # вариант с готовым отчётом: его не стирают
        if got.count(header) > 1:
            if old:
                return ("Заголовок дважды: в отчёте он уже был. Набери reset — отчёт вернётся "
                        "как был, — и допиши только строки через >>.")
            return "Заголовок дважды — head дописан лишний раз. Начни файл заново через >."
        if old and not set(base[1:]) <= set(got):
            return ("Старый отчёт затёрт: > стирает файл. Набери reset — файл вернётся, — и "
                    "допиши строки через >>.")
        if got and got == rows:
            return ("Заголовка нет — его кладут первым через >, а строки дописывают >> (второй > "
                    "стирает первый).")
        if any(datakit.REFUND_NOTE in x for x in got[len(base):]):
            return ("Попали оплаченные с заметкой «refund requested» — ищи статус с запятыми по "
                    "краям: ,refund,")
        if len(got) > len(want) and set(got) == set(want):
            again = (" Набери reset — отчёт вернётся как был, — и допиши один раз." if old else
                     " Начни файл заново через >.")
            return "Строки задвоились: >> дописал их второй раз." + again
        if "city" in st and len(got) > len(want) and set(want) <= set(got):
            return f"Лишние строки: в отчёт попали другие города, а нужен только {st['city']}."
        lost = [x for x in want if x not in got]
        if lost:
            return (f"Не хватает строк, например «{lost[0]}». Собери выборку заново: заголовок — "
                    "через >, строки — через >>.")
        extra = [x for x in got if x not in want]
        if extra:
            return f"Лишняя строка: «{extra[0]}» — её в выборке быть не должно."
        return "Строки те, но порядок другой: заголовок первым, дальше строки, как в orders.csv."


# --- D9 ------------------------------------------------------------------------------------

class CutUniq(_DataAnswer):
    """cut по полю и символам, tail -n +2 без заголовка, sort -u без повторов."""
    id = "cut_uniq"
    title = "Срез колонки"
    par = 50
    scroll = ("cut -d, -f3 файл — третья колонка CSV: -d — разделитель, -f — номер поля (-f2, "
              "-f4 — вторая, четвёртая). cut -c1-7 — characters, символы с 1-го по 7-й.\n"
              "tail -n +2 — всё со 2-й строки, без заголовка. sort -u — отсортировать и убрать "
              "повторы (как sort | uniq).")
    variants = (
        Variant("Из скольких разных городов пришли заказы в orders.csv? Город — третья колонка. "
                "Ответ: ans ЧИСЛО",
                wrong=("cut -d, -f3 orders.csv | sort -u | wc -l",
                       "cut -d, -f3 orders.csv | tail -n +2 | wc -l"),
                alternatives=("cut -d, -f3 orders.csv | tail -n +2 | sort | uniq | wc -l — то "
                              "же длиннее",)),
        Variant("Сколько разных товаров заказывали из города {city}? Товар — четвёртая колонка "
                "orders.csv, город — третья. Ответ: ans ЧИСЛО",
                hints=("Строки города отберёт grep, колонку вырежет cut, повторы уберёт sort -u.",
                       "grep ',{city},' — только заказы города, заголовка среди них нет. Товар — "
                       "cut -d, -f4.",
                       "grep ',{city},' orders.csv | cut -d, -f4 | sort -u | wc -l"),
                solution="grep ',{city},' orders.csv | cut -d, -f4 | sort -u | wc -l",
                wrong=("cut -d, -f4 orders.csv | tail -n +2 | sort -u | wc -l",
                       "grep ',{city},' orders.csv | cut -d, -f4 | wc -l"),
                alternatives=("grep ',{city},' orders.csv | cut -d, -f4 | sort | uniq -c — "
                              "заодно и сколько раз брали каждый",)),
        Variant("В orders.csv заказы за несколько месяцев. В скольких разных месяцах были "
                "заказы? Дата — вторая колонка, вида 2726-03-15; месяц — её первые 7 символов. "
                "Ответ: ans ЧИСЛО",
                hints=("Колонку вырежет cut -d, -f2, кусок строки — cut -c, повторы — sort -u.",
                       "Месяц — первые 7 символов даты: cut -c1-7. Заголовок date срежет "
                       "tail -n +2.",
                       "cut -d, -f2 orders.csv | tail -n +2 | cut -c1-7 | sort -u | wc -l"),
                solution="cut -d, -f2 orders.csv | tail -n +2 | cut -c1-7 | sort -u | wc -l",
                wrong=("cut -d, -f2 orders.csv | tail -n +2 | sort -u | wc -l",
                       "cut -d, -f2 orders.csv | cut -c1-7 | sort -u | wc -l"),
                alternatives=("tail -n +2 orders.csv | cut -d, -f2 | cut -c1-7 | sort -u | "
                              "wc -l — заголовок можно срезать и первым звеном",)),
    )
    hints = ("Колонку вырезает cut, повторы убирает sort -u, строки считает wc -l.",
             "Город — третья колонка: cut -d, -f3. Заголовок отрежь tail -n +2.",
             "cut -d, -f3 orders.csv | tail -n +2 | sort -u | wc -l")
    solution = "cut -d, -f3 orders.csv | tail -n +2 | sort -u | wc -l"
    explain = ("cut и sort -u за пару секунд показывают, что вообще водится в колонке. cut -c режет"
               " по символам — так от даты остаётся месяц.")
    spell = ("cut -d, -fN — колонка N; cut -c1-7 — символы; tail -n +2 — без заголовка; "
             "sort -u — без повторов")
    trap_messages = {
        "header": "В счёт попало слово {header} из заголовка: срежь его tail -n +2.",
        "rows": "Это число строк — повторы не убраны: sort -u.",
        "all": "Это товары всех городов, а нужны только из {city}: сначала grep ',{city},'.",
        "dates": "Это разные даты, а нужны месяцы: cut -c1-7 оставит от даты ГГГГ-ММ.",
    }
    fallback = "Не то. Вырежи колонку, убери повторы sort -u и проверь, не попал ли заголовок."

    def setup_variant(self, box, rng, variant):
        rows = _orders(box, rng)
        if variant == 1:
            return self._products(box, rng, rows)
        if variant == 2:
            return self._months(box, rng, rows)
        n = len({r["city"] for r in rows})
        return {"answer": n, "header": "city", "traps": [["header", n + 1], ["rows", len(rows)]]}

    @staticmethod
    def _products(box, rng, rows):
        """Город-лидер по числу заказов; одного товара у него нет (а у других есть)."""
        city = datakit.leader(Counter(r["city"] for r in rows))
        mine = [r for r in rows if r["city"] == city]
        have = sorted({r["product"] for r in mine})
        gone = rng.choice(have)
        rest = [p for p in have if p != gone]
        for r in mine:
            if r["product"] == gone:
                r["product"] = rng.choice(rest)
        if not any(r["product"] == gone for r in rows):
            rng.choice([r for r in rows if r["city"] != city])["product"] = gone
        kit.write(Path(box) / ORDERS, datakit.render_orders(rows))
        n = len({r["product"] for r in mine})
        return {"city": city, "answer": n, "header": "product",
                "traps": [["all", len({r["product"] for r in rows})], ["rows", len(mine)]]}

    @staticmethod
    def _months(box, rng, rows):
        """Даты разложены по 4–9 месяцам подряд кусками; порядок строк и дней сохранён."""
        # без февраля: дни в выгрузке — до 30-го
        pool = ([f"2725-{m:02d}" for m in (10, 11, 12)] +
                [f"2726-{m:02d}" for m in range(1, 10) if m != 2])
        months = sorted(rng.sample(pool, rng.randint(4, 9)))
        cuts = sorted(rng.sample(range(1, len(rows)), len(months) - 1))
        for i, (a, b) in enumerate(zip([0] + cuts, cuts + [len(rows)])):
            for r in rows[a:b]:
                r["date"] = months[i] + r["date"][7:]
        kit.write(Path(box) / ORDERS, datakit.render_orders(rows))
        dates = len({r["date"] for r in rows})
        return {"answer": len(months), "header": "date",
                "traps": [["dates", dates], ["header", len(months) + 1]]}


# --- D10 -----------------------------------------------------------------------------------

def _runs(values) -> List[int]:
    """Длины кусков подряд идущих одинаковых значений — что насчитает uniq -c без sort."""
    out: List[int] = []
    prev = object()
    for v in values:
        if out and v == prev:
            out[-1] += 1
        else:
            out.append(1)
        prev = v
    return out


def _rank_gaps(rows: List[dict], col: str, k: int, margin: int, rng) -> List[str]:
    """Первые k мест колонки col — с запасом не меньше margin над следующим местом: строки
    следующего переписываются на стоящего выше. Возвращает значения по убыванию частоты."""
    for _ in range(100000):
        counts = Counter(r[col] for r in rows)
        ranked = sorted(counts, key=lambda x: (-counts[x], x))
        for i in range(min(k, len(ranked) - 1)):
            if counts[ranked[i]] - counts[ranked[i + 1]] < margin:
                donors = [r for r in rows if r[col] == ranked[i + 1]
                          and r.get("note") != datakit.REFUND_NOTE]
                rng.choice(donors)[col] = ranked[i]
                break
        else:
            return ranked
    raise ValueError(f"не вышло развести места колонки {col}")


def _break_runs(rows: List[dict], col: str, value: str, rng) -> None:
    """Строки value не стоят одним сплошным куском: иначе uniq -c без sort случайно дал бы
    верное число. Обмен значениями двух строк счёт не меняет."""
    for _ in range(1000):
        vals = [r[col] for r in rows]
        if max(_runs(vals)) < vals.count(value) or len(set(vals)) < 2:
            return
        i = vals.index(value)
        j = rng.choice([n for n, v in enumerate(vals) if v != value])
        rows[i][col], rows[j][col] = rows[j][col], rows[i][col]


class TopValues(_DataAnswer):
    """sort | uniq -c | sort -rn | head — топ значений колонки; uniq видит только соседей."""
    id = "top_values"
    title = "Топ значений"
    par = 60
    scroll = ("uniq -c — склеить одинаковые СОСЕДНИЕ строки и приписать, сколько их было. "
              "Поэтому сначала sort. sort -rn — по числу, от большего к меньшему (r — reverse, "
              "обратный порядок); head -3 — первые три.\n"
              "Топ значений колонки: … | sort | uniq -c | sort -rn | head")
    variants = (
        Variant("Какой товар в orders.csv заказывали чаще всего и сколько раз? Товар — четвёртая "
                "колонка. Ответ: ans ТОВАР ЧИСЛО",
                wrong=("cut -d, -f4 orders.csv | tail -n +2 | uniq -c | sort -rn | head -1",),
                alternatives=("cut -d, -f4 orders.csv | tail -n +2 | sort | uniq -c | sort -rn | "
                              "head -3 — заодно видно, с каким запасом лидер",)),
        Variant("Какой товар в orders.csv на ВТОРОМ месте по числу заказов и сколько у него "
                "заказов? Товар — четвёртая колонка. Ответ: ans ТОВАР ЧИСЛО",
                hints=("Сначала топ: вырежи колонку, sort | uniq -c, самые частые наверх — "
                       "sort -rn.",
                       "Вторая строка топа: head -n 2 оставит две первые, tail -n 1 — последнюю "
                       "из них.",
                       "cut -d, -f4 orders.csv | tail -n +2 | sort | uniq -c | sort -rn | "
                       "head -n 2 | tail -n 1"),
                solution="cut -d, -f4 orders.csv | tail -n +2 | sort | uniq -c | sort -rn | "
                         "head -n 2 | tail -n 1",
                wrong=("cut -d, -f4 orders.csv | tail -n +2 | sort | uniq -c | sort -rn | head -1",
                       "cut -d, -f4 orders.csv | tail -n +2 | uniq -c | sort -rn | head -n 2 | "
                       "tail -n 1"),
                alternatives=("… | sort -rn | head -3 — и глазами взять вторую строку",)),
        Variant("Из какого города чаще всего возвращают заказы — статус refund — и сколько там "
                "возвратов? Город — третья колонка orders.csv; заметка «refund requested» — не "
                "возврат. Ответ: ans ГОРОД ЧИСЛО",
                hints=("Сначала оставь только возвраты, потом топ по колонке города.",
                       "Статус ищи с запятыми по краям: grep ',refund,'. Город — cut -d, -f3, "
                       "дальше формула топа.",
                       "grep ',refund,' orders.csv | cut -d, -f3 | sort | uniq -c | sort -rn | "
                       "head -1"),
                solution="grep ',refund,' orders.csv | cut -d, -f3 | sort | uniq -c | sort -rn | "
                         "head -1",
                wrong=("cut -d, -f3 orders.csv | tail -n +2 | sort | uniq -c | sort -rn | head -1",
                       "grep ',refund,' orders.csv | cut -d, -f3 | uniq -c | sort -rn | head -1"),
                alternatives=("grep ',refund,' orders.csv | cut -d, -f3 | sort | uniq -c | "
                              "sort -rn | head -3 — видно и запас лидера",)),
    )
    hints = ("Сначала вырежи колонку product, потом посчитай одинаковые: sort | uniq -c.",
             "uniq видит только соседей — без sort перед ним счёт неверный. Самые частые "
             "наверх — sort -rn.",
             "cut -d, -f4 orders.csv | tail -n +2 | sort | uniq -c | sort -rn | head -1")
    solution = "cut -d, -f4 orders.csv | tail -n +2 | sort | uniq -c | sort -rn | head -1"
    explain = ("sort | uniq -c | sort -rn — формула топа: частые IP, товары, ошибки. Забудешь "
               "первый sort — uniq насчитает куски подряд, а не все одинаковые строки, и топ "
               "соврёт.")
    spell = "sort | uniq -c | sort -rn | head — топ самых частых значений"
    trap_messages = {
        "count": "Название верное, а число — нет: uniq склеивает только соседние строки, перед "
                 "ним нужен sort.",
        "count_refund": "Город верный, а число — нет: перед uniq нужен sort, а статус ищи с "
                        "запятыми — ',refund,'.",
        "nosort": "Это длина одного куска, а не счёт: uniq без sort видит только соседей. "
                  "Сначала sort, потом uniq -c.",
        "first": "Это первое место, а нужно второе: head -n 2 | tail -n 1 оставит вторую строку "
                 "топа.",
        "all": "Это лидер по всем заказам, а нужны только возвраты: сначала grep ',refund,'.",
    }
    fallback = ("Не то. Топ колонки: вырежи её, sort | uniq -c | sort -rn. Сдай название и "
                "число через пробел.")

    def wrong_message(self, given, ctx):
        st = ctx.state
        got = textnorm.parts(given)
        name, n = (str(x).casefold() for x in st["answer"])
        numbers = [w for w in got if textnorm.as_number(w) is not None]
        if name in got and n not in got and numbers:
            return self.trap_messages[st["count_key"]]
        return super().wrong_message(given, ctx)

    def setup_variant(self, box, rng, variant):
        rows = _orders(box, rng, refund_notes=rng.randint(3, 6))
        if variant == 2:
            return self._refunds(box, rng, rows)
        ranked = _rank_gaps(rows, "product", 3, 3, rng)
        kit.write(Path(box) / ORDERS, datakit.render_orders(rows))
        counts = Counter(r["product"] for r in rows)
        name = ranked[1] if variant == 1 else ranked[0]
        runs = _runs(r["product"] for r in rows)
        traps = [["nosort", x] for x in sorted(set(runs))]
        if variant == 1:
            traps.append(["first", ranked[0]])
        return {"answer": [name, counts[name]], "count_key": "count", "traps": traps}

    @staticmethod
    def _refunds(box, rng, rows):
        """Лидер возвратов (с запасом) — не лидер всех заказов (с запасом)."""
        refunds = [r for r in rows if r["status"] == "refund"]
        rest = [r for r in rows if r["status"] != "refund"]
        city = rng.choice(sorted({r["city"] for r in refunds}))
        datakit.ensure_leader(refunds, "city", 3, rng, value=city)
        _break_runs(refunds, "city", city, rng)
        n = sum(r["city"] == city for r in refunds)
        # все заметки «refund requested» — у оплаченных заказов того же города: голый grep
        # refund даёт верный город, но число больше на 3–6 (ловушка построением)
        for r in rest:
            if r["note"] == datakit.REFUND_NOTE:
                r["city"] = city
        others = sorted({r["city"] for r in rest} - {city})
        top = datakit.leader(Counter(r["city"] for r in rest if r["city"] in others))
        datakit.ensure_leader(rest, "city", n + 3, rng, value=top)
        kit.write(Path(box) / ORDERS, datakit.render_orders(rows))
        runs = _runs(r["city"] for r in refunds)
        return {"answer": [city, n], "count_key": "count_refund",
                "traps": [["nosort", x] for x in sorted(set(runs))] + [["all", top]]}


# --- D11 -----------------------------------------------------------------------------------

PAID_NOTE = "paid twice"      # заметка у неоплаченных: голый grep paid цепляет и её


class FlagReview(_DataAnswer):
    """FB3 (6): повторение флагов без подсказки на карточке — нужный флаг игрок находит в man
    сам и склеивает со знакомыми (-c, -n): grep -w, uniq -d, grep -m."""
    id = "flag_review"
    title = "Флаг найди сам"
    par = 60
    scroll = ("Повторение. Нужного флага на этой карточке нет — найди его сам: man КОМАНДА, "
              "/слово и Enter, q — выйти.\n"
              "Знакомые флаги складывай с новым: короткие склеивают (grep -ci = grep -c -i), "
              "значение пишут следом за флагом (head -n 3). Регистр важен.")
    variants = (
        Variant("Сколько строк в words.txt содержат art отдельным словом — не start, не party, "
                "не artist? У grep есть флаг «только целые слова» — найди его в man grep (/word) "
                "и сложи с подсчётом -c. Ответ: ans ЧИСЛО",
                wrong=("grep -c art words.txt",),
                alternatives=("grep -w art words.txt | wc -l — то же через wc",)),
        Variant("В names.txt одно имя записано дважды. Какое? У uniq есть флаг, который "
                "печатает только повторы, — найди его в man uniq (/repeated). Помни: uniq видит "
                "только соседние строки. Ответ: ans ИМЯ",
                hints=("Повторы uniq находит только среди соседей — сначала sort.",
                       "В man uniq ищи /repeated — нужный флаг печатает только повторы.",
                       "sort names.txt | uniq -d"),
                solution="sort names.txt | uniq -d",
                wrong=("sort names.txt | uniq | head -1",),
                alternatives=("sort names.txt | uniq -c | sort -rn | head -1 — формула топа "
                              "тоже покажет имя",)),
        Variant("В app.log ошибок ERROR много. На какой строке файла — первая? Номер строки "
                "даёт -n, а остановиться после первого совпадения grep умеет сам — найди флаг в "
                "man grep (/max). Ответ: ans НОМЕР",
                hints=("Номер строки у grep — флаг -n.",
                       "Остановиться после N совпадений — флаг -m со значением: -m 1.",
                       "grep -n -m 1 ERROR app.log — номер до двоеточия"),
                solution="grep -n -m 1 ERROR app.log",
                solution_script="grep -n -m 1 ERROR app.log | cut -d: -f1",
                wrong=("grep -c ERROR app.log",),
                alternatives=("grep -n ERROR app.log | head -1 — то же через head",)),
    )
    man_flags = ("-w", "-cw", "-d", "-m")
    hints = ("Подсчёт строк у grep — -c. Целые слова — флаг в man grep, ищи /word.",
             "Флаги склеивают: подсчёт и «целое слово» вместе — -cw.",
             "grep -cw art words.txt")
    solution = "grep -cw art words.txt"
    explain = ("Флаг вылетел из головы — man КОМАНДА и /слово, гадать не надо. Новый флаг клеится к"
               " знакомому: grep -cw — сосчитать строки с целым словом.")
    spell = "grep -w — целое слово; uniq -d — только повторы; grep -m 1 — первое совпадение"
    trap_messages = {
        "partial": "Это все строки, где есть art, — и внутри start, party, artist. Нужны строки, "
                   "где art стоит отдельным словом.",
        "lines": "Это число совпадений, а нужен номер строки первой ошибки: -n и -m 1.",
    }
    MSG_WHOLE_LINE = ("Это строка вывода целиком: grep -n ставит номер в начало, до первого "
                      "двоеточия. Сдай только этот номер.")

    def wrong_message(self, given, ctx):
        # grep -n печатает «6:10:06 ERROR …» — игрок сдаёт всю строку или её начало
        first = str(ctx.state.get("answer"))
        if ctx.state.get("_variant") == 2 and textnorm.clean(given).startswith(first + ":"):
            return self.MSG_WHOLE_LINE
        return super().wrong_message(given, ctx)

    WORDS = ("art", "start", "party", "artist", "smart", "cart", "apart")

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            names = rng.sample(["anna", "boris", "vera", "gleb", "ilya", "kira", "lev", "mila",
                                "nina", "oleg"], 7)
            twice = rng.choice(sorted(names)[1:])     # не первое по алфавиту: wrong
            rows = names + [twice]
            rng.shuffle(rows)
            while any(a == b for a, b in zip(rows, rows[1:])):    # повтор — не по соседству
                rng.shuffle(rows)
            kit.write(box / "names.txt", "\n".join(rows) + "\n")
            return {"answer": [twice], "traps": []}
        if variant == 2:
            n = rng.randint(14, 22)
            first = rng.randint(4, n - 6)
            rows = []
            for i in range(1, n + 1):
                level = "ERROR" if i == first or (i > first and rng.random() < 0.3) else \
                    rng.choice(["INFO", "WARN"])
                rows.append(f"10:{i:02d} {level} worker {kit.latin(rng)}")
            errors = sum(1 for r in rows if " ERROR " in r)
            if errors == first:                 # счёт ошибок не должен совпасть с номером
                rows.append(f"10:{n + 1:02d} ERROR worker {kit.latin(rng)}")
                errors += 1
            kit.write(box / LOG, "\n".join(rows) + "\n")
            return {"answer": first, "traps": [["lines", errors]]}
        rows = []
        whole = 0
        for _ in range(rng.randint(10, 16)):
            picked = rng.sample(self.WORDS, 2)
            rows.append(f"{picked[0]} {kit.word(rng)} {picked[1]}")
            whole += "art" in picked
        if not whole:
            rows[0] = f"art {kit.word(rng)} start"
            whole = 1
        rows.insert(rng.randrange(len(rows)), f"start {kit.word(rng)} party")   # только кусок
        partial = sum(1 for r in rows if "art" in r)
        kit.write(box / "words.txt", "\n".join(rows) + "\n")
        return {"answer": whole, "traps": [["partial", partial]]}


class AwkSum(_DataAnswer):
    """awk -F, — колонки, условие перед скобками, копилка s и итог в END."""
    id = "awk_sum"
    title = "Сумма по колонке"
    par = 60
    scroll = ("awk -F, '{print $5}' файл — пятая колонка (-F — разделитель). Условие перед "
              "скобками: awk -F, '$6==\"paid\"' — только такие строки; слово — в двойных "
              "кавычках, число — без: $5>1000.\n"
              "Два условия сразу — &&: '$3==\"город\" && $6==\"paid\"'. Сумма: '{s+=$5} END "
              "{print s}' — копить в s и напечатать в конце.")
    variants = (
        Variant("На какую сумму набралось заказов со статусом {status} в orders.csv? Нужна "
                "сумма колонки amount — она пятая, статус — шестая. Ответ: ans ЧИСЛО",
                wrong=("awk -F, '{{s+=$5}} END {{print s}}' orders.csv",
                       "grep {status} orders.csv | awk -F, '{{s+=$5}} END {{print s}}'"),
                alternatives=("grep ',{status},' orders.csv | awk -F, '{{s+=$5}} END {{print s}}' "
                              "— отбор grep-ом, сумма awk-ом",)),
        Variant("Сколько выручки дал город {city}: сумма amount только по ОПЛАЧЕННЫМ заказам "
                "(status = paid)? Город — третья колонка orders.csv, amount — пятая, статус — "
                "шестая. Ответ: ans ЧИСЛО",
                hints=("Два условия на строку — awk соединяет их через &&.",
                       "$3==\"{city}\" && $6==\"paid\" перед скобками отберёт строки; s+=$5 копит, "
                       "END печатает.",
                       "awk -F, '$3==\"{city}\" && $6==\"paid\" {{s+=$5}} END {{print s}}' "
                       "orders.csv"),
                solution="awk -F, '$3==\"{city}\" && $6==\"paid\" {{s+=$5}} END {{print s}}' "
                         "orders.csv",
                wrong=("awk -F, '$3==\"{city}\" {{s+=$5}} END {{print s}}' orders.csv",
                       "awk -F, '$6==\"paid\" {{s+=$5}} END {{print s}}' orders.csv"),
                alternatives=("grep ',{city},' orders.csv | awk -F, '$6==\"paid\" {{s+=$5}} END "
                              "{{print s}}' — город отобрал grep",)),
        Variant("Сколько принесли крупные заказы — те, где amount строго больше {limit}? Статус "
                "не важен; amount — пятая колонка orders.csv. Ответ: ans ЧИСЛО",
                hints=("Условие на число пишут без кавычек: $5>…, перед фигурными скобками.",
                       "> — строго больше: заказ ровно на {limit} не в счёт. s+=$5 копит, END "
                       "печатает.",
                       "awk -F, '$5>{limit} {{s+=$5}} END {{print s}}' orders.csv"),
                solution="awk -F, '$5>{limit} {{s+=$5}} END {{print s}}' orders.csv",
                wrong=("awk -F, '$5>={limit} {{s+=$5}} END {{print s}}' orders.csv",
                       "awk -F, '{{s+=$5}} END {{print s}}' orders.csv"),
                alternatives=("awk -F, 'NR>1 && $5>{limit} {{s+=$5}} END {{print s}}' orders.csv "
                              "— то же, заголовок пропущен явно: NR — номер строки, NR>1 — со второй",)),
    )
    hints = ("Складывает awk: колонка amount — пятая, разделитель — запятая.",
             "Условие $6==\"{status}\" перед фигурными скобками отберёт строки; s+=$5 копит, END "
             "печатает.",
             "awk -F, '$6==\"{status}\" {{s+=$5}} END {{print s}}' orders.csv")
    solution = "awk -F, '$6==\"{status}\" {{s+=$5}} END {{print s}}' orders.csv"
    explain = ("awk — калькулятор по колонкам: условие перед скобками отбирает строки, копилка s "
               "складывает, END печатает итог. Слова сравнивай в кавычках, числа — без.")
    spell = "awk -F, '$6==\"paid\" {s+=$5} END {print s}' файл — сумма колонки по условию"
    trap_messages = {
        "all": "Это сумма всех заказов — добавь условие на статус перед скобками: "
               "$6==\"{status}\".",
        "notes": "В сумму попали чужие строки: голый grep {status} цепляет и заметки вроде "
                 "«refund requested». Сравни статус в awk: $6==\"{status}\".",
        "city_only": "Это все заказы {city}, а нужны только оплаченные: добавь && $6==\"paid\".",
        "paid_only": "Это все оплаченные заказы, а нужен только {city}: добавь $3==\"{city}\" &&.",
        "all_b": "Это сумма всех заказов: нужны два условия — $3==\"{city}\" && $6==\"paid\".",
        "ge": "В сумму попали заказы ровно на {limit}: > — строго больше, а >= — «больше или "
              "равно».",
        "all_c": "Это сумма всех заказов: отбери крупные условием $5>{limit} перед скобками.",
    }
    noquote = ("Ноль или пусто — условие не отобрало ни строки: голое слово awk считает "
               "именем переменной. Слово пишут в кавычках: $6==\"paid\", число — без них.")
    fallback = "Не то. Проверь номер колонки (amount — $5) и условие перед скобками."

    no_f = ("Пусто: без -F, awk режет строку по пробелам, а в CSV поля через запятую — $5 и $6 "
            "не те. Начни с awk -F, '…'.")
    no_end = ("Пусто: копилка набралась, но её никто не напечатал. Итог печатают в конце: "
              "… {s+=$5} END {print s}.")
    dollar_s = ("print $s печатает поле с номером s, а не копилку. Итог — END {print s}, без "
                "доллара.")
    no_rows = ("Ноль или пусто — условие не отобрало ни строки. Проверь номер колонки: статус — "
               "$6, город — $3, amount — $5.")
    _UNQUOTED = re.compile(r"==\s*[A-Za-z]")

    def _awk_why(self, cmds) -> str:
        """Пустой ответ: причина по последнему awk в журнале — у каждой своя."""
        awks = [seg for seg in _segments(cmds) if re.search(r"\bawk\b", seg)]
        if not awks:
            return self.no_rows
        last = awks[-1]
        if "-F" not in last:
            return self.no_f
        if "END" not in last:
            return self.no_end
        if re.search(r"print\s+\$s\b", last):
            return self.dollar_s
        if self._UNQUOTED.search(last):
            return self.noquote
        return self.no_rows

    def wrong_message(self, given, ctx):
        if textnorm.parts(given) in ([], ["0"]):
            return self._awk_why(ctx.cmds)
        return super().wrong_message(given, ctx)

    def setup_variant(self, box, rng, variant):
        rows = _orders(box, rng, refund_notes=rng.randint(3, 6))
        total = sum(r["amount"] for r in rows)
        if variant == 1:
            by = Counter((r["city"], r["status"] == "paid") for r in rows)
            city = rng.choice(sorted({c for c, paid in by if by[(c, True)] >= 2 and
                                      by[(c, False)] >= 2}))
            pick = sum(r["amount"] for r in rows if r["city"] == city and r["status"] == "paid")
            return {"city": city, "answer": pick, "traps": [
                ["city_only", sum(r["amount"] for r in rows if r["city"] == city)],
                ["paid_only", sum(r["amount"] for r in rows if r["status"] == "paid")],
                ["all_b", total]]}
        if variant == 2:
            limit = rng.choice(range(3000, 8001, 500))
            for r in rng.sample(rows, rng.randint(2, 4)):
                r["amount"] = limit
            kit.write(Path(box) / ORDERS, datakit.render_orders(rows))
            total = sum(r["amount"] for r in rows)
            return {"limit": limit,
                    "answer": sum(r["amount"] for r in rows if r["amount"] > limit),
                    "traps": [["ge", sum(r["amount"] for r in rows if r["amount"] >= limit)],
                              ["all_c", total]]}
        status = rng.choice(("paid", "refund"))
        if status == "paid":        # у возвратов «refund requested», у неоплаченных — эта
            for r in rng.sample([r for r in rows if r["status"] != "paid"], rng.randint(3, 6)):
                r["note"] = PAID_NOTE
            kit.write(Path(box) / ORDERS, datakit.render_orders(rows))
        # голый grep {status} цепляет и строки, где слово стоит в заметке
        noted = sum(r["amount"] for r in rows if status in (r["status"], r["note"].split(" ")[0]))
        return {"status": status, "traps": [["all", total], ["notes", noted]],
                "answer": sum(r["amount"] for r in rows if r["status"] == status)}


# --- D12 -----------------------------------------------------------------------------------

class LogPeriod(_DataAnswer):
    """Окно времени: ^, дата и часы (a|b) — приёмы блока «Регулярки» (FB21) в деле."""
    id = "log_period"
    title = "Окно в логе"
    par = 75
    # FB21: знаки регулярок учит блок регулярок раньше по треку; здесь — один главный приём
    scroll = ("Окно времени — регулярка с начала строки: ^, дата, час и двоеточие. grep -E "
              "'^2726-09-01 (08|09):' server.log — с 08:00 до 09:59, часы — через (a|b).\n"
              "Голое '14:' цепляет и минуты (10:14:05), а дата без ^ — чужие строки.")
    variants = (
        Variant("Сколько ошибок ERROR было в app.log {date} с {h1}:00 до {h2}:59? "
                "Ответ: ans ЧИСЛО",
                wrong=("grep -E '({h1}|{h2}):' app.log | grep -c ERROR",
                       "grep {date} app.log | grep -E '({h1}|{h2}):' | grep -c ERROR"),
                alternatives=("grep -E '^{date} ({h1}|{h2}):.*ERROR' app.log | wc -l — одним "
                              "шаблоном: .* — сколько угодно любых символов",)),
        Variant("Сколько повторов с номером — строк вида «retry 17 calling auth» — записано в "
                "app.log {date} за час с {h1}:00 до {h1}:59? Номер бывает любой длины; "
                "порядковые повторы («retry 2nd calling …») не считай. Ответ: ans ЧИСЛО",
                hints=("Сначала строки часа (^ и дата), потом из них — повторы с номером: "
                       "второй grep -E, счёт — wc -l.",
                       "Номер — одна цифра или больше: [0-9]+. За ним — пробел и calling, так "
                       "порядковые 2nd не пройдут.",
                       "grep -E '^{date} {h1}:' app.log | grep -E 'retry [0-9]+ calling' | wc -l"),
                solution="grep -E '^{date} {h1}:' app.log | grep -E 'retry [0-9]+ calling' | wc -l",
                wrong=("grep -E '^{date} {h1}:' app.log | grep -E 'retry [0-9] calling' | wc -l",
                       "grep -E '^{date} {h1}:' app.log | grep 'retry [0-9]+ calling' | wc -l",
                       "grep -E '{h1}:' app.log | grep -E 'retry [0-9]+ calling' | wc -l"),
                alternatives=("grep -E '^{date} {h1}:.*retry [0-9]+ calling' app.log | wc -l — "
                              "одним шаблоном: .* — сколько угодно любых символов",)),
        Variant("Окно — {date} с {lo}:00 до {hi}:59, несколько часов подряд. Сколько строк ERROR "
                "в app.log за это окно? Ответ: ans ЧИСЛО",
                hints=("Часы {lo}…{hi} начинаются одной и той же цифрой — вторую задаст класс "
                       "[ ]: в нём одна цифра, а не число.",
                       "Шаблон: ^, дата, пробел и час {cls} — так минуты не зацепятся. ERROR "
                       "сосчитает второй grep.",
                       "grep -E '^{date} {cls}:' app.log | grep -c ERROR"),
                solution="grep -E '^{date} {cls}:' app.log | grep -c ERROR",
                wrong=("grep -E '{cls}:' app.log | grep -c ERROR",
                       "grep {date} app.log | grep -E '{cls}:' | grep -c ERROR"),
                alternatives=("grep -E '^{date} ({hours}):' app.log | grep -c ERROR — часы "
                              "перечислены через |",)),
    )
    hints = ("Сначала отбери строки за период, потом посчитай ERROR — два grep через |.",
             "Период — регулярка с ^ и датой: часы перечисли через (a|b). Без ^ и даты '{h1}:' "
             "совпадёт с минутами.",
             "grep -E '^{date} ({h1}|{h2}):' app.log | grep -c ERROR")
    solution = "grep -E '^{date} ({h1}|{h2}):' app.log | grep -c ERROR"
    explain = ("Регулярка вырезает из лога ровно нужное окно времени: ^ и дата не дадут зацепить те"
               " же цифры в минутах и чужие дни, а (a|b) и [3-6] перечисляют часы.")
    spell = "grep -E '^дата (14|15):' лог — строки за период; ^ — начало строки, (a|b) — или"
    trap_messages = {
        "minutes": "В счёт попали чужие строки: те же цифры бывают минутами, а дни — другими. "
                   "Привяжи шаблон к началу строки: ^ и дата.",
        "levels": "Это все строки окна, а нужны только ERROR: добавь | grep -c ERROR.",
        "one_digit": "Ты посчитал только однозначные номера: [0-9] — ровно одна цифра. Одна или "
                     "больше — [0-9]+ (это grep -E).",
        "any_retry": "В счёт попали и порядковые повторы (retry 2nd): номер — только цифры, за "
                     "ним пробел и calling — 'retry [0-9]+ calling'.",
        "zero": "Шаблон ничего не нашёл. Частые причины: | + и ( ) работают только с grep -E; "
                "класс [ ] — одна цифра, а не число.",
        "edges": "Это только крайние часы, а окно — все часы от {lo} до {hi}. Первая цифра у "
                 "них общая — пиши её как есть, а вторую задай классом [ ]: от меньшей цифры до "
                 "большей через дефис.",
    }
    fallback = ("Не то. Окно — шаблон с ^, датой и часами; уровень — вторым grep через |.")
    # причина по последней команде grep в журнале — точнее, чем по числу
    range_class = ("Класс [ ] — это одна цифра, а не число: [13-15] grep читает как «1, от 3 до "
                   "1, 5» и ругается. Часы 13–15 пиши 1[3-5]: первая цифра как есть, вторая — "
                   "классом.")
    no_e = ("Без -E grep понимает | + и ( ) как обычные символы и ничего не находит. Нужен "
            "grep -E '…'.")
    no_paren = ("| делит весь шаблон надвое: '^дата 14|15:' — это «^дата 14» или «15:» где "
                "угодно. Возьми часы в скобки: '^дата (14|15):'.")
    _RANGE = re.compile(r"\[\d{2,}-\d+\]|\[\d-\d{2,}\]")
    _GREP_PAT = re.compile(r"\bgrep\s+((?:-[A-Za-z]+\s+)*)(?:'([^']*)'|\"([^\"]*)\")")

    def _journal_why(self, cmds):
        greps = [seg for seg in _segments(cmds) if re.search(r"\bgrep\b", seg)]
        for seg in reversed(greps[-3:]):          # последняя строка с grep, её звенья
            for m in self._GREP_PAT.finditer(seg):
                flags, pat = m.group(1), m.group(2) or m.group(3) or ""
                if self._RANGE.search(pat):
                    return self.range_class
                if not re.search(r"-[A-Za-z]*E", flags) and re.search(r"[|+()]", pat):
                    return self.no_e
                if pat.startswith("^") and "|" in pat and "(" not in pat:
                    return self.no_paren
            break
        return None

    def wrong_message(self, given, ctx):
        why = self._journal_why(ctx.cmds)
        if why:
            return why
        return super().wrong_message(given, ctx)

    def setup_variant(self, box, rng, variant):
        date = (datakit.LOG_START + timedelta(days=rng.randrange(3))).isoformat()
        if variant == 2:
            tens = rng.choice((0, 1))
            a = rng.randint(0, 6)
            b = a + rng.randint(2, 3)
            hours = [f"{tens}{u}" for u in range(a, b + 1)]
            st = {"lo": hours[0], "hi": hours[-1], "cls": f"{tens}[{a}-{b}]",
                  "hours": "|".join(hours)}
            avoid = hours
            traps_at = (hours[0], hours[-1])
        else:
            h1 = rng.randint(0, 22)
            hours = [f"{h1:02d}"] if variant == 1 else [f"{h1:02d}", f"{h1 + 1:02d}"]
            st = {"h1": hours[0], "h2": hours[-1]}
            avoid = ()
            traps_at = (hours[0], hours[-1])
        text, _ = datakit.app_log(rng, days=3, per_day=rng.randint(1500, 2500),
                                  minute_traps=(traps_at[0], traps_at[1], rng.randint(3, 6)),
                                  avoid_hours=avoid)
        if variant == 1:
            text = self._plant_retries(rng, text, date, int(hours[0]))
        kit.write(Path(box) / LOG, text)
        lines = text.splitlines()
        if variant == 1:
            return self._retry_state(st, lines, date, hours[0])
        else:
            def level(x):
                return "ERROR" in x
            pat = re.compile("(" + "|".join(hours) + "):")
        window = [x for x in lines if x[:10] == date and x[11:13] in hours]
        traps = [["minutes", sum(bool(pat.search(x)) and level(x) for x in lines)],
                 ["minutes", sum(date in x and bool(pat.search(x)) and level(x) for x in lines)],
                 ["levels", len(window)], ["zero", 0]]
        if variant == 2:        # рецепт A — только крайние часы окна
            traps.append(["edges", sum(x[11:13] in (hours[0], hours[-1]) and level(x)
                                       for x in window)])
        st.update({"date": date, "answer": sum(level(x) for x in window), "traps": traps})
        return st

    RETRY = re.compile(r"retry [0-9]+ calling")
    ORDINALS = ("1st", "2nd", "3rd", "4th")

    @staticmethod
    def _plant_retries(rng, text: str, date: str, hour: int) -> str:
        """Вариант B: в часе окна гарантированно есть повторы с однозначным и двузначным
        номером и порядковые (retry 2nd); в других часах этой даты — повторы с минутами,
        равными часу окна (голое «ЧЧ:» их цепляет). Строки снова по времени."""
        day = datetime.strptime(date, "%Y-%m-%d")
        others = [h for h in range(24) if h != hour]
        extra = []

        def add(h, m, msg):
            svc = rng.choice(datakit.SERVICES)
            when = day.replace(hour=h, minute=m, second=rng.randrange(60))
            extra.append(datakit.log_line(datakit._entry(when, "WARN", svc, msg)))

        def callee():
            return rng.choice(datakit.SERVICES)
        for _ in range(rng.randint(2, 4)):
            add(hour, rng.randrange(60), f"retry {rng.randint(2, 9)} calling {callee()}")
        for _ in range(rng.randint(2, 4)):
            add(hour, rng.randrange(60), f"retry {rng.randint(10, 99)} calling {callee()}")
        for _ in range(rng.randint(2, 4)):
            add(hour, rng.randrange(60),
                f"retry {rng.choice(LogPeriod.ORDINALS)} calling {callee()}")
        for _ in range(2):
            add(rng.choice(others), hour, f"retry {rng.randint(10, 99)} calling {callee()}")
        lines = sorted(text.splitlines() + extra, key=lambda x: x[:19])
        return "\n".join(lines) + "\n"

    def _retry_state(self, st, lines, date, hh):
        window = [x for x in lines if x[:10] == date and x[11:13] == hh]
        answer = sum(bool(self.RETRY.search(x)) for x in window)
        loose = re.compile(hh + ":")
        traps = [["one_digit", sum(bool(re.search(r"retry [0-9] calling", x)) for x in window)],
                 ["any_retry", sum("retry" in x for x in window)],
                 ["minutes", sum(bool(loose.search(x)) and bool(self.RETRY.search(x))
                                 for x in lines)],
                 ["minutes", sum(date in x and bool(loose.search(x)) and
                                 bool(self.RETRY.search(x)) for x in lines)],
                 ["zero", 0]]
        st.update({"date": date, "answer": answer, "traps": traps})
        return st


# --- D13 -----------------------------------------------------------------------------------

class JoinParts(Task):
    """Склейка выгрузок: один заголовок, все строки по порядку, без ==> имён <== tail."""
    id = "join_parts"
    track = "data"
    title = "Склейка выгрузок"
    par = 75
    scroll = ("cat a.csv b.csv > all.csv — склеить файлы подряд в один. Маска parts/*.csv "
              "раскрывается по алфавиту: 10-й файл встанет раньше 2-го.\n"
              "tail -n +2 файл — всё, кроме первой строки. С несколькими файлами tail вставляет "
              "строки ==> имя <==, их убирает флаг -q (quiet — тихо).")
    variants = (
        Variant("За неделю пришли выгрузки parts/day_1.csv … day_7.csv, у каждой свой заголовок. "
                "Склей их в all.csv: заголовок один раз сверху, дальше все строки по порядку "
                "дней.",
                wrong=("cat parts/*.csv > all.csv",
                       "head -1 parts/day_1.csv > all.csv; tail -n +2 parts/*.csv >> all.csv"),
                alternatives=("cat parts/day_1.csv > all.csv; tail -q -n +2 parts/day_[2-7].csv "
                              ">> all.csv — первый файл целиком, остальные без шапки",)),
        Variant("Выгрузки за 12 дней: parts/day_1.csv … parts/day_12.csv, у каждой свой "
                "заголовок. Собери all.csv: заголовок один раз, дальше строки строго по порядку "
                "дней — 1, 2, 3 … 12.",
                hints=("Заголовок — один раз из первого файла, остальное — строками без "
                       "заголовков, в порядке дней.",
                       "Маска * раскрывается по алфавиту: day_10 встанет раньше day_2. Отдельно "
                       "однозначные day_?.csv и двузначные day_??.csv.",
                       "head -1 parts/day_1.csv > all.csv; tail -q -n +2 parts/day_?.csv "
                       "parts/day_??.csv >> all.csv"),
                solution="head -1 parts/day_1.csv > all.csv; tail -q -n +2 parts/day_?.csv "
                         "parts/day_??.csv >> all.csv",
                wrong=("head -1 parts/day_1.csv > all.csv; tail -q -n +2 parts/*.csv >> all.csv",
                       "cat parts/day_?.csv parts/day_??.csv > all.csv"),
                alternatives=("head -1 parts/day_1.csv > all.csv; tail -q -n +2 "
                              "parts/day_{{1..12}}.csv >> all.csv — {{1..12}} перечисляет номера "
                              "по порядку",)),
        Variant("В archive.csv уже лежат прошлые заказы: заголовок и строки. Допиши в конец "
                "строки новой недели из parts/day_1.csv … day_7.csv, по порядку дней. Старое не "
                "трогай, заголовки кусков не нужны.",
                hints=("Старое в файле должно остаться: дописывают, а не записывают.",
                       "Строки без заголовков по всем кускам — tail -q -n +2, дописывает >>.",
                       "tail -q -n +2 parts/*.csv >> archive.csv"),
                solution="tail -q -n +2 parts/*.csv >> archive.csv",
                wrong=("tail -q -n +2 parts/*.csv > archive.csv",
                       "cat parts/*.csv >> archive.csv"),
                alternatives=("for f in parts/day_{{1..7}}.csv; do tail -n +2 $f >> archive.csv; "
                              "done — по одному куску, -q не нужен",)),
    )
    hints = ("Заголовок возьми один раз из первого файла, остальное допиши строками без "
             "заголовков.",
             "head -1 … > all.csv, потом tail -n +2 по всем файлам с >>. Строки ==> имя <== "
             "убирает tail -q.",
             "head -1 parts/day_1.csv > all.csv; tail -q -n +2 parts/*.csv >> all.csv")
    solution = "head -1 parts/day_1.csv > all.csv; tail -q -n +2 parts/*.csv >> all.csv"
    explain = ("Склеивать выгрузки придётся постоянно: один заголовок, все строки по порядку, "
               "никакого мусора между файлами. Маска раскладывает файлы по алфавиту — если номера "
               "больше 9, порядок проверь глазами.")
    spell = "cat a b > c — склеить; tail -q -n +2 файлы — без заголовков и без ==> имён <=="

    def setup_variant(self, box, rng, variant):
        n = 12 if variant == 1 else 7
        parts = datakit.parts(rng, n)
        rows: List[str] = []
        for d in range(1, n + 1):
            text = parts[f"day_{d}.csv"]
            kit.write(Path(box) / "parts" / f"day_{d}.csv", text)
            rows += text.splitlines()[1:]
        if variant == 2:
            first = int(rows[0].split(",")[0][2:])
            k = rng.randint(4, 9)
            ids = sorted(rng.sample(range(first - 300, first - 1), k))
            old = [{"id": f"A-{i}", "date": f"2726-08-{d:02d}", "city": rng.choice(datakit.CITIES),
                    "product": kit.latin(rng), "amount": rng.randint(100, 9999),
                    "status": rng.choice(datakit.STATUSES), "note": ""}
                   for i, d in zip(ids, sorted(rng.choices(range(20, 32), k=k)))]
            base = datakit.render_orders(old).splitlines()
            kit.write(Path(box) / "archive.csv", "\n".join(base) + "\n")
            return {"out": "archive.csv", "base": base, "want": base + rows}
        return {"out": "all.csv", "base": [datakit.ORDER_HEADER],
                "want": [datakit.ORDER_HEADER] + rows}

    def check(self, ctx):
        st = ctx.state
        data = sandbox.read_in_box(ctx.box, st["out"], READ_CAP)
        if data is None:
            return Verdict(False)
        got = data.decode("utf-8", errors="replace").splitlines()
        want, base = st["want"], st["base"]
        if got == want:
            return Verdict(True)
        if got == base or not got:
            return Verdict(False)           # работа идёт: шапка (или архив) на месте
        return Verdict(False, self._why(got, st))

    @staticmethod
    def _why(got: List[str], st: dict) -> str:
        header, want, base = datakit.ORDER_HEADER, st["want"], st["base"]
        old = len(base) > 1         # вариант с архивом: его не стирают
        if old:
            again = " Набери reset — архив вернётся как был, — и допиши строки через >> один раз."
        else:
            again = (" Начни файл заново: head -1 parts/day_1.csv > all.csv — > сотрёт старое, — "
                     "и допиши строки через >> один раз.")
        if old and not set(base[1:]) <= set(got):
            return "Старый архив затёрт: > стирает файл." + again
        if any(x.startswith("==>") for x in got):
            return "tail вставил строки ==> имя <== между файлами — нужен флаг -q." + again
        k = got.count(header)
        if k > 1:
            return (f"Заголовок встречается {k} раз: каждый кусок принёс свой. Строки без "
                    "заголовка даёт tail -n +2." + again)
        if not old and (not got or got[0] != header):
            return ("Заголовка нет — первой строкой положи head -1 первого куска через >, а "
                    "строки допиши >>.")
        if len(got) != len(set(got)) and set(got) <= set(want):
            # дважды всё или дважды один кусок (повтор команды из истории) — строки в
            # выгрузке уникальны, так что любой повтор — задвоение
            return "Строки задвоились — >> дописал их второй раз." + again
        if set(got) < set(want) and len(got) == len(set(got)):
            if got == want[:len(got)]:
                return ("Не хватает строк — дописаны не все куски. Допиши остальные по порядку "
                        "дней через >>.")
            return "Не хватает строк, и порядок сбит — дописаны не все куски." + again
        if sorted(got) == sorted(want):
            return ("Строки не по порядку дней: маска раскрывается по алфавиту, и day_10 встал "
                    "раньше day_2. Однозначные — day_?.csv, двузначные — day_??.csv." + again)
        return "Не совпадает с ожидаемым:\n" + kit.diff_text("\n".join(got), "\n".join(want))


# --- D14 -----------------------------------------------------------------------------------

EXPORT = "export.sh"
WARNS = ("WARN: amount for {id} looks odd", "WARN: duplicate id {id} skipped",
         "WARN: slow disk, retry {n}", "WARN: city for {id} unknown, kept as is",
         "WARN: clock drift {n} ms")
_DEVNULL = re.compile(r"(?<![0-9&])2>>?\s*/dev/null")


def _run_re(name: str):
    """Запуск скрипта name (а не cat name): ./name или sh/zsh/bash [-x] name, в том числе
    /bin/sh name."""
    n = re.escape(name)
    return re.compile(r"(?:^|[\s;&|({])(?:\./" + n + r"|(?:/(?:usr/)?bin/)?(?:ba|z)?sh\s+"
                      r"(?:-\w+\s+)*(?:\./)?" + n + r")")


_SEP = re.compile(r";|&&|\|\|")


def _segments_at(cmds):
    """Звенья журнала по порядку: (строка, начало звена в ней, звено). Строка бывает
    цепочкой «a; b», «a && b»."""
    for c in cmds:
        start = 0
        for m in list(_SEP.finditer(c.line)) + [None]:
            end = m.start() if m else len(c.line)
            yield c.line, start, c.line[start:end]
            if m:
                start = m.end()


def _segments(cmds):
    for _, _, seg in _segments_at(cmds):
        yield seg


_RUN_EXPORT = _run_re(EXPORT)
# exec 2>/dev/null — поток 2 выброшен для всех следующих команд сессии
_EXEC_QUIET = re.compile(r"(?:^|[\s;&|(])exec\s+2>>?\s*/dev/null")
# после закрывающей скобки группы: 2>/dev/null до конца звена — для всех команд внутри
_AFTER_GROUP_QUIET = re.compile(r"[^;|&]*(?<![0-9&])2>>?\s*/dev/null")


def _own_cmd(seg: str, pos: int) -> str:
    """Простая команда звена seg, в которой стоит позиция pos: от ближайшей слева палки или
    открывающей скобки до ближайшей справа палки или закрывающей скобки. Так 2>/dev/null у
    соседа по конвейеру (… | ls 2>/dev/null) или снаружи $( … ) не приписывается запуску."""
    left, right, depth = -1, len(seg), 0      # depth — внутри ${…}: его скобки не границы
    for i, ch in enumerate(seg):
        if seg.startswith("${", i):
            depth += 1
        elif ch == "{" and depth:
            continue
        elif ch == "}" and depth:
            depth -= 1
        elif ch in "|({" and i < pos:
            left = i
        elif ch in "|)}" and i >= pos:
            right = i
            break
    return seg[left + 1:right]


def _group_quiet(line: str, pos: int) -> bool:
    """Позиция pos строки — внутри группы { …; } или ( … ), за которой стоит 2>/dev/null.
    Скобки сопоставляются парами: группа правее запуска (./export.sh …; (ls) 2>/dev/null)
    и подстановка $( … ) не в счёт — её поток 2 идёт мимо перенаправления снаружи."""
    stack = []
    for i, ch in enumerate(line):
        if ch in "{(":
            stack.append((i, ch, i > 0 and line[i - 1] == "$"))
        elif ch in "})" and stack:
            start, _, subst = stack.pop()
            if start < pos < i and not subst and _AFTER_GROUP_QUIET.match(line, i + 1):
                return True
    return False
# запуск пишет clean.csv: > clean.csv, >> clean.csv, &> clean.csv или | tee clean.csv
_WRITES_CLEAN = re.compile(r"(?:(?<![0-9])>>?\s*|\btee\s+(?:-a\s+)?)clean\.csv")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StderrSplit(Task):
    """Два выхода команды: stdout (1) и stderr (2); 2>, 2>/dev/null и порядок 2>&1."""
    id = "stderr_split"
    track = "data"
    title = "Два выхода"
    par = 60
    scroll = ("У команды два выхода (потока): 1 — данные (stdout), 2 — ошибки и предупреждения (stderr). "
              "> файл ловит только данные; 2> файл — ошибки в свой файл; 2>/dev/null — "
              "выбросить их.\n"
              "Оба в один файл: команда > файл 2>&1. 2>&1 — «поток 2 туда же, куда сейчас "
              "смотрит 1», поэтому он идёт после >.")
    variants = (
        Variant("Скрипт ./export.sh печатает строки выгрузки и вперемешку предупреждения. "
                "Запусти его так, чтобы данные легли в clean.csv, а предупреждения — в "
                "warnings.log.",
                wrong=("./export.sh > clean.csv", "./export.sh > clean.csv 2>&1"),
                alternatives=("./export.sh 2> warnings.log > clean.csv — порядок двух разных "
                              "потоков не важен",)),
        Variant("Запусти ./export.sh так, чтобы его данные легли в clean.csv, а предупреждения "
                "пропали совсем — ни в файле, ни на экране. Скрипт не правь.",
                hints=("Предупреждения скрипт пишет во второй поток — stderr.",
                       "> ловит поток 1, а поток 2 можно выбросить в /dev/null — «чёрную "
                       "дыру».",
                       "./export.sh > clean.csv 2>/dev/null"),
                solution="./export.sh > clean.csv 2>/dev/null",
                wrong=("./export.sh > clean.csv", "./export.sh > clean.csv 2>&1"),
                alternatives=("./export.sh 2>/dev/null > clean.csv — тот же результат",)),
        Variant("Сохрани весь вывод ./export.sh — и данные, и предупреждения — в один файл "
                "all.log. Скрипт не правь.",
                hints=("Данные идут потоком 1, предупреждения — потоком 2; нужны оба в одном "
                       "файле.",
                       "Сначала > all.log направит поток 1 в файл, потом 2>&1 пошлёт поток 2 "
                       "туда же. Порядок важен.",
                       "./export.sh > all.log 2>&1"),
                solution="./export.sh > all.log 2>&1",
                wrong=("./export.sh 2>&1 > all.log", "./export.sh > all.log"),
                alternatives=("./export.sh &> all.log — короткая запись zsh для «оба потока в "
                              "файл»",)),
    )
    hints = ("Предупреждения скрипт пишет во второй поток — stderr.",
             "> ловит поток 1, 2> — поток 2. Оба можно в одной команде.",
             "./export.sh > clean.csv 2> warnings.log")
    solution = "./export.sh > clean.csv 2> warnings.log"
    explain = ("У данных и ошибок разные трубы: > ловит данные, 2> — ошибки, 2>/dev/null их "
               "выкидывает, а > файл 2>&1 сливает оба потока в один файл — именно в таком порядке.")
    spell = "2> файл — ошибки в файл; 2>/dev/null — выбросить ошибки; > файл 2>&1 — всё в файл"

    def setup_variant(self, box, rng, variant):
        _, rows = datakit.orders(rng, rng.randint(15, 30), refund_notes=0)
        data = datakit.render_orders(rows).splitlines()
        warn = []
        for _ in range(rng.randint(4, 7)):
            warn.append(rng.choice(WARNS).format(id=rng.choice(rows)["id"],
                                                 n=rng.randint(2, 900)))
        # предупреждения вперемешку с данными, но не первой строкой
        at = sorted(rng.sample(range(1, len(data)), len(warn)))
        lines, w = [], iter(warn)
        for i, line in enumerate(data):
            if at and i == at[0]:
                at.pop(0)
                lines.append(f"echo '{next(w)}' >&2")
            lines.append(f"echo '{line}'")
        text = "#!/bin/sh\n" + "\n".join(lines) + "\n"
        path = kit.write(Path(box) / EXPORT, text)
        os.chmod(path, 0o755)
        out = {0: "clean.csv", 1: "clean.csv", 2: "all.log"}[variant]
        return {"data": data, "warn": warn, "sha": _sha(text.encode("utf-8")), "out": out}

    @staticmethod
    def _read(box, name):
        raw = sandbox.read_in_box(box, name, READ_CAP)
        return None if raw is None else raw.decode("utf-8", errors="replace").splitlines()

    def check(self, ctx):
        st = ctx.state
        script = sandbox.read_in_box(ctx.box, EXPORT, READ_CAP)
        if script is None or _sha(script) != st["sha"]:
            return Verdict(False, "export.sh изменён, а скрипт править нельзя. Набери reset — он "
                                  "вернётся как был.")
        v = st.get("_variant", 0)
        got = self._read(ctx.box, st["out"])
        data, warn = st["data"], st["warn"]
        if v == 2:
            return self._one_file(got, data, warn, ctx.cmds)
        if v == 0:
            log = self._read(ctx.box, "warnings.log")
            if got == data and log == warn:
                return Verdict(True)
            if got is None and log == warn:
                return Verdict(False, "Предупреждения легли, а данные ушли на экран: добавь "
                                      "> clean.csv.")
        else:
            log = None
        runs = self._runs(ctx.cmds)
        if got is None:
            if v == 1 and any(quiet for _, quiet in runs):
                return Verdict(False, "Предупреждения выброшены, а данные ушли на экран: добавь "
                                      "> clean.csv.")
            return Verdict(False)
        if any(x in warn for x in got):
            if all(x in warn for x in got) and log is not None and \
                    any(x in data for x in log):
                return Verdict(False, "Потоки перепутаны: > ловит данные (поток 1), 2> — "
                                      "предупреждения (поток 2).")
            how = "2>/dev/null" if v == 1 else "2> warnings.log"
            return Verdict(False, "В clean.csv попали предупреждения: &> и 2>&1 сливают потоки "
                                  f"в один. Предупреждениям — свой выход: {how}.")
        if got != data:
            return Verdict(False, "В clean.csv должны быть все строки данных скрипта — и только "
                                  "они. Запусти его ещё раз с > clean.csv.")
        if v == 0:
            return Verdict(False, "Данные легли, а предупреждения ушли на экран или не туда: "
                                  "добавь 2> warnings.log.")
        # clean.csv дал последний запуск, который его писал; запуски без записи (контрольный
        # ./export.sh | head) не в счёт
        writes = [quiet for seg, quiet in runs if _WRITES_CLEAN.search(seg)]
        last = writes[-1] if writes else (runs[-1][1] if runs else False)
        if last:
            return Verdict(True)
        return Verdict(False, "Данные легли, а предупреждения не выброшены — на экране они или "
                              "в файле. Запусти так, чтобы поток 2 ушёл в никуда: 2>/dev/null.")

    @staticmethod
    def _runs(cmds) -> List[tuple]:
        """Запуски скрипта по порядку: (звено, выброшен ли в нём поток 2). Строка журнала
        бывает цепочкой «a; b» — делим на звенья; 2>/dev/null засчитывается в самом звене,
        после скобки группы { …; } или ( … ), внутри которой стоит запуск, и после exec
        2>/dev/null."""
        out, session = [], False
        for line, at, seg in _segments_at(cmds):
            if _EXEC_QUIET.search(seg):
                session = True
            elif _RUN_EXPORT.search(seg):
                # запуск внутри группы, за скобкой которой стоит 2>/dev/null
                run = _RUN_EXPORT.search(seg).end() - 1      # внутри имени скрипта
                grouped = _group_quiet(line, at + run)
                out.append((seg, session or grouped or bool(_DEVNULL.search(_own_cmd(seg, run)))))
        return out

    @staticmethod
    def _one_file(got, data, warn, cmds):
        if got is None:
            return Verdict(False)
        if sorted(got) == sorted(data + warn):
            return Verdict(True)
        if got == data:
            if any("2>&1" in c.line for c in cmds):
                return Verdict(False, "В all.log только данные: 2>&1 стоит раньше > и отправил "
                                      "предупреждения туда, куда тогда смотрел поток 1, — на "
                                      "экран. Порядок: > all.log 2>&1.")
            return Verdict(False, "В all.log только данные: предупреждения — поток 2 — ушли на "
                                  "экран. Добавь после > all.log ещё 2>&1.")
        if len(got) > len(data) + len(warn) and set(got) <= set(data + warn):
            return Verdict(False, "Лишние строки: похоже, скрипт отработал дважды и >> дописал. "
                                  "Запусти ещё раз с > all.log 2>&1 — > начнёт файл заново.")
        if got == warn:
            return Verdict(False, "Здесь только предупреждения: 2> ловит один поток 2. Данные — "
                                  "через > all.log, а 2>&1 после него добавит предупреждения.")
        return Verdict(False, "Строки потеряны или перемешаны: два перенаправления в один файл "
                              "затирают друг друга. Один файл — один >, второй поток — 2>&1.")


# --- D15 -----------------------------------------------------------------------------------

SYNC = "sync.sh"
SYNC_LOG = "sync.log"
SYNC_ERRORS = ("ERROR: {f}.txt: permission denied", "ERROR: {f}.txt: checksum mismatch",
               "ERROR: {f}.txt: backup host timeout", "ERROR: {f}.txt: file locked")
_RUN_SYNC = _run_re(SYNC)
# tee — звено конвейера после палки (| или |&), а не слово-аргумент
_TEE = re.compile(r"\|&?\s*(?:/usr/bin/)?tee\b")
# группа { …; } или ( … ), а за ней палка в tee: tee видит всё, что внутри
_GROUP_TEE = re.compile(r"[})][^;]*\|&?\s*(?:/usr/bin/)?tee\b")
# 2> или 2>&1 после «| tee» — достался tee, а не скрипту
_TEE_THEN_2 = re.compile(r"\|\s*(?:/usr/bin/)?tee\b[^|;]*(?<![0-9&])2>")


def _sync_run(rng, files: List[str], stamp: str, errs: int) -> List[tuple]:
    """Один запуск sync.sh: [(поток, строка), …] по порядку вывода. Первые errs файлов — с
    ошибкой (поток 2), остальные отправлены или не менялись (поток 1); ошибки вперемешку с
    сообщениями, но не первой и не последней строкой."""
    bad, good = files[:errs], files[errs:]
    out = [f"== sync {stamp} =="]
    sent = 0
    for f in good:
        if rng.random() < 0.7:
            out.append(f"sent {f}.txt {rng.randint(2, 900)} KB")
            sent += 1
        else:
            out.append(f"{f}.txt unchanged")
    out.append(f"== end {stamp}: {sent} sent, {len(good) - sent} unchanged, {len(bad)} failed ==")
    err = [rng.choice(SYNC_ERRORS).format(f=f) for f in bad]
    at = sorted(rng.sample(range(1, len(out)), len(err)))
    seq, e = [], iter(err)
    for i, line in enumerate(out):
        if at and at[0] == i:
            at.pop(0)
            seq.append((2, next(e)))
        seq.append((1, line))
    return seq


class TeeLog(Task):
    """tee — тройник: поток 1 и на экран, и в файл; tee -a дописывает; 2>&1 до палки."""
    id = "tee_log"
    track = "data"
    title = "Экран и файл"
    par = 60
    scroll = ("команда | tee файл — показать вывод на экране И записать в файл; tee -a файл — "
              "append, дописать в конец. Палка и tee получают только поток 1 (данные).\n"
              "Ошибки туда же: команда 2>&1 | tee файл — 2>&1 ставят до палки. Ошибки отдельно: "
              "команда 2> файл | tee …")
    variants = (
        Variant("Запусти ./sync.sh так, чтобы видеть его вывод на экране и одновременно "
                "сохранить в sync.log всё — и сообщения, и ошибки. Скрипт не правь.",
                wrong=("./sync.sh | tee sync.log", "./sync.sh > sync.log 2>&1"),
                alternatives=("./sync.sh |& tee sync.log — |& в zsh: оба потока в палку "
                              "разом",)),
        Variant("В sync.log уже лежит журнал прошлого запуска. Запусти ./sync.sh снова: вывод — "
                "на экран и в конец sync.log, сообщения вместе с ошибками. Старое не трогай, "
                "скрипт не правь.",
                hints=("Дописывать в конец, не стирая, умеет tee с флагом -a.",
                       "Ошибки присоедини к данным — 2>&1 до палки; tee -a sync.log покажет всё "
                       "и допишет в конец.",
                       "./sync.sh 2>&1 | tee -a sync.log"),
                solution="./sync.sh 2>&1 | tee -a sync.log",
                wrong=("./sync.sh 2>&1 | tee sync.log", "./sync.sh >> sync.log 2>&1"),
                alternatives=("./sync.sh |& tee -a sync.log — то же короче: |& шлёт в палку оба "
                              "потока",)),
        Variant("Запусти ./sync.sh так, чтобы сообщения шли на экран и одновременно в sync.log, "
                "а ошибки — только в errors.log: ни на экран, ни в sync.log. Скрипт не правь.",
                hints=("Экран и файл разом — tee; ошибкам нужен свой файл.",
                       "tee получает только поток 1. Ошибки уведи сразу после ./sync.sh — 2> "
                       "errors.log, до палки.",
                       "./sync.sh 2> errors.log | tee sync.log"),
                solution="./sync.sh 2> errors.log | tee sync.log",
                wrong=("./sync.sh 2>&1 | tee sync.log", "./sync.sh > sync.log 2> errors.log"),
                alternatives=("./sync.sh 2> errors.log | tee sync.log; cat errors.log — и сразу "
                              "проверить файл ошибок",)),
    )
    hints = ("Экран и файл одновременно — команда tee.",
             "tee получает только поток 1. Ошибки присоедини к нему: 2>&1 перед палкой.",
             "./sync.sh 2>&1 | tee sync.log")
    solution = "./sync.sh 2>&1 | tee sync.log"
    explain = ("tee — тройник: поток 1 идёт и на экран, и в файл, tee -a дописывает. Ошибки tee не "
               "видит: 2>&1 до палки подцепит их к данным, 2> файл до палки уведёт отдельно. Так и "
               "пишут журналы запусков.")
    spell = "команда 2>&1 | tee файл — на экран и в файл, с ошибками; tee -a — дописать"

    def setup_variant(self, box, rng, variant):
        pool = rng.sample(kit.LATIN, len(kit.LATIN))
        errs = rng.randint(3, 5)
        k = errs + rng.randint(6, 7)
        day = rng.randint(27, 30)
        stamp = f"2726-09-{day:02d} {rng.randint(8, 22):02d}:{rng.randint(0, 59):02d}"
        seq = _sync_run(rng, pool[:k], stamp, errs)
        lines = [f"echo '{x}'" + (" >&2" if n == 2 else "") for n, x in seq]
        text = "#!/bin/sh\n" + "\n".join(lines) + "\n"
        os.chmod(kit.write(Path(box) / SYNC, text), 0o755)
        st = {"out": [x for n, x in seq if n == 1], "err": [x for n, x in seq if n == 2],
              "sha": _sha(text.encode("utf-8")), "base": []}
        if variant == 1:        # журнал прошлого запуска: другие файлы, другой день
            old = f"2726-09-{day - rng.randint(1, 3):02d} {rng.randint(8, 22):02d}:" \
                  f"{rng.randint(0, 59):02d}"
            prev = _sync_run(rng, pool[k:k + 8], old, rng.randint(1, 2))
            st["base"] = [x for _, x in prev]
            kit.write(Path(box) / SYNC_LOG, "\n".join(st["base"]) + "\n")
        return st

    @staticmethod
    def _read(box, name):
        raw = sandbox.read_in_box(box, name, READ_CAP)
        return None if raw is None else raw.decode("utf-8", errors="replace").splitlines()

    @staticmethod
    def _last_run(cmds):
        """(шёл ли через tee последний запуск, что писал sync.log; само звено)."""
        runs = []
        for line, at, seg in _segments_at(cmds):
            if _RUN_SYNC.search(seg):
                tail = line[at:]
                grouped = bool(_GROUP_TEE.search(tail))
                runs.append((seg + tail if grouped else seg, grouped))
        writing = [r for r in runs if SYNC_LOG in r[0]]
        last, grouped = writing[-1] if writing else (runs[-1] if runs else ("", False))
        return grouped or bool(_TEE.search(last)), last

    @staticmethod
    def _no_err(last: str) -> str:
        if _TEE_THEN_2.search(last):
            return ("2>&1 стоит после палки и достался tee, а не скрипту: ошибки ушли на экран. "
                    "Ставь его до |.")
        return "Палка и tee получают только поток 1 — присоедини ошибки: 2>&1 до палки."

    def check(self, ctx):
        st = ctx.state
        script = sandbox.read_in_box(ctx.box, SYNC, READ_CAP)
        if script is None or _sha(script) != st["sha"]:
            return Verdict(False, "sync.sh изменён, а скрипт править нельзя. Набери reset — он "
                                  "вернётся как был.")
        got = self._read(ctx.box, SYNC_LOG)
        teed, last = self._last_run(ctx.cmds)
        v = st.get("_variant", 0)
        if v == 1:
            return self._append(got, st, teed, last)
        if v == 2:
            return self._split(got, self._read(ctx.box, "errors.log"), st, teed, last)
        return self._full(got, st, teed, last)

    @staticmethod
    def _twice(c: Counter, want: Counter) -> bool:
        return set(c) <= set(want) and any(n > 1 for n in c.values())

    def _full(self, got, st, teed, last):
        out, err = st["out"], st["err"]
        want = Counter(out + err)
        if got is None:
            return Verdict(False)
        c = Counter(got)
        if c == want:
            if teed:
                return Verdict(True)
            return Verdict(False, "Файл полный, но на экран ничего не шло: > пишет только в "
                                  "файл. Пропусти вывод через | tee sync.log.")
        if c == Counter(out):
            return Verdict(False, "В sync.log нет ошибок. " + self._no_err(last))
        if got and self._twice(c, want):
            return Verdict(False, "Журнал задвоился: второй запуск дописан в конец. Запусти ещё "
                                  "раз с tee без -a — он начнёт файл заново.")
        if c == Counter(err):
            return Verdict(False, "В sync.log только ошибки, а данные ушли мимо. Нужны оба "
                                  "потока: 2>&1 до палки, без лишних >.")
        return Verdict(False, "В sync.log не то: нужны все строки запуска — и сообщения, и "
                              "ошибки, по разу. Запусти ./sync.sh ещё раз: 2>&1 до палки, файл "
                              "— через tee.")

    def _append(self, got, st, teed, last):
        base = st["base"]
        want = Counter(st["out"] + st["err"])
        again = (" Набери reset — журнал вернётся как был, — и допиши запуск один раз: оба "
                 "потока, через tee -a.")
        if got is None:
            return Verdict(False, "sync.log пропал." + again)
        if got[:len(base)] != base:
            return Verdict(False, "Старый журнал затёрт: tee без -a, как и >, перезаписывает "
                                  "файл." + again)
        new = Counter(got[len(base):])
        if not new:
            return Verdict(False)
        if new == want:
            if teed:
                return Verdict(True)
            return Verdict(False, "Запуск дописан, но на экран ничего не шло: >> пишет только в "
                                  "файл. Набери reset и допиши через | tee -a sync.log.")
        if new == Counter(st["out"]):
            return Verdict(False, "Дописаны сообщения без ошибок. " + self._no_err(last) +
                           " Набери reset — журнал вернётся, — и допиши заново.")
        if self._twice(new, want):
            return Verdict(False, "Запуск дописан дважды." + again)
        return Verdict(False, "Хвост sync.log не похож на один запуск ./sync.sh." + again)

    def _split(self, got, errs, st, teed, last):
        out, err = st["out"], st["err"]
        if got is None:
            return Verdict(False)
        c = Counter(got)
        if c == Counter(out) and errs is not None and Counter(errs) == Counter(err):
            if teed:
                return Verdict(True)
            return Verdict(False, "Файлы верные, но на экран ничего не шло: > пишет только в "
                                  "файл. Сообщения пропусти через | tee sync.log.")
        if set(err) & set(got):
            return Verdict(False, "В sync.log попали ошибки: 2>&1 слил потоки. Ошибкам — свой "
                                  "выход: 2> errors.log сразу после ./sync.sh, до палки.")
        if c == Counter(out):
            if errs is not None and not set(err) & set(errs) and _TEE_THEN_2.search(last):
                return Verdict(False, "errors.log пуст: 2> после палки достался tee, а не "
                                      "скрипту. Ставь 2> errors.log сразу после ./sync.sh.")
            if errs is None or not set(err) & set(errs):
                return Verdict(False, "Сообщения легли, а ошибки ушли на экран: добавь 2> "
                                      "errors.log сразу после ./sync.sh, до палки.")
        return Verdict(False, "Не то: в sync.log — только сообщения, в errors.log — только "
                              "ошибки, по разу. Запусти ещё раз: 2> errors.log до палки, "
                              "сообщения — через | tee sync.log.")


# --- D16 -----------------------------------------------------------------------------------

EXCEL = "excel.csv"
_DMY = re.compile(r"\b(\d\d)\.(\d\d)\.(\d{4})\b")
_ISO = re.compile(r"\b\d{4}-\d\d-\d\d\b")
_ANY_DATE = re.compile(r"\b\d[\d.-]{8}\d\b")
_SED = re.compile(r"(?:^|[\s|(])sed\s")
# BSD sed: после -i обязателен аргумент — суффикс копии; шаблон сразу после -i ушёл в суффикс
_SED_I_BAD = re.compile(r"\bsed\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*i(?:''|\"\")?\s+['\"]?s\W")
_SED_I = re.compile(r"\bsed\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*i")


class SedFix(Task):
    """sed 's///g', -e дважды, -E с группами и \\1; на Mac — sed -i '' для правки на месте."""
    id = "sed_fix"
    track = "data"
    title = "Чистка выгрузки"
    par = 120
    scroll = ("sed 's/было/стало/g' файл > новый — заменить везде; g — все совпадения в строке, "
              "без g — первое. Несколько замен: sed -e '…' -e '…' (e — expression). На месте: "
              "sed -i '' '…' файл (i — in-place) — на Mac после -i нужны пустые кавычки.\n"
              "sed -E — Extended, регулярки: ( ) — запомнить кусок, \\1 \\2 — вставить его; "
              "[0-9]{2} — две цифры; \\. — сама точка.")
    variants = (
        Variant("В выгрузке excel.csv разделитель ; вместо запятой, а в датах точки "
                "(05.03.2726). Сделай fixed.csv: разделитель — запятая, в датах — дефисы "
                "(05-03-2726). Исходник не трогай.",
                wrong=("sed 's/;/,/' excel.csv > fixed.csv",
                       "sed -e 's/;/,/g' -e 's/./-/g' excel.csv > fixed.csv"),
                alternatives=(r"sed 's/;/,/g; s/\./-/g' excel.csv > fixed.csv — две замены "
                              "через ; в одной строке",)),
        Variant("В excel.csv разделитель ; — замени его везде на запятую прямо в этом файле, на "
                "месте. Даты не трогай, копий файла рядом не оставляй.",
                hints=("Замену делает sed: s/что/на что/g. Править прямо в файле — флаг -i.",
                       "На Mac после -i нужен аргумент — суффикс копии; пустые кавычки '' — без "
                       "копии.",
                       "sed -i '' 's/;/,/g' excel.csv"),
                solution="sed -i '' 's/;/,/g' excel.csv",
                wrong=("sed -i 's/;/,/g' excel.csv", "sed -i '' 's/;/,/' excel.csv"),
                alternatives=("sed 's/;/,/g' excel.csv > tmp.csv && mv tmp.csv excel.csv — "
                              "переносимо: так работает и на Linux",)),
        Variant("Для базы нужен dates.csv: тот же excel.csv, но даты ДД.ММ.ГГГГ переписаны в "
                "ГГГГ-ММ-ДД (05.03.2726 → 2726-03-05). Разделитель ; оставь как есть, исходник "
                "не трогай.",
                hints=("Замены делает sed; куски даты запоминают группы ( ) — это sed -E.",
                       r"([0-9]{{2}}) — две цифры в группе, \. — сама точка; \3-\2-\1 расставит "
                       "группы в новом порядке.",
                       r"sed -E 's/([0-9]{{2}})\.([0-9]{{2}})\.([0-9]{{4}})/\3-\2-\1/' excel.csv "
                       "> dates.csv"),
                solution=r"sed -E 's/([0-9]{{2}})\.([0-9]{{2}})\.([0-9]{{4}})/\3-\2-\1/' "
                         "excel.csv > dates.csv",
                wrong=(r"sed 's/([0-9]{{2}})\.([0-9]{{2}})\.([0-9]{{4}})/\3-\2-\1/' excel.csv > "
                       "dates.csv",
                       r"sed -E -e 's/;/,/g' -e 's/([0-9]{{2}})\.([0-9]{{2}})\.([0-9]{{4}})/"
                       r"\3-\2-\1/' excel.csv > dates.csv"),
                alternatives=(r"sed -E 's/([0-9]+)\.([0-9]+)\.([0-9]+)/\3-\2-\1/' excel.csv > "
                              "dates.csv — [0-9]+ — одна цифра или больше",)),
    )
    hints = ("Шаг 1 — только разделитель: sed 's/;/,/g' excel.csv > fixed.csv, и глянь head "
             "fixed.csv. g — заменить все ; в строке, а не первую.",
             r"Шаг 2 — точки в датах: вторая замена через второй -e. Точка в шаблоне — любой "
             r"символ, сама точка — \.",
             r"sed -e 's/;/,/g' -e 's/\./-/g' excel.csv > fixed.csv")
    solution = r"sed -e 's/;/,/g' -e 's/\./-/g' excel.csv > fixed.csv"
    explain = ("sed правит строки по шаблону: s/было/стало/g, а в sed -E группы ( ) с \\1 "
               "переставляют куски. Результат сваливай через > в новый файл; на месте — sed -i '' "
               "(на Mac без пустых кавычек никак). Замена всех точек годится, только пока точки "
               "есть лишь в датах; в жизни меняй по шаблону даты.")
    spell = (r"sed 's/было/стало/g' файл > новый — замена; sed -E 's/(..)-(..)/\2-\1/' — группы; "
             "sed -i '' — на месте")

    def setup_variant(self, box, rng, variant):
        src, both = datakit.excel(rng, rng.randint(40, 80))
        kit.write(Path(box) / EXCEL, src)
        src_lines = src.splitlines()
        if variant == 1:
            out, want = EXCEL, [x.replace(";", ",") for x in src_lines]
        elif variant == 2:
            out, want = "dates.csv", [_DMY.sub(r"\3-\2-\1", x) for x in src_lines]
        else:       # мягкий вход: две простые замены, без -E и групп
            out, want = "fixed.csv", [x.replace(";", ",").replace(".", "-") for x in src_lines]
        return {"out": out, "want": want, "src": src_lines}

    @staticmethod
    def _read(box, name):
        raw = sandbox.read_in_box(box, name, READ_CAP)
        return None if raw is None else raw.decode("utf-8", errors="replace").splitlines()

    @staticmethod
    def _last_sed(cmds) -> str:
        seds = [seg for seg in _segments(cmds) if _SED.search(seg)]
        return seds[-1] if seds else ""

    def check(self, ctx):
        st = ctx.state
        v, out, want = st.get("_variant", 0), st["out"], st["want"]
        src = self._read(ctx.box, EXCEL)
        last = self._last_sed(ctx.cmds)
        if v == 1:
            if src is None:
                return Verdict(False, "excel.csv пропал. Набери reset — он вернётся как был.")
            if src == st["src"]:
                if _SED_I_BAD.search(last):
                    return Verdict(False, "На Mac sed -i требует аргумент — суффикс копии: твой "
                                          "шаблон ушёл в суффикс, и sed не понял, что делать. "
                                          "Без копии пиши пустые кавычки: sed -i '' 's/…/…/g' "
                                          "файл.")
                return Verdict(False)
            if src == want:
                copies = sorted(n for n in os.listdir(ctx.box) if n.startswith(EXCEL) and
                                n != EXCEL)
                if copies:
                    name = shlex.quote("".join(ch if ch.isprintable() else "?"
                                               for ch in copies[0]))
                    return Verdict(False, f"Файл исправлен, но рядом осталась копия {name}: "
                                          "BSD sed принял то, что стояло после -i, за суффикс "
                                          f"копии. Убери её: rm {name}. Без копии — sed -i "
                                          "'' ….")
                return Verdict(True)
            return Verdict(False, self._why(src, st))
        if src != st["src"]:
            return Verdict(False, "Исходник excel.csv изменён, а его просили не трогать. Набери "
                                  "reset — он вернётся, — и пиши результат через > в новый файл.")
        got = self._read(ctx.box, out)
        if got is None:
            if _SED_I.search(last):
                return Verdict(False, "sed -i правит файл на месте, а исходник здесь не трогают "
                                      "(да и на Mac после -i нужен аргумент). Пиши результат в "
                                      f"новый файл: sed '…' excel.csv > {out}.")
            return Verdict(False)
        if got == want:
            return Verdict(True)
        return Verdict(False, self._why(got, st))

    @staticmethod
    def _why(got: List[str], st: dict) -> str:
        v, out, want = st.get("_variant", 0), st["out"], st["want"]
        again = " Набери reset — файл вернётся, — и замени заново." if v == 1 else ""
        if not got:
            if v == 1:
                return ("excel.csv пуст: > чистит файл до старта sed, и читать стало нечего. "
                        "Набери reset и правь на месте: sed -i '' ….")
            why = "" if v == 0 else " Частая причина: группы ( ) и \\1 работают только с sed -E."
            return (f"{out} пуст: sed, похоже, ругнулся и ничего не вывел — прочти его "
                    "сообщение." + why)
        semis = any(";" in x for x in got)
        if v in (0, 1) and semis:
            if all(";" in x and "," in x for x in got):
                return ("Остались ; — без флага g sed меняет только первое совпадение в строке."
                        + again)
            return "Остались ; — замени их все: s/;/,/g." + again
        if v == 2 and not semis:
            return "Разделитель трогать не надо: ; остаётся, меняются только даты."
        if v == 0:
            if any(set(x) <= {"-"} for x in got):
                return ("Заменилось всё подряд: точка в шаблоне — любой символ. Сама точка — "
                        "\\.: s/\\./-/g.")
            if any(_DMY.search(x) for x in got):
                return ("В датах остались точки: вторая замена — второй -e: -e 's/\\./-/g'.")
            if any(_ISO.search(x) for x in got):
                return ("Даты переставлять не надо: только точки на дефисы — 05.03.2726 станет "
                        "05-03-2726.")
        if v == 1 and any(_ISO.search(x) for x in got):
            return "Даты трогать не надо — здесь меняется только разделитель." + again
        if v == 2:
            if any(_DMY.search(x) for x in got):
                return ("Даты не переписаны: нужен sed -E и группы — ([0-9]{2}) запоминает две "
                        "цифры, \\1 вставляет первую группу.")
            if [_ANY_DATE.sub("D", x) for x in got] == [_ANY_DATE.sub("D", x) for x in want]:
                return ("Даты переставлены не так: нужно ГГГГ-ММ-ДД — год, третья группа, "
                        "встаёт первым, день — последним.")
        for i, (a, b) in enumerate(zip(got, want)):
            if a != b:
                return f"Строка {i + 1} не та: «{a}», а нужно «{b}»." + again
        return (f"Строк {len(got)}, а нужно {len(want)}: результат собирают из всего excel.csv "
                "одной командой." + again)


# --- D17 -----------------------------------------------------------------------------------

EXCHANGE = "exchange.json"
LOTS = "lots.json"              # jq_field C: тот же список лотов голым массивом
PRETTY_LINES = 6        # jq печатает лот (4 поля) красиво: { , четыре строки, }


class JqField(_DataAnswer):
    """jq: поле по пути, .список[], select(.id=="X"), | length, -r; JSON — одной строкой."""
    id = "jq_field"
    title = "Поле из JSON"
    par = 75
    scroll = ("jq '.поле' файл — достать поле из JSON; .a.b — вложенное; .users[] — каждый "
              "элемент списка; .users | length — сколько их.\n"
              "select(.name==\"ann\") — только подходящие: jq '.users[] | "
              "select(.name==\"ann\") | .age' f.json. -r — raw, текст без кавычек. Весь файл — "
              "список: .[] — каждый его элемент.")
    variants = (
        Variant("Сводка exchange.json — одна длинная строка JSON. Какая цена (поле price) у лота "
                "{lot} и сколько всего лотов в списке lots? Ответ: ans ЦЕНА ЧИСЛО",
                wrong=("jq length exchange.json",
                       "print -r -- $(jq '.lots[] | select(.id | contains(\"{lot}\")) | .price' "
                       "exchange.json) $(jq '.lots | length' exchange.json)"),
                alternatives=("jq '.lots[] | select(.id==\"{lot}\")' exchange.json — лот целиком, "
                              "цена — в поле price",)),
        Variant("В exchange.json — список лотов lots. Какой товар (поле item) у лота {lot} и "
                "сколько лотов со статусом sold (поле status)? Ответ: ans ТОВАР ЧИСЛО",
                hints=("Лот по id отберёт select, проданные — тоже select; строки сосчитает wc -l.",
                       "-r печатает товар без кавычек. Для счёта выведи id проданных — по одному "
                       "в строке — и отдай wc -l.",
                       "jq -r '.lots[] | select(.id==\"{lot}\") | .item' exchange.json; jq "
                       "'.lots[] | select(.status==\"sold\") | .id' exchange.json | wc -l"),
                solution="jq -r '.lots[] | select(.id==\"{lot}\") | .item' exchange.json; jq "
                         "'.lots[] | select(.status==\"sold\") | .id' exchange.json | wc -l",
                wrong=("print -r -- $(jq '.lots[] | select(.id==\"{lot}\") | .item' exchange.json) "
                       "$(jq '.lots[] | select(.status==\"sold\") | .id' exchange.json | wc -l)",
                       "print -r -- $(jq -r '.lots[] | select(.id==\"{lot}\") | .item' "
                       "exchange.json) $(jq '.lots | length' exchange.json)"),
                alternatives=("jq -r '.lots[] | .status' exchange.json | sort | uniq -c — сколько "
                              "лотов в каждом статусе разом",)),
        Variant("В lots.json сам файл — список лотов, без обёртки. Сколько стоит самый дорогой "
                "из проданных — тех, у кого status равен sold? Цена — поле price. Ответ: ans "
                "ЧИСЛО",
                hints=("Файл — список целиком: его элементы перебирает .[]. Цены проданных "
                       "достанет jq, самую большую найдёт sort.",
                       "jq '.[] | select(.status==\"sold\") | .price' выведет цены по одной в "
                       "строке; дальше — sort -rn | head -1, как в топе.",
                       "jq '.[] | select(.status==\"sold\") | .price' lots.json | sort -rn | "
                       "head -1"),
                solution="jq '.[] | select(.status==\"sold\") | .price' lots.json | sort -rn | "
                         "head -1",
                wrong=("jq '.[] | select(.status==\"sold\") | .price' lots.json | sort -r | "
                       "head -1",
                       "jq '.[].price' lots.json | sort -rn | head -1",
                       "jq '.lots[] | select(.status==\"sold\") | .price' lots.json | sort -rn | "
                       "head -1"),
                alternatives=("jq '.[] | select(.status==\"sold\") | .price' lots.json | "
                              "sort -n | tail -1 — то же с другого конца",)),
    )
    hints = ("JSON читает jq: путь к полю пишут через точку.",
             "Лоты — список .lots: .lots[] перебирает их, select(.id==\"{lot}\") оставляет нужный, "
             "| length считает.",
             "jq '.lots[] | select(.id==\"{lot}\") | .price' exchange.json; jq '.lots | length' "
             "exchange.json")
    solution = ("jq '.lots[] | select(.id==\"{lot}\") | .price' exchange.json; jq '.lots | length' "
                "exchange.json")
    explain = ("jq — это grep и cut для JSON: путь через точку достаёт поле, [] перебирает список, "
               "select оставляет подходящие, length считает, -r снимает кавычки. Ответы веб-сервисов "
               "и файлы настроек так и потрошат.")
    spell = "jq '.a.b' файл — поле; .список[] | select(.id==\"X\") — элемент; | length — сколько"
    trap_messages = {
        "twin": "В ответ попала цена другого лота с похожим id. select(.id==\"{lot}\") сравнивает "
                "id целиком, а contains и grep ищут кусок и цепляют соседей.",
        "top": "2 — это поля верхнего уровня (updated и lots), а лоты лежат в списке: считай "
               ".lots | length.",
        "lines": "1 — это строки, а весь JSON тут — одна строка: grep -c и wc -l его не сосчитают. "
                 "Лоты считает jq: .lots | length.",
        "all": "Это все лоты, а нужны только проданные: select(.status==\"sold\") оставит их, wc -l "
               "сосчитает.",
        "pretty": "Это строки, а не лоты: jq разворачивает каждый лот на 6 строк. Выведи по строке "
                  "на лот — одно поле, | .id (или флаг -c — compact, сжато: объект в одну строку), — тогда wc -l сосчитает лоты.",
        "pretty_len": "Это строки красивой печати, а не лоты: jq разворачивает каждый лот на 6 "
                      "строк. Число лотов скажет .lots | length.",
        "all_max": "Это самый дорогой лот вообще, а нужен самый дорогой из проданных: сначала "
                   "select(.status==\"sold\").",
        "text_sort": "Это самое большое по буквам, а не по числу: sort без -n сравнивает строки, и "
                     "950 у него «больше» 8000. Нужен sort -rn.",
        "min": "Это самая низкая цена: без -r sort ставит маленькие наверх. sort -rn | head -1 — "
               "самая высокая.",
    }
    fallback = ("Не то. JSON читает jq: путь через точку, нужный лот — select по id. Сдай только "
                "значения через пробел.")
    quotes = "Кавычки — от jq: без -r он печатает строки JSON в кавычках. jq -r даст голое слово."

    not_list = ("Ответа нет: lots.json — список целиком, поля lots в нём нет, и jq ругается "
                "«Cannot index array». Элементы списка — .[]: jq '.[] | …'.")

    def wrong_message(self, given, ctx):
        if '"' in given and self.matches(given.replace('"', " "), ctx):
            return self.quotes
        if ctx.state.get("file") == LOTS:
            jqs = [c.line for c in ctx.cmds if re.search(r"\bjq\b", c.line)]
            if not textnorm.parts(given) or (jqs and ".lots" in jqs[-1]):
                return self.not_list
        return super().wrong_message(given, ctx)

    def setup_variant(self, box, rng, variant):
        text, lots = datakit.exchange(rng)
        lot = datakit.exchange_target(lots)
        doc = json.loads(text)
        lots = doc["lots"]
        st = {"lot": lot}
        if variant == 2:
            st.update(self._sold_top(rng, lots))
        elif variant == 1:
            others = [x for x in lots if x["id"] != lot]
            def sold():
                return sum(x["status"] == "sold" for x in lots)
            # проданных 3+, не все, и 6·n (строки красивой печати jq) ≠ число всех лотов
            while sold() < 3 or 6 * sold() == len(lots):
                rng.choice([x for x in others if x["status"] != "sold"])["status"] = "sold"
            if sold() == len(lots):
                rng.choice(others)["status"] = "open"
            mine = next(x for x in lots if x["id"] == lot)
            n = sold()
            st.update({"answer": [mine["item"], n],
                       "traps": [["all", len(lots)], ["pretty", PRETTY_LINES * n]]})
        else:
            price = {x["id"]: x["price"] for x in lots}
            twins = [x["id"] for x in lots if x["id"] != lot and
                     (x["id"].startswith(lot) or lot.startswith(x["id"]))]
            st.update({"answer": [price[lot], len(lots)],
                       "traps": [["twin", price[t]] for t in sorted(twins)] +
                                [["top", 2], ["lines", 1],
                                 ["pretty_len", PRETTY_LINES * len(lots)]]})
        if variant == 2:        # голый список: элементы — .[] (аудит новичка п. 7)
            st["file"] = LOTS
            kit.write(Path(box) / LOTS,
                      json.dumps(lots, ensure_ascii=False, separators=(",", ":")) + "\n")
            return st
        kit.write(Path(box) / EXCHANGE,
                  json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
        return st

    @staticmethod
    def _sold_top(rng, lots):
        """Самый дорогой проданный — не самый дорогой вообще; среди проданных есть цена 9xx
        (sort без -n поставит её выше) и цена ниже 900 (минимум — отдельная ловушка)."""
        used = {x["price"] for x in lots}

        def fresh(lo, hi):
            while True:
                p = rng.randint(lo, hi)
                if p not in used:
                    used.add(p)
                    return p

        def reprice(x, lo, hi):
            used.discard(x["price"])
            x["price"] = fresh(lo, hi)

        gmax = max(lots, key=lambda x: x["price"])
        if gmax["price"] <= 9000:
            reprice(gmax, 9001, 9999)
        if gmax["status"] == "sold":
            gmax["status"] = rng.choice(("open", "closed"))
        others = [x for x in lots if x is not gmax]
        while sum(x["status"] == "sold" for x in others) < 4:
            rng.choice([x for x in others if x["status"] != "sold"])["status"] = "sold"
        sold = [x for x in others if x["status"] == "sold"]
        rng.shuffle(sold)
        top, nine, low = sold[0], sold[1], sold[2]
        reprice(top, 2000, 8999)
        reprice(nine, 900, 999)
        reprice(low, 100, 899)
        for x in sold[3:]:
            if x["price"] >= top["price"]:
                reprice(x, 100, top["price"] - 1)
        prices = [x["price"] for x in sold]
        return {"answer": top["price"],
                "traps": [["all_max", gmax["price"]],
                          ["text_sort", int(max(str(p) for p in prices))],
                          ["min", min(prices)]]}


# --- E12 (часть 7): глубже в JSON ----------------------------------------------------------

MARKET = "market.json"


class JqDeep(_DataAnswer):
    """jq вглубь: .a.b[0], keys, length, map(…), select(…), add. market.json — одной строкой.
    Ловушки (точное равенство сданного, правило 1 уроков 9а/9б): второй лот вместо первого,
    поля всего файла или число лотов вместо полей meta; «open» с хвостом (contains) и все
    лоты в сумме; null в qty — не ноль."""
    id = "jq_deep"
    title = "Глубже в JSON"
    par = 75
    scroll = (".a.b[0] — первый элемент списка внутри, счёт с нуля. Имена полей даёт keys, их "
              "число — length. Поле у каждого элемента — map(.price), только подходящие — "
              "map(select(.qty > 0)), сумма списка — add.\n"
              "Пример: jq '.users | map(.age) | add' f.json")
    variants = (
        Variant("Какой товар у самого первого лота в market.json и сколько полей в meta? "
                "ans ТОВАР ЧИСЛО",
                hints=("Путь — через точку, элемент списка — [номер]; счёт идёт с нуля.",
                       "Первый лот — .market.lots[0]; имена полей meta даст keys, их число — "
                       "length.",
                       "jq -r '.market.lots[0].item' market.json; jq '.meta | keys | length' "
                       "market.json"),
                solution="jq -r '.market.lots[0].item' market.json; jq '.meta | keys | length' "
                         "market.json",
                wrong=("print -r -- $(jq -r '.market.lots[1].item' market.json) $(jq '.meta | "
                       "keys | length' market.json)",
                       "print -r -- $(jq -r '.market.lots[0].item' market.json) $(jq 'keys | "
                       "length' market.json)"),
                alternatives=("jq '.meta | length' market.json — length у объекта тоже считает "
                              "поля",)),
        Variant("Сумма цен всех лотов со статусом open в market.json? ans ЧИСЛО",
                hints=("Лоты — .market.lots: select оставит подходящие, map достанет поле у "
                       "каждого.",
                       "map(select(.status==\"open\") | .price) — цены открытых; add сложит их.",
                       "jq '.market.lots | map(select(.status==\"open\") | .price) | add' "
                       "market.json"),
                solution="jq '.market.lots | map(select(.status==\"open\") | .price) | add' "
                         "market.json",
                wrong=("jq '.market.lots | map(select(.status | contains(\"open\")) | .price) "
                       "| add' market.json",
                       "jq '.market.lots | map(.price) | add' market.json"),
                alternatives=("jq '[.market.lots[] | select(.status==\"open\") | .price] | add' "
                              "market.json — то же через [ ]",)),
        Variant("Сколько лотов в market.json закончились (qty равно 0)? ans ЧИСЛО",
                hints=("Лоты — .market.lots: select оставит подходящие, length сосчитает.",
                       "map(select(.qty == 0)) — только лоты с нулём; | length — их число.",
                       "jq '.market.lots | map(select(.qty == 0)) | length' market.json"),
                solution="jq '.market.lots | map(select(.qty == 0)) | length' market.json",
                wrong=("jq '.market.lots | map(select(.qty < 1)) | length' market.json",
                       "jq '.market.lots | length' market.json"),
                alternatives=("jq '.market.lots[] | select(.qty == 0) | .id' market.json | wc -l "
                              "— по строке на лот",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("jq ныряет вглубь по пути (.a.b[0]), map гоняет фильтр по каждому элементу, select "
               "оставляет подходящие, add и length подбивают итог. == сравнивает точно: «opened» — "
               "не «open», а null — не 0.")
    spell = "jq '.a.b[0]' — элемент вглубь; keys | length; map(select(…) | .поле) | add — сумма"
    trap_messages = {
        "second": "Это второй лот: счёт в списке идёт с нуля — первый лот — [0].",
        "top": "2 — это поля всего файла (market и meta), а спрашивают поля meta: .meta | keys "
               "| length.",
        "lots": "Это число лотов, а спрашивают, сколько полей в meta: .meta | keys | length.",
        "loose": "Сюда попали лоты со статусом вроде opened или «open » с пробелом: contains и "
                 "grep ищут кусок. Точно open — select(.status==\"open\").",
        "all": "Это все лоты, а нужны только подходящие: сначала select(…). select уже стоит? "
               "Проверь знак: в jq = присваивает, сравнение — ==.",
        "null": "Сюда попали лоты, где qty — null (не указано): это не ноль. В jq null меньше "
                "любого числа, поэтому < 1 их берёт; select(.qty == 0) — нет.",
    }
    fallback = ("Не то. Лоты лежат в .market.lots: map и select — по каждому лоту, add и length "
                "— итог.")
    quotes = "Кавычки напечатал jq: без -r он выводит текст в кавычках. jq -r даст голое слово."
    # E24a (аудит env, мелкие): столбик цен вместо суммы; текст без кавычек в фильтре
    many = "Это цены по отдельности, а нужна их сумма: собери их в список и сложи — … | add."
    unquoted = ("Пусто: jq упал — текст в фильтре пишут в двойных кавычках: "
                "select(.status==\"open\").")
    _BARE_WORD = re.compile(r"==\s*(?!(?:null|true|false)\b)[A-Za-z_]")

    def setup_variant(self, box, rng, variant):
        d = datakit.market(rng)
        kit.write(Path(box) / MARKET, d["text"])
        lots = d["lots"]
        if variant == 1:
            return {"answer": d["open_sum"],
                    "traps": [["loose", d["loose_sum"]], ["all", d["total"]]]}
        if variant == 2:
            return {"answer": d["zeros"],
                    "traps": [["null", d["zeros"] + d["nulls"]], ["all", len(lots)]]}
        item, n = lots[0]["item"], len(d["meta"])
        return {"answer": [item, n],
                "traps": [["second", [lots[1]["item"], n]], ["top", [item, 2]],
                          ["lots", [item, len(lots)]]]}

    def wrong_message(self, given, ctx):
        """Ловушка — только при точном равенстве сданного её значению (все части)."""
        st = ctx.state
        for key, value in st.get("traps", ()):
            parts = value if isinstance(value, list) else [value]
            hit = (textnorm.same_parts(given, parts) if len(parts) > 1
                   else textnorm.same_number(given, parts[0]))
            if hit:
                return self.trap_messages[key].format(**st)
        if '"' in given:            # ревью P3, M6: вывод jq без -r дошёл до ans в кавычках
            return self.quotes
        v = variant_index(st.get("_variant", 0), len(self.variants))
        nums = [w for w in textnorm.parts(given) if textnorm.as_number(w) is not None]
        if v == 1 and len(nums) > 1:
            return self.many
        last = ctx.cmds[-1].line if ctx.cmds else ""
        if not textnorm.clean(given) and "jq" in last and self._BARE_WORD.search(last):
            return self.unquoted
        return self.common_mistake(given, ctx) or self.fallback


# --- D18 -----------------------------------------------------------------------------------

RATE_RANGES = (("USD", 78, 96), ("EUR", 86, 104), ("CNY", 10, 14), ("GBP", 102, 122))
_CURL = re.compile(r"(?:^|[\s|(])curl\s")
_URL_HOST = re.compile(r"https?://([^/\s'\"?:]+)")
_BARE_Q = re.compile(r"(?:^|\s)https?://[^\s'\"]*(?<!\\)\?")


def _rates(rng) -> Dict[str, float]:
    """Курсы с двумя знаками (вторая цифра — не ноль), попарно дальше 0.05 друг от друга."""
    while True:
        out = {}
        for cur, lo, hi in RATE_RANGES:
            cents = rng.choice([c for c in range(1, 100) if c % 10])
            out[cur] = round(rng.randint(lo, hi) + cents / 100, 2)
        vals = sorted(out.values())
        if all(b - a > 0.05 for a, b in zip(vals, vals[1:])):
            return out


class CurlApi(_DataAnswer):
    """curl к учебному API через --unix-socket: -s, -o, -i, адрес в кавычках, | jq."""
    id = "curl_api"
    title = "Запрос к API"
    par = 90
    scroll = ("curl АДРЕС — HTTP-запрос из терминала; curl -s -o файл АДРЕС — silent, без "
              "полосы загрузки, и output, ответ в файл; curl -i АДРЕС — include, и заголовки "
              "(код 200, 404, Content-Length).\n"
              "Сети в песочнице нет: сервер слушает сокет api.sock — curl -s --unix-socket "
              "api.sock http://localhost/путь. Ответ в JSON — дальше | jq. Адрес с ? — в "
              "кавычках: 'http://localhost/a?b=c'.")
    variants = (
        Variant("Здесь работает учебный сервер API (сокет api.sock). Сохрани ответ /lots в "
                "lots.json, а курс {cur} из /rates сдай: ans ЧИСЛО",
                wrong=("curl -s -m 2 http://localhost:9/rates | jq '.rates.{cur}'",
                       "curl -s --unix-socket api.sock http://localhost/lots -o lots.json; curl -s "
                       "--unix-socket api.sock http://localhost/rates | jq '.rates.{other}'"),
                alternatives=("curl -s --unix-socket api.sock http://localhost/rates > rates.json; "
                              "jq '.rates.{cur}' rates.json — сначала в файл, потом разбор",)),
        Variant("Учебный сервер за сокетом api.sock умеет отбирать лоты /lots по статусу — "
                "что он умеет, покажет адрес /. Сохрани в sold.json только проданные лоты (status "
                "sold) и сдай, сколько их: ans ЧИСЛО",
                hints=("Что умеет сервер, покажет адрес /: curl -s --unix-socket api.sock "
                       "http://localhost/",
                       "Фильтр — ?status=sold в конце адреса; адрес с ? бери в кавычки. -o "
                       "sold.json сохранит ответ, jq length сосчитает лоты.",
                       "curl -s --unix-socket api.sock 'http://localhost/lots?status=sold' -o "
                       "sold.json; jq length sold.json"),
                solution="curl -s --unix-socket api.sock 'http://localhost/lots?status=sold' -o "
                         "sold.json; jq length sold.json",
                wrong=("curl -s --unix-socket api.sock http://localhost/lots -o sold.json; jq "
                       "length sold.json",
                       "curl -s --unix-socket api.sock 'http://localhost/lots?status=open' -o "
                       "sold.json; jq length sold.json"),
                alternatives=("curl -s --unix-socket api.sock \"http://localhost/lots?status=sold\" "
                              "-o sold.json — двойные кавычки тоже годятся",)),
        Variant("Спроси учебный сервер API (сокет api.sock) про /lots: сколько байт в теле ответа "
                "— по заголовку Content-Length — и сколько в нём лотов? Ответ: ans БАЙТЫ ЛОТЫ",
                hints=("Заголовки ответа показывает curl -i; размер тела — в строке "
                       "Content-Length.",
                       "curl -i … http://localhost/lots — Content-Length в начале ответа. Лоты "
                       "сосчитает ответ без -i, отданный в jq length.",
                       "curl -i --unix-socket api.sock http://localhost/lots; curl -s "
                       "--unix-socket api.sock http://localhost/lots | jq length"),
                solution="curl -i --unix-socket api.sock http://localhost/lots; curl -s "
                         "--unix-socket api.sock http://localhost/lots | jq length",
                solution_script="print -r -- $(curl -s -i --unix-socket api.sock "
                                "http://localhost/lots | grep -i '^content-length' | tr -dc "
                                "'0-9') $(curl -s --unix-socket api.sock http://localhost/lots | "
                                "jq length)",
                wrong=("curl -s -i --unix-socket api.sock http://localhost/lots | wc -c; curl -s "
                       "--unix-socket api.sock http://localhost/lots | jq length",
                       "print -r -- $(curl -s --unix-socket api.sock http://localhost/lots | "
                       "wc -c) $(curl -s --unix-socket api.sock http://localhost/lots | wc -l)"),
                alternatives=("curl -s --unix-socket api.sock http://localhost/lots | wc -c — wc -c "
                              "считает байты: те же, что Content-Length, — длина тела",)),
    )
    hints = ("Запрос — curl; к сокету — флаг --unix-socket api.sock, адрес — http://localhost/путь.",
             "-o lots.json сохранит ответ /lots; ответ /rates отправь в jq: | jq '.rates.{cur}'.",
             "curl -s --unix-socket api.sock http://localhost/lots -o lots.json; curl -s "
             "--unix-socket api.sock http://localhost/rates | jq '.rates.{cur}'")
    solution = ("curl -s --unix-socket api.sock http://localhost/lots -o lots.json; curl -s "
                "--unix-socket api.sock http://localhost/rates | jq '.rates.{cur}'")
    explain = ("curl — браузер для скриптов: забрать данные у веб-сервиса, сохранить в файл (-o), глянуть "
               "заголовки (-i), передать в jq. Здесь он ходит через сокет, а в работе — на "
               "настоящий адрес.")
    spell = "curl -s --unix-socket сокет http://localhost/путь — запрос; -o файл — в файл; | jq"
    trap_messages = {
        "all": "Это все лоты, а нужны проданные: у /lots есть фильтр ?status=sold — адрес с ? бери "
               "в кавычки.",
        "open": "Это открытые лоты (open), а нужны проданные: ?status=sold.",
        "pretty": "Это строки, а не лоты: jq разворачивает каждый лот на 6 строк. Сосчитай сам "
                  "список: jq length sold.json — длина массива.",
        "headers": "Это байты вместе с заголовками: -i добавил их к ответу. Content-Length считает "
                   "только тело — возьми число из самого заголовка.",
        "lines": "1 — это строки: JSON в ответе идёт одной строкой. Лоты сосчитает jq length.",
    }
    fallback = ("Не то. Спроси сервер через сокет: curl -s --unix-socket api.sock "
                "http://localhost/путь, ответ разбери jq.")
    net = ("Сети здесь нет: песочница не выпускает curl к настоящим адресам. Учебный сервер — за "
           "сокетом: curl -s --unix-socket api.sock http://localhost/путь. В работе тот же приём "
           "направляют на настоящий адрес: curl -s https://…")
    sock = ("curl стучится на localhost по сети, а сети здесь нет: сервер слушает сокет. Добавь "
            "--unix-socket api.sock — адрес останется http://localhost/путь.")
    qmark = ("zsh принял ? в адресе за маску и curl не запустил («no matches found»). Возьми адрес "
             "в кавычки: 'http://localhost/…?…'.")

    def missing(self, root=None):
        from termit_app import sandbox      # длина пути — как у самой длинной песочницы
        if not apiserver.path_fits(sandbox.sample_box(root)):
            return "путь к папке игры слишком длинный для unix-сокета"
        return None

    def setup_variant(self, box, rng, variant):
        apiserver.link(box)
        _, lots = datakit.exchange(rng)
        if variant == 1:
            def n(status):
                return sum(x["status"] == status for x in lots)
            def clash():
                return n("sold") == n("open") or PRETTY_LINES * n("sold") in (len(lots), n("open"))
            while n("sold") < 2 or clash() or n("sold") == len(lots):
                if n("sold") < 2 or clash():
                    rng.choice([x for x in lots if x["status"] != "sold"])["status"] = "sold"
                else:
                    rng.choice(lots)["status"] = "open"
        rates = _rates(rng)
        cur = rng.choice(sorted(rates))
        routes = {"/": [200, {"endpoints": ["/health", "/rates", "/lots", "/lots?status=open"]}],
                  "/health": [200, {"status": "ok"}],
                  "/rates": [200, {"base": "CR", "rates": rates}],
                  "/lots": [200, lots]}
        st = {"routes": routes, "cur": cur,
              "other": rng.choice(sorted(c for c in rates if c != cur))}
        if variant == 1:
            sold = [x for x in lots if x["status"] == "sold"]
            st.update({"answer": len(sold), "file": "sold.json", "want": sold,
                       "traps": [["all", len(lots)],
                                 ["open", sum(x["status"] == "open" for x in lots)],
                                 ["pretty", PRETTY_LINES * len(sold)]]})
        elif variant == 2:
            head, body = apiserver.render(200, lots)
            st.update({"answer": [len(body), len(lots)],
                       "traps": [["headers", len(head + body)], ["lines", 1]]})
        else:
            st.update({"answer": rates[cur], "file": "lots.json", "want": lots})
        return st

    def service(self, box, state):
        routes = {k: (v[0], v[1]) for k, v in state["routes"].items()}
        return apiserver.open_server(box, routes)

    def _net(self, cmds):
        return _net_problem(cmds)

    def wrong_message(self, given, ctx):
        st = ctx.state
        if st.get("_variant", 0) == 0:
            rates = st["routes"]["/rates"][1]["rates"]
            for cur, value in sorted(rates.items()):
                if cur != st["cur"] and textnorm.same_number(given, value):
                    return f"Это курс {cur}, а нужен {st['cur']}: | jq '.rates.{st['cur']}'."
        return super().wrong_message(given, ctx)

    def _file_problem(self, box, st) -> str:
        name, want = st["file"], st["want"]
        path = "/lots?status=sold" if name == "sold.json" else "/lots"
        what = "Число верное." if name == "sold.json" else "Курс верный."
        raw = sandbox.read_in_box(box, name, READ_CAP)
        if raw is None:
            return f"{what} Осталось сохранить {path} в {name} (-o) и сдать ans ещё раз."
        text = raw.decode("utf-8", errors="replace")
        if text.startswith("HTTP/"):
            return (f"{what} Но в {name} попали заголовки — их добавил -i. Сохрани ответ без -i "
                    "и сдай ans ещё раз.")
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if data == want:
            return ""
        if name == "sold.json" and data == st["routes"]["/lots"][1]:
            return (f"{what} Но в sold.json все лоты: нужен фильтр ?status=sold — адрес в "
                    "кавычках. Сохрани заново и сдай ans ещё раз.")
        return (f"{what} Но в {name} не то, что отдаёт {path}. Сохрани заново: curl … -o {name}, "
                "и сдай ans ещё раз.")

    def check(self, ctx):
        st = ctx.state
        net = self._net(ctx.cmds)
        if ctx.answer is None:
            return Verdict(False, net)
        if not self.matches(ctx.answer, ctx):
            return Verdict(False, net or self.wrong_message(ctx.answer, ctx))
        if st.get("file"):
            problem = self._file_problem(ctx.box, st)
            if problem:
                return Verdict(False, problem)
        return Verdict(True)

def _net_problem(cmds) -> Optional[str]:
    """Отклик по последнему curl журнала: настоящий адрес, localhost без сокета, ? без
    кавычек (CurlApi и страж трека)."""
    calls = [seg for seg in _segments(cmds) if _CURL.search(seg)]
    if not calls:
        return None
    last = calls[-1]
    hosts = _URL_HOST.findall(last)
    if not hosts:
        return None
    if hosts[0] not in ("localhost", "127.0.0.1"):
        return CurlApi.net
    if "--unix-socket" not in last:
        return CurlApi.sock
    if _BARE_Q.search(last):
        return CurlApi.qmark
    return None


# --- FB14: curl POST, заголовки, опрос задачи; постраничная выдача ------------------------------
# Курс-карта (раздел 6, «Данные»): API спринтов 9 и 11 — POST с JSON, ключ в заголовке, task_id
# с опросом до готовности, offset/limit до пустой страницы. Сервер — тот же учебный api.sock
# (apiserver), обработчики собираются у родителя из state; ответы — по-английски (FB5 п. 42).

ORDER_ITEMS = ("lamp", "desk", "mug", "chair", "rug", "shelf", "kettle", "clock")
JSON_TYPE = "application/json"


def _post_routes(state: dict) -> dict:
    """Маршруты curl_post: /orders (POST JSON), /report (ключ в X-Api-Key), /jobs и
    /jobs/<task_id> (опрос: первый GET — running, дальше — done)."""
    want = state["order"]
    seen = {"posted": False, "polls": 0}

    def orders(req):
        if req.method != "POST":
            return 405, {"error": "use POST: curl -X POST -d '{...}'"}
        if JSON_TYPE not in req.headers.get("content-type", ""):
            return 400, {"error": "say it is JSON: -H 'Content-Type: application/json'"}
        body = req.body if isinstance(req.body, dict) else {}
        if body.get("item") != want["item"] or body.get("qty") != want["qty"]:
            return 400, {"error": "need item and qty", "got": body}
        return 201, {"id": state["order_id"], "item": want["item"], "qty": want["qty"]}

    def report(req):
        key = req.headers.get("x-api-key")
        if not key:
            return 401, {"error": "no key: add -H 'X-Api-Key: ...'"}
        if key != state["key"]:
            return 401, {"error": "bad key"}
        return 200, {"report": {"day": state["day"], "revenue": state["revenue"]}}

    def jobs(req):
        if req.method != "POST":
            return 405, {"error": "start a job with POST"}
        seen["posted"], seen["polls"] = True, 0
        return 201, {"task_id": state["task_id"], "status": "queued"}

    def job(req):
        if not seen["posted"]:
            return 404, {"error": "no such job: start it with POST /jobs"}
        seen["polls"] += 1
        if seen["polls"] < 2:
            return 200, {"task_id": state["task_id"], "status": "running"}
        return 200, {"task_id": state["task_id"], "status": "done", "result": state["result"]}

    return {"/": (200, {"endpoints": ["/orders", "/report", "/jobs"]}),
            "/orders": orders, "/report": report, "/jobs": jobs,
            f"/jobs/{state['task_id']}": job}


class CurlPost(_DataAnswer):
    """curl -X POST -H 'Content-Type: application/json' -d '{…}'; -H 'X-Api-Key: …'; task_id и
    опрос до status done."""
    id = "curl_post"
    title = "Отправить в API"
    par = 120
    scroll = ("curl -H 'X-Api-Key: КЛЮЧ' АДРЕС — запрос с заголовком: -H — header, строчка "
              "«Имя: значение»; ключ из файла — -H \"X-Api-Key: $(cat key.txt)\".\n"
              "Отправить данные — curl -X POST -d '{}' АДРЕС: -X — request, метод; -d — data, "
              "тело.\n"
              "Сервер тот же: curl -s --unix-socket api.sock http://localhost/путь.")
    variants = (
        Variant("Отчёт /report учебного API (сокет api.sock) отдаётся только с ключом: ключ "
                "лежит в key.txt, передают его заголовком X-Api-Key. Сдай выручку (revenue) из "
                "отчёта: ans ЧИСЛО",
                hints=("Без ключа сервер ответит 401. Заголовок добавляет -H 'Имя: значение'.",
                       "-H \"X-Api-Key: $(cat key.txt)\" — двойные кавычки, чтобы $( ) "
                       "подставил ключ; дальше | jq .report.revenue",
                       "curl -s --unix-socket api.sock -H \"X-Api-Key: $(cat key.txt)\" "
                       "http://localhost/report | jq .report.revenue"),
                solution="curl -s --unix-socket api.sock -H \"X-Api-Key: $(cat key.txt)\" "
                         "http://localhost/report | jq .report.revenue",
                wrong=("curl -s --unix-socket api.sock http://localhost/report | jq "
                       ".report.revenue",
                       "curl -s --unix-socket api.sock -H 'X-Api-Key: $(cat key.txt)' "
                       "http://localhost/report | jq .report.revenue"),
                alternatives=("curl -s --unix-socket api.sock -H \"X-Api-Key: {key}\" "
                              "http://localhost/report — ключ, вставленный руками",)),
        Variant("Оформи заказ в учебном API (сокет api.sock): POST на /orders с JSON — item "
                "{item}, qty {qty}. Сервер ответит номером заказа — сдай его: ans ЧИСЛО",
                hints=("Отправить данные — curl -X POST, тело — -d '{{…}}', что это JSON — "
                       "заголовок -H.",
                       "-H 'Content-Type: application/json' -d '{{\"item\": \"{item}\", "
                       "\"qty\": {qty}}}' — и номер заберёт | jq .id",
                       "curl -s --unix-socket api.sock -X POST -H 'Content-Type: "
                       "application/json' -d '{{\"item\": \"{item}\", \"qty\": {qty}}}' "
                       "http://localhost/orders | jq .id"),
                solution="curl -s --unix-socket api.sock -X POST -H 'Content-Type: "
                         "application/json' -d '{{\"item\": \"{item}\", \"qty\": {qty}}}' "
                         "http://localhost/orders | jq .id",
                wrong=("curl -s --unix-socket api.sock -X POST -d '{{\"item\": \"{item}\", "
                       "\"qty\": {qty}}}' http://localhost/orders | jq .id",
                       "curl -s --unix-socket api.sock -X POST -H 'Content-Type: "
                       "application/json' -d '{{\"item\": \"{item}\", \"qty\": \"{qty}\"}}' "
                       "http://localhost/orders | jq .id"),
                alternatives=("curl -s --unix-socket api.sock --json '{{\"item\": \"{item}\", "
                              "\"qty\": {qty}}}' http://localhost/orders — --json ставит и "
                              "метод, и заголовок",)),
        Variant("Отчёт в учебном API (сокет api.sock) считается не сразу: POST на /jobs с "
                "пустым JSON {{}} вернёт task_id, а GET /jobs/ЭТОТ_ID отвечает status "
                "running, пока не готово, и done с result, когда готово. Номер удобно держать "
                "в переменной tid. Сдай result: ans ЧИСЛО",
                hints=("Сначала POST: curl … -X POST -d '{{}}' http://localhost/jobs — в ответе "
                       "task_id.",
                       "Потом спрашивай GET /jobs/ID ещё раз, пока status не станет done: "
                       "стрелка вверх и Enter.",
                       "tid=$(curl -s --unix-socket api.sock -X POST -d '{{}}' "
                       "http://localhost/jobs | jq -r .task_id); curl -s --unix-socket api.sock "
                       "http://localhost/jobs/$tid | jq .result — дважды"),
                solution="tid=$(curl -s --unix-socket api.sock -X POST -d '{{}}' "
                         "http://localhost/jobs | jq -r .task_id); curl -s --unix-socket api.sock "
                         "http://localhost/jobs/$tid > /dev/null; curl -s --unix-socket api.sock "
                         "http://localhost/jobs/$tid | jq .result",
                wrong=("curl -s --unix-socket api.sock http://localhost/jobs | jq .result",),
                alternatives=("for i in 1 2 3; do curl -s --unix-socket api.sock "
                              "http://localhost/jobs/{task_id}; sleep 1; done — опрос циклом",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("GET забирает, POST отправляет: -X задаёт метод, -d — тело, а -H — заголовок, "
               "по которому сервер понимает, что пришло (Content-Type) и кто пришёл (ключ). "
               "Долгую работу API (вход сервиса для программ) часто отдаёт номером задачи — "
               "его опрашивают, пока не станет "
               "done.")
    spell = ("curl -X POST -H 'Content-Type: application/json' -d '{…}' URL; -H 'X-Api-Key: …'; "
             "task_id → GET до done")
    trap_messages = {
        "qty": "Это количество из заказа, а сдать нужно номер, который выдал сервер: | jq .id.",
        "day": "Это дата отчёта, а нужна выручка: .report.revenue.",
    }
    fallback = ("Не то. Посмотри весь ответ сервера без jq — в нём видно и ошибку, и нужное "
                "поле.")

    def missing(self, root=None):
        return CurlApi.missing(self, root)

    def setup_variant(self, box, rng, variant):
        apiserver.link(box)
        item = rng.choice(ORDER_ITEMS)
        qty = rng.randint(2, 9)
        st = {"order": {"item": item, "qty": qty}, "item": item, "qty": qty,
              "order_id": rng.randint(1000, 9999),
              "key": "k-" + "".join(rng.choice("abcdef0123456789") for _ in range(12)),
              "day": f"2726-10-{rng.randint(1, 28):02d}", "revenue": rng.randint(10000, 99999),
              "task_id": f"t-{rng.randint(10000, 99999)}", "result": rng.randint(100, 999)}
        kit.write(Path(box) / "key.txt", st["key"] + "\n")
        # FB14, ревью: вариант 0 — самый простой (один заголовок с ключом), 1 — POST с JSON
        if variant == 0:
            st.update({"answer": st["revenue"], "traps": []})
        elif variant == 2:
            st.update({"answer": st["result"], "traps": []})
        else:
            st.update({"answer": st["order_id"], "traps": [["qty", qty]]})
        return st

    def service(self, box, state):
        return apiserver.open_server(box, _post_routes(state))

    def check(self, ctx):
        net = _net_problem(ctx.cmds)
        if ctx.answer is None:
            return Verdict(False, net)
        if not self.matches(ctx.answer, ctx):
            return Verdict(False, net or self.wrong_message(ctx.answer, ctx))
        return Verdict(True)


PAGE_LIMITS = (4, 5, 6)


def _pages_routes(state: dict) -> dict:
    """/items?offset=N&limit=M — кусок списка; total — сколько всего, next_offset — откуда
    следующий кусок (null — дальше пусто). limit больше 10 сервер не даёт."""
    items = state["items"]

    def handle(req):
        raw_off = (req.query.get("offset") or ["0"])[0]
        raw_lim = (req.query.get("limit") or [str(state["limit"])])[0]
        if not (raw_off.isdigit() and raw_lim.isdigit()):
            return 400, {"error": "offset and limit are numbers: ?offset=0&limit=5"}
        off, lim = int(raw_off), min(int(raw_lim), 10)
        chunk = items[off:off + lim]
        nxt = off + lim if off + lim < len(items) else None
        return 200, {"total": len(items), "offset": off, "next_offset": nxt, "items": chunk}

    return {"/": (200, {"endpoints": ["/items?offset=0&limit=5"]}), "/items": handle}


class CurlPages(_DataAnswer):
    """Постраничная выдача: offset/limit циклом, склейка jq -s; total и next_offset."""
    id = "curl_pages"
    title = "Страница за страницей"
    par = 120
    scroll = ("Сервер отдаёт длинный список кусками: "
              "?offset=0&limit=5 — пять с начала, "
              "?offset=5&limit=5 — следующие пять. Адрес с ? и & — в кавычках.\n"
              "Все куски циклом: for o in 0 5 10; do curl -s … \"http://localhost/items?"
              "offset=$o&limit=5\"; done.\n"
              "Склеить ответы — jq -s: slurp, «всё разом», сделает из них один массив.")
    variants = (
        Variant("Учебный API (сокет api.sock) отдаёт товары кусками: /items?offset=N&limit="
                "{limit}, в ответе total — сколько всего. Собери все куски и сдай сумму qty по "
                "всем товарам: ans ЧИСЛО",
                hints=("Первый кусок — offset=0; total в ответе скажет, сколько кусков нужно.",
                       "Цикл по offset {offsets}, ответы — в jq -s и сложить: map(.items[].qty) "
                       "| add.",
                       "for o in {offsets}; do curl -s --unix-socket api.sock "
                       "\"http://localhost/items?offset=$o&limit={limit}\"; done | jq -s "
                       "'map(.items[].qty) | add'"),
                solution="for o in {offsets}; do curl -s --unix-socket api.sock "
                         "\"http://localhost/items?offset=$o&limit={limit}\"; done | jq -s "
                         "'map(.items[].qty) | add'",
                wrong=("curl -s --unix-socket api.sock 'http://localhost/items?offset=0&limit="
                       "{limit}' | jq '[.items[].qty] | add'",),
                alternatives=("curl -s --unix-socket api.sock 'http://localhost/items?offset=0&"
                              "limit=10' | jq .total — сколько всего, прежде чем считать "
                              "куски",)),
        Variant("Учебный API (сокет api.sock) отдаёт товары кусками по {limit}: "
                "/items?offset=N&limit={limit}, в ответе total — сколько всего. Сохрани все "
                "товары одним массивом в all.json и "
                "сдай, сколько их: ans ЧИСЛО",
                hints=("Пройди куски циклом по offset; total в первом ответе скажет, где конец.",
                       "jq -s 'map(.items) | add' склеит куски в один массив; > all.json; jq "
                       "length all.json.",
                       "for o in {offsets}; do curl -s --unix-socket api.sock "
                       "\"http://localhost/items?offset=$o&limit={limit}\"; done | jq -s "
                       "'map(.items) | add' > all.json; jq length all.json"),
                solution="for o in {offsets}; do curl -s --unix-socket api.sock "
                         "\"http://localhost/items?offset=$o&limit={limit}\"; done | jq -s "
                         "'map(.items) | add' > all.json; jq length all.json",
                wrong=("curl -s --unix-socket api.sock 'http://localhost/items?offset=0&limit="
                       "{limit}' | jq .items > all.json; jq length all.json",),
                alternatives=("next_offset в ответе — откуда следующий кусок; null — дальше "
                              "пусто",)),
        Variant("Учебный API (сокет api.sock) отдаёт товары кусками: /items?offset=N&limit="
                "{limit}, в ответе total — сколько всего. Сколько товаров со status sold? "
                "Собери все куски: ans ЧИСЛО",
                hints=("Куски — циклом по offset; без всех кусков посчитаешь только первые.",
                       "jq -s 'map(.items[]) | map(select(.status == \"sold\")) | length'.",
                       "for o in {offsets}; do curl -s --unix-socket api.sock "
                       "\"http://localhost/items?offset=$o&limit={limit}\"; done | jq -s "
                       "'map(.items[]) | map(select(.status == \"sold\")) | length'"),
                solution="for o in {offsets}; do curl -s --unix-socket api.sock "
                         "\"http://localhost/items?offset=$o&limit={limit}\"; done | jq -s "
                         "'map(.items[]) | map(select(.status == \"sold\")) | length'",
                wrong=("curl -s --unix-socket api.sock 'http://localhost/items?offset=0&limit="
                       "{limit}' | jq '[.items[] | select(.status == \"sold\")] | length'",),
                alternatives=("jq -s '[.[].items[] | select(.status == \"sold\")] | length' — "
                              "та же склейка другой записью",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Большой список сервер отдаёт кусками, чтобы не грузить всё разом: offset — с "
               "какого места, limit — сколько. Куски собирают циклом до конца (total или пустой "
               "next_offset), а jq -s превращает поток ответов в один массив.")
    spell = ("for o in 0 5 10; do curl -s \"URL?offset=$o&limit=5\"; done | jq -s "
             "'map(.items) | add'")
    trap_messages = {
        "first": "Это только первый кусок. Товаров больше — total в ответе; пройди все offset "
                 "циклом.",
    }
    fallback = "Не то. Проверь, что собраны все куски: offset от 0 до total с шагом limit."

    def missing(self, root=None):
        return CurlApi.missing(self, root)

    def setup_variant(self, box, rng, variant):
        apiserver.link(box)
        limit = rng.choice(PAGE_LIMITS)
        n = rng.randint(2 * limit + 1, 3 * limit)        # ровно три куска, последний неполный
        items = [{"id": f"P-{100 + i}", "item": rng.choice(ORDER_ITEMS),
                  "qty": rng.randint(1, 20), "status": rng.choice(("open", "sold"))}
                 for i in range(n)]
        first = items[:limit]
        offsets = " ".join(str(o) for o in range(0, n, limit))
        st = {"items": items, "limit": limit, "offsets": offsets}
        if variant == 1:
            st.update({"answer": n, "file": "all.json", "want": items,
                       "traps": [["first", limit]]})
        elif variant == 2:
            sold = sum(x["status"] == "sold" for x in items)
            st.update({"answer": sold,
                       "traps": [["first", sum(x["status"] == "sold" for x in first)]]})
        else:
            st.update({"answer": sum(x["qty"] for x in items),
                       "traps": [["first", sum(x["qty"] for x in first)]]})
        st["traps"] = [t for t in st["traps"] if t[1] != st["answer"]]
        return st

    def service(self, box, state):
        return apiserver.open_server(box, _pages_routes(state))

    def check(self, ctx):
        st = ctx.state
        net = _net_problem(ctx.cmds)
        if ctx.answer is None:
            return Verdict(False, net)
        if not self.matches(ctx.answer, ctx):
            return Verdict(False, net or self.wrong_message(ctx.answer, ctx))
        if st.get("file"):
            raw = sandbox.read_in_box(ctx.box, st["file"], READ_CAP)
            if raw is None:
                return Verdict(False, "Число верное. Осталось сохранить все товары в all.json "
                                      "(> all.json) и сдать ans ещё раз.")
            try:
                data = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                data = None
            if data != st["want"]:
                return Verdict(False, "Число верное, но в all.json не все товары одним "
                                      "массивом: склей куски jq -s 'map(.items) | add' > "
                                      "all.json и сдай ans ещё раз.")
        return Verdict(True)


# --- D19: страж ----------------------------------------------------------------------------

ACCESS = "access.log"
REPORT = "report"
BOSS_MODES = ("hour", "window", "owner")
_HOUR = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2})")
_IPV4 = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
# модель sed -E 's/\.[0-9]+ /.x /': первое «точка, цифры, пробел» — последнее число адреса
_LAST_OCTET = re.compile(r"\.[0-9]+ ")
LOGIN_FAIL = " POST /login 401 "
OWNER_TAILS = ("net", "host", "wifi", "cloud", "telecom")


def _lines_sha(lines) -> str:
    """Отпечаток набора строк: непустые, по алфавиту — порядок вывода игрока не важен."""
    return _sha("\n".join(sorted(x for x in lines if x.strip())).encode("utf-8"))


def _mask(line: str) -> str:
    return _LAST_OCTET.sub(".x ", line, count=1)


def _owners(rng, ips: List[str]) -> List[dict]:
    names, out = set(), []
    for ip in ips:
        name = f"{kit.latin(rng)}-{rng.choice(OWNER_TAILS)}"
        while name in names:
            name = f"{kit.latin(rng)}-{rng.choice(OWNER_TAILS)}"
        names.add(name)
        out.append({"ip": ip, "owner": name})
    rng.shuffle(out)
    return out


class BossData(Task):
    """Страж трека: журнал доступа за неделю со спрятанной атакой (datakit.access_log).
    Три режима, у каждого четыре файла в report/; первый шаг у всех — час атаки.
    A — топ-5 часа, строки лидера и его байты (cut/sort/uniq, awk по полю, сумма);
    B — первая половина часа, неудачные входы и копия с маской адресов (grep -E, grep -c, sed);
    C — топ-5, список хозяев с учебного сервера API и хозяин лидера (curl, jq).
    Ловушки построены данными: краулер — лидер недели, у лидера есть двойник «лидер+цифра»,
    у лидера есть и 200, и 401, неудачные входы бывают и в другие часы."""
    id = "boss_data"
    track = "data"
    title = "Разбор журнала доступа"
    boss = True
    par = 480
    scroll = ("cut -c1-13 файл — первые 13 символов строки (здесь дата и час). Топ — sort | "
              "uniq -c | sort -rn | head -5. Точный адрес — awk '$2==\"10.0.0.1\"' (grep "
              "10.0.0.1 зацепит и 10.0.0.15). Сумма по условию — awk '$5==200 {s+=$6} END "
              "{print s}'. mkdir -p папка — создать папку отчёта.")
    steps = ("report/hour.txt — час атаки: дата и час, когда запросов больше всего (вида "
             "2726-01-05T09)",
             "report/top5.txt — 5 адресов, чаще всех стучавших в этот час, по убыванию",
             "report/leader.log — все строки лидера топа за час атаки, как в access.log",
             "report/bytes.txt — сколько байт он унёс: сумма байт (шестое поле, после кода "
             "ответа) по его ответам 200")
    MODE_STEPS = (
        None,
        (steps[0],
         "report/first30.log — строки первой половины часа атаки (минуты 00–29), как в "
         "access.log",
         "report/logins.txt — сколько неудачных входов (POST /login 401) было за час атаки",
         "report/public.log — строки first30.log, где у адреса последнее число заменено на x "
         "(10.9.9.15 → 10.9.9.x); за адресом в строке идёт пробел"),
        (steps[0], steps[1],
         "report/owners.json — ответ /owners учебного сервера API целиком",
         "report/owner.txt — хозяин лидера топа по этому списку"),
    )
    _HOUR_SCRIPT = "\n".join([
        "mkdir -p report",
        "h=$(cut -c1-13 access.log | sort | uniq -c | sort -rn | head -1 | awk '{{print $2}}')",
        "print -r -- $h > report/hour.txt",
    ])
    _TOP_SCRIPT = "\n".join([
        "grep \"^$h\" access.log | cut -d' ' -f2 | sort | uniq -c | sort -rn | head -5 "
        "> report/top5.txt",
        "ip=$(head -1 report/top5.txt | awk '{{print $2}}')",
    ])
    _HOUR_SHOWN = ("mkdir -p report; cut -c1-13 access.log | sort | uniq -c | sort -rn | head -1 "
                   "> report/hour.txt; ")
    _TOP_SHOWN = ("grep '^{hour}' access.log | cut -d' ' -f2 | sort | uniq -c | sort -rn | "
                  "head -5 > report/top5.txt; ")
    _HINT_HOUR = ("Час атаки — тот, где строк больше всего: cut -c1-13 access.log | sort | "
                  "uniq -c | sort -rn | head -3. Папку — mkdir -p report.")
    _HINT_TOP = ("Топ часа: grep '^ЧАС' access.log | cut -d' ' -f2 | sort | uniq -c | sort -rn "
                 "| head -5 > report/top5.txt")
    variants = (
        Variant("Неделю кто-то долбил сервер, и access.log распух. Найди час атаки, пятёрку "
                "самых громких адресов этого часа и строки главного атакующего; сколько байт он "
                "унёс — тоже в отчёт. Всё — в папку report/, по шагам ниже.",
                hints=(_HINT_HOUR,
                       _HINT_TOP + ". Лидера бери точно: awk '$2==\"IP\"'.",
                       "grep '^ЧАС' access.log | awk '$2==\"IP\"' > report/leader.log; "
                       "awk '$5==200 {{s+=$6}} END {{print s}}' report/leader.log > "
                       "report/bytes.txt"),
                solution=(_HOUR_SHOWN + _TOP_SHOWN +
                          "grep '^{hour}' access.log | awk '$2==\"{leader}\"' > report/leader.log; "
                          "awk '$5==200 {{s+=$6}} END {{print s}}' report/leader.log > "
                          "report/bytes.txt"),
                solution_script="\n".join([
                    _HOUR_SCRIPT, _TOP_SCRIPT,
                    "grep \"^$h\" access.log | awk -v ip=$ip '$2==ip' > report/leader.log",
                    "awk '$5==200 {{s+=$6}} END {{print s}}' report/leader.log > report/bytes.txt",
                ]),
                wrong=("\n".join([
                    _HOUR_SCRIPT,
                    "cut -d' ' -f2 access.log | sort | uniq -c | sort -rn | head -5 > "
                    "report/top5.txt",
                    "grep '^{hour}' access.log | awk '$2==\"{leader}\"' > report/leader.log",
                    "awk '$5==200 {{s+=$6}} END {{print s}}' report/leader.log > report/bytes.txt",
                ]), "\n".join([
                    _HOUR_SCRIPT, _TOP_SCRIPT,
                    "grep \"^$h\" access.log | grep $ip > report/leader.log",
                    "awk '$5==200 {{s+=$6}} END {{print s}}' report/leader.log > report/bytes.txt",
                ]), "\n".join([
                    _HOUR_SCRIPT, _TOP_SCRIPT,
                    "grep \"^$h\" access.log | awk -v ip=$ip '$2==ip' > report/leader.log",
                    "awk '{{s+=$6}} END {{print s}}' report/leader.log > report/bytes.txt",
                ])),
                alternatives=("grep '^{hour}' access.log | awk '{{print $2}}' | sort | uniq -c | "
                              "sort -rn | head -5 — адрес вторым полем через awk вместо cut",)),
        Variant("В access.log за неделю спрятана атака. Отчёт — в папку report/: час атаки, "
                "строки его первой половины, сколько за этот час было неудачных входов и копия "
                "первой половины с замаскированными адресами — такую можно показать посторонним.",
                hints=(_HINT_HOUR,
                       "Первая половина часа — минуты 00–29: grep -E '^ЧАС:[0-2]' access.log. "
                       "Неудачный вход — строка с POST /login 401, grep -c её сосчитает.",
                       "sed -E 's/\\.[0-9]+ /.x /' report/first30.log > report/public.log — "
                       "последнее число адреса станет x."),
                solution=(_HOUR_SHOWN +
                          "grep -E '^{hour}:[0-2]' access.log > report/first30.log; "
                          "grep '^{hour}' access.log | grep -c 'POST /login 401' > "
                          "report/logins.txt; "
                          "sed -E 's/\\.[0-9]+ /.x /' report/first30.log > report/public.log"),
                solution_script="\n".join([
                    _HOUR_SCRIPT,
                    "grep -E \"^${{h}}:[0-2]\" access.log > report/first30.log",
                    "grep \"^$h\" access.log | grep -c 'POST /login 401' > report/logins.txt",
                    "sed -E 's/\\.[0-9]+ /.x /' report/first30.log > report/public.log",
                ]),
                wrong=("\n".join([
                    _HOUR_SCRIPT,
                    "grep \"^$h\" access.log > report/first30.log",
                    "grep \"^$h\" access.log | grep -c 'POST /login 401' > report/logins.txt",
                    "sed -E 's/\\.[0-9]+ /.x /' report/first30.log > report/public.log",
                ]), "\n".join([
                    _HOUR_SCRIPT,
                    "grep -E \"^${{h}}:[0-2]\" access.log > report/first30.log",
                    "grep -c 'POST /login 401' access.log > report/logins.txt",
                    "sed -E 's/\\.[0-9]+ /.x /' report/first30.log > report/public.log",
                ]), "\n".join([
                    _HOUR_SCRIPT,
                    "grep -E \"^${{h}}:[0-2]\" access.log > report/first30.log",
                    "grep \"^$h\" access.log | grep -c 'POST /login 401' > report/logins.txt",
                    "sed 's/\\.[0-9]+ /.x /' report/first30.log > report/public.log",
                ])),
                alternatives=("grep '^{hour}:[0-2]' access.log — класс [0-2] понимает и grep "
                              "без -E",)),
        Variant("Разбери access.log: найди час атаки и пятёрку самых громких адресов этого часа. "
                "Кто стоит за лидером, знает учебный сервер API (сокет api.sock): его список "
                "/owners сохрани в отчёт и назови хозяина лидера. Всё — в папку report/, по "
                "шагам ниже.",
                hints=(_HINT_HOUR,
                       _HINT_TOP + ". Список: curl -s --unix-socket api.sock "
                       "http://localhost/owners -o report/owners.json",
                       "jq -r '.[] | select(.ip==\"IP\") | .owner' report/owners.json > "
                       "report/owner.txt — IP лидера бери из первой строки top5.txt"),
                solution=(_HOUR_SHOWN + _TOP_SHOWN +
                          "curl -s --unix-socket api.sock http://localhost/owners -o "
                          "report/owners.json; jq -r '.[] | select(.ip==\"{leader}\") | .owner' "
                          "report/owners.json > report/owner.txt"),
                solution_script="\n".join([
                    _HOUR_SCRIPT, _TOP_SCRIPT,
                    "curl -s --unix-socket api.sock http://localhost/owners -o report/owners.json",
                    "jq -r --arg ip $ip '.[] | select(.ip==$ip) | .owner' report/owners.json > "
                    "report/owner.txt",
                ]),
                wrong=("\n".join([
                    _HOUR_SCRIPT, _TOP_SCRIPT,
                    "curl -s --unix-socket api.sock http://localhost/owners -o report/owners.json",
                    "jq -r '.[] | select(.ip==\"{collision}\") | .owner' report/owners.json > "
                    "report/owner.txt",
                ]), "\n".join([
                    _HOUR_SCRIPT, _TOP_SCRIPT,
                    "curl -s -m 2 http://localhost:9/owners -o report/owners.json",
                    "jq -r '.[] | select(.ip==\"{leader}\") | .owner' report/owners.json > "
                    "report/owner.txt",
                ])),
                alternatives=("curl -s --unix-socket api.sock http://localhost/owners > "
                              "report/owners.json — > вместо -o, файл тот же",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Сначала когда, потом кто, потом что он творил: пик — по счёту строк за час (cut | "
               "sort | uniq -c | sort -rn), адрес — точно по полю, а не подстрокой. Дальше тот же "
               "конвейер с grep -E, sed или curl и jq — так раскусывают любой журнал доступа.")
    spell = ("cut -c1-13 log | sort | uniq -c | sort -rn — пик по часам; awk '$2==\"IP\"' — "
             "точный адрес")

    msg = {
        "hour_form": "В report/hour.txt нужны дата и час, как в начале строки журнала — вида "
                     "2726-01-05T09: это первые 13 символов, cut -c1-13.",
        "hour": "Это не час атаки. Час атаки — тот, где строк больше всего: посчитай "
                "cut -c1-13 access.log | sort | uniq -c | sort -rn.",
        "week": "В top5.txt топ за всю неделю, а нужен час атаки: сначала отбери его строки "
                "grep '^ЧАС' access.log, потом считай.",
        "top_count": "В top5.txt нужно ровно пять адресов, громкие сверху: | head -5.",
        "top_order": "Адреса те, но не по порядку: sort -rn ставит самых громких наверх.",
        "top": "Это не пятёрка часа атаки: строки часа — grep '^ЧАС' access.log, адрес — "
               "cut -d' ' -f2, дальше sort | uniq -c | sort -rn | head -5.",
        "collision": "В leader.log чужие строки: адрес {collision} тоже начинается с {leader}. "
                     "Ищи точно по полю: awk '$2==\"{leader}\"'.",
        "leader": "В leader.log должны быть все строки лидера за час атаки — и только они: "
                  "grep '^ЧАС' access.log | awk '$2==\"IP\"'.",
        "bytes_all": "В сумму попали ответы не 200: условие $5==200 перед скобками.",
        "bytes": "Сумма не сходится: складывай поле bytes ($6) только у строк лидера с кодом "
                 "200 ($5).",
        "whole": "В first30.log весь час, а нужна первая половина: минуты 00–29 — после "
                 "двоеточия [0-2].",
        "days": "В first30.log есть строки других дней: привяжи шаблон к началу строки и дате — "
                "^ЧАС:[0-2].",
        "first": "В first30.log должны быть все строки часа атаки с минутами 00–29 — и только "
                 "они, как в access.log.",
        "logins_week": "Это неудачные входы за всю неделю, а нужен час атаки: сначала "
                       "grep '^ЧАС' access.log, потом grep -c.",
        "logins_any": "Посчитаны и удачные входы: нужен только ответ 401 — 'POST /login 401'.",
        "logins": "Число не сходится: строки часа атаки, где есть POST /login 401, — "
                  "grep '^ЧАС' access.log | grep -c 'POST /login 401'.",
        "same": "В public.log ничего не заменилось: шаблон не нашёл адрес. Последнее число "
                "адреса — точка, цифры и пробел за ними: \\.[0-9]+ и пробел.",
        "public_noE": "В public.log ничего не заменилось: + sed понимает только с флагом -E — "
                      "sed -E 's/…/…/'.",
        "public_dollar": "В public.log ничего не заменилось: $ — конец строки, а адрес стоит в "
                         "середине, за ним пробел. Убери $ и поставь в шаблон пробел.",
        "empty": "report/{file} пуст: команда, похоже, ругнулась или шаблон ничего не нашёл — "
                 "прочти её сообщение и запусти ещё раз.",
        "leader_empty": "leader.log пуст. Проверь разделитель: в access.log поля через пробел, "
                        "-F, здесь не нужен — адрес второе поле, $2.",
        "owner_quotes": "Хозяин верный, но в кавычках: jq без -r печатает строку JSON. Добавь "
                        "-r: jq -r '…'.",
        "owner_empty": "owner.txt пуст: jq, похоже, упал — прочти его сообщение и проверь фильтр. "
                       "Весь файл — список, поэтому начало фильтра .[].",
        "masked_whole": "public.log сделан из всего часа, а нужен из first30.log.",
        "public": "В public.log нужны строки first30.log, где у адреса только последнее число "
                  "стало x (10.9.9.15 → 10.9.9.x), остальное — как было.",
        "headers": "В owners.json попали заголовки ответа: без -i — только тело.",
        "owners": "В owners.json нужен ответ /owners целиком: curl -s --unix-socket api.sock "
                  "http://localhost/owners -o report/owners.json",
        "owner_collision": "Это хозяин {collision}, а не лидера: адрес лишь начинается так же. "
                           "Выбирай точно: select(.ip==\"…\").",
        "owner_week": "Это хозяин адреса, который громче всех за неделю, а нужен лидер часа "
                      "атаки — первый в top5.txt.",
        "owner_second": "Это хозяин второго в топе. Лидер — первая строка top5.txt.",
        "owner": "Это не хозяин лидера: в owners.json найди запись с его адресом — "
                 "jq -r '.[] | select(.ip==\"IP\") | .owner'.",
    }

    # missing() нет: страж — экзамен и ключ к званию, он доступен при любом пути к игре.
    # Режим C (учебный API на unix-сокете) выдаётся, только когда путь сокета влезает в
    # sun_path; иначе ротация идёт только по A и B (allowed_variants), а явный C заменяется
    # на A или B по зерну (allowed_variant) — в работе, в репетиции и при reset.
    API_MODE = 2

    def allowed_variants(self, box):
        if apiserver.path_fits(box):
            return tuple(range(len(self.variants)))
        return tuple(v for v in range(len(self.variants)) if v != self.API_MODE)

    def steps_for(self, state):
        mode = state.get("mode", "hour")
        steps = self.MODE_STEPS[BOSS_MODES.index(mode) if mode in BOSS_MODES else 0]
        return list(steps or self.steps)

    def setup_variant(self, box, rng, variant):
        text, facts = datakit.access_log(rng)
        kit.write(Path(box) / ACCESS, text)
        hour = facts["hour"]
        st = {"mode": BOSS_MODES[variant], "hour": hour, "leader": facts["leader"],
              "collision": facts["collision"], "top5": facts["top5"],
              "week_top5": facts["week_top5"]}
        if variant == 0:
            st.update({"leader_sha": _lines_sha(facts["leader_lines"]),
                       "bytes200": facts["bytes200"], "bytes_all": facts["bytes_all"]})
            return st
        lines = text.splitlines()
        whole = [x for x in lines if x.startswith(hour)]
        if variant == 1:
            hh = hour[-2:]
            first = [x for x in whole if x[13:14] == ":" and x[14:15] in "012"]
            days = [x for x in lines if x[10:14] == f"T{hh}:" and x[14:15] in "012"]
            logins = sum(LOGIN_FAIL in x for x in whole)
            week = sum(LOGIN_FAIL in x for x in lines)
            if week == logins or len(days) == len(first):     # построением не бывает
                raise ValueError("ловушки неудачных входов или других дней не сработают")
            st.update({"first_sha": _lines_sha(first), "whole_sha": _lines_sha(whole),
                       "days_sha": _lines_sha(days),
                       "public_sha": _lines_sha(_mask(x) for x in first),
                       "public_whole_sha": _lines_sha(_mask(x) for x in whole),
                       "logins": logins, "logins_week": week,
                       "logins_any": sum(" POST /login " in x for x in whole)})
            return st
        apiserver.link(box)
        hour_ips = sorted({x.split(" ", 2)[1] for x in whole} -
                          set(facts["top5"]) - {facts["collision"], datakit.CRAWLER})
        ips = (list(facts["top5"]) + [facts["collision"], datakit.CRAWLER] +
               rng.sample(hour_ips, min(8, len(hour_ips))))
        owners = _owners(rng, ips)
        by_ip = {x["ip"]: x["owner"] for x in owners}
        st.update({"routes": {"/": [200, {"endpoints": ["/health", "/owners"]}],
                              "/health": [200, {"status": "ok"}],
                              "/owners": [200, owners]},
                   "owner": by_ip[facts["leader"]],
                   "owner_traps": [["owner_collision", by_ip[facts["collision"]]],
                                   ["owner_week", by_ip[datakit.CRAWLER]],
                                   ["owner_second", by_ip[facts["top5"][1]]]]})
        return st

    def service(self, box, state):
        if state.get("mode") != "owner":
            return None
        routes = {k: (v[0], v[1]) for k, v in state["routes"].items()}
        return apiserver.open_server(box, routes)

    # --- чтение отчёта (только sandbox.read_in_box: без симлинков и гигантов) ---

    @staticmethod
    def _text(ctx, name) -> Optional[str]:
        raw = sandbox.read_in_box(ctx.box, Path(REPORT) / name, READ_CAP)
        return None if raw is None else raw.decode("utf-8", errors="replace")

    @staticmethod
    def _ips(text: str) -> List[str]:
        out = []
        for ip in _IPV4.findall(text):
            if ip not in out:
                out.append(ip)
        return out

    def _step_hour(self, ctx):
        """(готово, ключ отклика или None)."""
        text = self._text(ctx, "hour.txt")
        if text is None:
            return False, None
        m = _HOUR.search(text)
        if not m:
            return False, "hour_form"
        ok = f"{m.group(1)}T{m.group(2)}" == ctx.state["hour"]
        return ok, None if ok else "hour"

    def _step_top(self, ctx):
        text = self._text(ctx, "top5.txt")
        if text is None:
            return False, None
        st, ips = ctx.state, self._ips(text)
        if ips == st["top5"]:
            return True, None
        if ips[:5] == st["week_top5"]:
            return False, "week"
        if ips and (ips[:5] == st["top5"] or ips == st["top5"][:len(ips)]):
            return False, "top_count"
        if sorted(ips) == sorted(st["top5"]):
            return False, "top_order"
        return False, "top"

    def _step_leader(self, ctx):
        text = self._text(ctx, "leader.log")
        if text is None:
            return False, None
        lines = text.splitlines()
        if _lines_sha(lines) == ctx.state["leader_sha"]:
            return True, None
        if not text.strip():
            return False, "leader_empty"
        if any(len(x.split()) > 1 and x.split()[1] == ctx.state["collision"] for x in lines):
            return False, "collision"
        return False, "leader"

    def _step_bytes(self, ctx):
        text = self._text(ctx, "bytes.txt")
        if text is None:
            return False, None
        st = ctx.state
        if textnorm.same_number(text, st["bytes200"]):
            return True, None
        return False, "bytes_all" if textnorm.same_number(text, st["bytes_all"]) else "bytes"

    def _step_first(self, ctx):
        text = self._text(ctx, "first30.log")
        if text is None:
            return False, None
        sha, st = _lines_sha(text.splitlines()), ctx.state
        if sha == st["first_sha"]:
            return True, None
        if not text.strip():
            return False, ("empty", "first30.log")
        return False, {st["whole_sha"]: "whole", st["days_sha"]: "days"}.get(sha, "first")

    def _step_logins(self, ctx):
        text = self._text(ctx, "logins.txt")
        if text is None:
            return False, None
        st = ctx.state
        if textnorm.same_number(text, st["logins"]):
            return True, None
        for key in ("logins_week", "logins_any"):
            if textnorm.same_number(text, st[key]):
                return False, key
        return False, "logins"

    def _step_public(self, ctx):
        text = self._text(ctx, "public.log")
        if text is None:
            return False, None
        sha, st = _lines_sha(text.splitlines()), ctx.state
        if sha == st["public_sha"]:
            return True, None
        if not text.strip():
            return False, ("empty", "public.log")
        if sha == st["first_sha"]:
            return False, self._sed_why(ctx.cmds)
        return False, {st["public_whole_sha"]: "masked_whole"}.get(sha, "public")

    @staticmethod
    def _sed_why(cmds) -> str:
        """Почему sed ничего не заменил — по последнему вызову sed в журнале."""
        seds = [seg for seg in _segments(cmds) if _SED.search(seg)]
        if not seds:
            return "same"
        last = seds[-1]
        expr = re.search(r"s/((?:[^/\\]|\\.)*)/", last)
        if expr and expr.group(1).endswith("$"):
            return "public_dollar"
        if "+" in (expr.group(1) if expr else last) and not re.search(
                r"\bsed\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*[Er]", last):
            return "public_noE"
        return "same"

    def _step_owners(self, ctx):
        text = self._text(ctx, "owners.json")
        if text is None:
            return False, None
        if text.startswith("HTTP/"):
            return False, "headers"
        try:
            got = json.loads(text)
        except ValueError:
            return False, "owners"
        ok = got == ctx.state["routes"]["/owners"][1]
        return ok, None if ok else "owners"

    def _step_owner(self, ctx):
        text = self._text(ctx, "owner.txt")
        if text is None:
            return False, None
        st = ctx.state
        if textnorm.same_text(text, st["owner"]):
            return True, None
        if not text.strip():
            return False, "owner_empty"
        bare = text.strip().strip('"')
        if bare != text.strip() and textnorm.same_text(bare, st["owner"]):
            return False, "owner_quotes"
        for key, value in st["owner_traps"]:
            if textnorm.same_text(bare, value):
                return False, key
        return False, "owner"

    def _steps(self, ctx):
        mode = ctx.state.get("mode", "hour")
        if mode == "window":
            parts = (self._step_hour, self._step_first, self._step_logins, self._step_public)
        elif mode == "owner":
            parts = (self._step_hour, self._step_top, self._step_owners, self._step_owner)
        else:
            parts = (self._step_hour, self._step_top, self._step_leader, self._step_bytes)
        return [f(ctx) for f in parts]

    def progress(self, ctx):
        return [ok for ok, _ in self._steps(ctx)]

    def check(self, ctx):
        steps = self._steps(ctx)
        if all(ok for ok, _ in steps):
            return Verdict(True)
        st = ctx.state
        for ok, key in steps:
            if not ok and key:
                key, file = key if isinstance(key, tuple) else (key, "")
                return Verdict(False, self.msg[key].format(file=file, **st))
        if st.get("mode") == "owner" and not steps[2][0]:
            net = _net_problem(ctx.cmds)
            if net:
                return Verdict(False, net)
        return Verdict(False)


TASKS = [HeadTail(), GrepCount(), PipeCount(), RedirectReport(), CutUniq(),
         TopValues(), FlagReview(), AwkSum(), LogPeriod(), JoinParts(), StderrSplit(),
         TeeLog(), SedFix(), JqField(), JqDeep(), CurlApi(), CurlPost(), CurlPages(),
         BossData()]

# FB21: блок «Регулярки» — termit_app/tasks/regex.py; задачи блока сами встают в TASKS
from termit_app.tasks import regex  # noqa: E402,F401
