"""FB13 (FB5 п. 45 б): подсказчик привычек. Владелец: «нужно постоянно напоминать, как работать
с хоткеями». После команды хук смотрит пару «прошлая → эта» из cmds.log:
- та же команда ещё раз — «↑ и Enter или !!»;
- последнее слово прошлой команды набрано снова — «Esc, потом точка» (и !$);
- почти та же команда (1–3 знака правки) — «↑ и поправь» или ^старое^новое.
Совет — только если строка набрана руками: zsh песочницы (shell/.zshrc) следит за виджетами
строки и пишет в .termit/typed метку команды и флаг (0 — руками; 1 — ↑, поиск, Esc+., Tab,
вставка, Ctrl+Y или !-подстановка; 2 — неизвестно). Иначе совет сказал бы «перепечатал» тому,
кто как раз нажал ↑.

Не чаще одного совета за задачу; фразы без повторов за всю игру (remarks: память в
p["heard"], пул исчерпан — тишина). Песочница прогресс не пишет: родитель кладёт включатель и
сказанное в BOX_STATE, хук отвечает строкой «вид, отпечаток» в BOX_SAID, родитель после задачи
забирает её (collect), сверив отпечаток с пулом. Выключатель — ./termit coach off."""
import json
from typing import Optional, Tuple

from termit_app import remarks

BOX_STATE = ".termit/coach"
BOX_SAID = ".termit/coach_said"
BOX_TYPED = ".termit/typed"
SETTING = "coach"
KINDS = ("repeat", "last_word", "near")
MIN_LINE = 8        # короче — ↑ не быстрее, чем набрать (ls, pwd, cd ..)
MIN_WORD = 6        # короткое слово (a.txt) быстрее набрать, чем Esc и точку
MAX_EDIT = 3
CLIP = 40
STATE_CAP = 64 * 1024
TIP_MARK = "💡 "

# Пулы: фраза — со своим примером, поля — то, что игрок набрал ({cmd}, {word}, {fix}).
# Шаблон без нужного поля (нет простой замены для ^старое^новое) в этот раз не выбирается.
POOLS = {
    "repeat": (
        "Ту же команду не набирают заново: ↑ вернёт «{cmd}», Enter выполнит.",
        "Повтор прошлой команды — две клавиши: ↑ и Enter. Набирать «{cmd}» второй раз не надо.",
        "«{cmd}» уже лежит в истории. ↑ достанет её целиком, курсор встанет в конце.",
        "!! — это «прошлая команда целиком». Набери !! и Enter — zsh подставит «{cmd}»; "
        "встала в строку и ждёт — Enter ещё раз.",
        "Стрелка ↑ листает историю назад, ↓ — обратно. Одно нажатие ↑ — и «{cmd}» снова в "
        "строке.",
        "Длинное повторяют стрелкой: ↑ и Enter. Пригодится, когда проверяешь, изменилось ли "
        "что-то, — например, после ls.",
        "Совет на будущее: прошлая команда — ↑, команда постарше — ↑ ещё раз. Вместо «{cmd}» "
        "хватило бы одного ↑.",
        "Повторить — не значит перепечатать: !! и Enter (бывает, дважды) делают то же, "
        "что «{cmd}».",
        "Привычка, что экономит минуты: снова то же самое — ↑, Enter. Пальцы отдыхают.",
        "Если команда та же, что секунду назад, ↑ быстрее любой скорости набора: «{cmd}» "
        "вернётся целиком.",
    ),
    "last_word": (
        "«{word}» было последним словом прошлой команды. Нажми Esc, отпусти, потом точку — "
        "zsh вставит его сам.",
        "Последнее слово прошлой команды не печатают заново: Esc, потом «.» подставит "
        "«{word}».",
        "Вместо «{word}» можно набрать !$ — это последнее слово прошлой команды. Например: "
        "cd !$",
        "Esc и точка — «то, чем кончалась прошлая команда». Здесь это «{word}»: две клавиши "
        "вместо пути.",
        "Создал папку — и тут же в неё? cd, пробел, Esc, точка — и путь «{word}» встанет "
        "сам.",
        "Esc и «.» ещё раз подряд — слово из команды постарше. Сейчас хватило бы одного раза: "
        "«{word}».",
        "Путь из прошлой команды можно не набирать: !$ или Esc и точка подставят «{word}». "
        "В русской раскладке Esc и «ю» — то же самое.",
        "Набрал «{word}» второй раз подряд? Esc, потом точка — и опечатки в длинном имени не "
        "будет.",
        "Слово «{word}» zsh уже помнит: Esc, точка — вставка последнего слова прошлой "
        "команды.",
        "Посмотрел файл и правишь его же? Пробел после команды, Esc и точка — «{word}» "
        "на месте.",
    ),
    "near": (
        "Команда почти та же — не перепечатывай: ↑ вернёт прошлую, поправь пару знаков и "
        "Enter.",
        "Замена в прошлой команде — {fix} и Enter: zsh повторит её с заменой.",
        "^старое^новое повторяет прошлую команду с заменой. Здесь хватило бы: {fix}",
        "Поправить прошлую команду быстрее, чем набрать заново: ↑, стрелкой ← к нужному "
        "месту, исправь, Enter.",
        "Отличие от прошлой команды — пара знаков. ↑ и правка — и никакой новой опечатки в "
        "остальном.",
        "Быстрая правка: {fix} — прошлая команда, в которой первое «старое» стало «новым».",
        "↑, потом Option+← прыгает через слово влево — так быстро доберёшься до места "
        "правки.",
        "Почти та же строка? ↑, Ctrl+A — в начало, Ctrl+E — в конец; правка на месте, "
        "Enter.",
        "Вместо новой строки: ↑ и правка. Курсор в строке ходит стрелками, не мышью.",
        "Повтор с заменой в одно слово: {fix}. Пригодится, когда делаешь то же для "
        "соседнего файла.",
    ),
}


def pool_key(kind: str) -> str:
    return f"coach.{kind}"


def _clip(text: str) -> str:
    return text if len(text) <= CLIP else text[:CLIP - 1] + "…"


def distance(a: str, b: str, cap: int = MAX_EDIT) -> int:
    """Расстояние правки (вставка, удаление, замена); больше cap — cap + 1."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return min(prev[-1], cap + 1)


def swap(a: str, b: str) -> Optional[str]:
    """^старое^новое, которое из a делает b (замена первого вхождения, как в zsh), или None.
    Старое расширяем влево, пока первое вхождение не окажется нужным."""
    head = 0
    while head < min(len(a), len(b)) and a[head] == b[head]:
        head += 1
    tail = 0
    while (tail < min(len(a), len(b)) - head and a[-1 - tail] == b[-1 - tail]):
        tail += 1
    end_a, end_b = len(a) - tail, len(b) - tail
    for start in range(head, -1, -1):
        old, new = a[start:end_a], b[start:end_b]
        if any(ch.isspace() or ch == "^" for ch in old + new):
            return None
        if old and a.replace(old, new, 1) == b:
            return f"^{old}^{new}"
        if start == 0 or a[start - 1].isspace():
            return None
    return None


def classify(prev: str, cur: str) -> Optional[Tuple[str, dict]]:
    """Вид совета для пары команд и поля шаблона; None — советовать нечего."""
    a, b = prev.strip(), cur.strip()
    if not a or not b:
        return None
    if a == b:
        return ("repeat", {"cmd": _clip(b)}) if len(b) >= MIN_LINE else None
    # почти та же строка — сначала: правка ↑ полезнее, чем вставка одного слова
    if len(b) >= MIN_LINE and 1 <= distance(a, b) <= MAX_EDIT:
        ctx = {"cmd": _clip(b)}
        fix = swap(a, b)
        if fix and len(fix) <= CLIP:
            ctx["fix"] = fix
        return "near", ctx
    words_a, words_b = a.split(), b.split()
    last = words_a[-1]
    if (len(words_a) >= 2 and len(last) >= MIN_WORD and not last.startswith("-")
            and last in words_b[1:]):
        return "last_word", {"word": _clip(last)}
    return None


# --- песочница: что пишет родитель, что отвечает хук ---------------------------------------

def on(p: dict) -> bool:
    return (p.get("settings") or {}).get(SETTING) is not False


def box_text(p: dict, enabled: bool) -> str:
    """BOX_STATE: включён ли подсказчик в этой задаче и что из пулов уже сказано."""
    sec = p.get(remarks.KEY) if isinstance(p.get(remarks.KEY), dict) else {}
    heard = {remarks._full(pool_key(k)): sec.get(remarks._full(pool_key(k)))
             for k in KINDS}
    return json.dumps({"on": bool(enabled),
                       "heard": {k: v for k, v in heard.items() if isinstance(v, str)}})


def _box_state(box) -> Optional[dict]:
    from termit_app import sandbox
    raw = sandbox._read(box, "coach", STATE_CAP)
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _typed_by_hand(box, stamp: float) -> bool:
    """Флаг zsh для этой самой команды: 0 — набрана руками."""
    from termit_app import sandbox
    raw = sandbox._read(box, "typed") or ""
    parts = raw.strip().split("\t")
    if len(parts) != 2 or parts[1] != "0":
        return False
    try:
        return float(parts[0].replace(",", ".")) == stamp
    except ValueError:
        return False


def advise(box, cmds, service=()) -> Optional[str]:
    """Совет после последней команды или None. cmds — sandbox.read_cmds; service — слова
    тренажёра (task, hint, ans…): они в пары не входят."""
    from termit_app import sandbox
    state = _box_state(box)
    if not state or state.get("on") is not True:
        return None
    if (sandbox._read(box, "coach_said") or "").strip():
        return None                 # один совет за задачу
    mine = [c for c in cmds if c.line.split() and c.line.split()[0] not in service]
    if len(mine) < 2 or not cmds or mine[-1] is not cmds[-1]:
        return None
    cur, prev = mine[-1], mine[-2]
    if not _typed_by_hand(box, cur.t):
        return None
    got = classify(prev.line, cur.line)
    if got is None:
        return None
    kind, ctx = got
    heard = state.get("heard") if isinstance(state.get("heard"), dict) else {}
    fake = {remarks.KEY: {k: v for k, v in heard.items()
                          if isinstance(k, str) and isinstance(v, str)}}
    key = pool_key(kind)
    before = remarks.heard(fake, key)
    text = remarks.pick(fake, key, POOLS[kind], seed=int(cur.t * 1000), ctx=ctx)
    if text is None:
        return None                 # всё сказано — тишина, а не повтор
    new = remarks.heard(fake, key) - before
    if new:
        sandbox.write_box_file(box, BOX_SAID, f"{kind}\t{next(iter(new)).hex()}\n")
    return TIP_MARK + text


def collect(p: dict, box) -> Optional[str]:
    """Сказанное в песочнице — в память реплик (p["heard"]). Строку пишут изнутри: вид и
    отпечаток должны быть из пула, иначе — мимо. Вернуть вид или None."""
    from termit_app import sandbox
    raw = (sandbox._read(box, "coach_said") or "").strip().splitlines()
    if not raw:
        return None
    parts = raw[0].split("\t")
    if len(parts) != 2 or parts[0] not in KINDS:
        return None
    kind, mark = parts
    pool = POOLS[kind]
    match = [x for x in pool if remarks.mark_of(x).hex() == mark]
    if not match:
        return None
    remarks.remember(p, pool_key(kind), match[0], pool)
    return kind
