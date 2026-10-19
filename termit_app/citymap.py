"""Карта ./termit map: места (треки) — открытые, закрытые, пройденные — и где ты сейчас.

Схема строится из реестра: ярус — места с одинаковым требованием (кого из стражей взять),
ярусы соединены линиями. Места темы, для которых ещё нет задач, — строкой «за туманом».
Слова — из темы (раздел map и tracks), графика — tui; в plain — простой список словами.
Купленный стиль карты (cosmetics.map_style: метро, тепловизор) меняет в rich метки, линии и
цвета, в basic — только цвета; plain не меняется, ширины строк и слова легенды — те же."""
from typing import List, Optional

from termit_app import cosmetics, edition, icons, progress, theme, tui
from termit_app.tasks import registry


def _ui(key: str, default: str) -> str:
    return (theme.story("map") or {}).get(key) or default


def bare(place: str) -> str:
    """Название места без значка в начале: в рамке значки съезжают."""
    head, sep, tail = place.partition(" ")
    return tail if sep and not any(ch.isalnum() for ch in head) else place


def _state(p: dict, tr) -> dict:
    ts = registry.tasks_of(tr.key)
    boss = next((t.id for t in ts if t.boss), None)
    soon = not edition.track_open(tr.key)      # первый модуль: место в следующем модуле
    opened = set(tr.requires) <= set(p.get("bosses", ())) and not soon
    return {"key": tr.key, "name": bare(theme.place(tr.key)), "sender": theme.sender(tr.key),
            "seen": sum(1 for t in ts if progress.seen(p, t.id)), "total": len(ts),
            "open": opened, "soon": soon, "done": bool(boss) and boss in p.get("bosses", ()),
            "need": [_title(b) for b in tr.requires if b not in p.get("bosses", ())]}


def _title(task_id: str) -> str:
    tasks = registry.all_tasks()
    return theme.title(tasks[task_id]) if task_id in tasks else task_id


def current(p: dict) -> Optional[str]:
    """Место, куда идти сейчас: где ждёт следующая новая задача, иначе первое с повторами."""
    from termit_app import session
    new = session.next_new(p, 1)
    if new:
        return registry.get(new[0]).track
    return None


def _tiers() -> List[list]:
    tiers, seen = [], {}
    for tr in registry.shown_tracks():
        if tr.requires not in seen:
            seen[tr.requires] = len(tiers)
            tiers.append([])
        tiers[seen[tr.requires]].append(tr)
    return tiers


def _later() -> List[str]:
    """Места темы без задач в реестре — за туманом."""
    real = {tr.key for tr in registry.shown_tracks()}
    return [bare(t["place"]) for k, t in (theme.load(theme.current()).get("tracks") or {}).items()
            if k not in real]


def _status_words(s: dict, here: bool) -> str:
    if s.get("soon"):
        return edition.SOON
    if not s["open"]:
        return "закрыто: нужен " + ", ".join(s["need"])
    word = "пройдено" if s["done"] else "открыто"
    tail = f" — {_ui('here', '← сейчас здесь').lstrip('← ')}" if here else ""
    return f"{word}, {s['sender']}, {s['seen']}/{s['total']}{tail}"


def lines(p: dict, c: tui.Caps = None, style: Optional[dict] = None) -> List[str]:
    c = c or tui.caps()
    title = _ui("title", "КАРТА")
    here = current(p)
    states = {tr.key: _state(p, tr) for tr in registry.shown_tracks()}
    later = _later()
    if c.level == "plain":
        out = [title]
        for tr in registry.shown_tracks():
            s = states[tr.key]
            out += tui.fill(f"{s['name']} — {_status_words(s, tr.key == here)}",
                            tui.STORY, "  ", "    ")
        if later:
            out += tui.fill(_ui("later", "Дальше — закрыто:") + " " + ", ".join(later),
                            tui.STORY, "  ", "    ")
        return out
    rich = c.level == "rich"
    ms = style if style is not None else cosmetics.map_style(p)
    tokens = ms.get("tokens") or {}

    def paint(text: str, name: str) -> str:
        """Цвет места: токен стиля карты (тепловизор), иначе — палитры."""
        code = tui.pick(tokens[name], c) if name in tokens and c.colors else ""
        return f"\033[{code}m{text}\033[0m" if code and text else tui.style(text, name, c=c)
    inner = c.width - 5
    mark = {"done": "✓" if rich else "+", "open": "◆" if rich else "*",
            "shut": "░" if rich else "#"}
    if rich:
        mark.update(ms.get("marks") or {})
    here_word = _ui("here", "← сейчас здесь")
    if not rich:                                          # basic — стрелка ASCII
        here_word = here_word.replace("←", "<-")
    rows: list = [""]
    tiers = _tiers()
    for i, tier in enumerate(tiers):
        names, subs = [], []
        for tr in tier:
            s = states[tr.key]
            if s["open"]:            # значок места — только у открытых и только в rich
                cell = icons.mark(icons.track(tr.key, c)) + f"[{s['name']}]"
                sub = f"{s['sender']} {mark['done' if s['done'] else 'open']} " \
                      f"{s['seen']}/{s['total']}"
                if tr.key == here:
                    cell = paint(cell, "accent")
                    arrow = here_word
                    room = inner // len(tier) - 2
                    sub += " " + (arrow if tui.vlen(sub + arrow) < room else arrow.split()[0])
                else:
                    cell = paint(cell, "ok" if s["done"] else "neon")
            else:
                cell = paint(f"{mark['shut']}[{s['name']}]{mark['shut']}", "dim")
                # подсказка «нужен» — всегда читаемым dim (17 тепловизора на чёрном не видно)
                sub = tui.style(edition.SOON if s["soon"] else "нужен: " + ", ".join(s["need"]),
                                "dim", c=c)
            names.append(cell)
            subs.append(sub)
        fits = max(tui.vlen(x) for x in names + subs) <= inner // len(tier) - 1
        if i:                                             # линия от яруса к ярусу
            rows += _links(len(tiers[i - 1]), len(tier) if fits else 1, inner, rich,
                           ms.get("lines") if rich else None)
        if fits:
            rows += [tui.Raw(tui.columns(names, inner)), tui.Raw(tui.columns(subs, inner))]
        else:                       # в колонки не влезает — по месту на строку, по центру
            for k, (name, sub) in enumerate(zip(names, subs)):
                rows += ([""] if k else []) + [tui.Raw(tui.columns([name], inner)),
                                               tui.Raw(tui.columns([sub], inner))]
    if later:
        rows += ["", tui.style(_ui("later", "Дальше — закрыто:"), "dim", c=c),
                 ("  ".join(f"{mark['shut']}[{n}]{mark['shut']}".replace(" ", tui.NBSP)
                            for n in later), "", "")]
    rows.append("")
    out = tui.box(rows, title=title, right=(ms.get("label") or "") if rich else "", kind="round", c=c)
    legend = f"{mark['done']} пройдено   {mark['open']} открыто   {mark['shut']} закрыто"
    if here:
        legend += f"   {here_word}"
    return out + ["   " + tui.style(legend, "dim", c=c)]


HEAVY_JOINTS = "┏┓┳┻╋"


def _links(above: int, below: int, width: int, rich: bool, heavy=None) -> list:
    """Соединение ярусов: вертикаль от середины и вилка к колонкам нижнего яруса.
    heavy=(v, h) — линии метро (rich): толстые ┃ ━ и такие же узлы."""
    v, h = ("│", "─") if rich else ("|", "-")
    tl, tr, tee, up, cross = "┌┐┬┴┼"
    if rich and heavy:
        (v, h), (tl, tr, tee, up, cross) = heavy, HEAVY_JOINTS
    mid = width // 2
    if below == 1:
        return [tui.Raw(" " * mid + v)]
    col = width // below
    centres = [col * k + col // 2 for k in range(below)]
    line = [" "] * width
    for x in range(centres[0], centres[-1] + 1):
        line[x] = h
    for x in centres:
        line[x] = tl if rich and x == centres[0] else tr if rich and x == centres[-1] else \
            tee if rich else "+"
    line[mid] = up if rich and mid not in centres else (cross if rich else "+")
    return [tui.Raw(" " * mid + v), tui.Raw("".join(line).rstrip()),
            tui.Raw("".join(v if i in centres else " " for i in range(width)).rstrip())]
