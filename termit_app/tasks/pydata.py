"""Трек «Аналитика» (часть 10, Q4; FB15): pandas — установка по requirements.txt, чтение CSV,
фильтры, группировка, пропуски (задачи 1–5, здесь); даты, склейка, сводные, map/apply,
сохранение, SQL из pandas и requests — termit_app/tasks/pdmore.py; страж boss_pylib —
termit_app/tasks/pdboss.py.

Задачи — запас full (pyenvs: эталонный venv с pandas и requests из склада колёс); pd_install —
запас third (колёса склада и light: pandas она ставит сама). Без склада трек виден, но задачи честно отказывают через missing() с командой
./termit wheels get. Ответ считает Python-функция родителя на строках генератора (pdkit) —
без pandas и без исполнения кода игрока; совпадение с pandas проверяет только живой тест
tests/test_pydata_live.py (skipUnless склад). Порядок в TASKS — порядок обучения."""
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from termit_app import textnorm
from termit_app.tasks import envkit, kit, pdkit, pykit
from termit_app.tasks.base import AnswerTask, Task, Variant, Verdict, sources, variant_index

REQ = "requirements.txt"
WHEELS = "~/wheels"


def _v(task, state: dict) -> int:
    return variant_index(state.get("_variant", 0), len(task.variants))


def pandas_version() -> str:
    """Версия pandas по пинам склада (pylibs/lock.py)."""
    from termit_app.pylibs import lock
    for pin in sorted(lock.LOCK):
        name, ver = lock.split_pin(pin)
        if lock.norm(name) == "pandas":
            return ver
    raise KeyError("pandas нет в пинах склада")


def third_home(box) -> None:
    """~/wheels песочницы — колёса склада из запаса (.termit/stock/third): только обычные
    файлы *.whl. Без склада (подмена в тестах) папка пуста."""
    src = Path(box) / ".termit" / "stock" / "third"
    dst = kit.home(box) / "wheels"
    dst.mkdir(parents=True, exist_ok=True)
    for name in sorted(os.listdir(src)) if src.is_dir() else ():
        p = src / name
        if name.endswith(".whl") and p.is_file() and not p.is_symlink():
            shutil.copy2(p, dst / name)


def full_venv(box) -> Path:
    """Готовый .venv с pandas и requests — клон эталона full из запаса."""
    return kit.venv_from_stock(box, "full", ".venv")


# --- 1. pd_install ----------------------------------------------------------------------------

def _by_file(jour, venv: Optional[str]) -> bool:
    """В журнале — не упавший pip install -r requirements.txt из venv (None — из любого)."""
    for _, ok, seg, active in envkit.walk_venv(jour):
        a = envkit.pip_args(seg)
        if (a and a[0] == "install" and envkit.pip_r_file(a[1:], REQ) and ok is not False
                and (venv is None or envkit.from_venv(seg, active, venv))):
            return True
    return False


def _req_as_name(args) -> bool:
    """pip install requirements.txt — файл вместо -r: pip ищет пакет с таким именем."""
    for k, a in enumerate(args):
        if a.startswith("-"):
            continue
        prev = args[k - 1] if k else ""
        if a.rsplit("/", 1)[-1] == REQ and prev not in ("-r", "--requirement"):
            return True
    return False


def _pandas_run(seg: str, active) -> bool:
    """python3 -c с import pandas — из .venv (путём или включённым окружением)."""
    return (envkit.py_inline(seg) and "pandas" in seg
            and envkit.from_venv(seg, active, ".venv"))


class PdInstall(Task):
    """pip install -r requirements.txt из склада колёс (--no-index --find-links), import
    pandas as pd и pd.__version__. Что стоит в venv, родитель видит по dist-info (INSTALLER
    pip и RECORD); ver.txt — первая строка, записанная python3 -c с pandas из .venv."""
    id = "pd_install"
    track = "pydata"
    title = "pandas по списку"
    par = 105
    pinned_python = True
    stock = "third"            # колёса склада и light: эталон full ей не нужен
    scroll = ("pip install -r requirements.txt — всё по списку из файла, с зависимостями.\n"
              "Без сети: pip install --no-index --find-links ~/wheels -r requirements.txt\n"
              "pandas — таблицы в Python: import pandas as pd (pd — короткое имя); версия — "
              "pd.__version__")
    variants = (
        Variant("Проекту нужен pandas: список пакетов — в requirements.txt, колёса — в ~/wheels "
                "(сети нет). Поставь всё по файлу в .venv.",
                hints=("Сначала включи окружение: source .venv/bin/activate.",
                       "Ставь по файлу: pip install -r requirements.txt, а без сети добавь "
                       "--no-index --find-links ~/wheels.",
                       "source .venv/bin/activate; pip install --no-index --find-links "
                       "~/wheels -r requirements.txt"),
                solution="source .venv/bin/activate; pip install --no-index --find-links "
                         "~/wheels -r requirements.txt",
                wrong=("source .venv/bin/activate; pip install -r requirements.txt",
                       "source .venv/bin/activate; pip install --no-index --find-links "
                       "~/wheels pandas"),
                alternatives=(".venv/bin/pip install --no-index --find-links ~/wheels -r "
                              "requirements.txt — pip окружения и без activate",),
                key="by_file"),
        Variant("Поставь в .venv пакеты из requirements.txt (колёса — в ~/wheels, сети нет) и "
                "проверь, что pandas встал: запиши в ver.txt то, что печатает python3 -c "
                "'import pandas as pd; print(pd.__version__)'.",
                hints=("Включи .venv и поставь по файлу — без сети: --no-index --find-links "
                       "~/wheels.",
                       "Проверка — тем же python3 из .venv: python3 -c '…' > ver.txt.",
                       "source .venv/bin/activate; pip install --no-index --find-links ~/wheels "
                       "-r requirements.txt; python3 -c 'import pandas as pd; "
                       "print(pd.__version__)' > ver.txt"),
                solution="source .venv/bin/activate; pip install --no-index --find-links "
                         "~/wheels -r requirements.txt; python3 -c 'import pandas as pd; "
                         "print(pd.__version__)' > ver.txt",
                wrong=("source .venv/bin/activate; pip install --no-index --find-links ~/wheels "
                       "-r requirements.txt; print -r -- {ver} > ver.txt",
                       "pip install --user --no-index --find-links ~/wheels -r requirements.txt; "
                       "python3 -c 'import pandas as pd; print(pd.__version__)' > ver.txt"),
                alternatives=("python3 -c 'import pandas; print(pandas.__version__)' — то же "
                              "без as pd",),
                key="check"),
        Variant("Подними рядом новое окружение .venv2 и поставь в него всё из requirements.txt "
                "(колёса — в ~/wheels, сети нет). Старый .venv не трогай.",
                hints=("Новое окружение — python3 -m venv .venv2; потом включи его.",
                       "В .venv2 ставь по файлу: pip install -r requirements.txt, без сети — "
                       "--no-index --find-links ~/wheels.",
                       "python3 -m venv .venv2; source .venv2/bin/activate; pip install "
                       "--no-index --find-links ~/wheels -r requirements.txt"),
                solution="python3 -m venv .venv2; source .venv2/bin/activate; pip install "
                         "--no-index --find-links ~/wheels -r requirements.txt",
                wrong=("python3 -m venv .venv2; source .venv/bin/activate; pip install "
                       "--no-index --find-links ~/wheels -r requirements.txt",),
                alternatives=(".venv2/bin/pip install --no-index --find-links ~/wheels -r "
                              "requirements.txt — без activate",),
                key="venv2"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("requirements.txt — список пакетов проекта; pip install -r ставит всё по нему, "
               "вместе с зависимостями. Сети нет — не беда: pip возьмёт колёса из папки, "
               "--no-index --find-links.")
    spell = "pip install --no-index --find-links DIR -r requirements.txt; import pandas as pd"
    MSG_NO_VENV = "Окружения .venv нет — набери reset, соберу задачу заново."
    MSG_NET = ("Сети здесь нет, и не нужна: pip install --no-index --find-links ~/wheels -r "
               "requirements.txt")
    MSG_NO_R = ("pip install requirements.txt ищет пакет с таким именем. Файл со списком "
                "передают так: pip install -r requirements.txt")
    MSG_USER = ("Пакеты ушли не в .venv, а в домашнюю папку (--user): включи окружение — "
                "source .venv/bin/activate — и поставь заново.")
    MSG_FAILED = ("pip не справился — прочти последнюю строку его ошибки. Обычно хватает: "
                  "pip install --no-index --find-links ~/wheels -r requirements.txt")
    MSG_BY_ONE = ("pandas на месте, но ставь по файлу: pip install --no-index --find-links "
                  "~/wheels -r requirements.txt — так проект соберётся где угодно.")
    MSG_OTHER = ("pip install -r был, а в {venv} pandas нет — ставил в другое окружение. "
                 "Включи {venv}: source {venv}/bin/activate")
    MSG_NO_VENV2 = "Окружения .venv2 ещё нет: python3 -m venv .venv2, потом включи его."
    MSG_VER_TODO = ("pandas стоит. Осталось проверить: python3 -c 'import pandas as pd; "
                    "print(pd.__version__)' > ver.txt")
    MSG_VER_EMPTY = ("ver.txt пуст: python3 без окружения pandas не видит (ModuleNotFoundError). "
                     "Включи .venv и запусти снова.")
    MSG_VER = ("В ver.txt не версия pandas: python3 -c 'import pandas as pd; "
               "print(pd.__version__)' > ver.txt")
    MSG_VER_RUN = ("Версию пишет сам pandas из .venv: python3 -c 'import pandas as pd; "
                   "print(pd.__version__)' > ver.txt")

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        kit.venv_from_stock(box, "light", ".venv")
        third_home(box)
        ver = pandas_version()
        lines = [f"pandas=={ver}"]
        if rng.random() < 0.5:
            lines.insert(0, "# report packages")
        kit.write(box / REQ, "\n".join(lines) + "\n")
        return {"ver": ver}

    def _why_not(self, box, jour, venv: str, ver: str) -> Optional[str]:
        """Почему pandas не в venv — по ПОСЛЕДНЕЙ попытке pip install (None — молчим)."""
        if "pandas" in envkit.user_pkgs(box):
            return self.MSG_USER
        tries = envkit.pip_runs(jour, "install")
        if not tries:
            return None
        args, ok = tries[-1]
        if _req_as_name(args):
            return self.MSG_NO_R
        if ok is not True and "--no-index" not in args:
            return self.MSG_NET
        if ok is False:
            return self.MSG_FAILED
        if _by_file(jour, None):
            return self.MSG_OTHER.format(venv=venv)
        return None

    def check(self, ctx) -> Verdict:
        box, st = ctx.box, ctx.state
        v = _v(self, st)
        venv = ".venv2" if v == 2 else ".venv"
        ver = st.get("ver") or pandas_version()
        jour = envkit.journal(box)
        verdict = self._installed(box, jour, venv, ver)
        if verdict.solved and v == 1:
            verdict = self._ver(box, jour, ver)
        if verdict.solved or ctx.answer is None:
            return verdict
        return Verdict(False, verdict.message or self.stray_answer)

    def _installed(self, box, jour, venv: str, ver: str) -> Verdict:
        pk = envkit.venv_pkgs(box, venv)
        if pk is None:
            if venv == ".venv":
                return Verdict(False, self.MSG_NO_VENV)
            return Verdict(False, self.MSG_NO_VENV2 if _by_file(jour, None) else None)
        if envkit.pip_installed(box, venv, "pandas", ver):
            if _by_file(jour, venv):
                return Verdict(True)
            return Verdict(False, self.MSG_BY_ONE)
        return Verdict(False, self._why_not(box, jour, venv, ver))

    def _ver(self, box, jour, ver: str) -> Verdict:
        kind, text = envkit.box_text(box, "ver.txt", envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, "ver.txt")
        if bad:
            return Verdict(False, bad)
        if text is None:
            return Verdict(False, self.MSG_VER_TODO)
        line = envkit.first_line(text)
        if not line:
            return Verdict(False, self.MSG_VER_EMPTY)
        if line != ver:
            return Verdict(False, self.MSG_VER)
        if not envkit.written_by(jour, "ver.txt", _pandas_run):
            return Verdict(False, self.MSG_VER_RUN)
        return Verdict(True)


# --- общее для задач «найди и назови» ------------------------------------------------------------

MSG_MODULE = ("pandas не в этом окружении — Python его не нашёл. Включи .venv (source "
              ".venv/bin/activate) и запусти снова.")
MSG_CRASH = ("Команда упала — ответа она не дала. Прочти последнюю строку ошибки: там тип и "
             "суть, потом поправь и запусти снова.")


# код python3 -c в строке оболочки: в одинарных или двойных кавычках
_DASH_C = re.compile(r"-c\s+(?:'([^']*)'|\"([^\"]*)\")")


def last_pandas(box):
    """Последний python3 -c с pandas в журнале: (строка, исход) или None."""
    return envkit.last_line(envkit.journal(box), envkit.py_inline, mention="pandas")


class PdAnswer(AnswerTask):
    """Задача «Аналитики» «посчитай и назови»: данные из pdkit (gen), ответ и ловушки — у
    судьи (secret_keys AnswerTask). Число — как число (pykit.same_num: целое точно, дробь с
    допуском 0.005); отклик ловушки — только при точном совпадении. Отклики по форме смотрят
    на ПОСЛЕДНИЙ python3 -c с pandas (упал без .venv, упал вообще, свой приём задачи)."""
    track = "pydata"
    pinned_python = True
    stock = "full"
    kinds = ("number", "number", "number")
    FALLBACKS = ("Не то.", "Не то.", "Не то.")

    def gen(self, rng, variant: int) -> dict:
        raise NotImplementedError

    def files(self, box: Path, data: dict, variant: int) -> list:
        """Записать файлы задачи; вернуть их имена (файлы с ответом — sources)."""
        pdkit.write_csv(box, pdkit.DATA, data["rows"], data["header"])
        return [pdkit.DATA]

    def public(self, data: dict) -> dict:
        """Поля условия (в task.json — открытые)."""
        return {}

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        data = self.gen(rng, variant)
        names = self.files(box, data, variant)
        full_venv(box)
        st = dict(self.public(data))
        st["answer"] = data["answer"]
        st["traps"] = data["traps"]
        st["sources"] = sources(box, *names)
        return st

    def answer_kind(self, state: dict) -> str:
        return self.kinds[_v(self, state)]

    def matches(self, given: str, ctx) -> bool:
        if self.answer_kind(ctx.state) == "number":
            return pykit.same_num(given, self.expected(ctx.state))
        return super().matches(given, ctx)

    def trap_message(self, given: str, ctx) -> Optional[str]:
        """Только точное совпадение со значением ловушки (число — как число)."""
        st = ctx.state
        number = self.answer_kind(st) == "number"
        for key, value in st.get("traps") or ():
            if key not in self.trap_messages:
                continue
            value = str(value)
            if number:
                hit = pykit.same_num(given, value)
            else:
                hit = textnorm.same_text(given, value) or (
                    len(textnorm.parts(value)) > 1 and textnorm.same_words(given, value))
            if hit:
                return self.trap_messages[key].format(**st)
        return None

    def form_message(self, line: str, ok, ctx) -> Optional[str]:
        """Свой отклик задачи по упавшей команде с pandas (None — общий)."""
        return None

    def wrong_message(self, given: str, ctx) -> str:
        trap = self.trap_message(given, ctx)
        if trap:
            return trap
        last = last_pandas(ctx.box)
        if last is not None and last[1] is False:
            line = last[0]
            if not (pykit.activated(ctx.box) or ".venv/bin/" in line):
                return MSG_MODULE
            return self.form_message(line, last[1], ctx) or MSG_CRASH
        return self.common_mistake(given, ctx) or self.FALLBACKS[_v(self, ctx.state)]


# --- 2. pd_read -------------------------------------------------------------------------------

_READ = "import pandas as pd; df = pd.read_csv(\"{f}\"{sep}); "


def _pd(f: str, tail: str, sep: str = "") -> str:
    """python3 -c 'import pandas as pd; df = pd.read_csv("f"); …' — из .venv."""
    return ("source .venv/bin/activate; python3 -c '" + _READ.format(f=f, sep=sep) + tail
            + "'")


class PdRead(PdAnswer):
    """pd.read_csv, .head(), .shape, .columns, .dtypes; sep=";"."""
    id = "pd_read"
    title = "Первый взгляд на таблицу"
    par = 75
    kinds = ("number", "text", "number")
    scroll = ("Таблица из файла: df = pd.read_csv(\"a.csv\") — таблица pandas DataFrame: "
              "строки и колонки.\n"
              "Смотрим: df.head() — первые 5 строк, df.shape — (строк, колонок); шапка — не "
              "строка.\n"
              "Имена колонок — df.columns, типы — df.dtypes: текст object, числа int64 и "
              "float64.")
    variants = (
        Variant("Сколько строк данных в transfers.csv? ans NUMBER",
                hints=("Прочти файл в pandas: df = pd.read_csv(\"transfers.csv\") — и спроси "
                       "df.shape.",
                       "df.shape — пара (строк, колонок); шапка в строки не входит. Не "
                       "забудь включить .venv.",
                       _pd("transfers.csv", "print(df.shape)") + " → ans первое число"),
                solution=_pd("transfers.csv", "print(df.shape)"),
                solution_script=_pd("transfers.csv", "print(df.shape[0])"),
                wrong=("wc -l < transfers.csv",),
                alternatives=("tail -n +2 transfers.csv | wc -l — строки без шапки, без "
                              "pandas",),
                key="rows"),
        Variant("Сколько колонок в transfers.csv и какой тип у колонки {col}? ans NUMBER TYPE",
                hints=("Колонки и их типы покажет pandas: df.shape и df.dtypes.",
                       "Колонок — второе число df.shape; тип — в df.dtypes напротив {col}. "
                       "Номера строк слева в head — индекс, не колонка.",
                       _pd("transfers.csv", "print(df.shape); print(df.dtypes)")
                       + " → ans NUMBER TYPE"),
                solution=_pd("transfers.csv", "print(df.shape); print(df.dtypes)"),
                solution_script=_pd("transfers.csv",
                                    "print(df.shape[1], df.dtypes[\"{col}\"])"),
                wrong=(_pd("transfers.csv", "print(df.shape[1] + 1, df.dtypes[\"{col}\"])"),),
                alternatives=("print(df.columns) — имена колонок списком",),
                key="dtypes"),
        Variant("Выгрузка payments.csv пришла с разделителем «;», а pandas режет по запятой. "
                "Свой разделитель — так: pd.read_csv(\"f.csv\", sep=\";\"). Сколько колонок "
                "в payments.csv? ans NUMBER",
                hints=("Открой файл глазами: head -n 3 payments.csv — что стоит между полями?",
                       "pd.read_csv по умолчанию режет по запятой; другой разделитель — "
                       "sep=\";\".",
                       _pd("payments.csv", "print(df.shape)", sep=", sep=\";\"")
                       + " → ans второе число"),
                solution=_pd("payments.csv", "print(df.shape)", sep=", sep=\";\""),
                solution_script=_pd("payments.csv", "print(df.shape[1])", sep=", sep=\";\""),
                wrong=(_pd("payments.csv", "print(df.shape[1])"),),
                alternatives=("head -n 1 payments.csv | tr \";\" \"\\n\" | wc -l — по "
                              "шапке, без pandas",),
                key="sep"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("pd.read_csv затягивает файл в таблицу DataFrame. df.shape — (строк, колонок): "
               "шапка — это имена колонок, а не строка; индекс слева — номера строк, не колонка.")
    spell = "pd.read_csv(\"f.csv\", sep=\";\"); df.head(); df.shape; df.columns; df.dtypes"
    trap_messages = {
        "header": "Это строки файла вместе с шапкой. Шапка — имена колонок, а не данные: "
                  "df.shape считает только строки данных.",
        "index": "Слева в выводе head — индекс, номера строк. Это не колонка: колонки — "
                 "df.columns.",
        "sep": "Одна колонка — значит, pandas не понял разделитель и склеил всё в одну. "
               "Скажи ему: sep=\";\".",
    }
    FALLBACKS = (
        "Не то. Строк данных — первое число в df.shape.",
        "Не то. Колонок — второе число df.shape, тип — в df.dtypes напротив имени колонки.",
        "Не то. Прочти файл с sep=\";\" и посмотри df.shape.",
    )

    def gen(self, rng, variant: int) -> dict:
        return pdkit.read_data(rng, variant)

    def files(self, box: Path, data: dict, variant: int) -> list:
        if variant == 2:
            pdkit.write_csv(box, "payments.csv", data["rows"], data["header"], sep=";")
            return ["payments.csv"]
        return super().files(box, data, variant)

    def public(self, data: dict) -> dict:
        return {"col": data["col"]} if "col" in data else {}


# --- 3. pd_filter -----------------------------------------------------------------------------

def _count(cond: str) -> str:
    return _pd("transfers.csv", "print(len(df[" + cond + "]))")


_GT = 'df["amount"] > {limit}'
_IN = 'df["city"].isin(["{c1}", "{c2}"])'
_AND = '(df["city"] == "{city}") & (df["amount"] > {limit})'


class PdFilter(PdAnswer):
    """df[условие], &, .isin, len(). Ответ — число строк, ловушки — порог (>=), один город
    вместо двух, «или» вместо «и»."""
    id = "pd_filter"
    title = "Отбор строк"
    par = 75
    scroll = ("Отбор строк: df[df[\"amount\"] > 500] — те, где условие верно; а сколько их "
              "— скажет len(…).\n"
              "Из списка: df[df[\"city\"].isin([\"Omsk\", \"Ufa\"])]; два условия — & "
              "(и), | (или),\n"
              "каждое в скобках: df[(df[\"city\"] == \"Omsk\") & (df[\"amount\"] > 500)]; "
              "слово and pandas не поймёт.")
    variants = (
        Variant("Сколько переводов в transfers.csv больше {limit}? Строго больше: ровно "
                "{limit} не в счёт. ans NUMBER",
                hints=("Отбери строки условием: df[df[\"amount\"] > {limit}].",
                       "Сколько строк осталось — len(…) вокруг отбора. Не забудь .venv.",
                       _count(_GT) + " → ans NUMBER"),
                solution=_count(_GT),
                wrong=(_count('df["amount"] >= {limit}'),),
                alternatives=("(df[\"amount\"] > {limit}).sum() — True считается как 1",),
                key="gt"),
        Variant("Сколько переводов в transfers.csv из городов {c1} и {c2} вместе? ans NUMBER",
                hints=("Город из списка — .isin([…]) у колонки city.",
                       "df[df[\"city\"].isin([\"{c1}\", \"{c2}\"])] — и len(…) вокруг.",
                       _count(_IN) + " → ans NUMBER"),
                solution=_count(_IN),
                wrong=(_count('df["city"] == "{c1}"'),),
                alternatives=("два отбора по == и сложить их len — дольше, но верно",),
                key="isin"),
        Variant("Сколько переводов из {city} больше {limit}? Нужно и то, и другое сразу. ans "
                "NUMBER",
                hints=("Два условия: город и сумма. В pandas их соединяет &, не and.",
                       "Каждое условие — в своих скобках: (…) & (…), и len(…) вокруг отбора.",
                       _count(_AND) + " → ans NUMBER"),
                solution=_count(_AND),
                wrong=(_count('(df["city"] == "{city}") | (df["amount"] > {limit})'),),
                alternatives=("отбор в два шага: сначала город, потом сумма",),
                key="and"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("df[условие] оставляет строки, где условие верно; len — сколько их. Условия "
               "склеивают & и |, каждое в скобках: and и or с колонками pandas не прокатят.")
    spell = "df[df[\"a\"] > 5]; df[\"c\"].isin([…]); (…) & (…); len(df)"
    trap_messages = {
        "edge": "Это вместе с переводами ровно на {limit}. «Больше» — это >, а >= берёт и "
                "сам порог.",
        "one": "Это только один город. Оба сразу — .isin([…]) со списком из двух.",
        "or": "Это «или»: город ИЛИ сумма. Нужно и то, и другое — &, каждое условие в "
              "скобках.",
    }
    MSG_AND = ("В pandas условия соединяют & (и) и | (или), а каждое — в своих скобках: "
               "(…) & (…). Слова and и or с колонками не работают.")
    FALLBACKS = (
        "Не то. Отбери строки с суммой больше порога и посчитай их: len(df[…]).",
        "Не то. Оставь строки обоих городов: .isin([…]) — и посчитай len(…).",
        "Не то. Соедини оба условия через & и посчитай строки: len(df[(…) & (…)]).",
    )

    def gen(self, rng, variant: int) -> dict:
        return pdkit.filter_data(rng, variant)

    def public(self, data: dict) -> dict:
        return {k: data[k] for k in ("limit", "c1", "c2", "city") if k in data}

    def form_message(self, line: str, ok, ctx) -> Optional[str]:
        """MSG_AND — только когда в коде python3 -c (внутри кавычек) отбор df[…] соединяет
        условия: and/or вместо & и |, или & и | без скобок. Конвейер оболочки (… | head) — не
        повод (M5 ревью Q4)."""
        for m in _DASH_C.finditer(line):
            code = m.group(1) if m.group(1) is not None else m.group(2)
            for inside in re.findall(r"\[(.*)\]", code):
                if re.search(r"\b(?:and|or)\b|[&|]", inside):
                    return self.MSG_AND
        return None


# --- 4. pd_groupby ----------------------------------------------------------------------------

_SUMS = 's = df.groupby("city")["amount"].sum(); '
_BY_CITY = 's.sort_values(ascending=False)'
_BY_DEPT = 'df.groupby("dept")["amount"].mean().round(2)'


class PdGroupby(PdAnswer):
    """groupby, .sum(), .sort_values(ascending=False), .round(2), .index; B — .mean() (учит
    текст варианта). Ничьих нет: суммы городов разведены постройкой (pdkit.spread)."""
    id = "pd_groupby"
    title = "Итоги по группам"
    par = 90
    kinds = ("text", "number", "text")
    scroll = ("По группам: df.groupby(\"city\")[\"amount\"].sum() — сумма по каждому "
              "городу.\n"
              "Сортировка: .sort_values(ascending=False) — от большего, а без него — от "
              "меньшего.\n"
              "Первые N — .head(3); имена групп — .index, первое — .index[0].")
    variants = (
        Variant("В каком городе по transfers.csv переведено больше всего — по сумме amount? "
                "ans CITY",
                hints=("Сложи суммы по городам: df.groupby(\"city\")[\"amount\"].sum().",
                       "Отсортируй от большего — .sort_values(ascending=False): лидер будет "
                       "первым.",
                       _pd("transfers.csv", _SUMS + "print(" + _BY_CITY + ")")
                       + " → ans первый город"),
                solution=_pd("transfers.csv", _SUMS + "print(" + _BY_CITY + ")"),
                solution_script=_pd("transfers.csv",
                                    _SUMS + "print(" + _BY_CITY + ".index[0])"),
                wrong=(_pd("transfers.csv", 'print(df.groupby("city")["amount"].sum()'
                                            '.sort_values().index[0])'),),
                alternatives=("…sort_values().tail(1) — лидер внизу списка по возрастанию",),
                key="leader"),
        Variant("Какой средний перевод в отделе {dept} (колонка dept)? Средний — .mean() вместо "
                ".sum(); до 2 знаков округлит .round(2): ans NUMBER",
                hints=("Сгруппируй по отделу: df.groupby(\"dept\")[\"amount\"].",
                       "Средний по каждой группе — .mean(), до 2 знаков — .round(2); нужный "
                       "отдел найдёшь в списке.",
                       _pd("transfers.csv", "print(" + _BY_DEPT + ")") + " → ans число "
                       "напротив {dept}"),
                solution=_pd("transfers.csv", "print(" + _BY_DEPT + ")"),
                solution_script=_pd("transfers.csv", "print(" + _BY_DEPT + '["{dept}"])'),
                wrong=(_pd("transfers.csv", 'print(df.groupby("dept")["amount"].sum()'
                                            '["{dept}"])'),),
                alternatives=("df[df[\"dept\"] == \"{dept}\"][\"amount\"].mean() — сначала "
                              "отбор, потом среднее",),
                key="mean"),
        Variant("Назови три города с наибольшей суммой переводов в transfers.csv — от большей к "
                "меньшей. ans CITY CITY CITY",
                hints=("Суммы по городам — groupby и .sum(), потом сортировка.",
                       "От большего — .sort_values(ascending=False), первые три — .head(3).",
                       _pd("transfers.csv", _SUMS + "print(" + _BY_CITY + ".head(3))")
                       + " → ans три города по порядку"),
                solution=_pd("transfers.csv", _SUMS + "print(" + _BY_CITY + ".head(3))"),
                solution_script=_pd("transfers.csv",
                                    _SUMS + "print(*" + _BY_CITY + ".head(3).index)"),
                wrong=(_pd("transfers.csv", 'print(*df.groupby("city")["amount"].sum()'
                                            '.sort_values().head(3).index)'),),
                alternatives=("….nlargest(3) — три наибольших сразу",),
                key="top3"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("groupby раскладывает строки по кучкам, .sum() или .mean() считает каждую. "
               "sort_values идёт от меньшего — чтобы лидер встал первым, нужен ascending=False.")
    spell = "df.groupby(\"c\")[\"a\"].sum(); .sort_values(ascending=False); .head(3)"
    trap_messages = {
        "min": "Это город с наименьшей суммой: sort_values без ascending=False сортирует от "
               "меньшего.",
        "sum": "Это сумма переводов отдела, а нужен средний: .mean() вместо .sum().",
        "all": "Это средний по всем переводам. Нужен средний в отделе {dept}: "
               "groupby(\"dept\").",
        "asc": "Это три города с наименьшей суммой: sort_values без ascending=False идёт от "
               "меньшего.",
    }
    MSG_ORDER = "Города те, но порядок другой: от большей суммы к меньшей."
    FALLBACKS = (
        "Не то. Сложи суммы по городам (groupby и .sum()) и отсортируй от большего.",
        "Не то. Средний по отделам — groupby(\"dept\") и .mean(); округли до 2 знаков.",
        "Не то. Суммы по городам от большего — .sort_values(ascending=False), первые три — "
        ".head(3).",
    )

    def gen(self, rng, variant: int) -> dict:
        return pdkit.groupby_data(rng, variant)

    def public(self, data: dict) -> dict:
        return {"dept": data["dept"]} if "dept" in data else {}

    def wrong_message(self, given: str, ctx) -> str:
        st = ctx.state
        if _v(self, st) == 2 and not self.trap_message(given, ctx):
            got, want = textnorm.parts(given or ""), textnorm.parts(self.expected(st))
            if got != want and sorted(got) == sorted(want):
                return self.MSG_ORDER
        return super().wrong_message(given, ctx)


# --- 5. pd_missing ----------------------------------------------------------------------------

_NA = 'df["amount"].isna().sum()'
_ZERO = 'df["amount"].fillna(0).mean().round(2)'
_NUM = 'pd.to_numeric(df["amount"], errors="coerce").isna().sum()'


class PdMissing(PdAnswer):
    """.isna(), .fillna(0), .mean(), pd.to_numeric(errors="coerce"). Ловушки: пропуски всей
    таблицы, среднее без пустых, dropna целыми строками, только пустые без грязных."""
    id = "pd_missing"
    title = "Дыры в таблице"
    par = 90
    # FB15: текст в числах (pd.to_numeric, errors="coerce") — шаг стража boss_pylib
    practice_variant = 2
    scroll = ("Пустая ячейка в pandas — NaN: df[\"amount\"].isna().sum() — сколько их в "
              "колонке.\n"
              "Пропуск как 0: df[\"amount\"].fillna(0); среднее — .mean(), а пустые оно молча "
              "пропустит.\n"
              "Текст в числа: pd.to_numeric(df[\"amount\"], errors=\"coerce\") — что не "
              "число, станет NaN.")
    variants = (
        Variant("Сколько пустых ячеек в колонке amount файла transfers.csv? ans NUMBER",
                hints=("Пустая ячейка в pandas — NaN; найдёт их .isna() у колонки.",
                       "True считается как 1: .isna().sum() — сколько пустых. Только amount, "
                       "не вся таблица.",
                       _pd("transfers.csv", "print(" + _NA + ")") + " → ans NUMBER"),
                solution=_pd("transfers.csv", "print(" + _NA + ")"),
                wrong=(_pd("transfers.csv", "print(df.isna().sum().sum())"),),
                alternatives=("df.isna().sum() — пропуски по каждой колонке сразу",),
                key="isna"),
        Variant("Какой средний перевод в transfers.csv, если пустую сумму считать нулём? "
                "Округли до 2 знаков — .round(2): ans NUMBER",
                hints=("Пустые .mean() молча пропускает — а здесь они нули.",
                       "Сначала .fillna(0), потом .mean() и .round(2).",
                       _pd("transfers.csv", "print(" + _ZERO + ")") + " → ans NUMBER"),
                solution=_pd("transfers.csv", "print(" + _ZERO + ")"),
                wrong=(_pd("transfers.csv", 'print(df["amount"].mean().round(2))'),
                       _pd("transfers.csv", 'print(df.dropna()["amount"].mean().round(2))')),
                alternatives=("сумма, делённая на число строк: df[\"amount\"].sum() / "
                              "len(df)",),
                key="fillna"),
        Variant("В колонке amount файла transfers.csv попадаются записи вроде «1 200» и «12,5». "
                "Сколько значений amount не читаются как число — вместе с пустыми? ans NUMBER",
                hints=("Такие записи pandas читает как текст; в число их переводит "
                       "pd.to_numeric.",
                       "errors=\"coerce\" делает из нечисла NaN — дальше .isna().sum().",
                       _pd("transfers.csv", "print(" + _NUM + ")") + " → ans NUMBER"),
                solution=_pd("transfers.csv", "print(" + _NUM + ")"),
                wrong=(_pd("transfers.csv", "print(" + _NA + ")"),),
                alternatives=("сначала новая колонка: df[\"n\"] = pd.to_numeric(…), потом "
                              "df[\"n\"].isna().sum()",),
                key="coerce"),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Пустая ячейка — NaN: .isna() её видит, а .mean() и .sum() молча пропускают. "
               ".fillna(0) делает её нулём; текст в числа — pd.to_numeric(errors=\"coerce\").")
    spell = "df[\"a\"].isna().sum(); .fillna(0); pd.to_numeric(df[\"a\"], errors=\"coerce\")"
    trap_messages = {
        "all": "Это пропуски во всей таблице, а спрашивают только про amount.",
        "skipna": "Это среднее без пустых: .mean() молча их пропускает. Пустые — нули: сначала "
                  ".fillna(0).",
        "dropna": "Ты потерял строки: dropna выкинул их целиком, даже где пусто только в "
                  "отделе. Пустую сумму — в ноль: fillna(0).",
        "isna": "Это только пустые ячейки. «1 200» — текст, isna его не видит: сначала "
                "pd.to_numeric(…, errors=\"coerce\").",
    }
    FALLBACKS = (
        "Не то. Пустые ячейки колонки amount: .isna().sum().",
        "Не то. Пустые — в ноль (.fillna(0)), потом .mean() и .round(2).",
        "Не то. Переведи колонку в числа с errors=\"coerce\" и посчитай NaN.",
    )

    def gen(self, rng, variant: int) -> dict:
        return pdkit.missing_data(rng, variant)


TASKS = [PdInstall(), PdRead(), PdFilter(), PdGroupby(), PdMissing()]


def add_tasks(more) -> None:
    """FB15: дописать задачи модуля в TASKS (без повторов); страж трека — всегда последним.
    Модули pdmore и pdboss берут отсюда базу задач и дописывают себя сами, поэтому порядок их
    импорта не важен: сортировка устойчивая, обычные задачи идут в порядке модулей."""
    have = {t.id for t in TASKS}
    TASKS.extend(t for t in more if t.id not in have)
    TASKS.sort(key=lambda t: bool(getattr(t, "boss", False)))


# FB15: вторая половина pandas — termit_app/tasks/pdmore.py (после пропусков), страж —
# termit_app/tasks/pdboss.py
from termit_app.tasks import pdmore  # noqa: E402,F401
from termit_app.tasks import pdregex  # noqa: E402,F401  (FB21: регулярки в pandas)
from termit_app.tasks import pdboss  # noqa: E402,F401  (страж — последним)
