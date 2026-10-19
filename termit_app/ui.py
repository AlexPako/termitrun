"""Вывод в терминал: цвета, заголовок рана, карточка поручения, разбор. Слова — из темы."""
import contextlib
import os
import re
import sys
import textwrap
from typing import Optional

from termit_app import commands, icons, origins, progress, textnorm, theme, tui, zsh_only


def _color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR") and \
        os.environ.get("TERM") != "dumb"


def _framed() -> tui.Caps:
    """Возможности терминала для этого экрана; level plain — вывод как до графики."""
    return tui.caps()


def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _color() else s


# FB5 (владелец: «не понятно, что за команда ./termit home»): когда сообщение игры впервые
# называет команду ./termit СЛОВО, под ним — строка «что это и когда набирать» (commands.note).
# _seen — встреченные команды (progress["cmds_seen"]) на время запуска (cli.main, glossary);
# None — выключено (тесты модулей, процесс задачи). Строка внутри рамки ждёт её конца.
_seen = None
_pending = []
_ANSI = re.compile(r"\033\[[0-9;]*m")
_FRAME_INSIDE = "│║┃|├╠"


@contextlib.contextmanager
def glossary(seen):
    """На время блока — строки первой встречи; seen — список, дополняется на месте."""
    global _seen
    before = _seen
    _seen = seen
    try:
        yield seen
    finally:
        _flush()
        _seen = before


@contextlib.contextmanager
def glossary_off():
    """Текст, который сам объясняет команды (справка, вступление), — без строк первой встречи."""
    global _seen
    before = _seen
    _seen = None
    try:
        yield
    finally:
        _seen = before


def _flush() -> None:
    while _pending:
        name = _pending.pop(0)
        if _seen is not None and name not in _seen:
            _seen.append(name)
            print(c("2", story_fill(commands.note(name), "   ", "     ")))


def _glossary(s: str) -> None:
    if _seen is None:
        return
    plain = _ANSI.sub("", s)
    _pending.extend(n for n in commands.mentioned(plain) if n not in _seen and n not in _pending)
    head = plain.split("\n")[-1].lstrip()[:1]
    if _pending and (not head or head not in _FRAME_INSIDE):
        _flush()


def say(s: str = "") -> None:
    print(s)
    _glossary(s)


def ok(s: str) -> None:
    print(c("32", s))
    _glossary(s)


def bad(s: str) -> None:
    print(c("31", s))
    _glossary(s)


def warn(s: str) -> None:
    print(c("33", "⚠ " + s))
    _glossary(s)


def stars(n: int) -> str:
    return "★" * n + "☆" * (3 - n)


def task_mark(rec) -> str:
    """Отметка в ./termit list: · — не встречалась, ✓ — освоена в тренировке, звёзды — дело."""
    if not rec:
        return "·  "
    got = progress.job_stars(rec)
    if got is None:
        return "✓  " if rec.get("solved", 0) else stars(0)
    return stars(got)


def fmt_time(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def _wrap(text: str, indent: str = "   ", width: int = 78) -> str:
    return "\n".join(textwrap.fill(line, width, initial_indent=indent, subsequent_indent=indent,
                                     break_long_words=False, break_on_hyphens=False)
                     if line else "" for line in text.split("\n"))


NBSP = "\u00a0"    # textwrap не рвёт строку на неразрывном пробеле


def lesson_block(text: str, width: int = 78) -> str:
    """Мини-урок одним абзацем: команда в `…` не рвётся, тире не начинает строку."""
    parts = " ".join(text.split()).split("`")
    for i in range(1, len(parts), 2):                 # нечётные куски — внутри `…`
        parts[i] = parts[i].replace(" ", NBSP)
    glued = "`".join(parts).replace(" — ", NBSP + "— ")
    return textwrap.fill(glued, width, initial_indent="   ", subsequent_indent="   ",
                         break_long_words=False, break_on_hyphens=False).replace(NBSP, " ")


CODE = re.compile(r"`([^`\n]+)`")


def code_spans(text: str, cp: tui.Caps) -> str:
    """Команды в `…` — цветом без обратных кавычек: глаз сразу видит, что набирать.
    Без цвета (plain, NO_COLOR) кавычки остаются — иначе команду не отличить от текста."""
    if cp.level == "plain" or not cp.colors:
        return text
    return CODE.sub(lambda m: tui.style(m.group(1), "code", c=cp), text)


def balance(money: int) -> str:
    """Баланс для экрана: минус — это долг за подсказки."""
    return f"−{-money} (долг)" if money < 0 else str(money)


def header(title: str, streak: int, rank: str, count: int, money: int = None) -> None:
    """Заголовок рана; карма сюда не выводится — она только в ./termit stats.
    streak=None или 0 — серию не показываем: огонёк рядом с нулём звучал бы укором (П3.8)."""
    cash = "" if money is None else f"{theme.word('money')} {balance(money)} · "
    run = f"серия {streak} дн. 🔥 · " if streak else ""
    say()
    cp = _framed()
    rest = f"{run}{rank} · {cash}{theme.word('tasks_gen')}: {count}"
    if cp.level == "plain":
        say(c("1", f"  {title} · {rest}"))
        return
    say("\n".join(tui.fill(f"{tui.label(title, cp)} {tui.style(rest, 'bold', c=cp)}",
                            tui.STORY, "  ", "    ")))


def task_card(n, total, track, task, state, first_time: bool, mode: str = "train",
              unsolved: bool = False, par: float = None, rehearsal: bool = False,
              urgent: bool = False, owl: bool = False, master: str = None) -> None:
    """Карточка приёмов — при первой встрече, в тренировке и пока задача ни разу не решена.
    master — строка режима круга мастера (рекорд вместо таймера), вместо метки тренировки."""
    say()
    name = theme.title(task)
    label = f"[{n}/{total}] {theme.place(track.key)} · " + \
        (f"{theme.word('fight')}: {name}" if task.boss else name)
    if urgent:
        label += f" · {theme.word('urgent_mark')}"
    mode_word = master or theme.word("rehearsal_mode" if rehearsal else
                                     "job_mode" if mode == "job" else "train_mode")
    cp = _framed()
    if cp.level == "plain":
        say(c("1", label))
        say(c("2", "   " + mode_word))
    else:                   # шапка в рамке: задача — текст, поэтому рамка только вокруг шапки
        for row in tui.box([mode_word], title=label, kind="round", c=cp,
                           color="boss" if task.boss else "frame"):
            say(row)
    mark = "▸ " if cp.level == "rich" else "> " if cp.level == "basic" else ""
    wide = 78 if cp.level == "plain" else min(78, cp.width - 1)    # текст — по окну 60–78
    tw = tui.STORY if cp.level == "plain" else min(tui.STORY, cp.width - 2)
    if task.scroll and not master and (first_time or mode == "train" or unsolved):
        lesson = theme.lesson(task, state)
        # «новая прога» — только при первой встрече; повтор стража, выгодный ран, тренировка
        # после провала — «напомню приёмы» (P2 Б7: на экзамене «новое» само поднимает тревогу)
        spell = theme.word("new_spell" if first_time else "remind_spell")
        if lesson:          # урок персонажа вместо сухой шпаргалки
            say(c("36", f"{mark}{spell} · {theme.speaker(task)}:"))
            say(code_spans(lesson_block(lesson, wide), cp))
        else:
            say(c("36", mark + spell + ":"))
            say(_wrap(task.scroll_for(state) or task.scroll, width=wide))
        origin_notes(task.id, cp, tw)
    head = theme.intro(task, state)
    line = f"💬 {theme.speaker(task)}:" + (f" {head}" if head else "")
    if cp.level == "plain":
        say(textwrap.fill(line, 78, subsequent_indent="   ",
                          break_long_words=False, break_on_hyphens=False))
    else:                       # по экранной ширине: эмодзи в начале — две клетки
        say("\n".join(tui.fill(line, tw, "", "   ")))
    # само задание — жирным: что делать, видно сразу после урока и реплики
    say(tui.style(_wrap(task.text(state), width=wide), "bold", c=cp))
    # длинный шаг — переносом, под своим текстом
    for i, step in enumerate(task.steps_for(state), 1):
        say("\n".join(tui.style(r, "bold", c=cp)
                      for r in tui.fill(f"{i}. {step}", tw, "   ", "      ")))
    job = mode == "job"
    par = task.par_for(state) if par is None else par         # с модулем «охладитель» — длиннее
    timer = f"   {theme.word('timer')} {fmt_time(par)}" if job else ""
    hint = (f"hint — {theme.word('soft_label')} за {theme.word('money')}" if job
            else "hint — бесплатно")
    keys = f"task — задание снова · lesson — урок · {hint} · ans ОТВЕТ · reset · giveup · skip · quit · bug — замечание"
    if cp.level == "plain":     # Н3.8: в 80 колонок — переносом, таймер не отрывается
        items = (keys + timer.replace("   ", " · ", 1)).split(" · ")
        # по экранной ширине: 💳 и ⏱ — две клетки (textwrap считал их за одну)
        rows = tui.fill((NBSP + "· ").join(x.replace(" ", NBSP) for x in items), 75)
        say("\n".join(c("2", "   " + r.replace(NBSP, " ")) for r in rows))
    else:               # под чертой; в 78 колонок — переносом, таймер не отрывается
        say(tui.rule(cp))
        items = (keys + timer.replace("   ", " · ", 1)).split(" · ")
        # «bug — замечание» целиком, точка-разделитель — в конце строки, не в начале
        glued = (NBSP + "· ").join(x.replace(" ", NBSP) for x in items)
        rows = tui.fill(glued, tw, "   ", "   ")
        say("\n".join(tui.style(r.replace(NBSP, " "), "dim", c=cp) for r in rows))
    notes = [answer_form(task, state)]
    if job:             # отсчёт — с открытия задания (FB5)
        notes.append(TIMER_RUNS)
    elif first_time:
        notes.append(TIMER_OFF)
    if first_time and not job:
        notes += [HINT_OK, KEY_TIPS.get(task.id)]
    for note in notes:
        if not note:
            continue
        if cp.level == "plain":
            say(c("2", textwrap.fill(note, 78, initial_indent="   ", subsequent_indent="   ",
                                     break_long_words=False, break_on_hyphens=False)))
        else:
            say("\n".join(tui.style(r, "dim", c=cp) for r in tui.fill(note, tw, "   ", "   ")))
    if owl:             # мост Совы запущен (Ollama есть и Сова не выключена)
        say(c("2", f"   ask ВОПРОС — {theme.word('owl')}: наводка, не ответ"))


def origin_notes(task_id: str, cp: tui.Caps, tw: int) -> None:
    """FB5 (12): «🔤 pwd: «print working directory» …» — откуда имя у команды, впервые
    названной в этом уроке (origins.FIRST_SEEN), — тускло, под уроком или шпаргалкой.
    FB6: следом «🐚 только в zsh: …» — приёмы урока, которых в bash нет (zsh_only.FIRST_SEEN)."""
    for line in origins.notes(task_id) + zsh_only.notes(task_id):
        if cp.level == "plain":
            say(c("2", textwrap.fill(line, 78, initial_indent="   ", subsequent_indent="      ",
                                     break_long_words=False,
                                     break_on_hyphens=False).replace(NBSP, " ")))
        else:
            say("\n".join(tui.style(r, "dim", c=cp) for r in tui.fill(line, tw, "   ", "      ")))


# задача «Основ», где игрок впервые видит cat и ans $(cat файл): до неё про них не говорим
CAT_FIRST = "climb_down"


def _text(task, state) -> str:
    try:
        return str(task.text(state))
    except (AttributeError, KeyError, IndexError, ValueError, TypeError):
        return ""


def _cat_taught(task) -> bool:
    from termit_app.tasks import registry
    order = [t.id for t in registry.tasks_of("basics")]
    tid = getattr(task, "id", None)
    if tid not in order or CAT_FIRST not in order:
        return True
    return order.index(tid) >= order.index(CAT_FIRST)


def answer_form(task, state) -> Optional[str]:
    """Что сдавать — заранее, по форме эталона (слово, число, путь), не по его значению.
    FB5 (владелец 19.10): «где-то принимает $(cat файл), а где-то требует только слово»."""
    try:
        if not task.takes_answer(state):
            return None
        kind, exp = task.answer_kind(state), str(task.expected(state))
    except (AttributeError, KeyError, IndexError, ValueError, TypeError):
        return None
    if kind == "number":
        return "Сдаёшь одно число: ans ЧИСЛО — без слов вокруг."
    if kind == "path":
        return None             # путь задание объясняет само (ans $(pwd) и т.п.)
    n = len(textnorm.parts(exp))
    if n == 1 and "ans ИМЯ" in _text(task, state):     # FB6: задание просит имя, не слово
        return "Сдаёшь одно имя: ans ИМЯ — целиком, как написано, без остального текста."
    if n == 1 and not _cat_taught(task):        # FB6: $( ) и cat ещё не встречались
        return "Сдаёшь одно слово: ans СЛОВО — без остального текста."
    if n == 1:
        return ("Сдаёшь одно слово: ans СЛОВО — без остального текста (ans $(cat файл) "
                "подойдёт, только если в файле одно это слово).")
    return f"Сдаёшь {n} {plural(n, 'слово', 'слова', 'слов')} через пробел: ans СЛОВО СЛОВО…"


REHEARSAL_UNTOUCHED = "🎭 Это была репетиция — прогресс не тронут."


def review(task, state, outcome, mine, elapsed, stars_n, record_from,
           mode: str = "train", earned: int = 0, spent: int = 0,
           after_fail: str = None, rehearsal: bool = False, reaction: str = None) -> None:
    """after_fail — строка под «провалено» (у стража: первая репетиция даром).
    rehearsal — репетиция: ни шпаргалки, ни расписания, только разбор.
    reaction — реплика персонажа, выбранная по исходу (session.pick_reaction); None — по
    исходу и зерну, как раньше."""
    cash = theme.word("money")
    paid = f"   {theme.word('soft_label')}: −{spent} {cash}"
    # команда и эталон собраны из cmds.log и task.json песочницы — без управляющих кодов (В4)
    clean = progress.clean_text
    untouched = "   " + REHEARSAL_UNTOUCHED
    if outcome == "skip":
        if rehearsal:
            say(untouched.strip())
            return
        say("Отложено — вернётся завтра.")
        if spent:
            say(paid)
        return
    if outcome == "solved":
        tick = "✓ " + icons.mark(icons.of_task(task))     # значок инструмента — только в rich
        if mode == "train":         # звёзды в тренировке — только у выгодного рана (М1)
            line = f"{tick}Освоено за {fmt_time(elapsed)}" + (f"  {stars(stars_n)}" if stars_n else "")
            if earned:
                line += f"  +{earned} {cash}"
        else:
            line = f"{tick}Решено за {fmt_time(elapsed)}  {stars(stars_n)}"
            if earned:
                line += f"  +{earned} {cash}"
        if record_from is not None:
            line += f"  · рекорд! (было {fmt_time(record_from)})"
        ok(line)
        cp = _framed()
        if mine:
            say(f"   Ты:     {tui.style(clean(mine), 'code', c=cp)}")
        say(f"   Эталон: {tui.style(clean(task.shown_solution(state)), 'code', c=cp)}")
    else:
        bad("Сдался — не беда. Вот решение:")
        say(f"   {tui.style(clean(task.shown_solution(state)), 'code', c=_framed())}")
    if spent:
        say(paid)
    say(story_fill(f"Почему: {task.explain_for(state)}", "   ", "   "))     # Н3.8: по ширине
    if rehearsal:
        say(c("36", untouched))
    elif outcome == "solved":
        say(c("36", f"   {theme.word('book_add')}: {task.spell}"))
    elif mode == "job":
        say(story_fill(theme.msg("boss_failed" if task.boss else "job_failed"), "   ", "   "))
        if after_fail:
            say(story_fill(after_fail, "   ", "   "))
    else:
        say("   Задача вернётся завтра.")
    react(task.track, outcome, state.get("_seed", 0), line=reaction)


def react(track_key: str, outcome: str, seed: int, line: str = None) -> None:
    """Одна реплика персонажа трека после разбора — если у темы она есть."""
    line = line or theme.reaction(track_key, outcome, seed)
    if line:
        say(story_fill(f"💬 {theme.sender(track_key)}: {line}", "   ", "      "))


def voice(name: str, line: str) -> None:
    """Внутренний голос героя — тусклым курсивом, после реплики персонажа."""
    text = story_fill(f"{name} — {line}", "  ", "    ")
    say("\n".join(c("2;3", row) for row in text.splitlines()))


STORY_WIDTH = 76    # сюжетные строки: запас на двойную ширину эмодзи в терминале


def story_fill(text: str, first: str = "", rest: str = "   ") -> str:
    """Абзац по ширине; два последних слова склеены, чтобы одно слово не висело на строке."""
    head, sep, tail = text.rstrip().rpartition(" ")
    glued = head + NBSP + tail if sep and head.strip() else text
    glued = glued.replace("./termit ", "./termit" + NBSP)     # команда не рвётся после ./termit
    return textwrap.fill(glued, STORY_WIDTH, initial_indent=first, subsequent_indent=rest,
                         break_long_words=False, break_on_hyphens=False).replace(NBSP, " ")


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def shift_summary(title: str, streak_before: int, streak_after: int, solved: int = 0,
                  mastered: int = 0, warmed: int = 0, records=(), earned: int = 0, spent: int = 0,
                  book_total: int = 0, book_new: int = 0, freeze_saved: bool = False,
                  milestone: str = None, milestone_pay: int = 0, extra=(),
                  reward_at: int = None, week=None) -> None:
    """Экран «ран закрыт»: рамка, веха серии — событием под ней. reward_at — день следующей
    денежной вехи серии (строка с баром), week — активность по дням недели (спарклайн).
    rich — двойная рамка (она только здесь: итог — событие), basic — ASCII, plain — как было."""
    cp = _framed()
    rows = []
    if streak_before and streak_before != streak_after:
        rows.append(f"Серия: {streak_before} → {streak_after} дн. 🔥")
    else:
        rows.append(f"Серия: {streak_after} дн. 🔥")
    done = [f"решено: {solved}"] if solved else []
    if mastered:
        done.append(f"освоено: {mastered}")
    if warmed:
        done.append(f"размялся: {warmed}")
    if done:
        text = " · ".join(done)
        rows.append(text[0].upper() + text[1:])
    if records:
        label = "Рекорд" if len(records) == 1 else "Рекорды"
        rows.append(f"{label}: " + ", ".join(
            f"{r[0]} {r[1]}" + (f" (было {r[2]})" if len(r) > 2 else "") for r in records))
    cash = theme.word("money")
    money = ([f"заработано +{earned} {cash}"] if earned else []) + \
        ([f"{theme.word('soft_label')} −{spent} {cash}"] if spent else [])
    if money:
        text = " · ".join(money)
        rows.append(text[0].upper() + text[1:])
    if book_total:
        rows.append(f"{theme.word('book')}: {book_total} "
                    f"{plural(book_total, 'команда', 'команды', 'команд')}"
                    + (f" (+{book_new})" if book_new else ""))
    if freeze_saved:
        rows.append(theme.msg("freeze_saved"))
    rows.extend(extra)
    gauges = []
    if reward_at:
        left = max(0, reward_at - streak_after)
        gauges.append(f"До награды серии: {_gauge(streak_after, reward_at, cp)}"
                      f"{streak_after} из {reward_at} дн. (осталось {left})")
    if week:
        active = sum(1 for v in week if v)
        sp = tui.spark(week, cp)
        gauges.append(f"За неделю: {sp + '  ' if sp else ''}активных дней {active} из {len(week)}")
    say()
    if cp.level == "plain":
        say(c("1", f"  +-- {title} " + "-" * max(4, 56 - len(title))))
        for row in rows + gauges:
            say(story_fill(row, "  | ", "  |   "))
        say(c("1", "  +" + "-" * 60))
    else:
        body = [rows[0]] + [r for r in gauges if r.startswith("До награды")] + rows[1:] + \
            ([tui.SEP] + [r for r in gauges if r.startswith("За неделю")]
             if week else [])
        head = title.upper()
        centre = " " * max(0, (cp.width - 5 - tui.vlen(head)) // 2)
        framed = tui.box([(tui.style(head, "accent", c=cp), centre, ""), tui.SEP] + body,
                         kind="double", c=cp)
        anim = tui.anim_name()                   # купленный эффект итога (K5) вместо typewriter
        if anim == "scan":
            tui.scan(framed, c=cp)
        elif anim == "rain":
            tui.rain(cp.width - 1, c=cp)         # без cp.anim — ничего, вывод как обычно
            for row in framed:
                say(row)
        else:
            say(framed[0])
            if anim == "glitch":
                tui.glitch(framed[1], c=cp)
            else:
                tui.typewriter(framed[1], c=cp)  # заголовок итога печатается (только rich+tty)
            for row in framed[2:]:
                say(row)
    if milestone:
        ok(story_fill(milestone, "  ", "     "))
    if milestone_pay:
        ok(f"  🔥 Серия {streak_after} дн.: +{milestone_pay} {cash}")


def _gauge(done: int, total: int, cp: tui.Caps) -> str:
    """Бар с пробелом после; в plain — пусто (число пишется рядом всегда)."""
    b = tui.bar(done, total, min(total, 14), cp)
    return b + " " if b else ""


def until(expires: str, today) -> str:
    """Срок в днях, не в часах: до конца дня / до завтра / до послезавтра."""
    from datetime import date
    days = (date.fromisoformat(expires) - today).days
    return {0: "до конца дня", 1: "до завтра", 2: "до послезавтра"}.get(
        days, f"ещё {days} {plural(days, 'день', 'дня', 'дней')}")


def comeback(banner: str, voice: str) -> None:
    """Баннер выгодного рана: только радость возвращения — без серии (и лучшей тоже), без
    слов о потерях и без числа пропущенных дней (М7)."""
    say()
    ok(story_fill(banner, "  ", "  "))
    if voice:
        say(story_fill(voice, "  ", "     "))


def tomorrow(text: str, note: Optional[str] = None) -> None:
    """note — сколько старых дел войдёт в завтрашний ран (session.tomorrow_note), не весь хвост."""
    say(story_fill(f"⏭ Завтра: {text}"))
    if note:
        say(c("2", story_fill(f"({note})", "   ", "   ")))


def answer_guide() -> str:
    """Памятка «как сдавать ответ» — нейтральный текст движка, одинаковый во всех темах."""
    return """Как сдавать ответ:
  ans ОТВЕТ       — сдать ответ текстом, например: ans /Users/ты/Documents
  ans $(pwd)      — подставить вывод команды прямо в ответ: $( ) выполнит её
  ans $PWD        — то же через переменную: в $PWD лежит путь текущей папки
  pwd | pbcopy    — скопировать вывод в буфер, потом «ans » и Cmd+V
  Мышью: выдели вывод (в iTerm2 он копируется сам), затем «ans » и Cmd+V
  В iTerm2 с Shell Integration Cmd+Shift+A выделяет вывод последней команды
  Задачи «сделай» сдавать не нужно — они проверяются сами."""


# Первая минута (П3.4): одна строка — как сдать, одна — как выбраться. Остальные способы
# сдачи приходят по мере надобности — в уроках и «можно и так» следующих задач.
INTRO_KEYS = ("Ответ сдают так: ans ОТВЕТ. Команда повисла и молчит — Ctrl+C.\n"
              "Застрял — набери hint, это нормально: на тренировке подсказки бесплатны и на "
              "прогресс не влияют.\n"
              "Ещё: reset — собрать задачу заново · skip — отложить на завтра · giveup — "
              "сдаться и посмотреть разбор.\n"
              "Клавиши терминала — стрелки, история команд, прокрутка — в задаче набери keys.\n"
              "Решил — песочница остаётся: пробуй другие способы. Дальше — next. Когда ран "
              "окончен, игра предложит ещё урок — more. Что-то не так — bug, игра спросит текст.\n"
              # FB5: общее правило про ./termit СЛОВО — один раз и рано
              "Команды вида ./termit слово (./termit shop, ./termit home …) — команды самой "
              "игры: их набирают не в задаче, а в обычном терминале — после рана или вместо "
              "него. Список всех — ./termit help.")
# FB5 (владелец 19.10): запас у новичка большой, поэтому таймер дела идёт сразу, с открытия
# задания (было: с первой команды — и ответ первой же командой давал «решено за 0:00»).
# Первая встреча — без таймера.
TIMER_RUNS = "Таймер уже идёт — с открытия задания. Запас большой, но не зевай."
TIMER_OFF = "Первая встреча — без таймера: не торопись."
# FB5 (2): с самого начала — где игрок вообще находится. Подробности (что такое оболочка,
# команда, как поставить iTerm2) — в первом уроке meet_terminal и в README.
INTRO_SHELL = ("Ты в терминале — окне, где набирают команды. Команды понимает оболочка — "
               "программа zsh, она уже стоит в каждом Mac. Удобнее играть в iTerm2 (бесплатно, iterm2.com), "
               "но подойдёт и встроенный Терминал. Подробно — в первом уроке.")
# FB3 (7): песочница и её дом — заранее, до первой задачи: откуда длинный путь у pwd и куда
# ведёт ~. Нейтральный текст движка, одинаковый во всех темах.
INTRO_SANDBOX = ("Каждое задание идёт в песочнице — отдельной папке внутри папки игры. Твои "
                 "настоящие файлы игра не трогает: всё, что ты создашь или сотрёшь, живёт только "
                 "там. Поэтому pwd показывает длинный путь (адрес папки: имена папок через косую /) — "
                 "от корня диска (самой верхней папки /) до песочницы "
                 "(…/.sandbox/…). У песочницы и свой дом: ~, cd без пути и cd ~ ведут в него, а не в твою "
                 "настоящую домашнюю папку (/Users/имя). Внутри песочницы дом — папка "
                 ".termit/home.")
# FB1: «норма ли набирать hint» — на первой встрече с задачей карточка отвечает прямо
HINT_OK = "Не знаешь, с чего начать, — набери hint, это нормально: сейчас подсказка бесплатна."

# FB2 (1)+(3): клавиши терминала — порциями по первым задачам «Основ» (на первой встрече, на
# тренировке, до двух сочетаний за раз), целиком — шпаргалкой keys. Нажатия игра не проверяет:
# это советы, не зачёт. Сочетания проверены в zsh игры (emacs-раскладка, привязки — в
# termit_app/shell/.zshrc) и по стандартным клавишам iTerm2 (DefaultGlobalKeyMap).
KEY_TIPS = {
    "where_am_i": "⌨ Опечатка — не стирай всё: стрелки ← → двигают курсор по строке. "
                  "↑ — вернуть прошлую команду. Все клавиши — набери keys.",
    "climb_down": "⌨ Ctrl+A — прыжок в начало строки (A — первая буква), Ctrl+E — в конец "
                  "(End). Все клавиши — keys.",
    "back_up": "⌨ Ctrl+R (R — Reverse, поиск назад) и кусок команды — найти её в истории, "
               "Enter — выполнить. Ctrl+G — передумал (в старых терминалах это был звонок: «стоп»). "
               "Все клавиши — keys.",
    "home_tilde": "⌨ Ctrl+U — стереть всю строку (запоминай как Undo), Ctrl+W — слово "
                  "слева от курсора (W — Word). Все клавиши — keys.",
    "hidden_cache": "⌨ Вывод уехал вверх — прокрути колесом мыши или двумя пальцами по "
                    "трекпаду. Cmd+K — очистить экран. Все клавиши — keys.",
    "mkdir_p": "⌨ Option+← → — прыжок через слово. Вывод длиннее экрана — допиши | less: "
               "пробел листает, q — выход. Все клавиши — keys.",
}

KEYS_SHEET = """\
Клавиши терминала. Они же работают в Claude Code и почти везде, где есть
строка ввода.

Строка ввода
  ← →             курсор по строке: исправить опечатку, не стирая всё
  Option+← →      прыжок через слово
  Ctrl+A, Ctrl+E  в начало строки (A — первая буква), в конец (E — End)
  Ctrl+W          стереть слово слева (W — Word)
  Ctrl+U          стереть всю строку (запоминай как Undo)
  Ctrl+K          стереть до конца (K — Kill, вырезать: Ctrl+Y вернёт)
  Tab             дописать имя папки или файла (дважды — показать варианты)
  Ctrl+C          бросить строку или остановить повисшую команду (Cancel)

История
  ↑ ↓             прошлые команды: вернуть, поправить, Enter
  Ctrl+R          поиск по истории (R — Reverse, назад): набери кусок
                  команды; ещё Ctrl+R — совпадение постарше; Enter —
                  выполнить, ← → — сначала поправить, Ctrl+G — отмена
                  (G в ASCII — звонок «стоп»)
  !!              повторить последнюю команду («bang bang»); history — все
                  с номерами

Экран
  колесо мыши или два пальца по трекпаду — прокрутить вывод вверх и обратно
  iTerm2: Cmd+↑ ↓ — по строке, Shift+fn+↑ ↓ — по странице,
          Cmd+fn+← → — в самое начало и в конец,
          Cmd+Shift+↑ — к прошлой команде (если включена интеграция iTerm2)
  Cmd+K или clear (Ctrl+L) — очистить экран; L — «новый лист» у принтеров
  длинный вывод — команда | less: пробел — дальше, b — назад, /слово — поиск,
                  q — выйти (подробно — в «Инструментах»)

Откуда буквы
  Из редактора Emacs (1976) и терминалов 70–80-х, где стрелок часто не
  было. Bash и zsh взяли раскладку Emacs, а macOS понимает Ctrl+A, E, K
  почти в любом поле ввода — потому и живо до сих пор.
  Ctrl+B/F        Back/Forward — то же, что ← →
  Ctrl+P/N        Previous/Next — то же, что ↑ ↓
  Option+B/F      то же по словам (вне игры — если Option работает как Esc+)
  Ctrl+D          Done, ввод окончен (EOT): выход из python3, sqlite3, psql

Меню
  В игре выбор делается словом или числом и Enter — стрелками ходить не нужно.
  В less и man стрелки ↑ ↓ листают текст по строке.

Команды игры
  task            задание снова (экран забит — сначала clear, потом task)
  lesson          мини-урок к заданию снова
  hint            подсказка;  skip — отложить;  quit — выйти
  bug             замечание: игра спросит текст — пиши как есть, любые символы
  next            после решения — дальше; до того пробуй другие способы
  more            после итога рана — ещё урок (новая команда)
  ext             копилка расширений файлов: что значит хвост после точки
  book [слово]    книга выученных команд (с поиском)

Перед глазами
  Доска в убежище держит нужное из этой шпаргалки строкой над приглашением
  в каждой задаче: ./termit home board (набирать после рана, не в задаче)"""


def keys_sheet() -> str:
    """Шпаргалка клавиш: keys в задаче и ./termit keys."""
    return KEYS_SHEET


# FB5 (8): карточки доски убежища — строка над приглашением в каждой задаче (hideout.board_*).
# Это короткие выжимки разделов KEYS_SHEET, а не новые формулировки: охрана в test_board
# проверяет, что каждая клавиша карточки есть в шпаргалке. Одна карточка — одна строка
# не шире BOARD_WIDTH клеток экрана; постоянные — не шире BOARD_CARD_WIDTH (в ./termit home
# board они стоят с отступом 4). game — бывшая напоминалка TASK_TIPS (FB3).
BOARD_WIDTH = 78
BOARD_CARD_WIDTH = 74
BOARD_CARDS = {
    "keys-line": "⌨ Ctrl+A начало · E End · W Word · U Undo · K Kill · Option+←→ слово · Tab",
    "keys-history": "⌨ ↑↓ прошлые команды · Ctrl+R Reverse — поиск по истории · !! повторить",
    "keys-screen": "⌨ Cmd+↑↓ прокрутка · Cmd+K или clear (Ctrl+L — «новый лист») очистить",
    "game": "task задание · hint подсказка · book выученное · keys клавиши · skip · bug",
}
ROTATE_SHEET = "💡 "            # совет дня из шпаргалки
ROTATE_BOOK = "📖 "             # совет дня из книги выученного


def sheet_tips() -> list:
    """Советы дня из KEYS_SHEET: строки «клавиша  пояснение» (с продолжениями) — как
    «клавиша — пояснение»; не шире BOARD_WIDTH вместе со значком."""
    entries = []
    for line in KEYS_SHEET.splitlines():
        m = re.match(r"^  (\S.*?\S)\s{2,}(\S.*)$", line)
        if m:
            entries.append([m.group(1), m.group(2)])
        elif entries and entries[-1] and line.startswith(" " * 10) and line.strip():
            entries[-1][1] += " " + line.strip()
        else:
            entries.append(None)            # другой абзац: продолжения не цепляются
    tips = [f"{ROTATE_SHEET}{key} — {' '.join(text.split())}"
            for key, text in filter(None, entries)]
    return [t for t in tips if tui.vlen(t) <= BOARD_WIDTH]


def extension_notes(lines) -> None:
    """FB3: «📎 В копилку расширений: …» под карточкой задачи — тускло, переносом по ширине."""
    for line in lines:
        say(c("2", textwrap.fill(line, 78, initial_indent="   ", subsequent_indent="      ",
                                 break_long_words=False, break_on_hyphens=False)))


def show_intro(text: str, guide: bool = False) -> None:
    """Вступление темы и две строки управления — при первом ране; guide — ещё и памятка
    «как сдавать ответ» (./termit intro). Вступление само говорит, что такое ./termit
    СЛОВО, — без строк первой встречи."""
    with glossary_off():
        _show_intro(text, guide)


def _show_intro(text: str, guide: bool) -> None:
    say()
    cp = _framed()
    if cp.level == "plain":
        say(c("1", "  TermitRun — тренажёр терминала"))
    else:               # заголовок-плашка; в rich+tty печатается по буквам (≤ 0,6 с)
        tui.typewriter("  " + tui.label("TermitRun — тренажёр терминала", cp), c=cp)
        say(tui.rule(cp, indent="  "))
    for para in text.split("\n\n"):
        say()
        say(c("3", textwrap.fill(" ".join(para.split()), 78, initial_indent="  ",
                                 subsequent_indent="  ", break_long_words=False,
                                 break_on_hyphens=False)))
    say()
    say(c("3", textwrap.fill(INTRO_SHELL, 78, initial_indent="  ", subsequent_indent="  ",
                             break_long_words=False, break_on_hyphens=False)))
    say()
    for line in INTRO_SANDBOX.split("\n"):
        say(c("3", textwrap.fill(line, 78, initial_indent="  ", subsequent_indent="  ",
                                 break_long_words=False, break_on_hyphens=False)))
    say()
    if cp.level != "plain":
        say(tui.rule(cp, indent="  "))
    for line in INTRO_KEYS.split("\n"):
        say(c("36", textwrap.fill(line, 78, initial_indent="  ", subsequent_indent="    ",
                                  break_long_words=False, break_on_hyphens=False)))
    if guide:
        say()
        say(c("36", answer_guide()))


def rank_up(rank: str) -> None:
    say()
    ok(f"🎖 Новое звание: {rank}!")


def boss_clue(lines, new_line: str = None) -> None:
    """Улика стража — сразу под строкой «взломан», при первой победе."""
    say()
    for line in lines:
        say(c("36", story_fill(line, "   ", "   ")))
    if new_line:
        say(c("1", story_fill(new_line, "   ", "   ")))


def gift(line, names_line: str) -> None:
    """Подарок: реплика дарителя (если есть в теме) и строка «🎁 вещи — ./termit home»."""
    say()
    if line:
        say(story_fill(line, "   ", "   "))
    ok(story_fill(names_line, "", "   "))


def boss_down(task, opened) -> None:
    ok(theme.msg("boss_down", title=theme.title(task)))
    for tr in opened:
        say("   " + theme.msg("opened", place=theme.place(tr.key)))
