"""Пульт убежища: экран, строка подсказки, правило пустого Enter (спека 2.3). Без сети и
подпроцессов: только прогресс и реестр задач."""
from datetime import date, timedelta
from typing import List, Optional, Tuple

from termit_app import (hideout, inbox, progress, pyenvs, session, shop, theme, tui, ui,
                        weekly)
from termit_app.tasks import registry

LABELS = {"run": "ран дня", "inbox next": "читать деку", "train": "отработка",
          "new": "ещё урок", "master": "круг мастера", "hub": "пульт"}
LABEL_FRESH = "подтянуть свежее"


def today() -> date:
    """«Сегодня» пульта — функцией, чтобы тесты подменяли полночь."""
    return date.today()


def ran_today(p: dict, day: date) -> bool:
    return day.isoformat() in (p.get("days") or ())


def unread_count(p: dict) -> int:
    return len(inbox.unread(p))


def drill_ids(p: dict, day: date) -> List[str]:
    """Что реально даст train сейчас — та же выборка (спека 2.3: иначе новичок увидит
    пустой экран по Enter). Без подпроцессов: доступность — по кэшу интерпретатора."""
    from termit_app import train
    with pyenvs.cache_only():
        return train.weak_ids(p, day)


def failed_today(p: dict, day: date, ids: List[str]) -> bool:
    """Среди слабых есть сорвавшаяся сегодня: срок — завтра, уровень сброшен (так пишет
    progress.record при провале или подсказке)."""
    tomorrow = (day + timedelta(days=1)).isoformat()
    for tid in ids:
        rec = p.get("tasks", {}).get(tid) or {}
        if rec.get("due") == tomorrow and not rec.get("level"):
            return True
    return False


def next_lesson(p: dict) -> Optional[str]:
    """Новый урок для слова new; страж — экзамен, его Enter не предлагает (спека 2.3)."""
    new = session.next_new(p, 1)
    if new and not registry.get(new[0]).boss:
        return new[0]
    return None


def default_action(p: dict, day: date) -> Tuple[str, str]:
    """Что сделает пустой Enter: строка для хаба и метка ⏎. Никогда не страж, не покупка
    и не выход."""
    if not ran_today(p, day):
        line = "run"
    elif unread_count(p):
        line = "inbox next"
    else:
        drills = drill_ids(p, day)
        if drills and failed_today(p, day, drills):
            return "train", LABEL_FRESH
        if next_lesson(p):
            line = "new"
        elif drills:
            line = "train"
        elif progress.master_open(p):
            line = "master"
        else:
            line = "hub"
    return line, LABELS[line]


NEW_DAY = "Новый день: ран дня обновлён."
TOUR = ("Это убежище — твой пульт между ранами. Здесь набирают короткие слова игры, а не "
        "команды терминала. Enter делает то, что отмечено ⏎. Все слова — help, выйти — "
        "quit. В следующий раз запусти игру так же — и окажешься здесь.")
SILENT = ("hub", "help", "clear", "quit", "home")      # всегда в подсказке или служебные
NEW_IN_RELEASE = ("train", "inbox")     # слова этого выпуска: знакомство их не гасит
MAX_FRESH = 8                           # столько новых слов предлагает пульт за раз
MAX_HINT = 6
WORD_COLUMN = 9                         # слово справа: «[Enter]», «inbox», «board»
LABEL_COLUMN = 12


def row_width(cp=None) -> int:
    """FB17: строка пульта — по окну (до 100), с запасом в 4 клетки справа."""
    return tui.width(cp) - 4


def row(label: str, text: str, word: str, width: int = None) -> str:
    """«  Метка:     текст ……… слово»: колонки считаются от ширины окна."""
    return row_lines(label, text, word, width)[0]


def row_lines(label: str, text: str, word: str, width: int = None) -> List[str]:
    """Строка пульта; не влезший текст переносится под текст (FB19: в правой колонке рядом с
    картинкой места меньше — обрезать «…» нельзя, пропадёт смысл)."""
    width = width or row_width()
    room = width - WORD_COLUMN - 1 if word else width
    lead = f"  {tui.pad(label, LABEL_COLUMN - 1)} "
    lines = tui.fill(text, room, lead, " " * len(lead)) if text else [lead]
    lines = [tui.trunc(x, room) for x in lines]
    first = (tui.pad(lines[0], width - WORD_COLUMN) + word).rstrip()
    return [first] + [x.rstrip() for x in lines[1:]]


def header(p: dict, day: date) -> str:
    rank = theme.rank_name(registry.rank_level(p["bosses"]))
    streak = progress.current_streak(p, day)
    return (f"УБЕЖИЩЕ · {rank} · серия {streak} дн. · "
            f"{theme.word('money')} {ui.balance(p['money'])}")


def run_text(p: dict, day: date) -> str:
    old = len(session.today_reviews(p, day))
    new = len(session.next_new(p, progress.new_limit(p, day)))
    if not old + new:
        return "круг мастера по знакомому · ~5 мин"
    return f"дел: {old + new} (новых {new}, вспомнить {old}) · ~10 мин"


# --- Графики (FB19, владелец 21.10: «добавь графики») ----------------------------------------

BAR_CELLS = 8
WEEK = 7
DAY_MARKS = {"rich": ("●", "○", "◌", "❄"), "basic": ("#", ".", "?", "*"),
             "plain": ("#", ".", "?", "*")}       # сыграл, пропуск, сегодня ещё нет, заморозка


def place_state(p: dict) -> Optional[Tuple[str, int, int]]:
    """Текущее место (первое открытое со стражем впереди): ключ, решено и всего обычных задач
    до стража. None — стража впереди нет."""
    for tr in registry.unlocked(p["bosses"]):
        ts = registry.tasks_of(tr.key)
        if not any(t.boss and t.id not in p["bosses"] for t in ts):
            continue
        plain = [t for t in ts if not t.boss]
        solved = sum(1 for t in plain if (p.get("tasks", {}).get(t.id) or {}).get("solved"))
        return tr.key, solved, len(plain)
    return None


def to_boss(p: dict) -> Optional[int]:
    """Сколько обычных задач текущего места ещё не решено до стража; None — стража впереди
    нет."""
    state = place_state(p)
    return None if state is None else state[2] - state[1]


def place_text(p: dict, cp) -> Optional[str]:
    """«Основы ▰▰▰▰▰▰▱▱ 21 из 23 · до стража 2»: прогресс места и путь до стража — одна
    полоска (обычные задачи места и идут до стража); без полоски (plain) — «решено N из M»."""
    state = place_state(p)
    if state is None:
        return None
    key, solved, total = state
    # владелец 23.10: ни полоски, ни «из M», ни «до стража N» — страж приходит внезапно
    return f"{theme.place(key)} · решено задач: {solved}"


def week_marks(p: dict, day: date, cp) -> Tuple[str, int]:
    """Последние 7 дней значками (старые слева, сегодня — справа) и сколько из них сыграно."""
    on, off, today_mark, frozen_mark = DAY_MARKS.get(cp.level, DAY_MARKS["plain"])
    days = set(p.get("days") or ())
    frozen = p.get("frozen_days") or {}
    out, played = "", 0
    for k in range(WEEK - 1, -1, -1):
        iso = (day - timedelta(days=k)).isoformat()
        if iso in days:
            out += on
            played += 1
        elif isinstance(frozen, dict) and iso in frozen:
            out += frozen_mark
        else:
            out += today_mark if k == 0 else off
    return out, played


def week_text(p: dict, day: date, cp) -> Optional[str]:
    if not p.get("days"):
        return None
    marks, played = week_marks(p, day, cp)
    on, off, today_mark, frozen_mark = DAY_MARKS.get(cp.level, DAY_MARKS["plain"])
    keys = [f"{on} играл", f"{off} пропуск"]
    if today_mark in marks:
        keys.append(f"{today_mark} сегодня ещё нет")
    if frozen_mark in marks:
        keys.append(f"{frozen_mark} заморозка")
    return f"{marks} играл {played} из {WEEK} · " + ", ".join(keys)


# --- Комната на пульте (FB19: «изображение комнаты подвала, деки, того, что есть в доме») ----
# Рисует hideout.render (тот же рисунок, что ./termit home); сверх вещей комнаты — дека и
# купленное «не для комнаты» (звуки, досье, детали приглашения): у каждой группы свой значок.
# Под рисунком — подписи «значок — что это». Новое после покупки помечено один раз:
# память — p["hub"]["items"] (id вещей, уже показанных на пульте).

EXTRA_ART = {               # группа hideout.EXTRA_GROUPS: (ряд комнаты, значок, подпись)
    "sound": ("desk", "♪", "звуки"),
    "tape": ("desk", "▭", "записи для проигрывателя"),
    "dossier": ("mid", "[§]", "досье"),
    "fragment": ("mid", "◇", "фрагменты"),
    "prompt": ("wall", ">_", "детали приглашения"),
    "palette": ("wall", "▒", "палитры"),
    "glyph_pack": ("wall", "»", "знак у курсора"),
    "callsign": ("wall", "@", "позывной"),
    "style": ("wall", "✧", "стиль"),
}
SIDE_MIN = 90               # окно не уже — картинка слева, строки пульта справа
ART_SHARE = 0.32            # доля ширины под картинку
GAP = 1


def deck_glyph(p: dict, frame: str) -> str:
    deck = p.get("deck") or {}
    slots = deck.get("slots", 1)
    used = min(len(deck.get("installed") or ()), slots)
    on, off = ("▣", "□") if frame == "box" else ("#", ".")
    return "[" + on * used + off * (slots - used) + "]"


def deck_name(p: dict) -> str:
    deck = p.get("deck") or {}
    slots = deck.get("slots", 1)
    used = min(len(deck.get("installed") or ()), slots)
    return f"{shop.section_title('deck').lower()}: слотов {slots}, занято {used}"


def room_parts(p: dict, frame: str = "box") -> List[dict]:
    """Что нарисовано на пульте: вещи комнаты, дека, группы купленного. У каждой части —
    ряд, значок, подпись и id вещей (по ним — пометка «новое»)."""
    parts = []
    for iid in hideout.owned_items(p):
        name = hideout.ITEMS[iid]["name"] or hideout.name(iid)     # короткое имя, без эмодзи
        if iid == hideout.BOARD:
            slots = hideout.board_slots(p)
            name += f" ({slots} {ui.plural(slots, 'место', 'места', 'мест')})"
        parts.append({"row": hideout.ITEMS[iid]["row"], "glyph": hideout.glyph(p, iid, True),
                      "name": name, "ids": [iid], "item": iid})
    groups = {key: ids for key, _title, ids in hideout.extra_groups(p)}
    parts.append({"row": "desk", "glyph": deck_glyph(p, frame), "name": deck_name(p),
                  "ids": groups.get("deck", []), "item": None})
    for key, (where, sign, name) in EXTRA_ART.items():
        ids = groups.get(key)
        if ids:
            count = f" ({len(ids)})" if len(ids) > 1 else ""
            parts.append({"row": where, "glyph": sign, "name": name + count, "ids": ids,
                          "item": None})
    return parts


def seen_items(p: dict) -> Optional[set]:
    """Вещи, уже показанные на пульте; None — памяти ещё нет (старое сохранение: тогда
    «новым» ничего не считается, а память заводит хаб)."""
    seen = (p.get("hub") or {}).get("items")
    if not isinstance(seen, list):
        return None
    return {x for x in seen if isinstance(x, str)}


def room_ids(p: dict) -> List[str]:
    """Все id нарисованного — то, что хаб запоминает после показа пульта."""
    return [i for part in room_parts(p) for i in part["ids"]]


def _is_new(part: dict, seen: Optional[set]) -> bool:
    return seen is not None and any(i not in seen for i in part["ids"])


def room_drawing(p: dict, cp, width: int) -> Tuple[List[str], List[str]]:
    """Рисунок комнаты шириной width (вместе с рамкой и отступом) и подписи «значок — что»;
    новое — первым и с пометкой."""
    frame = "box" if cp.level == "rich" else "ascii"
    parts = room_parts(p, frame)
    seen = seen_items(p)
    mark = hideout.NEW_MARK[frame]
    marks = {pt["item"] for pt in parts if pt["item"] and _is_new(pt, seen)}
    extra = {}
    for pt in parts:
        if pt["item"] is None:
            sign = pt["glyph"] + (mark if _is_new(pt, seen) else "")
            extra.setdefault(pt["row"], []).append(sign)
    art = hideout.render(p, frame, width - 4, extra=extra, marks=marks, still=True)[1:]
    new = [pt for pt in parts if _is_new(pt, seen)]
    legend = [f"{pt['glyph']} — {pt['name']} (новое)" for pt in new]
    if new:
        legend.append(f"{mark} — новое")
    legend += [f"{pt['glyph']} — {pt['name']}" for pt in parts if pt not in new]
    return art, legend


def legend_lines(items: List[str], width: int) -> List[str]:
    """Подписи столбиком шириной width: короткие — по нескольку в строку, длинные — переносом."""
    lines, short = [], []
    for item in items:
        if tui.vlen(item) > width - 2:
            lines += _wrap(short, width, "  ")
            short = []
            lines += tui.fill(item, width, "  ", "    ")
        else:
            short.append(item)
    lines += _wrap(short, width, "  ")
    return [tui.trunc(x, width) for x in lines]


def room_art(p: dict, cp, width: int) -> List[str]:
    """Рисунок и все подписи под ним (правило «везде расшифровки»: подписи не урезаются)."""
    art, legend = room_drawing(p, cp, width)
    return art + legend_lines(legend, width)


def room_text(p: dict, cp, limit: Optional[int] = None) -> str:
    """Комната одной строкой (узкое окно, plain): «значок что» через точку, новое — первым; в
    plain — без значков, одни имена. limit — показать столько, остальное «… ещё N — в home»."""
    frame = "box" if cp.level == "rich" else "ascii"
    seen = seen_items(p)
    parts = room_parts(p, frame)
    parts = [pt for pt in parts if _is_new(pt, seen)] + [pt for pt in parts
                                                          if not _is_new(pt, seen)]
    out = []
    for pt in parts:
        new = " (новое)" if _is_new(pt, seen) else ""
        out.append(pt["name"] + new if cp.level == "plain" else f"{pt['glyph']} {pt['name']}{new}")
    if limit is not None and limit < len(out):
        out = out[:limit] + [f"… ещё {len(out) - limit} — в home"]
    return " · ".join(out)


def board(p: dict, day: date, cp=None, art: bool = True,
          room_lines: Optional[int] = None) -> List[str]:
    """room_lines — строка «Комната» без картинки не выше стольких строк (пульт по высоте)."""
    with pyenvs.cache_only():
        return _board(p, day, cp, art, room_lines)


def status_rows(p: dict, day: date, cp, art: bool) -> List[Tuple[str, str, str]]:
    """Строки «что сейчас» (метка, текст, слово справа) — пустые не показываются; у одной
    строки — [Enter] (спека 2.3, UX §2). art — комната нарисована рядом, строка «Комната»
    короткая."""
    enter = default_action(p, day)[0].split()[0]

    def mark(word: str) -> str:
        return "[Enter]" if word == enter else word

    rows = []
    if ran_today(p, day):
        rows.append(("Ран дня:", "сыгран ✓ · завтра будет новый", ""))
    else:
        rows.append(("Ран дня:", run_text(p, day), mark("run")))
    place = place_text(p, cp)
    if place:
        rows.append(("Место:", place, ""))
    week = week_text(p, day, cp)
    if week:
        rows.append(("7 дней:", week, ""))
    unread = unread_count(p)
    if unread:
        word = ui.plural(unread, "новое сообщение", "новых сообщения", "новых сообщений")
        rows.append(("Дека:", f"{unread} {word}", mark("inbox")))
    drills = drill_ids(p, day)
    if drills:
        rows.append(("Отработка:", f"подтянуть: {len(drills)}", mark("train")))
    if ran_today(p, day) and next_lesson(p):
        rows.append(("Ещё урок:", "новая команда сверх нормы", mark("new")))
    if weekly.visible(p, day):
        rows.append(("Неделя:", weekly.short_line(p, day).strip(), ""))
    if hideout.has_board(p):
        cards = ", ".join(hideout.pinned(p)) or "пусто"
        rows.append(("Доска:", f"мест {hideout.board_slots(p)}: {cards}", "board"))
    things = f"вещей: {len(hideout.owned_items(p))}"
    rows.append(("Комната:", things + " · осмотреть" if art else room_text(p, cp), "home"))
    if p.get("money", 0) > 0:           # владелец 21.10: «не было shop»
        rows.append(("Витрина:", f"{theme.word('money')} {ui.balance(p['money'])} — "
                                 "что купить", "shop"))
    if enter == "master":
        rows.append(("Круг:", "знакомые дела на время, против рекорда", "[Enter]"))
    return rows


def _board(p: dict, day: date, cp, art: bool, room_lines: Optional[int] = None) -> List[str]:
    """Пульт: шапка, под ней строки «что сейчас»; в широком окне (не plain) слева — рисунок
    комнаты с подписями, справа строки (FB19). Без подпроцессов: доступность задач — по кэшу
    интерпретатора, значки вещей — без проверки процессов."""
    cp = cp or tui.caps()
    wide = row_width(cp)
    side = art and cp.level != "plain" and tui.width(cp) >= SIDE_MIN
    rows = status_rows(p, day, cp, side)
    head = header(p, day)
    if cp.level == "plain":
        top = [tui.trunc(head, tui.width(cp))]
    else:
        top = [tui.trunc("  " + tui.label(head, cp), tui.width(cp)), tui.rule(cp, indent="  ")]
    if not side:
        out = []
        for label, text, word in rows:
            lines = row_lines(label, text, word, wide)
            if label == "Комната:" and room_lines:
                limit = len(room_parts(p))
                while len(lines) > room_lines and limit > 1:
                    limit -= 1
                    lines = row_lines(label, room_text(p, cp, limit), word, wide)
            out += lines
        return top + out
    left_w = int(wide * ART_SHARE)
    right_w = wide - left_w - GAP
    right = [x for r in rows for x in row_lines(*r, right_w)]
    art, legend = room_drawing(p, cp, left_w)
    # подписи — под рисунком, пока левая колонка не длиннее правой; остальные — строкой
    # «Значки:» под строками пульта (так пульт ниже, а подпись есть у каждого значка)
    k = len(legend)
    while k and len(art) + len(legend_lines(legend[:k], left_w)) > len(right):
        k -= 1
    left = art + legend_lines(legend[:k], left_w)
    if legend[k:]:
        right += row_lines("Значки:", " · ".join(legend[k:]), "", right_w)
    body = []
    for k in range(max(len(left), len(right))):
        a = left[k] if k < len(left) else ""
        b = right[k] if k < len(right) else ""
        body.append((tui.pad(a, left_w + GAP) + b).rstrip())
    return top + body


def fresh_words(p: dict, names: List[str]) -> List[str]:
    """Слова из names, которые подсказка ещё не показывала; не больше MAX_FRESH за раз."""
    shown = set(p.get("hub", {}).get("shown") or ())
    return [n for n in names if n not in shown and n not in SILENT][:MAX_FRESH]


def tour_shown(p: dict, names: List[str]) -> List[str]:
    """Что считать показанным после первого знакомства: все слова, кроме новых в этом выпуске —
    их игроки со старым сохранением должны увидеть с пометкой «новое»."""
    shown = list(p.get("hub", {}).get("shown") or ())
    return shown + [n for n in names if n not in shown and n not in NEW_IN_RELEASE]


HINT_LINES = 4
TAIL = ["help — подробно", "quit — выйти"]


def _wrap(items: List[str], width: int = None, indent: str = "") -> List[str]:
    width = width or tui.width()
    lines, cur = [], ""
    for item in items:
        joined = f"{cur} · {item}" if cur else indent + item
        if cur and tui.vlen(joined) > width:
            lines.append(cur)
            cur = indent + item
        else:
            cur = joined
    return lines + [cur] if cur else lines


def hint_line(p: dict, day: date, fresh: List[str] = (), words: List[str] = (),
              shorts: Optional[dict] = None) -> str:
    """Подсказка над приглашением: первым — что сделает ⏎, потом новое, потом все открытые
    слова (words — в порядке групп help), последними — help и quit. До четырёх строк по ширине
    окна (до 100); не влезло — слова убираются с конца, help и quit остаются (владелец 21.10:
    «6 команд мало… всё должно быть на виду, особенно первые разы»)."""
    with pyenvs.cache_only():
        line, label = default_action(p, day)
    unread = unread_count(p)
    if line == "inbox next" and unread:
        label = f"{label} ({unread})"           # число — тут же, без второго «inbox»
    items = [f"⏎ {label}"]
    if unread and line != "inbox next":
        items.append(f"inbox ({unread})")
    shorts = shorts or {}

    def said(w: str) -> str:            # владелец 21.10: везде хотя бы короткая расшифровка
        return f"{w} — {shorts[w]}" if w in shorts else w

    items += [f"{said(w)} (новое)" for w in fresh[:4]]
    taken = set(fresh) | {line.split()[0]} | ({"inbox"} if unread else set())
    rest = [said(w) for w in words if w not in taken and w not in SILENT[:4]]
    while True:
        lines = _wrap(items + rest + TAIL)
        if len(lines) <= HINT_LINES:
            return "\n".join(lines)
        if rest:
            rest.pop()
        elif len(items) > 1:
            items.pop()
        else:
            return "\n".join(tui.trunc(x, tui.width()) for x in lines[:HINT_LINES])
