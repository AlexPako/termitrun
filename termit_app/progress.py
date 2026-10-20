"""Прогресс владельца: звёзды, интервальные повторения, серия дней, карма, кредиты, шпаргалка."""
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

INTERVALS = [1, 3, 7, 16, 35]   # дни до следующего повторения на уровнях 1..5
START_MONEY = 50
# ярус трека — множитель цен: чем сложнее место, тем дороже софт
TIER = {"basics": 1, "tools": 1, "finder": 1, "speed": 1,
        "data": 2, "db": 2, "git": 2, "sql": 3, "env": 2, "ssh": 3}
HINT_BASE = (5, 10, 20)         # цена 1-й, 2-й, 3-й подсказки на деле при ярусе 1
HINT_CREDIT_FLOOR = -20         # в долг — любая подсказка дела, но не глубже этого (K11)
# Подсказки — по своему ярусу: «Данные» (jq, curl) для новичка новые, подсказки там по цене
# яруса I, хотя оплату срочных, хабар, репетиции и Сову трек считает по ярусу II (K11: у
# слабого игрока отказы «нет денег» шли наполовину отсюда). Так же «Базы данных» (SQL для
# новичка новый, 9а) — ярус I. «SQL и PostgreSQL» (9б) — ярус III, подсказки по II (план
# части 9, решение 9: проверка econ_sim; отказы у слабого выше 0,3 % — sql=1). «Окружение и
# скрипты» (часть 7, E22) — ярус II, подсказки по I, как у «Данных».
HINT_TIER = dict(TIER, data=1, db=1, sql=2, env=1)
MONEY_PER_STAR = 10
BOSS_MONEY = {"boss_basics": 100, "boss_tools": 150, "boss_finder": 150, "boss_data": 200,
              "boss_db": 200, "boss_git": 250, "boss_sql": 250, "boss_env": 220, "boss_ssh": 300}
FIELD_MONEY = 20
FIELD_KARMA = 20                # карма за задание в реале
FREEZE_PRICE = 50
FREEZE_CAP = 2                  # держать заморозок не больше (3 — с модулем деки freezer)
STREAK_MILESTONES = {7: 30, 14: 50, 30: 100, 60: 150, 90: 200, 180: 300}
SLOT_KARMA = {2: 1500, 3: 4000}  # карма открывает слоты деки, сама не тратится
TRAIN_XP = 5
NEW_FIRST_WEEK = 2              # новых задач в ране первые 7 дней игры
NEW_LATER = 1                   # дальше — по одной
FIRST_WEEK_DAYS = 7
# Сова (локальная Ollama): вопрос на деле = −1 ★ и OWL_BASE × ярус; в тренировке —
# OWL_FREE_TRAIN бесплатно за ран; не больше OWL_PER_TASK на задачу и OWL_PER_RUN за ран
OWL_BASE = 15
OWL_PER_TASK = 2
OWL_PER_RUN = 5
OWL_FREE_TRAIN = 3


def empty() -> dict:
    return {"version": 1, "tasks": {}, "days": [], "xp": 0, "bosses": [],
            "grimoire": {}, "field": {"done": [], "pending": None, "later": {}},
            # declined — старые отказы от формул (до части 5); живые отказы — implants.declined
            "dozors": 0, "declined": [], "settings": {},
            "money": START_MONEY, "freezes": 0, "intro_seen": False,
            # закрытые пропуски серии: {iso: "free"|"bought"} — заморозки тратятся (часть 7а)
            "frozen_days": {},
            "freeze_saves": 0,      # сколько раз купленная заморозка спасла серию (не убывает)
            "freeze_earned": None,  # день последней заработанной заморозки (C2 М4, freezes.py)
            "freeze_stock_earned": 0,   # сколько из запаса freezes — заработанные (M1 ревью C2)
            # экономика и сюжет (часть 2)
            "milestones": [], "owned": [], "gifts": [],
            "deck": {"installed": [], "slots": 1}, "shards": [], "opened": [], "flags": [],
            "urgent": None, "urgent_day": None, "comeback_last": None, "rehearsal_free_used": [], "paydata": [], "paydata_day": None,
            "shop_seen": [], "shard_tip": False,
            # последняя реплика персонажа по треку — подряд одна и та же не звучит (П3.6)
            "said": {},
            # косметика (часть 7а): завезённое на витрину по порядку и ран последнего завоза
            "stock": [], "stock_run": 0,
            # круг мастера (C2 М3): за какую задачу и в какой день платили за рекорд
            "master": {"paid": {}, "pending": {}},
            # контракт недели (C2 М5): ISO-неделя, решённые дела, выплачен ли
            "weekly": {"week": "", "solved": 0, "paid": False},
            # утилиты-подарки (часть 5): отказы, «позже», когда предлагали, сравнения
            # seen_installed зарезервирован (интерфейс плана I2: утилиты, которые игрок уже
            # поставил сам, — для будущего «поздравления»); пока не читается и не пишется
            "implants": {"declined": [], "later": {}, "offered": {}, "seen_installed": [],
                         "compare": {}},
            # FB3: копилка расширений — встреченные в заданиях, по порядку (termit_app.extensions)
            "extensions": [],
            # FB5: команды ./termit СЛОВО, которым уже показана строка «что это» (ui.glossary)
            "cmds_seen": [],
            # FB12 (N6): системные ошибки, которые игрок уже видел с переводом (syserrors)
            "errors_seen": []}


def _reserve_backup(path: Path) -> Path:
    """Свободное имя копии: время в наносекундах, PID и счётчик. Имя занимается через O_EXCL —
    существующий файл не затирается никогда, даже если две копии делаются в одну секунду."""
    stamp = f"{time.time_ns()}-{os.getpid()}"
    n = 0
    while True:
        backup = path.with_name(f"progress.broken-{stamp}-{n}.json")
        try:
            fd = os.open(str(backup), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            n += 1
            continue
        os.close(fd)
        return backup


def _broken(path: Path) -> dict:
    """Файл не читается как сохранение: копию в сторону, игра — с чистого листа.
    Файл переезжает на заранее занятое (пустое, своё) имя; пропал по дороге (гонка двух
    процессов) — пустышку убираем, копии нет."""
    backup = _reserve_backup(path)
    try:
        os.replace(str(path), str(backup))
    except FileNotFoundError:
        backup.unlink()
        return empty()
    print(f"⚠ progress.json повреждён — сохранил копию {backup.name}, начинаю с чистого листа.",
          file=sys.stderr)
    return empty()


# Вложенные разделы: (ключ, тип) — испорченное значение заменяется значением по умолчанию.
_NESTED = {"field": (("done", list), ("pending", (str, type(None))), ("later", dict)),
           "deck": (("installed", list), ("slots", int)),
           "implants": (("declined", list), ("later", dict), ("offered", dict),
                        ("seen_installed", list), ("compare", dict))}
_DICTS = ("settings", "grimoire", "field", "deck", "implants", "said", "master")


def _iso_day(d) -> bool:
    if not isinstance(d, str):
        return False
    try:
        date.fromisoformat(d)
    except ValueError:
        return False
    return True


def _normalize(p: dict) -> None:
    """Словари, которые игра ожидает, — словари; вложенные ключи — своего типа (недостающие
    дополняются). Ценное (tasks, money, xp, bosses) здесь не трогается; из days уходят только
    записи, которые не дата ГГГГ-ММ-ДД, — в p["days_bad"], не в никуда."""
    base = empty()
    days = p.get("days")
    if not isinstance(days, list) or not all(_iso_day(d) for d in days):
        # испорченные записи дней — в сторону (days_bad), валидные даты остаются
        raw = days if isinstance(days, list) else [days]
        bad = [d for d in raw if not _iso_day(d)]
        p["days"] = [d for d in raw if _iso_day(d)]
        old_bad = p.get("days_bad") if isinstance(p.get("days_bad"), list) else []
        p["days_bad"] = old_bad + bad
    for key in _DICTS:
        if not isinstance(p.get(key), dict):
            p[key] = base[key]
    for key, fields in _NESTED.items():
        sec = dict(p[key])
        for name, kind in fields:
            val = sec.get(name)
            if name not in sec or not isinstance(val, kind) or \
                    (kind is int and isinstance(val, bool)):
                sec[name] = base[key][name]
        p[key] = sec
    # счётчики — неотрицательные целые (bool — не число); купленное — список строк
    for key in ("freezes", "dozors"):
        val = p.get(key)
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            p[key] = base[key]
    ext = p.get("extensions")                    # FB3: копилка — список строк «.txt»
    p["extensions"] = ([x for x in ext if isinstance(x, str) and x.startswith(".")]
                       if isinstance(ext, list) else [])
    seen = p.get("cmds_seen")                    # FB5: встреченные команды — список строк
    p["cmds_seen"] = [x for x in seen if isinstance(x, str)] if isinstance(seen, list) else []
    tasks = p.get("tasks") if isinstance(p.get("tasks"), dict) else {}
    for rec in tasks.values():                   # FB12 (п. 34): выпавшие варианты — числа
        if isinstance(rec, dict) and "seen_variants" in rec:
            rec["seen_variants"] = seen_variants(rec)
    errs = p.get("errors_seen")                  # FB12 (N6): переведённые ошибки — строки
    p["errors_seen"] = [x for x in errs if isinstance(x, str)] if isinstance(errs, list) else []
    owned = p.get("owned")
    p["owned"] = [x for x in owned if isinstance(x, str)] if isinstance(owned, list) else []
    from termit_app import weekly                # C2 М5: испорченный контракт — пустой
    p["weekly"] = weekly.clean(p.get("weekly"))
    n = p.get("freeze_stock_earned")             # заработанных в запасе — 0..freezes
    p["freeze_stock_earned"] = (min(n, p["freezes"]) if isinstance(n, int)
                                and not isinstance(n, bool) and n > 0 else 0)
    if not _iso_day(p.get("freeze_earned")):     # C2 М4: дата или None
        p["freeze_earned"] = None
    # круг мастера (C2): paid {задача: ISO-дата}, pending {задача: вариант}; мусор — прочь
    paid, pending = p["master"].get("paid"), p["master"].get("pending")
    p["master"] = {"paid": {k: v for k, v in paid.items() if isinstance(k, str) and _iso_day(v)}
                   if isinstance(paid, dict) else {},
                   # выданный вариант круга до решения (M3 ревью C2): {задача: номер}
                   "pending": {k: v for k, v in pending.items() if isinstance(k, str)
                               and isinstance(v, int) and not isinstance(v, bool) and v >= 0}
                   if isinstance(pending, dict) else {}}


# FB9b: поручения, переехавшие в место дальше по игре: {задача: новый трек}. Запись из
# старого места уходит в p["moved"], пока новое место не открыто, — задача не всплывает в
# повторениях раньше своего места и встретится там новой, с уроком. Открыто — запись живёт.
MOVED_TASKS = {"read_long_list": "env", "perm_digits": "env"}


def park_moved(p: dict) -> None:
    from termit_app.tasks import registry
    bosses = set(p.get("bosses") or ())
    for task_id, track_key in MOVED_TASKS.items():
        if task_id not in p["tasks"] or set(registry.track(track_key).requires) <= bosses:
            continue
        moved = p.get("moved") if isinstance(p.get("moved"), dict) else {}
        moved[task_id] = p["tasks"].pop(task_id)
        p["moved"] = moved


# FB12 (B2): рекорд меньше секунды — наследие старого таймера (стартовал с первой команды,
# ans первой же командой давал «0:00»); его не побить никогда — такого рекорда не бывает.
# Дольше 10 минут — не рекорд, а открытое и забытое окно: в дневнике и круге мастера не видно.
BEST_MIN = 1.0
BEST_SHOWN_MAX = 600


def _note_best(rec: dict, elapsed: float) -> None:
    if elapsed >= BEST_MIN and (rec.get("best") is None or elapsed < rec["best"]):
        rec["best"] = round(elapsed, 1)


def shown_best(best) -> Optional[float]:
    """Рекорд для экрана и для круга мастера: число от BEST_MIN до BEST_SHOWN_MAX, иначе None."""
    if not isinstance(best, (int, float)) or isinstance(best, bool):
        return None
    return best if BEST_MIN <= best <= BEST_SHOWN_MAX else None


def drop_old_bests(p: dict) -> None:
    """Миграция: рекорды меньше секунды из старого сохранения — None («поставишь сейчас»).
    Испорченный раздел tasks (не словарь) — мимо: загрузку он ронять не должен."""
    tasks = p.get("tasks")
    if not isinstance(tasks, dict):
        return
    for rec in tasks.values():
        if not isinstance(rec, dict):
            continue
        best = rec.get("best")
        if isinstance(best, (int, float)) and not isinstance(best, bool) and best < BEST_MIN:
            rec["best"] = None


def load(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return empty()
    try:
        data = json.loads(path.read_text("utf-8"))
    except (ValueError, OSError):
        return _broken(path)
    if not isinstance(data, dict):
        return _broken(path)
    p = empty()
    p.update(data)
    _normalize(p)
    park_moved(p)
    drop_old_bests(p)
    if isinstance(p.get("declined"), list) and "tlrc" in p["declined"]:
        # до части 5 отказывались от формулы tlrc — теперь это отказ от утилиты tldr
        p["declined"] = [x for x in p["declined"] if x != "tlrc"]
        decl = p["implants"].get("declined")
        decl = decl if isinstance(decl, list) else []
        p["implants"]["declined"] = decl + ([] if "tldr" in decl else ["tldr"])
    if "frozen_days" not in data:
        # файл до части 7а: заморозки считались по всей истории и не тратились — переводим
        # мосты старой серии в записи, чтобы серия не пропала
        p["frozen_days"] = {}
        migrate_freezes(p, date.today())
    else:
        # ключ есть — только чистим мусор; старый алгоритм здесь «отремонтировал» бы разрывы
        p["frozen_days"] = clean_frozen(data.get("frozen_days"))
        if not isinstance(data.get("freeze_saves"), int) or isinstance(data["freeze_saves"], bool):
            p["freeze_saves"] = sum(1 for v in p["frozen_days"].values() if v == "bought")
    if "milestones" not in data:
        # файл до части 2: вехи уже набранной серии считаем пройденными — иначе первый же
        # ран выплатит их все разом
        have = current_streak(p, date.today())
        p["milestones"] = [d for d in sorted(STREAK_MILESTONES) if d <= have]
    return p


def save(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".progress-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def stars_for(solved: bool, hints: int, elapsed: float, par: int, first_time: bool) -> int:
    """3 звезды: решено, без подсказок, в таймер (при первой встрече время не считается)."""
    if not solved:
        return 0
    late = 0 if first_time or elapsed <= par else 1
    return max(1, 3 - hints - late)


def mode_for(p: dict, task_id: str, boss: bool = False, practice: bool = False) -> str:
    """«train» для практики, новой задачи или задачи после провала; иначе «job».
    Босс — экзамен, пока не побеждён; побеждённого в play можно повторить тренировкой."""
    if boss:
        return "train" if practice and task_id in p["bosses"] else "job"
    rec = p["tasks"].get(task_id)
    if practice or rec is None or rec.get("retrain"):
        return "train"
    return "job"


VARIANTS_KEEP = 6      # сколько последних выданных вариантов помнит запись задачи
REVIEW_ALTS = 3        # «можно и так» в снимке разбора (дневник) — не больше стольких
REVIEW_MAX = 400       # длина строки снимка: state из task.json песочницы мог раздуть эталон
# CSI целиком; C0 кроме \t и \n; DEL; C1 (\x9b — CSI в 8-битном режиме); разрывы строк U+2028/9
_CTRL = re.compile(r"\033\[[0-9;?]*[A-Za-z]|[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029]")


def variant_history(rec: Optional[dict], n: int) -> List[int]:
    """Последние выданные варианты из записи; мусор и номера вне 0..n-1 отбрасываются.
    Запись без ключа (сохранение до вариантов) — игрок видел только вариант 0."""
    if rec is not None and "variants" not in rec:
        return [0]
    raw = (rec or {}).get("variants")
    if not isinstance(raw, list):
        return []
    return [v for v in raw if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < n]


def pick_variant(rec: Optional[dict], n: int, rng,
                 allowed: Optional[Iterable[int]] = None, prefer: Optional[int] = None) -> int:
    """Какой вариант выдать на повторе: сначала ни разу не выпадавшие, иначе наименее
    недавний; тот же, что в прошлый раз, — никогда (если вариантов больше одного).
    Среди равных решает rng. allowed — какие варианты можно выдать здесь (Task.allowed_variants:
    режиму может не хватать среды); номера вне 0..n-1 отбрасываются, пусто — все."""
    if n <= 1:
        return 0
    pool = sorted({v for v in (allowed or ()) if isinstance(v, int) and 0 <= v < n}) \
        or list(range(n))
    if len(pool) == 1:
        return pool[0]
    if prefer in pool:          # FB12 (п. 34): вариант-практика стража — на первом повторе
        return prefer
    history = variant_history(rec, n)
    unseen = [v for v in pool if v not in history]
    if unseen:
        return rng.choice(unseen)
    last_seen = {v: i for i, v in enumerate(history) if v in pool}     # больше — недавнее
    oldest = min(last_seen.values())
    return rng.choice([v for v, i in last_seen.items() if i == oldest])


def clean_text(s) -> str:
    """Строка из песочницы (cmds.log, task.json) или из правленого руками файла — без
    управляющих кодов: ESC-последовательности, BEL, C1 и т.п. в терминал не попадают."""
    return _CTRL.sub("", str(s))


def review_text(s) -> str:
    """Строка снимка: без управляющих кодов (state мог прийти испорченным, progress.json —
    поправлен руками) и не длиннее REVIEW_MAX. Чистит и запись, и вывод дневника."""
    return clean_text(s)[:REVIEW_MAX]


def note_review(rec: dict, variant: Optional[int], solution: str, alts: List[str],
                today: date) -> None:
    """Снимок разбора для дневника: эталон и «можно и так» варианта, как их показал разбор
    (эталон форматируется state песочницы, без неё его не собрать). У варианта — последний."""
    if not isinstance(rec.get("review"), dict):
        rec["review"] = {}
    rec["review"][str(int(variant or 0))] = {
        "sol": review_text(solution),
        "alts": [review_text(a) for a in list(alts)[:REVIEW_ALTS]],
        "day": today.isoformat()}


def note_variant(rec: dict, variant: Optional[int]) -> None:
    """Дописать выданный вариант в историю записи (последние VARIANTS_KEEP) и в множество
    когда-либо выпавших (seen_variants: история короткая, а страж ждёт вариант-практику)."""
    if variant is None:
        return
    rec["seen_variants"] = sorted(set(seen_variants(rec)) | {int(variant)})
    hist = rec.get("variants") if isinstance(rec.get("variants"), list) else []
    rec["variants"] = (hist + [int(variant)])[-VARIANTS_KEEP:]


def seen_variants(rec: Optional[dict]) -> List[int]:
    """Какие варианты задачи у игрока хоть раз выпадали (FB12, п. 34). Старое сохранение без
    seen_variants — по истории variants; запись без истории — только вариант 0."""
    if not rec:
        return []
    raw = rec.get("seen_variants")
    if not isinstance(raw, list):
        raw = rec.get("variants") if isinstance(rec.get("variants"), list) else [0]
    return sorted({v for v in raw if isinstance(v, int) and not isinstance(v, bool) and v >= 0})


def record(p: dict, task_id: str, outcome: str, stars: int, elapsed: float, today: date,
           spell: str = None, boss: bool = False, mode: str = "job",
           practice: bool = False, pay_per_star: int = MONEY_PER_STAR,
           variant: Optional[int] = None, tools: Optional[Iterable[str]] = None,
           hints: Optional[int] = None) -> dict:
    """practice — повтор через play: знакомую освоенную задачу расписание не трогает.
    pay_per_star — оплата звезды дела (выше обычной в «выгодном ране»).
    variant — выданный вариант (его выбрал родитель, а не task.json песочницы)."""
    known = task_id in p["tasks"]
    rec = p["tasks"].setdefault(task_id, {"attempts": 0, "solved": 0, "best": None,
                                          "level": 0, "due": None, "last_stars": 0,
                                          "jobs": 0})
    if not known:       # день первой встречи: next_new чередует места по нему (П3.2)
        rec["first_day"] = today.isoformat()
    note_variant(rec, variant)
    if outcome == "solved" and not rec.get("solved") and "first_time" not in rec:
        # I9: время ПЕРВОГО решения — один раз; старым записям его не выдумываем. tools —
        # утилиты, отработавшие при нём (None — неизвестно): «руками» — только при []
        rec["first_time"] = round(elapsed, 1)
        if tools is not None:
            rec["first_tools"] = sorted(set(tools))
        if hints is not None:       # подсказки и вопросы Сове при нём (M5 финального ревью)
            rec["first_hints"] = int(hints)
    tomorrow = (today + timedelta(days=1)).isoformat()
    rec["attempts"] += 1
    if outcome == "solved":      # срочный заказ не предлагает то, что решено сегодня
        rec["last_solved"] = today.isoformat()
    if mode == "train":
        retrain = rec.get("retrain", False)
        if outcome == "solved":
            rec["solved"] += 1
            _note_best(rec, elapsed)
            p["xp"] += TRAIN_XP
            if spell:
                p["grimoire"][task_id] = spell
        if known and not retrain and (practice or outcome == "solved"):
            return rec          # знакомая задача в тренировке: уровень и срок как были
        rec["level"] = 0
        rec["due"] = tomorrow
        # не освоил (сдался, отложил) — в следующий раз снова тренировка, а не дело
        rec["retrain"] = outcome != "solved"
        return rec
    rec["jobs"] = rec.get("jobs", 0) + 1
    if outcome == "solved":
        rec["solved"] += 1
        _note_best(rec, elapsed)
        p["xp"] += stars * 10 + (50 if boss else 0)
        p["money"] += stars * pay_per_star
        if spell:
            p["grimoire"][task_id] = spell
        if boss and task_id not in p["bosses"]:
            p["bosses"].append(task_id)
            p["money"] += BOSS_MONEY.get(task_id, 100)
    if outcome == "solved" and stars == 3:
        rec["level"] = min(rec["level"] + 1, len(INTERVALS))
        rec["due"] = (today + timedelta(days=INTERVALS[rec["level"] - 1])).isoformat()
    elif outcome == "solved" and stars == 2 and hints == 0:
        # верно и без подсказок, но позже таймера: это не провал (П3.7). Уровень растёт
        # так же, как за ★★★ (так задумано: «освоено» меряет знание, а не скорость), а
        # интервал — середина между прошлым и следующим: растёт медленнее, но растёт
        was = rec["level"]
        rec["level"] = min(was + 1, len(INTERVALS))
        days = (INTERVALS[max(was, 1) - 1] + INTERVALS[rec["level"] - 1]) // 2
        rec["due"] = (today + timedelta(days=days)).isoformat()
    else:
        rec["level"] = 0
        rec["due"] = tomorrow
    if outcome == "giveup":
        rec["retrain"] = True
    elif outcome == "solved":
        rec["retrain"] = False
    rec["last_stars"] = stars
    return rec


def job_stars(rec: dict) -> Optional[int]:
    """Звёзды последнего дела; None — дел ещё не было (задача пройдена только тренировкой).

    Новые записи всегда несут счётчик `jobs`; эвристика ниже — только для старых файлов без него."""
    if "jobs" in rec:
        return rec["last_stars"] if rec["jobs"] else None
    # старый файл без счётчика дел: 0★ при решённой и не заваленной задаче — это тренировка
    if rec.get("last_stars", 0) == 0 and rec.get("solved", 0) > 0 and not rec.get("retrain"):
        return None
    return rec.get("last_stars", 0)


def weak(rec: dict) -> bool:
    """«Подтянуть»: последнее дело дало меньше 3★ с подсказкой или провалом, или задача ждёт
    тренировки. Верно и без подсказок, но позже таймера (★★, уровень вырос — ветка П3.7
    в record) — не слабость (P2 Б8): «освоено» меряет знание, а не скорость."""
    if rec.get("retrain"):
        return True
    stars = job_stars(rec)
    if stars == 2 and (rec.get("level") or 0) > 0:
        return False
    return stars is not None and stars < 3


def new_limit(p: dict, today: date) -> int:
    """Сколько новых задач в ране: первые 7 дней игры — по 2, потом — по 1."""
    before = [d for d in p["days"] if d < today.isoformat()]
    return NEW_FIRST_WEEK if len(before) < FIRST_WEEK_DAYS else NEW_LATER


def tier(track: str) -> int:
    return TIER.get(track, 1)


def hint_price(n: int, track: str = "basics") -> int:
    """Цена подсказки номер n+1 на деле; сверх списка — как последняя (так же считает хук)."""
    return HINT_BASE[min(n, len(HINT_BASE) - 1)] * HINT_TIER.get(track, 1)


def hint_cost(n_used: int, track: str = "basics", free_first: bool = False) -> int:
    """Сколько стоят n_used купленных подсказок; free_first — первая даром (модуль «Кэш»)."""
    return sum(hint_price(i, track) for i in range(1 if free_first else 0, n_used))


def owl_price(track: str = "basics") -> int:
    """Цена вопроса Сове на деле."""
    return OWL_BASE * tier(track)


def can_buy_hint(have: int, n: int, price: int) -> bool:
    """have — баланс за вычетом уже купленного. В долг — любая подсказка дела, пока остаток
    не ниже HINT_CREDIT_FLOOR (K11: застрять без подсказки хуже, чем немного задолжать).
    n оставлен в подписи: его передают хук, мост Совы и симуляция."""
    return have >= price or have - price >= HINT_CREDIT_FLOOR


def charge(p: dict, amount: int, floor: int = 0) -> None:
    """Списать; баланс не опускается ниже floor (и не поднимается, если уже ниже)."""
    p["money"] = min(p["money"], max(floor, p["money"] - amount))


def karma(p: dict) -> int:
    """Карма — прежние очки xp: копится, не тратится, открывает слоты деки."""
    return p["xp"]


def pay_milestone(p: dict, streak_days: int) -> int:
    """Выплата за вехи серии — каждая веха один раз. Платим все неоплаченные вехи не дальше
    текущей серии: заморозка может перескочить через день вехи (6 → 8)."""
    bonus = 0
    for days, pay in sorted(STREAK_MILESTONES.items()):
        if days <= streak_days and days not in p["milestones"]:
            p["milestones"].append(days)
            bonus += pay
    p["money"] += bonus
    return bonus


COOLER_FACTOR = 1.25             # модуль «охладитель»: таймер дел длиннее


def module_on(p: dict, mid: str) -> bool:
    """Модуль деки установлен в слот (куплен — мало, он должен стоять)."""
    return mid in p.get("deck", {}).get("installed", ())


# FB3 (3): «очень мало времени новичкам». Таймер дела на первых треках — с большим запасом:
# «Основы» ×3, «Инструменты» и «Вместо Finder» ×2, следующий ярус («Данные», «Базы данных»,
# «Окружение») ×1,5; дальше — как задано в задаче. Звёзды за время от этого только легче,
# деньги за звезду те же; охладитель (COOLER_FACTOR) умножается поверх.
NOVICE_FACTOR = {"basics": 3.0, "tools": 2.0, "finder": 2.0, "data": 1.5, "db": 1.5, "env": 1.5}


def novice_par(track: str, par: float) -> float:
    """Таймер задачи с запасом новичка по треку (NOVICE_FACTOR)."""
    return par * NOVICE_FACTOR.get(track, 1.0)


def job_par(p: dict, par: float) -> float:
    """Таймер дела с учётом модулей: охладитель растягивает его ×1,25."""
    return par * COOLER_FACTOR if module_on(p, "cooler") else par


def freeze_cap(p: dict) -> int:
    return FREEZE_CAP + (1 if module_on(p, "freezer") else 0)


def buy_freeze(p: dict) -> bool:
    if p["money"] < FREEZE_PRICE or p["freezes"] >= freeze_cap(p):
        return False
    p["money"] -= FREEZE_PRICE
    p["freezes"] += 1
    return True


def seen(p: dict, task_id: str) -> bool:
    return task_id in p["tasks"]


def due(p: dict, today: date) -> List[str]:
    iso = today.isoformat()
    items = [(r["due"], tid) for tid, r in p["tasks"].items() if r.get("due") and r["due"] <= iso]
    return [tid for _, tid in sorted(items)]


def mark_day(p: dict, today: date) -> None:
    iso = today.isoformat()
    if iso not in p["days"]:
        p["days"].append(iso)


def activity(p: dict, today: date, n: int = 7) -> List[int]:
    """Активность по дням (старые → сегодня) для спарклайна: сколько задач решено в последний
    раз в этот день; день рана без таких задач — 1 (ран был). Только для графики."""
    played = set(p.get("days", ()))
    last = {}
    for rec in p.get("tasks", {}).values():
        d = rec.get("last_solved")
        if d:
            last[d] = last.get(d, 0) + 1
    out = []
    for i in range(n - 1, -1, -1):
        iso = (today - timedelta(days=i)).isoformat()
        out.append(max(last.get(iso, 0), 1 if iso in played else 0))
    return out


def next_reward(streak_days: int) -> Optional[int]:
    """День следующей денежной вехи серии (None — все пройдены)."""
    return next((d for d in sorted(STREAK_MILESTONES) if d > streak_days), None)


def best_streak(days: Iterable[str], frozen: Optional[dict] = None) -> int:
    """Самая длинная серия за всю историю: сыгранные дни подряд; день, закрытый заморозкой
    (запись frozen_days), серию не рвёт, но и в счёт не идёт — как в current_streak."""
    ice = {date.fromisoformat(k) for k in clean_frozen(frozen)}
    best = run = 0
    prev = None
    for d in sorted({date.fromisoformat(x) for x in days}):
        gap = (d - prev).days if prev is not None else None
        bridged = gap is not None and all(prev + timedelta(days=k) in ice for k in range(1, gap))
        run = run + 1 if bridged else 1
        best = max(best, run)
        prev = d
    return best


def lost_streak(p: dict, today: date) -> int:
    """Серия, которая оборвалась: сейчас серии нет, а последний сыгранный день её держал
    (2 дня и больше). 0 — терять нечего. Для одной тёплой строки в начале рана (П3.8)."""
    if current_streak(p, today) > 0:
        return 0
    before = [d for d in p.get("days", []) if d < today.isoformat()]
    if not before:
        return 0
    n = streak(before, date.fromisoformat(max(before)), p.get("frozen_days") or {})
    return n if n >= 2 else 0


def clean_frozen(raw) -> dict:
    """Только корректные записи: ключ — дата ISO, значение "free" или "bought"."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if v not in ("free", "bought") or not isinstance(k, str):
            continue
        try:
            out[date.fromisoformat(k).isoformat()] = v
        except ValueError:
            continue
    return out


FROZEN_KEEP = 400      # записи frozen_days старше — удаляются при settle (если не в серии)


def _walk(days: Iterable[str], today: date, frozen: Optional[dict] = None, spare: int = 0,
          extra_freezes: int = 0):
    """Обход серии от сегодня (если сыгран) или вчера назад.
    Возвращает (серия, мосты [(iso, "free"|"bought"|"rec")], день разрыва или None).
    Пропуск: запись frozen — мост; бесплатный мост — если у ISO-недели нет "free" ни в записях,
    ни в этом обходе; extra_freezes — старый алгоритм (купленные чинят любой пропуск);
    spare — купленные, только в открытом промежутке после последнего сыгранного дня."""
    done = {date.fromisoformat(d) for d in days}
    if not done:
        return 0, [], None
    frozen = clean_frozen(frozen)
    free_weeks = {date.fromisoformat(k).isocalendar()[:2]
                  for k, v in frozen.items() if v == "free"}
    before = [d for d in done if d < today]
    anchor = max(before) if before else None
    if today in done:
        # день уже закрыт: settle либо записал мосты промежутка, либо промежуток не закрылся
        # целиком — тогда это разрыв. Запас, пришедший после закрытия (заработанная заморозка),
        # его задним числом не латает: начало рана и итог говорят одно (P2 А2)
        spare = 0
    d = today if today in done else today - timedelta(days=1)
    first, count, bridges = min(done), 0, []
    while d >= first:
        if d in done:
            count += 1
        elif d.isoformat() in frozen:
            bridges.append((d.isoformat(), "rec"))
        else:
            week = d.isocalendar()[:2]
            if week not in free_weeks:
                free_weeks.add(week)
                bridges.append((d.isoformat(), "free"))
            elif extra_freezes > 0:
                extra_freezes -= 1
                bridges.append((d.isoformat(), "bought"))
            elif spare > 0 and anchor is not None and anchor < d < today:
                spare -= 1
                bridges.append((d.isoformat(), "bought"))
            else:
                return count, bridges, d
        d -= timedelta(days=1)
    return count, bridges, None


def streak(days: Iterable[str], today: date, frozen: Optional[dict] = None, spare: int = 0,
           extra_freezes: int = 0) -> int:
    """Дни подряд. Пропуск закрывает запись frozen (уже потраченная заморозка), бесплатная
    заморозка недели (одна на ISO-неделю) или запас spare — но только в открытом промежутке
    после последнего сыгранного дня: прошлый разрыв купленная позже заморозка не чинит.
    extra_freezes — старый алгоритм (до части 7а), нужен только миграции."""
    return _walk(days, today, frozen, spare, extra_freezes)[0]


def current_streak(p: dict, today: date) -> int:
    """Серия игрока; запас заморозок — предпросмотр: до и после закрытия дня число одно."""
    return streak(p.get("days", []), today, p.get("frozen_days") or {}, p.get("freezes", 0))


def settle(p: dict, today: date) -> dict:
    """Закрыть открытый промежуток перед сегодня: бесплатные и купленные мосты пишутся в
    frozen_days, купленные списываются из запаса. Только если промежуток закрывается целиком —
    иначе ничего не пишется и не тратится. Возвращает {"free": [iso], "bought": [iso]}."""
    frozen = p.setdefault("frozen_days", {})
    out = {"free": [], "bought": []}
    days = p.get("days", [])
    before = [x for x in days if x < today.isoformat()]
    later = any(x > today.isoformat() for x in days)
    # часы назад (есть сыгранный день позже сегодня): «промежуток» — прошлый разрыв,
    # его не закрываем, иначе это платный ремонт серии
    if before and not later:
        anchor = date.fromisoformat(max(before))
        _, bridges, stop = _walk(days, today, frozen, p.get("freezes", 0))
        if stop is None or stop < anchor:       # промежуток закрыт целиком
            for x, kind in bridges:
                if kind != "rec" and date.fromisoformat(x) > anchor:
                    frozen[x] = kind
                    out[kind].append(x)
            p["freezes"] = max(0, p.get("freezes", 0) - len(out["bought"]))
            p["freeze_saves"] = p.get("freeze_saves", 0) + len(out["bought"])
    _prune(p, today)
    return out


def _prune(p: dict, today: date) -> None:
    """Убрать записи старше FROZEN_KEEP дней, если они раньше начала нынешней серии."""
    frozen = p.get("frozen_days") or {}
    count, bridges, stop = _walk(p.get("days", []), today, frozen, 0)
    limit = (today - timedelta(days=FROZEN_KEEP)).isoformat()
    reached = [x for x, _ in bridges] + [x for x in p.get("days", []) if x <= today.isoformat()]
    # неделю дня разрыва не трогаем: её "free" и держит разрыв разрывом
    low = (stop - timedelta(days=stop.weekday())).isoformat() if stop is not None \
        else (min(reached) if reached else limit)
    edge = min(limit, low)
    for k in [k for k in frozen if not isinstance(k, str) or k < edge]:
        del frozen[k]


def freezes_spent(p: dict) -> int:
    """Сколько раз купленная заморозка спасла серию: накопительный счётчик, чистка старых
    записей его не уменьшает."""
    n = p.get("freeze_saves", 0)
    return n if isinstance(n, int) and not isinstance(n, bool) else 0


def close_day(p: dict, today: date) -> dict:
    """День засчитан: settle (тратит заморозки за промежуток) + mark_day. Итог settle."""
    res = settle(p, today)
    mark_day(p, today)
    return res


def migrate_freezes(p: dict, today: date) -> None:
    """Файл без frozen_days: мосты старой серии (старый алгоритм, запас — extra_freezes)
    записываются как "free"/"bought", купленные списываются. Старая серия 0 — ничего."""
    frozen = p.setdefault("frozen_days", {})
    have = p.get("freezes", 0)
    count, bridges, _ = _walk(p.get("days", []), today, None, 0, extra_freezes=have)
    if count == 0:
        return
    bought = 0
    for x, kind in bridges:
        frozen[x] = kind
        bought += kind == "bought"
    p["freezes"] = max(0, have - bought)
    p["freeze_saves"] = p.get("freeze_saves", 0) + bought
