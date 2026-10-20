"""Ближняя цель (FB12, A2 + FB5 п. 28): «до стража N задач» — в итоге рана и в stats, и
реплики персонажей по мере приближения к стражу (N ≤ 5, N ≤ 2, «готов»). Реплики — в теме
(раздел boss_path); у темы без раздела (фэнтези) — только цифра, механика молчит."""
from typing import List, Optional, Tuple

from termit_app import progress, theme, ui
from termit_app.tasks import registry

# пороги реплик: при скольких оставшихся задачах звучит реплика (0 — страж ждёт)
STEPS = (5, 2, 0)


def _counts(p: dict, task) -> bool:
    """Задача ещё впереди на пути к стражу: не встречалась, выдать её можно (программы на
    месте) и её не держит невзятый страж (пары «после стража» — уже за ним)."""
    from termit_app import session      # здесь: session импортирует этот модуль
    if task.boss or progress.seen(p, task.id) or not session.available(task):
        return False
    tasks = registry.all_tasks()
    return not any(getattr(tasks.get(t), "boss", False)
                   for t in registry.missing_after(p, task))


def nearest(p: dict) -> Optional[Tuple[str, str, int]]:
    """Ближайший невзятый страж открытых мест: (место, страж, сколько задач до него).
    Из нескольких открытых мест — тот, до кого меньше; поровну — по порядку мест."""
    best = None
    for tr in registry.unlocked(p.get("bosses") or ()):
        ts = registry.tasks_of(tr.key)
        boss = next((t for t in ts if t.boss), None)
        if boss is None or boss.id in (p.get("bosses") or ()):
            continue
        left = sum(1 for t in ts if _counts(p, t))
        if best is None or left < best[2]:
            best = (tr.key, boss.id, left)
    return best


def line(p: dict) -> Optional[str]:
    """«Цель — Убежище «Ноль»: до стража 4 задачи» или «…: страж ждёт». Все стражи открытых мест
    взяты — None."""
    goal = nearest(p)
    if goal is None:
        return None
    key, _, left = goal
    boss = theme.word("boss")
    if not left:
        return f"Цель — {theme.place(key)}: {boss} ждёт, дорога к нему пройдена"
    tasks = ui.plural(left, "задача", "задачи", "задач")
    return f"Цель — {theme.place(key)}: до {_gen(boss)} {left} {tasks}"


def _gen(boss: str) -> str:
    """Родительный падеж слова темы: «страж» → «стража», «чудовище» → «чудовища»."""
    if boss.endswith("е"):
        return boss[:-1] + "а"
    return boss + "а"


def _said(p: dict, boss: str) -> List[int]:
    """Пороги, уже сказанные у этого стража; испорченное сохранение (раздел не словарь,
    запись не список, мусор внутри) — как пусто, итог рана из-за него не падает."""
    section = p.get("boss_path")
    said = section.get(boss) if isinstance(section, dict) else None
    if not isinstance(said, list):
        return []
    return [s for s in said if isinstance(s, int) and not isinstance(s, bool)]


def due_step(p: dict) -> Optional[Tuple[str, str, int]]:
    """Порог, пересечённый с прошлого раза: (место, страж, порог) — или None. Пересечено
    сразу несколько (сыграл пачку) — звучит ближайший к стражу, остальные отмечаются."""
    goal = nearest(p)
    if goal is None:
        return None
    key, boss, left = goal
    said = _said(p, boss)
    fresh = [s for s in STEPS if left <= s and s not in said]
    if not fresh:
        return None
    return key, boss, min(fresh)


def mark(p: dict, boss: str, left: int) -> None:
    """Отметить порог и все пороги выше него: назад реплики не возвращаются."""
    section = p.get("boss_path") if isinstance(p.get("boss_path"), dict) else {}
    section[boss] = sorted(set(_said(p, boss)) | {s for s in STEPS if s >= left}, reverse=True)
    p["boss_path"] = section


def say_lines(p: dict) -> List[Tuple[str, str, str]]:
    """Реплика нового порога: [(вид, кто, строка)] и отметка в сохранении. Вид "say" —
    персонаж (кто — имя), "voice" — внутренний голос места (story.voice_name). Нет реплики в
    теме — пусто, но порог отмечается: иначе он «догонял» бы игрока после смены темы."""
    step = due_step(p)
    if step is None:
        return []
    key, boss, at = step
    mark(p, boss, at)
    lines = ((theme.load(theme.current()).get("boss_path") or {}).get(key) or {}).get(at)
    if not lines:
        return []
    who, text = lines
    if who == "voice":
        from termit_app import story
        name = story.voice_name(key)
        return [("voice", name, text)] if name else [("say", theme.sender(key), text)]
    return [("say", who, text)]
