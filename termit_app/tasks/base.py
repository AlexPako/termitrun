"""Контракт поручения: что задача умеет и чего движок от неё ждёт."""
import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from termit_app import textnorm


@dataclass
class Cmd:
    """Одна команда владельца из журнала cmds.log."""
    t: float
    pwd: str
    line: str


@dataclass
class Ctx:
    """Всё, что видит проверка."""
    box: Path
    state: dict
    answer: Optional[str] = None
    cmds: List[Cmd] = field(default_factory=list)
    pwd: Optional[Path] = None
    # сервис родителя (Task.service: учебный API, сервер БД) — у судьи и в tests/refrun;
    # проверка внутри песочницы (хук без судьи, recheck) его не получает: None
    service: object = None


# шаги, посчитанные проверкой этой команды: progress того же Ctx их переиспользует
MARKS_ATTR = "_boss_marks"


def memo_marks(ctx, marks) -> None:
    setattr(ctx, MARKS_ATTR, [bool(m) for m in marks])


def memo_get(ctx) -> Optional[List[bool]]:
    return getattr(ctx, MARKS_ATTR, None)


@dataclass
class Verdict:
    solved: bool
    message: Optional[str] = None


@dataclass(frozen=True)
class Variant:
    """Вариант поручения: свой текст и, по желанию, свои подсказки, эталон, таймер и
    «Почему» разбора. None — берётся общее поле задачи. Шаги и spell — общие."""
    text: str
    hints: Optional[Sequence[str]] = None        # None — общие Task.hints
    solution: Optional[str] = None               # None — Task.solution
    solution_script: Optional[str] = None        # None — Task.solution_script
    wrong: Sequence[str] = ()                    # скрипты, которые НЕ должны решать (этот вариант)
    alternatives: Sequence[str] = ()             # «можно и так» в разборе
    par: Optional[int] = None
    key: str = ""                                # стабильное имя варианта (для статистики)
    implant_script: Optional[str] = None         # то же решение утилитой задачи (Task.implant)
    explain: Optional[str] = None                # «Почему» в разборе; None — Task.explain (Н3.4)


def variant_index(value, n: int) -> int:
    """Номер варианта из state или task.json: вне диапазона — по модулю, мусор — 0."""
    if n <= 0:
        return 0
    try:
        return int(value) % n
    except (TypeError, ValueError, OverflowError):
        return 0


def _fmt(items, state: dict) -> List[str]:
    return [s.format(**state) for s in items]


# needs_judge, а судья не поднимется (missing): причина — словами, как у прочих отказов
MSG_NO_JUDGE = ("проверке нужен судья игры, а путь к папке игры слишком длинный для его сокета "
                "— перенеси папку игры поближе к корню диска")


class Task:
    id = ""
    track = ""
    title = ""
    variants: Sequence[Union[str, Variant]] = ()   # тексты поручения; {поля} — из state
    scroll: Optional[str] = None       # карточка новой команды (первая встреча)
    par = 60                           # таймер, секунды (только повторения)
    hints: Sequence[str] = ()          # лестница из 3 подсказок
    solution = ""                      # эталон для человека
    solution_script: Optional[str] = None  # неинтерактивный эквивалент для тестов
    explain = ""
    spell = ""                         # строка шпаргалки (./termit book)
    boss = False
    steps: Sequence[str] = ()          # шаги схватки
    needs: Sequence[str] = ()          # команды, без которых поручение недоступно
    # FB3: флаги, которые игрок по условию находит в справке сам (man, --help): охраны
    # «сначала учим» не ждут их с карточек
    man_flags: Sequence[str] = ()
    implant: Optional[str] = None      # id рекомендованной утилиты (termit_app.implants)
    # стенд (часть 9б): "pg" — задаче нужен учебный PostgreSQL (implants, kind="stand"); без
    # него она недоступна через missing(), без штрафа (R004: только обычные задачи трека sql)
    stand: Optional[str] = None
    after: Sequence[str] = ()          # что должно быть решено до выдачи (близнец, страж)
    # FB12 (п. 34): вариант-практика стража. Первая встреча — простой вариант 0, составная
    # практика — повтор; страж места не выдаётся, пока этот вариант у игрока не выпал
    # (registry.practice_missing), а первый повтор задачи выдаёт именно его (practice_prefer)
    practice_variant: Optional[int] = None
    uses_clipboard = False
    uses_paste = False                 # pbpaste (читать буфер): только урокам, что его проверяют
    uses_gui = False                   # open/LaunchServices: иначе песочница их запрещает
    # часть 7: python3 в .termit/bin закреплён за интерпретатором треков (pyenvs.track_python;
    # симлинки кладёт sandbox.create); нет интерпретатора — задача недоступна (missing)
    pinned_python = False
    # запас готовых venv (A4): "light" | "full" | "wheels" — sandbox.create клонирует его из
    # кэша в box/.termit/stock (reset его не трогает, setup берёт оттуда); None — без запаса
    stock: Optional[str] = None
    uses_av = False                    # учебный clamscan (.termit/bin/clamscan, termit_app/avstub)
    uses_shellcheck = False            # учебный shellcheck (.termit/bin/shellcheck; FB14)
    uses_clip_stub = False             # учебные pbcopy/pbpaste (.termit/clipboard; FB13)
    uses_crontab = False               # учебный crontab (.termit/bin/crontab, cronstub; FB14)
    # проверка смотрит журнал сервиса родителя (учебный API): без судьи задача не решается
    needs_judge = False
    start_dir = ""                     # где стартует zsh, относительно песочницы
    autorun: Optional[str] = None      # команда, которую zsh выполнит сам при старте
    wrong: Sequence[str] = ()          # неверные решения (скрипты) для всех вариантов
    alternatives: Sequence[str] = ()   # «можно и так» для всех вариантов
    implant_script: Optional[str] = None   # решение утилитой (тесты — при найденной программе)
    # ключи state, которые выдают решение: в .termit/task.json их нет, они у родителя
    # (termit_app.judge). Хук проверяет такую задачу через судью (Н приёмки-1)
    secret_keys: Sequence[str] = ()
    # ans в задаче «сделай»: проверка идёт сама, сдавать нечего (Н3.10 приёмки-1)
    parts: Sequence[str] = ()          # части задачи из нескольких действий (parts_for)
    stray_answer = ("Здесь ответ сдавать не нужно: сделай, что велено, — проверка "
                    "сработает сама после команды.")

    def setup(self, box: Path, rng: random.Random) -> dict:
        return {}

    def takes_answer(self, state: dict) -> bool:
        """Ждёт ли задача ответ через ans (в этом варианте). Нет — ans не ошибка: хук скажет
        stray_answer без «✗» и без счётчика промахов (ревью P2, M4)."""
        return False

    def setup_variant(self, box: Path, rng: random.Random, variant: int) -> dict:
        """Подготовка под вариант; по умолчанию варианты различаются только текстом."""
        return self.setup(box, rng)

    def check(self, ctx: Ctx) -> Verdict:
        raise NotImplementedError

    def service(self, box: Path, state: dict):
        """Сервис родителя на время задачи (учебный API): объект с start() и stop() или None.
        Нельзя открыть — исключение, задача не начнётся. Сервис живёт в родителе и в
        песочнице ничего не исполняет; stop() зовут всегда (finally), и повторно — тоже."""
        return None

    def progress(self, ctx: Ctx) -> Optional[List[bool]]:
        """Какие шаги уже сделаны: у стража — шаги схватки (steps), у обычной задачи — части
        (parts_for, FB5 п. 68)."""
        return None

    def parts_for(self, state: dict) -> List[str]:
        """FB5 п. 68: части обычной задачи из нескольких действий («копия в backup/», «черновик
        в archive/») — по ним хук говорит «сделано k из n, осталось …», пока задача не решена.
        Пусто — задача молчит, как раньше. progress отдаёт отметки в том же порядке."""
        return list(self.parts)

    def check_marks(self, ctx: Ctx) -> Tuple["Verdict", Optional[List[bool]]]:
        """Вердикт и шаги схватки одной проверкой (судья, ревью P5 M2). Страж, чья проверка
        уже посчитала шаги, кладёт их в ctx (memo_marks) — тогда базу и файлы второй раз не
        снимаем; иначе — progress после check. Сам progress памяти не читает: Ctx в тестах
        живёт дольше одной команды."""
        if hasattr(ctx, MARKS_ATTR):
            delattr(ctx, MARKS_ATTR)
        v = self.check(ctx)
        marks = memo_get(ctx)
        if hasattr(ctx, MARKS_ATTR):
            delattr(ctx, MARKS_ATTR)
        if marks is None and self.boss:
            marks = self.progress(ctx)
        return v, marks

    def variant(self, state: dict) -> Variant:
        if not self.variants:
            return Variant(text="")
        v = self.variants[variant_index(state.get("_variant", 0), len(self.variants))]
        return v if isinstance(v, Variant) else Variant(text=v)

    def text(self, state: dict) -> str:
        return self.variant(state).text.format(**state)

    def hints_for(self, state: dict) -> List[str]:
        v = self.variant(state)
        return _fmt(self.hints if v.hints is None else v.hints, state)

    def _solution(self, v: Variant) -> str:
        return self.solution if v.solution is None else v.solution

    def wrong_scripts(self, state: dict) -> List[str]:
        return _fmt(list(self.wrong) + list(self.variant(state).wrong), state)

    def alternatives_for(self, state: dict) -> List[str]:
        return _fmt(list(self.alternatives) + list(self.variant(state).alternatives), state)

    def explain_for(self, state: dict) -> str:
        """«Почему» разбора про этот вариант (Н3.4 приёмки-1); общий explain — запасной."""
        v = self.variant(state)
        return self.explain if v.explain is None else v.explain

    def par_for(self, state: dict) -> int:
        v = self.variant(state)
        return self.par if v.par is None else v.par

    # префиксы переменных, которые env.zsh снимает до своих export (unset -m 'APP_*'): свои
    # учебные переменные задачи не смешиваются с такими же из ~/.zshrc владельца
    env_clear: Sequence[str] = ()

    def env_for(self, state: dict) -> Dict[str, str]:
        """Переменные окружения задачи (A7): родитель пишет их в .termit/env.zsh (create и
        reset), песочный .zshrc подключает файл после своих настроек и чистки секретов. Имена
        — ^[A-Z_][A-Z0-9_]*$, PATH — только префиксом «$HOME/…:$PATH» (sandbox.env_lines)."""
        return {}

    def missing(self, root=None) -> Optional[str]:
        """Чего не хватает для задачи, кроме программ из needs (None — всё есть). root —
        корень песочниц рана (None — sandbox.current_root(): корень текущего рана или игры).
        Задаче с закреплённым python3 (pinned_python) или запасом venv (stock) — интерпретатор
        треков и путь без пробелов, задаче с запасом — ещё и эталон, который можно собрать
        (pyenvs.stock_problem, M7 ревью P1); своя missing у такой задачи зовёт
        super().missing(root)."""
        if self.pinned_python or self.stock:
            from termit_app import pyenvs
            why = pyenvs.why_not(root) or (pyenvs.stock_problem(self.stock) if self.stock
                                           else None)
            if why:
                return why
        if self.needs_judge:
            # проверка по журналу сервиса родителя (учебный API) без судьи невозможна: путь
            # его сокета обязан влезть в sun_path (решение контроллера после Q1)
            from termit_app import judge, sandbox
            if not judge.path_fits(sandbox.sample_box(root)):
                return MSG_NO_JUDGE
        return None

    def reference(self, state: dict) -> str:
        """Эталон для прогона в zsh. Свой solution у варианта отсекает классовый
        solution_script: иначе вариант B молча гонял бы скрипт варианта A."""
        v = self.variant(state)
        if v.solution_script is not None:
            script = v.solution_script
        elif v.solution is not None:
            script = v.solution
        else:
            script = self.solution_script or self.solution
        return script.format(**state)

    def implant_reference(self, state: dict) -> Optional[str]:
        """Скрипт решения утилитой (Task.implant) для этого варианта; None — нет. Эталон
        reference обязан обходиться без неё: утилита даёт только скорость и точность."""
        v = self.variant(state)
        script = v.implant_script if v.implant_script is not None else self.implant_script
        return None if script is None else script.format(**state)

    def steps_for(self, state: dict) -> List[str]:
        """Шаги схватки для этого рана; по умолчанию — общие steps."""
        return list(self.steps)

    def scroll_for(self, state: Optional[dict]) -> Optional[str]:
        """Карточка приёмов для этого рана (финал M3: страж Хранилища — по движку); по
        умолчанию — общая scroll."""
        return self.scroll

    def shown_solution(self, state: dict) -> str:
        return self._solution(self.variant(state)).format(**state)

    def allowed_variants(self, box: Path) -> Tuple[int, ...]:
        """Какие варианты можно выдать в этой песочнице (по умолчанию — все). Задача, чьему
        варианту нужно то, чего здесь нет, сужает список; родитель ротирует только по нему
        (progress.pick_variant), а make_state заменяет недопустимый вариант (allowed_variant)."""
        return tuple(range(len(self.variants)))

    def allowed_variant(self, box: Path, v: int, drawn: int) -> int:
        """Вариант v, если он допустим; иначе замена из allowed_variants — детерминированно
        по drawn, без новых вызовов rng (поток зерна и данные не сдвигаются)."""
        allowed = self.allowed_variants(Path(box))
        if not allowed or v in allowed:
            return v
        return allowed[drawn % len(allowed)]

    def make_state(self, box: Path, seed: int, variant: Optional[int] = None,
                   engine: Optional[str] = None) -> dict:
        """Вариант тянется из rng ВСЕГДА — выбранный вручную вариант не сдвигает поток,
        и данные того же seed остаются теми же. engine — движок задачи БД (dbkit.ENGINES),
        выбранный родителем: задача видит его через dbkit.current_engine() на время setup,
        а в state он ложится ключом _engine (reset в песочнице берёт его оттуда). None —
        задача не про БД, ключа нет."""
        rng = random.Random(seed)
        n = len(self.variants)
        drawn = rng.randrange(n) if n else 0
        v = drawn if variant is None else variant_index(variant, n)
        v = self.allowed_variant(Path(box), v, drawn)
        if engine is None:
            state = self.setup_variant(Path(box), rng, v)
        else:
            from termit_app.tasks import dbkit
            with dbkit.engine_scope(engine):
                state = self.setup_variant(Path(box), rng, v)
            state[dbkit.ENGINE_KEY] = engine
        state["_variant"] = v
        state["_seed"] = seed
        return state


# Типовые промахи с ans (П3.5, Н3.2 приёмки-1). Тексты нейтральные — без сеттинга.
# Отклик зависит только от ФОРМЫ сданного, а не от того, верна ли его часть: иначе перебор
# «сдам всех кандидатов разом» подтвердил бы, что ответ среди них (I1 ревью C1b).
OUTPUT_CMDS = ("pwd", "ls", "cat", "find", "grep", "du", "wc", "head", "tail", "sort",
               "echo", "less", "cut", "uniq", "date", "whoami", "basename", "dirname")
# совет с подстановкой — всегда полный и безопасный: без голых cat/grep, ждущих ввода (I2)
SAFE_SUBST = {"pwd": "ans $(pwd)", "whoami": "ans $(whoami)", "date": "ans $(date)",
              "cat": "ans $(cat ИМЯ_ФАЙЛА)", "grep": "ans $(grep 'ШАБЛОН' ИМЯ_ФАЙЛА)"}
# Заготовка из текста задания: ПУТЬ, СЛОВО, ЧИСЛО, ИМЯ_ФАЙЛА… — заглавные кириллицей.
_PLACEHOLDER = re.compile(r"(?<![\w])([А-ЯЁ][А-ЯЁ_]+)(?![\w])")
# Похоже на имя файла: без пробелов, с расширением (в нём есть буква), скрытое имя с точки
# или путь с косой чертой внутри.
_FILE_LIKE = re.compile(r"^(?=.*[A-Za-zА-Яа-яЁё])[^\s:]*"
                        r"(?:\.(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{1,5}|/[^\s:]*)$"
                        r"|^\.[\w.-]*[A-Za-z][\w.-]*$")

# «ans cat note.txt»: в совет — то, что игрок уже набрал (N3), но только простые слова [\w./~=-] (без
# ; | $ ` кавычек и прочего) и только если команда не будет ждать ввода: у cat есть файл,
# у grep — шаблон и путь (или -r). Форма, а не верность: имя подставляется любое (I1).
_SAFE_WORD = re.compile(r"[\w./~=-]+")


# ключи grep со значением: короткие (значение слитно или следующим словом) и длинные (через «=»
# или следующим словом). Значение — не операнд: «grep -m 1 foo» — без файла (Minor-4 C2)
_GREP_SHORT_ARG = set("ABCDdefm")
_GREP_LONG_ARG = {"--max-count", "--regexp", "--file", "--after-context", "--before-context",
                  "--context", "--include", "--exclude", "--exclude-dir", "--label",
                  "--devices", "--directories", "--binary-files"}


def grep_parse(rest):
    """Разбор аргументов grep: (рекурсивно ли, шаблон задан ключом -e/-f, операнды)."""
    recursive, by_opt, ops = False, False, []
    it = iter(rest)
    for w in it:
        if w == "--":
            ops += list(it)
            break
        if w.startswith("--"):
            name = w.split("=", 1)[0]
            recursive = recursive or name == "--recursive"
            if name in ("--regexp", "--file"):
                by_opt = True
            if name in _GREP_LONG_ARG and "=" not in w:
                next(it, None)
            continue
        if w.startswith("-") and len(w) > 1:
            for i, ch in enumerate(w[1:], 1):
                if ch in "rR":
                    recursive = True
                if ch in _GREP_SHORT_ARG:
                    by_opt = by_opt or ch in "ef"
                    if i == len(w) - 1:
                        next(it, None)      # значение — следующим словом
                    break                   # остаток связки — значение ключа
            continue
        ops.append(w)
    return recursive, by_opt, ops


def grep_recursive(flags) -> bool:
    """grep ищет рекурсивно: -r/-R в связке коротких ключей (-rn, -Rl) или ровно --recursive.
    Длинные --color, --ignore-case, --regexp — не рекурсия (I2 ревью C2)."""
    return grep_parse(flags)[0]


def grep_waits(rest) -> bool:
    """grep с шаблоном, но без файла и без -r — читает stdin («завис»). Общий разбор для хука
    (сообщение про Ctrl+C) и совета N3. Голый grep без шаблона ввода не ждёт: печатает usage."""
    recursive, by_opt, ops = grep_parse(rest)
    files = ops if by_opt else ops[1:]
    has_pattern = by_opt or bool(ops)
    return has_pattern and not files and not recursive


def _own_subst(words) -> Optional[str]:
    if not all(_SAFE_WORD.fullmatch(w) for w in words):
        return None
    cmd, rest = words[0], words[1:]
    if cmd == "cat" and any(not w.startswith("-") for w in rest):
        return f"ans $({' '.join(words)})"
    _, by_opt, ops = grep_parse(rest)
    if cmd == "grep" and (by_opt or ops) and not grep_waits(rest):
        return f"ans $({' '.join(words)})"
    return None


MSG_EMPTY = "Пусто: после ans через пробел нужен сам ответ."
MSG_PLACEHOLDER = ("«{word}» в задании — место для ответа. Подставь вместо него то, что "
                   "нашёл.")
MSG_COMMAND_SUBST = ("Ты сдал саму команду {cmd}, а нужен её результат. Подставь его: "
                     "{example} — $( ) выполнит команду и сдаст её вывод.")
MSG_COMMAND = ("Ты сдал саму команду {cmd}, а нужен её результат. Запусти её, найди в выводе "
               "нужное и сдай только его.")
MSG_FILE = ("{name} — это имя файла, а нужно то, что написано внутри. Открой его (cat {name}) "
            "и сдай найденное.")
MSG_FILE_NUMBER = "{name} — это имя файла, а нужно число."
# FB5 (владелец 19.10): «где-то принимает $(cat файл), а где-то требует только слово» —
# подстановка сдаёт файл целиком; годится, только если в файле один ответ. Говорим прямо.
_WHOLE_FILE = (" ans $(cat файл) сдаёт файл целиком — так можно, только если в нём один ответ "
               "и больше ничего.")
MSG_EXTRA = ("Нужен только сам ответ — без остальной строки и подписей." + _WHOLE_FILE +
             " Найди ответ в тексте и сдай его один: ans ОТВЕТ")
MSG_ONE = ("Нужен ровно один ответ, а не несколько на выбор." + _WHOLE_FILE +
           " Выбери нужный и сдай его один: ans ОТВЕТ")
MSG_EXTRA_NUMBER = "Нужно одно число — без слов вокруг." + _WHOLE_FILE + " Сдай число: ans ЧИСЛО"
MSG_ONE_NUMBER = "Нужно одно число, а не несколько." + _WHOLE_FILE + " Сдай одно: ans ЧИСЛО"
MSG_GREP_LINE = ("Это строка вывода grep целиком. Путь — до первого двоеточия: сдай только "
                 "его (grep -l печатает одни пути).")
MSG_EXTRA_PATH = "Сдай только сам путь — без остальной строки."
MSG_NAME_ONLY = ("Это только имя, а нужен путь целиком — с папками, как его печатают pwd и "
                 "find.")
MSG_TILDE = ("~ — короткая запись домашней папки, а не путь того места, о котором спрашивают. "
             "Полный путь печатает pwd: ans $(pwd).")
MSG_HERE = ("Это путь папки, где ты стоишь, а спрашивают о другом месте. Дойди до него "
            "(cd) или найди его — и сдай его путь.")
MSG_NOT_NUMBER = "Нужно число — сдай его цифрами."
MSG_PARTIAL = "Ответ из {n} частей — сдай их все, через пробел."
MSG_CASE = "Почти: здесь важен регистр — большая и маленькая буква дают разное."
MSG_LOST_SOURCE = ("Файл, где лежал ответ, пропал или изменился. Набери reset — соберу задачу "
                   "заново, с теми же данными.")


class AnswerTask(Task):
    """Поручение «найди и назови»: решено, когда ans совпал с ответом.

    Неверный ответ получает объяснение (wrong_message): сначала ловушки задачи —
    state["traps"], пары [ключ, значение неверного пути] с текстами trap_messages[ключ], —
    потом типовые промахи (common_mistake), и только потом fallback."""
    kind_answer = "text"   # text | number | path
    case_sensitive = False
    # карточки учат «pwd | pbcopy → ans и Cmd+V»: буфер владельца сохраняем и возвращаем
    uses_clipboard = True
    # ответ, принимаемые слова, ловушки неверных ответов, данные учебного API, квитанция
    # sources — файлы с ответом {путь: sha}: стёрли или испортили — подсказать reset (Н3.1)
    secret_keys = ("answer", "accept", "traps", "want", "routes", "receipt", "sources")
    trap_messages: Dict[str, str] = {}
    fallback = "Не то. Попробуй ещё или набери hint."

    def takes_answer(self, state: dict) -> bool:
        return True

    def expected(self, state: dict) -> str:
        return str(state["answer"])

    def answer_kind(self, state: dict) -> str:
        """Вид ответа этого варианта (text | number | path); по умолчанию — kind_answer."""
        return self.kind_answer

    def _bases(self, ctx: Ctx) -> List[Path]:
        return [Path(ctx.box)] + ([Path(ctx.pwd)] if ctx.pwd else [])

    def _is_path(self, given: str, rel, ctx: Ctx) -> bool:
        target = Path(ctx.box) / str(rel)
        return any(textnorm.same_path(given, target, b) for b in self._bases(ctx))

    def matches(self, given: str, ctx: Ctx) -> bool:
        exp = self.expected(ctx.state)
        kind = self.answer_kind(ctx.state)
        if kind == "number":
            return textnorm.same_number(given, exp)
        if kind == "path":
            return self._is_path(given, exp, ctx)
        if textnorm.same_text(given, exp, self.case_sensitive):
            return True
        # ответ из нескольких частей: запятая между ними — как пробел (Н приёмки-1)
        return (not self.case_sensitive and len(textnorm.parts(exp)) > 1
                and textnorm.same_words(given, exp))

    def trap_message(self, given: str, ctx: Ctx) -> Optional[str]:
        """Сданное значение неверного пути — объяснение этой ловушки."""
        st = ctx.state
        for item in st.get("traps") or ():
            key, value = item[0], item[1]
            if key not in self.trap_messages:
                continue
            hit = (textnorm.same_text(given, str(value)) or
                   (len(textnorm.parts(str(value))) > 1 and textnorm.same_words(given, str(value))))
            kind = self.answer_kind(st)
            if not hit and kind == "number":
                hit = textnorm.same_number(given, value)
            if not hit and kind == "path" and "/" in str(value):
                hit = self._is_path(given, value, ctx)
            if hit:
                return self.trap_messages[key].format(**st)
        return None

    accepts_name = False    # путь можно сдать одним именем (du_heavy, grep_r)

    def common_mistake(self, given: str, ctx: Ctx) -> Optional[str]:
        """Промахи, одинаковые во всех задачах: пусто, заготовка, команда вместо вывода,
        лишнее вокруг ответа, несколько кандидатов, имя файла вместо содержимого, имя
        вместо пути, не число. Решает форма сданного, не его верность (I1 ревью C1b)."""
        g = textnorm.clean(given)
        if not g:
            return MSG_EMPTY
        st = ctx.state
        exp = self.expected(st)
        m = _PLACEHOLDER.search(g)
        if m and m.group(1) in self._task_text(st):
            return MSG_PLACEHOLDER.format(word=m.group(1))
        words = g.split()
        if words[0] in OUTPUT_CMDS and words[0] not in textnorm.parts(exp):
            cmd = words[0]
            example = _own_subst(str(given).split()) or SAFE_SUBST.get(cmd)   # как набрано
            if example:
                return MSG_COMMAND_SUBST.format(cmd=cmd, example=example)
            return MSG_COMMAND.format(cmd=cmd)
        kind = self.answer_kind(st)
        if kind == "path":
            return self._path_shape(g, words, exp, ctx)
        if kind == "number":
            nums = [w for w in textnorm.parts(g) if textnorm.as_number(w) is not None]
            if len(nums) > 1:
                return MSG_ONE_NUMBER
            if nums and len(textnorm.parts(g)) > 1:
                return MSG_EXTRA_NUMBER
            if _FILE_LIKE.match(g):
                return MSG_FILE_NUMBER.format(name=g)
            if not nums:
                return MSG_NOT_NUMBER
            return None
        got, want = textnorm.parts(g), textnorm.parts(exp)
        shape = _shape(exp)
        same = [w for w in g.split() if _shape(w) == shape] if shape != "word" else []
        if len(same) > 1:
            return MSG_ONE
        if want and len(got) > len(want):
            return MSG_EXTRA if (":" in g or len(got) - len(want) <= 2) else MSG_ONE
        if want and len(want) > 1 and len(got) < len(want):
            return MSG_PARTIAL.format(n=len(want))
        if _FILE_LIKE.match(g) and not _FILE_LIKE.match(exp):
            return MSG_FILE.format(name=g)
        if self.case_sensitive and textnorm.same_text(g, exp):
            return MSG_CASE
        return None

    def _task_text(self, st: dict) -> str:
        try:
            return self.text(st)
        except (KeyError, IndexError, ValueError):
            return ""

    def _path_shape(self, g: str, words, exp: str, ctx: Ctx) -> Optional[str]:
        """Ответ-путь: строка grep, несколько путей, путь со словами, голое имя."""
        if ":" in g and _FILE_LIKE.match(g.split(":", 1)[0]):
            return MSG_GREP_LINE
        paths = [w for w in words if _FILE_LIKE.match(w) or w in (".", "..")]
        if len(paths) > 1:
            return MSG_ONE
        if len(words) > 1:
            return MSG_EXTRA_PATH if paths else None
        if g == "~":
            return MSG_TILDE
        # имя папки из приглашения (текущая или сама песочница) — это имя, а не путь, даже
        # если эталон без «/» (P2 Б1): решает форма сданного и где стоит игрок, не ответ
        here = {Path(ctx.box).name} | ({Path(ctx.pwd).name} if ctx.pwd else set())
        if ("/" not in g and not self.accepts_name and g not in (".", "..")
                and ("/" in exp or g.rstrip("/") in here)):
            return MSG_NAME_ONLY
        if ctx.pwd and "/" in g and any(textnorm.same_path(g, Path(ctx.pwd), b)
                                        for b in self._bases(ctx)):
            return MSG_HERE
        return None

    def wrong_message(self, given: str, ctx: Ctx) -> str:
        return (self.trap_message(given, ctx) or self.common_mistake(given, ctx)
                or self.fallback)

    def lost_source(self, ctx: Ctx) -> bool:
        """Файл с ответом стёрт или изменён: без reset задачу не решить. Читает судья у
        родителя — только внутри песочницы, без симлинков (kit.sha_in_box)."""
        from termit_app.tasks import kit
        return any(kit.sha_in_box(ctx.box, rel) != h
                   for rel, h in (ctx.state.get("sources") or {}).items())

    def check(self, ctx: Ctx) -> Verdict:
        if ctx.answer is not None and self.matches(ctx.answer, ctx):
            return Verdict(True)            # ответ уже знают — засчитать и без файла
        if self.lost_source(ctx):
            return Verdict(False, MSG_LOST_SOURCE)
        if ctx.answer is None:
            return Verdict(False)
        return Verdict(False, self.wrong_message(ctx.answer, ctx))


def sources(box, *rels) -> dict:
    """{путь: sha} файлов с ответом — для AnswerTask.lost_source (в state, ключ sources)."""
    from termit_app.tasks import kit
    return {str(r): kit.sha(Path(box) / r) for r in rels}


def _shape(w: str) -> str:
    """Вид значения: флаг, число, имя файла или путь, слово. Несколько значений одного вида
    с ответом в одной строке — это перебор кандидатов, а не подпись вокруг ответа."""
    w = textnorm.clean(w)
    if w.startswith("-") and len(w) > 1 and textnorm.as_number(w) is None:
        return "flag"
    if textnorm.as_number(w) is not None:
        return "number"
    if _FILE_LIKE.match(w):
        return "file"
    return "word"
