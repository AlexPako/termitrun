"""Командная строка ./termit (TermitRun): ран, места, статистика, шпаргалка, темы, замечания."""
import json
import os
from datetime import date

import re

from termit_app import (citymap, contracts, cosmetics, diary, hideout, implants, loot, music,
                        paths, progress, repute, sandbox, session, story, updates, warehouse, weekly)
from termit_app import book as book_mod
from termit_app import inbox as inbox_mod
from termit_app import goal
from termit_app import commands, edition, extensions, icons, theme, tui, ui
from termit_app import owl as owl_mod
from termit_app import shop as shop_mod
from termit_app import sound as sound_mod
from termit_app.tasks import registry

FLAGS = {"--no-sandbox", "--bare", "--no-gui"}


LATER = "  … ещё команды откроются по ходу: страж, первые находки, покупки\n"


def _opened(p) -> dict:
    """Какие команды поздних фаз уже к месту. p=None — полная справка (всё открыто)."""
    if p is None:
        return dict.fromkeys(("deck", "fence", "rehearse", "owl", "case", "dossier",
                              "memory", "implants", "diary", "style", "callsign", "music",
                              "master", "wheels"), True)
    bosses = set(p.get("bosses", ()))
    owned = set(p.get("owned", ()))
    tasks = registry.all_tasks()
    return {
        # модули в витрине — после первого стража; дека нужна, когда есть что ставить
        "deck": bool(bosses) or any(m in owned for m in shop_mod.MODULES),
        "fence": "boss_basics" in bosses or bool(p.get("paydata")),
        # репетиция — когда непобеждённый страж уже встречался
        "rehearse": any(t.boss and tid in p.get("tasks", {}) and tid not in bosses
                        for tid, t in tasks.items()),
        "owl": p.get("dozors", 0) >= 1 or "owl" in (p.get("settings") or {}),
        "case": bool(bosses),                         # первая улика — после первого стража
        "dossier": any(shop_mod.get(i) is not None and shop_mod.get(i).kind == "dossier"
                       for i in owned),
        "memory": bool(p.get("shards")) or "shard_hint" in p.get("flags", ()),
        # утилиты-подарки — после урока установки
        "implants": ((p.get("tasks", {}).get("brew_lesson") or {}).get("solved") or 0) > 0,
        "diary": bool(p.get("tasks")),                # первая встреченная задача — первая страница
        "style": cosmetics.any_style(p),              # первая вещь стиля куплена
        "callsign": "callsign" in owned,
        "music": "player" in owned,                   # дека куплена — ей есть что сказать
        # круг мастера — когда есть что повторять на время
        "master": progress.master_open(p),
        # склад pandas/requests — когда открыт трек «Python» (часть 10, A3)
        "wheels": warehouse.OPENS_AFTER in bosses,
    }


def usage(p: dict = None) -> str:
    """Справка. С прогрессом p — по фазам: команды поздних фаз появляются, когда к месту.
    Описания команд — из commands.ABOUT: те же слова, что в строке первой встречи."""
    w = theme.word
    on = _opened(p)
    has_story = story.has_story()
    cmd = commands.line
    home = commands.home_line

    def line(key, text, enabled=True):
        return text if enabled and on[key] else ""
    story_lines = (line("case", cmd("case"), has_story) +
                   line("memory", cmd("memory"), has_story) +
                   line("dossier", cmd("dossier", "[ИМЯ]"), has_story))
    fence_line = line("fence", cmd("fence", "[sell N]"), loot.enabled())
    master_line = line("master", cmd("master"))
    rehearse_line = line("rehearse", cmd("rehearse", "ID"))
    deck_line = line("deck", cmd("deck", "[on|off ID]"))
    implants_line = line("implants", cmd("implants", "", "\n" + " " * 27 + "shell — подключить fzf и zoxide к своему zsh"))
    wheels_line = line("wheels", cmd("wheels", "[get]"))
    style_line = line("style", cmd("style", "[ВИД ID]"))
    callsign_line = line("callsign", home("callsign"))
    music_line = line("music", cmd("music", "[play ID]"))
    diary_line = line("diary", cmd("diary", "[N]"))
    owl_line = line("owl", cmd("owl", "[on|off]"))
    exists = {"fence": loot.enabled(), "case": has_story, "memory": has_story,
              "dossier": has_story}          # в теме без сюжета эти команды не появятся
    report_line = cmd("report") if edition.ISSUES_URL else ""
    report_line += cmd("update") if edition.ISSUES_URL else ""
    places = "basics" if edition.closed() else "basics, tools, finder"
    themes = f": {', '.join(theme.available())} (сейчас: {theme.current()})"
    later = LATER if any(not v and exists.get(k, True) for k, v in on.items()) else ""
    return f"""TermitRun — тренажёр терминала ({theme.tagline()})

  ./termit                 {w('session')} на ~10 минут — каждый день
{cmd("run")}{cmd("short")}{cmd("more")}{master_line}{cmd("track", "МЕСТО", f" ({places})")}\
{cmd("play", "ID")}{cmd("stats")}{cmd("intro")}{cmd("keys")}\
                           в задаче: next — дальше после решения; после итога рана — more, ещё урок
{cmd("ext")}{cmd("shop", "[all]")}\
  ./termit shop ID         купить (например, ./termit shop freeze)
{style_line}{rehearse_line}{cmd("list")}{cmd("map")}{cmd("home", "[look ID]")}\
{home("prompt")}{home("board")}{home("shop")}{home("help")}\
{callsign_line}{deck_line}{story_lines}{fence_line}{cmd("inbox", "[N|next]")}{cmd("book", "[слово]")}\
{diary_line}{cmd("theme", "[ИМЯ]", themes)}{cmd("sound", "[on|off]", ";")}\
                           test, pack ID|off, vol 1..10
{music_line}{implants_line}{wheels_line}{owl_line}{cmd("feedback")}\
{report_line}{cmd("help")}{later}
Флаги: --theme ИМЯ (тема на один запуск), --no-sandbox (без защиты sandbox-exec),
       --bare (без твоего ~/.zshrc), --no-gui (open не открывает окна)"""


def parse(argv):
    """Флаги, аргументы и значение --theme (None — флага не было)."""
    flags, args, theme_name = set(), [], None
    it = iter(argv)
    for a in it:
        if a == "--theme":
            theme_name = next(it, "")
        elif a.startswith("--theme="):
            theme_name = a.split("=", 1)[1]
        elif a.startswith("--"):
            flags.add(a)
        else:
            args.append(a)
    return flags, args, theme_name


def show_stats() -> None:
    p = progress.load(paths.PROGRESS_FILE)
    today = date.today()
    cp = tui.caps()
    rank = theme.rank_name(registry.rank_level(p["bosses"]))
    rows = [f"Звание: {rank}"]
    worn = cosmetics.title_for(p, today)
    if worn:
        rows[0] += f" · титул: {worn}"
    karma = progress.karma(p)
    slots = p["deck"].get("slots", 1)
    gate = progress.SLOT_KARMA.get(slots + 1)
    line = f"{theme.word('xp_title')}: {karma}"
    gate_text = theme.story("deck").get("gate")   # у темы без деки (фэнтези) строки нет
    if gate is not None and slots < 2 and gate_text:    # пока слот 2 не открыт — сколько до него
        line += " · " + gate_text.format(slot=slots + 1, need=max(0, gate - karma))
    rows.append(line)
    streak = progress.current_streak(p, today)
    rows.append(f"{theme.word('session')}ов: {p['dozors']}" + (f" · серия: {streak} дн." if streak else ""))
    rows.append(f"{theme.word('money')} {ui.balance(p['money'])} ({theme.word('money_name')}) · "
                f"заморозки: {p['freezes']} из {progress.freeze_cap(p)} · спасли серию: "
                f"{progress.freezes_spent(p)}")
    tasks = registry.all_tasks()
    beaten = [theme.title(tasks[b]) for b in p["bosses"] if b in tasks]
    rows.append(f"{theme.word('beaten')}: " + (", ".join(beaten) if beaten else "пока никто"))
    rows.append(repute.line(p, with_next=True))      # репутация (C2 М6) — отдельной строкой
    aim = goal.line(p)                               # FB12 (A2): ближняя цель
    if aim:
        rows.append(aim)
    guards = [t for t in tasks.values() if t.boss]
    places = []
    for tr in registry.shown_tracks():
        ts = registry.tasks_of(tr.key)
        seen = sum(1 for t in ts if progress.seen(p, t.id))
        name = theme.place(tr.key) + ("" if edition.track_open(tr.key) else " (скоро)")
        places.append((name, seen, len(ts)))
    weak = [theme.title(tasks[i]) for i, r in p["tasks"].items()
            if i in tasks and progress.weak(r)]
    if cp.level == "plain":                       # как до графики: строки без рамки
        for row in rows:
            ui.say(row)
        for place, seen, total in places:
            ui.say(f"  {place}: {seen}/{total}")
        if weak:
            ui.say("Подтянуть: " + ", ".join(weak[:8]))
        return
    week = progress.activity(p, today, 14)
    active = sum(1 for v in week if v)
    body = rows[1:]
    body[3] = (f"{theme.word('beaten')}: {tui.bar(len(beaten), len(guards), c=cp)} "
               f"{len(beaten)} из {len(guards)} · " + (", ".join(beaten) or "пока никто"))
    body += [tui.SEP, f"Активность 14 дн.: {tui.spark(week, cp)}  активных дней {active} из 14"]
    room = max(tui.vlen(pl) for pl, _, _ in places) + 2
    for place, seen, total in places:
        body.append(tui.Raw(f"{place}:{' ' * (room - tui.vlen(place) - 1)}"
                            f"{tui.bar(seen, total, 10, cp)} {seen}/{total}"))
    if weak:
        body += [tui.SEP, tui.style("Подтянуть: " + ", ".join(weak[:8]), "dim", c=cp)]
    for row in tui.box(body, title=rows[0].upper().replace("ЗВАНИЕ: ", "ЗВАНИЕ · "),
                       right=f"серия {streak} дн." if streak else "", c=cp):
        ui.say(row)


def show_list() -> None:
    p = progress.load(paths.PROGRESS_FILE)
    opened = {t.key for t in registry.unlocked(p["bosses"])}
    cp = tui.caps()
    for tr in registry.shown_tracks():
        if not edition.track_open(tr.key):      # первый модуль: место видно, задачи — потом
            ui.say(f"\n{theme.place(tr.key)} — {tr.title}  🔒 {edition.SOON}")
            continue
        lock = "" if tr.key in opened else "  🔒"
        ui.say(f"\n{theme.place(tr.key)} — {tr.title} ({tr.key}){lock}")
        met = set()                 # значок инструмента — при первой встрече в треке (не стена)
        for t in registry.tasks_of(tr.key):
            rec = p["tasks"].get(t.id)
            mark = ui.task_mark(rec)
            boss = "⚔ " if t.boss else ""
            if icons.shown(cp):     # rich: колонка значка в 3 клетки, названия — ровно
                tool = icons.tool_of(t)
                icon = "" if t.boss or tool in met else icons.tool(tool, cp)
                met.add(tool)
                boss = tui.pad(icons.mark(icon) or boss, 3)
            avail = "" if session.available(t) else \
                "  (" + (t.missing() or "нужен " + ", ".join(t.needs)) + ")"
            need = registry.missing_after(p, t)
            if need:        # пара «до/после»: откроется после близнеца и стража
                avail += "  🔒 после: " + ", ".join(theme.title(registry.get(x)) for x in need)
            ui.say(f"  {mark} {boss}{theme.title(t)}  [{t.id}]{avail}")


def show_book(query: str) -> None:
    p = progress.load(paths.PROGRESS_FILE)
    ui.say(book_mod.show(book_mod.sections(p), query))


def choose_theme(name) -> int:
    if not name:
        for n in theme.available():
            th = theme.load(n)
            mark = "▸" if n == theme.current() else " "
            ui.say(f" {mark} {n:10} {th['name']} — {th['tagline']}")
        ui.say("\nПереключить: ./termit theme ИМЯ  (прогресс общий для всех тем)")
        return 0
    if name not in theme.available():
        ui.bad(f"Нет темы {name}. Есть: " + ", ".join(theme.available()))
        return 2
    p = progress.load(paths.PROGRESS_FILE)
    p.setdefault("settings", {})["theme"] = name
    progress.save(paths.PROGRESS_FILE, p)
    theme.use(name)
    ui.ok(f"Тема: {theme.tagline()}. Прогресс общий для всех тем.")
    return 0


def _shop_ui(key: str, default: str) -> str:
    return (theme.story("shop") or {}).get(key) or default


def _buy_text(code: str, **kw) -> str:
    defaults = {"ok": "Куплено: {name}. Осталось {money} {cash}.",
                "money": "Не хватает: {name} стоит {price} {cash}, а у тебя {money}.",
                "karma": "Нужно {need} кармы, у тебя {karma}.",
                "slot": "Сначала открой предыдущий слот.",
                "owned": "Уже есть: {name}.", "cap": "Держать можно не больше {cap}, есть {have}.",
                "hidden": "Пока не продаётся — загляни позже.",
                "unknown": "Такого на витрине нет: {id}.",
                "home": ""}
    text = ((theme.story("shop") or {}).get("buy") or {}).get(code) or defaults[code]
    return text.format(**kw)


def _item_rows(p, items, new_ids) -> list:
    """Строки витрины: None — пустая строка, иначе (текст, отступ первой, отступ остальных)."""
    cash = theme.word("money")
    section, rows = None, []
    col = max([11] + [len(it.id) for it in items])     # колонка id — по самому длинному
    pad = " " * (col + 3)
    for it in items:
        if it.section != section:
            section = it.section
            rows += [None, ("§" + shop_mod.section_title(section), "  ", "  ")]
        mark = f"  · {_shop_ui('new', 'новое')}" if it.id in new_ids else ""
        price = f"{it.price} {cash}"
        rows.append((f"{shop_mod.name(it.id)} — {price}{mark}", f"  {it.id:{col}} ", pad))
        extra = shop_mod.desc(it.id)
        if it.kind == "freeze":
            extra = (extra + " · " if extra else "") + f"есть: {p['freezes']}"
        if extra:
            rows.append((extra, pad, pad))
        free = shop_mod.free_path(it.id)
        if free:
            rows.append((free, pad, pad))
    return rows


def _show_items(p, items, today, new_ids) -> None:
    """Витрина как до графики (plain): строки по ширине сюжетных строк."""
    for row in _item_rows(p, items, new_ids):
        if row is None:
            continue
        text, first, rest = row
        if text.startswith("§"):
            ui.say(f"\n{first}{text[1:]}")
        else:
            ui.say(_wrap(text, first, rest))


def _wrap(text: str, first: str, rest: str) -> str:
    """Строка витрины по ширине сюжетных строк (длинный id — без переноса внутри)."""
    import textwrap
    return textwrap.fill(text, ui.STORY_WIDTH, initial_indent=first, subsequent_indent=rest,
                         break_long_words=False, break_on_hyphens=False)


def _boxed_items(p, items, new_ids, cp) -> list:
    """Витрина в рамке: id — неоном, разделы — жирным, внутри рамки отступы те же, но короче."""
    body = []
    for row in _item_rows(p, items, new_ids):
        if row is None:
            if body:
                body.append("")
            continue
        text, first, rest = row
        if text.startswith("§"):
            body.append((tui.style(text[1:], "bold", c=cp), "", ""))
            continue
        first, rest = first[2:], rest[2:]           # рамка сама даёт отступ
        if first.strip():
            first = tui.style(first, "neon", c=cp)
        body.append((text, first, rest))
    return body


def shop_view(show_all: bool = False) -> int:
    p = progress.load(paths.PROGRESS_FILE)
    today = date.today()
    cp = tui.caps()
    balance = f"Баланс: {ui.balance(p['money'])} {theme.word('money')} " \
              f"({theme.word('money_name')})"
    if show_all:            # по разделам, как на витрине; внутри — порядок каталога
        items, rest = sorted(shop_mod.visible(p, today),
                             key=lambda i: shop_mod.SECTIONS.index(i.section)), 0
    else:
        items, rest = shop_mod.showcase(p, today)
    seen = set(p["shop_seen"])
    new_ids = {i.id for i in items if i.id not in seen} if seen else set()
    if cp.level == "plain":
        ui.say(balance)
        _show_items(p, items, today, new_ids)
    else:
        title = _shop_ui("title", "Витрина").upper()
        for row in tui.box([balance, ""] + _boxed_items(p, items, new_ids, cp), title=title,
                           right=f"{ui.balance(p['money'])} {theme.word('money')}",
                           kind="round", c=cp):
            ui.say(row)
    if rest:
        ui.say("\n" + _shop_ui("more", "и ещё {n} — ./termit shop all").format(n=rest))
    _soon_lines(p, today)
    _rehearsal_lines(p)
    ui.say("\nКупить: ./termit shop ID")
    fresh = [i.id for i in items if i.id not in seen]
    if fresh and paths.PROGRESS_FILE.exists():     # просмотр не создаёт прогресс с нуля
        p["shop_seen"] = sorted(seen | set(fresh))
        progress.save(paths.PROGRESS_FILE, p)
    return 0


def _soon_lines(p, today) -> None:
    """Витрина «скоро» (М4): косметика первой ступени завоза — названием и ценой, без покупки."""
    items = cosmetics.soon(p, today)
    if not items:
        return
    cash = theme.word("money")
    ui.say("\n" + ui.story_fill(cosmetics.soon_text("title"), "  ", "  "))
    for iid in items:
        ui.say(ui.story_fill(cosmetics.soon_text("row", name=shop_mod.name(iid),
                                                 price=shop_mod.get(iid).price, cash=cash),
                             "    ", "      "))


def _rehearsal_lines(p) -> None:
    """Строка репетиции под витриной — у каждого проваленного стража."""
    bosses = contracts.failed_bosses(p)
    if bosses:
        ui.say()
    for boss in bosses:
        price = contracts.rehearsal_price(p, boss)
        cost = (contracts.text("rehearse_shop_free") if price == 0
                else f"{price} {theme.word('money')}")
        ui.say(ui.story_fill(contracts.text("rehearse_shop", title=theme.title(registry.get(boss)),
                                            price=cost, id=boss), "  ", "    "))


def shop_buy(item_id: str) -> int:
    p = progress.load(paths.PROGRESS_FILE)
    today = date.today()
    item = shop_mod.get(item_id)
    cash = theme.word("money")
    idle = {m for m in shop_mod.MODULES
            if shop_mod.owned(p, m) and not progress.module_on(p, m)}
    stock_before = len(p["stock"]) if isinstance(p.get("stock"), list) else 0
    ok, code = shop_mod.buy(p, item_id, today)
    kw = {"id": item_id, "name": shop_mod.name(item_id), "cash": cash,
          "money": ui.balance(p["money"]), "price": item.price if item else 0,
          "need": shop_mod.karma_gate(item) if item else 0, "karma": progress.karma(p),
          "have": p["freezes"], "cap": progress.freeze_cap(p)}
    if not ok:
        (ui.bad if code == "unknown" else ui.say)(_buy_text(code, **kw))
        return 2 if code == "unknown" else 0
    progress.save(paths.PROGRESS_FILE, p)
    ui.ok(_buy_text("ok", **kw))
    if item.kind == "freeze":
        ui.say(f"   Заморозок: {p['freezes']}.")
    for line in story.bought_lines(item_id):
        ui.say(ui.story_fill(line, "   ", "   "))
    if item.cosmetic:           # долив витрины; первая вещь стиля надевается сама
        kind = next((k for k in cosmetics.STYLE_KINDS if item_id in cosmetics.style_items(k)),
                    None)
        if kind and cosmetics.chosen(p, kind) == item_id:
            ui.say("   " + cosmetics.style_text("bought"))
        if item_id in hideout.PALETTE_COLORS or item_id in hideout.WAVE2_PARTS:
            line = hideout.auto_enable(p, [item_id])
            progress.save(paths.PROGRESS_FILE, p)
            if line:
                ui.say(ui.story_fill(line, "   ", "   "))
            ui.say(ui.story_fill(cosmetics.SETUP_HINTS.get(item_id, cosmetics.SETUP_HINTS[
                "palette"]), "   ", "   "))
        elif item_id in hideout.ITEMS:
            home_line = _buy_text("home", **kw)
            if home_line:
                ui.say("   " + home_line)
            _say_use(item_id)
        stocked = p["stock"][stock_before:] if isinstance(p.get("stock"), list) else []
        if stocked:
            ui.say(ui.story_fill(cosmetics.stock_line(stocked), "   ", "   "))
    elif item.kind in ("prompt", "palette"):
        line = hideout.auto_enable(p, [item_id])
        progress.save(paths.PROGRESS_FILE, p)
        ui.say(ui.story_fill(line or "Приглашение: ./termit home prompt · как устроено: "
                                     "./termit home prompt show", "   ", "   "))
    elif item.kind == "module":
        ui.say("   " + (_deck_text("in_slot") if progress.module_on(p, item_id)
                        else _deck_text("no_slot")))
    elif item.kind == "slot":
        auto = [m for m in sorted(idle) if progress.module_on(p, m)]
        ui.say("   " + (_deck_text("slot_auto", name=shop_mod.name(auto[0])) if auto
                        else _deck_text("slot_open")))
    elif item.kind == "board":      # FB5: место на доске — сразу под открытую карточку
        line = hideout.auto_enable(p, [item_id])
        progress.save(paths.PROGRESS_FILE, p)
        if line:
            ui.say(ui.story_fill(line, "   ", "   "))
    elif item.kind in ("decor", "shnyr"):
        home = _buy_text("home", **kw)
        if home:
            ui.say("   " + home)
        _say_use(item_id)
    if _where_needed(item, story.bought_lines(item_id)):
        ui.say(ui.story_fill("⚙ " + hideout.where_text(item_id), "   ", "     "))
    return 0


# FB5 п. 17: виды, о которых покупка сама не говорила, где вещь и как ей пользоваться
# (вещи комнаты, приглашение, доска и дека говорят своими строками выше)
WHERE_AFTER_BUY = ("freeze", "tip", "dossier", "fragment", "sound", "soundpack", "tape") + \
    tuple(hideout.STYLE_ARG)


def _where_needed(item, bought: list) -> bool:
    if item.kind not in WHERE_AFTER_BUY or not hideout.where_text(item.id):
        return False
    if item.kind == "dossier" and item.id.endswith("1") and bought:
        return False            # «Читать: ./termit dossier ИМЯ» уже сказано
    return True


def _say_use(item_id: str) -> None:
    """FB8: купленная вещь сразу говорит, как ей пользоваться."""
    for line in hideout.use_news([item_id]):
        ui.say(ui.story_fill(line, "   ", "     "))


def shop(args) -> int:
    if not args:
        return shop_view()
    if args[0] == "all":
        return shop_view(show_all=True)
    if args[0] == "buy":
        if len(args) < 2:
            ui.bad("Что купить? ./termit shop buy ID (список — ./termit shop)")
            return 2
        return shop_buy(args[1])
    return shop_buy(args[0])


def _print_lines(lines) -> None:
    """Строки по ширине; строки с отступом (таблицы, календарь) печатаются как есть."""
    for line in lines:
        ui.say(line if not line or line.startswith("  ") else ui.story_fill(line, "", ""))


# подкоманды ./termit home СЛОВО: по ним охрана сверяет тексты «как пользоваться» (FB8)
HOME_SUBCOMMANDS = tuple(commands.HOME_ABOUT)


def home(args) -> int:
    p = progress.load(paths.PROGRESS_FILE)
    if not args:
        cp = tui.caps()
        room = hideout.render(p, "box" if cp.level == "rich" else "ascii")
        if cp.level != "plain":
            room[0] = "  " + tui.label(room[0].strip(), cp)
        _print_lines(room)
        rest = hideout.listing(p)
        if rest:
            ui.say()
            with ui.glossary_off():     # у каждой вещи своя строка ⚙ — ⓘ не нужны
                _print_lines(rest)
        ui.say()                # витрина видна из дома всегда (FB5 п. 16)
        ui.say(ui.story_fill(hideout.shop_line(), "  ", "  "))
        ui.say()                # дом — хаб: куда отсюда (FB5 п. 18)
        with ui.glossary_off():     # у каждой строки панели своё «что там» — ⓘ не нужны
            for line in home_hub(p):
                ui.say(line)
        ui.say()                # репутация (М6) и контракт недели (М5) — в убежище на виду
        if repute.grant(p):     # порог взят раньше, чем появилась награда, — рамка на месте
            progress.save(paths.PROGRESS_FILE, p)
        ui.say(ui.story_fill(repute.line(p, with_next=True), "  ", "    "))
        ui.say(ui.story_fill(weekly.line(p, date.today()), "  ", "    "))
        return 0
    if args[0] == "look":
        if len(args) < 2:
            ui.say("Что осмотреть? ./termit home look ID (список — ./termit home)")
            return 2
        _print_lines(hideout.look(p, args[1]))
        return 0
    if args[0] == "diary":
        return diary_cmd(args[1:])
    if args[0] == "prompt":
        return home_prompt(p, args[1:])
    if args[0] == "palette":
        return home_palette(p, args[1:])
    if args[0] == "callsign":
        return home_callsign(p, args[1:])
    if args[0] == "board":
        return home_board(p, args[1:])
    if args[0] == "shop":           # витрина прямо из дома — то же, что ./termit shop
        return shop(args[1:])
    if args[0] == "help":
        with ui.glossary_off():
            _print_lines(home_help(p))
        return 0
    ui.say("Убежище: ./termit home · осмотр: ./termit home look ID · "
           "приглашение: ./termit home prompt · палитра: ./termit home palette ID · "
           "дневник: ./termit home diary · позывной: ./termit home callsign ИМЯ · "
           "доска: ./termit home board · витрина: ./termit home shop · "
           "всё о доме: ./termit home help")
    return 2


# FB5 п. 18 (владелец: «нужны напоминалки дома — что как смотреть, где досье, где что»):
# панель «Куда отсюда» под комнатой — только то, что игроку уже открыто (как в cli.usage);
# слова — первая часть описания из commands.ABOUT / HOME_ABOUT, один источник
HUB = ("dossier", "case", "memory", "diary", "book", "keys", "map", "stats", "deck", "style",
       "music", "fence", "home board", "home prompt")


def _hub_open(p: dict) -> dict:
    on = _opened(p)
    has_story = story.has_story()
    parts = bool(hideout.prompt_parts(p)) or any(
        i in (p.get("owned") or ()) for i in hideout.WAVE2_PARTS)
    return {"dossier": on["dossier"] and has_story, "case": on["case"] and has_story,
            "memory": on["memory"] and has_story, "diary": on["diary"],
            "book": True, "keys": True, "map": True, "stats": True,
            "deck": on["deck"], "style": on["style"], "music": on["music"],
            "fence": on["fence"] and loot.enabled(),
            "home board": hideout.has_board(p), "home prompt": parts}


def _hub_about(name: str) -> str:
    if name.startswith("home "):
        text = commands.HOME_ABOUT[name[5:]][1]
    else:
        text = commands.about(name)
    return text.split(";")[0]


def home_hub(p: dict) -> list:
    """Панель «Куда отсюда»: команды, открытые игроку сейчас, по строке на каждую."""
    is_open = _hub_open(p)
    head = ("  Куда отсюда:" if commands.hub_on()
            else "  Куда отсюда (набирай после рана, не в задаче):")
    out = [head]
    for name in HUB:
        if is_open[name]:
            if name.startswith("home "):
                cmd = commands.home_cmd(name[5:])
            else:
                cmd = f"{commands.prefix()}{name}"
            out += ui.story_fill(f"{cmd:<21} {_hub_about(name)}", "    ",
                                 " " * 26).splitlines()
    out.append(f"  Подробно о доме — {commands.prefix()}home help")
    return out


def home_help(p: dict) -> list:
    """./termit home help: что такое дом, что на экране и все его команды."""
    return ["Дом — твоя комната с вещами и пульт игры. Вещи приходят подарками и с витрины; "
            "у каждой под именем строка ⚙ — как ею пользоваться. Что не стоит в комнате "
            "(досье, детали приглашения, модули деки, стиль…), лежит в разделе «Ещё твоё».",
            "",
            *[ui.story_fill(row.strip(), "  ", " " * 27)
              for row in [commands.line("home")] + [commands.home_line(sub)
                                                    for sub in commands.HOME_ABOUT]],
            "",
            "Внизу экрана дома — «Куда отсюда»: досье, дело, дневник, карта и прочее, что "
            "уже открыто. Все команды игры — ./termit help."]


def diary_cmd(args) -> int:
    """./termit diary [N|ID] (и ./termit home diary): только чтение, бесплатно."""
    p = progress.load(paths.PROGRESS_FILE)
    cp = tui.caps()
    if not args:
        ui.say("\n".join(diary.list_lines(p, cp)))
        return 0
    key = " ".join(args)
    ui.say("\n".join(diary.page(p, key, cp)))
    return 0 if diary.find(p, key) else 2


def style_cmd(args) -> int:
    """./termit style [ВИД ID|off]: купленные рамки, эффект итога, стиль карты, титул."""
    p = progress.load(paths.PROGRESS_FILE)
    st = cosmetics.style_text
    if not args:
        return style_view(p)
    kind = args[0]
    if kind not in cosmetics.STYLE_KINDS:
        ui.bad(st("unknown_kind", kind=kind))
        return 2
    if len(args) != 2:
        ui.say(st("usage"))
        if len(args) < 2:
            ui.say(_style_ids(p, kind))
        return 2
    label = st("title_kind" if kind == "title" else kind)
    if args[1] == "off":
        cosmetics.choose(p, kind, None)
        _save_settings(p)
        cosmetics.activate(p)
        ui.say(st("set_off", kind=label))
        return 0
    iid = cosmetics.resolve(kind, args[1])
    if iid is None or iid not in cosmetics.known_style(p, kind):
        if iid is not None:                  # есть в лестнице, но ещё не завозили
            ui.say(st("not_yet", name=shop_mod.name(iid)))
            return 2
        ui.bad(st("unknown", id=args[1], ids=", ".join(cosmetics.known_style(p, kind)) or "—"))
        return 2
    if iid not in cosmetics.owned_style(p, kind):
        ui.say(st("not_owned", name=shop_mod.name(iid)))
        return 2
    cosmetics.choose(p, kind, iid)
    _save_settings(p)
    cosmetics.activate(p)
    ui.ok(st("set", name=shop_mod.name(iid)))
    return 0


def _style_ids(p, kind: str) -> str:
    ids = cosmetics.known_style(p, kind)
    st = cosmetics.style_text
    # длинный список id переносится: в plain строки не шире 78 (FINAL-review M4)
    return ui.story_fill(st("ids", ids=", ".join(ids)), "", "  ") if ids else st("no_ids")


def style_view(p) -> int:
    st = cosmetics.style_text
    if not cosmetics.any_style(p):
        ui.say(st("empty"))
        return 0
    cp = tui.caps()
    rows = []
    for kind in cosmetics.STYLE_KINDS:
        have = cosmetics.owned_style(p, kind)
        if not have:
            continue
        pick = cosmetics.chosen(p, kind)
        label = st("title_kind" if kind == "title" else kind)
        rows.append((tui.style(f"{label} ({kind})" + ("" if pick else f" · {st('off')}"),
                               "bold", c=cp), "", ""))
        col = max(len(x) for x in have)
        for iid in have:
            mark = f" · {st('chosen')}" if iid == pick else ""
            rows.append(tui.Raw(f"  {iid.ljust(col)}  {shop_mod.name(iid)}{mark}"))
    rows += ["", tui.style(st("usage"), "dim", c=cp)]
    ui.say("\n".join(tui.box(rows, title=st("title"), kind="round", c=cp)))
    return 0


def _save_settings(p) -> None:
    progress.save(paths.PROGRESS_FILE, p)


def home_prompt(p, args) -> int:
    """./termit home prompt [on|off|show|path short|full]."""
    sub = args[0] if args else ""
    if not sub:
        _print_lines(hideout.prompt_lines(p))
        return 0
    if sub == "show":
        _print_lines(hideout.explain_prompt(p))
        return 0
    if sub in ("on", "off"):
        p.setdefault("settings", {})["prompt"] = sub == "on"
        _save_settings(p)
        if sub == "off":
            ui.say("Своё приглашение выключено: в задачах — приглашение твоей темы.")
        elif hideout.prompt_parts(p):
            ui.ok("Своё приглашение включено — со следующей задачи.")
        else:
            ui.say("Включено, но деталей пока нет. Витрина: ./termit shop")
        return 0
    if sub == "glyph":
        return home_glyph(p, args[1:])
    if sub == "path" and len(args) > 1 and args[1] in ("short", "full"):
        p.setdefault("settings", {})["prompt_path"] = args[1]
        _save_settings(p)
        ui.say(f"Путь в приглашении: {'%1~' if args[1] == 'short' else '%~'}"
               + ("" if f"path_{args[1]}" in p["owned"] else
                  f" — когда купишь деталь path_{args[1]}"))
        return 0
    ui.say("./termit home prompt [on|off|show|path short|full|glyph X]")
    return 2


BOARD_REPLIES = {
    "no_board": "Доски пока нет: её подарят за первое решённое задание.",
    "unknown": "Нет такой карточки: {card}. Есть: {cards}.",
    "closed": "Карточка {card} ещё закрыта — {note}.",
    "pinned": "Карточка {card} уже на доске.",
    "full": "Мест на доске нет: сначала сними одну — ./termit home board unpin КАРТОЧКА.",
    "not_pinned": "Карточки {card} на доске и так нет.",
    "auto": ("Карточка game висит сама, пока идут «Основы», и уйдёт после их стража. Убрать "
             "всё сейчас — ./termit home board off."),
}


def home_board(p, args) -> int:
    """./termit home board [pin КАРТОЧКА|unpin КАРТОЧКА|off|on] (FB5): доска убежища."""
    sub = args[0] if args else ""
    if not sub:
        _print_lines(hideout.board_view(p))
        return 0
    if sub in ("on", "off"):
        if not hideout.has_board(p):
            ui.say(BOARD_REPLIES["no_board"])
            return 2
        p.setdefault("settings", {})["board"] = sub == "on"
        _save_settings(p)
        if sub == "off":
            ui.say("Доска выключена: над приглашением в задачах ничего. Вернуть — "
                   "./termit home board on")
        else:
            ui.ok("Доска включена — со следующей задачи над приглашением.")
        return 0
    if sub in ("pin", "unpin") and len(args) == 2:
        card = args[1]
        act = hideout.board_pin if sub == "pin" else hideout.board_unpin
        ok, code = act(p, card)
        if ok:
            _save_settings(p)
            if sub == "pin":
                ui.ok(f"Приколото: {card} — со следующей задачи над приглашением.")
            else:
                ui.say(f"Снято: {card}. Вернуть — ./termit home board pin {card}")
            return 0
        note = hideout.open_note(card) if card in hideout.CARDS else ""
        ui.say(BOARD_REPLIES[code].format(card=card, cards=", ".join(hideout.CARDS),
                                          note=note))
        return 2
    ui.say("./termit home board — что на доске · pin КАРТОЧКА · unpin КАРТОЧКА · off · on")
    return 2


def home_glyph(p, args) -> int:
    """./termit home prompt glyph [X|off]: знак перед курсором (набор glyph_pack)."""
    names = " ".join(f"{g} {n}" for n, g in cosmetics.GLYPHS.items())
    if "glyph_pack" not in (p.get("owned") or ()):
        ui.say("Знаков приглашения у тебя пока нет. Витрина: ./termit shop")
        return 2
    if not args:
        cur = cosmetics.glyph(p)
        ui.say(f"Знак приглашения: {cur or 'снят (стоит ⟁, если есть значок деки)'}")
        ui.say(f"  есть: {names}")
        ui.say("  ./termit home prompt glyph ИМЯ|ЗНАК · снять: ./termit home prompt glyph off")
        return 0
    if len(args) != 1:
        ui.say("./termit home prompt glyph ИМЯ|ЗНАК|off")
        return 2
    if args[0] == "off":
        p.setdefault("settings", {})["glyph"] = None
        _save_settings(p)
        ui.say("Знак снят.")
        return 0
    g = cosmetics.resolve_glyph(args[0])
    if g is None:
        ui.bad(f"Такого знака в наборе нет. Есть: {names}")
        return 2
    p.setdefault("settings", {})["glyph"] = g
    _save_settings(p)
    ui.ok(f"Знак приглашения: {g} — со следующей задачи.")
    return 0


def home_callsign(p, args) -> int:
    """./termit home callsign [ИМЯ|off]: позывной в шапке рана и приглашении."""
    if not args:
        if "callsign" not in (p.get("owned") or ()):
            ui.say("Позывного пока нет. Витрина: ./termit shop")
            return 0
        cur = cosmetics.callsign(p)
        ui.say(f"Позывной: {cur or 'не задан'}")
        ui.say("  ./termit home callsign ИМЯ · снять: ./termit home callsign off")
        return 0
    if len(args) != 1:
        ui.say("Позывной — одно слово: ./termit home callsign ИМЯ")
        return 2
    code = cosmetics.set_callsign(p, args[0])
    if code == "not_owned":
        ui.say("Позывного у тебя пока нет. Витрина: ./termit shop")
        return 2
    if code == "bad":
        ui.bad("Позывной — от 2 до 12 знаков: буквы, цифры, _ и -. Без пробелов, без "
               "% $ ( ) ` \\ и кавычек — он попадает в приглашение zsh.")
        return 2
    _save_settings(p)
    if code == "off":
        ui.say("Позывной снят.")
    else:
        ui.ok(f"Позывной: {cosmetics.callsign(p)} — в шапке рана и в приглашении.")
    return 0


def home_palette(p, args) -> int:
    """./termit home palette [ID|off]: цвет пути в приглашении."""
    have = hideout.palettes(p)
    if not args:
        if not have:
            ui.say("Палитр пока нет. Витрина: ./termit shop")
            return 0
        cur = p.get("settings", {}).get("palette")
        for x in have:
            ui.say(f"  {'▸' if x == cur else ' '} {x[4:]:7} {shop_mod.name(x)}")
        ui.say("\nВыбрать: ./termit home palette ИМЯ · без цвета: ./termit home palette off")
        return 0
    want = args[0] if args[0].startswith("pal_") else "pal_" + args[0]
    if args[0] == "off":
        p.setdefault("settings", {})["palette"] = None
    elif want in have:
        p.setdefault("settings", {})["palette"] = want
    else:
        ui.say(f"Такой палитры у тебя нет: {args[0]}. Есть: "
               + (", ".join(x[4:] for x in have) or "пока никаких"))
        return 2
    _save_settings(p)
    ui.ok("Палитра: " + ("без цвета" if args[0] == "off" else shop_mod.name(want)))
    return 0


DECK_TEXTS = {   # нейтральные строки; тема может заменить своими (раздел deck)
    "in_slot": "Встал в слот — работает со следующей задачи. Дека: ./termit deck",
    "no_slot": "Куплен, слотов нет: ./termit deck — снять другой или открыть слот",
    "slot_open": "Слот открыт. Дека: ./termit deck",
    "slot_auto": "Слот открыт, и в него сразу встал купленный модуль: {name}. ./termit deck",
    "on": "Поставлено: {name}.",
    "off": "Снято: {name}. Остаётся твоим — вернуть: ./termit deck on {id}",
    "not_owned": "Сначала купи: ./termit shop {id}",
    "installed": "Уже стоит: {name}.",
    "no_slot_on": "Свободных слотов нет — сними другой: ./termit deck off ID",
    "unknown": "Нет такого модуля: {id}. Есть: {ids}",
    "not_on": "Не стоит: {name}.",
}


def _deck_text(key: str, **kw) -> str:
    return ((theme.story("deck") or {}).get(key) or DECK_TEXTS[key]).format(**kw)


def deck(args) -> int:
    """./termit deck — слоты и модули; deck on|off ID — поставить или снять, бесплатно."""
    p = progress.load(paths.PROGRESS_FILE)
    if args and args[0] in ("on", "off") and len(args) > 1:
        mid = args[1]
        kw = {"id": mid, "name": shop_mod.name(mid), "ids": ", ".join(shop_mod.MODULES)}
        if args[0] == "off":
            if shop_mod.get(mid) is None or shop_mod.get(mid).kind != "module":
                ui.say(_deck_text("unknown", **kw))
                return 2
            if not shop_mod.uninstall(p, mid):
                ui.say(_deck_text("not_on", **kw))
                return 0
            progress.save(paths.PROGRESS_FILE, p)
            ui.say(_deck_text("off", **kw))
            return 0
        code = shop_mod.install(p, mid)
        if code == "ok":
            progress.save(paths.PROGRESS_FILE, p)
        ui.say(_deck_text({"ok": "on", "no_slot": "no_slot_on"}.get(code, code), **kw))
        return 2 if code == "unknown" else 0
    if args:
        ui.say("./termit deck · ./termit deck on ID · ./termit deck off ID")
        return 2
    slots = p["deck"].get("slots", 1)
    installed = p["deck"].get("installed", [])
    ui.say(f"{shop_mod.section_title('deck')}: слотов {slots} из {1 + len(progress.SLOT_KARMA)}")
    for i in range(slots):
        mid = installed[i] if i < len(installed) else None
        ui.say(f"  слот {i + 1}: " + (f"{shop_mod.name(mid)} ({mid})" if mid else "пусто"))
        if mid and shop_mod.desc(mid):
            ui.say(_wrap(shop_mod.desc(mid), "           ", "           "))
    spare = [m for m in shop_mod.MODULES if shop_mod.owned(p, m) and m not in installed]
    if spare:                       # по одному в строке: имена длинные, ширина 76
        ui.say("  куплены, не стоят:")
        for m in spare:
            ui.say(f"    {shop_mod.name(m)} ({m})")
    nxt = slots + 1
    if nxt in progress.SLOT_KARMA and any(shop_mod.owned(p, m) for m in shop_mod.MODULES):
        need, karma = progress.SLOT_KARMA[nxt], progress.karma(p)
        item = shop_mod.get(f"slot{nxt}")
        gate = f"есть {karma}" if karma < need else "открыта"
        ui.say(f"  слот {nxt}: {theme.word('xp_title').lower()} {need} ({gate}) · "
               f"{item.price} {theme.word('money')} — ./termit shop slot{nxt}")
    if not any(shop_mod.owned(p, m) for m in shop_mod.MODULES):
        ui.say("  модулей пока нет — они на витрине: ./termit shop")
    ui.say("\nПоставить или снять (бесплатно): ./termit deck on ID · ./termit deck off ID")
    return 0


def sound_cmd(args) -> int:
    """./termit sound [on|off|test|pack ID|off|vol N]: купленные примочки звучат редко — только на взломе стража,
    рекорде и вехе серии. Играет родитель, песочница звуков не издаёт."""
    p = progress.load(paths.PROGRESS_FILE)
    sub = args[0] if args else ""
    have = sound_mod.gadgets(p)
    names = ", ".join(shop_mod.name(i) for i in have)
    if sub in ("on", "off"):
        p.setdefault("settings", {})["sound"] = sub == "on"
        _save_settings(p)
        if sub == "off":
            music.stop()                # выключить звук — это и дека тоже
            ui.say("Звуки выключены. Вернуть: ./termit sound on")
        elif have:
            ui.ok(f"Звуки включены: {names}. Звучат редко — на первом взломе босса, рекорде, "
                  "вехе серии.")
        else:
            ui.say("Включено, но звучать нечему: примочки — на витрине, ./termit shop")
        return 0
    if sub == "test":
        if not have:
            ui.say("Звучать нечему: примочки — на витрине, ./termit shop")
            return 0
        if not sound_mod.enabled(p):
            ui.say("Звуки выключены: ./termit sound on")
            return 0
        if os.environ.get("TERMIT_NO_SOUND"):
            ui.say("Звуки глушит переменная TERMIT_NO_SOUND.")
            return 0
        got = sound_mod.ring(p, "boss_down")
        ui.say(f"Проверка: {shop_mod.name(got)}." if got else "Тишина: системного звука на этом Mac не нашлось.")
        return 0
    if sub == "pack" and len(args) == 2:
        code = sound_mod.set_pack(p, args[1])
        if code in ("ok", "off"):
            _save_settings(p)
        packs = ", ".join(sound_mod.owned_packs(p)) or "нет — они на витрине, ./termit shop"
        ui.say({"ok": f"Звуки событий: {shop_mod.name(sound_mod.pack(p) or '')}.",
                "off": "Пакет снят: звучит кассета или звонок, если куплены.",
                "unknown": f"Нет такого пакета: {args[1]}. Куплены: {packs}.",
                "not_owned": f"{shop_mod.name(sound_mod.resolve_pack(args[1]) or '')} не куплен: "
                             "./termit shop"}[code])
        return 0 if code in ("ok", "off") else 2
    if sub == "vol" and len(args) == 2:
        n = int(args[1]) if args[1].isascii() and args[1].isdigit() else 0
        if not music.set_volume(p, n):
            ui.say("Громкость — от 1 до 10: ./termit sound vol 5")
            return 2
        _save_settings(p)
        ui.say(f"Громкость {n} из 10 — общая для звуков событий и деки.")
        _apply_volume(p)
        return 0
    if sub:
        ui.say("./termit sound [on|off|test|pack ID|off|vol 1..10]")
        return 2
    state = "включены" if sound_mod.enabled(p) else "выключены"
    ui.say(f"Звуки {state}. Примочки: {names or 'нет — они на витрине, ./termit shop'}.")
    vol = music.volume_level(p) if "volume" in (p.get("settings") or {}) else None
    ui.say(f"Громкость: {vol} из 10 (./termit sound vol N)." if vol else
           "Громкость: системная (./termit sound vol 1..10 — своя, общая с декой).")
    if sound_mod.owned_packs(p):
        ui.say("Пакеты: " + ", ".join(sound_mod.owned_packs(p)) +
               " — выбрать: ./termit sound pack ID · снять: ./termit sound pack off")
    ui.say("Звучат редко: первый взлом босса (повтор — молча), рекорд, веха серии — раз на "
           "событие за "
           f"{theme.word('session').lower()}.")
    ui.say("Выключить: ./termit sound off · включить: ./termit sound on · "
           "проверить: ./termit sound test")
    return 0


def _apply_volume(p) -> None:
    """Громкость общая: играющая дека перезапускается с новой (afplay не меняет её на ходу)."""
    now = music.playing()
    if now and now in music.owned_tapes(p):
        music.play(p, now)


def _music_say(code: str, item_id: str = "") -> None:
    ui.say(music.text(code, id=item_id, name=shop_mod.name(item_id) if item_id else ""))


def music_view(p) -> int:
    """./termit music: что играет, громкость, ран, записи, витрина."""
    ui.say(music.text("title"))
    now = music.playing()
    ui.say("  " + (music.text("playing", name=shop_mod.name(now)) if now else music.text("silent"))
           + " " + music.text("volume", n=music.volume_level(p)))
    tape = music.chosen_tape(p)
    ui.say("  " + (music.text("run_on", name=shop_mod.name(tape or ""))
                   if music.run_enabled(p) and tape else music.text("run_off")))
    have = music.owned_tapes(p)
    if have:
        ui.say(music.text("tapes"))
        col = max(len(i) for i in have)
        for iid in have:
            mark = "▶" if iid == now else ("·" if iid == tape else " ")
            ui.say(f"  {mark} {iid.ljust(col)}  {shop_mod.name(iid)}")
    else:
        ui.say("  " + music.text("no_tapes"))
    shelf = [i for i in cosmetics.offers(p) if music.tape_spec(i) is not None]
    if shelf:
        ui.say(ui.story_fill(music.text("shelf", ids=", ".join(shelf)), "", "  "))
    ui.say(music.text("usage"))
    return 0


def music_cmd(args) -> int:
    """./termit music [play ID|stop|vol N|preview ID|run on|off]: звук — только по команде."""
    p = progress.load(paths.PROGRESS_FILE)
    sub = args[0] if args else ""
    rest = args[1:]
    if sub == "stop" and not rest:
        code = music.halt()
        _music_say({"idle": "not_playing"}.get(code, code))
        return 0
    if sub == "preview":
        if len(rest) != 1:
            ui.say(music.text("usage"))
            return 2
        code = music.preview(p, rest[0])
        _music_say("preview" if code == "ok" else code, rest[0])
        return 0
    if "player" not in (p.get("owned") or ()):
        ui.say(music.text("no_player"))
        return 0 if sub in ("", "play") else 2
    if not sub:
        return music_view(p)
    if sub == "play" and len(rest) <= 1:
        tape = rest[0] if rest else music.chosen_tape(p)
        if not tape:
            ui.say(music.text("no_tape"))
            return 0
        code = music.play(p, tape)
        if code == "ok":
            _save_settings(p)
        _music_say(code, tape)
        return 0 if code != "missing" else 2
    if sub == "vol" and len(rest) == 1:
        n = int(rest[0]) if rest[0].isascii() and rest[0].isdigit() else 0
        if not music.set_volume(p, n):
            ui.say(music.text("usage"))
            return 2
        _save_settings(p)
        ui.say(music.text("vol_set", n=n))
        _apply_volume(p)
        return 0
    if sub == "run" and len(rest) == 1 and rest[0] in ("on", "off"):
        music.set_run(p, rest[0] == "on")
        _save_settings(p)
        tape = music.chosen_tape(p)
        if rest[0] == "on" and tape:
            ui.say(music.text("run_set_on", name=shop_mod.name(tape)))
        elif rest[0] == "on":
            ui.say(music.text("no_tape"))
        else:
            ui.say(music.text("run_set_off"))
        return 0
    ui.say(music.text("usage"))
    return 2


MODEL_NAME = re.compile(r"^[A-Za-z0-9._:/-]{1,80}$")


def owl_cmd(args) -> int:
    """./termit owl [on|off|model ИМЯ]: статус и настройки. Ollama только локальная."""
    p = progress.load(paths.PROGRESS_FILE)
    sub = args[0] if args else ""
    name = theme.word("owl")
    settings = p.setdefault("settings", {})
    if sub in ("on", "off"):
        settings["owl"] = sub == "on"
        _save_settings(p)
        ui.say(f"{name}: включена." if sub == "on" else
               f"{name}: выключена — ask молчит, денег не берёт. Вернуть: ./termit owl on")
        return 0
    if sub == "model":
        if len(args) < 2 or not MODEL_NAME.match(args[1]):
            ui.say("./termit owl model ИМЯ — например gemma3:4b (список: ./termit owl)")
            return 2
        settings["owl_model"] = args[1]
        _save_settings(p)
        names = owl_mod.models(timeout=1.0)
        if names is not None and args[1] not in names:
            ui.warn(f"Модели {args[1]} у Ollama нет — пока будет выбрана другая. "
                    f"Скачать: ollama pull {args[1]}")
        else:
            ui.say(f"{name}: модель {args[1]}.")
        return 0
    if sub:
        ui.say("./termit owl [on|off|model ИМЯ]")
        return 2
    on = settings.get("owl") is not False
    names = owl_mod.models(timeout=1.0)
    ui.say(f"{name}: {'включена' if on else 'выключена'}.")
    if names is None:
        ui.say(f"Ollama не найдена (не установлена или не запущена) — {name} спит, игра "
               "идёт как обычно, ask денег не берёт.")
        ui.say("Поставить: brew install ollama · ollama serve · ollama pull gemma3:4b")
    else:
        pick = owl_mod.pick_model(p, names)
        ui.say(f"Ollama: {OLLAMA_SHOWN}. Модели: {', '.join(names) or 'нет'}.")
        ui.say(f"Отвечает: {pick or '— (ollama pull gemma3:4b)'}.")
    w = theme.word("money")
    ui.say(f"В задаче: ask ВОПРОС — наводка, не ответ. Тренировка: "
           f"{progress.OWL_FREE_TRAIN} вопроса за {theme.word('session').lower()} бесплатно; "
           f"дело: {progress.OWL_BASE}×ярус {w} и −1 ★. Не больше {progress.OWL_PER_TASK} "
           f"на задачу и {progress.OWL_PER_RUN} за {theme.word('session').lower()}; "
           f"{theme.word('boss')}: ask молчит (в репетиции — можно).")
    ui.say("Выключить: ./termit owl off · модель: ./termit owl model ИМЯ")
    return 0


OLLAMA_SHOWN = owl_mod.OLLAMA_URL.replace("http://", "")


def fence(args) -> int:
    """./termit fence [sell N]: тайник и курсы трёх скупщиков; продать всё одному."""
    p = progress.load(paths.PROGRESS_FILE)
    today = date.today()
    if not args:
        _print_lines(loot.fence_lines(p, today))
        return 0
    n = len(loot.FENCE_K)
    if (args[0] != "sell" or len(args) < 2 or not (args[1].isascii() and args[1].isdigit())
            or not 1 <= int(args[1]) <= n):
        ui.say(f"./termit fence — курсы на сегодня · ./termit fence sell N (N от 1 до {n})")
        return 2
    if not loot.enabled():
        ui.say(loot.NO_FENCE)
        return 0
    if not p.get("paydata"):
        _print_lines(loot.fence_lines(p, today))
        return 0
    i = int(args[1]) - 1
    total = loot.sell(p, i, today)
    progress.save(paths.PROGRESS_FILE, p)
    ui.ok(loot.sold_line(theme.story("fences")[i]["name"], total))
    ui.say(f"   {theme.word('money_name')}: {ui.balance(p['money'])} {theme.word('money')}")
    return 0


def case_view(lines, cp: tui.Caps = None) -> list:
    """Доска дела: в plain — как есть; иначе заголовок плашкой, разделы — с маркером и цветом.
    Раздел — строка без отступа сразу после пустой."""
    cp = cp or tui.caps()
    if cp.level == "plain" or len(lines) < 2:
        return list(lines)
    mark = "▸ " if cp.level == "rich" else "> "
    out = [tui.label(lines[0], cp), tui.rule(cp, indent="")]
    for prev, line in zip(lines, lines[1:]):
        if not prev and line and not line.startswith(" "):
            line = tui.style(mark + line, "accent", c=cp)
        out.append(line)
    return out


def implants_cmd(args) -> int:
    """./termit implants [install ID | shell [write]]. brew — только после явного y."""
    p = progress.load(paths.PROGRESS_FILE)
    sub = args[0] if args else ""
    if not sub:
        _print_lines(implants.listing(p))
        return 0
    if sub == "install":
        imp = implants.find(args[1]) if len(args) > 1 else None
        if imp is None:
            ui.bad("Какую? ./termit implants install ID (список — ./termit implants)")
            return 2
        code = implants.install_cmd(p, imp, input)
        progress.save(paths.PROGRESS_FILE, p)
        return code
    if sub == "shell":
        return implants_shell(args[1:])
    ui.say("./termit implants · ./termit implants install ID · ./termit implants shell [write]")
    return 2


def wheels_cmd(args) -> int:
    """./termit wheels [status | get | verify | clean]. Скачивание — только после явного y."""
    sub = args[0] if args else "status"
    if sub == "status":
        _print_lines(warehouse.status_lines())
        return 0
    if sub == "get":
        p = progress.load(paths.PROGRESS_FILE)
        code = warehouse.get_cmd(p, input)
        progress.save(paths.PROGRESS_FILE, p)
        return code
    if sub == "verify":
        return warehouse.verify_cmd()
    if sub == "clean":
        return warehouse.clean_cmd(input)
    ui.say(warehouse.TEXT["usage"])
    return 2


def implants_shell(args) -> int:
    """./termit implants shell [write]: показать файл интеграции или записать его после y.
    ~/.zshrc игра не трогает никогда — строку source владелец вставляет сам."""
    if not args:
        _print_lines(implants.shell_lines())
        return 0
    if args != ["write"]:
        ui.say("./termit implants shell · ./termit implants shell write")
        return 2
    path = implants.SHELL_FILE
    try:
        answer = input(implants.text("shell_ask").format(path=path)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        answer = ""
    if answer not in implants.YES:
        ui.say(implants.text("not_now"))
        return 0
    if not implants.write_shell(path):
        ui.bad(implants.text("shell_refused").format(path=path))
        return 1
    ui.ok(implants.text("shell_written").format(path=path, line=implants.SHELL_LINE))
    return 0


def show_feedback() -> None:
    f = paths.FEEDBACK_FILE
    if not f.exists():
        ui.say("Замечаний пока нет. Внутри задачи: набери bug и опиши, что не так.")
        return
    for line in f.read_text("utf-8").splitlines():
        r = json.loads(line)
        ui.say(f"{r['when']}  [{r['task']}]  {r['text']}")


INTERRUPTED = "Прервано — ты снова в убежище."


IN_TASK_HUB = "Ты в задаче. quit — и вернёшься в убежище."


def main(argv) -> int:
    if os.environ.get("TERMIT_LAUNCHED"):
        # мы внутри песочницы задачи: вложенный termit запустил бы процессы задач без защиты
        if os.environ.get("TERMIT_HUB"):
            ui.bad(IN_TASK_HUB)
        else:
            ui.bad("termit уже запущен: ты внутри задачи. "
                   "Выйди из неё (quit) и запусти termit снова.")
        return 2
    flags, args, theme_flag = parse(argv)
    return run_once(args, flags, theme_flag)


def entry(argv) -> int:
    """Скрипты ./termit и ./termitrun: без слов — убежище, со словом — разовый запуск (main).
    Тесты зовут main: cli.main([]) в них — ран, а не хаб."""
    flags, args, theme_flag = parse(argv)
    if args or flags - FLAGS or "--help" in flags:
        return main(argv)
    from termit_app import hub         # поздно: hub сам импортирует cli
    return hub.main(flags, theme_flag)


def run_once(args, flags, theme_flag, hub: bool = False, ask=None) -> int:
    """Одно слово игры — тело прежнего main: тема, скин, строки первой встречи, Ctrl+C.
    Хаб зовёт её на каждое слово (hub=True): Ctrl+C не прощается, а возвращает в убежище;
    ask — чтение строки хаба, им же отвечают на вопросы внутри слова."""
    if theme_flag is not None and theme_flag not in theme.available():
        ui.bad(f"Нет темы {theme_flag!r}. Есть: " + ", ".join(theme.available()))
        return 2
    p = progress.load(paths.PROGRESS_FILE)
    theme.use(theme_flag or p.get("settings", {}).get("theme"))
    if flags - FLAGS or (args and args[0] in ("help", "-h")) or "--help" in flags:
        ui.say(usage(p))
        return 0 if not (flags - FLAGS - {"--help"}) else 2
    kw = {"ask": ask} if ask else {}
    opts = session.Options(no_sandbox="--no-sandbox" in flags, bare="--bare" in flags,
                           no_gui="--no-gui" in flags, sandbox_root=paths.SANDBOX_ROOT,
                           linger=True, hub=hub, **kw)     # FB3 (3): после решения — до next/more/quit
    if opts.no_sandbox:
        # без песочницы учебный PostgreSQL не запускается никогда (часть 9б): задачи стенда
        # недоступны (missing), общие задачи трека sql идут на SQLite
        os.environ["TERMIT_NO_PG"] = "1"
    cosmetics.activate(p)              # скин купленного стиля (в plain ничего не меняет)
    seen = list(p["cmds_seen"])
    if args and args[0] in commands.ABOUT and args[0] not in seen:
        seen.append(args[0])           # набранную команду игрок уже знает
    shown_before = len(seen)
    try:
        with ui.glossary(seen):
            return with_update_notice(args, opts)
    except KeyboardInterrupt:          # Ctrl+C у любого вопроса — спокойный выход без трассировки
        ui.say("\n" + (INTERRUPTED if hub else theme.msg("quit")))
        return 130
    finally:
        tui.set_skin()                 # скин живёт в пределах одного запуска (и одного теста)
        # без сохранения (игра ещё не начата) файл не заводим: просмотр ничего не пишет
        if len(seen) > shown_before and paths.PROGRESS_FILE.exists():
            remember_seen(seen)


def with_update_notice(args, opts) -> int:
    """Проверка обновления идёт в фоне; «вышло обновление» — на старте и в конце рана, раз в день."""
    game = (args[0] if args else "dozor") in GAME_CMDS
    if game:
        updates.start()
        note = updates.notice()
        if note:
            ui.say(note)
    try:
        return dispatch(args, opts)
    finally:
        if game:
            note = updates.notice()
            if note:
                ui.say(note)


def update_cmd() -> int:
    """./termit update (в хабе — слово update): подтянуть свежую версию игры."""
    ok, text = updates.update_text()
    ui.say(text)
    return 0 if ok else 1


def remember_seen(seen) -> None:
    """FB5: команды, которым показана строка «что это», — в прогресс. Файл перечитывается:
    ран и команды магазина сохраняют прогресс сами, их запись не затираем."""
    q = progress.load(paths.PROGRESS_FILE)
    q["cmds_seen"] += [x for x in seen if x not in q["cmds_seen"]]
    progress.save(paths.PROGRESS_FILE, q)


GAME_CMDS = {"dozor", "run", "short", "track", "play", "more", "rehearse", "master"}
BUSY = "TermitRun уже запущен в другом окне. Доиграй там или закрой то окно — и запусти снова."


LOCKED_INBOX = ("Ответ на вопрос меняет игру, а она сейчас идёт в другом окне. "
                "Доиграй там — и открой сообщение снова.")


def _inbox_pick(p, args):
    """Какое сообщение открыть: (сообщение, код ошибки)."""
    if args[0] == "next":
        new = inbox_mod.unread(p)
        return (new[0] if new else None), 0
    msg = inbox_mod.get(p, int(args[0])) if args[0].isascii() and args[0].isdigit() else None
    return msg, 2


def inbox_cmd(args, opts) -> int:
    """inbox - список сообщений на деке; inbox N - открыть; inbox next - первое новое.
    Открыл - прочитал; на вопрос отвечают прямо здесь (спека 2.5). Открытие пишет
    прогресс, поэтому идёт под замком игры: ран в другом окне не затрётся."""
    today = opts.today or date.today()
    p = progress.load(opts.progress_path)
    if not args:
        for line in inbox_mod.list_lines(p, today):
            ui.say(line)
        return 0
    msg, bad = _inbox_pick(p, args)
    if msg is None:
        if bad:
            ui.say(inbox_mod.NO_SUCH.format(n=args[0]))
        else:
            ui.say(inbox_mod.NO_NEW)
        return bad
    for line in inbox_mod.open_lines(msg, today):
        ui.say(line)
    lock = sandbox.lock_instance(opts.sandbox_root)
    if lock is None:
        ui.bad(LOCKED_INBOX)
        return 1
    try:
        p = progress.load(opts.progress_path)       # под замком - свежий прогресс
        msg = inbox_mod.get(p, msg["id"])
        if msg is None:
            return 0
        if msg["ask"]:
            reply = session._ask(opts, inbox_mod.ASK_PROMPT)
            inbox_mod.answer(p, msg, reply, today, opts)
        else:
            msg["read"] = True
        progress.save(opts.progress_path, p)
    finally:
        sandbox.unlock_instance(lock)
    return 0


def dispatch(args, opts) -> int:
    cmd = args[0] if args else "dozor"
    if cmd not in GAME_CMDS:
        return _dispatch(cmd, args, opts)
    lock = sandbox.lock_instance(opts.sandbox_root)    # одна игра за раз: песочницы общие
    if lock is None:
        ui.bad(BUSY)
        return 1
    try:
        return _dispatch(cmd, args, opts)
    finally:
        sandbox.unlock_instance(lock)


def _dispatch(cmd, args, opts) -> int:
    if cmd in ("dozor", "run"):        # run — то же слово, что в убежище
        session.dozor(opts)
    elif cmd == "short":
        session.dozor(opts, short=True)
    elif cmd == "track" and len(args) > 1:
        session.run_track(args[1], opts)
    elif cmd == "play" and len(args) > 1:
        session.play_one(args[1], opts)
    elif cmd == "more":
        session.more(opts)
    elif cmd == "master":
        session.master_run(opts)
    elif cmd == "rehearse":
        if len(args) < 2:
            ui.say("Кого репетировать? ./termit rehearse ID (id — в ./termit list)")
            return 2
        session.rehearse(args[1], opts)
    elif cmd == "stats":
        show_stats()
    elif cmd == "list":
        show_list()
    elif cmd == "book":
        show_book(" ".join(args[1:]))
    elif cmd == "theme":
        return choose_theme(args[1] if len(args) > 1 else None)
    elif cmd == "keys":
        ui.say(ui.keys_sheet(args[1:]))
    elif cmd == "ext":
        ui.say(extensions.sheet(progress.load(paths.PROGRESS_FILE)["extensions"]))
    elif cmd == "intro":
        ui.show_intro(theme.intro_text(), guide=True)
    elif cmd == "shop":
        return shop(args[1:])
    elif cmd == "deck":
        return deck(args[1:])
    elif cmd == "home":
        return home(args[1:])
    elif cmd == "diary":
        return diary_cmd(args[1:])
    elif cmd == "style":
        return style_cmd(args[1:])
    elif cmd == "memory":
        ui.say("\n".join(story.memory_lines(progress.load(paths.PROGRESS_FILE))))
    elif cmd == "dossier":
        ui.say("\n".join(story.dossier_lines(progress.load(paths.PROGRESS_FILE),
                                             " ".join(args[1:]) or None)))
    elif cmd == "case":
        ui.say("\n".join(case_view(story.case_lines(progress.load(paths.PROGRESS_FILE)))))
    elif cmd == "map":
        ui.say("\n".join(citymap.lines(progress.load(paths.PROGRESS_FILE))))
    elif cmd == "sound":
        return sound_cmd(args[1:])
    elif cmd == "music":
        return music_cmd(args[1:])
    elif cmd == "owl":
        return owl_cmd(args[1:])
    elif cmd == "fence":
        return fence(args[1:])
    elif cmd == "inbox":
        return inbox_cmd(args[1:], opts)
    elif cmd == "feedback":
        show_feedback()
    elif cmd == "report":
        ui.say("\n".join(edition.report_lines()))
    elif cmd == "update":
        return update_cmd()
    elif cmd == "implants":
        return implants_cmd(args[1:])
    elif cmd == "wheels":
        return wheels_cmd(args[1:])
    else:
        with ui.glossary_off():        # справка сама объясняет каждую команду
            ui.say(usage(progress.load(paths.PROGRESS_FILE)))
        return 2
    return 0
