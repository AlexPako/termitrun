"""Трек «Инструменты»: справка, less, nano, vim, задачи в фоне."""
import hashlib
import json
import os
import re
import shutil
import tarfile
from pathlib import Path
from typing import List

from termit_app import brewstub, implants, sandbox, textnorm
from termit_app.tasks import kit
from termit_app.tasks.base import AnswerTask, Task, Variant, Verdict, sources, variant_index

# Слово для поиска: в less поиск чувствителен к регистру, и ПЕРВОЕ совпадение в man
# должно попадать на строку нужного флага (проверяет tests/test_tools_unit.ManPoolTest).
MAN_POOL = [
    ("ls", "сортирует файлы по размеру", "-S", "by size"),
    ("sort", "сортирует в обратном порядке", "-r", "reverse"),
    ("wc", "считает байты", "-c", "number of bytes"),
    ("grep", "ищет без учёта больших и маленьких букв", "-i", "case"),
    ("du", "показывает размеры в «человеческих» единицах (K, M, G)", "-h", "Human"),
    ("head", "задаёт, сколько строк показать", "-n", "Print count"),
]

# Вариант B — другой пул, то же правило первого совпадения. У ls вместо -a взят -A: строка
# -a в man слово в слово повторяет начало строки -A, а -A стоит выше — до -a поиск не дойдёт.
MAN_POOL_B = [
    ("cp", "не перезаписывает уже существующий файл", "-n", "Do not overwrite"),
    ("mkdir", "создаёт и все недостающие промежуточные папки", "-p", "intermediate"),
    ("rm", "спрашивает подтверждение перед удалением каждого файла", "-i", "before attempting"),
    ("ls", "показывает скрытые файлы, но без строк . и ..", "-A", "except for"),
]

# Длинная форма флага — как она стоит в man macOS на той же строке (tests/test_tools_unit
# сверяет с настоящей справкой). Кто дочитал до неё, сдаёт верный ответ (Н приёмки-1).
MAN_LONG = {("sort", "-r"): "--reverse", ("grep", "-i"): "--ignore-case",
            ("grep", "-v"): "--invert-match", ("uniq", "-c"): "--count"}

# Вариант C — обратный вопрос: (команда, флаг, начала принимаемых слов, слово-ответ эталона,
# слово-обманка). Обманка — из соседнего флага, куда легко промахнуться поиском: /-v в man grep
# сначала находит --version, /-n в man sort — --general-numeric-sort.
MAN_POOL_C = [
    ("ls", "-r", ("revers",), "reverse", "recursive"),
    ("grep", "-v", ("invert", "invers"), "invert", "version"),
    ("wc", "-l", ("line",), "lines", "longest"),
    ("sort", "-n", ("numer", "arithmetic"), "numeric", "general"),
    ("uniq", "-c", ("count",), "count", "repeated"),
    ("head", "-c", ("byte",), "bytes", "lines"),
]


class ManFlag(AnswerTask):
    id = "man_flag"
    track = "tools"
    title = "Спроси у справки"
    case_sensitive = True
    scroll = ("man COMMAND — полная справка по команде COMMAND. Внутри: пробел — страница вниз, "
              "b — вверх, /WORD и Enter — искать слово WORD, n — следующее совпадение, q — "
              "выйти.\n"
              "Поиск различает большие и маленькие буквы. Флаг — минус и буква в начале строки "
              "описания; сдают его так: ans, пробел, минус и эта буква.")
    variants = (
        Variant("Каким флагом {cmd} {what}? Не гадай — найди в справке: man {cmd}, внутри "
                "ищи «{word}». Сдай флаг — минус и букву: ans -X, где -X — "
                "найденный флаг",
                wrong=("print -r -- {decoy}",),
                alternatives=("man {cmd} | grep -B1 '{word}' — строка со словом и та, что над "
                              "ней (-B1 — одна строка до совпадения), без листания",)),
        Variant("Какой флаг у {cmd} отвечает за то, что команда {what}? Найди в справке: "
                "man {cmd}, внутри ищи «{word}». Сдай флаг — минус и букву: ans -X, где -X — "
                "найденный флаг",
                wrong=("print -r -- {decoy}",),
                alternatives=("man {cmd} | grep -B1 '{word}' — найти строку, не открывая "
                              "листалку; -B1 добавит строку над совпадением",)),
        Variant("У {cmd} есть флаг {flag}. Что он делает? Открой man {cmd} и найди строку, "
                "которая начинается с {flag} (поиск: /{flag}). Первое совпадение бывает вверху, "
                "в строке-образце SYNOPSIS («краткий вид»): там все флаги команды подряд в "
                "квадратных скобках, вроде [-abc], без описаний — жми n, пока не дойдёшь до "
                "строки флага. Сдай одно слово из её описания — "
                "по-английски, как в man, — главное слово: то, что есть только у этого флага. "
                "Пример: у ls -l описание «List files in the long format» — список ls "
                "печатает всегда, а long — только с -l: сдают long. Сдают слово, а не флаг: "
                "ans WORD",
                hints=("Справка — man {cmd}. Внутри ищи сам флаг: /{flag} и Enter.",
                       "Поиск ловит и куски длинных слов: жми n, пока строка не начнётся "
                       "с {flag}. Большая и маленькая буква — разные флаги.",
                       "man {cmd}, /{flag}, n до строки «{flag} …», ключевое слово "
                       "описания, например ans {answer}"),
                solution="man {cmd}, затем /{flag}, n до строки флага, q",
                solution_script="print -r -- {answer}",
                wrong=("print -r -- {decoy}",),
                alternatives=("man {cmd} | col -b | grep -A2 -- '^ *{flag}' — описание "
                              "флага без листания: col -b счищает жирный шрифт man, без него "
                              "grep флаг не найдёт; -A2 — ещё две строки после совпадения",)),
    )
    par = 45
    hints = ("Справка по команде — man {cmd}. Внутри ищи слово через /.",
             "man {cmd}, потом /{word} и Enter; n — следующее совпадение.",
             "Ответ — буква с минусом в начале строки с «{word}» (или строкой выше). "
             "Сдай: ans -X, где -X — эта буква с минусом")
    solution = "man {cmd}, затем /{word}, n, q"
    solution_script = "print -r -- {answer}"
    explain = "man — главный справочник на Mac. Ищи через / — и не листай минутами."
    spell = "man COMMAND — справка; внутри /WORD — поиск, n — дальше, q — выход"

    def setup_variant(self, box, rng, variant):
        if variant == 2:
            cmd, flag, accept, answer, decoy = rng.choice(MAN_POOL_C)
            return {"cmd": cmd, "flag": flag, "accept": list(accept), "answer": answer,
                    "decoy": decoy}
        cmd, what, answer, word = rng.choice(MAN_POOL_B if variant == 1 else MAN_POOL)
        return {"cmd": cmd, "what": what, "answer": answer, "word": word,
                "decoy": answer.swapcase()}

    def matches(self, given, ctx):
        if ctx.state.get("_variant") == 2:      # ключевое слово описания, без регистра
            words = re.findall(r"[a-zа-яё]+", textnorm.norm(given).casefold())
            return any(w.startswith(a) for w in words for a in ctx.state["accept"])
        flag = ctx.state["answer"]
        forms = {flag, MAN_LONG.get((ctx.state.get("cmd"), flag), flag)}
        # «-r», «r», «--reverse» и строка из man целиком «-r, --reverse»
        got = [x if x.startswith("-") else "-" + x
               for x in re.split(r"[\s,]+", textnorm.clean(given)) if x]
        return 0 < len(got) <= 2 and all(x in forms for x in got)

    def wrong_message(self, given, ctx):
        if ctx.state.get("_variant") != 2:
            word = textnorm.clean(given)
            if re.fullmatch(r"[A-Za-z]{2,}", word):
                return ("Нужен сам флаг: минус и буква из начала строки справки, например "
                        "-x. Слово из описания — это не флаг.")
            return super().wrong_message(given, ctx)
        if re.search(r"[а-яё]", given.casefold()):
            return "Сдай слово из справки — по-английски, как написано в man."
        return (f"Это слово не говорит, что делает {ctx.state['flag']}. Найди строку, которая "
                f"начинается с {ctx.state['flag']}: какое слово в ней есть только у этого "
                "флага?")


class FlagUse(AnswerTask):
    """FB3 (6): флаг не на карточке — найди его в справке и примени. Флаг со значением,
    длинная форма, «--» — конец флагов."""
    id = "flag_use"
    track = "tools"
    title = "Найди флаг и примени"
    scroll = ("Флаг не помнишь — найди сам: man COMMAND, /WORD и Enter, q — выйти.\n"
              "Флаг ставят сразу после имени команды: grep -X PATTERN FILE.\n"
              "Флагу нужно число — оно идёт следом: head -X 5 FILE.")
    variants = (
        Variant("Сколько строк со словом ERROR в server.log? grep умеет сам считать совпавшие "
                "строки — найди этот флаг в man grep и примени. Ответ: ans NUMBER (NUMBER — сюда "
                "число строк)",
                wrong=("grep ERROR server.log",),
                alternatives=("grep ERROR server.log — и сосчитать строки глазами: дольше и "
                              "легко сбиться",)),
        Variant("Пароль — первые {n} символов файла code.txt. head умеет брать не строки, а "
                "символы (в справке они зовутся bytes, «байты»): найди флаг в man head и сдай "
                "пароль: ans PASSWORD (PASSWORD — сюда эти символы)",
                hints=("Нужен флаг head про байты: man head, внутри /bytes.",
                       "Флаг со значением: число символов идёт следом за флагом.",
                       "head -c {n} code.txt — и ans PASSWORD, где PASSWORD — эти символы"),
                solution="head -c {n} code.txt",
                solution_script="head -c {n} code.txt",
                wrong=("head -n {n} code.txt",),
                alternatives=("ans $(head -c {n} code.txt) — подставить сразу",)),
        Variant("ls показывает папку queue по алфавиту. Какое имя окажется первым, если ls "
                "перевернёт порядок? Флаг «наоборот» найди в man ls. Ответ: ans NAME (NAME — сюда "
                "имя файла, как ls его напечатал)",
                hints=("В man ls ищи слово Reverse — с большой R, как в справке: /Reverse и "
                       "Enter.",
                       "Флаг переворачивает любой порядок ls — и по алфавиту тоже.",
                       "ls -r queue — первое имя сверху, его и сдай"),
                solution="ls -r queue",
                solution_script="ls -r queue | head -1",
                wrong=("ls queue | head -1",),
                alternatives=("ls queue — и взять последнее имя снизу",)),
    )
    # флаги, которые игрок находит в справке сам: «сначала учим» их с карточек не ждёт
    man_flags = ("-c", "-r")
    par = 45
    hints = ("Флаг для подсчёта — в справке: man grep, внутри /count.",
             "Нашёл строку «-c …» — это он. Выйди из man (q) и примени флаг к файлу.",
             "grep -c ERROR server.log — и ans NUMBER, где NUMBER — число, что напечатал grep")
    solution = "grep -c ERROR server.log"
    explain = ("Флага нет на карточке — не беда: man COMMAND и /WORD выудят его за "
               "полминуты. Бывает, флаг ждёт значение — head -c 5 — его пишут следом.")
    spell = "man COMMAND, /WORD — найти флаг; флаг со значением: head -c 5"
    trap_messages = {"all": "Это все строки файла, а нужны только строки с ERROR.",
                     "first": "Это первое имя по алфавиту. Нужно первое, когда ls перевернёт "
                              "порядок.",
                     "line": "Это вся строка, а пароль — только первые {n} символов. head -n "
                             "считает строки, а символы — другой флаг: ищи в man head."}

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            n = rng.randint(5, 8)
            code = "".join(rng.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(12))
            kit.write(box / "code.txt", code + "\n")
            return {"n": n, "answer": code[:n], "traps": [["line", code]],
                    "sources": sources(box, "code.txt")}
        if variant == 2:
            names = sorted(f"{w}.txt" for w in rng.sample(kit.LATIN, 5))
            for name in names:
                kit.write(box / "queue" / name, "queued\n")
            return {"answer": names[-1], "traps": [["first", names[0]]]}
        kinds = ["INFO", "INFO", "WARN", "ERROR"]
        levels = [rng.choice(kinds) for _ in range(rng.randint(9, 14))]
        if "ERROR" not in levels:
            levels[rng.randrange(len(levels))] = "ERROR"
        rows = [f"12:{i:02d} {lv} job {kit.latin(rng)}" for i, lv in enumerate(levels)]
        kit.write(box / "server.log", "\n".join(rows) + "\n")
        return {"answer": str(levels.count("ERROR")), "traps": [["all", len(rows)]],
                "sources": sources(box, "server.log")}

    def answer_kind(self, state):
        return "number" if state.get("_variant", 0) == 0 else "text"

    def matches(self, given, ctx):
        if ctx.state.get("_variant") == 1:          # пароль — с учётом регистра, ровно
            return textnorm.clean(given) == ctx.state["answer"]
        return super().matches(given, ctx)


class LessSearch(AnswerTask):
    id = "less_search"
    track = "tools"
    title = "Иголка в логе"
    scroll = ("less FILE — листать большой файл FILE. Пробел — страница вниз, b — вверх, "
              "/WORD и Enter — поиск, n — следующее, Shift+G — в конец, g — в начало, q — "
              "выход.\n"
              "Поиск различает регистр: less -i FILE (ignore case, или -i и Enter прямо в less) — "
              "большие и маленькие буквы равны, пока в поиске нет большой; less -I FILE (IGNORE "
              "CASE) — равны всегда.")
    variants = (
        Variant("В логе server.log больше {n} строк. В строке с CRITICAL в конце стоит "
                "число — какое? И какое слово стоит после «Signature:» в самой последней строке? "
                "Сдай оба через пробел: ans NUMBER WORD (NUMBER — то число, WORD — то слово)",
                wrong=("grep CRITICAL server.log | cut -c1-5; tail -1 server.log | cut -d' ' -f2",),
                alternatives=("grep CRITICAL server.log и grep Signature server.log — обе строки без "
                              "листания",)),
        Variant("В логе server.log больше {n} строк, каждая начинается с пятизначного номера. "
                "Найди ПЕРВУЮ строку с WARN и сдай её номер: ans NUMBER (NUMBER — эти пять "
                "цифр)",
                hints=("Лог огромный — открывай в less, руками его не пролистать.",
                       "В less: /WARN и Enter прыгнет к первому совпадению. n — уже второе, "
                       "оно не нужно.",
                       "less server.log, /WARN, первые 5 цифр строки, q, ans и эти цифры"),
                solution="less server.log, /WARN, номер строки, q",
                solution_script="grep -m1 WARN server.log | cut -c1-5",
                wrong=("grep WARN server.log | sed -n 2p | cut -c1-5",),
                alternatives=("grep -m1 WARN server.log — -m1 остановит grep на первой "
                              "находке",)),
        Variant("В логе server.log больше {n} строк, и где-то в нём сервис перезапускался — "
                "строка с RESTART. Какое событие записано сразу после неё? Сдай его без "
                "номера строки: ans EVENT (EVENT — текст той строки после номера)",
                hints=("Открой лог в less и найди перезапуск поиском.",
                       "/RESTART и Enter — курсор на нужной строке; ответ — строка под ней.",
                       "less server.log, /RESTART, строка ниже, без номера, q, ans и её текст"),
                solution="less server.log, /RESTART, строка ниже, q",
                solution_script="grep -A1 RESTART server.log | tail -1 | cut -d' ' -f2-",
                wrong=("grep -B1 RESTART server.log | head -1 | cut -d' ' -f2-",),
                alternatives=("grep -A1 RESTART server.log — строка и одна после неё: -A1 — одна "
                              "строка после совпадения",)),
    )
    par = 50
    hints = ("Открой лог в less: cat вывалит на экран простыню, которой не видно конца.",
             "В less: /CRITICAL и Enter — найти; Shift+G — прыгнуть в самый конец.",
             "less server.log, /CRITICAL, запомни число, Shift+G, слово в последней строке, q")
    solution = "less server.log, /CRITICAL, Shift+G, q"
    solution_script = ("grep CRITICAL server.log | grep -oE '[0-9]+$'; "
                       "tail -1 server.log | cut -d' ' -f2")
    explain = "less не тащит файл целиком и умеет искать — им и читают логи на миллион строк."
    spell = "less FILE — листать; /WORD — поиск, n — дальше, Shift+G — конец, q — выход"

    EVENTS = ["INFO backup done", "INFO user login", "INFO cache cleared", "INFO cron ok",
              "WARN slow query", "INFO sync done", "INFO health ok"]
    # после перезапуска — события, которых в остальном логе нет: не угадать по частоте
    AFTER_RESTART = ["INFO config reloaded", "WARN cache cold", "INFO journal replayed",
                     "INFO workers up", "WARN queue backlog"]

    def setup_variant(self, box, rng, variant):
        n = rng.randint(3000, 6000)
        if variant == 0:
            num, seal = rng.randint(100, 9999), kit.latin(rng)
            pos = rng.randint(n // 4, n - 10)
            lines = [f"{i:05d} CRITICAL disk failure, code {num}" if i == pos
                     else f"{i:05d} {rng.choice(self.EVENTS)}" for i in range(n)]
            lines.append(f"Signature: {seal}")
            kit.write(box / "server.log", "\n".join(lines) + "\n")
            return {"n": n, "answer": f"{num} {seal}",
                    "traps": [["lineno", f"{pos:05d} {seal}"], ["lineno", f"{pos} {seal}"]],
                    "sources": sources(box, "server.log")}
        quiet = [e for e in self.EVENTS if not e.startswith("WARN")]
        if variant == 1:
            # до первого WARN — только INFO, дальше WARN встречаются как обычно
            first = rng.randint(n // 5, n // 2)
            events = [rng.choice(quiet) if i < first else
                      "WARN disk almost full" if i == first else rng.choice(self.EVENTS)
                      for i in range(n)]
            if not any(e.startswith("WARN") for e in events[first + 1:]):
                events[-5] = "WARN slow query"
            lines = [f"{i:05d} {e}" for i, e in enumerate(events)]
            kit.write(box / "server.log", "\n".join(lines) + "\n")
            second = next(i for i in range(first + 1, n) if events[i].startswith("WARN"))
            return {"n": n, "answer": f"{first:05d}", "traps": [["second", f"{second:05d}"]],
                    "sources": sources(box, "server.log")}
        pos = rng.randint(n // 4, n - 10)
        after = rng.choice(self.AFTER_RESTART)
        events = [rng.choice(self.EVENTS) for _ in range(n)]
        events[pos] = "CRIT service RESTART"
        events[pos + 1] = after
        lines = [f"{i:05d} {e}" for i, e in enumerate(events)]
        kit.write(box / "server.log", "\n".join(lines) + "\n")
        prev = events[pos - 1]
        return {"n": n, "answer": after,
                "traps": [["before", prev], ["before", prev.split(" ", 1)[1]],
                          ["restart", "CRIT service RESTART"], ["restart", "service RESTART"]],
                "sources": sources(box, "server.log")}

    trap_messages = {
        "second": "Это не первая строка с WARN: n уводит к следующей. После /WARN и Enter less "
                  "стоит на первой.",
        "before": "Это строка над RESTART, а нужна та, что под ней.",
        "restart": "Это сама строка перезапуска, а нужна следующая — под ней.",
        "lineno": "Число в начале — номер строки, а нужно то, что стоит в самом конце строки "
                  "с CRITICAL.",
    }

    def answer_kind(self, state):
        return "number" if state.get("_variant") == 1 else "text"

    def matches(self, given, ctx):
        if ctx.state.get("_variant") == 1:      # номер: «00731» и «731» — одно число
            return textnorm.same_number(given, ctx.state["answer"])
        if ctx.state.get("_variant") == 2:      # событие: уровень (INFO/WARN) можно опустить
            ans = ctx.state["answer"]
            return any(textnorm.same_words(given, a) for a in (ans, ans.split(" ", 1)[1]))
        # число и слово: порядок и запятая между ними не важны («6568, lighthouse»)
        return textnorm.same_parts(given, str(ctx.state["answer"]).split())


class NanoConfig(Task):
    id = "nano_config"
    track = "tools"
    title = "Конфиг в nano"
    scroll = ("nano FILE — простой редактор для файла FILE (на Mac вверху написано UW PICO — "
              "это он). Внизу подсказки, ^ — это Ctrl. Backspace — стереть букву слева, Ctrl+A "
              "— в начало строки, Ctrl+W — поиск куска текста, Ctrl+K — вырезать строку, "
              "Ctrl+X — выйти.\n"
              "Ctrl+W и сразу Enter — искать то же дальше. Ctrl+X по несохранённому файлу "
              "спросит, сохранить ли: Y, потом Enter; N — выйти без сохранения, Ctrl+C — "
              "остаться. Сохранил — игра сама сверит файл.")
    variants = (
        Variant("В конфиге app.conf замени port 5432 на 6432 (строка «port = 5432») и удали "
                "строку с debug. backup_port не трогай. Открой файл в nano: nano app.conf — "
                "и сохрани, ans не нужен.",
                wrong=("sed -i '' -e 's/5432/6432/' -e '/^debug = /d' app.conf",),
                alternatives=("nano app.conf, Ctrl+W port и Enter — прыжок к строке с port "
                              "без листания; встал на backup_port — Ctrl+W и Enter ещё раз",)),
        Variant("В db.ini поменяй пользователя: user = test должно стать user = admin. И допиши "
                "в самый конец файла новую строку timeout = 30: стрелкой вниз, пока курсор не "
                "встанет на пустую строку под последней. Остальное не трогай. Открой файл в "
                "nano: nano db.ini — и сохрани, ans не нужен.",
                hints=("Открой файл: nano db.ini",
                       "Ctrl+W user — найти строку, исправь test на admin; потом стрелкой вниз "
                       "до самого конца файла и напечатай новую строку.",
                       "nano db.ini, в строке user исправить test на admin, в конце файла "
                       "дописать timeout = 30, Ctrl+X, Y, Enter"),
                solution="nano db.ini, в строке user исправить test на admin, в конце "
                         "дописать timeout = 30, Ctrl+X, Y, Enter",
                solution_script=("sed -i '' 's/^user = test$/user = admin/' db.ini && "
                                 "echo 'timeout = 30' >> db.ini"),
                wrong=("sed -i '' 's/test/admin/' db.ini && echo 'timeout = 30' >> db.ini",
                       "sed -i '' 's/^user = test$/user = admin/' db.ini"),
                alternatives=("echo 'timeout = 30' >> db.ini — >> дописывает строку в конец "
                              "файла без редактора",)),
        Variant("В web.conf закомментируй строку ssl = off — поставь в её начало решётку, чтобы "
                "вышло «# ssl = off». И замени workers = {workers} на workers = {new_workers}. "
                "ssl_cert и max_workers не трогай. Решётку набирай в английской раскладке: "
                "Shift+3. Открой файл в nano: nano web.conf — и сохрани, ans не нужен.",
                hints=("Открой файл: nano web.conf",
                       "Решётка ставится в самое начало строки: встань на ssl = off, Ctrl+A — в "
                       "начало строки, набери # и пробел. workers ищи через Ctrl+W.",
                       "nano web.conf, в начало строки ssl = off дописать # и пробел, в "
                       "строке workers число {new_workers}, Ctrl+X, Y, Enter"),
                solution="nano web.conf, закомментировать ssl = off, в строке workers "
                         "поставить {new_workers}, Ctrl+X, Y, Enter",
                solution_script=("sed -i '' -e 's/^ssl = off$/# ssl = off/' "
                                 "-e 's/^workers = {workers}$/workers = {new_workers}/' web.conf"),
                wrong=("sed -i '' -e 's/^ssl = off$/# ssl = off/' "
                       "-e 's/workers = [0-9]*/workers = {new_workers}/' web.conf",
                       "sed -i '' -e 's/^ssl/# ssl/' "
                       "-e 's/^workers = {workers}$/workers = {new_workers}/' web.conf"),
                alternatives=("nano web.conf, Ctrl+W ssl и Enter — прыжок прямо к строке, "
                              "которую надо закомментировать",)),
    )
    par = 60
    hints = ("Открой файл: nano app.conf",
             "Ctrl+W port — найти строку (попал на backup_port — Ctrl+W и Enter ищут дальше); "
             "исправь число; на строке debug нажми Ctrl+K.",
             "nano app.conf: исправь port, Ctrl+K на строке debug, Ctrl+X, Y, Enter — "
             "сохранить и выйти. Проверить: cat app.conf")
    solution = "nano app.conf, исправить port, Ctrl+K на строке debug, Ctrl+X, Y, Enter"
    solution_script = "sed -i '' -e 's/^port = 5432$/port = 6432/' -e '/^debug = /d' app.conf"
    explain = "Так конфиги на серверах и правят: открыл, нашёл, поправил, сохранил."
    spell = "nano FILE — редактор: Ctrl+W поиск, Ctrl+K вырезать строку, Ctrl+X, Y, Enter — сохранить и выйти"

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            keys = [("host", "127.0.0.1"), ("port", "5432"), ("name", "test_db"),
                    ("user", "test"), ("password", f"{kit.latin(rng)}{rng.randint(10, 99)}"),
                    ("pool", str(rng.randint(2, 20)))]
            rng.shuffle(keys)
            body = "".join(f"{k} = {v}\n" for k, v in keys)
            f = kit.write(box / "db.ini", "[database]\n" + body)
            want = ("[database]\n" + body.replace("user = test\n", "user = admin\n") +
                    "timeout = 30\n")
            return {"file": "db.ini", "want": want, "orig": kit.sha(f)}
        if variant == 2:
            workers = rng.randint(2, 8)
            new = workers + rng.randint(1, 8)
            keys = [("server_name", f"{kit.latin(rng)}.local"), ("listen", "8443"),
                    ("ssl", "off"), ("ssl_cert", "/etc/ssl/site.pem"),
                    ("workers", str(workers)), ("max_workers", str(rng.randint(20, 64))),
                    ("log_level", "info")]
            rng.shuffle(keys)
            lines = [f"{k} = {v}\n" for k, v in keys]
            f = kit.write(box / "web.conf", "".join(lines))
            fix = {"ssl = off\n": "# ssl = off\n",
                   f"workers = {workers}\n": f"workers = {new}\n"}
            want = "".join(fix.get(l, l) for l in lines)
            return {"file": "web.conf", "workers": workers, "new_workers": new,
                    "want": want, "orig": kit.sha(f)}
        keys = [("name", f"app-{kit.latin(rng)}"), ("host", "127.0.0.1"), ("port", "5432"),
                ("backup_port", "5432"), ("debug", "true"), ("workers", str(rng.randint(2, 16))),
                ("log_dir", "/var/log/app"), ("timeout", str(rng.randint(10, 90)))]
        rng.shuffle(keys)
        f = kit.write(box / "app.conf", "".join(f"{k} = {v}\n" for k, v in keys))
        want = "".join(f"{k} = {'6432' if k == 'port' else v}\n" for k, v in keys if k != "debug")
        return {"file": "app.conf", "want": want, "orig": kit.sha(f)}

    def check(self, ctx):
        return check_edit(ctx.box / ctx.state.get("file", "app.conf"), ctx.state)


def check_edit(f, state) -> Verdict:
    """Правка файла в редакторе: точное совпадение; при ошибке — разница «ждали/получилось»."""
    if not f.is_file():
        return Verdict(False, f"Файл {f.name} пропал — набери reset.")
    got = f.read_text("utf-8", errors="replace")
    if got.rstrip("\n") == state["want"].rstrip("\n"):
        return Verdict(True)
    if kit.sha(f) == state["orig"]:
        return Verdict(False)
    return Verdict(False, "Файл ты поменял, но пока не так:\n" + kit.diff_text(got, state["want"]) +
                   "\n   Запутался — reset вернёт файл как был.")


COMMIT_SH = """#!/bin/sh
# Opens the message in vim, just like git commit does.
cd "$(dirname "$0")" || exit 1
cat > message.txt <<'EOT'
__BODY__
EOT
__NOEOL__before=$(md5 -q message.txt)
if [ -n "$TERMIT_VIM_EX" ]; then
  vim -Es -u NONE __VIMARGS__ -c "$TERMIT_VIM_EX" -c wq message.txt   # for reference tests
else
  vim __VIMARGS__ message.txt
fi
after=$(md5 -q message.txt)
grep -v '^#' message.txt | sed '/^[[:space:]]*$/d' > result.txt
echo "$before $after" > .msg_hash
echo "vim closed."
"""

VIM_SCROLL = ("vim — редактор, в который тебя закидывают другие программы и серверы. Он стартует в "
              "режиме команд: "
              "буквы — это приказы, а не текст. i — начать печатать, Esc — закончить, "
              ":wq и Enter — сохранить и выйти, :q! и Enter — выйти без сохранения.\n"
              "Команды vim набирай в английской раскладке: в русской :wq превратится в :цй.")


NO_EOL = 'printf \'%s\' "$(cat message.txt)" > message.txt   # no trailing newline\n'


def _commit_sh(box, body: str, no_eol: bool = False, vim_args: str = ""):
    """vim_args — стартовые -c для vim (и в эталонной ветке тоже: TERMIT_VIM_EX идёт после
    них, как клавиши игрока после старта)."""
    text = (COMMIT_SH.replace("__BODY__", body).replace("__NOEOL__", NO_EOL if no_eol else "")
            .replace("__VIMARGS__", vim_args))
    p = kit.write(box / "commit.sh", text)
    os.chmod(p, 0o755)


class VimTrap(Task):
    id = "vim_trap"
    track = "tools"
    title = "Капкан Vim: сохранить и выйти"
    autorun = "./commit.sh"
    scroll = VIM_SCROLL
    variants = (
        Variant("Впиши в vim строку «Signed: {name}» (подписано) и выйди С сохранением. Игра "
                "попросит нажать Enter и сама запустит скрипт ./commit.sh — он откроет vim, "
                "как это делают и другие программы, когда ждут от тебя текст. Первая строка "
                "там пустая — пиши в неё. Не вышло — набери ./commit.sh и Enter, начни снова.",
                wrong=("TERMIT_VIM_EX='q!' ./commit.sh",),
                alternatives=("ZZ — то же, что :wq, без двоеточия",)),
        Variant("Замени в vim строку-заглушку TODO одной строкой своего текста — любой, хоть "
                "одним словом — и выйди с сохранением. Нажми Enter, когда игра попросит, — "
                "откроется vim, курсор уже на строке TODO. В vim: S (Shift+s) — стереть строку "
                "под курсором и сразу печатать. Не вышло — набери ./commit.sh и Enter.",
                hints=("Ты в vim, курсор уже на строке TODO. Её нужно стереть и напечатать своё.",
                       "Не вышло с S — то же делает cc. Или по-простому: A (Shift+a) — печатать "
                       "в конце строки, потом Backspace четыре раза.",
                       "./commit.sh, S, свой текст, Esc, :wq, Enter"),
                solution="S, свой текст, Esc, :wq",
                solution_script="TERMIT_VIM_EX='1s/^TODO$/Fix login/' ./commit.sh",
                wrong=("TERMIT_VIM_EX='q!' ./commit.sh",
                       "TERMIT_VIM_EX='1s/^/Done /' ./commit.sh"),
                alternatives=("cc — то же, что S: стереть строку и печатать заново",)),
        Variant("Допиши в vim последней строкой «Checked: {name}» (проверено) и выйди с "
                "сохранением. Нажми Enter, когда игра попросит, — откроется vim с готовым "
                "сообщением. В vim: большая G — на последнюю строку (это Shift+G), o — новая "
                "строка под ней и сразу печать. Не вышло — набери ./commit.sh и Enter.",
                hints=("Ты в vim. Чтобы писать в конце, сначала прыгни на последнюю строку.",
                       "Без Shift+G и o тоже можно: стрелками вниз до последней строки, A — печатать "
                       "в её конце, Enter — новая строка.",
                       "./commit.sh, Shift+G, o, «Checked: {name}», Esc, :wq, Enter"),
                solution="Shift+G, o, «Checked: {name}», Esc, :wq",
                solution_script="TERMIT_VIM_EX='normal GoChecked: {name}' ./commit.sh",
                wrong=("TERMIT_VIM_EX='q!' ./commit.sh",
                       "TERMIT_VIM_EX='normal ggOChecked: {name}' ./commit.sh"),
                alternatives=(":$ и Enter — тоже прыжок на последнюю строку",)),
    )
    par = 60
    hints = ("Ты в vim. Сначала i — тогда буквы станут текстом.",
             "Напечатай строку, потом Esc, переключи раскладку на английскую и набери :wq",
             "./commit.sh, i, «Signed: {name}», Esc, :wq, Enter")
    solution = "i, «Signed: {name}», Esc, :wq"
    solution_script = "TERMIT_VIM_EX='1s/^$/Signed: {name}/' ./commit.sh"
    explain = "i — вставка, Esc — назад в команды, :wq — записать и выйти. Хватит, чтобы не застрять."
    spell = "vim: i — печатать, Esc — стоп, :wq — сохранить и выйти"

    SAVE = "\n# Lines starting with # will be ignored. Esc, then :wq and Enter to save and quit."

    def setup_variant(self, box, rng, variant):
        name = kit.latin(rng).capitalize()
        if variant == 1:
            _commit_sh(box, "TODO\n# Replace the TODO line with one line of your own text."
                            "\n# S (Shift+s) clears the line under the cursor and starts typing." +
                       self.SAVE)
            return {"name": name}
        if variant == 2:
            body = [f"Update {kit.latin(rng)}", f"Fix {kit.word(rng)}"]
            line = f"Checked: {name}"
            _commit_sh(box, "\n".join(body) + f"\n# Add as the last line: {line}"
                       "\n# G jumps to the last line, o opens a new line below and starts typing." +
                       self.SAVE)
            return {"name": name, "body": body, "line": line}
        _commit_sh(box, "\n# Type on the first line: Signed: " + name +
                   "\n# i to type, Esc to stop, :wq and Enter to save and quit."
                   "\n# Lines starting with # will be ignored.")
        return {"name": name}

    def check(self, ctx):
        r = ctx.box / "result.txt"
        if not r.exists():
            return Verdict(False)
        lines = [l.strip() for l in r.read_text("utf-8", errors="replace").splitlines() if l.strip()]
        v = ctx.state.get("_variant", 0)
        if v == 1:
            if len(lines) == 1 and "TODO" not in lines[0]:
                return Verdict(True)
            return Verdict(False, "Нужна одна строка твоего текста, и TODO в ней остаться не "
                                  "должно. Запусти ./commit.sh ещё раз.")
        if v == 2:
            if lines == ctx.state["body"] + [ctx.state["line"]]:
                return Verdict(True)
            return Verdict(False, "Строка не та, не в конце или не сохранилась. Запусти "
                                  "./commit.sh ещё раз.")
        if lines == [f"Signed: {ctx.state['name']}"]:
            return Verdict(True)
        return Verdict(False, "Строка не та или не сохранилась. Запусти ./commit.sh ещё раз.")


class VimEscape(Task):
    id = "vim_escape"
    track = "tools"
    title = "Капкан Vim: выйти без сохранения"
    autorun = "./commit.sh"
    scroll = VIM_SCROLL
    variants = (
        Variant("Нажми Enter — откроется vim с сообщением, которое не должно уйти. "
                "Выйди, НИЧЕГО не сохранив, даже если случайно что-то напечатал.",
                wrong=("TERMIT_VIM_EX='wq' ./commit.sh",),
                alternatives=("ZQ — выйти без сохранения, без двоеточия",)),
        Variant("Нажми Enter — откроется vim, а в сообщении уже есть чья-то несохранённая "
                "правка. Выйди, ничего не сохранив. Обычный :q тут откажется.",
                hints=("vim не выпустит по :q, пока в файле есть несохранённые правки: "
                       "внизу появится E37.",
                       "Восклицательный знак после q значит «выйти и выбросить правки».",
                       "Esc, :q!, Enter"),
                solution="Esc, :q!, Enter",
                solution_script="TERMIT_VIM_EX='q!' ./commit.sh",
                wrong=("TERMIT_VIM_EX='wq' ./commit.sh",),
                alternatives=(":qa! — выйти без сохранения, даже если открыто несколько "
                              "файлов",)),
        Variant("Нажми Enter — vim откроется сразу в режиме печати: всё, что наберёшь, станет "
                "текстом. Выйди, ничего не сохранив.",
                hints=("Внизу горит -- INSERT --: сейчас буквы — это текст, а не команды.",
                       "Сначала Esc — он вернёт в режим команд. Без него :q! ляжет в текст.",
                       "Esc, :q!, Enter (успел что-то напечатать — всё равно :q!)"),
                solution="Esc, :q!, Enter",
                solution_script="TERMIT_VIM_EX='q!' ./commit.sh",
                # второе — «набрал :q! в режиме вставки, текст лёг в буфер, потом с досады
                # :wq» (сам :wq допишет commit.sh): :x тут не годится — буфер без правок
                # он не пишет и засчитался бы
                wrong=("TERMIT_VIM_EX='wq' ./commit.sh",
                       "TERMIT_VIM_EX='normal i:q!' ./commit.sh"),
                alternatives=("Ctrl+[ — то же, что Esc, если до Esc тянуться далеко",)),
    )
    par = 30
    hints = ("Выход без сохранения в vim — двоеточие, q и восклицательный знак.",
             "Сначала Esc (на всякий случай), потом в английской раскладке :q!",
             "Esc, :q!, Enter")
    solution = "Esc, :q!, Enter"
    solution_script = "TERMIT_VIM_EX='q!' ./commit.sh"
    explain = ":q! — выйти и выбросить правки. Застрял в vim — Esc, потом :q!"
    spell = "vim: :q! — выйти без сохранения; застрял — Esc, :q!"

    # стартовые -c под вариант: B — буфер уже изменён (:q откажет), C — сразу режим вставки
    VIM_ARGS = ("", "-c 'normal GoWIP: do not send'", "-c startinsert")

    def setup_variant(self, box, rng, variant):
        # без финального перевода строки: :wq допишет его, и даже «пустой» :wq виден в хэше
        _commit_sh(box, "This message must not be sent"
                        "\n# Quit WITHOUT saving: Esc, then :q! and Enter.", no_eol=True,
                   vim_args=self.VIM_ARGS[variant])
        return {}

    def check(self, ctx):
        h = ctx.box / ".msg_hash"
        if not h.exists():
            return Verdict(False)
        before, _, after = h.read_text().strip().partition(" ")
        if before == after:
            return Verdict(True)
        return Verdict(False, "Сообщение изменилось — значит, сохранил. Запусти ./commit.sh "
                              "и выйди через :q!")


class VimPurge(Task):
    id = "vim_purge"
    track = "tools"
    title = "Чистка строк в vim"
    scroll = ("vim FILE — открыть файл FILE. В режиме команд: /WORD и Enter — поиск, n — "
              "следующее, dd — удалить строку (первая d — «удалить», вторая — «строку "
              "целиком»), u — отменить последнее, :wq — сохранить и выйти.\n"
              "Не знаешь, в каком ты режиме, — нажми Esc. ^ в поиске — начало строки: /^# найдёт "
              "только строки, которые начинаются с #. Пробел в поиске — тоже символ.")
    variants = (
        Variant("В rules.txt завёлся спам: строки, начинающиеся с «SPAM » — SPAM и пробел. "
                "Вычисти их в vim и сохрани (ans не нужен). Строку «SPAM: filter enabled» "
                "(фильтр включён) не трогать — удалил по ошибке, верни через u.",
                wrong=("vim -Es -u NONE '+g/SPAM/d' +wq rules.txt",),
                alternatives=(":g/^SPAM /d — vim сам удалит все строки по образцу, одной "
                              "командой",)),
        Variant("В list.txt некоторые строки повторяются дважды подряд. Удали в vim вторые "
                "копии — каждая такая строка должна остаться один раз — и сохрани (ans не "
                "нужен). Строки «---» повторяются не подряд: это разделители, их не трогай.",
                hints=("vim list.txt — повторы видно глазами: листай вниз стрелкой или j "
                       "(в vim это тоже «вниз»).",
                       "Встань на вторую копию и нажми dd; удалил не то — u.",
                       "vim list.txt, dd на каждой второй копии, :wq"),
                solution="vim list.txt, dd на каждой второй копии, :wq",
                solution_script="vim -Es -u NONE '+g/^\\(.*\\)\\n\\1$/d' +wq list.txt",
                wrong=("sort -u -o list.txt list.txt",
                       "awk '!seen[$0]++' list.txt > t.txt && mv t.txt list.txt"),
                alternatives=("uniq list.txt > t.txt && mv t.txt list.txt — uniq убирает "
                              "повторы подряд без редактора, > t.txt пишет вывод в файл t.txt",)),
        Variant("В script.sh слишком много комментариев. Удали в vim все строки, которые "
                "начинаются с #, и сохрани (ans не нужен). Первую строку #!/bin/sh оставь: это "
                "не комментарий, а указание, чем запускать скрипт. Решётку внутри строки тоже "
                "не трогай.",
                hints=("vim script.sh, потом /^# — ^ значит «начало строки»: найдутся только "
                       "строки, которые начинаются с #.",
                       "dd — удалить строку; под курсором снова комментарий — снова dd, нет — "
                       "n к следующей находке. До #!/bin/sh поиск тоже дойдёт — её пропусти.",
                       "vim script.sh, /^#, dd, n, dd … (#!/bin/sh пропустить), :wq"),
                solution="vim script.sh, /^#, dd, n, … (кроме #!/bin/sh), :wq",
                solution_script="vim -Es -u NONE '+2,$g/^#/d' +wq script.sh",
                wrong=("vim -Es -u NONE '+g/^#/d' +wq script.sh",
                       "vim -Es -u NONE '+2,$g/#/d' +wq script.sh"),
                alternatives=(":2,$g/^#/d — со второй строки до конца удалить всё, что "
                              "начинается с #",)),
    )
    par = 90
    hints = ("vim rules.txt, потом /^SPAM, пробел и Enter — найти первую.",
             "dd — удалить строку, n — к следующей находке.",
             "vim rules.txt, /^SPAM, пробел, Enter, dd, n, dd … (нужную строку удалил — u), :wq")
    solution = "vim rules.txt, /^SPAM и пробел, dd, n, …, :wq"
    solution_script = "vim -Es -u NONE '+g/^SPAM /d' +wq rules.txt"
    explain = "Поиск, dd, n — и строки чистятся пачкой; промахнулся — u спасёт."
    spell = "vim: /WORD — поиск, n — дальше, dd — удалить строку, u — отменить"

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            return self._list(box, rng)
        if variant == 2:
            return self._script(box, rng)
        n = rng.randint(40, 80)
        bad = set(rng.sample(range(n), rng.randint(3, 5)))
        special = rng.choice([i for i in range(n) if i not in bad])
        out, want = [], []
        for i in range(n):
            if i in bad:
                out.append(f"SPAM {kit.latin(rng)}{rng.randint(10, 99)}")
            rule = f"Rule {i + 1}: {kit.word(rng)} and {kit.word(rng)}"
            out.append(rule)
            want.append(rule)
            if i == special:
                out.append("SPAM: filter enabled")
                want.append("SPAM: filter enabled")
        return self._write(box, "rules.txt", out, want)

    def _write(self, box, name, out, want):
        f = kit.write(box / name, "\n".join(out) + "\n")
        return {"file": name, "want": "\n".join(want) + "\n", "orig": kit.sha(f)}

    def _list(self, box, rng):
        n = rng.randint(30, 45)
        dup = set(rng.sample(range(n), rng.randint(3, 5)))
        out, want, since = [], [], 0
        for i in range(n):
            item = f"{i + 1}. {kit.word(rng)} — {kit.latin(rng)}"
            out.append(item)
            want.append(item)
            if i in dup:
                out.append(item)
            since += 1
            if since >= rng.randint(5, 8) and i < n - 1:     # разделители — не подряд
                out.append("---")
                want.append("---")
                since = 0
        return self._write(box, "list.txt", out, want)

    def _script(self, box, rng):
        cmds = [f'echo "step {i + 1}: {kit.latin(rng)}"' for i in range(rng.randint(8, 12))]
        cmds += ["set -e", f"mkdir -p out/{kit.latin(rng)}", "date",
                 f'echo "Task #{rng.randint(2, 99)}"']           # решётка внутри строки
        rng.shuffle(cmds)
        notes = ["# Build the report", "#--------", "# TODO: remove debug output",
                 f"# author: {kit.latin(rng)}", "#  old version: rm -rf out", "# end"]
        out, want = ["#!/bin/sh"], ["#!/bin/sh"]
        for c in cmds:
            if notes and rng.random() < 0.5:
                out.append(notes.pop(0))
            out.append(c)
            want.append(c)
        out += notes
        return self._write(box, "script.sh", out, want)

    def check(self, ctx):
        return check_edit(ctx.box / ctx.state.get("file", "rules.txt"), ctx.state)


# Кэш страниц tlrc владельца: dirs::cache_dir() на macOS = ~/Library/Caches (cache.rs: Cache::locate).
# Вычисляется в родителе, где HOME — настоящий дом.
TLRC_CACHE = Path.home() / "Library" / "Caches" / "tlrc"


def tlrc_offline(box) -> None:
    """tldr без сети: копия кэша tlrc (только чтение) в .termit/tlrc — переживает reset — и
    конфиг tlrc в доме песочницы ($HOME/Library/Application Support/tlrc/config.toml, это
    dirs::config_dir()) с выключенным автообновлением."""
    dst = Path(box) / ".termit" / "tlrc"
    if not dst.exists() and (TLRC_CACHE / "pages.en").is_dir():
        shutil.copytree(TLRC_CACHE, dst, symlinks=True)    # ссылки не раскрываем — наружу не ведут
        for dirpath, dirnames, filenames in os.walk(dst):
            for f in filenames:
                p = os.path.join(dirpath, f)
                if not os.path.islink(p):
                    os.chmod(p, 0o444)
    if not dst.is_dir():
        return
    langs = sorted(p.name[len("pages."):] for p in dst.glob("pages.*")
                   if p.is_dir() and p.name != "pages.en")    # английский tlrc добавит сам
    kit.write(kit.home(box) / "Library" / "Application Support" / "tlrc" / "config.toml",
              "[cache]\n"
              f"dir = {json.dumps(str(dst))}\n"
              "auto_update = false\n"
              f"languages = {json.dumps(langs)}\n")


# Учебный brew (termit_app/brewstub.py) ведёт себя как настоящий. Вариант B: команда и
# формула называются по-разному (как в каталоге Homebrew): (команда, формула, что делает,
# слово из описания формулы для brew search --desc). brew which-formula по каждой команде
# даёт ровно одну формулу (tests/test_brewstub.py). Пример rg → ripgrep — в scroll и уроке.
BREW_BY_CMD = [("http", "httpie", "запросы к веб-API из терминала", "HTTP client"),
               ("gsed", "gnu-sed", "sed, как на Linux", "stream editor"),
               ("delta", "git-delta", "цветной diff для git", "diff")]
# формулы, у которых имя совпадает с командой: их «ставят» в варианте C
BREW_PLAIN = ["bat", "fd", "jq", "tree"]
BREW_LISTED = ["htop", "jq", "tree", "wget"]


class BrewLesson(AnswerTask):
    id = "brew_lesson"
    track = "tools"
    title = "Склад программ"
    scroll = ("brew info FORMULA — карточка формулы FORMULA (Replacement — замена). Homebrew — "
              "склад пакетов (программ для Mac), формула — карточка одной из них. "
              "brew which-formula COMMAND — из какой формулы команда COMMAND (rg — из "
              "ripgrep).\n"
              "HOMEBREW_NO_AUTO_UPDATE=1 brew install FORMULA — поставить, не обновляя список "
              "формул. Тут brew учебный: сети нет, он только делает вид, что ставит.")
    variants = (
        Variant("Нужна команда tldr. Формулу с таким же именем Homebrew отключил — больше её "
                "не ставит. Что он сам советует поставить взамен? Загляни в карточку формулы "
                "tldr и сдай имя замены: ans FORMULA (FORMULA — сюда имя формулы)",
                wrong=("print -r -- tldr", "print -r -- tealdeer"),
                alternatives=("HOMEBREW_NO_AUTO_UPDATE=1 brew install tldr — откажет, и в ошибке будет та же замена",)),
        Variant("Нужна команда {cmd} — {what}. Ставят её формулой с другим именем. Узнай, "
                "какой, и сдай: ans FORMULA (FORMULA — сюда имя формулы)",
                hints=("Имя команды и имя формулы бывают разные. brew умеет искать формулу "
                       "по команде.",
                       "brew which-formula COMMAND — какая формула ставит команду COMMAND.",
                       "brew which-formula {cmd}, в выводе {answer}, ans {answer}"),
                solution="brew which-formula {cmd}, ans {answer}",
                solution_script="brew which-formula {cmd}",
                wrong=("print -r -- {cmd}",),
                alternatives=("brew search --desc '{desc}' (--desc — искать по описаниям): "
                              "{answer} найдётся по тому, что делает",)),
        Variant("Поставь учебную формулу {formula} так, чтобы brew не полез обновлять список "
                "формул: сети тут нет. В конце установка напечатает квитанцию — строку "
                "«Receipt: …» с числом (receipt — квитанция). Сдай это число: ans NUMBER",
                hints=("Попробуй просто brew install {formula} и прочти, на чём он обрывается.",
                       "Переменная перед командой действует только на неё: "
                       "HOMEBREW_NO_AUTO_UPDATE=1 brew install FORMULA",
                       "HOMEBREW_NO_AUTO_UPDATE=1 brew install {formula}, число из строки "
                       "«Receipt», ans и это число"),
                solution="HOMEBREW_NO_AUTO_UPDATE=1 brew install {formula}, число из строки «Receipt»",
                solution_script=("HOMEBREW_NO_AUTO_UPDATE=1 brew install {formula} "
                                 "| sed -n 's/^Receipt: //p'"),
                wrong=("brew install {formula} >/dev/null 2>&1; print -r -- {receipt}",
                       "HOMEBREW_NO_AUTO_UPDATE=1 brew install {decoy} >/dev/null; "
                       "print -r -- {receipt}"),
                alternatives=("export HOMEBREW_NO_AUTO_UPDATE=1 — один раз на весь сеанс "
                              "терминала, дальше просто brew install; export подробно — в "
                              "треке про переменные",)),
    )
    par = 45
    hints = ("Карточка формулы — brew info FORMULA. У отключённой там написано, почему и чем "
             "заменить.",
             "Ищи в выводе строку Replacement: под ней команда установки замены.",
             "brew info tldr, Replacement: brew install tlrc, ans tlrc")
    solution = "brew info tldr, Replacement: brew install tlrc, ans tlrc"
    solution_script = "brew info tldr | sed -n 's/^ *brew install //p'"
    explain = ("Homebrew — склад программ для Mac: search ищет формулу по имени, which-formula — "
               "по команде, info показывает карточку, а с HOMEBREW_NO_AUTO_UPDATE=1 brew не тратит "
               "минуту на обновление списка формул.")
    spell = ("brew info FORMULA; brew which-formula COMMAND; "
             "HOMEBREW_NO_AUTO_UPDATE=1 brew install FORMULA")

    def setup_variant(self, box, rng, variant):
        state = {"brew_list": sorted(rng.sample(BREW_LISTED, rng.randint(1, 3)))}
        if variant == 0:
            state.update(cmd="tldr", answer="tlrc", traps=[["off", "tldr"]])
        elif variant == 1:
            cmd, formula, what, desc = rng.choice(BREW_BY_CMD)
            state.update(cmd=cmd, answer=formula, what=what, desc=desc, traps=[["cmd", cmd]])
        else:
            formula, decoy = rng.sample(BREW_PLAIN, 2)
            receipt = str(rng.randint(100000, 999999))
            state.update(formula=formula, decoy=decoy, receipt=receipt, answer=receipt)
        return state

    trap_messages = {
        "off": "Формула tldr как раз отключена — нужна та, что Homebrew советует взамен: "
               "Replacement в brew info tldr.",
        "cmd": "Это имя команды, а формула называется иначе: спроси brew which-formula {cmd}.",
    }

    def answer_kind(self, state):
        return "number" if state.get("_variant") == 2 else "text"

    def wrong_message(self, given, ctx):
        if ctx.state.get("_variant") == 0 and textnorm.same_text(given, "tealdeer"):
            return ("tealdeer тоже ставит tldr, но Homebrew в карточке отключённой формулы "
                    "советует другую. Найди там Replacement.")
        return super().wrong_message(given, ctx)

    def check(self, ctx):
        verdict = super().check(ctx)
        if (verdict.solved and ctx.state.get("_variant") == 2
                and not brewstub.installed_with_flag(ctx.box, ctx.state["formula"])):
            return Verdict(False, f"Номер верный, а учебной установки {ctx.state['formula']} с "
                                  "HOMEBREW_NO_AUTO_UPDATE=1 в журнале brew нет. Поставь — и "
                                  "сдай снова.")
        return verdict


class TldrTar(Task):
    id = "tldr_tar"
    track = "tools"
    title = "tldr и архив"
    implant = "tldr"      # близнец: решается и без tldr (man tar), tldr — подарок после
    scroll = ("tldr COMMAND — живые примеры (нет tldr — man tar, /extract). "
              "tar -xf ARCHIVE -C DIR — распаковать архив ARCHIVE в папку DIR (без -C — сюда; "
              "папка DIR должна уже быть); tar -tf ARCHIVE — оглавление; tar -xf ARCHIVE PATH — "
              "один файл; tar -czf ARCHIVE DIR — собрать сжатый. x — extract, c — create, t — "
              "table, f — file, -C — Change directory; z — gzip: нужна при сборке, при "
              "распаковке и оглавлении tar узнаёт сжатие сам.\n"
              "В tldr {{…}} или path/to/… — твоё имя; --wildcards — для Linux, на Mac не нужен.")
    variants = (
        Variant("В backup.tar.gz — архив с файлами. Распакуй его в папку backup/ — она уже "
                "есть, рядом. Как именно, подскажет tldr tar, а если tldr не стоит — man tar. "
                "Сдавать ничего не надо: игра проверит папку сама.",
                wrong=("tar -xf backup.tar.gz",),
                alternatives=("cd backup && tar -xf ../backup.tar.gz — зайти и распаковать "
                              "на месте",
                              "tar -xzf backup.tar.gz -C backup — с z то же самое: при "
                              "распаковке tar узнаёт сжатие сам")),
        Variant("В release.tar.gz целый проект, а нужен один файл — readme.txt, он лежит "
                "где-то внутри. Достань только его в текущую папку: путь из архива пишется "
                "после имени архива, и файл ляжет вместе с папками из этого пути. Где он "
                "лежит, покажет оглавление архива, а как распаковывать вообще — tldr tar или "
                "man tar. Сдавать ничего не надо.",
                hints=("Сначала оглавление: tar -tf release.tar.gz — там виден полный путь к "
                       "readme.txt.",
                       "Этот путь целиком допиши после имени архива: tar -xf release.tar.gz PATH, "
                       "где PATH — путь из оглавления",
                       "tar -tf release.tar.gz, затем tar -xf release.tar.gz {path} "
                       "(примеры — в tldr tar или man tar)"),
                solution="tar -tf release.tar.gz, tar -xf release.tar.gz {path}",
                solution_script="tar -xf release.tar.gz {path}",
                wrong=("tar -xf release.tar.gz", "tar -xf release.tar.gz readme.txt"),
                alternatives=("tar -xf release.tar.gz '*/readme.txt' — tar на Mac понимает "
                              "шаблон и без --wildcards",)),
        Variant("Собери из папки notes сжатый архив notes.tar.gz — здесь, рядом с папкой. "
                "Как — подскажет tldr tar, а если tldr не стоит — man tar. Сдавать ничего не "
                "надо: игра заглянет в архив сама.",
                hints=("tldr tar — короткие примеры, ищи create; если tldr не стоит — man tar, "
                       "/create",
                       "c — создать, z — сжать gzip, f — имя архива; за ним — что упаковать.",
                       "tar -czf notes.tar.gz notes — этот пример есть и в tldr tar"),
                solution="tldr tar (или man tar), tar -czf notes.tar.gz notes",
                solution_script="tar -czf notes.tar.gz notes",
                wrong=("tar -cf notes.tar.gz notes",),
                alternatives=("tar -czvf notes.tar.gz notes — -v печатает каждый файл, "
                              "который лёг в архив",)),
    )
    par = 60
    hints = ("tldr tar — короткие примеры; если tldr не стоит — man tar, /extract",
             "Распаковка — tar -xf, папка назначения — флаг -C и её имя (в tldr — "
             "--directory=).",
             "tar -xf backup.tar.gz -C backup (примеры — в tldr tar или man tar)")
    solution = "tldr tar (или man tar), tar -xf backup.tar.gz -C backup"
    solution_script = "tar -xf backup.tar.gz -C backup"
    explain = ("x — извлечь, f — файл архива, -C — куда. z (gzip) нужна только при сборке: "
               "при распаковке tar узнаёт сжатие сам. tldr выдаст это за пару секунд.")
    spell = "tldr COMMAND — примеры; tar -xf ARCHIVE -C DIR — распаковать"

    def _files(self, rng, folder, names):
        shas = {}
        for name in names:
            shas[name] = kit.sha(kit.write(folder / name, f"file {name} {rng.random()}\n"))
        return shas

    def _pack(self, box, archive, src, shas):
        with tarfile.open(box / archive, "w:gz") as tf:
            for name in shas:
                tf.add(src / name, arcname=name)
        shutil.rmtree(src)

    def setup_variant(self, box, rng, variant):
        # Сети в песочнице нет: tldr (если стоит) берёт страницы из копии кэша tlrc владельца.
        # Нет tldr или кэша — задача всё равно решается: man tar.
        if implants.which("tldr"):
            tlrc_offline(box)
        names = [f"{kit.latin(rng)}_{i}.txt" for i in range(rng.randint(3, 5))]
        if variant == 2:
            return {"files": self._files(rng, box / "notes", names)}
        src = box / ".termit" / "backupsrc"
        if variant == 1:
            proj = kit.latin(rng)
            path = f"{proj}/docs/readme.txt"
            names = ([path, f"{proj}/docs/changelog.txt"] +
                     [f"{proj}/src/{n}" for n in names])
            shas = self._files(rng, src, names)
            self._pack(box, "release.tar.gz", src, shas)
            return {"files": shas, "path": path}
        shas = self._files(rng, src, names)
        self._pack(box, "backup.tar.gz", src, shas)
        (box / "backup").mkdir()
        return {"files": shas}

    def check(self, ctx):
        v, files = ctx.state.get("_variant", 0), ctx.state["files"]
        if v == 1:
            path = ctx.state["path"]
            readme = ctx.box / path
            got = readme.is_file() and kit.sha(readme) == files[path]
            extra = [n for n in files if n != path and (ctx.box / n).exists()]
            if got and extra:
                return Verdict(False, "readme.txt на месте, но вылезло и лишнее: "
                                      f"{', '.join(sorted(extra))}. Набери reset и достань "
                                      "только его.")
            last = ctx.cmds[-1].line if ctx.cmds else ""
            if not got and not extra and re.search(r"tar .*(^|\s)readme\.txt", last):
                return Verdict(False, "В архиве readme.txt лежит не в корне, а в папке: имя "
                                      "нужно с полным путём, как в оглавлении tar -tf "
                                      "release.tar.gz.")
            return Verdict(got and not extra)
        if v == 2:
            return self._check_packed(ctx.box / "notes.tar.gz", files)
        d = ctx.box / "backup"
        if all((d / n).is_file() and kit.sha(d / n) == h for n, h in files.items()):
            return Verdict(True)
        if all((ctx.box / n).is_file() for n in files):
            return Verdict(False, "Файлы распаковались сюда, а не в backup/: tar кладёт их туда, "
                                  "где ты стоишь. Папку назначения задаёт флаг -C, за ним "
                                  "имя папки. Лишние копии здесь не мешают.")
        return Verdict(False)

    @staticmethod
    def _check_packed(archive, files) -> Verdict:
        """Архив — именно gzip (r:gz), внутри все файлы папки с тем же содержимым; путь
        внутри (notes/a.txt или ./a.txt) не важен, служебные ._файлы macOS не в счёт."""
        if not archive.is_file():
            return Verdict(False)
        try:
            with tarfile.open(archive, "r:gz") as tf:
                got = {}
                for m in tf.getmembers():
                    # ._имя — AppleDouble: tar на Mac сам кладёт туда расширенные атрибуты
                    if m.isfile() and not os.path.basename(m.name).startswith("._"):
                        got[os.path.basename(m.name)] = hashlib.sha1(
                            tf.extractfile(m).read()).hexdigest()
        except (tarfile.TarError, OSError, EOFError):
            return Verdict(False, "notes.tar.gz — не сжатый tar-архив. Сжатие gzip даёт флаг z.")
        if got != files:
            return Verdict(False, "В архиве не те файлы: нужно всё из notes/, и ничего лишнего.")
        return Verdict(True)


class BatLines(AnswerTask):
    """Пара «до/после» к less_search (часть 5): номера строк встроенными (cat -n, grep -n,
    sed -n), утилита bat — только быстрее и нагляднее. FB12 (N12): эталон варианта 0 —
    cat -n и глазами, grep -e с двумя шаблонами — «можно и так»."""
    id = "bat_lines"
    track = "tools"
    title = "Строка по номеру"
    implant = "bat"
    after = ("less_search", "boss_tools")
    scroll = ("cat -n FILE — файл FILE с номерами строк (n — number); grep -n WORD FILE — "
              "номера строк, где нашлось слово WORD.\n"
              "sed -n '12p' FILE — только строка 12 (у sed -n — no print: остальные не "
              "печатать).")
    variants = (
        Variant("В config.yaml несколько блоков настроек: блок — заголовок без отступа, "
                "например «{block}:», и строки с отступом под ним. В каждом блоке есть свой "
                "timeout. На какой строке файла стоит timeout блока {block}? Ответ: ans NUMBER "
                "(NUMBER — номер строки)",
                wrong=("grep -n timeout config.yaml | head -1 | cut -d: -f1",),
                alternatives=("grep -n -e '^[a-z]' -e timeout config.yaml (-e — ещё один "
                              "шаблон, expression; ^[a-z] — строка с буквы, без отступа) — "
                              "только заголовки блоков и их timeout, по порядку",
                              "less -N config.yaml — -N покажет номера строк прямо в less")),
        Variant("В events.log {total} строк, и все разные. Какая из них стоит под номером "
                "{n}? Сдай её целиком, как есть: ans и сама строка, через пробел — например "
                "ans red fox",
                hints=("Считать строки глазами не нужно — номера печатает cat -n.",
                       "Одну строку по номеру вырежет sed -n '{n}p': p — напечатать, -n — "
                       "молчать про остальные.",
                       "sed -n '{n}p' events.log, и ans с этой строкой"),
                solution="sed -n '{n}p' events.log",
                solution_script="sed -n '{n}p' events.log",
                implant_script="bat -pp -r {n}:{n} events.log",
                wrong=("sed -n '{prev}p' events.log", "cat -n events.log | grep {n}"),
                alternatives=("head -n {n} events.log | tail -1 — head -n {n} даст первые {n} "
                              "строк, tail -1 — последнюю из них",)),
        Variant("Вот три копии одного конфига: {f1}, {f2} и {f3}. В одной из них строка {n} "
                "не такая, как в двух других. В какой? Ответ: ans FILE (FILE — имя того "
                "файла)",
                hints=("Строку {n} одного файла покажет sed -n '{n}p' FILE — так узнаешь, какая "
                       "настройка стоит на строке {n}.",
                       "Имя этой настройки ищи сразу в трёх файлах: grep -n печатает перед "
                       "каждой находкой имя файла и номер строки.",
                       "sed -n '{n}p' {f1}, затем grep -n '^{key} =' {f1} {f2} {f3} — где "
                       "значение другое, тот файл"),
                solution="sed -n '{n}p' {f1}; grep -n '^{key} =' {f1} {f2} {f3}",
                solution_script="grep -lxF \"$(for f in {f1} {f2} {f3}; do sed -n '{n}p' $f; "
                                "done | sort | uniq -u)\" {f1} {f2} {f3}",
                implant_script="grep -lxF \"$(bat -pp -r {n}:{n} {f1} {f2} {f3} | sort | "
                               "uniq -u)\" {f1} {f2} {f3}",
                wrong=("grep -lxF \"$(for f in {f1} {f2} {f3}; do sed -n '{m}p' $f; done | "
                       "sort | uniq -u)\" {f1} {f2} {f3}",),
                alternatives=("sed -n '{n}p' {f1}, потом то же для {f2} и {f3} — по файлу "
                              "за раз, и сравнить глазами",)),
    )
    par = 45
    hints = ("Номера строк печатает cat -n — весь файл с номерами слева.",
             "timeout есть в каждом блоке: найди глазами заголовок {block}: (строка без "
             "отступа) и первый timeout под ним.",
             "cat -n config.yaml — номер timeout под {block}:, и ans с этим номером")
    solution = "cat -n config.yaml"
    solution_script = ("grep -n -e '^{block}:' -e 'timeout:' config.yaml | grep -A1 '{block}:' "
                       "| tail -1 | cut -d: -f1")
    implant_script = ("bat --decorations=always --color=never -n config.yaml | "
                      "sed -n '/ {block}:/,$p' | grep -m1 'timeout:' | awk '{{print $1}}'")
    # владелец 25.10: утилиту, которой у игрока нет и которую урок не учит, не называем (bat —
    # имплант: кто его поставил, получает руководство при установке и по help bat)
    explain = ("Номера строк покажут cat -n, grep -n и less -N, а одну строку по номеру "
               "выдернет sed -n 'Np'.")
    spell = "sed -n '12p' FILE — строка номер 12; cat -n — файл с номерами строк"

    BLOCKS = ("database", "cache", "queue", "mailer", "search")
    KEYS = ("host", "port", "timeout", "retries", "user")

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            total, n = rng.randint(210, 260), rng.randint(10, 99)
            pairs = [f"{w} {lat}" for w in kit.WORDS for lat in kit.LATIN]
            lines = rng.sample(pairs, total)
            kit.write(box / "events.log", "\n".join(lines) + "\n")
            return {"total": total, "n": n, "prev": n - 1, "answer": lines[n - 1],
                    "traps": [["prev", lines[n - 2]]]}
        if variant == 2:
            names = [f"{x}.conf" for x in rng.sample(kit.LATIN, 3)]
            keys = rng.sample([f"{lat}_{k}" for lat in kit.LATIN for k in ("on", "max", "min")],
                              rng.randint(30, 40))
            base = [f"{k} = {rng.randint(1, 90)}" for k in keys]
            n, m = rng.sample(range(5, len(base) + 1), 2)
            odd, other = rng.sample(range(3), 2)
            for i, name in enumerate(names):
                lines = list(base)
                if i == odd:
                    lines[n - 1] = f"{keys[n - 1]} = {rng.randint(91, 99)}"
                if i == other:      # вторая разница — на другой строке, в другом файле
                    lines[m - 1] = f"{keys[m - 1]} = {rng.randint(91, 99)}"
                kit.write(box / name, "\n".join(lines) + "\n")
            return {"f1": names[0], "f2": names[1], "f3": names[2], "n": n, "m": m,
                    "key": keys[n - 1],
                    "answer": names[odd], "traps": [["other", names[other]]]}
        blocks = rng.sample(self.BLOCKS, rng.randint(3, 5))
        target = rng.choice(blocks[1:])
        lines, answer, first = ["# service settings"], 0, 0
        for b in blocks:
            lines += ["", f"{b}:"]
            for k in rng.sample(self.KEYS, len(self.KEYS)):
                value = {"host": f"{b}.local", "port": rng.randint(1000, 9999),
                         "user": kit.latin(rng)}.get(k, rng.randint(2, 60))
                lines.append(f"  {k}: {value}")
                if b == target and k == "timeout":
                    answer = len(lines)
                if k == "timeout" and not first:
                    first = len(lines)
        kit.write(box / "config.yaml", "\n".join(lines) + "\n")
        return {"block": target, "answer": answer, "traps": [["first", first]]}

    trap_messages = {
        "first": "Это timeout первого блока, а нужен блок {block}: смотри, под каким заголовком "
                 "стоит строка.",
        "prev": "Это строка {prev}: нужна ровно {n}-я — номера у cat -n начинаются с 1.",
        "other": "Этот файл отличается на другой строке, а не на {n}-й.",
    }

    def answer_kind(self, state):
        return ("number", "text", "path")[variant_index(state.get("_variant"), 3)]

    def matches(self, given, ctx):
        v = variant_index(ctx.state.get("_variant"), len(self.variants))
        if v == 0:
            return textnorm.same_number(given, ctx.state["answer"])
        if v == 2:
            return textnorm.same_path(given, ctx.box / ctx.state["answer"], ctx.box)
        return super().matches(given, ctx)


JSON_KEYS = [("name", lambda r: f'"{kit.latin(r)}-{r.randint(1, 9)}"'),
             ("version", lambda r: f'"{r.randint(1, 4)}.{r.randint(0, 9)}"'),
             ("port", lambda r: str(r.randint(2000, 9999))),
             ("debug", lambda r: r.choice(["true", "false"])),
             ("owner", lambda r: f'"{kit.latin(r)}"'),
             ("timeout", lambda r: str(r.randint(5, 120))),
             ("retries", lambda r: str(r.randint(1, 9))),
             ("region", lambda r: r.choice(['"eu"', '"us"', '"asia"'])),
             ("tags", lambda r: f'["{kit.latin(r)}", "{kit.latin(r)}"]'),
             ("cache", lambda r: r.choice(["true", "false"]))]


def json_lines(rng, n: int) -> List[str]:
    """Строки объекта JSON (без скобок и запятых): name и ещё n-1 разных ключей вперемешку."""
    pairs = [JSON_KEYS[0]] + rng.sample(JSON_KEYS[1:], n - 1)
    rng.shuffle(pairs)
    return [f'  "{k}": {make(rng)}' for k, make in pairs]


def json_text(lines: List[str], skip_comma: int = -1) -> str:
    """Объект целиком; skip_comma — у этой строки (номер в lines) запятая потеряна."""
    body = [ln + ("" if i == len(lines) - 1 or i == skip_comma else ",")
            for i, ln in enumerate(lines)]
    return "{\n" + "\n".join(body) + "\n}\n"


class JsonCheck(AnswerTask):
    """Практика перед «Сломанным конфигом» (П3.1 приёмки-1): jq . и правила JSON — до
    стража. Вариант 0 (первая встреча): прочитать у jq номер строки с ошибкой."""
    id = "json_check"
    track = "tools"
    title = "Проверка JSON"
    scroll = ("jq . FILE — проверить JSON-файл FILE: цел — jq напечатает его красиво, сломан — "
              "скажет parse error … at line N. N — строка, где jq споткнулся: ошибка в ней "
              "или строкой выше.\n"
              "Правила JSON: текст и ключи — в двойных кавычках, числа и true/false — без "
              "кавычек, между парами запятая, после последней — нет.")
    secret_keys = AnswerTask.secret_keys + ("fixed", "good", "bad1")
    variants = (
        Variant("Конфиг {file} не грузится — где-то в нём ошибка. Спроси у jq, на какой строке "
                "он споткнулся, и сдай номер из его сообщения — число после at line: ans "
                "NUMBER",
                wrong=("wc -l < {file}",),
                alternatives=("jq . {file} 2>&1 | grep -o 'line [0-9]*' — 2>&1 пускает в трубу "
                              "и сообщение об ошибке, [0-9]* — цифры подряд, -o оставит "
                              "только совпадение",)),
        Variant("Из трёх конфигов {f1}, {f2} и {f3} цел только один — два других jq не "
                "читает. Какой цел? Ответ: ans FILE (FILE — сюда имя файла)",
                hints=("Проверь каждый файл: jq . FILE — цел, если напечатал его красиво.",
                       "Сломанный файл jq не печатает, а пишет parse error. Таких два.",
                       "jq . {f1}; jq . {f2}; jq . {f3} — сдай тот, что без parse error"),
                solution="jq . {f1}; jq . {f2}; jq . {f3}, цел тот, что без parse error",
                solution_script=("for f in {f1} {f2} {f3}; do jq . $f >/dev/null 2>&1 && "
                                 "print -r -- $f; done"),
                wrong=("print -r -- {bad1}",),
                alternatives=("jq . {f1} >/dev/null — >/dev/null выбросит вывод файла: цел — "
                              "молчит, сломан — пишет parse error",)),
        Variant("{file} сломан одной ошибкой — jq . его не читает. Почини файл в nano или vim, "
                "чтобы jq . читал его без ошибок, и сохрани. Значения не меняй. Сдавать ничего "
                "не надо: игра проверит файл сама.",
                hints=("Сначала спроси jq: jq . {file} — он назовёт строку, где споткнулся.",
                       "Ошибка в той строке или строкой выше. Сверь с правилами: кавычки "
                       "двойные, true/false маленькими, запятая между парами, после "
                       "последней — нет.",
                       "nano {file}, исправить строку, которую назвал jq, сохранить, "
                       "jq . {file}"),
                solution="nano {file}, исправить ошибку в строке, которую назвал jq, "
                         "jq . {file}",
                solution_script="print -r -- '{fixed}' > {file}",
                wrong=("print -r -- '{{}}' > {file}",),
                alternatives=("vim {file} — тот же ремонт в vim: x удаляет символ под "
                              "курсором",)),
    )
    par = 40
    hints = ("JSON проверяет jq: jq . FILE.",
             "Сломанный файл jq не печатает, а пишет parse error … at line N.",
             "jq . {file}, номер после «at line», ans и этот номер")
    solution = "jq . {file}, номер после «at line»"
    solution_script = "jq . {file} 2>&1 | grep -o 'line [0-9]*' | cut -d' ' -f2"
    explain = ("jq . — быстрая проверка JSON: цел — напечатает красиво, сломан — назовёт "
               "строку, где споткнулся; ошибка там или строкой выше.")
    spell = "jq . FILE — цел ли JSON (сломан — at line N)"

    # вариант 2: ошибка → (как испортить строку, подсказка не нужна — её назовёт jq)
    BREAKS = ("quotes", "case", "trailing")

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            names = [f"{x}.json" for x in rng.sample(kit.LATIN, 3)]
            good = rng.randrange(3)
            bad = [i for i in range(3) if i != good]
            for i, name in enumerate(names):
                lines = json_lines(rng, rng.randint(5, 7))
                if i == bad[0]:
                    text = json_text(lines, skip_comma=rng.randint(0, len(lines) - 2))
                elif i == bad[1]:
                    text = json_text(lines).replace("\n}", ",\n}")     # запятая в конце
                else:
                    text = json_text(lines)
                kit.write(box / name, text)
            return {"f1": names[0], "f2": names[1], "f3": names[2], "answer": names[good],
                    "bad1": names[bad[0]], "traps": [["broken", names[i]] for i in bad]}
        file = rng.choice(["implant.json", "service.json", "deck.json"])
        lines = json_lines(rng, rng.randint(6, 8))
        if variant == 2:
            good_text = json_text(lines)
            kind = rng.choice(self.BREAKS)
            if kind == "trailing":
                broken = good_text.replace("\n}", ",\n}")
            elif kind == "case" and any(": true" in x or ": false" in x for x in lines):
                broken = good_text.replace(": true", ": True", 1).replace(": false", ": False", 1)
            else:
                i = next(n for n, x in enumerate(lines) if '": "' in x)
                bad = lines[i].replace('"', "'", 2)
                broken = good_text.replace(lines[i], bad, 1)
            kit.write(box / file, broken)
            good = json.loads(good_text)
            return {"file": file, "good": good, "fixed": json.dumps(good, indent=2,
                                                                     ensure_ascii=False)}
        k = rng.randint(1, len(lines) - 3)          # не последние: wc -l ответа не даст
        kit.write(box / file, json_text(lines, skip_comma=k))
        # строка lines[k] — номер k + 2 в файле (первая — «{»); jq спотыкается на следующей
        return {"file": file, "answer": k + 3, "accept": [k + 2, k + 3],
                "traps": [["lines", len(lines) + 2]]}

    trap_messages = {
        "lines": "Это число строк файла, а нужен номер из сообщения jq — после «at line».",
        "broken": "Этот файл jq не читает — parse error. Нужен целый.",
    }

    def answer_kind(self, state):
        return "number" if variant_index(state.get("_variant"), 3) == 0 else "text"

    def takes_answer(self, state):
        """Вариант C — «почини файл»: ans там не промах, а лишний шаг (hook.stray_answer)."""
        return variant_index(state.get("_variant"), len(self.variants)) != 2

    def matches(self, given, ctx):
        v = variant_index(ctx.state.get("_variant"), len(self.variants))
        if v == 0:
            return any(textnorm.same_number(given, n) for n in ctx.state["accept"])
        if v == 1:
            exp = str(ctx.state["answer"])
            return (textnorm.same_text(given, exp) or
                    textnorm.same_text(given, exp[:-len(".json")]))
        return False

    def wrong_message(self, given, ctx):
        if ctx.state.get("_variant") == 2:
            return "Здесь ответ сдавать не нужно — почини файл, и проверка заметит сама."
        return super().wrong_message(given, ctx)

    def check(self, ctx):
        if variant_index(ctx.state.get("_variant"), len(self.variants)) != 2:
            return super().check(ctx)
        raw = sandbox.read_in_box(ctx.box, ctx.state["file"], kit.BOX_READ_CAP)
        try:
            data = json.loads((raw or b"").decode("utf-8"))
        except ValueError:
            data = None
        if data == ctx.state["good"]:
            return Verdict(True)
        if ctx.answer is not None:
            return Verdict(False, self.wrong_message(ctx.answer, ctx))
        if isinstance(data, dict):
            return Verdict(False, "JSON снова читается, но значения уже не те — верни их как "
                                  "были (reset, если запутался).")
        return Verdict(False)


class BossTools(Task):
    id = "boss_tools"
    track = "tools"
    title = "Сломанный конфиг"
    boss = True
    par = 300
    scroll = ("jq . FILE — проверить JSON: сломан — jq скажет, где: at line N (номер строки); "
              "цел — напечатает его красиво.\n"
              "Правила JSON: текст — в двойных кавычках, числа и true/false — без кавычек, "
              "между элементами запятая, после последнего — нет.\n"
              "Править — в nano или vim, как в прошлых задачах; после правки снова jq . FILE. "
              "jq молчит — значит, цела форма, а не смысл: значения сверяй с запиской сам.")
    steps = ("файл снова читается: jq . без ошибок",
             "число из записки note.txt — на месте и без кавычек",
             "остальное по записке и правилам JSON исправлено",
             "то, что велено не трогать, — на месте")
    variants = (
        Variant("Конфиг service.json сломан — в нём 4 ошибки. Почини его в nano или vim "
                "по записке note.txt и сохрани — ans не нужен. name и workers не трогай.",
                wrong=("print -r -- '{{}}' > service.json",
                       "print -r -- '{half}' > service.json"),
                alternatives=("vim service.json — тот же ремонт в vim: x удаляет символ под "
                              "курсором",)),
        Variant("База не стартует: db.json сломан. В нём три ошибки JSON, а ещё два значения "
                "расходятся с запиской note.txt. Почини файл в nano или vim и сохрани — ans не "
                "нужен. name и replicas не трогай.",
                hints=("Начни с проверки: jq . db.json — он покажет строку, где JSON сломан.",
                       "Ключи и текст в JSON — только в двойных кавычках, после последнего "
                       "элемента запятой нет. Числа и true/false — без кавычек.",
                       "nano db.json, одинарные кавычки на двойные, ключ host взять в "
                       "кавычки, убрать последнюю запятую, порт из записки, в readonly "
                       "поставить true, jq . db.json"),
                solution="nano db.json: кавычки везде двойные, ключ host в кавычках, без "
                         "запятой в конце, порт {port}, в readonly — true; проверить: "
                         "jq . db.json",
                solution_script="print -r -- '{fixed}' > db.json",
                wrong=("print -r -- '{{}}' > db.json",
                       "print -r -- '{half}' > db.json"),
                alternatives=("jq . db.json после каждой правки — ошибка сдвинется на "
                              "следующую строку",)),
        Variant("api.json сломан: в нём три ошибки JSON, а записка note.txt требует "
                "добавить ещё одно поле — новую пару «ключ: значение». Почини файл в nano или "
                "vim и сохрани — ans не нужен. name, port и paths не трогай.",
                hints=("Начни с проверки: jq . api.json — покажет строку с первой ошибкой. "
                       "Исправил — проверь снова.",
                       "Между элементами — запятая, после последнего — нет; true пишется "
                       "маленькими буквами. Новое поле — ещё одна пара «ключ: значение».",
                       "nano api.json, запятая после строки name, True на true, убрать "
                       "запятую в конце списка, добавить \"timeout\": {timeout}, "
                       "jq . api.json"),
                solution="nano api.json: запятая после name, True на true, без запятой в "
                         "конце списка, добавить \"timeout\": {timeout}; проверить: "
                         "jq . api.json",
                solution_script="print -r -- '{fixed}' > api.json",
                wrong=("print -r -- '{{}}' > api.json",
                       "print -r -- '{half}' > api.json"),
                alternatives=("jq .timeout api.json — проверить одно поле после правки",)),
    )
    hints = ("Начни с проверки: jq . service.json — он покажет строку, где JSON сломан.",
             "После последнего элемента в JSON запятую не ставят — ни в списке, ни в объекте. "
             "Порт — число, пиши без кавычек. Второй host удали целиком.",
             "nano service.json, убрать 2 лишние запятые, \"5432\" заменить на порт из записки, "
             "true на false, удалить второй host, оставшийся host на 127.0.0.1, сохранить, "
             "jq . service.json")
    solution = ("nano service.json: убрать лишние запятые, порт {port} без кавычек, debug false, "
                "один host 127.0.0.1; проверить: jq . service.json")
    solution_script = "print -r -- '{fixed}' > service.json"
    explain = ("jq . файл — лучшая проверка JSON: ткнёт пальцем, где сломано, а целый файл "
               "напечатает красиво.")
    spell = "jq . файл.json — проверить и красиво показать JSON"

    MODE_STEPS = (
        ("service.json снова читается: jq . service.json без ошибок",
         "port — число из записки note.txt (без кавычек)",
         "debug выключен: false",
         "host ровно один, и он 127.0.0.1"),
        ("db.json снова читается: jq . db.json без ошибок",
         "port — число из записки note.txt (без кавычек)",
         "readonly включён: true",
         "name и host на месте, ключи в двойных кавычках"),
        ("api.json снова читается: jq . api.json без ошибок",
         "timeout — число из записки note.txt (без кавычек)",
         "retry — true, маленькими буквами",
         "name, port и paths не тронуты"),
    )

    def steps_for(self, state):
        return list(self.MODE_STEPS[variant_index(state.get("_variant", 0),
                                                  len(self.MODE_STEPS))])

    def setup_variant(self, box, rng, variant):
        name_rand = kit.latin(rng)
        if variant == 1:
            port, name = rng.randint(6000, 6999), f"db-{name_rand}"
            broken = ('{\n'
                      f"  'name': '{name}',\n"
                      '  host: "127.0.0.1",\n'
                      '  "port": 5432,\n'
                      '  "replicas": [1, 2],\n'
                      '  "readonly": false,\n'
                      '}\n')
            note = (f"The database must listen on port {port}. Read-only mode (readonly) "
                    "must be on.\n")
            good = {"name": name, "host": "127.0.0.1", "port": port, "replicas": [1, 2],
                    "readonly": True}
            half = dict(good, port=5432)
            keep = {"name": name, "host": "127.0.0.1", "replicas": [1, 2]}
            return self._write(box, "db", "db.json", broken, note, good, half, keep,
                               port=port)
        if variant == 2:
            timeout, name = rng.randint(5, 120), f"api-{name_rand}"
            broken = ('{\n'
                      f'  "name": "{name}"\n'
                      '  "retry": True,\n'
                      '  "paths": ["/v1", "/v2",],\n'
                      '  "port": 8080\n'
                      '}\n')
            note = f"Add a timeout to api.json: field timeout, {timeout} seconds, as a number.\n"
            good = {"name": name, "retry": True, "paths": ["/v1", "/v2"], "port": 8080,
                    "timeout": timeout}
            half = dict(good, timeout=str(timeout))
            keep = {"name": name, "port": 8080, "paths": ["/v1", "/v2"]}
            return self._write(box, "api", "api.json", broken, note, good, half, keep,
                               timeout=timeout)
        port, name = rng.randint(6000, 6999), f"service-{name_rand}"
        broken = ('{\n'
                  f'  "name": "{name}",\n'
                  '  "host": "0.0.0.0",\n'
                  '  "port": "5432",\n'
                  '  "debug": true,\n'
                  '  "host": "0.0.0.0",\n'
                  '  "workers": [1, 2, 3,],\n'
                  '}\n')
        note = (f"The service must listen on port {port} on host 127.0.0.1. Debug must be "
                "off.\n")
        good = {"name": name, "host": "127.0.0.1", "port": port, "debug": False,
                "workers": [1, 2, 3]}
        half = dict(good, port=str(port))
        keep = {"name": name, "workers": [1, 2, 3]}
        return self._write(box, "service", "service.json", broken, note, good, half, keep,
                           port=port)

    @staticmethod
    def _write(box, mode, file, broken, note, good, half, keep, **extra):
        kit.write(box / file, broken)
        kit.write(box / "note.txt", note)
        state = {"mode": mode, "file": file, "name": good["name"], "keep": keep,
                 "fixed": json.dumps(good, indent=2), "half": json.dumps(half, indent=2)}
        state.update(extra)
        return state

    def _parse(self, ctx):
        f = ctx.box / ctx.state.get("file", "service.json")
        if not f.is_file():
            return None, ""
        text = f.read_text("utf-8", errors="replace")
        try:
            return json.loads(text), text
        except ValueError:
            return None, text

    def progress(self, ctx):
        s = ctx.state
        data, text = self._parse(ctx)
        ok = isinstance(data, dict)
        get = data.get if ok else (lambda k, d=None: d)
        mode = s.get("mode", "service")
        if mode == "db":
            port = type(get("port")) is int and get("port") == s["port"]
            return [ok, port, get("readonly") is True,
                    get("name") == s["name"] and get("host") == "127.0.0.1"]
        if mode == "api":
            timeout = type(get("timeout")) is int and get("timeout") == s["timeout"]
            return [ok, timeout, get("retry") is True,
                    all(get(k) == v for k, v in s["keep"].items())]
        port = type(get("port")) is int and get("port") == s["port"]
        host = ok and text.count('"host"') == 1 and get("host") == "127.0.0.1"
        return [ok, bool(port), get("debug") is False, bool(host)]

    def check(self, ctx):
        if not all(self.progress(ctx)):
            return Verdict(False)
        data, _ = self._parse(ctx)
        keep = ctx.state.get("keep") or {"name": ctx.state["name"], "workers": [1, 2, 3]}
        lost = sorted(k for k, v in keep.items() if data.get(k) != v)
        if lost:
            return Verdict(False, f"Пропали или изменились {', '.join(lost)} — верни их как "
                                  "были (reset, если всё сломалось).")
        return Verdict(True)


# --- FB10 (лайфхаки): задачи в фоне — Ctrl+Z, fg, bg, &, jobs, kill %N -----------------------

_JOB_HEAD = ('#!/bin/sh\n'
             '# Training script for the background jobs task. Lives while .termit exists, '
             'but no longer than LIFE seconds.\n'
             'cd "$(dirname "$0")" || exit 1\n')


def _job_script(box, name: str, body: str) -> None:
    p = kit.write(box / name, _JOB_HEAD + body)
    os.chmod(p, 0o755)


def _pid(box, name: str):
    """PID из файла, что скрипт пишет при старте; None — не запускали (или файл испорчен)."""
    try:
        return int((box / name).read_text("utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return None


class JobControl(Task):
    """FB10: Ctrl+Z и fg (приостановить и вернуть), & и bg (в фоне), jobs и kill %N.
    Скрипты задачи сами отмечают, что игрок сделал НА ХОДУ, пока они работали: проверка —
    по их следам, а не по нажатым клавишам."""
    id = "job_control"
    track = "tools"
    title = "Задачи в фоне"
    scroll = ("Ctrl+Z — приостановить то, что заняло экран (vim, скрипт); fg — вернуть "
              "на экран. Ctrl+C — прервать насовсем.\n"
              "bg — пусть работает в фоне; команда & — сразу в фоне. jobs — задачи с "
              "номерами и состоянием: работает, приостановлена, закончилась; + — её берут fg "
              "и bg без номера.\n"
              "kill %2 — остановить задачу 2 из jobs (% — номер задачи; без % число — номер "
              "процесса — запущенной программы — в системе, чужого). wait — дождаться "
              "фоновых.")
    variants = (
        Variant("Запусти ./build.sh — он будет ждать файл config.txt. Не закрывай его и не "
                "открывай новую вкладку: Ctrl+Z, сделай файл из образца командой cp "
                "config.example config.txt, потом fg — сборка доделает своё. Сдавать ничего "
                "не надо: игра увидит готовую сборку сама.",
                wrong=("cp config.example config.txt",),
                alternatives=("./build.sh & — сразу в фоне, потом cp config.example "
                              "config.txt и fg",)),
        Variant("./pack.sh пакует долго, секунд {dur}. Ждать не надо: запусти его в фоне "
                "(./pack.sh &) и, пока он работает, создай папку notes. Сдавать ничего не "
                "надо: скрипт сам заметит папку.",
                hints=("Команда с & на конце уходит в фон, приглашение — сразу твоё.",
                       "Знак & — в самом конце строки, через пробел: ./pack.sh &",
                       "./pack.sh &, затем mkdir notes"),
                solution="./pack.sh &, mkdir notes",
                solution_script="./pack.sh & sleep 2; mkdir notes; wait",
                wrong=("mkdir notes",),
                alternatives=("./pack.sh, Ctrl+Z, bg, mkdir notes — приостановить и "
                              "отпустить в фон",)),
        Variant("Запусти в фоне два скрипта: ./fetch.sh & и ./spam.sh &. spam.sh лишний и "
                "только мусорит на экран — найди его номер в jobs и останови: kill %N. "
                "fetch.sh пусть доработает, это секунд {dur}. Сдавать ничего не надо: игра "
                "увидит сама.",
                hints=("Каждая команда с & — своя задача в фоне. jobs покажет их с номерами.",
                       "kill %N останавливает задачу по номеру из jobs. Номер spam.sh — в "
                       "квадратных скобках.",
                       "./fetch.sh &, ./spam.sh &, jobs, kill %2"),
                solution="./fetch.sh &, ./spam.sh &, jobs, kill %2",
                solution_script="./fetch.sh & ./spam.sh & sleep 2; kill %2; wait %1",
                wrong=("./fetch.sh & ./spam.sh & sleep 2; kill %1 %2",),
                alternatives=("kill %?spam — задачу можно назвать и куском её команды",)),
    )
    par = 60
    hints = ("Пока build.sh ждёт, приглашения нет. Его можно вернуть, не закрывая скрипт.",
             "Ctrl+Z приостановит скрипт, fg вернёт его на экран.",
             "./build.sh, Ctrl+Z, cp config.example config.txt, fg")
    solution = "./build.sh, Ctrl+Z, cp config.example config.txt, fg"
    solution_script = "./build.sh & sleep 2; cp config.example config.txt; wait"
    explain = ("Команда не обязана занимать экран: Ctrl+Z приостанавливает, fg возвращает, bg и "
               "& отпускают в фон, jobs и kill %N управляют тем, что там.")
    spell = "Ctrl+Z — приостановить; fg / bg — на экран / в фон; & — сразу в фоне; jobs; kill %N"

    LIFE = 900          # секунд живут учебные скрипты, если их не трогать
    PACK_TIME = 6
    FETCH_TIME = 5
    MODES = ("release", "debug", "staging", "nightly")

    def setup_variant(self, box, rng, variant):
        life = self.LIFE
        if variant == 1:
            _job_script(box, "pack.sh", (
                'if [ -d notes ]; then\n'
                '  echo "Folder notes already exists. Remove it (rmdir notes) and run me '
                'again: create it while I pack."\n'
                '  exit 1\n'
                'fi\n'
                f'echo "Packing... {self.PACK_TIME} seconds. Do not wait: Ctrl+Z, then bg, '
                'or start with ./pack.sh &"\n'
                'i=0\n'
                f'while [ $i -lt {self.PACK_TIME} ]; do\n'
                '  [ -d .termit ] || exit 1\n'
                '  sleep 1\n'
                '  i=$((i + 1))\n'
                'done\n'
                'if [ -d notes ]; then\n'
                '  echo "packed with notes" > pack.log\n'
                '  echo "pack.sh: packed, and notes is there: you did not wait."\n'
                'else\n'
                '  echo "pack.sh: packed, but notes is missing: you just waited. Again: '
                './pack.sh &, and while it packs, mkdir notes"\n'
                'fi\n'))
            return {"dur": self.PACK_TIME, "log": "pack.log", "want": "packed with notes"}
        if variant == 2:
            _job_script(box, "fetch.sh", (
                'echo $$ > fetch.pid\n'
                f'sleep {self.FETCH_TIME}\n'
                '[ -d .termit ] || exit 1\n'
                'echo "fetched ok" > fetched.txt\n'
                'echo "fetch.sh: downloaded, see fetched.txt"\n'))
            _job_script(box, "spam.sh", (
                'echo $$ > spam.pid\n'
                f'end=$(( $(date +%s) + {life} ))\n'
                'while [ "$(date +%s)" -lt "$end" ] && [ -d .termit ]; do\n'
                '  echo "spam.sh: AD! AD! BUY NOW! (stop me: jobs, kill %N)"\n'
                '  sleep 5\n'
                'done\n'))
            return {"dur": self.FETCH_TIME, "spam": True}
        mode = rng.choice(self.MODES)
        kit.write(box / "config.example", f"{mode}\n")
        _job_script(box, "build.sh", (
            'if [ -e config.txt ]; then\n'
            '  echo "config.txt is already here, no fun. Remove it (rm config.txt) and run '
            'me again: create it while I wait."\n'
            '  exit 1\n'
            'fi\n'
            'echo "build.sh: waiting for config.txt... (pause me with Ctrl+Z)"\n'
            f'end=$(( $(date +%s) + {life} ))\n'
            'while [ ! -e config.txt ]; do\n'
            '  if [ "$(date +%s)" -ge "$end" ] || [ ! -d .termit ]; then\n'
            '    echo "build.sh: gave up waiting for config.txt"\n'
            '    exit 1\n'
            '  fi\n'
            '  sleep 0.2\n'
            'done\n'
            'echo "build $(head -n 1 config.txt) ok" > build.log\n'
            'echo "build.sh: built, see build.log"\n'))
        return {"mode": mode, "log": "build.log", "want": f"build {mode} ok"}

    def parts_for(self, state):
        """FB5 п. 68: вариант со сборкой — файл сделан, сборка доделала."""
        if state.get("spam") or state.get("log") != "build.log":
            return []
        return ["config.txt сделан", "сборка доделала (fg)"]

    def progress(self, ctx):
        s, box = ctx.state, ctx.box
        try:
            done = (box / s["log"]).read_text("utf-8").strip() == s["want"]
        except OSError:
            done = False
        return [(box / "config.txt").is_file(), done]

    def check(self, ctx):
        s, box = ctx.state, ctx.box
        if s.get("spam"):
            spam, fetch = _pid(box, "spam.pid"), _pid(box, "fetch.pid")
            if spam is None or fetch is None:
                return Verdict(False)
            done = (box / "fetched.txt").is_file()
            if not done and kit.gone(fetch):
                return Verdict(False, "fetch.sh остановлен раньше, чем доделал. Набери reset "
                                      "и запусти оба снова: останови только spam.sh.")
            if not kit.gone(spam):
                return Verdict(False)
            if not done:
                return Verdict(False, "spam.sh остановлен. fetch.sh ещё качает — подожди: "
                                      "jobs покажет, когда он закончит.")
            return Verdict(True)
        try:
            text = (box / s["log"]).read_text("utf-8").strip()
        except OSError:
            return Verdict(False)
        return Verdict(text == s["want"])


# FB10: «Задачи в фоне» — сразу после vim: Ctrl+Z там уже встречался (приостановленный vim)
TASKS = [ManFlag(), FlagUse(), LessSearch(), NanoConfig(), VimTrap(), VimEscape(), VimPurge(),
         JobControl(), BrewLesson(), TldrTar(), JsonCheck(), BatLines(), BossTools()]
