"""Косметика за кредиты (часть 7а, K3): ценовая лестница, ворота, «завоз», бутлеги.

Косметика не даёт игрового преимущества: ни звёзд, ни таймера, ни цен, ни подсказок, ни
расписания, ни денег. Модули progress, hook, contracts, loot этот модуль не импортируют
(тест «без преимущества»). Импланты не продаются — это подарки (часть 5).

Завоз (p["stock"]) — детерминированный поток новых товаров на витрину. Начинается, когда
витрина волны 1 раскуплена (wave1_done, после первого стража): деньгам есть куда уходить, а
до того косметика не отнимает их у модулей деки и подсказок новичка. Первые две позиции
приходят сразу (в конце рана или на покупке последней вещи волны 1), дальше по одной раз в
STOCK_EVERY ранов, пока предложений меньше STOCK_MAX. После покупки витрина доливается до
STOCK_MIN. Начатый завоз не останавливается, даже если позже на витрине появятся новые вещи
волны 1, но и не растёт, пока они не куплены: долив до STOCK_MIN идёт, «+1 раз в STOCK_EVERY
ранов» ждёт (часть 7, E22: новый район приносит досье и фрагмент разом, и полоса 2–4 цели
иначе рвалась у сильного игрока — econ_sim, цифры в спеке). Кандидат — первая позиция LADDER, которой ещё не завозили и у которой открыты
ворота; нет таких — бесконечные бутлеги bootN (только чтобы держать минимум). Никаких
случайностей, таймеров и «успей купить»: завезённое лежит, пока не купят.

Здесь данные и учёт; витрину и покупку делает shop. Эффекты: скины рамок, анимация итога,
стиль карты (K4–K5) — выбор в p["settings"]["style"], activate(p) ставит скин в tui;
звук и питомец — следующие пачки. Тексты сеттинга — в теме (раздел cosmetics и shop.items);
здесь — нейтральные запасные имена."""
import re
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from termit_app import progress, theme

# (id, вид, раздел витрины, цена, ворота) — в порядке завоза. Цены — масштаб 11 §1:
# мелочь 80–120, покупка 150–250, цель 300–400; бутлеги — до 600. Подгонка — K11 (econ_sim).
LADDER: List[Tuple[str, str, str, int, str]] = [
    ("frame_chrome", "frame", "style", 150, "boss1"),
    ("chiba_clock", "decor", "home", 120, "boss1"),
    ("player", "player", "extras", 250, "boss1"),
    ("tape_rain", "tape", "extras", 120, "player"),
    ("title_cowboy", "title", "style", 80, "runs15"),
    ("anim_glitch", "anim", "style", 120, "boss1"),
    ("pal_blood", "palette", "home", 120, "boss1"),
    ("frame_gold", "frame", "style", 250, "boss_tools"),
    ("neko", "decor", "home", 100, "always"),
    ("tape_8bit", "tape", "extras", 150, "player"),
    ("pet", "pet", "home", 300, "runs20"),
    ("glyph_pack", "glyph", "home", 90, "always"),
    ("map_metro", "mapstyle", "style", 120, "boss_tools"),
    ("title_icebreaker", "title", "style", 120, "bosses3"),
    ("frame_neon", "frame", "style", 300, "best7"),
    ("tape_chase", "tape", "extras", 150, "player"),
    ("callsign", "callsign", "home", 200, "always"),
    ("pal_dusk", "palette", "home", 120, "always"),
    ("anim_scan", "anim", "style", 160, "always"),
    ("safe", "decor", "home", 180, "book20"),
    ("snd_synth", "soundpack", "extras", 250, "wave1_done"),
    ("title_librarian", "title", "style", 100, "book30"),
    ("frame_ice", "frame", "style", 350, "boss_finder"),
    ("tape_ice", "tape", "extras", 180, "player"),
    ("map_thermal", "mapstyle", "style", 180, "boss_finder"),
    ("snd_chip", "soundpack", "extras", 250, "wave1_done"),
    ("anim_rain", "anim", "style", 200, "always"),
    ("title_ghost", "title", "style", 100, "shards3"),
    ("pal_chrome", "palette", "home", 120, "always"),
    ("tape_neon", "tape", "extras", 200, "player"),
    ("frame_acid", "frame", "style", 400, "runs40"),
    ("snd_noir", "soundpack", "extras", 300, "wave1_done"),
    ("pal_rust", "palette", "home", 120, "always"),
    ("title_iron", "title", "style", 150, "best30"),
    ("tape_boss", "tape", "extras", 250, "bosses3"),
]
KINDS = ("frame", "decor", "player", "tape", "title", "anim", "palette", "pet", "glyph",
         "mapstyle", "callsign", "soundpack")
STORY = frozenset({"title_ghost"})     # сюжетная: в теме без сюжета не продаётся и не завозится

STOCK_MIN, STOCK_MAX, STOCK_EVERY = 2, 4, 2     # витрина косметики и «раз в 2 рана»
BOOT_BASE, BOOT_STEP, BOOT_CAP = 300, 25, 600   # бутлег N: 300 + 25·(N−1), не выше 600
BOOT_MAX_N = 9999
_BOOT = re.compile(r"boot([1-9][0-9]{0,3})")

# нейтральные запасные имена (фэнтези и темы без своих); сеттинг — в теме
NAMES: Dict[str, str] = {
    "frame_chrome": "рамки «хром»", "chiba_clock": "часы другого пояса",
    "player": "проигрыватель", "tape_rain": "запись «дождь»",
    "title_cowboy": "титул «знаток консоли»", "anim_glitch": "эффект «сбой»",
    "pal_blood": "палитра «алая»", "frame_gold": "рамки «золото»",
    "neko": "кошка-талисман", "tape_8bit": "запись «восемь бит»", "pet": "питомец",
    "glyph_pack": "знаки приглашения", "map_metro": "карта «схема»",
    "title_icebreaker": "титул «ледокол»", "frame_neon": "рамки «неон»",
    "tape_chase": "запись «погоня»", "callsign": "своё имя в шапке",
    "pal_dusk": "палитра «сумерки»", "anim_scan": "эффект «развёртка»", "safe": "сейф",
    "snd_synth": "звуки «синтезатор»", "title_librarian": "титул «ходячий справочник»",
    "frame_ice": "рамки «лёд»", "tape_ice": "запись «лёд»", "map_thermal": "карта «тепло»",
    "snd_chip": "звуки «восемь бит»", "anim_rain": "эффект «дождь знаков»",
    "title_ghost": "титул «призрак»", "pal_chrome": "палитра «серебро»",
    "tape_neon": "запись «огни»", "frame_acid": "рамки «кислота»",
    "snd_noir": "звуки «ночь»", "pal_rust": "палитра «ржавчина»",
    "title_iron": "титул «железная серия»", "tape_boss": "запись «схватка»",
    "frame_rep": "рамки «репутация»",
}
TEXTS = {
    "stock": "Новое на витрине: {names}. ./termit shop",
    "bootleg": "запись без подписи #{n}",
}
SOON_N = 4              # витрина «скоро» (C2 М4): первые позиции лестницы, до завоза
SOON_TEXTS = {
    "title": "Скоро на витрине — завезут, когда разберёшь нынешнюю (пока не продаётся):",
    "row": "· {name}, {price} {cash}",
}

_BY_ID = {row[0]: row for row in LADDER}


# --- Ворота ------------------------------------------------------------------------------

def _bosses(p: dict) -> list:
    b = p.get("bosses")
    return b if isinstance(b, list) else []


Gate = Callable[[dict, date], bool]


def _best(n: int) -> Gate:
    """Серия хоть раз дотягивала до n дней: веха оплачена (с заморозками) или по дням."""
    def gate(p, today):
        ms = p.get("milestones") if isinstance(p.get("milestones"), list) else []
        return n in ms or progress.best_streak(p.get("days") or (), p.get("frozen_days")) >= n
    return gate


def _runs(n: int) -> Gate:
    return lambda p, today: _int(p.get("dozors")) >= n


def _int(x) -> int:
    return x if isinstance(x, int) and not isinstance(x, bool) else 0


def _book(n: int) -> Gate:
    return lambda p, today: len(p.get("grimoire") or {}) >= n


def _beaten(boss: str) -> Gate:
    return lambda p, today: boss in _bosses(p)


def _wave1_done(p: dict, today: date) -> bool:
    """Видимых некупленных разовых позиций волны 1 нет (закрытые кармой — не в счёт).
    Открывается мгновенно и не закрывается: «всё куплено» — это ровно момент, когда
    деньги начинают копиться (решение Q3, fix round 1)."""
    from termit_app import shop
    return not shop.wave1_left(p, today)


GATES: Dict[str, Gate] = {
    "always": lambda p, today: True,
    "boss1": lambda p, today: len(_bosses(p)) >= 1,
    "boss_tools": _beaten("boss_tools"),
    "boss_finder": _beaten("boss_finder"),
    "bosses3": lambda p, today: len(_bosses(p)) >= 3,
    "runs15": _runs(15), "runs20": _runs(20), "runs40": _runs(40),
    "best7": _best(7), "best30": _best(30),
    "book20": _book(20), "book30": _book(30),
    "shards3": lambda p, today: len(p.get("shards") or ()) >= 3,
    "player": lambda p, today: "player" in (p.get("owned") or ()),
    "wave1_done": _wave1_done,
}


def gate_of(item_id: str) -> Optional[str]:
    row = _BY_ID.get(item_id)
    return row[4] if row else None


def _story_on() -> bool:
    from termit_app import story
    return story.has_story()


# --- Бутлеги -----------------------------------------------------------------------------

def boot_n(item_id: str) -> Optional[int]:
    """Номер бутлега из id bootN (N от 1 без ведущих нулей); иначе None."""
    m = _BOOT.fullmatch(item_id) if isinstance(item_id, str) else None
    return int(m.group(1)) if m and int(m.group(1)) <= BOOT_MAX_N else None


def bootleg_price(n: int) -> int:
    return min(BOOT_CAP, BOOT_BASE + BOOT_STEP * (max(1, n) - 1))


def is_cosmetic(item) -> bool:
    return bool(getattr(item, "cosmetic", False))


# --- Завоз -------------------------------------------------------------------------------

def _stock(p: dict) -> List[str]:
    """Завезённое (в порядке завоза), очищенное: мусор в сохранении (не строка, чужой id,
    bootN вне 1..BOOT_MAX_N, повтор) отбрасывается и в p["stock"] не возвращается."""
    raw = p.get("stock")
    clean: List[str] = []
    for iid in raw if isinstance(raw, list) else ():
        if isinstance(iid, str) and _sellable(iid) and iid not in clean:
            clean.append(iid)
    if raw != clean:
        p["stock"] = clean
    return p["stock"]


def _sellable(item_id: str) -> bool:
    return item_id in _BY_ID or boot_n(item_id) is not None


def _pending(p: dict, story: Optional[bool] = None) -> List[str]:
    """Завезённое и не купленное; story=False — без сюжетного (тема без сюжета)."""
    raw = p.get("stock")
    if not isinstance(raw, list):
        return []
    owned = set(p.get("owned") or ())
    out: List[str] = []
    for iid in raw:
        if not isinstance(iid, str) or not _sellable(iid) or iid in owned or iid in out:
            continue
        if iid in STORY and story is False:
            continue
        out.append(iid)
    return out


def offers(p: dict) -> List[str]:
    """Завезённое и не купленное (сюжетное — только в теме с сюжетом)."""
    return _pending(p, story=_story_on())


def started(p: dict, today: date) -> bool:
    """Завоз идёт: уже начат или витрина волны 1 раскуплена после первого стража."""
    raw = p.get("stock")
    if isinstance(raw, list) and any(isinstance(x, str) and _sellable(x) for x in raw):
        return True
    return GATES["boss1"](p, today) and GATES["wave1_done"](p, today)


def next_ladder(p: dict, today: Optional[date] = None) -> Optional[str]:
    """Первая позиция лестницы, которой ещё не завозили, с открытыми воротами."""
    today = today or date.today()
    have = set(_stock(p)) | set(p.get("owned") or ())
    story = _story_on()
    for iid, _kind, _section, _price, gate in LADDER:
        if iid in have or (iid in STORY and not story):
            continue
        if GATES[gate](p, today):
            return iid
    return None


def _next_boot(p: dict) -> Optional[str]:
    """Следующий бутлег; номера кончились (BOOT_MAX_N) — None: сток конечен, но цикл — тоже."""
    nums = [boot_n(x) for x in _stock(p)]
    n = max([k for k in nums if k] or [0]) + 1
    return f"boot{n}" if n <= BOOT_MAX_N else None


def stock_tick(p: dict, today: date, on_buy: bool = False) -> List[str]:
    """Завоз: в конце рана (после p["dozors"] += 1) или после покупки (on_buy — только долив
    до STOCK_MIN). Вернуть завезённые id. Не больше STOCK_MAX позиций за вызов: мусор в
    сохранении не может зациклить завоз."""
    if not started(p, today):
        return []
    stock = _stock(p)
    first = not stock
    got: List[str] = []
    for _ in range(STOCK_MAX):              # предохранитель: долив — максимум до STOCK_MIN
        if len(offers(p)) >= STOCK_MIN:
            break
        iid = next_ladder(p, today) or _next_boot(p)
        if iid is None or iid in stock:
            break
        stock.append(iid)
        got.append(iid)
    runs = _int(p.get("dozors"))
    if not isinstance(p.get("stock_run"), int) or isinstance(p.get("stock_run"), bool):
        p["stock_run"] = 0
    if got and (first or not on_buy):
        p["stock_run"] = runs
    if on_buy or got:
        return got
    # +1 раз в STOCK_EVERY ранов; лимит считает и сюжетное, скрытое сменой темы. Пока на
    # витрине некупленное волны 1 (новый район), завоз не растёт — только долив до минимума
    if (len(_pending(p)) < STOCK_MAX and runs - p["stock_run"] >= STOCK_EVERY
            and _wave1_done(p, today)):
        iid = next_ladder(p, today)         # бутлеги — только чтобы держать минимум
        if iid:
            stock.append(iid)
            got.append(iid)
            p["stock_run"] = runs
    return got


def soon(p: dict, today: date) -> List[str]:
    """Витрина «скоро» (М4): пока завоз не начат, первые SOON_N позиций лестницы — цель на
    виду и у того, кто волну 1 ещё не раскупил. Купить их нельзя: правило «завоз только после
    wave1_done» не меняется (shop.buy отвечает hidden). Сюжетное — только в теме с сюжетом."""
    if started(p, today):
        return []
    story = _story_on()
    return [row[0] for row in LADDER if story or row[0] not in STORY][:SOON_N]


def soon_text(key: str, **kw) -> str:
    val = (_ui().get("soon") or {}).get(key) or SOON_TEXTS[key]
    return val.format(**kw) if kw else val


# --- Тексты ------------------------------------------------------------------------------

def _ui() -> dict:
    return theme.story("cosmetics") or {}


def stock_line(item_ids: List[str]) -> str:
    """Одна строка итога рана про завоз (не больше одной за ран)."""
    from termit_app import shop
    names = ", ".join(shop.name(i) for i in item_ids)
    return (_ui().get("stock") or TEXTS["stock"]).format(names=names)


# --- Стиль: скины рамок, анимация итога, карта, титул (K4–K5) ---------------------------------
# Выбор — p["settings"]["style"] = {вид: id | None}. Ключа вида нет — выбрана первая купленная
# вещь этого вида (покупка сама «надевает» первую); None — выключено игроком (style ВИД off).
# Красных рамок нет: красный — цвет стража (токен boss tui не даёт перекрасить вовсе).

def _tok(c16: str, c256: str) -> dict:
    return {"16": c16, "256": c256}


FRAMES: Dict[str, dict] = {
    "frame_chrome": {"frame": _tok("37", "38;5;250"), "accent": _tok("37;1", "38;5;255;1")},
    "frame_gold": {"frame": _tok("33", "38;5;220"), "accent": _tok("33;1", "38;5;220;1")},
    "frame_neon": {"frame": _tok("35", "38;5;199"), "accent": _tok("36;1", "38;5;51;1")},
    "frame_ice": {"frame": _tok("36", "38;5;51"), "accent": _tok("36;1", "38;5;123;1")},
    "frame_acid": {"frame": _tok("32", "38;5;46"), "accent": _tok("32;1", "38;5;118;1")},
    # репутация (C2 М6): не продаётся, приходит со ступенью кармы (repute.REWARD)
    "frame_rep": {"frame": _tok("34", "38;5;111"), "accent": _tok("37;1", "38;5;189;1")},
}
# вещи стиля вне лестницы: не продаются и не завозятся, приходят наградой (вид → id)
REWARDS: Dict[str, List[str]] = {"frame": ["frame_rep"]}
FRAME_KINDS: Dict[str, dict] = {"frame_ice": {"single": "heavy", "round": "heavy"}}
ANIMS = {"anim_glitch": "glitch", "anim_scan": "scan", "anim_rain": "rain"}
MAP_STYLES: Dict[str, dict] = {
    "map_metro": {"kind": "metro", "marks": {"done": "●", "open": "○", "shut": "×"},
                  "lines": ("┃", "━"), "tokens": {}},
    "map_thermal": {"kind": "thermal", "marks": {"done": "▓", "open": "▒", "shut": "░"},
                    "lines": None,
                    "tokens": {"ok": _tok("33;1", "38;5;226"), "neon": _tok("33", "38;5;208"),
                               "accent": _tok("37;1", "38;5;231;1"),
                               # холодное — закрытые места: 67 (стальной синий) читается
                               # на чёрном (контраст ≥ 4,5), 17 из брифа не виден
                               "dim": _tok("36", "38;5;67")}},
}
# вид в ./termit style → вид в LADDER; порядок — порядок показа
STYLE_KINDS = {"frame": "frame", "anim": "anim", "map": "mapstyle", "title": "title"}
STYLE_TEXTS = {
    "title": "Стиль", "empty": "Стиль пуст: рамки, эффекты, карты и титулы — на витрине, "
                               "./termit shop",
    "frame": "Рамки", "anim": "Эффект итога", "map": "Карта", "title_kind": "Титул",
    "chosen": "выбрано", "off": "выключено", "none": "нет",
    "usage": "./termit style [frame|anim|map|title ID|off]",
    "set": "Выбрано: {name}.", "set_off": "{kind}: выключено.",
    "unknown_kind": "Нет такого вида: {kind}. Есть: frame, anim, map, title.",
    "unknown": "Нет такой вещи: {id}. Есть: {ids}.",
    "not_owned": "{name} ещё не куплено: ./termit shop",
    "not_yet": "Такого пока нет: вещи появляются на витрине по ходу игры.",
    "no_ids": "Пока ничего: вещи этого вида появятся на витрине по ходу игры.",
    "ids": "Есть: {ids}.",
    "bought": "Уже выбрано. Сменить или снять: ./termit style",
    "map_metro": "схема", "map_thermal": "тепло",
}


def style_text(key: str, **kw) -> str:
    text = (_ui().get("style") or {}).get(key) or STYLE_TEXTS[key]
    return text.format(**kw) if kw else text


def style_items(kind: str) -> List[str]:
    """id вещей вида ./termit style (frame, anim, map, title) в порядке лестницы; в конце —
    награды вне лестницы (REWARDS: рамка репутации)."""
    real = STYLE_KINDS.get(kind)
    return [row[0] for row in LADDER if row[1] == real] + REWARDS.get(kind, [])


def _owned(p: dict) -> List[str]:
    return [x for x in (p.get("owned") or ()) if isinstance(x, str)]


def owned_style(p: dict, kind: str) -> List[str]:
    """Купленные вещи вида в порядке покупки."""
    allowed = set(style_items(kind))
    return [x for x in _owned(p) if x in allowed]


def _style(p: dict) -> dict:
    st = (p.get("settings") or {}).get("style") if isinstance(p.get("settings"), dict) else None
    return st if isinstance(st, dict) else {}


def chosen(p: dict, kind: str) -> Optional[str]:
    """Выбранная вещь вида: явный выбор (если куплена), None — выключено, иначе первая купленная."""
    st = _style(p)
    have = owned_style(p, kind)
    if kind in st:
        if st[kind] is None:
            return None
        if st[kind] in have:
            return st[kind]
    return have[0] if have else None


def known_style(p: dict, kind: str) -> List[str]:
    """Что игрок видел: купленное и завезённое на витрину (незавезённое не раскрываем)."""
    have = owned_style(p, kind)
    allowed = set(style_items(kind))
    return have + [x for x in offers(p) if x in allowed and x not in have]


def resolve(kind: str, item_id: str) -> Optional[str]:
    """id вещи вида: полный (frame_gold) или короткий (gold)."""
    items = style_items(kind)
    if item_id in items:
        return item_id
    for iid in items:
        if iid.split("_", 1)[-1] == item_id:
            return iid
    return None


def choose(p: dict, kind: str, item_id: Optional[str]) -> None:
    """Записать выбор (None — выключить); проверки — у вызывающего."""
    settings = p.setdefault("settings", {})
    if not isinstance(settings.get("style"), dict):
        settings["style"] = {}
    settings["style"][kind] = item_id


def any_style(p: dict) -> bool:
    return any(owned_style(p, k) for k in STYLE_KINDS)


def activate(p: dict) -> None:
    """Поставить скин выбранного в tui (без выбора — сброс к виду по умолчанию)."""
    from termit_app import tui
    frame = chosen(p, "frame")
    anim = chosen(p, "anim")
    tui.set_skin(FRAMES.get(frame), FRAME_KINDS.get(frame), ANIMS.get(anim))


def map_style(p: dict) -> dict:
    """Стиль карты: kind (None — обычный), marks, lines, tokens, label (подпись в шапке)."""
    iid = chosen(p, "map")
    if iid not in MAP_STYLES:
        return {"kind": None, "marks": {}, "lines": None, "tokens": {}, "label": ""}
    return dict(MAP_STYLES[iid], label=style_text(iid))


# --- Титул, позывной, глифы приглашения (K6) ----------------------------------------------
# Позывной попадает в zsh PROMPT песочницы, а в чужом ~/.zshrc (он подключается в песочнице)
# может стоять setopt prompt_subst — тогда $(…) и `…` в приглашении исполнились бы. Поэтому
# только буквы, цифры, _ и -: ни %, ни $, ни скобок, ни кавычек, ни пробелов, ни перевода
# строки (fullmatch: у «$» в re перевод строки в конце проскочил бы). Проверка — и при записи,
# и при каждом чтении: progress.json можно поправить руками.

CALLSIGN = re.compile(r"[A-Za-zА-Яа-яЁё0-9_-]{2,12}")
# знаки приглашения glyph_pack: имя → знак (по умолчанию — первый)
GLYPHS: Dict[str, str] = {"skull": "☠", "lambda": "λ", "eye": "◉", "hex": "⌬", "delta": "▲"}

# нейтральные запасные названия титулов (строка в шапке рана); сеттинг — в теме
TITLE_NAMES: Dict[str, str] = {
    "title_cowboy": "знаток консоли", "title_icebreaker": "ледокол",
    "title_librarian": "ходячий справочник", "title_ghost": "призрак",
    "title_iron": "железная серия",
}


# подсказка после покупки вещи приглашения (нейтрально: это справка по командам)
SETUP_HINTS = {
    "palette": "Палитра — цвет пути в приглашении: ./termit home palette",
    "glyph_pack": "Знак перед курсором: ./termit home prompt glyph (☠ стоит сразу)",
    "callsign": "Задай позывной: ./termit home callsign ИМЯ",
}


def valid_callsign(name) -> bool:
    return isinstance(name, str) and CALLSIGN.fullmatch(name) is not None


def _settings(p: dict) -> dict:
    s = p.get("settings")
    return s if isinstance(s, dict) else {}


def callsign(p: dict) -> Optional[str]:
    """Позывной для шапки и приглашения (капсом); None — не куплен, снят или испорчен."""
    name = _settings(p).get("callsign")
    if "callsign" not in _owned(p) or not valid_callsign(name):
        return None
    return name.upper()


def set_callsign(p: dict, name: str) -> str:
    """Записать позывной: "ok" | "off" | "bad" (не прошёл проверку) | "not_owned"."""
    if "callsign" not in _owned(p):
        return "not_owned"
    if name == "off":
        p.setdefault("settings", {})["callsign"] = None
        return "off"
    if not valid_callsign(name):
        return "bad"
    p.setdefault("settings", {})["callsign"] = name
    return "ok"


def glyph(p: dict) -> Optional[str]:
    """Знак приглашения: None — набор не куплен или снят (home prompt glyph off).
    Ключа нет или там мусор — первый знак набора."""
    if "glyph_pack" not in _owned(p):
        return None
    s = _settings(p)
    if "glyph" in s and s["glyph"] is None:
        return None
    return s["glyph"] if s.get("glyph") in GLYPHS.values() else next(iter(GLYPHS.values()))


def resolve_glyph(want: str) -> Optional[str]:
    """Знак по имени (skull) или по самому знаку (☠); иначе None."""
    if want in GLYPHS:
        return GLYPHS[want]
    return want if want in GLYPHS.values() else None


def title_name(item_id: str) -> str:
    return (_ui().get("titles") or {}).get(item_id) or TITLE_NAMES.get(item_id, item_id)


def title_for(p: dict, today: Optional[date] = None) -> Optional[str]:
    """Титул в шапке: выбран (куплен и не снят) и ворота открыты — нашивку сначала
    заслужить, потом пришить."""
    iid = chosen(p, "title")
    gate = gate_of(iid) if iid else None
    if not gate or not GATES[gate](p, today or date.today()):
        return None
    if iid in STORY and not _story_on():
        return None
    return title_name(iid)


def header_parts(p: dict, title: str, rank: str, today: Optional[date] = None) -> tuple:
    """Шапка рана: «Ран #31 · ПОЗЫВНОЙ» и «звание · титул»; без покупок — как было."""
    cs, tt = callsign(p), title_for(p, today)
    return (f"{title} · {cs}" if cs else title), (f"{rank} · {tt}" if tt else rank)
