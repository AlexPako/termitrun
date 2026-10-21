"""FB12: правила понятности уроков и вариантов (свод Fable: E1, N10, N11, N21, N25).

Проверки зовёт lint.static_issues; здесь — сами правила и списки исключений с причинами.

F001  урок длиннее LESSON_LINES строк в окне LESSON_WIDTH колонок (предупреждение)
F002  в уроке больше LESSON_TRICKS новых приёмов (команд в `…`, которых не было раньше)
F004  урок варианта учит больше VARIANT_TRICKS новых приёмов (команды и клавиши; сноски в
      скобках не в счёт) — FB5 п. 38: один главный приём, максимум +1 родственный
F005  у урока «Основ» нет примера применения «Пригодится, когда …»
F006  телеграфный обрывок: два приёма списком «X — что, Y — что» в одной фразе («Основы»)
F003  урок «Основ» не в формате п. 41: что это (с приёма), пример, шаги «1) …»
      F003–F006 для «Основ» — ошибки, F002/F004 у остальных мест — предупреждения.
V003  первая встреча (вариант 0) сложнее самого простого из остальных вариантов (N10)
S008  в эталоне команда, которой нет в третьей подсказке (N25)
S009  команда эталона или третьей подсказки не встретилась в карточках раньше по пути
      игрока: только своё место до задачи, места-предки целиком и after (N11)
Q001  первая задача места спрашивает больше одного ответа сразу (N21)"""
import re
from typing import Dict, List, Optional, Set

from termit_app import tui

# FB5 п. 41–50: урок — не телеграмма. Лимит «7 строк в 60 колонок» снят (толкал к обрывкам):
# длина — сколько нужно для ясности, после LESSON_LINES строк в окне LESSON_WIDTH — только
# мягкое предупреждение; задание при длинной карточке повторяется в её конце (ui.task_card).
# FB17: переносы считаются от самого широкого окна игры (tui.MAX_WIDTH, 100 колонок)
LESSON_WIDTH = tui.MAX_WIDTH
LESSON_LINES = 14
LESSON_TRICKS = 4
STRICT_TRACKS = ("basics",)

# приём — голова команды в `…`: слово и первый флаг (буквы склеенных флагов по алфавиту:
# -rv и -vr — один приём) или знак оболочки. Не приёмы: голый флаг (`-a` — расшифровка
# флага, который уже стоит в примере), путь и имя файла (`notes.txt`, `a/b/c`, `~/файл`),
# заглушка БОЛЬШИМИ (`ИМЯ`). Новый приём — тот, которого не было в уроках раньше по пути
# игрока (guaranteed_before): `ls` в пятом уроке — уже не новость, `ls -la` — новость.
_SPAN = re.compile(r"`([^`\n]+)`")
_PATHISH = re.compile(r"^(?:[\w…~*?-]*[./][\w./…*?-]*|[A-ZА-ЯЁ_]+|\w+\d+)$")
_KEY_START = re.compile(r"^(?:`|Ctrl\+|Cmd\+|Option\+|Esc|Tab|↑|Shift\+|Enter)")


def _head(span: str) -> Optional[str]:
    words = span.split()
    if not words:
        return None
    first = words[0]
    if first.startswith("-") or (_PATHISH.match(first) and first not in ("..", "./")):
        return None
    if len(words) > 1 and re.match(r"^-[A-Za-z]{2,}$", words[1]):
        return f"{first} -{''.join(sorted(words[1][1:]))}"
    if len(words) > 1 and words[1].startswith("-") and len(words[1]) > 1:
        return f"{first} {words[1]}"
    return first


def lesson_tricks(lesson: str) -> List[str]:
    """Приёмы урока в порядке появления (без повторов)."""
    out = []
    for span in _SPAN.findall(lesson or ""):
        head = _head(span)
        if head and head not in out:
            out.append(head)
    return out


def new_tricks(task, lesson: Optional[str], lesson_of=None) -> List[str]:
    """Приёмы урока, которых не было в уроках задач раньше по пути игрока."""
    from termit_app.tasks import lint, registry
    lesson_of = lesson_of or lint._lesson
    tasks = registry.all_tasks()
    known = set()
    for tid in guaranteed_before(task):
        known |= set(lesson_tricks(lesson_of(tasks[tid]) or ""))
    return [h for h in lesson_tricks(lesson or "") if h not in known]


# FB12 (п. 38): урок варианта — один главный приём и максимум один родственный
VARIANT_TRICKS = 2
# FB12 (владелец: «больше примеров, чтоб было для чего использовать»): у урока «Основ» —
# жизненный пример главного приёма одной фразой с этим маркером
USE_MARK = "Пригодится"
_KEY = re.compile(r"(?:Ctrl|Cmd|Option|Shift)(?:\+(?:fn|Shift|[^\s,;:()«»—]))+|\bEsc\b|\bTab\b")
_PAREN = re.compile(r"\([^()]*\)")


def _outside_parens(text: str) -> str:
    """Текст без скобок-пояснений «(…)»: «(вне игры — только iTerm2)», «(то же Ctrl+L)» —
    сноска, а не приём урока. Скобки внутри команды (`(D)`) не трогаем: `…` на время
    прячем за заглушки."""
    spans = []

    def hide(m):
        spans.append(m.group())
        return f"\x00{len(spans) - 1}\x00"
    body = re.sub(r"`[^`]*`", hide, text)
    prev = None
    while prev != body:
        prev, body = body, _PAREN.sub("", body)
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], body)


def _key_name(key: str) -> str:
    """Пара стрелок — один приём: Cmd+fn+← и Cmd+fn+→, Shift+fn+↑ и ↓."""
    return re.sub(r"[↑↓]", "↑↓", re.sub(r"[←→]", "←→", key.rstrip(".")))


def variant_tricks(text: str, notes: bool = False) -> List[str]:
    """Приёмы урока варианта: команды в `…` и клавиши; без сносок в скобках (notes=True —
    со сносками: что игрок уже видел) и без слов игры."""
    from termit_app.tasks import lint
    body = (text or "") if notes else _outside_parens(text or "")
    out = []
    for h in lesson_tricks(body) + [_key_name(k) for k in _KEY.findall(body)]:
        if h and h.strip(".") and h not in out and h not in lint.BASE_COMMANDS:
            out.append(h)
    return out


def all_lessons(task, lesson_of=None, variants_of=None) -> Dict[int, str]:
    """{вариант: урок} — общий урок у варианта 0 и уроки вариантов, где тема их задала."""
    from termit_app.tasks import lint
    lesson_of = lesson_of or lint._lesson
    variants_of = variants_of or lint._variant_lessons
    out = {0: lesson_of(task)} if lesson_of(task) else {}
    out.update(variants_of(task))
    return out


def new_variant_tricks(task, text: str) -> List[str]:
    """Приёмы урока варианта, которых не было в уроках (любых вариантов) задач раньше по пути."""
    from termit_app.tasks import registry
    tasks = registry.all_tasks()
    known = set()
    for tid in guaranteed_before(task):
        for t in all_lessons(tasks[tid]).values():
            known |= set(variant_tricks(t, notes=True))
    return [h for h in variant_tricks(text) if h not in known]


def lesson_issues(task, lesson: Optional[str], add) -> None:
    lessons = {0: lesson} if lesson else {}
    from termit_app.tasks import lint
    if lesson is not None and lesson == lint._lesson(task):
        lessons.update(lint._variant_lessons(task))
    for v, text in sorted(lessons.items()):
        _one_lesson_issues(task, text, add, "" if v == 0 else f"урок варианта {v}: ", v)


def _one_lesson_issues(task, lesson: str, add, where: str, variant: int) -> None:
    from termit_app import ui
    if not lesson:
        return
    strict = task.track in STRICT_TRACKS
    level = "error" if strict else "warn"
    many = new_variant_tricks(task, lesson)
    if len(many) > VARIANT_TRICKS:
        add("F004", level, f"{where}{len(many)} новых приёмов ({', '.join(many)}): урок варианта "
                           f"учит один главный приём и не больше одного родственного")
    lines = ui.lesson_block(lesson, LESSON_WIDTH).split("\n")
    if len(lines) > LESSON_LINES:
        add("F001", "warn", f"{where}урок — {len(lines)} строк в окне {LESSON_WIDTH} колонок, "
                            f"длиннее {LESSON_LINES} — проверь, всё ли нужно этому варианту")
    tricks = new_tricks(task, lesson)
    if len(tricks) > LESSON_TRICKS:
        add("F002", level, f"{where}в уроке {len(tricks)} новых приёмов ({', '.join(tricks)}), "
                           f"можно не больше {LESSON_TRICKS}")
    if not strict:
        return
    if USE_MARK not in lesson:
        add("F005", "error", f"{where}нет примера применения: фраза «{USE_MARK}, когда …» — "
                             "когда этот приём выручит в настоящей работе")
    for bit in telegraph(lesson):
        add("F006", "error", f"{where}телеграфный обрывок — несколько приёмов через «—» в одной "
                             f"фразе без глагола: {bit[:60]!r}")
    paras = ui.lesson_paragraphs(lesson)
    if len(paras) < 3 or not any(STEP.match(p) for p in paras):
        add("F003", "error", f"{where}формат урока: что это (фраза), «{USE_MARK}, когда…», "
                             "шаги «1) нажми — увидишь»")
        return
    if not _KEY_START.search(paras[0][:40].lstrip()) and "`" not in paras[0][:40]:
        add("F003", "error", f"{where}первая фраза — с самого приёма: {paras[0][:40]!r}")


STEP = re.compile(r"^\d\)\s")
_TELEGRAPH_ITEM = re.compile(r"(?:`[^`]+`|(?:Ctrl|Cmd|Option|Shift)\+\S+|\bEsc\b)\s*(?:\S+\s*)?— ")


def telegraph(text: str) -> List[str]:
    """Фразы, где два и больше приёма идут списком «X — что, Y — что» (FB5 п. 41): так урок
    превращается в обрывки. Фраза — до точки, «;» или шага «N)»; сноски в скобках не в счёт."""
    out = []
    for sent in re.split(r"[.;!?]\s|\n\n|\d\)\s", _outside_parens(text)):
        if len(_TELEGRAPH_ITEM.findall(sent)) >= 2:
            out.append(sent.strip())
    return out


# --- N10: первая встреча — самый простой вариант -----------------------------------------

_SINGLE_QUOTED = re.compile(r"'[^'\n]*'")
_FIELD = re.compile(r"(?<!\{)\{[A-Za-z_]\w*\}(?!\})")
_SEGMENT = re.compile(r"&&|\|\||[;|\n]|→|, ")
_FLAG = re.compile(r"(?<![\w-])--?[A-Za-z][\w-]*")
# приёмы оболочки: ** , уточнения zsh в скобках, ${…}, $(…), > и >>, {a,b}
_CONSTRUCT = re.compile(r"\*\*|\*?\((?:#[a-z]|[.D/]|[mL][-+]?\d*\w*|on|Om)[^)]*\)|\$\{|\$\(|"
                        r">>?|\{[^{}\s]*,[^{}\s]*\}")
_KEYS = re.compile(r"Ctrl\+|Cmd\+|Esc|Option\+")
# Допуск в одну единицу веса — не поблажка, а шум самой меры. Вес — грубый счёт слов (звено,
# флаг, знак оболочки), и единица разницы не говорит о сложности: «ls -la && cat .secret»
# (3) против «ls -la» (2), «grep -c x f» против «grep x f | wc -l», «-vic» (три флага одним
# словом — 1) против «-i -c». При допуске 0 правило срабатывает на 15 задачах, где v0 по сути
# не сложнее; при 1 — ловит настоящие составные первые встречи (было: disk_sweep 18 против 4,
# dup_sort 7 против 1, deep_rm 5 против 2).
SLACK = 1

# Задачи, где вариант 0 вправе быть сложнее (по счёту) — с причиной.
V0_COMPLEX_OK: Dict[str, str] = {
    "vim_purge": "эталон — клавиши vim словами, счёт команд к ним не применим",
    "fd_hunt": "вариант 1 короче только на словах: «самый глубокий путь» ищут глазами по "
               "выводу; вариант 0 — тот же find с двумя -not -path, что и урок",
    "create_insert": "SQL в кавычках: счёт видит флаги в тексте таблицы; вариант 0 — одна "
                     "таблица и одна строка, как в уроке",
    "constraints_fk": "SQL в кавычках: вариант 0 — одна таблица с теми ограничениями, "
                      "которые показывает урок",
    "view_index": "SQL в кавычках: вариант 0 — одно представление, ровно пример урока",
    "subquery": "SQL в кавычках: подзапрос — сама тема урока, без него задачи нет",
    "cte_with": "SQL в кавычках: WITH — сама тема урока",
    "sql_pipe": "SQL в кавычках: вариант 0 — один запрос с -csv -header, ровно урок",
    "curl_api": "оба шага варианта 0 — один и тот же curl из урока (список и запись в файл)",
    "pip_offline": "три шага урока (activate, pip install, запуск) — в каждом варианте; "
                   "остальные короче только потому, что часть уже сделана в setup",
    "av_scan": "карантин — три шага урока подряд; варианты 1–2 повторяют их частями",
    "zip_pack": "zip -r … -x — одна команда, оба флага — тема урока; вариант 2 без -r учит "
                "другому (маске файлов)",
    "grep_count": "вариант 1 склеивает три флага в -vic — счёт видит один; по сути он не легче",
    "redirect_report": "> и >> — тема урока: заголовок в новый файл, строки следом; вариант 2 "
                       "только дописывает в готовый файл",
    "join_parts": "> и >> с tail -q -n +2 — тема урока; вариант 2 только дописывает в готовый",
    "jq_deep": "фильтры jq в кавычках счёт не видит: в вариантах 1–2 map, select и add — "
               "по сути они тяжелее варианта 0",
    "sed_fix": "в варианте 1 -i '' (правка на месте) — свой подвох macOS; счёт его не видит",
    "csv_top": "частотный словарь — шесть звеньев, но одна формула урока; вариант 1 "
               "(sort -u | grep -c .) по сути не легче",
    "copy_dump": "\\copy вариантов 1–2 — длинная строка в кавычках, которую счёт не видит; "
                 "вариант 0 — ровно пример урока",
}


def complexity(solution: str) -> int:
    """Грубый вес эталона: команды (сегменты), флаги и приёмы оболочки."""
    s = _FIELD.sub("X", _SINGLE_QUOTED.sub("''", solution))
    segs = [x for x in _SEGMENT.split(s) if x.strip()]
    return len(segs) + len(_FLAG.findall(s)) + len(_CONSTRUCT.findall(s))


def first_variant_issues(task, add) -> None:
    from termit_app.tasks import lint
    vs = lint._variants(task)
    if task.boss or len(vs) < 2 or task.id in V0_COMPLEX_OK:
        return
    sols = [task._solution(v) for v in vs]
    if _KEYS.search(sols[0]):
        return              # эталон — клавиши словами (уроки клавиш), счёт не применим
    weights = [complexity(s) for s in sols]
    easiest = min(weights[1:])
    if weights[0] > easiest + SLACK:
        add("V003", "error", f"вариант 0 (первая встреча) тяжелее других: вес {weights} — "
                             "дай первым самый простой, составной — на повторы")


# --- N25: третья подсказка и эталон — одни команды ----------------------------------------

# эталон вправе звать команду, которой нет в третьей подсказке, — с причиной
HINT3_OK: Dict[str, str] = {
    "z_jump": "d1…d4 — имена папок в эталоне (z d1 d2), а не команды",
    "man_flag": "cmd в эталоне — заглушка «man КОМАНДА»; третья подсказка называет флаг",
    "json_config": "python3 -m json.tool в эталоне — проверка после правки, подсказка — сама "
                   "правка в nano",
    "constraints_fk": "load — слово SQL-файла в эталоне (.read load.sql), а не команда",
}


def _strip_fields(text: str) -> str:
    return _FIELD.sub("X", text).replace("{{", "{").replace("}}", "}")


def hint3_issues(task, add) -> None:
    from termit_app.tasks import lint
    if task.boss or task.id in HINT3_OK:
        return
    prog = lint._implant_program(task)
    for i, v in enumerate(lint._variants(task)):
        hints = lint._raw_hints(task, v)
        if len(hints) < 3 or lint.py_built(task, i):
            continue
        sol = lint.command_words(_strip_fields(task._solution(v)))
        third = lint.command_words(_strip_fields(hints[2]))
        extra = sol - third - {"ans", prog}
        if extra:
            add("S008", "error", f"вариант {i}: в эталоне {sorted(extra)}, а в третьей "
                                 "подсказке их нет — подсказка №3 и разбор расходятся")


# --- N11: команда к задаче уже звучала раньше по пути игрока ------------------------------

def _required_tracks(key: str, acc: Optional[Set[str]] = None) -> Set[str]:
    from termit_app.tasks import registry
    acc = set() if acc is None else acc
    tasks = registry.all_tasks()
    for boss in registry.track(key).requires:
        tk = tasks[boss].track
        if tk not in acc:
            acc.add(tk)
            _required_tracks(tk, acc)
    return acc


def guaranteed_before(task, _memo: Optional[Dict[str, Set[str]]] = None) -> Set[str]:
    """Задачи, которые игрок точно встретил до этой на любом пути: места-предки целиком
    (страж места выдаётся, когда свежих в нём нет), своё место до неё и after с их
    предшественниками. Параллельно открытые места (tools и finder) — не в счёт: круг выдачи
    может пустить любое из них первым."""
    from termit_app.tasks import registry
    memo = {} if _memo is None else _memo
    if task.id in memo:
        return memo[task.id]
    memo[task.id] = set()
    tasks = registry.all_tasks()
    out = set()
    for tk in _required_tracks(task.track):
        out |= {t.id for t in registry.tasks_of(tk) if t.boss or not t.after}
    for t in registry.tasks_of(task.track):
        if t.id == task.id:
            break
        if not t.boss and not t.after:
            out.add(t.id)
    for dep in task.after:
        out.add(dep)
        out |= guaranteed_before(tasks[dep], memo)
    memo[task.id] = out
    return out


def path_taught(task) -> Set[str]:
    from termit_app.tasks import lint, registry
    tasks = registry.all_tasks()
    out = set(lint.BASE_COMMANDS) | lint.EXTRA_OK.get(task.id, set())
    out |= lint.scroll_tokens(task.scroll or "")
    for tid in guaranteed_before(task):
        out |= lint.scroll_tokens(tasks[tid].scroll or "")
    return out


def path_issues(task, add) -> None:
    from termit_app.tasks import lint
    taught = path_taught(task) | {lint._implant_program(task)}
    for i, v in enumerate(lint._variants(task)):
        hints = lint._raw_hints(task, v)
        if lint.py_built(task, i):
            continue
        used = lint.command_words(_strip_fields(task._solution(v)))
        used |= lint.command_words(_strip_fields(hints[2] if len(hints) > 2 else ""))
        miss = used - taught
        if miss:
            add("S009", "error", f"вариант {i}: {sorted(miss)} — по пути игрока ещё не "
                                 "звучали (своё место до задачи, места-предки, after)")


# --- N21: первая задача места — один вопрос ------------------------------------------------

_TWO_ANSWERS = re.compile(r"ans [A-ZА-ЯЁ_]{2,}[ ,]+[A-ZА-ЯЁ_]{2,}")
# второй вопрос без заглушки: два «?» в тексте или связка «…? И сколько/какой…»
_SECOND_QUESTION = re.compile(r"\?[^?]*\?|\?\s+(?:И|А)\s+(?:сколько|какой|какая|какое|кто|где)",
                              re.I)


def two_questions(text: str) -> Optional[str]:
    """Чем текст просит два ответа сразу (None — один вопрос)."""
    m = _TWO_ANSWERS.search(text) or _SECOND_QUESTION.search(text)
    return m.group() if m else None


def first_of_track(task) -> bool:
    from termit_app.tasks import registry
    first = next((t for t in registry.tasks_of(task.track) if not t.boss and not t.after),
                 None)
    return first is not None and first.id == task.id


def one_question_issues(task, add) -> None:
    from termit_app.tasks import lint
    if not first_of_track(task):
        return
    vs = lint._variants(task)
    found = two_questions(vs[0].text) if vs else None
    if found:
        add("Q001", "error", f"первая задача места просит два ответа сразу ({found!r}): "
                             "один вопрос")


def static_issues(task, lesson: Optional[str], add) -> None:
    lesson_issues(task, lesson, add)
    first_variant_issues(task, add)
    hint3_issues(task, add)
    path_issues(task, add)
    one_question_issues(task, add)
