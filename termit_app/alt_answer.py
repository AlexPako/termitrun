"""«Разница:» в разборе — чем решение игрока отличается от эталона (FB5 п. 62).

Владелец 21.10 сдал `ans $(echo $TERM_PROGRAM)` при эталоне `ans $TERM_PROGRAM` и спросил,
как лучше. Разбор должен ответить: «твой ответ тоже верный, а короче так, потому что…».

Как устроено (без модели, только таблица):
- команда режется на звенья (`&&`, `||`, `;`, `|`, `&`) и слова — с учётом кавычек и $( );
- у каждого правила есть переписывание «длинная форма → короткая» (cat f | grep x → grep x f)
  и объяснение простыми словами;
- от ответа игрока идём правилами вперёд, от эталона — назад (только правила с обратным
  текстом), не больше MAX_STEPS шагов с каждой стороны; встретились — строка «Разница»
  собирается из объяснений по пути;
- не встретились — строки нет: лучше промолчать, чем объяснить не ту разницу.

Вид правила (kind) задаёт начало строки: эталон короче, эталон надёжнее, твой короче,
оба равноценны."""
import random
import re
from typing import Callable, Iterable, List, NamedTuple, Optional, Tuple

MAX_STEPS = 3
MAX_STATES = 200            # предохранитель перебора на длинных командах

SEPARATORS = ("&&", "||", ";", "|", "&")

# --- разбор строки ------------------------------------------------------------------------


class Seg(NamedTuple):
    words: Tuple[str, ...]
    sep: str                # разделитель ПОСЛЕ звена ("" у последнего)


Cmd = Tuple[Seg, ...]


def parse(line: str) -> Optional[Cmd]:
    """Строка → звенья со словами. Незакрытая кавычка или скобка — None (молчим)."""
    segs: List[Seg] = []
    words: List[str] = []
    word = ""
    quote = ""
    depth = 0
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if quote:
            word += ch
            if ch == "\\" and quote == '"' and i + 1 < n:
                word += line[i + 1]
                i += 1
            elif ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            word += ch
        elif ch == "\\" and i + 1 < n:
            word += line[i:i + 2]
            i += 1
        elif ch == "(":
            depth += 1
            word += ch
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return None
            word += ch
        elif depth:
            word += ch
        elif ch.isspace():
            if word:
                words.append(word)
                word = ""
        elif ch in "&|;" and not _redirect_amp(line, i, word):
            sep = line[i:i + 2] if line[i:i + 2] in ("&&", "||") else ch
            if word:
                words.append(word)
                word = ""
            if not words:
                return None
            segs.append(Seg(tuple(words), sep))
            words = []
            i += len(sep)
            continue
        else:
            word += ch
        i += 1
    if quote or depth:
        return None
    if word:
        words.append(word)
    if words:
        segs.append(Seg(tuple(words), ""))
    elif segs and segs[-1].sep in (";", "&"):
        segs[-1] = Seg(segs[-1].words, "")     # хвостовая «;» ничего не меняет
    else:
        return None
    return tuple(segs)


def _redirect_amp(line: str, i: int, word: str) -> bool:
    """& внутри перенаправления (2>&1, &>file) — часть слова, а не разделитель."""
    if line[i] != "&":
        return False
    return word.endswith(">") or line[i + 1:i + 2] == ">"


def render(cmd: Cmd) -> str:
    out = ""
    for seg in cmd:
        out += " ".join(seg.words)
        if seg.sep == ";":
            out += "; "
        elif seg.sep:
            out += f" {seg.sep} "
    return out.strip()


# --- сравнение -----------------------------------------------------------------------------

# буквы флагов, которые берут значение следующим словом; команды вне таблицы — слово в слово
_VALUE_FLAGS = {"grep": "efmABCdD", "ls": "", "wc": "", "cp": "", "mv": "", "rm": "",
                "mkdir": "m", "head": "nc", "tail": "nc", "sort": "tko", "uniq": "fs",
                "cut": "dfc", "chmod": ""}


def _canon_seg(seg: Seg):
    words = list(seg.words)
    letters = _VALUE_FLAGS.get(words[0]) if words else None
    if letters is None:
        return seg
    flags, valued, rest = set(), [], []
    i = 1
    while i < len(words):
        w = words[i]
        if re.fullmatch(r"-[A-Za-z]+", w) and not rest:
            for k, ch in enumerate(w[1:]):
                if ch in letters:
                    tail = w[2 + k:]
                    if not tail and i + 1 < len(words):
                        i += 1
                        tail = words[i]
                    valued.append((ch, tail))
                    break
                flags.add(ch)
        else:
            rest.append(w)
        i += 1
    return (words[0], tuple(sorted(flags)), tuple(sorted(valued)), tuple(rest), seg.sep)


def canon(cmd: Cmd):
    """Форма для сравнения: grep -ic и grep -i -c — одна команда."""
    return tuple(_canon_seg(seg) for seg in cmd)


# --- правила -------------------------------------------------------------------------------

SHORT = "short"     # эталон короче
SAFE = "safe"       # эталон надёжнее
MINE = "mine"       # твой короче (обратный ход правила)
SAME = "same"       # оба равноценны


class Rule(NamedTuple):
    key: str
    apply: Callable[[Cmd], Optional[Tuple[Cmd, dict]]]
    kind: str                       # вид при ходе вперёд (у игрока длинная форма)
    text: str                       # объяснение хода вперёд, поля {…} — из apply
    back_kind: Optional[str] = None     # вид при обратном ходе (у игрока короткая форма)
    back_text: Optional[str] = None


def _replace(cmd: Cmd, i: int, segs: Iterable[Seg], count: int = 1) -> Cmd:
    return cmd[:i] + tuple(segs) + cmd[i + count:]


def _alone(cmd: Cmd, i: int) -> bool:
    """Звено не в трубе: ни до, ни после него нет |."""
    return cmd[i].sep != "|" and (i == 0 or cmd[i - 1].sep != "|")


_ECHO_VAR = re.compile(r'"?\$\(\s*echo\s+("?)\$(\{?[A-Za-z_]\w*\}?)\1\s*\)"?')


def _echo_var(cmd: Cmd):
    for i, seg in enumerate(cmd):
        for j, w in enumerate(seg.words):
            m = _ECHO_VAR.search(w)
            if m:
                var = "$" + m.group(2)
                new = w[:m.start()] + var + w[m.end():]
                words = seg.words[:j] + (new,) + seg.words[j + 1:]
                return _replace(cmd, i, [Seg(words, seg.sep)]), {"var": var}
    return None


def _echo_cmd(cmd: Cmd):
    for i, seg in enumerate(cmd):
        if len(seg.words) == 2 and seg.words[0] == "echo" and _alone(cmd, i):
            m = re.fullmatch(r'"?\$\((.+)\)"?', seg.words[1])
            inner = parse(m.group(1)) if m else None
            if inner and len(inner) == 1 and inner[0].words[0] != "echo":
                new = Seg(inner[0].words, seg.sep)
                return _replace(cmd, i, [new]), {"inner": " ".join(new.words)}
    return None


# программы, которые сами читают файл, если дать им имя последним словом
_FILE_READERS = {"grep", "head", "tail", "sort", "uniq", "cut", "awk", "sed", "jq", "less",
                 "wc"}


def _cat_pipe(cmd: Cmd):
    for i, seg in enumerate(cmd[:-1]):
        if seg.sep != "|" or len(seg.words) != 2 or seg.words[0] != "cat":
            continue
        src = seg.words[1]
        if src.startswith("-"):
            continue
        nxt = cmd[i + 1]
        prog = nxt.words[0]
        if prog not in _FILE_READERS or (prog == "jq" and len(nxt.words) < 2):
            continue
        if prog == "wc":        # wc с именем файла печатает и имя — короткая форма через <
            words = nxt.words + ("<", src)
        else:
            words = nxt.words + (src,)
        new = Seg(words, nxt.sep)
        return _replace(cmd, i, [new], 2), {"prog": prog, "short": " ".join(words)}
    return None


def _grep_count(cmd: Cmd):
    for i, seg in enumerate(cmd[:-1]):
        nxt = cmd[i + 1]
        if (seg.sep == "|" and seg.words[0] == "grep" and len(seg.words) > 1
                and "-c" not in seg.words and nxt.words == ("wc", "-l")):
            new = Seg(("grep", "-c") + seg.words[1:], nxt.sep)
            return _replace(cmd, i, [new], 2), {"short": " ".join(new.words)}
    return None


_EXT_PATTERN = re.compile(r"""(['"]?)\\?\.([A-Za-z0-9]+)\$?\1""")


def _ls_grep(cmd: Cmd):
    for i, seg in enumerate(cmd[:-1]):
        nxt = cmd[i + 1]
        if (seg.sep != "|" or seg.words[0] != "ls"
                or any(not w.startswith("-") for w in seg.words[1:])
                or len(nxt.words) != 2 or nxt.words[0] != "grep"):
            continue
        m = _EXT_PATTERN.fullmatch(nxt.words[1])
        if not m:
            continue
        mask = f"*.{m.group(2)}"
        new = Seg(seg.words + (mask,), nxt.sep)
        return _replace(cmd, i, [new], 2), {"mask": mask, "pat": nxt.words[1]}
    return None


def _cd_join(cmd: Cmd):
    for i, seg in enumerate(cmd[:-1]):
        nxt = cmd[i + 1]
        if (seg.sep in ("&&", ";") and len(seg.words) == 2 and len(nxt.words) == 2
                and seg.words[0] == nxt.words[0] == "cd"):
            a, b = seg.words[1], nxt.words[1]
            if a == "-" or b[:1] in ("/", "~", "-", "$") or "$" in a:
                continue
            path = a if a.endswith("/") else a + "/"
            joined = Seg(("cd", path + b), nxt.sep)
            return _replace(cmd, i, [joined], 2), {"path": path + b}
    return None


def _semi_and(cmd: Cmd):
    for i, seg in enumerate(cmd[:-1]):
        if seg.sep == ";":
            return _replace(cmd, i, [Seg(seg.words, "&&")]), {}
    return None


def _cp_rm(cmd: Cmd):
    for i, seg in enumerate(cmd[:-1]):
        nxt = cmd[i + 1]
        if (seg.sep in ("&&", ";") and len(seg.words) == 3 and seg.words[0] == "cp"
                and nxt.words == ("rm", seg.words[1])):
            new = Seg(("mv",) + seg.words[1:], nxt.sep)
            return _replace(cmd, i, [new], 2), {"short": " ".join(new.words)}
    return None


def _dot_slash(cmd: Cmd):
    for i, seg in enumerate(cmd):
        for j, w in enumerate(seg.words[1:], 1):
            if w.startswith("./") and len(w) > 2 and not w.startswith(".//"):
                words = seg.words[:j] + (w[2:],) + seg.words[j + 1:]
                return _replace(cmd, i, [Seg(words, seg.sep)]), {"word": w}
    return None


_PWD_SUB = ("$(pwd)", '"$(pwd)"', "$PWD", '"$PWD"')


def _pwd_dot(cmd: Cmd):
    for i, seg in enumerate(cmd):
        if seg.words[0] in ("cp", "mv") and len(seg.words) >= 3 and seg.words[-1] in _PWD_SUB:
            words = seg.words[:-1] + (".",)
            return _replace(cmd, i, [Seg(words, seg.sep)]), {"sub": seg.words[-1]}
    return None


def _dot_name(cmd: Cmd):
    for i, seg in enumerate(cmd):
        words = seg.words
        if len(words) == 3 and words[0] in ("cp", "mv") and words[2] == ".":
            name = words[1].rstrip("/").rsplit("/", 1)[-1]
            if "/" in words[1].rstrip("/") and name and not re.search(r"[*?\[\]{}$]", name):
                new = Seg(words[:2] + (name,), seg.sep)
                return _replace(cmd, i, [new]), {"src": words[1], "name": name,
                                                 "prog": words[0]}
    return None


def _pwd_var(cmd: Cmd):
    for i, seg in enumerate(cmd):
        for j, w in enumerate(seg.words):
            if "$(pwd)" in w:
                words = seg.words[:j] + (w.replace("$(pwd)", "$PWD"),) + seg.words[j + 1:]
                return _replace(cmd, i, [Seg(words, seg.sep)]), {}
    return None


def _quote_var(cmd: Cmd):
    for i, seg in enumerate(cmd):
        for j, w in enumerate(seg.words[1:], 1):
            m = re.fullmatch(r'"(\$\{?[A-Za-z_]\w*\}?)"', w)
            if m:
                words = seg.words[:j] + (m.group(1),) + seg.words[j + 1:]
                return _replace(cmd, i, [Seg(words, seg.sep)]), {"var": m.group(1)}
    return None


def _home_var(cmd: Cmd):
    for i, seg in enumerate(cmd):
        for j, w in enumerate(seg.words[1:], 1):
            m = re.fullmatch(r'(\$HOME|"\$HOME"|\$\{HOME\})(/.*)?', w)
            if m:
                words = seg.words[:j] + ("~" + (m.group(2) or ""),) + seg.words[j + 1:]
                return _replace(cmd, i, [Seg(words, seg.sep)]), {"word": w}
    return None


def _cd_home(cmd: Cmd):
    for i, seg in enumerate(cmd):
        if seg.words in (("cd", "~"), ("cd", "~/")):
            return _replace(cmd, i, [Seg(("cd",), seg.sep)]), {}
    return None


def _head_n(cmd: Cmd):
    for i, seg in enumerate(cmd):
        w = seg.words
        for j in range(1, len(w) - 1):
            if w[0] in ("head", "tail") and w[j] == "-n" and w[j + 1].isdigit():
                words = w[:j] + ("-" + w[j + 1],) + w[j + 2:]
                return _replace(cmd, i, [Seg(words, seg.sep)]), {"prog": w[0], "n": w[j + 1]}
    return None


def _same_prog_many(prog: str, keep_last: bool):
    """cat a && cat b → cat a b; mv a d && mv b d → mv a b d (последнее слово общее)."""
    def apply(cmd: Cmd):
        for i, seg in enumerate(cmd[:-1]):
            nxt = cmd[i + 1]
            if seg.sep != "&&" or seg.words[0] != prog or nxt.words[0] != prog:
                continue
            a, b = seg.words[1:], nxt.words[1:]
            if not a or not b or any(w.startswith("-") for w in a + b):
                continue
            if keep_last:
                if len(a) < 2 or len(b) < 2 or a[-1] != b[-1]:
                    continue
                words = (prog,) + a[:-1] + b[:-1] + (a[-1],)
            else:
                words = (prog,) + a + b
            new = Seg(words, nxt.sep)
            return _replace(cmd, i, [new], 2), {"short": " ".join(words), "prog": prog}
        return None
    return apply


RULES: Tuple[Rule, ...] = (
    Rule("echo_var", _echo_var, SHORT,
         "переменную {var} zsh подставляет сам — это уже готовое значение. $( ) нужен, "
         "чтобы вставить вывод команды (например, $(pwd)), а echo внутри лишь печатает то, "
         "что zsh и так подставил."),
    Rule("echo_cmd", _echo_cmd, SHORT,
         "echo $(команда) печатает то же, что команда сама: $( ) забирает её вывод, а echo "
         "выводит его обратно. Обёртка лишняя — хватит {inner}."),
    Rule("cat_pipe", _cat_pipe, SHORT,
         "cat тут лишний: {prog} сам читает файл, если дать ему имя, — {short}. "
         "Без трубы от cat — на одну программу меньше."),
    Rule("grep_count", _grep_count, SHORT,
         "grep -c сам считает строки с совпадением, поэтому труба в wc -l не нужна: {short}."),
    Rule("ls_grep", _ls_grep, SHORT,
         "маска {mask} отбирает файлы сразу: zsh сам подставит в ls подходящие имена. "
         "grep {pat} тут лишний, а точка у grep значит «любой знак» — он поймал бы и имя "
         "вроде notatxt."),
    Rule("cd_join", _cd_join, SHORT,
         "cd проходит весь путь за раз: cd {path}. Несколько cd подряд делают то же самое, "
         "только длиннее."),
    Rule("semi_and", _semi_and, SAFE,
         "&& надёжнее, чем ; — команда после && запустится, только если предыдущая прошла "
         "без ошибки, а после ; — в любом случае."),
    Rule("cp_rm", _cp_rm, SHORT,
         "mv переносит одной командой: {short}. cp + rm делают копию и стирают оригинал — "
         "дольше, а если rm не дойдёт, останутся два файла."),
    Rule("dot_slash", _dot_slash, SHORT,
         "./ перед именем не нужен: имя без / и так ищется в текущей папке. ./ обязателен, "
         "только когда запускаешь скрипт, например ./decode.sh."),
    Rule("pwd_dot", _pwd_dot, SHORT,
         "{sub} подставляет полный путь текущей папки, а короче — точка: . и значит "
         "«эта папка»."),
    Rule("dot_name", _dot_name, SAME,
         "{prog} {src} . — то же, что {prog} {src} {name}: в точку («сюда») файл ложится "
         "с тем же именем.",
         SAME,
         "{prog} {src} {name} — то же, что {prog} {src} .: в точку («сюда») файл ложится "
         "с тем же именем."),
    Rule("pwd_var", _pwd_var, SAME,
         "$PWD — переменная, где zsh держит текущую папку, а $(pwd) — вывод команды pwd. "
         "Значение одно и то же.",
         SAME,
         "$PWD — переменная, где zsh держит текущую папку, а $(pwd) — вывод команды pwd. "
         "Значение одно и то же."),
    Rule("quote_var", _quote_var, SAME,
         "кавычки вокруг {var} тут не нужны, но и не мешают: в zsh переменная и без них "
         "не рассыпается на слова.",
         SAME,
         "кавычки вокруг {var} в эталоне — привычка из bash; в zsh переменная и без них "
         "не рассыпается на слова."),
    Rule("home_var", _home_var, SHORT,
         "{word} и ~ — одна и та же домашняя папка, ~ просто короче.",
         SAME,
         "~ и {word} — одна и та же домашняя папка, ~ просто короче."),
    Rule("cd_home", _cd_home, SAME,
         "cd без адреса и так ведёт домой, а ~ — это и есть дом.",
         SAME,
         "cd без адреса и так ведёт домой, а ~ — это и есть дом."),
    Rule("head_n", _head_n, SAME,
         "{prog} -n {n} и {prog} -{n} — одно и то же, -n лишь называет число строк явно.",
         SAME,
         "{prog} -{n} и {prog} -n {n} — одно и то же, -n лишь называет число строк явно."),
    Rule("cat_many", _same_prog_many("cat", keep_last=False), SHORT,
         "cat читает несколько файлов подряд, поэтому хватит одной команды: {short}.",
         MINE,
         "cat сам читает файлы по очереди, а эталон делает то же через && — по команде "
         "на файл."),
    Rule("mv_many", _same_prog_many("mv", keep_last=True), SHORT,
         "mv берёт сразу несколько файлов: всё перед последним словом уедет в папку из "
         "последнего слова — {short}.",
         MINE,
         "mv берёт сразу несколько файлов: всё перед последним словом уедет в папку из "
         "последнего слова."),
    Rule("cp_many", _same_prog_many("cp", keep_last=True), SHORT,
         "cp берёт сразу несколько файлов: всё перед последним словом скопируется в папку "
         "из последнего слова — {short}.",
         MINE,
         "cp берёт сразу несколько файлов: всё перед последним словом скопируется в папку "
         "из последнего слова."),
)

# --- поиск ---------------------------------------------------------------------------------

Step = Tuple[str, str, str]     # (ключ правила, вид, текст)


def _spread(start: Cmd, backward: bool) -> dict:
    """Всё, куда дойти от start за ≤ MAX_STEPS ходов: canon → путь (список Step)."""
    seen = {canon(start): []}
    layer = [(start, [])]
    for _ in range(MAX_STEPS):
        nxt = []
        for cmd, path in layer:
            for rule in RULES:
                if backward and rule.back_text is None:
                    continue
                got = rule.apply(cmd)
                if not got:
                    continue
                new, fields = got
                key = canon(new)
                if key in seen:
                    continue
                kind = rule.back_kind if backward else rule.kind
                text = (rule.back_text if backward else rule.text).format(**fields)
                seen[key] = path + [(rule.key, kind, text)]
                nxt.append((new, seen[key]))
                if len(seen) >= MAX_STATES:
                    return seen
        layer = nxt
    return seen


def explain(mine: str, reference: str) -> Optional[List[Step]]:
    """Цепочка объяснений от ответа игрока к эталону; None — разницы нет или она не
    распознана."""
    a, b = parse(mine or ""), parse(reference or "")
    if not a or not b or canon(a) == canon(b):
        return None
    forward = _spread(a, backward=False)
    backward = _spread(b, backward=True)
    best = None
    for key, path in forward.items():
        if key in backward:
            steps = path + backward[key]
            if steps and (best is None or len(steps) < len(best)):
                best = steps
    return best


# начало строки по виду разницы; вариант — по зерну задачи, чтобы фраза не повторялась
# слово в слово от задачи к задаче
OPENERS = {
    SAFE: ("Твой ответ тоже сработал, но эталон надёжнее.",
           "Сработало и у тебя, а эталон ещё и осторожнее.",
           "Верно, только эталон надёжнее."),
    SHORT: ("Твой ответ тоже верный, а короче так: {ref}.",
            "Сработало и у тебя, но можно короче: {ref}.",
            "Верно, только короче — {ref}."),
    MINE: ("Твой ответ даже короче эталона, и он верный.",
           "Верно — и короче эталона.",
           "Твой вариант короче эталона, результат тот же."),
    SAME: ("Оба способа верны.",
           "Оба варианта правильные.",
           "Тут оба способа равноценны."),
    "mixed": ("Оба ответа верны, разница вот в чём.",
              "Оба варианта сработали, разница вот в чём."),
}


def _cap(text: str) -> str:
    """Заглавная — только у русского слова: имя команды (cd, mv, ./) пишется как в терминале."""
    if re.match(r"[а-яё]", text):
        return text[:1].upper() + text[1:]
    return text


def difference(mine: str, reference: str, seed: int = 0) -> Optional[str]:
    """Текст строки «Разница:» (без самой подписи) или None."""
    steps = explain(mine, reference)
    if not steps:
        return None
    kinds = {kind for _, kind, _ in steps}
    if SAFE in kinds:
        head = SAFE
    elif SHORT in kinds and MINE in kinds:
        head = "mixed"
    elif SHORT in kinds:
        head = SHORT
    elif MINE in kinds:
        head = MINE
    else:
        head = SAME
    pool = OPENERS[head]
    opener = pool[random.Random(seed).randrange(len(pool))]
    ref = " ".join(reference.split())
    texts = []
    for _, _, text in steps:
        if text not in texts:
            texts.append(_cap(text))
    return " ".join([opener.format(ref=ref)] + texts)
