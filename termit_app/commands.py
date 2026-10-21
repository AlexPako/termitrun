"""Команды самой игры ./termit СЛОВО: одно описание на команду, одним словарём.

Отсюда берут слова справка (cli.usage) и строка «что это» при первой встрече команды в
сообщениях игры (ui.glossary, FB5: владелец не понял, что за ./termit home после подарка).
Описания — с подстановками слов темы: {xp_gen}, {xp_title_low}, {money_name}, {owl},
{book}."""
import contextlib
import contextvars
import re

from termit_app import theme

ABOUT = {
    "run": "ран дня: новые и повторы, ~10 минут",
    "short": "короткий вариант: меньше повторений, новое — как обычно",
    "new": "ещё урок: пачка новых команд сверх нормы рана (more — то же)",
    "master": "круг мастера: знакомые дела на время, против своего рекорда",
    "train": "отработка: слабые места; train ТЕМА, train ID, train exam",
    "track": "пройти место по порядку",
    "play": "то же, что train ID: одна задача отработкой (id — в ./termit list)",
    "stats": "звание, серия, {xp_title_low}, {money_name}, боссы",
    "intro": "вступление и памятка «как сдавать ответ» ещё раз",
    "keys": "клавиши: строка, история, прокрутка; keys hacks — все лайфхаки (в задаче — keys)",
    "ext": "копилка расширений файлов (в задаче — ext)",
    "shop": "магазин: баланс и витрина; all — всё, что сейчас продаётся",
    "style": "купленный стиль: рамки, эффект итога, карта, титул; off — снять",
    "rehearse": "репетиция босса; первая после провала — даром",
    "list": "все задачи с отметками",
    "map": "карта: места открытые и закрытые, где ты сейчас",
    "home": "убежище: вещи, осмотр, как пользоваться; home shop — витрина",
    "deck": "модули в деке: что стоит, слоты, сколько {xp_gen} до нового",
    "case": "доска дела: улики, вопросы, версия",
    "memory": "найденные осколки памяти",
    "dossier": "досье персонажей: купленные страницы",
    "inbox": "сообщения на деке: inbox N — открыть, inbox next — новое",
    "fence": "тайник с хабаром — вынесенными файлами; sell N — продать скупщику",
    "book": "{book} — выученные команды",
    "diary": "дневник: уроки и разборы пройденного, бесплатно",
    "theme": "темы оформления игры",
    "sound": "звуки купленных примочек: взлом босса, рекорд, веха; off — тишина",
    "music": "музыка купленных записей: stop, vol 1..10, preview ID, run on|off",
    "implants": "утилиты-подарки для Mac: статус; install ID — поставить",
    "wheels": "склад пакетов pandas/requests для «Аналитики»; get — скачать",
    "owl": "{owl}: подсказки нейросети Ollama на твоём Mac (ask в задаче)",
    "feedback": "замечания бета-тестера (в задаче набери bug)",
    "report": "баг или идея — ссылка на карточку для разработчика",
    "update": "обновить игру до свежей версии (git pull); прогресс не пропадёт",
    "help": "справка: все команды игры",
}

# Подкоманды ./termit home СЛОВО (FB5 п. 18: дом — хаб): справка, ./termit home help и охрана
# текстов «как пользоваться» берут их отсюда
HOME_ABOUT = {
    "look": ("ID", "осмотр вещи: команда терминала и живое значение"),
    "board": ("", "доска: подсказки над приглашением в задаче; pin|unpin|off|on"),
    "prompt": ("", "своё приглашение zsh в задачах: детали, on|off, show"),
    "palette": ("ID", "цвет пути в приглашении; off — без цвета"),
    "callsign": ("ИМЯ", "позывной в шапке рана и приглашении; off — снять"),
    "diary": ("", "то же, что ./termit diary"),
    "shop": ("", "витрина прямо из дома — то же, что ./termit shop"),
    "help": ("", "подробно о доме: что где и как пользоваться"),
}


def raised(sub: str) -> bool:
    """В убежище слово дома набирают без home — только если это живое слово хаба
    (look, board, prompt…); home help и всё, чего в WORDS нет, остаётся «home X»."""
    if not hub_on():
        return False
    from termit_app import hub      # hub сам импортирует commands — подгружаем позже
    word = hub.find(sub)
    return word is not None and not word.own


def home_cmd(sub: str) -> str:
    return sub if raised(sub) else f"{prefix()}home {sub}"


def home_line(sub: str) -> str:
    """Строка справки для ./termit home СЛОВО — той же колонкой, что line(); в убежище
    слова дома подняты наверх (board, а не home board), кроме home help."""
    args, text = HOME_ABOUT[sub]
    cmd = home_cmd(sub) + (f" {args}" if args else "")
    return f"  {cmd.ljust(24)} {text}\n"


# Когда набирать — одна и та же оговорка у каждой строки первой встречи
WHEN = "набирают в обычном терминале после рана, не в задаче"
MENTION = re.compile(r"\./termit ([a-z]+)")

# Режим убежища (хаб, спека 2.7): команды набирают без ./termit — справка строится без
# префикса, строка первой встречи говорит «в убежище». Включает его hub.Hub на свой цикл.
_HUB = contextvars.ContextVar("termit_hub", default=False)
HUB_WHEN = "набирают в убежище"


@contextlib.contextmanager
def hub_mode(on: bool = True):
    token = _HUB.set(on)
    try:
        yield
    finally:
        _HUB.reset(token)


def hub_on() -> bool:
    return _HUB.get()


def prefix() -> str:
    return "" if hub_on() else "./termit "


def about(name: str) -> str:
    """Описание команды словами текущей темы."""
    w = theme.word
    return ABOUT[name].format(xp_gen=w("xp_gen"), xp_title_low=w("xp_title").lower(),
                              money_name=w("money_name"), owl=w("owl"), book=w("book"))


def line(name: str, args: str = "", tail: str = "") -> str:
    """Строка справки: «  ./termit ИМЯ АРГУМЕНТЫ   описание» с колонкой описаний."""
    cmd = f"{prefix()}{name}" + (f" {args}" if args else "")
    return f"  {cmd.ljust(24)} {about(name)}{tail}\n"


def mentioned(text: str) -> list:
    """Команды игры, упомянутые в тексте, — по порядку, без повторов, только известные."""
    out = []
    for name in MENTION.findall(text):
        if name in ABOUT and name not in out:
            out.append(name)
    return out


def note(name: str) -> str:
    """Строка «что это» при первой встрече команды в сообщении игры."""
    if hub_on():
        return f"ⓘ {name} — {about(name)}; {HUB_WHEN}."
    return f"ⓘ ./termit {name} — {about(name)}; {WHEN}."
