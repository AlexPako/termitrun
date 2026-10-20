"""FB12 (N9): разовый экран «настрой iTerm2 за 3 минуты».

Часть сочетаний из уроков клавиш (Option+← → вне игры, Cmd+Shift+↑ ↓, Cmd+Shift+A) работает
только в iTerm2 и только после настройки — без неё новичок решит, что «не умеет», а не что
«не настроено». Экран говорит по шагам, что включить и зачем.

Кто показывает: keys iterm (в задаче и ./termit keys iterm) — всегда; хаб (план хаба) зовёт
offer_once при входе — один раз, и только если окно не iTerm2. Пункт «настройка» в хабе
делает план хаба, здесь — только сам экран."""
import os
import textwrap
from typing import Optional

from termit_app import layout

FLAG = "iterm_setup_shown"           # p["flags"]: экран уже показан при входе

TITLE = "Настрой iTerm2 за 3 минуты"

STEPS = (
    ("Поставь iTerm2",
     "iterm2.com → Download, перетащи iTerm в «Программы» и запускай игру из него. Зачем: "
     "вкладки, панели рядом, поиск по выводу — Terminal.app так не умеет."),
    ("Слова — стрелками",
     "Cmd+, (Settings) → Profiles → Keys → Key Mappings → Presets… → Natural Text Editing. "
     "Зачем: Option+← → прыгает через слово, Option+Delete стирает слово — как в любой "
     "программе Mac. В игре это работает и без настройки."),
    ("Метки у команд",
     "Меню iTerm2 → Install Shell Integration → Continue. Она допишет строку в твой "
     "~/.zshrc — так и задумано. Зачем: Cmd+Shift+↑ ↓ прыгает от команды к команде, "
     "Cmd+Shift+A выделяет вывод последней."),
    ("Длинная память (по желанию)",
     "Settings → Profiles → Terminal → Scrollback lines — побольше, например 10000. Зачем: "
     "длинный вывод не обрежется сверху."),
)

ONLY_ITERM = "только iTerm2"         # пометка у сочетаний, которым нужна эта настройка


def needed(env: Optional[dict] = None) -> bool:
    """Окно не iTerm2 — экран пригодится (TERM_PROGRAM ставят Terminal.app и iTerm2)."""
    env = os.environ if env is None else env
    return env.get("TERM_PROGRAM") != "iTerm.app"


def screen(width: int = 78) -> str:
    """Экран целиком: заголовок, шаги с «зачем», как вернуться к нему."""
    out = [TITLE, ""]
    for n, (head, body) in enumerate(STEPS, 1):
        out.append(f"{n}. {head}")
        out += textwrap.wrap(body, width - 3, initial_indent="   ", subsequent_indent="   ",
                             break_long_words=False, break_on_hyphens=False)
    out += [""] + textwrap.wrap("Раскладка. " + layout.NOTE, width - 3, initial_indent="   ",
                                subsequent_indent="   ", break_long_words=False,
                                break_on_hyphens=False)
    out += ["", "Вернуться к этому экрану: keys iterm (в задаче) или ./termit keys iterm."]
    return "\n".join(out)


def offer_once(p: dict, env: Optional[dict] = None) -> Optional[str]:
    """Для хаба: экран при входе — один раз и только вне iTerm2 (иначе None)."""
    flags = p.setdefault("flags", [])
    if FLAG in flags or not needed(env):
        return None
    flags.append(FLAG)
    return screen()
