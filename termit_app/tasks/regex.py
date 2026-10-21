"""Блок «Регулярки» трека «Данные» (FB21, владелец 21.10: «по маскам классные уроки, а ещё
регулярки будут?»). Один приём на урок, вариант 0 — самый простой, примеры — из работы с
логами и выгрузками.

Порядок в треке: маска против регулярки, ^ и $, классы [ ], повторы (grep -E), выбор и группы,
grep -o — после top_values (там учат sort | uniq -c); sed -E с группами и финал блока — после
sed_fix. Задачи сами встают в data.TASKS (insert_after ниже): data.py импортирует этот модуль
последней строкой, а он — data. Порядок импорта любой: data.TASKS к этому моменту уже есть.

Ответ считает тот же шаблон через re Python: в этих шаблонах (классы, ^ $, * + ? {n}, | и
группы) расширенные регулярки BSD grep и re совпадают. Ловушки — как в data.py: пары
[ключ, значение неверного пути] в state["traps"]."""
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from termit_app import sandbox
from termit_app.tasks import data, datakit, kit
from termit_app.tasks.base import Task, Variant, Verdict

LOG = data.LOG
ORDERS = data.ORDERS
CHAT = "chat.txt"

# шаблон grep в кавычках и флаги перед ним (как LogPeriod._GREP_PAT)
_GREP_PAT = re.compile(r"\bgrep\s+((?:-[A-Za-z]+\s+)*)(?:'([^']*)'|\"([^\"]*)\")")
# grep с шаблоном без кавычек, где есть * : zsh принимает его за маску имён файлов
_BARE_STAR = re.compile(r"\bgrep\s+(?:-[A-Za-z]+\s+)*[^\s'\"|;&-][^\s'\"|;&]*\*")
_EXT_SIGNS = re.compile(r"[|+?(){}]")

MSG_NO_E = ("Без -E grep понимает + ? { } | и ( ) как обычные знаки и ищет их буквально. "
            "Нужен grep -E '…'.")
MSG_BARE = ("Шаблон без кавычек: zsh принял * за маску имён файлов (отсюда no matches found) "
            "и до grep его не допустил. Возьми шаблон в одинарные кавычки: grep '…' файл.")


def insert_after(tasks: list, anchor: str, more) -> None:
    """Вставить задачи more сразу за задачей anchor (без повторов по id)."""
    have = {t.id for t in tasks}
    fresh = [t for t in more if t.id not in have]
    at = next(i for i, t in enumerate(tasks) if t.id == anchor) + 1
    tasks[at:at] = fresh


def _write(box, name: str, lines: List[str]) -> None:
    kit.write(Path(box) / name, "\n".join(lines) + "\n")


def _count(pattern: str, lines: List[str]) -> int:
    rx = re.compile(pattern)
    return sum(bool(rx.search(x)) for x in lines)


def _grep_patterns(cmds):
    """(флаги, шаблон) каждого grep в кавычках из последней строки журнала, где есть grep."""
    greps = [seg for seg in data._segments(cmds) if re.search(r"\bgrep\b", seg)]
    if not greps:
        return []
    last = cmds[-1].line if cmds else ""
    segs = [s for s in greps if s in last] or greps[-1:]
    out = []
    for seg in segs:
        for m in _GREP_PAT.finditer(seg):
            out.append((m.group(1), m.group(2) or m.group(3) or ""))
    return out


def _journal_why(cmds, need_e: bool = True) -> Optional[str]:
    """Причина по последней строке с grep: шаблон без кавычек со *, знаки -E без -E."""
    recent = [c for c in cmds[-3:] if re.search(r"\bgrep\b", c.line)]
    if recent and _BARE_STAR.search(recent[-1].line):
        return MSG_BARE
    if need_e:
        for flags, pat in _grep_patterns(cmds):
            if not re.search(r"-[A-Za-z]*E", flags) and _EXT_SIGNS.search(pat):
                return MSG_NO_E
    return None


class _RegexAnswer(data._DataAnswer):
    """Ответ числом или частями; до ловушек — причина по журналу (кавычки, -E)."""
    need_e = True

    def wrong_message(self, given, ctx):
        why = _journal_why(ctx.cmds, self.need_e)
        if why:
            return why
        return super().wrong_message(given, ctx)


def _log_lines(rng, days: int = 1, per_day: Optional[int] = None) -> List[str]:
    text, _ = datakit.app_log(rng, days=days, per_day=per_day or rng.randint(600, 1200))
    return text.splitlines()


def _sorted_log(lines: List[str]) -> List[str]:
    return sorted(lines, key=lambda x: x[:19])


def _log_line(rng, when, level: str, svc: str, msg: str) -> str:
    return datakit.log_line(datakit._entry(when, level, svc, msg))


def _random_when(rng, day: date) -> datetime:
    return datetime(day.year, day.month, day.day) + timedelta(seconds=rng.randrange(86400))


# --- A. маска против регулярки -------------------------------------------------------------

CHATTER = ("what a match", "pass it already", "nice save", "who is on the bench",
           "ref is blind", "coffee anyone", "see you at the gala night", "that was legal",
           "gal pal says hi", "go total", "offside again", "keep the ball")
CHEERS = ("goal", "gooal", "goooal", "goooooal")


class RegexMask(_RegexAnswer):
    """Маска против регулярки: .* — что угодно, * — повтори прошлый знак; шаблон в кавычках."""
    id = "regex_mask"
    title = "Маска или регулярка"
    par = 50
    need_e = False
    scroll = ("Регулярка (регулярное выражение) — шаблон текста для grep, вроде маски, но знаки "
              "другие: . — любой символ, .* — что угодно: grep -c 'ann.*paid' файл — сначала "
              "ann, дальше в строке paid.\n"
              "* — «повтори прошлый знак, хоть ноль раз»: 'lo*g' подходит под lg (ноль o) и под loog. Шаблон — в "
              "одинарных кавычках, иначе zsh примет * за маску файлов: no matches found.")
    variants = (
        Variant("В app.log сколько строк, где стоит метка svc={svc}, а где-то дальше в той же "
                "строке — слово timeout? Ответ: ans ЧИСЛО",
                wrong=("grep -c 'svc={svc}*timeout' app.log", "grep -c timeout app.log"),
                alternatives=("grep svc={svc} app.log | grep -c timeout — то же двумя "
                              "звеньями конвейера",)),
        Variant("Сколько заказов в orders.csv из города {city} со статусом refund? Между "
                "городом и статусом в строке стоят другие колонки. Ответ: ans ЧИСЛО",
                hints=("Город и статус — в одной строке, между ними что угодно: в регулярке "
                       "это .*",
                       "Колонки ищи с запятыми по краям: ',{city},' и ',refund,' — так не "
                       "зацепится заметка «refund requested» в последней колонке.",
                       "grep -c ',{city},.*,refund,' orders.csv → ans ЧИСЛО"),
                solution="grep -c ',{city},.*,refund,' orders.csv",
                wrong=("grep -c ',{city},*,refund,' orders.csv", "grep -c ',{city},' orders.csv"),
                alternatives=("grep ',{city},' orders.csv | grep -c ',refund,' — то же двумя "
                              "звеньями конвейера",)),
        Variant("В chat.txt болельщики кричат гол: goal, gooal, goooooal — o сколько угодно, "
                "но хоть одна. Сколько строк с таким криком? Слова вроде gala и legal не в "
                "счёт. Ответ: ans ЧИСЛО",
                hints=("* повторяет знак перед собой: o* — сколько угодно o, хоть ни одной.",
                       "Хоть одну o напиши саму, а за ней — o*: тогда подойдёт и goal, и "
                       "goooal, а gal — нет.",
                       "grep -c 'goo*al' chat.txt → ans ЧИСЛО"),
                solution="grep -c 'goo*al' chat.txt",
                wrong=("grep -c 'go*al' chat.txt", "grep -c goal chat.txt"),
                alternatives=("grep -ic 'goo*al' chat.txt — то же и без учёта регистра",),
                explain="o* — это и ноль o: 'go*al' нашёл бы gal в gala и legal. Одна o "
                        "написана сама, а o* за ней добирает остальные."),
    )
    hints = ("Шаблон регулярки: сначала svc={svc}, потом «что угодно», потом timeout.",
             "«Что угодно» в регулярке — точка и звёздочка: .* ; одна * повторяет только знак "
             "перед собой.",
             "grep -c 'svc={svc}.*timeout' app.log → ans ЧИСЛО")
    solution = "grep -c 'svc={svc}.*timeout' app.log"
    explain = ("В маске имён * значит «что угодно», а в регулярке «что угодно» — это .* : точка "
               "— любой знак, * — повтори его сколько угодно. Одна * повторяет только знак перед "
               "собой, поэтому 'svc=X*timeout' не нашёл ничего.")
    spell = "grep 'a.*b' файл — a, дальше что угодно, потом b; 'lo*g' — o сколько угодно раз"
    trap_messages = {
        "mask": "Ноль: * в регулярке — не «что угодно», а «повтори прошлый знак». Что угодно "
                "— .* , точка и звёздочка.",
        "all": "В счёт попали лишние строки: нужны оба куска в одной строке — первый, потом "
               ".*, потом второй.",
        "one_o": "Это только goal с одной o. Остальные o добирает o* после первой: goo*al.",
        "zero_o": "В счёт попали gala и legal: o* — это и ноль o. Одну o напиши саму: goo*al.",
    }
    fallback = "Не то. Помни: «что угодно» в регулярке — .* , а шаблон — в одинарных кавычках."

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            rows = data._orders(box, rng)
            refunds = Counter(r["city"] for r in rows if r["status"] == "refund")
            city = rng.choice(sorted(c for c, n in refunds.items() if n >= 2) or
                              sorted(refunds) or [rows[0]["city"]])
            own = [r for r in rows if r["city"] == city]
            answer = sum(r["status"] == "refund" for r in own)
            return {"city": city, "answer": answer,
                    "traps": [["mask", 0], ["all", len(own)]]}
        if variant == 2:
            lines = []
            for _ in range(rng.randint(60, 120)):
                lines.append(rng.choice(CHATTER))
            for cheer in CHEERS:
                for _ in range(rng.randint(2, 5)):
                    lines.insert(rng.randrange(len(lines) + 1), f"{cheer}!" * rng.randint(1, 2))
            _write(box, CHAT, lines)
            return {"answer": _count(r"goo*al", lines),
                    "traps": [["zero_o", _count(r"go*al", lines)],
                              ["one_o", _count(r"goal", lines)], ["mask", 0]]}
        lines = _log_lines(rng)
        # ответ не ноль: сервис, у которого есть хоть две строки с timeout (иначе ловушка
        # 'svc=X*timeout' с её нулём совпала бы с ответом)
        good = [s for s in datakit.SERVICES if _count(rf"svc={s}.*timeout", lines) >= 2]
        svc = rng.choice(good or list(datakit.SERVICES))
        kit.write(Path(box) / LOG, "\n".join(lines) + "\n")
        own = [x for x in lines if f"svc={svc}" in x]
        return {"svc": svc, "answer": _count(rf"svc={svc}.*timeout", lines),
                "traps": [["mask", 0], ["all", len(own)],
                          ["all", _count("timeout", lines)]]}


# --- B. якоря ^ и $ ------------------------------------------------------------------------

NEAR_CITIES = ("{c} north", "new {c}", "old {c} road", "{c}ville", "{c} ")


class RegexAnchor(_RegexAnswer):
    """^ — начало строки, $ — конец, ^…$ — строка целиком."""
    id = "regex_anchor"
    title = "Начало и конец строки"
    par = 45
    need_e = False
    scroll = ("^ в начале шаблона — «строка начинается так»: grep -c '^2726-09-30' лог — только "
              "строки, которые с этой даты начинаются, а не те, где она упомянута в тексте.\n"
              "$ в конце шаблона — «строка кончается так»: grep 'done$' файл. Вместе ^…$ — "
              "строка целиком, без ничего вокруг: grep -c '^yes$' answers.txt.")
    variants = (
        Variant("Сколько строк в app.log за {date} — эта дата стоит в начале строки? В "
                "сообщениях бывают ссылки на этот день из других дней. Ответ: ans ЧИСЛО",
                wrong=("grep -c {date} app.log", "grep -c '{date}$' app.log"),
                alternatives=("grep '^{date}' app.log | wc -l — то же через подсчёт строк",)),
        Variant("Сколько строк в app.log кончаются именем сервиса {svc}: «… calling {svc}», «… "
                "by {svc}»? Строки, где {svc} стоит в середине, не в счёт. Ответ: ans ЧИСЛО",
                hints=("Конец строки в регулярке — знак $ в конце шаблона.",
                       "Сначала слово, потом $: '{svc}$' — после имени в строке ничего нет.",
                       "grep -c '{svc}$' app.log → ans ЧИСЛО"),
                solution="grep -c '{svc}$' app.log",
                wrong=("grep -c {svc} app.log", "grep -c '^{svc}' app.log"),
                alternatives=("grep '{svc}$' app.log | wc -l — то же через подсчёт строк",)),
        Variant("В cities.txt по городу в строке, но есть и мусор: {city} north, new {city}, "
                "{city} с пробелом в конце. Сколько строк — ровно {city}, и больше ничего? "
                "Ответ: ans ЧИСЛО",
                hints=("Строка целиком — шаблон между ^ и $.",
                       "^ — строка начинается так, $ — кончается так: между ними только имя "
                       "города, и ни пробела.",
                       "grep -c '^{city}$' cities.txt → ans ЧИСЛО"),
                solution="grep -c '^{city}$' cities.txt",
                wrong=("grep -c {city} cities.txt", "grep -c '^{city}' cities.txt"),
                alternatives=("grep '^{city}$' cities.txt | wc -l — то же через подсчёт "
                              "строк",),
                explain="^ и $ держат строку с двух концов: строки с соседними словами и с "
                        "пробелом в конце не прошли."),
    )
    hints = ("Начало строки в регулярке — знак ^ в начале шаблона.",
             "Дата в начале строки — когда строка появилась, а дата в тексте — просто ссылка: "
             "'^{date}'.",
             "grep -c '^{date}' app.log → ans ЧИСЛО")
    solution = "grep -c '^{date}' app.log"
    explain = ("^ привязывает шаблон к началу строки, $ — к концу. Дата в начале строки лога — "
               "её время; та же дата в тексте — только упоминание, и голый шаблон её цепляет.")
    spell = "grep '^начало' файл, grep 'конец$' файл; '^целиком$' — строка целиком"
    trap_messages = {
        "mention": "В счёт попали строки, где это слово просто упомянуто. Привяжи шаблон к "
                   "краю строки: ^ — к началу, $ — к концу.",
        "start": "^ держит только начало, а хвост остался свободным: допиши $ в конце.",
        "end": "$ держит только конец, а начало осталось свободным: допиши ^ в начале.",
    }
    fallback = "Не то. ^ — начало строки, $ — её конец; шаблон — в одинарных кавычках."

    def setup_variant(self, box, rng, variant):
        if variant == 2:
            city = rng.choice(datakit.CITIES)
            others = [c for c in datakit.CITIES if c != city]
            lines = [city] * rng.randint(5, 12)
            lines += [rng.choice(others) for _ in range(rng.randint(20, 40))]
            for tmpl in NEAR_CITIES:
                lines += [tmpl.format(c=city)] * rng.randint(1, 3)
            rng.shuffle(lines)
            _write(box, "cities.txt", lines)
            exact = sum(x == city for x in lines)
            return {"city": city, "answer": exact,
                    "traps": [["mention", sum(city in x for x in lines)],
                              ["start", sum(x.startswith(city) for x in lines)],
                              ["end", sum(x.endswith(city) for x in lines)]]}
        if variant == 1:
            svc = rng.choice(datakit.SERVICES)
            lines = _log_lines(rng)
            kit.write(Path(box) / LOG, "\n".join(lines) + "\n")
            return {"svc": svc, "answer": sum(x.endswith(svc) for x in lines),
                    "traps": [["mention", sum(svc in x for x in lines)]]}
        lines = _log_lines(rng, days=3, per_day=rng.randint(400, 800))
        day = (datakit.LOG_START + timedelta(days=rng.randrange(3))).isoformat()
        other = [d for d in (datakit.LOG_START + timedelta(days=i) for i in range(3))
                 if d.isoformat() != day]
        extra = []
        for _ in range(rng.randint(4, 9)):
            when = _random_when(rng, rng.choice(other))
            svc = rng.choice(datakit.SERVICES)
            extra.append(_log_line(rng, when, "INFO", svc, f"replay of {day} batch done"))
        lines = _sorted_log(lines + extra)
        kit.write(Path(box) / LOG, "\n".join(lines) + "\n")
        return {"date": day, "answer": sum(x.startswith(day) for x in lines),
                "traps": [["mention", sum(day in x for x in lines)]]}


# --- C. классы [ ] ------------------------------------------------------------------------

def _plant_codes(rng, lines: List[str], k: int, two: int = 0, decoys: int = 0,
                 pool=None) -> List[str]:
    """Коды ошибок code=E### у k строк ERROR, у two из них — второй код; decoys строк с
    обрывком E и двумя цифрами (code=E12)."""
    pool = pool or [f"E{n}" for n in rng.sample(range(100, 1000), 6)]
    errs = [i for i, x in enumerate(lines) if "[ERROR]" in x]
    picked = rng.sample(errs, min(len(errs), k + decoys))
    out = list(lines)
    for j, i in enumerate(picked):
        if j < k:
            code = rng.choice(pool)
            tail = f" code={code}"
            if j < two:
                tail += f" after {rng.choice(pool)}"
        else:
            tail = f" code=E{rng.randint(10, 99)}"
        out[i] = out[i] + tail
    return out


TICKET_FORMS = ("{a}{b}-{n}", "{A}{B}-{n}", "{a}{d}-{n}", "{a}{b}{c}-{n}", "{A}{b}-{n}")


class RegexClass(_RegexAnswer):
    """[0-9] [a-z] — один знак из набора; [^…] — любой, кроме; \\d — не везде."""
    id = "regex_class"
    title = "Знак из набора"
    par = 50
    need_e = False
    scroll = ("[ ] — класс: ровно один знак из набора. [0-9] — любая цифра, [a-z] — маленькая "
              "латинская буква, [aeiou] — одна из этих букв. [^0-9] — с крышкой внутри скобок: "
              "любой знак, КРОМЕ цифры.\n"
              "Класс — всегда один знак: три цифры — [0-9][0-9][0-9]. \\d (от слова digit — цифра) "
              "grep на Mac понимает, а на Linux-сервере — только grep -P '\\d' файл (P — Perl). "
              "[0-9] работает везде; \\d — норма в Python.")
    variants = (
        Variant("У части ошибок в app.log есть код: буква E и три цифры, вроде E404 или E503. "
                "Сколько строк с таким кодом? Обрывки с двумя цифрами (E12) не в счёт. "
                "Ответ: ans ЧИСЛО",
                wrong=("grep -c 'E[0-9]' app.log", "grep -c E app.log"),
                alternatives=("grep -c 'code=E[0-9][0-9][0-9]' app.log — то же с меткой "
                              "поля",)),
        Variant("Номер тикета в tickets.txt начинается с префикса и дефиса. Сколько тикетов, где "
                "префикс — ровно две маленькие латинские буквы, как в ab-1043? AB-1043, a1-1043 "
                "и abc-1043 не подходят. Ответ: ans ЧИСЛО",
                hints=("Каждую букву префикса задаёт класс [a-z] — один знак.",
                       "Две буквы — два класса подряд, потом дефис; ^ держит начало строки, "
                       "чтобы abc- не прошёл.",
                       "grep -c '^[a-z][a-z]-' tickets.txt → ans ЧИСЛО"),
                solution="grep -c '^[a-z][a-z]-' tickets.txt",
                wrong=("grep -c '[a-z][a-z]-' tickets.txt", "grep -ic '^[a-z][a-z]-' tickets.txt"),
                alternatives=("grep -c '^[a-z][a-z]-[0-9]' tickets.txt — то же, цифра после "
                              "дефиса",)),
        Variant("В phones.txt телефоны написаны кто как: одними цифрами и с дефисами, скобками, "
                "пробелами. Сколько строк, где есть хоть один знак, кроме цифры? "
                "Ответ: ans ЧИСЛО",
                hints=("«Любой знак, кроме цифры» — класс с крышкой внутри.",
                       "[^0-9] — один знак, который не цифра: хватит одного такого в строке.",
                       "grep -c '[^0-9]' phones.txt → ans ЧИСЛО"),
                solution="grep -c '[^0-9]' phones.txt",
                wrong=("grep -vc '[0-9]' phones.txt", "grep -c '[0-9]' phones.txt"),
                alternatives=("grep -vc '^[0-9]*$' phones.txt — то же наоборот: строки, где не "
                              "одни цифры",),
                explain="Крышка внутри скобок переворачивает класс: [^0-9] — любой знак, кроме "
                        "цифры. А -v '[0-9]' искал бы строки совсем без цифр — таких нет."),
    )
    hints = ("Цифру в регулярке задаёт класс [0-9] — ровно один знак.",
             "Три цифры — три класса подряд, перед ними буква E.",
             "grep -c 'E[0-9][0-9][0-9]' app.log → ans ЧИСЛО")
    solution = "grep -c 'E[0-9][0-9][0-9]' app.log"
    explain = ("Класс [ ] — один знак из набора: [0-9][0-9][0-9] — ровно три цифры подряд. "
               "Обрывок E12 не прошёл, а ERROR без цифры не прошёл никогда.")
    spell = "[0-9] — цифра, [a-z] — буква, [^0-9] — не цифра; класс — всегда один знак"
    trap_messages = {
        "short": "В счёт попали обрывки вроде E12: класс — ровно один знак, на три цифры — три "
                 "класса.",
        "letters": "Это все строки с буквой E — их полно в ERROR. Код — E и три цифры: "
                   "E[0-9][0-9][0-9].",
        "anywhere": "В счёт попал abc-: без ^ шаблон нашёл bc- внутри. Привяжи начало: ^.",
        "case": "-i уравнял большие и маленькие буквы, а нужны только маленькие: без -i "
                "[a-z] берёт только их.",
        "inverse": "-v '[0-9]' — строки совсем без цифр, их нет. Нужен класс «кроме цифры»: "
                   "'[^0-9]'.",
        "digits": "Это строки, где есть цифра, — то есть все. Нужен знак КРОМЕ цифры: "
                  "крышка внутри скобок, [^0-9].",
        "only": "Это строки из одних цифр — наоборот. Нужны те, где есть хоть один знак "
                "кроме цифры: '[^0-9]'.",
    }
    fallback = "Не то. Класс [ ] — ровно один знак; [^…] — любой, кроме перечисленных."

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            lines = []
            for _ in range(rng.randint(40, 80)):
                a, b, c = (rng.choice("abcdefghkmnprstuvwxyz") for _ in range(3))
                form = rng.choices(TICKET_FORMS, (6, 2, 1, 1, 1))[0]
                lines.append(form.format(a=a, b=b, c=c, A=a.upper(), B=b.upper(),
                                         d=rng.randint(0, 9), n=rng.randint(1000, 9999)))
            for form in TICKET_FORMS:       # каждой формы — хоть по одной
                lines.append(form.format(a="q", b="z", c="x", A="Q", B="Z", d=7,
                                         n=rng.randint(1000, 9999)))
            rng.shuffle(lines)
            _write(box, "tickets.txt", lines)
            return {"answer": _count(r"^[a-z][a-z]-", lines),
                    "traps": [["anywhere", _count(r"[a-z][a-z]-", lines)],
                              ["case", _count(r"(?i)^[a-z][a-z]-", lines)]]}
        if variant == 2:
            lines = _phones(rng)
            _write(box, "phones.txt", lines)
            plain = _count(r"^[0-9]*$", lines)
            return {"answer": len(lines) - plain,
                    "traps": [["inverse", 0], ["digits", len(lines)], ["only", plain]]}
        lines = _plant_codes(rng, _log_lines(rng), rng.randint(15, 40),
                             decoys=rng.randint(4, 9))
        kit.write(Path(box) / LOG, "\n".join(lines) + "\n")
        return {"answer": _count(r"E[0-9][0-9][0-9]", lines),
                "traps": [["short", _count(r"E[0-9]", lines)],
                          ["letters", _count("E", lines)]]}


def _phone(rng, digits: str, form: int) -> str:
    a, b, c = digits[:3], digits[3:6], digits[6:]
    return (digits, f"{a}-{b}-{c}", f"({a}) {b}-{c}", f"{a} {b} {c}", f"+1{digits}")[form]


def _phones(rng, n: Optional[int] = None) -> List[str]:
    n = n or rng.randint(30, 60)
    out = []
    for i in range(n):
        digits = f"{rng.choice((415, 628, 510, 650))}{rng.randint(2000000, 9999999)}"
        out.append(_phone(rng, digits, rng.choices(range(5), (5, 3, 2, 2, 1))[0]))
    return out


# --- D. повторы + ? {n} (grep -E) -----------------------------------------------------------

SHIP_TAILS = ("shipped", "packed", "lost")


class RegexRepeat(_RegexAnswer):
    """grep -E: + — одно или больше, {n} и {n,m} — сколько раз, ? — ноль или одно."""
    id = "regex_repeat"
    title = "Сколько раз подряд"
    par = 55
    scroll = ("grep -E (E — Extended, расширенные шаблоны) понимает знаки повторов: + — одно "
              "или больше: [0-9]+ — число любой длины; ? — ноль или одно: favou?rite — слово с "
              "u и без неё; {3} — ровно три раза: [0-9]{3}; {2,4} — от двух до четырёх.\n"
              "grep -Ec 'шаблон' файл — сколько строк. Без -E grep примет + ? { } за обычные "
              "знаки и молча найдёт не то.")
    variants = (
        Variant("В shipping.txt строки вида «order #7 shipped», «order #1042 packed». Номер — "
                "цифры, сколько угодно, но хоть одна. Сколько строк «order #НОМЕР shipped»? "
                "Номера вроде #x12 — опечатки, не в счёт. Ответ: ans ЧИСЛО",
                wrong=("grep -Ec '#[0-9] shipped' shipping.txt",
                       "grep -c '#[0-9]+ shipped' shipping.txt"),
                alternatives=("grep -c '#[0-9][0-9]* shipped' shipping.txt — то же без -E: "
                              "цифра, а за ней сколько угодно цифр",)),
        Variant("В phones.txt телефоны кто как написал. Сколько строк — ровно десять цифр, и "
                "ничего больше в строке? Ответ: ans ЧИСЛО",
                hints=("Сколько раз повторить класс, говорят фигурные скобки: {{10}}.",
                       "Строка целиком — между ^ и $, внутри — класс цифры с {{10}}; это "
                       "grep -E.",
                       "grep -Ec '^[0-9]{{10}}$' phones.txt → ans ЧИСЛО"),
                solution="grep -Ec '^[0-9]{{10}}$' phones.txt",
                wrong=("grep -Ec '[0-9]{{10}}' phones.txt", "grep -Ec '^[0-9]+$' phones.txt"),
                alternatives=("grep -E '^[0-9]{{10}}$' phones.txt | wc -l — то же через "
                              "подсчёт строк",)),
        Variant("В notes.txt пишут то color, то colour. Сколько строк, где есть хоть одно из "
                "двух написаний? Ответ: ans ЧИСЛО",
                hints=("Разница — одна буква u: она то есть, то нет.",
                       "? после знака — «ноль или одно»: u? — u есть или нет. Это grep -E.",
                       "grep -Ec 'colou?r' notes.txt → ans ЧИСЛО"),
                solution="grep -Ec 'colou?r' notes.txt",
                wrong=("grep -c color notes.txt", "grep -c 'colou?r' notes.txt"),
                alternatives=("grep -Ec 'color|colour' notes.txt — оба написания через «или» "
                              "(следующий урок)",)),
    )
    hints = ("«Одна цифра или больше» — класс [0-9] и знак + после него; это grep -E.",
             "За номером — пробел и shipped: так packed и lost не попадут, а #x12 не пройдёт.",
             "grep -Ec '#[0-9]+ shipped' shipping.txt → ans ЧИСЛО")
    solution = "grep -Ec '#[0-9]+ shipped' shipping.txt"
    explain = ("+ — одно или больше: [0-9]+ берёт номер любой длины, а [0-9] — ровно одну "
               "цифру. Знаки повторов работают с grep -E; без него grep ищет сам знак +.")
    spell = "grep -E: + — одно или больше, ? — ноль или одно, {3} — ровно три, {2,4} — от и до"
    trap_messages = {
        "one_digit": "Это только однозначные номера: [0-9] — ровно одна цифра. Одна или больше "
                     "— [0-9]+ (с grep -E).",
        "zero": "Шаблон ничего не нашёл. Частая причина: + ? и {{ }} работают только с grep -E.",
        "long": "В счёт попали и номера длиннее: без ^ и $ десять цифр нашлись внутри "
                "одиннадцати. Держи строку целиком: ^…$.",
        "any_len": "Это все строки из одних цифр, любой длины. Ровно десять — {{10}}.",
        "one_form": "Это только одно написание. u? — «u есть или нет»: colou?r ловит оба.",
    }
    fallback = "Не то. Повторы + ? {n} — только с grep -E, шаблон — в одинарных кавычках."

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            lines = _phones(rng)
            lines += [f"{rng.randint(10 ** 8, 10 ** 9 - 1)}" for _ in range(rng.randint(2, 4))]
            lines += [f"1{rng.randint(10 ** 9, 10 ** 10 - 1)}" for _ in range(rng.randint(2, 4))]
            rng.shuffle(lines)
            _write(box, "phones.txt", lines)
            return {"answer": _count(r"^[0-9]{10}$", lines),
                    "traps": [["long", _count(r"[0-9]{10}", lines)],
                              ["any_len", _count(r"^[0-9]+$", lines)], ["zero", 0]]}
        if variant == 2:
            words = ("the {w} of the logo", "pick a {w} for the chart", "{w} codes are in hex",
                     "no {w} here", "the cover is fine", "call me at noon")
            lines = []
            for _ in range(rng.randint(40, 70)):
                w = rng.choice(("color", "colour", "colr", "tint"))
                lines.append(rng.choice(words).format(w=w))
            lines += ["color", "colour"]
            rng.shuffle(lines)
            _write(box, "notes.txt", lines)
            return {"answer": _count(r"colou?r", lines),
                    "traps": [["one_form", _count("color", lines)],
                              ["one_form", _count("colour", lines)], ["zero", 0]]}
        lines = []
        for _ in range(rng.randint(50, 90)):
            n = rng.choice((rng.randint(1, 9), rng.randint(10, 99), rng.randint(100, 9999)))
            tag = rng.choices(("", "x"), (12, 1))[0]
            lines.append(f"order #{tag}{n} {rng.choice(SHIP_TAILS)}")
        lines += ["order #5 shipped", "order #77 shipped", "order #x12 shipped"]
        rng.shuffle(lines)
        _write(box, "shipping.txt", lines)
        return {"answer": _count(r"#[0-9]+ shipped", lines),
                "traps": [["one_digit", _count(r"#[0-9] shipped", lines)], ["zero", 0]]}


# --- E. выбор | и группы ( ) ---------------------------------------------------------------

LAUGHS = ("ha", "haha", "hahaha", "hahahaha", "haaa", "aha", "hah", "haha lol", "ok")


class RegexGroup(_RegexAnswer):
    """grep -E: | — или; ( ) — собрать кусок шаблона в группу; группу можно повторить."""
    id = "regex_group"
    title = "То или это"
    par = 55
    scroll = ("| в grep -E — «или»: grep -E 'GET|POST' access.log — строки с тем или другим. "
              "( ) — группа: кусок шаблона вместе. ',(paid|refund),' — колонка со значением "
              "paid либо refund.\n"
              "Без скобок | делит пополам весь шаблон. Группу можно повторить: (12)+ — 12, 1212, "
              "121212.")
    variants = (
        Variant("Сколько строк в app.log уровня WARN или ERROR — всё, кроме обычной болтовни? "
                "Ответ: ans ЧИСЛО",
                wrong=("grep -c WARN app.log", "grep -c 'WARN|ERROR' app.log"),
                alternatives=("grep -vc INFO app.log — то же наоборот: все, кроме INFO",)),
        Variant("Сколько заказов в orders.csv со статусом refund или cancel? В заметках бывает "
                "«refund requested» — это не статус. Ответ: ans ЧИСЛО",
                hints=("Два статуса — «или» в grep -E; колонку держат запятые по краям.",
                       "Или — внутри скобок, чтобы запятые остались по обе стороны: "
                       "',(…|…),'.",
                       "grep -Ec ',(refund|cancel),' orders.csv → ans ЧИСЛО"),
                solution="grep -Ec ',(refund|cancel),' orders.csv",
                wrong=("grep -Ec ',refund|cancel,' orders.csv",
                       "grep -Ec 'refund|cancel' orders.csv"),
                alternatives=("grep -c -e ',refund,' -e ',cancel,' orders.csv — два шаблона "
                              "через -e (expression)",)),
        Variant("В chat.txt одни смеются, другие болтают. Сколько строк целиком из смеха: ha, "
                "haha, hahaha — ha сколько угодно раз и ничего больше? haaa и aha не в счёт. "
                "Ответ: ans ЧИСЛО",
                hints=("Повторить надо два знака сразу — собери их в группу ( ).",
                       "(ha)+ — ha один раз или больше; строка целиком — между ^ и $.",
                       "grep -Ec '^(ha)+$' chat.txt → ans ЧИСЛО"),
                solution="grep -Ec '^(ha)+$' chat.txt",
                wrong=("grep -Ec '^ha+$' chat.txt", "grep -c ha chat.txt"),
                alternatives=("grep -E '^(ha)+$' chat.txt | wc -l — то же через подсчёт "
                              "строк",),
                explain="+ повторяет то, что прямо перед ним: в ha+ — только a (haaa), а в "
                        "(ha)+ — всю группу ha."),
    )
    hints = ("Два уровня сразу — «или»: знак | в grep -E.",
             "Шаблон 'WARN|ERROR' — строки с тем или другим; без -E | — обычный знак.",
             "grep -Ec 'WARN|ERROR' app.log → ans ЧИСЛО")
    solution = "grep -Ec 'WARN|ERROR' app.log"
    explain = ("| в grep -E — «или»: одна команда вместо двух. Скобки собирают кусок шаблона, "
               "чтобы «или» не разрезало весь шаблон пополам.")
    spell = "grep -E 'a|b' — то или это; ',(a|b),' — или внутри группы; (ab)+ — группа подряд"
    trap_messages = {
        "one": "Это только один из двух уровней. Оба сразу — «или»: 'WARN|ERROR' с grep -E.",
        "zero": "Шаблон ничего не нашёл. Частая причина: | + и ( ) работают только с grep -E.",
        "halves": "Без скобок | разрезал шаблон: ',refund' или 'cancel,' где угодно — и "
                  "заметки попали в счёт. Или — в скобки: ',(…|…),'.",
        "notes": "В счёт попали заметки «refund requested». Колонку держи запятыми по краям.",
        "letter": "+ повторил только a: в счёт попал haaa. Повторить ha целиком — группа: "
                  "(ha)+.",
        "inside": "Это все строки, где есть ha, — и aha, и болтовня. Строка целиком — ^…$.",
    }
    fallback = "Не то. «Или» — | в grep -E, кусок шаблона собирают скобки ( )."

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            rows = data._orders(box, rng)
            text = (Path(box) / ORDERS).read_text("utf-8").splitlines()
            return {"answer": sum(r["status"] in ("refund", "cancel") for r in rows),
                    "traps": [["halves", _count(r",refund|cancel,", text)],
                              ["notes", _count(r"refund|cancel", text)],
                              ["zero", 0]]}
        if variant == 2:
            lines = [rng.choice(CHATTER) for _ in range(rng.randint(30, 60))]
            lines += [rng.choice(LAUGHS) for _ in range(rng.randint(20, 40))]
            lines += list(LAUGHS)
            rng.shuffle(lines)
            while _count(r"^ha+$", lines) == _count(r"^(ha)+$", lines):   # ловушка ≠ ответу
                lines.insert(rng.randrange(len(lines) + 1), "haaa")
            _write(box, CHAT, lines)
            return {"answer": _count(r"^(ha)+$", lines),
                    "traps": [["letter", _count(r"^ha+$", lines)],
                              ["inside", _count("ha", lines)], ["zero", 0]]}
        lines = _log_lines(rng)
        kit.write(Path(box) / LOG, "\n".join(lines) + "\n")
        return {"answer": _count(r"WARN|ERROR", lines),
                "traps": [["one", _count("WARN", lines)], ["one", _count("ERROR", lines)],
                          ["zero", 0]]}


# --- F. grep -o -----------------------------------------------------------------------------

DOMAINS = ("mail.sf", "corp.sf", "dataexchange.sf", "inbox.sf", "post.sf", "fastmail.sf")
PEOPLE = ("ann", "bob", "kim", "lee", "max", "zoe", "sam", "eva")


def _contacts(rng, n: int) -> List[str]:
    doms = rng.sample(DOMAINS, rng.randint(3, 6))
    out = []
    for _ in range(n):
        a = f"{rng.choice(PEOPLE)}@{rng.choice(doms)}"
        if rng.random() < 0.4:
            b = f"{rng.choice(PEOPLE)}@{rng.choice(doms)}"
            out.append(f"to {a} cc {b} about invoice")
        else:
            out.append(f"from {a} re: meeting")
    return out


class GrepOnly(_RegexAnswer):
    """grep -o — только совпадение, каждое строкой; | sort | uniq -c — сколько раз каждое."""
    id = "grep_only"
    title = "Только совпадение"
    par = 60
    scroll = ("grep -o (o — only matching, только совпадение) печатает не строку целиком, а "
              "только кусок, что подошёл под шаблон, — каждый на своей строке. Два совпадения в "
              "одной строке — две строки вывода: grep -o 'ID[0-9]' файл | wc -l — сколько их "
              "всего.\n"
              "Дальше — знакомый конвейер: grep -Eo 'шаблон' файл | sort | uniq -c — сколько раз "
              "встретилось каждое.")
    variants = (
        Variant("У ошибок в app.log есть коды: E и три цифры, у некоторых строк — по два кода. "
                "Сколько кодов всего — не строк, а самих кодов? Ответ: ans ЧИСЛО",
                wrong=("grep -c 'E[0-9][0-9][0-9]' app.log",),
                alternatives=("grep -Eo 'E[0-9]{{3}}' app.log | wc -l — то же с повтором "
                              "{{3}}",)),
        Variant("Какой код ошибки (E и три цифры) встречается в app.log чаще всех и сколько раз? "
                "Ответ: ans КОД ЧИСЛО",
                hints=("Сначала вытащи сами коды — grep -o, каждый строкой.",
                       "Коды посчитает знакомый конвейер: sort | uniq -c | sort -rn — частые "
                       "сверху, head -1 — самый частый.",
                       "grep -Eo 'E[0-9]{{3}}' app.log | sort | uniq -c | sort -rn | head -1 → "
                       "ans КОД ЧИСЛО"),
                solution="grep -Eo 'E[0-9]{{3}}' app.log | sort | uniq -c | sort -rn | head -1",
                solution_script="grep -Eo 'E[0-9]{{3}}' app.log | sort | uniq -c | sort -rn | "
                                "head -1 | awk '{{print $2, $1}}'",
                wrong=("print -r -- $(grep -Eo 'E[0-9]{{3}}' app.log | sort | uniq -c | sort -n "
                       "| head -1 | awk '{{print $2, $1}}')",),
                alternatives=("grep -o 'E[0-9][0-9][0-9]' app.log | sort | uniq -c | sort -rn "
                              "— тот же счёт без -E",)),
        Variant("В contacts.txt — письма с адресами, в строке бывает два адреса. Сколько разных "
                "почтовых доменов — того, что после @? Ответ: ans ЧИСЛО",
                hints=("Вытащи из строк только домены: grep -o с шаблоном «@ и буквы с точками».",
                       "Домен — @, потом [a-z.]+ ; одинаковые схлопнет sort | uniq, а "
                       "посчитает wc -l.",
                       "grep -Eo '@[a-z.]+' contacts.txt | sort | uniq | wc -l → ans ЧИСЛО"),
                solution="grep -Eo '@[a-z.]+' contacts.txt | sort | uniq | wc -l",
                wrong=("grep -Eo '@[a-z.]+' contacts.txt | wc -l", "grep -c @ contacts.txt"),
                alternatives=("cut -d@ -f2 contacts.txt — не годится: у строк с двумя "
                              "адресами домены перепутаются; grep -o надёжнее",)),
    )
    hints = ("grep -c считает строки, а в строке бывает два кода. Каждое совпадение строкой "
             "печатает grep -o.",
             "Коды строками — посчитай их wc -l.",
             "grep -o 'E[0-9][0-9][0-9]' app.log | wc -l → ans ЧИСЛО")
    solution = "grep -o 'E[0-9][0-9][0-9]' app.log | wc -l"
    explain = ("grep -c отвечает «сколько строк», а grep -o выдаёт сами совпадения — по одному "
               "в строке. Так из лога вытаскивают коды, номера заказов, адреса, а дальше их "
               "считает старый конвейер sort | uniq -c.")
    spell = "grep -o 'шаблон' файл — только совпадения; | sort | uniq -c — сколько каждого"
    trap_messages = {
        "lines": "Это строки, а не коды: в строке бывает два кода. Каждый строкой печатает "
                 "grep -o.",
        "rare": "Это самый редкий код: sort -n ставит частые вниз. Частые сверху — sort -rn.",
        "all": "Это все адреса, с повторами. Разные — после sort | uniq.",
    }
    fallback = "Не то. Сами совпадения печатает grep -o, считает их конвейер sort | uniq -c."

    def setup_variant(self, box, rng, variant):
        if variant == 2:
            lines = _contacts(rng, rng.randint(30, 60))
            _write(box, "contacts.txt", lines)
            found = [m for x in lines for m in re.findall(r"@[a-z.]+", x)]
            return {"answer": len(set(found)),
                    "traps": [["all", len(found)],
                              ["lines", sum("@" in x for x in lines)]]}
        lines = _log_lines(rng)
        pool = [f"E{n}" for n in rng.sample(range(100, 1000), 5)]
        lines = _plant_codes(rng, lines, rng.randint(25, 50), two=rng.randint(5, 10), pool=pool)
        found = [m for x in lines for m in re.findall(r"E[0-9]{3}", x)]
        counts = Counter(found)
        if variant == 1:
            top = datakit.leader(counts)
            while datakit.lead(counts, top) < 1:    # строгий лидер: его коду — ещё строку
                i = rng.choice([j for j, x in enumerate(lines) if "[ERROR]" in x
                                and "code=" not in x])
                lines[i] += f" code={top}"
                counts[top] += 1
            kit.write(Path(box) / LOG, "\n".join(lines) + "\n")
            rare = min(counts, key=lambda k: (counts[k], k))
            return {"answer": [top, counts[top]], "traps": [["rare", rare]]}
        kit.write(Path(box) / LOG, "\n".join(lines) + "\n")
        return {"answer": len(found),
                "traps": [["lines", _count(r"E[0-9]{3}", lines)]]}


# --- G. sed -E с группами (после sed_fix) --------------------------------------------------

PEOPLE_FULL = (("Lee", "Ann"), ("Park", "Bob"), ("Kim", "Zoe"), ("Stone", "Max"),
               ("Reyes", "Eva"), ("Gray", "Sam"), ("Moss", "Kai"), ("Wolfe", "Ida"))
_SED = re.compile(r"(?:^|[\s|(])sed\s")


class SedGroups(Task):
    """sed -E: ( ) запоминает кусок, \\1 \\2 вставляют его; вырезать кусок, переставить."""
    id = "sed_groups"
    track = "data"
    title = "Переставь куски"
    par = 90
    scroll = ("sed -E (E — Extended) понимает те же регулярки, что grep -E. ( ) в шаблоне "
              "запоминает кусок, а \\1, \\2 в замене вставляют первый, второй кусок: "
              "sed -E 's/(.*) (.*)/\\2 \\1/' — «two one» станет «one two».\n"
              "Что под шаблон не попало, sed оставит как было; .* по краям шаблона захватит "
              "строку целиком — так от строки остаётся только нужный кусок.")
    variants = (
        Variant("Сделай svc.txt: из каждой строки app.log — только имя сервиса, что стоит после "
                "svc= (auth, payments…), по строке на строку лога. app.log не трогай.",
                wrong=("sed 's/.*svc=([a-z]+).*/\\1/' app.log > svc.txt",
                       "sed -E 's/svc=([a-z]+)/\\1/' app.log > svc.txt"),
                alternatives=("grep -o 'svc=[a-z]*' app.log | cut -d= -f2 > svc.txt — то же "
                              "через grep -o и cut",)),
        Variant("В people.txt имена идут как «Фамилия, Имя»: Lee, Ann. Сделай names.txt, где те "
                "же люди — «Имя Фамилия»: Ann Lee. people.txt не трогай.",
                hints=("Два куска поменять местами — две группы ( ) и \\2 \\1 в замене, sed -E.",
                       "Первый кусок — до запятой, второй — после запятой и пробела: "
                       "([A-Za-z]+), ([A-Za-z]+).",
                       "sed -E 's/([A-Za-z]+), ([A-Za-z]+)/\\2 \\1/' people.txt > names.txt"),
                solution="sed -E 's/([A-Za-z]+), ([A-Za-z]+)/\\2 \\1/' people.txt > names.txt",
                wrong=("sed -E 's/([A-Za-z]+), ([A-Za-z]+)/\\1 \\2/' people.txt > names.txt",
                       "sed 's/([A-Za-z]+), ([A-Za-z]+)/\\2 \\1/' people.txt > names.txt"),
                alternatives=("sed -E 's/(.*), (.*)/\\2 \\1/' people.txt > names.txt — .* "
                              "вместо класса букв",)),
        Variant("В sales.csv даты по-американски, месяц-день-год: 09-28-2726. Сделай iso.csv: "
                "те же строки, но дата — год-месяц-день, 2726-09-28. Заголовок останется как "
                "есть, sales.csv не трогай.",
                hints=("Три куска даты — три группы ( ) в sed -E, новый порядок — в замене.",
                       "([0-9]{{2}})-([0-9]{{2}})-([0-9]{{4}}) — месяц, день, год; год — третья "
                       "группа, встаёт первым: \\3-\\1-\\2.",
                       "sed -E 's/([0-9]{{2}})-([0-9]{{2}})-([0-9]{{4}})/\\3-\\1-\\2/' sales.csv "
                       "> iso.csv"),
                solution="sed -E 's/([0-9]{{2}})-([0-9]{{2}})-([0-9]{{4}})/\\3-\\1-\\2/' "
                         "sales.csv > iso.csv",
                wrong=("sed -E 's/([0-9]{{2}})-([0-9]{{2}})-([0-9]{{4}})/\\3-\\2-\\1/' "
                       "sales.csv > iso.csv",
                       "sed 's/([0-9]{{2}})-([0-9]{{2}})-([0-9]{{4}})/\\3-\\1-\\2/' sales.csv "
                       "> iso.csv"),
                alternatives=("sed -E 's/^([0-9]+)-([0-9]+)-([0-9]+)/\\3-\\1-\\2/' sales.csv > "
                              "iso.csv — [0-9]+ и ^: дата в начале строки",),
                explain="Группы нумеруются слева направо: месяц — \\1, день — \\2, год — \\3. В "
                        "замене их ставят в любом порядке: \\3-\\1-\\2."),
    )
    hints = ("Оставить от строки кусок — группа ( ) вокруг него и .* по краям: sed -E.",
             "Имя сервиса — буквы после svc=: svc=([a-z]+); в замене — только \\1.",
             "sed -E 's/.*svc=([a-z]+).*/\\1/' app.log > svc.txt")
    solution = "sed -E 's/.*svc=([a-z]+).*/\\1/' app.log > svc.txt"
    explain = ("( ) запоминает кусок, \\1 вставляет его обратно. .* по краям захватывает строку "
               "целиком, и от неё остаётся только группа. Без -E скобки — обычные знаки, и sed "
               "не находит ничего.")
    spell = "sed -E 's/(a) (b)/\\2 \\1/' — группы ( ) и \\1 \\2: вырезать и переставить куски"

    OUTS = ("svc.txt", "names.txt", "iso.csv")
    SRCS = (LOG, "people.txt", "sales.csv")

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            src = [f"{last}, {first}" for last, first in rng.sample(PEOPLE_FULL,
                                                                     rng.randint(5, 8))]
            want = [re.sub(r"([A-Za-z]+), ([A-Za-z]+)", r"\2 \1", x) for x in src]
        elif variant == 2:
            src = ["date,item,amount"]
            for _ in range(rng.randint(12, 25)):
                src.append(f"09-{rng.randint(1, 30):02d}-2726,{kit.latin(rng)},"
                           f"{rng.randint(10, 900)}")
            want = [re.sub(r"([0-9]{2})-([0-9]{2})-([0-9]{4})", r"\3-\1-\2", x) for x in src]
        else:
            src = _log_lines(rng, per_day=rng.randint(80, 160))
            want = [re.search(r"svc=([a-z]+)", x).group(1) for x in src]
        _write(box, self.SRCS[variant], src)
        return {"src_name": self.SRCS[variant], "out": self.OUTS[variant], "src": src,
                "want": want}

    @staticmethod
    def _read(box, name):
        raw = sandbox.read_in_box(box, name, data.READ_CAP)
        return None if raw is None else raw.decode("utf-8", errors="replace").splitlines()

    def check(self, ctx):
        st = ctx.state
        src = self._read(ctx.box, st["src_name"])
        if src != st["src"]:
            return Verdict(False, f"Исходник {st['src_name']} изменён, а его просили не трогать. "
                                  "Набери reset — он вернётся, — и пиши результат через > в "
                                  "новый файл.")
        got = self._read(ctx.box, st["out"])
        if got is None:
            return Verdict(False)
        if got == st["want"]:
            return Verdict(True)
        return Verdict(False, self._why(got, st, ctx.cmds))

    @staticmethod
    def _why(got: List[str], st: dict, cmds) -> str:
        out, want = st["out"], st["want"]
        seds = [seg for seg in data._segments(cmds) if _SED.search(seg)]
        last = seds[-1] if seds else ""
        no_e = bool(last) and not re.search(r"\bsed\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*E", last)
        if not got:
            return (f"{out} пуст: sed, похоже, ругнулся и ничего не вывел — прочти его "
                    "сообщение. Частая причина: группы ( ) и \\1 работают только с sed -E.")
        if got == st["src"]:
            why = (" Без -E скобки ( ) — обычные знаки, и шаблон не нашёлся." if no_e
                   else " Шаблон ни разу не совпал — проверь его на одной строке: head -1 "
                        "исходника | sed -E '…'.")
            return f"{out} — копия исходника: sed ничего не заменил." + why
        if len(got) != len(want):
            return (f"Строк {len(got)}, а нужно {len(want)}: результат — из всего исходника, "
                    "строка в строку.")
        for a, b in zip(got, want):
            if a != b:
                return (f"Строка не та: «{a}», а нужно «{b}». Проверь порядок групп в замене: "
                        "\\1 — первая скобка слева, \\2 — вторая.")
        return "Не то."


# --- H. финал блока: грязная выгрузка цепочкой ----------------------------------------------

JUNK = ("lorem sync ok", "ping", "---", "ticket closed by bot", "see attached",
        "ORD-1043 typo, ignore", "call back tomorrow", "n/a")


def _dirty(rng):
    """Строки dirty.txt и что в них: номера заказов ORD-#####, телефоны tel: в трёх видах.
    Обрывки ORD-#### (четыре цифры) — мусор."""
    orders = [f"ORD-{n}" for n in rng.sample(range(10000, 99999), rng.randint(8, 14))]
    weights = [rng.randint(1, 6) for _ in orders]
    phones = [f"{rng.choice((415, 628, 510))}{rng.randint(2000000, 9999999)}"
              for _ in range(rng.randint(4, 8))]
    lines = []
    for _ in range(rng.randint(60, 110)):
        kind = rng.choices(("order", "phone", "both", "junk"), (5, 2, 2, 3))[0]
        parts = []
        if kind in ("order", "both"):
            parts.append(f"{rng.choice(('paid', 'refund', 'hold'))} "
                         f"{rng.choices(orders, weights)[0]}")
        if kind in ("phone", "both"):
            parts.append(f"tel: {_phone(rng, rng.choice(phones), rng.randrange(4))}")
        if kind == "junk":
            parts.append(rng.choice(JUNK))
        lines.append(f"2726-09-{rng.randint(1, 30):02d} " + ", ".join(parts))
    for o in orders:                    # каждый заказ — хоть раз
        lines.append(f"2726-09-30 paid {o}")
    lines.append(f"2726-09-{rng.randint(1, 29):02d} ORD-{rng.randint(1000, 9999)} typo, ignore")
    rng.shuffle(lines)
    return lines


class RegexClean(_RegexAnswer):
    """Финал блока: grep -Eo, sed -E и счёт — цепочкой по грязной выгрузке."""
    id = "regex_clean"
    title = "Грязная выгрузка"
    par = 120
    scroll = ("Грязную выгрузку чистят цепочкой: grep -Eo вытаскивает нужные куски, sed -E "
              "приводит их к одному виду, sort | uniq -c считает. Пример: grep -Eo 'id=[0-9]+' "
              "f | sort | uniq | wc -l — сколько разных id.\n"
              "Каждое звено проверяй отдельно: обрежь цепочку на середине и глянь, что "
              "течёт.")
    variants = (
        Variant("dirty.txt — выгрузка поддержки: заказы, телефоны, мусор. Номер заказа — ORD- и "
                "ровно пять цифр; обрывки с четырьмя цифрами — опечатки. Сколько разных "
                "заказов упомянуто? Один заказ упоминают по нескольку раз. Ответ: ans ЧИСЛО",
                wrong=("grep -Eo 'ORD-[0-9]{{5}}' dirty.txt | wc -l",
                       "grep -Eo 'ORD-[0-9]+' dirty.txt | sort | uniq | wc -l"),
                alternatives=("grep -Eo 'ORD-[0-9]{{5}}' dirty.txt | sort -u | wc -l — "
                              "sort -u (unique) схлопывает повторы сам",)),
        Variant("В dirty.txt номера заказов — ORD- и ровно пять цифр. Какой заказ упоминают чаще "
                "всех и сколько раз? Ответ: ans НОМЕР ЧИСЛО",
                hints=("Вытащи номера grep -Eo, дальше — знакомый счёт.",
                       "sort | uniq -c | sort -rn — частые сверху, head -1 — самый частый.",
                       "grep -Eo 'ORD-[0-9]{{5}}' dirty.txt | sort | uniq -c | sort -rn | head -1 "
                       "→ ans НОМЕР ЧИСЛО"),
                solution="grep -Eo 'ORD-[0-9]{{5}}' dirty.txt | sort | uniq -c | sort -rn | "
                         "head -1",
                solution_script="grep -Eo 'ORD-[0-9]{{5}}' dirty.txt | sort | uniq -c | "
                                "sort -rn | head -1 | awk '{{print $2, $1}}'",
                wrong=("print -r -- $(grep -Eo 'ORD-[0-9]{{5}}' dirty.txt | sort | uniq -c | "
                       "sort -n | head -1 | awk '{{print $2, $1}}')",),
                alternatives=("grep -o 'ORD-[0-9][0-9][0-9][0-9][0-9]' dirty.txt | sort | uniq "
                              "-c | sort -rn | head -1 — то же без -E",)),
        Variant("В dirty.txt телефоны идут после tel: и написаны кто как: 4155550134, "
                "415-555-0134, (415) 555-0134, 415 555 0134. Сколько разных телефонов, если "
                "один номер в разном виде — один телефон? Ответ: ans ЧИСЛО",
                hints=("Цепочка: вытащить телефоны, оставить в них одни цифры, посчитать "
                       "разные.",
                       "grep -Eo 'tel: [0-9() -]+' — кусок с телефоном (в классе скобки и "
                       "пробел — обычные знаки); sed -E 's/[^0-9]//g' — убрать всё, кроме "
                       "цифр.",
                       "grep -Eo 'tel: [0-9() -]+' dirty.txt | sed -E 's/[^0-9]//g' | sort | "
                       "uniq | wc -l → ans ЧИСЛО"),
                solution="grep -Eo 'tel: [0-9() -]+' dirty.txt | sed -E 's/[^0-9]//g' | sort | "
                         "uniq | wc -l",
                wrong=("grep -Eo 'tel: [0-9() -]+' dirty.txt | sort | uniq | wc -l",
                       "grep -c 'tel:' dirty.txt"),
                alternatives=("grep -o 'tel: [^,]*' dirty.txt | sed -E 's/[^0-9]//g' | sort "
                              "-u | wc -l — [^,]* — всё до запятой",),
                explain="Один номер в четырёх видах — четыре разные строки, пока в них есть "
                        "скобки, дефисы и пробелы. sed оставил одни цифры, и повторы "
                        "схлопнулись."),
    )
    hints = ("Вытащи номера grep -Eo: ORD- и ровно пять цифр, {{5}}.",
             "Разные — после sort | uniq, посчитает wc -l.",
             "grep -Eo 'ORD-[0-9]{{5}}' dirty.txt | sort | uniq | wc -l → ans ЧИСЛО")
    solution = "grep -Eo 'ORD-[0-9]{{5}}' dirty.txt | sort | uniq | wc -l"
    explain = ("Грязь не чистят руками: grep -Eo вытащил ровно пятизначные номера, мимо "
               "опечаток, а sort | uniq схлопнул повторы. Каждое звено можно проверить "
               "отдельно — обрежь цепочку и глянь.")
    spell = "grep -Eo 'шаблон' f | sed -E 's/…/…/' | sort | uniq -c — чистка цепочкой"
    trap_messages = {
        "repeats": "Это все упоминания, с повторами. Разные — после sort | uniq.",
        "typos": "В счёт попали опечатки с четырьмя цифрами: ровно пять — {{5}}.",
        "forms": "Это разные написания, а не разные телефоны: один номер пишут по-разному. "
                 "Оставь одни цифры: sed -E 's/[^0-9]//g'.",
        "lines": "Это строки с tel:, а не разные телефоны: один номер встречается много раз.",
        "rare": "Это самый редкий заказ: sort -n ставит частые вниз. Частые сверху — sort -rn.",
    }
    fallback = "Не то. Проверь цепочку по звену: обрежь её на середине и глянь, что течёт."

    def setup_variant(self, box, rng, variant):
        lines = _dirty(rng)
        _write(box, "dirty.txt", lines)
        orders = [m for x in lines for m in re.findall(r"ORD-[0-9]{5}", x)]
        loose = [m for x in lines for m in re.findall(r"ORD-[0-9]+", x)]
        if variant == 2:
            raw = [m for x in lines for m in re.findall(r"tel: [0-9() -]+", x)]
            digits = {re.sub(r"[^0-9]", "", m) for m in raw}
            return {"answer": len(digits),
                    "traps": [["forms", len(set(raw))],
                              ["lines", sum("tel:" in x for x in lines)]]}
        counts = Counter(orders)
        if variant == 1:
            top = datakit.leader(counts)
            if datakit.lead(counts, top) < 1:       # строгий лидер: ещё одно упоминание
                lines.append(f"2726-09-30 hold {top}")
                _write(box, "dirty.txt", lines)
                counts[top] += 1
            rare = min(counts, key=lambda k: (counts[k], k))
            return {"answer": [top, counts[top]], "traps": [["rare", rare]]}
        return {"answer": len(set(orders)),
                "traps": [["repeats", len(orders)], ["typos", len(set(loose))]]}


FIRST = [RegexMask(), RegexAnchor(), RegexClass(), RegexRepeat(), RegexGroup(), GrepOnly()]
SED = [SedGroups(), RegexClean()]
insert_after(data.TASKS, "top_values", FIRST)
insert_after(data.TASKS, "sed_fix", SED)
