"""Витрина: каталог трат, видимость по фазам игры, покупка, подарки.

Имена и описания позиций — в теме (раздел shop); здесь только нейтральное запасное имя.
Купленное и подаренное лежит в p["owned"]; поведение вещей (приглашение, убежище, модули,
звуки) подключают отдельные модули — здесь только учёт. Косметика (часть 7а) — из
cosmetics.LADDER: видна, когда завезена (p["stock"]) и не куплена; бутлеги bootN собираются
на лету (get)."""
from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from termit_app import cosmetics, progress, theme
from termit_app.tasks import registry


@dataclass(frozen=True)
class Item:
    id: str
    kind: str           # freeze|dossier|fragment|prompt|palette|decor|shnyr|module|slot|sound|tip
                        # board — место на доске убежища (FB5)
                        # косметика — cosmetics.KINDS
    section: str        # work|story|home|deck|style|extras
    price: Optional[int]    # None — только подарок
    name: str           # нейтральное запасное имя, если в теме нет своего
    story: bool = False     # сюжетная позиция: в теме без сюжета её нет
    consumable: bool = False
    cosmetic: bool = False  # косметика (часть 7а): без игрового преимущества, видна по завозу


SECTIONS = ("story", "home", "deck", "work", "style", "extras")    # порядок на витрине
# нейтральные названия разделов, если в теме нет своих
SECTION_NAMES = {"story": "сюжет", "home": "дом", "deck": "дека", "work": "работа",
                 "style": "стиль", "extras": "примочки"}
SHOWCASE = 8            # позиций на виду одновременно (11 §3: витрина, а не прайс)

# досье: персонаж → трек (страницы 1–3)
DOSSIERS = {"voron": "basics", "gaika": "tools", "shnyr": "finder", "marina": "data",
            "plomba": "db", "dubrov": "sql", "frosya": "env"}
DOSSIER_PRICES = (30, 60, 120)
DOSSIER_PAGE2_SOLVED = 5        # стр. 2 — решено задач трека не меньше
# FB5 п. 69: что лежит в tar.gz (досье, стр. 3; фрагмент 2), продаём после урока tar — иначе
# игрок купит то, что открыть ещё не умеет
TAR_LESSON = "tldr_tar"
TAR_FRAGMENTS = (2,)
FRAGMENT_PRICES = (100, 150, 200, 250, 300, 350, 400, 500)
FRAGMENTS_ON_SALE = 7           # продаются фрагменты 1–7 (7-й — Фабрика, после 7-го стража)
# цена вне лестницы: фрагмент 6 — 300 по плану части 9 (B5). 9б B6 проверил ступень лестницы
# 350: ёмкость витрины 6030 выходит за коридор 3500–6000, а без PostgreSQL у типичного игрока
# дней с > 4 целей за 120 дней по 12 зёрнам — 11,8 % (порог test_economy_balance — 10 %).
# Фрагмент 7 (Фабрика, часть 7, E22) — 350: следующая ступень после 300 у 6-го (лестничные 400 —
# скачок без нужды). Ёмкость витрины 6540, коридор поднят до 7000 (test_economy_balance);
# цифры econ_sim — в спеке, раздел экономики
FRAGMENT_PRICE_AT = {6: 300, 7: 350}
PALETTES = ("pal_neon", "pal_toxic", "pal_ice", "pal_amber")
SHNYR_ITEMS = ("mug", "jacket", "tag", "photo", "tape", "key")
SHELF_BOOK = 10                 # полка — в шпаргалке не меньше стольких команд
MODULES = ("cache", "cooler", "freezer")
TROPHY_TRACKS = ("basics", "tools", "finder", "data", "db", "sql", "env")  # трофей — за стража
BOARD2_PRICE = 60       # второе место на доске убежища — как деталь приглашения (FB5)


def _catalog() -> List[Item]:
    out = [Item("freeze", "freeze", "work", progress.FREEZE_PRICE, "заморозка серии",
                consumable=True)]
    # главная история — первой в своём разделе витрины
    for k in range(1, FRAGMENTS_ON_SALE + 1):
        out.append(Item(f"half{k}", "fragment", "story",
                        FRAGMENT_PRICE_AT.get(k, FRAGMENT_PRICES[k - 1]),
                        f"фрагмент {k}", story=True))
    for who in DOSSIERS:
        for k, price in enumerate(DOSSIER_PRICES, 1):
            out.append(Item(f"{who}{k}", "dossier", "story", price, f"досье {who}, стр. {k}",
                            story=True))
    for iid, price, name in (("path_short", 40, "путь коротко"), ("path_full", 40, "путь полностью"),
                             ("exit_code", 60, "код ошибки"), ("time_right", 60, "время справа"),
                             ("two_lines", 60, "две строки"), ("deck_icon", 80, "значок")):
        out.append(Item(iid, "prompt", "home", price, f"приглашение: {name}"))
    for iid in PALETTES:
        out.append(Item(iid, "palette", "home", 120, f"палитра {iid[4:]}"))
    for iid, price, name in (("clock", 50, "часы"), ("calendar", 80, "календарь"),
                             ("monitor", 100, "монитор"), ("shelf", 150, "полка"),
                             ("neon", 200, "вывеска")):
        out.append(Item(iid, "decor", "home", price, name))
    for track in TROPHY_TRACKS:
        out.append(Item(f"trophy_{track}", "decor", "home", None, f"трофей: {track}"))
    # FB5 (8): доска «перед глазами» — подарок за первое решённое задание; место 2 — витрина
    # (цена детали приглашения), место 3 — подарок за стража «Основ»
    out.append(Item("board", "decor", "home", None, "доска"))
    out.append(Item("board2", "board", "home", BOARD2_PRICE, "место на доске"))
    out.append(Item("board3", "board", "home", None, "ещё место на доске"))
    for iid, price, name in zip(SHNYR_ITEMS, (40, 60, 80, 100, 120, 150),
                                ("кружка", "куртка", "жетон", "фотография", "кассета", "ключ")):
        out.append(Item(iid, "shnyr", "story", price, name, story=True))
    for iid, price, name in (("cache", 300, "модуль: кэш"), ("cooler", 250, "модуль: охладитель"),
                             ("freezer", 200, "модуль: морозилка")):
        out.append(Item(iid, "module", "deck", price, name))
    out.append(Item("slot2", "slot", "deck", 200, "слот 2"))
    out.append(Item("slot3", "slot", "deck", 400, "слот 3"))
    out.append(Item("bell", "sound", "extras", 40, "звонок"))
    out.append(Item("cassette", "sound", "extras", 80, "кассета"))
    out.append(Item("shard_tip", "tip", "story", 30, "наводка на осколок", story=True,
                    consumable=True))
    for iid, kind, section, price, _gate in cosmetics.LADDER:
        out.append(Item(iid, kind, section, price, cosmetics.NAMES[iid],
                        story=iid in cosmetics.STORY, cosmetic=True))
    return out


CATALOG: List[Item] = _catalog()
_BY_ID: Dict[str, Item] = {i.id: i for i in CATALOG}


def get(item_id: str) -> Optional[Item]:
    item = _BY_ID.get(item_id)
    if item is None:
        n = cosmetics.boot_n(item_id)
        if n is not None:       # бутлег: позиция собирается на лету
            item = Item(item_id, "tape", "extras", cosmetics.bootleg_price(n),
                        cosmetics.TEXTS["bootleg"].format(n=n), cosmetic=True)
    return item


def owned(p: dict, item_id: str) -> bool:
    return item_id in p.get("owned", ())


# --- Видимость по фазам (11 §3.1–3.2) -----------------------------------------------------

def _beaten(p: dict, boss: str) -> bool:
    return boss in p.get("bosses", ())


def track_boss(track: str) -> Optional[str]:
    return next((t.id for t in registry.tasks_of(track) if t.boss), None)


def _track_open(p: dict, track: str) -> bool:
    return any(t.key == track for t in registry.unlocked(p.get("bosses", [])))


def _solved_in(p: dict, track: str) -> int:
    return sum(1 for t in registry.tasks_of(track) if not t.boss
               and p["tasks"].get(t.id, {}).get("solved", 0) > 0)


def _seen_in(p: dict, track: str) -> int:
    return sum(1 for t in registry.tasks_of(track) if t.id in p["tasks"])


def _dossier_rule(who: str, k: int) -> Callable[[dict, date], bool]:
    track = DOSSIERS[who]

    def rule(p, today):
        if k == 1:
            return _track_open(p, track)
        if not owned(p, f"{who}{k - 1}"):
            return False
        if k == 2:
            return _solved_in(p, track) >= DOSSIER_PAGE2_SOLVED
        return _beaten(p, track_boss(track)) and _knows(p, TAR_LESSON)
    return rule


def _knows(p: dict, task_id: str) -> bool:
    """Урок пройден: задача решена хоть раз."""
    return p["tasks"].get(task_id, {}).get("solved", 0) > 0


def _fragment_rule(k: int) -> Callable[[dict, date], bool]:
    return lambda p, today: (len(p.get("bosses", ())) >= k and
                             (k == 1 or owned(p, f"half{k - 1}")) and
                             (k not in TAR_FRAGMENTS or _knows(p, TAR_LESSON)))


def _shnyr_rule(k: int) -> Callable[[dict, date], bool]:
    return lambda p, today: (_seen_in(p, "finder") >= 2 * k - 1 and
                             (k == 1 or owned(p, SHNYR_ITEMS[k - 2])))


def _after(boss: str) -> Callable[[dict, date], bool]:
    return lambda p, today: _beaten(p, boss)


def _next_palette(iid: str) -> Callable[[dict, date], bool]:
    def rule(p, today):
        nxt = next((x for x in PALETTES if not owned(p, x)), None)
        return _beaten(p, "boss_basics") and nxt == iid
    return rule


def _shard_tip(p: dict, today: date) -> bool:
    from termit_app import story
    have = set(p.get("shards", ()))
    return ("hidden_cache" in p["tasks"] and not p.get("shard_tip")
            and any(s.id not in have for s in story.SHARDS))


def _always(p: dict, today: date) -> bool:
    return True


def _board2(p: dict, today: date) -> bool:
    """Второе место на доске видно, когда есть доска и вторая карточка клавиш — есть что
    приколоть рядом с первой."""
    from termit_app import hideout
    keys = [c for c in hideout.open_cards(p) if c != hideout.GAME_CARD]
    return hideout.has_board(p) and len(keys) >= 2


VISIBLE: Dict[str, Callable[[dict, date], bool]] = {
    "freeze": _always, "path_short": _always, "exit_code": _always, "clock": _always,
    "bell": _always,
    "path_full": _after("boss_basics"), "time_right": _after("boss_basics"),
    "two_lines": _after("boss_basics"), "deck_icon": _after("boss_basics"),
    "calendar": _after("boss_basics"), "cache": _after("boss_basics"),
    "cooler": _after("boss_basics"), "cassette": _after("boss_basics"),
    "monitor": _after("boss_tools"), "freezer": _after("boss_tools"),
    "neon": _after("boss_finder"),
    "shelf": lambda p, today: len(p.get("grimoire", {})) >= SHELF_BOOK,
    # слот виден, когда в нём есть смысл; ворота кармы проверяет покупка (код karma)
    "slot2": lambda p, today: any(owned(p, m) for m in MODULES),
    "slot3": lambda p, today: owned(p, "slot2"),
    "shard_tip": _shard_tip,
    "board2": _board2,
}
for _who in DOSSIERS:
    for _k in (1, 2, 3):
        VISIBLE[f"{_who}{_k}"] = _dossier_rule(_who, _k)
for _k in range(1, FRAGMENTS_ON_SALE + 1):
    VISIBLE[f"half{_k}"] = _fragment_rule(_k)
for _k in range(1, len(SHNYR_ITEMS) + 1):
    VISIBLE[SHNYR_ITEMS[_k - 1]] = _shnyr_rule(_k)
for _iid in PALETTES:
    VISIBLE[_iid] = _next_palette(_iid)


def _story_on() -> bool:
    from termit_app import story
    return story.has_story()


def _shown(p: dict, item: Item, today: date) -> bool:
    if item.price is None or (item.story and not _story_on()):
        return False
    from termit_app import absence
    if absence.sold_out(p, item.id, today):     # пока игрока не было, «кто-то выкупил»
        return False
    if not item.consumable and owned(p, item.id):
        return False
    if item.cosmetic:
        return item.id in cosmetics.offers(p)
    rule = VISIBLE.get(item.id)
    return bool(rule and rule(p, today))


def visible(p: dict, today: date) -> List[Item]:
    """Всё, что сейчас можно купить, в порядке каталога (бутлеги — в конце, по завозу)."""
    out = [i for i in CATALOG if _shown(p, i, today)]
    return out + [get(b) for b in cosmetics.offers(p) if b not in _BY_ID]


def wave1_left(p: dict, today: date) -> List[Item]:
    """Видимые некупленные разовые позиции волны 1 (не косметика); слот, закрытый кармой, —
    не в счёт: его не купить, пока карма не дорастёт. Место на доске (FB5) — тоже: оно
    появляется у давно раскупивших витрину и не должно задерживать завоз косметики."""
    return [i for i in visible(p, today) if not i.cosmetic and not i.consumable
            and i.kind != "board"
            and (karma_gate(i) is None or progress.karma(p) >= karma_gate(i))]


def available_count(p: dict, today: date) -> int:
    return len(visible(p, today))


def showcase(p: dict, today: date) -> Tuple[List[Item], int]:
    """Не больше SHOWCASE позиций: по кругу из каждого раздела, чтобы на виду был каждый
    раздел, а не один самый длинный; внутри раздела сначала новое (ещё не виденное на
    витрине). Возвращает (позиции по разделам, сколько скрыто)."""
    # слот, закрытый кармой, на витрине не маячит — он виден в ./termit shop all
    items = [i for i in visible(p, today)
             if karma_gate(i) is None or progress.karma(p) >= karma_gate(i)]
    hidden_slots = available_count(p, today) - len(items)
    seen = set(p.get("shop_seen", ()))
    # волна 1 впереди косметики своего раздела; пока волна 1 не раскуплена, раздел style
    # занимает не больше одного места (новая косметика не уводит волну 1 в «и ещё N»)
    queues = {s: sorted((i for i in items if i.section == s),
                        key=lambda i: (i.cosmetic, i.id in seen))
              for s in SECTIONS}
    if any(not i.cosmetic and not i.consumable for i in items):
        queues["style"] = queues["style"][:1]
    picked: List[Item] = []
    while len(picked) < SHOWCASE and any(queues.values()):
        for s in SECTIONS:
            if queues[s] and len(picked) < SHOWCASE:
                picked.append(queues[s].pop(0))
    order = {i.id: n for n, i in enumerate(CATALOG)}
    picked.sort(key=lambda i: (SECTIONS.index(i.section),
                               order.get(i.id, len(CATALOG) + (cosmetics.boot_n(i.id) or 0))))
    return picked, len(items) - len(picked) + hidden_slots


# --- Покупка -------------------------------------------------------------------------------

def karma_gate(item: Item) -> Optional[int]:
    """Сколько кармы нужно для покупки (только слоты деки); None — ворот нет."""
    return progress.SLOT_KARMA.get(int(item.id[4:])) if item.kind == "slot" else None


def buy(p: dict, item_id: str, today: date) -> Tuple[bool, str]:
    """Купить позицию. Код: ok|unknown|hidden|owned|money|cap|karma|slot."""
    item = get(item_id)
    if item is None:
        return False, "unknown"
    if item.kind == "freeze":
        if p["freezes"] >= progress.freeze_cap(p):
            return False, "cap"
        return (True, "ok") if progress.buy_freeze(p) else (False, "money")
    if not item.consumable and owned(p, item.id):
        return False, "owned"
    if item.kind == "slot" and int(item.id[4:]) > p["deck"].get("slots", 1) + 1:
        return False, "slot"
    if not _shown(p, item, today):
        return False, "hidden"
    gate = karma_gate(item)
    if gate is not None and progress.karma(p) < gate:
        return False, "karma"
    if p["money"] < item.price:
        return False, "money"
    p["money"] -= item.price
    if item.kind == "tip":
        p["shard_tip"] = True
        return True, "ok"
    p["owned"].append(item.id)
    # долив косметики до минимума сразу; последняя вещь волны 1 открывает завоз
    cosmetics.stock_tick(p, today, on_buy=True)
    if item.kind == "slot":
        p["deck"]["slots"] = max(p["deck"].get("slots", 1), int(item.id[4:]))
        waiting = next((m for m in MODULES if owned(p, m) and not progress.module_on(p, m)), None)
        if waiting:             # новый слот сразу занимает купленный, но не вставший модуль
            install(p, waiting)
    elif item.kind == "module":
        install(p, item.id)     # нет свободного слота — модуль просто лежит купленным
    return True, "ok"


# --- Модули деки (E9) ----------------------------------------------------------------------

def free_slots(p: dict) -> int:
    deck = p["deck"]
    return deck.get("slots", 1) - len(deck.get("installed", []))


def install(p: dict, mid: str) -> str:
    """Поставить купленный модуль в свободный слот — бесплатно.
    Код: ok|unknown|not_owned|installed|no_slot."""
    item = get(mid)
    if item is None or item.kind != "module":
        return "unknown"
    if not owned(p, mid):
        return "not_owned"
    if progress.module_on(p, mid):
        return "installed"
    if free_slots(p) <= 0:
        return "no_slot"
    p["deck"].setdefault("installed", []).append(mid)
    return "ok"


def uninstall(p: dict, mid: str) -> bool:
    """Снять модуль (он остаётся купленным); False — он и не стоял."""
    if not progress.module_on(p, mid):
        return False
    p["deck"]["installed"].remove(mid)
    return True


# --- Подарки (решение 15) ------------------------------------------------------------------

GIFTS: Dict[str, List[Tuple[str, Tuple[str, ...]]]] = {
    "first_solve": [("board", ())],         # FB5: первое решённое задание — доска
    "streak3": [("clock", ("calendar",))],
    "boss_basics": [("trophy_basics", ()), ("path_short", ("exit_code", "time_right")),
                    ("board3", ())],
    "boss_tools": [("trophy_tools", ()), ("exit_code", ("time_right", "two_lines"))],
    "boss_finder": [("trophy_finder", ())],
    "boss_data": [("trophy_data", ()), ("time_right", ("two_lines", "deck_icon"))],
    "boss_db": [("trophy_db", ()), ("two_lines", ("deck_icon", "path_full"))],
    "boss_sql": [("trophy_sql", ())],
    "boss_env": [("trophy_env", ())],
}
GIFT_STREAK = 3
# кто дарит (роль из раздела characters темы): от него и сообщение на деке
GIFT_FROM = {"first_solve": "raven", "streak3": "raven", "boss_basics": "gaika",
             "boss_tools": "gaika", "boss_finder": "shnyr", "boss_data": "marina",
             "boss_db": "plomba", "boss_sql": "dubrov", "boss_env": "frosya"}


def give(p: dict, event: str) -> List[str]:
    """Выдать подарки события один раз; уже купленная вещь заменяется первой некупленной из
    запасных. Возвращает выданные id."""
    if event not in GIFTS or event in p["gifts"]:
        return []
    out = []
    for item, spares in GIFTS[event]:
        got = next((x for x in (item,) + spares if not owned(p, x)), None)
        if got:
            p["owned"].append(got)
            out.append(got)
    p["gifts"].append(event)
    return out


# --- Тексты темы ---------------------------------------------------------------------------

def _ui() -> dict:
    return theme.story("shop")


def _bootleg_text(item_id: str, key: str) -> Optional[str]:
    n = cosmetics.boot_n(item_id)
    if n is None:
        return None
    t = ((theme.story("cosmetics") or {}).get("bootleg") or {}).get(key)
    return t.format(n=n) if t else None


def name(item_id: str) -> str:
    t = (_ui().get("items") or {}).get(item_id) or {}
    item = get(item_id)
    return (t.get("name") or _bootleg_text(item_id, "name")
            or (item.name if item else cosmetics.NAMES.get(item_id, item_id)))


def desc(item_id: str) -> str:
    return (((_ui().get("items") or {}).get(item_id) or {}).get("desc")
            or _bootleg_text(item_id, "desc") or "")


def free_path(item_id: str) -> Optional[str]:
    return (_ui().get("free_paths") or {}).get(item_id)


def section_title(section: str) -> str:
    return (_ui().get("sections") or {}).get(section) or SECTION_NAMES.get(section, section)


def gift_line(event: str) -> Optional[str]:
    return (_ui().get("gifts") or {}).get(event)


def gift_from(event: str) -> str:
    """Ключ отправителя подарка на деке: персонаж, а не безликий «Подарок»."""
    return GIFT_FROM.get(event, "gift")
