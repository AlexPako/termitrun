"""Реплики без повторов (FB12-voices, FB5 п. 44 и 46): точная фраза персонажа не звучит дважды
за всю игру. Владелец: «не должно быть вообще повторов… повторы — редко и только смысл, а не
сами фразы».

Как устроено:
- пул — список строк темы или словарь «мысль → строки» (мысль — о чём реплика: скорость, город,
  воспоминание, совет…). Подряд одна и та же мысль у персонажа не идёт;
- память — p["heard"]: {ключ пула: base64 из 4-байтовых отпечатков сказанных строк}. Отпечаток
  — sha1 текста шаблона, поэтому правка запятой в строке делает её новой, а память не держит
  того, чего в пуле больше нет (рост памяти ограничен размером пула);
- пул исчерпан — тишина (None), а не повтор;
- шаблон — строка с полями {…}: подставляется то, что реально было (команда игрока, время,
  серия, сколько до стража, время суток). Шаблон без нужного поля в этот раз не выбирается;
- рядовой повтор задачи (решено, а не первая победа, не рекорд, не сдача, не страж) —
  реплика не каждый раз: после реплики — молчание, после молчания — монетка по seed, после
  двух молчаний — реплика: 40 % среди подряд идущих рядовых повторов, около 25 % в игре
  (первая победа, рекорд, сдача сбрасывают счётчик). Счётчик — p["heard"]["#gap"];
- ключ памяти — с именем темы (remarks._full): смена темы не стирает сказанное.

Прогресс хранит только строки, поэтому раздел переживает любую порчу: не строка — забыта."""
import base64
import hashlib
import random
import string
import zlib
from typing import Dict, Iterable, List, Optional, Tuple

KEY = "heard"
HASH_BYTES = 4
GAP = "#gap"            # молчаний подряд на рядовых повторах
THOUGHT = "@"           # «@трек» — мысль последней реплики персонажа трека
NIGHT_FROM = 22         # с этого часа и до 5 утра — поле {night}
ROUTINE_COIN = 0.5      # после одного молчания реплика — с этой вероятностью (по seed)

Line = Tuple[str, str]  # (мысль, текст); у простого списка мысль — ""


def flat(pool) -> List[Line]:
    """Пул темы в список (мысль, строка): список строк (или пар (мысль, строка)), строка или
    словарь мыслей."""
    if not pool:
        return []
    if isinstance(pool, str):
        return [("", pool)]
    if isinstance(pool, dict):
        out = []
        for thought, xs in pool.items():
            for x in [xs] if isinstance(xs, str) else xs or ():
                if isinstance(x, str) and x:
                    out.append((str(thought), x))
        return out
    out = []
    for x in pool:
        if isinstance(x, str) and x:
            out.append(("", x))
        elif (isinstance(x, tuple) and len(x) == 2 and isinstance(x[1], str) and x[1]):
            out.append((str(x[0] or ""), x[1]))
    return out


def texts(pool) -> List[str]:
    return [x for _, x in flat(pool)]


def mark_of(text: str) -> bytes:
    return hashlib.sha1(text.strip().encode("utf-8")).digest()[:HASH_BYTES]


def _section(p: dict) -> Dict[str, str]:
    sec = p.get(KEY)
    if not isinstance(sec, dict):
        sec = {}
    clean = {k: v for k, v in sec.items() if isinstance(k, str) and isinstance(v, str)}
    p[KEY] = clean
    return clean


def _full(pool_key: str) -> str:
    """Ключ памяти с именем темы: пулы разных тем с одним ключом (basics.solved) не стирают
    память друг друга (remember держит только строки текущего пула)."""
    from termit_app import theme
    return f"{theme.current()}:{pool_key}"


def heard(p: dict, pool_key: str) -> set:
    raw = _section(p).get(_full(pool_key), "")
    try:
        data = base64.b64decode(raw.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        return set()
    return {data[i:i + HASH_BYTES] for i in range(0, len(data) - HASH_BYTES + 1, HASH_BYTES)}


def _store(p: dict, pool_key: str, marks: Iterable[bytes]) -> None:
    data = b"".join(sorted(set(marks)))
    sec = _section(p)
    if data:
        sec[_full(pool_key)] = base64.b64encode(data).decode("ascii")
    else:
        sec.pop(_full(pool_key), None)


def remember(p: dict, pool_key: str, text: str, pool=None) -> None:
    """Строка сказана. pool — весь пул: память держит только отпечатки его строк."""
    marks = heard(p, pool_key) | {mark_of(text)}
    if pool is not None:
        alive = {mark_of(x) for x in texts(pool)}
        marks &= alive
    _store(p, pool_key, marks)


def migrate_said(p: dict, track: str, pool_key: str, pool) -> None:
    """Старое сохранение: p["said"][трек] — последние реплики списком (или строкой). Они
    уходят в память без повторов этого пула, чтобы не прозвучать снова сразу после обновления."""
    said = p.get("said")
    if not isinstance(said, dict) or track not in said:
        return
    old = said.get(track)
    old = [old] if isinstance(old, str) else old if isinstance(old, list) else []
    mine = set(texts(pool))
    hit = [x for x in old if isinstance(x, str) and x in mine]
    if hit:
        _store(p, pool_key, heard(p, pool_key) | {mark_of(x) for x in hit})
    rest = [x for x in old if not (isinstance(x, str) and x in mine)]
    if rest:
        said[track] = rest
    else:
        said.pop(track, None)


def fields(text: str) -> List[str]:
    try:
        return [f for _, f, _, _ in string.Formatter().parse(text) if f]
    except ValueError:
        return ["\0"]       # битый шаблон не выбирается никогда


def render(text: str, ctx: Optional[dict]) -> Optional[str]:
    """Подставить поля шаблона; поля нет в ctx (или оно пустое) — None."""
    need = fields(text)
    if not need:
        return text
    ctx = ctx or {}
    if any(ctx.get(f) in (None, "") for f in need):
        return None
    try:
        out = text.format(**{f: ctx[f] for f in need})
    except (KeyError, IndexError, ValueError):
        return None
    if text.startswith("{") and not text.startswith("{prog"):
        out = out[:1].upper() + out[1:]     # «{za_time} …» → «За 12 секунд …»
    return out


def _rng(seed: int, pool_key: str) -> random.Random:
    return random.Random((int(seed) * 1_000_003) ^ zlib.crc32(pool_key.encode("utf-8")))


def pick(p: dict, pool_key: str, pool, seed: int, ctx: Optional[dict] = None,
         who: Optional[str] = None, remember_it: bool = True,
         lead: bool = False) -> Optional[str]:
    """Несказанная строка пула (шаблон — с подстановкой) или None, если сказать нечего.
    who — чья мысль: подряд одна мысль у него не идёт (ключ «@who»). lead — первая строка
    пула каноническая: пока она не сказана, звучит она."""
    lines = flat(pool)
    if not lines:
        return None
    done = heard(p, pool_key)
    ready = []
    for thought, text in lines:
        if mark_of(text) in done:
            continue
        out = render(text, ctx)
        if out is not None:
            ready.append((thought, text, out))
    if not ready:
        return None
    if lead and ready[0][1] == lines[0][1]:
        if remember_it:
            remember(p, pool_key, ready[0][1], pool)
        return ready[0][2]
    rng = _rng(seed, pool_key)
    last = _section(p).get(THOUGHT + who, "") if who else ""
    fresh = [r for r in ready if not r[0] or r[0] != last] or ready
    by_thought: Dict[str, list] = {}
    for r in fresh:
        by_thought.setdefault(r[0], []).append(r)
    names = sorted(by_thought)
    weights = [len(by_thought[n]) for n in names]
    thought = rng.choices(names, weights)[0]
    choice = rng.choice(by_thought[thought])
    if remember_it:
        remember(p, pool_key, choice[1], pool)
        if who and choice[0]:
            _section(p)[THOUGHT + who] = choice[0]
    return choice[2]


def left(p: dict, pool_key: str, pool) -> int:
    """Сколько строк пула ещё не сказано."""
    done = heard(p, pool_key)
    return sum(1 for x in texts(pool) if mark_of(x) not in done)


# --- Частота: рядовой повтор — не каждый раз ------------------------------------------------

def _gap(p: dict) -> int:
    raw = _section(p).get(GAP, "0")
    return int(raw) if raw.isdigit() else 0


def speaks(p: dict, routine: bool, seed: int, update: bool = True) -> bool:
    """Говорит ли персонаж. Не рядовой случай (первая победа, рекорд, сдача, страж) — всегда.
    Рядовой: сразу после реплики — молчит; после одного молчания — монетка по seed; после двух
    — говорит. Так подряд реплик на повторах нет, а длинной тишины не бывает."""
    if not routine:
        if update:
            _section(p)[GAP] = "0"
        return True
    gap = _gap(p)
    coin = random.Random(int(seed) ^ 0x5EED).random() < ROUTINE_COIN
    say = gap >= 2 or (gap == 1 and coin)
    if update:
        _section(p)[GAP] = "0" if say else str(min(gap + 1, 9))
    return say


def size(p: dict) -> int:
    """Байт памяти в сохранении (для охраны: память не раздувает progress.json)."""
    return sum(len(k) + len(v) for k, v in _section(p).items())


# --- Контекст для шаблонов: числа с правильными падежами -----------------------------------

def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def duration(seconds: float) -> str:
    """«12 секунд», «1 минуту 5 секунд» — винительный падеж (после «за», «на»)."""
    s = max(1, int(round(seconds)))
    m, s = divmod(s, 60)
    parts = []
    if m:
        parts.append(f"{m} {plural(m, 'минуту', 'минуты', 'минут')}")
    if s:
        parts.append(f"{s} {plural(s, 'секунду', 'секунды', 'секунд')}")
    return " ".join(parts)


def daypart(hour: int) -> str:
    """Наречие времени суток: «ночью», «утром», «днём», «вечером»."""
    if hour < 5:
        return "ночью"
    if hour < 11:
        return "утром"
    if hour < 17:
        return "днём"
    return "вечером"


def program(cmd: Optional[str]) -> Optional[str]:
    """Имя программы из команды игрока: первое слово, без пути; служебные слова игры и
    подозрительное (не латиница, слишком длинное) — None: в реплику не годится."""
    if not cmd or not isinstance(cmd, str):
        return None
    head = cmd.strip().split()[:1]
    if not head:
        return None
    name = head[0].rsplit("/", 1)[-1]
    if name in ("ans", "hint", "task", "giveup", "skip", "quit", "reset", "lesson", "bug",
                "sudo", "cd", "echo") or not (1 <= len(name) <= 12):
        return None
    if not all(ch.isascii() and (ch.isalnum() or ch in "-_.") for ch in name):
        return None
    return name


def context(cmd: Optional[str] = None, elapsed: Optional[float] = None,
            gain: Optional[float] = None, streak: Optional[int] = None,
            left_to_boss: Optional[int] = None, hour: Optional[int] = None) -> dict:
    """Поля шаблонов. Нет данных — поля нет, и шаблон с ним в этот раз не выбирается.
      {prog}    — программа из команды игрока: find
      {za_time} — «за 12 секунд»
      {by_gain} — «на 7 секунд» (насколько быстрее прошлого рекорда)
      {streak}  — «3 дня» (серия, от двух дней)
      {left}    — «2 задачи» (до стража места, от одной)
      {daypart} — «ночью», «утром», «днём», «вечером»: только во фразах, верных в любое
                  время суток (тест: вокруг поля нет слов про ночь, сон, утро)
      {night}   — «ночью», и только с 22 до 5 часов: ночные фразы («город спит»); в другое
                  время шаблон не выбирается"""
    ctx = {}
    prog = program(cmd)
    if prog:
        ctx["prog"] = prog
    if isinstance(elapsed, (int, float)) and 1 <= elapsed <= 600:
        ctx["za_time"] = "за " + duration(elapsed)
    if isinstance(gain, (int, float)) and gain >= 1:
        ctx["by_gain"] = "на " + duration(gain)
    if isinstance(streak, int) and streak >= 2:
        ctx["streak"] = f"{streak} {plural(streak, 'день', 'дня', 'дней')}"
    if isinstance(left_to_boss, int) and left_to_boss >= 1:
        ctx["left"] = f"{left_to_boss} {plural(left_to_boss, 'задача', 'задачи', 'задач')}"
    if isinstance(hour, int) and 0 <= hour <= 23:
        ctx["daypart"] = daypart(hour)
        if hour < 5 or hour >= NIGHT_FROM:
            ctx["night"] = "ночью"
    return ctx
