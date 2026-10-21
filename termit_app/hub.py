"""Убежище — командная строка игры (хаб). Тонкий слой: каждое слово превращается в обычный
argv и уходит в cli.run_once, как ./termit СЛОВО. Таблица WORDS — единственный источник
слов: из неё строятся help, Tab, строка подсказки и «может, home?»."""
import difflib
import os
import shlex
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from termit_app import (cli, commands, edition, hideout, hubline, hubview, layout, loot, music,
                        paths, progress, pyenvs, story, theme, tui, ui)
from termit_app.hubline import LINE_MAX
from termit_app.implants import STUB_NAME     # «brew» — только из implants (охрана I-2)
from termit_app import book as book_mod
from termit_app import shop as shop_mod
from termit_app import train as train_mod
from termit_app.tasks import registry

PROMPT = "убежище › "


@dataclass(frozen=True)
class Word:
    name: str
    argv: Tuple[str, ...]
    group: str                      # play | home | story | help | settings | hub
    args_hint: str = ""
    rule: Optional[str] = None      # ключ open_map; None — открыто всегда
    aliases: Tuple[str, ...] = ()
    own: bool = False               # слово самого хаба, в cli не уходит


WORDS = (
    Word("run", ("dozor",), "play"),
    Word("short", ("short",), "play"),
    Word("new", ("new",), "play", aliases=("more",)),
    Word("train", ("train",), "play", "[ТЕМА|ID|exam|keys]", aliases=("play",)),
    Word("master", ("master",), "play", rule="master"),
    Word("rehearse", ("rehearse",), "play", "ID", rule="rehearse"),
    Word("home", ("home",), "home"),
    Word("look", ("home", "look"), "home", "ВЕЩЬ"),
    Word("board", ("home", "board"), "home", rule="board"),
    Word("prompt", ("home", "prompt"), "home", rule="prompt"),
    Word("palette", ("home", "palette"), "home", "ID", rule="palette"),
    Word("callsign", ("home", "callsign"), "home", "ИМЯ", rule="callsign"),
    Word("shop", ("shop",), "home", "[ID|all]"),
    Word("deck", ("deck",), "home", "[on|off ID]", rule="deck"),
    Word("case", ("case",), "story", rule="case"),
    Word("dossier", ("dossier",), "story", "[ИМЯ]", rule="dossier"),
    Word("memory", ("memory",), "story", rule="memory"),
    Word("diary", ("diary",), "story", "[N]", rule="diary"),
    Word("map", ("map",), "story"),
    Word("fence", ("fence",), "story", "[sell N]", rule="fence"),
    Word("inbox", ("inbox",), "story", "[N|next]"),
    Word("book", ("book",), "help", "[слово]"),
    Word("keys", ("keys",), "help"),
    Word("ext", ("ext",), "help"),
    Word("stats", ("stats",), "help"),
    Word("list", ("list",), "help"),
    Word("intro", ("intro",), "help"),
    Word("feedback", ("feedback",), "help"),
    Word("report", ("report",), "help", rule="report"),
    Word("style", ("style",), "settings", "[ВИД ID]", rule="style"),
    Word("music", ("music",), "settings", "[play ID]", rule="music"),
    Word("sound", ("sound",), "settings", "[on|off]"),
    Word("theme", ("theme",), "settings", "[ИМЯ]"),
    Word("owl", ("owl",), "settings", "[on|off]", rule="owl"),
    Word("coach", ("coach",), "settings", "[on|off]"),
    Word("implants", ("implants",), "settings", rule="implants"),
    Word("wheels", ("wheels",), "settings", "[get]", rule="wheels"),
    Word("update", ("update",), "settings"),
    Word("hub", (), "hub", own=True),
    Word("help", (), "hub", "[СЛОВО]", own=True),
    Word("clear", (), "hub", own=True),
    Word("quit", (), "hub", aliases=("exit", "q"), own=True),
)

# команды ./termit, которых нет в убежище, — с причиной (охранный тест сверяет с ABOUT)
HUB_SKIP = {
    "track": "из убежища убран: новое приходит только с раном и new (спека 2.2)",
    "play": "синоним train в убежище (спека 2.2)",
}

# короткая расшифровка слова — на пульте и в help рядом со словом (владелец 21.10:
# «не хватает расшифровки команд»); подробно — help СЛОВО
SHORT = {
    "run": "ран дня, ~10 минут",
    "short": "короткий ран",
    "new": "ещё урок сверх нормы",
    "train": "отработать слабое",
    "master": "знакомое на время",
    "rehearse": "репетиция стража",
    "home": "твоя комната и вещи",
    "look": "осмотреть вещь",
    "board": "доска подсказок",
    "prompt": "своё приглашение zsh",
    "palette": "цвет приглашения",
    "callsign": "твой позывной",
    "shop": "витрина: купить",
    "deck": "модули деки",
    "case": "доска дела",
    "dossier": "досье персонажей",
    "memory": "осколки памяти",
    "diary": "уроки и разборы",
    "map": "карта мест",
    "fence": "тайник: продать хабар",
    "inbox": "сообщения на деке",
    "book": "выученные команды",
    "keys": "клавиши терминала",
    "ext": "расширения файлов",
    "stats": "звание, серия, счёт",
    "list": "все задачи",
    "intro": "вступление ещё раз",
    "feedback": "твои замечания",
    "report": "карточка замечания",
    "style": "рамки и стиль",
    "music": "музыка",
    "sound": "звуки",
    "theme": "тема оформления",
    "owl": "Сова-подсказчица",
    "coach": "подсказчик привычек",
    "implants": "утилиты",
    "wheels": "пакеты Python",
    "update": "обновить игру",
    "hub": "показать пульт",
    "help": "все слова подробно",
    "clear": "очистить экран",
    "quit": "выйти из игры",
}

# группы help: порядок групп и заголовки (слово — в группе из Word.group)
GROUPS: Tuple[Tuple[str, str], ...] = (
    ("play", "Играть"),
    ("home", "Дом"),
    ("story", "История"),
    ("help", "Справка"),
    ("settings", "Настройки"),
    ("hub", "Убежище"),
)

# команды задачи, которые игрок по привычке набирает в убежище, — с подсказкой, что здесь
TASK_ONLY = {
    "lesson": "lesson — мини-урок внутри задачи. Новый урок здесь — слово new.",
}

HUB_ABOUT = {
    "run": "ран дня на ~10 минут — главное дело дня",
    "hub": "показать пульт заново",
    "help": "все открытые слова; help СЛОВО — подробно об одном",
    "clear": "очистить экран",
    "quit": "выйти из игры (Ctrl+D — то же)",
}

CLOSED = {
    "master": "Круг мастера откроется, когда решишь первое задание.",
    "rehearse": "Репетиция откроется, когда встретишь первого стража.",
    "board": "Доска откроется после первого решённого задания.",
    "prompt": "Своё приглашение откроется, когда появится первая деталь для него.",
    "palette": "Палитры откроются, когда купишь первую на витрине.",
    "callsign": "Позывной откроется, когда купишь его на витрине.",
    "deck": "Дека откроется после первого стража или с первым модулем.",
    "case": "Доска дела откроется после первого стража.",
    "dossier": "Досье откроется, когда купишь первую страницу на витрине.",
    "memory": "Осколки памяти появятся по ходу рана — найдёшь первый, и слово откроется.",
    "diary": "Дневник откроется после первого задания.",
    "fence": "Тайник откроется, когда вынесешь первый хабар.",
    "report": "В этой копии игры карточек нет: замечание — bug внутри задачи.",
    "style": "Стиль откроется, когда купишь первую вещь стиля.",
    "music": "Музыка откроется, когда купишь деку-плеер.",
    "owl": "Сова откроется после первого рана.",
    "implants": "Утилиты откроются после урока установки.",
    "wheels": "Склад пакетов откроется вместе с треком «Python».",
}

NO_PREFIX = "В убежище ./termit не нужен — достаточно слова."
LAYOUT_NOTE = "Похоже, включена русская раскладка — понял как «{word}»."
NOT_TERMINAL = ("Это убежище: тут свои короткие слова. Команды терминала (ls, cd, cat…) "
                "пробуют в задании — run или train.")
UNKNOWN = "Не знаю слова «{word}»."
MAYBE = " Может, {word}?"
HELP_TAIL = " Все слова — help."

TERMINAL = frozenset((
    "ls", "cd", "pwd", "cat", "mkdir", "rmdir", "rm", "mv", "cp", "echo", "open", "git",
    STUB_NAME, "python", "python3", "pip", "pip3", "touch", "less", "head", "tail", "grep",
    "find", "sudo", "man", "chmod", "nano", "vim", "code", "ln", "du", "df", "ps", "kill",
    "top", "which", "wc", "sort", "tree", "zsh", "bash", "exit()",
))


def find(name: str) -> Optional[Word]:
    for w in WORDS:
        if name == w.name or name in w.aliases:
            return w
    return None


def open_map(p: dict) -> Dict[str, bool]:
    """Что игроку уже открыто — те же правила, что справка (cli._opened) и дом (_hub_open)."""
    on = dict(cli._opened(p))
    home = cli._hub_open(p)
    on.update({k: v for k, v in home.items() if not k.startswith("home ")})
    on["board"] = home["home board"]
    on["prompt"] = home["home prompt"]
    on["palette"] = bool(hideout.palettes(p))
    on["report"] = bool(edition.ISSUES_URL)
    return on


def is_open(word: Word, p: dict) -> bool:
    return word.rule is None or open_map(p).get(word.rule, False)


def open_words(p: dict) -> List[Word]:
    on = open_map(p)
    return [w for w in WORDS if w.rule is None or on.get(w.rule, False)]


def about(word: Word) -> str:
    if word.own or word.name == "run":
        return HUB_ABOUT[word.name]
    if word.argv[0] == "home" and len(word.argv) > 1:
        return commands.HOME_ABOUT[word.argv[1]][1]
    return commands.about(word.argv[0])


NO_STORY = "В этой теме этого нет."
_NEEDS_STORY = ("case", "dossier", "memory")


def closed_text(word: Word) -> str:
    """Почему слово закрыто. Если в теме нет сюжета или добычи, обещание «откроется»
    было бы ложным — говорим, что этого здесь нет."""
    if word.rule in _NEEDS_STORY and not story.has_story():
        return NO_STORY
    if word.rule == "fence" and not (story.has_story() and loot.enabled()):
        return NO_STORY
    return CLOSED.get(word.rule or "", f"«{word.name}» пока закрыто — откроется по ходу игры.")


@dataclass
class Action:
    kind: str                       # empty | word | own | quit | say
    name: str = ""
    argv: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    note: str = ""
    text: str = ""


CHAIN_STOP = "Дальше по цепочке не иду: прошлое слово не получилось (после && — только при успехе)."
CHAIN_OPS = ("&&", ";")


def split_chain(text: str) -> List[Tuple[str, str]]:
    """«shop a && shop b; stats» → [("", "shop a"), ("&&", "shop b"), (";", "stats")]: связки
    вне кавычек, как в zsh; пустые куски (хвостовое &&) выбрасываются."""
    parts, buf, op, quote, k = [], "", "", "", 0
    while k < len(text):
        ch = text[k]
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        else:
            sep = next((s for s in CHAIN_OPS if text.startswith(s, k)), "")
            if sep:
                parts.append((op, buf.strip()))
                buf, op, k = "", sep, k + len(sep)
                continue
        buf += ch
        k += 1
    parts.append((op, buf.strip()))
    return [(o, t) for o, t in parts if t]


def _split(text: str) -> List[str]:
    try:
        return shlex.split(text)
    except ValueError:              # непарная кавычка — делим по пробелам
        return text.split()


def _terminal_like(parts: List[str], text: str) -> bool:
    head = parts[0]
    return (head in TERMINAL or "/" in head or head.startswith("-")
            or any(ch in text for ch in "|><&$`"))


def parse_line(line: str, p: dict) -> Action:
    """Строка игрока → действие. Чистая функция: без ввода-вывода (спека 2.1, eng §1.3)."""
    text = line.strip()
    parts = [x for x in _split(text) if x] if text else []
    if not parts:
        return Action("empty")
    note = ""
    if parts[0] in ("./termit", "termit", "./termitrun", "termitrun"):
        parts = parts[1:]
        note = NO_PREFIX
        if not parts:
            return Action("empty", note=note)
    head = parts[0].lower()
    word = find(head)
    if word is None and layout.has_cyrillic(head):
        guess = find(layout.to_qwerty(head).lower())
        if guess is not None:
            word = guess
            note = LAYOUT_NOTE.format(word=guess.name)
    if word is None and head in TASK_ONLY:
        return Action("say", text=TASK_ONLY[head])
    if word is None:
        if _terminal_like(parts, text):
            return Action("say", text=NOT_TERMINAL)
        near = difflib.get_close_matches(head, [w.name for w in open_words(p)], n=1,
                                         cutoff=0.6)
        tail = MAYBE.format(word=near[0]) if near else HELP_TAIL
        return Action("say", text=UNKNOWN.format(word=head) + tail)
    if not is_open(word, p):
        return Action("say", name=word.name, text=closed_text(word))
    args = parts[1:]
    if word.name == "quit":
        return Action("quit", name="quit", note=note)
    if word.own:
        return Action("own", name=word.name, args=args, note=note)
    return Action("word", name=word.name, argv=list(word.argv) + args, args=args, note=note)


def _help_row(word: Word) -> List[str]:
    label = word.name + (f" {word.args_hint}" if word.args_hint else "")
    return ui.story_fill(f"{label.ljust(22)} {about(word)}", "  ", " " * 25).splitlines()


BOOK_HEAD = "«{word}» — не слово убежища. В книге выученного:"


def _book_lines(p: dict, name: str) -> List[str]:
    """help ТЕРМИН: команда терминала из книги выученного (то же, что book ТЕРМИН)."""
    found = book_mod.lines(book_mod.sections(p), name)
    if not found:
        return []
    return [BOOK_HEAD.format(word=name)] + [line.lstrip("\n") for line in found]


CLOSED_HEAD = "  Закрыто:"
CLOSED_TAIL = "help СЛОВО — когда откроется."


def closed_words(p: dict) -> List[Word]:
    """Закрытые слова, которые ещё откроются: без тех, что в этой теме или копии игры
    не появятся никогда (владелец 21.10: «не все команды в хабе указаны»)."""
    return [w for w in WORDS if not is_open(w, p) and closed_text(w) != NO_STORY
            and not (w.rule == "report" and not edition.ISSUES_URL)]


HELP_HEAD = "Слова убежища (Enter — то, что отмечено ⏎; help СЛОВО — подробно):"


def help_lines(p: dict, name: str = "", width: Optional[int] = None) -> List[str]:
    """help — открытые слова по группам, у каждого короткая расшифровка (в две колонки, если
    окно позволяет); закрытые — именами; help СЛОВО — подробно об одном (закрытое объясняет,
    когда откроется); не слово, но есть в книге — строки книги."""
    width = width or tui.caps().width
    if name:
        word = find(name.lower())
        if word is None:
            book = _book_lines(p, name)
            if book:
                return [tui.trunc(line, width) for line in book]
            return [UNKNOWN.format(word=name) + HELP_TAIL]
        if not is_open(word, p):
            return [closed_text(word)]
        out = _help_row(word)
        if word.aliases:
            out.append("  то же: " + ", ".join(word.aliases))
        return out
    words = open_words(p)
    out = tui.fill(HELP_HEAD, width)
    longest = max(tui.vlen(_cell(w.name)) for w in words)     # одна сетка на все группы
    for group, title in GROUPS:
        names = [w.name for w in words if w.group == group]
        if names:
            out += _short_rows("  " + (title + ":").ljust(12), names, width, longest)
    closed = [w.name for w in closed_words(p)]
    if closed:
        out += _group_rows(CLOSED_HEAD.ljust(14), closed, width)
        out.append(" " * 14 + CLOSED_TAIL)
    return [tui.trunc(line, width) for line in out]


def _cell(name: str) -> str:
    return f"{name.ljust(9)} {SHORT[name]}"


def _short_rows(head: str, names: List[str], width: int, longest: int) -> List[str]:
    """Группа слов с расшифровкой: «слово  что делает» ячейками общей ширины; ячеек в строке —
    сколько влезает в окно (у последней хвостовой отступ не нужен)."""
    step = longest + 3
    per_row = max(1, (width - len(head) - longest) // step + 1)
    rows = []
    for k in range(0, len(names), per_row):
        part = [_cell(n) for n in names[k:k + per_row]]
        line = "".join(tui.pad(c, step) for c in part[:-1]) + part[-1]
        rows.append((head if k == 0 else " " * len(head)) + line)
    return rows


def _group_rows(head: str, names: List[str], width: int = 78) -> List[str]:
    """Строка группы: слова через « · »; не влезло — перенос целым словом под первое слово
    (точка остаётся в конце строки, а не в начале следующей)."""
    rows = []
    line = head
    for i, name in enumerate(names):
        piece = name + (" ·" if i < len(names) - 1 else "")
        if line != head and len(line) + 1 + len(piece) > width:
            rows.append(line)
            line = " " * len(head)
        line += piece if line.endswith(" ") else " " + piece
    rows.append(line)
    return rows


def _open_task_ids(p: dict) -> List[str]:
    """Ids задач только открытых мест: закрытое издание (edition.OPEN_TRACKS) не подсказываем."""
    keys = {t.key for t in registry.unlocked(p.get("bosses", ()))}
    tasks = registry.all_tasks()
    return [t for t in p.get("tasks", {}) if t in tasks and tasks[t].track in keys]


def _rehearse_ids(p: dict) -> List[str]:
    tasks = registry.all_tasks()
    return [t for t in _open_task_ids(p) if tasks[t].boss]


def _train_args(p: dict) -> List[str]:
    """Tab после train: exam, места, команды и id — как отбирает сама отработка (F16):
    ни закрытых мест, ни стражей. Доступность — по кэшу, без подпроцессов."""
    with pyenvs.cache_only():
        ids = train_mod.candidates(p, date.today())
    return ["exam", train_mod.KEYS] + train_mod.places(p) + train_mod.commands_of(p) + sorted(ids)


# аргументы для Tab после слова; невстреченное не предлагаем (спойлер и тупик)
ARG_SOURCES: Dict[str, Callable[[dict], List[str]]] = {
    "look": lambda p: hideout.owned_items(p),
    "inbox": lambda p: ["next"] + [str(m["id"]) for m in p.get("inbox") or []],
    "shop": lambda p: ["all"] + [i.id for i in shop_mod.visible(p, date.today())],
    "theme": lambda p: list(theme.available()),
    "help": lambda p: [w.name for w in open_words(p)],
    "home": lambda p: list(commands.HOME_ABOUT),
    "music": lambda p: ["play", "stop", "vol", "preview", "run"],
    "sound": lambda p: ["on", "off", "test", "pack", "vol"],
    "coach": lambda p: ["on", "off"],
    "train": lambda p: _train_args(p),
    "rehearse": _rehearse_ids,
}


def candidates(before: str, p: dict) -> List[str]:
    """Что дописать Tab: before — строка до курсора. Первое слово — открытые слова хаба,
    второе — аргументы из ARG_SOURCES."""
    parts = before.lstrip().split(" ")
    if len(parts) == 1:
        head = parts[0].lower()
        return sorted(w.name for w in open_words(p) if w.name.startswith(head))
    if len(parts) != 2:
        return []
    word = find(parts[0].lower())
    if word is None or not is_open(word, p) or word.name not in ARG_SOURCES:
        return []
    return sorted(x for x in ARG_SOURCES[word.name](p) if x.startswith(parts[1]))


BYE = "До встречи. Возвращайся — убежище никуда не денется."
CTRL_C_HINT = "Строка стёрта. Выйти — quit или Ctrl+D."
EMPTY_HINT = "Набери слово и Enter. Все слова — help, выйти — quit."
TOO_LONG = f"Слишком длинная строка — в убежище слова короткие (до {LINE_MAX} знаков)."
IN_TASK = cli.IN_TASK_HUB
BROKE = ("Что-то пошло не так, но убежище цело. Подробности для разработчика — "
         "в .cache/hub-errors.log.")
CLEAR = "\033[H\033[2J"
BACK = "в убежище: Enter "
# слова, после которых игрок был в задачах: терминал и музыку приводим в порядок
RUN_WORDS = frozenset(("run", "short", "new", "master", "rehearse", "train"))


class Hub:
    """Цикл убежища. Ничего игрового в памяти не держит: прогресс и тема — с диска перед
    каждым словом (две вкладки и полночь не мешают, спека 2.8)."""

    def __init__(self, reader, flags=frozenset(), theme_flag=None, strict=False, tty=False,
                 remember=None, autostart=None):
        self.reader = reader
        self.remember = remember
        self.saved_term = None
        self.tab_p = None           # прогресс для Tab - один раз на приглашение
        self.flags = set(flags)
        self.theme_flag = theme_flag
        self.strict = strict
        self.tty = tty
        # первый запуск сам открывает задачу только в настоящем терминале: из трубы zsh бессмыслен
        self.autostart = tty if autostart is None else autostart
        self.last_day = None
        self.ok = True              # удалось ли прошлое слово — для цепочки через &&
        self.board_above = False    # пульт только что показан: слова уже на экране

    def load(self) -> dict:
        p = progress.load(paths.PROGRESS_FILE)
        theme.use(self.theme_flag or p.get("settings", {}).get("theme"))
        return p

    def loop(self) -> int:
        with commands.hub_mode():
            return self._loop()

    def _loop(self) -> int:
        self.saved_term = hubline.term_save() if self.tty else None
        started = False
        if self.autostart and not self.load()["intro_seen"]:    # первый запуск — сразу в задачу
            started = self.guarded(lambda: self.step("run"))    # step сам покажет пульт
        if not started:
            self.guarded(self.show_board)
        self.last_day = hubview.today()
        while True:
            try:
                self.safe_hint()
                self.tab_p = self.load()
                try:
                    line = self.reader(PROMPT)
                except EOFError:
                    ui.say()            # libedit печатает ^D без перевода строки
                    break
                except KeyboardInterrupt:
                    ui.say()
                    ui.say(CTRL_C_HINT)
                    continue
                if len(line) > LINE_MAX:
                    ui.say(TOO_LONG)
                    continue
                if self.remember and line.strip():
                    self.remember(line)
                if not self.step(line):
                    break
            except KeyboardInterrupt:
                ui.say()
                ui.say(cli.INTERRUPTED)
            except Exception as exc:        # noqa: BLE001 - одна команда хаб не роняет
                self.broke(exc)
        ui.say(BYE)
        return 0

    def broke(self, exc: Exception) -> None:
        if self.strict:
            raise exc
        hubline.log_error(exc)
        ui.bad(BROKE)

    def guarded(self, action: Callable[[], object]) -> bool:
        """Действие вне цикла (первый запуск, пульт при входе) с той же защитой, что у слова.
        True — выполнилось без падения."""
        try:
            action()
            return True
        except KeyboardInterrupt:
            ui.say()
            ui.say(cli.INTERRUPTED)
        except Exception as exc:        # noqa: BLE001 - первый запуск хаб не роняет
            self.broke(exc)
        return False

    def step(self, line: str) -> bool:
        """Строка убежища; цепочка через && и ; — слова по очереди, как в терминале
        (владелец 21.10). False — выйти из убежища."""
        chain = split_chain(line)
        if len(chain) < 2:
            return self.step_one(line)
        for op, part in chain:
            if op == "&&" and not self.ok:
                ui.say(CHAIN_STOP)
                break
            if not self.step_one(part):
                return False
        return True

    def step_one(self, line: str) -> bool:
        self.ok = True
        p = self.load()
        act = parse_line(line, p)
        if act.note:
            ui.say(act.note)
        if act.kind == "quit":
            return False
        if act.kind == "empty":
            return self.enter()
        elif act.kind == "say":
            self.ok = False
            ui.say(act.text)
        elif act.kind == "own":
            self.own(act)
        else:
            run = act.name in RUN_WORDS
            music_before = music.playing() if run else None
            code = 1
            try:
                code = self.run_word(act.argv)
                self.ok = code == 0
            finally:
                # даже если слово упало: терминал и музыка дома приходят в порядок
                if run:
                    self.after_run(music_before, code == 0)
            if run:
                self.show_board()
        return True

    def show_board(self) -> None:
        p = self.load()
        if self.tty and tui.caps().level != "plain":
            sys.stdout.write(CLEAR)
            sys.stdout.flush()
        if p["intro_seen"] and not p["hub"]["tour"]:
            ui.say(ui.story_fill(hubview.TOUR, "  ", "  "))
            ui.say()
            names = [w.name for w in open_words(p)]
            self.mark_shown(hubview.tour_shown(p, names), tour=True)
            p = self.load()
        day = hubview.today()
        for line in hubview.board(p, day):
            ui.say(line)
        ui.say()
        for line in help_lines(p):          # владелец 21.10: все слова — на виду
            ui.say(line)
        self.board_above = True
        self.last_day = day         # пульт уже на сегодняшнюю дату: «новый день» не повторять

    def mark_shown(self, names, tour=None) -> None:
        """Показанные в подсказке слова — в прогресс (короткий цикл load → save)."""
        if not paths.PROGRESS_FILE.exists():
            return
        q = progress.load(paths.PROGRESS_FILE)
        q["hub"]["shown"] += [n for n in names if n not in q["hub"]["shown"]]
        if tour is not None:
            q["hub"]["tour"] = tour
        progress.save(paths.PROGRESS_FILE, q)

    def safe_hint(self) -> None:
        """Подсказка не должна лишать приглашения: сбой (диск только для чтения, нет места)
        — в лог, без BROKE, и приглашение показывается всё равно."""
        try:
            self.hint()
        except Exception as exc:        # noqa: BLE001 - подсказка не важнее приглашения
            if self.strict:
                raise
            hubline.log_error(exc)

    def hint(self) -> None:
        day = hubview.today()
        if self.last_day is not None and day != self.last_day:
            ui.say(hubview.NEW_DAY)
            self.show_board()
        self.last_day = day
        p = self.load()
        names = [w.name for w in open_words(p)]
        fresh = hubview.fresh_words(p, names)
        # пульт прямо над приглашением уже перечислил слова — тогда только ⏎, новое и quit
        words = () if self.board_above else names
        self.board_above = False
        ui.say(ui.c("36", hubview.hint_line(p, day, fresh, words, SHORT)))
        if fresh and p["hub"]["tour"]:
            self.mark_shown(fresh[:4])

    def enter(self) -> bool:
        line, _ = hubview.default_action(self.load(), hubview.today())
        if line == "hub":
            self.show_board()
            return True
        return self.step(line)

    def after_run(self, music_before: Optional[str], ran: bool = True) -> None:
        """После вылазки: терминал как при входе, музыка дома снова играет, лишние Enter
        из итога - прочь; в терминале после настоящего рана один Enter, чтобы дочитать итог (спека 2.4)."""
        hubline.term_restore(self.saved_term)
        if music_before and music.playing() != music_before:
            music.play(self.load(), music_before)
        if self.tty and ran:        # ошибка или «занято» - дочитывать нечего
            hubline.drop_typeahead()
            ui.say()
            try:
                self.reader(BACK)
            except (EOFError, KeyboardInterrupt):
                ui.say()

    def own(self, act: Action) -> None:
        if act.name == "help":
            for line in help_lines(self.load(), " ".join(act.args)):
                ui.say(line)
        elif act.name == "clear":
            if self.tty:
                sys.stdout.write(CLEAR)
                sys.stdout.flush()
        elif act.name == "hub":
            self.show_board()

    def run_word(self, argv: List[str]) -> int:
        with commands.hub_mode():
            return cli.run_once(argv, self.flags, self.theme_flag, hub=True, ask=self.reader)


def main(flags=frozenset(), theme_flag=None, reader=None, strict=False) -> int:
    if os.environ.get("TERMIT_LAUNCHED"):
        ui.bad(IN_TASK)
        return 2
    if theme_flag is not None and theme_flag not in theme.available():
        ui.bad(f"Нет темы {theme_flag!r}. Есть: " + ", ".join(theme.available()))
        return 2
    strict = strict or bool(os.environ.get("TERMIT_DEBUG"))
    live = reader is None
    tty = live and sys.stdin.isatty() and sys.stdout.isatty()
    hub = Hub(reader or input, flags, theme_flag, strict=strict, tty=tty)
    if tty:
        editor = hubline.LineEditor(hubline.history_path(),
                                    complete=lambda before: candidates(before, hub.tab_p),
                                    tty=True)
        hub.reader = editor.read
        hub.remember = editor.remember
    old = hubline.install_signals() if live else {}
    os.environ["TERMIT_HUB"] = "1"      # zsh задач узнаёт по нему, что ран из убежища
    try:
        return hub.loop()
    finally:
        os.environ.pop("TERMIT_HUB", None)
        music.stop()                # звук дома гаснет вместе с ним (спека 2.8)
        hubline.restore_signals(old)
