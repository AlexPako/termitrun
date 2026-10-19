"""Конец контента и круг мастера (C2, М2+М3).

Сезон закрыт (season_done): взломаны все стражи реестра (волна 1 и D) и в открытых местах не
осталось невстреченных задач, которые можно выдать (next_new пуст; задача без нужной утилиты
выдана быть не может и в счёт не идёт). Пока жив хоть один страж — сезон идёт: так «всё
освоено» не наступит раньше последнего экзамена. Тогда один раз звучит честное объявление
(«сезон закрыт, новые места в работе» и чем заняться), дальше — коротко: строка в
./termit more и зацепки «на завтра» из того, что живёт после сезона.

Круг мастера — знакомые дела на время, против своего рекорда:
- задачи — освоенные (решены, не ждут тренировки, программы на месте), вариант — свежий;
  взломанный страж — реванш, не больше одного за круг;
- режим тренировки: подсказки даром, расписание не двигается, рекорд времени —
  rec["best"] задачи (он и так хранится в прогрессе и виден в дневнике);
- побил рекорд без подсказок — короткая реплика (реплика персонажа вида record, П3.6) и
  MASTER_PAY × ярус, раз в день на задачу (p["master"]["paid"]); первый проход только ставит
  рекорд;
- пустых ранов не бывает: дел нет — ран из круга мастера (бывшая разминка), а после закрытия
  сезона ран без новых задач добирается кругом до MASTER_TASKS дел;
- на заказ — ./termit master.

Тексты — в теме (раздел master), здесь нейтральные запасные."""
import hashlib
import random
from datetime import date
from typing import List, Optional

from termit_app import progress, theme
from termit_app.tasks import registry

MASTER_PAY = 10         # × ярус трека — за побитый рекорд круга (раз в день на задачу)
MASTER_TASKS = 3        # после сезона ран без нового добирается кругом до стольких дел
FLAG = "season_done"    # p["flags"]: «season_done:КЛЮЧ» — объявление для этого контента было

TEXTS = {
    "announce": "Все места пройдены — сезон закрыт. Новые места в работе. Пока они едут — "
                "круг мастера: знакомые дела на время, против своего рекорда, ./termit master. "
                "Повторения, витрина, контракт недели и дневник никуда не делись.",
    "short": "Новых команд пока нет: сезон закрыт, новые места в работе. Пока — "
             "круг мастера: ./termit master",
    "mode": "🏁 Круг мастера — на время, без расписания, подсказки даром",
    "best": "рекорд {time}",
    "no_best": "рекорд поставишь сейчас",
    "record_paid": "🏁 Рекорд круга побит: +{pay} {cash}",
    "start": "Круг мастера: знакомые дела на время. Рекорд без подсказок — пара монет "
             "сверху; расписание не двигается.",
    "none": "Кругу мастера пока не из чего собраться: сначала освой хоть одну задачу.",
    "reviews": ["Старые дела ждут — проверим, не заржавели ли руки.",
                "Знакомые задачи. Повторишь — руки не забудут.",
                "Пара старых дел — на свежую голову они проще.",
                "Повторения по расписанию: память любит возвращения."],
    # итоги сезона — в разовом объявлении (P2 Б4): 4–6 строк, только цифры из прогресса
    "summary": {"title": "🏁 Итоги сезона",
                "days": "Дней в игре: {n}", "solved": "Решено дел: {n}",
                "bosses": "Стражей взломано: {n}", "streak": "Лучшая серия: {n} дн.",
                "records": "Лучшие рекорды: {items}"},
    "after": ["Круг мастера ждёт: побей свой рекорд — ./termit master.",
              "Повторения и круг мастера. Новые места в работе.",
              "Загляни на витрину: завоз идёт, пока ты держишь форму.",
              "Контракт недели — посмотри, сколько осталось: ./termit home."],
}


def text(key: str, **kw) -> str:
    val = (theme.story("master") or {}).get(key) or TEXTS[key]
    return val.format(**kw) if kw else val


def lines(kind: str) -> List[str]:
    """Набор строк (reviews, after). Для reviews первой идёт прежняя строка
    темы tomorrow_reviews — она остаётся одной из формулировок."""
    pool = list((theme.story("master") or {}).get(kind) or TEXTS[kind])
    if kind == "reviews":
        pool = [theme.msg("tomorrow_reviews")] + [x for x in pool
                                                  if x != theme.msg("tomorrow_reviews")]
    return pool


def tomorrow_line(p: dict, kind: str, seed: int) -> str:
    """Строка зацепки kind по зерну дня; подряд одна и та же не звучит (как реплики П3.6)."""
    pool = lines(kind)
    said = p.get("said") if isinstance(p.get("said"), dict) else {}
    key = f"~{kind}"
    left = [x for x in pool if x != said.get(key)] or pool
    line = left[seed % len(left)]
    p["said"] = dict(said, **{key: line})
    return line


# --- Конец сезона -------------------------------------------------------------------------

def season_done(p: dict) -> bool:
    """Все стражи взломаны и нового в открытых местах нет."""
    from termit_app import session
    bosses = [tid for tid, t in registry.all_tasks().items() if t.boss]
    beaten = set(p.get("bosses") or ())
    return all(b in beaten for b in bosses) and not session.next_new(p, 1)


def content_key() -> str:
    """Отпечаток набора контента — множества задач реестра (стражи в нём): новая волна —
    новый ключ, и объявление о конце сезона прозвучит снова (M4 ревью C2)."""
    ids = ",".join(sorted(registry.all_tasks()))
    return hashlib.sha256(ids.encode("utf-8")).hexdigest()[:12]


def season_flag() -> str:
    return f"{FLAG}:{content_key()}"


def announce(p: dict) -> Optional[str]:
    """Полное объявление — один раз на набор контента (флаг season_done:КЛЮЧ в p["flags"]);
    None — уже звучало или рано. Голый флаг season_done из сохранений до fix1 — объявление
    для нынешнего набора (волна 1 и D) уже было: переводим в ключ при первом же вызове (он —
    в начале каждого рана), пока набор тот же."""
    flags = p.setdefault("flags", [])
    if FLAG in flags:
        flags[:] = [x for x in flags if x != FLAG] + [season_flag()]
    if season_flag() in flags or not season_done(p):
        return None
    flags.append(season_flag())
    return text("announce")


SUMMARY_RECORDS = 3     # сколько лучших рекордов в итогах сезона


def summary_lines(p: dict) -> List[str]:
    """Итоги сезона одним коротким экраном (P2 Б4): дни, дела, стражи, лучшая серия и лучшие
    рекорды — те, что дальше всего ниже контрольного времени задачи. Без сюжета."""
    from termit_app import ui
    t = dict(TEXTS["summary"], **((theme.story("master") or {}).get("summary") or {}))
    tasks = p.get("tasks") or {}
    solved = sum(int(r.get("solved") or 0) for r in tasks.values() if isinstance(r, dict))
    out = ["  " + t["title"],
           "  " + t["days"].format(n=len(set(p.get("days") or ()))),
           "  " + t["solved"].format(n=solved),
           "  " + t["bosses"].format(n=len(set(p.get("bosses") or ()))),
           "  " + t["streak"].format(n=progress.best_streak(p.get("days") or (),
                                                           p.get("frozen_days")))]
    best = []
    for tid, r in tasks.items():
        task = registry.all_tasks().get(tid)
        b = r.get("best") if isinstance(r, dict) else None
        if task is None or not isinstance(b, (int, float)) or isinstance(b, bool) or b <= 0:
            continue
        best.append((b / max(1, task.par), theme.title(task), b))
    if best:
        top = sorted(best)[:SUMMARY_RECORDS]
        # итоги — одним экраном: рекордов столько, сколько влезает в строку (B5: длинное имя
        # «ИИ-казначей «Мерида Корп.»» не переносит строку), но хотя бы один
        items = [f"{name} {ui.fmt_time(b)}" for _, name, b in top]
        fit = 1
        while fit < len(items) and len("  " + t["records"].format(
                items=", ".join(items[:fit + 1]))) <= 78:
            fit += 1
        out.append("  " + t["records"].format(items=", ".join(items[:fit])))
    return out


# --- Круг мастера -------------------------------------------------------------------------

def pool(p: dict) -> List[str]:
    """Освоенные задачи: решены, не ждут тренировки, доступны; страж — только взломанный."""
    from termit_app import session
    beaten = set(p.get("bosses") or ())
    return [tid for tid, t in registry.all_tasks().items()
            if (p["tasks"].get(tid) or {}).get("solved", 0) > 0
            and not p["tasks"][tid].get("retrain")
            and session.available(t) and registry.after_done(p, t)
            and (not t.boss or tid in beaten)]


def queue(p: dict, rng=None, n: Optional[int] = None, exclude=()) -> List[str]:
    """Круг: n (по умолчанию 2–3) освоенных задач, не больше одного стража (реванш)."""
    rng = rng or random.Random()
    n = rng.randint(2, 3) if n is None else n
    cand = [t for t in pool(p) if t not in set(exclude)]
    rng.shuffle(cand)
    out, boss = [], False
    for tid in cand:
        if len(out) >= n:
            break
        if registry.get(tid).boss:
            if boss:
                continue
            boss = True
        out.append(tid)
    return out


SHORT_TASKS = 2         # короткий ран (./termit short) — не длиннее стольких дел


def fill(p: dict, run: List[str], rng=None, short: bool = False) -> List[str]:
    """После закрытия сезона ран без нового добирается кругом мастера до MASTER_TASKS дел
    (хотя бы одно). Короткий ран — только до SHORT_TASKS, сверх своей длины не растёт (M8
    ревью C2). До закрытия сезона — ничего."""
    if not season_done(p):
        return []
    n = max(0, SHORT_TASKS - len(run)) if short else max(1, MASTER_TASKS - len(run))
    return queue(p, rng, n, exclude=run) if n else []


def _section(p: dict, key: str) -> dict:
    sec = p.get("master")
    if not isinstance(sec, dict):
        sec = p["master"] = {"paid": {}, "pending": {}}
    if not isinstance(sec.get(key), dict):
        sec[key] = {}
    return sec[key]


def _paid(p: dict) -> dict:
    return _section(p, "paid")


def held_variant(p: dict, task_id: str, n: int, allowed) -> Optional[int]:
    """Вариант, выданный кругу и ещё не решённый (M3 ревью C2): выход и новый круг дают его
    же — подсмотреть задачу и взять «другую» нельзя. Вне 0..n-1 или недоступен — None."""
    v = _section(p, "pending").get(task_id)
    ok = isinstance(v, int) and 0 <= v < n and (not allowed or v in set(allowed))
    return v if ok else None


def hold_variant(p: dict, task_id: str, variant: int) -> None:
    _section(p, "pending")[task_id] = int(variant)


def release_variant(p: dict, task_id: str) -> None:
    _section(p, "pending").pop(task_id, None)


def pay(p: dict, task, elapsed: float, prev_best, hints: int, today: date) -> int:
    """Побитый рекорд круга: без подсказок, был прежний рекорд, сегодня за задачу не платили.
    Начислить и вернуть сумму (0 — без выплаты)."""
    if hints or prev_best is None or elapsed >= prev_best:
        return 0
    paid = _paid(p)
    if paid.get(task.id) == today.isoformat():
        return 0
    amount = MASTER_PAY * progress.tier(task.track)
    paid[task.id] = today.isoformat()
    p["money"] += amount
    return amount
