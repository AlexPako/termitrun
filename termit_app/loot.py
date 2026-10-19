"""Хабар данных (E17, минимальный v1): файл *.pd в скрытой .cache/.pd песочницы, сдача
командой loot ПУТЬ, тайник в прогрессе и продажа скупщикам (./termit fence).

Как с осколками: родитель кладёт файл до запуска zsh и помнит, что положил (plan). В метке
песочницы (.termit/paydata) только имя и база — sha там нет. Хук находит сданный файл с этим
именем, сам считает sha его содержимого и пишет .termit/looted; родитель после задачи
сверяет этот sha со своим планом. Скопировать метку или переписать файл — ничего не даёт.
Тексты — в теме (fences, fence_ui). Нет скупщиков в теме — хабар не кладётся."""
import glob
import hashlib
import json
import math
import os
import random
import re
from datetime import date
from pathlib import Path
from typing import List, Optional

from termit_app import progress, sandbox, story, theme
from termit_app.tasks import kit

PAYDATA_CHANCE = 0.35                   # на ран, после первого стража
PAYDATA_BASE = {1: 15, 2: 30, 3: 50}    # по ярусу трека задачи-хозяина
FENCE_K = (0.7, 1.3, 2.1)               # курс скупщика: 1 + 0,3·sin(день × k)
REQUIRES = "boss_basics"
META = ".termit/paydata"                # пишет родитель: что лежит в этой песочнице
LOOTED = ".termit/looted"               # пишет хук: игрок вынес верный файл
PD_DIR = ".cache/.pd"
FILE_CAP = 64 * 1024
GLOB_CAP = 50
NO_FENCE = "В этой теме скупщиков нет."


def enabled() -> bool:
    return len(theme.story("fences") or ()) == len(FENCE_K)


def _ui(key: str, default: str) -> str:
    return (theme.story("fence_ui") or {}).get(key) or default


def roll(today: date) -> bool:
    """Жребий дня: детерминирован датой."""
    return random.Random(today.toordinal() ^ 0xDA7A).random() < PAYDATA_CHANCE


def plant_for_run(p: dict, queue: List[str], today: date) -> Optional[str]:
    """Задача рана, в песочницу которой ляжет хабар, или None: первый страж взят, сегодня
    ещё не клали, выпал жребий, в очереди есть безопасный хозяин."""
    if (not enabled() or REQUIRES not in p.get("bosses", ())
            or p.get("paydata_day") == today.isoformat() or not roll(today)):
        return None
    return next((t for t in queue if t in story.SAFE_HOSTS["paydata"]), None)


def plan(seed: int, tier: int = 1) -> dict:
    """Что кладём: имя, содержимое и его sha. Нейтральные строки PD-<hex>."""
    rng = random.Random(seed ^ 0xDA7A)
    name = f"{kit.latin(rng)}_{rng.randint(10, 99)}"
    body = "".join(f"PD-{rng.getrandbits(64):016x}\n" for _ in range(20))
    return {"id": name, "path": f"{PD_DIR}/{name}.pd", "body": body,
            "sha": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "base": PAYDATA_BASE.get(tier, PAYDATA_BASE[1])}


def extras(pd: dict) -> list:
    """Файл хабара в корне песочницы и служебная метка для хука (без sha — его знает
    только родитель)."""
    meta = {"id": pd["id"], "base": pd["base"]}
    return [story.extra("box", pd["path"], pd["body"]),
            story.extra("box", META, json.dumps(meta))]


def claim(box, arg: str, cwd: Optional[str] = None) -> Optional[dict]:
    """Хук: loot ПУТЬ. Путь внутри песочницы, обычный файл (не симлинк) с именем из метки и
    в формате хабара → .termit/looted с sha, который хук посчитал сам по этому файлу.
    Возвращает метку или None. Верен ли sha, решает родитель (collect)."""
    box = Path(box)
    arg = arg.strip()
    meta = story._read_json(box, META)
    if not arg or not meta or not isinstance(meta.get("id"), str):
        return None
    full = os.path.join(cwd or os.getcwd(), os.path.expanduser(arg))
    # loot — noglob (ради кодов осколков), поэтому маску вроде *.pd раскрываем сами
    cands = sorted(glob.glob(full))[:GLOB_CAP] if glob.has_magic(arg) else [full]
    sha = next((x for x in (_file_sha(box, Path(os.path.normpath(c)), meta["id"])
                            for c in cands) if x), None)
    if sha is None:
        return None
    body = json.dumps({"id": meta["id"], "sha": sha}).encode()
    return meta if story.write_mark(box / LOOTED, body) else None


PD_LINE = re.compile(rb"PD-[0-9a-f]{16}")


def _file_sha(box: Path, path: Path, name: str) -> Optional[str]:
    """sha файла хабара: внутри песочницы, не в .termit, имя name.pd, строки PD-<hex>."""
    if (path.name != f"{name}.pd" or not sandbox.inside(path.parent, box)
            or path.parent == box / ".termit"):
        return None
    # путь — от реального корня (/var и /private/var — одно место); дальше read_in_box
    # проходит звенья без симлинков: папка-ссылка наружу не прочтётся
    real_box = Path(os.path.realpath(box))
    try:
        rel = Path(os.path.realpath(path.parent)).relative_to(real_box) / path.name
    except ValueError:
        return None
    raw = sandbox.read_in_box(real_box, rel, FILE_CAP)
    lines = raw.splitlines() if raw else []
    if not lines or not all(PD_LINE.fullmatch(ln) for ln in lines):
        return None
    return hashlib.sha256(raw).hexdigest()


def looted_message() -> str:
    return _ui("looted", "📦 Файл сдан. Дальше — ./termit fence")


def collect(box, p: dict, expect: Optional[dict], today: date) -> Optional[dict]:
    """Родитель после задачи (и при quit): вынесенный хабар — в тайник. Засчитывается
    только файл, положенный в эту песочницу (expect), сверка — по своему ожиданию."""
    if not expect:
        return None
    got = story._read_json(box, LOOTED)
    if not got or got.get("id") != expect["id"] or got.get("sha") != expect["sha"]:
        return None
    return credit(p, expect, today)


def credit(p: dict, expect: dict, today: date) -> Optional[dict]:
    """Сверенный хабар — в тайник (один раз на файл). Общий шаг для collect и симуляции."""
    if any(x.get("id") == expect["id"] for x in p["paydata"]):
        return None
    item = {"id": expect["id"], "base": int(expect["base"]), "day": today.isoformat()}
    p["paydata"].append(item)
    return item


def hint(p: dict) -> Optional[str]:
    """Одноразовая реплика после первого стража: хабар существует и где его искать."""
    text = (theme.story("fence_ui") or {}).get("hint")
    if (not text or not enabled() or "paydata_hint" in p["flags"]
            or REQUIRES not in p.get("bosses", ())):
        return None
    p["flags"].append("paydata_hint")
    return text


def rate(today: date, k: float) -> float:
    return 1 + 0.3 * math.sin(today.toordinal() * k)


def price(base: int, today: date, k: float) -> int:
    return round(base * rate(today, k))


def offer(p: dict, i: int, today: date) -> int:
    """Сколько скупщик i (с нуля) даст сегодня за весь тайник."""
    k = FENCE_K[i]
    return sum(price(int(x.get("base", 0)), today, k) for x in p.get("paydata", ()))


def sell(p: dict, i: int, today: date) -> int:
    """Продать весь тайник скупщику i (с нуля): деньги зачислены, тайник пуст."""
    if not p.get("paydata"):
        return 0
    total = offer(p, i, today)          # IndexError на чужом номере — до любых изменений
    p["money"] += total
    p["paydata"] = []
    return total


def fence_lines(p: dict, today: date) -> List[str]:
    """./termit fence: тайник и три курса на сегодня."""
    if not enabled():
        return [NO_FENCE]
    cash = theme.word("money")
    stash = p.get("paydata", [])
    if not stash:
        return [_ui("empty", "Тайник пуст.")]
    base = sum(int(x.get("base", 0)) for x in stash)
    out = [_ui("title", "Тайник: {n} шт., база {base} {cash}").format(
        n=len(stash), base=base, cash=cash), "", _ui("buyers", "Сегодня дают:")]
    for i, f in enumerate(theme.story("fences")):
        out.append(f"  {i + 1}. {f['name']} — ×{rate(today, FENCE_K[i]):.2f} → "
                   f"{offer(p, i, today)} {cash}")
        out.append(f"     {f['line']}")
    out += ["", _ui("sell", "Продать всё: ./termit fence sell N")]
    return out


def sold_line(name: str, total: int) -> str:
    return _ui("sold", "{name}: +{total} {cash}").format(
        name=name, total=total, cash=theme.word("money"))
