"""Контракт недели (C2, М5): недельный ритм без таймера и без FOMO.

Цель календарной (ISO) недели — 4 рана в разные дни ИЛИ 12 решённых дел (только дела обычных
ранов: тренировки, круг мастера и play не в счёт — M2 ревью C2): какой путь удобнее,
тот игрок и выбирает своей игрой — засчитывается первый выполненный. Награда — WEEK_PAY
кредитов, один раз за неделю. Часов и минут нет нигде: срок — «до понедельника». Невыполненный
контракт тихо сменяется новым в понедельник: ни штрафа, ни строки о провале, ни счётчика.

Состояние — p["weekly"] = {"week": "ГГГГ-Wнн", "solved": n, "paid": bool}; сыгранные дни
недели считаются по p["days"]. Тексты — раздел темы weekly; здесь нейтральные запасные."""
from datetime import date
from typing import Optional

from termit_app import theme

WEEK_RUNS = 4           # ранов в разные дни недели
WEEK_SOLVED = 12        # или решённых дел за неделю
WEEK_PAY = 30           # награда (сверено с econ_sim, см. отчёт C2)

TEXTS = {
    "title": "📋 Контракт недели: {runs} из {need_runs} ранов в разные дни или {solved} из "
             "{need_solved} решённых дел — как тебе удобнее; до понедельника, +{pay} {cash}.",
    "done": "📋 Контракт недели закрыт. Новый — с понедельника.",
    "paid": "📋 Контракт недели закрыт: +{pay} {cash}.",
    # шапка рана — одной строкой (P2 Б6); целиком — в убежище (line)
    "short": "📋 Контракт недели: ранов {runs}/{need_runs} или дел {solved}/{need_solved}, "
             "+{pay} {cash}",
    "short_done": "📋 Контракт недели закрыт. Новый — с понедельника.",
}
SHOW_FROM_DAY = 3       # в шапке рана — с 3-го дня игры (дни с ранами): первые дни — терминал


def text(key: str, **kw) -> str:
    val = (theme.story("weekly") or {}).get(key) or TEXTS[key]
    return val.format(**kw) if kw else val


def week_key(day: date) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def fresh(day: Optional[date]) -> dict:
    return {"week": week_key(day) if day else "", "solved": 0, "paid": False}


def clean(raw) -> dict:
    """Испорченное сохранение — пустой контракт (загрузка progress)."""
    if (not isinstance(raw, dict) or not isinstance(raw.get("week"), str)
            or not isinstance(raw.get("solved"), int) or isinstance(raw.get("solved"), bool)
            or raw["solved"] < 0 or not isinstance(raw.get("paid"), bool)):
        return fresh(None)
    return {"week": raw["week"], "solved": raw["solved"], "paid": raw["paid"]}


def state(p: dict, day: date) -> dict:
    """Контракт этой недели; запись прошлой недели тихо заменяется новой."""
    st = clean(p.get("weekly"))
    if st["week"] != week_key(day):
        st = fresh(day)
    p["weekly"] = st
    return st


def runs(p: dict, day: date) -> int:
    key = week_key(day)
    return sum(1 for d in set(p.get("days", ())) if week_key(date.fromisoformat(d)) == key)


def note(p: dict, day: date, solved: int) -> int:
    """После закрытого дня (день уже в p["days"]): дописать решённые дела; цель выполнена —
    заплатить один раз. Вернуть выплату (0 — нет)."""
    st = state(p, day)
    st["solved"] += max(0, int(solved))
    if st["paid"] or (runs(p, day) < WEEK_RUNS and st["solved"] < WEEK_SOLVED):
        return 0
    if not visible(p, day):     # контракт ещё не показан игроку — копим молча (P2 fix1 M5)
        return 0
    st["paid"] = True
    p["money"] += WEEK_PAY
    return WEEK_PAY


def line(p: dict, day: date) -> str:
    """Строка в начале рана и в убежище."""
    st = state(p, day)
    if st["paid"]:
        return text("done")
    return text("title", runs=min(runs(p, day), WEEK_RUNS), need_runs=WEEK_RUNS,
                solved=min(st["solved"], WEEK_SOLVED), need_solved=WEEK_SOLVED, pay=WEEK_PAY,
                cash=theme.word("money"))


def visible(p: dict, day: date) -> bool:
    """Контракт в шапке рана — с SHOW_FROM_DAY-го дня игры: сыгранных дней до сегодня хватает
    (P2 Б6, psych 3.3: в первые дни новичок держит в голове сам терминал)."""
    before = {d for d in p.get("days", ()) if isinstance(d, str) and d < day.isoformat()}
    return len(before) >= SHOW_FROM_DAY - 1


def short_line(p: dict, day: date) -> str:
    """Шапка рана: одна строка."""
    st = state(p, day)
    if st["paid"]:
        return text("short_done")
    return text("short", runs=min(runs(p, day), WEEK_RUNS), need_runs=WEEK_RUNS,
                solved=min(st["solved"], WEEK_SOLVED), need_solved=WEEK_SOLVED, pay=WEEK_PAY,
                cash=theme.word("money"))
