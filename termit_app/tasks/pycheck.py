"""Трек «Python», FB14 (FB5 п. 35, 37): линтеры и тесты — flake8 (+pep8-naming, flake8-isort),
pytest, mypy. Курс «Инженер данных», спринт 2, тема 3: «файл с ошибками → запусти → прочитай
вывод → исправь».

Пакеты — из склада колёс (pylibs/lock.py, ./termit wheels get): запас third кладёт их в
~/wheels, игрок ставит в .venv сам (pip install --no-index --find-links, урок pip_offline).
Без склада задачи честно закрыты (missing → pyenvs.NO_WAREHOUSE).

Родитель код игрока не исполняет и сами инструменты не запускает. Решено — по результату:
- py_lint и py_types: заложенные в файл замечания исправлены (разбор ast и строк — тот же
  вид замечаний, что напечатает инструмент), файл цел (функции на месте), а инструмент
  запускали из .venv и последний его запуск не провалился (журнал команд);
- py_test: кэш самого pytest (.pytest_cache): тесты прогнаны после последней правки и
  упавших нет; файл тестов не тронут.
Данные песочницы — по-английски (FB5 п. 42)."""
import ast
import hashlib
import json
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from termit_app.tasks import envkit, kit
from termit_app.tasks.base import Task, Variant, Verdict, variant_index

LINT_PKGS = "flake8 pep8-naming flake8-isort"
PIP = "pip install --no-index --find-links ~/wheels"
ACTIVATE = "source .venv/bin/activate"
MAX_LINE = 79                                   # flake8 по умолчанию: E501 — длиннее 79
TEXT_CAP = 64 * 1024


def _v(task, state: dict) -> int:
    return variant_index(state.get("_variant", 0), len(task.variants))


def _setup_venv(box: Path) -> None:
    """Пустой .venv из запаса light и колёса склада в ~/wheels (как у pd_install)."""
    from termit_app.tasks.pydata import third_home
    kit.venv_from_stock(box, "light", ".venv")
    third_home(box)


def _text(box, rel: str) -> Tuple[str, Optional[str]]:
    return envkit.box_text(box, rel, TEXT_CAP)


def _parse(text: str) -> Optional[ast.Module]:
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


def _defs(tree: ast.Module) -> List[str]:
    return [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef,
                                                             ast.AsyncFunctionDef))]


def _tool_runs(jour, tool: str) -> List[Tuple[str, Optional[bool]]]:
    """Строки журнала, где запускали tool (по имени — из включённого .venv, или .venv/bin/…;
    python3 -m tool — тоже)."""
    out = []
    for line, ok in jour:
        for seg in envkit.segments(line):
            _, cmd, args = envkit.lead(seg)
            if cmd is None:
                continue
            name = cmd.rsplit("/", 1)[-1]
            if name == tool or (name.startswith("python") and args[:2] == ["-m", tool]):
                out.append((line, ok))
                break
    return out


MSG_NO_VENV = "Окружения .venv нет — набери reset, соберу задачу заново."
MSG_BROKEN = ("{script} больше не разбирается Python: SyntaxError. Открой его (nano {script}) — "
              "или reset, если проще начать заново.")
MSG_GUTTED = "Из {script} пропала функция {func} — правь замечания, а не удаляй код. reset вернёт."
MSG_NOT_INSTALLED = ("{tool} в .venv нет. Колёса — в ~/wheels: {activate}; {pip} {pkgs}")
MSG_NO_RUN = ("Файл исправлен, но {tool} ты не запускал. Набери {tool} {script} — урок в "
              "том, чтобы прочитать его вывод.")
MSG_LAST_FAILED = ("Последний запуск {tool} закончился с ошибкой — значит, замечания ещё есть. "
                   "Прочитай вывод, поправь и запусти снова.")


def _installed(box, pkg: str) -> bool:
    pk = envkit.venv_pkgs(box, ".venv") or {}
    return envkit.canon(pkg) in pk


def _finish(box, jour, tool: str, script: str, pkg: str, pkgs: str) -> Verdict:
    """Общий хвост: инструмент стоит в .venv, его запускали, последний запуск не упал."""
    if not _installed(box, pkg):
        return Verdict(False, MSG_NOT_INSTALLED.format(tool=tool, activate=ACTIVATE, pip=PIP,
                                                      pkgs=pkgs))
    runs = _tool_runs(jour, tool)
    if not runs:
        return Verdict(False, MSG_NO_RUN.format(tool=tool, script=script))
    if runs[-1][1] is False:
        return Verdict(False, MSG_LAST_FAILED.format(tool=tool))
    return Verdict(True)


# --- py_lint: flake8 + pep8-naming + flake8-isort -------------------------------------------

CITY_COLS = ("city", "region", "store")
UNUSED = ("os", "sys", "json")
SCRIPTS = ("report.py", "sales.py", "totals.py")

LINT_LONG = '''"""Sales report: total amount per {col} from sales.csv."""
import csv
import {unused}


def total_by_{col}(path):
    totals = {{}}
    with open(path) as f:
        for row in csv.DictReader(f):
            totals[row["{col}"]] = totals.get(row["{col}"], 0) + int(row["amount"])
    return totals


if __name__ == "__main__":
    print(total_by_{col}("sales.csv"))
'''
LINT_LONG_FIXED = '''"""Sales report: total amount per {col} from sales.csv."""
import csv


def total_by_{col}(path):
    totals = {{}}
    with open(path) as f:
        for row in csv.DictReader(f):
            key = row["{col}"]
            totals[key] = totals.get(key, 0) + int(row["amount"])
    return totals


if __name__ == "__main__":
    print(total_by_{col}("sales.csv"))
'''
LINT_NAMING = '''"""Sales report: total amount per {col} from sales.csv."""
import csv


def {bad}(path):
    totals = {{}}
    with open(path) as f:
        for row in csv.DictReader(f):
            key = row["{col}"]
            totals[key] = totals.get(key, 0) + int(row["amount"])
    return totals


if __name__ == "__main__":
    print({bad}("sales.csv"))
'''
LINT_ORDER = '''"""Sales report: top {col}s by amount from sales.csv."""
import sys
import csv
from collections import Counter
import json


def top_{col}s(path, n):
    totals = Counter()
    with open(path) as f:
        for row in csv.DictReader(f):
            totals[row["{col}"]] += int(row["amount"])
    return totals.most_common(n)


if __name__ == "__main__":
    json.dump(top_{col}s("sales.csv", int(sys.argv[1])), sys.stdout)
'''
# как их расставит isort (профиль по умолчанию): в своей секции сперва «import x», потом «from»
ORDER_FIXED = ["import csv", "import json", "import sys", "from collections import Counter"]


def _camel(col: str) -> str:
    return "TotalBy" + col.capitalize()


def top_imports(tree: ast.Module) -> List[str]:
    """Импорты верхнего уровня по порядку — строками, как их пишут («import x», «from a import
    b»)."""
    out = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            out += [f"import {a.name}" for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = ", ".join(a.name for a in node.names)
            out.append(f"from {node.module} import {names}")
    return out


def used_names(tree: ast.Module) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                out.add(base.id)
    return out


def lint_issues(text: str, kind: int, col: str) -> List[str]:
    """Заложенные замечания, которые ещё на месте (коды, как у flake8): kind 0 — F401 и E501,
    1 — N802, 2 — I001. Пусто — исправлено. Остальное решает сам flake8 (журнал)."""
    tree = _parse(text)
    if tree is None:
        return ["E999"]
    out = []
    if kind == 0:
        imported = {i.split()[1] for i in top_imports(tree) if i.startswith("import ")}
        if imported - used_names(tree):
            out.append("F401")
        if any(len(x) > MAX_LINE for x in text.split("\n")):
            out.append("E501")
    elif kind == 1:
        if any(name != name.lower() for name in _defs(tree)):
            out.append("N802")
        elif _camel(col) in used_names(tree):
            out.append("F821")          # определение переименовано, а вызов внизу — нет
    elif top_imports(tree) != ORDER_FIXED:
        out.append("I001")
    return out


class PyLint(Task):
    """flake8 FILE: формат «файл:строка:колонка: CODE текст», F401/E501, N802 (pep8-naming),
    I001 (flake8-isort) и isort, который чинит порядок импортов сам."""
    id = "py_lint"
    track = "py"
    title = "Код на проверке"
    par = 150
    pinned_python = True
    stock = "third"
    tool = "python"                     # значок 🐍, как у всего трека
    secret_keys = ("fixed",)
    scroll = ("flake8 файл.py — корректор кода: печатает замечания строками "
              "файл:строка:колонка: CODE текст, а сам ничего не правит.\n"
              "Ставится в .venv из склада: pip install --no-index --find-links ~/wheels flake8 "
              "pep8-naming.\n"
              "Исправил — запусти снова: пустой вывод — замечаний нет. isort файл.py сам "
              "расставит импорты.")
    variants = (
        Variant("В {script} функция называется {bad} — по правилам оформления так "
                "называют классы, а не функции. Поставь flake8 с плагином pep8-naming из "
                "~/wheels, найди замечание "
                "и переименуй функцию так, чтобы flake8 {script} молчал.",
                hints=("{activate}; {pip} {pkgs} — потом flake8 {script}.",
                       "N802 — имя функции должно быть строчными: {good}. Переименуй и "
                       "определение, и вызов внизу.",
                       "{activate}; {pip} {pkgs}; flake8 {script}; sed -i '' 's/{bad}/{good}/g' "
                       "{script}; flake8 {script}"),
                solution="{activate}; {pip} {pkgs}; flake8 {script}; sed -i '' "
                         "'s/{bad}/{good}/g' {script}; flake8 {script}",
                wrong=("{activate}; {pip} {pkgs}; flake8 {script}",
                       "{activate}; {pip} {pkgs}; sed -i '' 's/def {bad}/def {good}/' {script}; "
                       "flake8 {script}"),
                alternatives=("nano {script} — переименовать в двух местах руками",)),
        Variant("В {script} — отчёт по продажам; ревьюер вернул его со словами «прогони "
                "flake8». Поставь flake8 в .venv из ~/wheels, прочитай замечания и исправь их "
                "так, чтобы flake8 {script} молчал. Отчёт должен остаться рабочим.",
                hints=("Сначала {activate}; {pip} {pkgs} — потом flake8 {script}.",
                       "F401 — импорт, который не используется: удали его. E501 — строка "
                       "длиннее 79: раздели её на две.",
                       "{activate}; {pip} {pkgs}; flake8 {script}; nano {script}: убери "
                       "import {unused}, длинную строку раздели на две; flake8 {script}"),
                solution="{activate}; {pip} {pkgs}; flake8 {script}; nano {script} — убери "
                         "import {unused}, длинную строку раздели на две; flake8 {script}",
                solution_script="{activate}; {pip} {pkgs}; flake8 {script}; sed -i '' -e "
                                "'/^import {unused}$/d' -e {split_sed} {script}; flake8 {script}",
                wrong=("{activate}; {pip} {pkgs}; flake8 {script}",
                       "{activate}; {pip} {pkgs}; sed -i '' '/^import {unused}$/d' {script}; "
                       "flake8 {script}"),
                alternatives=("flake8 без имени файла — проверит всю папку разом",)),
        Variant("Импорты в {script} стоят вразнобой. Поставь flake8 с плагином flake8-isort из "
                "~/wheels, прочитай замечание I001 и наведи порядок — руками или командой "
                "isort — так, чтобы flake8 {script} молчал.",
                hints=("{activate}; {pip} {pkgs} — потом flake8 {script}.",
                       "I001 — импорты не по порядку. isort {script} расставит их сам: он ставится "
                       "вместе с flake8-isort.",
                       "{activate}; {pip} {pkgs}; flake8 {script}; isort {script}; flake8 "
                       "{script}"),
                solution="{activate}; {pip} {pkgs}; flake8 {script}; isort {script}; flake8 "
                         "{script}",
                wrong=("{activate}; {pip} {pkgs}; flake8 {script}",),
                alternatives=("isort --diff {script} — сначала посмотреть, что он поменяет",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("flake8 — корректор: он только находит места (файл:строка:колонка) и называет "
               "код правила, а правит человек. Плагины добавляют свои коды: N — имена "
               "(pep8-naming), I — порядок импортов (flake8-isort). isort, в отличие от "
               "flake8, сам переписывает файл.")
    spell = "flake8 файл.py — замечания файл:строка:колонка: CODE; isort файл.py — порядок импортов"
    MSG_LEFT = ("flake8 ещё найдёт {codes} в {script}. Запусти flake8 {script} и исправь строки "
                "из вывода.")

    # вариант → вид замечаний (lint_issues): 0 — F401 и E501, 1 — N802, 2 — I001. Ревью FB14:
    # первым идёт самый простой — одно переименование (N802)
    KIND_OF = (1, 0, 2)

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        _setup_venv(box)
        variant = self.KIND_OF[variant % 3]
        col, script = rng.choice(CITY_COLS), rng.choice(SCRIPTS)
        unused = rng.choice(UNUSED)
        st = {"split_sed": "", "script": script, "col": col, "unused": unused,
              "bad": _camel(col),
              "good": f"total_by_{col}", "activate": ACTIVATE, "pip": PIP, "pkgs": LINT_PKGS}
        if variant == 0:
            text = LINT_LONG.format(col=col, unused=unused)
            st["fixed"] = LINT_LONG_FIXED.format(col=col)
            # длинную строку — на две (sed с переводом строки в замене: \ и новая строка)
            st["split_sed"] = ("'s/^\\( *\\)totals\\[row\\[\"" + col + "\"\\]\\] = .*$/"
                               "\\1key = row[\"" + col + "\"]\\\n\\1totals[key] = "
                               "totals.get(key, 0) + int(row[\"amount\"])/'")
        elif variant == 1:
            text = LINT_NAMING.format(col=col, bad=st["bad"])
            st["fixed"] = ""
        else:
            text = LINT_ORDER.format(col=col)
            st["fixed"] = ""
        kit.write(box / script, text)
        st["func"] = {0: f"total_by_{col}", 1: None, 2: f"top_{col}s"}[variant]
        return st

    def check(self, ctx) -> Verdict:
        st, box = ctx.state, ctx.box
        if envkit.venv_pkgs(box, ".venv") is None:
            return Verdict(False, MSG_NO_VENV)
        script = st["script"]
        kind, text = _text(box, script)
        bad = envkit.file_problem(kind, script)
        if bad:
            return Verdict(False, bad)
        if text is None:
            return Verdict(False, MSG_GUTTED.format(script=script, func=st.get("func") or
                                                    st["good"]))
        tree = _parse(text)
        if tree is None:
            return Verdict(False, MSG_BROKEN.format(script=script))
        func = st.get("func")
        if func and func not in _defs(tree):
            return Verdict(False, MSG_GUTTED.format(script=script, func=func))
        if not _defs(tree) or "csv" not in text:
            return Verdict(False, MSG_GUTTED.format(script=script, func=st["good"]))
        left = lint_issues(text, self.KIND_OF[_v(self, st)], st["col"])
        jour = envkit.journal(box)
        if left:
            if not _tool_runs(jour, "flake8") and not ctx.cmds:
                return Verdict(False)
            return Verdict(False, self.MSG_LEFT.format(codes=", ".join(left), script=script))
        return _finish(box, jour, "flake8", script, "flake8", LINT_PKGS)


# --- py_test: pytest ------------------------------------------------------------------------

PRICES_PY = '''"""Price helpers for the shop."""


def with_tax(price, rate):
    """Price with tax: rate 0.2 means plus 20 percent."""
    return {tax_body}


def discount(price, percent):
    """Price after a discount in percent."""
    return {disc_body}
'''
TEST_PRICES_PY = '''from prices import discount, with_tax


def test_tax_zero():
    assert with_tax(100, 0) == 100


def test_tax_twenty():
    assert with_tax(100, 0.2) == 120


def test_discount_half():
    assert discount(80, 50) == 40


def test_discount_none():
    assert discount(80, 0) == 80
'''
TAX_OK = "round(price * (1 + rate), 2)"
TAX_BUG = "round(price * rate, 2)"
DISC_OK = "round(price * (100 - percent) / 100, 2)"
DISC_BUG = "round(price * percent / 100, 2)"
TEST_FILE = "test_prices.py"
CACHE = ".pytest_cache/v/cache"
TEST_IDS = ("test_tax_zero", "test_tax_twenty", "test_discount_half", "test_discount_none")


def pytest_cache(box) -> Tuple[Optional[list], Optional[dict], Optional[float]]:
    """(nodeids, lastfailed, время nodeids) из кэша pytest в песочнице; нет — None."""
    kind, raw = envkit.box_text(box, f"{CACHE}/nodeids", TEXT_CAP)
    ids = None
    stamp = None
    if kind == "ok":
        try:
            ids = json.loads(raw or "")
        except ValueError:
            ids = None
        try:
            stamp = os.lstat(Path(box) / CACHE / "nodeids").st_mtime
        except OSError:
            stamp = None
    kind, raw = envkit.box_text(box, f"{CACHE}/lastfailed", TEXT_CAP)
    failed = None
    if kind == "ok":
        try:
            failed = json.loads(raw or "")
        except ValueError:
            failed = {"?": True}
    return ids, failed, stamp


class PyTest(Task):
    """pytest: прочитать упавший assert («assert 20.0 == 120»), починить функцию, зелёный
    прогон; -x — стоп на первом падении; -k — выбрать тесты по слову, -q — коротко."""
    id = "py_test"
    track = "py"
    title = "Тесты краснеют"
    par = 150
    pinned_python = True
    stock = "third"
    tool = "python"                     # значок 🐍, как у всего трека
    scroll = ("pytest — запускает функции test_… из файлов test_*.py и пишет, какие проверки "
              "упали и чем ожидаемое отличается от полученного.\n"
              "Ставится в .venv из склада: pip install --no-index --find-links ~/wheels pytest.\n"
              "Упал тест — читай assert: слева то, что вернула функция, справа — что ждали.")
    variants = (
        Variant("Тесты test_prices.py проверяют prices.py, и тесты падают. Поставь pytest в "
                "{venv} из ~/wheels, найди по выводу, что сломано, и почини функцию в "
                "prices.py (тесты не трогай) — до зелёного прогона.",
                hints=("{activate}; {pip} pytest — потом pytest.",
                       "Читай строку с assert: слева — что вернула функция, справа — что ждали. "
                       "Почини {func} в prices.py.",
                       "{activate}; {pip} pytest; pytest; nano prices.py: в {func} верни "
                       "{good_body}; pytest"),
                solution="{activate}; {pip} pytest; pytest; nano prices.py — в {func} верни "
                         "{good_body}; pytest",
                solution_script="{activate}; {pip} pytest; pytest; sed -i '' "
                                "'s|{bug_sed}|{good_sed}|' prices.py; pytest",
                wrong=("{activate}; {pip} pytest; pytest",
                       "{activate}; {pip} pytest; sed -i '' 's/== 120/== 20.0/' test_prices.py; "
                       "pytest"),
                alternatives=("pytest -q — то же коротко: точки и F вместо имён",)),
        Variant("В prices.py сломаны обе функции. Поставь pytest в {venv} из ~/wheels и чини "
                "по одной: pytest -x останавливается на первом падении. Тесты не трогай — "
                "добейся зелёного прогона.",
                hints=("{activate}; {pip} pytest — потом pytest -x.",
                       "Первое падение — первая функция. Почини, снова pytest -x — покажет "
                       "следующую.",
                       "{activate}; {pip} pytest; pytest -x; nano prices.py: верни правильные "
                       "формулы в with_tax и discount; pytest"),
                solution="{activate}; {pip} pytest; pytest -x; nano prices.py — верни "
                         "правильные формулы в with_tax и discount; pytest",
                solution_script="{activate}; {pip} pytest; pytest -x; sed -i '' -e "
                                "'s|{tax_bug_sed}|{tax_ok_sed}|' -e "
                                "'s|{disc_bug_sed}|{disc_ok_sed}|' prices.py; pytest",
                wrong=("{activate}; {pip} pytest; sed -i '' 's|{tax_bug_sed}|{tax_ok_sed}|' "
                       "prices.py; pytest",),
                alternatives=("pytest без -x — покажет все падения сразу",)),
        Variant("В test_prices.py тесты и про налог, и про скидку; сломана {func}. Поставь "
                "pytest в {venv} из ~/wheels, гоняй только тесты про {word}: pytest -k {word}. "
                "Почини функцию и добейся зелёного прогона всех тестов.",
                hints=("{activate}; {pip} pytest — потом pytest -k {word}.",
                       "-k {word} выбирает тесты, в имени которых есть {word}. Почини {func} и "
                       "в конце запусти все — просто pytest.",
                       "{activate}; {pip} pytest; pytest -k {word}; nano prices.py: в {func} "
                       "верни {good_body}; pytest"),
                solution="{activate}; {pip} pytest; pytest -k {word}; nano prices.py — в {func} "
                         "верни {good_body}; pytest",
                solution_script="{activate}; {pip} pytest; pytest -k {word}; sed -i '' "
                                "'s|{bug_sed}|{good_sed}|' prices.py; pytest",
                wrong=("{activate}; {pip} pytest; pytest -k {word}",),
                alternatives=("pytest -k {word} -q — коротко: сколько прошло и сколько "
                              "отобрано (deselected)",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("pytest находит функции test_… и запускает их; упавший assert он печатает с "
               "обеими сторонами — что вернула функция и что ждали. Чинят код, а не тест: "
               "тест — это договор о том, как код должен работать.")
    spell = "pytest — все тесты; pytest -x — до первого падения; pytest -k слово — только эти"
    MSG_TESTS_TOUCHED = ("test_prices.py изменён — так тест не починить, а спрятать. reset "
                         "вернёт тесты; чинить нужно prices.py.")
    MSG_RED = "Последний прогон pytest — с падениями: {failed}. Почини prices.py и запусти снова."
    MSG_STALE = ("prices.py правился после последнего прогона pytest. Запусти pytest ещё раз — "
                 "все тесты.")
    MSG_PARTIAL = ("Последний прогон был не по всем тестам (-k или один файл). В конце запусти "
                   "все: pytest.")
    MSG_NOT_RUN = "pytest ещё не запускали: {activate}; {pip} pytest; pytest"
    MSG_SAME = "prices.py не изменился — тесты зелёными не станут. Почини функцию из вывода."

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        _setup_venv(box)
        broken_tax = variant == 1 or rng.random() < 0.5
        tax_body = TAX_BUG if broken_tax else TAX_OK
        disc_body = DISC_BUG if (variant == 1 or not broken_tax) else DISC_OK
        text = PRICES_PY.format(tax_body=tax_body, disc_body=disc_body)
        kit.write(box / "prices.py", text)
        kit.write(box / TEST_FILE, TEST_PRICES_PY)
        func = "with_tax" if broken_tax else "discount"
        bug, good = (TAX_BUG, TAX_OK) if broken_tax else (DISC_BUG, DISC_OK)

        def sed(x: str) -> str:
            return x.replace("*", "\\*")     # в шаблоне sed звёздочка — «повтор», экранируем
        return {"venv": ".venv", "activate": ACTIVATE, "pip": PIP, "func": func,
                "word": "tax" if broken_tax else "discount", "good_body": good,
                "bug_sed": sed(bug), "good_sed": good, "tax_bug_sed": sed(TAX_BUG),
                "tax_ok_sed": TAX_OK, "disc_bug_sed": sed(DISC_BUG), "disc_ok_sed": DISC_OK,
                "tests_sha": hashlib.sha256(TEST_PRICES_PY.encode()).hexdigest(),
                "orig_sha": hashlib.sha256(text.encode()).hexdigest()}

    def check(self, ctx) -> Verdict:
        st, box = ctx.state, Path(ctx.box)
        if envkit.venv_pkgs(box, ".venv") is None:
            return Verdict(False, MSG_NO_VENV)
        kind, tests = _text(box, TEST_FILE)
        if kind != "ok" or hashlib.sha256((tests or "").encode()).hexdigest() != st["tests_sha"]:
            return Verdict(False, self.MSG_TESTS_TOUCHED)
        kind, text = _text(box, "prices.py")
        bad = envkit.file_problem(kind, "prices.py")
        if bad:
            return Verdict(False, bad)
        if text is None or _parse(text) is None:
            return Verdict(False, MSG_BROKEN.format(script="prices.py"))
        for func in ("with_tax", "discount"):
            if func not in _defs(_parse(text)):
                return Verdict(False, MSG_GUTTED.format(script="prices.py", func=func))
        ids, failed, stamp = pytest_cache(box)
        if ids is None:
            if not ctx.cmds:
                return Verdict(False)
            return Verdict(False, self.MSG_NOT_RUN.format(**st))
        if failed:
            names = ", ".join(sorted(k.split("::")[-1] for k in failed)[:3])
            return Verdict(False, self.MSG_RED.format(failed=names))
        if hashlib.sha256(text.encode()).hexdigest() == st["orig_sha"]:
            return Verdict(False, self.MSG_SAME)
        try:
            edited = os.lstat(box / "prices.py").st_mtime
        except OSError:
            edited = None
        if stamp is not None and edited is not None and edited > stamp:
            return Verdict(False, self.MSG_STALE)
        ran = {str(i).split("::")[-1] for i in ids}
        runs = _tool_runs(envkit.journal(box), "pytest")
        # кэш nodeids копит имена между запусками: «прогон был по всем» — по журналу (ревью)
        last = runs[-1][0] if runs else ""
        if not set(TEST_IDS) <= ran or re.search(r"(?<!\S)-k\b", last):
            return Verdict(False, self.MSG_PARTIAL)
        if not _installed(box, "pytest"):
            return Verdict(False, MSG_NOT_INSTALLED.format(tool="pytest", activate=ACTIVATE,
                                                          pip=PIP, pkgs="pytest"))
        return Verdict(True)


# --- py_types: mypy -------------------------------------------------------------------------

TYPES_ARG = '''"""Invoice helpers."""


def add_vat(price: float, rate: float = 0.2) -> float:
    return round(price * (1 + rate), 2)


def invoice_total(prices: list) -> float:
    return sum(add_vat(p) for p in prices)


if __name__ == "__main__":
    print(add_vat("{amount}"))
'''
TYPES_RETURN = '''"""Invoice helpers."""


def count_lines(path: str) -> int:
    with open(path) as f:
        n = sum(1 for _ in f)
    return str(n)


if __name__ == "__main__":
    print(count_lines("invoices.csv"))
'''
TYPES_OPTIONAL = '''"""Invoice helpers."""
from typing import Optional


def find_client(clients: dict, code: str) -> str:
    if code in clients:
        return clients[code]
    return None


if __name__ == "__main__":
    print(find_client({{"{code}": "Acme"}}, "{code}"))
'''


def types_issue(text: str, kind: int) -> Optional[str]:
    """Заложенная ошибка типов ещё на месте? Код mypy ([arg-type], [return-value]) или None."""
    tree = _parse(text)
    if tree is None:
        return "syntax"
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    if kind == 0:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "add_vat":
                if any(isinstance(a, ast.Constant) and isinstance(a.value, str)
                       for a in node.args):
                    return "arg-type"
        return None
    if kind == 1:
        fn = funcs.get("count_lines")
        if fn is None:
            return None
        for node in ast.walk(fn):
            returns_str = (isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
                           and getattr(node.value.func, "id", None) == "str")
            if returns_str:
                ann = ast.unparse(fn.returns) if hasattr(ast, "unparse") and fn.returns else ""
                return None if ann == "str" else "return-value"
        return None
    fn = funcs.get("find_client")
    if fn is None:
        return None
    returns_none = any(isinstance(n, ast.Return) and (n.value is None or (
        isinstance(n.value, ast.Constant) and n.value.value is None)) for n in ast.walk(fn))
    if not returns_none:
        return None
    ann = ast.get_source_segment(text, fn.returns) if fn.returns is not None else ""
    return None if ann and ("Optional" in ann or "None" in ann) else "return-value"


class PyTypes(Task):
    """mypy FILE: «error: … [arg-type]» — проверка аннотаций без запуска; Optional."""
    id = "py_types"
    track = "py"
    title = "Обещания в коде"
    par = 150
    pinned_python = True
    stock = "third"
    tool = "python"                     # значок 🐍, как у всего трека
    scroll = ("mypy файл.py — сверяет аннотации типов (price: float, -> int) с тем, что "
              "реально передают и возвращают, не запуская код.\n"
              "Ставится в .venv из склада: pip install --no-index --find-links ~/wheels mypy.\n"
              "Вывод: файл:строка: error: текст [код]; в конце — Success: no issues found.")
    variants = (
        Variant("В {script} функция add_vat обещает принять число (price: float), а внизу её "
                "зовут со строкой. Поставь mypy в .venv из ~/wheels, прочитай ошибку и "
                "исправь вызов так, чтобы mypy {script} сказал Success (строка — это str).",
                hints=("{activate}; {pip} mypy — потом mypy {script}.",
                       "[arg-type] — аргумент не того типа: \"{amount}\" в кавычках — строка. "
                       "Убери кавычки — будет число.",
                       "{activate}; {pip} mypy; mypy {script}; sed -i '' "
                       "'s/add_vat(\"{amount}\")/add_vat({amount})/' {script}; mypy {script}"),
                solution="{activate}; {pip} mypy; mypy {script}; sed -i '' "
                         "'s/add_vat(\"{amount}\")/add_vat({amount})/' {script}; mypy {script}",
                wrong=("{activate}; {pip} mypy; mypy {script}",),
                alternatives=("nano {script} — убрать кавычки вокруг числа руками",)),
        Variant("count_lines в {script} обещает вернуть int, а возвращает строку (str). "
                "Поставь mypy "
                "в .venv из ~/wheels, прочитай ошибку и исправь return так, чтобы mypy "
                "{script} сказал Success.",
                hints=("{activate}; {pip} mypy — потом mypy {script}.",
                       "[return-value] — вернули не тот тип, что обещали после ->. Верни n, "
                       "а не str(n).",
                       "{activate}; {pip} mypy; mypy {script}; sed -i '' 's/return str(n)/return "
                       "n/' {script}; mypy {script}"),
                solution="{activate}; {pip} mypy; mypy {script}; sed -i '' 's/return "
                         "str(n)/return n/' {script}; mypy {script}",
                wrong=("{activate}; {pip} mypy; mypy {script}",),
                alternatives=("-> str в заголовке тоже успокоит mypy, но обещание станет "
                              "другим: функция считает строки, число честнее",)),
        Variant("find_client в {script} обещает вернуть str, но иногда возвращает None. "
                "Поставь mypy в .venv из ~/wheels и исправь обещание: -> Optional[str] "
                "(Optional — «или None»; импорт из модуля typing в файле уже есть). mypy "
                "{script} должен сказать Success.",
                hints=("{activate}; {pip} mypy — потом mypy {script}.",
                       "Обещание — после ->: замени -> str на -> Optional[str].",
                       "{activate}; {pip} mypy; mypy {script}; sed -i '' 's/-> str:/-> "
                       "Optional[str]:/' {script}; mypy {script}"),
                solution="{activate}; {pip} mypy; mypy {script}; sed -i '' 's/-> str:/-> "
                         "Optional[str]:/' {script}; mypy {script}",
                wrong=("{activate}; {pip} mypy; mypy {script}",),
                alternatives=("nano {script} — заменить -> str на -> Optional[str] руками",
                              "-> str | None — та же запись в Python 3.10+; здесь 3.9, нужен "
                              "Optional")),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Аннотации — обещания: price: float — «приму число», -> int — «верну целое». "
               "Python их сам не проверяет, а mypy сверяет каждое обещание со всеми вызовами "
               "и return, не запуская код, и называет нарушение кодом в скобках.")
    spell = "mypy файл.py — ошибки типов [arg-type], [return-value]; Success — чисто"
    MSG_LEFT = "mypy ещё найдёт [{code}] в {script}. Запусти mypy {script} и прочитай строку."

    FUNCS = ("add_vat", "count_lines", "find_client")

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        _setup_venv(box)
        script = rng.choice(("invoice.py", "billing.py", "vat.py"))
        amount = rng.randint(100, 9000)
        code = rng.choice(("A1", "B7", "C3", "D9"))
        text = (TYPES_ARG.format(amount=amount) if variant == 0 else TYPES_RETURN
                if variant == 1 else TYPES_OPTIONAL.format(code=code))
        kit.write(box / script, text)
        return {"script": script, "amount": amount, "code": code, "activate": ACTIVATE,
                "pip": PIP}

    def check(self, ctx) -> Verdict:
        st, box = ctx.state, ctx.box
        v = _v(self, st)
        if envkit.venv_pkgs(box, ".venv") is None:
            return Verdict(False, MSG_NO_VENV)
        script = st["script"]
        kind, text = _text(box, script)
        bad = envkit.file_problem(kind, script)
        if bad:
            return Verdict(False, bad)
        if text is None or _parse(text) is None:
            return Verdict(False, MSG_BROKEN.format(script=script))
        func = self.FUNCS[v]
        if func not in _defs(_parse(text)):
            return Verdict(False, MSG_GUTTED.format(script=script, func=func))
        left = types_issue(text, v)
        jour = envkit.journal(box)
        if left:
            if not ctx.cmds:
                return Verdict(False)
            return Verdict(False, self.MSG_LEFT.format(code=left, script=script))
        return _finish(box, jour, "mypy", script, "mypy", "mypy")


TASKS = [PyLint(), PyTest(), PyTypes()]
