"""Страж трека «Аналитика» boss_pylib (FB15, FB5 п. 37 и 49): мини-конвейер pipeline.py —
API → проверка данных → таблица → отчёт — врёт на каждом шаге.

Как у boss_py: игрок чинит готовый скрипт, родитель кода не исполняет. Проверка — по файлам
(clients.csv, clean.csv, report.csv — разбор модулем csv), журналу учебного API (requests с
ключом, обе страницы) и неизменности transfers.csv; задача скрытая, вердикт судьи. Каждый
приём — из задач трека: страницы API (py_urllib, rq_get), ключ в заголовке (rq_get C —
вариант-практика), текст в числах (pd_missing C — вариант-практика), склейка по номеру
(pd_merge C — вариант-практика), сортировка от большего (pd_groupby)."""
from pathlib import Path
from typing import List, Optional

from termit_app.tasks import envkit, kit, pdkit, pydata, pykit
from termit_app.tasks.base import Task, Variant, Verdict, memo_marks
from termit_app.tasks.pydata import _v, full_venv

_RUN = "source .venv/bin/activate && python3 pipeline.py"
FIXES = ("pages", "numbers", "join", "order")
_LIES = {"pages": ("for page in [1]:", "for page in [1, 2]:"),
         "numbers": ('df["amount"] = df["amount"].astype(float)',
                     'df["amount"] = pd.to_numeric(df["amount"], errors="coerce")'),
         "join": ('m = pd.merge(clients, df, on="name")',
                  'm = pd.merge(clients, df, on="client")'),
         "order": ("sort_values()", "sort_values(ascending=False)")}
_WHAT = ("total by city", "number of transfers by city", "total by client tier")


def pipeline(variant: int, fixed=()) -> str:
    """pipeline.py стража: fixed — что уже починено («pages», «numbers», «join», «order»)."""
    key, how = pdkit.BOSS_REPORT[variant]
    agg = "count" if how == "count" else "sum"

    def pick(name: str) -> str:
        bad, good = _LIES[name]
        return good if name in fixed else bad
    lines = ["# pipeline.py: clients from the API + transfers.csv -> report.csv "
             f"({_WHAT[variant]})",
             "import os", "", "import pandas as pd", "import sockhttp", "",
             "s = sockhttp.session()    # requests.Session for the game server in api.sock",
             f'key = {{"X-Api-Key": os.environ["{pdkit.CLIENTS_KEY}"]}}', "",
             "# 1. clients from all API pages into clients.csv", "rows = []",
             pick("pages"),
             '    r = s.get(f"http://api/clients?page={page}", headers=key, timeout=5)',
             "    r.raise_for_status()", '    rows += r.json()["items"]',
             "clients = pd.DataFrame(rows)", 'clients.to_csv("clients.csv", index=False)', "",
             "# 2. transfers: amounts that are not numbers become empty, into clean.csv",
             'df = pd.read_csv("transfers.csv")', pick("numbers"),
             'df.to_csv("clean.csv", index=False)', "",
             f"# 3. transfers with their clients, {_WHAT[variant]}, biggest first, into report.csv",
             pick("join"),
             f't = m.groupby("{key}")["amount"].{agg}().' + pick("order"),
             't.to_csv("report.csv")', "print(t)"]
    return "\n".join(lines) + "\n"


def _script(variant: int, fixed=FIXES) -> str:
    body = pipeline(variant, fixed).rstrip("\n")
    return pykit.py(f"cat > pipeline.py <<'{pykit.HEREDOC}'\n{body}\n{pykit.HEREDOC}\n{_RUN}\n")


def _wrong(variant: int):
    return tuple(_script(variant, [f for f in FIXES if f != miss]) for miss in FIXES)


_SHOWN = (_RUN + " → прочти traceback → nano pipeline.py: for page in [1, 2]:; "
          "pd.to_numeric(df[\"amount\"], errors=\"coerce\"); pd.merge(…, on=\"client\"); "
          ".sort_values(ascending=False) → " + _RUN)
_H1 = ("Запусти и прочти: " + _RUN + " — последняя строка traceback скажет, что сломалось; "
       "править — nano pipeline.py.")
_H2 = ("Сколько страниц клиентов, скажет сам API: next в ответе. Суммы вроде «1 200» — текст; "
       "у тёзок одно имя; отчёт — от большего.")
_H3 = ("for page in [1, 2]:; pd.to_numeric(df[\"amount\"], errors=\"coerce\"); "
       "on=\"client\" вместо on=\"name\"; .sort_values(ascending=False) — и снова " + _RUN)


class BossPylib(Task):
    """Страж «Аналитики»: pipeline.py собирает отчёт и врёт в четырёх местах — одна страница
    API из двух, astype(float) на суммах с текстом (падает), склейка по имени (тёзки), отчёт
    от меньшего. Шаги — по файлам и журналу API; transfers.csv не трогают."""
    id = "boss_pylib"
    track = "pydata"
    title = "Конвейер-кровопийца"
    boss = True
    par = 600
    pinned_python = True
    stock = "full"
    needs_judge = True
    tool = "python"
    secret_keys = ("clients", "clean", "report", "traps", "rows", "transfers_sha")
    scroll = ("Конвейер врёт — читай traceback снизу; ValueError у сумм — в них текст: "
              "pd.to_numeric(df[\"amount\"], errors=\"coerce\").\n"
              "API отдаёт страницами — смотри next; ключ — s.get(адрес, headers={\"X-Api-Key\": "
              "os.environ[\"CLIENTS_KEY\"]}).\n"
              "Склейка — по номеру клиента; число строк в группе — .count(); от большего — "
              ".sort_values(ascending=False).")
    steps = ("clients.csv — все клиенты со всех страниц API, запросом requests с ключом",
             "clean.csv — все переводы, суммы-текст стали пустыми, transfers.csv не тронут",
             "report.csv — верные итоги по группам: склейка по номеру клиента",
             "report.csv — от большего к меньшему")
    variants = tuple(
        Variant(text, hints=(_H1, _H2, _H3), solution=_SHOWN, solution_script=_script(i),
                wrong=_wrong(i),
                alternatives=("head -n 5 clean.csv — проверить, что суммы стали числами",))
        for i, text in enumerate((
            "pipeline.py собирает отчёт — клиенты с API, переводы из transfers.csv, итог "
            "по городам — и выдаёт себя за правильный; запусти его в .venv, прочти traceback и "
            "почини конвейер по шагам ниже.",
            "Конвейер pipeline.py считает, сколько переводов в каждом городе, — и врёт на каждом "
            "шаге: клиенты с API, проверка сумм, склейка, отчёт. Почини его по шагам ниже.",
            "pipeline.py сводит переводы по уровням клиентов (tier) — клиенты с API, переводы "
            "из transfers.csv — и тихо врёт; почини конвейер по шагам ниже.")))
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Конвейер врёт тихо: берёт одну страницу из двух, падает на суммах-тексте, "
               "склеивает тёзок по имени и ставит лидера последним. Лечится по шагам: "
               "запустил, прочёл traceback и файлы, поправил, снова запустил.")
    spell = ("next у API → pd.to_numeric(…, errors=\"coerce\") → on=\"client\" → "
             "sort_values(ascending=False)")
    MSG_GONE = "pipeline.py пропал. Набери reset — соберу задачу заново."
    MSG_DATA = ("transfers.csv изменён, а это данные — их не правят: чинят конвейер. Набери "
                "reset — файл вернётся.")
    MSG_PAGES = "В clients.csv только первая страница. Страниц две — посмотри поле next в ответе."
    MSG_NOT_REQUESTS = ("В журнале API нет запросов pipeline.py (requests с ключом) ко всем "
                        "страницам — clients.csv пишет конвейер: " + _RUN)
    MSG_CLIENTS = "В clients.csv не те строки: их пишет pipeline.py со всех страниц /clients."
    MSG_CLEAN = ("В clean.csv не то: там все строки transfers.csv, а суммы-текст — пустые "
                 "(pd.to_numeric, errors=\"coerce\").")
    MSG_NAME = ("Итоги раздуты: склейка по имени размножила переводы тёзок. Склеивай по номеру: "
                "on=\"client\".")
    MSG_ASC = "Итоги верные, но от меньшего к большему. Нужно наоборот: ascending=False."
    MSG_REPORT = "В report.csv не те итоги: сверь склейку и группировку с заданием."
    MSG_HEAD = "Шапка report.csv не та: нужна {head} — её пишет t.to_csv(\"report.csv\")."
    MSG_NO_LOG = "Журнал учебного API не читается — набери reset."
    MSG_EMPTY = "{out} пуст: pipeline.py упал, не дописав его. Запусти и прочти traceback: " + _RUN
    MSG_VALUE = ("Конвейер упал с ValueError: в суммах есть текст вроде «1 200». "
                 "astype(float) его не прочтёт — pd.to_numeric(…, errors=\"coerce\") сделает "
                 "из него NaN.")

    def reads_script(self) -> bool:
        return False

    def env_for(self, state: dict) -> dict:
        return {pdkit.CLIENTS_KEY: state["key"]}

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        from termit_app import apiserver
        box = Path(box)
        apiserver.link(box)
        full_venv(box)
        d = pdkit.boss_pylib_data(rng, variant)
        kit.write(box / "transfers.csv", pdkit.boss_transfers_csv(d["rows"]))
        kit.write(box / "pipeline.py", pipeline(variant))
        d["transfers_sha"] = kit.sha(box / "transfers.csv")
        return d

    def service(self, box, state):
        from termit_app import apiserver
        return apiserver.open_server(box, pdkit.clients_routes(state))

    # --- шаги: (готово, отклик или None) ---------------------------------------------------

    def _rows(self, ctx, rel: str):
        kind, raw = envkit.box_file(ctx.box, rel)
        if kind == "missing":
            return None, None
        if kind == "ok" and not raw.strip():
            return None, self.MSG_EMPTY.format(out=rel)
        rows, msg = pykit.read_csv(ctx.box, rel, _RUN)
        return rows, msg

    def _hits(self, ctx) -> List[dict]:
        svc = ctx.service
        if svc is None or not hasattr(svc, "journal"):
            return []
        return [e for e in svc.journal()
                if e.get("path") == "/clients" and e.get("code") == 200
                and str(e.get("user_agent") or "").startswith(pdkit.REQUESTS_AGENT)
                and e.get("api_key") == ctx.state["key"]]

    @staticmethod
    def _same_clients(body, want) -> bool:
        if len(body) != len(want):
            return False
        got = sorted(tuple(r) for r in body)
        exp = sorted((str(c["client"]), c["name"], c["city"], c["tier"]) for c in want)
        return got == exp

    def _step_clients(self, ctx):
        st = ctx.state
        rows, msg = self._rows(ctx, "clients.csv")
        if rows is None:
            return False, msg
        if rows[0] != pdkit.CLIENTS_HEADER:
            return False, self.MSG_CLIENTS
        body = rows[1:]
        if self._same_clients(body, st["clients"]):
            if ctx.service is None:
                return False, self.MSG_NO_LOG
            pages = {(e["query"].get("page") or ["1"])[0] for e in self._hits(ctx)}
            ok = {"1", "2"} <= pages
            return ok, None if ok else self.MSG_NOT_REQUESTS
        traps = dict((k, t) for k, t in st.get("traps") or ())
        if self._same_clients(body, traps.get("first") or []):
            return False, self.MSG_PAGES
        return False, self.MSG_CLIENTS

    def _step_clean(self, ctx):
        st = ctx.state
        if kit.sha_in_box(ctx.box, "transfers.csv") != st.get("transfers_sha"):
            return False, self.MSG_DATA
        rows, msg = self._rows(ctx, "clean.csv")
        if rows is None:
            return False, msg
        if rows[0] != pdkit.BOSS_TR_HEADER:
            return False, self.MSG_CLEAN
        body, want = rows[1:], st["clean"]
        if len(body) != len(want):
            return False, self.MSG_CLEAN
        for g, w in zip(body, want):
            if len(g) != 5 or g[:4] != w[:4]:
                return False, self.MSG_CLEAN
            if w[4] == "":
                if g[4].strip():
                    return False, self.MSG_CLEAN
            elif not pykit.same_num(g[4], w[4]):
                return False, self.MSG_CLEAN
        return True, None

    def _same_report(self, body, want, ordered: bool) -> bool:
        if len(body) != len(want) or any(len(r) != 2 for r in body):
            return False
        if not ordered:
            body = sorted(body, key=lambda r: r[0])
            want = sorted(want, key=lambda r: r[0])
        return all(g[0] == w[0] and pykit.same_num(g[1], w[1]) for g, w in zip(body, want))

    def _report_steps(self, ctx):
        st = ctx.state
        rows, msg = self._rows(ctx, "report.csv")
        if rows is None:
            return (False, msg), (False, None)
        head = st["report_head"]
        if rows[0] != head:
            text = self.MSG_HEAD.format(head=",".join(head))
            return (False, text), (False, None)
        body = rows[1:]
        traps = dict((k, t) for k, t in st.get("traps") or ())
        if self._same_report(body, st["report"], ordered=False):
            if self._same_report(body, st["report"], ordered=True):
                return (True, None), (True, None)
            return (True, None), (False, self.MSG_ASC)
        if self._same_report(body, traps.get("name") or [], ordered=False):
            return (False, self.MSG_NAME), (False, None)
        return (False, self.MSG_REPORT), (False, None)

    def _steps(self, ctx):
        right, order = self._report_steps(ctx)
        return [self._step_clients(ctx), self._step_clean(ctx), right, order]

    def progress(self, ctx):
        return [ok for ok, _ in self._steps(ctx)]

    def _crash(self, ctx) -> Optional[str]:
        last = pykit.last_command(ctx.box)
        if last is None or not pykit.runs_python(last[0]) or last[1] is not False:
            return None
        if not pykit.activated(ctx.box):
            return pykit.MSG_MODULE
        typ = pykit.out_type(ctx.box)
        if typ == "ValueError":
            return self.MSG_VALUE
        return pykit.MSG_TRACEBACK_TYPE.format(typ=typ) if typ else pykit.MSG_TRACEBACK

    def check(self, ctx) -> Verdict:
        if envkit.box_file(ctx.box, "pipeline.py")[0] == "missing":
            return Verdict(False, self.MSG_GONE)
        steps = self._steps(ctx)
        memo_marks(ctx, [ok for ok, _ in steps])
        if all(ok for ok, _ in steps):
            return Verdict(True)
        if steps[1][1] == self.MSG_DATA:
            return Verdict(False, self.MSG_DATA)
        crash = self._crash(ctx)
        if crash:
            return Verdict(False, crash)
        for ok, msg in steps:
            if not ok and msg:
                return Verdict(False, msg)
        return Verdict(False)


TASKS = [BossPylib()]
pydata.add_tasks(TASKS)
