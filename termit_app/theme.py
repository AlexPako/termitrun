"""Темы: все слова сеттинга. Движок, файлы песочницы и проверки от темы не зависят."""
import importlib
import os
import pkgutil
from typing import List, Optional

DEFAULT = "cyberpunk"

# Слова интерфейса: ключ → что это (подсказка автору новой темы).
WORDS = {
    "session": "ежедневная сессия, с большой буквы: Ран / Дозор",
    "tasks_gen": "«задач» в родительном падеже мн. числа: заказов / поручений",
    "new_spell": "заголовок карточки новой команды: 💾 Новая прога / 📖 Новое заклинание",
    "remind_spell": "тот же заголовок, когда приём уже встречался: 💾 Напомню приёмы",
    "book": "шпаргалка (./termit book), с большой буквы: Арсенал / Гримуар",
    "book_add": "подпись при записи в шпаргалку: 💾 В арсенал / 📖 В гримуар",
    "xp_gen": "очки (карма/опыт), не тратятся, в родительном падеже: кармы / опыта",
    "xp_title": "очки (карма/опыт), не тратятся, с большой буквы: Карма / Опыт",
    "timer": "значок таймера повторения: ⏱ / ⏳",
    "boss": "босс трека: страж / чудовище",
    "fight": "метка задачи-босса в карточке: ⚔ ВЗЛОМ / ⚔ СХВАТКА",
    "beaten": "заголовок списка поверженных боссов: Взломаны / Повержены",
    "field": "задание в настоящих папках: Заказ в реале / Полевое поручение",
    "field_icon": "значок задания в реале: 📡 / 🌾",
    "artifact": "утилита в подарок: имплант / артефакт",
    "money": "значок валюты: 💳 / 🪙",
    "money_name": "название денег: кредиты / золото",
    "train_mode": "метка режима тренировки в карточке: 🏠 Тренировка",
    "job_mode": "метка режима дела в карточке: 💼 Дело / 📜 Заказ",
    "rehearsal_mode": "метка репетиции босса в карточке: 🎭 Репетиция",
    "urgent_mark": "метка срочного заказа в карточке: 💼 срочно",
    "soft_label": "платные подсказки одним словом: софт / магия",
    "soft": "три платные подсказки дела через |: справочник|сканер|взломщик",
    "owl": "наводчица на локальной модели (команда ask), со значком: 🦉 Сова",
}

# Реплики: ключ → поля, которые подставляются через {…}.
MESSAGES = {
    "quit": (),
    "empty_day": (),
    "warmup": (),
    "next": (),
    "field_bonus": ("xp",),
    "boss_down": ("title",),
    "opened": ("place",),
    "locked": ("place", "need"),
    "after_locked": ("title", "need"),
    "no_money": ("cost", "have"),
    "job_failed": (),
    "boss_failed": (),
    "more_boss": ("title",),
    "shift_closed": ("n",),
    "freeze_saved": (),
    "streak_lost": ("n",),
    "freeze_spent": ("n", "left"),    # купленная заморозка сгорела, спасая серию
    "tomorrow_reviews": (),
    "tomorrow_quiet": (),
    "tomorrow_count": ("n",),         # сколько старых дел придёт завтра (не вся очередь)
    "tomorrow_count_tail": ("n",),    # то же, когда очередь длиннее рана — без её числа
    "result_unconfirmed": (),     # «решено» в песочнице, а проверка родителя не согласна
    # Сова (команда ask, локальная Ollama)
    "owl_persona": (),        # одна строка персоны для модели: кто она и как говорит
    "owl_sleep": (),          # Ollama нет или мост не запущен
    "owl_silent": (),         # Ollama не ответила — денег не взято
    "owl_thinking": (),
    "owl_refuse": (),         # заготовка вместо ответа, похожего на решение
    "owl_disclaimer": (),     # «может ошибаться — проверь в man»
    "owl_boss": (),           # на страже нельзя (можно в репетиции)
    "owl_limit": (),          # лимит вопросов на задачу или ран
    "owl_no_money": ("cost", "have"),
    "owl_closing": (),        # задача закрыта, а модель ещё пишет — ждём пару секунд
}

# Сюжетные строки — только из выбранной темы (чужая атмосфера хуже никакой):
#   reactions[трек][вид] — реплика персонажа трека после разбора, одна строка; вид —
#   solved (чисто), hard (с подсказкой), slow (без подсказок, но дольше таймера — P2 Б5),
#   record, giveup (П3.6);
#   tomorrow["tracks"][трек] — 2–3 тизера новой задачи, ["places"][трек] — тизер места,
#   ["bosses"][id] — тизер стража; milestones[дни] — событие на вехе серии.
OUTCOMES = ("solved", "giveup")
REACTION_KINDS = ("solved", "hard", "slow", "record", "giveup")
MILESTONES = (3, 7, 14, 30)

_cache = {}
_active: Optional[str] = None


def available() -> List[str]:
    from termit_app import themes
    return sorted(m.name for m in pkgutil.iter_modules(themes.__path__))


def load(name: str) -> dict:
    if name not in _cache:
        _cache[name] = importlib.import_module(f"termit_app.themes.{name}").THEME
    return _cache[name]


def use(name: Optional[str] = None) -> str:
    """Тема на этот запуск: явное имя → TERMIT_THEME → по умолчанию; неизвестная — по умолчанию."""
    global _active
    name = name or os.environ.get("TERMIT_THEME") or DEFAULT
    _active = name if name in available() else DEFAULT
    return _active


def current() -> str:
    return _active or use()


def _pick(section: str, key):
    for name in (current(), DEFAULT):
        val = load(name).get(section, {}).get(key)
        if val:
            return val
    raise KeyError(f"в теме нет {section}.{key}")


def word(key: str) -> str:
    return _pick("words", key)


def soft_names() -> List[str]:
    """Названия 1-й, 2-й, 3-й платной подсказки на деле."""
    return [s.strip() for s in word("soft").split("|")]


def msg(key: str, **kw) -> str:
    return _pick("messages", key).format(**kw)


def place(track_key: str) -> str:
    """Название места; в rich — со значком трека впереди (раздел icons, termit_app/icons.py),
    в basic и plain — голым словом."""
    from termit_app import icons
    return icons.mark(icons.track(track_key)) + _pick("tracks", track_key)["place"]


def sender(track_key: str) -> str:
    return _pick("tracks", track_key)["sender"]


def speaker(task) -> str:
    """Кто ведёт задачу: свой sender в записи темы (Гайка дарит импланты и в Основах) или
    персонаж трека. Подпись одна — в текстах интро и урока имени нет (П3.10)."""
    return _entry(task).get("sender") or sender(task.track)


def rank_name(level: int) -> str:
    return (load(current()).get("ranks") or load(DEFAULT)["ranks"])[level]


def intro_text() -> str:
    """Вступление при первом запуске: из выбранной темы, иначе из темы по умолчанию."""
    return load(current()).get("intro") or load(DEFAULT)["intro"]


def _own(section: str) -> dict:
    return load(current()).get(section) or {}


def story(section: str) -> dict:
    """Сюжетный раздел только выбранной темы, без запасного варианта: нет раздела — пусто,
    и механика молча выключена (чужая атмосфера хуже никакой)."""
    return _own(section)


def _one(val, seed: int) -> Optional[str]:
    if isinstance(val, str):
        return val or None
    return val[seed % len(val)] if val else None


def _reaction_pool(track_key: str, outcome: str):
    """Группа реплик вида outcome; нет группы hard/slow/record — берётся solved."""
    groups = _own("reactions").get(track_key) or {}
    val = groups.get(outcome)
    if not val and outcome in ("hard", "slow", "record"):
        val = groups.get("solved")
    return val


def _recent(avoid) -> List[str]:
    """Память реплик: строка (старый progress.json) или список, свежие в конце."""
    if isinstance(avoid, str):
        return [avoid]
    if isinstance(avoid, (list, tuple)):
        return [x for x in avoid if isinstance(x, str)]
    return []


def reaction(track_key: str, outcome: str, seed: int = 0,
             avoid=None) -> Optional[str]:
    """Реплика персонажа после разбора; None — у темы нет такой. outcome — вид реплики
    (REACTION_KINDS). avoid — недавние реплики трека (строка или список, свежие в конце):
    последние N из этого пула, N — половина пула, снова не звучат (П3.6, FB5)."""
    val = _reaction_pool(track_key, outcome)
    if isinstance(val, str) or not val:
        return _one(val, seed)
    window = len(val) // 2
    mine = [x for x in _recent(avoid) if x in val]
    blocked = set(mine[max(0, len(mine) - window):]) if window else set()
    pool = [x for x in val if x not in blocked] or list(val)
    return pool[seed % len(pool)]


def remember_reaction(track_key: str, avoid, line: str) -> List[str]:
    """Новая память трека после реплики line: на каждый вид — не больше половины его пула
    последних реплик; реплик, которых в теме больше нет, память не держит."""
    groups = _own("reactions").get(track_key) or {}
    pools = [v for v in groups.values() if isinstance(v, list)]
    left = {id(v): len(v) // 2 for v in pools}
    kept = []
    for x in reversed(_recent(avoid) + [line]):
        owner = next((v for v in pools if x in v), None)
        if owner is None or left[id(owner)] <= 0:
            continue
        left[id(owner)] -= 1
        kept.append(x)
    return kept[::-1]


def tomorrow(kind: str, key: str, seed: int = 0) -> Optional[str]:
    """Зацепка на завтра: kind — tracks (новая задача), places (новое место), bosses (страж)."""
    return _one((_own("tomorrow").get(kind) or {}).get(key), seed)


def milestone(days: int) -> Optional[str]:
    return _own("milestones").get(days)


def tagline() -> str:
    th = load(current())
    return f"{th['name']} — {th['tagline']}"


def _entry(task) -> dict:
    """Запись задачи — только из выбранной темы: чужая атмосфера хуже никакой."""
    return load(current()).get("tasks", {}).get(task.id) or {}


def title(task) -> str:
    return _entry(task).get("title") or task.title


def lesson(task, state: Optional[dict] = None) -> Optional[str]:
    """Мини-урок персонажа к новой команде; нет в выбранной теме — None (покажем scroll).
    state с движком БД (_engine) — урок этого движка, если тема его задала (lessons, финал M3:
    страж Хранилища в SQLite не называет pg_dump). FB12 (п. 38): урок учит то, что нужно
    текущему варианту — state с _variant берёт variant_lessons[номер], если тема его задала;
    вариант 0 и вызов без state — общий урок."""
    entry = _entry(task)
    state = state or {}
    by_variant = entry.get("variant_lessons") or {}
    try:
        own = by_variant.get(int(state.get("_variant", 0)))
    except (TypeError, ValueError):
        own = None
    engine = state.get("_engine")
    return own or (entry.get("lessons") or {}).get(engine) or entry.get("lesson") or None


def lesson_texts(task) -> list:
    """Все уроки задачи: общий (вариант 0) и уроки вариантов — для охран «в уроке названо»."""
    entry = _entry(task)
    out = [entry.get("lesson")] + list((entry.get("lessons") or {}).values())
    out += [text for _, text in sorted((entry.get("variant_lessons") or {}).items())]
    return [t for t in out if t]


def intro(task, state: dict, lore: bool = True) -> Optional[str]:
    """Строка атмосферы карточки. lore — порция сюжета перед ней (FB3: ответы порциями),
    текст без подстановок. FB12 (D1): порция разовая — карточка просит её только при первой
    встрече (lore=False на повторах и в команде task)."""
    entry = _entry(task)
    lines = entry.get("intro") or ()
    lore = entry.get("lore") if lore else None
    if not lines:
        return lore or None
    head = lines[state.get("_seed", 0) % len(lines)].format(**state)
    return f"{lore} {head}" if lore else head


def task_text(task, state: dict) -> str:
    """Строка атмосферы (если есть) + суть задачи обычным языком."""
    head = intro(task, state, lore=False)
    body = task.text(state)
    return f"{head}\n{body}" if head else body
