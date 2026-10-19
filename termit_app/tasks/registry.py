"""Треки, требования к званиям и реестр всех поручений. Имена мест, персонажей и званий — в теме."""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Track:
    key: str
    title: str                  # нейтральное название трека
    requires: Tuple[str, ...]   # какие боссы должны быть повержены


TRACKS = [
    Track("basics", "Основы", ()),
    Track("tools", "Инструменты", ("boss_basics",)),
    Track("finder", "Вместо Finder", ("boss_basics",)),
    Track("data", "Данные", ("boss_tools", "boss_finder")),
    Track("db", "Базы данных", ("boss_data",)),
    Track("sql", "SQL и PostgreSQL", ("boss_db",)),
    Track("env", "Окружение и скрипты", ("boss_data",)),
    Track("py", "Python", ("boss_env",)),
    # часть 10, Q4: pandas и requests — после Python и Картотеки (решение 14: boss_db, а не
    # boss_sql); без склада колёс задачи честно закрыты (missing), звания трек не держит
    Track("pydata", "Аналитика", ("boss_py", "boss_db")),
]

# Звание — за поверженных боссов; требования накапливаются сверху вниз.
# Имена пяти званий — theme.rank_name(уровень).
RANKS = [
    (),
    ("boss_basics",),
    ("boss_tools", "boss_finder", "boss_data"),
    ("boss_db", "boss_git", "boss_sql"),
    ("boss_env", "boss_ssh"),
]

_CACHE: Optional[Dict[str, object]] = None


def all_tasks() -> Dict[str, object]:
    global _CACHE
    if _CACHE is None:
        from termit_app.tasks import (basics, data, db, env, finder, pydata, python, sql,
                                      tools)
        mods = {"basics": basics, "tools": tools, "finder": finder, "data": data, "db": db,
                "sql": sql, "env": env, "py": python, "pydata": pydata}
        found = {}
        for tr in TRACKS:
            for t in mods[tr.key].TASKS:
                if t.id in found:
                    raise ValueError(f"повтор id поручения: {t.id}")
                found[t.id] = t
        _CACHE = found
    return _CACHE


def get(task_id: str):
    return all_tasks()[task_id]


def track(key: str) -> Track:
    for t in TRACKS:
        if t.key == key:
            return t
    raise KeyError(key)


def tasks_of(key: str) -> List[object]:
    return [t for t in all_tasks().values() if t.track == key]


def shown_tracks() -> List[Track]:
    """Треки, которые видит игрок: с поручениями. Трек-скелет (часть 10, Q1: «Python» до
    первых задач) живёт в реестре и темах, но игрок его не видит нигде — ни открытым после
    стража, ни на карте (там он за туманом), ни в списке и статистике."""
    return [t for t in TRACKS if tasks_of(t.key)]


def unlocked(bosses) -> List[Track]:
    """Открытые места: стражи взяты и место есть в издании (первый модуль — только «Основы»,
    edition.OPEN_TRACKS; остальные видны в списке и на карте, но не открываются)."""
    from termit_app import edition
    have = set(bosses)
    return [t for t in shown_tracks() if set(t.requires) <= have and edition.track_open(t.key)]


def missing_after(p: dict, task) -> List[str]:
    """Что из task.after ещё не выполнено: обычная задача — не решена ни разу
    (rec["solved"]), страж — не взломан (нет в p["bosses"]; тренировка стража не в счёт)."""
    tasks = all_tasks()
    out = []
    for tid in getattr(task, "after", ()):
        if getattr(tasks.get(tid), "boss", False):
            done = tid in p.get("bosses", ())
        else:
            done = bool((p.get("tasks", {}).get(tid) or {}).get("solved"))
        if not done:
            out.append(tid)
    return out


def after_done(p: dict, task) -> bool:
    """Задачи-пары открываются после близнеца и стража трека. Этим фильтром пользуются все
    пути выдачи: next_new, track, разминка, срочные заказы, возвращение, play ID. Задачи мест
    вне издания (edition.OPEN_TRACKS) не выдаются ни одним путём — и из старого сохранения."""
    from termit_app import edition
    return edition.track_open(getattr(task, "track", "")) and not missing_after(p, task)


def rank_level(bosses) -> int:
    have, need, level = set(bosses), set(), 0
    for i, req in enumerate(RANKS):
        need |= set(req)
        if not need <= have:
            break
        level = i
    return level
