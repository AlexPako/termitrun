"""Карма как репутация (C2, М6): пять ступеней по порогам кармы, видны в убежище и stats, а в
итоге рана — только при смене ступени (P2 Б6). Карма не тратится — ступень только называет, кем тебя считает город.

Одна ступень (REWARD_LEVEL) открывает рамку «Репутация» (REWARD): косметика без
преимущества, за деньги не продаётся (её нет в каталоге витрины) — она просто появляется в
гардеробе (p["owned"]) и надевается через ./termit style frame rep. Тексты — раздел темы
repute; здесь нейтральные запасные."""
from typing import List

from termit_app import progress, theme

THRESHOLDS = (0, 300, 1500, 4000, 8000)     # карма; у типичного к 90-му дню ≈ 4 800
REWARD = "frame_rep"
REWARD_LEVEL = 3

TEXTS = {
    "titles": ["новое лицо", "примелькался", "свой человек", "имя на слуху", "живая легенда"],
    "line": "🎖 Репутация: {title}",
    "next": "до «{next}» — {need} {xp}",
    "up": "🎖 Новая репутация: {title}.",
    "reward": "В гардеробе — рамка «Репутация», её не купить: ./termit style frame rep",
}


def text(key: str, **kw) -> str:
    val = (theme.story("repute") or {}).get(key) or TEXTS[key]
    return val.format(**kw) if kw else val


def title_name(lvl: int) -> str:
    names = (theme.story("repute") or {}).get("titles") or TEXTS["titles"]
    return names[max(0, min(lvl, len(names) - 1))]


def level_of(karma: int) -> int:
    return max(k for k, need in enumerate(THRESHOLDS) if karma >= need)


def level(p: dict) -> int:
    return level_of(progress.karma(p))


def grant(p: dict) -> List[str]:
    """Ступень с наградой достигнута — рамка в гардероб (один раз). Вернуть выданное."""
    if level(p) < REWARD_LEVEL or REWARD in (p.get("owned") or ()):
        return []
    p.setdefault("owned", []).append(REWARD)
    return [REWARD]


def line(p: dict, with_next: bool = False) -> str:
    """«🎖 Репутация: …»; with_next — и сколько кармы до следующей ступени (убежище)."""
    lvl = level(p)
    out = text("line", title=title_name(lvl))
    if with_next and lvl + 1 < len(THRESHOLDS):
        out += " · " + text("next", next=title_name(lvl + 1),
                            need=THRESHOLDS[lvl + 1] - progress.karma(p),
                            xp=theme.word("xp_gen"))
    return out


def summary_lines(p: dict, karma_before: int) -> List[str]:
    """Строки итога рана: только когда ступень выросла — событие и, если дана рамка, где её
    найти. Без смены ступени — ничего (P2 Б6): в убежище и stats она видна всегда."""
    lvl = level(p)
    if lvl > level_of(karma_before):
        out = [text("up", title=title_name(lvl))]
        if grant(p):
            out.append(text("reward"))
        return out
    grant(p)            # старое сохранение, где порог взят раньше: рамка молча на месте
    return []
