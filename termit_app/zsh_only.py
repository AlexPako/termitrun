"""FB6: приёмы, которые есть только в zsh или в bash ведут себя иначе.

Владелец спросил, работает ли игра в bash. Игра запускается из любой оболочки, а задания идут
в своём zsh. Но часть приёмов из уроков в bash не сработает или сработает по-другому — при
первой встрече игрок видит короткую пометку «🐚 только в zsh: …» или «🐚 в bash иначе: …».

Единый источник: имя приёма → Trick(pattern, line).
- pattern — регулярка: по ней охрана (tools/audit_zsh.py) находит приём в уроке, шпаргалке
  или совете клавиш;
- line — то, что видит игрок.

Факты проверены на этом Mac: /bin/bash 3.2.57 и zsh (zsh -f). Bash на macOS — 3.2: globstar
в нём нет вовсе, он появился в bash 4.

Где звучит: FIRST_SEEN — задача → приёмы, чья строка «🐚» стоит в её карточке под уроком
(ui.origin_notes, рядом со строками «🔤»). Пометка засчитана и тогда, когда сам текст встречи
уже говорит, как в bash (как урок line_edit про Ctrl+U). Охрана сверяет список с порядком игры."""
from dataclasses import dataclass
from typing import Dict, List, Tuple


NBSP = "\u00a0"        # команда в строке не рвётся переносом: «shopt -s dotglob» целиком


def _keep(code: str) -> str:
    return code.replace(" ", NBSP)


@dataclass(frozen=True)
class Trick:
    pattern: str        # регулярка: встреча приёма в тексте карточки
    line: str           # строка игроку, без значка впереди


ITEMS: Dict[str, Trick] = {
    "globstar": Trick(
        r"\*\*",
        "только в zsh: ** — «на любой глубине». В bash на Mac ** работает как простая *, "
        "вглубь не идёт."),
    "qualifiers": Trick(
        r"[*\w]\((?:D|N|\.|/)[\w+-]*\)",
        "только в zsh: уточнения в скобках после маски — (D), (.), (.m-3). Bash на них "
        f"ругнётся syntax error, скрытые файлы он берёт после {_keep('shopt -s dotglob')}."),
    "ctrl_u": Trick(
        r"Ctrl\+U",
        "в bash иначе: Ctrl+U стирает не всю строку, а только то, что левее курсора."),
    "history": Trick(
        r"`?\bhistory\b`? —",
        "в bash иначе: там голая history выдаёт все команды разом. В zsh — последние 16 "
        f"строк, всю историю покажет {_keep('history 1')}."),
    "setopt": Trick(
        r"\bsetopt\b",
        f"только в zsh: setopt. В bash похожие настройки включают {_keep('shopt -s')} и "
        f"{_keep('set -o')}."),
    "auto_pushd": Trick(
        r"auto_pushd",
        f"в bash иначе: cd стопку не пополняет — папку в неё кладёт {_keep('pushd папка')}. "
        f"{_keep('dirs -v')} и {_keep('cd ~2')} там работают так же."),
    "zshrc": Trick(
        r"\.zshrc",
        "в bash иначе: ~/.zshrc — файл настроек zsh, а bash в окне терминала Mac читает "
        "~/.bash_profile."),
    "nomatch": Trick(
        r"no matches found",
        "в bash иначе: маска без совпадений там не ругается, а уходит в команду как есть. "
        "Кавычки всё равно ставь — так надёжно в любой оболочке."),
    "quotes": Trick(
        r'"\$\w+"',
        "в bash иначе: без кавычек $f с пробелом в имени развалится на два слова. zsh так не "
        "делает, но кавычки — привычка, которая спасёт в любой оболочке."),
    "case_glob": Trick(
        r"\(#i\)|extendedglob",
        f"только в zsh: {_keep('setopt extendedglob')} и (#i). В bash большие и маленькие "
        f"буквы в маске уравнивает {_keep('shopt -s nocaseglob')}."),
    "alternation": Trick(
        r"\.\((?:#i\))?\(?\w+\|\w+",
        f"только в zsh: (a|b) в маске. Bash поймёт её только после {_keep('shopt -s extglob')} "
        "и в виде @(a|b)."),
    "zmv": Trick(
        r"\bzmv\b",
        "только в zsh: zmv. В bash пачку файлов переименовывают тем же циклом for."),
    "print": Trick(
        r"\bprint -r\b",
        "только в zsh: print — встроенная команда zsh, в bash её нет. Там то же делает "
        + _keep("printf '%s\\n' 'строка'") + "."),
}


# Задача → приёмы, чья строка «🐚» стоит в её карточке: здесь игрок встречает их впервые.
# Сверяет tools/audit_zsh.py.
FIRST_SEEN: Dict[str, Tuple[str, ...]] = {
    # «Основы»
    "home_tilde": ("ctrl_u",),        # Ctrl+U впервые — в совете клавиш (ui.KEY_TIPS)
    "deep_dig": ("globstar", "qualifiers"),
    "history_recall": ("history",),
    "z_jump": ("setopt", "auto_pushd", "zshrc"),
    # «Свалка»
    "find_name": ("nomatch",),
    "batch_rename": ("quotes", "zmv"),
    "disk_sweep": ("case_glob",),
    "dup_sort": ("alternation",),
    # «Окружение»
    "dotenv": ("print",),
}

MARK = "🐚 "


def note(name: str) -> str:
    """Строка игроку: «🐚 только в zsh: …» или «🐚 в bash иначе: …»."""
    return MARK + ITEMS[name].line


def notes(task_id: str) -> List[str]:
    return [note(n) for n in FIRST_SEEN.get(task_id, ())]
