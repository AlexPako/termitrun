"""Ход рана: подбор поручений, запуск zsh, звёзды, прогресс, замечания бета-тестера."""
import dataclasses
import functools
import json
import random
import subprocess
import time
from dataclasses import dataclass, field as dfield
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from termit_app import book as book_mod
from termit_app import (contracts, cosmetics, edition, extensions, field, freezes, goal,
                        hideout, hook, implants, judge, lifehacks,
                        loot, master, music, owl, paths, progress, sandbox, shell_run, shop,
                        repute, sound, story, theme, ui, warehouse, weekly)
from termit_app.tasks import dbkit, registry
from termit_app.tasks.base import variant_index


@dataclass
class Options:
    no_sandbox: bool = False
    bare: bool = False
    no_gui: bool = False
    # пути по умолчанию берутся при создании Options, а не при импорте (P2 А1): подмена
    # paths.* после импорта (тесты, пробы) действует
    sandbox_root: Path = dfield(default_factory=lambda: paths.SANDBOX_ROOT)
    progress_path: Path = dfield(default_factory=lambda: paths.PROGRESS_FILE)
    feedback_path: Path = dfield(default_factory=lambda: paths.FEEDBACK_FILE)
    runner: Callable = shell_run.run
    ask: Callable = input
    today: Optional[date] = None
    practice: bool = False          # ./termit play ID — тренировка без денег; непобеждённый босс — дело
    real_home: Path = dfield(default_factory=Path.home)
    rehearsal: bool = False         # репетиция стража: тренировка, прогресс не записывается
    pay_mult: int = 1               # множитель оплаты звезды дела (выгодный ран — ×2)
    comeback_bonus: int = 0         # премия выгодного рана, если в нём что-то решено
    comeback: bool = False          # выгодный ран (М1): тренировка без таймера, за звезду ×2
    master: frozenset = frozenset()  # задачи круга мастера (М3): на время, без расписания
    owl_transport: Optional[Callable] = None    # транспорт Совы к Ollama (тесты подменяют)
    installer: Optional[Callable] = None        # установка утилиты; None — implants.brew_install
    wheels_getter: Optional[Callable] = None    # склад колёс (часть 10); None — pyenvs.get_wheels
    # FB3 (3): после решения — остаться в песочнице до next/more/quit (./termit ставит True;
    # тесты с подставным runner по умолчанию — прежний поток с Enter и [y/N])
    linger: bool = False


def _ask(opts: Options, prompt: str) -> str:
    """Вопрос родителя; Ctrl+D и Ctrl+C — как пустой ответ."""
    try:
        return opts.ask(prompt) or ""
    except EOFError:
        return ""
    except KeyboardInterrupt:
        print()
        return ""


def available(task, root=None) -> bool:
    """Задача выдаётся: программы на месте и ничего не нехватает (missing) — в корне
    песочниц root, без него — в корне текущего рана (sandbox.run_root, ревью B2 M5)."""
    return all(implants.which(n) for n in task.needs) and task.missing(root) is None


def _rooted(fn):
    """Публичный вход рана: на время вызова корень песочниц — opts.sandbox_root (по нему
    available() меряет длину пути сокета, а не по корню игры)."""
    @functools.wraps(fn)
    def wrapper(*args, **kw):
        opts = kw.get("opts") or next((a for a in args if isinstance(a, Options)), None)
        with sandbox.run_root(opts.sandbox_root if opts is not None else None):
            return fn(*args, **kw)
    return wrapper


after_done = registry.after_done        # пары: после близнеца и стража (общий фильтр выдачи)


def last_new(p: dict, track_key: str) -> str:
    """Когда место последний раз давало новое: самый поздний день первой встречи его задач
    (запись first_day). Старые записи без даты — «давно»; место без встреченных — "" ."""
    days = [str((p["tasks"].get(t.id) or {}).get("first_day") or " ")
            for t in registry.tasks_of(track_key) if progress.seen(p, t.id)]
    return max(days, default="")


def next_new(p: dict, limit: int) -> List[str]:
    """Следующие невстреченные поручения открытых мест — по одному из каждого места по кругу.
    Круг начинается с места, которое дольше всех не давало нового (П3.2): при одной новой
    в ран открытые места чередуются, свежее место не простаивает за соседним.
    Задача с невыполненным after не свежая: запертые пары не задерживают стража.
    Проваленный (встреченный) страж места не свежий — новое других мест идёт (П3.3)."""
    lines = []
    opened = registry.unlocked(p["bosses"])
    for tr in sorted(opened, key=lambda tr: last_new(p, tr.key)):     # sorted устойчив
        ts = registry.tasks_of(tr.key)
        fresh = [t.id for t in ts if not t.boss and available(t) and not progress.seen(p, t.id)
                 and after_done(p, t)]
        if not fresh:
            fresh = [t.id for t in ts if t.boss and not progress.seen(p, t.id)]
        if fresh:
            lines.append(fresh)
    out = []
    while len(out) < limit and any(lines):
        for line in lines:
            if line and len(out) < limit:
                out.append(line.pop(0))
    return out


REVIEWS_PER_RUN = 4         # столько старых дел берёт обычный ран (build_queue, tomorrow_note)
REVIEWS_SHORT = 2           # и короткий (./termit short)


def build_queue(p: dict, today: date, short: bool = False, rng=None) -> List[str]:
    rng = rng or random.Random()
    tasks = registry.all_tasks()
    # замок after — одно правило для всех путей, и для повторений по сроку тоже: пара,
    # решённая до стража в старом сохранении, ждёт замка, как в play ID и разминке
    reviews = [i for i in progress.due(p, today)
               if i in tasks and available(tasks[i]) and after_done(p, tasks[i])]
    # проваленный страж — вне лимита повторений: иначе долг старых дел (срок раньше)
    # вечно вытесняет его из рана, а новое в его месте не откроется, пока он не взломан
    guards = [i for i in reviews if tasks[i].boss and i not in p["bosses"]]
    rest = [i for i in reviews if i not in guards]
    rev = rest[:REVIEWS_SHORT if short else REVIEWS_PER_RUN]
    queue = guards + rev + next_new(p, progress.new_limit(p, today))
    rng.shuffle(queue)
    # сначала тренировки (новое), потом дела (повторения), схватка — в конце
    queue.sort(key=lambda i: (tasks[i].boss,
                              progress.mode_for(p, i, boss=tasks[i].boss) == "job"))
    return queue


# FB3 (2): команды, которые таймер не запускают — прочитать условие, шпаргалку, подсказку,
# заглянуть в копилку или книгу, спросить Сову или написать замечание. Работа над задачей (и ans) — запускает.
# FB5 (владелец 19.10): «сначала предупреждение, что сейчас пойдут боевые раны и нельзя вафлить»
COMBAT_WARNING = ("⚔ Дальше — боевые задания. Таймер стартует сразу, как откроется задание: "
                  "читай и делай, вафлить нельзя. Запас времени большой — успеешь.")
COMBAT_PROMPT = "Готов? Enter — в бой. "
BOSS_PAUSE = "\n   Enter — дальше "      # FB12 (B6): после первой победы над стражем


def _shown_cmd(box) -> Optional[str]:
    """Строка «Ты:» в разборе — последняя команда игрока. ans — служебная, но если задача решена
    ответом, показываем именно его: иначе «Ты: pwd» против эталона «ans $(pwd)» (17.10)."""
    lines = [c.line for c in sandbox.read_cmds(box) if c.line.split()[:1]
             and (c.line.split()[0] not in hook.SERVICE or c.line.split()[0] == "ans")]
    return lines[-1] if lines else None


def _user_cmds(box) -> List[str]:
    return [c.line for c in sandbox.read_cmds(box)
            if c.line.split()[:1] and c.line.split()[0] not in hook.SERVICE]


# Пределы замечаний bug (P2 А4, security В-Н2): изнутри не раздуть feedback.jsonl вне песочницы
BUG_MAX_LINES = 20          # замечаний за задачу
BUG_TEXT_CAP = 500          # символов в одном замечании
BUG_CMDS = 10               # последних команд при замечании
BUG_CMD_CAP = 300           # символов в одной команде
BUG_FILE_CAP = 5 * 1024 * 1024      # feedback.jsonl больше — новые записи не дописываются


def _clip_text(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[:cap - 1] + "…"


def _collect_feedback(box, task, seed, opts: Options) -> None:
    """seed — зерно родителя (не _seed из task.json: его пишут изнутри)."""
    lines = sandbox.read_feedback(box)[:BUG_MAX_LINES]      # симлинк, FIFO, гигант — мимо
    if not lines:
        return
    try:
        if Path(opts.feedback_path).stat().st_size >= BUG_FILE_CAP:
            return          # тихо: замечаний и так много, диск не забиваем
    except OSError:
        pass
    cmds = [_clip_text(c, BUG_CMD_CAP) for c in _user_cmds(box)[-BUG_CMDS:]]
    seed = seed if isinstance(seed, int) and not isinstance(seed, bool) else None
    with open(opts.feedback_path, "a", encoding="utf-8") as out:
        for line in lines:
            out.write(json.dumps({"when": datetime.now().isoformat(timespec="seconds"),
                                  "task": task.id, "seed": seed,
                                  "text": _clip_text(line, BUG_TEXT_CAP), "cmds": cmds},
                                 ensure_ascii=False) + "\n")
    # публичное издание: ссылка на готовую карточку GitHub (печатаем, ничего не открываем)
    for line in lines:
        send = edition.send_lines(_clip_text(line, BUG_TEXT_CAP), task.id)
        if send:
            ui.say()
            ui.say("📝 " + send[0])
            ui.say("   " + send[1])


def _clip_save() -> bytes:
    return subprocess.run(["pbpaste"], capture_output=True).stdout


def _clip_restore(data: bytes) -> None:
    if not data:      # pbpaste отдаёт только текст: картинку или файлы в буфере не затираем
        return
    subprocess.run(["pbcopy"], input=data)


def new_tally() -> dict:
    """Счёт рана для экрана «ран закрыт»."""
    return {"solved": 0, "mastered": 0, "warm": 0, "records": [], "earned": 0, "spent": 0,
            "milestone_pay": 0, "free_hint_used": False, "voice": False,
            "sounds": set()}


# Поддельный runner тестов (функция вместо zsh) пишет .termit/result сам — ему родитель верит,
# только если TRUST_TEST_RUNNER (ставит tests/__init__.py). Настоящий zsh (shell_run.run)
# проверяется всегда, флаг на него не действует.
TRUST_TEST_RUNNER = False
HINTS_FALLBACK = 3          # подсказок у задачи не посчитать (испорчено состояние) — не больше


RECHECK_TIMEOUT = 10.0      # секунд на повторную проверку: дольше — «не подтверждено»


def live_for_recheck(task, box, state: dict, referee) -> Optional[dict]:
    """Состояние родителя для повторной проверки. Метки отложенного запуска (PID процессов
    задачи) — из записей судьи: launch и reset сообщают ему PID, он сверяет их с процессами
    этой песочницы и командами из очереди (P2 fix1 M1). Не подтверждены — None. Без судьи —
    как раньше, из task.json (известное ограничение)."""
    if not sandbox._has_token(state):
        return dict(state)
    if referee is None:
        try:
            return sandbox.live_state(state, sandbox.read_task_json(box).get("state"))
        except (OSError, ValueError, KeyError, AttributeError):
            return None
    from termit_app.tasks import kit
    out = kit.replace_tokens(state, dict(getattr(referee, "pids", {}) or {}))
    return None if sandbox._has_token(out) else out


def _recheck_child(task, box, state: dict, real_home, use_sandbox: bool) -> bool:
    """check задачи — в отдельном процессе под sandbox-exec (shell_run.recheck_profile), с
    таймаутом; вердикт — строкой в трубу родителя (P2 fix1 I1). Родитель сам из песочницы
    ничего не читает: ни симлинк наружу, ни FIFO, ни гигант его не касаются."""
    import os
    import shutil
    import signal
    import sys
    from termit_app import recheck
    from termit_app.tasks import kit
    # -I: без cwd и папки скрипта в sys.path, без PYTHON* окружения и пользовательского site;
    # путь к коду игры — явно, первым; cwd — корень игры, не песочница (P2 fix2 C1: с -m и
    # cwd=box подложенный в песочницу termit_app/recheck.py или json.py исполнялся бы вместо)
    boot = ("import sys; sys.path.insert(0, sys.argv[1]); "
            "from termit_app import recheck; sys.exit(recheck.main(sys.argv[2:]))")
    cmd = [sys.executable, "-I", "-c", boot, str(paths.ROOT), str(box)]
    if use_sandbox and shutil.which("sandbox-exec"):
        cmd = ["sandbox-exec", "-p", shell_run.recheck_profile(Path(box), Path(real_home), task)] + cmd
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin", "LANG": "en_US.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1",
           "TERMIT_BOX": str(box), "HOME": str(kit.home(box)), "TERMIT_NO_SOUND": "1",
           "TERMIT_NO_OWL": "1", "TERMIT_NO_BREW": "1", "TERMIT_THEME": theme.current()}
    try:
        payload = json.dumps({"task": task.id, "state": state}, ensure_ascii=False)
        proc = subprocess.Popen(cmd, cwd=str(paths.ROOT), env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                start_new_session=True)
    except (OSError, TypeError, ValueError):
        return False
    try:
        out, _ = proc.communicate(payload.encode("utf-8"), timeout=RECHECK_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            proc.communicate(timeout=2)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
        return False
    except (OSError, ValueError):
        return False
    lines = out.decode("utf-8", errors="replace").strip().splitlines()
    return proc.returncode == 0 and lines[-1:] == [recheck.MARK + "1"]


def _recheck(task, box, state: dict, referee=None, opts: Optional[Options] = None) -> bool:
    """Повторная проверка родителем сразу после выхода из zsh, до reap: процессы задачи ещё
    живы (их проверка и смотрит), а «решено» в файле изнутри ничего не стоит."""
    live = live_for_recheck(task, box, state, referee)
    if live is None:
        return False
    opts = opts or Options()
    return _recheck_child(task, box, live, opts.real_home, not opts.no_sandbox)


def confirmed(task, box, state: dict, referee, hidden: bool, opts: Options):
    """Исход и число подсказок — не со слов песочницы (P2 А3, security В-Н1).
    «solved» засчитывается, только если с ним согласен судья (скрытый ответ: он помнит, что
    check сказал «решено») или повторная проверка родителя по своему состоянию. Подсказки
    скрытой задачи считает судья; открытой — файл хука, зажатый в [0, число подсказок]."""
    outcome = sandbox.result(box)
    raw = sandbox.counter(box, "hints")
    try:
        limit = len(task.hints_for(state))
    except Exception:       # noqa: BLE001
        limit = HINTS_FALLBACK
    trusted = TRUST_TEST_RUNNER and opts.runner is not shell_run.run
    judged = hidden and referee is not None and not trusted
    hints = min(referee.hints_served, limit) if judged else min(max(0, raw), limit)
    if outcome == "solved" and not trusted:
        ok = referee.solved if judged else _recheck(task, box, state, referee, opts)
        if not ok:
            ui.warn(theme.msg("result_unconfirmed"))
            outcome = None
    return outcome, hints


def _hint_gate(p: dict, track: str, free_first: bool, bridge_of):
    """can_hint(n) для судьи: можно ли выдать подсказку n на деле — с учётом уже взятых
    подсказок и платных вопросов Сове, тем же правилом пола долга, что у хука."""
    def can_hint(n: int) -> bool:
        bridge = bridge_of()
        owl = (getattr(bridge, "paid_asks", 0) or 0) * progress.owl_price(track)
        price = 0 if free_first and n == 0 else progress.hint_price(n, track)
        have = p["money"] - progress.hint_cost(n, track, free_first=free_first) - owl
        return progress.can_buy_hint(have, n, price)
    return can_hint


def _charge_hints(p: dict, hints: int, track: str, free_first: bool = False) -> int:
    """Списать купленный софт (до пола долга); вернуть, сколько списано на самом деле.
    free_first — первая подсказка даром (модуль «кэш», раз в ран)."""
    before = p["money"]
    progress.charge(p, progress.hint_cost(hints, track, free_first=free_first),
                    floor=progress.HINT_CREDIT_FLOOR)
    return before - p["money"]


def _charge_owl(p: dict, paid: int, track: str) -> int:
    """Списать вопросы Сове на деле; вернуть списанное."""
    if not paid:
        return 0
    before = p["money"]
    progress.charge(p, paid * progress.owl_price(track), floor=progress.HINT_CREDIT_FLOOR)
    return before - p["money"]


def _start_owl(task, state: dict, p: dict, mode: str, box, tally: dict, opts: Options,
               free_hint: bool):
    """Мост Совы на время задачи, если она не выключена и Ollama отвечает (проверка — раз
    за ран). Иначе None: Сова спит, игра идёт как обычно."""
    if (p.get("settings") or {}).get("owl") is False:
        return None
    if "owl_models" not in tally:
        tally["owl_models"] = owl.models(transport=opts.owl_transport)
    model = owl.pick_model(p, tally["owl_models"])
    if not model:
        return None
    budget = tally.setdefault("owl", {"left": progress.OWL_PER_RUN,
                                      "free": progress.OWL_FREE_TRAIN})
    try:
        return owl.start_bridge(box=box, task=task, state=state, mode=mode, boss=task.boss,
                                rehearsal=opts.rehearsal, budget=budget, money=p["money"],
                                transport=opts.owl_transport, model=model,
                                free_first=free_hint)
    except Exception:
        return None


def _say_alternative(task, state, variant, seed, outcome) -> None:
    """После разбора — «Можно и так»: одна из альтернатив варианта, по seed. Только когда
    разбор с решением (решено или сдался), не при skip. Вариант берём родительский."""
    if outcome == "skip":
        return
    if variant_index(state.get("_variant"), len(task.variants)) != variant:
        return      # task.json подменили изнутри: альтернатива и эталон были бы из разных вариантов
    try:
        alts = task.alternatives_for(dict(state, _variant=variant))
    except (KeyError, IndexError, ValueError, AttributeError):
        return
    if not alts:
        return
    alt = progress.clean_text(alts[random.Random(seed).randrange(len(alts))])   # В4
    ui.say(f"   Можно и так: {alt}")


def _note_review(task, state, variant, rec: dict, today: date) -> None:
    """Снимок разбора (эталон и «можно и так») для дневника. task.json подменили изнутри
    или испортили — снимка нет: в дневнике не должно оказаться чужого варианта."""
    if variant_index(state.get("_variant"), len(task.variants)) != variant:
        return
    try:
        st = dict(state, _variant=variant)
        progress.note_review(rec, variant, task.shown_solution(st),
                             task.alternatives_for(st), today)
    except (KeyError, IndexError, ValueError, AttributeError, TypeError):
        return


def _say_teaser(task, p: dict, outcome: str) -> None:
    """Под разбором пары — строка про утилиту, если её нет (не при skip). Отдельно от
    альтернатив: пара без них строку не теряет."""
    if outcome == "skip":
        return
    hint = implants.teaser(task, p)
    if hint:
        ui.say(ui.story_fill(hint, "   ", "   "))


def _service(line: str) -> bool:
    return bool(line.split()[:1]) and line.split()[0] in hook.SERVICE


def _last_answer(cmds) -> Optional[str]:
    """Последняя ans — та, что решила задачу: её подстановка (ans $(qsv …)) и дала ответ."""
    return next((line for line in reversed(cmds) if line.split()[:1] == ["ans"]), None)


def _ok_cmds(box, solved: bool = False) -> List[str]:
    """Команды игрока, которые отработали с кодом 0 (служебные — мимо), и — если задача
    решена — последняя ans: код самой ans о подстановке не говорит, но верный ответ из
    $(утилита …) доказывает, что утилита отработала (ревью P10)."""
    rows = sandbox.read_cmd_status(box)
    out = [line for line, ok in rows if ok and not _service(line)]
    last = _last_answer([line for line, _ in rows]) if solved else None
    return out + [last] if last else out


def _first_tools(box) -> List[str]:
    """Утилиты, которые могли отработать при этом решении, — для ручной базы близнеца
    (implants.hand_time): стоит у родителя и набрана в команде, у которой нет «command not
    found» (127) — код конвейера неважен (нет совпадений, SIGPIPE от head), кода может и не
    быть. Любая ans тоже в счёт: подстановка в ней запускалась. База «руками» строже,
    чем доказательство выигрыша (_ok_cmds)."""
    ran = [line for line, nums in sandbox.read_cmd_codes(box)
           if (not _service(line) or line.split()[0] == "ans")
           and (nums is None or "127" not in nums)]
    return [i for i in implants.tools_used(ran) if implants.installed(i)]


def reaction_kind(outcome: str, hints: int, stars: int, job: bool, record: bool):
    """Вид реплики персонажа (П3.6): похвала сообщает о мастерстве. Чисто — без подсказок и
    в таймер; с подсказкой (hard); без подсказок, но позже таймера (slow, P2 Б5 — своя
    реплика, без слов о подсказках); рекорд; сдался. skip — молчим."""
    if outcome == "giveup":
        return "giveup"
    if outcome != "solved":
        return None
    if hints:                       # рекорд с купленными подсказками — не мастерство (M4)
        return "hard"
    if record:
        return "record"
    if job and stars < 3:           # подсказок нет — значит, позже таймера
        return "slow"
    return "solved"


def pick_reaction(p: dict, track: str, kind, seed: int, remember: bool = True):
    """Реплика вида kind, которой не было среди недавних у этого трека; память —
    p["said"][track], список последних реплик (в старом прогрессе — одна строка), на вид
    не больше половины пула (remember=False — репетиция: прогресс она не трогает)."""
    if kind is None:
        return None
    said = p.get("said") if isinstance(p.get("said"), dict) else {}
    line = theme.reaction(track, kind, seed, avoid=said.get(track))
    if line and remember:
        recent = theme.remember_reaction(track, said.get(track), line)
        p["said"] = dict(said, **{track: recent})
    return line


def _review(task, state, outcome, *args, **kw) -> None:
    """Разбор по state из task.json песочницы: его могли испортить изнутри — тогда разбор
    короткий, а не трейсбек в родителе (прогресс к этому моменту уже сохранён)."""
    try:
        ui.review(task, state, outcome, *args, **kw)
    except (KeyError, IndexError, ValueError, AttributeError):
        ui.warn("Разбор не собрался: служебный task.json задачи кто-то покорёжил изнутри.")


@_rooted
def run_task(task, p: dict, n: int, total: int, opts: Options, tally: dict = None) -> str:
    tally = new_tally() if tally is None else tally
    today = opts.today or date.today()
    tr = registry.track(task.track)
    first = not progress.seen(p, task.id)
    in_master = task.id in opts.master and not first      # круг мастера — только освоенное
    practice = opts.practice or in_master
    mode = ("train" if opts.rehearsal or opts.comeback else
            progress.mode_for(p, task.id, boss=task.boss, practice=practice))
    seed = random.randrange(1_000_000)
    # вариант выбирает родитель: первая встреча — канонический 0 (с карточкой), повторы
    # ротируются. В прогресс уходит он, а не _variant из task.json (его можно испортить)
    # ротация — только по вариантам, которые эта песочница может дать (allowed_variants)
    allowed = task.allowed_variants(sandbox.sample_box(opts.sandbox_root))
    held = (master.held_variant(p, task.id, len(task.variants), allowed)
            if in_master else None)
    variant = (0 if first else held if held is not None else
               progress.pick_variant(p["tasks"].get(task.id), len(task.variants),
                                     random.Random(seed), allowed=allowed))
    shard = story.shard_for(task, p, seed)
    found = story.found_for(task, p, seed)      # найденный скрипт (часть 7, E20): разбор ниже
    # хабар данных: только в задаче, выбранной на этот ран (loot.plant_for_run), и один раз
    pd = None
    if tally.get("paydata_host") == task.id and not opts.rehearsal:
        tally["paydata_host"] = None
        pd = loot.plan(seed, progress.tier(task.track))
    try:
        # движок задачи БД (SQLite или учебный PostgreSQL) — до create и явно (часть 9б);
        # без песочницы PostgreSQL не запускается никогда
        engine = dbkit.choose_engine(task, p, pg_ok=False if opts.no_sandbox else None)
        box, state = sandbox.create(task, seed, root=opts.sandbox_root, defer_spawn=True,
                                    variant=variant, engine=engine)
        seed0 = state.get("_seed")      # зерно родителя — для замечаний bug (P2 А4)
        # задача могла заменить вариант (allowed_variant: режиму не хватает среды); state
        # здесь — из родителя, task.json ещё не читали, поэтому верим ему
        variant = variant_index(state.get("_variant"), len(task.variants))
        if in_master:       # вариант круга держится до решения: выход его не меняет (M3)
            master.hold_variant(p, task.id, variant)
            progress.save(opts.progress_path, p)
        # подложенные файлы рана (осколок, хабар и т.п.) — родителем, до запуска zsh
        sandbox.write_extras(box, story.extras_for(task, state, p, seed) +
                             (loot.extras(pd) if pd else []))
        # сервис родителя (учебный API): не поднялся — та же ветка, что сбой подготовки
        svc = task.service(box, state)
    except Exception as e:     # подготовка упала — сообщаем и идём к следующей задаче
        ui.bad(f"Задача «{theme.title(task)}» не собралась: {e}")
        try:
            sandbox.cleanup_stale(opts.sandbox_root)
        except Exception:
            pass
        return "broken"
    clip = None
    collected = False
    bridge = None
    referee = None
    try:
        # судья: ответ задачи живёт только у родителя (Н приёмки-1); не поднялся — полный
        # task.json, как раньше, чтобы задача всё равно решалась
        referee = judge.attach(box, task, state, service=svc)
        hidden = sandbox.public_state(task, state) != state
        # хук пишет только в песочницу: режим и баланс ему передаём файлами
        # запись — безопасной заменой, не по ссылке (В1 приёмки-1)
        sandbox.write_box_file(box, ".termit/mode", mode)
        sandbox.write_box_file(box, ".termit/money", str(p["money"]))
        # модуль «кэш»: первая подсказка дела раз в ран даром. Решает родитель — файл для
        # хука только подсказка цены, списание считается здесь по своему флагу
        free_hint = (mode == "job" and progress.module_on(p, "cache")
                     and not tally.get("free_hint_used"))
        if free_hint:
            sandbox.write_box_file(box, ".termit/free_hint", "1")
        par = progress.novice_par(task.track, task.par_for(state))
        par = progress.job_par(p, par) if mode == "job" else par
        clip = _clip_save() if task.uses_clipboard else None
        bridge = _start_owl(task, state, p, mode, box, tally, opts, free_hint)
        if referee is not None:
            referee.caged = not opts.no_sandbox     # без sandbox-exec процессы не «в клетке»
            if mode == "job":       # пол долга: судья отказывает так же, как хук (P2 fix1 M2)
                referee.can_hint = _hint_gate(p, task.track, free_hint, lambda: bridge)
        unsolved = not first and p["tasks"][task.id].get("solved", 0) == 0
        urgent = (mode == "job" and not opts.rehearsal
                  and contracts.urgent_task(p, today) == task.id)
        best_before = p["tasks"].get(task.id, {}).get("best")
        # FB3: копилка расширений — новые из этой песочницы; хуку — файлом для команды ext
        new_ext = [] if opts.rehearsal else extensions.collect(p, box)
        sandbox.write_box_file(box, extensions.BOX_FILE, extensions.box_text(p["extensions"]))
        sandbox.write_box_file(box, book_mod.BOX_FILE, book_mod.box_text(book_mod.sections(p)))
        if mode == "job" and not opts.rehearsal and not in_master and not tally.get("warned"):
            tally["warned"] = True          # раз за ран: дальше таймер идёт сразу
            ui.say("\n" + ui.story_fill(COMBAT_WARNING, "", "   "))
            _ask(opts, COMBAT_PROMPT)
        ui.task_card(n, total, tr, task, state, first, mode, unsolved=unsolved, par=par,
                     rehearsal=opts.rehearsal, urgent=urgent,
                     owl=bridge is not None and (not task.boss or opts.rehearsal),
                     master=_master_label(best_before) if in_master else None)
        # пара «до/после» без утилиты: одна строка на карточке — только в тренировке
        nudged = None if mode != "train" or opts.rehearsal else implants.nudge(task, p)
        if nudged:
            ui.say(ui.story_fill(nudged, "   ", "   "))
        if new_ext:
            ui.extension_notes(extensions.notes(new_ext))
            progress.save(opts.progress_path, p)
        if task.autorun:
            _ask(opts, "   Нажми Enter — сейчас откроется программа ")
        prompt, rprompt = hideout.build_prompt(p)
        env = shell_run.build_env(box, task.id, opts.real_home, bare=opts.bare, no_gui=opts.no_gui,
                                  autorun=task.autorun.format(**state) if task.autorun else None,
                                  prompt=prompt, rprompt=rprompt, task=task,
                                  db_engine=state.get(dbkit.ENGINE_KEY))
        if opts.linger:     # FB3 (3) + FB5 (8): строки над приглашением — с доски убежища
            hideout.board_tick(p)
            tips = hideout.board_lines(p)
            if tips:
                env["TERMIT_TIPS"] = "\n".join(tips)
        cwd = sandbox.start_dir(box)
        argv = shell_run.argv(box, opts.real_home, use_sandbox=not opts.no_sandbox, task=task)
        shell_run.mark_sandbox(env, argv)
        if svc is not None:
            try:
                svc.start()
            except Exception as e:      # поток не стартовал — задача не начинается
                ui.bad(f"Задача «{theme.title(task)}» не собралась: {e}")
                collected = True
                return "broken"
        t0 = time.monotonic()
        verdict = (None, 0)
        try:
            opts.runner(cwd, env, argv)
        finally:
            # время — с открытия задания (FB5, владелец 19.10: запас большой — стартуем сразу)
            elapsed = time.monotonic() - t0
            # итог и подсказки — родитель подтверждает сам (P2 А3), и до reap: процессы
            # задачи (оставить копию, не трогать приманки) и сервис проверке ещё нужны
            try:
                verdict = confirmed(task, box, state, referee, hidden, opts)
            except Exception:       # noqa: BLE001 — проверка не роняет уборку
                verdict = (None, 0)
            # сервис — до reap (часть 9б): сервер PostgreSQL гасится штатно и убирает свой
            # SysV; reap бьёт SIGKILL, и сегмент с семафорами утекли бы
            if svc is not None:
                try:
                    svc.stop()
                except Exception:   # noqa: BLE001 — уборка идёт дальше
                    pass
            # zsh закрыт: всё, что игрок оставил в фоне (nohup … &!), гасим сразу (В1)
            sandbox.reap(box)
        outcome, hints = verdict
        owl_paid = owl_asked = 0
        if bridge is not None:          # мост закрыт до подсчёта: счётчики окончательные
            bridge.stop()
            owl_paid = bridge.paid_asks if mode == "job" else 0
            owl_asked = bridge.task_asks
        if referee is not None:
            referee.stop()
        try:
            # открытая часть из песочницы (её могли поменять изнутри) + секреты родителя
            state = sandbox.merge_state(task, state, sandbox.read_task_json(box)["state"])
        except (OSError, ValueError, KeyError):
            # служебную папку .termit удалили изнутри — задача прервана, прогресс не трогаем
            collected = True
            ui.warn("Служебная папка .termit пропала — задачу бросаем, она вернётся в другой раз.")
            return "quit"
        collected = True
        _collect_feedback(box, task, seed0, opts)
        # находки — до разбора исхода: сданный осколок засчитан и при quit
        if story.collect(box, p, expect=shard.id if shard else None)["shard"]:
            progress.save(opts.progress_path, p)
        if loot.collect(box, p, pd, today):     # хабар — в тайник, сверка по своему плану
            progress.save(opts.progress_path, p)
        try:        # досье и фрагменты, открытые руками; сюжет не роняет задачу
            opened = story.mark_opened(p, _user_cmds(box))
        except Exception:
            opened = []
        if opened:
            progress.save(opts.progress_path, p)
            line = theme.story("dossier_ui").get("opened")
            if line:
                what = ", ".join(story.opened_name(p, st) for st in opened)
                ui.say(ui.story_fill(line.format(what=what), "", "   "))
        if free_hint and hints:
            tally["free_hint_used"] = True
        if outcome in (None, "quit"):
            if mode == "job" and (hints or owl_paid):   # купленное оплачивается и при выходе
                spent = _charge_hints(p, hints, task.track, free_first=free_hint)
                spent += _charge_owl(p, owl_paid, task.track)
                progress.save(opts.progress_path, p)
                tally["spent"] += spent
                ui.say(f"   {theme.word('soft_label')}: −{spent} {theme.word('money')}")
            ui.say(theme.msg("quit"))
            return "quit"
        if opts.rehearsal:      # репетиция: только разбор — ни расписания, ни звёзд, ни денег
            kind = reaction_kind(outcome, hints + owl_asked, 0, False, False)
            _review(task, state, outcome, (_user_cmds(box) or [None])[-1], elapsed, 0, None,
                    mode="train", rehearsal=True,
                    reaction=pick_reaction(p, task.track, kind, seed, remember=False))
            if opts.linger and outcome in LINGER_AFTER:
                tally["after"] = _linger(task, box, state, outcome, opts, tally,
                                         prompt, rprompt, seed0)
            return outcome
        prev_best = p["tasks"].get(task.id, {}).get("best")
        rank_before = registry.rank_level(p["bosses"])
        opened_before = {t.key for t in registry.unlocked(p["bosses"])}
        beaten_before = set(p["bosses"])
        solved = outcome == "solved"
        job = mode == "job"
        stars = (progress.stars_for(solved, hints + owl_paid, elapsed, par, first_time=False)
                 if job else 0)
        money_before = p["money"]
        ok_cmds = _ok_cmds(box, solved)
        progress.record(p, task.id, outcome, stars, elapsed, today, spell=task.spell,
                        boss=task.boss, mode=mode, practice=practice,
                        pay_per_star=progress.MONEY_PER_STAR * opts.pay_mult,
                        variant=variant, tools=_first_tools(box),
                        hints=hints + owl_asked)
        if opts.comeback and solved:    # выгодный ран: тренировка, но звезда платится ×2
            stars = contracts.comeback_stars(True, hints + owl_asked)
            p["money"] += stars * progress.MONEY_PER_STAR * opts.pay_mult
        master_pay = (master.pay(p, task, elapsed, prev_best, hints + owl_asked, today)
                      if in_master and solved else 0)
        if outcome in ("solved", "giveup"):     # разбор показан — вариант круга отпускаем
                                                # (и после обычного рана: Minor-1 перепроверки)
            master.release_variant(p, task.id)
        if outcome in ("solved", "giveup"):     # разбор с решением — снимок для дневника
            _note_review(task, state, variant, p["tasks"][task.id], today)
        earned = p["money"] - money_before
        spent = (_charge_hints(p, hints, task.track, free_first=free_hint)
                 + _charge_owl(p, owl_paid, task.track)) if job else 0
        progress.save(opts.progress_path, p)
        mine = _shown_cmd(box)
        shown = progress.shown_best(prev_best)      # FB12 B2: «было 99:55» — не рекорд
        record = (shown if solved and shown is not None and progress.BEST_MIN <= elapsed < shown
                  else None)
        if solved:
            tally["solved" if job else ("warm" if practice else "mastered")] += 1
        if record is not None:
            tally["records"].append((theme.title(task), ui.fmt_time(elapsed),
                                     ui.fmt_time(record)))
        tally["earned"] += earned
        tally["spent"] += spent
        after_fail = None
        if task.boss and job and not solved and contracts.rehearsal_price(p, task.id) == 0:
            after_fail = contracts.text("rehearse_free", id=task.id)
        kind = reaction_kind(outcome, hints + owl_asked, stars, job, record is not None)
        line = pick_reaction(p, task.track, kind, seed)
        if line:
            progress.save(opts.progress_path, p)
        _review(task, state, outcome, mine, elapsed, stars, record,
                mode=mode, earned=earned, spent=spent, after_fail=after_fail, reaction=line)
        if master_pay:      # круг мастера: рекорд побит без подсказок — пара монет
            ui.ok(ui.story_fill(master.text("record_paid", pay=master_pay,
                                            cash=theme.word("money")), "   ", "   "))
        _say_alternative(task, state, variant, seed, outcome)
        for fl in story.found_lines(box, found, _user_cmds(box)):    # без штрафа (E20)
            ui.say(ui.story_fill(fl, "   ", "   "))
        if not nudged:      # об утилите уже сказала карточка этого рана — одной строки хватит
            _say_teaser(task, p, outcome)
        gain = (implants.compare(task, p, elapsed, ok_cmds, hints + owl_asked)
                if solved else None)
        if gain:            # «до/после»: только настоящий выигрыш (implants.compare)
            progress.save(opts.progress_path, p)
            ui.ok(ui.story_fill(gain, "   ", "   "))
        if record is not None:      # купленная примочка — редкий звук на рекорде
            sound.play(p, "record", tally.setdefault("sounds", set()))
        said = story.voice(task, outcome, seed, p, tally.get("voice"))
        if said:            # редкий внутренний голос — после реплики персонажа
            tally["voice"] = True
            ui.voice(story.voice_name(task.track), said)
        if job:             # срочный заказ: премия при решении, skip оставляет до срока
            bonus = contracts.settle(p, task.id, outcome, stars, today)
            if bonus:
                tally["earned"] += bonus
                progress.save(opts.progress_path, p)
                ok_line = contracts.text("urgent_paid", bonus=bonus, cash=theme.word("money"))
                ui.ok(ui.story_fill(ok_line, "   ", "   "))
        if task.boss and solved:
            first_win = task.id in p["bosses"] and task.id not in beaten_before
            ui.boss_down(task, [t for t in registry.unlocked(p["bosses"])
                                if t.key not in opened_before], first=first_win)
            clue = story.clue(task.id)
            if first_win:       # звук — только если игрок его включил (примочка)
                sound.play(p, "boss_down", tally.setdefault("sounds", set()))
                _ask(opts, BOSS_PAUSE)      # FB12 (B6): пик — с паузой, улика не проскочит
            if clue and first_win:
                ui.boss_clue(clue, story.new_in_case(task.id))     # первая победа: улика
            if first_win and give_gifts(p, task.id):               # после улики — подарки
                progress.save(opts.progress_path, p)
        if solved:          # FB5 (8): первое решённое задание — доска; новые карточки — на неё
            gifted = give_gifts(p, "first_solve")
            news = hideout.board_news(p)
            for line in news:
                ui.say(ui.story_fill(line, "   ", "   "))
            if gifted or news:
                progress.save(opts.progress_path, p)
        rank_after = registry.rank_level(p["bosses"])
        if rank_after != rank_before:
            ui.rank_up(theme.rank_name(rank_after))
        if opts.linger and outcome in LINGER_AFTER:
            tally["board"] = hideout.board_lines(p, game=False)    # доска — и после решения
            tally["after"] = _linger(task, box, state, outcome, opts, tally,
                                     prompt, rprompt, seed0)
        return outcome
    finally:
        if bridge is not None:
            bridge.stop()
        if referee is not None:
            referee.stop()
        if svc is not None:             # и при Ctrl+C, и при любом сбое — до destroy
            try:
                svc.stop()
            except Exception:
                pass
        try:
            if not collected:
                _collect_feedback(box, task, seed0, opts)
        except Exception:
            pass
        try:
            if clip is not None:
                _clip_restore(clip)
        finally:
            sandbox.destroy(box)


# FB3 (3): после решения игрок остаётся в той же песочнице и пробует другие способы; дальше —
# только по команде: next — следующее задание (или конец рана), more — ещё новая команда в
# конце рана (вместо вопроса [y/N]), quit — выход. Время, звёзды и деньги уже посчитаны по
# моменту решения: эксперименты их не трогают. После giveup — так же: разбор показан, можно
# повторить решение руками.
LINGER_AFTER = ("solved", "giveup")
LINGER_CHOICES = ("next", "quit")
TASK_TIPS = ui.BOARD_CARDS["game"]      # FB5: теперь карточка game доски убежища
LINGER_NOTE = ("🧪 Песочница осталась как после твоего решения — пробуй другие способы, "
               "смотри, что вышло. Звёзды и деньги уже посчитаны, эксперименты их не тронут.")
LINGER_NO_SERVICE = "Учебный сервер этой задачи уже выключен — его команды здесь не ответят."


def task_tips_on(p: dict) -> bool:
    """Короткая напоминалка над приглашением во время задачи — пока идут «Основы» (страж
    «Основ» не взят). Дальше игрок команды знает, а после решения напоминалка есть всегда.
    FB5: строки над приглашением собирает доска убежища (hideout.board_lines)."""
    return hideout.basics_on(p)


def linger_tips(last: bool) -> str:
    """Строка над приглашением после решения: что набрать дальше. Ещё урок (more) — только
    после итога рана (FB3 правка владельца 17.10: more посреди рана путал счёт задач)."""
    go = "next — итог рана" if last else "next — следующее задание"
    return f"✓ засчитано · {go} · quit — выйти · book · keys · bug"


def _linger(task, box, state, outcome: str, opts: Options, tally: dict, prompt, rprompt,
            seed) -> str:
    """Та же песочница после разбора: zsh заново, проверок нет, хук знает режим по
    .termit/linger. Вернуть выбор игрока: next или quit (exit/Ctrl+D — как next)."""
    plan = tally.get("linger") or {}
    last = plan.get("last", True)
    lines = [LINGER_NOTE]
    if getattr(task, "needs_judge", False) or state.get(dbkit.ENGINE_KEY) == "pg":
        lines.append(LINGER_NO_SERVICE)
    ui.say()
    for line in lines:
        ui.say(ui.story_fill(line, "", "   "))
    ui.say(ui.story_fill(linger_tips(last), "   ", "   "))
    sandbox.set_result(box, "")
    sandbox.write_box_file(box, ".termit/feedback", "")     # уже перенесены в отзывы
    sandbox.write_box_file(box, ".termit/linger", "next")
    env = shell_run.build_env(box, task.id, opts.real_home, bare=opts.bare, no_gui=opts.no_gui,
                              prompt=prompt, rprompt=rprompt, task=task,
                              db_engine=state.get(dbkit.ENGINE_KEY))
    env["TERMIT_LINGER"] = "1"
    env["TERMIT_TIPS"] = "\n".join(list(tally.get("board") or []) + [linger_tips(last)])
    pwd = sandbox.read_pwd(box)
    cwd = pwd if pwd is not None and sandbox.inside(pwd, box) and pwd.is_dir() else \
        sandbox.start_dir(box)
    argv = shell_run.argv(box, opts.real_home, use_sandbox=not opts.no_sandbox, task=task)
    shell_run.mark_sandbox(env, argv)
    try:
        opts.runner(cwd, env, argv)
    finally:
        sandbox.reap(box)
        try:
            _collect_feedback(box, task, seed, opts)
        except Exception:       # noqa: BLE001 — замечание не роняет ран
            pass
    choice = sandbox.result(box)
    return choice if choice in LINGER_CHOICES else "next"


def give_gifts(p: dict, event: str) -> list:
    """Подарки события (один раз) и строка о них; вернуть выданные id."""
    got = shop.give(p, event)
    if got:
        fmt = (theme.story("shop") or {}).get("gift_got") or "🎁 {names}"
        ui.gift(shop.gift_line(event), fmt.format(names=", ".join(shop.name(i) for i in got)))
        prompt_was = "prompt" in (p.get("settings") or {})
        line = hideout.auto_enable(p, got)
        if line:
            ui.say(ui.story_fill(line, "   ", "   "))
        # FB8: как пользоваться новым; о только что включённом приглашении уже сказано выше
        skip = () if prompt_was else ("prompt",)
        for use in hideout.use_news(got, skip=skip):
            ui.say(ui.story_fill(use, "   ", "     "))
        _say_shop_tip(p)
    return got


def _say_shop_tip(p: dict) -> None:
    """FB5 п. 16: первый подарок или первые деньги — один раз сказать, где витрина."""
    tip = hideout.shop_tip(p)
    if tip:
        ui.say(ui.story_fill(tip, "   ", "   "))


def gifts_for_old_bosses(p: dict) -> list:
    """Стражи, взломанные до появления подарков: выдать их подарки (один раз на стража)."""
    got = []
    for boss in list(p["bosses"]):
        if boss in shop.GIFTS and boss not in p["gifts"]:
            got += give_gifts(p, boss)
    return got


def tomorrow_note(p: dict, nxt: date) -> Optional[str]:
    """Сколько старых дел войдёт в завтрашний ран (P2 Б3): не вся очередь, а то, что придёт.
    Хвост больше рана — спокойной строкой, без числа очереди."""
    tasks = registry.all_tasks()
    rest = [i for i in progress.due(p, nxt)
            if i in tasks and available(tasks[i]) and after_done(p, tasks[i])
            and not (tasks[i].boss and i not in p["bosses"])]
    n = min(len(rest), REVIEWS_PER_RUN)
    if not n:
        return None
    return theme.msg("tomorrow_count_tail" if len(rest) > n else "tomorrow_count", n=n)


def _tomorrow(p: dict, today: date) -> None:
    """Сюжетная зацепка: новое место → страж → новая задача трека → просто дела."""
    nxt = today + timedelta(days=1)
    tasks = registry.all_tasks()
    due = [i for i in progress.due(p, nxt) if i in tasks and after_done(p, tasks[i])]
    seed = today.toordinal()
    new = [registry.get(i) for i in next_new(p, progress.new_limit(p, nxt))]
    guards = [registry.get(i) for i in due
              if i in registry.all_tasks() and registry.get(i).boss and i not in p["bosses"]]
    fresh = [t.track for t in new
             if not any(progress.seen(p, x.id) for x in registry.tasks_of(t.track))]
    bosses = [t.id for t in guards + new if t.boss]
    tracks = [t.track for t in new if not t.boss]
    text = next((line for line in
                 [theme.tomorrow("places", k, seed) for k in fresh] +
                 [theme.tomorrow("bosses", b, seed) for b in bosses] +
                 [theme.tomorrow("tracks", k, seed) for k in tracks] if line), None)
    if not text:        # «старые дела» — разными словами, подряд одна не звучит (М2)
        text = (master.tomorrow_line(p, "after", seed) if master.season_done(p) else
                master.tomorrow_line(p, "reviews", seed) if due else theme.msg("tomorrow_quiet"))
    ui.say()
    ui.tomorrow(text, tomorrow_note(p, nxt))


def _summary(p: dict, today: date, tally: dict, streak_before: int, book_before: int) -> None:
    after = progress.current_streak(p, today)
    moved = after != streak_before
    froze = tally.get("froze") or {}
    extra = list(tally.get("extra", ()))
    bought, earned = tally.get("froze_split") or (len(froze.get("bought") or ()), 0)
    if bought:
        extra.append(theme.msg("freeze_spent", n=bought, left=p["freezes"]))
    if earned:          # заработанная — своим текстом, не «купленная» (M1 ревью C2)
        extra.append(freezes.text("spent", n=earned, left=p["freezes"]))
    ui.shift_summary(theme.msg("shift_closed", n=p["dozors"]), streak_before, after,
                     solved=tally["solved"], mastered=tally["mastered"],
                     warmed=tally["warm"], records=tally["records"],
                     earned=tally["earned"], spent=tally["spent"],
                     book_total=len(p["grimoire"]),
                     book_new=max(0, len(p["grimoire"]) - book_before),
                     freeze_saved=bool(froze.get("free")) and not froze.get("bought"),
                     milestone=theme.milestone(after) if moved else None,
                     milestone_pay=tally.get("milestone_pay", 0), extra=extra,
                     reward_at=progress.next_reward(after), week=progress.activity(p, today))
    # FB10: приём из каталога лайфхаков — по силам игроку, каждый ран следующий
    ui.hack_tip(lifehacks.summary_line(p, p["dozors"]))


def _yes(answer: str) -> bool:
    return answer.strip().lower() in ("y", "yes", "д", "да")


def _more_prompt(nxt) -> str:
    """Вопрос «ещё одну?»; про стража — абзацем, «[y/N]» всегда отдельной последней строкой."""
    if nxt.boss:
        return "\n" + ui.story_fill(theme.msg("more_boss", title=theme.title(nxt))) + "\n[y/N] "
    return "\nХочешь ещё одну новую команду? [y/N] "


def run_queue(queue: List[str], p: dict, opts: Options, today: date,
              offer_more: bool = False, paydata: bool = True, ritual: bool = True) -> None:
    """offer_more — после итога рана (если игрок не вышел сам) предложить ещё урок: more.
    paydata=False — без хабара (разминка пустого дня). ritual=False — запуск вне рана дня
    (круг мастера на заказ, play ID): ритуал закрытия дня он не тратит (FB12 A3)."""
    tasks = registry.all_tasks()
    tally = new_tally()
    # хабар данных: раз в день, по жребию даты; не в разминке, тренировке play и репетиции
    if paydata and not opts.practice and not opts.rehearsal:
        tally["paydata_host"] = loot.plant_for_run(p, queue, today)
        if tally["paydata_host"]:
            p["paydata_day"] = today.isoformat()
    gifts_for_old_bosses(p)
    progress.save(opts.progress_path, p)
    streak_before = progress.current_streak(p, today)
    book_before = len(p["grimoire"])
    karma_before = progress.karma(p)
    solved_any = False
    stopped = False         # игрок вышел сам (quit, Ctrl+C) — ещё урок не предлагаем
    choice = None
    for i, tid in enumerate(queue, 1):
        last = i == len(queue)
        tally["linger"] = {"last": last}
        try:
            outcome = run_task(tasks[tid], p, i, len(queue), opts, tally)
        except KeyboardInterrupt:      # песочницу уже убрал finally в run_task
            ui.say("\n" + theme.msg("quit"))
            stopped = True
            break
        if outcome == "quit":
            stopped = True
            break
        solved_any = solved_any or outcome == "solved"
        choice = tally.pop("after", None)       # FB3 (3): next/quit из песочницы
        if choice == "quit":
            stopped = True
            break
        if i < len(queue) and choice is None:
            try:
                opts.ask("\n" + theme.msg("next"))
            except (EOFError, KeyboardInterrupt):
                print()
                stopped = True
                break
    if solved_any:
        # FB12 (A3): ритуал «ран закрыт» — раз в день, своя отметка ritual_day (не days: день
        # закрывает и play, и круг мастера, а ритуал им не положен); урок после него (more,
        # второй ран за день) кончается итогом в две строки; счётчик ранов — по дням
        day_closed = not ritual or p.get("ritual_day") == today.isoformat()
        tally["froze"] = progress.close_day(p, today)    # тут и тратятся заморозки
        tally["froze_split"] = freezes.split_spent(p, len(tally["froze"]["bought"]))
        earned_freeze = freezes.earn(p, today)          # 3 рана за 7 дней — в запас (М4)
        tally["extra"] = list(tally.get("extra", ())) + freezes.lines(p, tally["froze"],
                                                                      earned_freeze)
        # 12 дел недели — только дела обычных ранов: тренировки, круг мастера и play не в счёт
        # (M2 ревью C2: иначе пять кругов за вечер закрывали контракт)
        week_pay = weekly.note(p, today, 0 if opts.practice else tally["solved"])
        if week_pay:                                    # контракт недели: один раз (М5)
            tally["earned"] += week_pay
            tally["extra"].append(weekly.text("paid", pay=week_pay, cash=theme.word("money")))
        tally["extra"] += repute.summary_lines(p, karma_before)     # репутация (М6)
        if opts.comeback_bonus:     # выгодный ран: премия, если что-то решено, — при любом итоге
            tally["earned"] += contracts.pay_comeback(p, opts.comeback_bonus, today)
            tally["extra"].append(contracts.text("comeback_paid", bonus=opts.comeback_bonus,
                                                 cash=theme.word("money")))
        if day_closed:
            progress.save(opts.progress_path, p)
            _lesson_summary(p, tally, book_before)
            _goal_talk(p)
            progress.save(opts.progress_path, p)
        else:
            _close_day_ritual(p, opts, today, tally, streak_before, book_before)
    progress.save(opts.progress_path, p)
    if not opts.rehearsal:
        _edition_finish(p, opts)
    if offer_more and solved_any and not stopped:
        _offer_more(p, opts, today)


def _lesson_summary(p: dict, tally: dict, book_before: int) -> None:
    """FB12 (A3): итог урока после закрытого дня — две строки: что решено и заработано,
    и ближняя цель (goal.line). Редкие события (репутация, контракт недели) — следом."""
    cash = theme.word("money")
    parts = [f"решено {tally['solved'] + tally['mastered'] + tally['warm']}"]
    if tally["earned"]:
        parts.append(f"+{tally['earned']} {cash}")
    if tally["spent"]:
        parts.append(f"{theme.word('soft_label')} −{tally['spent']} {cash}")
    total = len(p["grimoire"])
    if total:
        new = max(0, total - book_before)
        parts.append(f"{theme.word('book')}: {total}" + (f" (+{new})" if new else ""))
    ui.say()
    ui.ok(ui.story_fill("✓ Урок закрыт: " + " · ".join(parts), "  ", "    "))
    for row in [goal.line(p)] + list(tally.get("extra") or ()):
        if row:
            ui.say(ui.story_fill(row, "  ", "    "))


def _goal_talk(p: dict) -> None:
    """FB12 (A2): реплика по дороге к стражу — когда пересечён порог (goal.STEPS)."""
    for kind, who, text in goal.say_lines(p):
        ui.say()
        if kind == "voice":
            ui.voice(who, text)
        else:
            ui.say(ui.story_fill(f"💬 {who}: {text}", "", "   "))


def _close_day_ritual(p: dict, opts: Options, today: date, tally: dict, streak_before: int,
                      book_before: int) -> None:
    """Первое закрытие дня: рамка «ран закрыт», веха серии, завоз, предложения, «Завтра»."""
    p["dozors"] += 1
    p["ritual_day"] = today.isoformat()
    bonus = progress.pay_milestone(p, progress.current_streak(p, today))
    tally["earned"] += bonus
    tally["milestone_pay"] = bonus
    progress.save(opts.progress_path, p)    # день засчитан, даже если дальше прервут
    aim = goal.line(p)              # FB12 (A2): ближняя цель — первой строкой под счётом
    tally["extra"] = ([aim] if aim else []) + list(tally.get("extra") or ())
    _summary(p, today, tally, streak_before, book_before)
    _goal_talk(p)
    if tally["earned"] > 0:
        _say_shop_tip(p)
    after = progress.current_streak(p, today)
    if after != streak_before and (bonus or theme.milestone(after)):
        sound.play(p, "milestone", tally.setdefault("sounds", set()))
    if after >= shop.GIFT_STREAK:
        give_gifts(p, "streak3")        # после вехи 3 — первый предмет в убежище
    stocked = cosmetics.stock_tick(p, today)       # завоз косметики: ≤ 1 строки за ран
    if stocked:
        ui.say()
        ui.say(ui.story_fill(cosmetics.stock_line(stocked), "", "   "))
    for hint in story.hunt_hints(p) + [loot.hint(p)]:   # один раз: охота существует
        if hint:
            ui.say()
            ui.say(ui.story_fill(hint, "", "   "))
    # склад pandas/requests (часть 10, A3): трек «Python» открыт, склада нет — один
    # вопрос в день, качает только родитель и только по y. Вопрос в конце рана — один на
    # всех (M1 ревью Q4): склад или имплант, другой ждёт следующего рана
    if warehouse.goes_first(p, today):
        warehouse.offer(p, lambda q: _ask(opts, q), today, opts.wheels_getter)
    else:
        implants.offer(p, lambda q: _ask(opts, q), today, opts.installer)   # ≤ 1 за ран
    field.give(p, today)
    offered = None
    if not opts.practice:       # не в разминке и не в play
        contracts.expire(p, today)
        offered = contracts.offer_urgent(       # жребий — по дате, раз в день
            p, today, random.Random(f"urgent:{today.isoformat()}"))
    _tomorrow(p, today)
    if offered:
        ui.say(ui.story_fill(contracts.urgent_line(p, today, "urgent_offer"), "", "   "))


def _edition_finish(p: dict, opts: Options) -> None:
    """Публичное издание: первый модуль пройден — тёплое сообщение один раз."""
    text = edition.finish_once(p)
    if text:
        ui.say()
        ui.ok(ui.story_fill(text, "", "   "))
        progress.save(opts.progress_path, p)


MORE_PROMPT = ("\nРан окончен. Ещё урок — пара-тройка новых команд сверх нормы: набери more "
               "и Enter. Выйти — просто Enter.\n> ")
# FB12 (A3) + FB5 п. 28: урок — пачка новых задач, не одна (больше дела за вечер)
MORE_BATCH = 3


def more_batch(p: dict) -> List[str]:
    """Пачка урока: до MORE_BATCH новых задач. Страж — экзамен, он всегда отдельно: первым
    стоит — урок из него одного (с вопросом more_boss), дальше в пачке — пачка до него."""
    new = next_new(p, MORE_BATCH)
    tasks = registry.all_tasks()
    if new and tasks[new[0]].boss:
        return new[:1]
    cut = next((i for i, t in enumerate(new) if tasks[t].boss), len(new))
    return new[:cut]


def _offer_more(p: dict, opts: Options, today: date) -> None:
    """После итога рана — ещё урок по команде more (правка владельца 17.10: more — когда
    день закончен, а не посреди рана). Урок — пачка новых задач (more_batch) с коротким итогом
    (FB12), после него вопрос снова. Стража спрашиваем отдельно: это экзамен (more_boss)."""
    new = more_batch(p)
    if not new:
        return
    if _ask(opts, MORE_PROMPT).strip().lower() not in ("more", "m", "y", "yes", "д", "да"):
        return
    nxt = registry.get(new[0])
    if nxt.boss and not _yes(_ask(opts, _more_prompt(nxt))):
        return
    run_queue(new, p, opts, today, offer_more=True)


@_rooted
def dozor(opts: Options, short: bool = False) -> None:
    """Ран. С music run on — своя кассета на время рана; стоп в finally (и по Ctrl+C)."""
    with music.in_run(progress.load(opts.progress_path)):
        _dozor(opts, short)


def _dozor(opts: Options, short: bool = False) -> None:
    p = progress.load(opts.progress_path)
    today = opts.today or date.today()
    first_run = _intro_once(p, opts)
    sandbox.cleanup_stale(opts.sandbox_root)
    field.ask_pending(p, opts.ask, today)
    back = contracts.comeback(p, today)
    queue = contracts.comeback_queue(p) if back else []
    if queue:       # выгодный ран: сильные знакомые дела + одно новое, тренировкой, ×2 (М1)
        contracts.expire(p, today)
        opts = dataclasses.replace(opts, pay_mult=contracts.COMEBACK_PAY_MULT,
                                   comeback_bonus=back["bonus"], comeback=True)
    else:
        back = None
        queue = contracts.inject(p, build_queue(p, today, short), today)  # срочный — делом
    warmup = not queue
    if warmup:                 # пустых дней нет: круг мастера по знакомому (М3), без расписания
        queue = warmup_queue(p)
        opts = dataclasses.replace(opts, practice=True, master=frozenset(queue))
    elif not back and not any(not progress.seen(p, t) for t in queue):
        extra = master.fill(p, queue, short=short)  # сезон закрыт, нового нет: добор кругом
        if extra:
            queue = queue + extra
            opts = dataclasses.replace(opts, master=frozenset(extra))
    opening = registry.tasks_of("basics")[0].id      # вступление ведёт к первому делу
    if first_run and opening in queue and not progress.seen(p, opening):
        queue.remove(opening)
        queue.insert(0, opening)
    # FB12 (A3): ранов — по дням; второй заход за день — тот же номер
    number = p["dozors"] + (0 if p.get("ritual_day") == today.isoformat() else 1)
    head, rank = cosmetics.header_parts(p, f"{theme.word('session')} #{number}",
                                        theme.rank_name(registry.rank_level(p["bosses"])), today)
    ui.header(head, None if back else progress.current_streak(p, today), rank, len(queue),
              money=p["money"])
    lost = 0 if back else progress.lost_streak(p, today)
    if lost:        # серия оборвалась: честно и без укора, одной строкой (П3.8)
        ui.say(ui.story_fill(theme.msg("streak_lost", n=lost), "  ", "    "))
    if weekly.visible(p, today):    # контракт недели (М5): с 3-го дня, одной строкой (P2 Б6)
        ui.say(ui.story_fill(weekly.short_line(p, today), "  ", "    "))
    line = contracts.urgent_line(p, today)
    if line and not warmup:
        ui.say(ui.story_fill(line, "  ", "    "))
    _edition_finish(p, opts)
    if back:        # только радость возвращения: без серии и пропущенных дней (М7)
        fresh = any(not progress.seen(p, t) for t in queue)
        ui.comeback(contracts.text("comeback_banner_new" if fresh else "comeback_banner"),
                    contracts.text("comeback_voice"))
    if not queue:
        ui.say(theme.msg("empty_day"))
        progress.save(opts.progress_path, p)
        return
    said = master.announce(p)           # конец сезона: один раз, честно (М2)
    if said:
        ui.say()
        ui.ok(ui.story_fill(said, "  ", "  "))
        ui.say("\n".join(master.summary_lines(p)))      # и короткие итоги сезона (P2 Б4)
        progress.save(opts.progress_path, p)
    if warmup:
        ui.say(ui.story_fill(theme.msg("warmup"), "", ""))
    run_queue(queue, p, opts, today, offer_more=not warmup and not back, paydata=not warmup)


def warmup_queue(p: dict, rng=None) -> List[str]:
    """Круг мастера (бывшая разминка): 2–3 освоенные задачи, не больше одного взломанного
    стража; непобеждённый страж был бы экзаменом, провал ждёт тренировки — мимо."""
    return master.queue(p, rng)


def _master_label(best) -> str:
    """Строка режима на карточке круга мастера: рекорд вместо таймера."""
    best = progress.shown_best(best)
    tail = (master.text("best", time=ui.fmt_time(best)) if best is not None
            else master.text("no_best"))
    return f"{master.text('mode')} · {tail}"


@_rooted
def master_run(opts: Options) -> None:
    """./termit master — круг мастера на заказ: знакомые дела на время, без расписания."""
    p = progress.load(opts.progress_path)
    today = opts.today or date.today()
    sandbox.cleanup_stale(opts.sandbox_root)
    queue = warmup_queue(p)
    if not queue:
        ui.say(ui.story_fill(master.text("none"), "", ""))
        return
    ui.say(ui.story_fill(master.text("start"), "", ""))
    opts = dataclasses.replace(opts, practice=True, master=frozenset(queue))
    run_queue(queue, p, opts, today, paydata=False, ritual=False)


def _intro_once(p: dict, opts: Options) -> bool:
    """Вступление и две строки управления — при самом первом запуске; True, если показано."""
    today = opts.today or date.today()
    if p["intro_seen"]:
        # «Ранее…» (FB3) — при новой вехе или после перерыва, не каждый день (FB12, S10)
        if story.recap_due(p, today):
            for line in story.recap_lines(p):
                ui.say(ui.story_fill(line, "  ", "    "))
            story.recap_mark(p, today)
            progress.save(opts.progress_path, p)
        return False
    ui.show_intro(theme.intro_text())
    _ask(opts, "\n   Enter — начать ")
    p["intro_seen"] = True
    story.recap_mark(p, today)      # вступление и есть первое «Ранее…»
    progress.save(opts.progress_path, p)
    return True


@_rooted
def more(opts: Options) -> None:
    """./termit more — урок: пачка новых задач вне нормы рана (FB12: до MORE_BATCH)."""
    p = progress.load(opts.progress_path)
    today = opts.today or date.today()
    first_run = _intro_once(p, opts)
    sandbox.cleanup_stale(opts.sandbox_root)
    field.ask_pending(p, opts.ask, today)
    new = more_batch(p)
    if not new:
        ui.say(ui.story_fill(edition.FINISH, "", "") if edition.module_done(p) else
               ui.story_fill(master.text("short"), "", "") if master.season_done(p) else
               "Новых команд пока нет — всё открытое уже встречалось.")
        progress.save(opts.progress_path, p)
        return
    opening = registry.tasks_of("basics")[0].id      # вступление ведёт к первому делу
    if first_run and not progress.seen(p, opening):
        new = [opening]
    nxt = registry.get(new[0])
    if nxt.boss and not _yes(_ask(opts, _more_prompt(nxt))):
        progress.save(opts.progress_path, p)         # от стража отказались — выходим спокойно
        return
    run_queue(new, p, opts, today, offer_more=True)


@_rooted
def run_track(key: str, opts: Options) -> None:
    shown = registry.shown_tracks()
    tr = next((t for t in shown if t.key == key), None)
    if tr is None:                  # трек-скелет без задач игроку не виден (fix1 Q1, I4)
        ui.bad(f"Нет такого места: {key}. Есть: " + ", ".join(t.key for t in shown))
        return
    p = progress.load(opts.progress_path)
    today = opts.today or date.today()
    if not edition.track_open(tr.key):
        ui.say(ui.story_fill(edition.LOCKED.format(place=theme.place(tr.key)), "", ""))
        return
    if tr not in registry.unlocked(p["bosses"]):
        need = ", ".join(theme.title(registry.get(b)) for b in tr.requires)
        ui.say(theme.msg("locked", place=theme.place(tr.key), need=need))
        return
    sandbox.cleanup_stale(opts.sandbox_root)
    ts = registry.tasks_of(key)
    # пары с невыполненным after не выдаются и отсюда: иначе track обходил бы расписание
    ts = [t for t in ts if after_done(p, t)]
    queue = [t.id for t in ts if not t.boss and available(t) and not progress.seen(p, t.id)][:5]
    if not queue:
        due = set(progress.due(p, today))
        queue = [t.id for t in ts if t.id in due][:5]
    if not queue:
        queue = [t.id for t in ts if t.boss and t.id not in p["bosses"]]
    if not queue:
        avail = [t.id for t in ts if available(t)]
        queue = random.sample(avail, min(5, len(avail)))
    contracts.expire(p, today)
    if contracts.urgent_task(p, today) in {t.id for t in ts}:
        queue = contracts.inject(p, queue, today)
    run_queue(queue, p, opts, today)


@_rooted
def rehearse(boss_id: str, opts: Options) -> None:
    """./termit rehearse BOSS — страж в режиме тренировки; первая после провала даром."""
    p = progress.load(opts.progress_path)
    code = contracts.can_rehearse(p, boss_id)
    if code != "ok":
        kw = {"id": boss_id}
        if code in ("beaten", "locked"):
            kw["title"] = theme.title(registry.get(boss_id))
        ui.say(contracts.text("rehearse_" + code, **kw))
        return
    task = registry.get(boss_id)
    if not available(task):
        ui.bad(f"Задача {boss_id} пока закрыта: " +
               (task.missing() or "нужен " + ", ".join(task.needs)))
        return
    price = contracts.rehearsal_price(p, boss_id)
    cash = theme.word("money")
    if price:
        if p["money"] < price:
            ui.say(contracts.text("rehearse_money", price=price, cash=cash,
                                  money=ui.balance(p["money"])))
            return
        q = contracts.text("rehearse_ask", title=theme.title(task), price=price, cash=cash)
        if not _yes(_ask(opts, "\n" + ui.story_fill(q) + "\n[y/N] ")):
            return
    else:
        ui.say(ui.story_fill(contracts.text("rehearse_free_go", title=theme.title(task))))
    progress.save(opts.progress_path, p)
    sandbox.cleanup_stale(opts.sandbox_root)
    opts = dataclasses.replace(opts, rehearsal=True, practice=False)
    outcome = None
    try:
        outcome = run_task(task, p, 1, 1, opts, new_tally())
    except KeyboardInterrupt:
        ui.say("\n" + theme.msg("quit"))
    # репетиция оплачивается (или тратит бесплатную), только если страж правда сыгран:
    # вышел, отложил, песочница не собралась — ни денег, ни бесплатной не теряешь
    if outcome not in (None, "quit", "broken", "skip"):
        if price:
            p["money"] -= price
        else:
            p["rehearsal_free_used"].append(boss_id)
    progress.save(opts.progress_path, p)


def boss_waiting(p: dict, task) -> List[str]:
    """Чего не хватает, чтобы страж был взят честно: невстреченные обычные поручения его
    трека (те, что обход выдал бы раньше стража). Пусто — страж уже встречался или до него
    дошли по порядку (next_new выдаёт стража, только когда свежих поручений не осталось)."""
    if not task.boss or progress.seen(p, task.id):
        return []
    return [t.id for t in registry.tasks_of(task.track)
            if not t.boss and available(t) and not progress.seen(p, t.id) and after_done(p, t)]


@_rooted
def play_one(task_id: str, opts: Options) -> None:
    if task_id not in registry.all_tasks():
        ui.bad(f"Нет задачи {task_id}. Список: ./termit list")
        return
    task = registry.get(task_id)
    if not available(task):
        ui.bad(f"Задача {task_id} пока закрыта: " +
               (task.missing() or "нужен " + ", ".join(task.needs)))
        return
    p = progress.load(opts.progress_path)
    # play ID не обходит замок трека и порядок: страж — экзамен и ступень звания
    tr = registry.track(task.track)
    if not edition.track_open(tr.key):
        ui.say(ui.story_fill(edition.LOCKED.format(place=theme.place(tr.key)), "", ""))
        return
    if tr not in registry.unlocked(p["bosses"]):
        need = ", ".join(theme.title(registry.get(b)) for b in tr.requires
                         if b not in p["bosses"])
        ui.say(theme.msg("locked", place=theme.place(tr.key), need=need))
        return
    waiting = boss_waiting(p, task)
    if waiting:
        names = [theme.title(registry.get(t)) for t in waiting[:3]]
        more = f" и ещё {len(waiting) - 3}" if len(waiting) > 3 else ""
        ui.say(theme.msg("after_locked", title=theme.title(task),
                         need=", ".join(names) + more))
        return
    need = registry.missing_after(p, task)
    if need:
        ui.say(theme.msg("after_locked", title=theme.title(task),
                         need=", ".join(theme.title(registry.get(t)) for t in need)))
        return
    sandbox.cleanup_stale(opts.sandbox_root)
    opts = dataclasses.replace(opts, practice=True)
    run_queue([task_id], p, opts, opts.today or date.today(), ritual=False)
