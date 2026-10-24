"""Вызывается из zsh песочницы: python3 -m termit_app.hook <команда> [аргументы]."""
import json
import os
import re
import socket
import sys
from pathlib import Path

from termit_app import book as book_mod
from termit_app import (coach, edition, extensions, judge, layout, loot, progress, sandbox, shop,
                        story, syserrors, theme, tui, ui)
from termit_app.tasks import registry
from termit_app.tasks.base import AnswerTask, Verdict, grep_recursive, grep_waits

EXIT_SHELL = 10
SERVICE = ("task", "hint", "ans", "reset", "giveup", "skip", "quit", "bug", "loot", "memory", "ask",
           "keys", "ext", "book", "lesson", "help")


QUIT_HUB = "Назад в убежище."


def quit_text() -> str:
    """quit в задаче: в ране из убежища (TERMIT_HUB) — «назад в убежище» (спека 2.1)."""
    return QUIT_HUB if os.environ.get("TERMIT_HUB") else "До встречи."


def _load(box):
    data = sandbox.read_task_json(box)
    return registry.get(data["id"]), data["state"]


def _hidden(box) -> bool:
    """Секреты задачи (ответ) у родителя: проверка и подсказки — через судью."""
    try:
        return bool(sandbox.read_task_json(box).get("hidden"))
    except (OSError, ValueError, AttributeError):
        return False


NO_JUDGE = ("Проверяющий тренажёра не отвечает. Набери quit — задача начнётся заново "
            "в следующий раз; прогресс не пострадает.")


def _ask_judge(box, op: str, **extra):
    """Ответ судьи (dict) или None — тогда хук уже сказал, что проверить нельзя."""
    reply = judge.ask(box, dict(extra, op=op))
    if reply is None or "error" in reply:
        ui.warn(NO_JUDGE)
        return None
    return reply


def _boss_progress(box, task, ctx, marks=None):
    """Шаги стража, когда что-то сдвинулось. marks — от судьи (скрытый страж: его проверка
    смотрит секреты родителя), иначе — Task.progress здесь же."""
    if marks is None:
        marks = task.progress(ctx)
    if marks is None:
        return
    key = "".join("1" if m else "0" for m in marks)
    f = Path(box) / ".termit" / "boss"
    if f.exists() and f.read_text() == key:
        return
    f.write_text(key)
    ui.say(f"⚔ {theme.title(task)}: {sum(marks)} из {len(marks)}")
    for m, step in zip(marks, task.steps_for(ctx.state)):
        ui.say(f"   {'✓' if m else '·'} {step}")


PARTS_BASE = "parts0"       # отметки частей на старте: сделанное до игрока не в счёт
PARTS_SHOWN = 3             # сколько несделанных частей назвать, остальное — «…»


def _part_marks(task, ctx):
    """(названия, отметки) частей обычной задачи или None (FB5 п. 68)."""
    labels = task.parts_for(ctx.state)
    if not labels or task.boss:
        return None
    marks = task.progress(ctx)
    if not marks or len(marks) != len(labels):
        return None
    return labels, [bool(m) for m in marks]


def _parts_baseline(box) -> None:
    """Первое приглашение: что из частей уже выполнено раскладкой (оригинал на месте) — это
    не заслуга игрока, в «сделано k из n» не считается."""
    try:
        task, state = _load(box)
        if _hidden(box):
            return
        got = _part_marks(task, sandbox.make_ctx(box, state))
    except (KeyError, OSError, ValueError):
        return
    if got:
        sandbox.write_box_file(box, ".termit/" + PARTS_BASE,
                               "".join("1" if m else "0" for m in got[1]))


def _part_progress(box, task, ctx) -> None:
    """Владелец 21.10 (open_gui): сделал половину — игра молчала. Задача с частями говорит,
    сколько сделано и что осталось; одно и то же сообщение — один раз (_say_once)."""
    got = _part_marks(task, ctx)
    if not got:
        return
    labels, marks = got
    base = sandbox._read(box, PARTS_BASE) or ""
    todo = [i for i in range(len(labels)) if base[i:i + 1] != "1"]
    done = [i for i in todo if marks[i]]
    if not done or len(done) == len(todo):
        return
    left = [labels[i] for i in todo if not marks[i]]
    more = "…" if len(left) > PARTS_SHOWN else ""
    _say_once(f"Сделано {len(done)} из {len(todo)}: ✓ "
              + ", ".join(labels[i] for i in done)
              + " · осталось: " + ", ".join(left[:PARTS_SHOWN]) + more, box)


# Команды, которые без файла ждут ввода с клавиатуры: игроку кажется, что всё зависло
WAITERS = ("cat", "sort", "uniq", "wc", "head", "tail", "tr")
_SUBST_CAT = re.compile(r"\s*cat\s+\"?\$\(.*\)\"?\s*")


def _waiting(line: str):
    """Команда, что ждала ввода с клавиатуры: голые cat/sort/… (одни флаги), grep с одним
    шаблоном и без файла, или cat, которому досталась только подстановка $( ). Вход по
    конвейеру или из файла — не ждёт. Возвращает (имя, через подстановку) или None."""
    if _SUBST_CAT.fullmatch(line):
        return "cat", True
    if "|" in line or "<" in line or ";" in line or "&" in line:
        return None
    words = line.split()
    if not words:
        return None
    args = [w for w in words[1:] if not w.startswith("-")]
    if words[0] in WAITERS and not args:
        return words[0], False
    if words[0] == "grep" and grep_waits(words[1:]):        # тот же разбор, что у совета N3
        return "grep", False
    return None


def _recursive(flags) -> bool:
    """grep -r/-R (в любой связке ключей) без пути ищет в «.» и stdin не ждёт (N1)."""
    return grep_recursive(flags)


def _interrupted(box, rc, cmds) -> None:
    """Ctrl+C (код 130) прервал команду, которая ждала ввода, — объяснить, что случилось.
    Только если эта команда и правда запускалась с прошлого приглашения (I4 ревью C1b):
    Ctrl+C на пустой строке после cat note.txt — не повод для разбора."""
    seen = sandbox.counter(box, "seen_cmds")
    sandbox.write_box_file(box, ".termit/seen_cmds", str(len(cmds)))
    if str(rc) != "130" or len(cmds) <= seen:
        return
    hit = _waiting(cmds[-1].line)
    if hit is None:
        return
    cmd, subst = hit
    if subst:
        # по коду 130 не различить «подстановка пуста» и «подстановка долго работала» (N2)
        _say_once("Ctrl+C — верно. Либо подстановка $( ) ничего не нашла и cat остался без "
                  "файла, ждал ввода с клавиатуры, либо она просто долго работала и Ctrl+C её "
                  "прервал. Проверь подстановку отдельно — запусти её без обёртки.", box)
        return
    _say_once(f"Ctrl+C — верно. {cmd} без файла ждёт ввода с клавиатуры — поэтому казалось, "
              "что всё зависло. Ctrl+C прерывает любую такую команду.", box)


def _say_once(text: str, box) -> None:
    """Сообщение проверки — один раз, пока оно не изменилось: не после каждой команды."""
    if sandbox._read(box, "lastmsg") == text:
        return
    sandbox.write_box_file(box, ".termit/lastmsg", text)
    ui.say(text)


def precmd(box, rc, pwd) -> int:
    sandbox.write_pwd(box, pwd)
    if sandbox.result(box):
        return EXIT_SHELL
    cmds = sandbox.read_cmds(box)
    if not cmds:
        _parts_baseline(box)
        return 0          # первое приглашение — владелец ещё ничего не делал
    fresh = len(cmds) > sandbox.counter(box, "seen_cmds")     # не пустой Enter после команды
    _interrupted(box, rc, cmds)
    if fresh:             # FB12 (N6): системная ошибка впервые — перевод одной строкой
        note = syserrors.explain_once(box, rc, pwd, cmds[-1].line)
        if note:
            ui.say(note)
        found = story.auto_claim(box, cmds[-1].line, pwd)
        if found:               # владелец 21.10: прочитал осколок — он сохранён
            ui.ok(story.found_message(found) + " — " + AUTO_CLAIMED)
    task, state = _load(box)
    if not sandbox.inside(Path(pwd), box):
        ui.warn(f"ты вне песочницы: {pwd} — вернуться: cd $TERMIT_BOX")
    ctx = sandbox.make_ctx(box, state)
    if _hidden(box):            # ответа в песочнице нет: решает судья у родителя
        reply = _ask_judge(box, "check")
        if reply is None:
            return 0
        if "stale" in reply:
            return _stale(box, task, KeyError(reply["stale"]))
        marks = reply.get("marks")
        if task.boss and isinstance(marks, list) and len(marks) <= 16:
            try:
                _boss_progress(box, task, ctx, [bool(m) for m in marks])
            except KeyError as e:
                return _stale(box, task, e)
        verdict = Verdict(bool(reply.get("solved")), reply.get("message"))
    else:
        try:
            if task.boss:
                _boss_progress(box, task, ctx)
            verdict = task.check(ctx)
        except KeyError as e:
            # код задачи сменился, пока zsh открыт: в task.json старые ключи state
            return _stale(box, task, e)
    if verdict.solved:
        sandbox.set_result(box, "solved")
        ui.ok("✓ Готово!")
        return EXIT_SHELL
    if ctx.answer is not None:
        sandbox.clear_answer(box)
        if not task.takes_answer(state):
            # «сделай»: сдавать нечего — не «Не то», не «✗» и не промах (ревью P2, M4)
            ui.say(verdict.message or task.stray_answer)
            return 0
        wrong = sandbox.bump(box, "wrong")
        ui.bad("✗ " + (verdict.message or AnswerTask.fallback))
        if wrong >= 2 and sandbox.counter(box, "hints") == 0:
            if _mode(box) == "job":
                ui.say(f"   Застрял? hint — {theme.word('soft_label')} за {theme.word('money')}, "
                       "giveup — разбор бесплатный.")
            else:
                ui.say("   Застрял? Набери hint — подскажу.")
    elif verdict.message:
        _say_once(verdict.message, box)
    elif not task.boss and not _hidden(box):
        _part_progress(box, task, ctx)
    if fresh:               # FB13: подсказчик привычек — не чаще совета за задачу
        tip = coach.advise(box, cmds, SERVICE)
        if tip:
            ui.say(ui.c("2", tip))
    return 0


def _stale(box, task, e: BaseException) -> int:
    """KeyError по state: чаще всего task.json от старой версии кода (обновились посреди рана),
    но может быть и настоящая ошибка задачи. Игроку — reset и bug; в .termit/feedback — одна
    запись на песочницу, чтобы ошибку увидел и разработчик (родитель переносит её в отзывы)."""
    ui.warn("Задание обновилось, пока ты в нём. Набери reset — соберу заново. "
            "Не помогло — набери bug и опиши, что случилось, разберёмся.")
    if sandbox.bump(box, "stale") == 1:
        try:
            with open(Path(box) / ".termit" / "feedback", "a", encoding="utf-8") as f:
                f.write(f"[авто] KeyError {e!r} в задаче {task.id}\n")
        except OSError:
            pass
    return 0


def cmd_task(box) -> int:
    task, state = _load(box)
    try:
        text = theme.task_text(task, state)
        steps = task.steps_for(state)
    except KeyError as e:
        reply = judge.ask(box, {"op": "task"}) if _hidden(box) else None
        if not reply or "text" not in reply:
            return _stale(box, task, e)
        text, steps = str(reply["text"]), [str(x) for x in reply.get("steps") or ()]
    # задание снова перед глазами: заметная шапка, текст жирным, как в карточке
    ui.say()
    ui.say(ui.c("1;36", f"📋 Задание · {theme.title(task)}"))
    ui.say(ui.c("1", text))
    for i, step in enumerate(steps, 1):
        ui.say(ui.c("1", f"   {i}. {step}"))
    ui.say(ui.c("2", TASK_AGAIN_TIP))
    return 0


TASK_AGAIN_TIP = ("   Экран забит — clear (или Ctrl+L), потом снова task: задание будет наверху. "
                  "Урок к заданию — lesson.")
AUTO_CLAIMED = "осколок сохранён. Перечитать в убежище: memory"
NO_LESSON = "У этого задания нет мини-урока. Застрял — hint, выученное — book."


def cmd_lesson(box) -> int:
    """Владелец 19.10: «task выводит задание, но не мини-урок — как урок вывести?» Тот же урок,
    что на карточке: урок персонажа или шпаргалка, плюс откуда имена команд (🔤)."""
    task, state = _load(box)
    cp = tui.caps()
    try:
        lesson = theme.lesson(task, state)
        scroll = task.scroll_for(state) or task.scroll
    except (KeyError, IndexError, ValueError) as e:
        return _stale(box, task, e)
    if not lesson and not scroll:
        ui.say(NO_LESSON)
        return 0
    ui.say()
    if lesson:
        ui.say(ui.c("1;36", f"📖 Урок · {theme.speaker(task)}"))
        ui.say(ui.code_spans(ui.lesson_block(lesson, tui.text_width(cp)), cp))
    else:
        ui.say(ui.c("1;36", "📖 Урок"))
        ui.say(ui._wrap(scroll, width=tui.text_width(cp)))
    ui.show_diagram(task.id, cp)
    ui.origin_notes(task.id, cp, tui.story_width(cp))
    return 0


def _mode(box) -> str:
    """Режим пишет родитель в .termit/mode; нет файла (старая песочница) — тренировка."""
    f = Path(box) / ".termit" / "mode"
    try:
        return "job" if f.read_text().strip() == "job" else "train"
    except OSError:
        return "train"


def cmd_hint(box) -> int:
    task, state = _load(box)
    hidden = _hidden(box)
    n = sandbox.counter(box, "hints")
    if hidden:
        # подсказка может назвать ответ — текст у судьи, и счёт выданных тоже у него (P2 А3):
        # файл .termit/hints — только для цены на экране, родитель его не слушает
        reply = _ask_judge(box, "hint", peek=True)
        if reply is None:
            return 0
        if "stale" in reply:
            return _stale(box, task, KeyError(reply["stale"]))
        n, total = int(reply.get("n") or 0), int(reply.get("total") or 0)
    else:
        try:
            hints = task.hints_for(state)
        except KeyError as e:
            return _stale(box, task, e)
        n, total = max(0, n), len(hints)
    if n >= total:
        ui.say("Подсказки кончились. giveup — покажу решение и разбор.")
        return 0

    def take():
        """Текст подсказки n: скрытой — у судьи (он и считает выдачу), открытой — из задачи."""
        if not hidden:
            return hints[n]
        got = _ask_judge(box, "hint")
        if got is not None and got.get("refused"):      # пол долга держит и судья (M2)
            ui.say(f"   Подсказки в долг — не ниже −{-progress.HINT_CREDIT_FLOOR}.")
        if got is None or "hint" not in got:
            return None
        return str(got["hint"])

    if _mode(box) == "train":
        text = take()
        if text is None:
            return 0
        sandbox.write_box_file(box, ".termit/hints", str(n + 1))
        ui.say(f"💡 Подсказка {n + 1} из {total} (бесплатно): {text}")
        return 0
    # дело: деньги списывает родитель после задачи, здесь — только проверка баланса
    free = _free_hint(box)
    price = 0 if free and n == 0 else progress.hint_price(n, task.track)
    # платные вопросы Сове тоже уже потрачены (родитель спишет их по счётчику моста)
    have = (sandbox.counter(box, "money") - progress.hint_cost(n, task.track, free_first=free)
            - sandbox.counter(box, "owl_paid") * progress.owl_price(task.track))
    if not progress.can_buy_hint(have, n, price):
        ui.say(ui.story_fill(theme.msg("no_money", cost=price, have=ui.balance(have))))
        # любая подсказка дела — в долг, но с полом: объяснить, почему эту не дали (K11)
        ui.say(f"   Подсказки в долг — не ниже −{-progress.HINT_CREDIT_FLOOR}.")
        return 0
    text = take()
    if text is None:
        return 0
    sandbox.write_box_file(box, ".termit/hints", str(n + 1))
    soft = theme.soft_names()
    name = soft[min(n, len(soft) - 1)]
    if price == 0:
        ui.say(f"💡 {name} (даром — {shop.name('cache')}, −1 ★): {text}")
        return 0
    debt = " в долг" if have < price else ""
    ui.say(f"💡 {name} (−{price} {theme.word('money')}{debt}, −1 ★): {text}")
    return 0


def _free_hint(box) -> bool:
    """Первая подсказка дела даром (модуль «кэш»): файл пишет родитель до запуска zsh."""
    try:
        return (Path(box) / ".termit" / "free_hint").read_text().strip() == "1"
    except OSError:
        return False


RESET_BUSY = "Сервер базы только что пересобран — подожди пару секунд и набери reset снова."
RESET_FAILED = "Сервер базы не поднялся заново ({why}). Набери quit — задача начнётся заново."


STOCK_RESTORED = "📦 Запас готовых окружений был изменён — вернул его как было."
STOCK_FAILED = ("Запас готовых окружений испорчен и не восстановился ({why}). Набери skip — "
                "задача начнётся заново в другой раз.")


def cmd_reset(box) -> int:
    task, _ = _load(box)
    if getattr(task, "stock", None):
        # .venv задачи клонируется из запаса: испорченный изнутри запас (pip install не в тот
        # venv) родитель сверяет с кэшем и кладёт заново — до rebuild (M7 ревью P1). Судьи
        # нет — как раньше, без сверки
        reply = judge.ask(box, {"op": "stock"})
        if isinstance(reply, dict) and "failed" in reply:
            ui.warn(STOCK_FAILED.format(why=str(reply["failed"])[:200]))
            return 1
        if isinstance(reply, dict) and reply.get("ok") == "restored":
            ui.say(STOCK_RESTORED)
    state = sandbox.rebuild(box, task)
    if isinstance(state, dict):         # новые PID процессов задачи — судье (P2 fix1 M1)
        from termit_app import launch
        launch.tell_judge(Path(box), sandbox.public_state(task, state))
    sandbox.write_box_file(box, ".termit/lastmsg", "")      # после reset — заново
    pg = isinstance(state, dict) and state.get("_engine") == "pg"
    if not pg and getattr(task, "needs_judge", False):
        # журнал учебного API (A5, часть 10) живёт у родителя: reset чистит и его. Без судьи
        # такую задачу не выдают (Task.missing — MSG_NO_JUDGE); если он всё же молчит —
        # песочница уже пересобрана, без отказа (M14 ревью Q1)
        judge.ask(box, {"op": "service_reset"})
    if pg:
        # сервер PostgreSQL задачи живёт у родителя: данные заново — его руками (часть 9б)
        reply = _ask_judge(box, "service_reset")
        if reply is None:
            return 1
        if "busy" in reply:
            ui.warn(RESET_BUSY)
            return 1
        if "failed" in reply:
            ui.warn(RESET_FAILED.format(why=str(reply["failed"])[:200]))
            return 1
    ui.say("🔄 Песочница пересобрана с теми же данными.")
    return 0


BUG_ASK = ("📝 Опиши проблему одной строкой и нажми Enter — запишу как есть, любые символы "
           "можно.\n   Пустой Enter или Ctrl+C — отмена, ничего не отправится.")


def cmd_bug(box, text: str) -> int:
    """Замечание бета-тестера: копится в .termit/feedback, родитель переносит в feedback.jsonl.
    Текст приходит из read -r оболочки (bug без слов) или из аргументов (bug текст)."""
    if not text.strip():
        ui.say(BUG_ASK)
        return 0
    with open(Path(box) / ".termit" / "feedback", "a", encoding="utf-8") as f:
        f.write(text.strip().replace("\n", " ") + "\n")
    ui.ok("📝 Записал, спасибо, бета-тестер!")
    if edition.ISSUES_URL:      # публичное издание: ссылку на карточку покажем после задачи
        ui.say("   Ссылку, чтобы отправить замечание разработчику, покажу, когда выйдешь из задачи.")
    return 0


def cmd_loot(box, arg: str) -> int:
    """loot CODE или loot PATH (второе имя — memory): сдать находку. Штрафа за промах нет."""
    if not arg.strip():
        ui.say(story.NO_ARG)
        return 0
    meta = story.claim(box, arg)
    if meta:
        ui.ok(story.found_message(meta))
    elif loot.claim(box, arg):          # путь к файлу хабара данных
        ui.ok(loot.looted_message())
    else:
        ui.say(story.EMPTY)
    return 0


ASK_TIMEOUT = 60
ASK_REPLY_CAP = 16384


def cmd_ask(box, question: str) -> int:
    """ask QUESTION: наводка Совы через мост родителя (unix-сокет в .termit). Моста нет —
    Сова спит, ничего не списано. Цены и лимиты считает мост, хук только передаёт."""
    if not question.strip():
        ui.say(f"ask QUESTION — {theme.word('owl')}: наводка, не ответ.")
        return 0
    path = str(Path(box) / ".termit" / "owl.sock")
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        c.settimeout(3)
        c.connect(path)
    except OSError:
        c.close()
        ui.say(theme.msg("owl_sleep"))
        return 0
    ui.say(theme.msg("owl_thinking"))
    data = b""
    try:
        c.sendall((json.dumps({"q": question.strip()}, ensure_ascii=False) + "\n").encode())
        c.settimeout(ASK_TIMEOUT)
        while b"\n" not in data and len(data) <= ASK_REPLY_CAP:
            chunk = c.recv(4096)
            if not chunk:
                break
            data += chunk
    except KeyboardInterrupt:
        ui.say("Вопрос снят.")
        return 0
    except OSError:
        data = b""
    finally:
        c.close()
    try:
        reply = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
        text = str(reply["text"])
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        ui.say(theme.msg("owl_silent"))
        return 0
    if isinstance(reply.get("paid"), int) and reply["paid"] > 0:
        sandbox.bump(box, "owl_paid")       # для проверки баланса подсказок (cmd_hint)
    ui.say(text)
    return 0


def cmd_end(box, outcome: str, message: str) -> int:
    sandbox.set_result(box, outcome)
    ui.say(message)
    return 0


# FB3 (3): песочница после решения (session._linger). Проверок нет, переход — командами.
LINGER_DONE = ("Задача уже засчитана — разбор выше. Пробуй свои способы; дальше — next, "
               "выйти — quit.")
LINGER_NO_MORE = "Ещё урок — слово new в убежище после рана. Сейчас дальше — next."
LINGER_SKIP = "Задача уже засчитана — идём дальше."
LINGER_NO_RESET = ("После решения reset здесь недоступен: задача встретится снова и соберётся "
                   "заново. Дальше — next.")
NOT_YET = ("next — после решения задачи, ещё урок — new в убежище. Сейчас: skip — "
           "отложить, quit — выйти.")


def _lingering(box) -> bool:
    return sandbox._read(box, "linger") is not None


def linger_cmd(box, cmd: str, args) -> int:
    """Команды в песочнице после решения. None — команда обычная, её разбирает main."""
    if cmd == "precmd":
        sandbox.write_pwd(box, args[1])
        return EXIT_SHELL if sandbox.result(box) else 0
    if cmd == "next":
        return cmd_end(box, "next", "Дальше.")
    if cmd == "more":           # ещё урок — слово new в убежище, не из песочницы
        ui.say(LINGER_NO_MORE)
        return 0
    if cmd in ("skip", "giveup"):
        return cmd_end(box, "next", LINGER_SKIP)
    if cmd in ("hint", "ans") or (cmd == "task" and _hidden(box)):     # судьи уже нет
        ui.say(LINGER_DONE)
        return 0
    if cmd == "reset":
        task, _ = _load(box)
        engine = sandbox.read_task_json(box).get("state", {}).get("_engine")
        if _hidden(box) or getattr(task, "stock", None) or engine == "pg":
            ui.say(LINGER_NO_RESET)
            return 0
        return cmd_reset(box)
    return None


MISSING = "служебная папка .termit удалена — набери quit, задача начнётся заново"


def no_task(box, cmd: str) -> int:
    """task.json пропал (например, rm -rf .*): не падаем, а подсказываем выход."""
    if cmd in ("quit", "giveup", "skip"):
        (Path(box) / ".termit").mkdir(parents=True, exist_ok=True)
        return cmd_end(box, "quit", quit_text())
    if cmd == "precmd" and sandbox.result(box):
        return EXIT_SHELL
    ui.warn(MISSING)
    return 0 if cmd == "precmd" else 1


def main(argv) -> int:
    box = Path(os.environ["TERMIT_BOX"])
    cmd, args = argv[0], argv[1:]
    theme.use()          # тема родителя приходит через TERMIT_THEME
    try:
        if cmd == "keys":       # FB2: шпаргалка клавиш — задачу не трогает; keys hacks — FB10
            ui.say(ui.keys_sheet(args))
            return 0
        if cmd == "layout":     # FB5 п. 40: «ды» вместо ls — подсказка про раскладку
            note = layout.hint(" ".join(args))
            if note:
                ui.say(note)
            return 0 if note else 1
        if cmd == "ext":        # FB3: копилка расширений — задачу не трогает
            ui.say(extensions.sheet(extensions.read_box(box)))
            return 0
        if cmd == "help":       # владелец 24.10: о задаче и все её команды — таймер не трогает
            try:
                task, state = _load(box)
            except Exception:                   # noqa: BLE001 — нет задачи: хватит списка
                task, state = None, None
            ui.say(ui.task_help(task, state))
            return 0
        if cmd == "book":       # FB3: книга выученных команд — задачу и таймер не трогает
            ui.say(book_mod.show(book_mod.read_box(box), " ".join(args)))
            return 0
        if not (box / ".termit" / "task.json").is_file():
            return no_task(box, cmd)
        if _lingering(box):
            done = linger_cmd(box, cmd, args)
            if done is not None:
                return done
        elif cmd in ("next", "more"):
            ui.say(NOT_YET)
            return 0
        if cmd == "precmd":
            return precmd(box, args[0], args[1])
        if cmd == "task":
            return cmd_task(box)
        if cmd == "lesson":
            return cmd_lesson(box)
        if cmd == "hint":
            return cmd_hint(box)
        if cmd == "ans":
            sandbox.write_answer(box, " ".join(args))
            return 0
        if cmd == "reset":
            return cmd_reset(box)
        if cmd in ("loot", "memory"):
            return cmd_loot(box, " ".join(args))
        if cmd == "ask":
            return cmd_ask(box, " ".join(args))
        if cmd == "bug":
            return cmd_bug(box, " ".join(args))
        if cmd == "bug_ask":        # FB3 (1): вопрос перед вводом строки в оболочке
            ui.say(BUG_ASK)
            return 0
        if cmd == "giveup":
            return cmd_end(box, "giveup", "Сдаёшься — покажу решение.")
        if cmd == "skip":
            return cmd_end(box, "skip", "Отложено.")
        if cmd == "quit":
            return cmd_end(box, "quit", quit_text())
        ui.bad(f"неизвестная команда тренажёра: {cmd}")
        return 1
    except Exception as e:   # хук не должен ронять оболочку владельца
        ui.bad(f"[тренажёр] внутренняя ошибка: {e!r}")
        return 0 if cmd == "precmd" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
