"""Пульт убежища: экран, строка подсказки, правило пустого Enter (спека 2.3). Без сети и
подпроцессов: только прогресс и реестр задач."""
from datetime import date, timedelta
from typing import List, Optional, Tuple

from termit_app import hideout, inbox, progress, pyenvs, session, theme, tui, ui, weekly
from termit_app.tasks import registry

LABELS = {"run": "ран дня", "inbox next": "читать деку", "train": "отработка",
          "lesson": "ещё урок", "master": "круг мастера", "hub": "пульт"}
LABEL_FRESH = "подтянуть свежее"


def today() -> date:
    """«Сегодня» пульта — функцией, чтобы тесты подменяли полночь."""
    return date.today()


def ran_today(p: dict, day: date) -> bool:
    return day.isoformat() in (p.get("days") or ())


def unread_count(p: dict) -> int:
    return len(inbox.unread(p))


def drill_ids(p: dict, day: date) -> List[str]:
    """Что реально даст отработка сейчас. До отработки (шаг 8 спеки) — ничего."""
    return []


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
    """Новый урок для lesson; страж — экзамен, его Enter не предлагает (спека 2.3)."""
    new = session.next_new(p, 1)
    if new and not registry.get(new[0]).boss:
        return new[0]
    return None


def to_boss(p: dict) -> Optional[int]:
    """Сколько обычных задач текущего места ещё не решено до стража; None — стража впереди
    нет. Текущее место — первое открытое, где страж ещё не взломан."""
    for tr in registry.unlocked(p["bosses"]):
        ts = registry.tasks_of(tr.key)
        if not any(t.boss and t.id not in p["bosses"] for t in ts):
            continue
        return sum(1 for t in ts
                   if not t.boss and not (p.get("tasks", {}).get(t.id) or {}).get("solved"))
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
            line = "lesson"
        elif drills:
            line = "train"
        elif progress.master_open(p):
            line = "master"
        else:
            line = "hub"
    return line, LABELS[line]


WIDTH = 74
NEW_DAY = "Новый день: ран дня обновлён."
TOUR = ("Это убежище — твой пульт между ранами. Здесь набирают короткие слова игры, а не "
        "команды терминала. Enter делает то, что отмечено ⏎. Все слова — help, выйти — "
        "quit. В следующий раз запусти игру так же — и окажешься здесь.")
SILENT = ("hub", "help", "clear", "quit", "home")      # всегда в подсказке или служебные
NEW_IN_RELEASE = ("train", "inbox")     # слова этого выпуска: знакомство их не гасит
MAX_FRESH = 8                           # столько новых слов предлагает пульт за раз
MAX_HINT = 6
HINT_WIDTH = 78


def _row(label: str, text: str, word: str) -> str:
    left = f"  {label}{' ' * max(1, 12 - tui.vlen(label))}{text}"
    left = tui.trunc(left, WIDTH - 10)
    return (tui.pad(left, WIDTH - 9) + word).rstrip()


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


def board(p: dict, day: date, cp=None) -> List[str]:
    with pyenvs.cache_only():
        return _board(p, day, cp)


def _board(p: dict, day: date, cp) -> List[str]:
    """Пульт: шапка и строки «что сейчас» — пустые не показываются; справа слово, которое
    строку открывает, у одной строки — [Enter] (спека 2.3, UX §2). Без подпроцессов:
    доступность задач считается по кэшу интерпретатора."""
    cp = cp or tui.caps()
    enter = default_action(p, day)[0].split()[0]

    def mark(word: str) -> str:
        return "[Enter]" if word == enter else word

    rows = []
    if ran_today(p, day):
        rows.append(_row("Ран дня:", "сыгран ✓ · завтра будет новый", ""))
    else:
        rows.append(_row("Ран дня:", run_text(p, day), mark("run")))
    left = to_boss(p)
    if left:
        word = ui.plural(left, "задача", "задачи", "задач")
        rows.append(_row("Страж:", f"до стража {left} {word}", ""))
    unread = unread_count(p)
    if unread:
        word = ui.plural(unread, "новое сообщение", "новых сообщения", "новых сообщений")
        rows.append(_row("Дека:", f"{unread} {word}", mark("inbox")))
    drills = drill_ids(p, day)
    if drills:
        rows.append(_row("Отработка:", f"подтянуть: {len(drills)}", mark("train")))
    if ran_today(p, day) and next_lesson(p):
        rows.append(_row("Ещё урок:", "новая команда сверх нормы", mark("lesson")))
    if weekly.visible(p, day):
        rows.append(_row("Неделя:", weekly.short_line(p, day).strip(), ""))
    if hideout.has_board(p):
        cards = ", ".join(hideout.pinned(p)) or "пусто"
        rows.append(_row("Доска:", f"мест {hideout.board_slots(p)}: {cards}", "board"))
    rows.append(_row("Комната:", f"вещей: {len(hideout.owned_items(p))}", "home"))
    if enter == "master":
        rows.append(_row("Круг:", "знакомые дела на время, против рекорда", "[Enter]"))
    head = header(p, day)
    if cp.level == "plain":
        return [tui.trunc(head, 78)] + rows
    return [tui.trunc("  " + tui.label(head, cp), 78), tui.rule(cp, indent="  ")] + rows


def fresh_words(p: dict, names: List[str]) -> List[str]:
    """Слова из names, которые подсказка ещё не показывала; не больше MAX_FRESH за раз."""
    shown = set(p.get("hub", {}).get("shown") or ())
    return [n for n in names if n not in shown and n not in SILENT][:MAX_FRESH]


def tour_shown(p: dict, names: List[str]) -> List[str]:
    """Что считать показанным после первого знакомства: все слова, кроме новых в этом выпуске —
    их игроки со старым сохранением должны увидеть с пометкой «новое»."""
    shown = list(p.get("hub", {}).get("shown") or ())
    return shown + [n for n in names if n not in shown and n not in NEW_IN_RELEASE]


def hint_line(p: dict, day: date, fresh: List[str] = ()) -> str:
    """Строка над приглашением: первым — что сделает ⏎, последним — quit; до 6 пунктов,
    не шире 78 колонок. Первый визит (знакомства ещё не было) — только ⏎, home, help,
    quit (UX §8)."""
    with pyenvs.cache_only():
        line, label = default_action(p, day)
    unread = unread_count(p)
    if line == "inbox next" and unread:
        label = f"{label} ({unread})"           # число — тут же, без второго «inbox»
    items = [f"⏎ {label}"]
    tail = ["home", "help", "quit — выйти"]
    if not p.get("hub", {}).get("tour"):
        return " · ".join(items + tail)
    if unread and line != "inbox next":
        items.append(f"inbox ({unread})")
    items += [f"{w} — новое" for w in fresh[:2]]
    items = items[:MAX_HINT - len(tail)]
    # не влезло — выбрасываем с конца необязательное, quit остаётся
    while len(items) > 1 and tui.vlen(" · ".join(items + tail)) > HINT_WIDTH:
        items.pop()
    return tui.trunc(" · ".join(items + tail), HINT_WIDTH)
