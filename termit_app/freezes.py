"""Заморозки для слабого игрока (C2, М4): заработать навыком регулярности и понять, что это.

- Заработанная заморозка: 3 рана (сыгранных дня) за любые 7 календарных дней → +1 в запас
  p["freezes"] (тот же запас, что у купленных), не чаще раза в 7 дней. Дни, за которые уже
  дали, второй раз не идут (p["freeze_earned"] — день последней выдачи). Заработать можно
  только до FREEZE_CAP = 2; модуль «морозилка» (3) — только для купленных.
- Бесплатная заморозка недели (progress._walk) не меняется: одна на ISO-неделю.
- Объяснение: в первый раз, когда заморозка выдана или сработала (бесплатная или из запаса),
  одна тёплая строка — что это, зачем, сколько держать. Флаг FLAG в p["flags"].

Тексты — раздел темы freezes; здесь нейтральные запасные."""
from datetime import date, timedelta

from termit_app import progress, theme

EARN_RUNS = 3           # сыгранных дней
EARN_WINDOW = 7         # за столько календарных дней (сегодня включительно)
EARN_CAP = progress.FREEZE_CAP     # заработать — до 2; «морозилка» (3) — только купленным
FLAG = "freeze_explained"

TEXTS = {
    "explain": "❄ Заморозка прощает серии пропущенный день: одна в неделю даром, ещё одна — "
               "за 3 рана за 7 дней. В запасе до {cap}, тратится сама.",
    "earned": "❄ Три рана за неделю — заморозка в запас. Теперь их: {left}.",
    "spent": "❄ Заработанная заморозка закрыла пропуск (×{n}) — серия жива. В запасе: {left}.",
}


def text(key: str, **kw) -> str:
    return ((theme.story("freezes") or {}).get(key) or TEXTS[key]).format(**kw)


def earn(p: dict, today: date) -> int:
    """После закрытия дня: 3 сыгранных дня за 7 календарных (после прошлой выдачи, не чаще
    раза в 7 дней) → +1 заморозка, если в запасе меньше 2. Вернуть, сколько выдано (0 или 1)."""
    if p.get("freezes", 0) >= EARN_CAP:
        return 0
    last = p.get("freeze_earned") or ""
    if last > today.isoformat():
        last = ""           # дата из будущего (сбой часов) — как не было (M5 ревью C2)
    if last and (today - date.fromisoformat(last)).days < EARN_WINDOW:
        return 0            # не чаще раза в 7 дней (econ_sim: иначе слабый копит сверх коридора)
    start = (today - timedelta(days=EARN_WINDOW - 1)).isoformat()
    days = {d for d in p.get("days", ()) if start <= d <= today.isoformat() and d > last}
    if len(days) < EARN_RUNS:
        return 0
    p["freezes"] = p.get("freezes", 0) + 1
    p["freeze_stock_earned"] = p.get("freeze_stock_earned", 0) + 1
    p["freeze_earned"] = today.isoformat()
    return 1


def split_spent(p: dict, n: int):
    """settle потратил n заморозок из запаса: сколько из них купленных и сколько заработанных
    (заработанные — первыми). Учёт заработанных в запасе (p["freeze_stock_earned"]) уменьшается.
    Вернуть (купленных, заработанных) — у каждой своя строка в итоге рана (M1 ревью C2)."""
    have = max(0, min(p.get("freeze_stock_earned", 0), p.get("freezes", 0) + n))
    used = min(have, n)
    p["freeze_stock_earned"] = have - used
    return n - used, used


def lines(p: dict, froze: dict, earned: int) -> list:
    """Строки итога рана: выдана заморозка; в первый раз выдана или сработала — объяснение."""
    out = [text("earned", left=p.get("freezes", 0))] if earned else []
    fired = bool(froze.get("free") or froze.get("bought"))
    if (earned or fired) and FLAG not in (p.get("flags") or ()):
        p.setdefault("flags", []).append(FLAG)
        out.append(text("explain", cap=progress.freeze_cap(p)))   # с «морозилкой» — 3 (M7)
    return out
