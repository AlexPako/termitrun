"""Издание игры: какие места открыты в этой копии и куда отправлять замечания.

В приватной копии всё открыто и ссылок нет (None). Публичный экспорт (tools/export_public.py)
переписывает три строки ниже: первый модуль — только «Основы», замечания — в GitHub Issues.
Модуль ничего не импортирует из игры при загрузке: его читает и реестр, и хук в песочнице."""
import os
import platform
import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode

OPEN_TRACKS = ('basics',)
ISSUES_URL = 'https://github.com/AlexPako/termitrun/issues/new'
RELEASE = 'модуль 1 · 2026-10-24 · f358f3f'

SOON = "скоро — следующий модуль"
LOCKED = ("{place} откроется в следующем модуле игры — уже скоро. Следи за репозиторием, "
          "а идеи и пожелания пиши через bug в задаче или ./termit report.")
FINISH = ("🎉 Первый модуль пройден! Ты освоил основы терминала — дальше будет больше: "
          "инструменты, работа вместо Finder, данные, базы, Python. Следующие модули уже "
          "в работе — следи за репозиторием игры. А пока напиши, что понравилось, что было "
          "непонятно и чего не хватило: в задаче набери bug, или ./termit report.")
FINISH_FLAG = "edition_done"

SEND = "Отправить разработчику: открой ссылку (Cmd+клик), проверь текст и нажми Submit:"
URL_CAP = 6000
TITLE_CAP = 60
TEMPLATE = "feedback.yml"


def closed() -> bool:
    """Издание урезано: открыты не все места."""
    return OPEN_TRACKS is not None


def track_open(key: str) -> bool:
    return OPEN_TRACKS is None or key in OPEN_TRACKS


def module_done(p: dict) -> bool:
    """Первый модуль пройден: стражи открытых мест взломаны и нового в них не осталось."""
    if not closed():
        return False
    from termit_app import session
    from termit_app.tasks import registry
    bosses = [t.id for key in OPEN_TRACKS for t in registry.tasks_of(key) if t.boss]
    beaten = set(p.get("bosses", ()))
    return all(b in beaten for b in bosses) and not session.next_new(p, 1)


def finish_once(p: dict) -> Optional[str]:
    """Тёплое сообщение о конце модуля — один раз (флаг в p["flags"]); None — рано или было."""
    flags = p.setdefault("flags", [])
    if FINISH_FLAG in flags or not module_done(p):
        return None
    flags.append(FINISH_FLAG)
    return FINISH


# --- Замечания → карточка GitHub Issues --------------------------------------------------

def _scrub(text: str) -> str:
    """Убрать из текста домашнюю папку и имя пользователя: в публичную карточку их не несём."""
    home = str(Path.home())
    out = text.replace(home, "~") if home not in ("", "/") else text
    user = os.environ.get("USER") or Path(home).name
    if user and len(user) > 2:
        out = re.sub(rf"\b{re.escape(user)}\b", "user", out)
    return out


def _clip(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[:cap - 1] + "…"


def _macos() -> str:
    return platform.mac_ver()[0] or platform.system() or "?"


def issue_url(text: str, task_id: str = "") -> Optional[str]:
    """Ссылка на новую карточку с заполненной формой; None — у издания нет ссылки на Issues.
    Поля формы feedback.yml заполняются по их id; длина ссылки — не больше URL_CAP."""
    if not ISSUES_URL:
        return None
    clean = _scrub(" ".join(text.split()))
    cap = len(clean)
    while True:
        what = _clip(clean, cap)
        query = urlencode({"template": TEMPLATE,
                           "title": "[из игры] " + _clip(what, TITLE_CAP),
                           "what": what, "task": task_id or "-",
                           "version": RELEASE or "-", "macos": _macos()})
        url = f"{ISSUES_URL}?{query}"
        if len(url) <= URL_CAP or cap <= 20:
            return url
        cap = cap * 3 // 4


def send_lines(text: str, task_id: str = "") -> List[str]:
    """Строки после записанного замечания; пусто — издание без ссылки на Issues."""
    url = issue_url(text, task_id)
    return [SEND, url] if url else []


def report_lines() -> List[str]:
    """./termit report: новая карточка и список всех карточек."""
    if not ISSUES_URL:
        return ["В этой копии игры ссылки на карточки нет. Замечание: в задаче набери bug, "
                "список замечаний — ./termit feedback."]
    board = ISSUES_URL.rsplit("/new", 1)[0]
    return ["Баг, идея или что-то непонятно — пиши, всё это ценно.",
            "Новая карточка (Cmd+клик по ссылке, нужен аккаунт GitHub):",
            f"  {ISSUES_URL}?{urlencode({'template': TEMPLATE})}",
            "Все карточки — что уже нашли другие:",
            f"  {board}"]
