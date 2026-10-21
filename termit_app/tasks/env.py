"""Трек «Окружение и скрипты» (часть 7, «Фабрика демонов»): переменные окружения, export и
.env, PATH и which, shebang и коды возврата, конфиги в JSON, проверка чужих скриптов, venv и
pip без сети.

Основа трека (пачка P1): окружение задачи (Task.env_for → .termit/env.zsh), закреплённый
python3 (pinned_python), запас готовых venv (stock) и учебный clamscan (uses_av) живут в base,
sandbox, pyenvs и avstub. Данные и разбор сделанного — termit_app/tasks/envkit.py: родитель
читает файлы и журнал команд, код игрока не исполняет. Порядок в TASKS — порядок обучения.

Правило 16 (fix1 P1): значение, которое знают и игрок (окружение задачи, файл в песочнице), и
судья, в secret_keys не кладём — иначе write_env откажет (ValueError)."""
import os
import random
import re
import shlex
import shutil
import stat
from pathlib import Path
from typing import Dict, List, Optional

from termit_app import textnorm
from termit_app.tasks import envkit, kit
from termit_app.tasks.base import AnswerTask, Task, Variant, Verdict, variant_index
from termit_app.tasks.base import memo_marks as base_memo_marks


# --- E5 -------------------------------------------------------------------------------------

class EnvVars(AnswerTask):
    """env, echo $ИМЯ, printenv, env | grep: переменные задачи — в .termit/env.zsh."""
    id = "env_vars"
    track = "env"
    title = "Что в окружении"
    par = 45
    scroll = ("Окружение — переменные, которые оболочка отдаёт каждой запущенной программе. "
              "env — все они, по строке ИМЯ=значение. echo $HOME — значение "
              "одной (знак $ перед именем); printenv HOME — то же без $.\n"
              "env | grep APP_ — только нужные. Переменные — настройки, которые программа "
              "читает при запуске.")
    variants = (
        Variant("В окружении этой оболочки есть переменная APP_REGION. Какое у неё значение? "
                "ans ЗНАЧЕНИЕ",
                hints=("Все переменные печатает env, одну — echo $ИМЯ.",
                       "Перед именем — знак $: без него echo напечатает само имя.",
                       "echo $APP_REGION, затем ans ЗНАЧЕНИЕ"),
                solution="echo $APP_REGION",
                wrong=("echo APP_REGION", "echo $REGION"),
                alternatives=("printenv APP_REGION — то же без знака $",
                              "env | grep APP_REGION — строка целиком, значение после =")),
        Variant("Сколько переменных окружения начинаются с APP_? ans ЧИСЛО",
                hints=("Все переменные печатает env, по строке на каждую.",
                       "Отфильтруй env через grep: строки, которые НАЧИНАЮТСЯ с APP_, — знак ^ "
                       "в шаблоне; -c сосчитает.",
                       "env | grep -c '^APP_', затем ans ЧИСЛО"),
                solution="env | grep -c '^APP_'",
                wrong=("env | grep -c APP_",),
                alternatives=("env | cut -d= -f1 | grep -c '^APP_' — то же по одним именам",)),
        Variant("Одна из переменных окружения хранит значение {needle}. Как она называется? "
                "ans ИМЯ",
                hints=("env печатает строки ИМЯ=значение — найди нужную.",
                       "Отфильтруй env через grep по значению; имя — то, что до знака =.",
                       "env | grep {needle} | cut -d= -f1, затем ans ИМЯ"),
                solution="env | grep {needle} | cut -d= -f1",
                wrong=("env | grep {needle}",),
                alternatives=("env | grep {needle} — строка целиком, имя до знака =",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Окружение — пачка настроек, которую оболочка вручает каждой программе при "
               "запуске. Программа заглядывает туда, как в записку: где дом, какой язык.")
    spell = "env — все переменные; echo $ИМЯ — одна; env | grep ИМЯ — поиск"
    env_clear = ("APP_",)       # APP_* из ~/.zshrc владельца не сбивают счёт варианта B
    # ответ варианта A (значение APP_REGION) знает и окружение — не секрет (правило 16)
    secret_keys = ("answer", "traps")
    trap_messages = {
        "anywhere": "Сюда попали и строки, где APP_ стоит в значении. Нужны строки, которые с "
                    "APP_ НАЧИНАЮТСЯ: grep '^APP_'.",
    }
    MSG_NAME = "Это имя, а нужно значение: echo $APP_REGION"
    MSG_NEAR = ("Это значение REGION — другой переменной. Спрашивают APP_REGION: имя пиши "
                "целиком.")
    MSG_VALUE = "Сдай только значение — то, что после знака =."
    MSG_NAME_ONLY = "Сдай только имя — то, что до знака =."
    MSG_NEEDLE = ("Это само значение из условия, а спрашивают имя переменной: в строке env оно "
                  "стоит до знака =.")
    FALLBACKS = (
        "Не то. Значение одной переменной печатает echo $ИМЯ — со знаком $ и именем целиком.",
        "Не то. Считай строки env, которые НАЧИНАЮТСЯ с APP_.",
        "Не то. Найди строку с этим значением (env | grep) — имя стоит до знака =.",
    )

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        d = envkit.env_vars(rng)
        # переменные в task.json не кладём (там бы лежали и ответы B и C): их по зерну заново
        # собирает data(); traps — всегда (пусть пустые): задача скрытая, как все «найди и
        # назови». Ответ A — значение из окружения — не секрет (правило 16)
        st = {"traps": []}
        if variant == 1:
            st["answer"] = len(d["apps"])
            anywhere = sum("APP_" in f"{k}={v}" for k, v in d["vars"].items())
            st["traps"] = [["anywhere", anywhere]]
        elif variant == 2:
            st["needle"] = d["vars"][d["needle_name"]]
            st["answer"] = d["needle_name"]
        return st

    @staticmethod
    def data(state: dict) -> dict:
        """Данные envkit.env_vars этого рана: тот же поток зерна, что в make_state (сначала
        вариант, потом данные)."""
        rng = random.Random(state["_seed"])
        rng.randrange(3)
        return envkit.env_vars(rng)

    def env_for(self, state: dict) -> Dict[str, str]:
        return dict(self.data(state)["vars"])

    def _v(self, state: dict) -> int:
        return variant_index(state.get("_variant", 0), len(self.variants))

    def expected(self, state: dict) -> str:
        if "answer" in state:
            return str(state["answer"])
        return self.data(state)["vars"]["APP_REGION"]

    def answer_kind(self, state: dict) -> str:
        return "number" if self._v(state) == 1 else "text"

    def wrong_message(self, given: str, ctx) -> str:
        st, v = ctx.state, self._v(ctx.state)
        g = textnorm.clean(given)
        if v == 0:
            if g.lstrip("$").upper() == "APP_REGION":
                return self.MSG_NAME
            if "=" in g:
                return self.MSG_VALUE
            if textnorm.same_text(g, self.data(st)["vars"].get("REGION", "")):
                return self.MSG_NEAR
        if v == 2:
            if "=" in g:
                return self.MSG_NAME_ONLY
            if textnorm.same_text(g, st.get("needle", "")):
                return self.MSG_NEEDLE
        return (self.trap_message(given, ctx) or self.common_mistake(given, ctx)
                or self.FALLBACKS[v])


# --- E6 -------------------------------------------------------------------------------------

GREET = """#!/bin/sh
# Приветствие: пишет в greet.txt, что видит в окружении.
cd "$(dirname "$0")" || exit 1
if [ -n "$DEBUG" ]; then
  echo "greet.sh: DEBUG set — refusing" >&2
  echo "DEBUG set — refusing" > greet.txt
  exit 1
fi
echo "mode=${MODE:-none} lang=${LANG_CODE:-none}" > greet.txt
echo "greet.sh: готово, смотри greet.txt"
"""
MODES = ("fast", "quiet", "safe", "night", "batch", "live", "eco", "turbo")
LANGS = ("ru", "en", "de", "fr", "es", "it", "fi", "pt")


class ExportChild(Task):
    """export, разовое ИМЯ=значение ./cmd, unset: дочерний скрипт видит только окружение."""
    id = "export_child"
    track = "env"
    title = "Наследство"
    par = 60
    scroll = ("ИМЯ=значение — переменная только этой оболочки; запущенная программа её не "
              "видит. export ИМЯ=значение — передать её всем, кого запустишь.\n"
              "Разово: ИМЯ=значение ./скрипт. unset ИМЯ — убрать переменную.\n"
              "Задают без пробелов у = и без $ перед именем: $ИМЯ — это уже значение.")
    variants = (
        Variant("./greet.sh пишет в greet.txt то, что видит в MODE и LANG_CODE. Сделай, чтобы "
                "там было mode={mode} lang={lang}.",
                hints=("Программа видит только то, что ты отдал через export.",
                       "export MODE=… или запись перед командой: MODE=… LANG_CODE=… ./greet.sh",
                       "export MODE={mode} LANG_CODE={lang}; ./greet.sh"),
                solution="export MODE={mode} LANG_CODE={lang}; ./greet.sh",
                wrong=("MODE={mode}; LANG_CODE={lang}; ./greet.sh",),
                alternatives=("MODE={mode} LANG_CODE={lang} ./greet.sh — разово, без export",)),
        Variant("Запусти ./greet.sh один раз с MODE={mode} и LANG_CODE={lang}, не оставляя эти "
                "переменные в оболочке: в greet.txt должно быть mode={mode} lang={lang}.",
                hints=("Запись перед командой действует только на эту команду.",
                       "Обе переменные — перед ./greet.sh через пробел, без ; и без export.",
                       "MODE={mode} LANG_CODE={lang} ./greet.sh"),
                solution="MODE={mode} LANG_CODE={lang} ./greet.sh",
                wrong=("export MODE={mode} LANG_CODE={lang}; ./greet.sh",),
                alternatives=("export MODE={mode} LANG_CODE={lang}; ./greet.sh; unset MODE "
                              "LANG_CODE — тоже ничего не останется",)),
        Variant("./greet.sh не работает, пока в окружении есть DEBUG. Убери её и получи в "
                "greet.txt mode={mode} lang={lang}.",
                hints=("Запусти ./greet.sh и прочти, на что он жалуется.",
                       "unset DEBUG убирает переменную; дальше — как обычно: MODE=… LANG_CODE=… "
                       "./greet.sh",
                       "unset DEBUG; MODE={mode} LANG_CODE={lang} ./greet.sh"),
                solution="unset DEBUG; MODE={mode} LANG_CODE={lang} ./greet.sh",
                wrong=("MODE={mode} LANG_CODE={lang} ./greet.sh",),
                alternatives=("env -u DEBUG MODE={mode} LANG_CODE={lang} ./greet.sh — без DEBUG "
                              "только для этого запуска: -u убирает переменную",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Программа получает от оболочки только экспортированные переменные. Запись перед "
               "командой — разовый подарок одной программе, unset — забрать насовсем.")
    spell = "export ИМЯ=знач — передать детям; ИМЯ=знач ./cmd — разово; unset ИМЯ"
    OUT = "greet.txt"
    MSG_NOT_SET = ("greet.sh не видит MODE и LANG_CODE: задай их и передай скрипту — export или "
                   "запись перед командой.")
    MSG_DEBUG = "В окружении осталась DEBUG, и greet.sh отказался работать: unset DEBUG"
    MSG_LEFT = ("В greet.txt верно, но {names} {verb} в оболочке, а просили разово: "
                "ИМЯ=значение ./greet.sh. Убрать сейчас — unset {plain}.")
    MSG_OTHER = "В greet.txt другие значения, а нужно mode={mode} lang={lang}."
    # E24a, I9: промахи формы присваивания и отклик по каждой переменной
    MSG_SPACES = "Пробелы вокруг = нельзя: MODE=значение слитно — иначе zsh ищет команду MODE."
    MSG_DOLLAR = ("Когда задаёшь переменную, $ не пиши: export MODE=значение. $MODE — это "
                  "уже её значение (а оно пустое — отсюда и странная ошибка).")
    MSG_COMMA = ("Запятая попала в значение: переменные перечисляют через пробел — export "
                 "MODE=… LANG_CODE=…")
    MSG_SEEN = "В greet.txt {fields}: {why}."
    WHY = {"none": "{name} не задана",
           "bare": "{name} задана, но не экспортирована — скрипт её не получит: нужен export",
           "once": "{name} была разовой — запись перед командой действует только на неё; обе "
                   "переменные ставь перед одним ./greet.sh",
           "late": "{name} экспортирована уже после запуска — прогони ./greet.sh ещё раз"}
    NAMES = ("MODE", "LANG_CODE")

    def _slip(self, lines) -> Optional[str]:
        """Промах формы присваивания MODE/LANG_CODE: пробел у =, $ перед именем, запятая между
        присваиваниями. Смотрится только ПОСЛЕДНЯЯ попытка задать каждое имя (FINAL fix1, I1):
        исправленный промах не перекрывает настоящую причину. Линейно по журналу."""
        last: Dict[str, Optional[str]] = {}

        def mark(word: str, slip: Optional[str]) -> None:
            name = word.lstrip("$").split("=", 1)[0]
            if name in self.NAMES:
                last[name] = slip

        for assigns, cmd, args in envkit.commands(lines):
            if cmd in self.NAMES and args and args[0].startswith("="):
                mark(cmd, self.MSG_SPACES)
            elif cmd is not None and cmd.startswith("$") and "=" in cmd:
                mark(cmd, self.MSG_DOLLAR)
            if cmd in envkit.EXPORTERS:
                for k, a in enumerate(args):
                    if a == "=" or (a.startswith("=") and k > 0):
                        mark(args[k - 1], self.MSG_SPACES)
                    elif a.startswith("$") and "=" in a:
                        mark(a, self.MSG_DOLLAR)
                    elif "=" in a and not a.startswith("="):
                        mark(a, self.MSG_COMMA if a.endswith(",") else None)
            for n, v in assigns:
                mark(n, self.MSG_COMMA if v.endswith(",") else None)
        for name in self.NAMES:
            if last.get(name):
                return last[name]
        return None

    def _why(self, lines, name: str) -> str:
        """Почему greet.sh не увидел name: не задана / разовая / без export / export позже."""
        exported, bare, once = set(), set(), set()
        for assigns, cmd, args in envkit.commands(lines):
            names = {n for n, _ in assigns}
            if cmd is None:
                bare |= names
            elif cmd in envkit.EXPORTERS:
                exported |= {a.split("=", 1)[0] for a in args if not a.startswith(("-", "+"))}
            elif cmd == "unset":
                gone = {a for a in args if not a.startswith("-")}
                exported -= gone
                bare -= gone
            else:
                once |= names
        kind = ("late" if name in exported else "bare" if name in bare
                else "once" if name in once else "none")
        return self.WHY[kind].format(name=name)

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        os.chmod(kit.write(Path(box) / "greet.sh", GREET), 0o755)
        return {"mode": rng.choice(MODES), "lang": rng.choice(LANGS)}

    def env_for(self, state: dict) -> Dict[str, str]:
        return {"DEBUG": "1"} if self._v(state) == 2 else {}

    def _v(self, state: dict) -> int:
        return variant_index(state.get("_variant", 0), len(self.variants))

    def check(self, ctx) -> Verdict:
        st = ctx.state
        lines = [c.line for c in ctx.cmds]
        kind, text = envkit.box_text(ctx.box, self.OUT, envkit.TEXT_CAP)
        if kind == "missing":
            return Verdict(False, self._slip(lines))
        bad = envkit.file_problem(kind, self.OUT)
        if bad:
            return Verdict(False, bad)
        if "refusing" in text:
            return Verdict(False, self.MSG_DEBUG)
        line = envkit.first_line(text)
        if line == f"mode={st['mode']} lang={st['lang']}":
            left = sorted(envkit.shell_vars(lines) & {"MODE", "LANG_CODE"})
            if self._v(st) == 1 and left:
                return Verdict(False, self.MSG_LEFT.format(
                    names=" и ".join(left), plain=" ".join(left),
                    verb="остались" if len(left) > 1 else "осталась"))
            return Verdict(True)
        slip = self._slip(lines)
        if slip:
            return Verdict(False, slip)
        fields = [f for f in line.split() if f in ("mode=none", "lang=none")]
        if fields and not envkit.assigned(lines) & {"MODE", "LANG_CODE"}:
            return Verdict(False, self.MSG_NOT_SET)
        if fields:
            why = [self._why(lines, "MODE" if f.startswith("mode") else "LANG_CODE")
                   for f in fields]
            return Verdict(False, self.MSG_SEEN.format(fields=" ".join(fields),
                                                       why="; ".join(why)))
        return Verdict(False, self.MSG_OTHER.format(**st))


# --- FB14: alias и свой ~/.zshrc ------------------------------------------------------------
# Курс-карта (раздел 6, «Окружение»): короткое имя для длинной команды — alias в ~/.zshrc
# песочницы, source ~/.zshrc — перечитать; вариант C — функция mkcd (alias не умеет
# аргументы в середине). Проверка — по результату: отчёт пишет учебный скрипт, и журнал
# показывает, что его звали коротким именем, а не полным путём.

REPORT_SH = """#!/bin/sh
# Daily report: writes the chosen mode (first word) into report.txt.
echo "report ${{1:-none}}" > {out}
echo "daily_report: done, see report.txt"
"""
REPORT_MODES = ("short", "full", "night", "brief", "weekly", "sales")
ALIAS_NAME = "rep"
ALIAS_RC_HEAD = "# my settings\nexport EDITOR=nano\n"
MKCD_DIRS = ("reports/2026-10", "photos/trip", "notes/work", "backup/old", "music/live")
_ALIAS_LINE = re.compile(r"^\s*alias\s+(?:--\s+)?([A-Za-z_][\w-]*)=(.+)$")
_ALIAS_SPACED = re.compile(r"^\s*alias\s+[A-Za-z_][\w-]*\s+=|^\s*alias\s+[A-Za-z_][\w-]*=\s")
_FUNC_LINE = re.compile(r"^\s*(?:function\s+mkcd\b|mkcd\s*\(\s*\))")


def _alias_rc(mode: str) -> str:
    """Строка alias для варианта A и B: короткое имя → скрипт с ключом режима."""
    return f"alias {ALIAS_NAME}='~/tools/daily_report.sh {mode}'"


class AliasRc(Task):
    """alias ИМЯ='команда' в ~/.zshrc песочницы, source ~/.zshrc, функция mkcd."""
    id = "alias_rc"
    track = "env"
    title = "Короткое имя"
    par = 75
    scroll = ("alias ls='ls -a' — короткое имя для команды: без пробелов у =, команда — в "
              "одинарных кавычках.\n"
              "Насовсем — той же строкой в ~/.zshrc: echo \"alias …\" >> ~/.zshrc. "
              "source ~/.zshrc — перечитать файл в этом окне.")
    variants = (
        Variant("Каждый день ты набираешь ~/tools/daily_report.sh {mode}. Заведи короткое имя "
                "rep: строкой alias в ~/.zshrc, перечитай файл и запусти rep — он напишет "
                "report.txt.",
                hints=("alias rep='команда' — короткое имя; насовсем — эта строка в ~/.zshrc.",
                       "Допиши строку через >> (echo \"alias rep='…'\" >> ~/.zshrc), потом "
                       "source ~/.zshrc и rep.",
                       "echo \"alias rep='~/tools/daily_report.sh {mode}'\" >> ~/.zshrc; "
                       "source ~/.zshrc; rep"),
                solution="echo \"alias rep='~/tools/daily_report.sh {mode}'\" >> ~/.zshrc; "
                         "source ~/.zshrc; rep",
                solution_script="echo \"alias rep='~/tools/daily_report.sh {mode}'\" >> "
                                "~/.zshrc; source ~/.zshrc; eval rep",
                wrong=("~/tools/daily_report.sh {mode}",
                       "alias rep='~/tools/daily_report.sh {mode}'; eval rep"),
                alternatives=("nano ~/.zshrc — дописать строку alias руками, потом source "
                              "~/.zshrc",)),
        Variant("В ~/.zshrc уже есть короткое имя rep для отчёта, но source ~/.zshrc ругается "
                "bad assignment, и rep не работает. Почини строку, перечитай файл и запусти "
                "rep — он напишет report.txt.",
                hints=("source ~/.zshrc покажет ошибку и номер строки.",
                       "bad assignment — пробелы вокруг =. В alias имя, = и кавычка идут "
                       "вплотную: rep='…'. Убрать пробелы — sed.",
                       "sed -i '' 's/rep = /rep=/' ~/.zshrc; source ~/.zshrc; rep"),
                solution="sed -i '' 's/rep = /rep=/' ~/.zshrc; source ~/.zshrc; rep",
                solution_script="sed -i '' 's/rep = /rep=/' ~/.zshrc; source ~/.zshrc; eval rep",
                wrong=("~/tools/daily_report.sh {mode}",
                       "alias rep='~/tools/daily_report.sh {mode}'; eval rep"),
                alternatives=("nano ~/.zshrc — убрать пробелы вокруг = руками (Ctrl+O, "
                              "Enter, Ctrl+X), потом source ~/.zshrc",)),
        Variant("Заведи в ~/.zshrc функцию mkcd (короткое имя, которое принимает слова): "
                "mkcd ПАПКА создаёт папку со всеми родителями и сразу в неё заходит. "
                "Перечитай файл и сделай mkcd {target}.",
                hints=("alias не умеет вставлять слово в середину команды, функция (имя со "
                       "словами) умеет: $1 — первое слово после её имени.",
                       "Строка функции (имени со словами): mkcd() {{ mkdir -p \"$1\" && cd "
                       "\"$1\"; }} — допиши её в ~/.zshrc через >>, потом source ~/.zshrc.",
                       "echo 'mkcd() {{ mkdir -p \"$1\" && cd \"$1\"; }}' >> ~/.zshrc; source "
                       "~/.zshrc; mkcd {target}"),
                solution="echo 'mkcd() {{ mkdir -p \"$1\" && cd \"$1\"; }}' >> ~/.zshrc; "
                         "source ~/.zshrc; mkcd {target}",
                wrong=("mkdir -p {target}; cd {target}",
                       "mkcd() {{ mkdir -p \"$1\" && cd \"$1\"; }}; mkcd {target}"),
                alternatives=("nano ~/.zshrc — вписать функцию (имя со словами) руками; "
                              "function mkcd {{ … }} — та же функция другой записью",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("alias — короткое имя для длинной команды, функция — короткое имя, которое "
               "принимает слова ($1). Набранное в окне живёт до его закрытия; строка в "
               "~/.zshrc — в каждом новом окне, а source ~/.zshrc перечитывает файл сразу.")
    spell = "alias ИМЯ='команда' — короткое имя; в ~/.zshrc — насовсем; source ~/.zshrc"
    RC = ".termit/home/.zshrc"
    OUT = "report.txt"
    MSG_NO_REPORT = "report.txt нет: его пишет отчёт, когда ты запускаешь rep."
    MSG_OTHER = "В report.txt «{got}», а нужен отчёт со словом {mode}: проверь команду в alias."
    MSG_FULL = ("Отчёт есть, но ты звал его полным путём. Нужно коротким именем — просто rep.")
    MSG_RC = ("rep работает только в этом окне: строки alias нет в ~/.zshrc. Допиши её туда — "
              "тогда имя будет в каждом новом окне.")
    MSG_SPACED = ("В строке alias пробел вокруг = — zsh скажет bad assignment и имя не заведёт. "
                  "Пиши вплотную: alias rep='…'.")
    MSG_CLOBBER = ("> переписал ~/.zshrc целиком — прежние строки пропали. Дописывают >>. "
                   "reset вернёт файл.")
    MSG_NO_DIR = "Папки {target} нет: mkcd должна создать её (mkdir -p) и зайти в неё."
    MSG_NO_FUNC = ("Функции mkcd нет в ~/.zshrc: набранная в окне живёт до его закрытия. "
                   "Допиши её строкой в ~/.zshrc и перечитай: source ~/.zshrc.")
    MSG_NO_CALL = "Папка есть, но mkcd ты не звал. Набери mkcd {target}."
    MSG_NOT_IN = ("Папка есть, но ты не в ней: функция должна и создать папку, и зайти — "
                  "mkdir -p \"$1\" && cd \"$1\".")

    def _v(self, state: dict) -> int:
        return variant_index(state.get("_variant", 0), len(self.variants))

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        mode = rng.choice(REPORT_MODES)
        target = rng.choice(MKCD_DIRS)
        out = shlex.quote(str(Path(box) / self.OUT))
        os.chmod(kit.write(kit.home(box) / "tools" / "daily_report.sh",
                           REPORT_SH.format(out=out)), 0o755)
        rc = ALIAS_RC_HEAD
        if variant == 1:
            rc += _alias_rc(mode).replace("rep=", "rep = ", 1) + "\n"
        kit.write(Path(box) / self.RC, rc)
        return {"mode": mode, "target": target}

    @staticmethod
    def _called(lines, name: str) -> bool:
        """Звали ли name коротким именем (или через eval name — прогон эталона)."""
        for _, cmd, args in envkit.commands(lines):
            if cmd == name or (cmd == "eval" and args[:1] == [name]):
                return True
        return False

    def _rc_lines(self, rc: Optional[str]):
        return [x for x in (rc or "").splitlines() if not x.lstrip().startswith("#")]

    def _check_alias(self, ctx, rc: Optional[str], lines) -> Verdict:
        st = ctx.state
        kind, text = envkit.box_text(ctx.box, self.OUT, envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, self.OUT)
        if bad:
            return Verdict(False, bad)
        rc_lines = self._rc_lines(rc)
        spaced = any(_ALIAS_SPACED.match(x) for x in rc_lines)
        if kind == "missing":
            return Verdict(False, self.MSG_SPACED if spaced and lines else
                           (self.MSG_NO_REPORT if lines else None))
        got = envkit.first_line(text)
        if got != f"report {st['mode']}":
            return Verdict(False, self.MSG_OTHER.format(got=got, mode=st["mode"]))
        if not self._called(lines, ALIAS_NAME):
            return Verdict(False, self.MSG_FULL)
        if spaced:
            return Verdict(False, self.MSG_SPACED)
        if not any((m := _ALIAS_LINE.match(x)) and m.group(1) == ALIAS_NAME
                   and "daily_report" in m.group(2) for x in rc_lines):
            return Verdict(False, self.MSG_RC)
        return Verdict(True)

    def _check_func(self, ctx, rc: Optional[str], lines) -> Verdict:
        target = ctx.state["target"]
        p = Path(ctx.box) / target
        if not p.is_dir() or p.is_symlink():
            return Verdict(False, self.MSG_NO_DIR.format(target=target) if lines else None)
        if not any(_FUNC_LINE.match(x) for x in self._rc_lines(rc)):
            return Verdict(False, self.MSG_NO_FUNC)
        if not self._called(lines, "mkcd"):
            return Verdict(False, self.MSG_NO_CALL.format(target=target))
        if ctx.pwd is not None and Path(ctx.pwd).resolve() != p.resolve():
            return Verdict(False, self.MSG_NOT_IN)
        return Verdict(True)

    def check(self, ctx) -> Verdict:
        kind, rc = envkit.box_text(ctx.box, self.RC, envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, "~/.zshrc")
        if bad:
            return Verdict(False, bad)
        lines = [c.line for c in ctx.cmds]
        if "EDITOR=nano" not in (rc or ""):
            return Verdict(False, self.MSG_CLOBBER)
        if self._v(ctx.state) == 2:
            return self._check_func(ctx, rc, lines)
        return self._check_alias(ctx, rc, lines)


# --- FB9b: права — понятия ------------------------------------------------------------------
# Владелец (FB5 п. 24): «про права вообще надо рассказывать отдельно, а не только цифрами».
# Два урока по одному кругу понятий: perm_basics — зачем права и кто ты в системе (whoami,
# groups, id; владелец, группа, остальные; root и sudo — только рассказ), perm_rwx — что
# значат r, w, x у файла и у папки и откуда Permission denied. Ответ — то, что видно только
# своими глазами (имя, группа, номер) или после починки прав.


def _me():
    """Имя, основная группа и номер игрока — то, что напечатают whoami, groups и id -u."""
    import grp
    import pwd
    uid, gid = os.getuid(), os.getgid()
    try:
        name = pwd.getpwuid(uid).pw_name
    except KeyError:
        name = str(uid)
    try:
        group = grp.getgrgid(gid).gr_name
    except KeyError:
        group = str(gid)
    return name, group, uid, gid


class PermBasics(AnswerTask):
    id = "perm_basics"
    track = "env"
    title = "Кто ты в системе"
    scroll = ("Права решают, кто что может с файлом: на Mac много пользователей, чужое "
              "закрыто. У файла три круга: владелец, группа (круг пользователей с общими "
              "правами) и остальные.\n"
              "whoami — твоё имя; groups — твои группы (обычно staff, у хозяина Mac ещё "
              "admin); id — «identity», всё с номерами. root — суперпользователь, ему можно всё; sudo — "
              "«superuser do», команда от его имени.")
    variants = (
        Variant("Под каким именем тебя знает система? Сдай его: ans ИМЯ",
                hints=("Имя в системе спрашивают командой «кто я».",
                       "who am i — пишется слитно: whoami.",
                       "whoami, потом ans ИМЯ"),
                solution="whoami",
                wrong=("groups | awk '{{print $1}}'",),
                alternatives=("id -un — то же: -u — user, -n — name, имя вместо номера",)),
        Variant("Как зовут твою основную группу — первую в списке groups? Сдай её: ans ГРУППА",
                hints=("Группы печатает команда с тем же именем.",
                       "В выводе groups основная — первая слева.",
                       "groups, потом ans и первое слово"),
                solution="groups",
                solution_script="groups | awk '{{print $1}}'",
                wrong=("whoami",),
                alternatives=("id -gn — то же: -g — group, -n — name",),
                explain=("На Mac основная группа — обычно staff, «сотрудники»: в неё входят "
                         "все обычные пользователи. admin — те, кому можно sudo.")),
        Variant("У каждого пользователя есть номер — uid, user id. Найди свой в выводе id и "
                "сдай: ans ЧИСЛО",
                hints=("id печатает строку вида uid=…(имя) gid=…(группа) groups=….",
                       "Нужно число сразу после uid=, а не после gid=.",
                       "id, потом ans и число после uid="),
                solution="id",
                solution_script="id -u",
                wrong=("id -g",),
                alternatives=("id -u — сразу только номер: -u — user",),
                explain=("Система помнит тебя по номеру, имя — для людей. У root номер 0: "
                         "отсюда и сила — проверки прав для нуля не действуют.")),
    )
    par = 30
    hints = ("Имя в системе спрашивают командой «кто я».",
             "who am i — пишется слитно: whoami.",
             "whoami, потом ans ИМЯ")
    solution = "whoami"
    explain = ("Права есть у каждого файла: владелец, группа и остальные. Кто ты в этих кругах "
               "— скажут whoami, groups и id.")
    spell = "whoami — кто я; groups — мои группы; id — всё с номерами; sudo — от имени root"
    trap_messages = {
        "group": "Это группа, а нужно имя пользователя — его печатает whoami.",
        "user": "Это твоё имя, а нужна группа — первое слово в выводе groups.",
        "gid": "Это номер группы — gid. Нужен номер пользователя: число после uid=.",
    }

    def answer_kind(self, state):
        return "number" if state.get("_variant") == 2 else "text"

    def setup_variant(self, box, rng, variant):
        name, group, uid, gid = _me()
        kit.write(Path(box) / "readme.txt", "Тут ничего прятать не нужно: ответ — у тебя.\n")
        if variant == 2:
            return {"answer": str(uid), "traps": [["gid", str(gid)]] if gid != uid else []}
        if variant == 1:
            return {"answer": group, "traps": [["user", name]] if name != group else []}
        return {"answer": name, "traps": [["group", group]] if group != name else []}


# имена файлов и папок perm_rwx
RWX_FILES = ("note.txt", "pass.txt", "plan.txt", "memo.txt")
RWX_DIRS = ("vault", "stash", "locker", "inbox")


class PermRwx(AnswerTask):
    id = "perm_rwx"
    track = "env"
    title = "Что значат r, w, x"
    scroll = ("У файла: r — читать, w — менять, x — запускать.\n"
              "У папки иначе: r — смотреть список (ls), w — создавать и удалять внутри, x — "
              "заходить (cd) и открывать файлы внутри. Без x на папке файл в ней не "
              "открыть, даже свой.\n"
              "Нет права — Permission denied, «доступ запрещён»: ищи, какой буквы не хватает. "
              "chmod +r, chmod +w, chmod +x — дать право, как chmod +x у скрипта.")
    variants = (
        Variant("cat {file} отвечает Permission denied: читать файл нельзя даже тебе. Дай "
                "себе право читать и сдай слово из файла: ans СЛОВО",
                hints=("Читать — буква r.",
                       "Право дают так же, как запуск скрипту: chmod +буква.",
                       "chmod +r {file}; cat {file}, потом ans СЛОВО"),
                solution="chmod +r {file}; cat {file}",
                wrong=("cat {file}",),
                alternatives=("chmod u+r {file} — только себе: u — user, владелец",)),
        Variant("Файл {dir}/{file} есть, но cat {dir}/{file} отвечает Permission denied, и cd "
                "{dir} тоже. Почини папку и сдай слово из файла: ans СЛОВО",
                hints=("Не пускает папка, а не файл. Заходить в папку — какая буква?",
                       "У папки x — заходить и открывать файлы внутри.",
                       "chmod +x {dir}; cat {dir}/{file}, потом ans СЛОВО"),
                solution="chmod +x {dir}; cat {dir}/{file}",
                wrong=("chmod +r {dir}/{file}; cat {dir}/{file}",),
                alternatives=("chmod u+x {dir} — только себе",),
                explain=("У папки x — пропуск внутрь: без него не открыть ни один файл в ней, "
                         "даже с правом r у самого файла.")),
        Variant("ls {dir} отвечает Permission denied: список папки скрыт. Верни право "
                "смотреть список и сдай, сколько в папке файлов: ans ЧИСЛО",
                hints=("Смотреть список папки — буква r.",
                       "chmod +r {dir}, потом ls {dir}.",
                       "chmod +r {dir}; ls {dir}, сосчитай имена: ans ЧИСЛО"),
                solution="chmod +r {dir}; ls {dir}",
                solution_script="chmod +r {dir}; ls {dir} | wc -l",
                wrong=("ls {dir} | wc -l",),
                alternatives=("chmod u+r {dir}; ls -1 {dir} | wc -l — сразу числом",),
                explain=("У папки r — только список имён. Файл по точному имени без r "
                         "открывается, если есть x: потому и прячут так — «знаешь имя — "
                         "входи».")),
    )
    par = 40
    hints = ("Читать — буква r.",
             "Право дают так же, как запуск скрипту: chmod +буква.",
             "chmod +r ИМЯ; cat ИМЯ, потом ans СЛОВО")
    solution = "chmod +r {file}; cat {file}"
    explain = ("Permission denied — не поломка, а замок: глянь, какой буквы не хватает, и "
               "дай её chmod.")
    spell = "файл: r читать, w менять, x запускать; папка: r список, w внутри, x заходить"

    def answer_kind(self, state):
        return "number" if state.get("_variant") == 2 else "text"

    def setup_variant(self, box, rng, variant):
        box = Path(box)
        w = kit.word(rng)
        file = rng.choice(RWX_FILES)
        folder = rng.choice(RWX_DIRS)
        if (box / folder).is_dir():         # повторная сборка: замок с папки снимаем сами
            os.chmod(box / folder, 0o700)
        if variant == 2:
            names = rng.sample(RWX_FILES, rng.randint(2, 4))
            for name in names:
                kit.write(box / folder / name, "Обычный текст.\n")
            os.chmod(box / folder, 0o300)
            return {"dir": folder, "answer": str(len(names))}
        if variant == 1:
            kit.write(box / folder / file, f"{w}\n")
            os.chmod(box / folder, 0o200)
            return {"dir": folder, "file": file, "answer": w}
        os.chmod(kit.write(box / file, f"{w}\n"), 0o200)
        return {"file": file, "answer": w}


# --- FB9b: длинный список ls -l ---------------------------------------------------------------
# FB9: урок разбора строки ls -l; владелец (FB5 п. 26): «это не основы», а описание — «крайне
# непонятное». Переехал из «Основ» сюда, после perm_basics и perm_rwx (кто ты, что значат
# r, w, x): урок — две фразы, колонки показывает схема строки (diagrams, id read_long_list).
EXEC_NAMES = ("sync", "deploy", "cleanup", "backup", "update", "build")
SCRIPT_DECOYS = ("start.sh", "setup.sh", "install.sh", "run.sh")
PLAIN_FILES = ("plan.txt", "contacts.txt", "prices.txt", "keys.txt", "log.txt", "map.txt",
               "list.txt", "notes.txt")
# права файлов варианта B: ответ — «менять может только владелец, читать — все»
MODE_ANSWER = 0o644
MODE_TRAPS = {0o666: "all_write", 0o664: "group_write", 0o444: "read_only",
              0o600: "owner_only"}


def _owner_group(path: Path):
    """Имена владельца и группы файла — те, что напечатает ls -l."""
    import grp
    import pwd
    st = path.stat()
    try:
        owner = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        owner = str(st.st_uid)
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = str(st.st_gid)
    return owner, group


class ReadLongList(AnswerTask):
    id = "read_long_list"
    track = "env"
    title = "Длинный список"
    scroll = ("ls -l (l — long) — длинный список: строка на файл, что в какой колонке — на "
              "схеме. Прочерк вместо буквы права — права нет.\n"
              "ls -lh — то же, но с K и M вместо байтов (h — human-readable).")
    variants = (
        Variant("Один файл в этой папке можно запускать. Найди его по правам в ls -l и сдай "
                "имя: ans ИМЯ",
                wrong=("ls -l | grep '^d' | awk '{{print $NF}}'",),
                alternatives=("ls -lh — то же, размеры в K и M: -h — human-readable, "
                              "«для людей»",)),
        Variant("Один файл здесь менять может только владелец, а читать — все остальные. "
                "Найди его по правам и сдай имя: ans ИМЯ",
                hints=("Права — девять букв после первого знака: три тройки — владелец, "
                       "группа, остальные.",
                       "Нужно w только в первой тройке, а r — во всех трёх: rw-r--r--.",
                       "ls -l, найди строку -rw-r--r-- и сдай имя из её конца: ans ИМЯ"),
                solution="ls -l",
                solution_script="ls -l | grep '^-rw-r--r--' | awk '{{print $NF}}'",
                wrong=("ls -l | grep '^-rw-------' | awk '{{print $NF}}'",
                       "ls -l | grep '^-rw-rw-r--' | awk '{{print $NF}}'"),
                alternatives=("ls -l *.txt — то же, только файлы с хвостом .txt",)),
        Variant("Кто владелец файла {file}? Сдай имя владельца: ans ИМЯ",
                hints=("Владелец стоит в строке ls -l сразу после прав и числа ссылок.",
                       "Колонки: права, число ссылок, владелец, группа, размер, дата, имя.",
                       "ls -l {file} — третья колонка и есть владелец: ans ИМЯ"),
                solution="ls -l {file}",
                solution_script="ls -l {file} | awk '{{print $3}}'",
                wrong=("ls -l {file} | awk '{{print $4}}'",),
                alternatives=("ls -l — то же сразу для всех файлов папки",),
                explain=("Владелец — ты сам: файл принадлежит тому, кто его создал, а игра "
                         "создаёт файлы от твоего имени. Группа — колонка правее.")),
    )
    par = 30
    hints = ("Право на запуск — буква x в правах, это девять букв после первого знака.",
             "Строка папки начинается с d, файла — с прочерка. Нужен файл с x.",
             "ls -l, найди строку вроде -rwxr-xr-x и сдай имя из её конца: ans ИМЯ")
    solution = "ls -l"
    solution_script = "ls -l | grep '^-..x' | awk '{{print $NF}}'"
    explain = ("Строка ls -l читается слева направо: тип, права трёх троек, ссылки, владелец, "
               "группа, размер, дата и имя.")
    spell = "ls -l — тип, права rwx (владелец, группа, остальные), владелец, размер, дата"
    trap_messages = {
        "dir": "Это папка — её строка начинается с d. У папки x значит «можно зайти», а "
               "нужен файл: его строка начинается с прочерка.",
        "noexec": "Хвост .sh обещает запускаемый файл, но глянь на права: буквы x нет ни в одной тройке. "
                  "Запускать его нельзя — имя не решает.",
        "all_write": "У этого файла w во всех трёх тройках: менять его может кто угодно.",
        "group_write": "Тут w и во второй тройке: менять может ещё и группа, не только "
                       "владелец.",
        "read_only": "У этого файла w нет нигде: менять его не может никто, даже владелец.",
        "owner_only": "Менять может только владелец — верно, но читать остальным тоже "
                      "нельзя: во второй и третьей тройке одни прочерки.",
        "group": "Это группа — колонка правее владельца. Владелец стоит сразу после числа "
                 "ссылок.",
    }

    def answer_kind(self, state):
        return "text" if state.get("_variant") == 2 else "path"

    accepts_name = True        # имя файла засчитывается и без ./

    def setup_variant(self, box, rng, variant):
        if variant == 0:
            names = rng.sample(PLAIN_FILES, 3)
            for name in names:
                os.chmod(kit.write(box / name, "Обычный текст.\n"), 0o644)
            decoy = rng.choice(SCRIPT_DECOYS)
            os.chmod(kit.write(box / decoy, "#!/bin/sh\necho пусто\n"), 0o644)
            answer = rng.choice(EXEC_NAMES)
            os.chmod(kit.write(box / answer, "#!/bin/sh\necho готово\n"), 0o755)
            folder = box / "tools"
            folder.mkdir(exist_ok=True)
            os.chmod(folder, 0o755)
            return {"answer": answer, "traps": [["dir", "tools"], ["noexec", decoy]]}
        if variant == 1:
            names = rng.sample(PLAIN_FILES, 1 + len(MODE_TRAPS))
            answer, rest = names[0], names[1:]
            os.chmod(kit.write(box / answer, "Обычный текст.\n"), MODE_ANSWER)
            traps = []
            for name, (mode, key) in zip(rest, MODE_TRAPS.items()):
                os.chmod(kit.write(box / name, "Обычный текст.\n"), mode)
                traps.append([key, name])
            return {"answer": answer, "traps": traps}
        names = rng.sample(PLAIN_FILES, 4)
        for name in names:
            kit.write(box / name, "Обычный текст.\n")
        file = rng.choice(names)
        owner, group = _owner_group(box / file)
        traps = [["group", group]] if group != owner else []
        return {"file": file, "answer": owner, "traps": traps}


# --- FB9b: права цифрами --------------------------------------------------------------------
# Владелец (FB5 п. 23): «ничего не понятно… это точно не основы» — урок переехал из «Основ»
# сюда, перед dotenv (там chmod 600 .env). По одному понятию за раз: тройка, три тройки,
# 755 и 600, почему не 777; буквы (u/g/o/a, +/-) — вторым шагом, в варианте про share.
# Проверка — по итоговым правам файла, а не по команде.
PERM_FILES = ("report.txt", "keys.txt", "plan.txt", "notes.txt", "prices.txt", "contacts.txt")
PERM_SCRIPTS = ("deploy.sh", "backup.sh", "sync.sh", "cleanup.sh")


def _mode_of(box: Path, rel: str):
    """Права файла в песочнице (без перехода по симлинку); None — файла нет или не файл."""
    try:
        st = os.lstat(Path(box) / rel)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    return stat.S_IMODE(st.st_mode)


def _rwx(mode: int) -> str:
    return stat.filemode(stat.S_IFREG | mode)[1:]


class PermDigits(Task):
    id = "perm_digits"
    track = "env"
    title = "Права цифрами"
    scroll = ("Права цифрами. В одной тройке r — 4, w — 2, x — 1, их складывают: 4 + 2 = 6, "
              "значит rw-.\n"
              "Три цифры — три тройки: владелец, группа, остальные. chmod 644 файл даст "
              "rw-r--r--: тебе 6, прочим по 4.\n"
              "Скрипту — 755, значит rwxr-xr-x; ключам — 600, значит rw-------, только тебе. "
              "777 не ставят: переписать файл сможет любой.")
    variants = (
        Variant("Файл {file} сейчас читают все. Сделай так, чтобы читать и менять его мог "
                "только ты, а группе и остальным — ничего.",
                hints=("Тебе нужны r и w: 4 + 2. Группе и остальным — ноль.",
                       "Три цифры — владелец, группа, остальные: 6, 0, 0.",
                       "chmod 600 {file}"),
                solution="chmod 600 {file}",
                wrong=("chmod 640 {file}", "chmod 700 {file}"),
                alternatives=("chmod go-r {file} — то же буквами: g — группа, o — остальные, "
                              "минус r — убрать чтение",),
                explain=("600 значит rw-------: так держат ключи и пароли. Цифры прав — "
                         "восьмеричная запись: в каждой цифре от 0 до 7 ровно три "
                         "переключателя — r, w и x. Так права записывали ещё в первом Unix, "
                         "в 1970-х.")),
        Variant("Скрипту {file} нужны обычные права скрипта: тебе — всё, группе и остальным — "
                "читать и запускать, но не менять.",
                hints=("Тебе — rwx: 4 + 2 + 1. Остальным — r и x: 4 + 1.",
                       "Три цифры: 7 владельцу, 5 группе, 5 остальным.",
                       "chmod 755 {file}"),
                solution="chmod 755 {file}",
                wrong=("chmod 777 {file}", "chmod u+x {file}"),
                alternatives=("chmod a+x {file} — то же буквами: a — все, плюс x — дать "
                              "запуск; из rw-r--r-- выйдет rwxr-xr-x",),
                explain=("755 значит rwxr-xr-x, обычные права скрипта. 777 тоже запустится, "
                         "но даёт всем ещё и запись: любой подменит скрипт, а запустишь его "
                         "ты. Владельца файла меняет chown — change owner, «сменить "
                         "владельца»; чужой файл так не заберёшь, нужен sudo — запуск от "
                         "имени администратора. В игре он не нужен.")),
        Variant("В папке share один файл открыт всем на всё — 777, в ls -l это rwxrwxrwx. "
                "Убери у него запись для группы и остальных, другие файлы не трогай. Права "
                "можно писать и буквами: u — владелец, g — группа, o — остальные, a — все; "
                "плюс — дать, минус — убрать.",
                hints=("ls -l share: нужный файл — тот, где rwxrwxrwx.",
                       "Цифрами нужно 755. Буквами: go-w — группе и остальным убрать w.",
                       "chmod go-w share/{file}"),
                solution="chmod go-w share/{file}",
                wrong=("chmod 644 share/{file}", "chmod 755 share/*"),
                alternatives=("chmod 755 share/{file} — то же цифрами",),
                explain=("go-w убирает только w у группы и остальных, прочее не трогает: из "
                         "rwxrwxrwx выйдет rwxr-xr-x, как 755. Цифры задают права целиком, "
                         "буквы — правят. 777 — плохая привычка: кто угодно перепишет файл.")),
    )
    par = 30
    hints = ("В тройке r — 4, w — 2, x — 1, их складывают.",
             "Тебе — 4 + 2, группе и остальным — ноль: 600.",
             "chmod 600 ИМЯ")
    solution = "chmod 600 {file}"
    explain = "Права цифрами: r — 4, w — 2, x — 1, сумма на каждую тройку."
    spell = "chmod 755 — rwxr-xr-x, 644 — rw-r--r--, 600 — только себе; go-w — убрать запись"

    def setup_variant(self, box, rng, variant):
        box = Path(box)
        if variant == 2:
            names = rng.sample(PERM_FILES, 4)
            target, rest = names[0], names[1:]
            keep = {}
            os.chmod(kit.write(box / "share" / target, "Общий файл.\n"), 0o777)
            for name, mode in zip(rest, (0o644, 0o664, 0o600)):
                os.chmod(kit.write(box / "share" / name, "Обычный текст.\n"), mode)
                keep[f"share/{name}"] = mode
            return {"file": target, "target": f"share/{target}", "want": 0o755, "start": 0o777,
                    "keep": keep}
        if variant == 1:
            name = rng.choice(PERM_SCRIPTS)
            os.chmod(kit.write(box / name, "#!/bin/sh\necho готово\n"), 0o644)
            return {"file": name, "target": name, "want": 0o755, "start": 0o644, "keep": {}}
        name = rng.choice(PERM_FILES)
        os.chmod(kit.write(box / name, "Обычный текст.\n"), 0o644)
        return {"file": name, "target": name, "want": 0o600, "start": 0o644, "keep": {}}

    def check(self, ctx):
        st = ctx.state
        mode = _mode_of(ctx.box, st["target"])
        if mode is None:
            return Verdict(False, f"Файла {st['target']} нет на месте. " + kit.RESET_TAIL)
        changed = [rel for rel, m in st["keep"].items() if _mode_of(ctx.box, rel) != m]
        if changed:
            return Verdict(False, "Задеты права и у других файлов: " + kit.names_line(changed)
                           + ". Верни им прежние или набери reset.")
        if mode == st["want"]:
            return Verdict(True)
        if mode == st["start"]:
            return Verdict(False)       # ещё не трогали
        if mode & 0o022:
            return Verdict(False, f"Сейчас {_rwx(mode)}: менять файл может не только "
                                  f"владелец. Нужно {_rwx(st['want'])}.")
        return Verdict(False, f"Сейчас права {_rwx(mode)}, а нужно {_rwx(st['want'])}.")


# --- E7 -------------------------------------------------------------------------------------

APP_SH = """#!/bin/sh
# Подключение к учебной базе: ждёт DB_HOST, DB_USER и DB_PASS в окружении.
cd "$(dirname "$0")" || exit 1
for v in DB_HOST DB_USER DB_PASS; do
  eval "val=\\${$v}"
  if [ -z "$val" ]; then
    echo "app.sh: в окружении нет $v" >&2
    exit 1
  fi
done
if [ "$DB_PASS" != '{pw}' ]; then
  echo "app.sh: пароль не подошёл" >&2
  exit 1
fi
echo "connected $DB_USER@$DB_HOST" > app.log
echo "app.sh: подключено"
"""
NOTE = """Доступ к учебной базе для app.sh (значения ненастоящие):
адрес:  {host}
логин:  {user}
пароль: {pw}
"""
GITIGNORE_LINES = ("*.log", "__pycache__/", ".DS_Store", "build/", "dist/", "*.tmp",
                   "node_modules/")
_PW_CHARS = "abcdefghjkmnpqrstuvwxyz23456789"
_SET_A = re.compile(r"(?<![\w-])(?:set\s+-a|set\s+-o\s+allexport|setopt\s+all_?export)\b")


def lost_lines(text: Optional[str], own) -> list:
    """Прежние строки файла (own), которых в нём больше нет: > вместо >> (E24a, I3). Файла
    нет — тоже пропали."""
    have = {x.strip() for x in (text or "").splitlines()}
    return [x for x in own if x.strip() and x.strip() not in have]


class Dotenv(Task):
    """.env, set -a; source .env; set +a, chmod 600, .gitignore: секреты не в открытом тексте."""
    id = "dotenv"
    track = "env"
    title = "Ключи в .env"
    par = 90
    scroll = (".env — настройки и секреты ИМЯ=значение, без пробелов у =. В оболочку: set -a; "
              "source .env; set +a (set -a — all export: экспортировать прочитанное).\n"
              "chmod 600 .env — читать только тебе. .gitignore — что git (система версий кода) "
              "не берёт: строка .env там обязательна.\n"
              "print -r -- 'строка' >> файл — дописать как есть (r — raw; > — переписать файл).")
    _H3 = ("print -r -- 'DB_HOST={host}' > .env; print -r -- 'DB_USER={user}' >> .env; "
           "print -r -- 'DB_PASS={pw}' >> .env; chmod 600 .env; print -r -- .env >> .gitignore; "
           "set -a; source .env; set +a; ./app.sh")
    variants = (
        Variant("Собери .env для app.sh из значений в note.txt, закрой его правами 600, внеси в "
                ".gitignore и запусти ./app.sh с этими переменными — в app.log должна быть "
                "строка подключения.",
                wrong=("print -r -- 'DB_HOST={host}' > .env; print -r -- 'DB_USER={user}' >> "
                       ".env; print -r -- 'DB_PASS={pw}' >> .env; chmod 600 .env; print -r -- "
                       ".env >> .gitignore; source .env; ./app.sh",),
                alternatives=("nano .env — три строки руками, Ctrl+O, Ctrl+X",
                              "env $(cat .env) ./app.sh — разово, без загрузки в оболочку")),
        Variant("app.sh ждёт DB_HOST, DB_USER и DB_PASS. Положи их в .env (значения — в "
                "note.txt), сделай .env невидимым для git и чужих глаз и запусти скрипт.",
                wrong=("print -r -- 'DB_HOST={host}' > .env; print -r -- 'DB_USER={user}' >> "
                       ".env; print -r -- 'DB_PASS={pw}' >> .env; print -r -- .env >> "
                       ".gitignore; set -a; source .env; set +a; ./app.sh",),
                alternatives=("chmod 400 .env — тоже никому, кроме тебя, только читать",)),
        Variant("Секреты для ./app.sh лежат открытым текстом в note.txt. Перенеси их в .env с "
                "правами 600, добавь .env в .gitignore, загрузи и запусти ./app.sh.",
                wrong=("print -r -- 'DB_HOST={host}' > .env; print -r -- 'DB_USER={user}' >> "
                       ".env; print -r -- 'DB_PASS={pw}' >> .env; chmod 600 .env; set -a; "
                       "source .env; set +a; ./app.sh",),
                alternatives=("export $(cat .env) — тоже загрузит, пока в значениях нет "
                              "пробелов",)),
    )
    hints = ("Три строки ИМЯ=значение в .env; права — chmod; .gitignore — обычный текстовый "
             "файл.",
             "Загрузка с экспортом: set -a; source .env; set +a. Потом ./app.sh.",
             _H3)
    solution = _H3
    explain = ("Секреты живут в .env, отдельно от кода: права 600 прячут его от чужих глаз, "
               ".gitignore — от истории git, а set -a раздаёт значения запущенным программам.")
    spell = "set -a; source .env; set +a — загрузить .env; chmod 600 .env; .env — в .gitignore"
    NAMES = ("DB_HOST", "DB_USER", "DB_PASS")
    MSG_SPACE = "Пробел вокруг = — source споткнётся: пиши ИМЯ=значение слитно."
    MSG_JUNK = "В .env лишняя строка — нужны только строки вида ИМЯ=значение."
    MSG_VALUE = "В .env {name} не совпадает с note.txt — сверь значение."
    MSG_LOG = "В app.log не та строка подключения — проверь значения в .env и загрузи его заново."
    MSG_SET_A = ("source без set -a: переменные есть в оболочке, но app.sh их не видит. "
                 "set -a; source .env; set +a — и снова ./app.sh.")
    MSG_NO_ENV = "app.sh ждёт переменные из .env, а .env ещё нет: собери его из note.txt."
    MSG_PARTIAL = "Сделано {n} из 4: app.log верен, осталось — {rest}."
    PARTS = ("три строки в .env", "права 600 (chmod 600 .env)", "строка .env в .gitignore",
             "запуск ./app.sh")
    # E24a, I3: > вместо >> стёр прежние строки .gitignore
    MSG_IGN_CLOBBER = ("> переписал .gitignore целиком — прежние строки ({line} и другие) "
                       "пропали. Дописывают >>. reset вернёт файл.")

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        host = f"db-{kit.latin(rng)}.lan"
        user = kit.latin(rng)
        pw = "demo-" + "".join(rng.choice(_PW_CHARS) for _ in range(8))
        os.chmod(kit.write(Path(box) / "app.sh", APP_SH.replace("{pw}", pw)), 0o755)
        kit.write(Path(box) / "note.txt", NOTE.format(host=host, user=user, pw=pw))
        lines = rng.sample(GITIGNORE_LINES, rng.randint(3, 5))
        kit.write(Path(box) / ".gitignore", "\n".join(lines) + "\n")
        return {"host": host, "user": user, "pw": pw, "ign": lines}

    def check(self, ctx) -> Verdict:
        st, box = ctx.state, ctx.box
        texts = {}
        for rel in (".env", ".gitignore", "app.log"):
            kind, text = envkit.box_text(box, rel, envkit.TEXT_CAP)
            bad = envkit.file_problem(kind, rel)
            if bad:
                return Verdict(False, bad)
            texts[rel] = text
        want = {"DB_HOST": st["host"], "DB_USER": st["user"], "DB_PASS": st["pw"]}
        env_ok = False
        if texts[".env"] is not None:
            pairs, problems = envkit.parse_dotenv(texts[".env"])
            if "space" in problems:
                return Verdict(False, self.MSG_SPACE)
            for name in self.NAMES:
                if name in pairs and pairs[name] != want[name]:
                    return Verdict(False, self.MSG_VALUE.format(name=name))
            if "junk" in problems:
                return Verdict(False, self.MSG_JUNK)
            env_ok = all(pairs.get(n) == want[n] for n in self.NAMES)
        mode = envkit.mode_of(box, ".env")
        mode_ok = mode is not None and not mode & 0o077 and bool(mode & 0o400)
        ign_ok = envkit.ignores_env(texts[".gitignore"])
        lost = lost_lines(texts[".gitignore"], st.get("ign", ()))
        if lost:
            return Verdict(False, self.MSG_IGN_CLOBBER.format(line=lost[0]))
        log = texts["app.log"]
        if log is not None and envkit.first_line(log) != f"connected {st['user']}@{st['host']}":
            return Verdict(False, self.MSG_LOG)
        app_ok = any(ok is not False and any(envkit.runs(seg, "app.sh", by_name=False)
                                            for seg in envkit.segments(line))
                     for line, ok in envkit.journal(box) if "app.sh" in line)
        done = [env_ok, mode_ok, ign_ok, log is not None and app_ok]
        if all(done):
            return Verdict(True)
        if log is not None:
            rest = ", ".join(p for p, ok in zip(self.PARTS, done) if not ok)
            return Verdict(False, self.MSG_PARTIAL.format(n=sum(done), rest=rest))
        lines = [c.line for c in ctx.cmds]
        if envkit.ran(lines[-1:], "app.sh", by_name=False):
            if texts[".env"] is None:
                return Verdict(False, self.MSG_NO_ENV)
            if env_ok and not any(_SET_A.search(x) for x in lines):
                return Verdict(False, self.MSG_SET_A)
        return Verdict(False)


# --- E8 -------------------------------------------------------------------------------------

STAMP = """#!/bin/sh
# Ставит отметку: пишет в stamp.txt свою версию.
echo "stamp {ver}" > {out}
echo "stamp {ver}: отметка поставлена"
"""
# ~/.zshrc песочницы (box/.termit/home), не настоящий: пара безобидных строк для урока
HOME_RC_TEXT = "# мои настройки\nalias ll='ls -la'\n"
_EXPORT_PATH = 'export PATH="$HOME/tools/bin:$PATH"'


class PathWhich(Task):
    """PATH, which -a, export PATH="папка:$PATH", строка в ~/.zshrc и source ~/.zshrc."""
    id = "path_which"
    track = "env"
    title = "Где живут команды"
    par = 75
    scroll = ("PATH — список папок через двоеточие, где оболочка ищет команды: echo $PATH | tr "
              ": '\\n' — по строке. which ИМЯ — какой файл запустится; which -a — all, все "
              "одноимённые, первый побеждает.\n"
              "export PATH=\"$HOME/tools/bin:$PATH\" — папку вперёд, до закрытия окна.\n"
              "Забыл $PATH — пропадут ls и cat; вернёт export PATH=/usr/bin:/bin:$PATH.")
    variants = (
        Variant("Команда stamp лежит в ~/tools/bin, но оболочка её не находит. Сделай, чтобы "
                "stamp запускалась по имени, и запусти её.",
                hints=("Оболочка ищет команды по папкам из PATH: echo $PATH | tr : '\\n'",
                       "Добавь ~/tools/bin в PATH впереди: export PATH=… — и набери просто "
                       "stamp.",
                       _EXPORT_PATH + "; which stamp; stamp"),
                # M6 ревью P5: which — в показанном эталоне варианта 0 (страж зовёт which -a)
                solution=_EXPORT_PATH + "; which stamp; stamp",
                wrong=("~/tools/bin/stamp",),
                alternatives=("path=(~/tools/bin $path) — то же через массив path в zsh",)),
        Variant("Подключи ~/tools/bin к PATH насовсем — строкой в ~/.zshrc (этот файл "
                "оболочка выполняет при каждом старте), перечитай его в этом окне — source "
                "~/.zshrc — и запусти stamp.",
                hints=("Настройки оболочки живут в ~/.zshrc: всё, что там, выполняется при "
                       "старте.",
                       "Допиши в ~/.zshrc строку export PATH=… через >>, потом source ~/.zshrc "
                       "и stamp.",
                       "print -r -- '" + _EXPORT_PATH + "' >> ~/.zshrc; source ~/.zshrc; stamp"),
                solution="print -r -- '" + _EXPORT_PATH + "' >> ~/.zshrc; source ~/.zshrc; stamp",
                wrong=(_EXPORT_PATH + "; stamp",),
                alternatives=("nano ~/.zshrc — дописать строку руками, потом source ~/.zshrc",)),
        Variant("stamp запускается, но старая — из ~/old/bin. Сделай, чтобы побеждала новая из "
                "~/tools/bin, и запусти её.",
                hints=("which -a stamp покажет все одноимённые — побеждает первая.",
                       "Поставь ~/tools/bin впереди всех: export PATH=…, проверь which -a stamp.",
                       _EXPORT_PATH + "; stamp"),
                solution=_EXPORT_PATH + "; stamp",
                wrong=('export PATH="$PATH:$HOME/tools/bin"; stamp',),
                alternatives=("rm ~/old/bin/stamp — убрать старую совсем; ~/tools/bin в PATH "
                              "всё равно нужна",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Оболочка ищет команду по папкам PATH слева направо и берёт первую найденную. "
               "Своя папка впереди — и команда твоя; навсегда — только строкой в ~/.zshrc.")
    spell = 'which -a ИМЯ — откуда команда; export PATH="папка:$PATH" — папку вперёд'
    OUT = "stamp.txt"
    RC = ".termit/home/.zshrc"
    MSG_OLD = "v1 — первой нашлась старая: новая папка должна стоять в PATH впереди."
    MSG_OTHER = "В stamp.txt не то: его пишет сама stamp — запусти её."
    MSG_FULL = ("stamp не запускалась по имени: по полному пути работает и без PATH — а нужно "
                "по имени, просто stamp.")
    MSG_NOT_FOUND = ("stamp по имени не запустилась — оболочка её не нашла: папку нужно "
                     "поставить в PATH.")
    MSG_RC = ("Сработает до закрытия окна. Насовсем — пропиши строку с ~/tools/bin в ~/.zshrc "
              "и перечитай: source ~/.zshrc.")
    MSG_SOURCE = "Строка в ~/.zshrc есть, но оболочка её ещё не перечитала: source ~/.zshrc"
    # E24a (аудит новичка): I1 — PATH без $PATH, I3 — > вместо >> и $PATH, раскрытый при
    # записи, I4 — ~ в кавычках и файл вместо папки
    MSG_LOST = ("PATH без $PATH: старые папки пропали, ls и cat больше не найдутся. Верни их: "
                "export PATH=/usr/bin:/bin:$PATH (reset переменные не чинит). Свою папку "
                'ставят так: export PATH="$HOME/tools/bin:$PATH"')
    MSG_RC_LOST = ("Строка в ~/.zshrc без $PATH: в каждом новом окне ls и cat пропадут. Нужна "
                   'export PATH="$HOME/tools/bin:$PATH" — с $PATH в конце.')
    MSG_RC_EXPANDED = ("В ~/.zshrc вместо $PATH застыл сегодняшний длинный список: двойные "
                       "кавычки раскрыли его ещё при записи. Строку пиши в одинарных кавычках: "
                       "print -r -- '…' >> ~/.zshrc")
    MSG_RC_CLOBBER = ("> переписал ~/.zshrc целиком — твоя строка {line} пропала. Дописывают "
                      ">>. reset вернёт файл.")
    MSG_TILDE = ("~ в кавычках не раскрывается: в PATH попала папка с именем «~». Пиши $HOME: "
                 'export PATH="$HOME/tools/bin:$PATH"')
    MSG_FILE = "В PATH кладут папку, а не файл: …/tools/bin, без /stamp на конце."
    _TILDE = re.compile(r"""PATH=(?:"[^"]*~|'[^']*~)""")

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        home = kit.home(box)
        out = shlex.quote(str(Path(box) / self.OUT))
        for sub, ver in (("tools/bin", "v2"), ("old/bin", "v1")):
            os.chmod(kit.write(home / sub / "stamp", STAMP.format(ver=ver, out=out)), 0o755)
        kit.write(Path(box) / self.RC, HOME_RC_TEXT)
        return {}

    def env_for(self, state: dict) -> Dict[str, str]:
        if variant_index(state.get("_variant", 0), 3) == 2:
            return {"PATH": "$HOME/old/bin:$PATH"}
        return {}

    def _path_slip(self, lines) -> Optional[str]:
        """Промах с PATH оболочки (по журналу): потерян $PATH, ~ в кавычках, путь к файлу."""
        if envkit.path_lost(lines):
            return self.MSG_LOST
        sets = envkit.path_sets(lines)
        if not sets:
            return None
        value, typed = sets[-1]
        if self._TILDE.search(typed):
            return self.MSG_TILDE
        if any(p.rstrip("/").endswith("/stamp") for p in value.split(":")):
            return self.MSG_FILE
        return None

    def _rc_slip(self, rc: Optional[str], v: int) -> Optional[str]:
        """~/.zshrc: свои строки игрока целы (> вместо >>); в варианте B — строка PATH с $PATH
        буквально (без него — сломает каждое окно; раскрытый двойными кавычками — застынет)."""
        lines = [x.strip() for x in (rc or "").splitlines()]
        for own in HOME_RC_TEXT.splitlines():
            if own.strip() and own.strip() not in lines:
                return self.MSG_RC_CLOBBER.format(line=own.strip())
        if v != 1:
            return None
        for x in lines:
            if x.startswith("#") or "tools/bin" not in x or "PATH" not in x.upper():
                continue
            if envkit.keeps_path(x):
                continue
            return self.MSG_RC_EXPANDED if "/usr/bin" in x else self.MSG_RC_LOST
        return None

    def check(self, ctx) -> Verdict:
        v = variant_index(ctx.state.get("_variant", 0), 3)
        kind, rc = envkit.box_text(ctx.box, self.RC, envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, "~/.zshrc")
        if bad:
            return Verdict(False, bad)
        jour = envkit.journal(ctx.box)
        lines = [x for x, _ in jour]
        rc_slip = self._rc_slip(rc, v)
        kind, text = envkit.box_text(ctx.box, self.OUT, envkit.TEXT_CAP)
        if kind == "missing":
            return Verdict(False, self._path_slip(lines) or rc_slip)
        bad = envkit.file_problem(kind, self.OUT)
        if bad:
            return Verdict(False, bad)
        line = envkit.first_line(text)
        if line == "stamp v1":
            return Verdict(False, self._path_slip(lines) or rc_slip or self.MSG_OLD)
        if line != "stamp v2":
            return Verdict(False, self.MSG_OTHER)
        # решает последний запуск stamp (как угодно): он — по имени и не провалился. Полный путь
        # после неудачи по имени и подделка stamp.txt не засчитываются (ревью P2, I1)
        last = envkit.last_run(jour, "stamp")
        if last is None or not any(envkit.runs(seg, "stamp", by_name=True)
                                   for seg in envkit.segments(last[0])):
            return Verdict(False, self.MSG_FULL)
        if last[1] is False:
            return Verdict(False, self.MSG_NOT_FOUND)
        if envkit.path_lost(lines):
            return Verdict(False, self.MSG_LOST)
        if rc_slip:
            return Verdict(False, rc_slip)
        if v == 1:
            if not any("tools/bin" in x and "PATH" in x.upper() and not x.lstrip().startswith("#")
                       for x in (rc or "").splitlines()):
                return Verdict(False, self.MSG_RC)
            if not any(cmd in ("source", ".") and args and args[0].endswith(".zshrc")
                       for _, cmd, args in envkit.commands(lines)):
                return Verdict(False, self.MSG_SOURCE)
        return Verdict(True)


# --- E9 -------------------------------------------------------------------------------------

# Скрипты задачи начинаются с def: без shebang оболочка отдаёт файл sh, и он падает на первой
# же строке (syntax error), не исполнив ни одной команды.
COUNT_PY = '''#!/usr/bin/python
def main(argv):
    """Число строк данных в CSV — без строки заголовка."""
    with open(argv[1], encoding="utf-8") as f:
        rows = f.read().splitlines()
    print(len(rows) - 1)


if __name__ == "__main__":
    import sys
    main(sys.argv)
'''
STATS_PY = '''def main(argv):
    """Сводка по ценам: сколько, самая низкая и самая высокая."""
    with open(argv[1], encoding="utf-8") as f:
        prices = [int(x) for x in f.read().split()]
    print("count", len(prices), "min", min(prices), "max", max(prices))


if __name__ == "__main__":
    import sys
    main(sys.argv)
'''
BACKUP_SH = """#!/bin/bash
# Кладёт копию файла в backups/: ./backup.sh ФАЙЛ
if [ -z "$1" ]; then
  echo "usage: ./backup.sh ФАЙЛ" >&2
  exit 2
fi
mkdir -p backups && cp "$1" backups/ && echo "копия: backups/$(basename "$1")"
"""
_SHEBANG_OK = re.compile(r"^#!\s*/usr/bin/env\s+python3(?:\.\d+)?\s*$")


class ShebangRun(Task):
    """chmod +x, ./скрипт, #!/usr/bin/env python3, python3 файл.py, аргумент $1 / sys.argv[1].
    «Решено» не зависит от чтения .py (повторная проверка родителя .py не читает): верный
    вывод, бит x и запуск через ./ в журнале. Первую строку читают только отклики."""
    id = "shebang_run"
    track = "env"
    title = "Запусти меня"
    par = 75
    pinned_python = True
    scroll = ("Чтобы запускать файл как программу: chmod +x файл и ./файл (./ — потому что "
              "текущей папки нет в PATH). Первая строка #! (shebang) говорит, чем исполнять: "
              "#!/usr/bin/env python3 — найдёт python3 по PATH.\n"
              "python3 файл.py — запуск без прав и shebang. ./файл аргумент — внутри это $1 (в "
              "Python — sys.argv[1]). #! в echo — только в '…': в \"…\" zsh скажет event not "
              "found.")
    variants = (
        Variant("./count.py orders.csv должен печатать число заказов, а он ругается. Почини "
                "запуск (сам код не трогай) и сохрани вывод в count.txt.",
                hints=("Ошибка подскажет: permission denied — нет прав, bad interpreter — плохая "
                       "первая строка.",
                       "chmod +x count.py; первая строка — #!/usr/bin/env python3: поправь её в "
                       "nano (или sed -i '' '1s|.*|…|').",
                       "nano count.py: первую строку замени на #!/usr/bin/env python3, Ctrl+O, "
                       "Enter, Ctrl+X; chmod +x count.py; ./count.py orders.csv > count.txt"),
                # FB12 (N25): эталон разбора — тот же путь, что третья подсказка (nano);
                # скрипт для тестов правит строку sed'ом (lint.SHOWN_RULES)
                solution="nano count.py: первую строку замени на #!/usr/bin/env python3, "
                         "Ctrl+O, Enter, Ctrl+X; chmod +x count.py; ./count.py orders.csv > "
                         "count.txt",
                solution_script="sed -i '' '1s|.*|#!/usr/bin/env python3|' count.py; chmod +x "
                                "count.py; ./count.py orders.csv > count.txt",
                wrong=("python3 count.py orders.csv > count.txt",
                       "chmod +x count.py; ./count.py orders.csv > count.txt"),
                alternatives=("sed -i '' '1s|.*|#!/usr/bin/env python3|' count.py — поправить "
                              "первую строку без редактора",
                              "python3 count.py orders.csv > count.txt — тот же вывод, но цель "
                              "задачи — запуск через ./")),
        Variant("Сделай backup.sh запускаемым и сохрани им копию notes.txt: ./backup.sh "
                "notes.txt.",
                hints=("Запусти ./backup.sh notes.txt и прочти ошибку.",
                       "permission denied — у файла нет права на запуск: chmod +x.",
                       "chmod +x backup.sh; ./backup.sh notes.txt"),
                solution="chmod +x backup.sh; ./backup.sh notes.txt",
                wrong=("bash backup.sh notes.txt",),
                alternatives=("bash backup.sh notes.txt — копия будет, но файл так и не станет "
                              "программой",)),
        Variant("stats.py не запускается как ./stats.py. Добавь ему правильную первую строку и "
                "права и запусти: ./stats.py prices.txt > stats.txt.",
                hints=("Без первой строки #! оболочка читает файл как свой скрипт — отсюда "
                       "syntax error.",
                       "Первой строкой — #!/usr/bin/env python3 (nano или через временный файл), "
                       "потом chmod +x.",
                       "nano stats.py: первой строкой допиши #!/usr/bin/env python3, Ctrl+O, "
                       "Enter, Ctrl+X; chmod +x stats.py; ./stats.py prices.txt > stats.txt"),
                solution="nano stats.py: первой строкой допиши #!/usr/bin/env python3, "
                         "Ctrl+O, Enter, Ctrl+X; chmod +x stats.py; ./stats.py prices.txt > "
                         "stats.txt",
                solution_script="print -r -- '#!/usr/bin/env python3' > s.tmp; cat stats.py "
                                ">> s.tmp; mv s.tmp stats.py; chmod +x stats.py; ./stats.py "
                                "prices.txt > stats.txt",
                wrong=("chmod +x stats.py; ./stats.py prices.txt > stats.txt",),
                alternatives=("print -r -- '#!/usr/bin/env python3' > s.tmp; cat stats.py >> "
                              "s.tmp; mv s.tmp stats.py — первая строка через временный файл, "
                              "без редактора",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Чтобы файл стал программой, хватит двух вещей: права x и первой строки #! — "
               "она говорит, кому этот файл исполнять (править её проще всего в nano). А ./ "
               "нужен, потому что текущей папки нет в PATH.")
    spell = "chmod +x f; #!/usr/bin/env python3 — первая строка; ./f арг — внутри $1"
    secret_keys = ("want",)
    MSG_PY3 = "Вывод верен, но через python3 — сделай запуск через ./: права и первая строка."
    MSG_PERM = "permission denied — у {script} нет права на запуск: chmod +x {script}"
    MSG_BAD = ("bad interpreter: {interp} — на Mac такого нет. Первая строка — "
               "#!/usr/bin/env python3")
    # E24a (аудит, мелкие): код затёрт (> вместо правки первой строки); #! не первой строкой
    MSG_CLOBBERED = ("{script} перезаписан: > стёр весь код, осталась одна строка. reset вернёт "
                     "файл; первую строку правят в nano.")
    MSG_SHEBANG_LATE = ("#! стоит не первой строкой — оболочка его не видит. Он нужен ПЕРВОЙ "
                        "строкой: nano {script} (или через временный файл).")
    MSG_NONE = ("Без первой строки #! оболочка читает {script} как свой скрипт — отсюда syntax "
                "error. Добавь первой строкой #!/usr/bin/env python3")
    MSG_WRONG = "В {out} не то, что печатает {script}. Код не трогай: reset вернёт его."
    MSG_COPY = "Копия в backups/ не совпадает с notes.txt — сделай её заново: ./backup.sh notes.txt"
    MSG_B_RUN = ("Копия есть, но сделал её не сам скрипт — запусти его: ./backup.sh notes.txt")
    MSG_B_NOX = ("Копия есть, но backup.sh так и не стал программой: chmod +x backup.sh, потом "
                 "./backup.sh notes.txt")
    FILES = (("count.py", "count.txt"), ("backup.sh", "backups/notes.txt"),
             ("stats.py", "stats.txt"))

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        if variant == 1:
            notes = [f"{kit.latin(rng)} {rng.randint(1, 99)}" for _ in range(rng.randint(3, 8))]
            text = "\n".join(notes) + "\n"
            kit.write(box / "notes.txt", text)
            os.chmod(kit.write(box / "backup.sh", BACKUP_SH), 0o644)
            return {"want": text}
        if variant == 2:
            prices = [rng.randint(50, 9999) for _ in range(rng.randint(8, 30))]
            kit.write(box / "prices.txt", "\n".join(map(str, prices)) + "\n")
            os.chmod(kit.write(box / "stats.py", STATS_PY), 0o644)
            return {"want": f"count {len(prices)} min {min(prices)} max {max(prices)}"}
        n = rng.randint(20, 80)
        rows = ["id,city,amount"] + [f"{1000 + i},{kit.latin(rng)},{rng.randint(100, 9999)}"
                                     for i in range(n)]
        kit.write(box / "orders.csv", "\n".join(rows) + "\n")
        os.chmod(kit.write(box / "count.py", COUNT_PY), 0o644)
        return {"want": str(n)}

    def check(self, ctx) -> Verdict:
        st, box = ctx.state, ctx.box
        v = variant_index(st.get("_variant", 0), 3)
        script, out = self.FILES[v]
        kind, data = envkit.box_file(box, out, envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, out)
        if bad:
            return Verdict(False, bad)
        jour = envkit.journal(box)
        lines = [x for x, _ in jour]
        xok = envkit.executable(box, script)
        if v == 1:
            return self._backup(box, data, jour, xok, st)
        text = data.decode("utf-8", errors="replace") if data is not None else None
        if text is not None and envkit.first_line(text) == st["want"]:
            # вывод должен быть от удачного ./script: последняя строка, где script пишет в out,
            # — запуск по пути, и он не провалился (ревью P2, I2: python3 + chmod без shebang)
            row = next(((x, ok) for x, ok in reversed(jour) if out in x and script in x), None)
            if (row is None or row[1] is False or not xok
                    or not any(envkit.runs(seg, script, by_name=False)
                               for seg in envkit.segments(row[0]))):
                return Verdict(False, self.MSG_PY3)
            return Verdict(True)
        if text is None and not envkit.ran(lines[-1:], script, by_name=False):
            return Verdict(False)
        if not xok:
            return Verdict(False, self.MSG_PERM.format(script=script))
        _, src = envkit.box_text(box, script, envkit.TEXT_CAP)
        first = envkit.first_line(src)
        if src is not None and "def main" not in src:
            return Verdict(False, self.MSG_CLOBBERED.format(script=script))
        if first.startswith("#!") and not _SHEBANG_OK.match(first):
            return Verdict(False, self.MSG_BAD.format(interp=first[2:].strip()[:60]))
        if src is not None and not first.startswith("#!"):
            if any(x.strip().startswith("#!") for x in src.splitlines()[1:]):
                return Verdict(False, self.MSG_SHEBANG_LATE.format(script=script))
            return Verdict(False, self.MSG_NONE.format(script=script))
        if text:
            return Verdict(False, self.MSG_WRONG.format(out=out, script=script))
        return Verdict(False)

    def _backup(self, box, data, jour, xok, st) -> Verdict:
        last = envkit.last_run(jour, "backup.sh")
        via = (last is not None and last[1] is not False
               and any(envkit.runs(seg, "backup.sh", by_name=False)
                       for seg in envkit.segments(last[0])))
        if data is not None:
            if data.decode("utf-8", errors="replace") != st["want"]:
                return Verdict(False, self.MSG_COPY)
            if not xok:
                return Verdict(False, self.MSG_B_NOX)
            return Verdict(True) if via else Verdict(False, self.MSG_B_RUN)
        if envkit.ran([x for x, _ in jour][-1:], "backup.sh", by_name=False) and not xok:
            return Verdict(False, self.MSG_PERM.format(script="backup.sh"))
        return Verdict(False)


# --- E10 ------------------------------------------------------------------------------------

CHECK_SH = """#!/bin/sh
# Проверка конфигов: сводку пишет в поток ошибок, итог — кодом возврата.
echo "check.sh: файлов проверено: {k}, замечаний: {m}" >&2
exit {n}
"""
BUILD_SH = """#!/bin/sh
# Сборка: из src/main.txt — build/app.txt.
cd "$(dirname "$0")" || exit 1
if [ ! -f src/main.txt ]; then
  echo "build.sh: нет файла src/main.txt — собирать нечего" >&2
  exit 3
fi
mkdir -p build && cp src/main.txt build/app.txt && echo "build.sh: собрано"
"""
DEPLOY_SH = """#!/bin/sh
# Выкатка: отдаёт то, что лежит в build/. Сама ничего не проверяет.
cd "$(dirname "$0")" || exit 1
if [ -f build/app.txt ]; then
  echo "deployed $(head -n 1 build/app.txt)" > deploy.log
else
  echo "deployed nothing" > deploy.log
fi
echo "deploy.sh: выкачено"
"""
NOTIFY_SH = """#!/bin/sh
# Уведомление о провале сборки.
cd "$(dirname "$0")" || exit 1
echo "build failed" > notify.log
echo "notify.sh: команда предупреждена"
"""
# цепочки — по командам строки (envkit.sequence, линейно), а не регэкспом по тексту: echo
# с цепочкой в кавычках — не цепочка (ревью P2, I3)
_AND = [("build.sh", "&&"), ("deploy.sh", "")]
_AND_OR = [("build.sh", "&&"), ("deploy.sh", "||"), ("notify.sh", "")]
_SEMI = [("build.sh", ";"), ("deploy.sh", "")]
_AND_SEMI = [("build.sh", "&&"), ("deploy.sh", ";"), ("notify.sh", "")]


def _if_chain(line: str) -> bool:
    """Строка — if ./build.sh; then ./deploy.sh; else ./notify.sh; fi (по командам, не по
    тексту: echo '…' в кавычках не в счёт). Линейно."""
    want = [("if", "build.sh"), ("then", "deploy.sh"), ("else", "notify.sh")]
    k = 0
    for seg in envkit.segments(line):
        if k == len(want):
            break
        ws = envkit.words(seg)
        word, name = want[k]
        if ws and ws[0] == word and envkit.runs(seg, name, by_name=False):
            k += 1
        elif ws and ws[0] in ("if", "then", "else"):
            return False
    return k == len(want)


class ExitCodes(AnswerTask):
    """$?, 0 — успех, &&, ||, ;. Вариант A — «найди и назови» (ans), B и C — «сделай»."""
    id = "exit_codes"
    track = "env"
    title = "Ноль — это успех"
    par = 60
    scroll = ("Каждая команда на выходе отдаёт код: 0 — всё хорошо, не 0 — что-то упало. echo $? "
              "— код последней команды.\n"
              "A && B — B только если A успешна; A || B — B только если A упала; A ; B — B в "
              "любом случае.")
    variants = (
        Variant("С каким кодом завершается ./check.sh? ans ЧИСЛО",
                hints=("Код последней команды лежит в $?.",
                       "Запусти ./check.sh и сразу за ним — echo $?.",
                       "./check.sh; echo $?, затем ans ЧИСЛО"),
                solution="./check.sh; echo $?",
                wrong=("./check.sh; echo hi > /dev/null; echo $?",
                       "./check.sh 2>&1 | cut -d: -f4"),
                alternatives=("./check.sh || echo $? — код печатается, только если он не 0",)),
        Variant("Выкатка: ./deploy.sh можно запускать, только если ./build.sh прошёл. Запусти "
                "их одной строкой так, чтобы при провале сборки деплоя не было, а при провале "
                "сработал ./notify.sh. Сборка сейчас падает.",
                hints=("&& запускает следующую команду только при успехе, || — только при "
                       "провале.",
                       "Цепочка одной строкой: сборка && деплой || уведомление.",
                       "./build.sh && ./deploy.sh || ./notify.sh"),
                solution="./build.sh && ./deploy.sh || ./notify.sh",
                wrong=("./build.sh; ./deploy.sh || ./notify.sh",),
                alternatives=("if ./build.sh; then ./deploy.sh; else ./notify.sh; fi — то же "
                              "длиннее",)),
        Variant("Сборка падает — найди почему (сообщение ./build.sh), исправь и запусти "
                "./build.sh && ./deploy.sh.",
                hints=("Запусти ./build.sh и прочти, на что он жалуется.",
                       "Ему нужен src/main.txt — посмотри ls: файл лежит не там. Перенеси его "
                       "в src/.",
                       "mv main.txt src/; ./build.sh && ./deploy.sh"),
                solution="mv main.txt src/; ./build.sh && ./deploy.sh",
                wrong=("./build.sh; ./deploy.sh",),
                alternatives=("cp main.txt src/ — копия тоже годится",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Код возврата — короткий ответ программы: «вышло» или «не вышло». На нём "
               "держатся && и ||: && пускает дальше только после удачи, || — только после провала.")
    spell = "echo $? — код последней; A && B — если успех; A || B — если провал"
    trap_messages = {
        "printed": "Это число из сообщения скрипта, а нужен код возврата — его печатает echo $? "
                   "сразу после команды.",
        "zero": "0 — код последней команды, но это была не ./check.sh: echo $? нужен сразу "
                "после неё.",
        "notfound": "127 — «команда не найдена»: скрипт из текущей папки запускают как "
                    "./check.sh.",
    }
    fallback = "Не то. Запусти ./check.sh и сразу за ним — echo $?."
    MSG_SEMI = ("deploy.log появился при упавшей сборке — нужен &&, а не ;. Убери его (rm "
                "deploy.log) и запусти снова.")
    MSG_NO_BUILD = ("deploy.sh запущен без сборки: выкатывать можно только после удачной "
                    "./build.sh — через &&. Убери deploy.log (rm deploy.log) и попробуй снова.")
    MSG_WRONG_MAIN = "В сборку ушёл не тот main.txt. Посмотри ls: настоящий где-то рядом."
    MSG_FIXED = ("Сборку тут чинить не надо: смотрим, сработает ли notify при провале. "
                 "Набери reset и прогони цепочку на падающей сборке.")
    MSG_ONE_LINE = ("Сборка упала и notify сработал. Теперь всё одной строкой: ./build.sh && "
                    "./deploy.sh || ./notify.sh")
    MSG_AND = "Выкачено. А теперь одной строкой и через &&: ./build.sh && ./deploy.sh"
    # E24a, I10: строка одна, но перед notify — ; вместо ||
    MSG_SEMI_NOTIFY = ("; запустит notify и при удаче сборки — после деплоя нужен ||: "
                       "./build.sh && ./deploy.sh || ./notify.sh")

    def _v(self, state: dict) -> int:
        return variant_index(state.get("_variant", 0), len(self.variants))

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        if variant == 0:
            n = rng.randint(2, 9)
            k, m = rng.sample(range(10, 99), 2)
            os.chmod(kit.write(box / "check.sh", CHECK_SH.format(k=k, m=m, n=n)), 0o755)
            return {"answer": n,
                    "traps": [["printed", k], ["printed", m], ["zero", 0], ["notfound", 127]]}
        for name, body in (("build.sh", BUILD_SH), ("deploy.sh", DEPLOY_SH),
                           ("notify.sh", NOTIFY_SH)):
            os.chmod(kit.write(box / name, body), 0o755)
        (box / "src").mkdir()
        tag = f"release {kit.latin(rng)}-{rng.randint(10, 99)}"
        if variant == 2:
            kit.write(box / "main.txt", tag + "\n")
        return {"tag": tag, "traps": []}    # traps — секрет: задача скрытая, как вариант A

    def expected(self, state: dict) -> str:
        return str(state.get("answer", ""))

    def answer_kind(self, state: dict) -> str:
        return "number" if self._v(state) == 0 else "text"

    def matches(self, given: str, ctx) -> bool:
        return self._v(ctx.state) == 0 and super().matches(given, ctx)

    def takes_answer(self, state: dict) -> bool:
        return self._v(state) == 0

    def check(self, ctx) -> Verdict:
        v = self._v(ctx.state)
        if v == 0:
            return super().check(ctx)
        verdict = self._do(ctx, v)
        if verdict.solved or ctx.answer is None:
            return verdict
        return Verdict(False, verdict.message or self.stray_answer)

    def _do(self, ctx, v: int) -> Verdict:
        box, st = ctx.box, ctx.state
        texts = {}
        for rel in ("deploy.log", "notify.log"):
            kind, text = envkit.box_text(box, rel, envkit.TEXT_CAP)
            bad = envkit.file_problem(kind, rel)
            if bad:
                return Verdict(False, bad)
            texts[rel] = text
        deploy = texts["deploy.log"]
        lines = [c.line for c in ctx.cmds]
        if deploy is not None:
            line = envkit.first_line(deploy)
            if line == "deployed nothing":
                # «;» — только если она и была между сборкой и выкаткой (ревью P2, I4) — в
                # последней строке с deploy.sh (FINAL fix1: давняя «;» не перекрывает причину)
                last = envkit.last_run(envkit.journal(box), "deploy.sh")
                if last is not None and envkit.sequence(last[0], _SEMI):
                    return Verdict(False, self.MSG_SEMI)
                return Verdict(False, self.MSG_NO_BUILD)
            if v == 1:
                return Verdict(False, self.MSG_FIXED)
            if line != f"deployed {st['tag']}":
                return Verdict(False, self.MSG_WRONG_MAIN)
            if any(envkit.sequence(x, _AND) for x in lines):
                return Verdict(True)
            return Verdict(False, self.MSG_AND)
        if v == 1 and texts["notify.log"] is not None:
            if any(envkit.sequence(x, _AND_OR) for x in lines):
                return Verdict(True)
            if any(_if_chain(x) for x in lines):
                return Verdict(True)        # FINAL fix1, M2: if … then … else … fi — то же
            last = envkit.last_run(envkit.journal(box), "notify.sh")
            if last is not None and envkit.sequence(last[0], _AND_SEMI):
                return Verdict(False, self.MSG_SEMI_NOTIFY)
            return Verdict(False, self.MSG_ONE_LINE)
        return Verdict(False)


# --- FB14: cron — строка расписания ----------------------------------------------------------
# Курс-карта (раздел 6, «Окружение»): строка «минута час день месяц день_недели команда»,
# полный путь (у cron короткий PATH). Настоящий crontab владельца не трогаем: в песочнице —
# учебный (termit_app/cronstub.py, uses_crontab), расписание — в .termit/crontab.

CRON_SCRIPTS = ("backup", "report", "cleanup", "sync")
CRON_SH = """#!/bin/sh
# {name}: a job for the schedule. Prints the time it ran.
date
"""
CRON_STEPS = (5, 10, 15, 20, 30)
_FULL_PATH = re.compile(r"^(?:/|~/|\$HOME/|\$\{HOME\}/)")


class CronLine(Task):
    """crontab ФАЙЛ, crontab -l: строка из пяти полей и команды; */n, a-b; полный путь."""
    id = "cron_line"
    track = "env"
    title = "По расписанию"
    par = 90
    uses_crontab = True
    scroll = ("Строка расписания cron: минута час день_месяца месяц день_недели команда — "
              "15 3 * * * $HOME/bin/backup.sh: каждый день в 03:15. * — «любое».\n"
              "crontab my.cron — поставить расписание из файла, crontab -l — list, показать "
              "его.\n"
              "PATH по расписанию короткий: команду пиши полным путём.")
    variants = (
        Variant("Скрипт ~/bin/{name}.sh должен запускаться каждый день в {hh:02d}:{mm:02d}. "
                "Напиши строку расписания в my.cron и поставь её: crontab my.cron.",
                hints=("Пять полей и команда: минута, час, день месяца, месяц, день недели; * — "
                       "любое.",
                       "Минута {mm}, час {hh}, остальные три — *. Команда — полным путём: "
                       "$HOME/bin/{name}.sh.",
                       "echo '{mm} {hh} * * * $HOME/bin/{name}.sh' > my.cron; crontab my.cron; "
                       "crontab -l"),
                solution="echo '{mm} {hh} * * * $HOME/bin/{name}.sh' > my.cron; crontab "
                         "my.cron; crontab -l",
                wrong=("echo '{hh} {mm} * * * $HOME/bin/{name}.sh' > my.cron; crontab my.cron",
                       "echo '{mm} {hh} * * * $HOME/bin/{name}.sh' > my.cron"),
                alternatives=("echo '{mm} {hh} * * * $HOME/bin/{name}.sh' | crontab - — та же "
                              "строка без файла: - значит «со входа»",)),
        Variant("Скрипт ~/bin/{name}.sh нужен по будням (понедельник–пятница) в {hh:02d}:00. "
                "Напиши строку в my.cron и поставь её: crontab my.cron.",
                hints=("День недели — пятое поле: 1 — понедельник, 5 — пятница, 0 и 7 — "
                       "воскресенье.",
                       "Диапазон пишут через дефис: 1-5. Минута 0, час {hh}.",
                       "echo '0 {hh} * * 1-5 $HOME/bin/{name}.sh' > my.cron; crontab my.cron; "
                       "crontab -l"),
                solution="echo '0 {hh} * * 1-5 $HOME/bin/{name}.sh' > my.cron; crontab "
                         "my.cron; crontab -l",
                wrong=("echo '0 {hh} 1-5 * * $HOME/bin/{name}.sh' > my.cron; crontab my.cron",
                       "echo '0 {hh} * * * $HOME/bin/{name}.sh' > my.cron; crontab my.cron"),
                alternatives=("echo '0 {hh} * * mon-fri $HOME/bin/{name}.sh' — дни можно и "
                              "именами",)),
        Variant("Скрипт ~/bin/{name}.sh должен запускаться каждые {step} минут, круглые сутки. "
                "Напиши строку в my.cron и поставь её: crontab my.cron.",
                hints=("«Каждые N» пишут через косую: */N — «каждое N-е значение».",
                       "Минуты — */{step}, остальные четыре поля — *.",
                       "echo '*/{step} * * * * $HOME/bin/{name}.sh' > my.cron; crontab my.cron; "
                       "crontab -l"),
                solution="echo '*/{step} * * * * $HOME/bin/{name}.sh' > my.cron; crontab "
                         "my.cron; crontab -l",
                wrong=("echo '{step} * * * * $HOME/bin/{name}.sh' > my.cron; crontab my.cron",
                       "echo '*/{step} * * * * {name}.sh' > my.cron; crontab my.cron"),
                alternatives=("перечислить минуты через запятую (0,15,30,45) — то же, но "
                              "длиннее",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("cron — служба, которая запускает команды по часам. Строка: минута, час, день "
               "месяца, месяц, день недели, команда; * — «любое», a-b — диапазон, */n — "
               "«каждое n-е». Команду пишут полным путём: у cron свой короткий PATH, и "
               "«руками работает, по расписанию — нет» — чаще всего про это.")
    spell = "M H * * * /полный/путь — по расписанию; crontab файл — поставить; crontab -l"
    STORE = ".termit/crontab"
    MSG_NOT_INSTALLED = ("Строка есть в my.cron, но расписание не поставлено: crontab my.cron "
                         "(потом crontab -l — проверить).")
    MSG_NO_LINE = ("В расписании нет строки со скриптом {name}.sh. Проверь: crontab -l.")
    MSG_PATH = ("Команда без полного пути: у cron короткий PATH (/usr/bin:/bin), {cmd} он не "
                "найдёт. Пиши $HOME/bin/{name}.sh.")
    MSG_WHEN = "Строка стоит, но время не то: {why}. Поправь my.cron и снова crontab my.cron."
    FIELD_NAMES = ("минута", "час", "день месяца", "месяц", "день недели")

    def _v(self, state: dict) -> int:
        return variant_index(state.get("_variant", 0), len(self.variants))

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        name = rng.choice(CRON_SCRIPTS)
        os.chmod(kit.write(kit.home(box) / "bin" / f"{name}.sh", CRON_SH.format(name=name)),
                 0o755)
        return {"name": name, "hh": rng.randint(1, 22), "mm": rng.randint(1, 59),
                "step": rng.choice(CRON_STEPS)}

    def want(self, state: dict) -> List[set]:
        from termit_app import cronstub
        v = self._v(state)
        allv = [cronstub.field_set("*", lo, hi, names) for _, lo, hi, names in cronstub.FIELDS]
        if v == 0:
            return [{state["mm"]}, {state["hh"]}] + allv[2:]
        if v == 1:
            return [{0}, {state["hh"]}, allv[2], allv[3], {1, 2, 3, 4, 5}]
        return [set(range(0, 60, state["step"]))] + allv[1:]

    def _lines(self, text: Optional[str], name: str):
        from termit_app import cronstub
        out = []
        for line in (text or "").split("\n"):
            sets, cmd, err = cronstub.parse_line(line)
            if sets and f"{name}.sh" in (cmd or ""):
                out.append((sets, cmd.strip()))
        return out

    def check(self, ctx) -> Verdict:
        st = ctx.state
        name = st["name"]
        kind, text = envkit.box_text(ctx.box, self.STORE, envkit.TEXT_CAP)
        mine = self._lines(text, name)
        if not mine:
            _, draft = envkit.box_text(ctx.box, "my.cron", envkit.TEXT_CAP)
            if self._lines(draft, name):
                return Verdict(False, self.MSG_NOT_INSTALLED)
            if kind == "ok":
                return Verdict(False, self.MSG_NO_LINE.format(name=name))
            return Verdict(False)
        sets, cmd = mine[-1]
        word = cmd.split()[0]
        if not _FULL_PATH.match(word) or not word.endswith(f"/bin/{name}.sh"):
            return Verdict(False, self.MSG_PATH.format(cmd=word, name=name))
        want = self.want(st)
        for got, exp, field in zip(sets, want, self.FIELD_NAMES):
            if got != exp:
                return Verdict(False, self.MSG_WHEN.format(why=f"поле «{field}» не то"))
        return Verdict(True)


# --- E11 ------------------------------------------------------------------------------------

# путь правки варианта: им jq и присваивает (ревью P3, M2 — путь целиком, а не слово ключа)
_JQ_PATHS = (".db.port", ".features.beta", ".server.hosts[0]")


def _assigns_path(arg: str, path: str) -> bool:
    """Фильтр jq присваивает path: после пути (пробелы можно) стоит = или |=, но не ==."""
    i = arg.find(path)
    while i >= 0:
        rest = arg[i + len(path):].lstrip()
        if rest.startswith("|=") or (rest.startswith("=") and not rest.startswith("==")):
            return True
        i = arg.find(path, i + 1)
    return False


def _to_file(words) -> bool:
    """В команде есть вывод в файл (> или >> не в /dev/null)."""
    for i, w in enumerate(words):
        target = None
        if w in (">", ">>", ">|"):
            target = words[i + 1] if i + 1 < len(words) else None
        elif w.startswith(">") and w.lstrip(">|"):
            target = w.lstrip(">|")
        if target and target != "/dev/null":
            return True
    return False


def _jq_assigns(jour, path: str) -> bool:
    """Был ли в журнале не упавший jq, чей фильтр присваивает path (.db.port = …) и чей вывод
    идёт в файл."""
    for line, ok in jour:
        if ok is False or "jq" not in line or path not in line:
            continue
        for seg in envkit.segments(line):
            _, cmd, args = envkit.lead(seg)
            if cmd is None or cmd.rsplit("/", 1)[-1] != "jq":
                continue
            if any(_assigns_path(a, path) for a in args) and _to_file(args):
                return True
    return False


def _last_write(jour, name: str) -> Optional[str]:
    """Чем последним в журнале писали файл name: "mv" — перенесли на его место другой файл,
    иначе вид записи envkit.writes (">", ">>", "cmd"); None — не писали. Линейно."""
    last = None
    for line, _ in jour:
        if name not in line:
            continue
        for seg in envkit.segments(line):
            op = envkit.writes(seg, name)
            if op is None:
                continue
            _, cmd, args = envkit.lead(seg)
            moved = (op == "cmd" and cmd == "mv" and len(args) >= 2
                     and args[-1].rsplit("/", 1)[-1] == name
                     and args[0].rsplit("/", 1)[-1] != name)
            last = "mv" if moved else op
    return last


def _first_diff(a, b, path: str = "") -> Optional[str]:
    """Первый путь (.db.port, .server.hosts[0]), где a и b расходятся; None — равны."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in list(b) + [k for k in a if k not in b]:
            if k not in a or k not in b:
                return f"{path}.{k}"
            d = _first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return path
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    if a == b and type(a) is type(b):
        return None
    return path


class JsonConfig(Task):
    """python3 -m json.tool (строка и колонка ошибки), jq '.a.b = X' f > new; mv new f;
    ловушка jq … f > f. «Решено» — app.json (разобран у родителя) равен ожидаемому и в
    журнале есть jq с присваиванием этого ключа."""
    id = "json_config"
    track = "env"
    title = "Конфиг на JSON"
    par = 90
    pinned_python = True
    scroll = ("python3 -m json.tool файл — проверить JSON и красиво напечатать (m — module, "
              "модуль); сломан — скажет где: line 7 column 5 (или строкой выше). jq '.db.port = "
              "6432' f.json > new.json — поменять значение и записать в НОВЫЙ файл; && mv "
              "new.json f.json — заменить, если jq не упал.\n"
              "jq … f.json > f.json сотрёт файл раньше, чем jq его прочтёт.")
    variants = (
        Variant("app.json не читается. Найди ошибку, почини, потом через jq выставь db.port = "
                "{port} — результат должен остаться в app.json.",
                hints=("python3 -m json.tool app.json назовёт строку и колонку ошибки.",
                       "Почини в nano, потом jq с присваиванием — в новый файл, и через && — mv обратно.",
                       "nano app.json — поправь строку из ошибки; потом jq '.db.port = {port}' "
                       "app.json > app.new.json && mv app.new.json app.json"),
                solution="python3 -m json.tool app.json; nano app.json — поправь строку из "
                         "ошибки; jq '.db.port = {port}' app.json > app.new.json && mv "
                         "app.new.json app.json",
                solution_script="print -r -- '{fixed}' > app.json; jq '.db.port = {port}' "
                                "app.json > app.new.json && mv app.new.json app.json",
                wrong=("jq '.db.port = 1' app.json > app.json",),
                alternatives=("jq . app.json — тоже назовёт строку ошибки",
                              "vim app.json — та же правка в vim")),
        Variant("Почини app.json (python3 -m json.tool покажет, где беда) и выключи через jq "
                "флаг features.beta — значение false, остальное как было.",
                hints=("python3 -m json.tool app.json назовёт строку и колонку ошибки.",
                       "Почини в nano, потом jq с присваиванием — в новый файл, и через && — mv обратно.",
                       "nano app.json — поправь строку из ошибки; потом jq '.features.beta = "
                       "false' app.json > app.new.json && mv app.new.json app.json"),
                solution="python3 -m json.tool app.json; nano app.json — поправь строку из "
                         "ошибки; jq '.features.beta = false' app.json > app.new.json && mv "
                         "app.new.json app.json",
                solution_script="print -r -- '{fixed}' > app.json; jq '.features.beta = "
                                "false' app.json > app.new.json && mv app.new.json app.json",
                wrong=("print -r -- '{fixed}' > app.json; jq '.features.beta = \"false\"' "
                       "app.json > n.json; mv n.json app.json",),
                alternatives=("jq . app.json — тоже назовёт строку ошибки",)),
        Variant("В app.json ошибка записи (JSON не читается), а первый адрес в server.hosts нужно заменить на "
                "{host} — через jq. Сделай оба дела.",
                hints=("python3 -m json.tool app.json назовёт строку и колонку ошибки.",
                       "Почини в nano, потом jq с присваиванием — в новый файл, и через && — mv обратно. "
                       "Первый элемент списка — [0], текст — в двойных кавычках.",
                       "nano app.json — поправь строку из ошибки; потом jq '.server.hosts[0] = "
                       "\"{host}\"' app.json > app.new.json && mv app.new.json app.json"),
                solution="python3 -m json.tool app.json; nano app.json — поправь строку из "
                         "ошибки; jq '.server.hosts[0] = \"{host}\"' app.json > app.new.json "
                         "&& mv app.new.json app.json",
                solution_script="print -r -- '{fixed}' > app.json; jq '.server.hosts[0] = "
                                "\"{host}\"' app.json > app.new.json && mv app.new.json app.json",
                wrong=("print -r -- '{fixed}' > app.json; jq '.server.hosts = [\"{host}\"]' "
                       "app.json > n.json; mv n.json app.json",),
                alternatives=("jq --arg h {host} '.server.hosts[0] = $h' — значение снаружи "
                              "фильтра: --arg h задаёт переменную $h",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("json.tool и jq . называют строку, где JSON сломан, а jq с присваиванием правит "
               "одно значение, не трогая остальное. Пишут в новый файл: > чистит файл раньше, "
               "чем jq его прочтёт.")
    spell = "python3 -m json.tool f.json — проверить; jq '.a.b = X' f > new && mv new f — поправить"
    secret_keys = ("fixed",)        # исправленный текст — у судьи: задача скрытая
    OUT = "app.json"
    WHAT = ("db.port = {port}", "features.beta = false", "server.hosts[0] = {host}")
    MSG_MISSING = "app.json нет на месте. Набери reset — он вернётся, сломанный, как был."
    MSG_CLOBBER = ("app.json пуст: jq … > app.json стёр файл раньше, чем jq его прочёл. Пиши в "
                   "новый файл и mv. Набери reset — app.json вернётся.")
    # E24a, I2: писал в новый файл, но jq упал — и mv перенёс пустой файл на место app.json
    MSG_JQ_FAILED = ("app.json пуст: jq упал (его ошибка — выше), а mv всё равно перенёс пустой "
                     "файл. Ставь && между jq и mv — mv сработает, только если jq не упал. reset "
                     "вернёт app.json.")
    MSG_BROKEN = ("app.json всё ещё не JSON: python3 -m json.tool app.json скажет line и column "
                  "ошибки.")
    MSG_DEEP = "app.json вложен слишком глубоко — это уже не конфиг. Набери reset."
    MSG_PARTIAL = "Сделано 1 из 2: app.json читается. Осталось — {what} через jq, в новый файл и mv."
    MSG_HAND = ("app.json верен, но правка сделана руками. Задача — про jq: jq '.…' app.json > "
                "app.new.json && mv app.new.json app.json.")
    MSG_QUOTED = ("{path} — в кавычках, то есть текст. {plain} пиши без кавычек: jq '{path} = "
                  "{plain}'.")
    MSG_VALUE = "{path} = {got}, а нужно {want}."
    MSG_OTHER = ("Задел лишнее: {path} должен остаться как был. Набери reset и поправь "
                 "только {what}.")

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        d = envkit.app_config(rng)
        kit.write(Path(box) / self.OUT, d["broken"])
        return {"port": d["port"], "host": d["host"], "fixed": d["text"],
                "broken_sha": kit.sha(Path(box) / self.OUT)}

    def _v(self, state: dict) -> int:
        return variant_index(state.get("_variant", 0), len(self.variants))

    def _target(self, state: dict):
        """(путь как в jq, функция-получатель, нужное значение)."""
        v = self._v(state)
        if v == 0:
            return ".db.port", ("db", "port"), state["port"]
        if v == 1:
            return ".features.beta", ("features", "beta"), False
        return ".server.hosts[0]", ("server", "hosts", 0), state["host"]

    @staticmethod
    def _get(doc, keys):
        for k in keys:
            try:
                doc = doc[k]
            except (KeyError, IndexError, TypeError):
                return None
        return doc

    @staticmethod
    def _set(doc, keys, value) -> bool:
        for k in keys[:-1]:
            try:
                doc = doc[k]
            except (KeyError, IndexError, TypeError):
                return False
        try:
            doc[keys[-1]] = value
        except (KeyError, IndexError, TypeError):
            return False
        return True

    def check(self, ctx) -> Verdict:
        import copy
        import hashlib
        import json
        st, box = ctx.state, ctx.box
        v = self._v(st)
        kind, data = envkit.box_file(box, self.OUT, envkit.TEXT_CAP)
        if kind == "missing":
            return Verdict(False, self.MSG_MISSING)
        bad = envkit.file_problem(kind, self.OUT)
        if bad:
            return Verdict(False, bad)
        if hashlib.sha1(data).hexdigest() == st["broken_sha"]:
            return Verdict(False)           # ещё не трогали: молчим
        jk, doc = envkit.load_json(data.decode("utf-8", errors="replace"))
        if jk == "empty":
            moved = _last_write(envkit.journal(box), self.OUT) == "mv"
            return Verdict(False, self.MSG_JQ_FAILED if moved else self.MSG_CLOBBER)
        if jk == "deep":
            return Verdict(False, self.MSG_DEEP)
        if jk == "broken":
            return Verdict(False, self.MSG_BROKEN)
        orig = json.loads(st["fixed"])
        path, keys, value = self._target(st)
        want = copy.deepcopy(orig)
        self._set(want, keys, value)
        what = self.WHAT[v].format(**st)
        if _first_diff(doc, want) is None:
            if _jq_assigns(envkit.journal(box), _JQ_PATHS[v]):
                return Verdict(True)
            return Verdict(False, self.MSG_HAND)
        if _first_diff(doc, orig) is None:
            return Verdict(False, self.MSG_PARTIAL.format(what=what))
        probe = copy.deepcopy(doc)
        if self._set(probe, keys, value) and _first_diff(probe, want) is None:
            got = self._get(doc, keys)
            plain = json.dumps(value, ensure_ascii=False)
            if isinstance(got, str) and not isinstance(value, str) and got == plain:
                return Verdict(False, self.MSG_QUOTED.format(path=path, plain=plain))
            return Verdict(False, self.MSG_VALUE.format(
                path=path, got=json.dumps(got, ensure_ascii=False)[:40], want=plain))
        other = _first_diff(doc, want) or path
        return Verdict(False, self.MSG_OTHER.format(path=other.lstrip("."), what=what))


# --- E13 ------------------------------------------------------------------------------------

MSG_RAN = ("Ты его запустил: в ~/.zshrc песочницы теперь его строка-метка. В жизни она легла "
           "бы в твой настоящий ~/.zshrc и срабатывала при каждом старте. Здесь её уберёт "
           "reset.")


def ran_dirty(box) -> bool:
    """Игрок запускал учебную «заразу»: в ~/.zshrc песочницы стоит её метка (envkit.SYNC_MARK).
    Читает родитель — только обычный файл песочницы, с пределом размера."""
    _, text = envkit.box_text(box, ".termit/home/.zshrc", envkit.TEXT_CAP)
    return bool(text) and any(x.strip() in envkit.MARKS for x in text.splitlines())


class ScriptAudit(AnswerTask):
    """head, grep -n -E по опасным словам, shasum -a 256 и -c: хэш доказывает «тот самый
    файл», а не «безопасный». downloads/ собирает envkit.downloads; «грязный» скрипт безвреден
    (A8). Ловушки — только при точном равенстве сданного; запуск «заразы» — отклик без штрафа."""
    id = "script_audit"
    track = "env"
    title = "Прочти, потом запускай"
    par = 90
    scroll = ("Чужой скрипт сначала читай: head -n 20 файл, less файл. grep -n -E "
              "'curl|wget|eval|\\.zshrc' * — опасные места с номерами строк.\n"
              "shasum -a 256 файл — отпечаток файла (a — algorithm); shasum -a 256 -c "
              "SHA256SUMS — check, сверить все разом. Совпал — файл тот, что выложил автор. "
              "Безопасен ли — решаешь ты, читая.")
    variants = (
        Variant("В downloads/ — скрипты, скачанные из сети. Один из них портит настройки "
                "оболочки. Как он называется? ans ИМЯ",
                hints=("Не запускай — читай: grep по всем файлам сразу.",
                       "grep -n -E 'curl|\\.zshrc' downloads/* — кто из них пишет в ~/.zshrc?",
                       "grep -n -E 'curl|wget|eval|\\.zshrc' downloads/*, затем ans ИМЯ"),
                solution="grep -n -E 'curl|wget|eval|\\.zshrc' downloads/*",
                solution_script="cd downloads; grep -l '\\.zshrc' *",
                wrong=("cd downloads; shasum -a 256 -c SHA256SUMS 2>/dev/null | grep FAILED | "
                       "cut -d: -f1",),
                alternatives=("less downloads/ИМЯ и /zshrc — поиск внутри less",)),
        Variant("В downloads/ рядом со скриптами лежит SHA256SUMS — отпечатки от автора. Какой "
                "файл не совпадает с опубликованным отпечатком? ans ИМЯ",
                hints=("Отпечаток печатает shasum -a 256, а весь список разом сверит флаг -c (check).",
                       "Сверяй из папки downloads: имена в SHA256SUMS — без пути. FAILED покажет "
                       "чужака.",
                       "cd downloads; shasum -a 256 -c SHA256SUMS, затем ans ИМЯ"),
                solution="cd downloads; shasum -a 256 -c SHA256SUMS",
                solution_script="cd downloads; shasum -a 256 -c SHA256SUMS 2>/dev/null | grep "
                                "FAILED | cut -d: -f1",
                wrong=("cd downloads; grep -l '\\.zshrc' *",),
                alternatives=("shasum -a 256 downloads/* — отпечатки всех и сверка глазами",)),
        Variant("Какой скрипт из downloads/ пишет в ~/.zshrc и на какой строке? Назови оба: "
                "ans ИМЯ НОМЕР",
                hints=("grep -n печатает номер строки перед её текстом.",
                       "Ищи по всем файлам разом: grep -n по шаблону .zshrc (точку — через \\.).",
                       "grep -n '\\.zshrc' downloads/*, затем ans ИМЯ НОМЕР"),
                solution="grep -n '\\.zshrc' downloads/*",
                solution_script="cd downloads; grep -n '\\.zshrc' * | cut -d: -f1,2 | tr : ' '",
                wrong=("cd downloads; grep -n curl * | cut -d: -f1,2 | tr : ' '",),
                alternatives=("head -n 20 downloads/ИМЯ — строки по порядку, считать глазами",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Отпечаток говорит «файл не меняли», но не говорит «файл добрый». Читать "
               "приходится всё равно.")
    spell = "grep -n -E 'curl|eval|\\.zshrc' * — чужой скрипт; shasum -a 256 -c SHA256SUMS — сверка"
    trap_messages = {
        "tampered": "Этот подменён, но ничего не портит — посмотри, кто пишет в ~/.zshrc.",
        "dirty": "Отпечаток у него верный: автор сам выложил такой файл. Отпечаток скажет «файл не "
                 "подменили», но не скажет «файл безопасен».",
        "curl": "Это строка скачивания, а нужна запись в настройки — строка с .zshrc.",
    }
    FALLBACKS = (
        "Не то. Не запускай — читай: grep -n по всем файлам downloads/ покажет, кто пишет в "
        "~/.zshrc.",
        "Не то. Сверь отпечатки из папки downloads: shasum -a 256 -c SHA256SUMS — ищи FAILED.",
        "Не то. Нужны имя скрипта и номер строки с .zshrc — grep -n печатает их перед текстом.",
    )
    DIR = "downloads"
    secret_keys = AnswerTask.secret_keys + ("names",)
    MSG_EXT = "Имя файла — целиком, как в ls: с .sh."
    # E24a (аудит, мелкие): shasum -c не из той папки — у всех «FAILED open or read»
    MSG_OPEN = ("«FAILED open or read» — shasum не нашёл файл: имена в SHA256SUMS без пути. "
                "Сверяй из папки с файлами: cd downloads.")

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        d = envkit.downloads(rng)
        for name, text in d["files"].items():
            os.chmod(kit.write(Path(box) / self.DIR / name, text), 0o644)
        kit.write(Path(box) / self.DIR / "SHA256SUMS", d["sums"])
        names = sorted(d["files"])        # у судьи: отклик «с .sh» — по любому файлу
        if variant == 1:
            return {"answer": d["tampered"], "traps": [["dirty", d["dirty"]]], "names": names}
        if variant == 2:
            return {"answer": f"{d['dirty']} {d['zshrc']}",
                    "traps": [["curl", f"{d['dirty']} {d['curl']}"]], "names": names}
        return {"answer": d["dirty"], "traps": [["tampered", d["tampered"]]], "names": names}

    def _v(self, state: dict) -> int:
        return variant_index(state.get("_variant", 0), len(self.variants))

    @staticmethod
    def _norm(given: str) -> str:
        """downloads/x.sh:13 и ./x.sh 13 — как x.sh 13: путь и двоеточие grep — не ошибка."""
        out = []
        for w in textnorm.clean(given).replace(":", " ").split():
            for prefix in ("./", "downloads/", "./downloads/"):
                if w.startswith(prefix) and len(w) > len(prefix):
                    w = w[len(prefix):]
            out.append(w)
        return " ".join(out)

    def matches(self, given: str, ctx) -> bool:
        exp = textnorm.parts(self.expected(ctx.state))
        return textnorm.same_parts(self._norm(given), exp)

    def wrong_message(self, given: str, ctx) -> str:
        if "open or read" in given.casefold():
            return self.MSG_OPEN
        g = self._norm(given)
        for key, value in ctx.state.get("traps") or ():
            if key in self.trap_messages and textnorm.same_parts(g, textnorm.parts(str(value))):
                return self.trap_messages[key]
        stems = {n.rsplit(".", 1)[0].casefold() for n in ctx.state.get("names") or ()}
        if any("." not in w and w.casefold() in stems for w in g.split()):
            return self.MSG_EXT
        return self.common_mistake(given, ctx) or self.FALLBACKS[self._v(ctx.state)]

    def check(self, ctx) -> Verdict:
        verdict = super().check(ctx)
        if not verdict.solved and ctx.answer is None and ran_dirty(ctx.box):
            return Verdict(False, MSG_RAN)
        return verdict


# --- FB14: shellcheck — линтер скриптов -----------------------------------------------------
# Курс-карта (разделы 3 и 6): после script_audit («прочти, потом запускай») — «дай прочитать
# машине»: shellcheck → код SCxxxx → правка → тишина. shellcheck здесь учебный
# (termit_app/shellstub.py, uses_shellcheck), настоящий ставится brew install shellcheck.
# Вариант C — zsh-скрипт: shellcheck его не понимает (SC1071), синтаксис проверяет zsh -n.
# Решено — по результату (копия, чистка, отчёт) плюс разбор скрипта тем же анализатором, что
# у заглушки; родитель скрипт не исполняет.

LINT_BACKUP_SH = """#!/bin/sh
# Copies one file into backup/ and says what it copied.
src=$1
mkdir -p backup
cp $src backup/
echo "copied: $src"
"""
CLEANUP_SH = """#!/bin/sh
# Removes temporary files from the folder given as the first word.
cd "$1"
rm -f ./*.tmp
echo "cleaned: $1"
"""
STATS_ZSH = """#!/bin/zsh
# Counts csv files in data/ and writes the number into count.txt.
cd "${0:a:h}" || exit 1
files=(data/*.csv(N))
if (( ${#files} > 0 )); then
  print -r -- "csv files: ${#files}" > count.txt
else
  print -r -- "csv files: 0" > count.txt
"""
SPACED_NAMES = ("march report.txt", "client list.txt", "old notes.txt", "tax form.txt",
                "trip plan.txt", "price list.txt")
CACHE_DIRS = ("cache", "tmp_files", "build_cache", "scratch")
KEEP_TMP = ("draft.tmp", "letter.tmp", "budget.tmp")
_FIX_CP = "sed -i '' 's/cp \\$src/cp \"$src\"/' backup.sh"
_FIX_CD = "sed -i '' 's/^cd \"\\$1\"$/cd \"$1\" || exit/' cleanup.sh"


class ShellLint(Task):
    """shellcheck скрипт.sh → SC-код → правка → тишина; zsh -n для zsh-скриптов."""
    id = "shell_lint"
    track = "env"
    title = "Скрипт на проверке"
    par = 90
    uses_shellcheck = True
    scroll = ("shellcheck скрипт.sh — проверка скрипта sh/bash без запуска: под строкой — ^ и "
              "код правила, например SC2086 — $имя без кавычек.\n"
              "Исправил — запусти снова: тишина — замечаний нет.\n"
              "Здесь shellcheck учебный; настоящий ставится brew install shellcheck.")
    variants = (
        Variant("./backup.sh '{name}' должен положить копию файла в backup/, а падает. "
                "Прогони shellcheck backup.sh, исправь то, на что он покажет, добейся тишины и "
                "сделай копию этим скриптом.",
                hints=("shellcheck backup.sh — под строкой с ошибкой будет ^ и код SC.",
                       "SC2086 — $src без двойных кавычек: имя с пробелом разваливается на два "
                       "слова. Нужно \"$src\".",
                       "shellcheck backup.sh; " + _FIX_CP + "; shellcheck backup.sh; "
                       "./backup.sh '{name}'"),
                solution="shellcheck backup.sh; " + _FIX_CP + "; shellcheck backup.sh; "
                         "./backup.sh '{name}'",
                wrong=("mkdir -p backup; cp '{name}' backup/",
                       _FIX_CP + "; ./backup.sh '{name}'"),
                alternatives=("nano backup.sh — поставить \"$src\" в двойные кавычки руками "
                              "(Ctrl+O, Enter, Ctrl+X)",)),
        Variant("./cleanup.sh {cache} чистит *.tmp в папке {cache}. Прежде чем доверять ему, "
                "прогони shellcheck cleanup.sh, исправь замечание, добейся тишины и почисти "
                "{cache} этим скриптом.",
                hints=("shellcheck cleanup.sh — прочти код и текст замечания.",
                       "SC2164 — cd без проверки: не зайдёт в папку — rm удалит *.tmp там, где "
                       "ты стоишь. Допиши к cd: || exit.",
                       "shellcheck cleanup.sh; " + _FIX_CD + "; shellcheck cleanup.sh; "
                       "./cleanup.sh {cache}"),
                solution="shellcheck cleanup.sh; " + _FIX_CD + "; shellcheck cleanup.sh; "
                         "./cleanup.sh {cache}",
                wrong=("rm -f {cache}/*.tmp",
                       "./cleanup.sh {cache}"),
                alternatives=("nano cleanup.sh — дописать к строке cd \"$1\" хвост || exit "
                              "руками",)),
        Variant("./stats.zsh должен записать в count.txt, сколько CSV в data/, но падает, а "
                "shellcheck его проверять отказывается. Проверь синтаксис (правила записи) "
                "через zsh -n, "
                "исправь и запусти ./stats.zsh.",
                hints=("shellcheck stats.zsh скажет SC1071: он понимает только sh и bash, а "
                       "это zsh.",
                       "zsh -n stats.zsh — проверка без запуска: покажет строку parse error. "
                       "if без закрывающего fi.",
                       "zsh -n stats.zsh; echo fi >> stats.zsh; zsh -n stats.zsh; ./stats.zsh"),
                solution="zsh -n stats.zsh; echo fi >> stats.zsh; zsh -n stats.zsh; ./stats.zsh",
                wrong=("echo fi >> stats.zsh; ./stats.zsh",
                       "print -r -- 'csv files: {n}' > count.txt"),
                alternatives=("nano stats.zsh — дописать fi последней строкой руками",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("shellcheck читает скрипт и называет места, где он сломается, — до запуска. "
               "Код SC в замечании ищут в справке, правят и прогоняют снова, пока не станет "
               "тихо. zsh он не понимает: там синтаксис (правила записи) проверяет zsh -n.")
    spell = "shellcheck f.sh — замечания с кодом SC; тишина = чисто; zsh -n f.zsh — синтаксис"
    MSG_NO_CHECK = ("Скрипт исправлен и сработал, но shellcheck ты не запускал. Прогони "
                    "shellcheck {script} — урок в том, чтобы прочитать его замечания.")
    MSG_ISSUES = ("shellcheck {script} ещё находит замечания ({codes}). Прогони его, исправь "
                  "строку под ^ и запусти скрипт снова.")
    MSG_GUTTED = ("В {script} пропала строка с {what} — скрипт больше не делает свою работу. "
                  "reset вернёт его.")
    MSG_MANUAL = ("Результат есть, но сделан руками, а не скриптом. Почини {script} и запусти "
                  "его: ./{script} …")
    MSG_NO_COPY = "Копии backup/{name} нет: запусти ./backup.sh '{name}' — в кавычках."
    MSG_COPY_DIFF = "backup/{name} не совпадает с оригиналом: копию делает cp в скрипте."
    MSG_LEFT = "В {cache} остались .tmp-файлы: запусти ./cleanup.sh {cache}."
    MSG_WRONG_PLACE = ("Пропали .tmp-файлы не из {cache}: {gone}. Чистка ушла не туда — reset "
                       "вернёт файлы.")
    MSG_NO_COUNT = "count.txt нет: его пишет ./stats.zsh, когда синтаксис исправлен."
    MSG_COUNT = "В count.txt «{got}», а CSV в data/ — {n}. Запусти ./stats.zsh ещё раз."
    MSG_NO_N = ("count.txt верный, но синтаксис ты не проверял. Прогони zsh -n stats.zsh — "
                "так zsh-скрипты проверяют без запуска.")

    def _v(self, state: dict) -> int:
        return variant_index(state.get("_variant", 0), len(self.variants))

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        name = rng.choice(SPACED_NAMES)
        cache = rng.choice(CACHE_DIRS)
        n = rng.randint(2, 6)
        state = {"name": name, "cache": cache, "n": n}
        if variant == 0:
            os.chmod(kit.write(box / "backup.sh", LINT_BACKUP_SH), 0o755)
            kit.write(box / name, " ".join(kit.latin(rng) for _ in range(8)) + "\n")
        elif variant == 1:
            os.chmod(kit.write(box / "cleanup.sh", CLEANUP_SH), 0o755)
            tmps = sorted(rng.sample(("a.tmp", "b.tmp", "run.tmp", "old.tmp", "log.tmp"), 3))
            for t in tmps:
                kit.write(box / cache / t, "temp\n")
            kit.write(box / cache / "keep.txt", "keep me\n")
            for t in KEEP_TMP:
                kit.write(box / t, "my work in progress\n")
            state["tmps"] = tmps
        else:
            os.chmod(kit.write(box / "stats.zsh", STATS_ZSH), 0o755)
            for i in range(n):
                kit.write(box / "data" / f"part{i + 1}.csv", "id,value\n1,10\n")
            kit.write(box / "data" / "readme.txt", "csv parts\n")
        return state

    @staticmethod
    def _ran_cmd(lines, name: str, flag: Optional[str] = None) -> bool:
        for _, cmd, args in envkit.commands(lines):
            if cmd == name and (flag is None or flag in args):
                return True
        return False

    def _script_state(self, ctx, script: str, need: str, what: str) -> Optional[str]:
        """Скрипт цел (строка need на месте) и чист по анализатору заглушки — иначе отклик."""
        from termit_app import shellstub
        kind, text = envkit.box_text(ctx.box, script, envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, script)
        if bad:
            return bad
        if kind == "missing" or need not in (text or ""):
            return self.MSG_GUTTED.format(script=script, what=what)
        issues = shellstub.analyze(text or "")
        if issues:
            codes = ", ".join(dict.fromkeys(x.code for x in issues))
            return self.MSG_ISSUES.format(script=script, codes=codes)
        return None

    def _check_backup(self, ctx, lines) -> Verdict:
        st = ctx.state
        name = st["name"]
        copy = Path(ctx.box) / "backup" / name
        if not copy.is_file() or copy.is_symlink():
            if not lines:
                return Verdict(False)
            return Verdict(False, self._script_state(ctx, "backup.sh", "cp ", "cp")
                           or self.MSG_NO_COPY.format(name=name))
        kind, got = envkit.box_file(ctx.box, f"backup/{name}")
        _, orig = envkit.box_file(ctx.box, name)
        if kind != "ok" or got != orig:
            return Verdict(False, self.MSG_COPY_DIFF.format(name=name))
        return self._finish(ctx, lines, "backup.sh", "cp ", "cp")

    def _finish(self, ctx, lines, script: str, need: str, what: str) -> Verdict:
        if not envkit.ran(lines, script, by_name=False):
            return Verdict(False, self.MSG_MANUAL.format(script=script))
        slip = self._script_state(ctx, script, need, what)
        if slip:
            return Verdict(False, slip)
        if not self._ran_cmd(lines, "shellcheck"):
            return Verdict(False, self.MSG_NO_CHECK.format(script=script))
        return Verdict(True)

    def _check_cleanup(self, ctx, lines) -> Verdict:
        st = ctx.state
        box = Path(ctx.box)
        gone = [t for t in KEEP_TMP if not (box / t).is_file()]
        if gone:
            return Verdict(False, self.MSG_WRONG_PLACE.format(cache=st["cache"],
                                                             gone=", ".join(gone)))
        left = [t for t in st["tmps"] if os.path.lexists(box / st["cache"] / t)]
        if left:
            if not lines:
                return Verdict(False)
            return Verdict(False, self._script_state(ctx, "cleanup.sh", "rm ", "rm")
                           or self.MSG_LEFT.format(cache=st["cache"]))
        if not (box / st["cache"] / "keep.txt").is_file():
            return Verdict(False, self.MSG_WRONG_PLACE.format(cache=st["cache"],
                                                             gone="keep.txt"))
        return self._finish(ctx, lines, "cleanup.sh", "rm ", "rm")

    def _check_stats(self, ctx, lines) -> Verdict:
        st = ctx.state
        kind, text = envkit.box_text(ctx.box, "count.txt", envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, "count.txt")
        if bad:
            return Verdict(False, bad)
        if kind == "missing":
            return Verdict(False, self.MSG_NO_COUNT if lines else None)
        got = envkit.first_line(text)
        if got != f"csv files: {st['n']}":
            return Verdict(False, self.MSG_COUNT.format(got=got, n=st["n"]))
        if not envkit.ran(lines, "stats.zsh", by_name=False):
            return Verdict(False, self.MSG_MANUAL.format(script="stats.zsh"))
        if not self._ran_cmd(lines, "zsh", "-n"):
            return Verdict(False, self.MSG_NO_N)
        return Verdict(True)

    def check(self, ctx) -> Verdict:
        lines = [c.line for c in ctx.cmds]
        v = self._v(ctx.state)
        if v == 0:
            return self._check_backup(ctx, lines)
        if v == 1:
            return self._check_cleanup(ctx, lines)
        return self._check_stats(ctx, lines)


# --- E14 ------------------------------------------------------------------------------------

QUARANTINE = "quarantine"
WALK_MAX = 300          # записей в quarantine/ или inbox/ больше — это уже не данные задачи


def walk_box(box, rel: str, limit: int = WALK_MAX):
    """Обычные файлы под папкой песочницы rel (вглубь, без перехода по ссылкам):
    ([(путь, байты, права)], проблема или None). Ссылка, канал, файл больше 4 МБ, слишком
    много записей — проблема с откликом (envkit.file_problem); папки нет — ([], None)."""
    root = Path(box) / rel
    try:
        st = os.lstat(root)
    except OSError:
        return [], None
    import stat as _stat
    if _stat.S_ISLNK(st.st_mode):
        return [], envkit.file_problem("link", rel)
    if not _stat.S_ISDIR(st.st_mode):
        return [], None
    out, stack, seen = [], [rel], 0
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(Path(box) / d)
        except OSError:
            return out, envkit.file_problem("bad", d)
        with it:
            for entry in it:            # без чтения папки целиком: стоп на пределе (M11)
                seen += 1
                if seen > limit:
                    return out, (f"В {rel}/ больше {limit} файлов — столько в задаче не "
                                 "бывает. Набери reset.")
                sub = f"{d}/{entry.name}"
                try:
                    lst = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if _stat.S_ISDIR(lst.st_mode):
                    if sub.count("/") < 8:
                        stack.append(sub)
                    continue
                kind, data = envkit.box_file(box, sub)
                bad = envkit.file_problem(kind, sub)
                if bad:
                    return out, bad
                if data is not None:
                    out.append((sub, data, _stat.S_IMODE(lst.st_mode)))
    return out, None


class AvScan(Task):
    """Учебный clamscan -r -i (A6), сигнатура — отпечаток известного образца, своя база .hsb
    (sha256:размер:Имя), карантин: mkdir -p quarantine, mv, chmod -x. Проверка — по состоянию
    файлов у родителя (по sha256 содержимого, а не по имени); av.log подделке не доверяет и
    в решение не идёт. Своя база разбирается тем же разборщиком, что у avstub."""
    id = "av_scan"
    track = "env"
    title = "Сигнатуры"
    par = 105
    uses_av = True
    scroll = ("clamscan -r -i папка — проверить всё внутри (r — recursive), показать только "
              "заражённое (i — infected, FOUND). Антивирус ищет сигнатуры — отпечатки известных "
              "вредоносов.\n"
              "Найденное — в карантин: mkdir -p quarantine; mv файл quarantine/; chmod -x файл (x — "
              "execute: снять право на запуск).")
    _NEW = "print -r -- '{sha}:{size}:Demo.New' >> ~/av/local.hsb"
    _QUAR = "mkdir -p quarantine; mv {moves} quarantine/; chmod -x quarantine/*"
    variants = (
        Variant("Проверь inbox/ антивирусом и перенеси всё заражённое в quarantine/ без права "
                "запуска. Чистые файлы не трогай.",
                hints=("-r — внутрь папок, -i — только найденное.",
                       "Найденное — в карантин: mkdir -p quarantine, mv файлов туда, потом "
                       "chmod -x.",
                       "clamscan -r -i inbox; " + _QUAR),
                solution="clamscan -r -i inbox; " + _QUAR,
                wrong=("clamscan -r -i inbox; mkdir -p quarantine; mv {moves} quarantine/",
                       "rm {moves}"),
                alternatives=("chmod a-x quarantine/* — то же, у всех сразу",)),
        Variant("База антивируса старая: новый образец (его sha256 — в report.txt) она не "
                "видит. Допиши свою сигнатуру в ~/av/local.hsb — строку sha256:размер:Имя — так, "
                "чтобы clamscan -d ~/av/local.hsb (своя база вместо обычной) его нашёл.",
                hints=("Строка базы .hsb — sha256:размер:Имя, по строке на образец.",
                       "Обе цифры — в report.txt, имя — любое латиницей без пробелов. Допиши "
                       "строку через >>.",
                       _NEW + "; clamscan -r -i -d ~/av/local.hsb inbox"),
                solution=_NEW + "; clamscan -r -i -d ~/av/local.hsb inbox",
                wrong=("print -r -- '{sha}:1:Demo.New' >> ~/av/local.hsb",),
                alternatives=("find inbox -type f -exec shasum -a 256 {{}} + — найти образец по "
                              "отпечатку (-exec выполнит shasum для найденных), wc -c — его "
                              "размер",)),
        Variant("Найди в inbox/ все заражённые файлы — и известные базе, и новый из report.txt "
                "— и убери их в quarantine/ без права запуска. Новый база не знает: допиши его "
                "сигнатуру строкой sha256:размер:Имя в ~/av/local.hsb и проверяй двумя базами — "
                "clamscan -d ~/av/local.hsb -d ~/av/main.hsb.",
                hints=("Старая база нового не знает: сначала своя сигнатура, потом проверка "
                       "двумя базами.",
                       "Своя сигнатура из report.txt: " + _NEW + " — потом проверка двумя "
                       "базами (-d дважды).",
                       "print -r -- СИГНАТУРА >> ~/av/local.hsb; clamscan -r -i -d "
                       "~/av/local.hsb -d ~/av/main.hsb inbox; mkdir -p quarantine; "
                       "mv НАЙДЕННЫЕ quarantine/; chmod -x quarantine/*"),
                solution=(_NEW + "; clamscan -r -i -d ~/av/local.hsb -d ~/av/main.hsb inbox; "
                          + _QUAR),
                wrong=("clamscan -r -i inbox; mkdir -p quarantine; mv {known} quarantine/; "
                       "chmod -x quarantine/*",),
                alternatives=("find inbox -type f -exec shasum -a 256 {{}} + | grep — найти "
                              "новый образец по отпечатку из report.txt",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Антивирус узнаёт только то, что уже видел. Новое ловят люди — и пишут "
               "сигнатуру для всех.")
    spell = "clamscan -r -i папка; sha256:размер:Имя в свой.hsb; mv в quarantine/ + chmod -x"
    secret_keys = ("dirty", "clean", "sample", "moves", "known")
    LOCAL = ".termit/home/av/local.hsb"
    MSG_CLEAN = ("{name} — чистый файл: антивирус его не назвал. Верни на место: mv {got} "
                 "{orig}")
    MSG_CHANGED = "{rel} изменён, а чистые файлы просили не трогать. Набери reset."
    MSG_GONE = "{rel} пропал. Набери reset — inbox/ вернётся как был."
    MSG_RM = ("{name} нет ни в inbox/, ни в quarantine/: удалённое не изучить и не вернуть. "
              "Карантин — это mv. Набери reset.")
    MSG_COPY = ("В quarantine/ — копия, а сам {name} остался в inbox/ и запускается. Карантин — "
                "это mv, а не cp: убери лишнюю копию из quarantine/ (rm) или набери reset.")
    MSG_X = "В карантине {name} всё ещё запускается: chmod -x quarantine/{name}"
    MSG_PART = ("В quarantine/ {k} из {m} заражённых — проверь ещё раз: clamscan -r -i inbox.")
    MSG_NEW = ("Новый образец остался в inbox/: старая база его не знает — нужна своя "
               "сигнатура (строка из report.txt в ~/av/local.hsb) и проверка с -d.")
    MSG_SIZE = ("Отпечаток верный, а размер — нет: clamscan сверяет оба. Размер — в report.txt "
                "(или wc -c файла).")
    MSG_FORMAT = ("Строку {n} в local.hsb не разобрать ({why}) — из-за неё clamscan выкинет "
                  "всю базу. Нужно sha256:размер:Имя, имя — латиницей без пробелов.")
    MSG_OTHER = ("В local.hsb отпечаток другого файла, а нужен новый образец — его sha256 в "
                 "report.txt.")
    MSG_NO_SAMPLE = "В local.hsb нет строки с sha256 нового образца из report.txt."
    MSG_REPORT = ("Это отпечаток самого report.txt, а нужен образец: его sha256 записан внутри "
                  "report.txt — cat report.txt.")
    # E24a, I8: mv без mkdir — файл стал «quarantine»; своя сигнатура уже есть (правило 8)
    MSG_NOT_DIR = ("quarantine — не папка, а файл: mv без mkdir переименовал его. Набери reset, "
                   "потом mkdir -p quarantine и mv в quarantine/.")
    MSG_SIG_DONE = ("Сигнатура есть — с ней clamscan видит и новый образец. Теперь всех "
                    "найденных — в quarantine/ (mv) и chmod -x.")

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        d = envkit.inbox(rng, variant)
        for rel, (data, mode) in d["files"].items():
            p = box / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            os.chmod(p, mode)
        av = kit.home(box) / "av"
        kit.write(av / "main.hsb", d["main_hsb"])
        kit.write(av / "local.hsb", envkit.LOCAL_HSB)
        if d["report"]:
            kit.write(box / "report.txt", d["report"])
        moves = " ".join(rel for rel, _, _ in d["dirty"])
        known = " ".join(rel for rel, _, new in d["dirty"] if not new)
        st = {"dirty": d["dirty"], "clean": d["clean"], "moves": moves, "known": known,
              "sample": d["sample"] or {}}
        if d["sample"]:
            st.update(sha=d["sample"]["sha"], size=d["sample"]["size"],
                      report_sha=envkit.sha256_hex(d["report"]))
        return st

    def _v(self, state: dict) -> int:
        return variant_index(state.get("_variant", 0), len(self.variants))

    def check(self, ctx) -> Verdict:
        verdict = self._sig(ctx) if self._v(ctx.state) == 1 else self._quarantine(ctx)
        if not verdict.solved and verdict.message is None and ran_dirty(ctx.box):
            return Verdict(False, MSG_RAN)
        return verdict

    def _sig(self, ctx) -> Verdict:
        from termit_app import avstub
        st = ctx.state
        kind, text = envkit.box_text(ctx.box, self.LOCAL, 64 * 1024)
        bad = envkit.file_problem(kind, "~/av/local.hsb")
        if bad:
            return Verdict(False, bad)
        if text is None or text == envkit.LOCAL_HSB:
            return Verdict(False)
        sample = st["sample"]
        entries, problems = avstub.parse_hsb(text)
        if problems:        # как ClamAV: сломанная строка — вся база отвергнута (ревью P3, M3)
            n, _, why = problems[0]
            return Verdict(False, self.MSG_FORMAT.format(n=n, why=why))
        size_off = False
        for algo, h, size, _ in entries:
            if h in (sample["sha"], sample["sha1"]):
                if size is None or size == sample["size"]:
                    return Verdict(True)
                size_off = True
        if size_off:
            return Verdict(False, self.MSG_SIZE)
        if any(h == st.get("report_sha") for _, h, _, _ in entries):
            return Verdict(False, self.MSG_REPORT)
        others = set(st["clean"].values()) | {h for _, h, _ in st["dirty"]}
        if any(h in others for _, h, _, _ in entries):
            return Verdict(False, self.MSG_OTHER)
        return Verdict(False, self.MSG_NO_SAMPLE)

    def _has_sig(self, ctx) -> bool:
        """В ~/av/local.hsb есть разобранная строка нового образца (отпечаток и размер)."""
        from termit_app import avstub
        sample = ctx.state.get("sample") or {}
        if not sample:
            return False
        _, text = envkit.box_text(ctx.box, self.LOCAL, 64 * 1024)
        if not text:
            return False
        entries, problems = avstub.parse_hsb(text)
        return not problems and any(
            h in (sample["sha"], sample["sha1"]) and size in (None, sample["size"])
            for _, h, size, _ in entries)

    def _quarantine(self, ctx) -> Verdict:
        import hashlib
        import stat as _stat
        st, box = ctx.state, ctx.box
        try:
            if _stat.S_ISREG(os.lstat(Path(box) / QUARANTINE).st_mode):
                return Verdict(False, self.MSG_NOT_DIR)
        except OSError:
            pass
        found, bad = walk_box(box, QUARANTINE)
        if bad:
            return Verdict(False, bad)
        quar = {}
        for rel, data, mode in found:
            quar.setdefault(hashlib.sha256(data).hexdigest(), (rel, mode))
        for rel, h in sorted(st["clean"].items()):
            kind, data = envkit.box_file(box, rel)
            name = rel.rsplit("/", 1)[1]
            if kind == "missing":
                if h in quar:
                    return Verdict(False, self.MSG_CLEAN.format(name=name, got=quar[h][0],
                                                                orig=rel.rsplit("/", 1)[0] + "/"))
                return Verdict(False, self.MSG_GONE.format(rel=rel))
            problem = envkit.file_problem(kind, rel)
            if problem:
                return Verdict(False, problem)
            if hashlib.sha256(data).hexdigest() != h:
                return Verdict(False, self.MSG_CHANGED.format(rel=rel))
        inbox, bad = walk_box(box, "inbox")
        if bad:
            return Verdict(False, bad)
        in_box = {hashlib.sha256(data).hexdigest() for _, data, _ in inbox}
        done, left_new, left = 0, False, 0
        for rel, h, new in st["dirty"]:
            name = rel.rsplit("/", 1)[1]
            if h in quar:
                if h in in_box:         # копия: сам файл (или его копия) ещё в inbox/ (I1)
                    return Verdict(False, self.MSG_COPY.format(name=name))
                if quar[h][1] & 0o111:
                    return Verdict(False, self.MSG_X.format(name=quar[h][0].split("/", 1)[1]))
                done += 1
                continue
            kind, data = envkit.box_file(box, rel)
            if kind == "ok" and hashlib.sha256(data).hexdigest() == h:
                left += 1
                left_new = left_new or new
                continue
            if kind != "missing":
                problem = envkit.file_problem(kind, rel)
                if problem:
                    return Verdict(False, problem)
            return Verdict(False, self.MSG_RM.format(name=name))
        if left == 0:
            return Verdict(True)
        sig = left_new and self._has_sig(ctx)
        if done == 0:
            return Verdict(False, self.MSG_SIG_DONE if sig else None)
        if left_new and left == 1:
            return Verdict(False, self.MSG_SIG_DONE if sig else self.MSG_NEW)
        return Verdict(False, self.MSG_PART.format(k=done, m=len(st["dirty"])))


# --- E15 ------------------------------------------------------------------------------------

MAIN_PY = '''"""Пишет в where.txt, из какого окружения запущен Python (sys.prefix)."""
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
(here / "where.txt").write_text(sys.prefix + "\\n", encoding="utf-8")
if sys.prefix == sys.base_prefix:
    print("main.py: запущен без окружения, Python —", sys.prefix)
else:
    print("main.py: окружение", sys.prefix)
'''
FOREIGN_USERS = ("anna", "dev", "max", "olga", "build", "ivan")
FOREIGN_DIRS = ("work", "projects", "src", "code")


def _box_paths(box, rel: str) -> set:
    """Путь rel в песочнице — как его напишут программы: через box и через его realpath."""
    return {os.path.normpath(os.path.join(b, rel)) for b in (str(box), os.path.realpath(box))}


class VenvBasics(Task):
    """python3 -m venv, source .venv/bin/activate, which python3, deactivate; venv не
    переносят — пересоздают. «Решено» — по файлу, который пишет сам main.py (sys.prefix), и
    удачному запуску main.py в журнале; C — по двум строкам which python3."""
    id = "venv_basics"
    track = "env"
    title = "Своя комната для пакетов"
    par = 90
    pinned_python = True
    stock = "light"
    start_dir = "proj"
    scroll = ("python3 -m venv .venv — виртуальное окружение (своя комната Python) в папке .venv: "
              "свой python3 и pip.\n"
              "source .venv/bin/activate — включить: в приглашении (.venv), which python3 — из "
              ".venv/bin.\n"
              "deactivate — выключить. Окружение помнит свой путь: переехал — rm -rf .venv "
              "(точное имя; f — force, без вопросов) и создай заново.")
    variants = (
        Variant("Создай здесь, в proj/, виртуальное окружение (свою комнату для пакетов) .venv, включи его и запусти "
                "python3 main.py изнутри — в where.txt должен оказаться путь этого окружения.",
                hints=("Окружение делает сам python3 — модулем venv.",
                       "python3 -m venv .venv, потом source .venv/bin/activate — и только "
                       "тогда python3 main.py.",
                       "python3 -m venv .venv; source .venv/bin/activate; python3 main.py"),
                solution="python3 -m venv .venv; source .venv/bin/activate; python3 main.py",
                wrong=("python3 main.py", "python3 -m venv .venv; python3 main.py"),
                alternatives=(".venv/bin/python3 main.py — python3 окружения и без activate",)),
        Variant("В proj/ лежит .venv, перенесённый с чужой машины: activate ведёт в никуда. "
                "Пересоздай окружение и запусти main.py из него.",
                hints=("Включи его и запусти python3 main.py — что оказалось в where.txt?",
                       "Чужой venv не чинят: удали папку .venv точным именем и создай заново, "
                       "потом включи.",
                       "rm -rf .venv; python3 -m venv .venv; source .venv/bin/activate; "
                       "python3 main.py"),
                solution="rm -rf .venv; python3 -m venv .venv; source .venv/bin/activate; "
                         "python3 main.py",
                wrong=("source .venv/bin/activate; python3 main.py",
                       "sed -i '' \"s|{foreign}|$PWD/.venv|\" .venv/bin/activate; "
                       "source .venv/bin/activate; .venv/bin/python3 main.py"),
                alternatives=("python3 -m venv --clear .venv — пересоздать на месте, без rm",)),
        Variant("Узнай, какой python3 запускается без окружения и с ним: создай .venv, включи и "
                "сохрани which python3 в venv.txt, потом выключи и допиши which python3 в "
                "venv.txt второй строкой.",
                hints=("which python3 печатает путь того python3, что запустится.",
                       "Первую строку — при включённом .venv (>), вторую — после deactivate "
                       "(>>).",
                       "python3 -m venv .venv; source .venv/bin/activate; which python3 > "
                       "venv.txt; deactivate; which python3 >> venv.txt"),
                solution="python3 -m venv .venv; source .venv/bin/activate; which python3 > "
                         "venv.txt; deactivate; which python3 >> venv.txt",
                wrong=("python3 -m venv .venv; source .venv/bin/activate; which python3 > "
                       "venv.txt; which python3 >> venv.txt",
                       "python3 -m venv .venv; which python3 > venv.txt; source "
                       ".venv/bin/activate; which python3 >> venv.txt"),
                alternatives=("command -v python3 — то же, что which",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("venv — своя папка с python3 и pip (установщик пакетов) для одного проекта: "
               "activate ставит её "
               "bin/ первой в PATH, deactivate убирает. Внутри зашиты полные пути, поэтому "
               "venv не переносят, а пересоздают.")
    spell = "python3 -m venv .venv; source .venv/bin/activate; deactivate"
    VENV = "proj/.venv"
    MSG_BASE = ("main.py запущен без окружения — в where.txt базовый Python. Включи его: "
                "source .venv/bin/activate, потом python3 main.py")
    MSG_OTHER = ("main.py запущен из другого окружения, а нужно proj/.venv: создай его здесь, "
                 "в proj/, и включи.")
    MSG_OLD = ("Окружение всё то же, перенесённое: внутри чужие пути. venv не чинят — "
               "пересоздают: rm -rf .venv (точное имя) и python3 -m venv .venv")
    MSG_FOREIGN = ("activate этого .venv ведёт в чужую папку — вот и запустился базовый "
                   "python3. venv не чинят — пересоздают: rm -rf .venv и python3 -m venv .venv")
    MSG_BASE_OLD = ("main.py запущен без окружения. А этот .venv — перенесённый, включать его "
                    "бесполезно: venv не чинят — пересоздают: rm -rf .venv и python3 -m venv .venv")
    MSG_RUN = ("where.txt пишет сам main.py, запущенный из окружения: source "
               ".venv/bin/activate, потом python3 main.py")
    MSG_CREATE = ("Окружения .venv ещё нет: python3 -m venv .venv, потом source "
                  ".venv/bin/activate и python3 main.py")
    MSG_WHICH_RUN = ("venv.txt пишет which python3: первая строка — с включённым .venv (> "
                     "venv.txt), вторая — после deactivate (>> venv.txt).")
    MSG_WHERE = "В where.txt не путь окружения: его пишет main.py — запусти python3 main.py."
    MSG_NO_VENV = "Окружения proj/.venv ещё нет: python3 -m venv .venv"
    MSG_SECOND = ("Первая строка есть. Теперь deactivate и допиши which python3 второй строкой: "
                  ">> venv.txt")
    MSG_ONE = ("Строка одна, и это python3 без окружения. Первой — при включённом .venv (>), "
               "второй — после deactivate (>>).")
    MSG_SAME = "Обе строки — из .venv: перед второй выключи окружение — deactivate."
    MSG_SWAP = "Строки наоборот: первой — с окружением, второй — без."
    MSG_FIRST = ("Первая строка — не python3 из proj/.venv: включи окружение (source "
                 ".venv/bin/activate) и запиши which python3.")
    MSG_NOT_PATH = "Во второй строке не путь: его печатает which python3 после deactivate."
    MSG_MANY = "В venv.txt нужно ровно две строки: с окружением и без."
    # E24a, I7: python3 -m venv поверх перенесённого .venv падает (Errno 2) — окружения нет
    MSG_OVER = ("python3 -m venv поверх перенесённого .venv не создаёт окружение (ошибка выше) — "
                "включать нечего. Сначала rm -rf .venv, потом python3 -m venv .venv (или сразу "
                "python3 -m venv --clear .venv).")

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        proj = Path(box) / "proj"
        kit.write(proj / "main.py", MAIN_PY)
        user, where = rng.choice(FOREIGN_USERS), rng.choice(FOREIGN_DIRS)
        minor = rng.randint(5, 18)
        if variant != 1:
            return {}
        st = {"foreign": f"/home/{user}/{where}/proj/.venv",
              "foreign_home": f"/home/{user}/.pyenv/versions/3.9.{minor}/bin"}
        kit.venv_from_stock(box, "light", "proj/.venv")
        kit.venv_foreign(proj / ".venv", st["foreign"], st["foreign_home"])
        return st

    def check(self, ctx) -> Verdict:
        st, box = ctx.state, ctx.box
        v = variant_index(st.get("_variant", 0), 3)
        if v == 2:
            return self._which(box)
        kind, text = envkit.box_text(box, "proj/where.txt", envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, "where.txt")
        if bad:
            return Verdict(False, bad)
        _, cfg = envkit.box_text(box, f"{self.VENV}/pyvenv.cfg", envkit.TEXT_CAP)
        old = v == 1 and cfg is not None and bool(st.get("foreign_home")) and \
            st["foreign_home"] in cfg
        if v == 1 and not old and cfg is not None and st.get("foreign"):
            # venv поверх перенесённого переписал pyvenv.cfg и упал: activate всё ещё чужой
            _, act = envkit.box_text(box, f"{self.VENV}/bin/activate", envkit.TEXT_CAP)
            if act is not None and st["foreign"] in act:
                return Verdict(False, self.MSG_OVER)
        if text is None:
            # B: python3 перенесённого venv ведёт к чужому интерпретатору — main.py не
            # запустился вовсе (правка activate руками, .venv/bin/python3 напрямую)
            if old and envkit.last_line(envkit.journal(box),
                                        lambda seg: envkit.py_runs(seg, "main.py"),
                                        "main.py"):
                return Verdict(False, self.MSG_OLD)
            return Verdict(False)
        first = envkit.first_line(text)
        line = os.path.normpath(first) if first else ""
        if line in _box_paths(box, self.VENV):
            if old:
                return Verdict(False, self.MSG_OLD)
            if cfg is None:
                return Verdict(False, self.MSG_NO_VENV)
            if not self._ran_in_venv(box):
                return Verdict(False, self.MSG_RUN)
            return Verdict(True)
        if not line.startswith("/"):
            return Verdict(False, self.MSG_WHERE)
        if any(line.startswith(b + "/") for b in _box_paths(box, ".")):
            return Verdict(False, self.MSG_OTHER)
        if not old:
            # M2 ревью P4: окружения ещё нет — сначала создать, а не включать
            return Verdict(False, self.MSG_BASE if cfg is not None else self.MSG_CREATE)
        lines = [x for x, _ in envkit.journal(box)]
        activated = any(cmd in ("source", ".") and args and args[0].endswith("activate")
                        for _, cmd, args in envkit.commands(lines))
        return Verdict(False, self.MSG_FOREIGN if activated else self.MSG_BASE_OLD)

    @staticmethod
    def _ran_in_venv(box) -> bool:
        """I1 ревью P4: where.txt написал main.py, запущенный из .venv (python3 при
        включённом .venv или .venv/bin/python3), запуск удачный, и после него where.txt
        никто не писал (>, >>, cp, mv, tee…)."""
        rows = envkit.walk_venv(envkit.journal(box))
        last = None
        for k, (_, _, seg, active) in enumerate(rows):
            if envkit.py_runs(seg, "main.py") and envkit.from_venv(seg, active, ".venv"):
                last = k
        if last is None or rows[last][1] is False:
            return False
        return not any(envkit.writes(seg, "where.txt") for _, _, seg, _ in rows[last + 1:])

    @staticmethod
    def _which_lines(box) -> bool:
        """I1 ревью P4: в журнале — удачный which python3 (command -v, type, whence) в
        venv.txt при включённом .venv, а позже — такой же с >> при выключенном."""
        first = False
        for _, ok, seg, active in envkit.walk_venv(envkit.journal(box)):
            ws = envkit.words(seg)
            if ok is False or not ws or ws[0] not in ("which", "command", "type", "whence") \
                    or "python3" not in ws:
                continue
            op = envkit.writes(seg, "venv.txt")
            inside = active is not None and active.rsplit("/", 1)[-1] == ".venv"
            if inside and op in (">", ">>"):
                first = True
            elif first and not inside and op == ">>":
                return True
        return False

    def _which(self, box) -> Verdict:
        kind, text = envkit.box_text(box, "proj/venv.txt", envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, "venv.txt")
        if bad:
            return Verdict(False, bad)
        if text is None:
            return Verdict(False)
        if envkit.box_file(box, f"{self.VENV}/pyvenv.cfg", envkit.TEXT_CAP)[0] != "ok":
            return Verdict(False, self.MSG_NO_VENV)
        venv_py = _box_paths(box, f"{self.VENV}/bin/python3")
        lines = [os.path.normpath(x.strip()) for x in text.splitlines() if x.strip()]
        inside = [x in venv_py for x in lines]
        if not lines:
            return Verdict(False)
        if len(lines) == 1:
            return Verdict(False, self.MSG_SECOND if inside[0] else self.MSG_ONE)
        if len(lines) > 2:
            return Verdict(False, self.MSG_MANY)
        if inside == [True, True]:
            return Verdict(False, self.MSG_SAME)
        if inside == [False, True]:
            return Verdict(False, self.MSG_SWAP)
        if not inside[0]:
            return Verdict(False, self.MSG_FIRST)
        second = lines[1]
        if (not second.startswith("/") or second.rsplit("/", 1)[-1] != "python3"
                or "/.venv/" in second):
            return Verdict(False, self.MSG_NOT_PATH)
        if not self._which_lines(box):
            return Verdict(False, self.MSG_WHICH_RUN)
        return Verdict(True)


# --- E16 ------------------------------------------------------------------------------------

SALES_CITIES = ("Kazan", "Omsk", "Tver", "Perm", "Sochi", "Ufa", "Kursk")
SALES_ITEMS = ("tea", "coffee", "juice", "water", "milk", "cocoa")
LIGHT_NAMES = ("datapeek", "sockhttp", "tabprint")      # учебные пакеты эталона light


def _install(segment_args, name: str) -> bool:
    """В аргументах pip install есть пакет name (ИМЯ, ИМЯ==…, ИМЯ>=…; без ключей)."""
    for a in segment_args:
        if not a.startswith("-") and envkit.canon(re.split(r"[=<>!~\[;]", a, 1)[0]) == name:
            return True
    return False


_ONE_EQ = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\s*=(?!=)")


def _one_eq(args) -> bool:
    """В аргументах pip install версия через одно =: имя=1.0, «имя = 1.0», 'имя = 1.0'."""
    for a in args:
        if a.startswith("-"):
            continue
        if _ONE_EQ.match(a) or (a.startswith("=") and not a.startswith("==")):
            return True
    return False


def wheels_home(box) -> None:
    """~/wheels песочницы — колёса учебных пакетов из запаса (.termit/stock/wheels): только
    обычные файлы *.whl."""
    src = Path(box) / ".termit" / "stock" / "wheels"
    dst = kit.home(box) / "wheels"
    dst.mkdir(parents=True, exist_ok=True)
    for name in sorted(os.listdir(src)):
        p = src / name
        if name.endswith(".whl") and p.is_file() and not p.is_symlink():
            shutil.copy2(p, dst / name)


def bare_venv(box, rel: str = ".venv", keep=()) -> None:
    """Готовый venv задачи из запаса light: учебные пакеты, кроме keep, убраны (как pip
    uninstall — kit.venv_drop)."""
    kit.venv_from_stock(box, "light", rel)
    for name in LIGHT_NAMES:
        if name not in keep:
            kit.venv_drop(Path(box) / rel, name)


def _reports_tabprint(seg: str, active) -> bool:
    """python3 -c с import tabprint или pip show/list — из .venv."""
    if not envkit.from_venv(seg, active, ".venv"):
        return False
    if envkit.py_inline(seg):
        return "tabprint" in seg
    a = envkit.pip_args(seg)
    return bool(a) and a[0] in ("show", "list")


class PipOffline(AnswerTask):
    """pip install --no-index --find-links, зависимости, консольный скрипт, pip list и show,
    ИМЯ==версия, pip uninstall -y. A и C — «сделай», B — «найди и назови» (ans). Что стоит в
    .venv, родитель видит по именам папок dist-info; сводку datapeek считает тем же кодом
    пакета из src/ на данных генератора (pylibs.peek), а не запуском из песочницы."""
    id = "pip_offline"
    track = "env"
    title = "pip без сети"
    par = 105
    pinned_python = True
    stock = "wheels"
    scroll = ("pip install --no-index --find-links ~/wheels ИМЯ — пакет из папки, без сети.\n"
              "pip ставит во включённый venv и сам тянет зависимости — то, что нужно пакету.\n"
              "pip list — что стоит; pip uninstall -y ИМЯ — убрать пакет (y — yes, без "
              "вопроса).")
    variants = (
        Variant("Поставь в .venv пакет datapeek из папки ~/wheels (сети нет) и сохрани его "
                "сводку по sales.csv: datapeek sales.csv > summary.txt. Старый sockhttp в "
                ".venv проекту не нужен — убери его.",
                hints=("Сначала включи окружение: source .venv/bin/activate.",
                       "pip install --no-index --find-links ~/wheels datapeek — потом сама "
                       "команда datapeek; лишнее убирает pip uninstall -y.",
                       "source .venv/bin/activate; pip install --no-index --find-links "
                       "~/wheels datapeek; datapeek sales.csv > summary.txt; pip uninstall -y "
                       "sockhttp"),
                solution="source .venv/bin/activate; pip install --no-index --find-links "
                         "~/wheels datapeek; datapeek sales.csv > summary.txt; pip uninstall "
                         "-y sockhttp",
                wrong=("source .venv/bin/activate; pip install datapeek",
                       "pip install --user --no-index --find-links ~/wheels datapeek",
                       "source .venv/bin/activate; pip install --no-index --find-links "
                       "~/wheels datapeek; datapeek sales.csv > summary.txt"),
                alternatives=(".venv/bin/pip install --no-index --find-links ~/wheels datapeek "
                              "— pip окружения и без activate",)),
        Variant("Какие пакеты потянул за собой datapeek? Поставь его в .venv из ~/wheels (что ему "
                "нужно, покажет pip show datapeek — строка Requires) и сдай имя зависимости и её "
                "версию: ans ИМЯ ВЕРСИЯ.",
                hints=("Включи .venv и поставь datapeek, потом pip list: что появилось, кроме "
                       "него самого, pip и setuptools?",
                       "pip show datapeek — строка Requires называет зависимость; версию "
                       "покажет pip list.",
                       "source .venv/bin/activate; pip install --no-index --find-links ~/wheels "
                       "datapeek; pip list, затем ans ИМЯ ВЕРСИЯ"),
                solution="source .venv/bin/activate; pip install --no-index --find-links "
                         "~/wheels datapeek; pip list",
                solution_script="source .venv/bin/activate; pip install --no-index "
                                "--find-links ~/wheels datapeek > /dev/null; pip list "
                                "2>/dev/null | grep '^tabprint ' | tr -s ' '",
                wrong=("source .venv/bin/activate; pip install --no-index --find-links ~/wheels "
                       "datapeek > /dev/null; pip list 2>/dev/null | grep '^datapeek ' | tr -s "
                       "' '",),
                alternatives=("pip show datapeek — Requires: tabprint; версия — pip show "
                              "tabprint",)),
        Variant("Поставь в .venv из ~/wheels пакет tabprint именно версии 1.0.0 — так и пиши: "
                "tabprint==1.0.0 (без == pip берёт новейшую) — и запиши в ver.txt то, что "
                "печатает python3 -c 'import tabprint; print(tabprint.__version__)'.",
                hints=("Без версии pip берёт из папки самую новую.",
                       "Версию задают так: tabprint==1.0.0 — и не забудь включить .venv.",
                       "source .venv/bin/activate; pip install --no-index --find-links ~/wheels "
                       "tabprint==1.0.0; python3 -c 'import tabprint; "
                       "print(tabprint.__version__)' > ver.txt"),
                solution="source .venv/bin/activate; pip install --no-index --find-links "
                         "~/wheels tabprint==1.0.0; python3 -c 'import tabprint; "
                         "print(tabprint.__version__)' > ver.txt",
                wrong=("source .venv/bin/activate; pip install --no-index --find-links ~/wheels "
                       "tabprint; python3 -c 'import tabprint; print(tabprint.__version__)' > "
                       "ver.txt",),
                alternatives=("pip install … 'tabprint<1.1' — тоже 1.0.0",
                              "уже стоит новее? pip uninstall -y tabprint, потом "
                              "tabprint==1.0.0")),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("pip ставит пакет и всё, что тот просит (зависимости), во включённое "
               "окружение. Без сети годится папка с колёсами: --no-index --find-links. Без "
               "== pip берёт самую новую версию.")
    spell = "pip install --no-index --find-links ПАПКА ИМЯ — без сети; pip list; pip show ИМЯ"
    secret_keys = ("want",)
    MSG_NET = ("Сети здесь нет, и не нужна: pip install --no-index --find-links ~/wheels "
               "{name}")
    MSG_USER = ("Пакет ушёл не в .venv, а в домашнюю папку (--user): включи окружение — "
                "source .venv/bin/activate — и поставь заново. Совет pip про PATH здесь не "
                "нужен.")
    MSG_NOT_YET = ("{name} в .venv ещё нет: source .venv/bin/activate, потом pip install "
                   "--no-index --find-links ~/wheels {name}")
    MSG_INACTIVE = ("datapeek стоит в .venv, но команда его не нашла: окружение не включено — "
                    "source .venv/bin/activate")
    MSG_SUMMARY = "В summary.txt не сводка sales.csv: datapeek sales.csv > summary.txt"
    MSG_RUN_DP = "Сводку пишет сам datapeek — запусти его: datapeek sales.csv > summary.txt"
    MSG_NO_VENV = "Окружения .venv нет — набери reset, соберу задачу заново."
    # плана П3.1 (решение 15): pip uninstall -y отрабатывается в варианте 0 — страж его требует
    MSG_DROP = ("Сводка готова. Осталось убрать старый sockhttp из .venv: pip uninstall -y "
                "sockhttp (окружение включено).")
    MSG_DEP_GONE = ("Перестарался: без tabprint datapeek не работает. Верни его на место: "
                    "pip install --no-index --find-links ~/wheels tabprint")
    MSG_FIRST = ("Сначала поставь datapeek в .venv: что он потянул, видно в pip list после "
                 "установки.")
    MSG_SELF = "Это сам datapeek, а спрашивают, что он потянул за собой."
    MSG_REQUIRES = ("Requires называет только имя, а нужны имя и версия: версию покажет pip "
                    "list. Сдай без слова Requires: ans ИМЯ ВЕРСИЯ")
    MSG_BASE = "pip и setuptools есть в любом окружении — их ставит venv, а не datapeek."
    MSG_NEWEST = ("pip взял самую новую. Версию задают так: pip install --no-index "
                  "--find-links ~/wheels tabprint==1.0.0")
    MSG_VER_RUN = ("ver.txt пишет сам python3 из .venv: python3 -c 'import tabprint; "
                   "print(tabprint.__version__)' > ver.txt")
    MSG_VER_PIP = ("tabprint 1.0.0 должен поставить pip: pip install --no-index --find-links "
                   "~/wheels tabprint==1.0.0")
    MSG_VER_EMPTY = ("ver.txt пуст: python3 без окружения tabprint не видит — включи .venv "
                     "(source .venv/bin/activate) и запусти снова.")
    MSG_VER_STALE = "В ver.txt старая версия — перезапиши его после установки 1.0.0."
    MSG_VER = ("В ver.txt не версия tabprint: python3 -c 'import tabprint; "
               "print(tabprint.__version__)' > ver.txt")
    fallback = "Не то. Смотри pip list после установки: что появилось, кроме datapeek?"
    # E24a, I6: одно = в версии (pip сам подсказывает ==)
    MSG_ONE_EQ = ("Версию пишут через два знака: tabprint==1.0.0. Одно = pip не понимает — он "
                  "и сам подсказал: Did you mean ==?")

    def _v(self, state: dict) -> int:
        return variant_index(state.get("_variant", 0), len(self.variants))

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        bare_venv(box, keep=("sockhttp",) if variant == 0 else ())
        wheels_home(box)
        rows = ["city,item,qty"] + [f"{rng.choice(SALES_CITIES)},{rng.choice(SALES_ITEMS)},"
                                    f"{rng.randint(1, 20)}" for _ in range(rng.randint(12, 30))]
        kit.write(box / "sales.csv", "\n".join(rows) + "\n")
        if variant != 0:
            # want — всегда (пусть пустой): задача «найди и назови» скрытая во всех вариантах
            return {"want": ""}
        from termit_app.pylibs import peek
        return {"want": peek.report(box / "sales.csv", "sales.csv")}

    def takes_answer(self, state: dict) -> bool:
        return self._v(state) == 1

    def expected(self, state: dict) -> str:
        return "tabprint 1.1.0"

    def answer_kind(self, state: dict) -> str:
        return "text"

    def matches(self, given: str, ctx) -> bool:
        if self._v(ctx.state) != 1:
            return False
        pk = envkit.venv_pkgs(ctx.box, ".venv") or {}
        if "datapeek" not in pk or "tabprint" not in pk:
            return False
        g = textnorm.clean(given).replace("==", " ")
        return textnorm.same_words(g, f"tabprint {pk['tabprint']}")

    def wrong_message(self, given: str, ctx) -> str:
        words = textnorm.clean(given).replace("==", " ").split()
        if words and envkit.canon(words[0]) == "datapeek":
            return self.MSG_SELF
        if words and envkit.canon(words[0]) in envkit.VENV_BASE:
            return self.MSG_BASE
        if words and words[0].casefold().rstrip(":") == "requires":
            return self.MSG_REQUIRES
        return self.common_mistake(given, ctx) or self.fallback

    def check(self, ctx) -> Verdict:
        v = self._v(ctx.state)
        if v == 1:
            pk = envkit.venv_pkgs(ctx.box, ".venv")
            if ctx.answer is not None and (pk is None or "datapeek" not in pk):
                return Verdict(False, self.MSG_FIRST if pk is not None else self.MSG_NO_VENV)
            return super().check(ctx)
        verdict = self._summary(ctx) if v == 0 else self._version(ctx)
        if verdict.solved or ctx.answer is None:
            return verdict
        return Verdict(False, verdict.message or self.stray_answer)

    def _missing(self, box, jour, pk, name: str, show: Optional[str] = None) -> Optional[str]:
        """Почему name не в .venv — по журналу и пользовательскому site (None — молчим).
        show — как назвать пакет в готовой команде отклика (tabprint==1.0.0 в варианте C)."""
        if pk is None:
            return self.MSG_NO_VENV
        if name in envkit.user_pkgs(box):
            return self.MSG_USER
        tries = [(a, ok) for a, ok in envkit.pip_runs(jour, "install") if _install(a, name)]
        # FINAL fix1: по последней попытке — давний запуск без сети не перекрывает новую причину
        if tries and "--no-index" not in tries[-1][0] and tries[-1][1] is not True:
            return self.MSG_NET.format(name=show or name)
        return self.MSG_NOT_YET.format(name=show or name) if tries else None

    def _summary(self, ctx) -> Verdict:
        box, st = ctx.box, ctx.state
        kind, text = envkit.box_text(box, "summary.txt", envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, "summary.txt")
        if bad:
            return Verdict(False, bad)
        jour = envkit.journal(box)
        pk = envkit.venv_pkgs(box, ".venv")
        if pk is None or "datapeek" not in pk:
            why = self._missing(box, jour, pk, "datapeek")
            if why is None and text is not None:
                why = self.MSG_NOT_YET.format(name="datapeek")
            return Verdict(False, why)
        if text is None:
            return Verdict(False)
        if not text.strip():
            return Verdict(False, self.MSG_INACTIVE)
        want = st.get("want", "")
        got, exp = text.rstrip("\n").split("\n"), want.rstrip("\n").split("\n")
        tail = exp[0].split(":", 1)[1] if ":" in exp[0] else exp[0]
        if got[1:] != exp[1:] or not got[0].endswith(":" + tail):
            return Verdict(False, self.MSG_SUMMARY)
        last = envkit.last_run(jour, "datapeek", mention="summary.txt")
        if last is None or last[1] is False:
            return Verdict(False, self.MSG_RUN_DP)
        if "tabprint" not in pk:
            return Verdict(False, self.MSG_DEP_GONE)
        if "sockhttp" in pk:
            return Verdict(False, self.MSG_DROP)
        return Verdict(True)

    def _version(self, ctx) -> Verdict:
        box = ctx.box
        kind, text = envkit.box_text(box, "ver.txt", envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, "ver.txt")
        if bad:
            return Verdict(False, bad)
        jour = envkit.journal(box)
        pk = envkit.venv_pkgs(box, ".venv")
        if pk is not None and pk.get("tabprint", "1.0.0") != "1.0.0":
            return Verdict(False, self.MSG_NEWEST)
        if pk is None or "tabprint" not in pk:
            # FINAL fix1, M3: только последняя попытка поставить tabprint
            tries = [(a, ok) for a, ok in envkit.pip_runs(jour, "install")
                     if _install(a, "tabprint") or _one_eq(a)]
            if tries and tries[-1][1] is not True and _one_eq(tries[-1][0]):
                return Verdict(False, self.MSG_ONE_EQ)
            why = self._missing(box, jour, pk, "tabprint", "tabprint==1.0.0")
            if why is None and text is not None:
                why = self.MSG_NOT_YET.format(name="tabprint==1.0.0")
            return Verdict(False, why)
        if text is None:
            return Verdict(False)
        line = envkit.first_line(text)
        if not line:
            return Verdict(False, self.MSG_VER_EMPTY)
        if line != "1.0.0":
            return Verdict(False, self.MSG_VER_STALE if line == "1.1.0" else self.MSG_VER)
        # M1 ревью P4: tabprint поставил pip (INSTALLER, RECORD), а ver.txt написал python3 -c
        # с import tabprint (или pip show/list) из .venv — той же строкой, последней записью
        if not envkit.pip_installed(box, ".venv", "tabprint", "1.0.0"):
            return Verdict(False, self.MSG_VER_PIP)
        if not envkit.written_by(jour, "ver.txt", _reports_tabprint):
            return Verdict(False, self.MSG_VER_RUN)
        return Verdict(True)


# --- E17 ------------------------------------------------------------------------------------

LIGHT_VERSIONS = {"datapeek": "0.2.0", "sockhttp": "1.0.0", "tabprint": "1.0.0"}
# наборы пакетов по зерну: tabprint есть всегда (datapeek без него не живёт) — и всегда 1.0.0,
# не новейшая: «поставь без версии» гарантированно даёт не то (ловушка — постройкой)
KEEP_SETS = (("tabprint",), ("sockhttp", "tabprint"), ("datapeek", "tabprint"),
             ("datapeek", "sockhttp", "tabprint"))
REQ = "requirements.txt"


def _pins_text(names, rng, bare=()) -> str:
    lines = [n if n in bare else f"{n}=={LIGHT_VERSIONS[n]}" for n in names]
    rng.shuffle(lines)
    return "\n".join(lines) + "\n"


def _by_file(jour, venv: Optional[str] = ".venv2", offline: bool = True) -> bool:
    """В журнале — не упавший pip install -r requirements.txt (именно этот файл) из venv
    (None — из любого окружения). M1 ревью P4. offline=False — наоборот, такой запуск без
    --no-index, не удавшийся (сети нет; E24a, I5)."""
    last = None
    for _, ok, seg, active in envkit.walk_venv(jour):
        a = envkit.pip_args(seg)
        if not (a and a[0] == "install" and envkit.pip_r_file(a[1:], REQ)
                and (venv is None or envkit.from_venv(seg, active, venv))):
            continue
        if offline and ok is not False:
            return True
        last = (a, ok)
    # FINAL fix1: «сети нет» — только если без --no-index была ПОСЛЕДНЯЯ такая попытка
    return (not offline and last is not None and last[1] is not True
            and "--no-index" not in last[0])


def _freeze_from_venv(seg: str, active) -> bool:
    a = envkit.pip_args(seg)
    return bool(a) and a[0] == "freeze" and envkit.from_venv(seg, active, ".venv")


class PipFreeze(Task):
    """pip freeze > requirements.txt, pip install -r, пины ==. Что стоит в .venv и .venv2 —
    по именам dist-info; requirements.txt — построчный разбор (envkit.parse_requirements)."""
    id = "pip_freeze"
    track = "env"
    title = "Список для другой машины"
    par = 90
    pinned_python = True
    stock = "wheels"
    scroll = ("pip freeze > requirements.txt — точный список пакетов venv: ИМЯ==ВЕРСИЯ.\n"
              "pip install -r requirements.txt — поставить всё по списку (r — requirement, в "
              "новый venv).\n"
              "Без == pip возьмёт самую новую. pip list — таблица для глаз, -r её не поймёт.")
    variants = (
        Variant("В .venv стоят пакеты проекта. Сохрани их точный список в requirements.txt.",
                hints=("Включи .venv: список берётся из включённого окружения.",
                       "pip freeze печатает строки ИМЯ==ВЕРСИЯ — запиши их в файл через >.",
                       "source .venv/bin/activate; pip freeze > requirements.txt"),
                solution="source .venv/bin/activate; pip freeze > requirements.txt",
                wrong=("source .venv/bin/activate; pip list > requirements.txt",
                       "pip freeze > requirements.txt"),
                alternatives=(".venv/bin/pip freeze > requirements.txt — pip окружения и без "
                              "activate",)),
        Variant("Подними рядом новое окружение .venv2 и поставь в него ровно то, что записано в "
                "requirements.txt (из ~/wheels, без сети).",
                hints=("Новое окружение — python3 -m venv .venv2; потом включи его.",
                       "pip install -r ставит всё по списку; без сети — --no-index --find-links "
                       "~/wheels.",
                       "python3 -m venv .venv2; source .venv2/bin/activate; pip install "
                       "--no-index --find-links ~/wheels -r requirements.txt"),
                solution="python3 -m venv .venv2; source .venv2/bin/activate; pip install "
                         "--no-index --find-links ~/wheels -r requirements.txt",
                wrong=("python3 -m venv .venv2; source .venv2/bin/activate; pip install "
                       "--no-index --find-links ~/wheels datapeek sockhttp tabprint",),
                alternatives=(".venv2/bin/pip install --no-index --find-links ~/wheels -r "
                              "requirements.txt — без activate",)),
        Variant("В requirements.txt tabprint записан без версии — на новой машине так встала "
                "1.1.0, и отчёт съехал. Закрепи в файле версию, что стоит в .venv, и подними по "
                "нему новое окружение .venv2.",
                hints=("Какая tabprint стоит в .venv, скажет pip freeze — включи его.",
                       "Перепиши файл из .venv: pip freeze > requirements.txt; потом .venv2 и "
                       "pip install -r.",
                       "source .venv/bin/activate; pip freeze > requirements.txt; deactivate; "
                       "python3 -m venv .venv2; source .venv2/bin/activate; pip install "
                       "--no-index --find-links ~/wheels -r requirements.txt"),
                solution="source .venv/bin/activate; pip freeze > requirements.txt; deactivate; "
                         "python3 -m venv .venv2; source .venv2/bin/activate; pip install "
                         "--no-index --find-links ~/wheels -r requirements.txt",
                wrong=("python3 -m venv .venv2; source .venv2/bin/activate; pip install "
                       "--no-index --find-links ~/wheels -r requirements.txt",),
                alternatives=("nano requirements.txt — дописать к tabprint ==1.0.0 руками",)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("pip freeze — точный список «имя==версия», по нему pip install -r соберёт то же "
               "окружение где угодно. Строка без == — не список, а пожелание: pip возьмёт "
               "новейшую.")
    spell = "pip freeze > requirements.txt; pip install -r requirements.txt"
    MSG_LIST = ("Это таблица pip list — она для глаз, pip install -r её не поймёт: pip freeze > "
                "requirements.txt")
    MSG_FORMAT = "В requirements.txt нужны строки ИМЯ==ВЕРСИЯ, по одной — их печатает pip freeze."
    MSG_NOPIN = ("Без версии pip возьмёт новейшую: в файле нужны строки ИМЯ==ВЕРСИЯ — как у pip "
                 "freeze.")
    MSG_OUTSIDE = ("В списке не пакеты .venv: pip freeze без окружения смотрит базовый Python. "
                   "Включи .venv: source .venv/bin/activate")
    MSG_BY_HAND = ("Список пишет сам pip из .venv — запусти его: source .venv/bin/activate; "
                   "pip freeze > requirements.txt")
    MSG_VENV_CHANGED = ("В .venv теперь не то, что было: ты в него ставил или убирал. reset "
                        "вернёт как было.")
    MSG_VER = "Версия {name} в списке не та, что стоит в .venv: пиши то, что печатает pip freeze."
    MSG_EXTRA = "В списке лишнее: {names} — в .venv этого нет."
    MSG_PART = "В списке {k} из {m}: pip freeze печатает всё, что стоит в .venv."
    MSG_NO_VENV2 = "Окружения .venv2 ещё нет: python3 -m venv .venv2, потом включи его."
    MSG_EMPTY2 = ("В .venv2 пока пусто: включи его (source .venv2/bin/activate) и pip install "
                  "--no-index --find-links ~/wheels -r requirements.txt")
    MSG_OTHER_ENV = ("pip install -r был, а в .venv2 пусто — ставил в другое окружение. Включи "
                     ".venv2: source .venv2/bin/activate")
    MSG_NEWEST = ("В .venv2 tabprint {got}, а в файле {want}: ставь по файлу — pip install -r "
                  "requirements.txt, там версия закреплена.")
    MSG_EXTRA2 = "В .venv2 лишнее: {names} — ставь ровно то, что в файле."
    MSG_PART2 = "В .venv2 стоит {k} из {m} — не всё из requirements.txt."
    MSG_BY_ONE = ("Пакеты верные, но ставь по файлу: pip install --no-index --find-links "
                  "~/wheels -r requirements.txt")
    MSG_PIN_WRONG = ("Версия tabprint в файле не та, что стоит в .venv: посмотри pip freeze "
                     "там.")
    MSG_CHANGED = "Остальные строки менять не нужно — закрепи только tabprint."
    # E24a: I5 — pip без флагов «без сети»; мелкое — freeze снят с пустого окружения
    MSG_NET2 = ("Сети здесь нет, и не нужна: pip install --no-index --find-links ~/wheels -r "
                "requirements.txt")
    MSG_EMPTY_FREEZE = ("Файл пуст: pip freeze снят с пустого окружения. Включи .venv (source "
                        ".venv/bin/activate) и запиши заново.")
    MSG_STALE = ("Файл исправлен, а .venv2 собран по старому: поставь в него заново — pip "
                 "install -r requirements.txt (или пересоздай .venv2).")

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        box = Path(box)
        keep, req = rng.choice(KEEP_SETS), rng.choice(KEEP_SETS)
        wheels_home(box)
        if variant == 1:
            bare_venv(box, keep=LIGHT_NAMES)
            kit.write(box / REQ, _pins_text(req, rng))
            return {"want": {n: LIGHT_VERSIONS[n] for n in req}}
        bare_venv(box, keep=keep)
        want = {n: LIGHT_VERSIONS[n] for n in keep}
        if variant == 2:
            kit.write(box / REQ, _pins_text(keep, rng, bare=("tabprint",)))
        return {"want": want}

    def check(self, ctx) -> Verdict:
        st, box = ctx.state, ctx.box
        v = variant_index(st.get("_variant", 0), 3)
        kind, text = envkit.box_text(box, REQ, envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, REQ)
        if bad:
            return Verdict(False, bad)
        jour = envkit.journal(box)
        if v == 1:
            return self._venv2(box, jour, st["want"])
        if text is None:
            return Verdict(False)
        r = envkit.parse_requirements(text)
        if r["table"]:
            return Verdict(False, self.MSG_LIST)
        if r["bad"]:
            return Verdict(False, self.MSG_FORMAT)
        if r["bare"]:
            return Verdict(False, self.MSG_NOPIN)
        if not r["pins"]:
            return Verdict(False, self.MSG_EMPTY_FREEZE)
        want, got = st["want"], r["pins"]
        if v == 2:
            if got.get("tabprint") != want["tabprint"]:
                return Verdict(False, self.MSG_PIN_WRONG)
            if got != want:
                return Verdict(False, self.MSG_CHANGED)
            return self._venv2(box, jour, want, fixed=True)
        # M3 ревью P4: сверка с тем, что стоит в .venv сейчас
        if envkit.venv_pkgs(box, ".venv") != want:
            return Verdict(False, self.MSG_VENV_CHANGED)
        if got == want:
            # M1 ревью P4: файл написал pip freeze из .venv — последней записью
            if not envkit.written_by(jour, REQ, _freeze_from_venv):
                return Verdict(False, self.MSG_BY_HAND)
            return Verdict(True)
        if not set(got) & set(want):
            return Verdict(False, self.MSG_OUTSIDE)
        for name in sorted(got):
            if name in want and got[name] != want[name]:
                return Verdict(False, self.MSG_VER.format(name=name))
        extra = sorted(set(got) - set(want))
        if extra:
            return Verdict(False, self.MSG_EXTRA.format(names=", ".join(extra)))
        return Verdict(False, self.MSG_PART.format(k=len(got), m=len(want)))

    def _venv2(self, box, jour, want: Dict[str, str], fixed: bool = False) -> Verdict:
        got = envkit.venv_pkgs(box, ".venv2")
        if got is None:
            if fixed or _by_file(jour, None):
                return Verdict(False, self.MSG_NO_VENV2)
            return Verdict(False)
        if got == want:
            return Verdict(True) if _by_file(jour) else Verdict(False, self.MSG_BY_ONE)
        if not got:
            if _by_file(jour, ".venv2", offline=False):
                return Verdict(False, self.MSG_NET2)
            return Verdict(False, self.MSG_OTHER_ENV if _by_file(jour, None)
                           else self.MSG_EMPTY2)
        if "tabprint" in got and got["tabprint"] != want.get("tabprint"):
            if fixed and got["tabprint"] == "1.1.0":
                return Verdict(False, self.MSG_STALE)
            return Verdict(False, self.MSG_NEWEST.format(got=got["tabprint"],
                                                         want=want.get("tabprint", "—")))
        extra = sorted(n for n in got if n not in want or got[n] != want[n])
        if extra:
            return Verdict(False, self.MSG_EXTRA2.format(names=", ".join(extra)))
        return Verdict(False, self.MSG_PART2.format(k=len(got), m=len(want)))


# --- E18: страж -----------------------------------------------------------------------------

APP = "app"
SOURCE_TXT = "report/source.txt"
RC = ".termit/home/.zshrc"
APP_REQ = f"{APP}/{REQ}"
APP_VENV = f"{APP}/.venv"
_PLACEHOLDERS = ("ИМЯ", "<ИМЯ>", "<имя>", "NAME")

# части пути решения — ими собраны эталон и неверные решения (каждое — эталон с одной ошибкой)
_B_FIX = "print -r -- '{fixed}' > app/config.json; "
_B_SRC = ("mkdir -p report quarantine; jq -r '.sources[0].path' app/config.json > "
          "report/source.txt; ")
_B_RC = ("grep -v -e sync-agent -e .cache/bin ~/.zshrc > rc.new; mv rc.new ~/.zshrc; "
         "rm ~/.cache/bin/{cmd}; ")
_B_QUAR = "mv {src} quarantine/; chmod -x quarantine/{name}; "
_B_ENV = "chmod 600 app/.env; print -r -- .env >> app/.gitignore; "
_B_PIP = ("source app/.venv/bin/activate; pip uninstall -y {extra}; pip freeze > "
          "app/requirements.txt")
_B_SHOWN = ("which -a {cmd}; python3 -m json.tool app/config.json; nano app/config.json — поправь строку из "
            "ошибки; mkdir -p report quarantine; jq -r '.sources[0].path' app/config.json > "
            "report/source.txt; nano ~/.zshrc — убери строки # sync-agent и ~/.cache/bin; "
            "rm ~/.cache/bin/{cmd}; mv {src} quarantine/; chmod -x quarantine/{name}; chmod 600 "
            "app/.env; print -r -- .env >> app/.gitignore; source app/.venv/bin/activate; pip "
            "uninstall -y {extra}; pip freeze > app/requirements.txt")


def _freeze_app(seg: str, active) -> bool:
    """pip freeze из app/.venv (путём …/.venv/bin/pip или при включённом .venv)."""
    a = envkit.pip_args(seg)
    return bool(a) and a[0] == "freeze" and envkit.from_venv(seg, active, ".venv")


class BossEnv(Task):
    """Страж трека: проект после неосторожного запуска найденного скрипта. Четыре шага —
    каждый приём уже отработан в варианте 0 задач трека (П3.1): json.tool и jq -r — E11 и
    «Данные», ~/.zshrc и PATH — E8, карантин mv + chmod -x — E14, chmod 600 и .gitignore — E7,
    pip uninstall -y — E16, pip freeze — E17. Варианты: подменена ls, grep или python3.
    Проверка — по состоянию файлов у родителя (read_in_box, листинг без ссылок): «новая
    оболочка» не запускается никогда, код песочницы не исполняется. requirements.txt засчитан,
    только если его последним писал pip freeze из app/.venv (журнал)."""
    id = "boss_env"
    track = "env"
    title = "Чужой скрипт в проекте"
    boss = True
    par = 540
    pinned_python = True
    stock = "light"
    uses_av = True
    # у судьи — всё, чего игрок заранее не знает (ревью P5, M1): исправленный конфиг (как в
    # E11), путь и имя источника, лишний пакет, прочие источники, отпечатки, пакеты проекта.
    # Открыты только cmd (шаги схватки) и строки игрока own (они и так в его ~/.zshrc)
    secret_keys = ("fixed", "src", "name", "extra", "others", "src_sha", "broken_sha", "want")
    scroll = ("Ничего не запускай — читай. python3 -m json.tool f.json — где сломан JSON;\n"
              "jq -r '.a[0].b' f.json — значение без кавычек; which -a ИМЯ — кто первый.\n"
              "Чужие строки ~/.zshrc убирают в nano; находку — mv в quarantine/, chmod -x.\n"
              "chmod 600 .env и строка .env в .gitignore; лишний пакет — pip uninstall -y.\n"
              "Список пакетов — pip freeze > requirements.txt из включённого venv.")
    steps = ("Источник найден: app/config.json снова читается, в report/source.txt — путь из "
             "его .sources[0].path",
             "Подмена снята: в ~/.cache/bin нет поддельной команды, в ~/.zshrc нет чужих строк, "
             "свои — целы",
             "Источник — в quarantine/ без права запуска, в downloads/ его больше нет",
             "Проект закрыт: app/.env — права 600 и в app/.gitignore, лишнего пакета в app/.venv "
             "нет, app/requirements.txt — по pip freeze")
    STEP_TEMPLATES = (steps[0],
                      "Подмена снята: в ~/.cache/bin нет поддельной {cmd}, в ~/.zshrc нет чужих "
                      "строк, свои — целы",
                      steps[2], steps[3])
    _H1 = ("Не запускай найденное — читай. python3 -m json.tool app/config.json назовёт строку "
           "ошибки; источник — в .sources[0].path: jq -r.")
    _H2 = ("which -a {cmd} покажет подмену в ~/.cache/bin, а ~/.zshrc — строку, что ставит её "
           "первой. Источник — в quarantine/ без права запуска; .env — chmod 600 и в .gitignore.")
    _H3 = ("Лишний пакет назван в самом источнике: grep -n pip в нём. Потом source "
           "app/.venv/bin/activate; pip uninstall -y ИМЯ; pip freeze > app/requirements.txt")
    _REF = _B_FIX + _B_SRC + _B_RC + _B_QUAR + _B_ENV + _B_PIP
    _ALT_SED = ("sed -i '' -e '/sync-agent/d' -e '/cache.bin/d' ~/.zshrc — чужие строки без "
                "редактора")
    variants = (
        Variant("Кто-то запустил скрипт из downloads/, не читая, — и проект app/ заболел: "
                "app/config.json не читается, в PATH подсунута поддельная ls, app/.env открыт "
                "всем, в app/.venv завёлся лишний пакет. Найди источник и вылечи всё по шагам "
                "ниже — ничего не запуская вслепую.",
                hints=(_H1, _H2, _H3), solution=_B_SHOWN, solution_script=_REF,
                wrong=(_B_FIX + _B_SRC + "rm ~/.zshrc ~/.cache/bin/{cmd}; " + _B_QUAR + _B_ENV
                       + _B_PIP,),
                alternatives=(_ALT_SED,
                              "clamscan -r -i downloads — база ~/av/main.hsb источник знает")),
        Variant("После запуска непрочитанного скрипта из downloads/ grep в этой оболочке — уже "
                "не тот grep, app/config.json сломан, app/.env читают все, а в app/.venv "
                "лишний пакет. Разберись, откуда беда, и вылечи проект по шагам ниже.",
                hints=(_H1, _H2, _H3), solution=_B_SHOWN, solution_script=_REF,
                wrong=(_B_FIX + _B_SRC + _B_RC + "rm {src}; " + _B_ENV + _B_PIP,),
                alternatives=(_ALT_SED,
                              ".venv/bin/pip uninstall -y ИМЯ из папки app — pip окружения и без "
                              "activate")),
        Variant("Скрипт из downloads/ запустили, не читая. Теперь первым в PATH стоит "
                "поддельный python3, app/config.json не читается, app/.env открыт всем, в "
                "app/.venv чужой пакет. Найди источник, сними подмену и вылечи проект по шагам "
                "ниже.",
                hints=(_H1, _H2, _H3), solution=_B_SHOWN, solution_script=_REF,
                wrong=(_B_FIX + _B_SRC + _B_RC + _B_QUAR + _B_ENV + "source "
                       "app/.venv/bin/activate; pip freeze > app/requirements.txt; pip "
                       "uninstall -y {extra}",),
                alternatives=("which -a python3 — первой стоит подмена из ~/.cache/bin, за ней "
                              "настоящий",
                              _ALT_SED)),
    )
    hints = variants[0].hints
    solution = variants[0].solution
    explain = ("Чужой скрипт оставляет следы в четырёх местах: в конфиге, в PATH через "
               "~/.zshrc, в правах файлов и в окружении Python. Лечат по порядку и ничего не "
               "запуская: читают, находят источник, убирают его в карантин, закрывают дыры.")
    spell = ("json.tool, jq -r, which -a, nano ~/.zshrc, mv в quarantine/ + chmod -x, "
             "chmod 600, pip uninstall -y, pip freeze — по порядку")

    MSG_CONF_GONE = "app/config.json нет на месте. Набери reset — он вернётся, сломанный, как был."
    MSG_CONF_CLOBBER = ("app/config.json пуст: > стёр его раньше, чем его прочли. Набери reset — "
                        "он вернётся.")
    MSG_CONF_BROKEN = ("app/config.json всё ещё не JSON: python3 -m json.tool app/config.json "
                       "скажет line и column ошибки.")
    MSG_CONF_DEEP = "app/config.json вложен слишком глубоко — это уже не конфиг. Набери reset."
    MSG_CONF_OTHER = ("config.json починен, но значение не то — сравни с исходным: {path} должен "
                      "остаться как был. Чинят только ошибку синтаксиса.")
    MSG_SRC_QUOTED = ("В report/source.txt путь в кавычках: jq без -r печатает строку JSON. "
                      "Добавь -r.")
    MSG_SRC_OTHER = ("Это другой скрипт из .sources. Источник — первый в списке: "
                     ".sources[0].path.")
    MSG_SRC_WRONG = ("В report/source.txt нужен путь из .sources[0].path починенного "
                     "app/config.json — одной строкой, как в файле.")
    MSG_SRC_UNFIXED = ("Путь верный, а app/config.json всё ещё сломан: почини его — python3 -m "
                       "json.tool скажет line и column.")
    MSG_SRC_DIR = "report/source.txt — в папке report/ корня (рядом с app/ и downloads/)."
    MSG_RC_GONE = ("Ты удалил весь ~/.zshrc — свои строки тоже. Убирай только чужие: reset "
                   "вернёт как было.")
    MSG_RC_OWN = ("Из ~/.zshrc пропала и твоя строка: {line}. Убирай только чужие — reset "
                  "вернёт как было.")
    MSG_RC_LEFT = ("Подмену убрал, а чужая строка в ~/.zshrc осталась: в новом окне PATH снова "
                   "начнётся с ~/.cache/bin. Убери её (nano ~/.zshrc).")
    MSG_RERUN = ("Ты запустил источник ещё раз: в ~/.zshrc новая чужая строка. Найденное не "
                 "запускают — читают (head, grep -n).")
    MSG_FAKE_LEFT = ("Строку автозапуска убрал, а сама подмена ~/.cache/bin/{cmd} на месте — в "
                     "этой оболочке она всё ещё первая в PATH (which -a {cmd}). Убери файл.")
    MSG_SRC_RM = ("Источника нет ни в downloads/, ни в quarantine/ в прежнем виде — удалён или "
                  "изменён, изучать его нечем. Набери reset и перенеси как есть: mv в "
                  "quarantine/.")
    MSG_QUAR_EDITED = ("Источник в quarantine/ изменён — улику не правят, в карантине она лежит "
                       "как была. Набери reset и перенеси заново: mv, потом chmod -x.")
    MSG_SRC_EDITED = ("Источник в downloads/ изменён — улику не правят. Набери reset — он "
                      "вернётся как был.")
    MSG_SRC_COPY = ("В quarantine/ — копия, а сам источник остался в downloads/ и запускается. "
                    "Карантин — это mv, а не cp: убери лишнюю копию (rm) или набери reset.")
    MSG_SRC_X = "В карантине источник всё ещё запускается: chmod -x quarantine/{name}"
    MSG_VENV_GONE = "app/.venv нет — набери reset, соберу проект заново."
    MSG_VENV_NEED = ("Из app/.venv пропал пакет проекта {name}: лишний — только тот, что ставил "
                     "источник (grep -n pip в нём). reset вернёт как было.")
    MSG_EXTRA_RM = ("Лишний пакет убран не до конца: в site-packages остались его хвосты. "
                    "Пакеты убирают pip uninstall -y, а не rm. Набери reset и убери заново.")
    MSG_REQ_DIR = "requirements.txt нужен в app/, рядом с .venv: pip freeze > app/requirements.txt"
    MSG_REQ_TABLE = ("app/requirements.txt — таблица pip list, pip install -r её не поймёт: pip "
                     "freeze > app/requirements.txt")
    MSG_REQ_FORMAT = ("В app/requirements.txt нужны строки ИМЯ==ВЕРСИЯ, по одной — их печатает "
                      "pip freeze.")
    MSG_REQ_EXTRA = ("В app/requirements.txt попал лишний пакет: сначала pip uninstall -y, потом "
                     "pip freeze заново.")
    MSG_REQ_STALE = ("app/requirements.txt не совпадает с тем, что стоит в app/.venv: запиши "
                     "заново — pip freeze > app/requirements.txt (app/.venv включён).")
    MSG_REQ_HAND = ("Список пишет сам pip из app/.venv: source app/.venv/bin/activate; pip "
                    "freeze > app/requirements.txt")
    MSG_PLACEHOLDER = ("ИМЯ в подсказке — место для имени пакета: его называет сам источник "
                       "(grep -n pip в нём).")
    MSG_PART = "В app/ сделано {k} из 4: осталось — {rest}."
    # E24a (аудит, мелкие): pip вне окружения; jq по ещё сломанному конфигу
    MSG_UNINST_OUT = ("{extra} всё ещё в app/.venv: pip вне окружения его не видит (Skipping… "
                      "not installed). Включи окружение — source app/.venv/bin/activate — и "
                      "pip uninstall -y снова.")
    MSG_JQ_BROKEN = ("report/source.txt пуст: jq упал — app/config.json ещё сломан (ошибка "
                     "выше). Сначала почини: python3 -m json.tool app/config.json скажет где.")
    MSG_IGN_CLOBBER = ("> переписал app/.gitignore целиком — прежние строки ({line} и другие) "
                       "пропали. Дописывают >>. reset вернёт файл.")
    PARTS = (".env закрыть (chmod 600)", ".env в app/.gitignore", "лишний пакет из app/.venv",
             "app/requirements.txt по pip freeze")

    def steps_for(self, state):
        try:
            return [s.format(**state) for s in self.STEP_TEMPLATES]
        except (KeyError, IndexError):
            return list(self.steps)

    def env_for(self, state: dict) -> Dict[str, str]:
        # «новое окно» после заразы: её строка в ~/.zshrc уже сработала — ~/.cache/bin первым
        return {"PATH": "$HOME/.cache/bin:$PATH"}

    def setup_variant(self, box: Path, rng, variant: int) -> dict:
        from termit_app.pylibs import wheelmake
        box = Path(box)
        d = envkit.boss_env(rng, variant)
        for rel, (text, mode) in d["files"].items():
            os.chmod(kit.write(box / rel, text), mode)
        kit.write(box / APP / "config.json", d["broken"])
        host, user = f"db-{kit.latin(rng)}.lan", kit.latin(rng)
        pw = "demo-" + "".join(rng.choice(_PW_CHARS) for _ in range(8))
        os.chmod(kit.write(box / APP / ".env", f"DB_HOST={host}\nDB_USER={user}\nDB_PASS={pw}\n"),
                 0o644)
        ign = rng.sample(GITIGNORE_LINES, rng.randint(3, 5))
        kit.write(box / APP / ".gitignore", "\n".join(ign) + "\n")
        keep = rng.choice(KEEP_SETS)
        bare_venv(box, APP_VENV, keep=keep)
        kit.venv_put(box / APP_VENV,
                     wheelmake.wheel_files(wheelmake.stub(d["extra"], envkit.EXTRA_VERSION)))
        home = kit.home(box)
        kit.write(box / RC, d["rc"])          # дом песочницы (RC), не настоящий
        os.chmod(kit.write(home / envkit.FAKE_DIR / d["cmd"], d["fake"]), 0o755)
        kit.write(home / ".cache" / ".sync", "")
        kit.write(home / "av" / "main.hsb", d["main_hsb"])
        kit.write(home / "av" / "local.hsb", envkit.LOCAL_HSB)
        return {"cmd": d["cmd"], "extra": d["extra"], "src": d["src"],
                "name": d["src"].rsplit("/", 1)[1], "src_sha": d["src_sha"],
                "others": d["others"], "own": d["own"], "fixed": d["fixed"],
                "broken_sha": kit.sha(box / APP / "config.json"),
                "want": {n: LIGHT_VERSIONS[n] for n in keep}, "ign": ign}

    # --- шаги: (готово, отклик или None) ---------------------------------------------------

    def _step_source(self, ctx):
        import hashlib
        import json
        st, box = ctx.state, ctx.box
        rel = f"{APP}/config.json"
        kind, data = envkit.box_file(box, rel, envkit.TEXT_CAP)
        if kind == "missing":
            return False, self.MSG_CONF_GONE
        bad = envkit.file_problem(kind, rel)
        if bad:
            return False, bad
        fixed = False
        if hashlib.sha1(data).hexdigest() != st["broken_sha"]:
            jk, doc = envkit.load_json(data.decode("utf-8", errors="replace"))
            if jk == "empty":
                return False, self.MSG_CONF_CLOBBER
            if jk == "deep":
                return False, self.MSG_CONF_DEEP
            if jk == "broken":
                return False, self.MSG_CONF_BROKEN
            diff = _first_diff(doc, json.loads(st["fixed"]))
            if diff is not None:
                return False, self.MSG_CONF_OTHER.format(path=diff.lstrip(".") or "весь файл")
            fixed = True
        kind, text = envkit.box_text(box, SOURCE_TXT, envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, SOURCE_TXT)
        if bad:
            return False, bad
        if text is None:
            k2, _ = envkit.box_file(box, "source.txt", envkit.TEXT_CAP)
            return False, self.MSG_SRC_DIR if k2 == "ok" else None
        got = envkit.first_line(text)
        if not got:
            return False, self.MSG_SRC_WRONG if fixed else self.MSG_JQ_BROKEN
        if self._same_path(got.strip('"'), st["src"]) and got != got.strip('"'):
            return False, self.MSG_SRC_QUOTED
        if any(self._same_path(got.strip('"'), o) for o in st["others"]):
            return False, self.MSG_SRC_OTHER
        if not self._same_path(got, st["src"]):
            return False, self.MSG_SRC_WRONG
        return (True, None) if fixed else (False, self.MSG_SRC_UNFIXED)

    @staticmethod
    def _same_path(got: str, want: str) -> bool:
        """downloads/x.sh, ./downloads/x.sh или полный путь песочницы …/downloads/x.sh."""
        got = got.strip()
        while got.startswith("./"):
            got = got[2:]
        return got == want or (got.startswith("/") and got.endswith("/" + want))

    def _step_rc(self, ctx):
        st, box = ctx.state, ctx.box
        kind, text = envkit.box_text(box, RC, envkit.TEXT_CAP)
        if kind == "missing":
            return False, self.MSG_RC_GONE
        bad = envkit.file_problem(kind, "~/.zshrc")
        if bad:
            return False, bad
        lines = [x.strip() for x in text.splitlines()]
        alien = any(envkit.infected_line(x) for x in lines)
        lost = [x for x in st["own"] if x.strip() and x.strip() not in lines]
        fake_rel = f".termit/home/{envkit.FAKE_DIR}/{st['cmd']}"
        mode = envkit.mode_of(box, fake_rel)
        fake = os.path.islink(box / fake_rel) or (mode is not None and bool(mode & 0o111))
        if lost:
            return False, (self.MSG_RC_GONE if len(lost) == len(st["own"]) or not text.strip()
                           else self.MSG_RC_OWN.format(line=lost[0]))
        if sum(x == envkit.SYNC_MARK for x in lines) > 1 or (
                envkit.SYNC_MARK in lines and self._ran_source(ctx)):
            return False, self.MSG_RERUN
        if not alien and fake:
            return False, self.MSG_FAKE_LEFT.format(**st)
        if alien and not fake:
            return False, self.MSG_RC_LEFT
        return not alien and not fake, None

    @staticmethod
    def _ran_source(ctx) -> bool:
        """Источник запускали уже в игре (./…, sh …, source …): его метка в ~/.zshrc — новая,
        даже если прежнюю игрок убрал (E24a, мелкое: MSG_RERUN, а не «чужая строка осталась»)."""
        name = ctx.state.get("name") or ""
        if not name:
            return False
        for line, _ in envkit.journal(ctx.box):
            if name not in line:
                continue
            for seg in envkit.segments(line):
                _, cmd, args = envkit.lead(seg)
                if cmd is None:
                    continue
                if envkit.runs(seg, name, by_name=False) or (
                        cmd.rsplit("/", 1)[-1] in ("sh", "bash", "zsh", "source", ".")
                        and args and args[0].rsplit("/", 1)[-1] == name):
                    return True
        return False

    def _step_quarantine(self, ctx):
        import hashlib
        st, box = ctx.state, ctx.box
        found, bad = walk_box(box, QUARANTINE)
        if bad:
            return False, bad
        quar = {hashlib.sha256(data).hexdigest(): (rel, mode) for rel, data, mode in found}
        kind, data = envkit.box_file(box, st["src"])
        here = kind == "ok" and hashlib.sha256(data).hexdigest() == st["src_sha"]
        if kind not in ("ok", "missing"):
            return False, envkit.file_problem(kind, st["src"])
        if st["src_sha"] in quar:
            if here:
                return False, self.MSG_SRC_COPY
            rel, mode = quar[st["src_sha"]]
            if mode & 0o111:
                return False, self.MSG_SRC_X.format(name=rel.split("/", 1)[1])
            return kind == "missing", None
        if kind == "missing":
            # M5 ревью P5: перенесён под тем же именем и изменён — честно «изменён»
            if any(rel.rsplit("/", 1)[-1] == st["name"] for rel, _, _ in found):
                return False, self.MSG_QUAR_EDITED
            return False, self.MSG_SRC_RM
        return False, None if here else self.MSG_SRC_EDITED

    def _step_project(self, ctx):
        """(готово, отклик, сколько из 4 частей сделано)."""
        st, box = ctx.state, ctx.box
        mode = envkit.mode_of(box, f"{APP}/.env")
        env_ok = mode is not None and not mode & 0o077 and bool(mode & 0o400)
        kind, ign = envkit.box_text(box, f"{APP}/.gitignore", envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, "app/.gitignore")
        if bad:
            return False, bad, 0
        ign_ok = envkit.ignores_env(ign)
        lost = lost_lines(ign, st.get("ign", ()))
        if lost:
            return False, self.MSG_IGN_CLOBBER.format(line=lost[0]), 0
        pk = envkit.venv_pkgs(box, APP_VENV)
        if pk is None:
            return False, self.MSG_VENV_GONE, 0
        want = st["want"]
        for name in sorted(want):
            if pk.get(name) != want[name]:
                return False, self.MSG_VENV_NEED.format(name=name), 0
        # M3 ревью P5: «убран» — ушли и dist-info, и сам модуль; половина — это rm руками
        site = envkit.venv_site(box, APP_VENV)
        module = st["extra"] in (envkit.dirs_in_box(box, site) or ()) if site else False
        listed = envkit.canon(st["extra"]) in pk
        if listed != module:
            return False, self.MSG_EXTRA_RM, 0
        clean = not listed
        # FINAL fix1: по последней попытке убрать лишний пакет
        tries = [(seg, act) for _, _, seg, act in envkit.walk_venv(envkit.journal(box))
                 if (envkit.pip_args(seg) or [""])[0] == "uninstall"
                 and _install(envkit.pip_args(seg)[1:], envkit.canon(st["extra"]))]
        if listed and tries and not envkit.from_venv(tries[-1][0], tries[-1][1], ".venv"):
            return False, self.MSG_UNINST_OUT.format(extra=st["extra"]), 0
        req_ok, msg = self._req(ctx, pk)
        done = [env_ok, ign_ok, clean, req_ok]
        if all(done):
            return True, None, 4
        if msg:
            return False, msg, sum(done)
        if any(done):
            rest = ", ".join(p for p, ok in zip(self.PARTS, done) if not ok)
            return False, self.MSG_PART.format(k=sum(done), rest=rest), sum(done)
        return False, None, 0

    def _req(self, ctx, pk):
        box = ctx.box
        kind, text = envkit.box_text(box, APP_REQ, envkit.TEXT_CAP)
        bad = envkit.file_problem(kind, APP_REQ)
        if bad:
            return False, bad
        jour = envkit.journal(box)
        if text is None:
            k2, _ = envkit.box_file(box, REQ, envkit.TEXT_CAP)
            if k2 == "ok":
                return False, self.MSG_REQ_DIR
            runs = envkit.pip_runs(jour, "uninstall")
            if runs and any(p in a for p in _PLACEHOLDERS for a in runs[-1][0]):
                return False, self.MSG_PLACEHOLDER
            return False, None
        r = envkit.parse_requirements(text)
        if r["table"]:
            return False, self.MSG_REQ_TABLE
        if r["bad"] or r["bare"]:
            return False, self.MSG_REQ_FORMAT
        if envkit.canon(ctx.state["extra"]) in r["pins"]:
            return False, self.MSG_REQ_EXTRA
        if r["pins"] != pk:
            return False, self.MSG_REQ_STALE
        if not envkit.written_by(jour, REQ, _freeze_app):
            return False, self.MSG_REQ_HAND
        return True, None

    def _steps(self, ctx):
        proj = self._step_project(ctx)
        return [self._step_source(ctx), self._step_rc(ctx), self._step_quarantine(ctx),
                proj[:2]]

    def progress(self, ctx):
        return [ok for ok, _ in self._steps(ctx)]

    def check(self, ctx) -> Verdict:
        steps = self._steps(ctx)
        base_memo_marks(ctx, [ok for ok, _ in steps])
        if all(ok for ok, _ in steps):
            return Verdict(True)
        src, rc, quar, proj = steps
        # порча важнее недоделок: стёртый ~/.zshrc, удалённый источник, сломанный venv
        severe = {self.MSG_RC_GONE, self.MSG_SRC_RM, self.MSG_SRC_EDITED, self.MSG_VENV_GONE}
        for ok, msg in (rc, quar, proj, src):
            if not ok and msg and (msg in severe or msg.startswith(("Из ~/.zshrc",
                                                                     "Из app/.venv"))):
                return Verdict(False, msg)
        for ok, msg in (src, rc, quar, proj):
            if not ok and msg:
                return Verdict(False, msg)
        return Verdict(False)


# FB14: alias_rc — после блока прав и dotenv (FB5 п. 24/26: права идут сразу за
# export_child, следом dotenv), перед PATH: свой ~/.zshrc рядом с подключением .env
TASKS = [EnvVars(), ExportChild(), PermBasics(), PermRwx(), ReadLongList(), PermDigits(),
         Dotenv(), AliasRc(), PathWhich(), ShebangRun(), ExitCodes(), CronLine(),
         JsonConfig(), ScriptAudit(), ShellLint(),
         AvScan(), VenvBasics(), PipOffline(), PipFreeze(), BossEnv()]
