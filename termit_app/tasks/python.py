"""Трек «Python» (часть 10, «Змеиный рынок»): запуск скриптов и traceback, переменные,
списки и словари, циклы и функции, своя библиотека, REPL, импорт стандартной поставки
(json, csv, pathlib, re, datetime, collections, statistics, urllib) и учебные пакеты.

Движок задач «поправь скрипт» — termit_app/tasks/pykit.py (PyEditTask, py(), py_text), там
же генераторы данных: ответ считает Python-функция родителя по строкам генератора, код игрока
родитель не исполняет и не импортирует. Учебный API с POST и журналом —
termit_app/apiserver.py. Порядок в TASKS — порядок обучения."""
import re
from pathlib import Path
from typing import List, Tuple

from termit_app.tasks import envkit, kit, pykit
from termit_app.tasks.base import (AnswerTask, Task, Variant, Verdict, memo_marks, sources,
                                  variant_index)
from termit_app.tasks.pykit import py


def _v(task, state: dict) -> int:
    return variant_index(state.get("_variant", 0), len(task.variants))


# --- 1. py_run ------------------------------------------------------------------------------

def script_args(jour, script: str):
    """Аргументы после script в последнем запуске «python3 … script …» журнала: (список, исход)
    или None — не запускали. Перенаправления (> файл) — не аргументы."""
    hit = envkit.last_line(jour, lambda s: envkit.py_runs(s, script))
    if hit is None:
        return None
    for seg in envkit.segments(hit[0]):
        if not envkit.py_runs(seg, script):
            continue
        _, _, args = envkit.lead(seg)
        after, seen, skip = [], False, False
        for a in args:
            if skip:
                skip = False
                continue
            if not seen:
                seen = a == script or a.endswith("/" + script)
                continue
            if a in (">", ">>", "<", "2>", "2>>", "&>"):
                skip = True
                continue
            if a[:1] in "<>" or a.startswith(("2>", "&>")):
                continue
            after.append(a)
        return after, hit[1]
    return None


class PyRun(AnswerTask):
    """python3 файл.py, аргумент скрипта, python3 -c, print и traceback."""
    id = "py_run"
    track = "py"
    title = "Запусти и прочти"
    par = 50
    pinned_python = True
    scroll = ("Запуск: python3 hello.py; с файлом после имени скрипта — python3 count.py "
              "data.txt.\n"
              "Код прямо строкой: python3 -c 'print(2 * 3)' (c — command); вывод делает "
              "print(x).\n"
              "Скрипт упал — Traceback: читают снизу, последняя строка — тип ошибки, над ней — "
              "строка line N.")
    variants = (
        Variant("Скрипт count.py считает сумму заказов в файле — что он печатает для "
                "orders.txt? ans ЧИСЛО",
                hints=("Скрипт запускают так: python3 имя.py, а файл для него — следом через "
                       "пробел.",
                       "Без имени файла count.py упадёт: ему нечего читать.",
                       "python3 count.py orders.txt → ans ЧИСЛО"),
                solution="python3 count.py orders.txt",
                wrong=("python3 count.py", "wc -l < orders.txt"),
                alternatives=("cd не нужен: скрипт и файл лежат рядом, в этой папке",),
                key="argv"),
        Variant("Скрипт broken.py падает. С какой ошибкой и на какой строке? ans ТИП НОМЕР",
                hints=("Запусти его: python3 broken.py — он упадёт и напечатает traceback.",
                       "Traceback читают снизу: последняя строка — тип ошибки (до двоеточия), "
                       "ближайшая над кодом — File …, line N.",
                       "python3 broken.py → тип из последней строки и N из последней «line N» "
                       "→ ans ТИП N"),
                solution="python3 broken.py",
                solution_script=("t=$(python3 broken.py 2>&1 | tail -n 1 | cut -d: -f1); "
                                 "n=$(python3 broken.py 2>&1 | grep -o 'line [0-9]*' | "
                                 "tail -n 1 | cut -d' ' -f2); print -r -- \"$t $n\""),
                wrong=("python3 broken.py 2>&1 | grep -o 'line [0-9]*' | head -n 1",),
                alternatives=("python3 broken.py 2>&1 | tail -n 3 — только хвост traceback",),
                key="traceback"),
        Variant('Что напечатает python3 -c "print({a} * {b} + {k})"? ans ЧИСЛО',
                hints=("python3 -c выполняет код Python прямо из строки — запусти её.",
                       "Набери команду из задания как есть — кавычки тоже.",
                       'python3 -c "print({a} * {b} + {k})" → ans ЧИСЛО'),
                solution='python3 -c "print({a} * {b} + {k})"',
                wrong=('python3 -c "print({a} * ({b} + {k}))"',),
                alternatives=("python3, а в нём >>> {a} * {b} + {k} — то же в интерактивном "
                              "Python (выход — exit())",),
                key="dash_c"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("python3 файл.py запускает скрипт; слова после имени скрипта — его аргументы. "
               "Упал — читай traceback снизу вверх: внизу тип ошибки, над ним — где рвануло.")
    spell = "python3 файл.py АРГУМЕНТ — запуск; python3 -c 'код' — строкой; traceback — снизу"
    trap_messages = {
        "lines": "Это число строк файла, а count.py печатает сумму — запусти его: python3 "
                 "count.py orders.txt.",
        "call": "Отсюда код с ошибкой только позвали. Смотри последнюю строку «line …» — ниже неё сама "
                "ошибка.",
        "order": "Сначала умножение, потом сложение — Python считает как в математике. "
                 "Запусти команду и сдай то, что она напечатала.",
    }
    MSG_NO_ARG = ("count.py ждёт имя файла после себя: без него sys.argv[1] нет — отсюда "
                  "IndexError. python3 count.py orders.txt")
    FALLBACKS = (
        "Не то. Запусти скрипт с файлом: python3 count.py orders.txt — и сдай напечатанное.",
        "Не то. Тип — в последней строке traceback, номер — в последней «line N» над ней.",
        "Не то. Запусти команду из задания и сдай напечатанное число.",
    )

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        d = pykit.run_data(rng)
        kit.write(box / "hello.py", pykit.HELLO_PY.format(greet=d["greet"]))
        kit.write(box / "count.py", pykit.COUNT_PY)
        kit.write(box / "orders.txt", "\n".join(d["orders"]) + "\n")
        kit.write(box / "broken.py", d["broken"])
        st = {"a": d["a"], "b": d["b"], "k": d["k"]}
        if variant == 0:
            st["answer"] = d["total"]
            st["traps"] = [["lines", d["lines"]]]
            st["sources"] = sources(box, "count.py", "orders.txt")
        elif variant == 1:
            st["answer"] = f"{d['err_type']} {d['err_line']}"
            st["traps"] = [["call", f"{d['err_type']} {d['call_line']}"]]
            st["sources"] = sources(box, "broken.py")
        else:
            st["answer"] = d["expr"]
            st["traps"] = [["order", d["wrong_order"]]]
        return st

    def answer_kind(self, state: dict) -> str:
        return "text" if _v(self, state) == 1 else "number"

    _TYPE_COLON = re.compile(r"^\s*([A-Za-z_]\w*Error)\s*:\s*")

    def _norm(self, given: str, state: dict) -> str:
        """Вариант B: «NameError: 9», «NameError:9» = «NameError 9» — двоеточие после типа
        переписано из traceback (форма, не верность: так же для любого типа и числа)."""
        if given is None or _v(self, state) != 1:
            return given
        return self._TYPE_COLON.sub(r"\1 ", given, count=1)

    def matches(self, given: str, ctx) -> bool:
        return super().matches(self._norm(given, ctx.state), ctx)

    def wrong_message(self, given: str, ctx) -> str:
        v = _v(self, ctx.state)
        given = self._norm(given, ctx.state)
        trap = self.trap_message(given, ctx)
        if trap:
            return trap
        if v == 0:
            last = script_args(envkit.journal(ctx.box), "count.py")
            if last is not None and not last[0]:
                return self.MSG_NO_ARG
        return self.common_mistake(given, ctx) or self.FALLBACKS[v]


# --- 2. py_vars -----------------------------------------------------------------------------

class NumberOut(pykit.PyEditTask):
    """«Поправь скрипт», чей ответ — одно число в файле out_name (последняя строка, после «:»
    или «=»). Ловушки — точным значением (state["traps"]); больше 2 знаков после точки — совет
    про round по форме (если задача его требует: rounded); прочее — «Не то число»."""
    out_name = "total.txt"
    rounded = True
    MSG_EMPTY = "{out} пуст: допиши print и запусти скрипт снова: {run}"
    MSG_NOT_NUM = "В {out} не число. Напечатай итог: print(f\"total: {{total}}\") или print(total)."
    MSG_ROUND = "Округли до 2 знаков: round(x, 2)."
    MSG_WRONG = "Не то число. Сверь формулу с заданием — и запусти скрипт снова."
    trap_messages = {}

    def check_outputs(self, ctx) -> Verdict:
        kind, text = envkit.box_text(ctx.box, self.out_name, envkit.TEXT_CAP)
        if kind != "ok":
            return Verdict(False, envkit.file_problem(kind, self.out_name))
        value = pykit.last_value(text)
        if not value:
            return Verdict(False, self.MSG_EMPTY.format(out=self.out_name, run=self.run))
        for key, trap in ctx.state.get("traps") or ():
            if value == str(trap) and key in self.trap_messages:
                return Verdict(False, self.trap_messages[key].format(**ctx.state))
        if pykit.as_num(value) is None:
            return Verdict(False, self.MSG_NOT_NUM.format(out=self.out_name))
        if self.rounded and pykit.decimals(value) > 2:
            return Verdict(False, self.MSG_ROUND)
        if pykit.same_num(value, ctx.state["expect"]):
            return Verdict(True)
        return Verdict(False, self.MSG_WRONG)


VARS_TODO2 = "# TODO 2: напечатай f-строкой: total: …"
VARS_PRINT = 'print(f"total: {total}")'


class PyVars(NumberOut):
    """Переменные, int/float/str, f-строка, round: цена партии в total.txt."""
    id = "py_vars"
    track = "py"
    title = "Цена партии"
    par = 60
    script = "price.py"
    run = "python3 price.py > total.txt"
    outputs = ("total.txt",)
    scroll = ("Переменная: x = 12.5, имя = значение; число с точкой зовут float, целое зовут "
              "int, текст в кавычках зовут str.\n"
              "Текст в число: int(\"7\"); до 2 знаков после точки: round(x, 2).\n"
              "F-строка: print(f\"итог: {x * 2}\") подставит то, что в {}; вывод в файл: "
              "python3 файл.py > out.txt.")
    variants = (
        Variant("В price.py допиши расчёт: цена за кг × вес, до 2 знаков после точки, и "
                "печать «total: …»; итог сохрани в total.txt: python3 price.py > total.txt",
                hints=("Открой price.py: nano price.py — там две строки # TODO.",
                       py("Перемножь price и weight, округли round(…, 2), напечатай: "
                          'print(f"total: {total}")')),
                wrong=("python3 price.py > total.txt",),
                alternatives=("print(total) — тоже засчитается: в total.txt одно число",),
                key="weight"),
        Variant("Партия — {qty} шт., скидка {discount} %. Допиши price.py: сколько стоит "
                "партия со скидкой, до 2 знаков. Вывод скрипта — в total.txt: python3 "
                "price.py > total.txt",
                hints=("Открой price.py: nano price.py — там две строки # TODO.",
                       "Скидка {discount} % — это price * qty * (100 - discount) / 100; "
                       "округли round(…, 2)."),
                wrong=("python3 price.py > total.txt",),
                alternatives=("price * qty * (1 - discount / 100) — та же формула",),
                key="discount"),
        Variant("В input.txt — продажи за понедельник и вторник. Допиши price.py: сколько "
                "продано за два дня. Ответ — в total.txt: python3 price.py > total.txt",
                hints=("Открой price.py: nano price.py — там две строки # TODO.",
                       "monday и tuesday — текст из файла. Сложить их как числа: сначала "
                       "int(…) каждое."),
                wrong=("python3 price.py > total.txt",),
                alternatives=("print(f\"total: {{int(monday) + int(tuesday)}}\") — сложение "
                              "прямо в f-строке, тоже можно",),
                key="int"),
    )
    hints = variants[0].hints
    explain = ("Переменная — ярлык со значением. Из файла приходит текст, str: сперва int(), "
               "потом считай. round(x, 2) — до копеек, а f-строка вставляет значения прямо в "
               "текст.")
    spell = "имя = значение; int(\"7\") — в число; round(x, 2); print(f\"итог: {x * 2}\")"
    trap_messages = {
        "glued": "Это склеенный текст: «3» + «4» = «34». Сначала int(), потом +.",
        "unrounded": NumberOut.MSG_ROUND,
    }
    crash_tips = {
        "TypeError": "Скрипт упал с TypeError: текст и число так не складываются. Сначала "
                     "int(…) — потом считать.",
    }

    def prepare(self, box, rng, variant):
        st = pykit.vars_data(rng, variant)
        if variant == 2:
            kit.write(Path(box) / "input.txt", f"{st['monday']}\n{st['tuesday']}\n")
        return st

    def skeleton(self, state: dict) -> str:
        v = _v(self, state)
        if v == 0:
            head = ["# price.py — сколько стоит покупка на развес",
                    f"price = {state['price']}    # цена за кг",
                    f"weight = {state['weight']}    # вес, кг",
                    "",
                    "# TODO 1: total — цена × вес, до 2 знаков"]
        elif v == 1:
            head = ["# price.py — цена партии со скидкой",
                    f"price = {state['price']}    # цена за штуку",
                    f"qty = {state['qty']}    # штук",
                    f"discount = {state['discount']}    # скидка, %",
                    "",
                    "# TODO 1: total — цена × штуки минус скидка, до 2 знаков"]
        else:
            head = ["# price.py — сколько продано за два дня",
                    'lines = open("input.txt").read().split()',
                    "monday = lines[0]    # это текст (str), а не число",
                    "tuesday = lines[1]",
                    "",
                    "# TODO 1: total — сумма двух дней, числом"]
        return "\n".join(head + [VARS_TODO2]) + "\n"

    def edits(self, state: dict) -> List[Tuple[str, str]]:
        v = _v(self, state)
        first = ("total = round(price * weight, 2)", "total = round(price * qty * (100 - "
                 "discount) / 100, 2)", "total = int(monday) + int(tuesday)")[v]
        return [("# TODO 1", first), ("# TODO 2", VARS_PRINT)]


# --- 3. py_loop -----------------------------------------------------------------------------

class PyLoop(NumberOut):
    """Список, for, if, +=: сумма больше порога, число нулей, наибольшее без max()."""
    id = "py_loop"
    track = "py"
    title = "По списку"
    par = 75
    script = "loop.py"
    run = "python3 loop.py > result.txt"
    outputs = ("result.txt",)
    out_name = "result.txt"
    rounded = False
    scroll = ("Список: visits = [3, 0, 7]; повтор для каждого числа: for v in visits: — тело "
              "с отступом в 4 пробела.\n"
              "Условие: if v > 5: (знаки: > больше, >= больше или равно, == равно, одно = "
              "присвоить); прибавить: count += 1.")
    variants = (
        Variant("В loop.py допиши цикл и условие: сумма заказов больше limit, итог — в "
                "result.txt: python3 loop.py > result.txt",
                hints=("Открой loop.py: nano loop.py — две строки # TODO, тело цикла уже "
                       "есть.",
                       "Цикл и условие — как в уроке про visits, только со своими именами из "
                       "loop.py; «больше» — это > (а не >=)."),
                wrong=("python3 loop.py > result.txt",),
                alternatives=("total = sum(a for a in amounts if a > limit) — то же одной "
                              "строкой",),
                key="sum"),
        Variant("Сколько дней в sales без продаж (нулей)? Допиши loop.py — ответ в "
                "result.txt.",
                hints=("Открой loop.py: nano loop.py — две строки # TODO.",
                       "Пройди циклом по sales; «равно» в условии — два знака ==, одно = — "
                       "это присвоить."),
                wrong=("python3 loop.py > result.txt",),
                alternatives=("print(sales.count(0)) — готовый подсчёт у списка",),
                key="zeros"),
        Variant("Найди самый крупный заказ без max(): допиши цикл в loop.py, ответ — в "
                "result.txt.",
                hints=("Открой loop.py: nano loop.py — две строки # TODO.",
                       "Иди циклом по amounts и запоминай в best то, что больше best."),
                wrong=("python3 loop.py > result.txt",),
                alternatives=("print(max(amounts)) — тоже засчитается: проверяется "
                              "result.txt",),
                key="max"),
    )
    hints = variants[0].hints
    explain = ("for перебирает список по одному, if решает, что делать с каждым. Тело "
               "цикла — всё, что сдвинуто на 4 пробела под for; сдвинул иначе — уже не внутри.")
    spell = "for x in xs: — по списку; if x > n: — условие; n += 1 — прибавить"
    trap_messages = {
        "ge": "Значение ровно {limit} попало: «больше» — это >, а >= — «больше или равно».",
        "nonzero": "Это дни С продажами: условие «равно нулю» — == 0.",
        "min": "Это наименьшее: знак смотрит не туда — нужно a > best.",
        "first": "Это первое число списка: best так и не поменялся — проверь цикл и условие.",
    }
    MSG_WRONG = "Не то число. Проверь цикл и условие — и запусти скрипт снова."
    crash_tips = {
        "IndentationError": "Скрипт упал с IndentationError: в Python отступы — часть кода. "
                            "Внутри for — 4 пробела, внутри if — ещё 4.",
        "SyntaxError": "Скрипт упал с SyntaxError: в конце строки for и if — двоеточие, "
                       "сравнение — ==, а одно = — присвоить.",
    }

    def prepare(self, box, rng, variant):
        return pykit.loop_data(rng, variant)

    def skeleton(self, state: dict) -> str:
        v = _v(self, state)
        nums = ", ".join(str(a) for a in state["amounts"])
        if v == 0:
            lines = ["# loop.py — сумма крупных заказов", f"amounts = [{nums}]",
                     f"limit = {state['limit']}", "total = 0",
                     "# TODO 1: цикл по amounts — каждое число в a",
                     "    # TODO 2: условие: a больше limit", "        total += a",
                     "print(total)"]
        elif v == 1:
            lines = ["# loop.py — сколько дней без продаж", f"sales = [{nums}]", "zeros = 0",
                     "# TODO 1: цикл по sales — каждое число в s",
                     "    # TODO 2: условие: s равно нулю", "        zeros += 1",
                     "print(zeros)"]
        else:
            lines = ["# loop.py — самый крупный заказ (без max)", f"amounts = [{nums}]",
                     "best = amounts[0]",
                     "# TODO 1: цикл по amounts — каждое число в a",
                     "    # TODO 2: условие: a больше best", "        best = a",
                     "print(best)"]
        return "\n".join(lines) + "\n"

    def edits(self, state: dict) -> List[Tuple[str, str]]:
        cond = ("if a > limit:", "if s == 0:", "if a > best:")
        loop = ("for a in amounts:", "for s in sales:", "for a in amounts:")
        v = _v(self, state)
        return [("# TODO 1", loop[v]), ("# TODO 2", cond[v])]


# --- 4. py_dict -----------------------------------------------------------------------------

def _q(name: str) -> str:
    return f'"{name}"'


class PyDict(pykit.PyEditTask):
    """Словарь, d[k], d.get(k, 0), sorted: штуки по товарам, суммы по категориям, стоимость по
    справочнику."""
    id = "py_dict"
    track = "py"
    title = "Счёт по словарю"
    par = 75
    script = "tally.py"
    run = "python3 tally.py > tally.txt"
    outputs = ("tally.txt",)
    scroll = ("Словарь: d = {}, ключ → значение; записать: d[k] = 3, прочитать: d[k], а ключа "
              "нет — KeyError.\n"
              "Значение или 0, если ключа нет: d.get(k, 0); ключи по алфавиту: sorted(d); "
              "пары: for k, v in d.items():")
    variants = (
        Variant("Сколько штук каждого товара в buys? Допиши tally.py — строки товар=число в "
                "tally.txt: python3 tally.py > tally.txt",
                hints=("Открой tally.py: nano tally.py — одна строка # TODO внутри цикла.",
                       "Ключа сначала нет: возьми значение через get с умолчанием 0 — и "
                       "прибавь к нему."),
                wrong=("python3 tally.py > tally.txt",),
                alternatives=("from collections import Counter; Counter(buys) — то же "
                              "готовым счётчиком",),
                key="count"),
        Variant("Сумма продаж по каждой категории: допиши tally.py, вывод — в tally.txt.",
                hints=("Открой tally.py: nano tally.py — одна строка # TODO внутри цикла.",
                       "Сумма до этой продажи — через get с умолчанием 0 (ключа может ещё не "
                       "быть); прибавь к ней продажу."),
                wrong=("python3 tally.py > tally.txt",),
                alternatives=("if cat not in sums: sums[cat] = 0 — и потом += amount",),
                key="sum"),
        Variant("Во что обошёлся каждый товар из buys? Цены — в справочнике prices, но там "
                "есть не всё: чего нет — считай 0. Итог — в tally.txt.",
                hints=("Открой tally.py: nano tally.py — одна строка # TODO внутри цикла.",
                       "Нет ключа — get с умолчанием 0: и для цены из prices, и для того, что "
                       "уже накоплено в cost."),
                wrong=("python3 tally.py > tally.txt",),
                alternatives=("if item in prices: … — проверка ключа до чтения",),
                key="lookup"),
    )
    hints = variants[0].hints
    explain = ("Словарь — ярлыки и значения. Ключа ещё нет — d[k] падает с KeyError, а "
               "d.get(k, 0) спокойно вернёт 0: от него и копят.")
    spell = "d.get(k, 0) — значение или 0; d[k] = d.get(k, 0) + 1 — подсчёт"
    trap_messages = {
        "overwrite_a": "Каждый раз ставишь заново: прибавляй к тому, что было — "
                       "counts.get(item, 0) + 1.",
        "overwrite_b": "Сумма затирается последней продажей: прибавляй к тому, что было — "
                       "sums.get(cat, 0) + amount.",
        "overwrite_c": "Цена затирается: товар брали не раз — прибавляй к тому, что было: "
                       "cost.get(item, 0) + цена.",
    }
    crash_tips = {
        "KeyError": "Скрипт упал с KeyError: такого ключа в словаре ещё нет. d.get(k, 0) "
                    "вернёт 0 вместо ошибки: d.get(k, 0) + 1.",
    }
    MSG_EMPTY = "tally.txt пуст: допиши строку # TODO и запусти: python3 tally.py > tally.txt"
    MSG_FORM = "Строки в tally.txt — вида товар=число, по одной на ключ. Печать уже есть в tally.py."
    MSG_EXTRA = "В tally.txt есть ключи, которых нет в данных скрипта. Запусти tally.py заново."
    MSG_PARTIAL = "Есть {n} из {m}: что есть — верно, но ключей не хватает."
    MSG_WRONG = "Не те числа. Проверь строку # TODO: копить надо к тому, что уже было."

    def prepare(self, box, rng, variant):
        return pykit.dict_data(rng, variant)

    def skeleton(self, state: dict) -> str:
        v = _v(self, state)
        if v == 0:
            buys = ", ".join(_q(x) for x in state["buys"])
            lines = ["# tally.py — сколько штук каждого товара", f"buys = [{buys}]",
                     "counts = {}", "for item in buys:",
                     "    # TODO 1: counts[item] — на 1 больше, чем было (сначала 0)",
                     "for name in sorted(counts):", '    print(f"{name}={counts[name]}")']
        elif v == 1:
            rows = ", ".join(f"({_q(c)}, {a})" for c, a in state["rows"])
            lines = ["# tally.py — сумма продаж по категориям",
                     f"sales = [{rows}]", "sums = {}", "for cat, amount in sales:",
                     "    # TODO 1: sums[cat] — прибавь amount (сначала 0)",
                     "for name in sorted(sums):", '    print(f"{name}={sums[name]}")']
        else:
            prices = ", ".join(f"{_q(k)}: {p}" for k, p in state["prices"].items())
            buys = ", ".join(_q(x) for x in state["buys"])
            lines = ["# tally.py — во что обошёлся каждый товар",
                     f"prices = {{{prices}}}    # справочник цен",
                     f"buys = [{buys}]    # есть и товары не из справочника", "cost = {}",
                     "for item in buys:",
                     "    # TODO 1: cost[item] — прибавь цену из prices (нет в справочнике — 0)",
                     "for name in sorted(cost):", '    print(f"{name}={cost[name]}")']
        return "\n".join(lines) + "\n"

    def edits(self, state: dict) -> List[Tuple[str, str]]:
        return [("# TODO 1", ("counts[item] = counts.get(item, 0) + 1",
                              "sums[cat] = sums.get(cat, 0) + amount",
                              "cost[item] = cost.get(item, 0) + prices.get(item, 0)",
                              )[_v(self, state)])]

    @staticmethod
    def _same(got: dict, want: dict) -> bool:
        return set(got) == set(want) and all(pykit.same_num(got[k], want[k]) for k in want)

    def check_outputs(self, ctx) -> Verdict:
        kind, text = envkit.box_text(ctx.box, "tally.txt", envkit.TEXT_CAP)
        if kind != "ok":
            return Verdict(False, envkit.file_problem(kind, "tally.txt"))
        got, bad = pykit.pairs(text)
        if not got and not bad:
            return Verdict(False, self.MSG_EMPTY)
        if bad or any(pykit.as_num(x) is None for x in got.values()):
            return Verdict(False, self.MSG_FORM)
        want = {str(k): v for k, v in ctx.state["expect"].items()}
        if self._same(got, want):
            return Verdict(True)
        for key, trap in ctx.state.get("traps") or ():
            if key in self.trap_messages and self._same(got, trap):
                return Verdict(False, self.trap_messages[key])
        if set(got) - set(want):
            return Verdict(False, self.MSG_EXTRA)
        if all(pykit.same_num(got[k], want[k]) for k in got):
            return Verdict(False, self.MSG_PARTIAL.format(n=len(got), m=len(want)))
        return Verdict(False, self.MSG_WRONG)


# --- 5. py_func -----------------------------------------------------------------------------

MYLIB_HEAD = '"""mylib — общие расчёты для отчётов: report.py зовёт их через import mylib."""'
MYLIB_TAIL = ["", "", "# дальше — другие функции отчётов"]


class PyFunc(pykit.PyEditTask):
    """def, return, import своего файла, вызов mylib.f(): комиссия по заказам."""
    id = "py_func"
    track = "py"
    title = "Своя библиотека"
    par = 90
    script = "mylib.py"
    run = "python3 report.py > fees.txt"
    reads_py = True     # сверка байтов report.py (fix1 M1): задача скрытая, вердикт судьи (P003)
    outputs = ("fees.txt",)
    scroll = ("Своя функция: def share(x, n): (x и n — параметры: то, что функция получает на вход), тело с отступом, а вернуть результат: return "
              "x / n; если только печатать print, вернётся None.\n"
              "Свой файл рядом: import shelf подключит shelf.py из той же папки; вызов: "
              "shelf.share(9, 3).")
    variants = (
        Variant("report.py считает комиссию по заказам через import mylib, а функции fee в "
                "mylib.py ещё нет — допиши её; отчёт — в fees.txt: python3 report.py > "
                "fees.txt",
                hints=("Открой mylib.py: nano mylib.py — там строка # TODO; report.py не "
                       "трогай.",
                       "def fee(amount): и на следующей строке, с отступом, return — "
                       "комиссия RATE % с суммы, round(…, 2)."),
                wrong=("python3 report.py > fees.txt",),
                alternatives=("return amount * RATE / 100 без round — тоже засчитается: "
                              "числа сверяются с допуском",),
                key="one"),
        Variant("У каждого заказа своя ставка: report.py зовёт mylib.fee(amount, rate). Допиши "
                "fee с двумя параметрами (входными значениями) в mylib.py — отчёт в fees.txt.",
                hints=("Открой mylib.py: nano mylib.py — там строка # TODO.",
                       "def fee(amount, rate): — два параметра через запятую; return — "
                       "комиссия rate % с суммы, round(…, 2)."),
                wrong=("python3 report.py > fees.txt",),
                alternatives=("return round(amount * rate * 0.01, 2) — то же",),
                key="two"),
        Variant("fee в mylib.py уже есть. Допиши total_fee(amounts): сумма fee по всем заказам "
                "— report.py печатает её в fees.txt.",
                hints=("Открой mylib.py: nano mylib.py — fee готова, ниже строка # TODO.",
                       "В total_fee копи s += fee(a) в цикле по amounts и верни round(s, 2)."),
                wrong=("python3 report.py > fees.txt",),
                alternatives=("return round(sum(fee(a) for a in amounts), 2) — то же одной "
                              "строкой",),
                key="loop"),
    )
    hints = variants[0].hints
    explain = ("Функция — расчёт с именем: def его заводит, return отдаёт результат. Свой файл "
               ".py рядом со скриптом — уже библиотека (готовый код для import): import mylib, и дальше "
               "mylib.fee().")
    spell = "def f(x): return x * 2 — функция; import mylib — свой файл рядом; mylib.f(1)"
    trap_messages = {
        "percent": "Процент — это доля из 100: amount * rate / 100.",
        "no_fee": "Это сумма самих заказов: в цикле зови fee(a) и копи её результат.",
    }
    MSG_MYLIB = ("import ищет файл mylib.py рядом со скриптом: имя — ровно mylib.py, в той "
                 "же папке, что report.py.")
    MSG_REPORT = ("report.py изменён, а править нужно только mylib.py: расчёт — в функции. "
                  "Набери reset — report.py вернётся.")
    MSG_PRINT = ("В fees.txt лишние строки без «=» — это print внутри функции. Оставь в ней "
                 "только return.")
    crash_tips = {
        "TypeError": "Скрипт упал с TypeError: сколько значений report.py передаёт в fee — "
                     "столько параметров и пиши в def.",
        "IndentationError": "Скрипт упал с IndentationError: тело функции — с отступом в 4 "
                            "пробела под строкой def.",
        "AttributeError": "Скрипт упал с AttributeError: report.py зовёт из mylib функцию, "
                          "которой там нет. Имя после def — ровно как в вызове (смотри "
                          "последнюю строку traceback).",
    }
    MSG_NONE = ("В fees.txt — None: функция печатает, но не возвращает. Вместо print — "
                "return.")
    MSG_EMPTY = "fees.txt пуст: допиши функцию в mylib.py и запусти: python3 report.py > fees.txt"
    MSG_FORM = "Строки fees.txt печатает report.py — не правь его, допиши только mylib.py."
    MSG_WRONG = "Не те числа. Сверь формулу с заданием: комиссия — процент от суммы."

    def prepare(self, box, rng, variant):
        st = pykit.func_data(rng, variant)
        kit.write(Path(box) / "report.py", self.report(st, variant))
        # report.py не правят (fix1 M1): сверка байтов, а не разбор кода — родитель его не
        # читает как программу; расчёт прямо в report.py (без def/return) не засчитывается
        st["report_sha"] = kit.sha(Path(box) / "report.py")
        return st

    @staticmethod
    def report(st: dict, v: int) -> str:
        if v == 1:
            rows = ", ".join(f"({a}, {r})" for a, r in st["orders"])
            body = [f"orders = [{rows}]    # (сумма, ставка %)", "for a, r in orders:",
                    '    print(f"{a}={mylib.fee(a, r)}")']
        else:
            body = [f"amounts = {st['amounts']}"]
            body += (['print(f"total={mylib.total_fee(amounts)}")'] if v == 2 else
                     ["for a in amounts:", '    print(f"{a}={mylib.fee(a)}")'])
        head = ["# report.py — комиссия по заказам (не правь: функции — в mylib.py)",
                "import mylib", ""]
        return "\n".join(head + body) + "\n"

    def skeleton(self, state: dict) -> str:
        v = _v(self, state)
        rate = [f"RATE = {state.get('rate')}    # комиссия, %"] if v != 1 else []
        if v == 0:
            mid = ["", "", "# TODO 1: функция fee(amount) — комиссия RATE % с суммы, до 2 "
                   "знаков"]
        elif v == 1:
            mid = ["", "", "# TODO 1: функция fee(amount, rate) — комиссия rate % с суммы, "
                   "до 2 знаков"]
        else:
            mid = ["", "", "def fee(amount):", "    return round(amount * RATE / 100, 2)",
                   "", "", "# TODO 1: функция total_fee(amounts) — сумма fee(a) по всем, до 2 "
                   "знаков"]
        return "\n".join([MYLIB_HEAD] + rate + mid + MYLIB_TAIL) + "\n"

    def edits(self, state: dict) -> List[Tuple[str, str]]:
        return [("# TODO 1", (
            "def fee(amount):\n    return round(amount * RATE / 100, 2)",
            "def fee(amount, rate):\n    return round(amount * rate / 100, 2)",
            "def total_fee(amounts):\n    s = 0\n    for a in amounts:\n        s += fee(a)\n"
            "    return round(s, 2)",
        )[_v(self, state)])]

    def crash_message(self, ctx):
        """Пропал mylib.py — совет про import; ModuleNotFoundError при mylib.py на месте (чужой
        модуль в import, fix1 M2) — общий отклик с типом, а не совет про .venv."""
        msg = super().crash_message(ctx)
        if msg and envkit.box_file(ctx.box, "mylib.py")[0] == "missing":
            return self.MSG_MYLIB
        if msg == pykit.MSG_MODULE:
            return pykit.MSG_TRACEBACK_TYPE.format(typ="ModuleNotFoundError")
        return msg

    def check(self, ctx) -> Verdict:
        if kit.sha_in_box(ctx.box, "report.py") != ctx.state.get("report_sha"):
            return Verdict(False, self.MSG_REPORT)
        return super().check(ctx)

    def check_outputs(self, ctx) -> Verdict:
        kind, text = envkit.box_text(ctx.box, "fees.txt", envkit.TEXT_CAP)
        if kind != "ok":
            return Verdict(False, envkit.file_problem(kind, "fees.txt"))
        got, bad = pykit.pairs(text)
        if not got and not bad:
            return Verdict(False, self.MSG_EMPTY)
        if any(x == "None" for x in got.values()):
            return Verdict(False, self.MSG_NONE)
        if bad and all(pykit.as_num(x) is not None or x == "None" for x in bad):
            return Verdict(False, self.MSG_PRINT)       # голые числа — print в функции (M6)
        if bad or any(pykit.as_num(x) is None for x in got.values()):
            return Verdict(False, self.MSG_FORM)
        want = ctx.state["expect"]
        if PyDict._same(got, want):
            return Verdict(True)
        for key, trap in ctx.state.get("traps") or ():
            if key in self.trap_messages and PyDict._same(got, trap):
                return Verdict(False, self.trap_messages[key])
        if set(got) != set(want):
            return Verdict(False, self.MSG_FORM)
        return Verdict(False, self.MSG_WRONG)


# --- 6. py_repl -----------------------------------------------------------------------------

class PyRepl(AnswerTask):
    """REPL (>>>, exit()/Ctrl+D), help(), dir(), python3 -c в конвейере: учебные пакеты в
    .venv и items.json."""
    id = "py_repl"
    track = "py"
    title = "Живой Python"
    par = 75
    pinned_python = True
    stock = "light"
    scroll = ("Живой Python: python3 без файла; >>> ждёт строку кода, ... — продолжение, Enter "
              "на пустой строке его закончит.\n"
              "Команды игры — ans, hint — внутри >>> не работают: сначала exit() или Ctrl+D.\n"
              "Имена внутри модуля: dir(x); справка: help(x), выход из неё — q.")
    variants = (
        Variant("В .venv стоит пакет {mod} — сколько в нём {ask}? Смотри dir(). ans ЧИСЛО",
                hints=("Включи окружение: source .venv/bin/activate, затем python3 — "
                       "появится >>>.",
                       ">>> import {mod}, потом >>> dir({mod}) — считай имена {which}; "
                       "выход — exit().",
                       "source .venv/bin/activate && python3 -c 'import {mod}; "
                       "print(dir({mod}))' → сосчитай имена {which} → ans ЧИСЛО"),
                solution="source .venv/bin/activate && python3 -c 'import {mod}; "
                         "print(dir({mod}))'",
                # имена — по одному в строке силами оболочки: sep= в print ещё не учили
                solution_script=(".venv/bin/python -c 'import {mod}; print(dir({mod}))' | "
                                 "tr -d \"[]' \" | tr , \"\\n\" | grep {grep}"),
                wrong=(".venv/bin/python -c 'import {mod}; print(len(dir({mod})))'",),
                alternatives=("python3 из .venv: >>> import {mod}; >>> dir({mod}) — то же "
                              "в живом Python",),
                key="dir"),
        Variant("Как называется {nth} параметр функции {mod}.{fn} (первый — {first})? "
                "Подсмотри в help(). Пакет — в .venv. ans ИМЯ",
                hints=("Включи окружение: source .venv/bin/activate, затем python3.",
                       ">>> import {mod}, потом >>> help({mod}.{fn}) — в первой строке "
                       "параметры по порядку; выход из справки — q.",
                       "source .venv/bin/activate && python3 -c 'import {mod}; "
                       "help({mod}.{fn})' → {nth} параметр по порядку → ans ИМЯ"),
                solution="source .venv/bin/activate && python3 -c 'import {mod}; "
                         "help({mod}.{fn})'",
                solution_script=(".venv/bin/python -c 'import {mod}; help({mod}.{fn})' | "
                                 "grep -m 1 '^{fn}(' | cut -d'(' -f2 | tr -d ' ' | "
                                 "cut -d, -f{pos} | cut -d= -f1"),
                wrong=("print -r -- {first}",),
                alternatives=("cat .venv/lib/python3*/site-packages/{mod}/__init__.py — "
                              "подпись def в исходнике",),
                key="help"),
        Variant("Сколько записей в списке items файла items.json? Посчитай Python в "
                "конвейере: cat … | python3 -c '…' — там json.load(sys.stdin) читает JSON, "
                "пришедший по |, а len(x) — длина списка. ans ЧИСЛО",
                hints=("Код в конвейере: cat items.json | python3 -c 'import json, sys; …'.",
                       "Список лежит по ключу \"items\": json.load(sys.stdin)[\"items\"].",
                       "cat items.json | python3 -c 'import json, sys; "
                       "print(len(json.load(sys.stdin)[\"items\"]))' → ans ЧИСЛО"),
                solution="cat items.json | python3 -c 'import json, sys; "
                         "print(len(json.load(sys.stdin)[\"items\"]))'",
                wrong=("wc -l < items.json",),
                alternatives=("jq '.items | length' items.json — то же через jq",),
                key="pipe"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("python3 без файла — живой Python: набрал строку — сразу видишь ответ. dir() "
               "покажет, что лежит в модуле, help() — как с этим работать.")
    spell = "python3 — >>>; exit() или Ctrl+D — выход; dir(x), help(x); python3 -c 'код'"
    trap_messages = {
        "underscore": "С подчёркиванием — служебные, их не считай: только имена без _ в "
                      "начале.",
        "first": "Это первый параметр — он есть в задании. Нужен {nth} по порядку.",
        "neighbor": "Это соседний параметр. Считай с первого, по порядку: нужен {nth}.",
        "dunder": "Сюда попали и __служебные__ (два подчёркивания). Нужны имена ровно с одним "
                  "_ в начале.",
        "public": "Это имена без _ в начале, а спрашивают про имена с одним _.",
        "default": "Это значение по умолчанию (после =), а нужно имя параметра — до =.",
        "lines": "Это строки файла, а нужно число записей в items — длина списка: len(…).",
    }
    FALLBACKS = (
        "Не то. В >>>: import, затем dir(…) — и считай только нужные имена, по одному.",
        "Не то. В help(…) первая строка — подпись: параметры в скобках по порядку.",
        "Не то. Длина списка по ключу items: len(json.load(sys.stdin)[\"items\"]).",
    )

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        kit.venv_from_stock(box, "light", ".venv")
        d = pykit.repl_data(rng, variant)
        if variant == 2:
            kit.write(box / "items.json", d.pop("json"))
            d["sources"] = sources(box, "items.json")
        return d

    def answer_kind(self, state: dict) -> str:
        return "text" if _v(self, state) == 1 else "number"

    def wrong_message(self, given: str, ctx) -> str:
        return (self.trap_message(given, ctx) or self.common_mistake(given, ctx)
                or self.FALLBACKS[_v(self, ctx.state)])


# --- 7. py_json -----------------------------------------------------------------------------

class PyJson(pykit.PyEditTask):
    """json.load, вложенный доступ d["a"][0]["b"], фильтр, json.dump(indent=2,
    ensure_ascii=False): заказы словарь → список → словарь."""
    id = "py_json"
    track = "py"
    title = "Вглубь JSON"
    par = 90
    script = "orders.py"
    run = "python3 orders.py"
    OUT = ("paid.json", "totals.json", "renamed.json")
    scroll = ("Прочесть JSON: with open(\"a.json\") as f: — открыть; shelf = json.load(f) — "
              "словари и списки.\n"
              "Вглубь — по шагам: shelf[\"books\"][0][\"title\"] — ключ, номер в списке, ключ.\n"
              "Записать: with open(\"b.json\", \"w\") as f: — и в нём json.dump(x, f, indent=2, "
              "ensure_ascii=False) — с отступами, кириллица буквами.")
    variants = (
        Variant("В orders.json — заказы магазина; допиши orders.py: только оплаченные, со "
                "статусом paid, — списком в paid.json, с отступом 2 и кириллицей как есть; "
                "запуск — python3 orders.py",
                hints=("Открой orders.py: nano orders.py — две строки # TODO.",
                       "Условие — if и сравнение ==, как в цикле по списку; запись — json.dump "
                       "с indent=2 и ensure_ascii=False."),
                wrong=("python3 orders.py",),
                alternatives=("paid = [o for o in data[\"orders\"] if o[\"status\"] == "
                              "\"paid\"] — тот же фильтр одной строкой",),
                key="filter"),
        Variant("Сколько стоит каждый заказ из orders.json? Допиши orders.py: сумма цена × "
                "количество по позициям заказа — в totals.json, ключ — id заказа.",
                hints=("Открой orders.py: nano orders.py — две строки # TODO.",
                       "Позиции заказа — order[\"items\"], у каждой price и qty; копи "
                       "price * qty в s; запись — json.dump с indent=2."),
                wrong=("python3 orders.py",),
                alternatives=("sum(i[\"price\"] * i[\"qty\"] for i in order[\"items\"]) — "
                              "сумма одной строкой",),
                key="nested"),
        Variant("В каждом заказе orders.json ключ cust надо переименовать в customer — весь "
                "документ сохрани в renamed.json (отступ 2, кириллица как есть). del d[k] "
                "убирает ключ из словаря.",
                hints=("Открой orders.py: nano orders.py — три строки # TODO.",
                       "Новый ключ — то же значение, что у старого; старый — del; запись — "
                       "json.dump с indent=2 и ensure_ascii=False."),
                wrong=("python3 orders.py",),
                alternatives=("order[\"customer\"] = order.pop(\"cust\") — перенос одной "
                              "строкой",),
                key="rename"),
    )
    hints = variants[0].hints
    explain = ("JSON в Python — это словари и списки: json.load читает, а вглубь идёшь по "
               "шагам [ключ][номер][ключ]. json.dump пишет обратно; indent=2 — чтобы читалось "
               "глазами, ensure_ascii=False — кириллица буквами, а не кодами.")
    spell = "json.load(f); d[\"a\"][0][\"b\"]; json.dump(x, f, indent=2, ensure_ascii=False)"
    trap_messages = {
        "all": "Здесь все заказы, а нужны только оплаченные: условие status == \"paid\".",
        "unpaid": "Это неоплаченные: условие наоборот — нужен status == \"paid\".",
        "price_only": "Цена без количества: позиция стоит price * qty.",
        "both": "Старый ключ cust остался: после копии убери его — del order[\"cust\"].",
    }
    MSG_PARTIAL = "Есть {n} из {m}: что есть — верно, но заказов не хватает."
    MSG_WRONG = "Не те данные. Сверь условие и ключи с orders.json — и запусти скрипт снова."
    crash_tips = {
        "KeyError": "Скрипт упал с KeyError: такого ключа нет. Сверь имена ключей с "
                    "orders.json: cat orders.json.",
        "IndentationError": "Скрипт упал с IndentationError: строка под for, if и with — с "
                            "отступом в 4 пробела.",
    }

    def prepare(self, box, rng, variant):
        st = pykit.json_data(rng, variant)
        kit.write(Path(box) / "orders.json", st.pop("json"))
        return st

    def outputs_for(self, state: dict) -> List[str]:
        return [self.OUT[_v(self, state)]]

    def skeleton(self, state: dict) -> str:
        v = _v(self, state)
        head = ["import json", "", 'with open("orders.json") as f:', "    data = json.load(f)"]
        if v == 0:
            lines = (["# orders.py — оплаченные заказы из orders.json в paid.json"] + head +
                     ["paid = []", 'for order in data["orders"]:',
                      '    # TODO 1: условие — status заказа равен "paid"',
                      "        paid.append(order)", 'with open("paid.json", "w") as f:',
                      "    # TODO 2: запиши paid — с отступом 2 и кириллицей как есть"])
        elif v == 1:
            lines = (["# orders.py — сумма каждого заказа в totals.json"] + head +
                     ["totals = {}", 'for order in data["orders"]:', "    s = 0",
                      '    for item in order["items"]:',
                      "        # TODO 1: s — прибавь цену × количество этой позиции",
                      '    totals[order["id"]] = s', 'with open("totals.json", "w") as f:',
                      "    # TODO 2: запиши totals — с отступом 2"])
        else:
            lines = (["# orders.py — в каждом заказе ключ cust → customer, итог в renamed.json"]
                     + head +
                     ['for order in data["orders"]:',
                      '    # TODO 1: order["customer"] — то же значение, что у order["cust"]',
                      "    # TODO 2: старый ключ cust — убрать (del)",
                      'with open("renamed.json", "w") as f:',
                      "    # TODO 3: запиши data — с отступом 2 и кириллицей как есть"])
        return "\n".join(lines) + "\n"

    def edits(self, state: dict) -> List[Tuple[str, str]]:
        v = _v(self, state)
        if v == 0:
            return [("# TODO 1", 'if order["status"] == "paid":'),
                    ("# TODO 2", "json.dump(paid, f, indent=2, ensure_ascii=False)")]
        if v == 1:
            return [("# TODO 1", 's += item["price"] * item["qty"]'),
                    ("# TODO 2", "json.dump(totals, f, indent=2)")]
        return [("# TODO 1", 'order["customer"] = order["cust"]'),
                ("# TODO 2", 'del order["cust"]'),
                ("# TODO 3", "json.dump(data, f, indent=2, ensure_ascii=False)")]

    def check_outputs(self, ctx) -> Verdict:
        st = ctx.state
        out = self.outputs_for(st)[0]
        doc, msg, text = pykit.read_json(ctx.box, out, self.run)
        if msg:
            return Verdict(False, msg)
        want = st["expect"]
        if doc == want:
            form = pykit.json_form(text, out, cyrillic=_v(self, st) != 1)
            return Verdict(form is None, form)
        for key, trap in st.get("traps") or ():
            if doc == trap and key in self.trap_messages:
                return Verdict(False, self.trap_messages[key])
        if (isinstance(doc, list) and isinstance(want, list) and doc
                and len(doc) < len(want) and all(x in want for x in doc)):
            return Verdict(False, self.MSG_PARTIAL.format(n=len(doc), m=len(want)))
        return Verdict(False, self.MSG_WRONG)


# --- 8. py_csv_json -------------------------------------------------------------------------

def _same_cell(got, want: str) -> bool:
    """Ячейка: текст как есть, число — как число («120» = 120 = 120.0)."""
    if isinstance(got, str) and got == want:
        return True
    if isinstance(got, (int, float)) and not isinstance(got, bool):
        return pykit.same_num(got, want) if pykit.as_num(want) is not None else False
    return False


def _same_records(doc, want: List[dict]) -> bool:
    return (isinstance(doc, list) and len(doc) == len(want)
            and all(isinstance(d, dict) and set(d) == set(w)
                    and all(_same_cell(d[k], w[k]) for k in w) for d, w in zip(doc, want)))


def _csv_cell(got: str, want: str) -> bool:
    """Ячейка CSV: текст как есть, число — как число («72.0» = «72», правило 3)."""
    if got == want:
        return True
    return (pykit.as_num(want) is not None and pykit.as_num(got) is not None
            and pykit.same_num(got, want))


def _same_csv(rows, want) -> bool:
    return (isinstance(rows, list) and len(rows) == len(want)
            and all(len(g) == len(w) and all(_csv_cell(a, b) for a, b in zip(g, w))
                    for g, w in zip(rows, want)))


def _cut_quotes(doc) -> bool:
    """Форма разрезанного поля (M3 ревью Q3): у какого-то значения кавычка на краю — «"tea» или
    « green"». DictReader кавычки снимает, так бывает, только если строку резали по запятой.
    Смотрит только вид файла, не ответ."""
    items = doc if isinstance(doc, list) else []
    for item in items[:pykit.CSV_ROWS_CAP]:
        cells = item.values() if isinstance(item, dict) else item if isinstance(item, list) else ()
        for x in cells:
            if isinstance(x, str) and x.strip() and (x.strip()[0] == '"' or x.strip()[-1] == '"'):
                return True
    return False


class PyCsvJson(pykit.PyEditTask):
    """csv.DictReader, csv.DictWriter, newline="", writeheader: CSV ↔ JSON, новая колонка;
    поле с запятой в кавычках (split по запятой его режет)."""
    id = "py_csv_json"
    track = "py"
    title = "CSV и JSON"
    par = 90
    script = "convert.py"
    run = "python3 convert.py"
    OUT = ("sales.json", "stock.csv", "sales2.csv")
    scroll = ("CSV словарями: with open(\"t.csv\", newline=\"\") as f: и for row in "
              "csv.DictReader(f): — строка как словарь по шапке.\n"
              "Поле в кавычках «\"a, b\"» DictReader прочтёт целым, а резать строку по запятой "
              "руками — сломать.\n"
              "Запись: w = csv.DictWriter(f, fieldnames=[\"a\", \"b\"]); w.writeheader() — "
              "шапка, потом строки.")
    variants = (
        Variant("Продажи — в sales.csv; допиши convert.py: каждая строка — словарь по шапке, "
                "весь список — в sales.json; запуск — python3 convert.py",
                hints=("Открой convert.py: nano convert.py — одна строка # TODO.",
                       "Читатель, что отдаёт строки словарями по шапке, — csv.DictReader; "
                       "запятую в кавычках он не режет."),
                wrong=("python3 convert.py",),
                alternatives=("rows = list(csv.DictReader(f)) — весь файл одним списком",),
                key="reader"),
        Variant("Остатки — в stock.json. Допиши convert.py: тот же список — в stock.csv, с "
                "шапкой name,city,qty. Все строки разом пишет w.writerows(rows).",
                hints=("Открой convert.py: nano convert.py — две строки # TODO.",
                       "Писатель w уже есть: сначала шапка, потом все строки — у DictWriter "
                       "на это два метода."),
                wrong=("python3 convert.py",),
                alternatives=("for r in rows: w.writerow(r) — те же строки по одной",),
                key="writer"),
        Variant("Допиши convert.py: sales.csv с новой колонкой total — цена × количество — "
                "в sales2.csv. Числа из CSV приходят текстом.",
                hints=("Открой convert.py: nano convert.py — одна строка # TODO.",
                       "price и qty — текст: сначала int(…) каждое, потом умножай."),
                wrong=("python3 convert.py",),
                alternatives=("row[\"total\"] = str(int(row[\"price\"]) * int(row[\"qty\"])) — "
                              "то же, текстом",),
                key="column"),
    )
    hints = variants[0].hints
    explain = ("csv.DictReader читает строки словарями по шапке и понимает кавычки — поле "
               "«a, b» он не разрежет. csv.DictWriter пишет обратно: writeheader — шапка, потом "
               "строки. newline=\"\" — пусть модуль csv сам решает, где кончается строка.")
    spell = "csv.DictReader(f); w = csv.DictWriter(f, fieldnames=[…]); w.writeheader()"
    trap_messages = {
        "split": "Поле с запятой в кавычках разрезано: строку резали по запятой. Читай "
                 "csv.DictReader — он кавычки понимает.",
        "no_header": "Шапки нет: перед строками — w.writeheader().",
        "repeat": "В total — текст, повторённый qty раз: «12» * 3 = «121212». Сначала "
                  "int(…), потом умножай.",
    }
    MSG_PARTIAL = "Есть {n} из {m}: что есть — верно, но строк не хватает."
    MSG_WRONG = "Не те данные. Сверь с исходным файлом и шапкой — и запусти скрипт снова."
    MSG_HEAD = "Шапка не та: нужна {head} — как в fieldnames."
    MSG_NO_ROWS = "Шапка есть, а строк нет: 0 из {m}."
    crash_tips = {
        "NameError": "Скрипт упал с NameError: имя ещё не задано. Строка # TODO должна его "
                     "создать — например, reader = …",
        "TypeError": "Скрипт упал с TypeError: текст на число множится совсем не так, "
                     "как ты ждёшь — сначала int(…).",
    }

    def prepare(self, box, rng, variant):
        import json
        st = pykit.csv_data(rng, variant)
        if variant == 1:
            kit.write(Path(box) / "stock.json",
                      json.dumps(st.pop("recs"), indent=2, ensure_ascii=False) + "\n")
        else:
            kit.write(Path(box) / "sales.csv", st.pop("file"))
        return st

    def outputs_for(self, state: dict) -> List[str]:
        return [self.OUT[_v(self, state)]]

    def skeleton(self, state: dict) -> str:
        v = _v(self, state)
        if v == 0:
            lines = ["# convert.py — продажи из sales.csv в sales.json", "import csv",
                     "import json", "", "rows = []",
                     'with open("sales.csv", newline="") as f:',
                     "    # TODO 1: reader — читатель csv.DictReader для f",
                     "    for row in reader:", "        rows.append(row)",
                     'with open("sales.json", "w") as f:',
                     "    json.dump(rows, f, indent=2, ensure_ascii=False)"]
        elif v == 1:
            lines = ["# convert.py — остатки из stock.json в stock.csv, с шапкой", "import csv",
                     "import json", "", 'with open("stock.json") as f:',
                     "    rows = json.load(f)",
                     'with open("stock.csv", "w", newline="") as f:',
                     '    w = csv.DictWriter(f, fieldnames=["name", "city", "qty"])',
                     "    # TODO 1: сначала шапка", "    # TODO 2: потом все строки rows"]
        else:
            lines = ["# convert.py — sales.csv с новой колонкой total — в sales2.csv",
                     "import csv", "", 'with open("sales.csv", newline="") as f:',
                     "    rows = list(csv.DictReader(f))",
                     'with open("sales2.csv", "w", newline="") as f:',
                     '    w = csv.DictWriter(f, fieldnames=["id", "item", "price", "qty", '
                     '"total"])',
                     "    w.writeheader()", "    for row in rows:",
                     "        # TODO 1: row[\"total\"] — цена × количество (они текстом: "
                     "сначала int)",
                     "        w.writerow(row)"]
        return "\n".join(lines) + "\n"

    def edits(self, state: dict) -> List[Tuple[str, str]]:
        v = _v(self, state)
        if v == 0:
            return [("# TODO 1", "reader = csv.DictReader(f)")]
        if v == 1:
            return [("# TODO 1", "w.writeheader()"), ("# TODO 2", "w.writerows(rows)")]
        return [("# TODO 1", 'row["total"] = int(row["price"]) * int(row["qty"])')]

    def check_outputs(self, ctx) -> Verdict:
        st = ctx.state
        out = self.outputs_for(st)[0]
        if _v(self, st) == 0:
            doc, msg, text = pykit.read_json(ctx.box, out, self.run)
            if msg:
                return Verdict(False, msg)
            want = st["expect"]
            if _same_records(doc, want):
                form = pykit.json_form(text, out, cyrillic=False)
                return Verdict(form is None, form)
            for key, trap in st.get("traps") or ():
                if key in self.trap_messages and _same_records(doc, trap):
                    return Verdict(False, self.trap_messages[key])
            if _cut_quotes(doc):
                return Verdict(False, self.trap_messages["split"])
            if (isinstance(doc, list) and doc and len(doc) < len(want)
                    and _same_records(doc, want[:len(doc)])):
                return Verdict(False, self.MSG_PARTIAL.format(n=len(doc), m=len(want)))
            return Verdict(False, self.MSG_WRONG)
        rows, msg = pykit.read_csv(ctx.box, out, self.run)
        if msg:
            return Verdict(False, msg)
        want = st["expect"]
        if rows[0] == want[0] and _same_csv(rows, want):
            return Verdict(True)
        for key, trap in st.get("traps") or ():
            if key in self.trap_messages and _same_csv(rows, trap):
                return Verdict(False, self.trap_messages[key])
        if rows[0] != want[0]:
            return Verdict(False, self.MSG_HEAD.format(head=",".join(want[0])))
        body, need = rows[1:], want[1:]
        if not body:
            return Verdict(False, self.MSG_NO_ROWS.format(m=len(need)))
        if len(body) < len(need) and _same_csv(body, need[:len(body)]):
            return Verdict(False, self.MSG_PARTIAL.format(n=len(body), m=len(need)))
        return Verdict(False, self.MSG_WRONG)


# --- 9. py_files ----------------------------------------------------------------------------

class PyFiles(pykit.PyEditTask):
    """pathlib.Path, .glob/.rglob, .stat().st_size, re.search: размер логов с подпапками,
    строки с кодом ошибки, отчёты старше даты по имени."""
    id = "py_files"
    track = "py"
    title = "Файлы скриптом"
    par = 90
    script = "files.py"
    run = "python3 files.py > out.txt"
    outputs = ("out.txt",)
    scroll = ("Пути: from pathlib import Path; Path(\"shelf\") — папка; .glob(\"*.txt\") — "
              "файлы в ней, .rglob(\"*.txt\") — ещё и во всех подпапках.\n"
              "Размер: p.stat().st_size — в байтах; по файлам: for p in "
              "Path(\"shelf\").glob(\"*.txt\"):")
    variants = (
        Variant("Сколько байт занимают все файлы *.log в папке logs — вместе с подпапками? "
                "Допиши files.py, итог — в out.txt: python3 files.py > out.txt",
                hints=("Открой files.py: nano files.py — две строки # TODO.",
                       "«Вместе с подпапками» — это rglob, а не glob; размер файла — "
                       "p.stat().st_size, копи его в total."),
                wrong=("python3 files.py > out.txt",),
                alternatives=("sum(p.stat().st_size for p in Path(\"logs\").rglob(\"*.log\")) "
                              "— то же одной строкой",),
                key="size"),
        Variant(py("Сколько строк app.log с кодом ошибки — E и три цифры, например E404? "
                   "re.search(r\"E\\d{3}\", line) найдёт код где угодно в строке, а re.match — "
                   "только в начале. Допиши files.py, итог — в out.txt: python3 files.py > "
                   "out.txt"),
                hints=("Открой files.py: nano files.py — одна строка # TODO.",
                       py("Условие — if re.search(шаблон, line): шаблон r\"E\\d{3}\" — "
                          "буква E и ровно три цифры.")),
                wrong=("python3 files.py > out.txt",),
                alternatives=(py("grep -c 'E[0-9]\\{3\\}' app.log — то же в оболочке"),),
                key="search"),
        Variant("Какие отчёты в reports старше {cutoff} (cutoff в files.py)? Дата — в имени "
                "файла, report-ГГГГ-ММ-ДД.txt. Допиши files.py: имена по алфавиту, по одному в "
                "строке, — в out.txt: python3 files.py > out.txt",
                hints=("Открой files.py: nano files.py — две строки # TODO.",
                       "Цикл — по sorted(…glob(\"report-*.txt\")); даты ГГГГ-ММ-ДД сравнивают "
                       "как строки: «раньше» — это <."),
                wrong=("python3 files.py > out.txt",),
                alternatives=("ls reports | sort — посмотреть имена глазами",),
                key="dates"),
    )
    hints = variants[0].hints
    explain = ("pathlib.Path — путь как объект: .glob ищет в папке, .rglob — ещё и во всех "
               "подпапках, .stat().st_size — размер. re.search ловит шаблон где угодно в "
               "строке, а re.match — только в самом начале.")
    spell = "Path(\"logs\").rglob(\"*.log\"); p.stat().st_size; re.search(r\"E\\d{3}\", s)"
    trap_messages = {
        "glob": "Это только верхний уровень logs: glob не заходит в подпапки — rglob.",
        "all": "Сюда попали и не-логи (.txt): шаблон — \"*.log\".",
        "match": "Это строки, где код в самом начале: re.match ищет только там — нужен "
                 "re.search.",
        "letter_e": "Сюда попали строки, где просто есть буква E: шаблон — E и три цифры, "
                    "r\"E\\d{{3}}\".",
        "le": "Сюда попал и сам день {cutoff}: «старше» — строго раньше, знак <.",
        "newer": "Это отчёты новее {cutoff}: знак смотрит не туда — нужен <.",
    }
    MSG_EMPTY = "out.txt пуст: допиши строки # TODO и запусти: python3 files.py > out.txt"
    MSG_NOT_NUM = "В out.txt не число: скрипт печатает итог одной строкой — print(total)."
    MSG_WRONG = "Не то число. Глянь, по каким файлам или строкам считаешь, — и запусти снова."
    MSG_NAMES = "В out.txt есть имена, которых нет в reports. Запусти files.py заново."
    MSG_PARTIAL = "Есть {n} из {m}: эти отчёты верные, но не все."
    MSG_WRONG_C = "Не те отчёты. Сверь условие с cutoff — и запусти скрипт снова."
    MSG_ORDER = ("Отчёты верные, а порядок — нет: имена нужны по алфавиту — цикл по "
                 "sorted(…).")
    crash_tips = {
        "NameError": "Скрипт упал с NameError: имя не задано — Path и re нужно сначала "
                     "import, а цикл задаёт p.",
        "IndentationError": "Скрипт упал с IndentationError: тело for и if — с отступом в 4 "
                            "пробела.",
    }

    def prepare(self, box, rng, variant):
        st = pykit.files_data(rng, variant)
        for rel, text in st.pop("files").items():
            kit.write(Path(box) / rel, text)
        return st

    def skeleton(self, state: dict) -> str:
        v = _v(self, state)
        if v == 0:
            lines = ["# files.py — сколько байт во всех *.log в logs, вместе с подпапками",
                     "from pathlib import Path", "", "total = 0",
                     "# TODO 1: цикл по всем *.log в logs и в подпапках — каждый в p",
                     "    # TODO 2: total — прибавь размер файла p в байтах", "print(total)"]
        elif v == 1:
            lines = ["# files.py — сколько строк app.log с кодом ошибки: E и три цифры (E404)",
                     "import re", "", "count = 0", 'for line in open("app.log"):',
                     "    # TODO 1: если в строке где угодно есть код — re.search",
                     "        count += 1", "print(count)"]
        else:
            lines = ["# files.py — отчёты reports/report-ДАТА.txt старше cutoff",
                     "from pathlib import Path", "", f'cutoff = "{state["cutoff"]}"',
                     "# TODO 1: цикл по report-*.txt в reports, по алфавиту — каждый в p",
                     "    day = p.stem[-10:]    # report-2026-03-14 → 2026-03-14",
                     "    # TODO 2: если day раньше cutoff (даты ГГГГ-ММ-ДД — как строки)",
                     "        print(p.name)"]
        return "\n".join(lines) + "\n"

    def edits(self, state: dict) -> List[Tuple[str, str]]:
        v = _v(self, state)
        if v == 0:
            return [("# TODO 1", 'for p in Path("logs").rglob("*.log"):'),
                    ("# TODO 2", "total += p.stat().st_size")]
        if v == 1:
            return [("# TODO 1", 'if re.search(r"E\\d{3}", line):')]
        return [("# TODO 1", 'for p in sorted(Path("reports").glob("report-*.txt")):'),
                ("# TODO 2", "if day < cutoff:")]

    def check_outputs(self, ctx) -> Verdict:
        st = ctx.state
        kind, text = envkit.box_text(ctx.box, "out.txt", envkit.TEXT_CAP)
        if kind != "ok":
            return Verdict(False, envkit.file_problem(kind, "out.txt"))
        if _v(self, st) == 2:
            return self._names(text, st)
        value = pykit.last_value(text)
        if not value:
            return Verdict(False, self.MSG_EMPTY)
        for key, trap in st.get("traps") or ():
            if key in self.trap_messages and value == str(trap):
                return Verdict(False, self.trap_messages[key].format(**st))
        if pykit.as_num(value) is None:
            return Verdict(False, self.MSG_NOT_NUM)
        if pykit.same_num(value, st["expect"]):
            return Verdict(True)
        return Verdict(False, self.MSG_WRONG)

    def _names(self, text: str, st: dict) -> Verdict:
        got = [x.strip() for x in text.split("\n")[:2000] if x.strip()]
        got = [x.rsplit("/", 1)[-1] for x in got]       # reports/x.txt — то же имя
        if not got:
            return Verdict(False, self.MSG_EMPTY)
        want = st["expect"]
        if got == want:
            return Verdict(True)
        if sorted(got) == sorted(want):
            return Verdict(False, self.MSG_ORDER)
        # ловушка — тот же набор имён в любом порядке (порядок — отдельная ошибка)
        for key, trap in st.get("traps") or ():
            if key in self.trap_messages and sorted(got) == sorted(trap):
                return Verdict(False, self.trap_messages[key].format(**st))
        known = set(want) | {n for _, t in st.get("traps") or () for n in t}
        if set(got) - known:
            return Verdict(False, self.MSG_NAMES)
        if set(got) < set(want):
            return Verdict(False, self.MSG_PARTIAL.format(n=len(got), m=len(want)))
        return Verdict(False, self.MSG_WRONG_C)


# --- 10. py_stats ---------------------------------------------------------------------------

class PyStats(pykit.PyEditTask):
    """collections.Counter и most_common, statistics.median и mean, date.fromisoformat: самые
    частые товары, медиана и среднее чеков, дней между датами."""
    id = "py_stats"
    track = "py"
    title = "Счёт и середина"
    par = 90
    script = "stats.py"
    run = "python3 stats.py > out.txt"
    outputs = ("out.txt",)
    scroll = ("Подсчёт: from collections import Counter; c = Counter(words) — сколько раз "
              "каждое; c.most_common(2) — пары «слово, сколько», от самых частых.\n"
              "Середина: statistics.median(xs) — при чётном числе это среднее двух "
              "серединных; statistics.mean(xs) — среднее; модуль: import statistics.")
    variants = (
        Variant("Какие три товара в sales продавались чаще всех? Допиши stats.py: строки "
                "товар=сколько, от самого частого, — в out.txt: python3 stats.py > out.txt",
                hints=("Открой stats.py: nano stats.py — две строки # TODO.",
                       "Counter посчитает всё сам, а пары от самых частых отдаёт most_common "
                       "— ему передают, сколько пар нужно."),
                wrong=("python3 stats.py > out.txt",),
                alternatives=("sorted(counts.items(), key=lambda x: -x[1])[:3] — то же без "
                              "most_common",),
                key="counter"),
        Variant("Чеки дня — список checks в stats.py. Допиши stats.py: медиана и среднее, "
                "среднее — до 2 знаков; вывод — в out.txt: python3 stats.py > out.txt",
                hints=("Открой stats.py: nano stats.py — две строки # TODO.",
                       "Модуль statistics: median — середина, mean — среднее; среднее "
                       "округли round(…, 2)."),
                wrong=("python3 stats.py > out.txt",),
                alternatives=("sum(checks) / len(checks) — то же среднее без statistics",),
                key="median"),
        Variant(py("Сколько дней прошло от самой ранней даты списка days в stats.py до самой "
                   "поздней? date.fromisoformat(\"2026-03-14\") делает из строки дату, а "
                   "(d2 - d1).days — сколько дней между двумя датами. Допиши stats.py — ответ "
                   "в out.txt: python3 stats.py > out.txt"),
                hints=("Открой stats.py: nano stats.py — две строки # TODO.",
                       "Из first и last — даты через date.fromisoformat; разница дат, у неё "
                       "поле .days — его и печатай."),
                wrong=("python3 stats.py > out.txt",),
                alternatives=("from datetime import datetime; datetime.fromisoformat(…) — "
                              "тоже работает: дата со временем",),
                key="dates"),
    )
    hints = variants[0].hints
    explain = ("Counter считает, сколько раз встречается каждое, most_common(n) отдаёт n самых "
               "частых. statistics.median при чётном числе берёт среднее двух серединных — "
               "руками это легко проморгать.")
    spell = "Counter(xs).most_common(3); statistics.median(xs); date.fromisoformat(s)"
    trap_messages = {
        "alpha": "Это первые три по алфавиту, а нужны самые частые: most_common(3).",
        "upper": "Это одна середина. При чётном числе чеков медиана — среднее двух "
                 "серединных: statistics.median.",
        "lower": "Это одна середина. При чётном числе чеков медиана — среднее двух "
                 "серединных: statistics.median.",
        "unsorted": "Это середина списка как есть, без сортировки: медиана — середина по "
                    "возрастанию, statistics.median.",
        "plus_one": "Разница дат — без +1: (d2 - d1).days.",
    }
    MSG_EMPTY = "out.txt пуст: допиши строки # TODO и запусти: python3 stats.py > out.txt"
    MSG_FORM = "Строки в out.txt — вида имя=число, по одной. Печать уже есть в stats.py."
    MSG_ORDER = ("Товары верные, а порядок — нет: от самого частого к редкому, как отдаёт "
                 "most_common.")
    MSG_PARTIAL = "Есть {n} из 3: эти верные, но нужны все три."
    MSG_WRONG = "Не те числа. Сверь, что считаешь, — и запусти скрипт снова."
    MSG_ROUND = "Округли среднее до 2 знаков: round(x, 2)."
    MSG_NOT_NUM = "В out.txt не число: напечатай итог одной строкой — print(…)."
    crash_tips = {
        "NameError": "Скрипт упал с NameError: имя не задано — строка # TODO должна его "
                     "создать.",
        "TypeError": "Скрипт упал с TypeError: даты-строки не вычитают — сначала "
                     "date.fromisoformat(…).",
    }

    def prepare(self, box, rng, variant):
        return pykit.stats_data(rng, variant)

    def skeleton(self, state: dict) -> str:
        v = _v(self, state)
        if v == 0:
            sales = ", ".join(_q(x) for x in state["sales"])
            lines = ["# stats.py — три самых частых товара в sales",
                     "from collections import Counter", "", f"sales = [{sales}]",
                     "# TODO 1: counts — Counter по sales",
                     "# TODO 2: цикл по трём самым частым — пары name, n",
                     '    print(f"{name}={n}")']
        elif v == 1:
            lines = ["# stats.py — медиана и среднее чеков", "import statistics", "",
                     f"checks = {state['checks']}",
                     "# TODO 1: median — середина checks (модуль statistics)",
                     "# TODO 2: mean — среднее checks, до 2 знаков",
                     'print(f"median={median}")', 'print(f"mean={mean}")']
        else:
            days = ", ".join(_q(x) for x in state["days"])
            lines = ["# stats.py — сколько дней от самой ранней даты до самой поздней",
                     "from datetime import date", "", f"days = [{days}]",
                     "first = min(days)    # даты ГГГГ-ММ-ДД сравнивают как строки",
                     "last = max(days)",
                     "# TODO 1: d1 и d2 — даты из first и last (date.fromisoformat)",
                     "# TODO 2: напечатай, сколько дней между d1 и d2"]
        return "\n".join(lines) + "\n"

    def edits(self, state: dict) -> List[Tuple[str, str]]:
        v = _v(self, state)
        if v == 0:
            return [("# TODO 1", "counts = Counter(sales)"),
                    ("# TODO 2", "for name, n in counts.most_common(3):")]
        if v == 1:
            return [("# TODO 1", "median = statistics.median(checks)"),
                    ("# TODO 2", "mean = round(statistics.mean(checks), 2)")]
        return [("# TODO 1", "d1 = date.fromisoformat(first)\nd2 = date.fromisoformat(last)"),
                ("# TODO 2", "print((d2 - d1).days)")]

    def check_outputs(self, ctx) -> Verdict:
        st = ctx.state
        kind, text = envkit.box_text(ctx.box, "out.txt", envkit.TEXT_CAP)
        if kind != "ok":
            return Verdict(False, envkit.file_problem(kind, "out.txt"))
        if not text.strip():
            return Verdict(False, self.MSG_EMPTY)
        v = _v(self, st)
        if v == 0:
            return self._top(text, st)
        if v == 1:
            return self._middle(text, st)
        value = pykit.last_value(text)
        for key, trap in st.get("traps") or ():
            if key in self.trap_messages and value == str(trap):
                return Verdict(False, self.trap_messages[key])
        if pykit.as_num(value) is None:
            return Verdict(False, self.MSG_NOT_NUM)
        if pykit.same_num(value, st["expect"]):
            return Verdict(True)
        return Verdict(False, self.MSG_WRONG)

    def _top(self, text: str, st: dict) -> Verdict:
        rows = []
        for line in [x.strip() for x in text.split("\n")[:500] if x.strip()]:
            name, eq, value = line.partition("=")
            if not eq or pykit.as_num(value) is None:
                return Verdict(False, self.MSG_FORM)
            rows.append([name.strip(), value.strip()])

        def same(got, want):
            return len(got) == len(want) and all(
                g[0] == w[0] and pykit.same_num(g[1], w[1]) for g, w in zip(got, want))
        want = st["expect"]
        if same(rows, want):
            return Verdict(True)
        for key, trap in st.get("traps") or ():
            if key in self.trap_messages and same(rows, trap):
                return Verdict(False, self.trap_messages[key])
        if len(rows) == len(want) and same(sorted(rows), sorted(want)):
            return Verdict(False, self.MSG_ORDER)
        if rows and len(rows) < len(want) and same(rows, want[:len(rows)]):
            return Verdict(False, self.MSG_PARTIAL.format(n=len(rows)))
        return Verdict(False, self.MSG_WRONG)

    def _middle(self, text: str, st: dict) -> Verdict:
        got, bad = pykit.pairs(text)
        want = st["expect"]
        if bad or set(got) != set(want) or any(pykit.as_num(x) is None for x in got.values()):
            return Verdict(False, self.MSG_FORM)
        med_ok = pykit.same_num(got["median"], want["median"])
        if not med_ok:
            for key, trap in st.get("traps") or ():
                if key in self.trap_messages and pykit.same_num(got["median"], trap):
                    return Verdict(False, self.trap_messages[key])
            return Verdict(False, self.MSG_WRONG)       # M7: медиана — раньше округления
        if pykit.decimals(got["mean"]) > 2:
            return Verdict(False, self.MSG_ROUND)
        if med_ok and pykit.same_num(got["mean"], want["mean"]):
            return Verdict(True)
        return Verdict(False, self.MSG_WRONG)


# --- 11. py_urllib --------------------------------------------------------------------------

URLLIB_HEAD = ["import json", "import urllib.request", "", "import sockhttp", "",
               "sockhttp.install()    # только для учебного сервера: дальше — обычный urllib"]


class PyUrllib(pykit.PyEditTask):
    """sockhttp.install(), urllib.request.urlopen, json.load(r), запись в файл: остатки с
    учебного API — страница, фильтр по городу, две страницы. Засчитывается по stock.json и
    журналу API: запросы от urllib (Python-urllib/…) — у родителя, судья."""
    id = "py_urllib"
    track = "py"
    title = "Данные с API"
    par = 105
    script = "fetch.py"
    run = "source .venv/bin/activate && python3 fetch.py"
    outputs = ("stock.json",)
    stock = "light"
    venv_modules = ("sockhttp",)
    needs_judge = True
    secret_keys = ("expect", "traps", "stock")
    scroll = ("API — вход сервиса для программ. Сервер игры — в файле api.sock: "
              "sockhttp.install() направит туда запросы urllib (только у нас).\n"
              "Запрос: r = urllib.request.urlopen(\"http://api/items\") — ответ; json.load(r) — "
              "его JSON; модуль: import urllib.request.\n"
              "Параметры — в адресе: http://api/items?page=2&city=Omsk; пакет — в .venv: "
              "source .venv/bin/activate.")
    variants = (
        Variant("Учебный API отдаёт остатки склада по адресу http://api/stock; допиши fetch.py: "
                "список items ответа — в stock.json; запуск — source .venv/bin/activate && "
                "python3 fetch.py",
                hints=("Открой fetch.py: nano fetch.py — одна строка # TODO.",
                       "Запрос — urllib.request.urlopen с адресом из задания; ответ дальше "
                       "читает json.load(r)."),
                wrong=("source .venv/bin/activate && python3 fetch.py",),
                alternatives=("curl --unix-socket api.sock http://api/stock — посмотреть "
                              "ответ глазами",),
                key="get"),
        Variant("Нужны остатки только города {city}: API фильтрует сам — параметр city в адресе "
                "http://api/stock. Допиши fetch.py — список в stock.json.",
                hints=("Открой fetch.py: nano fetch.py — одна строка # TODO.",
                       "Параметр — после ? в адресе: http://api/stock?city={city}."),
                wrong=("source .venv/bin/activate && python3 fetch.py",),
                alternatives=("curl --unix-socket api.sock 'http://api/stock?city={city}' — "
                              "проверить фильтр глазами",),
                key="params"),
        Variant("Остатков много: http://api/stock отдаёт их страницами — ?page=N, а в поле next "
                "номер следующей (null — дальше пусто). Допиши fetch.py: все строки всех "
                "страниц — одним списком в stock.json.",
                hints=("Открой fetch.py: nano fetch.py — две строки # TODO.",
                       "Сколько страниц — скажет next: curl --unix-socket api.sock "
                       "http://api/stock; цикл — по номерам, адрес — f-строкой с page."),
                wrong=("source .venv/bin/activate && python3 fetch.py",),
                alternatives=("for page in range(1, 3): — те же номера 1 и 2",),
                key="pages"),
    )
    hints = variants[0].hints
    explain = ("urllib.request.urlopen — запрос из Python, json.load(r) разбирает ответ. "
               "sockhttp.install() нужен, только чтобы urllib достучался до сервера игры в "
               "api.sock; в жизни urlopen(\"https://…\") сам идёт в сеть. Параметры и страницы "
               "— прямо в адресе.")
    spell = "sockhttp.install(); r = urllib.request.urlopen(\"http://api/…\"); json.load(r)"
    trap_messages = {
        "all": "Здесь все города: в адресе нет фильтра — ?city={city}.",
        "first": "Здесь только первая страница. Страниц две — посмотри поле next в ответе.",
    }
    MSG_WHOLE = ("В stock.json — весь ответ API, а нужен только список строк: "
                 "data[\"items\"].")
    MSG_PARTIAL = "Есть {n} из {m}: эти строки верные, но не все."
    MSG_WRONG = "Не те строки. Сверь адрес запроса с заданием — и запусти скрипт снова."
    MSG_NOT_URLLIB = ("В журнале API нет запроса от urllib (Python) по этому адресу — "
                      "stock.json пишет скрипт: {run}")
    MSG_NO_LOG = "Журнал учебного API не читается — набери reset."
    crash_tips = {
        "NameError": "Скрипт упал с NameError: r ещё не задан — строка # TODO делает запрос: "
                     "r = urllib.request.urlopen(…).",
    }

    def prepare(self, box, rng, variant):
        from termit_app import apiserver
        apiserver.link(box)
        kit.venv_from_stock(box, "light", ".venv")
        return pykit.urllib_data(rng, variant)

    def service(self, box, state):
        from termit_app import apiserver
        return apiserver.open_server(box, pykit.stock_routes(state))

    def skeleton(self, state: dict) -> str:
        v = _v(self, state)
        if v == 2:
            body = ["items = []",
                    "# TODO 1: цикл по номерам страниц — сколько их, скажет поле next",
                    "    # TODO 2: r — ответ на http://api/stock?page=… (номер — из page)",
                    '    items += json.load(r)["items"]', 'with open("stock.json", "w") as f:',
                    "    json.dump(items, f, indent=2)"]
            head = "# fetch.py — все страницы остатков учебного API в stock.json"
        else:
            what = ("на http://api/stock" if v == 0 else
                    f"на http://api/stock только по городу {state['city']} (параметр city)")
            body = [f"# TODO 1: r — ответ urllib.request.urlopen {what}", "data = json.load(r)",
                    'with open("stock.json", "w") as f:',
                    '    json.dump(data["items"], f, indent=2)']
            head = "# fetch.py — остатки учебного API в stock.json"
        return "\n".join([head] + URLLIB_HEAD + body) + "\n"

    def edits(self, state: dict) -> List[Tuple[str, str]]:
        v = _v(self, state)
        if v == 0:
            return [("# TODO 1", 'r = urllib.request.urlopen("http://api/stock")')]
        if v == 1:
            return [("# TODO 1", "r = urllib.request.urlopen("
                                 f'"http://api/stock?city={state["city"]}")')]
        return [("# TODO 1", "for page in [1, 2]:"),
                ("# TODO 2", 'r = urllib.request.urlopen(f"http://api/stock?page={page}")')]

    def _fetched(self, ctx) -> bool:
        """Журнал API: urllib запросил то, что нужно варианту (B — с city, C — и страницу 2)."""
        hits = pykit.urllib_hits(ctx.service)
        v = _v(self, ctx.state)
        if v == 1:
            return any(e["query"].get("city") == [ctx.state["city"]] for e in hits)
        if v == 2:
            pages = {(e["query"].get("page") or ["1"])[0] for e in hits}
            return {"1", "2"} <= pages
        return bool(hits)

    def check_outputs(self, ctx) -> Verdict:
        st = ctx.state
        doc, msg, _ = pykit.read_json(ctx.box, "stock.json", self.run)
        if msg:
            return Verdict(False, msg)
        want = st["expect"]
        if pykit.same_rows(doc, want):
            if ctx.service is None:
                return Verdict(False, self.MSG_NO_LOG)
            if not self._fetched(ctx):
                return Verdict(False, self.MSG_NOT_URLLIB.format(run=self.run))
            return Verdict(True)
        for key, trap in st.get("traps") or ():
            if key in self.trap_messages and pykit.same_rows(doc, trap):
                return Verdict(False, self.trap_messages[key].format(**st))
        if isinstance(doc, dict) and "items" in doc:
            return Verdict(False, self.MSG_WHOLE)
        if isinstance(doc, list) and doc and len(doc) < len(want) and all(x in want for x in doc):
            return Verdict(False, self.MSG_PARTIAL.format(n=len(doc), m=len(want)))
        return Verdict(False, self.MSG_WRONG)


# --- страж: boss_py -------------------------------------------------------------------------

_BOSS_RUN = "source .venv/bin/activate && python3 report.py"
_BOSS_FIXES = ("swap", "pages", "json", "header")
# «for …:» и разделитель «;» подряд читались как «:;» — цикл назван словами (FB7)
_BOSS_LATER = ("цикл for page in [1, 2]: по обеим страницам; json.dump(paid, f, indent=2, "
               "ensure_ascii=False); "
               "w.writeheader() перед циклом строк")
_BOSS_SWAP = ("убери строку import requests", "rm csv.py", "order[\"town\"] → order[\"city\"]")


def _boss_script(variant: int, fixed=_BOSS_FIXES) -> str:
    """Скрипт для тестов стража: report.py с починками fixed (B — и двойник csv.py убран, если
    подмена починена) и запуск в .venv. Через str.format — скобки Python удвоены (py)."""
    pre = "rm csv.py\n" if variant == 1 and "swap" in fixed else ""
    body = pykit.boss_report(variant, fixed).rstrip("\n")
    return py(f"{pre}cat > report.py <<'{pykit.HEREDOC}'\n{body}\n{pykit.HEREDOC}\n"
              f"{_BOSS_RUN}\n")


def _boss_wrong(variant: int) -> Tuple[str, ...]:
    return tuple(_boss_script(variant, [f for f in _BOSS_FIXES if f != miss])
                 for miss in _BOSS_FIXES)


def _boss_shown(variant: int) -> str:
    swap = _BOSS_SWAP[variant]
    if variant == 1:
        return (f"{_BOSS_RUN} → прочти traceback → {swap} → nano report.py: {_BOSS_LATER} → "
                f"python3 report.py")
    return (f"{_BOSS_RUN} → прочти traceback → nano report.py: {swap}; {_BOSS_LATER} → "
            f"python3 report.py")


_BOSS_H1 = ("Запусти и прочти: source .venv/bin/activate && python3 report.py — последняя "
       "строка traceback скажет, что сломалось; править — nano report.py.")
_BOSS_H2 = ("Сколько страниц у /stock, спроси сам API: curl --unix-socket api.sock "
       "http://api/stock | python3 -c 'import json, sys; "
       "print(json.load(sys.stdin)[\"next\"])'. И проверь отступы, кириллицу и шапку CSV.")
_BOSS_H3 = ("Лишний import requests — отчёту он не нужен: убери строку. ",
       "csv.py рядом — двойник: import csv берёт его, а не модуль Python. rm csv.py. ",
       "KeyError: 'town' — в orders.json ключ city: order[\"city\"]. ")


class BossPy(Task):
    """Страж трека: report.py выдаёт себя за правильный, а врёт в четырёх местах — подмена (A:
    лишний import, B: двойник csv.py рядом, C: чужой ключ), одна страница API, json.dump без
    отступов и кириллицы, CSV без шапки. Каждый приём — из варианта 0 задач трека (П3.1):
    traceback — py_run, ключи словаря — py_dict, свой файл рядом — py_func, страницы API —
    py_urllib, json.dump — py_json, writeheader — py_csv_json. Проверка — по файлам у родителя
    (разбор json/csv), журналу учебного API и тексту report.py (как текст, без исполнения):
    задача скрытая, вердикт судьи (P003)."""
    id = "boss_py"
    track = "py"
    title = "Скрипт-подменыш"
    boss = True
    par = 480
    pinned_python = True
    stock = "light"
    needs_judge = True
    tool = "python"
    secret_keys = ("stock", "paid", "summary", "traps", "orders_sha")
    scroll = ("Скрипт врёт — запусти и читай traceback снизу; ModuleNotFoundError — нет "
              "пакета в .venv или лишний import; файл с именем модуля рядом со скриптом "
              "(shelf.py) перекроет настоящий; KeyError — сверь ключи с файлом данных.\n"
              "API отдаёт страницами — смотри next; JSON — json.dump(x, f, indent=2, "
              "ensure_ascii=False); CSV — w.writeheader() перед строками, строка — "
              "w.writerow(d).")
    steps = ("report.py больше не падает: подмена найдена и убрана, orders.json не тронут",
             "stock.json скачан с API скриптом — строки всех страниц",
             "paid.json — только оплаченные заказы, с отступами и кириллицей буквами",
             "summary.csv — шапка и по строке на каждый город")
    variants = tuple(
        Variant(text, hints=(_BOSS_H1, _BOSS_H2, py(_BOSS_H3[i] + "Дальше: " + _BOSS_LATER + ".")),
                solution=py(_boss_shown(i)), solution_script=_boss_script(i),
                wrong=_boss_wrong(i),
                alternatives=("python3 -m json.tool paid.json — проверить, что JSON цел",))
        for i, text in enumerate((
            "report.py собирает отчёт магазина — остатки с API, оплаченные заказы и сводку по "
            "городам, сумму заказов, — и выдаёт себя за правильный; запусти его в .venv, "
            "прочти traceback и почини отчёт по шагам ниже.",
            "Отчёт report.py — остатки с API, оплаченные заказы, сводка по городам, число "
            "заказов, — падает и врёт; найди подмену, почини скрипт и собери отчёт по шагам "
            "ниже.",
            "report.py считает отчёт магазина — остатки с API, оплаченные заказы, сводку по "
            "городам, штуки товара, — и врёт на каждом шаге; почини его и собери отчёт по "
            "шагам ниже.")))
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Скрипт-подменыш врёт тихо: падает на чужом модуле или ключе, берёт одну "
               "страницу из двух, пишет JSON без отступов и кириллицы, а CSV — без шапки. "
               "Лечится по traceback и по файлам: запустил, поправил, снова запустил.")
    spell = ("traceback снизу → лишний import / двойник модуля / ключ → next у API → "
             "indent=2, ensure_ascii=False → writeheader")
    MSG_REPORT_GONE = "report.py пропал. Набери reset — соберу задачу заново."
    MSG_ORDERS = ("orders.json изменён, а это данные — их не правят: чинят скрипт. Набери "
                  "reset — файл вернётся.")
    MSG_PAGES = "В stock.json только первая страница. Страниц две — посмотри поле next в ответе."
    MSG_STOCK_NOT_PY = ("В журнале API нет запросов report.py (urllib) ко всем страницам — "
                        "stock.json пишет скрипт: " + _BOSS_RUN)
    MSG_STOCK_WRONG = "В stock.json не те строки: их пишет report.py со всех страниц /stock."
    MSG_PAID_ALL = "В paid.json все заказы, а нужны только оплаченные: status == \"paid\"."
    MSG_PAID_UNPAID = "В paid.json неоплаченные: условие наоборот — status == \"paid\"."
    MSG_PAID_WRONG = "В paid.json не те заказы: их пишет report.py из orders.json."
    MSG_NO_HEADER = "В summary.csv строки верные, а шапки нет: w.writeheader() перед ними."
    MSG_HEAD = "Шапка summary.csv не та: нужна {head} — как в fieldnames."
    MSG_SUM_PART = "В summary.csv внесено {n} из {m} городов: сделанное верно, но не всё."
    MSG_SUM_WRONG = "В summary.csv не те числа: сверь расчёт в report.py с заданием."
    MSG_NO_LOG = "Журнал учебного API не читается — набери reset."
    MSG_TOWN = "В report.py остался ключ town, а в orders.json его нет: убери его из скрипта."
    MSG_ATTR = ("Скрипт упал с AttributeError: у модуля нет нужного имени. А тот ли это "
                "модуль? Глянь, что лежит рядом со скриптом: ls.")
    MSG_EMPTY = ("{out} пуст: report.py упал, не дописав его. Запусти и прочти traceback: "
                 + _BOSS_RUN)

    def reads_script(self) -> bool:
        """Проверка читает report.py как текст (подмена убрана?) — задача скрытая (P003)."""
        return True

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        from termit_app import apiserver
        box = Path(box)
        apiserver.link(box)
        kit.venv_from_stock(box, "light", ".venv")
        d = pykit.boss_py_data(rng, variant)
        kit.write(box / "orders.json", d.pop("json"))
        kit.write(box / "report.py", pykit.boss_report(variant))
        if variant == 1:
            kit.write(box / "csv.py", pykit.FAKE_CSV)
        d["orders_sha"] = kit.sha(box / "orders.json")
        return d

    def service(self, box, state):
        from termit_app import apiserver
        return apiserver.open_server(box, pykit.stock_routes(state))

    # --- шаги: (готово, отклик или None) ---------------------------------------------------

    def _step_swap(self, ctx):
        import re
        st, box = ctx.state, ctx.box
        if kit.sha_in_box(box, "orders.json") != st.get("orders_sha"):
            return False, self.MSG_ORDERS
        kind, text = pykit.py_text(ctx, "report.py")
        if kind == "missing":
            return False, self.MSG_REPORT_GONE
        if kind != "ok":
            return False, envkit.file_problem(kind, "report.py")
        v = _v(self, st)
        if v == 0:
            return not pykit.imports(text, "requests"), None
        if v == 1:
            return envkit.box_file(box, "csv.py")[0] == "missing", None
        return re.search(r"""["']town["']""", text) is None, None

    def _step_stock(self, ctx):
        st = ctx.state
        kind, raw = envkit.box_file(ctx.box, "stock.json")
        if kind == "missing":
            return False, None
        if kind == "ok" and not raw.strip():
            return False, self.MSG_EMPTY.format(out="stock.json")
        doc, msg, _ = pykit.read_json(ctx.box, "stock.json", _BOSS_RUN)
        if msg:
            return False, msg
        if pykit.same_rows(doc, st["stock"]):
            if ctx.service is None:
                return False, self.MSG_NO_LOG
            pages = {(e["query"].get("page") or ["1"])[0] for e in pykit.urllib_hits(ctx.service)}
            return ({"1", "2"} <= pages), (None if {"1", "2"} <= pages else self.MSG_STOCK_NOT_PY)
        traps = dict((k, t) for k, t in st.get("traps") or ())
        if pykit.same_rows(doc, traps.get("first") or []):
            return False, self.MSG_PAGES
        return False, self.MSG_STOCK_WRONG

    def _step_paid(self, ctx):
        st = ctx.state
        kind, raw = envkit.box_file(ctx.box, "paid.json")
        if kind == "missing":
            return False, None
        if kind == "ok" and not raw.strip():
            return False, self.MSG_EMPTY.format(out="paid.json")
        doc, msg, text = pykit.read_json(ctx.box, "paid.json", _BOSS_RUN)
        if msg:
            return False, msg
        if doc == st["paid"]:
            form = pykit.json_form(text, "paid.json", cyrillic=True)
            return form is None, form
        traps = dict((k, t) for k, t in st.get("traps") or ())
        if doc == traps.get("all"):
            return False, self.MSG_PAID_ALL
        if doc == traps.get("unpaid"):
            return False, self.MSG_PAID_UNPAID
        return False, self.MSG_PAID_WRONG

    def _step_summary(self, ctx):
        st = ctx.state
        kind, raw = envkit.box_file(ctx.box, "summary.csv")
        if kind == "missing":
            return False, None
        if kind == "ok" and not raw.strip():
            return False, self.MSG_EMPTY.format(out="summary.csv")
        rows, msg = pykit.read_csv(ctx.box, "summary.csv", _BOSS_RUN)
        if msg:
            return False, msg
        head, want = st["summary"][0], st["summary"][1:]

        def same(got):
            return len(got) == len(want) and all(
                any(len(g) == 2 and g[0] == c and pykit.same_num(g[1], n) for g in got)
                for c, n in want)
        if rows[0] != head:
            if same(rows):
                return False, self.MSG_NO_HEADER
            return False, self.MSG_HEAD.format(head=",".join(head))
        body = rows[1:]
        if same(body):
            return True, None
        ok = [g for g in body if any(len(g) == 2 and g[0] == c and pykit.same_num(g[1], n)
                                     for c, n in want)]
        if body and len(ok) == len(body) < len(want):
            return False, self.MSG_SUM_PART.format(n=len(body), m=len(want))
        return False, self.MSG_SUM_WRONG

    def _steps(self, ctx):
        return [self._step_swap(ctx), self._step_stock(ctx), self._step_paid(ctx),
                self._step_summary(ctx)]

    def progress(self, ctx):
        return [ok for ok, _ in self._steps(ctx)]

    def _crash(self, ctx):
        """Последняя команда — python и упала: совет читать traceback (без .venv — про .venv:
        sockhttp живёт там)."""
        last = pykit.last_command(ctx.box)
        if last is None or not pykit.runs_python(last[0]) or last[1] is not False:
            return None
        if not pykit.activated(ctx.box):
            return pykit.MSG_MODULE
        typ = pykit.out_type(ctx.box)
        if typ == "AttributeError":         # M10: у модуля нет имени — не тот модуль?
            return self.MSG_ATTR
        return pykit.MSG_TRACEBACK_TYPE.format(typ=typ) if typ else pykit.MSG_TRACEBACK

    def check(self, ctx) -> Verdict:
        steps = self._steps(ctx)
        memo_marks(ctx, [ok for ok, _ in steps])
        if all(ok for ok, _ in steps):
            return Verdict(True)
        swap = steps[0]
        if not swap[0] and swap[1] is None and _v(self, ctx.state) == 2 and steps[3][0]:
            # M12: сводка верна, а в тексте report.py остался чужой ключ (order.get("town") or …)
            steps[0] = swap = (False, self.MSG_TOWN)
        if swap[1] in (self.MSG_REPORT_GONE, self.MSG_ORDERS):
            return Verdict(False, swap[1])
        crash = self._crash(ctx)
        if crash:
            return Verdict(False, crash)
        for ok, msg in steps:
            if not ok and msg:
                return Verdict(False, msg)
        return Verdict(False)


TASKS = [PyRun(), PyVars(), PyLoop(), PyDict(), PyFunc(), PyRepl(), PyJson(),
         PyCsvJson(), PyFiles(), PyStats(), PyUrllib(),
         BossPy()]
