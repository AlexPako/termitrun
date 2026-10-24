"""Пропуски и серия (владелец 24.10): «за постоянные заходы и беспрерывные раны что-то должно
прилетать бонусом, и должны быть какие-то штрафы — письмо от Гайки или Ворона: мы тебя
потеряли, жирный ран ушёл на сторону, отнимается карма, случайный товар пропал с витрины (на
время), мол, кто-то купил».

Пропуск — день между прошлым сыгранным и сегодняшним, который не закрыла заморозка серии.
Штраф — один раз за возвращение: карма (не ниже нуля), а с SOLD_FROM дней — ещё и случайная
позиция витрины «раскуплена» на SOLD_DAYS дней. Прогресс уроков штраф не трогает никогда.
Серия — надбавка к закрытию дня: STREAK_DAILY кредитов за день серии, не больше STREAK_CAP."""
import random
from datetime import date, timedelta
from typing import Optional

KARMA_PER_DAY = 15
KARMA_CAP = 60
SOLD_FROM = 2
SOLD_DAYS = 3
STREAK_DAILY = 2
STREAK_CAP = 20


def missed_days(p: dict, today: date) -> int:
    """Дни после прошлого сыгранного, не закрытые заморозкой (frozen_days)."""
    days = sorted(d for d in p.get("days", []) if isinstance(d, str) and d < today.isoformat())
    if not days:
        return 0
    try:
        last = date.fromisoformat(days[-1])
    except ValueError:
        return 0
    frozen = p.get("frozen_days") or {}
    gap = (today - last).days - 1
    return sum(1 for k in range(1, gap + 1) if (last + timedelta(days=k)).isoformat() not in frozen)


def sold_out(p: dict, item_id: str, today: date) -> bool:
    until = (p.get("sold_out") or {}).get(item_id)
    return isinstance(until, str) and until > today.isoformat()


def apply(p: dict, today: date, rng: Optional[random.Random] = None) -> Optional[dict]:
    """Штраф за пропуск — один раз в день возвращения. {missed, karma, sold} или None."""
    missed = missed_days(p, today)
    if missed <= 0 or p.get("absence_day") == today.isoformat():
        return None
    p["absence_day"] = today.isoformat()
    loss = min(KARMA_PER_DAY * missed, KARMA_CAP, max(p.get("xp", 0), 0))
    p["xp"] = p.get("xp", 0) - loss
    sold = None
    if missed >= SOLD_FROM:
        from termit_app import shop
        pool = [i for i in shop.visible(p, today) if not i.consumable]
        if pool:
            item = (rng or random.Random()).choice(pool)
            until = (today + timedelta(days=SOLD_DAYS + 1)).isoformat()
            p.setdefault("sold_out", {})[item.id] = until
            sold = item
    return {"missed": missed, "karma": loss, "sold": sold}


def streak_pay(p: dict, streak: int) -> int:
    """Надбавка серии к закрытию дня: чем дольше серия, тем больше (до потолка)."""
    pay = min(STREAK_DAILY * max(streak, 0), STREAK_CAP) if streak >= 2 else 0
    p["money"] = p.get("money", 0) + pay
    return pay
