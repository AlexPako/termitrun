"""Работа сверх расписания: репетиция стража, срочные заказы, выгодный ран после перерыва.

Тексты — в темах; здесь только правила. Ставок, штрафов и счётчиков упущенного нет."""
from datetime import date, timedelta
from typing import List, Optional

from termit_app import implants, progress, theme
from termit_app.tasks import registry

REHEARSAL_PRICE = 20            # × ярус трека; первая после провала — даром
URGENT_WINDOW_DAYS = 2          # срочный заказ живёт 2 календарных дня после предложения
URGENT_CHANCE = 0.30            # шанс предложения в конце рана, если заказа нет
URGENT_BONUS = 20               # × ярус трека — премия сверх обычной оплаты дела
URGENT_MIN_DAYS = 7             # не в первую неделю
COMEBACK_ABSENCE = 4            # выгодный ран — после стольких пропущенных дней подряд
COMEBACK_EVERY = 14             # и не чаще, чем раз в столько дней
COMEBACK_TASKS = 3
COMEBACK_PAY_MULT = 2           # ×2 за звезду
COMEBACK_PER_DAY = 10           # премия за день отсутствия
COMEBACK_MAX = 100

# нейтральные строки; тема заменяет своими (раздел contracts)
TEXTS = {
    "rehearse_free": "Первая репетиция — бесплатно: ./termit rehearse {id}",
    "rehearse_free_go": "Репетиция «{title}» — бесплатно: первая после провала.",
    "rehearse_ask": "Репетиция «{title}»: {price} {cash}. Тренировка — подсказки даром, "
                    "без таймера; ни денег, ни расписания она не меняет, и день в серию не идёт. Начать?",
    "rehearse_money": "Репетиция стоит {price} {cash}, а у тебя {money}.",
    "rehearse_beaten": "«{title}» уже побеждён — повторить можно тренировкой: ./termit play {id}",
    "rehearse_locked": "«{title}» пока за закрытой дверью — сначала открой его место.",
    "rehearse_not_boss": "Репетируют только боссов. Обычную задачу — ./termit play {id}",
    "rehearse_unknown": "Нет такой задачи: {id}. Список: ./termit list",
    "rehearse_shop": "🎭 Репетиция «{title}» — {price}: ./termit rehearse {id}",
    "rehearse_shop_free": "бесплатно",
    "urgent_offer": "💼 Срочный заказ: «{title}» — {until}, +{bonus} {cash}",
    "urgent_header": "💼 Срочный заказ: «{title}» — {until}, +{bonus} {cash}",
    "urgent_paid": "💼 Срочный заказ закрыт: +{bonus} {cash}",
    # выгодный ран — только радость возвращения: ни серии, ни потерь, ни пропущенных дней (М7)
    "comeback_banner": "Выгодный ран: знакомые дела тренировкой — без таймера, подсказки "
                       "даром (звезду, правда, съедают). За звезду ×2, премия в конце.",
    "comeback_banner_new": "Выгодный ран: знакомые дела и одно новое, тренировкой — без "
                           "таймера, подсказки даром (звезду, правда, съедают). За звезду ×2, "
                           "премия в конце.",
    "comeback_voice": "",
    "comeback_paid": "Выгодный ран: премия +{bonus} {cash}",
}


def text(key: str, **kw) -> str:
    return ((theme.story("contracts") or {}).get(key) or TEXTS[key]).format(**kw)


# --- Репетиция стража (E10) ----------------------------------------------------------------

def failed(p: dict, boss_id: str) -> bool:
    """Страж не взломан, но дело по нему уже было — значит, проваливал."""
    rec = p["tasks"].get(boss_id) or {}
    return boss_id not in p["bosses"] and rec.get("jobs", 0) > 0


def failed_bosses(p: dict) -> List[str]:
    return [t.id for t in registry.all_tasks().values() if t.boss and failed(p, t.id)]


def rehearsal_price(p: dict, boss_id: str) -> int:
    if failed(p, boss_id) and boss_id not in p["rehearsal_free_used"]:
        return 0
    return REHEARSAL_PRICE * progress.tier(registry.get(boss_id).track)


def can_rehearse(p: dict, boss_id: str) -> str:
    """Код: ok|unknown|not_boss|beaten|locked."""
    if boss_id not in registry.all_tasks():
        return "unknown"
    task = registry.get(boss_id)
    if not task.boss:
        return "not_boss"
    if boss_id in p["bosses"]:
        return "beaten"
    if task.track not in {t.key for t in registry.unlocked(p["bosses"])}:
        return "locked"
    from termit_app import session      # стража, до которого не дошли, не репетируют
    if session.boss_waiting(p, task):
        return "locked"
    return "ok"


# --- Срочные заказы (E11) ------------------------------------------------------------------

def _available(task) -> bool:
    return all(implants.which(n) for n in task.needs) and task.missing() is None


def _job_ready(p: dict, task_id: str) -> bool:
    """Знакомое дело: не страж, уже было делом, не ждёт тренировки, программы на месте."""
    tasks = registry.all_tasks()
    rec = p["tasks"].get(task_id)
    if task_id not in tasks or rec is None or tasks[task_id].boss:
        return False
    return (rec.get("jobs", 0) >= 1 and progress.mode_for(p, task_id) == "job"
            and _available(tasks[task_id]) and registry.after_done(p, tasks[task_id]))


def expire(p: dict, today: date) -> None:
    """Просроченный или ставший невозможным заказ молча исчезает: ни строки, ни счётчика."""
    u = p.get("urgent")
    if u and (today.isoformat() > u["expires"] or not _job_ready(p, u["task"])):
        p["urgent"] = None


def offer_urgent(p: dict, today: date, rng) -> Optional[dict]:
    """В конце рана: заказа нет, сыграно не меньше недели, сегодня заказ ещё не предлагали,
    выпал шанс — новый заказ (играется с завтрашнего дня)."""
    if (p.get("urgent") or len(p["days"]) < URGENT_MIN_DAYS
            or p.get("urgent_day") == today.isoformat() or rng.random() >= URGENT_CHANCE):
        return None
    pool = sorted(t for t in p["tasks"] if _job_ready(p, t)
                  and p["tasks"][t].get("last_solved") != today.isoformat())
    if not pool:
        return None
    tid = rng.choice(pool)
    p["urgent_day"] = today.isoformat()        # не больше одного предложения в день
    p["urgent"] = {"task": tid, "created": today.isoformat(),
                   "expires": (today + timedelta(days=URGENT_WINDOW_DAYS)).isoformat(),
                   "bonus": URGENT_BONUS * progress.tier(registry.get(tid).track)}
    return p["urgent"]


def urgent_task(p: dict, today: Optional[date] = None) -> Optional[str]:
    """Задача заказа. С today — только заказ в работе: предложенный сегодня ждёт завтра,
    иначе второй ран того же дня сразу закрыл бы его и получил новый."""
    u = p.get("urgent") or {}
    if today is not None and u.get("created", "") >= today.isoformat():
        return None
    return u.get("task")


def inject(p: dict, queue: List[str], today: date) -> List[str]:
    """Заказ — в очередь как дело, вне лимита повторений: перед схваткой, иначе в конец."""
    expire(p, today)
    tid = urgent_task(p, today)
    if not tid or tid in queue:
        return list(queue)
    tasks = registry.all_tasks()
    out = list(queue)
    at = next((n for n, i in enumerate(out) if i in tasks and tasks[i].boss), len(out))
    out.insert(at, tid)
    return out


def settle(p: dict, task_id: str, outcome: str, stars: int,
           today: Optional[date] = None) -> int:
    """Исход дела по заказу: решено — премия; сдался или провал — заказ закрыт без укора;
    skip/quit — остаётся до срока. Вернуть премию. Заказ, предложенный сегодня, не в работе."""
    if urgent_task(p, today) != task_id:
        return 0
    if outcome == "solved" and stars >= 1:
        bonus = p["urgent"]["bonus"]
        p["money"] += bonus
        p["urgent"] = None
        return bonus
    if outcome not in ("skip", "quit", None):
        p["urgent"] = None
    return 0


def urgent_line(p: dict, today: date, key: str = "urgent_header") -> Optional[str]:
    from termit_app import ui
    u = p.get("urgent")
    if not u or (key == "urgent_header" and urgent_task(p, today) is None):
        return None             # заголовок рана — только про заказ в работе
    return text(key, title=theme.title(registry.get(u["task"])),
                until=ui.until(u["expires"], today), bonus=u["bonus"], cash=theme.word("money"))


# --- Выгодный ран после перерыва (E12) -----------------------------------------------------

def comeback(p: dict, today: date) -> Optional[dict]:
    """Вернулся после перерыва ≥ 4 дней и выгодного рана не было 14 дней — премия за возврат.
    Никакого наказания: просто тёплый разогрев."""
    if not p["days"]:
        return None
    last = date.fromisoformat(max(p["days"]))
    absent = (today - last).days - 1
    if absent < COMEBACK_ABSENCE:
        return None
    prev = p.get("comeback_last")
    if prev and (today - date.fromisoformat(prev)).days < COMEBACK_EVERY:
        return None
    return {"absent": absent, "bonus": min(COMEBACK_MAX, COMEBACK_PER_DAY * absent)}


def comeback_known(p: dict) -> List[str]:
    """Освоенные знакомые задачи (решены хоть раз, не ждут тренировки, не стражи, доступны),
    сначала самые сильные: «руки помнят» (М1)."""
    tasks = registry.all_tasks()
    pool = [tid for tid, rec in p["tasks"].items()
            if tid in tasks and not tasks[tid].boss and rec.get("solved", 0) > 0
            and not rec.get("retrain") and _available(tasks[tid])
            and registry.after_done(p, tasks[tid])]
    pool.sort(key=lambda t: (-p["tasks"][t].get("level", 0),
                             -p["tasks"][t].get("last_stars", 0), t))
    return pool


def comeback_queue(p: dict, n: int = COMEBACK_TASKS) -> List[str]:
    """Выгодный ран (М1): до n самых сильных освоенных дел и одно новое из открытых мест, если
    есть. Всё — тренировкой (без таймера, подсказки даром), а платится за звезду ×2. Вариант
    знакомого дела — свежий: run_task выдаёт не тот, что был в прошлый раз. Знакомых нет —
    пусто (обычный ран)."""
    known = comeback_known(p)[:n]
    if not known:
        return []
    from termit_app import session
    # страж — только экзаменом: тренировкой он прошёл бы без записи в bosses (I1 ревью C2)
    fresh = [t for t in session.next_new(p, len(registry.TRACKS) * 2)
             if not registry.get(t).boss]
    return known + fresh[:1]


def comeback_stars(solved: bool, hints: int) -> int:
    """Звёзды выгодного рана: таймера нет, подсказка (даром) забирает звезду."""
    return progress.stars_for(solved, hints, 0, 0, first_time=True)


def pay_comeback(p: dict, bonus: int, today: date) -> int:
    p["money"] += bonus
    p["comeback_last"] = today.isoformat()
    return bonus
