"""Движок задач Python (часть 10, A9): «поправь скрипт» (PyEditTask), помощник py() для
текстов через str.format, чтение скрипта игрока только как текста (py_text) и отклики на
упавший скрипт.

Правила (план части 10, «Уроки ревью 9а/9б»):
- родитель код игрока не исполняет и не импортирует. Проверка — только по результатам:
  файлы (разбор json/csv), ответ (судья), журнал учебного API (сервис). Требование
  «через модуль X» — регулярка по тексту скрипта (≤ PY_TEXT_CAP), без ast;
- задача, чья проверка читает .py, — скрытая (P003): в recheck профиль запрещает читать
  .py песочницы, вердикт даёт судья по своему состоянию (secret_keys);
- тексты подсказки 3, показанного эталона и скрипта для тестов генерируются из скелета и
  правок (edits), руками не пишутся. Эталон — `cat > report.py <<'PYEOF' … PYEOF`, без
  .format: фигурные скобки Python удваивать не нужно;
- отклик на traceback — общий («читай последнюю строку»); тип ошибки называется, только
  если он из белого списка TRACEBACK_TYPES. Текст traceback в отклик не подставляется."""
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from termit_app.tasks import envkit, kit
from termit_app.tasks.base import Ctx, Task, Verdict, _fmt

PY_TEXT_CAP = 64 * 1024         # скрипт игрока читаем как текст — не больше
OUT_LOG = ".termit/out.log"     # вывод последней команды (если игра его пишет)
OUT_TAIL = 4096                 # из вывода смотрим только хвост
OUT_CAP = 1 << 20
HEREDOC = "PYEOF"

# типы ошибок, которые можно назвать в отклике (остальное — общий совет)
TRACEBACK_TYPES = ("NameError", "TypeError", "KeyError", "IndexError", "ValueError",
                   "FileNotFoundError", "ModuleNotFoundError", "SyntaxError",
                   "IndentationError", "ZeroDivisionError", "JSONDecodeError",
                   "AttributeError")
_ERROR_LINE = re.compile(r"^(?:[A-Za-z_][\w]*\.)*([A-Za-z]+Error)(?::|$)")
# как зовут интерпретатор в строке оболочки
PYTHONS = ("python3", "python", "python3.9")

MSG_TRACEBACK = ("Скрипт упал. Читай traceback снизу: последняя строка — тип ошибки, а "
                 "выше — File …, line N: номер строки в скрипте.")
MSG_TRACEBACK_TYPE = ("Скрипт упал с {typ}. Читай traceback снизу: последняя строка — тип и "
                      "суть ошибки, а выше — File …, line N: номер строки в скрипте.")
MSG_NO_REDIRECT = "Вывод скрипта улетел на экран, а результат ждут в файле {out}: {run}"
MSG_MODULE = ("Пакет не в этом окружении — включи .venv (source .venv/bin/activate) и "
              "запусти скрипт снова.")
MSG_IMPORT = "Задача — про {mod}: в {script} нет import {mod}."
MSG_NO_SCRIPT = "{script} пропал. Набери reset — соберу задачу заново."
MSG_UNTOUCHED = ("{script} ещё не тронут — запущен как был. Открой его (nano {script}) и "
                 "впиши код вместо строк # TODO, потом запусти снова: {run}")
MSG_LONG_PATH = "путь к папке игры слишком длинный для unix-сокета"
MSG_BIG_SCRIPT = ("{script} больше 64 КБ — для задачи хватит короткого скрипта. Набери reset, "
                  "если файл испорчен.")

_FIELD = re.compile(r"<<([A-Za-z_]\w*)>>")


def py(text: str) -> str:
    """Текст с кодом Python для полей, что идут через str.format (variants, hints,
    solution…): фигурные скобки кода удваиваются, а <<поле>> становится {поле}."""
    return _FIELD.sub(r"{\1}", text.replace("{", "{{").replace("}", "}}"))


def py_text(ctx_or_box, name: str) -> Tuple[str, Optional[str]]:
    """Скрипт игрока КАК ТЕКСТ (не больше PY_TEXT_CAP): ("ok", текст) или вид отказа
    envkit.box_file ("missing", "link", "notreg", "big", "bad"). Только для регулярок
    «есть import X» — код не исполняется и не импортируется."""
    box = ctx_or_box.box if isinstance(ctx_or_box, Ctx) else ctx_or_box
    return envkit.box_text(box, name, PY_TEXT_CAP)


def _is_mod(name: Optional[str], module: str) -> bool:
    return bool(name) and (name == module or name.startswith(module + "."))


def imports(text: Optional[str], module: str) -> bool:
    """Импортирует ли скрипт модуль: `import os, json`, `import json as j`, `from json import
    x`, `from json.decoder import y`, `x = 1; import json`. Разбор ТЕКСТА: ast.parse строит
    дерево и ничего не исполняет; не разобрался (синтаксис, глубина) — запасной разбор
    строк (_imports_lines)."""
    if not text:
        return False
    import ast
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return _imports_lines(text, module)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(_is_mod(a.name, module) for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if not node.level and _is_mod(node.module, module):
                return True
    return False


_IMPORT_STMT = re.compile(r"^(?:import[ \t]+([\w., \t]+)|from[ \t]+([\w.]+)[ \t]+import\b)")


def _imports_lines(text: str, module: str) -> bool:
    """Запас для скрипта с ошибкой синтаксиса: операторы строки через «;» (и после «:»
    однострочного if/for), import a, b as c — список через запятую. Линейно."""
    for line in text.split("\n"):
        for stmt in line.split(";"):
            stmt = stmt.strip()
            if ":" in stmt and not stmt.startswith(("import", "from")):
                stmt = stmt.rsplit(":", 1)[1].strip()
            m = _IMPORT_STMT.match(stmt)
            if not m:
                continue
            if m.group(2) and _is_mod(m.group(2), module):
                return True
            for item in (m.group(1) or "").split(","):
                name = item.split()[0] if item.split() else ""
                if _is_mod(name, module):
                    return True
    return False


def traceback_type(text: Optional[str]) -> Optional[str]:
    """Тип ошибки из последней непустой строки вывода — только из TRACEBACK_TYPES."""
    if not text:
        return None
    for line in reversed(text[-OUT_TAIL:].splitlines()):
        line = line.strip()
        if not line:
            continue
        m = _ERROR_LINE.match(line)
        return m.group(1) if m and m.group(1) in TRACEBACK_TYPES else None
    return None


def out_type(box) -> Optional[str]:
    """Тип ошибки из .termit/out.log — его пишет usercustomize песочницы (sandbox.OUT_LOG_HOOK)
    при падении «python3 файл.py». Файла нет, он старше последней команды игрока (ошибка
    прошлого запуска) или тип не из белого списка — None."""
    import os
    kind, text = envkit.box_text(box, OUT_LOG, OUT_CAP)
    if kind != "ok":
        return None
    since = last_stamp(box)
    try:
        if since is not None and os.lstat(Path(box) / OUT_LOG).st_mtime < since:
            return None
    except OSError:
        return None
    return traceback_type(text)


def last_stamp(box) -> Optional[float]:
    """Метка времени последней команды игрока (кроме команд игры) из cmds.log; нет — None."""
    from termit_app import hook, sandbox
    raw = sandbox.read_in_box(box, ".termit/cmds.log", sandbox.CMDS_CAP)
    for line in reversed((raw or b"").decode("utf-8", errors="replace").splitlines()):
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[2].split()[:1] and parts[2].split()[0] not in hook.SERVICE:
            try:
                return float(parts[0])
            except ValueError:
                return None
    return None


def runs_python(line: str) -> bool:
    """Запускает ли строка оболочки интерпретатор Python (по имени или по пути)."""
    return any(envkit.runs(seg, name) for seg in envkit.segments(line) for name in PYTHONS)


def last_command(box) -> Optional[Tuple[str, Optional[bool]]]:
    """Последняя команда игрока, кроме команд игры (ans, hint, loot… — hook.SERVICE, тот же
    список, что у песочного .zshrc): (строка, исход)."""
    from termit_app import hook
    for line, ok in reversed(envkit.journal(box)):
        words = line.split()
        if words and words[0] not in hook.SERVICE:
            return line, ok
    return None


_VENV_PY = re.compile(r"(?:^|/)\.venv\w*/bin/python[\d.]*$")


def activated(box) -> bool:
    """venv включён к концу журнала: последняя команда source/. …/activate не отменена
    deactivate; или python звали из .venv напрямую (.venv/bin/python). cat activate — не
    включение."""
    on = False
    for line, _ in envkit.journal(box):
        for seg in envkit.segments(line):
            _, cmd, args = envkit.lead(seg)
            if cmd in ("source", ".") and args and args[0].endswith("/activate"):
                on = True
            elif cmd == "deactivate":
                on = False
            elif cmd and _VENV_PY.search(cmd):
                return True
    return on


def apply_edits(text: str, edits: Sequence[Tuple[str, str]]) -> str:
    """Скелет с правками: строка с меткой (ровно одна) заменяется строкой правки с тем же
    отступом; у многострочной правки отступ получает каждая строка. Метки нет или их
    несколько — ValueError (ошибка задачи, P001)."""
    lines = text.split("\n")
    for mark, new in edits:
        hits = [i for i, ln in enumerate(lines) if has_mark(ln, mark)]
        if len(hits) != 1:
            raise ValueError(f"метка {mark!r} в скелете {len(hits)} раз")
        i = hits[0]
        indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
        lines[i:i + 1] = [indent + part if part else part for part in new.split("\n")]
    return "\n".join(lines)


def has_mark(line: str, mark: str) -> bool:
    """Метка в строке целиком: «# TODO 1» не совпадает с «# TODO 10» и «# TODO 1a»."""
    return re.search(re.escape(mark) + r"(?![\w])", line) is not None


INDENT_DOT = "·"
# расшифровка записи многострочной правки в одну строку (FB7: отступ не терять)
ONE_LINE_LEGEND = "(⏎ — новая строка)"
ONE_LINE_LEGEND_INDENT = "(⏎ — новая строка, · — пробел отступа)"


def _one_line(code: str) -> str:
    """Многострочная правка — одной строкой: строки через ⏎, а отступ каждой строки (от
    отступа метки) — точками ·: без них игрок перепечатывает тело функции или цикла без
    отступа и получает IndentationError (FB7)."""
    parts = []
    for line in code.split("\n"):
        body = line.lstrip(" ")
        parts.append(INDENT_DOT * (len(line) - len(body)) + body.rstrip())
    return " ⏎ ".join(parts)


class PyEditTask(Task):
    """«Поправь скрипт»: в песочнице — скелет script с метками # TODO, игрок вписывает
    строки и запускает run; проверка — по файлам outputs (check_outputs подкласса).

    Подкласс задаёт prepare (данные), skeleton и edits; при желании — requires_import
    (скрипт обязан импортировать эти модули: регулярка по тексту, задача скрытая — P003) и
    venv_modules (пакеты из .venv: при падении без activate — отклик про окружение)."""
    py_edit = True                  # признак для линтера (P001, D005 skip) без импорта pykit
    tool = "python"                 # инструмент задачи для значка (icons.tool_of): эталона нет
    pinned_python = True
    script = "report.py"
    run = "python3 report.py"       # без полей: идёт в тексты как есть
    outputs: Sequence[str] = ()
    requires_import: Sequence[str] = ()
    venv_modules: Sequence[str] = ()
    reads_py = False                # проверка читает .py сама (кроме requires_import)
    # совет задачи на тип ошибки из .termit/out.log (белый список): {тип: текст} — вместо
    # общего «скрипт упал» (IndentationError в цикле, KeyError у словаря…)
    crash_tips: Dict[str, str] = {}
    secret_keys = ("expect", "traps")

    # --- данные --------------------------------------------------------------------------

    def prepare(self, box: Path, rng, variant: int) -> dict:
        return {}

    def skeleton(self, state: dict) -> str:
        raise NotImplementedError

    def edits(self, state: dict) -> List[Tuple[str, str]]:
        raise NotImplementedError

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        state = dict(self.prepare(Path(box), rng, variant))
        state.setdefault("_variant", variant)
        kit.write(Path(box) / self.script, self.skeleton(state))
        return state

    def solved_text(self, state: dict) -> str:
        return apply_edits(self.skeleton(state), self.edits(state))

    def reads_script(self) -> bool:
        """Читает ли проверка .py (тогда задача обязана быть скрытой, P003)."""
        return bool(self.reads_py or self.requires_import)

    # --- тексты --------------------------------------------------------------------------

    def edit_text(self, state: dict) -> str:
        """`# TODO 1` → `строка`; … — одна строка (подсказка 3 и разбор)."""
        text = "; ".join(f"`{mark}` → `{_one_line(new)}`" for mark, new in self.edits(state))
        if " ⏎ " not in text:
            return text
        legend = ONE_LINE_LEGEND_INDENT if INDENT_DOT in text else ONE_LINE_LEGEND
        return f"{text} {legend}"

    def hints_for(self, state: dict) -> List[str]:
        """Две подсказки задачи (с полями) и третья — точная правка из edits."""
        v = self.variant(state)
        given = list(self.hints if v.hints is None else v.hints)
        if len(given) >= 3:
            return _fmt(given, state)
        return _fmt(given[:2], state) + [f"nano {self.script}: {self.edit_text(state)}; "
                                         f"{self.run}"]

    def shown_solution(self, state: dict) -> str:
        v = self.variant(state)
        if v.solution is not None or self.solution:
            return super().shown_solution(state)
        return f"nano {self.script}: {self.edit_text(state)}; {self.run}"

    def reference(self, state: dict) -> str:
        v = self.variant(state)
        if v.solution_script is not None or self.solution_script:
            return super().reference(state)
        body = self.solved_text(state).rstrip("\n")
        return f"cat > {self.script} <<'{HEREDOC}'\n{body}\n{HEREDOC}\n{self.run}\n"

    def missing(self, root=None) -> Optional[str]:
        """Интерпретатор треков (pinned_python, base) и, у задачи с журналом учебного API
        (needs_judge), — путь сокета, который влезает в sun_path (как у curl_api)."""
        why = super().missing(root)
        if why or not self.needs_judge:
            return why
        from termit_app import apiserver, sandbox   # длина пути — как у самой длинной песочницы
        if not apiserver.path_fits(sandbox.sample_box(root)):
            return MSG_LONG_PATH
        return None

    # --- проверка ------------------------------------------------------------------------

    def outputs_for(self, state: dict) -> List[str]:
        return list(self.outputs)

    def check_outputs(self, ctx: Ctx) -> Verdict:
        """Разбор файлов outputs (они есть и обычные): подкласс."""
        raise NotImplementedError

    def crash_message(self, ctx: Ctx) -> Optional[str]:
        """Последняя команда — python3 …, и она не удалась: совет читать traceback (тип —
        из белого списка, если есть .termit/out.log); пакет venv без activate — про .venv."""
        last = last_command(ctx.box)
        if last is None or not runs_python(last[0]):
            return None
        typ = out_type(ctx.box)
        # исход неизвестен (rc.log нет), но в выводе — ошибка из белого списка: тоже падение
        if last[1] is not False and not (last[1] is None and typ):
            return None
        if typ in self.crash_tips:
            return self.crash_tips[typ]
        if typ == "ModuleNotFoundError" or (typ is None and self.venv_modules
                                            and not activated(ctx.box)):
            return MSG_MODULE
        return MSG_TRACEBACK_TYPE.format(typ=typ) if typ else MSG_TRACEBACK

    def redirect_message(self, ctx: Ctx, rel: str) -> Optional[str]:
        """M5 ревью Q3: файла rel нет, а последняя команда — удачный (rc 0) запуск без «>»
        (вывод ушёл на экран): отклик по форме — куда ждут результат. Только у задач, чей run
        сам пишет в файл через «>»."""
        if ">" not in self.run:
            return None
        last = last_command(ctx.box)
        if last is None or last[1] is not True or not runs_python(last[0]):
            return None
        if self.script not in last[0] or ">" in last[0]:
            return None
        return MSG_NO_REDIRECT.format(out=rel, run=self.run)

    def untouched_message(self, ctx: Ctx) -> Optional[str]:
        """FB7: последняя команда запускала скрипт, а он слово в слово как скелет — игрок не
        вписал ни одной строки. Отклик про это понятнее «Не то число» или общего traceback."""
        last = last_command(ctx.box)
        # запускают сам скрипт или того, кто его зовёт (py_func: правят mylib.py, а запуск —
        # python3 report.py)
        names = {self.script, *re.findall(r"[\w.-]+\.py", self.run)}
        if last is None or not runs_python(last[0]) or not any(n in last[0] for n in names):
            return None
        kind, text = py_text(ctx, self.script)
        if kind != "ok" or text != self.skeleton(ctx.state):
            return None
        return MSG_UNTOUCHED.format(script=self.script, run=self.run)

    def first_problem(self, ctx: Ctx) -> Optional[str]:
        """Отклик на неудачный запуск: окружение без пакета — первым (пока .venv не включён,
        правка скрипта не поможет), затем «скрипт не тронут», затем совет по traceback."""
        crash = self.crash_message(ctx)
        if crash == MSG_MODULE:
            return crash
        return self.untouched_message(ctx) or crash

    def import_problem(self, ctx: Ctx) -> Optional[str]:
        if not self.requires_import:
            return None
        kind, text = py_text(ctx, self.script)
        if kind == "missing":
            return MSG_NO_SCRIPT.format(script=self.script)
        if kind == "big":
            return MSG_BIG_SCRIPT.format(script=self.script)
        if kind != "ok":
            return envkit.file_problem(kind, self.script)
        for mod in self.requires_import:
            if not imports(text, mod):
                return MSG_IMPORT.format(mod=mod, script=self.script)
        return None

    def check(self, ctx: Ctx) -> Verdict:
        for rel in self.outputs_for(ctx.state):
            kind, _ = envkit.box_file(ctx.box, rel)
            if kind == "missing":
                return Verdict(False, self.first_problem(ctx)
                               or self.redirect_message(ctx, rel))
            if kind != "ok":
                return Verdict(False, envkit.file_problem(kind, rel))
        problem = self.import_problem(ctx)
        if problem:
            return Verdict(False, problem)
        v = self.check_outputs(ctx)
        if v.solved:
            return v
        # «> total.txt» создаёт файл до запуска: упавший скрипт оставляет его пустым — отклик
        # про traceback (или .venv) важнее «файл пуст» (fix1 I1)
        return Verdict(False, self.first_problem(ctx) or v.message)


# --- числа в файлах вывода (правило 3: число — как число) -----------------------------------

def as_num(text) -> Optional[float]:
    """Число из строки: «75560», «75560.0», «12,5»; inf, nan, 1e400 — не число (None)."""
    import math
    from termit_app import textnorm
    if text is None:
        return None
    g = textnorm.as_number(str(text))
    return g if g is not None and math.isfinite(g) else None


def same_num(given, expected) -> bool:
    """Число ответа: целое — точно (75560.0 = 75560), дробное — с допуском 0,005."""
    g = as_num(given)
    if g is None:
        return False
    e = float(expected)
    if e != int(e) or g != int(g):
        return abs(g - e) <= 0.005 + 1e-9
    return g == e


def last_value(text: Optional[str]) -> str:
    """Значение из вывода скрипта: последняя непустая строка, после последнего «:» или «=»
    («total: 86.45» → «86.45»). Линейно."""
    lines = [x.strip() for x in (text or "").split("\n") if x.strip()]
    if not lines:
        return ""
    line = lines[-1]
    for sep in (":", "="):
        if sep in line:
            line = line.rsplit(sep, 1)[1]
    return line.strip()


def decimals(value: str) -> int:
    """Сколько знаков после точки в записи числа («86.4499» → 4, «12» → 0)."""
    v = value.strip()
    if "e" in v.lower() or "." not in v:
        return 0
    return len(v.split(".", 1)[1])


def pairs(text: Optional[str], limit: int = 500) -> Tuple[dict, List[str]]:
    """Строки «имя=число» вывода: ({имя: значение-строка}, [строки не в этой форме]).
    Больше limit строк — разбираем только первые limit (вывод задачи — десяток строк)."""
    got, bad = {}, []
    for line in (text or "").split("\n")[:limit]:
        line = line.strip()
        if not line:
            continue
        if "=" not in line:
            bad.append(line)
            continue
        name, value = line.split("=", 1)
        got[name.strip()] = value.strip()
    return got, bad


# --- данные задач трека py (Q2): строки генераторов и ответы, посчитанные по ним ------------

ITEMS = ("tea", "cake", "jam", "milk", "bread", "honey", "rice", "salt", "soap", "lamp",
         "pen", "cup")
CATS = ("food", "home", "books", "games", "tools", "toys")
GREETS = ("hello", "privet", "salut", "hola", "ciao", "hej")


def run_data(rng) -> dict:
    """py_run: hello.py, count.py (сумма второй колонки файла), orders.txt и broken.py.
    Ответы: сумма (A), «Тип строка» ошибки (B), число выражения (C) — по строкам генератора."""
    greet = f"{rng.choice(GREETS)}, {kit.latin(rng)}"
    n = rng.randint(18, 28)
    amounts = [rng.randint(10, 990) for _ in range(n)]
    orders = [f"A-{100 + i} {a}" for i, a in enumerate(amounts)]
    broken, err_type, err_line, call_line = broken_script(rng)
    a, b = rng.randint(12, 29), rng.randint(13, 31)
    k = rng.randint(2, 99)
    return {"greet": greet, "orders": orders, "total": sum(amounts), "lines": n,
            "broken": broken, "err_type": err_type, "err_line": err_line,
            "call_line": call_line, "a": a, "b": b, "k": k, "expr": a * b + k,
            "wrong_order": a * (b + k)}


HELLO_PY = '# hello.py — первый скрипт\nprint("{greet}")\n'
COUNT_PY = ("# count.py — сумма заказов из файла: python3 count.py ФАЙЛ\n"
            "import sys\n"
            "\n"
            "total = 0\n"
            "for line in open(sys.argv[1]):\n"
            "    total += int(line.split()[1])\n"
            "print(total)\n")

# скрипт, что падает внутри функции: (тип ошибки, строки тела функции с меткой ошибки «!»,
# строки после функции с меткой вызова «>»)
_BROKEN = (
    ("NameError", "total", ["def total(rows):", "    s = 0", "    for r in rows:",
                            "        s += r", "!    return s + bonus"],
     ["rows = [{x}, {y}, {z}]", ">print(total(rows))"]),
    ("KeyError", "price_of", ["def price_of(name):", '    prices = {{"tea": {x}, "cake": {y}}}',
                              "!    return prices[name]"],
     ['>print(price_of("{item}"))']),
    ("ZeroDivisionError", "average", ["def average(rows):", "    s = sum(rows)",
                                      "!    return s / len(rows)"],
     ["rows = []", ">print(average(rows))"]),
    ("IndexError", "pick", ["def pick(rows, n):", "!    return rows[n]"],
     ["rows = [{x}, {y}, {z}]", ">print(pick(rows, {far}))"]),
)


def broken_script(rng) -> Tuple[str, str, int, int]:
    """broken.py: (текст, тип ошибки, строка ошибки, строка вызова). Ошибка — внутри функции,
    поэтому в traceback две строки «line»: вызов (выше) и сама ошибка (последняя)."""
    typ, _, body, tail = rng.choice(_BROKEN)
    fill = {"x": rng.randint(10, 99), "y": rng.randint(10, 99), "z": rng.randint(10, 99),
            "item": rng.choice(("jam", "milk", "honey")), "far": rng.randint(5, 9)}
    lines = ["# broken.py — скрипт с ошибкой: запусти и прочти traceback"]
    lines += ["# " + x for x in rng.sample(("считает по списку", "версия 2", "не трогать",
                                             "проверено вчера"), rng.randint(0, 2))]
    lines.append("")
    err = call = 0
    for chunk in (body, [""] * rng.randint(1, 2), tail):
        for raw in chunk:
            mark = raw[:1] if raw[:1] in "!>" else ""
            text = (raw[1:] if mark else raw).format(**fill)
            lines.append(text)
            if mark == "!":
                err = len(lines)
            elif mark == ">":
                call = len(lines)
    return "\n".join(lines) + "\n", typ, err, call


def _messy(raw: float) -> bool:
    """Неокруглённое число и правда «длинное»: в записи больше 2 знаков после точки, и оно не
    у границы полкопейки (…5): там round по разным формулам расходится на копейку."""
    frac = (raw * 100) % 1
    return (decimals(repr(raw)) > 2 and abs(raw - round(raw, 2)) > 1e-6
            and abs(frac - 0.5) > 0.02)


def vars_data(rng, variant: int) -> dict:
    """py_vars: A — цена × вес, B — цена × штуки со скидкой (обе — до 2 знаков, неокруглённое
    число гарантированно длинное), C — сумма двух чисел из input.txt (склейка текста ≠ сумма)."""
    if variant == 2:
        mon, tue = rng.randint(12, 89), rng.randint(12, 89)
        return {"monday": mon, "tuesday": tue, "expect": mon + tue,
                "traps": [["glued", f"{mon}{tue}"]]}
    while True:
        price = rng.randint(101, 9999) / 100
        if variant == 0:
            weight = rng.randint(1001, 4999) / 1000
            raw = price * weight
            extra = {"weight": f"{weight:.3f}"}
        else:
            qty = rng.randint(3, 19)
            disc = rng.choice((5, 15, 25, 35, 45))
            raw = price * qty * (100 - disc) / 100
            alt = price * qty * (1 - disc / 100)
            extra = {"qty": qty, "discount": disc}
        if _messy(raw):
            break
    traps = [["unrounded", repr(raw)]]
    if variant == 1 and _messy(alt) and repr(alt) != repr(raw):
        traps.append(["unrounded", repr(alt)])
    return dict(extra, price=f"{price:.2f}", expect=round(raw, 2), traps=traps)


def loop_data(rng, variant: int) -> dict:
    """py_loop: A — сумма чисел больше limit (ровно limit в списке есть: > против >=), B —
    сколько нулей (ловушка — число ненулевых), C — наибольшее без max() (первое число списка —
    не наибольшее и не наименьшее; ловушки — наименьшее и первое)."""
    n = rng.randint(9, 12)
    if variant == 0:
        limit = rng.randint(15, 35) * 10
        values = [limit] * rng.randint(1, 2)
        values += [rng.randint(limit + 1, 500) for _ in range(2)]
        values += [rng.randint(10, limit - 1) for _ in range(2)]
        values += [rng.randint(10, 500) for _ in range(n - len(values))]
        rng.shuffle(values)
        return {"amounts": values, "limit": limit,
                "expect": sum(a for a in values if a > limit),
                "traps": [["ge", sum(a for a in values if a >= limit)]]}
    if variant == 1:
        zeros = rng.randint(2, 4)
        values = [0] * zeros + [rng.randint(1, 90) for _ in range(n - zeros)]
        rng.shuffle(values)
        return {"amounts": values, "expect": zeros, "traps": [["nonzero", n - zeros]]}
    values = rng.sample(range(10, 999), n)
    while values[0] in (max(values), min(values)):
        rng.shuffle(values)
    return {"amounts": values, "expect": max(values),
            "traps": [["min", min(values)], ["first", values[0]]]}


def dict_data(rng, variant: int) -> dict:
    """py_dict: A — сколько штук каждого товара, B — сумма по категориям, C — стоимость по
    товарам по справочнику (товара нет в справочнике — 0). Постройкой каждый ответ отличается
    от «затёртого» словаря (значение без накопления): есть ключ, что встречается дважды."""
    if variant == 0:
        names = rng.sample(ITEMS, rng.randint(4, 5))
        buys = list(names) + [rng.choice(names) for _ in range(rng.randint(6, 9))]
        rng.shuffle(buys)
        want = {k: buys.count(k) for k in names}
        last = {k: 1 for k in names}
        return {"buys": buys, "expect": want, "traps": [["overwrite_a", last]]}
    if variant == 1:
        cats = rng.sample(CATS, rng.randint(3, 4))
        rows = [(c, rng.randint(10, 500)) for c in cats for _ in range(2)]
        rows += [(rng.choice(cats), rng.randint(10, 500)) for _ in range(rng.randint(2, 4))]
        rng.shuffle(rows)
        want, last = {}, {}
        for c, a in rows:
            want[c] = want.get(c, 0) + a
            last[c] = a
        return {"rows": rows, "expect": want, "traps": [["overwrite_b", last]]}
    names = rng.sample(ITEMS, 6)
    priced, unknown = names[:4], names[4:4 + rng.randint(1, 2)]
    prices = {k: rng.randint(10, 99) for k in priced}
    buys = list(priced) + list(unknown) + [rng.choice(priced) for _ in range(rng.randint(3, 5))]
    rng.shuffle(buys)
    want, last = {}, {}
    for k in buys:
        want[k] = want.get(k, 0) + prices.get(k, 0)
        last[k] = prices.get(k, 0)
    return {"prices": prices, "buys": buys, "expect": want, "traps": [["overwrite_c", last]]}


def func_data(rng, variant: int) -> dict:
    """py_func: суммы заказов и ставка комиссии. A — fee(amount) по RATE, B — fee(amount,
    rate) со ставкой у каждого заказа, C — total_fee(amounts): сумма fee по всем. Ответ —
    {сумма: комиссия} (A, B) или {"total": сумма} (C); ловушки — без «/ 100» (A, B) и сумма
    самих заказов (C)."""
    amounts = rng.sample(range(100, 5000), rng.randint(5, 7))
    if variant == 1:
        rates = [rng.randint(2, 9) for _ in amounts]
        want = {str(a): round(a * r / 100, 2) for a, r in zip(amounts, rates)}
        raw = {str(a): a * r for a, r in zip(amounts, rates)}
        return {"orders": [[a, r] for a, r in zip(amounts, rates)], "expect": want,
                "traps": [["percent", raw]]}
    rate = rng.randint(2, 9)
    if variant == 0:
        return {"amounts": amounts, "rate": rate,
                "expect": {str(a): round(a * rate / 100, 2) for a in amounts},
                "traps": [["percent", {str(a): a * rate for a in amounts}]]}
    s = 0
    for a in amounts:
        s += round(a * rate / 100, 2)
    return {"amounts": amounts, "rate": rate, "expect": {"total": round(s, 2)},
            "traps": [["no_fee", {"total": sum(amounts)}]]}


# --- py_repl: учебные пакеты игры (их исходники — termit_app/pylibs/src, не код игрока) ------

# что кладёт в пространство имён пакета сам import (dir() их показывает)
IMPORT_DUNDERS = ("__builtins__", "__cached__", "__doc__", "__file__", "__loader__",
                  "__name__", "__package__", "__path__", "__spec__")
# (модуль, что считать): «public» — имена без _ в начале, «private» — с одним _ (не __).
# Ответы разные по зерну (fix1 I1): tabprint 4/3, sockhttp 17/4 — три разных ответа (у
# datapeek публичных тоже 4: он только сдвинул бы долю четвёрки)
REPL_COUNTS = (("tabprint", "public"), ("sockhttp", "public"), ("tabprint", "private"),
               ("sockhttp", "private"))
REPL_MODULES = ("tabprint", "datapeek", "sockhttp")
# (модуль, функция, номер параметра с 1): вопрос «как зовут N-й параметр». datapeek.summary
# (path, top) не берём: ответ «top» — слово служебных файлов песочницы (обёртка
# .termit/bin/top), охрана test_judge «ответа нет в служебных файлах»
REPL_FUNCS = (("tabprint", "table", 2), ("tabprint", "from_csv", 2), ("sockhttp", "get", 3),
              ("sockhttp", "get", 4), ("sockhttp", "post", 2), ("sockhttp", "install", 2))
NTH = {2: "второй", 3: "третий", 4: "четвёртый"}
# значение по умолчанию — ловушка, только если его можно сдать словом (',' оболочка съест)
_WORDLIKE = re.compile(r"^[A-Za-z0-9_.]+$")


def _pkg_tree(mod: str):
    import ast
    from termit_app.pylibs import SRC
    return ast.parse((Path(SRC) / mod / "__init__.py").read_text("utf-8"))


def module_names(mod: str) -> List[str]:
    """Имена, что покажет dir(mod) у учебного пакета: верхний уровень его __init__.py (def,
    class, import, присваивания) и то, что кладёт сам import (IMPORT_DUNDERS). Разбор
    исходника игры через ast — ничего не исполняется."""
    import ast
    names = set(IMPORT_DUNDERS)
    for node in _pkg_tree(mod).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return sorted(names)


def func_params(mod: str, fn: str) -> List[Tuple[str, Optional[str]]]:
    """Параметры функции учебного пакета: [(имя, значение по умолчанию как его печатает
    help() — repr литерала, или None)]. Не литерал (имя константы) — значения нет."""
    import ast
    for node in _pkg_tree(mod).body:
        if isinstance(node, ast.FunctionDef) and node.name == fn:
            args = node.args.args
            defaults = [None] * (len(args) - len(node.args.defaults))
            for d in node.args.defaults:
                try:
                    defaults.append(repr(ast.literal_eval(d)))
                except ValueError:
                    defaults.append(None)
            return [(a.arg, d) for a, d in zip(args, defaults)]
    raise KeyError(f"{mod}.{fn}")


def repl_data(rng, variant: int) -> dict:
    """py_repl: A — сколько в dir(модуль) публичных имён или имён с одним _ (по зерну; ловушки
    — счёт с __ и счёт не тех имён); B — имя N-го параметра функции (ловушки — первый и
    соседние параметры, значение по умолчанию);
    C — сколько записей в items.json (ловушка — число строк файла, indent=2)."""
    import json
    if variant == 0:
        mod, what = rng.choice(REPL_COUNTS)
        names = module_names(mod)
        under = [n for n in names if n.startswith("_")]
        if what == "public":
            answer = len(names) - len(under)
            wrong = [["underscore", len(names)],
                     ["underscore", len([n for n in names if not n.startswith("__")])]]
            ask, which, grep = ("публичных имён — тех, что без _ в начале", "без _ в начале",
                                "-vc '^_'")
        else:
            answer = len([n for n in under if not n.startswith("__")])
            wrong = [["dunder", len(under)], ["public", len(names) - len(under)]]
            ask, which, grep = ("имён с одним _ в начале (_имя, но не __имя__)",
                                "с одним _ в начале", "-c '^_[^_]'")
        traps, seen = [], {answer}
        for key, x in wrong:
            if x not in seen:
                seen.add(x)
                traps.append([key, x])
        return {"mod": mod, "what": what, "ask": ask, "which": which, "grep": grep,
                "answer": answer, "traps": traps}
    if variant == 1:
        mod, fn, pos = rng.choice(REPL_FUNCS)
        params = func_params(mod, fn)
        name, default = params[pos - 1]
        traps = [["first", params[0][0]]]
        traps += [["neighbor", params[k][0]] for k in (pos - 2, pos) if 0 < k < len(params)]
        if default is not None and _WORDLIKE.match(default):
            traps.append(["default", default])
        return {"mod": mod, "fn": fn, "first": params[0][0], "pos": pos, "nth": NTH[pos],
                "answer": name, "traps": traps}
    n = rng.randint(5, 12)
    names = rng.sample(ITEMS, min(n, len(ITEMS)))
    items = [{"name": names[i % len(names)], "qty": rng.randint(1, 40)} for i in range(n)]
    doc = {"updated": f"2026-{rng.randint(1, 9):02d}-{rng.randint(10, 28)}", "items": items}
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    return {"json": text, "answer": n, "traps": [["lines", text.count("\n")]]}


# --- файлы JSON и CSV из песочницы (Q3): разбор у родителя, без исполнения -------------------

MSG_JSON_EMPTY = "{out} пуст: допиши строки # TODO и запусти скрипт снова: {run}"
MSG_JSON_BROKEN = ("{out} — не JSON. Пиши его json.dump(…), а не print и не руками — и "
                   "запусти скрипт снова.")
MSG_JSON_REPR = ("В {out} — печать Python (одинарные кавычки), а не JSON: записывай "
                 "json.dump(x, f), а не print(x) или str(x).")
MSG_JSON_DEEP = "{out} вложен слишком глубоко — это не файл задачи. Набери reset."
MSG_JSON_ASCII = ("Кириллица в {out} — кодами \\u…: допиши в json.dump ensure_ascii=False — и "
                  "буквы останутся буквами.")
MSG_JSON_INDENT = ("{out} — одной строкой: допиши в json.dump indent=2 — каждая запись с новой "
                   "строки.")


def _looks_repr(text: str) -> bool:
    """Печать Python вместо JSON: начинается со скобки и ключи в одинарных кавычках."""
    t = text.lstrip()
    return t[:1] in "[{" and ("{'" in t or "': " in t or "['" in t)


def read_json(box, rel: str, run: str = "") -> Tuple[Optional[object], Optional[str], str]:
    """Файл JSON вывода: (объект, отклик, текст). Объект None — отклик говорит, что не так:
    ссылка, FIFO, слишком большой (envkit), пустой, глубокий, печать Python или просто не
    JSON. Разбор json у родителя (глубина ≤ 64), код не исполняется."""
    kind, text = envkit.box_text(box, rel, envkit.READ_CAP)
    if kind != "ok":
        return None, envkit.file_problem(kind, rel), ""
    jk, doc = envkit.load_json(text)
    if jk == "empty":
        return None, MSG_JSON_EMPTY.format(out=rel, run=run), text
    if jk == "deep":
        return None, MSG_JSON_DEEP.format(out=rel), text
    if jk == "broken":
        msg = MSG_JSON_REPR if _looks_repr(text) else MSG_JSON_BROKEN
        return None, msg.format(out=rel), text
    return doc, None, text


def json_form(text: str, rel: str, cyrillic: bool) -> Optional[str]:
    """Форма записи JSON: с отступами (indent) и, если в данных кириллица, — буквами, а не
    кодами \\u (ensure_ascii=False). Вид файла, а не верность данных."""
    if cyrillic and "\\u04" in text:
        return MSG_JSON_ASCII.format(out=rel)
    if "\n " not in text.strip():
        return MSG_JSON_INDENT.format(out=rel)
    return None


# --- py_json: заказы словарь → список → словарь ---------------------------------------------

CITIES_RU = ("Казань", "Омск", "Тверь", "Пермь", "Сочи", "Уфа", "Курск", "Самара")
STATUSES = ("paid", "new", "cancelled")


def orders_doc(rng) -> dict:
    """orders.json: {"shop", "updated", "orders": [{"id", "cust", "city" (кириллица),
    "status", "items": [{"name", "price", "qty"}]}]}. Постройкой: оплаченных и прочих — не
    меньше двух, у какой-то позиции qty ≥ 2 (цена без количества ≠ сумма)."""
    n = rng.randint(6, 9)
    paid_n = rng.randint(2, n - 2)
    statuses = ["paid"] * paid_n + [rng.choice(STATUSES[1:]) for _ in range(n - paid_n)]
    rng.shuffle(statuses)
    orders = []
    for i, status in enumerate(statuses):
        names = rng.sample(ITEMS, rng.randint(1, 3))
        items = [{"name": x, "price": rng.randint(20, 900), "qty": rng.randint(1, 5)}
                 for x in names]
        orders.append({"id": f"A-{101 + i}", "cust": kit.latin(rng),
                       "city": rng.choice(CITIES_RU), "status": status, "items": items})
    if all(it["qty"] == 1 for o in orders for it in o["items"]):
        orders[rng.randrange(n)]["items"][0]["qty"] = rng.randint(2, 5)
    day = f"2026-{rng.randint(1, 9):02d}-{rng.randint(10, 28)}"
    return {"shop": kit.latin(rng), "updated": day, "orders": orders}


def json_data(rng, variant: int) -> dict:
    """py_json: A — оплаченные заказы списком (ловушки: все заказы, неоплаченные); B — сумма
    каждого заказа {id: Σ price×qty} (ловушка: Σ price без количества); C — ключ cust →
    customer во всём документе (ловушка: старый ключ остался). Ответ — объект для сравнения
    разобранного."""
    import copy
    import json
    doc = orders_doc(rng)
    orders = doc["orders"]
    st = {"json": json.dumps(doc, indent=2, ensure_ascii=False) + "\n"}
    if variant == 0:
        st.update(expect=[o for o in orders if o["status"] == "paid"],
                  traps=[["all", orders],
                         ["unpaid", [o for o in orders if o["status"] != "paid"]]])
    elif variant == 1:
        st.update(expect={o["id"]: sum(it["price"] * it["qty"] for it in o["items"])
                          for o in orders},
                  traps=[["price_only", {o["id"]: sum(it["price"] for it in o["items"])
                                         for o in orders}]])
    else:
        want, both = copy.deepcopy(doc), copy.deepcopy(doc)
        for o, b in zip(want["orders"], both["orders"]):
            o["customer"] = o.pop("cust")
            b["customer"] = b["cust"]
        st.update(expect=want, traps=[["both", both]])
    return st


# --- py_csv_json: CSV ↔ JSON, поле с запятой в кавычках ---------------------------------------

CSV_CITIES = ("Kazan", "Omsk", "Tver", "Perm", "Sochi", "Ufa", "Kursk")
COMMA_ITEMS = ("tea, green", "jam, cherry", "milk, oat", "bread, rye", "rice, long")
CSV_ROWS_CAP = 5000             # строк в CSV вывода больше — это не файл задачи
MSG_CSV_EMPTY = "{out} пуст: допиши строки # TODO и запусти скрипт снова: {run}"
MSG_CSV_BROKEN = ("{out} не читается как CSV. Пиши его через csv.DictWriter — и запусти "
                  "скрипт снова.")


def csv_text(rows: List[List[object]]) -> str:
    """CSV, как его пишет модуль csv (поле с запятой — в кавычках)."""
    import csv
    import io
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def read_csv(box, rel: str, run: str = "") -> Tuple[Optional[List[List[str]]], Optional[str]]:
    """CSV вывода: (строки без пустых, None) или (None, отклик). Разбор модулем csv у
    родителя — линейно, не больше CSV_ROWS_CAP строк (файл — не больше 4 МБ)."""
    import csv
    import io
    kind, text = envkit.box_text(box, rel, envkit.READ_CAP)
    if kind != "ok":
        return None, envkit.file_problem(kind, rel)
    if not text.strip():
        return None, MSG_CSV_EMPTY.format(out=rel, run=run)
    rows = []
    try:
        for row in csv.reader(io.StringIO(text, newline="")):
            if any(x.strip() for x in row):
                rows.append(row)
                if len(rows) > CSV_ROWS_CAP:
                    return None, MSG_CSV_BROKEN.format(out=rel)
    except csv.Error:
        return None, MSG_CSV_BROKEN.format(out=rel)
    return rows, None


def _naive(line: str, head: List[str]) -> dict:
    return dict(zip(head, line.split(",")))


def csv_data(rng, variant: int) -> dict:
    """py_csv_json: A — sales.csv → список словарей (ловушка: строки, разрезанные split по
    запятой); B — stock.json → CSV с шапкой (ловушка: без шапки); C — sales.csv + колонка
    total = price × qty (ловушка: текст цены, повторённый qty раз). Постройкой в каждом
    файле есть поле с запятой в кавычках, а в C — строка с qty ≥ 2."""
    n = rng.randint(5, 8)
    names = [rng.choice(ITEMS) for _ in range(n)]
    for i in rng.sample(range(n), rng.randint(1, 2)):
        names[i] = rng.choice(COMMA_ITEMS)
    if variant == 0:
        head = ["id", "city", "item", "amount"]
        rows = [[f"S-{201 + i}", rng.choice(CSV_CITIES), names[i], str(rng.randint(10, 900))]
                for i in range(n)]
        text = csv_text([head] + rows)
        return {"file": text, "expect": [dict(zip(head, r)) for r in rows],
                "traps": [["split", [_naive(x, head) for x in text.splitlines()[1:]]]]}
    if variant == 1:
        head = ["name", "city", "qty"]
        recs = [{"name": names[i], "city": rng.choice(CSV_CITIES), "qty": rng.randint(1, 60)}
                for i in range(n)]
        rows = [[r["name"], r["city"], str(r["qty"])] for r in recs]
        return {"recs": recs, "head": head, "expect": [head] + rows,
                "traps": [["no_header", rows]]}
    head = ["id", "item", "price", "qty"]
    raw = [[f"S-{201 + i}", names[i], rng.randint(10, 99), rng.randint(1, 6)] for i in range(n)]
    if all(r[3] == 1 for r in raw):
        raw[rng.randrange(n)][3] = rng.randint(2, 6)
    rows = [[str(x) for x in r] for r in raw]
    pq = [(r[2], r[3]) for r in raw]
    return {"file": csv_text([head] + rows),
            "expect": [head + ["total"]] + [r + [str(p * q)] for r, (p, q) in zip(rows, pq)],
            "traps": [["repeat", [head + ["total"]] + [r + [str(p) * q]
                                                         for r, (p, q) in zip(rows, pq)]]]}


# --- py_files: pathlib, glob/rglob, размер, re.search ------------------------------------------

LOG_WORDS = ("disk", "cache", "sync", "queue", "login", "upload", "backup", "report", "worker")
LOG_SUBDIRS = ("api", "web", "jobs", "db", "mail")


def _log_text(rng, lines: int) -> str:
    out = []
    for _ in range(lines):
        out.append(f"10:{rng.randint(10, 59)} {rng.choice(LOG_WORDS)} "
                   f"{rng.choice(LOG_WORDS)} ok {rng.randint(1, 999)}")
    return "\n".join(out) + "\n"


def files_data(rng, variant: int) -> dict:
    """py_files: A — суммарный размер *.log в logs/ с подпапками (ловушки: только верхний
    уровень — glob; все файлы, и .txt тоже); B — сколько строк app.log с кодом E и три цифры
    где угодно (ловушки: только с начала строки — re.match; все строки с буквой E); C —
    отчёты reports/report-ДАТА.txt старше cutoff (ловушки: вместе с днём cutoff — <=; новые).
    files — {путь: текст}; размеры считаются по байтам текста."""
    files = {}
    if variant == 0:
        for sub in [""] + rng.sample(LOG_SUBDIRS, 2):
            folder = f"logs/{sub}/" if sub else "logs/"
            for i in range(rng.randint(1, 2) + (1 if not sub else 0)):
                files[f"{folder}{rng.choice(LOG_WORDS)}-{i + 1}.log"] = _log_text(
                    rng, rng.randint(2, 9))
        files["logs/readme.txt"] = "логи сервиса: *.log — по папкам\n"
        files[f"logs/{rng.choice(LOG_SUBDIRS)}/notes.txt"] = _log_text(rng, rng.randint(1, 3))
        size = {k: len(v.encode("utf-8")) for k, v in files.items()}
        logs = sum(n for k, n in size.items() if k.endswith(".log"))
        top = sum(n for k, n in size.items() if k.endswith(".log") and k.count("/") == 1)
        return {"files": files, "expect": logs,
                "traps": [["glob", top], ["all", sum(size.values())]]}
    if variant == 1:
        start, middle, near, plain = (rng.randint(1, 3), rng.randint(1, 4), rng.randint(1, 3),
                                      rng.randint(3, 6))
        kinds = ["start"] * start + ["middle"] * middle + ["near"] * near + ["plain"] * plain
        rng.shuffle(kinds)
        lines = []
        for k in kinds:
            code = f"E{rng.randint(100, 999)}"
            word = rng.choice(LOG_WORDS)
            if k == "start":
                lines.append(f"{code} {word} failed")
            elif k == "middle":
                lines.append(f"10:{rng.randint(10, 59)} {word} {code} failed")
            elif k == "near":
                lines.append(rng.choice((f"10:{rng.randint(10, 59)} Every {word} ok",
                                         f"E{rng.randint(10, 99)} {word} slow",
                                         f"10:{rng.randint(10, 59)} Error budget ok")))
            else:
                lines.append(f"10:{rng.randint(10, 59)} {word} ok")
        files["app.log"] = "\n".join(lines) + "\n"
        return {"files": files, "expect": start + middle,
                "traps": [["match", start], ["letter_e", start + middle + near]]}
    days = sorted(rng.sample(range(1, 200), rng.randint(6, 9)))
    import datetime
    iso = [(datetime.date(2026, 1, 1) + datetime.timedelta(days=d)).isoformat() for d in days]
    cut = rng.randint(2, len(iso) - 2)
    cutoff = iso[cut]
    names = [f"report-{d}.txt" for d in iso]
    for name in names:
        files[f"reports/{name}"] = f"отчёт {name[7:17]}\n"
    files["reports/readme.md"] = "отчёты по дням: report-ГГГГ-ММ-ДД.txt\n"
    return {"files": files, "cutoff": cutoff, "expect": names[:cut],
            "traps": [["le", names[:cut + 1]], ["newer", names[cut + 1:]]]}


# --- py_stats: Counter, statistics, даты ------------------------------------------------------

def stats_data(rng, variant: int) -> dict:
    """py_stats: A — три самых частых товара по порядку (счёты все разные — ничьих нет;
    ловушка: первые три по алфавиту); B — медиана и среднее чеков (число чеков чётное, сумма
    двух серединных нечётная: медиана — с .5; ловушки — верхняя и нижняя середина, середина
    неотсортированного списка); C — дней между самой ранней и самой поздней датой (ловушки:
    первая и последняя по порядку списка, «+1»)."""
    import datetime
    if variant == 0:
        while True:
            names = rng.sample(ITEMS, rng.randint(5, 6))
            counts = rng.sample(range(1, 10), len(names))
            pairs = sorted(zip(names, counts), key=lambda x: -x[1])
            top = [[n, c] for n, c in pairs[:3]]
            alpha = [[n, dict(pairs)[n]] for n in sorted(names)[:3]]
            if alpha != top:
                break
        sales = [n for n, c in pairs for _ in range(c)]
        rng.shuffle(sales)
        return {"sales": sales, "expect": top, "traps": [["alpha", alpha]]}
    if variant == 1:
        while True:
            n = rng.choice((8, 10, 12))
            checks = rng.sample(range(100, 2000), n)
            s = sorted(checks)
            lo, hi = s[n // 2 - 1], s[n // 2]
            mean = round(sum(checks) / n, 2)
            if ((lo + hi) % 2 and checks[n // 2] not in (lo, hi)
                    and abs(mean - (lo + hi) / 2) > 1):
                break
        return {"checks": checks, "expect": {"median": (lo + hi) / 2, "mean": mean},
                "traps": [["upper", hi], ["lower", lo], ["unsorted", checks[n // 2]]]}
    # ловушки «от первой в списке до последней» нет (M6 ревью Q3): скелет уже даёт min и max
    base = datetime.date(2026, 1, 1)
    offs = rng.sample(range(0, 300), rng.randint(6, 9))
    days = [(base + datetime.timedelta(days=d)).isoformat() for d in offs]
    iso = datetime.date.fromisoformat
    span = (iso(max(days)) - iso(min(days))).days
    return {"days": days, "expect": span, "traps": [["plus_one", span + 1]]}


# --- py_urllib и boss_py: остатки на учебном API (обработчик A5, журнал запросов) ------------

URLLIB_AGENT = "Python-urllib/"      # User-Agent запросов urllib (версия — после «/»)


def stock_items(rng, n: int) -> List[dict]:
    """Остатки склада: [{"name", "city", "qty"}], в каждом городе — не меньше двух строк."""
    cities = rng.sample(CSV_CITIES, rng.randint(3, 4))
    rows = [{"name": rng.choice(ITEMS), "city": c, "qty": rng.randint(1, 90)}
            for c in cities for _ in range(2)]
    rows += [{"name": rng.choice(ITEMS), "city": rng.choice(cities), "qty": rng.randint(1, 90)}
             for _ in range(max(0, n - len(rows)))]
    rng.shuffle(rows)
    return rows


def stock_handler(items: List[dict], per_page: int):
    """Обработчик GET /stock учебного API: ?city=ГОРОД — фильтр, ?page=N — страница (по
    per_page строк); ответ {"page", "next" (номер следующей или null), "items"}. Чужая
    страница — 404, не число — 400. Данные — из state задачи, из песочницы ничего не читает."""
    import math

    def handle(req):
        city = (req.query.get("city") or [None])[0]
        rows = [x for x in items if city is None or x["city"] == city]
        raw = (req.query.get("page") or ["1"])[0]
        if not raw.isdigit():
            return 400, {"error": "page — номер страницы: ?page=1"}
        page, pages = int(raw), max(1, math.ceil(len(rows) / per_page))
        if not 1 <= page <= pages:
            return 404, {"error": "нет такой страницы", "pages": pages}
        chunk = rows[(page - 1) * per_page:page * per_page]
        return 200, {"page": page, "next": page + 1 if page < pages else None, "items": chunk}
    return handle


def stock_routes(state: dict) -> dict:
    """Маршруты API задачи: / — подсказка, /stock — обработчик по state."""
    return {"/": (200, {"routes": ["/stock", "/stock?page=N", "/stock?city=ГОРОД"]}),
            "/stock": stock_handler(state["stock"], state["per_page"])}


def urllib_data(rng, variant: int) -> dict:
    """py_urllib: A — все остатки одной страницей; B — только город city (?city=; ловушка —
    все города); C — две страницы, склеить (ловушка — только первая). Ответ — список строк в
    stock.json; журнал API — запросы от urllib (User-Agent Python-urllib/…)."""
    n = rng.randint(7, 10)
    items = stock_items(rng, n)
    if variant == 0:
        return {"stock": items, "per_page": 100, "expect": items, "traps": []}
    if variant == 1:
        city = rng.choice(sorted({x["city"] for x in items}))
        want = [x for x in items if x["city"] == city]
        return {"stock": items, "per_page": 100, "city": city, "expect": want,
                "traps": [["all", items]]}
    per = (len(items) + 1) // 2
    return {"stock": items, "per_page": per, "expect": items, "traps": [["first", items[:per]]]}


def same_rows(doc, want: List[dict]) -> bool:
    """Списки строк равны без учёта порядка (порядок страниц — дело клиента)."""
    import json
    if not isinstance(doc, list) or len(doc) != len(want):
        return False
    key = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False)  # noqa: E731
    try:
        return sorted(map(key, doc)) == sorted(map(key, want))
    except (TypeError, ValueError):
        return False


def urllib_hits(service, path: str = "/stock") -> List[dict]:
    """Удачные (200) запросы GET к path от urllib — из журнала учебного API (у родителя)."""
    if service is None or not hasattr(service, "journal"):
        return []
    return [e for e in service.journal()
            if e.get("path") == path and e.get("code") == 200 and e.get("method") == "GET"
            and str(e.get("user_agent") or "").startswith(URLLIB_AGENT)]


# --- boss_py: «Подменыш» — report.py, что выдаёт себя за правильный ---------------------------

# сводка по городам у варианта: (колонка, что копится по заказу)
BOSS_GROUPS = (("total", "сумма заказов"), ("orders", "число заказов"), ("qty", "штук товара"))
FAKE_CSV = ('# csv.py — «быстрый csv»: пришёл вместе с отчётом, не трогать\n'
            'VERSION = "0.1"\n')


def boss_py_data(rng, variant: int) -> dict:
    """boss_py: orders.json (как у py_json), остатки на API двумя страницами. Ответы —
    объекты для сравнения: все строки остатков, оплаченные заказы, строки сводки по городам
    (оплаченные заказы; A — сумма price×qty, B — число заказов, C — сумма qty)."""
    import json
    doc = orders_doc(rng)
    items = stock_items(rng, rng.randint(7, 10))
    paid = [o for o in doc["orders"] if o["status"] == "paid"]
    col = BOSS_GROUPS[variant][0]
    sums: Dict[str, int] = {}
    for o in paid:
        if variant == 0:
            add = sum(i["price"] * i["qty"] for i in o["items"])
        elif variant == 1:
            add = 1
        else:
            add = sum(i["qty"] for i in o["items"])
        sums[o["city"]] = sums.get(o["city"], 0) + add
    return {"json": json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
            "stock": items, "per_page": (len(items) + 1) // 2, "paid": paid,
            "summary": [["city", col]] + [[c, str(v)] for c, v in sorted(sums.items())],
            "traps": [["first", items[:(len(items) + 1) // 2]], ["all", doc["orders"]],
                      ["unpaid", [o for o in doc["orders"] if o["status"] != "paid"]]]}


def boss_report(variant: int, fixed=()) -> str:
    """report.py стража: врёт в четырёх местах — подмена (A: лишний import requests, B: двойник
    csv.py рядом — его в тексте нет, C: чужой ключ town), одна страница API вместо двух,
    json.dump без отступов и кириллицы, CSV без шапки. fixed — что уже починено: «swap»,
    «pages», «json», «header» (эталон и неверные решения собираются отсюда)."""
    col = BOSS_GROUPS[variant][0]
    key = "town" if variant == 2 and "swap" not in fixed else "city"
    head = ["# report.py — отчёт магазина: остатки с API, оплаченные заказы, сводка по городам",
            "import csv", "import json", "import urllib.request", ""]
    if variant == 0 and "swap" not in fixed:
        head.append("import requests")
    head += ["import sockhttp", "",
             "sockhttp.install()    # только для учебного сервера: дальше — обычный urllib", "",
             "# 1. остатки со всех страниц API — в stock.json", "stock = []",
             "for page in [1, 2]:" if "pages" in fixed else "for page in [1]:",
             '    r = urllib.request.urlopen(f"http://api/stock?page={page}")',
             '    stock += json.load(r)["items"]', 'with open("stock.json", "w") as f:',
             "    json.dump(stock, f, indent=2)", "",
             "# 2. оплаченные заказы — в paid.json", 'with open("orders.json") as f:',
             "    data = json.load(f)",
             'paid = [order for order in data["orders"] if order["status"] == "paid"]',
             'with open("paid.json", "w") as f:',
             ("    json.dump(paid, f, indent=2, ensure_ascii=False)" if "json" in fixed else
              "    json.dump(paid, f)"), "",
             "# 3. сводка по городам — в summary.csv", "sums = {}", "for order in paid:",
             f'    city = order["{key}"]']
    if variant == 1:
        head.append("    sums[city] = sums.get(city, 0) + 1")
    else:
        add = 'item["price"] * item["qty"]' if variant == 0 else 'item["qty"]'
        head += ["    n = 0", '    for item in order["items"]:', f"        n += {add}",
                 "    sums[city] = sums.get(city, 0) + n"]
    head += ['with open("summary.csv", "w", newline="") as f:',
             f'    w = csv.DictWriter(f, fieldnames=["city", "{col}"])']
    if "header" in fixed:
        head.append("    w.writeheader()")
    head += ["    for city in sorted(sums):",
             f'        w.writerow({{"city": city, "{col}": sums[city]}})']
    return "\n".join(head) + "\n"
