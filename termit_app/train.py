"""Отработка (train, спека 2.6): кого повторять и что сказать. Запуск — session.train_run.
Не платит, не даёт кармы, не держит серию и не двигает расписание; считает всё из задач,
своего хранит только лучший экзамен (p["train"])."""
import random
from datetime import date, timedelta
from typing import List, Optional, Tuple

from termit_app import book, edition, progress, session, theme, ui
from termit_app.tasks import registry

WEAK_FROM = 40
DRILL_SIZE = 3
EXAM_SIZE = 5
EXAM_PER_PLACE = 2
SOLID_LEVEL = 3                 # «закреплено» — интервал от недели

# Тексты печатаются и в разовом ./termit train: команды — с ./termit (в убежище фильтр ui
# снимает префикс), вместо «Enter» — run: оно верно в обоих режимах (финальное ревью В-4)
NOTHING = ("Отрабатывать пока нечего: здесь повторяют только пройденное. Начни с рана "
           "дня — ./termit run. Завтра тут будет что подтянуть.")
IN_RUN = ("Всё, что можно повторить, уже ждёт тебя в ране дня — там оно и засчитается. "
          "Сначала ран: ./termit run.")
DONE_TODAY = ("На сегодня отработано. Память крепнет с перерывом — завтра ран проверит, "
              "как держится.")
NO_WEAK = "Слабых мест нет: всё пройденное держится. Можно так:"
NOT_MET = ("Эту задачу ты ещё не встречал — она придёт в ране. Новое сейчас: "
           "./termit new.")
GUARD = ("Это страж — его пробуют по-настоящему. Потренироваться: ./termit rehearse {id} "
         "(первая после провала — даром).")
GUARD_BEATEN = ("Это страж — отработка стражей не трогает. Взломанного можно сыграть заново: "
                "./termit rehearse {id}.")
CLOSED_TASK = "«{title}» сейчас не собрать на этом компьютере. Попробуй другую."
TOPIC_EMPTY = "По теме «{topic}» сейчас нечего отрабатывать — всё в ране дня или уже сегодня."
FEW_FOR_EXAM = ("Для экзамена нужно 5 знакомых заданий — пройди ещё пару ранов. "
                "Отработанное сегодня отдыхает до завтра.")
UNKNOWN = ("Нет такой темы: {topic}. Места: {places}. Команды: {cmds}. Клавиши — "
           "./termit train keys.")


def score(rec: dict) -> int:
    """Балл слабости (learn §3.2). Время не считаем: «освоено» меряет знание."""
    total = 100 if rec.get("retrain") else 0
    if progress.weak(rec):
        total += 40
    total += 15 * min(rec.get("lapses") or 0, 3)
    if (rec.get("first_hints") or 0) > 0 and (rec.get("level") or 0) < 2:
        total += 10
    return total


def _opened(p: dict) -> set:
    """Места, открытые игроку: стражи взяты и место есть в издании."""
    return {tr.key for tr in registry.unlocked(p["bosses"])}


def drillable(p: dict) -> List[str]:
    """Встреченные задачи, которые отработка вообще берёт: открытое место, не страж (спека
    2.6: train стражей не трогает — их пробуют делом и репетицией), замок пары снят,
    собираются. Без учёта дня — это делает candidates."""
    tasks = registry.all_tasks()
    opened = _opened(p)
    out = []
    for tid in p["tasks"]:
        task = tasks.get(tid)
        if task is None or task.boss or task.track not in opened:
            continue
        if not session.after_done(p, task) or not session.available(task):
            continue
        out.append(tid)
    return out


def candidates(p: dict, day: date) -> List[str]:
    """Что можно отработать сегодня: drillable без сегодняшнего среза рана и без
    отработанного сегодня. Пульт зовёт это под pyenvs.cache_only (без подпроцессов)."""
    busy = set(session.today_reviews(p, day))
    iso = day.isoformat()
    return [t for t in drillable(p) if t not in busy and p["tasks"][t].get("drill_day") != iso]


def _stale(rec: dict) -> str:
    return rec.get("drill_day") or rec.get("last_solved") or rec.get("first_day") or ""


def weak_ids(p: dict, day: date) -> List[str]:
    ids = [t for t in candidates(p, day) if score(p["tasks"][t]) >= WEAK_FROM]
    ids.sort(key=lambda t: (-score(p["tasks"][t]), _stale(p["tasks"][t])))
    return ids


def places(p: dict) -> List[str]:
    return [tr.key for tr in registry.unlocked(p["bosses"]) if edition.track_open(tr.key)
            and any(progress.seen(p, t.id) for t in registry.tasks_of(tr.key))]


def commands_of(p: dict) -> List[str]:
    """Команды для train КОМАНДА — только из задач, которые отработка берёт (drillable): без
    стражей и несобираемых, иначе тема честно пуста, но с неверной причиной."""
    tasks = registry.all_tasks()
    out = []
    for tid in drillable(p):
        for name in book.command_names(tasks[tid].spell):
            if name not in out:
                out.append(name)
    return out


def topic_ids(p: dict, day: date, topic: str) -> Optional[List[str]]:
    tasks = registry.all_tasks()
    if topic in places(p):
        pool = [t for t in candidates(p, day) if tasks[t].track == topic]
    elif topic in commands_of(p):
        pool = [t for t in candidates(p, day) if topic in book.command_names(tasks[t].spell)]
    else:
        return None
    pool.sort(key=lambda t: (score(p["tasks"][t]) < WEAK_FROM, _stale(p["tasks"][t])))
    return pool[:DRILL_SIZE]


# FB13 (FB5 п. 45 в): вид отработки «сделай клавишами» — уроки строки ввода, истории, экрана
# и буфера. Проверка у них и так по результату (файлы, сданное слово): без приёма решить
# можно, но долго — отработка гоняет именно руки. Порядок — как в игре.
KEYS = "keys"
KEY_TASKS = ("line_edit", "cursor_clip", "cut_paste", "history_recall", "screen_scroll",
             "screen_find", "quick_fix", "job_control")


def keys_ids(p: dict, day: date) -> List[str]:
    """train keys: встреченные уроки клавиш, что можно отработать сегодня, — слабые первыми,
    потом давно не трогавшие; не больше DRILL_SIZE."""
    pool = [t for t in candidates(p, day) if t in KEY_TASKS]
    pool.sort(key=lambda t: (score(p["tasks"][t]) < WEAK_FROM, _stale(p["tasks"][t])))
    return pool[:DRILL_SIZE]


def exam_pool(p: dict, day: date, place: Optional[str] = None) -> List[str]:
    """Знакомые решённые задачи для экзамена; меньше EXAM_SIZE — экзамена нет."""
    tasks = registry.all_tasks()
    pool = [t for t in candidates(p, day) if (p["tasks"][t].get("solved") or 0) > 0
            and (place is None or tasks[t].track == place)]
    return pool if len(pool) >= EXAM_SIZE else []


def reason(rec: dict, day: date) -> str:
    """Почему задача в списке — коротко, для строки списка отработки."""
    tomorrow = (day + timedelta(days=1)).isoformat()
    lapses = min(rec.get("lapses") or 0, 3)        # потолок, как в балле: «3 раза»
    if rec.get("due") == tomorrow and not rec.get("level") and progress.weak(rec):
        return "сегодня в ране не вышло"
    if rec.get("retrain"):
        return "в прошлый раз не вышло"
    if lapses >= 2:
        return f"задача сбивалась {lapses} раза"
    if progress.weak(rec):
        return "в прошлый раз ушла подсказка"
    return "ты давно её не трогал"


def single_problem(p: dict, task_id: str, day: Optional[date] = None) -> Optional[str]:
    """train ID: почему эту задачу сейчас не отработать (None — можно). С днём day — ещё
    правила дня (спека 2.6): задача из сегодняшнего рана и отработанная сегодня не берутся."""
    task = registry.get(task_id)
    if not edition.track_open(task.track):
        return edition.LOCKED.format(place=theme.place(task.track))
    if not progress.seen(p, task_id):
        return NOT_MET
    if task.boss:
        return (GUARD_BEATEN if task_id in p["bosses"] else GUARD).format(id=task_id)
    if not registry.place_open(p, task):
        guards = [b for b in registry.track(task.track).requires if b not in p["bosses"]]
        need = ", ".join(theme.title(registry.get(b)) for b in guards)
        return theme.msg("locked", place=theme.place(task.track), need=need)
    need = registry.missing_after(p, task)
    if need:
        return theme.msg("after_locked", title=theme.title(task),
                         need=", ".join(theme.title(registry.get(t)) for t in need))
    if not session.after_done(p, task) or not session.available(task):
        return CLOSED_TASK.format(title=theme.title(task))
    if day is not None and task_id in session.today_reviews(p, day):
        return IN_RUN
    if day is not None and p["tasks"][task_id].get("drill_day") == day.isoformat():
        return DONE_TODAY
    return None


def empty_lines(p: dict, day: date) -> List[str]:
    """Что сказать, когда слабых для train нет (learn §7)."""
    if not p["tasks"]:
        return [NOTHING]
    # слабые — только среди тех, что отработка вообще берёт: закрытая или несобираемая не
    # мешает сказать «всё уже в ране»
    weak = [t for t in drillable(p) if score(p["tasks"][t]) >= WEAK_FROM]
    busy = set(session.today_reviews(p, day))
    if weak and all(t in busy for t in weak):
        return [IN_RUN]
    if any(p["tasks"][t].get("drill_day") == day.isoformat() for t in weak):
        return [DONE_TODAY]
    menu = [NO_WEAK, "   ./termit train ТЕМА — знакомое из одного места или по одной команде",
            "   ./termit train keys — уроки клавиш: сделай руками, без перепечатки"]
    if exam_pool(p, day):
        menu.append("   ./termit train exam — 5 заданий из разных мест, на время")
    else:
        menu.append("   " + FEW_FOR_EXAM)
    menu.append("   ./termit master — круг мастера: побить свой рекорд")
    return menu


def unknown_topic(p: dict, topic: str) -> str:
    return UNKNOWN.format(topic=topic, places=", ".join(places(p)) or "пока нет",
                          cmds=", ".join(commands_of(p)[:12]) or "пока нет")


def solid(p: dict) -> Tuple[int, int]:
    """(закреплено, встречено): закреплено — уровень от SOLID_LEVEL; растёт только в ранах."""
    recs = list(p["tasks"].values())
    return sum(1 for r in recs if (r.get("level") or 0) >= SOLID_LEVEL), len(recs)


# экраны отработки (session.train_run). Вид отработки — заголовок и очередь; новый вид
# (флаги, горячие клавиши) добавляется своим TITLE_* и своей выборкой рядом с weak_ids
TITLE_WEAK = "🎯 Отработка: слабые места — без таймера, подсказки даром."
TITLE_ONE = "🎯 Отработка: одна задача — без таймера, подсказки даром."
TITLE_TOPIC = "🎯 Отработка: «{topic}» — без таймера, подсказки даром."
GYM = "  Не платит и серию не держит — это спортзал, а не работа."
START = "  Enter — начать · Ctrl+C — назад "
TITLE_KEYS = ("🎯 Отработка: клавиши — сделай руками, без перепечатки: засчитывается "
              "результат. Без таймера, подсказки даром.")
KEYS_EMPTY = ("Клавиши отрабатывать пока нечего: уроки клавиш (правка строки, история, "
              "экран) придут в ране. Уже встреченные сегодня — в ране дня или отработаны.")
TITLE_EXAM = "🎯 Экзамен: 5 заданий вперемешку, на время. Без денег и без серии."
STOPPED = "  Отработка прервана — ничего не засчитано, день не тронут."
EXAM_TAIL = "  Без денег и без серии. Слабое — в ./termit train."
OUTCOME = {"giveup": "сдался — разбор в diary", "skip": "отложено"}


def list_lines(p: dict, ids: List[str], day: date, title: str) -> List[str]:
    """Что будет в отработке и почему каждая задача в списке."""
    out = [ui.story_fill(title, "  ", "     ")]
    for tid in ids:
        name = theme.title(registry.get(tid))
        out.append(f"     • {name[:30]:<30} {reason(p['tasks'][tid], day)}")
    out.append(GYM)
    return out


def summary_lines(p: dict, day: date, results: List[dict]) -> List[str]:
    """Итог отработки (learn §6.3): что вышло, сколько слабых осталось, что снова в строю."""
    out = ["  ── Отработка " + "─" * 48]
    for r in results:
        name = theme.title(registry.get(r["id"]))[:26]
        if r["outcome"] == "solved":
            tag = "с подсказкой" if r["hints"] else "без подсказок"
            out.append(f"  ✓ {name:<26} {ui.fmt_time(r['elapsed']):>5}   {tag}")
        else:
            out.append(f"  ✗ {name:<26} {OUTCOME.get(r['outcome'], 'не вышло')}")
    fixed = [r for r in results if r["outcome"] == "solved"]
    # дальше — только то, что train ещё даст сегодня (отработанное сегодня не повторяется)
    left = len(weak_ids(p, day))
    tail = f"сегодня можно подтянуть ещё {left}" if left else "на сегодня отработано"
    out.append(f"  Подтянул {len(fixed)} из {len(results)} · {tail}")
    for r in fixed:
        if r["was_retrain"]:
            name = theme.title(registry.get(r["id"]))
            out.append(ui.story_fill(f"«{name}» снова в строю — завтра ран проверит её делом.",
                                     "  ", "  "))
    done, seen = solid(p)
    out.append(f"  Закреплено: {done} из {seen} — растёт в ранах.")
    return out


def exam_ids(p: dict, day: date, place: Optional[str] = None, rng=None) -> List[str]:
    """5 знакомых заданий без стражей (выбирает exam_pool). Без МЕСТА — вперемешку, не больше
    EXAM_PER_PLACE из одного места (чередование учит выбирать приём); с МЕСТОМ — из него.
    Пусто — экзамена нет (знакомых меньше пяти)."""
    rng = rng or random.Random()
    pool = exam_pool(p, day, place)
    rng.shuffle(pool)
    if place is not None:
        return pool[:EXAM_SIZE]
    tasks = registry.all_tasks()
    out = []
    per = {}
    for tid in pool:
        key = tasks[tid].track
        if per.get(key, 0) < EXAM_PER_PLACE:
            out.append(tid)
            per[key] = per.get(key, 0) + 1
    rest = [t for t in pool if t not in out]
    return (out + rest)[:EXAM_SIZE]         # мест мало — добираем, чтобы было пять


def exam_summary(p: dict, results: List[dict], place: Optional[str] = None,
                 total: Optional[int] = None) -> List[str]:
    """Итог экзамена; лучший результат места (или «all») пишем, только если чисто стало
    больше прежнего."""
    key = place or "all"
    name = theme.place(place) if place else "все места"
    n = len(results)

    def is_clean(r: dict) -> bool:
        return r["outcome"] == "solved" and not r["hints"] and r["elapsed"] <= r["par"]

    clean = sum(1 for r in results if is_clean(r))
    solved_n = sum(1 for r in results if r["outcome"] == "solved")
    unfinished = total is not None and n < total      # вышел до конца — не засчитан
    best = p["train"]["exam_best"].get(key)
    better = not unfinished and (best is None or clean > best[0])
    if better:
        p["train"]["exam_best"][key] = [clean, n]
    out = [f"  ── Экзамен: {name} " + "─" * 40]
    for r in results:
        title = theme.title(registry.get(r["id"]))[:24]
        if r["outcome"] != "solved":
            out.append(f"  ✗ {title:<24} {OUTCOME.get(r['outcome'], 'не вышло')}")
            continue
        times = f"{ui.fmt_time(r['elapsed'])} / {ui.fmt_time(r['par'])}"
        if is_clean(r):
            tag = "чисто"
        elif r["hints"]:
            tag = f"подсказок: {r['hints']}"
        else:
            tag = "поздно"
        out.append(f"  {'★' if is_clean(r) else '✓'} {title:<24} {times:>13}   {tag}")
    tail = " · новый лучший!" if better and best is not None else ""
    if unfinished:
        out.append(f"  Чисто: {clean} · решено: {solved_n} из {total} — экзамен не завершён — "
                   "не засчитан")
        out.append(EXAM_TAIL)
        return out
    out.append(f"  Чисто: {clean} из {n} · решено: {solved_n} из {n}{tail}")
    out.append(EXAM_TAIL)
    return out


def stats_line(p: dict) -> str:
    done, seen = solid(p)
    line = f"Закреплено: {done} из {seen}"
    best = p.get("train", {}).get("exam_best") or {}
    if best:
        parts = [f"{'все места' if k == 'all' else theme.place(k)} {v[0]}/{v[1]}"
                 for k, v in sorted(best.items())]
        line += " · экзамен: " + ", ".join(parts)
    return line
