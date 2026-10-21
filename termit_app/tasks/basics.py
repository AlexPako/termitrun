"""Трек «Основы»: навигация, файлы, маски."""
import os
import re
from pathlib import Path
from typing import List

from termit_app import sandbox, textnorm
from termit_app.tasks import kit
from termit_app.tasks.base import (MSG_FILE, MSG_FILE_NUMBER, AnswerTask, Task, Variant,
                                    Verdict, sources, variant_index)


# FB5: первый урок — что такое терминал, оболочка и команда. Ответы честные в любом
# терминале: игра сверяет с тем, что видит сама песочница, а не с ожиданием «у всех iTerm2».
OTHER_SHELLS = ("bash", "sh", "fish", "tcsh", "csh", "ksh", "dash")
# имя программы-терминала из $TERM_PROGRAM: iTerm.app, Apple_Terminal, vscode, tmux, ghostty
_TERM_NAME = re.compile(r"[\w.+-]{1,40}")
_ZSH_VERSION = re.compile(r"\d+(?:\.\d+)*")


def term_program() -> str:
    """Название программы-терминала, как его видит песочница: родитель передаёт
    $TERM_PROGRAM в окружение zsh как есть (shell_run.ENV_KEEP_PREFIX). Странное — пусто."""
    value = os.environ.get("TERM_PROGRAM", "").strip()
    return value if _TERM_NAME.fullmatch(value) else ""


_VERSIONS: dict = {}


def zsh_versions() -> List[str]:
    """Номера версий zsh, которые может запустить игра: тот, что найдёт PATH (его берёт
    shell_run.argv), и системный /bin/zsh (его берут прогоны эталонов). Каждый — спросить
    у самой программы один раз за процесс."""
    import shutil
    import subprocess
    out = []
    for zsh in dict.fromkeys(p for p in (shutil.which("zsh"), "/bin/zsh") if p):
        if zsh not in _VERSIONS:
            try:
                run = subprocess.run([zsh, "-fc", "print -r -- $ZSH_VERSION"],
                                     capture_output=True, text=True, timeout=10)
                value = run.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                value = ""
            _VERSIONS[zsh] = value if _ZSH_VERSION.fullmatch(value) else ""
        if _VERSIONS[zsh] and _VERSIONS[zsh] not in out:
            out.append(_VERSIONS[zsh])
    return out


def program_name(given: str) -> str:
    """Имя программы из сданного: путь /bin/zsh → zsh, «-zsh» (так $0 зовёт оболочку входа)
    → zsh. Регистр не важен."""
    name = textnorm.clean(given).rstrip("/").rsplit("/", 1)[-1]
    return name.lstrip("-").lower()


class MeetTerminal(AnswerTask):
    id = "meet_terminal"
    track = "basics"
    title = "Терминал и оболочка"
    # FB5-plain: по одному понятию за раз; переменная — сразу бытовым образом (ярлык), имена
    # БОЛЬШИМИ и регистр важен (владелец спросил: «ШЕЛЛ большими — это важно?»)
    scroll = ("Терминал — окно для команд: Terminal.app или iTerm2 (он удобнее).\n"
              "Оболочка (shell) — программа в окне, что понимает команды; на Mac это zsh.\n"
              "echo печатает, что ему дали. Переменная — ярлык: имя и значение на нём; "
              "знак $ перед именем — «покажи, что на ярлыке»: echo $SHELL.\n"
              "Имена пишут БОЛЬШИМИ, и это важно: $shell — пусто. ans $SHELL — сдать.")
    variants = (
        Variant("Узнай, какая оболочка понимает твои команды. Набери echo $SHELL и нажми "
                "Enter — терминал напечатает, где она лежит на диске, вроде /bin/zsh. Сдай "
                "это: ans $SHELL и Enter — ответ подставится сам.",
                wrong=("echo bash",),
                alternatives=("ans $0 — в $0 лежит имя программы, которая работает прямо "
                              "сейчас: оболочка назовёт себя сама",
                              "ans zsh — имя можно сдать и словом, без пути")),
        Variant("В какой программе-терминале открыто это окно? Её название хранит "
                "переменная TERM_PROGRAM. Сдай название: ans ОТВЕТ",
                hints=("Знак $ перед именем переменной — «покажи, что на ярлыке».",
                       "echo $TERM_PROGRAM напечатает название: iTerm.app — это iTerm2, "
                       "Apple_Terminal — встроенный Терминал.",
                       "ans $TERM_PROGRAM — $ подставит название прямо в ответ"),
                solution="ans $TERM_PROGRAM",
                # прогон эталонов идёт без переменных терминала (zsh -f, пустое окружение):
                # там вместо $TERM_PROGRAM — то, что видел родитель
                solution_script="print -r -- ${{TERM_PROGRAM:-{answer}}}",
                wrong=("echo zsh",),
                alternatives=("echo $TERM_PROGRAM, а потом ans и название руками — "
                              "большие и маленькие буквы тут не важны",),
                explain=("Терминал — окно, оболочка — программа в нём, а TERM_PROGRAM "
                         "называет само окно. iTerm2 удобнее встроенного Терминала: "
                         "вкладки, деление окна, поиск по тексту в окне.")),
        Variant("Узнай номер версии своей оболочки zsh — его хранит переменная "
                "ZSH_VERSION. Сдай только номер: ans ОТВЕТ",
                hints=("Знак $ перед именем переменной — «покажи, что на ярлыке».",
                       "echo $ZSH_VERSION напечатает номер, например 5.9.",
                       "ans $ZSH_VERSION — $ подставит номер прямо в ответ"),
                solution="ans $ZSH_VERSION", solution_script="echo $ZSH_VERSION",
                wrong=("echo $ZSH_NAME",),
                alternatives=("zsh --version — спросить саму программу (--version — "
                              "версия): она напечатает «zsh 5.9 (…)», сдай только номер",),
                explain=("Оболочка — обычная программа, и у неё есть версия. Команда из чужой "
                         "инструкции не заводится — первым делом глянь версию: в старой "
                         "чего-то может и не быть.")),
    )
    par = 20
    hints = ("Где лежит оболочка, написано на ярлыке SHELL; знак $ перед именем — «покажи».",
             "echo $SHELL напечатает что-то вроде /bin/zsh.",
             "ans $SHELL — $SHELL подставит это прямо в ответ")
    solution = "ans $SHELL"
    # $SHELL приходит из окружения терминала, в прогоне эталонов (zsh -f) его нет; $0 —
    # та же оболочка, её имя zsh знает всегда
    solution_script = "echo $0"
    explain = ("$SHELL — оболочка, которую Mac запускает в новом окне терминала. С 2019 года "
               "в macOS это zsh; bash — старая оболочка, её ещё встретишь на серверах.")
    spell = "echo $SHELL — какая у меня оболочка; echo $TERM_PROGRAM — в каком я терминале"
    trap_messages = {
        "term_type": "Это TERM — тип терминала для программ. Название самого окна хранит "
                     "TERM_PROGRAM.",
    }
    MSG_OTHER_SHELL = ("{name} — оболочка, которую твой Mac открывает в новых окнах (её "
                       "хранит $SHELL). А игра запускает zsh — спроси её саму: ans $0.")
    MSG_TERM_NOT_SHELL = ("Это название окна-терминала. А спрашивают оболочку — программу "
                          "внутри окна: echo $SHELL.")
    MSG_SHELL_NOT_TERM = ("zsh — это оболочка, программа внутри окна. А спрашивают само окно "
                          "— его название хранит TERM_PROGRAM.")
    MSG_NAME_NOT_VERSION = "zsh — это имя оболочки, а нужен номер её версии: echo $ZSH_VERSION."
    TERM_MODE = 1
    VERSION_MODE = 2

    def allowed_variants(self, box):
        """Терминал — только если игра видит его название, версия — если zsh её назвал."""
        out = [0]
        if term_program():
            out.append(self.TERM_MODE)
        if zsh_versions():
            out.append(self.VERSION_MODE)
        return tuple(out)

    def setup_variant(self, box, rng, variant):
        if variant == self.TERM_MODE:
            state = {"mode": "term", "answer": term_program()}
            term = os.environ.get("TERM", "").strip()
            if _TERM_NAME.fullmatch(term):
                state["traps"] = [["term_type", term]]
            return state
        if variant == self.VERSION_MODE:
            versions = zsh_versions()
            return {"mode": "version", "answer": versions[0], "accept": versions}
        return {"mode": "shell", "answer": "zsh"}

    def matches(self, given, ctx):
        st = ctx.state
        mode = st.get("mode", "shell")
        if mode == "shell":
            return program_name(given) == "zsh"
        if mode == "term":
            # название, что видел родитель при сборке, или то, что видит песочница сейчас
            # (задачу продолжили в другом окне)
            return any(textnorm.same_text(given, name)
                       for name in (st["answer"], term_program()) if name)
        return any(textnorm.same_text(given, v) for v in st.get("accept") or [st["answer"]])

    def wrong_message(self, given, ctx):
        mode = ctx.state.get("mode", "shell")
        name = program_name(given)
        if mode == "shell" and name in OTHER_SHELLS:
            return self.MSG_OTHER_SHELL.format(name=name)
        if mode == "shell" and term_program() and textnorm.same_text(given, term_program()):
            return self.MSG_TERM_NOT_SHELL
        if mode == "term" and name == "zsh":
            return self.MSG_SHELL_NOT_TERM
        if mode == "version" and name == "zsh":
            return self.MSG_NAME_NOT_VERSION
        return super().wrong_message(given, ctx)

    def common_mistake(self, given, ctx):
        """Общие промахи, кроме «имя файла — открой его cat»: iTerm.app и /bin/zsh похожи на
        имена файлов, но совет «cat /bin/zsh» здесь только собьёт."""
        message = super().common_mistake(given, ctx)
        if message in (MSG_FILE.format(name=textnorm.clean(given)),
                       MSG_FILE_NUMBER.format(name=textnorm.clean(given))):
            return None
        return message


class WhereAmI(AnswerTask):
    id = "where_am_i"
    track = "basics"
    title = "Где я стою"
    kind_answer = "path"
    # первая минута (П3.4): один способ сдать; $PWD и буфер — в «можно и так» и дальше
    scroll = ("pwd — полный путь текущей папки.\n"
              "Путь не перепечатывай: ans $(pwd) — $( ) выполнит команду и подставит её вывод "
              "(то, что она напечатала) прямо в ответ.\n"
              "Путь выйдет длинным: задание идёт в песочнице — отдельной папке игры, "
              "настоящие файлы она не трогает.")
    # «ans .» засчитывается в любом варианте (путь относительно текущей папки) — не wrong
    variants = (
        Variant("Назови полный путь папки, в которой ты сейчас стоишь. Набери pwd и нажми "
                "Enter — терминал напечатает путь. Сдай его: ans $(pwd) и Enter — путь "
                "подставится в ответ сам.",
                wrong=("echo $HOME",),
                alternatives=("ans $PWD — в $PWD терминал всегда держит путь текущей папки",
                              "мышью — выдели путь, что напечатал pwd, и нажми Cmd+C; потом "
                              "набери ans и пробел, вставь путь Cmd+V и нажми Enter")),
        Variant("Тебя забросило в незнакомую глубину, и откуда ты пришёл — неизвестно. "
                "Где ты? Сдай полный путь: ans ПУТЬ",
                wrong=("echo src", "echo {name}/src"),
                alternatives=("ans $PWD — в $PWD терминал всегда держит путь текущей папки",)),
        Variant("Нужен адрес не этой папки, а той, что на уровень выше неё. "
                "Назови её полный путь: ans ПУТЬ",
                hints=("Папка уровнем выше — это .. — туда можно просто подняться.",
                       "Поднимись командой cd .. и там спроси путь у pwd.",
                       "cd .. && ans $(pwd) — && запустит ans, только если cd удался"),
                solution="cd .. && ans $(pwd)", solution_script="cd .. && pwd",
                wrong=("pwd",),
                alternatives=("ans .. — путь можно сдать и относительно текущей папки",
                              "ans $(dirname $PWD) — dirname отрезает последнюю папку")),
    )
    start_dir = "{start}"
    par = 20
    hints = ("Путь печатает команда pwd. Перепечатывать его не нужно — вывод можно подставить.",
             "$( ) выполняет команду внутри и подставляет её вывод в строку: ans $(pwd)",
             "ans $(pwd) — $( ) подставит вывод pwd прямо в ответ")
    solution = "ans $(pwd)"
    solution_script = "pwd"
    explain = ("pwd печатает полный путь текущей папки. Вывод не перепечатывают — пальцы врут: "
               "ans $(pwd) подставит его сам, а в $PWD текущий путь лежит всегда.")
    spell = "pwd — где я стою (полный путь текущей папки)"
    trap_messages = {"here": "Это путь текущей папки, а нужна папка на уровень выше: "
                             "поднимись cd .. и спроси pwd там."}

    def setup_variant(self, box, rng, variant):
        if variant == 0:
            return {"start": ".", "answer": "."}
        name = kit.latin(rng)
        if variant == 1:
            start = f"projects/{name}/src"
            for d in (start, f"projects/{name}/docs", f"projects/{kit.latin(rng)}_old"):
                (box / d).mkdir(parents=True, exist_ok=True)
            kit.write(box / start / "main.txt", "Code draft.\n")
            return {"start": start, "name": name, "answer": start}
        parent = f"work/{name}"
        start = f"{parent}/{rng.choice(['inbox', 'tmp', 'drafts'])}"
        (box / start).mkdir(parents=True)
        kit.write(box / parent / "plan.txt", "Plan for the week.\n")
        return {"start": start, "name": name, "answer": parent, "traps": [["here", start]]}


class ClimbDown(AnswerTask):
    id = "climb_down"
    track = "basics"
    title = "Записка в глубине"
    # FB5-plain: «в чём отличие cat от echo?» — сравнение там, где игрок видит обе команды
    # FB12 (N2): && — в уроке back_up, здесь — только поясняется в подсказке и разборе
    scroll = ("cd ПАПКА — войти (можно по пути a/b/c); ls — что в папке; cat ФАЙЛ — что в "
              "файле: echo notes.txt печатает само слово, а cat notes.txt — то, что внутри.\n"
              "Две-три буквы имени и Tab — терминал допишет.\n"
              "ans $(cat note.txt) подставит слово. Повисло (cat ждёт ввода) — Ctrl+C.")
    variants = (
        Variant("Глубоко в {path} лежит файл note.txt. Зайди туда и прочти, "
                "какое слово в нём написано. Ответ: ans СЛОВО",
                wrong=("cat note.txt",),
                alternatives=("cat {path}/note.txt — прочесть, не заходя внутрь",
                              "ans $(cat {path}/note.txt) — cat прочтёт записку, а $( ) "
                              "подставит её слово прямо в ответ")),
        Variant("Записка note.txt лежит в «{path}» — в имени папки есть пробелы. "
                "Доберись до неё и назови слово: ans СЛОВО",
                hints=("Пробел cd считает границей: имя из трёх слов нужно склеить.",
                       "Возьми путь в кавычки — или набери cd Old и жми Tab: он сам поставит \\ "
                       "перед каждым пробелом.",
                       'cd "{path}" && cat note.txt — потом ans $(cat note.txt)'),
                solution='cd "{path}" && cat note.txt',
                wrong=("cd Old Projects 2719/{sub} && cat note.txt", "cat note.txt"),
                alternatives=("cd Old\\ Projects\\ 2719/{sub} — пробелы через \\ (так их "
                              "пишет Tab)",)),
        Variant("Здесь три папки, и в каждой лежит свой note.txt. Какая записка настоящая, "
                "сказано в readme.txt. Найди её и сдай слово: ans СЛОВО",
                hints=("Начни с cat readme.txt — там сказано, куда идти.",
                       "Потом cd в названную папку и cat note.txt; чужие записки — обманки.",
                       "cat readme.txt, затем cd {target} && cat note.txt — и ans $(cat note.txt)"),
                solution="cat readme.txt && cd {target} && cat note.txt",
                solution_script="cd {target} && cat note.txt",
                wrong=("cd {decoy} && cat note.txt", "cat note.txt"),
                alternatives=("ans $(cat {target}/note.txt) — когда папка уже известна",)),
    )
    par = 40
    hints = ("Сначала войди в папку командой cd, потом прочти файл командой cat.",
             "Имена длинные — набери cd old и жми Tab.",
             "cd {path} && cat note.txt (&& пустит cat, только если cd удался) — потом "
             "ans $(cat note.txt)")
    solution = "cd {path} && cat note.txt"
    explain = ("cd меняет текущую папку, cat печатает файл. Длинные имена за тебя добьёт Tab, а "
               "&& пускает вторую команду, только если первая удалась.")
    spell = "cd путь — войти в папку; cat файл — прочесть файл целиком"
    trap_messages = {"decoy": "Это записка-обманка. Какая настоящая — сказано в readme.txt."}

    def setup_variant(self, box, rng, variant):
        if variant == 2:
            dirs = rng.sample(kit.LATIN, 3)
            words = rng.sample(kit.WORDS, 3)
            for d, w in zip(dirs, words):
                kit.write(box / d / "note.txt", f"{w}\n")
            target, decoy = dirs[0], dirs[1]
            kit.write(box / "readme.txt", f"The real note is in the {target} folder.\n")
            return {"target": target, "decoy": decoy, "answer": words[0],
                    "traps": [["decoy", w] for w in words[1:]],
                    "sources": sources(box, f"{target}/note.txt", "readme.txt")}
        sub = f"{rng.choice(['archive', 'misc', 'drafts'])}_{kit.latin(rng)}"
        w = kit.word(rng)
        if variant == 1:
            path = f"Old Projects 2719/{sub}"
            kit.write(box / path / "note.txt", f"{w}\n")
            kit.write(box / "Old Projects 2719" / "readme.txt", "The note is deeper.\n")
            return {"path": path, "sub": sub, "answer": w,
                    "sources": sources(box, f"{path}/note.txt")}
        path = "/".join(["old_projects_backup_2719", sub, "notes"])
        kit.write(box / path / "note.txt", f"{w}\n")
        kit.write(box / "old_projects_backup_2719" / "readme.txt", "The note is deeper.\n")
        return {"path": path, "answer": w, "sources": sources(box, f"{path}/note.txt")}


class BackUp(Task):
    id = "back_up"
    track = "basics"
    title = "Наверх по лестнице"
    scroll = (".. — папка на уровень выше. cd .. — подняться на этаж, cd ../.. — на два. "
              "cd без аргумента (слова после команды) — домой (~), cd - — туда, где был "
              "только что.\n"
              "cd .. && ls — две команды подряд: && пускает вторую, только если первая удалась.")
    variants = (
        Variant("Ты стоишь в archive/{year}/q3/docs. Поднимись на три уровня вверх — "
                "в саму папку archive — одной командой.",
                wrong=("cd ..", "cd ../.."),
                alternatives=("cd .. трижды — верно, но три команды вместо одной",)),
        Variant("Из archive/{year}/q3 перейди в соседнюю ветку archive/other: два шага вверх "
                "и сразу вбок — одной строкой.",
                hints=("Сначала посчитай, сколько раз нужно подняться до archive.",
                       "Вверх — .., а после подъёма путь можно продолжить: ../../имя",
                       "cd ../../other"),
                solution="cd ../../other",
                wrong=("cd ../other", "cd ../.."),
                alternatives=("cd ../.. && cd other — то же в две команды",),
                explain="После подъёма путь продолжается: ../../other — два этажа вверх и "
                        "сразу вбок, одной строкой."),
        Variant("Забрёл глубоко в archive/{year}/q3/docs. Вернись в свою домашнюю папку "
                "самой короткой командой.",
                hints=("Домашняя папка — это ~, и путь к ней знать не нужно.",
                       "У cd есть особый случай: без аргумента он ведёт домой.",
                       "cd — или cd ~"),
                solution="cd",
                wrong=("cd ../../../..", "cd /"),
                alternatives=("cd ~ — то же самое, явно",),
                explain="cd без аргумента ведёт домой, откуда бы ты ни начал: путь к дому "
                        "помнит сам zsh."),
    )
    start_dir = "{start}"
    par = 30
    hints = ("Две точки .. означают папку на уровень выше.",
             "Уровни можно склеить через /: ../..",
             "cd ../../..")
    solution = "cd ../../.."
    explain = ".. — папка этажом выше; ../../.. — три этажа вверх за один шаг."
    spell = "cd .. — на уровень выше; cd ../.. — на два"

    def setup_variant(self, box, rng, variant):
        year = str(rng.randint(2719, 2725))
        (box / "archive" / year / "q3" / "docs").mkdir(parents=True)
        (box / "archive" / "other").mkdir()
        kit.write(box / "archive" / "other" / "list.txt", "To-do list.\n")
        if variant == 1:
            return {"year": year, "start": f"archive/{year}/q3", "target": "archive/other"}
        target = (str(kit.home(box).relative_to(box)) if variant == 2 else "archive")
        return {"year": year, "start": f"archive/{year}/q3/docs", "target": target}

    def check(self, ctx):
        return Verdict(ctx.pwd is not None and
                       ctx.pwd.resolve() == (ctx.box / ctx.state["target"]).resolve())


class HomeTilde(AnswerTask):
    id = "home_tilde"
    track = "basics"
    title = "Записка дома"
    scroll = ("~ — твоя домашняя папка. cd ~ (или просто cd) — домой; cat ~/файл — файл из "
              "домашней папки, где бы ты ни стоял; cd - — вернуться туда, где был.\n"
              "В игре ~ — дом песочницы (pwd там покажет …/.termit/home), а не твоя "
              "настоящая домашняя папка: её игра не трогает.\n"
              "Нужно одно слово из вывода — дважды щёлкни по нему мышью: выделится только оно; "
              "Cmd+C, потом ans, пробел и Cmd+V.")
    variants = (
        Variant("У тебя в домашней папке лежит записка ~/memo.txt. Прочти её, не уходя "
                "отсюда. Ответ — слово из записки: ans СЛОВО",
                wrong=("cat memo.txt",),
                alternatives=("cd ~ && cat memo.txt && cd - — сходить домой и вернуться",)),
        # копия, а не ответ: решено, когда здесь появилась точная копия, а дома — оригинал
        Variant("Записка ~/memo.txt нужна здесь, в текущей папке. Сделай её копию сюда "
                "(копию делает cp ЧТО КУДА) — оригинал пусть остаётся дома.",
                hints=("~ — домашняя папка: до файла можно дотянуться, не уходя отсюда.",
                       "Точка . означает «сюда»: КУДА в cp можно записать одной точкой.",
                       "cp ~/memo.txt ."),
                solution="cp ~/memo.txt .", solution_script="cp ~/memo.txt .",
                wrong=("mv ~/memo.txt .", "cat ~/memo.txt"),
                alternatives=("cp ~/memo.txt memo.txt — то же с именем явно",)),
        Variant("Дома, в подпапке notes, лежит today.txt. Прочти его отсюда, никуда не "
                "переходя, и сдай слово: ans СЛОВО",
                hints=("~ работает и с вложенными папками: путь продолжается после ~/.",
                       "Путь до файла: ~/notes/today.txt — читай его cat.",
                       "cat ~/notes/today.txt, затем ans СЛОВО"),
                solution="cat ~/notes/today.txt",
                solution_script="cat ~/notes/today.txt | cut -d: -f2",
                wrong=("cat notes/today.txt | cut -d: -f2", "cat ~/today.txt | cut -d: -f2"),
                alternatives=("cd ~/notes && cat today.txt && cd - — сходить в папку, "
                              "прочесть и вернуться обратно",)),
    )
    par = 25
    hints = ("Значок ~ означает домашнюю папку.",
             "Можно не ходить домой: cat ~/memo.txt",
             "cat ~/memo.txt, затем ans СЛОВО (двойной щелчок по слову выделит его)")
    solution = "cat ~/memo.txt"
    solution_script = "cat ~/memo.txt | cut -d: -f2"
    explain = "~ — короткая запись пути домой: файл из дома достаётся откуда угодно, без походов."
    spell = "~ — домашняя папка; cd — домой; cd - — обратно"
    trap_messages = {"yesterday": "Это вчерашняя записка, а нужна today.txt."}

    def setup_variant(self, box, rng, variant):
        w = kit.word(rng)
        home = kit.home(box)
        if variant == 2:
            kit.write(home / "notes" / "today.txt", f"Today: {w}\n")
            old = kit.word(rng)
            kit.write(home / "notes" / "yesterday.txt", f"Yesterday: {old}\n")
            return {"answer": w, "traps": [["yesterday", old]],
                    "sources": sources(box, ".termit/home/notes/today.txt")}
        f = kit.write(home / "memo.txt", f"Today's word: {w}\n")
        st = {"answer": w, "sha": kit.sha(f)}
        if variant == 0:
            st["sources"] = sources(box, ".termit/home/memo.txt")
        return st

    def takes_answer(self, state):
        """Вариант с копией — «сделай», а не «ответь»: карточка не зовёт сдавать слово (FB6)."""
        return state.get("_variant") != 1

    def wrong_message(self, given, ctx):
        if ctx.state.get("_variant") == 1:
            return "Здесь ответ сдавать не нужно — сделай копию записки сюда."
        return super().wrong_message(given, ctx)

    def check(self, ctx):
        if ctx.state.get("_variant") != 1:
            return super().check(ctx)
        # проверку зовёт судья у родителя: чтение только внутри песочницы, без симлинков
        here = kit.sha_in_box(ctx.box, "memo.txt")
        home = kit.sha_in_box(ctx.box, kit.home(ctx.box) / "memo.txt")
        want = ctx.state["sha"]
        same = here is not None and here == home == want
        if same:
            return Verdict(True)
        if home != want and here == want:
            return Verdict(False, "Оригинал ушёл из дома: mv переносит, а нужна копия. Верни "
                                  "его домой (mv memo.txt ~/) и сделай cp.")
        if home != want:
            return Verdict(False, "Записки с тем же текстом больше нет дома. "
                           + kit.RESET_TAIL)
        if ctx.answer is not None:
            return Verdict(False, self.wrong_message(ctx.answer, ctx))
        return Verdict(False)


class HiddenCache(AnswerTask):
    id = "hidden_cache"
    track = "basics"
    title = "Скрытый файл"
    scroll = ("ls -la — показать все файлы, включая скрытые (имя начинается с точки), с "
              "размерами и датами. Строки . и .. в начале — это сама папка и папка выше.\n"
              "Скрытой бывает и папка: точка в начале — часть имени, а не команда.\n"
              "Буквы после минуса — флаги (ключи): меняют поведение команды. -l — long "
              "(подробно), -a — all (все); короткие склеивают: -la = -l -a. Регистр (большие или маленькие буквы) важен: ls -A — "
              "almost all, всё, кроме . и ..")
    variants = (
        Variant("В этой папке есть скрытый файл. Найди его и назови слово, что в нём "
                "записано: ans СЛОВО",
                wrong=("cat .old_cache",),
                alternatives=("ls -a — без подробностей, только имена",)),
        Variant("Обычный ls показывает не всё: здесь спрятана целая папка, а в ней записка. "
                "Прочти её: ans СЛОВО",
                hints=("Скрытой бывает и папка — имя тоже начинается с точки.",
                       "ls -la покажет её: у папки строка начинается с буквы d. Имя с "
                       "точкой, например .stash, — это имя папки, а не команда; что внутри, "
                       "покажет ls -la .stash",
                       "ls -la, затем cat .stash/note.txt — и ans $(cat .stash/note.txt)"),
                solution="ls -la && cat .stash/note.txt",
                solution_script="cat .stash/note.txt",
                wrong=("cat .secret",),
                alternatives=("ls -la .stash — показать, что лежит в скрытой папке .stash, "
                              "не заходя в неё",)),
        Variant("Сколько скрытых файлов в папке {folder}? Сдай число: ans ЧИСЛО",
                hints=("Скрытые файлы покажет ls -la, имя у них начинается с точки.",
                       "Строки . и .. — не файлы, а сама папка и папка выше: их не считай.",
                       "ls -la {folder} — сосчитай строки с точкой, кроме . и .., и ans ЧИСЛО"),
                solution="ls -la {folder}",
                solution_script="ls -A {folder} | grep -c '^[.]'",
                wrong=("ls -a {folder} | grep -c '^[.]'",),
                alternatives=("ls -A {folder} — то же без . и .., считать проще",)),
    )
    par = 30
    hints = ("Скрытые файлы начинаются с точки, обычный ls их не показывает.",
             "ls -la покажет всё.",
             "ls -la, затем cat .secret — и ans $(cat .secret)")
    solution = "ls -la && cat .secret"
    solution_script = "cat .secret"
    explain = "Файлы с точкой в начале скрыты; флаг -a показывает их, -l — подробности."
    spell = "ls -la — все файлы, включая скрытые, с подробностями"
    trap_messages = {
        "old": "Это .old_cache — старая копия, обманка. Слово лежит в другом скрытом файле.",
        "secret": "Это .secret — пустышка. Записка — в скрытой папке: ls -la покажет и её.",
        "stashdir": "Это имя скрытой папки, а нужно слово из записки, что лежит в ней.",
        "dots": "Посчитаны и строки . и .. — это сама папка и папка выше, не файлы.",
        "all": "Посчитаны все файлы, а нужны только скрытые — те, чьё имя начинается с точки.",
    }

    def setup_variant(self, box, rng, variant):
        w = kit.word(rng)
        if variant == 2:
            folder = rng.choice(["inbox", "drop", "mail"])
            docs = rng.randint(4, 8)
            for i in range(docs):
                kit.write(box / folder / f"doc_{i + 1}.txt", "Nothing here.\n")
            n = rng.randint(2, 6)
            for name in rng.sample(kit.LATIN, n):
                kit.write(box / folder / f".{name}", "hidden\n")
            return {"folder": folder, "answer": str(n),
                    "traps": [["dots", n + 2], ["all", n + docs], ["all", n + docs + 2]]}
        for i in range(rng.randint(6, 10)):
            kit.write(box / f"doc_{i + 1}.txt", "Nothing here.\n")
        if variant == 1:
            kit.write(box / ".stash" / "note.txt", f"{w}\n")
            kit.write(box / ".secret", "Not here.\n")
            return {"answer": w, "traps": [["secret", "Not here"], ["secret", ".secret"],
                                           ["stashdir", ".stash"]],
                    "sources": sources(box, ".stash/note.txt")}
        kit.write(box / ".secret", f"{w}\n")
        kit.write(box / ".old_cache", "Old cache only.\n")
        return {"answer": w, "traps": [["old", "Old cache only"], ["old", "old cache"],
                                       ["old", ".old_cache"]],
                "sources": sources(box, ".secret")}

    def answer_kind(self, state):
        return "number" if state.get("_variant") == 2 else "text"   # счёт: «3», «3.0»


class RunScript(AnswerTask):
    id = "run_script"
    track = "basics"
    title = "Запустить скрипт"
    scroll = ("Скрипт — текстовый файл с командами. ./файл — запустить файл из текущей папки "
              "(без ./ терминал ищет программу среди установленных). chmod +x файл — дать "
              "право на запуск (разрешить файлу запускаться).")
    # «decode.sh без ./» — тоже неверно, но это command not found: D004 счёл бы такое
    # решение сломанным само по себе. Ловушки — «без chmod» и «не из той папки».
    variants = (
        Variant("Здесь лежит скрипт decode.sh. Сделай его исполняемым и запусти — "
                "он напечатает слово. Ответ: ans СЛОВО",
                wrong=("./decode.sh",),
                alternatives=("sh decode.sh — sh прочтёт файл и без права на запуск",)),
        Variant("Скрипт decode.sh лежит в папке tools. Дай ему право на запуск и запусти "
                "отсюда, не заходя внутрь, — выйдет слово: ans СЛОВО",
                hints=("Заходить в папку не обязательно: путь к скрипту пишется целиком.",
                       "Право — chmod +x tools/decode.sh, запуск — ./tools/decode.sh",
                       "chmod +x tools/decode.sh && ./tools/decode.sh — или ans "
                       "$(./tools/decode.sh)"),
                solution="chmod +x tools/decode.sh && ./tools/decode.sh",
                wrong=("./tools/decode.sh", "chmod +x tools/decode.sh && ./decode.sh"),
                alternatives=("sh tools/decode.sh — без права на запуск",)),
        Variant("В папке bin — готовый скрипт decode.sh, право на запуск у него уже есть. "
                "Но слово он выдаёт, только если стоишь в его папке. Добудь слово: ans СЛОВО",
                hints=("Скрипт ищет свои данные в текущей папке — стоять нужно рядом с ним.",
                       "Сначала cd bin, потом ./decode.sh.",
                       "cd bin && ./decode.sh — или ans $(cd bin && ./decode.sh)"),
                solution="cd bin && ./decode.sh",
                wrong=("./bin/decode.sh", "sh bin/decode.sh"),
                alternatives=("(cd bin && ./decode.sh) — в скобках cd не уводит из текущей "
                              "папки",)),
    )
    par = 40
    hints = ("Файл нельзя запустить, пока у него нет права на запуск.",
             "Право даёт chmod +x decode.sh, запуск — ./decode.sh",
             "chmod +x decode.sh && ./decode.sh — или сразу ans $(./decode.sh)")
    solution = "chmod +x decode.sh && ./decode.sh"
    explain = "./ — «отсюда»: без него zsh ищет команду в PATH. chmod +x даёт право на запуск."
    spell = "./файл — запустить файл отсюда; chmod +x файл — разрешить запуск"
    trap_messages = {
        "reversed": "Это слово задом наперёд — так оно лежит в файле. Расшифрует его сам "
                    "скрипт: запусти его.",
        "cwd": "Это ошибка скрипта: он ищет данные в папке, где стоишь. Встань рядом с ним "
               "(cd) и запусти оттуда.",
    }

    def wrong_message(self, given, ctx):
        if textnorm.clean(given).rstrip("/").endswith("decode.sh"):     # I3 ревью C1b
            return ("decode.sh — программа: её не читают, а запускают — ./decode.sh (без права "
                    "на запуск сперва chmod +x). Сдай то, что она выведет.")
        return super().wrong_message(given, ctx)

    BY_DIRNAME = ("#!/bin/sh\n# Prints the word backwards.\n"
                  'rev "$(dirname "$0")/.word"\n')
    BY_CWD = ("#!/bin/sh\n# Prints the word backwards, from the current folder.\n"
              "if [ ! -f .word ]; then\n"
              '  echo "decode.sh: run me from my own folder" >&2\n'
              "  exit 1\n"
              "fi\n"
              "rev .word\n")

    def setup_variant(self, box, rng, variant):
        w = kit.latin(rng)
        where = box / ("", "tools", "bin")[variant]
        kit.write(where / ".word", w[::-1] + "\n")
        script = kit.write(where / "decode.sh",
                           self.BY_CWD if variant == 2 else self.BY_DIRNAME)
        os.chmod(script, 0o755 if variant == 2 else 0o644)
        traps = [["reversed", w[::-1]]]
        if variant == 2:
            traps.append(["cwd", "decode.sh: run me from my own folder"])
        rel = where.relative_to(box)
        return {"answer": w, "traps": traps,
                "sources": sources(box, rel / ".word", rel / "decode.sh")}


class MkdirP(Task):
    id = "mkdir_p"
    track = "basics"
    title = "Цепочка папок"
    scroll = ("mkdir папка — создать папку. mkdir -p a/b/c — создать всю цепочку разом (-p — "
              "parents, с родителями).\n"
              "Несколько имён через пробел — несколько папок одной командой: mkdir a b c. Общее "
              "начало пишут один раз, а разное — в фигурных скобках через запятую: mkdir -p "
              "x/{a,b} — это x/a и x/b.")
    variants = (
        Variant("Создай цепочку папок project/src/app/tests — одной командой, "
                "а не четырьмя.",
                wrong=("mkdir project/src/app/tests",),
                alternatives=("mkdir project project/src project/src/app project/src/app/tests "
                              "— работает, но длинно",)),
        Variant("Выгрузке за {month}.{year} нужен дом: data/{year}/{month}/raw. Папка {year} "
                "уже есть, остального нет. Проложи путь за один заход.",
                hints=("Голый mkdir споткнётся о папку {month}, которой ещё нет.",
                       "Флаг -p создаст недостающие папки и не тронет те, что уже есть.",
                       "mkdir -p data/{year}/{month}/raw"),
                solution="mkdir -p data/{year}/{month}/raw",
                wrong=("mkdir data/{year}/{month}/raw", "mkdir -p data/{year}/{month}"),
                alternatives=("mkdir data/{year}/{month} data/{year}/{month}/raw — по порядку, "
                              "без -p",)),
        Variant("Под отчёты за {year} год нужны две соседние папки: reports/{year}/q1 и "
                "reports/{year}/q2. Ни одной из них пока нет. Сделай обе одной командой.",
                hints=("mkdir принимает сразу несколько путей, а -p достроит недостающее.",
                       "Две ветки с общим началом можно записать в фигурных скобках через "
                       "запятую.",
                       "mkdir -p reports/{year}/{{q1,q2}}"),
                solution="mkdir -p reports/{year}/{{q1,q2}}",
                wrong=("mkdir reports/{year}/q1 reports/{year}/q2", "mkdir -p reports/{year}/q1"),
                alternatives=("mkdir -p reports/{year}/q1 reports/{year}/q2 — два пути без "
                              "скобок",)),
    )
    par = 25
    hints = ("Папки создаёт mkdir.",
             "У mkdir есть флаг, который создаёт и все промежуточные папки.",
             "mkdir -p project/src/app/tests")
    solution = "mkdir -p project/src/app/tests"
    explain = "-p (parents) создаёт недостающие папки по пути и не ругается, если они уже есть."
    spell = "mkdir -p a/b/c — создать цепочку папок"

    def setup_variant(self, box, rng, variant):
        year = str(rng.randint(2719, 2726))
        if variant == 1:
            month = f"{rng.randint(1, 12):02d}"
            other = f"{(int(month) % 12) + 1:02d}"
            kit.write(box / "data" / year / other / "raw" / "dump.csv", "id,sum\n1,10\n")
            return {"year": year, "month": month,
                    "need": [f"data/{year}/{month}/raw"]}
        if variant == 2:
            return {"year": year, "need": [f"reports/{year}/q1", f"reports/{year}/q2"]}
        return {"need": ["project/src/app/tests"]}

    def check(self, ctx):
        return Verdict(all((ctx.box / d).is_dir() for d in ctx.state["need"]))


class CopyMove(Task):
    id = "copy_move"
    track = "basics"
    title = "Копия и перенос"
    scroll = ("cp ЧТО КУДА — копия. mv ЧТО КУДА — перенос. mv старое новое — переименование. "
              "Перенос с новым именем: mv a.txt folder/b.txt\n"
              "Несколько файлов за раз: mv a.txt b.txt folder/ — перечисли их через пробел, "
              "а последней в строке поставь папку. cp умеет так же.")
    variants = (
        Variant("Сделай копию contract.txt в папку backup/, а черновик draft.txt перенеси "
                "в archive/ и назови там contract_v2.txt.",
                wrong=("mv contract.txt backup/ && mv draft.txt archive/contract_v2.txt",),
                alternatives=("cp contract.txt backup/contract.txt — имя в пути назначения "
                              "можно написать и явно",)),
        Variant("Черновик готов: переименуй draft.txt прямо здесь в final.txt, а его копию "
                "положи в backup/{year}/ — папка уже есть.",
                hints=("Переименование — тот же mv, только без папки в пути назначения.",
                       "Сначала mv draft.txt final.txt, потом cp готового файла в папку копий.",
                       "mv draft.txt final.txt && cp final.txt backup/{year}/"),
                solution="mv draft.txt final.txt && cp final.txt backup/{year}/",
                wrong=("cp draft.txt final.txt && cp final.txt backup/{year}/",
                       "mv draft.txt final.txt && mv final.txt backup/{year}/"),
                alternatives=("cp draft.txt backup/{year}/final.txt && mv draft.txt final.txt "
                              "— сначала копия, потом имя",)),
        Variant("Таблицы {a}.csv, {b}.csv и index.csv переезжают в data/. Только index.csv "
                "нужен и здесь: его — копией, остальные две — переносом.",
                hints=("Две таблицы переносит mv, а для index.csv нужен cp — оригинал останется.",
                       "mv берёт сразу несколько файлов: последней в строке идёт папка.",
                       "mv {a}.csv {b}.csv data/ && cp index.csv data/"),
                solution="mv {a}.csv {b}.csv data/ && cp index.csv data/",
                wrong=("mv {a}.csv {b}.csv index.csv data/",
                       "cp {a}.csv {b}.csv index.csv data/"),
                alternatives=("cp index.csv data/ && mv {a}.csv {b}.csv data/ — порядок не "
                              "важен",)),
    )
    par = 45
    hints = ("Копирует cp, переносит и переименовывает mv.",
             "cp contract.txt backup/ — копия; mv умеет перенести и сразу переименовать.",
             "cp contract.txt backup/ && mv draft.txt archive/contract_v2.txt")
    solution = "cp contract.txt backup/ && mv draft.txt archive/contract_v2.txt"
    explain = ("cp оригинал оставляет, mv — забирает с собой; новое имя в конце пути — сразу "
               "и переименование. Несколько файлов — одной командой: mv a.csv b.csv data/ "
               "(последней идёт папка), отдельная команда на каждый файл не нужна.")
    spell = "cp что куда — копия; mv что куда — перенос и переименование"

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            year = str(rng.randint(2719, 2726))
            draft = kit.write(box / "draft.txt", f"Final: {kit.word(rng)} and {kit.word(rng)}\n")
            kit.write(box / "backup" / year / "old_final.txt", "Last year's final.\n")
            # должно быть: имя → sha; отсутствовать: имена
            return {"year": year, "want": {"final.txt": kit.sha(draft),
                                           f"backup/{year}/final.txt": kit.sha(draft)},
                    "gone": ["draft.txt"]}
        if variant == 2:
            a, b = rng.sample(kit.LATIN, 2)
            names = [f"{a}.csv", f"{b}.csv", "index.csv"]
            sha = {n: kit.sha(kit.write(box / n, f"id,{n}\n{rng.randint(1, 99)},x\n"))
                   for n in names}
            kit.write(box / "notes.txt", "Not a table.\n")
            (box / "data").mkdir()
            want = {f"data/{n}": sha[n] for n in names}
            want["index.csv"] = sha["index.csv"]
            return {"a": a, "b": b, "csv": names, "want": want,
                    "gone": [f"{a}.csv", f"{b}.csv"]}
        contract = kit.write(box / "contract.txt",
                             f"Contract #{rng.randint(1, 999)}: {kit.word(rng)}\n")
        draft = kit.write(box / "draft.txt", f"Draft: {kit.word(rng)} and {kit.word(rng)}\n")
        (box / "backup").mkdir()
        (box / "archive").mkdir()
        return {"want": {"contract.txt": kit.sha(contract),
                         "backup/contract.txt": kit.sha(contract),
                         "archive/contract_v2.txt": kit.sha(draft)},
                "gone": ["draft.txt"]}

    def check(self, ctx):
        b, s = ctx.box, ctx.state
        same = all((b / rel).is_file() and kit.sha(b / rel) == h for rel, h in s["want"].items())
        if same and not any((b / rel).exists() for rel in s["gone"]):
            return Verdict(True)
        if kit.lost(b, s["want"].values()):     # содержимого нет нигде — стёрто или испорчено
            return Verdict(False, "Нужный файл стёрт или испорчен — его текста больше нет "
                                  "ни в одном файле. " + kit.RESET_TAIL)
        return self._mixed_up(b, s) or Verdict(False)

    MSG_MOVED = ("{name} пропал из {here}: mv переносит, а здесь нужна копия. Верни его: "
                 "mv {back} {where} — и сделай cp.")
    MSG_LEFT = ("{names} {verb} на месте: {pron} нужно было перенести (mv), а не скопировать. "
                "Копия уже лежит где надо — лишнее убери: rm {args}")

    def _mixed_up(self, b, s):
        """FB6: перепутал cp и mv — без отклика игрок не видел, почему не засчитано.
        Только тупики: оригинала нет, а его текст лежит лишь там, куда шла копия (mv вместо
        cp); или всё на местах, но то, что надо было унести, осталось (cp вместо mv)."""
        want = s["want"]
        have = {rel: kit.sha_in_box(b, rel) for rel in want}
        left = [rel for rel in s["gone"] if kit.sha_in_box(b, rel) is not None]
        left_shas = {kit.sha_in_box(b, rel) for rel in left}
        for rel, h in want.items():
            if have[rel] is not None or h in left_shas:
                continue
            back = [r for r, got in have.items() if r != rel and got == h]
            if back:
                where = str(Path(rel).parent)
                return Verdict(False, self.MSG_MOVED.format(
                    name=Path(rel).name, back=back[0],
                    where="." if where == "." else where + "/",
                    here="этой папки" if where == "." else where + "/"))
        if left and all(have[rel] == h for rel, h in want.items()):
            many = len(left) > 1
            return Verdict(False, self.MSG_LEFT.format(
                names=", ".join(left), verb="остались" if many else "остался",
                pron="их" if many else "его", args=" ".join(left)))
        return None


class FileExt(AnswerTask):
    """FB3 (6): мини-урок «расширения файлов» — до первых масок вида *.tmp. Расширение — часть
    имени и подсказка, а не тип; что внутри на самом деле, скажет file; копилка — ext."""
    id = "file_ext"
    track = "basics"
    title = "Что за файл"
    scroll = ("Расширение — хвост имени после точки (notes.txt, data.csv): подсказка, что "
              "внутри. Finder по нему выбирает, чем открыть, а терминалу всё равно.\n"
              "Расширение — часть имени: при файле notes.txt cat notes ответит No such file.\n"
              "file ИМЯ — что внутри на самом деле: текст, картинка, архив. ext — копилка "
              "встреченных расширений.")
    variants = (
        Variant("Здесь свалены файлы разного сорта. Какой из них — таблица с данными? "
                "Сдай его полное имя, вместе с расширением: ans ИМЯ",
                wrong=("ls *.json",),
                alternatives=("ext — копилка расширений скажет, что .csv — это таблица",)),
        Variant("Нужна записка {stem} — в ней слово. Рядом лежит её старая резервная копия, "
                "слово в ней устарело. Прочти записку и сдай слово: ans СЛОВО",
                hints=("Расширение — часть имени: файла с именем ровно {stem} здесь нет.",
                       "ls покажет полные имена. .bak — резервная копия (что значит "
                       "расширение, подскажет ext).",
                       "ls, затем cat {stem}.txt — и ans СЛОВО"),
                solution="ls && cat {stem}.txt", solution_script="cat {stem}.txt | cut -d: -f2",
                wrong=("cat {stem}.bak | cut -d: -f2",),
                alternatives=("двойной щелчок по слову в выводе cat, Cmd+C, потом ans, пробел "
                              "и Cmd+V — слово не перепечатывать",),
                explain="Расширение — часть имени: cat без .txt ищет файл ровно с таким "
                        "именем и не находит. ls показывает полные имена, а .bak — старая "
                        "копия."),
        Variant("В папке {folder} три файла без расширений: {a}, {b} и {c}. Только один из них "
                "— текст, остальные — картинка и архив. Узнай командой file, какой текстовый, и "
                "сдай слово из него: ans СЛОВО",
                hints=("Без расширения по имени не понять, что внутри, — спроси file.",
                       "file принимает сразу несколько имён: каждому — строка, что внутри.",
                       "cd {folder} && file {a} {b} {c} — потом cat того, где text"),
                solution="cd {folder} && file {a} {b} {c} && cat {text}",
                solution_script="cat {folder}/{text}",
                wrong=("file {folder}/{text}",),
                alternatives=("file {folder}/{a} {folder}/{b} {folder}/{c} — не заходя "
                              "внутрь",),
                explain="Имя ничего не обещает: что внутри, file узнаёт по первым байтам файла. "
                        "cat картинки или архива выдал бы мусор на экран."),
    )
    par = 40
    hints = ("Что значит расширение, подскажет ext; список файлов — ls.",
             ".csv — таблица: строки, поля через запятую.",
             "ls — найди файл .csv и сдай его имя: ans ИМЯ.csv")
    solution = "ls"
    solution_script = "ls *.csv"
    explain = ("Расширение — подсказка, что внутри: .csv — таблица, .json — данные, .jpg — фото, "
               ".zip — архив, .log — журнал. Сдают и открывают файл по полному имени — вместе с "
               "расширением.")
    spell = "file имя — что внутри файла; ext — копилка расширений"
    trap_messages = {
        "old": "Это слово из резервной копии .bak — оно устарело. Нужна сама записка .txt.",
        "stem": "Это имя без расширения, а нужен файл-таблица целиком: имя и расширение.",
        "other": "Это не таблица. Что значит расширение, подскажет ext.",
        # FB6: в варианте с file сдают слово, а не таблицу — «не таблица» сбивало
        "not_text": "Это картинка или архив, а не текст — так сказал бы file. Нужен "
                    "текстовый файл, и сдают слово из него, а не имя.",
        "text_name": "Это имя текстового файла, а нужно слово, что в нём написано: cat {text}.",
    }

    # минимальные файлы, которые file узнаёт по первым байтам
    PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                        "0000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            stem = rng.choice(["plan", "memo", "todo", "brief"])
            word, old = rng.sample(kit.WORDS, 2)
            kit.write(box / f"{stem}.txt", f"Word: {word}\n")
            kit.write(box / f"{stem}.bak", f"Word: {old}\n")
            kit.write(box / "photo.jpg", "not an image, just a placeholder\n")
            return {"stem": stem, "answer": word, "traps": [["old", old]],
                    "sources": sources(box, f"{stem}.txt")}
        if variant == 2:
            import io
            import zipfile
            folder = rng.choice(["drop", "inbox", "found"])
            names = rng.sample(["item1", "item2", "item3", "blob", "piece", "chunk"], 3)
            text, image, archive = names
            word = kit.word(rng)
            kit.write(box / folder / text, f"{word}\n")
            (box / folder / image).write_bytes(self.PNG)
            packed = io.BytesIO()
            with zipfile.ZipFile(packed, "w") as z:
                z.writestr("readme.txt", "empty\n")
            (box / folder / archive).write_bytes(packed.getvalue())
            a, b, c = sorted(names)
            return {"folder": folder, "a": a, "b": b, "c": c, "text": text, "answer": word,
                    "traps": [["not_text", image], ["not_text", archive],
                              ["text_name", text]],
                    "sources": sources(box, f"{folder}/{text}")}
        name = rng.choice(["sales", "clients", "orders", "prices"])
        files = {f"{name}.csv": "id,sum\n1,10\n2,25\n", "notes.txt": "Notes.\n",
                 "readme.md": "# Readme\n", "config.json": '{"debug": false}\n',
                 "server.log": "12:00 start\n", "photo.jpg": "placeholder\n",
                 "backup.zip": "placeholder\n"}
        for fname, body in files.items():
            kit.write(box / fname, body)
        traps = [["stem", name]] + [["other", f] for f in files if not f.endswith(".csv")]
        return {"answer": f"{name}.csv", "traps": traps}


def _keep_check(box: Path, keep, must_move, extra, where=("", "data")) -> Verdict:
    """Не решено: стёрто ли то, что трогать было нельзя (тупик — reset), или поправимо.
    keep — имена, которые должны уцелеть (в корне или в папке where); must_move — то, что
    надо было перенести, а не стереть; extra — лишнее в папке назначения (поправимо)."""
    alive = lambda n: any((box / d / n).exists() for d in where)
    lost = [n for n in keep if not alive(n)]
    if lost:
        return Verdict(False, f"Ты стёр лишнее: {kit.names_line(lost)}. " + kit.RESET_TAIL)
    gone = [n for n in must_move or () if not alive(n)]
    if gone:
        return Verdict(False, f"Стёрто то, что нужно было перенести: {kit.names_line(gone)}. "
                       + kit.RESET_TAIL)
    if extra:
        name = sorted(extra)[0]
        return Verdict(False, f"В {where[-1]}/ попало лишнее: {kit.names_line(extra)} — верни "
                              f"обратно: mv {where[-1]}/{name} .")
    return Verdict(False)


class StarMask(Task):
    id = "star_mask"
    track = "basics"
    title = "Уборка по маске *"
    scroll = ("* в имени — «любые символы»: rm *.tmp удаляет всё, что кончается на .tmp. "
              "Сначала проверь маску безопасно: ls *.tmp\n"
              "rm удаляет сразу и навсегда, мимо Корзины, — поэтому сначала ls с той же маской.")
    variants = (
        Variant("Здесь намусорили. Удали все файлы с окончанием .tmp, но не тронь ни одного "
                "другого — даже если в имени есть tmp.",
                wrong=("rm *tmp*",),
                alternatives=("ls *.tmp && rm *.tmp — сначала посмотреть, кого заденет",)),
        Variant("Черновики больше не нужны: сотри всё, чьё имя начинается с draft_. Файлы, "
                "где draft стоит не в начале или без подчёркивания, остаются.",
                hints=("Маска * работает и в конце: начало имени фиксируешь, хвост — любой.",
                       "Подчёркивание — часть маски: draft_* и draft* ловят разное. Проверь ls.",
                       "ls draft_* — проверить, затем rm draft_*"),
                solution="rm draft_*",
                wrong=("rm draft*", "rm *draft*"),
                alternatives=("ls draft_* && rm draft_* — с проверкой",),
                explain="draft_* держит начало имени вместе с подчёркиванием: draft.md и "
                        "final_draft.txt под маску не попали."),
        Variant("Таблицы переезжают в папку data/. Перенеси туда каждый файл, имя которого "
                "кончается на .csv, — и ни одного сверх того.",
                hints=("Маска с * годится не только для rm, но и для mv.",
                       "Окончание держит конец маски: *.csv. csv в середине имени — не окончание.",
                       "ls *.csv — проверить, затем mv *.csv data/"),
                solution="mv *.csv data/",
                wrong=("mv *csv* data/", "mv *.csv* data/"),
                alternatives=("ls *.csv && mv *.csv data/ — с проверкой",),
                explain="*.csv держит окончание: report.csv.bak и csv_notes.txt под маску не "
                        "попали — у них .csv не в конце."),
    )
    par = 25
    hints = ("Удаляет rm. Перечислять файлы по одному не нужно — есть маска.",
             "Сначала посмотри: ls *.tmp — что попадёт под маску.",
             "rm *.tmp")
    solution = "rm *.tmp"
    explain = "*.tmp совпадает только с именами, которые кончаются на .tmp; tmp_plan.txt не задет."
    spell = "* — любые символы: rm *.tmp, ls *.csv"

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            exts = (".txt", ".md", ".csv")
            hit = [f"draft_{kit.latin(rng)}_{i}{rng.choice(exts)}" for i in range(rng.randint(6, 10))]
            keep = (["final_draft.txt", "draft.md", "redraft_plan.txt", "plan_draft_v2.md"] +
                    [f"entry_{i}.txt" for i in range(rng.randint(3, 6))])
            moved = {}
        elif variant == 2:
            hit = [f"{kit.latin(rng)}_{i}.csv" for i in range(rng.randint(5, 9))]
            keep = (["csv_notes.txt", "report.csv.bak", "old.csv.txt"] +
                    [f"entry_{i}.txt" for i in range(rng.randint(3, 6))])
            (box / "data").mkdir()
            moved = {n: f"data/{n}" for n in hit}
        else:
            hit = [f"{kit.latin(rng)}_{i}.tmp" for i in range(rng.randint(8, 14))]
            keep = ([f"entry_{i}.txt" for i in range(rng.randint(5, 9))] +
                    [f"plan_{i}.md" for i in range(3)] + ["tmp_plan.txt", "notes.tmp.txt"])
            moved = {}
        for n in hit:
            kit.write(box / n, "junk\n" if not moved else f"id\n{n}\n")
        for n in keep:
            kit.write(box / n, "keep\n")
        return {"tmp": hit, "keep": keep, "moved": moved}

    def check(self, ctx):
        b, s = ctx.box, ctx.state
        moved = s.get("moved") or {}
        extra = set()
        if moved:
            data = b / "data"
            inside = {p.name for p in data.iterdir()} if data.is_dir() else set()
            extra = inside - set(moved)
        if (not any((b / n).exists() for n in s["tmp"]) and
                all((b / n).exists() for n in s["keep"]) and
                all((b / rel).is_file() for rel in moved.values()) and not extra):
            return Verdict(True)
        return _keep_check(b, s["keep"], moved and s["tmp"], extra)


class QuestionMask(Task):
    id = "question_mask"
    track = "basics"
    title = "Маска ?"
    scroll = ("? в имени — ровно один любой символ: ls chapter?.txt — это chapter1…chapter9, "
              "но не chapter10.")
    variants = (
        Variant("Здесь файлы chapter1.txt … chapter{n}.txt. Перенеси в part1/ только главы с "
                "однозначным номером — ровно одна цифра после chapter.",
                wrong=("mv chapter*.txt part1/",),
                alternatives=("mv chapter[1-9].txt part1/ — диапазон цифр в скобках",)),
        Variant("Скопируй в short/ все .txt, у которых имя ровно из трёх букв — не короче и "
                "не длиннее. Оригиналы пусть остаются на месте.",
                hints=("Нужна маска, где на каждую букву имени приходится один символ.",
                       "? — один любой символ: три буквы — три вопроса подряд, потом .txt.",
                       "ls ???.txt — проверить, затем cp ???.txt short/"),
                solution="cp ???.txt short/",
                wrong=("cp *.txt short/", "mv ???.txt short/"),
                alternatives=("ls ???.txt && cp ???.txt short/ — с проверкой",),
                explain="Три знака ? — ровно три символа имени: длинные и короткие имена, как "
                        "и не .txt, под маску не попали."),
        Variant("Снимки IMG_ с двузначным номером — дубли, удали их. Четырёхзначные номера "
                "и всё, что не .jpg, не трогай.",
                hints=("Маска должна держать ровно две цифры номера — не больше.",
                       "Два вопроса подряд — ровно два символа. Сначала проверь маску через ls.",
                       "ls IMG_??.jpg — проверить, затем rm IMG_??.jpg"),
                solution="rm IMG_??.jpg",
                wrong=("rm IMG_*.jpg", "rm IMG_??*"),
                alternatives=("ls IMG_??.jpg && rm IMG_??.jpg — с проверкой",),
                explain="IMG_??.jpg — ровно две цифры и окончание .jpg: четырёхзначные номера "
                        "и .png уцелели."),
    )
    par = 30
    hints = ("Нужна маска, где на месте номера ровно один символ.",
             "Такой символ — ?",
             "mv chapter?.txt part1/")
    solution = "mv chapter?.txt part1/"
    explain = "? совпадает ровно с одним символом, поэтому двузначные главы под маску не попали."
    spell = "? — ровно один символ: chapter?.txt"

    THREE = ("dog", "sun", "sea", "map", "pen", "box", "cup", "key", "jam", "owl")
    OTHER = ("book", "plan", "list", "ok", "go", "note", "totals")

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            three = sorted(rng.sample(self.THREE, rng.randint(3, 5)))
            other = rng.sample(self.OTHER, 4)
            for n in three + other:
                kit.write(box / f"{n}.txt", f"{n}\n")
            trap = rng.choice([n for n in self.THREE if n not in three])
            kit.write(box / f"{trap}.md", "not a txt\n")
            (box / "short").mkdir()
            files = [f"{n}.txt" for n in three + other] + [f"{trap}.md"]
            return {"want": [f"{n}.txt" for n in three], "files": files}
        if variant == 2:
            two = sorted({f"IMG_{rng.randint(1, 99):02d}.jpg" for _ in range(rng.randint(4, 8))})
            four = sorted({f"IMG_{rng.randint(1000, 9999)}.jpg" for _ in range(rng.randint(3, 6))})
            keep = four + [f"IMG_{rng.randint(10, 99)}.png", "IMG_notes.txt"]
            for n in two + keep:
                kit.write(box / n, n + "\n")
            return {"gone": two, "keep": keep}
        n = rng.randint(12, 19)
        for i in range(1, n + 1):
            kit.write(box / f"chapter{i}.txt", f"Chapter {i}\n")
        (box / "part1").mkdir()
        return {"n": n}

    def check(self, ctx):
        b, s = ctx.box, ctx.state
        v = s.get("_variant", 0)
        if v == 1:
            short = b / "short"
            inside = {p.name for p in short.iterdir()} if short.is_dir() else set()
            if inside == set(s["want"]) and all((b / f).exists() for f in s["files"]):
                return Verdict(True)
            gone = [f for f in s["files"] if not (b / f).exists()]
            if any(not (short / f).exists() for f in gone):
                return _keep_check(b, gone, (), set(), where=("", "short"))
            if gone:
                return Verdict(False, "Оригиналы переехали в short/, а нужна была копия (cp). "
                                      + kit.RESET_TAIL)
            extra = inside - set(s["want"])
            if extra:       # FB6: cp *.txt — молча не засчитывалось
                name = sorted(extra)[0]
                return Verdict(False, f"В short/ попало лишнее: {kit.names_line(extra)} — "
                                      f"это копии, их можно стереть: rm short/{name}")
            return Verdict(False)
        if v == 2:
            if (not any((b / f).exists() for f in s["gone"]) and
                    all((b / f).exists() for f in s["keep"])):
                return Verdict(True)
            return _keep_check(b, s["keep"], (), set())
        n = s["n"]
        inside = {p.name for p in (b / "part1").iterdir()} if (b / "part1").is_dir() else set()
        if (inside == {f"chapter{i}.txt" for i in range(1, 10)} and
                all((b / f"chapter{i}.txt").exists() for i in range(10, n + 1))):
            return Verdict(True)
        # лишние главы в part1 (mv chapter*.txt) — назвать их и как вернуть (P2 Б10)
        extra = inside - {f"chapter{i}.txt" for i in range(1, 10)}
        return _keep_check(b, [f"chapter{i}.txt" for i in range(1, n + 1)], (), extra,
                           where=("", "part1"))


def _tree(root: Path, rng, n: int) -> List[Path]:
    """Дерево папок глубиной до трёх уровней под root: [root, папка, …]."""
    root.mkdir(parents=True, exist_ok=True)
    dirs = [root]
    for i in range(n):
        parent = rng.choice(dirs)
        if len(parent.relative_to(root).parts) >= 3:
            parent = root
        d = parent / f"{kit.latin(rng)}_{i}"
        d.mkdir()
        dirs.append(d)
    return dirs


def _rel(box: Path, p: Path) -> str:
    return str(p.relative_to(box))


def _copies_check(ctx, dest_name: str = "") -> Verdict:
    """Копии на месте: оригиналы (loc) целы, в папке назначения ровно want {имя: sha}."""
    b, s = ctx.box, ctx.state
    if not all((b / r).is_file() for r in s["loc"]):
        return Verdict(False, "Файлы пропали со своих мест — тут нужна копия (cp), а не "
                              "перенос и не удаление. " + kit.RESET_TAIL)
    d = b / s["dest"]
    have = {p.name: kit.sha(p) for p in d.iterdir() if p.is_file()} if d.is_dir() else {}
    if have == s["want"]:
        return Verdict(True)
    extra = sorted(set(have) - set(s["want"]))
    if extra:
        return Verdict(False, f"В {dest_name or s['dest']} попало лишнее: "
                              f"{kit.names_line(extra)}.")
    missing = sorted(set(s["want"]) - set(have))
    if have and missing:        # FB6: копия неполная — раньше молчали, и игрок не знал почему
        where = {Path(r).name: Path(r).parent.parts for r in s["loc"]}
        hidden = [n for n in missing if any(p.startswith(".") for p in where.get(n, ()))]
        dest = dest_name or s["dest"]
        if hidden == missing:
            return Verdict(False, f"В {dest} не хватает: {kit.names_line(missing)} — лежит в "
                                  "скрытой папке, а ** без (D) скрытые не видит.")
        return Verdict(False, f"В {dest} пока {len(have)} из {len(s['want'])}: нет "
                              f"{kit.names_line(missing)}. Часть лежит глубже — проверь маску "
                              "через ls.")
    return Verdict(False)


class DeepDig(Task):
    """FB4: «искать вглубь» — первая из двух задач на глубину (вторая — deep_rm). * — одна
    папка без скрытых, ** — любая глубина, откуда стартует поиск, ls -R и (D). Вариант 0
    (первая встреча) — только ** (FB12, N10: первая встреча — самый простой вариант); (D)
    требуют повторы 1 и 2; удаление — в deep_rm."""
    id = "deep_dig"
    track = "basics"
    title = "Поиск вглубь"
    scroll = ("* — любые символы, в одной папке, без скрытых; ** — на любой глубине (zsh).\n"
              "ls **/*.log — отсюда вниз (то же ./**/*.log), ls logs/**/*.log — от logs.\n"
              "ls -R — Recursive, всё дерево (папка со всеми вложенными); ls -r — reverse, обратный порядок.\n"
              "(D) — и скрытые: в конце маски, вплотную: ls **/*.log(D). D — Dot (точка); "
              "только большая, (d) — ошибка.")
    variants = (
        Variant("Папка archive — свалка: отчёты *.pdf разбросаны по вложенным папкам. "
                "Скопируй все .pdf в папку collected (она уже есть) — плоско, без подпапок. "
                "Оригиналы пусть остаются на местах.",
                wrong=("cp archive/*.pdf collected/",),
                alternatives=("ls archive/**/*.pdf — сначала увидеть всю добычу, потом "
                              "копировать",
                              "ls -R archive — всё дерево разом, чтобы понять, где что лежит")),
        Variant("Ты стоишь в верхней папке проекта. Скопируй все таблицы .csv — отсюда и со всех "
                "глубин, включая скрытые папки, — в папку ../tables (она уже есть). Путь к "
                "проекту не набирай: поиск начинается там, где стоишь.",
                hints=("Одна * видит только текущую папку. Глубже — **, и начинать маску можно "
                       "прямо с неё: она пойдёт отсюда вниз.",
                       "Скрытые папки ** пропускает, пока после маски не стоит (D). Проверь: "
                       "ls **/*.csv(D)",
                       "ls **/*.csv(D) — проверить, затем cp **/*.csv(D) ../tables/"),
                solution="cp **/*.csv(D) ../tables/",
                wrong=("cp *.csv ../tables/", "cp **/*.csv ../tables/"),
                alternatives=("cp ./**/*.csv(D) ../tables/ — то же: ./ — «здесь», откуда "
                              "начать",),
                explain="Маска без папки впереди начинается там, где стоишь: **/*.csv — "
                        "отсюда вниз, на любую глубину; (D) добавил скрытые папки."),
        Variant("Где-то в глубине папки notes лежит {name} — может быть, и в скрытой папке. "
                "Где именно — неизвестно. Скопируй его сюда, в текущую папку.",
                hints=("Путь неизвестен, а имя — да: ** найдёт файл на любой глубине.",
                       "notes/**/{name} — от папки notes вниз; скрытые — с (D). Проверь ls.",
                       "ls notes/**/{name}(D) — проверить, затем cp notes/**/{name}(D) ."),
                solution="cp notes/**/{name}(D) .",
                wrong=("cp notes/{name} .", "cp notes/**/{name} ."),
                alternatives=("ls -R notes — всё дерево: где лежит файл, видно глазами",),
                explain="Имя известно, путь — нет: notes/**/ИМЯ ищет от папки notes на "
                        "любой глубине, (D) заглядывает и в скрытые папки."),
    )
    par = 50
    hints = ("Отчёты лежат глубоко: всё дерево покажет ls -R archive.",
             "* видит одну папку, ** — любые вложенные: ls archive/**/*.pdf",
             "ls archive/**/*.pdf — проверить, затем cp archive/**/*.pdf collected/")
    solution = "cp archive/**/*.pdf collected/"
    explain = ("* видит одну папку, ** спускается во все вложенные. Маска с папкой впереди "
               "ищет от неё, без папки — от текущей.")
    spell = "**/*.pdf(D) — на любой глубине, со скрытыми (zsh); ls -R — всё дерево"
    start_dir = "{start}"

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            dirs = _tree(box / "app", rng, rng.randint(8, 12))
            want, loc = {}, []
            for i in range(rng.randint(4, 7)):
                name = f"{kit.latin(rng)}_{i}.csv"
                p = kit.write(rng.choice(dirs) / name, f"id,{name}\n{rng.randint(1, 99)},x\n")
                want[name], loc = kit.sha(p), loc + [_rel(box, p)]
            for p in (box / "app" / "main.csv", rng.choice(dirs) / ".cache" / "stats.csv"):
                kit.write(p, f"id,{p.name}\n{rng.randint(1, 99)},x\n")
                want[p.name], loc = kit.sha(p), loc + [_rel(box, p)]
            for i in range(rng.randint(3, 5)):
                kit.write(rng.choice(dirs) / f"{kit.latin(rng)}_{i}"
                          f"{rng.choice(['.csv.old', '.txt', '.md'])}", "not a table\n")
            (box / "tables").mkdir()
            return {"start": "app", "want": want, "dest": "tables", "loc": loc}
        if variant == 2:
            name = rng.choice(["plan_final.txt", "budget_2725.csv", "contacts.txt"])
            dirs = _tree(box / "notes", rng, rng.randint(8, 12))
            hidden = rng.choice(dirs[1:]) / ".old"
            p = kit.write(hidden / name, f"the file you need {rng.random()}\n")
            stem, ext = name.rsplit(".", 1)
            for decoy in (f"{name}.bak", f"{stem}_draft.{ext}"):
                kit.write(rng.choice(dirs) / decoy, "decoy\n")
            for i in range(rng.randint(4, 7)):
                kit.write(rng.choice(dirs) / f"{kit.latin(rng)}_{i}.txt", "note\n")
            return {"start": ".", "name": name, "want": {name: kit.sha(p)}, "dest": ".",
                    "loc": [_rel(box, p)]}
        dirs = _tree(box / "archive", rng, rng.randint(10, 14))
        want, loc = {}, []
        for i in range(rng.randint(5, 8)):
            name = f"{kit.latin(rng)}_{i}.pdf"
            p = kit.write(rng.choice(dirs[1:]) / name, f"report {name} {rng.random()}\n")
            want[name], loc = kit.sha(p), loc + [_rel(box, p)]
        for i in range(rng.randint(3, 5)):
            kit.write(rng.choice(dirs) / f"{kit.latin(rng)}_{i}{rng.choice(['.pdf.part', '.txt'])}",
                      "not a report\n")
        (box / "collected").mkdir()
        return {"start": ".", "want": want, "dest": "collected", "loc": loc}

    def check(self, ctx):
        if ctx.state["dest"] != ".":
            return _copies_check(ctx)
        b, s = ctx.box, ctx.state
        if not all((b / r).is_file() for r in s["loc"]):
            return Verdict(False, "Файл пропал со своего места — тут нужна копия (cp), а не "
                                  "перенос и не удаление. " + kit.RESET_TAIL)
        name = s["name"]
        return Verdict((b / name).is_file() and kit.sha(b / name) == s["want"][name])


class DeepRm(Task):
    """FB4: «удалять вглубь» — сразу после deep_dig. rm с маской на любой глубине, rm -r —
    папка целиком; привычка «сначала ls той же маской». Вариант 0 (первая встреча, FB12 N10)
    — один приём: rm по маске **(D); оба приёма стража сразу (маска и rm -r) — вариант 1."""
    id = "deep_rm"
    track = "basics"
    title = "Удаление вглубь"
    scroll = ("rm понимает те же маски: rm **/*.bak(D) — все .bak отсюда и глубже, вместе со "
              "скрытыми папками.\n"
              "Папку голый rm не удаляет. rm -r папка — папку со всем содержимым: -r — "
              "recursive (рекурсивно, вглубь). Навсегда, мимо Корзины.\n"
              "Привычка: сначала ls с той же маской (или ls -R папка) — посмотреть, что "
              "исчезнет, — и только потом rm.")
    variants = (
        Variant("Ты стоишь в папке сборки. Сотри все файлы *.tmp — отсюда и на любой глубине, "
                "в том числе в скрытых папках. Всё остальное не трогай.",
                wrong=("rm *.tmp", "rm **/*.tmp"),
                alternatives=("ls **/*.tmp(D) && rm **/*.tmp(D) — с проверкой",)),
        Variant("В проекте project на любой глубине валяются временные файлы *.tmp — есть "
                "они и в скрытых папках. Сотри их все, остальное в project не трогай. А "
                "папку trash рядом удали целиком, со всем, что внутри.",
                hints=("Временные файлы на всех уровнях: ** — любая глубина, (D) — и скрытые "
                       "папки.",
                       "Папку целиком удаляет rm с флагом -r. Сначала проверь: "
                       "ls project/**/*.tmp(D)",
                       "ls project/**/*.tmp(D) — проверить, затем rm project/**/*.tmp(D) && "
                       "rm -r trash"),
                solution="rm project/**/*.tmp(D) && rm -r trash",
                wrong=("rm project/**/*.tmp && rm -r trash",
                       "rm project/**/*.tmp(D) && rm trash/*(D)"),
                alternatives=("ls project/**/*.tmp(D) && rm project/**/*.tmp(D) — сначала "
                              "посмотреть, кого заденет",
                              "ls -R trash — что исчезнет вместе с папкой"),
                explain="rm берёт те же маски, что ls: **/*.tmp(D) — на любой глубине, со "
                        "скрытыми. rm -r удаляет папку со всем, что внутри. Сначала ls той "
                        "же маской."),
        Variant("Папка old — старый проект: внутри вложенные папки и скрытые файлы. Снеси её "
                "целиком одной командой. Соседнюю new не трогай.",
                hints=("Голый rm папку не удаляет — ему нужен флаг.",
                       "-r — со всем содержимым, на любую глубину. Сначала посмотри, что "
                       "исчезнет: ls -R old",
                       "ls -R old — проверить, затем rm -r old"),
                solution="rm -r old",
                wrong=("rm old/*", "rm -r old/*"),
                alternatives=("ls -laR old && rm -r old — сначала посмотреть всё, со "
                              "скрытым",)),
    )
    par = 50
    hints = ("Маска без папки впереди ищет там, где стоишь; ** — на любой глубине.",
             "Скрытые папки ** пропускает, пока после маски не стоит (D). "
             "Сначала посмотри: ls **/*.tmp(D)",
             "ls **/*.tmp(D) — проверить, затем rm **/*.tmp(D)")
    solution = "rm **/*.tmp(D)"
    explain = ("rm берёт те же маски, что ls: **/*.tmp(D) — отсюда на любой глубине, со "
               "скрытыми папками. Сначала ls той же маской — потом rm.")
    spell = "rm **/*.tmp(D) — удалить по маске вглубь; rm -r папка — папку целиком"
    start_dir = "{start}"

    def setup_variant(self, box, rng, variant):
        if variant == 2:
            dirs = _tree(box / "old", rng, rng.randint(4, 7))
            for i in range(rng.randint(6, 10)):
                kit.write(rng.choice(dirs) / f"{kit.latin(rng)}_{i}.txt", "old stuff\n")
            kit.write(rng.choice(dirs) / ".env", "old stuff\n")
            keep = [kit.write(box / "new" / f"{kit.latin(rng)}_{i}.txt", "new\n")
                    for i in range(rng.randint(3, 5))]
            return {"start": ".", "gone": ["old"], "keep": [_rel(box, p) for p in keep]}
        root = "build" if variant == 0 else "project"
        dirs = _tree(box / root, rng, rng.randint(8, 12))
        hidden = rng.choice(dirs) / ".cache"
        gone = [kit.write(rng.choice(dirs[1:]) / f"{kit.latin(rng)}_{i}.tmp", "junk\n")
                for i in range(rng.randint(5, 8))]
        gone += [kit.write(box / root / "session.tmp", "junk\n"),
                 kit.write(hidden / f"{kit.latin(rng)}.tmp", "junk\n")]
        keep = [kit.write(rng.choice(dirs) / f"{kit.latin(rng)}_{i}.txt", "keep\n")
                for i in range(rng.randint(5, 8))]
        keep += [kit.write(rng.choice(dirs) / "tmp_notes.md", "keep\n"),
                 kit.write(rng.choice(dirs) / "plan.tmp.bak", "keep\n"),
                 kit.write(hidden / "index.db", "keep\n")]
        gone = [_rel(box, p) for p in gone]
        if variant == 1:
            tdirs = _tree(box / "trash", rng, rng.randint(2, 4))
            for i in range(rng.randint(3, 6)):
                kit.write(rng.choice(tdirs) / f"{kit.latin(rng)}_{i}.txt", "clutter\n")
            kit.write(box / "trash" / ".leftover", "clutter\n")
            gone.append("trash")
        return {"start": "build" if variant == 0 else ".", "gone": gone,
                "keep": [_rel(box, p) for p in keep]}

    def check(self, ctx):
        b, s = ctx.box, ctx.state
        lost = [r for r in s["keep"] if not (b / r).exists()]
        if lost:
            return Verdict(False, "Ты стёр лишнее: " + kit.names_line(Path(r).name for r in lost)
                           + ". " + kit.RESET_TAIL)
        left = [r for r in s["gone"] if (b / r).exists()]
        if not left:
            return Verdict(True)
        if len(left) == len(s["gone"]):
            return Verdict(False)       # ещё ничего не удалено — молчим
        # FB6: удалил не всё — раньше молчали, и игрок не понимал, чего не хватает
        dirs = [r for r in left if (b / r).is_dir()]
        if dirs:
            return Verdict(False, f"Папка {dirs[0]} ещё на месте: голый rm и маски папку не "
                                  f"удаляют — нужен rm -r {dirs[0]}")
        if all(any(p.startswith(".") for p in Path(r).parent.parts) for r in left):
            return Verdict(False, f"Осталось в скрытых папках: "
                                  f"{kit.names_line(Path(r).name for r in left)} — ** без (D) "
                                  "их не видит.")
        return Verdict(False, f"Осталось ещё: {kit.names_line(Path(r).name for r in left)} — "
                              "глубже, чем достала маска. Проверь её через ls.")


# --- FB4: уроки навигации по терминалу (временно — сразу после deep_rm) -------------------
# Проверка, как у всех задач, — по результату (файлы, ответ), а не по нажатым клавишам: без
# приёма задачу решить можно, но неудобно (длинная строка из истории с правкой).

FILLER = ("ls", "pwd", "ls -la", "cd ..", "cd -", "cat readme.txt", "ls *.txt", "cd ~",
          "mkdir -p drafts", "ls drafts", "cat notes.txt", "cd drafts", "cd ..", "ls -R",
          "pwd", "ls *.md", "cat todo.txt", "ls -A", "cd -", "ls")


def _history(box, lines) -> None:
    """Заготовленная история песочницы: песочный .zshrc читает .termit/history (fc -R) при
    старте zsh. Последняя строка — самая свежая (её вернёт ↑ и повторит !!)."""
    sandbox.write_box_file(box, ".termit/history", "".join(f"{x}\n" for x in lines))


def _files_check(ctx) -> Verdict:
    """want {путь: sha} — файлы на месте; dirs — папки есть; stay — эти пути не ушли."""
    b, s = ctx.box, ctx.state
    stay = [r for r in s.get("stay", ()) if not (b / r).is_file()]
    if stay:
        name = Path(stay[0]).name
        moved = next((p for p in b.rglob(name) if p.is_file()), None)
        back = f" Верни: mv {_rel(b, moved)} {Path(stay[0]).parent}/" if moved else ""
        return Verdict(False, f"{name} должен был остаться на месте.{back}")
    if kit.lost(b, s.get("want", {}).values()):
        return Verdict(False, "Нужный файл стёрт или испорчен — его текста больше нет ни в "
                              "одном файле. " + kit.RESET_TAIL)
    files = all((b / r).is_file() and kit.sha(b / r) == h for r, h in s.get("want", {}).items())
    dirs = all((b / d).is_dir() for d in s.get("dirs", ()))
    return Verdict(files and dirs)


class LineEdit(Task):
    """FB4: строка ввода — ↑, Ctrl+A/E, Option+← →, Ctrl+W/K/U, Tab. Длинная команда из
    истории с ошибкой в начале, в конце или в середине: исправить, а не перепечатать."""
    id = "line_edit"
    track = "basics"
    title = "Правка строки"
    scroll = ("↑ — прошлая команда. Ctrl+A / Ctrl+E — в начало / в конец строки, Option+← → "
              "— через слово (вне игры — если в iTerm2 стоит пресет Natural Text Editing или "
              "Option как Esc+).\n"
              "Ctrl+W — стереть слово слева (W — Word), Ctrl+K — до конца строки (K — Kill, "
              "вырезать: Ctrl+Y вставит обратно), Ctrl+U — всю строку (в zsh; в bash — до "
              "курсора). Tab — дописать имя.")
    variants = (
        Variant("Последнюю команду в истории набрали с опечаткой в самом начале — mkdri "
                "вместо mkdir, и она не сработала. Не перепечатывай: ↑ вернёт строку, Ctrl+A "
                "прыгнет в её начало. Исправь опечатку и нажми Enter.",
                wrong=("mkdir -p archive/{year}/reports/q1",),
                alternatives=("Ctrl+A, Option+→ — курсор за первым словом; Ctrl+W сотрёт его, "
                              "остаётся набрать mkdir",)),
        Variant("Последняя команда в истории копирует три отчёта в папку shared/, но такой "
                "папки нет — нужна outbox/ (она уже есть). Верни строку стрелкой ↑, сотри "
                "последнее слово Ctrl+W, допиши outbox/ и нажми Enter.",
                hints=("Строка уже набрана — она в истории: ↑ вернёт её целиком.",
                       "Курсор после ↑ стоит в конце: Ctrl+W стирает слово слева от него. "
                       "Стёрлось не всё — нажми ещё раз.",
                       "↑, Ctrl+W, допиши outbox/ и Enter"),
                solution="↑, Ctrl+W, допиши outbox/, Enter",
                solution_script=("cp reports/{year}/summary.txt reports/{year}/figures.csv "
                                 "reports/{year}/notes.txt outbox/"),
                wrong=("cp reports/{year}/summary.txt outbox/",),
                alternatives=("↑, Option+← — к началу shared/, Ctrl+K сотрёт хвост, допиши "
                              "outbox/",)),
        Variant("Последняя команда в истории переносит в archive/ четыре файла, но фото "
                "{photo} должно остаться в inbox. Достань строку (↑), доберись до фото "
                "прыжками Option+←, сотри его Ctrl+W и нажми Enter.",
                hints=("Строка — в истории: ↑. Перепечатывать её не нужно.",
                       "Option+← прыгает через слово влево. Встань сразу за именем фото — "
                       "Ctrl+W сотрёт его.",
                       "↑, Option+← дважды, Ctrl+W, Enter"),
                solution="↑, Option+← дважды, Ctrl+W, Enter",
                solution_script=("mv inbox/report_{year}.txt inbox/budget_{year}.csv "
                                 "inbox/contacts.txt archive/"),
                wrong=("mv inbox/report_{year}.txt inbox/budget_{year}.csv inbox/{photo} "
                       "inbox/contacts.txt archive/",),
                alternatives=("набрать строку заново без фото — тоже верно, но долго",)),
    )
    par = 40
    hints = ("Строка уже набрана — она в истории: ↑ вернёт её целиком.",
             "Опечатка в самом начале: Ctrl+A прыгает в начало строки, там исправь.",
             "↑, Ctrl+A, исправь mkdri на mkdir и Enter")
    solution = "↑, Ctrl+A, исправь mkdri на mkdir, Enter"
    solution_script = ("mkdir -p archive/{year}/reports/q1 archive/{year}/reports/q2 "
                       "archive/{year}/reports/q3 archive/{year}/reports/q4")
    explain = ("Длинную строку не перепечатывают: ↑ возвращает её, Ctrl+A и Ctrl+E — в начало "
               "и конец, Option+← → — через слово, Ctrl+W стирает слово слева.")
    spell = "↑ — прошлая команда; Ctrl+A/E — начало/End; Ctrl+W — Word; Option+← → — прыжок"

    def setup_variant(self, box, rng, variant):
        year = str(rng.randint(2724, 2726))
        fill = list(rng.sample(FILLER, 8))
        if variant == 1:
            want = {}
            for name in ("summary.txt", "figures.csv", "notes.txt"):
                f = kit.write(box / "reports" / year / name, f"{name}: {kit.word(rng)}\n")
                want[f"reports/{year}/{name}"] = want[f"outbox/{name}"] = kit.sha(f)
            (box / "outbox").mkdir()
            _history(box, fill + [f"cp reports/{year}/summary.txt reports/{year}/figures.csv "
                                  f"reports/{year}/notes.txt shared/"])
            return {"year": year, "want": want}
        if variant == 2:
            photo = f"photo_{year}.jpg"
            names = (f"report_{year}.txt", f"budget_{year}.csv", photo, "contacts.txt")
            want = {}
            for name in names:
                f = kit.write(box / "inbox" / name, f"{name}: {kit.word(rng)}\n")
                where = "inbox" if name == photo else "archive"
                want[f"{where}/{name}"] = kit.sha(f)
            (box / "archive").mkdir()
            _history(box, fill + ["mv " + " ".join(f"inbox/{n}" for n in names) + " archive/"])
            return {"year": year, "photo": photo, "want": want, "stay": [f"inbox/{photo}"]}
        dirs = [f"archive/{year}/reports/q{i}" for i in range(1, 5)]
        _history(box, fill + ["mkdri -p " + " ".join(dirs)])
        return {"year": year, "dirs": dirs}

    def check(self, ctx):
        return _files_check(ctx)


class CursorClip(Task):
    """FB13 (FB5 п. 47): курсор и буфер — «курсор ведёт себя не как в Ворде». Строка ввода и
    вывод — разные зоны: курсор живёт только в строке, Option+клик ставит его туда (вариант 0);
    Ctrl+W/U/K кладут вырезанное в карман zsh, Ctrl+Y вставляет, Esc y — вырезанное раньше
    (вариант 1); | pbcopy — вывод в буфер обмена (вариант 2: в песочнице учебный pbcopy пишет в
    .termit/clipboard, буфер владельца не трогаем). Проверка — по результату."""
    id = "cursor_clip"
    track = "basics"
    title = "Курсор и буфер"
    uses_clip_stub = True
    scroll = ("Курсор — только в строке ввода: Option+клик ставит его туда (iTerm2: галочка "
              "Option-Click moves cursor).\n"
              "Мышью: двойной клик — слово, тройной — строка, Cmd+C и Cmd+V; Cmd+Shift+A — "
              "вывод последней команды.\n"
              "Ctrl+W/U/K — в карман zsh, Ctrl+Y — вставить, Esc y — то, что раньше (не буфер "
              "обмена Mac). | pbcopy — в буфер, pbpaste — обратно.")
    variants = (
        Variant("Последняя команда в истории копирует в outbox/ три черновика, но в середине "
                "строки опечатка: invoce вместо invoice. Верни строку (↑), поставь курсор "
                "прямо в опечатку Option+кликом, исправь и нажми Enter.",
                wrong=("cp drafts/{year}/contract_final.txt outbox/",),
                alternatives=("↑ и Option+← прыжками до опечатки — тоже верно",)),
        Variant("Последняя команда в истории переносит отчёт в outbox/, но слова перепутаны: "
                "сначала папка, потом файл. Переставь их через карман zsh: ↑, Ctrl+W — вырезать "
                "имя файла, Option+← — к началу outbox/, Ctrl+Y — вставить, пробел, Enter.",
                hints=("Строка — в истории: ↑. Порядок у mv такой: что переносим, потом куда.",
                       "Ctrl+W вырезает слово слева и кладёт его в карман zsh; Ctrl+Y вставляет "
                       "его там, где курсор.",
                       "↑, Ctrl+W, Option+←, Ctrl+Y, пробел, Enter"),
                solution="↑, Ctrl+W, Option+←, Ctrl+Y, пробел, Enter",
                solution_script="mv report_{year}.txt outbox/",
                wrong=("mv outbox/ report_{year}.txt",),
                alternatives=("набрать mv report_{year}.txt outbox/ заново — верно, но "
                              "дольше",)),
        Variant("Коллега просит список таблиц — имена всех файлов .csv в этой папке. Отправь "
                "их в буфер обмена, не выделяя мышью: ls *.csv | pbcopy. Проверить, что "
                "легло, — pbpaste.",
                hints=("| передаёт вывод одной команды на вход другой.",
                       "pbcopy забирает свой вход в буфер обмена. Нужны только .csv — маска "
                       "*.csv.",
                       "ls *.csv | pbcopy"),
                solution="ls *.csv | pbcopy",
                solution_script="ls *.csv | pbcopy",
                wrong=("ls | pbcopy",),
                alternatives=("ls -1 *.csv | pbcopy — то же, по одному имени в строке",)),
    )
    par = 40
    hints = ("Строка уже набрана — она в истории: ↑ вернёт её целиком.",
             "Мышь в строке ввода работает с Option: зажми Option и кликни по опечатке — "
             "курсор встанет туда.",
             "↑, Option+клик по invoce, допиши i после «invo», Enter")
    solution = "↑, Option+клик по опечатке, исправь invoce на invoice, Enter"
    solution_script = ("cp drafts/{year}/contract_final.txt drafts/{year}/invoice_final.txt "
                       "drafts/{year}/letter_final.txt outbox/")
    explain = ("Терминал — не Ворд: курсор только в строке ввода, Option+клик ставит его туда. "
               "Вырезанное Ctrl+W/U/K лежит в кармане zsh (Ctrl+Y), а буфер Mac — Cmd+C, "
               "Cmd+V и | pbcopy.")
    spell = ("Option+клик — курсор в строку; Ctrl+Y — Yank, вставить вырезанное; "
             "pbcopy — pasteboard copy, в буфер")

    def setup_variant(self, box, rng, variant):
        year = str(rng.randint(2724, 2726))
        fill = list(rng.sample(FILLER, 8))
        if variant == 1:
            f = kit.write(box / f"report_{year}.txt", f"report {year}: {kit.word(rng)}\n")
            (box / "outbox").mkdir()
            _history(box, fill + [f"mv outbox/ report_{year}.txt"])
            return {"year": year, "want": {f"outbox/report_{year}.txt": kit.sha(f)}}
        if variant == 2:
            tables = sorted(rng.sample(("customers", "orders", "payments", "products",
                                        "regions", "returns", "stores"), 4))
            for name in tables:
                kit.write(box / f"{name}.csv", f"id,{name}\n1,{kit.word(rng)}\n")
            kit.write(box / "readme.txt", "Tables for the weekly report.\n")
            kit.write(box / "notes.md", f"# Notes\n{kit.word(rng)}\n")
            return {"year": year, "csv": [f"{name}.csv" for name in tables]}
        want = {}
        (box / "outbox").mkdir()
        for name in ("contract_final.txt", "invoice_final.txt", "letter_final.txt"):
            f = kit.write(box / "drafts" / year / name, f"{name}: {kit.word(rng)}\n")
            want[f"outbox/{name}"] = kit.sha(f)
        _history(box, fill + [f"cp drafts/{year}/contract_final.txt "
                              f"drafts/{year}/invoce_final.txt "
                              f"drafts/{year}/letter_final.txt outbox/"])
        return {"year": year, "want": want}

    def check(self, ctx):
        csv = ctx.state.get("csv")
        if csv is None:
            return _files_check(ctx)
        got = sandbox._read(ctx.box, "clipboard")
        if got is None:
            return Verdict(False)
        names = [x.strip() for x in got.splitlines() if x.strip()]
        extra = [x for x in names if x not in csv]
        if extra:
            return Verdict(False, f"В буфере лишнее: {extra[0]}. Нужны только имена .csv — "
                                  "маска *.csv после ls.")
        if sorted(set(names)) != sorted(csv):
            return Verdict(False, "В буфере не все таблицы. ls *.csv | pbcopy положит "
                                  "все сразу.")
        return Verdict(True)


class HistoryRecall(Task):
    """FB4: история — Ctrl+R (поиск), history и !N, !!. В истории песочницы — заготовленная
    длинная команда: достать, поправить и выполнить."""
    id = "history_recall"
    track = "basics"
    title = "Поиск в истории"
    scroll = ("↑ ↓ — прошлые команды. Ctrl+R и кусок — поиск: ещё Ctrl+R — постарше; Enter — "
              "выполнить, ← или → — поправить, Ctrl+G — отмена.\n"
              "history — свежие с номерами, вся — history 1; !N — команда номер N: !42.\n"
              "!! — последняя команда целиком: набери !! и Enter — zsh покажет подстановку и "
              "выполнит. Без папки: mkdir -p папка && !! — папка, потом та команда.")
    variants = (
        Variant("Когда-то ты уже копировал три шаблона из templates в папку клиента {old}: "
                "команда лежит в истории. Теперь те же шаблоны нужны клиенту {new} — папка "
                "clients/{new} уже есть. Найди ту команду Ctrl+R (набери кусок, например "
                "templates), поправь конец и выполни.",
                wrong=("cp templates/invoice_base.txt clients/{new}/",),
                alternatives=("history — найти строку глазами и !N по её номеру; потом ↑ и "
                              "поправить конец",)),
        Variant("Последняя команда в истории копирует отчёты в shared/{month}/, но этой папки "
                "ещё нет — команда упала. Создай папку и повтори ту команду, не "
                "перепечатывая: !! — последняя команда истории.",
                hints=("Папку с вложенной создаёт mkdir -p.",
                       "!! подставит последнюю команду истории — даже в той же строке, после "
                       "&&. Уже что-то набрал — тогда ↑ ↑ найдёт её.",
                       "mkdir -p shared/{month} && !!"),
                solution="mkdir -p shared/{month} && !!",
                solution_script=("mkdir -p shared/{month} && cp reports/summary.txt "
                                 "reports/figures.csv reports/notes.txt shared/{month}/"),
                wrong=("mkdir -p shared/{month}",),
                alternatives=("mkdir -p shared/{month}, затем ↑ ↑ и Enter — та же команда "
                              "стрелкой",)),
        Variant("В истории есть команда, которая переносила снимки — IMG_*.jpg и скриншоты "
                ".png — из downloads в photos. Сегодня снимков снова набежало. Найди её номер "
                "командой history и запусти по номеру: !N.",
                hints=("history печатает свежие команды, у каждой — номер слева; всю историю — history 1.",
                       "Нужна строка, где mv переносит в photos/. !N выполнит команду номер N.",
                       "history, найди строку с photos/ и набери ! и её номер"),
                solution="history, затем !N",
                solution_script="mv downloads/IMG_*.jpg downloads/screenshot_*.png photos/",
                wrong=("mv downloads/*.pdf downloads/*.docx documents/",),
                alternatives=("Ctrl+R и photos — тот же поиск, без номеров",)),
    )
    par = 40
    hints = ("Команда уже есть в истории — набирать её заново не нужно.",
             "Ctrl+R и кусок команды (templates) найдут её; → — поправить, а не выполнить "
             "сразу.",
             "Ctrl+R и набери кусок templates, затем →, Ctrl+W, допиши clients/{new}/ и Enter")
    solution = "Ctrl+R и кусок templates, стрелка →, Ctrl+W, допиши clients/{new}/, Enter"
    solution_script = ("cp templates/invoice_base.txt templates/letter_base.txt "
                       "templates/report_base.txt clients/{new}/")
    explain = ("История помнит всё: Ctrl+R ищет по куску, history показывает номера (!N), "
               "!! повторяет последнюю команду.")
    spell = "Ctrl+R — Reverse, поиск по истории; history — список, !N — номер; !! — повторить"

    CLIENTS = ("atlas", "orbit", "nova", "delta", "vertex")

    def setup_variant(self, box, rng, variant):
        fill = list(rng.sample(FILLER, 12))
        if variant == 1:
            month = rng.choice(PICK_MONTHS)
            want = {}
            for name in ("summary.txt", "figures.csv", "notes.txt"):
                f = kit.write(box / "reports" / name, f"{name}: {kit.word(rng)}\n")
                want[f"reports/{name}"] = want[f"shared/{month}/{name}"] = kit.sha(f)
            _history(box, fill + ["cp reports/summary.txt reports/figures.csv "
                                  f"reports/notes.txt shared/{month}/"])
            return {"month": month, "want": want}
        if variant == 2:
            want = {}
            for i in range(rng.randint(3, 5)):
                for name in (f"IMG_{rng.randint(1000, 9999)}_{i}.jpg", f"screenshot_{i}.png"):
                    f = kit.write(box / "downloads" / name, f"shot {name} {rng.random()}\n")
                    want[f"photos/{name}"] = kit.sha(f)
            stay = []
            for name in ("invoice.pdf", "contract.docx", "backup.zip", "IMG_notes.txt"):
                f = kit.write(box / "downloads" / name, f"{name} {rng.random()}\n")
                want[f"downloads/{name}"] = kit.sha(f)
                stay.append(f"downloads/{name}")
            for d in ("photos", "documents", "archives"):
                (box / d).mkdir()
            mid = len(fill) // 2
            lines = (fill[:mid] + ["mv downloads/*.pdf downloads/*.docx documents/",
                                   "mv downloads/IMG_*.jpg downloads/screenshot_*.png photos/",
                                   "mv downloads/*.zip archives/"] + fill[mid:])
            _history(box, lines)
            return {"want": want, "stay": stay}
        old, new = rng.sample(self.CLIENTS, 2)
        want = {}
        names = ("invoice_base.txt", "letter_base.txt", "report_base.txt")
        for name in names:
            f = kit.write(box / "templates" / name, f"{name}: {kit.word(rng)}\n")
            kit.write(box / "clients" / old / name, f"{name}: old copy\n")
            want[f"templates/{name}"] = want[f"clients/{new}/{name}"] = kit.sha(f)
        (box / "clients" / new).mkdir(parents=True)
        mid = len(fill) // 2
        line = "cp " + " ".join(f"templates/{n}" for n in names) + f" clients/{old}/"
        _history(box, fill[:mid] + [line] + fill[mid:])
        return {"old": old, "new": new, "want": want}

    def check(self, ctx):
        return _files_check(ctx)


class ScreenScroll(AnswerTask):
    """FB4: экран — прокрутка вывода (колесо, Cmd+↑ ↓, Shift+fn+↑ ↓, Cmd+fn+← →, Cmd+Shift+↑)
    и очистка (clear, Ctrl+L, Cmd+K). Ответ — в той части вывода, что убежала за край окна."""
    id = "screen_scroll"
    track = "basics"
    title = "Прокрутка вывода"
    scroll = ("Вывод уехал вверх — колесо мыши или два пальца по трекпаду. iTerm2: Cmd+↑ ↓ "
              "— по строке, Shift+fn+↑ ↓ — по странице, Cmd+fn+← → — в начало и конец, "
              "Cmd+Shift+↑ — к прошлой команде (с интеграцией iTerm2).\n"
              "Голые fn+↑ ↓ (Page Up/Down) iTerm2 отдаёт программе — окно не крутится.\n"
              "Очистить экран — clear, Ctrl+L или Cmd+K. L — от «form feed», «новый лист»: "
              "так в ASCII звали прогон бумаги у принтеров.")
    variants = (
        Variant("Журнал journal.txt длинный: cat вывалит его, и начало убежит за край окна. "
                "Слово дня (строка Today's word) — в самой первой строке. Выведи журнал "
                "командой cat, прокрути к началу и сдай слово: ans СЛОВО",
                wrong=("echo {old}",),
                alternatives=("cat journal.txt, затем Cmd+fn+← — сразу в самое начало "
                              "вывода",)),
        Variant("Выведи по очереди два длинных файла: cat part1.txt, затем cat part2.txt. "
                "Нужное слово — в последней строке первого файла: после второй команды оно "
                "уедет далеко вверх. Прокрути к нему и сдай: ans СЛОВО",
                hints=("Слово — в конце первого вывода, над второй командой.",
                       "Cmd+Shift+↑ прыгает к прошлой команде (с интеграцией iTerm2); без неё "
                       "— Shift+fn+↑ по страницам.",
                       "cat part1.txt, cat part2.txt, прокрути вверх до строки над cat "
                       "part2.txt — ans СЛОВО"),
                solution="cat part1.txt && cat part2.txt",
                solution_script="tail -n 1 part1.txt | cut -d' ' -f2",
                wrong=("echo {old}",),
                alternatives=("cat part1.txt — одного первого файла хватит: слово в конце, "
                              "прямо над приглашением",)),
        Variant("Где-то в середине длинного отчёта report.txt есть строка «Tag: …» (метка). "
                "Выведи отчёт командой cat и листай вверх страницами, пока не найдёшь. Сдай "
                "слово после метки: ans СЛОВО",
                hints=("Вывод длиннее окна — его прокручивают вверх.",
                       "Shift+fn+↑ — страница вверх, Shift+fn+↓ — вниз; колесо мыши тоже "
                       "годится.",
                       "cat report.txt, затем Shift+fn+↑ до строки «Tag:» — ans СЛОВО"),
                solution="cat report.txt",
                solution_script="grep 'Tag:' report.txt | cut -d' ' -f2",
                wrong=("echo {old}",),
                alternatives=("cat report.txt, затем Cmd+F в iTerm2 — поиск по экрану",)),
    )
    par = 40
    hints = ("Вывод длиннее окна — начало уехало вверх, его можно прокрутить.",
             "Колесо мыши, Cmd+↑ — по строке, Shift+fn+↑ — по странице, Cmd+fn+← — в самое "
             "начало.",
             "cat journal.txt, затем Cmd+fn+← — первая строка, ans СЛОВО")
    solution = "cat journal.txt"
    solution_script = "head -n 1 journal.txt | cut -d' ' -f3"
    explain = ("Вывод не пропадает, он уезжает вверх: колесо, Cmd+↑ ↓, Shift+fn+↑ ↓ и "
               "Cmd+fn+← → возвращают его. Нашёл командой — тоже честно; "
               "прокрутка — когда вывод уже на экране и повторять команду дорого.")
    spell = "Cmd+↑ ↓, Shift+fn+↑ ↓ — прокрутка; Cmd+fn+← — в начало; clear — очистить экран"
    trap_messages = {"old": "Это слово из другой строки — нужное записано там, где сказано в "
                            "задании. Прокрути вывод."}

    def setup_variant(self, box, rng, variant):
        word, old = rng.sample(kit.WORDS, 2)

        def lines(n, tag):
            return [f"{tag} {i}: ok" for i in range(1, n + 1)]

        if variant == 1:
            kit.write(box / "part1.txt", "\n".join(lines(rng.randint(250, 320), "line")
                                                   + [f"Word: {word}"]) + "\n")
            kit.write(box / "part2.txt", "\n".join(lines(rng.randint(250, 320), "entry")
                                                   + [f"Word: {old}"]) + "\n")
            return {"answer": word, "old": old, "traps": [["old", old]],
                    "sources": sources(box, "part1.txt")}
        if variant == 2:
            body = lines(rng.randint(400, 480), "item")
            body.insert(rng.randint(150, 250), f"Tag: {word}")
            body.append(f"Total: {old}")
            kit.write(box / "report.txt", "\n".join(body) + "\n")
            return {"answer": word, "old": old, "traps": [["old", old]],
                    "sources": sources(box, "report.txt")}
        body = ([f"Today's word: {word}"] + lines(rng.randint(350, 420), "entry")
                + [f"Yesterday's word: {old}"])
        kit.write(box / "journal.txt", "\n".join(body) + "\n")
        return {"answer": word, "old": old, "traps": [["old", old]],
                "sources": sources(box, "journal.txt")}


class ScreenFind(AnswerTask):
    """FB10 (лайфхаки): поиск по экрану iTerm2 — Cmd+F, метки Cmd+Shift+↑ ↓ (прыжок от
    команды к команде), Cmd+Shift+A (вывод последней команды); панели Cmd+D — в уроке.
    Ответ виден только в выводе: проверка — по сданному слову, как у screen_scroll."""
    id = "screen_find"
    track = "basics"
    title = "Поиск по экрану"
    scroll = ("Cmd+F — поиск по выводу, и по уехавшему вверх: Enter или Cmd+G — следующее "
              "совпадение, Esc — закрыть.\n"
              "Cmd+Shift+↑ ↓ — от команды к команде (метки iTerm2; меню iTerm2, Install Shell "
              "Integration). В Terminal.app — Cmd+↑ ↓.\n"
              "Cmd+Shift+A — выделить вывод последней команды. Cmd+D — вторая панель рядом, "
              "Cmd+W — закрыть.")
    variants = (
        Variant("Склад выдал опись stock.txt на сотни строк. Где-то в середине одна строка "
                "помечена словом MISSING (пропуск). Выведи опись командой cat, найди метку поиском "
                "Cmd+F и сдай слово, что стоит после неё: ans СЛОВО",
                wrong=("echo {old}",),
                alternatives=("cat stock.txt, затем Cmd+F и MISSING — Enter прыгает к "
                              "совпадению",)),
        Variant("Выведи три журнала по очереди: cat day1.txt, cat day2.txt, cat day3.txt. "
                "Слово дня (Today's word) — в первой строке второго журнала. После третьей "
                "команды оно уедет далеко вверх: прыгай к началу вывода day2.txt метками "
                "Cmd+Shift+↑ и сдай его: ans СЛОВО",
                hints=("Слово — сразу под командой cat day2.txt.",
                       "Cmd+Shift+↑ прыгает к прошлой команде (с интеграцией iTerm2); без неё — "
                       "Cmd+F и day2.txt.",
                       "cat day1.txt, cat day2.txt, cat day3.txt, Cmd+Shift+↑ дважды — ans "
                       "СЛОВО"),
                solution="cat day1.txt && cat day2.txt && cat day3.txt",
                solution_script="head -n 1 day2.txt | cut -d' ' -f3",
                wrong=("echo {old}",),
                alternatives=("cat day2.txt одной командой — слово в первой строке, Cmd+Shift+↑ "
                              "сразу к ней",)),
        Variant("В файле ticket.txt — код доступа: длинный, из цифр и латиницы. Перепечатывать "
                "долго, а ошибка в одном знаке — и код не тот. Выведи его командой cat, выдели "
                "вывод Cmd+Shift+A (или двойным щелчком по коду), Cmd+C и сдай: ans КОД — вместо "
                "КОД вставь Cmd+V",
                hints=("Код печатает cat ticket.txt. Набирать его руками не нужно.",
                       "Cmd+Shift+A выделяет вывод последней команды (с интеграцией iTerm2); "
                       "двойной щелчок по коду — тоже выделит его целиком.",
                       "cat ticket.txt, Cmd+Shift+A, Cmd+C, ans и Cmd+V"),
                solution="cat ticket.txt",
                solution_script="cat ticket.txt",
                wrong=("echo {old}",),
                alternatives=("ans $(cat ticket.txt) — подстановка тоже сдаст код без "
                              "перепечатки",)),
    )
    par = 40
    hints = ("Вывод длинный, читать глазами долго — пусть ищет терминал.",
             "Cmd+F открывает поиск: набери MISSING, Enter — к совпадению.",
             "cat stock.txt, затем Cmd+F и MISSING — ans СЛОВО после метки")
    solution = "cat stock.txt"
    solution_script = "grep 'MISSING' stock.txt | cut -d' ' -f4"
    explain = ("Искать глазами — долго: Cmd+F находит слово в выводе, Cmd+Shift+↑ ↓ прыгает от "
               "команды к команде. Нашёл командой — тоже честно; Cmd+F — когда вывод "
               "уже на экране.")
    spell = "Cmd+F — поиск по выводу; Cmd+Shift+↑ ↓ — от команды к команде; Cmd+Shift+A — вывод"
    trap_messages = {"old": "Это слово из другой строки — нужное там, где сказано в задании. "
                            "Найди его поиском Cmd+F."}

    def setup_variant(self, box, rng, variant):
        word, old = rng.sample(kit.WORDS, 2)
        if variant == 1:
            for day, n in (("day1", 120), ("day2", 140), ("day3", 160)):
                head = [f"Today's word: {word}"] if day == "day2" else [f"Today's word: {old}"]
                body = [f"{day} entry {i}: ok" for i in range(1, n + rng.randint(0, 40))]
                kit.write(box / f"{day}.txt", "\n".join(head + body) + "\n")
            return {"answer": word, "old": old, "traps": [["old", old]],
                    "sources": sources(box, "day2.txt")}
        if variant == 2:
            alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
            code = "".join(rng.choice(alphabet) for _ in range(24))
            kit.write(box / "ticket.txt", code + "\n")
            return {"answer": code, "old": old, "traps": [["old", old]],
                    "sources": sources(box, "ticket.txt")}
        body = [f"position {i}: in place" for i in range(1, rng.randint(500, 600))]
        body.insert(rng.randint(200, 350), f"position {rng.randint(600, 900)}: MISSING {word}")
        body.append(f"Total: {old}")
        kit.write(box / "stock.txt", "\n".join(body) + "\n")
        return {"answer": word, "old": old, "traps": [["old", old]],
                "sources": sources(box, "stock.txt")}


class QuickFix(Task):
    """FB10 (лайфхаки): быстрая правка — Esc . и !$ (последний аргумент прошлой команды),
    ^старое^новое (повтор с заменой), Ctrl+Y (вставить стёртое), Ctrl+_ (отмена). Прошлая
    команда заготовлена в истории песочницы; проверка — по результату."""
    id = "quick_fix"
    track = "basics"
    title = "Быстрая правка"
    scroll = ("Esc, потом точка — последнее слово прошлой команды; ещё раз — слово команды "
              "постарше (Option+. — если Option работает как Esc+).\n"
              "!$ — то же слово набором: cd !$. ^старое^новое — прошлая команда с заменой: "
              "^q1^q2.\n"
              "Ctrl+Y — вставить стёртое Ctrl+W, Ctrl+U, Ctrl+K. Ctrl+_ — отменить правку.")
    variants = (
        Variant("Последняя команда в истории создала папку с длинным путём. Перейди в неё, не "
                "набирая путь: cd, пробел, Esc, потом точка — путь встанет сам — и Enter.",
                wrong=("cd projects/{client}",),
                alternatives=("cd !$ — то же слово набором; zsh подставит путь сам",)),
        Variant("Последняя команда в истории скопировала в архив отчёт первого квартала, "
                "summary_q1.txt. Сделай то же для второго квартала, не перепечатывая: "
                "^q1^q2 и Enter.",
                hints=("Команда почти та же — поменять надо одно: q1 на q2.",
                       "^старое^новое повторит прошлую команду с заменой. ↑ жать не нужно: "
                       "прошлая — та, что надо.",
                       "^q1^q2"),
                solution="^q1^q2",
                solution_script="cp reports/{year}/summary_q2.txt archive/{year}/",
                wrong=("cp reports/{year}/summary_q1.txt archive/{year}/",),
                alternatives=("↑, Option+← к q1, поправь на q2 и Enter — тоже верно, но "
                              "дольше",)),
        Variant("Последней командой ты посмотрел лог с длинным путём. Скопируй именно его в "
                "outbox/: cp, пробел, Esc, потом точка — путь встанет сам, — пробел, outbox/ "
                "и Enter.",
                hints=("Путь — последнее слово прошлой команды: Esc . вставит его.",
                       "cp, пробел, Esc . (или !$), пробел, outbox/",
                       "cp !$ outbox/"),
                solution="cp, пробел, Esc ., пробел, outbox/, Enter",
                solution_script="cp logs/{year}/october/server_{name}.log outbox/",
                wrong=("cp logs/{year}/october/*.log outbox/",),
                alternatives=("cp !$ outbox/ — то же слово набором",)),
    )
    par = 40
    hints = ("Путь — последнее слово прошлой команды. Набирать его не нужно.",
             "Esc, отпусти, потом точка — вставит последнее слово прошлой команды. Или !$ — то "
             "же набором.",
             "cd !$ (или cd, пробел, Esc . и Enter)")
    solution = "cd, пробел, Esc ., Enter"
    solution_script = "cd projects/{client}/drafts/{year}/final"
    explain = ("Что уже набрано, не набирают снова: Esc . и !$ берут последнее слово прошлой "
               "команды, ^старое^новое повторяет её с заменой.")
    spell = "Esc . и !$ — последний аргумент; ^старое^новое — повтор с заменой; Ctrl+Y, Ctrl+_"

    CLIENTS = ("atlas", "orbit", "nova", "delta", "vertex")
    SERVERS = ("alpha", "bravo", "cobalt", "delta")

    def setup_variant(self, box, rng, variant):
        year = str(rng.randint(2724, 2726))
        fill = list(rng.sample(FILLER, 8))
        if variant == 1:
            want = {}
            for q in ("q1", "q2", "q3"):
                f = kit.write(box / "reports" / year / f"summary_{q}.txt",
                              f"Report {q} {year}: {kit.word(rng)}\n")
                want[f"reports/{year}/summary_{q}.txt"] = kit.sha(f)
                if q in ("q1", "q2"):
                    want[f"archive/{year}/summary_{q}.txt"] = kit.sha(f)
            (box / "archive" / year).mkdir(parents=True)
            kit.write(box / "archive" / year / "summary_q1.txt",
                      (box / "reports" / year / "summary_q1.txt").read_text("utf-8"))
            _history(box, fill + [f"cp reports/{year}/summary_q1.txt archive/{year}/"])
            return {"year": year, "want": want}
        if variant == 2:
            name, *others = rng.sample(self.SERVERS, 3)
            want = {}
            for srv in [name] + others:
                f = kit.write(box / "logs" / year / "october" / f"server_{srv}.log",
                              f"server {srv}: {kit.word(rng)}\n")
                want[f"logs/{year}/october/server_{srv}.log"] = kit.sha(f)
                if srv == name:
                    want[f"outbox/server_{srv}.log"] = kit.sha(f)
            (box / "outbox").mkdir()
            _history(box, fill + [f"ls -l logs/{year}/october/server_{name}.log"])
            return {"year": year, "name": name, "want": want, "only": f"server_{name}.log"}
        client = rng.choice(self.CLIENTS)
        target = f"projects/{client}/drafts/{year}/final"
        (box / target).mkdir(parents=True)
        (box / "projects" / client / "notes").mkdir()
        _history(box, fill + [f"mkdir -p {target}"])
        return {"year": year, "client": client, "target": target}

    def check(self, ctx):
        s = ctx.state
        if "target" in s:
            return Verdict(ctx.pwd is not None and
                           ctx.pwd.resolve() == (ctx.box / s["target"]).resolve())
        if "only" in s:
            extra = sorted(p.name for p in (ctx.box / "outbox").glob("*")
                           if p.name != s["only"]) if (ctx.box / "outbox").is_dir() else []
            if extra:
                return Verdict(False, "В outbox/ лишнее: " + ", ".join(extra) + ". Нужен один "
                                      "файл — тот, что ты смотрел последним. Убери лишнее: "
                                      "rm outbox/" + extra[0])
        return _files_check(ctx)


# --- Пары «до/после» (часть 5): fzf_pick и z_jump ------------------------------------------

class CopyDir(Task):
    """FB3 (6): флаги на практике — cp -r (папка целиком), -n (не затирать), -v (показать);
    флаги порознь или вместе, в любом порядке."""
    id = "cp_dir"
    track = "basics"
    title = "Копия целиком"
    scroll = ("Папку голый cp не копирует — скажет «is a directory». Флаг -r (recursive — "
              "вглубь) копирует папку со всем содержимым: cp -r папка копия.\n"
              "cp -r -n папка копия — no clobber: не затирать то, что уже лежит в копии; -v — "
              "verbose: печатать каждый скопированный файл.\n"
              "Флаги пишут порознь или вместе и в любом порядке: cp -r -v, cp -rv и cp -vr — "
              "одно и то же.")
    variants = (
        Variant("Сделай копию папки {proj} целиком — рядом с ней, под именем {proj}_backup.",
                wrong=("mkdir {proj}_backup",),
                alternatives=("cp -rv {proj} {proj}_backup — то же, и cp покажет каждый файл",
                              "cp -R {proj} {proj}_backup — большая -R у cp значит то же, что -r")),
        Variant("Папки {a} и {b} нужны и в archive/ — скопируй обе, одной командой. Оригиналы "
                "остаются на месте.",
                hints=("Папки копирует только cp с флагом -r.",
                       "cp, как и mv, берёт сразу несколько имён: последней идёт папка.",
                       "cp -r {a} {b} archive/"),
                solution="cp -r {a} {b} archive/",
                wrong=("mv {a} {b} archive/",),
                alternatives=("cp -rv {a} {b} archive/ — -v покажет, что скопировано",)),
        Variant("Скопируй все файлы из photos в backup. Но cover.jpg в backup новее, чем в "
                "photos, — его не затирай.",
                hints=("Обычный cp затирает файл с тем же именем молча, без вопроса.",
                       "У cp есть флаг «не затирать то, что уже есть» — он на карточке.",
                       "cp -n photos/* backup/"),
                solution="cp -n photos/* backup/",
                wrong=("cp photos/* backup/",),
                alternatives=("cp -nv photos/* backup/ — -v покажет, какие файлы легли",),
                explain="-n (no clobber) не трогает файлы, которые уже лежат в папке "
                        "назначения; без него cp затирает молча."),
    )
    par = 40
    hints = ("Голый cp папку не копирует: нужен флаг.",
             "-r — копировать папку со всем, что внутри.",
             "cp -r {proj} {proj}_backup")
    solution = "cp -r {proj} {proj}_backup"
    explain = ("Флаг меняет поведение команды: -r велит cp идти вглубь папки. Флаги можно "
               "склеивать и менять местами: cp -rv = cp -vr.")
    spell = "cp -r папка копия — копия папки; -n — не затирать; -v — показать"

    def setup_variant(self, box, rng, variant):
        if variant == 2:
            names = ["cover.jpg"] + [f"{n}.jpg" for n in rng.sample(kit.LATIN, 3)]
            want = {}
            for n in names:
                f = kit.write(box / "photos" / n, f"shot {n} {rng.randint(1, 999)}\n")
                if n != "cover.jpg":
                    want[f"backup/{n}"] = kit.sha(f)
                want[f"photos/{n}"] = kit.sha(f)
            fresh = kit.write(box / "backup" / "cover.jpg", f"new cover {rng.randint(1, 999)}\n")
            want["backup/cover.jpg"] = kit.sha(fresh)
            return {"want": want}
        if variant == 1:
            a, b = rng.sample(["notes", "drafts", "scans", "letters"], 2)
            want = {}
            for d in (a, b):
                for n in rng.sample(kit.LATIN, 2):
                    f = kit.write(box / d / f"{n}.txt", f"{d}: {kit.word(rng)}\n")
                    want[f"{d}/{n}.txt"] = want[f"archive/{d}/{n}.txt"] = kit.sha(f)
            (box / "archive").mkdir()
            return {"a": a, "b": b, "want": want}
        proj = rng.choice(["site", "shop", "blog", "game"])
        want = {}
        for rel in ("index.txt", "src/main.txt", f"src/{kit.latin(rng)}.txt", "docs/plan.md"):
            f = kit.write(box / proj / rel, f"{rel}: {kit.word(rng)}\n")
            want[f"{proj}/{rel}"] = want[f"{proj}_backup/{rel}"] = kit.sha(f)
        return {"proj": proj, "want": want}

    def check(self, ctx):
        b, want = ctx.box, ctx.state["want"]
        if all((b / rel).is_file() and kit.sha(b / rel) == h for rel, h in want.items()):
            return Verdict(True)
        if kit.lost(b, want.values()):
            return Verdict(False, "Нужный файл стёрт или затёрт — его текста больше нет ни в "
                                  "одном файле. " + kit.RESET_TAIL)
        return self._moved(b, want) or Verdict(False)

    def _moved(self, b, want):
        """FB6: папку перенесли (mv), а не скопировали — раньше молчали. Оригинала нет на
        месте, а его файл лежит там, куда шла копия: назвать, как вернуть."""
        have = {rel: kit.sha_in_box(b, rel) for rel in want}
        back = {}
        for rel, h in want.items():
            if have[rel] is not None:
                continue
            for other, got in have.items():
                if other == rel or got != h:
                    continue
                orig, copy = Path(rel), Path(other)
                tail = len(orig.parts) - 1
                if not tail or (b / orig.parts[0]).exists():
                    continue        # ушла не папка целиком (cp -n photos/* — другой случай)
                if copy.parts[-tail:] != orig.parts[1:]:
                    continue
                back[orig.parts[0]] = str(Path(*copy.parts[:len(copy.parts) - tail]))
                break
        if not back:
            return None
        tops = sorted(back)
        if all(Path(back[t]).name == t for t in tops):
            cmd = "mv " + " ".join(back[t] for t in tops) + " ."
        else:
            cmd = "; ".join(f"mv {back[t]} {t}" for t in tops)
        word = "пропали" if len(tops) > 1 else "пропала"
        return Verdict(False, f"{', '.join(tops)} {word} со своего места: mv переносит, а нужна "
                              f"копия. Верни: {cmd} — и сделай cp -r.")


# Части имён для fzf_pick: ни одна не сидит внутри другой и внутри слов kit.LATIN
# (проверяет tests/test_implant_tasks; короткий месяц may не берём — такой кусок легко
# оказывается внутри чужого слова).
PICK_YEARS = ("2722", "2723", "2724", "2725")
PICK_MONTHS = ("january", "february", "march", "april", "june", "july", "august",
               "september", "october", "november", "december")
PICK_KINDS = ("final", "draft", "review", "backup", "summary")


class FzfPick(AnswerTask):
    id = "fzf_pick"
    track = "basics"
    title = "Три обрывка имени"
    implant = "fzf"
    after = ("climb_down", "boss_basics")
    start_dir = "{start}"
    scroll = ("ls | grep слово — только строки со словом; grep -i — ignore case, без учёта "
              "регистра. Цепочкой через трубу | (вывод левой — на вход правой): | grep a | grep b.\n"
              "cat \"$(команда)\" — подставит найденное имя. Пусто — cat ждёт ввода: Ctrl+C.\n"
              "Утилита (маленькая отдельная программа) fzf — выбор кусками имени: ls | fzf.")
    variants = (
        Variant("Тут, в reports, под три сотни отчётов с похожими именами. Нужен тот, в "
                "имени которого есть {y}, {m} и {k} — в любом порядке, буквы могут быть "
                "большими. В нём одно слово. Ответ: ans СЛОВО",
                wrong=("cat *{y}*{m}*{k}*",
                       "cat $(ls | grep {y} | grep {m} | grep {k}) </dev/null"),
                alternatives=("cat \"$(ls | fzf)\" — набрать {y} {m} {k} и Enter",
                              "ls *{y}* | grep -i {m} | grep -i {k} — первый фильтр маской")),
        Variant("Тут, в projects, три сотни папок, и названия похожи как близнецы. В нужной "
                "папке в названии есть {y}, {m} и {k}, порядок любой, регистр любой. Внутри "
                "лежит readme.txt с одним словом. Ответ: ans СЛОВО",
                hints=("Отфильтруй список папок: ls | grep {y} оставит только с {y}.",
                       "Цепочка фильтров через |, а -i у grep не различает большие и маленькие "
                       "буквы. К найденной папке допиши /readme.txt.",
                       "cat \"$(ls | grep {y} | grep -i {m} | grep -i {k})/readme.txt\" — "
                       "утилитой: cd \"$(ls | fzf)\" и набрать {y} {m} {k}"),
                solution="cat \"$(ls | grep {y} | grep -i {m} | grep -i {k})/readme.txt\"",
                implant_script="cat \"$(ls | fzf -e --filter '{y} {m} {k}')/readme.txt\"",
                wrong=("cat \"$(ls | grep {y} | grep {m} | grep {k})/readme.txt\" </dev/null",),
                alternatives=("cd \"$(ls | fzf)\" && cat readme.txt",)),
        Variant("В drafts три сотни черновиков с похожими именами. Открой в nano тот, в имени "
                "которого есть {y}, {m} и {k} (в любом порядке, регистр любой), и замени в "
                "нём слово {old} на {new}. Остальные не трогай.",
                hints=("Найди имя фильтрами: ls | grep {y} | grep -i {m} | grep -i {k}.",
                       "nano откроет файл по имени — подставь найденное: nano \"$(…)\". Поправь "
                       "слово, Ctrl+O, Enter, Ctrl+X.",
                       "nano \"$(ls | grep {y} | grep -i {m} | grep -i {k})\" — утилитой: "
                       "nano \"$(ls | fzf)\" и набрать {y} {m} {k}"),
                solution="nano \"$(ls | grep {y} | grep -i {m} | grep -i {k})\"",
                solution_script="sed -i '' 's/{old}/{new}/' "
                                "\"$(ls | grep {y} | grep -i {m} | grep -i {k})\"",
                implant_script="sed -i '' 's/{old}/{new}/' \"$(ls | fzf -e --filter "
                               "'{y} {m} {k}')\"",
                wrong=("sed -i '' 's/{old}/{new}/' *{y}*",),
                alternatives=("nano \"$(ls | fzf)\" — выбрать набором {y} {m} {k}",)),
    )
    par = 50
    hints = ("Глазами три сотни имён не перебрать — отфильтруй список: ls | grep {y} оставит "
             "имена с {y}.",
             "Фильтры ставятся цепочкой через |, а -i у grep не различает большие и маленькие "
             "буквы: | grep -i {m}.",
             "cat \"$(ls | grep {y} | grep -i {m} | grep -i {k})\" — утилитой: cat \"$(fzf)\" "
             "и набрать {y} {m} {k}")
    solution = "cat \"$(ls | grep {y} | grep -i {m} | grep -i {k})\""
    implant_script = "cat \"$(ls | fzf -e --filter '{y} {m} {k}')\""
    explain = ("grep — фильтр: каждый | grep отсекает лишнее, -i не смотрит на регистр. fzf "
               "делает то же на лету, пока набираешь.")
    spell = "ls | grep a | grep -i b — отфильтровать длинный список по кускам имени"

    STARTS = ("reports", "projects", "drafts")
    SWAPS = (("draft", "done"), ("pending", "accepted"), ("open", "closed"))

    @staticmethod
    def _name(rng, y, m, k):
        """Части в случайном порядке, месяц в случайном регистре (не всегда маленькими)."""
        parts = [y, rng.choice([m, m.capitalize(), m.upper()]), k, kit.latin(rng)]
        rng.shuffle(parts)
        return rng.choice(["_", "-"]).join(parts)

    def setup_variant(self, box, rng, variant):
        start = self.STARTS[variant_index(variant, 3)]
        root = box / start
        y, m, k = rng.choice(PICK_YEARS), rng.choice(PICK_MONTHS), rng.choice(PICK_KINDS)
        # macOS различает имена без учёта регистра: March и MARCH — один файл
        found = {}
        while len(found) < 299:
            t = (rng.choice(PICK_YEARS), rng.choice(PICK_MONTHS), rng.choice(PICK_KINDS))
            if t != (y, m, k):
                name = self._name(rng, *t)
                found.setdefault(name.lower(), name)
        names = found.values()
        target = self._name(rng, y, m.capitalize(), k)    # хоть одна большая буква
        old, new = rng.choice(self.SWAPS)
        word = kit.word(rng)

        def other():
            """Слово чужого файла — не слово ответа: открыл не тот — ответ не сойдётся (P2 Б10)."""
            w = kit.word(rng)
            while w == word:
                w = kit.word(rng)
            return w

        for name in sorted(names):
            if variant == 1:
                kit.write(root / name / "readme.txt", f"{other()}\n")
            elif variant == 2:
                kit.write(root / f"{name}.txt", f"status: {old}\n")
            else:
                kit.write(root / f"{name}.txt", f"{other()}\n")
        if variant == 1:
            kit.write(root / target / "readme.txt", f"{word}\n")
        else:
            kit.write(root / f"{target}.txt", f"{word}\n" if variant == 0 else f"status: {old}\n")
        st = {"start": start, "y": y, "m": m, "k": k, "old": old, "new": new,
              "target": target + ("" if variant == 1 else ".txt"), "answer": word}
        if variant != 2:
            src = f"{start}/{target}/readme.txt" if variant == 1 else f"{start}/{target}.txt"
            st["sources"] = sources(box, src)
        return st

    def takes_answer(self, state):
        """Вариант с правкой в nano — «сделай»: карточка не зовёт сдавать слово (FB6)."""
        return variant_index(state.get("_variant"), 3) != 2

    def check(self, ctx):
        if variant_index(ctx.state.get("_variant"), 3) != 2:
            return super().check(ctx)
        start = Path(ctx.state["start"])
        old, new = ctx.state["old"], ctx.state["new"]
        # проверку зовёт судья у родителя: папка и файлы — только внутри песочницы, по
        # звеньям без симлинков, обычные файлы не больше 1 МБ (sandbox.read_in_box)
        names = sandbox.files_in_box(ctx.box, start)
        if names is None:
            return Verdict(False)
        texts = {n: (sandbox.read_in_box(ctx.box, start / n, kit.BOX_READ_CAP) or b"").decode(
                     "utf-8", errors="replace") for n in names}
        if ctx.state["target"] not in texts:
            return Verdict(False, "Нужного черновика больше нет. " + kit.RESET_TAIL)
        target = texts.get(ctx.state["target"], "")
        others_ok = all(new not in t for n, t in texts.items() if n != ctx.state["target"])
        if new in target and old not in target:
            if others_ok:
                return Verdict(True)
            return Verdict(False, f"Нужный файл исправлен, но «{new}» появилось и в других — "
                                  "их трогать было нельзя (reset вернёт всё как было).")
        return Verdict(False)


class ZJump(Task):
    """Пара к back_up: прыжок назад по стеку каталогов zsh (auto_pushd включён в песочном
    .zshrc), утилита zoxide — по куску имени. Проверка: стоишь в цели, все четыре папки
    посещены, а команда, которая привела в цель, короче 15 знаков и без пути цели."""
    id = "z_jump"
    track = "basics"
    title = "Прыжок назад"
    implant = "zoxide"
    after = ("back_up", "boss_basics")
    scroll = ("zsh здесь помнит, где ты был (setopt auto_pushd): каждый cd кладёт прежнюю папку "
              "в стек (стопку, свежее — сверху). dirs -v — стек с номерами (v — verbose, подробно), cd ~3 — прыжок в "
              "папку номер 3, cd - — на шаг назад.\n"
              "Утилита zoxide запоминает папки сама: z кусок_имени — и ты там.")
    variants = (
        Variant("Обойди четыре папки по порядку, в каждую — одной командой cd с путём целиком: "
                "{d1}, {d2}, {d3}, {d4}. Затем вернись в самую первую одной командой короче 15 "
                "знаков и без её пути.",
                wrong=("setopt auto_pushd; cd {d1}; cd {d2}; cd {d3}; cd {d4}; cd -",
                       "setopt auto_pushd; cd {d1}; cd {d2}; cd {d3}; cd {d4}; cd {d1}"),
                alternatives=("z {leaf1} — если стоит zoxide: прыжок по куску имени",)),
        Variant("Маршрут — {d1}, затем {d2}, {d3} и {d4}: заходи по очереди, каждый раз cd и "
                "полный путь. После четвёртой прыгни обратно во вторую — короткой командой "
                "(меньше 15 знаков, путь не набирать).",
                hints=("Каждый cd в этом zsh запоминает, откуда ты ушёл: папки копятся в стеке.",
                       "dirs -v покажет стек с номерами: 0 — где ты сейчас, дальше — от "
                       "свежих к старым.",
                       "dirs -v, затем cd ~2 — вторая из четырёх; утилитой: z и кусок её имени"),
                solution="cd {d1}; cd {d2}; cd {d3}; cd {d4}; dirs -v; cd ~2",
                solution_script="setopt auto_pushd; cd {d1}; cd {d2}; cd {d3}; cd {d4}; cd ~2",
                implant_script=("export _ZO_DATA_DIR=$TERMIT_BOX/.termit/zoxide; mkdir -p "
                                "$_ZO_DATA_DIR; eval \"$(zoxide init zsh)\"; cd {d1}; cd {d2}; "
                                "cd {d3}; cd {d4}; z {leaf2}"),
                wrong=("setopt auto_pushd; cd {d1}; cd {d2}; cd {d3}; cd {d4}; cd -",
                       "setopt auto_pushd; cd {d1}; cd {d2}; cd {d3}; cd {d4}; cd ~3"),
                alternatives=("z {leaf2} — если стоит zoxide: прыжок по куску имени",)),
        Variant("Пройди {d1}, {d2}, {d3} и {d4} — в каждую одной командой cd с полным путём — и "
                "по дороге загляни, где лежит marker.txt. Закончи там, где он лежит, а "
                "последнюю команду сделай короче 15 знаков и без пути.",
                hints=("ls в каждой папке покажет, где marker.txt; запомни, которая по счёту.",
                       "dirs -v перечислит пройденные папки с номерами — от свежих к старым.",
                       "dirs -v, затем cd ~N — номер папки с marker.txt; утилитой: z и кусок её "
                       "имени"),
                solution="cd {d1}; ls; cd {d2}; ls; cd {d3}; cd {d4}; dirs -v; cd ~{k}",
                solution_script="setopt auto_pushd; cd {d1}; cd {d2}; cd {d3}; cd {d4}; cd ~{k}",
                implant_script=("export _ZO_DATA_DIR=$TERMIT_BOX/.termit/zoxide; mkdir -p "
                                "$_ZO_DATA_DIR; eval \"$(zoxide init zsh)\"; cd {d1}; cd {d2}; "
                                "cd {d3}; cd {d4}; z {leaf}"),
                wrong=("setopt auto_pushd; cd {d1}; cd {d2}; cd {d3}; cd {d4}; cd -",
                       "setopt auto_pushd; cd {d1}; cd {d2}; cd {d3}; cd {d4}; cd ~{wk}"),
                alternatives=("z {leaf} — если стоит zoxide: прыжок по куску имени",)),
    )
    par = 60
    hints = ("Каждый cd в этом zsh запоминает, откуда ты ушёл: папки копятся в стеке.",
             "dirs -v покажет стек с номерами: 0 — где ты сейчас, дальше — от свежих к старым.",
             "dirs -v, затем cd ~3 — первая из четырёх; утилитой: z и кусок её имени")
    solution = "cd {d1}; cd {d2}; cd {d3}; cd {d4}; dirs -v; cd ~3"
    solution_script = "setopt auto_pushd; cd {d1}; cd {d2}; cd {d3}; cd {d4}; cd ~3"
    implant_script = ("export _ZO_DATA_DIR=$TERMIT_BOX/.termit/zoxide; mkdir -p $_ZO_DATA_DIR; "
                      "eval \"$(zoxide init zsh)\"; cd {d1}; cd {d2}; cd {d3}; cd {d4}; z {leaf1}")
    explain = ("zsh складывает пройденные папки в стек: dirs -v показывает номера, cd ~N "
               "прыгает. zoxide помнит частые папки и между сеансами.")
    spell = "dirs -v — где я был; cd ~3 — прыжок в папку номер 3 из стека"

    AREAS = ("clients", "vault", "depot", "archive", "ledger", "studio")
    SHORT = 15

    def setup_variant(self, box, rng, variant):
        """Папки — в доме песочницы: путь через ~ работает из любой папки."""
        home = kit.home(box)
        areas = rng.sample(self.AREAS, 4)
        leaves = rng.sample(kit.LATIN, 4)
        dirs = []
        for area, leaf in zip(areas, leaves):
            rel = f"{area}/{rng.randint(2719, 2725)}/{kit.latin(rng)}_{rng.randint(10, 99)}/{leaf}"
            kit.write(home / rel / "list.txt", f"{kit.word(rng)}\n")
            dirs.append(rel)
        st = {f"d{i + 1}": f"~/{d}" for i, d in enumerate(dirs)}
        st.update({f"leaf{i + 1}": leaf for i, leaf in enumerate(leaves)})
        if variant == 2:
            idx = rng.randrange(2)                  # первая или вторая: cd - туда не ведёт
            kit.write(home / dirs[idx] / "marker.txt", "here\n")
            st.update({"k": 3 - idx, "wk": 2 + idx, "leaf": leaves[idx], "target": dirs[idx]})
        else:
            st["target"] = dirs[1] if variant == 1 else dirs[0]
        st["dirs"] = dirs
        return st

    # прыжок стеком каталогов (dirs -v: cd ~N, cd ±N, pushd ±N, popd) или утилитой z с
    # ключевыми словами (без /, точек и ~: путь — это уже cd, а не прыжок)
    _JUMP = re.compile(r"(?:cd|pushd)\s+(?:[-+]\d+|~[-+]?\d+/?|-)|popd(?:\s+[-+]?\d+)?|"
                       r"zi?(?:\s+[\w-]+)*")
    _MOVERS = ("cd", "pushd", "popd", "z", "zi")

    @staticmethod
    def _segments(line: str):
        """Команды строки по границам && || ; | и переводу строки; хвост «# …» отрезан."""
        out = []
        for seg in re.split(r"&&|\|\||[;|\n]", line):
            seg = re.sub(r"(?:^|\s)#.*$", "", seg).strip()
            if seg:
                out.append(seg)
        return out

    def _move(self, line: str) -> str:
        """Последняя команда строки, которая меняет папку (cd ~3 && ls → cd ~3)."""
        movers = [s for s in self._segments(line) if s.split()[0] in self._MOVERS]
        return movers[-1] if movers else ""

    def check(self, ctx):
        st = ctx.state
        home = kit.home(ctx.box)

        def same(p, rel):
            try:
                return Path(p).resolve() == (home / rel).resolve()
            except (OSError, RuntimeError):
                return False

        def went(line, rel):        # cd/pushd с путём папки: через ~ или полностью
            return any(seg.split()[:1] in (["cd"], ["pushd"]) and
                       (f"~/{rel}" in seg or str(home / rel) in seg)
                       for seg in self._segments(line))

        if ctx.pwd is None or not same(ctx.pwd, st["target"]):
            return Verdict(False)
        seen = [any(same(c.pwd, d) or went(c.line, d) for c in ctx.cmds) for d in st["dirs"]]
        if not all(seen):
            # честный проход через цель посреди маршрута — не повод одёргивать (P2 Б10):
            # говорим, только если игрок уже был дальше цели по маршруту и вернулся
            at = st["dirs"].index(st["target"]) if st["target"] in st["dirs"] else -1
            if any(seen[at + 1:]):
                return Verdict(False, "Ты на месте, но маршрут не пройден: сначала зайди во "
                                      "все четыре папки — каждую своей командой cd.")
            return Verdict(False)
        arrival = next((c for c in reversed(ctx.cmds) if not same(c.pwd, st["target"])), None)
        seg = self._move(arrival.line) if arrival else ""
        words = seg.split()
        # z ИМЯ, где ИМЯ — папка рядом: zoxide тогда просто делает cd — это шаг, не прыжок
        near = (len(words) == 2 and words[0] in ("z", "zi")
                and (Path(arrival.pwd) / words[1]).is_dir())
        if (self._JUMP.fullmatch(seg) and len(seg) < self.SHORT
                and st["target"] not in seg and not near):
            return Verdict(True)
        return Verdict(False, "Дошёл пешком — честно, но задача про короткий путь: dirs -v "
                              "покажет, куда прыгать, cd ~N — прыжок.")


class BossBasics(Task):
    id = "boss_basics"
    track = "basics"
    title = "Сбор ключей"
    boss = True
    par = 180
    scroll = ("** в маске — любые вложенные папки на любой глубине (это умеет zsh): "
              "ls old_disk/**/*.key\n"
              "(D) после маски — включить скрытые файлы и папки: ls old_disk/**/*.key(D). "
              "ls -R папка — показать всё дерево разом.\n"
              "rm -r папка — удалить папку со всем содержимым (навсегда, мимо Корзины).")
    steps = ("создать папку для копий",
             "скопировать туда все настоящие файлы-ключи (оригиналы оставить на месте)",
             "не забыть спрятанный",
             "убрать ловушку")
    variants = (
        Variant("На старом диске old_disk спрятаны ключи *.key. Собери КОПИИ всех настоящих "
                "ключей в новую папку keys — плоско, без подпапок. Подделки .key.fake и .key~ "
                "(хвост ~ в конце имени — копия редактора) не брать. Потом удали "
                "папку-ловушку trap.",
                wrong=("mkdir keys && cp old_disk/**/*.key keys/ && rm -r old_disk/**/trap",
                       "mkdir keys && mv old_disk/**/*.key(D) keys/ && rm -r old_disk/**/trap(D)"),
                alternatives=("mkdir -p keys — не ругается, если папка уже создана",)),
        Variant("Со старого диска old_disk выносим сертификаты *.cert. Сложи копии каждого "
                "подлинного в папку certs, одним слоем; хвосты .cert.old и .cert~ — фальшивки. "
                "Где-то внутри сидит папка decoy — снеси её.",
                hints=("Начни с mkdir certs. Сертификаты лежат глубоко — всё дерево покажет "
                       "ls -laR old_disk",
                       "** — любые вложенные папки, (D) — и скрытые тоже: "
                       "ls old_disk/**/*.cert(D)",
                       "mkdir certs && cp old_disk/**/*.cert(D) certs/ && rm -r old_disk/**/decoy"),
                solution="mkdir certs && cp old_disk/**/*.cert(D) certs/ && "
                         "rm -r old_disk/**/decoy(D)",
                wrong=("mkdir certs && cp old_disk/**/*.cert certs/ && rm -r old_disk/**/decoy",
                       "mkdir certs && cp old_disk/**/*.cert*(D) certs/ && "
                       "rm -r old_disk/**/decoy(D)"),
                alternatives=("ls old_disk/**/*.cert(D) — сначала увидеть всю добычу, потом "
                              "копировать",)),
        Variant("В old_disk лежат ключи *.key, а вокруг — резервные копии *.bak, которым на "
                "диске не место. Собери копии настоящих ключей в папку keys, плоско, без "
                "подделок, и сотри с диска все *.bak до единого.",
                hints=("Начни с mkdir keys. И ключи, и .bak разбросаны по всему дереву: "
                       "ls -laR old_disk",
                       "** и (D) работают с любой маской: и с *.key, и с *.bak — скрытые "
                       "папки тоже в счёт.",
                       "mkdir keys && cp old_disk/**/*.key(D) keys/ && rm old_disk/**/*.bak(D)"),
                solution="mkdir keys && cp old_disk/**/*.key(D) keys/ && rm old_disk/**/*.bak(D)",
                wrong=("mkdir keys && cp old_disk/**/*.key keys/ && rm old_disk/**/*.bak",
                       "mkdir keys && mv old_disk/**/*.key(D) keys/ && rm old_disk/**/*.bak(D)"),
                alternatives=("ls old_disk/**/*.bak(D) — сначала посмотреть, что сотрёшь",)),
    )
    hints = ("Начни с mkdir keys. Ключи лежат глубоко — посмотри всё дерево: ls -laR old_disk",
             "В zsh есть глубокий поиск: ** — любые вложенные папки, (D) — включая "
             "скрытые: ls old_disk/**/*.key(D)",
             "mkdir keys && cp old_disk/**/*.key(D) keys/ && rm -r old_disk/**/trap")
    solution = "mkdir keys && cp old_disk/**/*.key(D) keys/ && rm -r old_disk/**/trap(D)"
    explain = ("** спускается во все вложенные папки, (D) добавляет скрытые; rm -r удаляет папку "
               "вместе с содержимым.")
    spell = "**/*.key(D) — все .key во всех вложенных папках, включая скрытые (zsh); rm -r папка"

    # вариант → (режим, расширение ключей, папка для копий, подделки, ловушка)
    MODES = (("key", "key", "keys", (".key.fake", ".key~"), "trap"),
             ("cert", "cert", "certs", (".cert.old", ".cert~"), "decoy"),
             ("bak", "key", "keys", (".key.fake", ".key~"), None))

    def setup_variant(self, box, rng, variant):
        mode, ext, folder, fakes, trap_name = self.MODES[variant]
        root = box / "old_disk"
        root.mkdir()
        dirs = [root]
        for i in range(rng.randint(22, 30)):
            parent = rng.choice(dirs)
            if len(parent.relative_to(box).parts) >= 5:
                parent = root
            d = parent / f"{kit.latin(rng)}_{i}"
            d.mkdir()
            dirs.append(d)
        keys, loc = {}, {}
        for i in range(rng.randint(8, 11)):
            name = f"{kit.latin(rng)}_{i}.{ext}"
            p = kit.write(rng.choice(dirs) / name, f"key {name} {rng.random()}\n")
            keys[name], loc[name] = kit.sha(p), str(p.relative_to(box))
        hname = f"{kit.latin(rng)}_hidden.{ext}"
        hidden_dir = rng.choice(dirs) / ".hidden"
        hp = kit.write(hidden_dir / hname, f"hidden key {rng.random()}\n")
        keys[hname], loc[hname] = kit.sha(hp), str(hp.relative_to(box))
        for i in range(rng.randint(4, 7)):
            kit.write(rng.choice(dirs) / f"{kit.latin(rng)}_{i}{rng.choice(fakes)}", "fake\n")
        state = {"mode": mode, "folder": folder, "keys": keys, "loc": loc, "hidden": hname,
                 "trap": None, "baks": []}
        if trap_name:
            trap = rng.choice(dirs[1:]) / trap_name
            kit.write(trap / "bait.txt", "Gotcha!\n")
            state["trap"] = str(trap.relative_to(box))
        else:
            # .bak — и рядом с ключами (x.key.bak — не ключ), и в скрытой папке
            baks = [rng.choice(dirs) / f"{kit.latin(rng)}_b{i}{rng.choice(['.bak', '.key.bak'])}"
                    for i in range(rng.randint(4, 7))]
            baks.append(hidden_dir / f"{kit.latin(rng)}_old.bak")
            for b in baks:
                kit.write(b, "backup copy\n")
            state["baks"] = [str(b.relative_to(box)) for b in baks]
        return state

    # шаги под режим: что собрать, куда и что снести (общие steps — для шпаргалки и T002)
    MODE_STEPS = (
        ("создать папку keys",
         "скопировать в keys все настоящие *.key (оригиналы оставить на месте)",
         "не забыть ключ в скрытой папке",
         "удалить папку-ловушку trap целиком (она где-то внутри old_disk)"),
        ("создать папку certs",
         "скопировать в certs все настоящие *.cert (оригиналы оставить на месте)",
         "не забыть сертификат в скрытой папке",
         "удалить папку-ловушку decoy целиком (она где-то внутри old_disk)"),
        ("создать папку keys",
         "скопировать в keys все настоящие *.key (оригиналы оставить на месте)",
         "не забыть ключ в скрытой папке",
         "стереть с диска все *.bak — и в скрытых папках тоже"),
    )

    def steps_for(self, state):
        return list(self.MODE_STEPS[variant_index(state.get("_variant", 0),
                                                  len(self.MODE_STEPS))])

    def _have(self, ctx):
        folder = ctx.box / ctx.state["folder"]
        if not folder.is_dir():
            return None
        return {p.name: kit.sha(p) for p in folder.iterdir() if p.is_file()}

    def progress(self, ctx):
        s, box = ctx.state, ctx.box
        have = self._have(ctx) or {}
        originals = all((box / rel).is_file() for rel in s["loc"].values())
        regular = {n: h for n, h in s["keys"].items() if n != s["hidden"]}
        if s["mode"] == "bak":
            trap_gone = not any((box / rel).exists() for rel in s["baks"])
        else:
            trap_gone = not (box / s["trap"]).exists()
        return [self._have(ctx) is not None,
                originals and all(have.get(n) == h for n, h in regular.items()),
                have.get(s["hidden"]) == s["keys"][s["hidden"]],
                trap_gone]

    def check(self, ctx):
        if not all((ctx.box / rel).is_file() for rel in ctx.state["loc"].values()):
            return Verdict(False, "Оригиналы пропали со своих мест — нужна копия (cp), а не "
                                  "перенос и не удаление. " + kit.RESET_TAIL)
        if not all(self.progress(ctx)):
            return Verdict(False)
        extra = set(self._have(ctx)) - set(ctx.state["keys"])
        if extra:
            return Verdict(False, f"В папке {ctx.state['folder']} лишнее: " +
                           ", ".join(sorted(extra)))
        return Verdict(True)


# FB5: MeetTerminal — первым: что такое терминал, оболочка и команда.
# FB4: уроки навигации (LineEdit, HistoryRecall, ScreenScroll) — временно сразу после двух
# задач на глубину: владелец проходит их следующими, потом их переставят на постоянное место.
# FB10: за ними — лайфхаки: поиск по экрану (к прокрутке) и быстрая правка (строка + история)
# FB13: «Курсор и буфер» — сразу за правкой строки
TASKS = [MeetTerminal(), WhereAmI(), ClimbDown(), BackUp(), HomeTilde(), HiddenCache(),
         MkdirP(), CopyMove(), FileExt(), StarMask(), QuestionMask(),
         RunScript(), DeepDig(), DeepRm(),
         LineEdit(), CursorClip(), HistoryRecall(), ScreenScroll(), ScreenFind(), QuickFix(),
         CopyDir(),
         FzfPick(), ZJump(), BossBasics()]
