"""Дневник ./termit diary: пройденные мини-уроки и разборы — перечитать бесплатно.

Записи — задачи, которые встречались (урок уже показан), в порядке мест и задач реестра;
номера сквозные. Страница: урок (тема, иначе scroll), «Разбор» — explain и снимок эталона
по каждому виденному варианту (progress.note_review: эталон форматируется state песочницы,
без неё его не собрать), строка шпаргалки. У непобеждённого стража эталона нет — экзамен
остаётся экзаменом. Прогресс дневник только читает. Код нейтрален: слова сеттинга — в теме
(раздел diary), здесь — нейтральные запасные строки."""
import re
from collections import namedtuple
from typing import List, Optional

from termit_app import progress, theme, tui, ui
from termit_app.tasks import registry

Entry = namedtuple("Entry", "n task_id track title has_lesson variants_seen locked")

# нейтральные строки (фэнтези и темы без раздела diary); тема заменяет своими
TEXTS = {
    "title": "Дневник",
    "empty": "Дневник пуст: страницы появятся после первой задачи. Начать: ./termit",
    "open": "Открыть страницу: ./termit diary N (номер или id). Бесплатно, прогресс не "
            "меняется.",
    "unknown": "Такой страницы нет: {key}. Список страниц: ./termit diary",
    "lesson": "Урок",
    "steps": "Шаги",
    "review": "Разбор",
    "why": "Почему",
    "reference": "Эталон",
    "variant": "Вариант {k}",
    "alt": "Можно и так",
    "locked": "Решение откроется после победы над боссом: экзамен остаётся экзаменом.",
    "legacy": "Эталон покажу, когда встретишь задачу ещё раз.",
    "boss": "босс",
    "item": "дневник",          # предмет убежища (hideout)
    "records": "🏁 — твой рекорд времени. Побить его — круг мастера: ./termit master",
    "look": "Страниц в дневнике: {n} — по одной на каждую встреченную задачу. Список — "
            "`./termit diary`, страница — `./termit diary N` (номер или id). Бесплатно, "
            "прогресс не меняется.",
}


def text(name: str, **kw) -> str:
    return ((theme.story("diary") or {}).get(name) or TEXTS[name]).format(**kw)


def _variants(rec: dict, n: int) -> List[int]:
    """Номера вариантов со снимком разбора (мусор и чужие номера — мимо)."""
    review = rec.get("review") if isinstance(rec, dict) else None
    if not isinstance(review, dict):
        return []
    out = set()
    for key, snap in review.items():
        if isinstance(key, str) and key.isdigit() and isinstance(snap, dict) \
                and int(key) < max(1, n):
            out.add(int(key))
    return sorted(out)


def entries(p: dict) -> List[Entry]:
    tasks = p.get("tasks") or {}
    beaten = set(p.get("bosses", ()))
    out = []
    for tr in registry.shown_tracks():
        for t in registry.tasks_of(tr.key):
            if t.id not in tasks:
                continue
            out.append(Entry(len(out) + 1, t.id, tr.key, theme.title(t),
                             bool(theme.lesson(t) or t.scroll),
                             _variants(tasks[t.id], len(t.variants)),
                             bool(t.boss) and t.id not in beaten))
    return out


def find(p: dict, key: str) -> Optional[Entry]:
    """Запись по номеру из списка или по id задачи."""
    key = (key or "").strip()
    for e in entries(p):
        if key == str(e.n) or key == e.task_id:
            return e
    return None


# --- Вывод ---------------------------------------------------------------------------------

def _para(s: str, cp: tui.Caps, first: str = "   ", rest: str = "   ") -> List[str]:
    return tui.fill(s, cp.width, first, rest)


# граница звена — ПОСЛЕ связки: строка кончается на «&&», «|», «;» или «→», и следующая с
# неё не начинается. zsh, получив вставкой «a &&» и «b», ждёт продолжения и выполнит обе
# (P2 Б10: перенос перед && ломал копирование двух строк)
_SEPS = re.compile(r"(?<=&& )|(?<=\|\| )|(?<=[^|]\| )|(?<=; )|(?<=→ )")


def _command(name: str, sol: str, cp: tui.Caps) -> List[str]:
    """Эталон — команда: её не рвут посреди звена (Н3.8 приёмки-1). Влезла с подписью —
    одной строкой; влезает сама — подпись отдельно, команда целиком своей строкой; иначе
    перенос только после связок «&&», «|», «;», «→»: каждое звено целиком, скопируешь —
    сработает."""
    line = f"   {name}: {sol}"
    if tui.vlen(line) <= cp.width:
        return [line]
    pad = "      "
    if tui.vlen(pad + sol) <= cp.width:
        return [f"   {name}:", pad + sol]
    out, cur = [f"   {name}:"], ""
    for part in _SEPS.split(sol):
        if cur and tui.vlen(pad + cur + part.rstrip()) > cp.width:
            out.append(pad + cur.rstrip())
            cur = ""
        cur += part
    if cur:
        out.append(pad + cur.rstrip())
    # звено длиннее строки — это уже описание словами, а не команда: переносим по словам
    return [r for row in out for r in (tui.fill(row.strip(), cp.width, pad, pad)
                                       if tui.vlen(row) > cp.width else [row])]


def _head(s: str, cp: tui.Caps) -> str:
    """Заголовок раздела: в plain — как есть, иначе с маркером и цветом."""
    if cp.level == "plain":
        return s
    mark = "▸ " if cp.level == "rich" else "> "
    return tui.style(mark + s, "accent", c=cp)


def _title(s: str, cp: tui.Caps) -> str:
    return s if cp.level == "plain" else tui.label(s, cp)


def list_lines(p: dict, cp: tui.Caps) -> List[str]:
    es = entries(p)
    out = [_title(text("title"), cp)]
    if not es:
        return out + _para(text("empty"), cp, "", "")
    track = None
    for e in es:
        if e.track != track:
            track = e.track
            out += ["", _head(theme.place(track), cp)]
        boss = f"{text('boss')}: " if registry.get(e.task_id).boss else ""
        best = _best(p, e.task_id)
        row = f"  {e.n:>2}. {boss}{e.title}  [{e.task_id}]" + (f"  🏁 {best}" if best else "")
        out.append(tui.trunc(row, cp.width))
    tail = _para(text("records"), cp, "", "") if any(_best(p, e.task_id) for e in es) else []
    return out + [""] + tail + _para(text("open"), cp, "", "")


def _best(p: dict, task_id: str) -> Optional[str]:
    """Личный рекорд времени задачи (rec["best"]) для дневника; нет — None (М3)."""
    best = (p["tasks"].get(task_id) or {}).get("best")
    if not isinstance(best, (int, float)) or isinstance(best, bool) or best < 0:
        return None
    return ui.fmt_time(best)


def page(p: dict, key: str, cp: tui.Caps) -> List[str]:
    """Страница дневника; неизвестный ключ — строка с подсказкой списка."""
    e = find(p, key)
    if e is None:
        return _para(text("unknown", key=(key or "").strip()[:40]), cp, "", "")
    t = registry.get(e.task_id)
    rec = p["tasks"][e.task_id]
    out = [_title(f"{e.title}  [{e.task_id}]", cp), _para(theme.place(e.track), cp)[0]]
    lesson = theme.lesson(t)
    if lesson or t.scroll:
        who = f" · {theme.speaker(t)}" if lesson else ""     # урок персонажа — с подписью
        out += ["", _head(text("lesson") + who, cp)]
        if lesson:
            out += ui.lesson_block(lesson, cp.width).split("\n")
        else:
            for line in t.scroll.split("\n"):
                out += _para(line, cp) if line.strip() else [""]
    if t.boss and t.steps:
        out += ["", _head(text("steps"), cp)]
        for i, step in enumerate(t.steps, 1):
            out += _para(f"{i}. {step}", cp, "   ", "      ")
    out += ["", _head(text("review"), cp)]
    out += _para(f"{text('why')}: {t.explain}", cp)
    seen = e.variants_seen
    if e.locked:
        out += _para(text("locked"), cp)
    elif not seen:
        out += _para(text("legacy"), cp)
    else:
        for k in seen:
            snap = rec["review"][str(k)]
            name = text("variant", k=k + 1) if len(t.variants) > 1 else text("reference")
            # чистим и при выводе: progress.json могли поправить руками
            sol = progress.review_text(snap.get("sol", ""))
            out += _command(name, sol, cp)
            alts = snap.get("alts")
            for alt in (alts if isinstance(alts, list) else [])[:progress.REVIEW_ALTS]:
                out += _para(f"{text('alt')}: {progress.review_text(alt)}", cp,
                             "      ", "         ")
        # варианты, виденные до снимков (история записи), — без эталона: строка legacy
        met = progress.variant_history(rec, max(1, len(t.variants)))
        if set(met) - set(seen):
            out += _para(text("legacy"), cp)
    if t.spell and not e.locked:        # шпаргалка стража — после взлома, как в арсенале
        out += ["", *_para(f"{theme.word('book')}: {t.spell}", cp, "   ", "      ")]
    return out
