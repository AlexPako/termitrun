"""Убежище ./termit home: ASCII-комната из купленного и подаренного, осмотр предметов.

Каждый предмет «нарисован» командой терминала: при осмотре он показывает её и живое значение,
посчитанное на stdlib (внешние программы не вызываются, песочница не нужна). Атмосфера —
из темы (раздел home), техническая строка — отсюда. Код нейтрален: без слов сеттинга."""
import calendar
import hashlib
import math
import os
import random
import re
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from termit_app import paths, shop, theme

WIDTH = 60                  # внутренняя ширина комнаты; с рамкой и отступом — 64 символа
MONTHS = ("ЯНВ", "ФЕВ", "МАР", "АПР", "МАЙ", "ИЮН", "ИЮЛ", "АВГ", "СЕН", "ОКТ", "НОЯ", "ДЕК")
BANNER = "<< TERMITRUN >>"


def _now() -> datetime:     # подменяется в тестах
    return datetime.now()


def _load() -> tuple:
    try:
        return os.getloadavg()
    except OSError:
        return (0.0, 0.0, 0.0)


# --- Живые значения и техническая строка осмотра ------------------------------------------

def _clock_glyph(p: dict) -> str:
    return f"({_now():%H:%M})"


def _clock_look(p: dict) -> List[str]:
    t = _now()
    return [f"Часы показывают `date '+%H:%M'`: {t:%H:%M}. Хочешь секунды — `date '+%T'`: "
            f"{t:%H:%M:%S}."]


def _cal_glyph(p: dict) -> str:
    t = _now()
    return f"[{t.day:02d} {MONTHS[t.month - 1]}]"


def _cal_look(p: dict) -> List[str]:
    t = _now()
    played = {d for d in p.get("days", ()) if d.startswith(f"{t.year:04d}-{t.month:02d}-")}
    out = ["`cal` рисует месяц — неделя у него начинается с воскресенья. "
           "Звёздочкой отмечены дни, когда ты занимался:", "",
           f"   {MONTHS[t.month - 1]} {t.year}",
           "  " + "".join(f"{d:>3} " for d in ("Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб")).rstrip()]
    for week in calendar.Calendar(firstweekday=6).monthdayscalendar(t.year, t.month):
        cells = []
        for d in week:
            if not d:
                cells.append("    ")
            else:
                mark = "*" if f"{t.year:04d}-{t.month:02d}-{d:02d}" in played else " "
                cells.append(f"{d:>3}{mark}")
        out.append("  " + "".join(cells).rstrip())
    out += ["", "Хочешь весь год — `cal -y`, другой месяц — `cal 12 2026`."]
    return out


def _monitor_glyph(p: dict) -> str:
    return f"[={_load()[0]:.2f}=]"


def _monitor_look(p: dict) -> List[str]:
    a, b, c = _load()
    return [f"`uptime` — сколько машина работает без перезагрузки и средняя нагрузка за 1, 5 и "
            f"15 минут. Сейчас нагрузка: {a:.2f} {b:.2f} {c:.2f}. Больше числа ядер — машина "
            "не успевает.",
            f"Ядер у этой машины: {os.cpu_count() or '?'}. Пройдено ранов: {p.get('dozors', 0)}."]


def _shelf_glyph(p: dict) -> str:
    n = len(p.get("grimoire", {}))
    return "|" * min(n, 16) + f" {n}"


def _shelf_look(p: dict) -> List[str]:
    book = p.get("grimoire", {})
    out = [f"Книг на полке столько, сколько команд в шпаргалке — {len(book)}. Пересчитай сам: "
           "`./termit book | grep -c '•'` — `grep -c` считает строки с точкой-маркером, "
           "заголовки мест не в счёт."]
    if book:
        rng = random.Random(_now().date().toordinal())     # одна книга в день, не мельтешит
        spell = book[rng.choice(sorted(book))]
        out.append(f"С полки выпала одна: {spell} — помнишь, что делает?")
    return out


def _neon_glyph(p: dict) -> str:
    return BANNER


def _neon_look(p: dict) -> List[str]:
    return [BANNER,
            "Вывеска набрана встроенным шрифтом. Поставишь `figlet` сам (brew install figlet) — "
            "`figlet TermitRun` нарисует буквы в шесть строк ростом."]


def _trophy_look(boss: str) -> Callable[[dict], List[str]]:
    def look(p):
        from termit_app.tasks import registry
        tasks = registry.all_tasks()
        title = theme.title(tasks[boss]) if boss in tasks else boss
        return [f"Взломан: {title}. Повторить схватку без экзамена: `./termit rehearse {boss}`."]
    return look


def _no_look(p: dict) -> List[str]:
    return []


def _diary_look(p: dict) -> List[str]:
    from termit_app import diary
    return [diary.text("look", n=len(p.get("tasks") or {}))]


# --- Волна 2 (K7): часы Тибы, сейф, манэки-нэко, дека, питомец ---------------------------
# Технические строки осмотра — LOOKS (нейтрально, для фэнтези); тема переопределяет их в
# разделе cosmetics → looks. Каждая учит команде терминала в обратных кавычках.

TOKYO = timezone(timedelta(hours=9))        # в Японии нет перехода на летнее время
LOOKS: Dict[str, str] = {
    "chiba": "Второе время — Токио: `TZ=Asia/Tokyo date '+%H:%M'` покажет {t}. Переменная TZ "
             "меняет пояс только для одной команды. Все пояса — `ls /usr/share/zoneinfo`.",
    "safe": "Отпечаток файла прогресса: `shasum -a 256 progress.json | cut -c1-12` — {h}. "
            "Поменяется хоть один байт — отпечаток станет другим целиком.",
    "safe_empty": "Пока пусто: файла прогресса ещё нет. Появится — `shasum -a 256 "
                  "progress.json` даст его отпечаток.",
    "neko": "Кубик дня: {n}. Случайное число в zsh — `echo $RANDOM`, кубик — "
            "`echo $((RANDOM % 6 + 1))`: % — остаток от деления. На игру не влияет.",
    "deck_on": "Проигрыватель играет. Звук в терминале — `afplay файл.wav`.",
    "deck_off": "Проигрыватель молчит. Звук в терминале — `afplay файл.wav`.",
    # хвост осмотра деки: команда музыки есть (music) или ещё нет (soon)
    "deck_music": "Свои записи — `./termit music`.",
    "deck_soon": "Записи для него скоро появятся.",
    "pet_gnaw": "Питомец грызёт твой progress.json — на диске он занимает {size}, как "
                "покажет `du -h progress.json` (du считает занятые блоки диска, а не байты).",
    "pet_nofile": "Грызть пока нечего: progress.json ещё нет. Размер любого файла — "
                  "`du -h файл`.",
    "pet_fed": "Сыт и доволен.",
    "pet_waiting": "Ждёт у проигрывателя.",
    "pet_asleep": "Спит в системном блоке — там тепло.",
}


def look_text(key: str, **kw) -> str:
    text = ((theme.story("cosmetics") or {}).get("looks") or {}).get(key) or LOOKS[key]
    return text.format(**kw) if kw else text


def _tokyo() -> datetime:
    t = _now()
    if t.tzinfo is None:            # наивное местное время — сначала в свой пояс
        t = t.astimezone()
    return t.astimezone(TOKYO)


def _chiba_glyph(p: dict) -> str:
    return f"(TYO {_tokyo():%H:%M})"


def _chiba_look(p: dict) -> List[str]:
    return [look_text("chiba", t=f"{_tokyo():%H:%M}")]


def du_h(nbytes: int) -> str:
    """Размер как у `du -h` на macOS: 1К = 1024, меньше 10 — с одним знаком (4.0K, 12K, 1.5M)."""
    size, unit = nbytes / 1024, "K"
    for nxt in ("M", "G"):
        if size < 1024:
            break
        size, unit = size / 1024, nxt
    if size == 0:
        return "0B"
    return f"{size:.1f}{unit}" if size < 10 else f"{math.ceil(size)}{unit}"


def _disk_size() -> Optional[int]:
    """Сколько байт файл прогресса занимает на диске (блоки, как считает du); нет — None."""
    try:
        st = paths.PROGRESS_FILE.stat()
    except OSError:
        return None
    if not paths.PROGRESS_FILE.is_file():
        return None
    blocks = getattr(st, "st_blocks", None)
    return blocks * 512 if isinstance(blocks, int) else st.st_size


def _progress_bytes() -> Optional[bytes]:
    """Файл прогресса только на чтение; нет его или не читается — None."""
    try:
        return paths.PROGRESS_FILE.read_bytes()
    except OSError:
        return None


def _digest() -> Optional[str]:
    data = _progress_bytes()
    return None if data is None else hashlib.sha256(data).hexdigest()


def _safe_glyph(p: dict) -> str:
    h = _digest()
    return f"[#{h[:4]}]" if h else "[#----]"


def _safe_look(p: dict) -> List[str]:
    h = _digest()
    return [look_text("safe", h=h[:12]) if h else look_text("safe_empty")]


def _dice() -> int:
    return random.Random(_now().date().toordinal()).randint(1, 6)


def _neko_glyph(p: dict) -> str:
    return f"=^.^= {_dice()}"


def _neko_look(p: dict) -> List[str]:
    return [look_text("neko", n=_dice())]


def _deck_playing() -> bool:
    """Играет ли кассетная дека (PID-файл music, часть Q6); модуля ещё нет — молчит."""
    try:
        from termit_app import music        # type: ignore
    except ImportError:
        return False
    fn = getattr(music, "is_playing", None)
    try:
        return bool(fn()) if callable(fn) else False
    except Exception:
        return False


def _deck_glyph(p: dict) -> str:
    return "[▶oo]" if _deck_playing() else "[■oo]"


def _music_ready() -> bool:
    """Команда ./termit music есть (модуль music, часть Q6) — только тогда учим ей."""
    import importlib.util
    return importlib.util.find_spec("termit_app.music") is not None


def _deck_look(p: dict) -> List[str]:
    return [look_text("deck_on" if _deck_playing() else "deck_off") + " " +
            look_text("deck_music" if _music_ready() else "deck_soon")]


def _runs(p: dict) -> int:
    n = p.get("dozors")
    return n if isinstance(n, int) and not isinstance(n, bool) else 0


def _pet_glyph(p: dict) -> str:
    runs = _runs(p)
    body = "<:3)~" if runs < 30 else "<°3)~" if runs < 100 else "<◉3)═~"
    # каждый день сидит на новом месте вдоль стены — без случайности внутри дня
    return " " * random.Random(_now().date().toordinal() * 7).randint(0, 30) + body


def _days_away(p: dict) -> Optional[int]:
    played = []
    for d in p.get("days") or ():
        try:
            played.append(date.fromisoformat(d))
        except (TypeError, ValueError):
            continue
    return (_now().date() - max(played)).days if played else None


def _pet_mood(p: dict) -> str:
    away = _days_away(p)
    if away is None or away <= 1:
        return "pet_fed"
    return "pet_waiting" if away <= 6 else "pet_asleep"


def _pet_look(p: dict) -> List[str]:
    used = _disk_size()
    size = look_text("pet_nofile") if used is None else look_text("pet_gnaw", size=du_h(used))
    return [size, look_text(_pet_mood(p))]


TROPHY = r"\_/"


ITEMS: Dict[str, dict] = {
    "clock": {"name": "часы", "row": "wall", "glyph": _clock_glyph, "look": _clock_look},
    "calendar": {"name": "календарь", "row": "wall", "glyph": _cal_glyph, "look": _cal_look},
    "neon": {"name": "вывеска", "row": "wall", "glyph": _neon_glyph, "look": _neon_look},
    "monitor": {"name": "монитор", "row": "mid", "glyph": _monitor_glyph,
                "look": _monitor_look},
    "shelf": {"name": "полка", "row": "mid", "glyph": _shelf_glyph, "look": _shelf_look},
    # волна 2 (K7): приходят завозом косметики
    "chiba_clock": {"name": "часы другого пояса", "row": "wall", "glyph": _chiba_glyph,
                    "look": _chiba_look},
    "player": {"name": "проигрыватель", "row": "desk", "glyph": _deck_glyph,
               "look": _deck_look},
    "safe": {"name": "сейф", "row": "desk", "glyph": _safe_glyph, "look": _safe_look},
    "neko": {"name": "кошка-талисман", "row": "desk", "glyph": _neko_glyph,
             "look": _neko_look},
    "pet": {"name": "питомец", "row": "pet", "glyph": _pet_glyph, "look": _pet_look},
}
for _track in shop.TROPHY_TRACKS:
    ITEMS[f"trophy_{_track}"] = {"name": f"трофей: {_track}", "row": "mid",
                                 "glyph": lambda p: TROPHY,
                                 "look": _trophy_look(f"boss_{_track}")}
for _iid, _glyph in zip(shop.SHNYR_ITEMS, ("c[_]", "/^\\", "<0|", "[#]", "[oo]", "o-+")):
    ITEMS[_iid] = {"name": shop.get(_iid).name, "row": "floor",
                   "glyph": (lambda g: lambda p: g)(_glyph), "look": _no_look}
# бесплатный предмет: есть, пока выполняется free(p), покупать не нужно
# имя и строка осмотра — diary.text("item"/"look"): тема переопределяет их в разделе diary
ITEMS["diary"] = {"name": "", "row": "floor", "glyph": lambda p: "[≡]",
                  "look": _diary_look, "free": lambda p: bool(p.get("tasks"))}


def _board_glyph(p: dict) -> str:
    """Доска «перед глазами» (FB5): ■ — приколотая карточка, · — свободное место."""
    used = len(pinned(p))
    return "[" + "■" * used + "·" * max(0, board_slots(p) - used) + "]"


def _board_look(p: dict) -> List[str]:
    cards = ", ".join(pinned(p)) or "ничего"
    state = "" if board_on(p) else " Сейчас доска выключена: ./termit home board on."
    return [look_text("board", cards=cards, free=_free(p)) + state]


LOOKS["board"] = ("Приколото: {cards}; свободных мест: {free}. Карточки висят над строкой "
                  "ввода в каждой задаче. Приколоть, снять и посмотреть, что есть, — "
                  "./termit home board.")
ITEMS["board"] = {"name": "доска", "row": "wall", "glyph": _board_glyph, "look": _board_look}
ROWS = ("wall", "mid", "desk", "floor", "pet")     # desk и pet пустыми не рисуются


# --- Как пользоваться (FB8) ------------------------------------------------------------------
# Владелец: «надо явно добавить, как пользоваться предметами в доме, а не просто посмотреть».
# На каждую вещь — пара (коротко, полно): коротко — строкой «⚙ …» под именем в ./termit home,
# полно — строкой «Пользоваться: …» в осмотре и сразу при подарке или покупке. Если вещь
# «просто есть», так и сказано: что она показывает и где. Тема может переопределить оба текста
# (home → items → ID → use / use_short). Группы — то, что не стоит в комнате, а живёт в
# приглашении: детали, палитры, знак, позывной.

USE: Dict[str, tuple] = {
    "clock": ("просто висит: время видно прямо в комнате",
              "Делать ничего не надо — время видно прямо в комнате. А в осмотре — как "
              "спросить время у самого терминала командой date."),
    "calendar": ("звёздочки в осмотре — дни, когда ты занимался",
                 "Глянь его осмотром: звёздочкой отмечены дни, когда ты занимался, — сразу "
                 "видно, держишь ли серию. Заодно научишься команде cal."),
    "neon": ("для красоты, ничего не делает",
             "Ничего не делает, просто светит — для красоты. В осмотре подскажет, как "
             "нарисовать такие же большие буквы самому."),
    "monitor": ("нагрузка твоего Mac, в осмотре — uptime",
                "Число на нём — нагрузка твоего Mac прямо сейчас. Осмотр расскажет, что "
                "оно значит, научит uptime и посчитает, сколько раз ты уже садился играть."),
    "shelf": ("⚙ ./termit book — выученные команды целиком",
              "Книг на полке столько, сколько команд ты выучил. Перечитать их с пояснениями — "
              "./termit book (или ./termit book слово — найти нужную)."),
    "chiba_clock": ("просто висят: второе время — Токио",
                    "Делать ничего не надо — вторые часы показывают Токио. В осмотре — как "
                    "узнать время в любом поясе одной командой."),
    "player": ("⚙ ./termit music — включить свои записи",
               "Крутит купленные записи: ./termit music — что есть и что играет, "
               "./termit music play ID — включить, ./termit music stop — тишина."),
    "safe": ("отпечаток файла прогресса, в осмотре — shasum",
             "Ничего в нём не хранится — он показывает отпечаток файла с твоим прогрессом. "
             "Осмотр научит shasum: так проверяют, что файл никто не трогал."),
    "neko": ("талисман: каждый день новое число на кубике",
             "Талисман на удачу: каждый день выкидывает новое число. На игру не влияет — "
             "зато осмотр покажет, как бросить кубик в самом терминале."),
    "pet": ("живёт сам, растёт, пока ты играешь",
            "Ухаживать не нужно — живёт сам и подрастает, пока ты играешь. Осмотр покажет, "
            "сколько места на диске занимает файл, который он грызёт (du -h)."),
    "diary": ("⚙ ./termit diary — уроки и разборы пройденного",
              "Перечитать уроки и разборы того, что уже прошёл: ./termit diary — список, "
              "./termit diary N — нужная запись. Бесплатно."),
    "board": ("⚙ ./termit home board — что висит над приглашением",
              "Что приколешь, то и висит над приглашением в каждой задаче: ./termit home board "
              "— что можно, потом pin КАРТОЧКА — приколоть, unpin — снять."),
    # не в комнате — в приглашении (строке перед курсором в задаче)
    "prompt": ("⚙ ./termit home prompt — что стоит, вкл/выкл",
               "Детали собираются в твоё приглашение — строку перед курсором в задаче: "
               "./termit home prompt — что стоит, on/off — включить или выключить, show — "
               "как устроено, чтобы перенести к себе."),
    "palette": ("⚙ ./termit home palette ID — цвет пути",
                "Палитра красит путь в приглашении: ./termit home palette — какие есть, "
                "./termit home palette ID — выбрать, off — без цвета."),
    "glyph_pack": ("⚙ ./termit home prompt glyph — знак у курсора",
                   "Знак перед курсором: ./termit home prompt glyph — какие есть, "
                   "./termit home prompt glyph CHAR — поставить, off — убрать."),
    "callsign": ("⚙ ./termit home callsign NAME — свой позывной",
                 "Позывной встанет в шапку и в приглашение: ./termit home callsign NAME — "
                 "задать (буквы, цифры, _ и -), off — снять."),
}
USE_GROUPS = ("prompt", "palette", "glyph_pack", "callsign")
for _track in shop.TROPHY_TRACKS:
    USE[f"trophy_{_track}"] = (
        f"⚙ ./termit rehearse boss_{_track} — реванш без экзамена",
        f"Висит в честь победы. Хочешь размяться ещё раз — ./termit rehearse boss_{_track}: та "
        "же схватка, но без экзамена и без риска.")
for _iid in shop.SHNYR_ITEMS:
    USE[_iid] = ("просто лежит: вещь из прошлого",
                 "Пользоваться не нужно — это вещь из прошлого, её история в осмотре. "
                 "Сколько таких уже собрано — ./termit case.")


def use_key(item_id: str) -> Optional[str]:
    """Чей текст «как пользоваться» у вещи: свой, группы приглашения или ничей (места доски)."""
    if item_id in ITEMS or item_id in USE_GROUPS:
        return item_id
    if item_id in PROMPT_PARTS:
        return "prompt"
    if item_id in PALETTE_COLORS:
        return "palette"
    return None


USE_PLAYER_SOON = ("пока молчит: записи скоро появятся",
                   "Пока молчит — записи для него скоро появятся. Осмотр покажет, как "
                   "проиграть звук в терминале самому.")


def _use(key: str) -> tuple:
    t = (_ui().get("items") or {}).get(key) or {}
    short, full = USE_PLAYER_SOON if key == "player" and not _music_ready() else USE[key]
    return t.get("use_short") or short, t.get("use") or full


def use_short(key: str) -> str:
    return _use(key)[0]


def use_text(key: str) -> str:
    return _use(key)[1]


def use_news(item_ids, skip=()) -> List[str]:
    """Строки «как пользоваться» для только что полученного: по одной на вещь или группу.
    Доска и места на ней молчат — о них говорит board_enable."""
    out, seen = [], set(skip) | {BOARD}
    for iid in item_ids:
        key = use_key(iid)
        if key is None or key in seen:
            continue
        seen.add(key)
        text = _with_look(key, use_text(key))
        if len(text) > 1 and text[1].islower():     # после двоеточия — со строчной
            text = text[0].lower() + text[1:]
        out.append(f"⚙ {_use_name(key)}: {text}")
    return out


def _with_look(key: str, text: str) -> str:
    """Вещь «просто есть» — где на неё посмотреть: осмотр по её ID."""
    if key in ITEMS and "./termit " not in text:
        return f"{text} Осмотреть — ./termit home look {key}."
    return text


def _use_name(key: str) -> str:
    names = {"prompt": "детали приглашения", "palette": "палитра", "glyph_pack": "знак",
             "callsign": "позывной"}
    return names.get(key) or name(key)


# --- Тексты темы ---------------------------------------------------------------------------

def _ui() -> dict:
    return theme.story("home")


def title() -> str:
    return _ui().get("title") or "Убежище"


def name(item_id: str) -> str:
    """Имя предмета: из раздела home темы, иначе из витрины, иначе нейтральное."""
    t = (_ui().get("items") or {}).get(item_id) or {}
    if t.get("name"):
        return t["name"]
    if item_id == "diary":
        from termit_app import diary
        return diary.text("item")
    if shop.get(item_id) is None and item_id in ITEMS:     # бесплатный, не из витрины
        return ITEMS[item_id]["name"]
    return shop.name(item_id)


def flavour(item_id: str) -> Optional[str]:
    return ((_ui().get("items") or {}).get(item_id) or {}).get("look") or None


def owned_items(p: dict) -> List[str]:
    """Предметы убежища, которые есть у игрока, в порядке ITEMS (сюжетные — только в теме
    с сюжетом)."""
    have = set(p.get("owned", ()))
    out = []
    for iid in ITEMS:
        item = shop.get(iid)
        free = ITEMS[iid].get("free")
        has = iid in have or (free is not None and free(p))
        hidden_story = bool(item and item.story and not _story_on())
        if has and not hidden_story:
            out.append(iid)
    return out


def _story_on() -> bool:
    from termit_app import story
    return story.has_story()


# --- Ещё твоё: купленное, что не стоит в комнате (FB5 п. 17) --------------------------------
# Владелец купил место на доске и страницу досье — и в доме не нашёл ни того, ни другого.
# Теперь всё купленное видно в ./termit home: вещи — в комнате, места доски — в строке доски,
# остальное — разделом «Ещё твоё» с подсказкой, где оно и как им пользоваться. Тот же текст
# «где и как» печатает покупка любого вида (where_text).

STYLE_ARG = {"frame": "frame", "anim": "anim", "mapstyle": "map", "title": "title"}
# (группа, заголовок, виды витрины) — порядок раздела «Ещё твоё»
EXTRA_GROUPS = (("prompt", "детали", ("prompt",)), ("palette", "палитры", ("palette",)),
                ("glyph_pack", "знак", ("glyph",)), ("callsign", "позывной", ("callsign",)),
                ("dossier", "досье", ("dossier",)), ("fragment", "фрагменты", ("fragment",)),
                ("deck", "дека", ("module", "slot")), ("sound", "звуки", ("sound", "soundpack")),
                ("style", "стиль", tuple(STYLE_ARG)), ("tape", "записи", ("tape",)))
EXTRA_SHORT = {
    "dossier": "⚙ ./termit dossier {who} — читать страницы",
    "fragment": "⚙ ./termit case — где лежат и как открыть",
    "deck": "⚙ ./termit deck — что стоит в слотах, on/off ID",
    "sound": "⚙ ./termit sound — on/off, pack ID, test",
    "style": "⚙ ./termit style — надеть или снять: ВИД ID",
    "tape": "⚙ ./termit music play ID — включить запись",
}
KIND_WHERE = {
    "freeze": "Заморозка лежит в запасе и сама спасёт серию, если пропустишь день. Сколько "
              "их — ./termit stats.",
    "tip": "Наводка записана: в одном из ближайших дел осколок памяти точно найдётся. "
           "Найденное — ./termit memory.",
    "dossier": "Страница легла в досье: ./termit dossier {who} — все его страницы.",
    "fragment": "Фрагмент — в деле: ./termit case покажет, где он лежит и как его открыть.",
    "module": "Модуль работает сам со следующего дела. Что стоит в слотах, поставить или "
              "снять — ./termit deck (on/off ID).",
    "slot": "Слот появился в деке: ./termit deck — что стоит, ./termit deck on ID — "
            "поставить модуль.",
    "sound": "Звук играет сам — на взломе, рекорде, вехе. Выключить — ./termit sound off, "
             "послушать — ./termit sound test.",
    "soundpack": "Набор звуков: ./termit sound pack {id} — поставить, ./termit sound test — "
                 "послушать.",
    "style": "Это стиль: ./termit style — что надето, ./termit style {arg} {id} — надеть.",
    "tape": "Запись для проигрывателя: ./termit music play {id} — включить, ./termit music "
            "stop — тишина.",
    "board": "Ещё одно место на доске: что приколото и что можно добавить — ./termit home "
             "board.",
}
GROUP_OF_KIND = {k: key for key, _title, kinds in EXTRA_GROUPS for k in kinds}


def where_text(item_id: str) -> Optional[str]:
    """Где купленная вещь теперь и как ею пользоваться — для строки после покупки."""
    item = shop.get(item_id)
    if item is None:
        return None
    if item_id in ITEMS:
        return _with_look(item_id, use_text(item_id))
    group = GROUP_OF_KIND.get(item.kind)
    if group in USE_GROUPS:
        return use_text(group)
    kind = "style" if item.kind in STYLE_ARG else item.kind
    text = KIND_WHERE.get(kind)
    if text is None:
        return None
    return text.format(who=item_id[:-1], id=item_id, arg=STYLE_ARG.get(item.kind, ""))


def extra_groups(p: dict) -> List[tuple]:
    """(группа, заголовок, id) купленного не для комнаты; места доски — в строке доски."""
    have = [i for i in p.get("owned") or () if isinstance(i, str)]
    out = []
    for key, title, kinds in EXTRA_GROUPS:
        ids = []
        for iid in have:
            item = shop.get(iid)
            if item is None or item.kind not in kinds or iid in ITEMS or iid in ids:
                continue
            if item.story and not _story_on():
                continue
            ids.append(iid)
        if ids:
            out.append((key, title, ids))
    return out


def _extra_short(key: str, ids: List[str]) -> str:
    if key in USE_GROUPS:
        return use_short(key)
    whos = sorted({i[:-1] for i in ids})
    return EXTRA_SHORT[key].format(who=whos[0] if len(whos) == 1 else "NAME")


def _extra_lines(p: dict) -> List[str]:
    from termit_app import ui
    groups = extra_groups(p)
    if not groups:
        return []
    out = ["", "  Ещё твоё (не для комнаты):"]
    for key, title, ids in groups:
        names = ", ".join(shop.name(i).replace(" ", ui.NBSP) for i in ids)   # имя не рвётся
        out += ui.story_fill(f"{title:14} {names}", "  ", " " * 17).splitlines()
        out.append(" " * 17 + _mark(_extra_short(key, ids)))
    return out


def _board_short(p: dict) -> str:
    from termit_app import tui
    cards = ", ".join(pinned(p)) or "пусто"
    text = f"⚙ ./termit home board — мест {board_slots(p)} из {1 + len(BOARD_SLOTS)}: {cards}"
    return tui.trunc(text, 57)


# --- Витрина из дома (FB5 п. 16) -------------------------------------------------------------
# Владелец: «стоит в игре упоминать, что есть магазин, доступный из дома». На экране дома —
# всегда строка про витрину; один раз (первые деньги или первый подарок) — подсказка, где
# тратить. Память — p["settings"]["shop_tip"], как board_seen: старое сохранение читается.

SHOP_LINE = ("Витрина: вещи за {cash} — их платят за решённые задачи. Зайти — ./termit shop "
             "или прямо отсюда: ./termit home shop")
SHOP_TIP = ("{cash} Заработанное тратят на витрине: ./termit shop (или из дома: "
            "./termit home shop) — вещи для дома, подсказки и не только.")


def _shop_text(key: str, default: str) -> str:
    return (_ui().get(key) or default).format(cash=theme.word("money"))


def shop_line() -> str:
    return _shop_text("shop_line", SHOP_LINE)


def shop_tip(p: dict) -> Optional[str]:
    """Подсказка про витрину — один раз за игру; потом None."""
    s = _settings(p)
    if s.get("shop_tip"):
        return None
    s["shop_tip"] = True
    return _shop_text("shop_tip", SHOP_TIP)


# --- Комната -------------------------------------------------------------------------------

def _row(glyphs: List[str], side: str = "|", inner: int = WIDTH) -> str:
    text = "   ".join(glyphs)
    if len(text) > inner - 4:
        text = text[:inner - 5] + "…"
    return f"  {side}  {text:<{inner - 2}}{side}"


def _rows(glyphs: List[str], side: str, inner: int, wrap: bool) -> List[str]:
    """Ряд комнаты; wrap — не влезло, вещи переносятся на следующую строку (пульт FB19), а не
    обрезаются «…» (так рисует ./termit home)."""
    if not wrap:
        return [_row(glyphs, side, inner)]
    lines, cur = [], []
    for g in glyphs:
        if cur and len("   ".join(cur + [g])) > inner - 4:
            lines.append(cur)
            cur = []
        cur.append(g)
    return [_row(part, side, inner) for part in lines + [cur]]


FRAMES = {"ascii": ("+", "+", "+", "+", "-", "|"),       # как всегда (basic, plain)
          "box": ("┌", "┐", "└", "┘", "─", "│")}          # рамка линиями (rich)
NEW_MARK = {"ascii": "*", "box": "✦"}                    # новая вещь на пульте (FB19)
PLAYER_STILL = "[■oo]"


def glyph(p: dict, item_id: str, still: bool = False) -> str:
    """Значок вещи. still — для пульта: без проверки процессов (играет ли запись) и без
    сдвига питомца вдоль стены — значок короткий и считается мгновенно."""
    if still and item_id == "player":
        return PLAYER_STILL
    if still and item_id == "shelf":            # полка короче: на пульте мало места
        n = len(p.get("grimoire", {}))
        return "|" * max(1, min(n, 4)) + f" {n}"
    g = ITEMS[item_id]["glyph"](p)
    return g.strip() if still else g


def render(p: dict, frame: str = "ascii", inner: int = WIDTH, extra: Optional[dict] = None,
           marks=(), still: bool = False) -> List[str]:
    """ASCII-комната: не больше 12 строк (рамка — WIDTH + 4 символа), только купленное и подаренное.
    frame="box" — стены линиями ┌─┐ (графика rich), предметы те же.
    Для пульта (FB19): inner — своя ширина (ряды тогда переносятся), extra — {ряд: [значки]}
    сверх вещей комнаты (дека, звуки, досье), marks — id вещей с пометкой «новое», still —
    см. glyph()."""
    items = owned_items(p)
    extra = extra or {}
    wrap = inner != WIDTH
    tl, tr, bl, br, h, v = FRAMES[frame]
    top, edge = f"  {tl}" + h * inner + tr, f"  {bl}" + h * inner + br
    out = [f"  {title()}", top]
    if not items and not any(extra.values()):
        empty = _ui().get("empty") or "Голые стены. Вещи появятся из подарков и с витрины."
        out += [_row([], v, inner), _row(["[____]"], v, inner), edge]
        from termit_app import ui
        out.append(ui.story_fill(empty, "  ", "  "))
        return out[:12]
    mark = NEW_MARK[frame]

    def drawn(i: str) -> str:
        return glyph(p, i, still) + (mark if i in marks else "")
    by_row = {r: [drawn(i) for i in items if ITEMS[i]["row"] == r] + list(extra.get(r, ()))
              for r in ROWS}
    out += _rows(by_row["wall"], v, inner, wrap)
    out.append(_row([], v, inner))
    out += _rows(by_row["mid"], v, inner, wrap)
    if by_row["desk"]:
        out += _rows(by_row["desk"], v, inner, wrap)
    out += _rows(by_row["floor"] + ["[____]"], v, inner, wrap)      # матрас стоит всегда
    if by_row["pet"]:
        out += _rows(by_row["pet"], v, inner, wrap)
    out.append(edge)
    return out


def listing(p: dict) -> List[str]:
    """Под комнатой: что есть и как осмотреть."""
    items = owned_items(p)
    out = []
    for iid in items:
        short = _board_short(p) if iid == BOARD else use_short(iid)
        out += [f"  {iid:14} {name(iid)}", f"{' ' * 17}{_mark(short)}"]
    out += _extra_lines(p)
    if not out:
        return []
    return out + ["", "  осмотреть: ./termit home look ID · пользоваться — см. ⚙"]


def _mark(short: str) -> str:
    return short if short.startswith("⚙") else "⚙ " + short


def look(p: dict, item_id: str) -> List[str]:
    """Осмотр: имя, строка атмосферы из темы, команда и живое значение."""
    if item_id not in ITEMS:
        have = ", ".join(owned_items(p))
        return [f"Нет такого предмета: {item_id}." + (f" Есть: {have}." if have else ""),
                "Осмотреть: ./termit home look ID (список — ./termit home)"]
    if item_id not in owned_items(p):
        return [f"{name(item_id)} — этого у тебя пока нет. Витрина: ./termit shop"]
    out = [name(item_id)]
    fl = flavour(item_id)
    if fl:
        out.append(fl)
    return out + ITEMS[item_id]["look"](p) + [f"Пользоваться: {use_text(item_id)}"]


# --- Конструктор приглашения zsh (E8) ------------------------------------------------------
# Только приглашение внутри песочницы: родитель передаёт строки через TERMIT_PROMPT и
# TERMIT_RPROMPT, .zshrc игры ставит их поверх темы владельца. Настоящий ~/.zshrc игра не
# трогает — `prompt show` печатает строки, перенести их игрок может сам.

PROMPT_PARTS: Dict[str, str] = {
    "path_short": "%1~",
    "path_full": "%~",
    "exit_code": "%(?..%F{red}✗%?%f )",
    "deck_icon": "%F{magenta}⟁%f ",
    "two_lines": "\n",
    "time_right": "%*",
}
PALETTE_COLORS: Dict[str, int] = {"pal_neon": 201, "pal_toxic": 46, "pal_ice": 51,
                                  "pal_amber": 214,
                                  # волна 2 (K6): приходят завозом, не цепочкой витрины
                                  "pal_blood": 196, "pal_dusk": 141, "pal_chrome": 250,
                                  "pal_rust": 166}
CALLSIGN_COLOR = 117        # позывной: свой цвет, не совпадает ни с одной палитрой
WAVE2_PARTS = ("glyph_pack", "callsign")    # косметика приглашения: тоже включает его
EXPLAIN: Dict[str, str] = {
    "%1~": "%1~ — только последняя папка пути (дом — значком ~)",
    "%~": "%~ — весь путь, дом сокращён до ~",
    "%(?..%F{red}✗%?%f )": "%(?..X) — «если код возврата 0, ничего, иначе X»: красный ✗ и "
                           "сам код %? упавшей команды",
    "%F{magenta}⟁%f ": "%F{magenta}…%f — цвет до %f; ⟁ — просто символ",
    "\n": "$'\\n' — перевод строки: путь сверху, курсор снизу",
    "%# ": "%# — # у root, % у всех остальных",
    "%*": "RPROMPT — правое приглашение; %* — время с секундами",
}


def _settings(p: dict) -> dict:
    return p.setdefault("settings", {})


def prompt_parts(p: dict) -> List[str]:
    """Детали приглашения, которые есть у игрока."""
    have = set(p.get("owned", ()))
    return [pid for pid in PROMPT_PARTS if pid in have]


def palettes(p: dict) -> List[str]:
    have = set(p.get("owned", ()))
    return [x for x in PALETTE_COLORS if x in have]


def prompt_on(p: dict) -> bool:
    return bool(_settings(p).get("prompt"))


def _glyph_part(g: str) -> str:
    return f"%F{{magenta}}{g}%f "


def _callsign_part(name: str) -> str:
    return f"%F{{{CALLSIGN_COLOR}}}{name}%f "


def build_prompt(p: dict):
    """(PROMPT, RPROMPT) из деталей; None — своё приглашение выключено или деталей нет
    (тогда в песочнице остаётся приглашение темы владельца). Позывной и глиф берутся из
    cosmetics: там они проверены строго (безопасны и при prompt_subst)."""
    from termit_app import cosmetics
    parts = set(prompt_parts(p))
    glyph, name = cosmetics.glyph(p), cosmetics.callsign(p)
    if not prompt_on(p) or not (parts or glyph or name):
        return None, None
    s = _settings(p)
    path = ""
    if "path_full" in parts and (s.get("prompt_path") != "short" or "path_short" not in parts):
        path = PROMPT_PARTS["path_full"]
    elif "path_short" in parts:
        path = PROMPT_PARTS["path_short"]
    color = PALETTE_COLORS.get(s.get("palette")) if s.get("palette") in palettes(p) else None
    head = PROMPT_PARTS["deck_icon"] if "deck_icon" in parts else ""
    if glyph:                                       # глиф встаёт вместо ⟁
        head = _glyph_part(glyph)
    if name:
        head += _callsign_part(name)
    if path:
        head += (f"%F{{{color}}}{path}%f" if color else path) + " "
    if "exit_code" in parts:
        head += PROMPT_PARTS["exit_code"]
    if head and "two_lines" in parts:
        head += PROMPT_PARTS["two_lines"]
    left = head + "%# " if head else None
    right = PROMPT_PARTS["time_right"] if "time_right" in parts else None
    return left, right


def zsh_quote(value: str) -> str:
    """Строка для ~/.zshrc: '…', перевод строки — через $'\\n'."""
    return "'" + value.replace("'", "'\\''").replace("\n", "'$'\\n''") + "'"


def explain_prompt(p: dict) -> List[str]:
    """`prompt show`: готовые строки и объяснение каждого куска."""
    left, right = build_prompt(p)
    if left is None and right is None:
        return ["Своё приглашение выключено или деталей нет: в песочнице — приглашение твоей "
                "темы. Включить: ./termit home prompt on"]
    out = []
    if left:
        out.append(f"  PROMPT={zsh_quote(left)}")
    if right:
        out.append(f"  RPROMPT={zsh_quote(right)}")
    out += ["", "Что здесь что:"]
    notes = {k: v for k, v in EXPLAIN.items() if k != "%*" and left and k in left}
    from termit_app import cosmetics
    glyph, name = cosmetics.glyph(p), cosmetics.callsign(p)
    if glyph and left and _glyph_part(glyph) in left:
        notes[_glyph_part(glyph)] = (f"{glyph} — просто символ Юникода U+{ord(glyph):04X}; "
                                     f"напечатать его: printf '\\u{ord(glyph):04x}'")
    if name and left and _callsign_part(name) in left:
        notes[_callsign_part(name)] = (f"%F{{{CALLSIGN_COLOR}}}{name}%f — позывной: только "
                                       "буквы, цифры, _ и -, поэтому в приглашении ничего "
                                       "не исполнится")
    pal = _settings(p).get("palette")      # руками могли записать что угодно, даже список
    color = PALETTE_COLORS.get(pal) if pal in palettes(p) else None
    mark = f"%F{{{color}}}"
    if color and left and mark in left:
        notes[mark] = (f"%F{{{color}}}…%f — цвет пути: номер {color} из 256 цветов терминала "
                       f"(проверь: printf '\\e[38;5;{color}mцвет\\e[0m\\n')")
    order = sorted(notes, key=lambda k: left.index(k))
    if right:
        notes["%*"] = EXPLAIN["%*"]
        order.append("%*")
    from termit_app import ui
    out += [ui.story_fill(notes[k], "  ", "      ") for k in order]
    out += ["", "Перенеси в свой ~/.zshrc сам — игра его не трогает. Метка задачи [id] "
                "в песочнице добавляется отдельно."]
    return out


def auto_enable(p: dict, item_ids) -> Optional[str]:
    """Первая деталь сама включает своё приглашение; первая палитра выбирается сама.
    Вернуть строку для игрока, если приглашение только что включилось."""
    s = _settings(p)
    msg = None
    for iid in item_ids:
        if (iid in PROMPT_PARTS or iid in WAVE2_PARTS) and "prompt" not in s:
            s["prompt"] = True
            msg = ("Своё приглашение включено. Приглашение (prompt) — строка перед курсором, "
                   "где набираешь команды: подарок добавил в неё своё, увидишь в следующей "
                   "задаче. Как устроено — ./termit home prompt show, выключить — "
                   "./termit home prompt off (обе набирают после рана, не в задаче).")
        if iid in PALETTE_COLORS and s.get("palette") not in palettes(p):
            s["palette"] = iid
    board = board_enable(p, item_ids)       # FB5: доска и места на ней
    return " ".join(m for m in (msg, board) if m) or None


PROMPT_WHAT = ("Приглашение (по-английски prompt) — надпись в начале строки ввода в задаче, "
               "перед курсором: терминал как бы говорит «готов, вводи». Хорошее приглашение "
               "сразу показывает, где ты стоишь и не упала ли прошлая команда.")
# как деталь выглядит на деле (папка-пример drum внутри ~/projects/drum/src)
PROMPT_LOOKS: Dict[str, str] = {
    "path_short": "drum % — только папка, где стоишь",
    "path_full": "~/projects/drum/src % — весь путь от дома (~ — домашняя папка)",
    "exit_code": "drum ✗1 % — красный ✗ и код ошибки, только если прошлая команда упала",
    "deck_icon": "⟁ drum % — значок деки в начале",
    "two_lines": "путь на одной строке, ввод — на следующей: длинный путь не съедает место",
    "time_right": "время у правого края: …   18:15:07",
}


def prompt_sample(left: str, right: str) -> str:
    """Собранное приглашение — так, как его видно в задаче (пример: папка drum, прошлая
    команда упала с кодом 1), без кодов zsh."""
    text = left
    for code, shown in (("%F{red}", ""), ("%F{magenta}", ""), ("%f", ""), ("%1~", "drum"),
                        ("%~", "~/projects/drum/src"), ("%(?..", ""), ("✗%? )", "✗1 "),
                        ("%#", "%")):
        text = text.replace(code, shown)
    text = re.sub(r"%F\{\d+\}", "", text)
    rows = text.split("\n")
    if right:
        rows[-1] = rows[-1] + "▌" + " " * 8 + right.replace("%*", "18:15:07")
    else:
        rows[-1] += "▌"
    return "\n".join(rows)


def prompt_lines(p: dict) -> List[str]:
    """`./termit home prompt`: что это, как выглядит сейчас, детали с примером вида — есть и
    можно купить (владелец 21.10: «совсем непонятно, что за промпт, что за приглашение,
    какие-то цифры, знаки»). Коды zsh — только в prompt show."""
    from termit_app import commands, tui, ui
    pre = "" if commands.hub_on() else "./termit home "
    have = set(prompt_parts(p))
    cash = theme.word("money")
    out = [*ui.story_fill(PROMPT_WHAT, "", "").splitlines(), ""]
    left, right = build_prompt(p)
    if prompt_on(p) and (left or right):
        out += ui.story_fill("Сейчас в задачах оно выглядит так (пример: ты в папке drum, "
                             "прошлая команда упала):", "", "").splitlines()
        out += ["    " + row for row in prompt_sample(left, right).split("\n")]
    else:
        out.append("Сейчас своё приглашение выключено: в задачах — обычное приглашение игры. "
                   f"Включить — {pre}prompt on.")
    on_sale = {i.id for i in shop.visible(p, date.today())}
    owned = [pid for pid in PROMPT_PARTS if pid in have]
    buy = [pid for pid in PROMPT_PARTS if pid not in have]
    if owned:
        out += ["", "Детали, которые у тебя есть:"]
        out += [ui.story_fill(f"{pid} — {PROMPT_LOOKS[pid]}", "  ", "      ") for pid in owned]
    if buy:
        out += ["", "Можно купить:"]
        for pid in buy:
            price = (f" · {shop.get(pid).price} {cash}, купить: shop {pid}" if pid in on_sale
                     else " · пока не продаётся")
            out.append(ui.story_fill(f"{pid} — {PROMPT_LOOKS[pid]}{price}", "  ", "      "))
    pals = palettes(p)
    if pals:
        cur = _settings(p).get("palette")
        out += ["", "Палитры (цвет пути): " + ", ".join(
            (f"▸{x[4:]}" if x == cur else x[4:]) for x in pals) + f" — выбрать: {pre}palette ID"]
    out += ["", "Как поменять (набирай здесь, в убежище):",
            f"  {pre}prompt off — выключить своё приглашение",
            f"  {pre}prompt on — включить снова",
            f"  {pre}prompt path full — весь путь",
            f"  {pre}prompt path short — только папка",
            f"  {pre}prompt show — как это записано на языке zsh,",
            "  чтобы перенести такое же приглашение в свой терминал (~/.zshrc)",
            "  Изменения видно со следующей задачи."]
    return [row for x in out for row in (x.split("\n") if "\n" in x else [x])]


# --- Доска «перед глазами» (FB5, п. 8) -------------------------------------------------------
# Предмет убежища board: что к нему приколото, игра показывает строками над приглашением в
# каждой задаче (env TERMIT_TIPS → .zshrc игры). Одна карточка — одна строка из
# ui.BOARD_CARDS (выжимки шпаргалки keys) или совет дня (каталог lifehacks). Места: одно с доской, board2 —
# витрина, board3 — подарок за стража «Основ». Настройки — в p["settings"]: board (вкл/выкл),
# board_cards (приколотые), board_seen (о каких карточках уже сказано), board_turn (счётчик
# совета дня). Старое сохранение без этих полей читается значениями по умолчанию.

BOARD = "board"
BOARD_SLOTS = ("board2", "board3")
CARDS = ("keys-line", "keys-history", "keys-screen", "game", "rotate", "hunt")
DEFAULT_CARDS = ["keys-line"]
GAME_CARD = "game"          # сама висит над приглашением, пока не взят страж «Основ»
BASICS_BOSS = "boss_basics"
# карточка открыта: None — сразу; иначе решён урок или взят страж с этим id
CARD_OPEN: Dict[str, Optional[str]] = {"keys-line": None, "game": None,
                                       "keys-history": "history_recall",
                                       "keys-screen": "screen_scroll", "rotate": BASICS_BOSS}
CARD_NAMES = {"keys-line": "клавиши правки строки",
              "keys-history": "история команд",
              "keys-screen": "экран: прокрутка и очистка",
              "game": "команды игры в задаче",
              "rotate": "совет дня: приём терминала, каждую задачу новый",
              "hunt": "охота: что искать в песочницах, кроме задания"}
# владелец 23.10: «прочитал про хабар раз — и забыл, что мы вообще ищем»: карточка открыта,
# как только кто-то рассказал про охоту (флаги story.HUNT_FLAGS и подсказка хабара loot)
HUNT_OPEN = ("paydata_hint", "shard_hint", "nol_hint", "db_hint", "script_hint")


def has_board(p: dict) -> bool:
    return BOARD in (p.get("owned") or ())


def board_slots(p: dict) -> int:
    """Мест на доске: одно с самой доской и по одному за board2/board3; без доски — 0."""
    if not has_board(p):
        return 0
    owned = p.get("owned") or ()
    return 1 + sum(1 for slot in BOARD_SLOTS if slot in owned)


def basics_on(p: dict) -> bool:
    """Идут «Основы»: страж первого места не взят — game висит над приглашением сама."""
    return BASICS_BOSS not in (p.get("bosses") or ())


def card_open(p: dict, card: str) -> bool:
    if card == "hunt":
        return any(f in (p.get("flags") or ()) for f in HUNT_OPEN)
    need = CARD_OPEN.get(card, "")
    if need is None:
        return True
    if need.startswith("boss_"):
        return need in (p.get("bosses") or ())
    rec = (p.get("tasks") or {}).get(need)
    return isinstance(rec, dict) and bool(rec.get("solved"))


def open_cards(p: dict) -> List[str]:
    return [card for card in CARDS if card_open(p, card)]


def board_on(p: dict) -> bool:
    return has_board(p) and _settings(p).get("board") is not False


def pinned(p: dict) -> List[str]:
    """Приколотые карточки: известные, открытые, без повторов, не больше мест. Мусор в
    сохранении (не список, чужие слова) не роняет игру — остаётся то, что можно показать."""
    raw = _settings(p).get("board_cards")
    if not isinstance(raw, list):
        raw = DEFAULT_CARDS
    out: List[str] = []
    for card in raw:
        if isinstance(card, str) and card in CARDS and card_open(p, card) and card not in out:
            out.append(card)
    return out[:board_slots(p)]


def _rotate_tips(p: dict) -> List[str]:
    """FB10: советы дня — только из каталога лайфхаков (termit_app/lifehacks.py), от простых
    к сложным и только то, что игрок уже может применить (решена задача after)."""
    from termit_app import lifehacks, ui
    return [tip for tip in lifehacks.tips(p) if _width(tip) <= ui.BOARD_WIDTH]


def _width(text: str) -> int:
    from termit_app import tui
    return tui.vlen(text)


def _turn(p: dict) -> int:
    turn = _settings(p).get("board_turn")
    return turn if isinstance(turn, int) and not isinstance(turn, bool) and turn >= 0 else 0


def card_text(p: dict, card: str) -> str:
    from termit_app import ui
    if card == "rotate":
        tips = _rotate_tips(p)
        return tips[_turn(p) % len(tips)] if tips else ""
    if card == "hunt":
        from termit_app import story
        return story.hunt_card(p)
    from termit_app import theme
    return ui.BOARD_CARDS[card].replace("{money}", theme.word("money_name"))


def game_rows(p: dict) -> List[str]:
    """Подсказки игры над приглашением — готовыми строками: валюта темы, перенос по окну."""
    return _board_rows(card_text(p, GAME_CARD))


def board_tick(p: dict) -> None:
    """Новая задача — следующий совет дня (только если он приколот)."""
    if board_on(p) and "rotate" in pinned(p):
        _settings(p)["board_turn"] = _turn(p) + 1


def board_lines(p: dict, game: bool = True) -> List[str]:
    """Строки над приглашением в задаче. Без доски — как до неё: команды игры, пока идут
    «Основы». Доска выключена — ничего. game=False — без команд игры (после решения их
    заменяет своя строка linger_tips)."""
    from termit_app import ui
    if not has_board(p):
        return game_rows(p) if game and basics_on(p) else []
    if not board_on(p):
        return []
    cards = pinned(p)
    if basics_on(p) and GAME_CARD not in cards:
        cards = cards + [GAME_CARD]             # внизу, у самого приглашения — как раньше
    if not game:
        cards = [card for card in cards if card != GAME_CARD]
    return [row for text in (card_text(p, card) for card in cards) if text
            for row in _board_rows(text)]


def _board_rows(text: str) -> List[str]:
    """FB17: карточка доски — строкой по ширине окна (до 100); в узком окне — переносом по
    словам, продолжение с отступом (zsh печатает строки над приглашением как есть)."""
    from termit_app import tui
    width = tui.text_width()
    return [text] if tui.vlen(text) <= width else tui.fill(text, width, "", "  ")


def _free(p: dict) -> int:
    return board_slots(p) - len(pinned(p))


def _pin(p: dict, card: str) -> None:
    _settings(p)["board_cards"] = pinned(p) + [card]


def _autopin(p: dict) -> Optional[str]:
    """Свободное место — первой открытой, но не приколотой карточке (кроме game). Вернуть её."""
    if not board_on(p) or _free(p) <= 0:
        return None
    card = next((c for c in open_cards(p) if c != GAME_CARD and c not in pinned(p)), None)
    if card:
        _pin(p, card)
    return card


BOARD_TEXTS = {
    "gift": ("Доска: что на неё приколешь, то и будет висеть строкой над приглашением (это "
             "строка, где набираешь команды) — в каждой задаче, начиная со следующей. Пока там "
             "клавиши правки строки и, до конца «Основ», команды игры. Что ещё приколоть — "
             "./termit home board (набирай после рана, не в задаче)."),
    "slot": "На доске новое место — {free} свободно. Что приколоть: ./termit home board",
    "slot_auto": ("На доске новое место, и туда сразу встала карточка {card} ({name}). "
                  "Доска: ./termit home board"),
    "card_pinned": ("📌 Новая карточка на доске: {card} ({name}) — встала в свободное место, "
                    "увидишь над приглашением в следующей задаче. Доска: ./termit home board"),
    "card_new": ("📌 Новая карточка для доски: {card} ({name}). Свободных мест нет — что "
                 "снять, чтобы приколоть эту, подскажет ./termit home board (после рана)."),
}


def board_text(key: str, **kw) -> str:
    text = ((_ui().get("board") or {}).get(key)) or BOARD_TEXTS[key]
    return text.format(**kw) if kw else text


def board_news(p: dict) -> List[str]:
    """Карточки, открытые с прошлого раза: встают в свободное место сами; строка для игрока —
    один раз на карточку. Без доски — молчит (откроются, когда доска появится)."""
    if not has_board(p):
        return []
    s = _settings(p)
    seen = [c for c in (s.get("board_seen") or []) if isinstance(c, str)] \
        if isinstance(s.get("board_seen"), list) else []
    out = []
    for card in open_cards(p):
        if card in seen:
            continue
        seen.append(card)
        if card in DEFAULT_CARDS or card == GAME_CARD:
            continue
        if card in pinned(p):
            continue
        if board_on(p) and _free(p) > 0:
            _pin(p, card)
            out.append(board_text("card_pinned", card=card, name=CARD_NAMES[card]))
        else:
            out.append(board_text("card_new", card=card, name=CARD_NAMES[card]))
    s["board_seen"] = seen
    return out


def board_enable(p: dict, item_ids) -> Optional[str]:
    """Доска или новое место пришли (подарок, покупка): включить и сказать, что изменилось."""
    s = _settings(p)
    msg = None
    for iid in item_ids:
        if iid == BOARD:
            s.setdefault("board", True)
            if not isinstance(s.get("board_cards"), list):
                s["board_cards"] = list(DEFAULT_CARDS)
            # о том, что уже открыто, сказано подарком; новые карточки — board_news
            s["board_seen"] = list(DEFAULT_CARDS) + [GAME_CARD]
            # сохранение старше доски: страж «Основ» уже взят, а его подарок (третье место)
            # выдан до FB5 — место кладём вместе с доской
            if not basics_on(p) and "board3" not in p.setdefault("owned", []):
                p["owned"].append("board3")
            msg = board_text("gift")
        elif iid in BOARD_SLOTS and has_board(p):
            card = _autopin(p)
            msg = (board_text("slot_auto", card=card, name=CARD_NAMES[card]) if card
                   else board_text("slot", free=_free(p)))
    return msg


def open_note(card: str) -> str:
    need = CARD_OPEN.get(card)
    from termit_app.tasks import registry
    task = registry.all_tasks().get(need) if need else None
    title = theme.title(task) if task else need
    return f"откроется после задания «{title}»"


def board_cmd(rest: str) -> str:
    """Команда доски так, как её набирают здесь: в убежище — «board …», снаружи — полностью."""
    from termit_app import commands
    return f"board {rest}" if commands.hub_on() else f"./termit home board {rest}"


BOARD_WHERE = ("Доска — подсказки, которые висят над строкой ввода (там, где набираешь "
               "команды) в каждой задаче. Увидеть их — зайди в задачу (run или train): "
               "карточки будут прямо над строкой.")


def board_view(p: dict) -> List[str]:
    """`./termit home board`: что это, где видно, что приколото, что можно и как поменять —
    готовыми командами с настоящими именами карточек (владелец 21.10: «не понятно, как
    работать с доской, как прикалывать, откреплять, где смотреть»)."""
    from termit_app import tui, ui
    if not has_board(p):
        return ["Доски пока нет — её подарят за первое решённое задание. На неё прикалывают "
                "подсказки (скажем, клавиши терминала), и они висят строкой над приглашением "
                "в каждой задаче."]
    cards, slots = pinned(p), board_slots(p)
    width = tui.width() - 4
    state = "включена" if board_on(p) else f"выключена — над строкой ничего (вернуть: {board_cmd('on')})"
    out = [*ui.story_fill(BOARD_WHERE, "", "").splitlines(), "",
           f"Доска {state} · мест {slots}, занято {len(cards)}", ""]

    def card_rows(card: str, note: str = "") -> List[str]:
        rows = [f"  {card} — {CARD_NAMES[card]}{note}"]
        sample = card_text(p, card)
        if sample:
            rows.append("      " + tui.trunc(sample, width - 2))
        return rows

    out.append("Приколото сейчас:" if cards else "Приколото сейчас: ничего")
    for card in cards:
        out += card_rows(card)
    waiting = [c for c in CARDS if c not in cards and card_open(p, c)]
    if waiting:
        out += ["", "Можно приколоть:"]
        for card in waiting:
            note = (" (пока идут «Основы», висит сама — прикалывать не нужно)"
                    if card == GAME_CARD and basics_on(p) else "")
            out += card_rows(card, note)
    closed = [c for c in CARDS if not card_open(p, c)]
    if closed:
        out += ["", "Закрыто:"]
        out += [ui.story_fill(f"{c} — {CARD_NAMES[c]}: {open_note(c)}", "  ", "    ")
                for c in closed]
    out += ["", "Как поменять (набирай здесь, в убежище):"]
    target = next((c for c in waiting if c != GAME_CARD), None)
    if cards:
        out.append(f"  {board_cmd('unpin ' + cards[-1])} — снять «{CARD_NAMES[cards[-1]]}», "
                   "место освободится")
    if target:
        out.append(f"  {board_cmd('pin ' + target)} — приколоть «{CARD_NAMES[target]}»")
    out.append(f"  {board_cmd('off')} — спрятать всю доску · {board_cmd('on')} — вернуть")
    if len(cards) >= slots and target:
        from datetime import date
        on_sale = "board2" in {i.id for i in shop.visible(p, date.today())}
        more = (f" Или купи ещё место: shop board2 ({shop.get('board2').price} "
                f"{theme.word('money')})." if on_sale else "")
        out.append(ui.story_fill("Свободных мест нет: сначала сними одну карточку (unpin), "
                                 "потом приколи другую (pin)." + more, "  ", "  "))
    out.append("  Изменения видно со следующей задачи. Все клавиши терминала — keys.")
    return out


def board_pin(p: dict, card: str) -> tuple:
    """Приколоть карточку. Код: ok|unknown|closed|pinned|full|no_board."""
    if not has_board(p):
        return False, "no_board"
    if card not in CARDS:
        return False, "unknown"
    if not card_open(p, card):
        return False, "closed"
    if card in pinned(p):
        return False, "pinned"
    if _free(p) <= 0:
        return False, "full"
    _pin(p, card)
    _settings(p)["board"] = True
    return True, "ok"


def board_unpin(p: dict, card: str) -> tuple:
    """Снять карточку. Код: ok|unknown|not_pinned|auto|no_board (auto — game в «Основах»)."""
    if not has_board(p):
        return False, "no_board"
    if card not in CARDS:
        return False, "unknown"
    if card not in pinned(p):
        return False, "auto" if card == GAME_CARD and basics_on(p) else "not_pinned"
    _settings(p)["board_cards"] = [c for c in pinned(p) if c != card]
    return True, "ok"
