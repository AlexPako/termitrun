"""Трек «Основы»: навигация, файлы, маски."""
import io
import os
import re
import zipfile
from pathlib import Path
from typing import List, Optional

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
    scroll = ("Терминал — окно для команд: Terminal.app или iTerm2.\n"
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
                "переменная TERM_PROGRAM: echo $TERM_PROGRAM его покажет. Сдай название: "
                "ans ANSWER — вместо ANSWER вставь его (или сразу ans $TERM_PROGRAM).",
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
                "ZSH_VERSION: echo $ZSH_VERSION его покажет. Сдай только номер: ans ANSWER — "
                "вместо ANSWER вставь его (или сразу ans $ZSH_VERSION).",
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
    # владелец 23.10 (Р4): первая задача — без $( ): путь копируют мышью, $( ) — «быстрее так»
    scroll = ("pwd — полный путь текущей папки. Путь — её вывод: то, что команда напечатала.\n"
              "Путь не перепечатывай: трижды щёлкни по нему — выделится вся строка, Cmd+C; "
              "потом ans, пробел, Cmd+V и Enter.\n"
              "Путь выйдет длинным: задание идёт в песочнице — отдельной папке игры, "
              "настоящие файлы она не трогает.")
    # «ans .» засчитывается в любом варианте (путь относительно текущей папки) — не wrong
    variants = (
        Variant("Назови полный путь папки, в которой ты сейчас стоишь. Набери pwd и нажми "
                "Enter — терминал напечатает путь. Не перепечатывай его: трижды щёлкни по "
                "строке с путём, нажми Cmd+C, потом набери ans и пробел, вставь Cmd+V и нажми "
                "Enter.",
                hints=("Путь печатает команда pwd.",
                       "Тройной щелчок выделит всю строку с путём, Cmd+C скопирует.",
                       "pwd, тройной щелчок по пути, Cmd+C, затем ans, пробел, Cmd+V, Enter"),
                solution="pwd, тройной щелчок по пути, Cmd+C, затем ans, пробел, Cmd+V, Enter",
                solution_script="pwd",
                wrong=("echo $HOME",),
                alternatives=("ans $(pwd) — быстрее: $( ) выполнит pwd и подставит путь сам",
                              "ans $PWD — в $PWD терминал всегда держит путь текущей папки")),
        # новичок 24.10: $( ) объясняет «Своя дека», cd .. — «Отход», оба позже — здесь
        # тот же путь мышью, а в варианте 2 — «стереть в пути последнюю папку»
        Variant("Тебя забросило в незнакомую глубину, и откуда ты пришёл — неизвестно. "
                "Где ты? Сдай полный путь: ans PATH — вместо PATH вставь путь, что "
                "напечатает pwd (тройной щелчок по нему, Cmd+C, потом Cmd+V).",
                hints=("Путь печатает команда pwd.",
                       "Тройной щелчок выделит всю строку с путём, Cmd+C скопирует.",
                       "pwd, тройной щелчок по пути, Cmd+C, затем ans, пробел, Cmd+V, Enter"),
                solution="pwd, тройной щелчок по пути, Cmd+C, затем ans, пробел, Cmd+V, Enter",
                solution_script="pwd",
                wrong=("echo src", "echo {name}/src"),
                alternatives=("ans $(pwd) — быстрее: $( ) выполнит pwd и подставит путь сам",
                              "ans $PWD — в $PWD терминал всегда держит путь текущей папки")),
        Variant("Нужен полный путь не этой папки, а той, в которой она лежит, — на уровень "
                "выше. Сдай его: ans PATH — вместо PATH вставь путь от pwd и сотри в конце "
                "последнюю папку.",
                hints=("В пути папки разделены косой чертой /, последняя — та, где ты стоишь.",
                       "Вставь путь от pwd после ans и сотри Backspace последнюю папку вместе "
                       "с её /.",
                       "pwd, тройной щелчок по пути, Cmd+C, затем ans, пробел, Cmd+V, "
                       "Backspace до последней /, Enter"),
                solution="pwd, тройной щелчок по пути, Cmd+C, затем ans, пробел, Cmd+V, "
                         "Backspace до последней /, Enter",
                solution_script="cd .. && pwd",
                wrong=("pwd",),
                alternatives=("ans .. — две точки значат «папка уровнем выше»: путь можно "
                              "сдать и так",
                              "ans $(dirname $PWD) — dirname отрезает последнюю папку")),
    )
    start_dir = "{start}"
    par = 20
    hints = ("Путь печатает команда pwd.",
             "Тройной щелчок выделит всю строку с путём, Cmd+C скопирует.",
             "pwd, тройной щелчок по пути, Cmd+C, затем ans, пробел, Cmd+V, Enter")
    solution = "pwd, тройной щелчок по пути, Cmd+C, затем ans, пробел, Cmd+V, Enter"
    solution_script = "pwd"
    explain = ("pwd печатает полный путь текущей папки. Вывод — то, что команда напечатала, — "
               "не перепечатывают: пальцы врут. Копируют мышью, а позже — подставляют сам.")
    spell = "pwd — где я стою (полный путь текущей папки)"
    trap_messages = {"here": "Это путь текущей папки, а нужна папка на уровень выше: сотри в "
                             "конце пути последнюю папку вместе с её /."}

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
    # новичок 24.10: && объясняет урок back_up (следующий), кавычки — quotes (позже): эталоны
    # здесь — шагами словами («затем»), имя с пробелами добивает Tab
    scroll = ("cd DIR — войти в папку (DIR — сюда имя папки; можно путь a/b/c — папка в "
              "папке); ls — что в папке; cat FILE — что внутри файла: cat notes.txt.\n"
              "Две-три буквы имени и Tab — терминал допишет.\n"
              "Слово сдай: двойной щелчок по нему, Cmd+C, ans, пробел, Cmd+V. Повисло (cat ждёт "
              "ввода) — Ctrl+C.")
    variants = (
        Variant("Глубоко в {path} лежит файл note.txt. Зайди туда и прочти, "
                "какое слово в нём написано. Ответ: ans WORD — вместо WORD вставь это слово.",
                wrong=("cat note.txt",),
                alternatives=("cat {path}/note.txt — прочесть, не заходя внутрь",)),
        Variant("Записка note.txt лежит в «{path}» — в имени папки есть пробелы. "
                "Доберись до неё и назови слово: ans WORD — вместо WORD вставь это слово. "
                "Кавычки-ёлочки вокруг имени не набирай.",
                hints=("Пробел терминал считает границей между словами — имя из трёх слов "
                       "развалится. Набирать его целиком не надо.",
                       "Набери cd Old и жми Tab: он допишет имя и сам поставит \\ перед каждым "
                       "пробелом.",
                       "cd Old, Tab, первые буквы {sub}, Tab, Enter; затем cat note.txt"),
                solution="cd Old, Tab, первые буквы {sub}, Tab, Enter; затем cat note.txt",
                solution_script='cd "{path}" && cat note.txt',
                wrong=("cd Old Projects 2719/{sub} && cat note.txt", "cat note.txt"),
                alternatives=('cd "{path}" — кавычки тоже склеивают имя с пробелами (про '
                              'них — задача «Слово с пробелом»)',)),
        Variant("Здесь три папки, и в каждой лежит свой note.txt. Какая записка настоящая, "
                "сказано в readme.txt — он лежит прямо здесь. Найди её и сдай слово: ans WORD — вместо WORD вставь "
                "это слово.",
                hints=("Начни с cat readme.txt — там сказано, в какую папку идти.",
                       "Потом cd в названную папку и cat note.txt; чужие записки — обманки.",
                       "cat readme.txt, затем cd {target}, затем cat note.txt"),
                solution="cat readme.txt, затем cd {target}, затем cat note.txt",
                solution_script="cd {target} && cat note.txt",
                wrong=("cd {decoy} && cat note.txt", "cat note.txt"),
                alternatives=("cat {target}/note.txt — когда папка уже известна",)),
    )
    par = 40
    hints = ("Сначала войди в папку командой cd, потом прочти файл командой cat.",
             "Имена длинные — набери cd old и жми Tab.",
             "cd {path}, затем cat note.txt")
    solution = "cd {path}, затем cat note.txt"
    solution_script = "cd {path} && cat note.txt"
    explain = ("cd меняет текущую папку, cat печатает файл. Длинные имена за тебя добьёт Tab — "
               "и пробелы в них прикроет сам.")
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
    # новичок 24.10: «как сдавать — ans нет?», «как строить путь вверх и вбок»; cd - и ; —
    # лишнее в уроке (; — только в шпаргалке), && — одной строкой: он нужен со следующих задач
    scroll = (".. — папка на уровень выше. cd .. — подняться на этаж, cd ../.. — на два, "
              "cd ../other — подняться и войти в соседнюю other. cd без аргумента (слова "
              "после команды) — домой.\n"
              "Сдавать ответ не надо: засчитается, когда встанешь в нужную папку.\n"
              "cd .. && ls — две команды одной строкой: && пускает вторую, только если первая "
              "удалась; cd .. ; ls — ; пускает вторую в любом случае.")
    variants = (
        Variant("Ты стоишь в archive/{year}/q3/docs. Поднимись на три уровня вверх — "
                "в саму папку archive — одной командой (тремя cd .. тоже засчитается, но "
                "попробуй одной). Сдавать ничего не надо: засчитается, когда встанешь в "
                "archive.",
                wrong=("cd ..", "cd ../.."),
                alternatives=("cd .. трижды — верно, но три команды вместо одной",)),
        Variant("Ты стоишь в archive/{year}/q3. Перейди в соседнюю ветку archive/other: два "
                "шага вверх и сразу вбок — одной командой. Сдавать ничего не надо: "
                "засчитается, когда встанешь в other.",
                hints=("Сначала посчитай, сколько раз нужно подняться до archive.",
                       "Вверх — .., а после подъёма путь можно продолжить: ../../имя",
                       "cd ../../other"),
                solution="cd ../../other",
                wrong=("cd ../other", "cd ../.."),
                alternatives=("cd ../.. && cd other — то же в две команды",),
                explain="После подъёма путь продолжается: ../../other — два этажа вверх и "
                        "сразу вбок, одной строкой."),
        Variant("Забрёл глубоко в archive/{year}/q3/docs. Вернись в свою домашнюю папку "
                "самой короткой командой. Сдавать ничего не надо: засчитается, когда "
                "окажешься дома.",
                hints=("Домашняя папка — это ~, и путь к ней знать не нужно.",
                       "У cd есть особый случай: без аргумента он ведёт домой.",
                       "cd"),
                solution="cd",
                wrong=("cd ../../../..", "cd /"),
                alternatives=("cd ~ — то же самое: ~ — короткое имя домашней папки",),
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
    # новичок 24.10: «как набрать ~», «cp SOURCE DEST — куда это сюда?»; cd - задаче не нужен
    scroll = ("~ (тильда: Shift и клавиша с ~ слева от 1 или от Z) — твоя домашняя папка. "
              "cat ~/FILE — файл из дома, где бы ты ни стоял (FILE — сюда имя файла).\n"
              "В игре ~ — дом песочницы (путь кончается на .termit/home), а не твоя настоящая "
              "домашняя папка.\n"
              "cp SOURCE DEST — копия: SOURCE — что копировать, DEST — имя копии. Слово из "
              "вывода сдай: двойной щелчок по нему, Cmd+C, потом ans, пробел и Cmd+V.")
    variants = (
        Variant("У тебя в домашней папке лежит записка ~/memo.txt. Прочти её, не уходя "
                "отсюда. Ответ — слово из записки: ans WORD — вместо WORD вставь это слово.",
                wrong=("cat memo.txt",),
                alternatives=("cd ~ && cat memo.txt — сходить домой и прочесть там",)),
        # копия, а не ответ: решено, когда здесь появилась точная копия, а дома — оригинал
        Variant("Записка ~/memo.txt нужна здесь, в текущей папке. Сделай её копию сюда "
                "командой cp SOURCE DEST: SOURCE — что копировать, DEST — имя копии (здесь "
                "просто memo.txt). Оригинал пусть остаётся дома, сдавать ничего не надо.",
                hints=("~ — домашняя папка: до файла можно дотянуться, не уходя отсюда.",
                       "DEST — имя копии здесь: просто memo.txt, без папки впереди.",
                       "cp ~/memo.txt memo.txt"),
                # FB18: точку «сюда» объясняют позже (copy_move) — здесь имя
                solution="cp ~/memo.txt memo.txt", solution_script="cp ~/memo.txt memo.txt",
                wrong=("mv ~/memo.txt memo.txt", "cat ~/memo.txt"),
                alternatives=("cp ~/memo.txt . — короче: точка значит «сюда», про неё — в "
                              "задаче про копии и перенос",)),
        Variant("Дома, в подпапке notes, лежит today.txt. Прочти его отсюда, никуда не "
                "переходя, и сдай слово: ans WORD — вместо WORD вставь это слово.",
                hints=("~ работает и с вложенными папками: путь продолжается после ~/.",
                       "Путь до файла: ~/notes/today.txt — читай его cat.",
                       "cat ~/notes/today.txt, затем ans WORD"),
                solution="cat ~/notes/today.txt",
                solution_script="cat ~/notes/today.txt | cut -d: -f2",
                wrong=("cat notes/today.txt | cut -d: -f2", "cat ~/today.txt | cut -d: -f2"),
                alternatives=("cd ~/notes && cat today.txt — сходить в папку и прочесть "
                              "там",)),
    )
    par = 25
    hints = ("Значок ~ означает домашнюю папку.",
             "Можно не ходить домой: cat ~/memo.txt",
             "cat ~/memo.txt, затем ans WORD (двойной щелчок по слову выделит его)")
    solution = "cat ~/memo.txt"
    solution_script = "cat ~/memo.txt | cut -d: -f2"
    explain = "~ — короткая запись пути домой: файл из дома достаётся откуда угодно, без походов."
    spell = "~ — домашняя папка; cat ~/файл — файл из дома откуда угодно"
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
    scroll = ("ls -la — все файлы, и скрытые (точка в начале — часть имени, не команда), с "
              "датами. Первые строки . и .. — не файлы: . — эта самая папка, .. — папка выше.\n"
              "Буквы после минуса — флаги: меняют поведение команды. -l — long, подробно, "
              "-a — all, все; -la = -l -a.\n"
              "Регистр (большие или маленькие буквы) важен: ls -A — almost all, всё, кроме "
              ". и ..")
    variants = (
        Variant("В этой папке есть скрытый файл. Найди его и назови слово, что в нём "
                "записано: ans WORD — вместо WORD вставь это слово.",
                wrong=("cat .old_cache",),
                alternatives=("ls -a — без подробностей, только имена",)),
        Variant("Обычный ls показывает не всё: здесь спрятана целая папка, а в ней записка. "
                "Прочти её и сдай слово: ans WORD — вместо WORD вставь это слово.",
                hints=("Скрытой бывает и папка — имя тоже начинается с точки.",
                       "ls -la покажет её: у папки строка начинается с буквы d. Имя с "
                       "точкой, например .stash, — это имя папки, а не команда; что внутри, "
                       "покажет ls -la .stash",
                       "ls -la, затем cat .stash/note.txt — и ans WORD"),
                solution="ls -la && cat .stash/note.txt",
                solution_script="cat .stash/note.txt",
                wrong=("cat .secret",),
                alternatives=("ls -la .stash — показать, что лежит в скрытой папке .stash, "
                              "не заходя в неё",)),
        Variant("Сколько скрытых файлов в папке {folder}? Строки . и .. не считай; скрытых "
                "папок там нет, только файлы. Сдай число: ans NUMBER — вместо NUMBER впиши его.",
                hints=("Скрытые файлы покажет ls -la, имя у них начинается с точки.",
                       "Строки . и .. — не файлы: . — эта самая папка, .. — папка выше; их "
                       "не считай (или смотри ls -A — он их не показывает).",
                       "ls -la {folder} — сосчитай строки с точкой, кроме . и .., и ans NUMBER"),
                solution="ls -la {folder}",
                solution_script="ls -A {folder} | grep -c '^[.]'",
                wrong=("ls -a {folder} | grep -c '^[.]'",),
                alternatives=("ls -A {folder} — то же без . и .., считать проще",)),
    )
    par = 30
    hints = ("Скрытые файлы начинаются с точки, обычный ls их не показывает.",
             "ls -la покажет всё.",
             "ls -la, затем cat .secret — и ans WORD")
    solution = "ls -la && cat .secret"
    solution_script = "cat .secret"
    explain = "Файлы с точкой в начале скрыты; флаг -a показывает их, -l — подробности."
    spell = "ls -la — все файлы, включая скрытые, с подробностями"
    trap_messages = {
        "old": "Это .old_cache — старая копия, обманка. Слово лежит в другом скрытом файле.",
        "secret": "Это .secret — пустышка. Записка — в скрытой папке: ls -la покажет и её.",
        "stashdir": "Это имя скрытой папки, а нужно слово из записки, что лежит в ней.",
        "dots": "Посчитаны и строки . и .. — а это не файлы: . — эта самая папка, .. — папка "
                "уровнем выше, они есть в каждой папке, даже в пустой. Их не считают; ls -A "
                "покажет всё без них.",
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
    scroll = ("Скрипт — текстовый файл с командами. ./FILE — запустить файл FILE из текущей "
              "папки (без ./ терминал ищет программу среди установленных). chmod +x FILE — "
              "дать файлу право на запуск (разрешить файлу запускаться). FILE — сюда подставь имя "
              "своего файла.")
    # «decode.sh без ./» — тоже неверно, но это command not found: D004 счёл бы такое
    # решение сломанным само по себе. Ловушки — «без chmod» и «не из той папки».
    # Новичок 24.10: «ans WORD» кириллицей, вариант 1 без урока про ./папка/файл, вариант 2
    # «право уже есть» спорил с шагами общего урока — у вариантов 1 и 2 свои уроки.
    variants = (
        Variant("Здесь лежит скрипт decode.sh. Дай ему право на запуск и запусти — он "
                "напечатает слово. Сдай его: ans WORD (WORD — сюда подставь это слово)",
                wrong=("./decode.sh",),
                alternatives=("sh decode.sh — sh прочтёт файл и без права на запуск",
                              "chmod +x decode.sh && ans $(./decode.sh) — сдать вывод "
                              "скрипта сразу")),
        Variant("Скрипт decode.sh лежит в папке tools. Дай ему право на запуск и запусти "
                "отсюда, не заходя в tools. Слово, которое он выведет, сдай: ans WORD — вместо "
                "WORD это слово.",
                hints=("Заходить в папку не обязательно: путь к скрипту пишется целиком.",
                       "Право — chmod +x tools/decode.sh, запуск — ./tools/decode.sh",
                       "chmod +x tools/decode.sh && ./tools/decode.sh — и ans WORD"),
                solution="chmod +x tools/decode.sh && ./tools/decode.sh",
                wrong=("./tools/decode.sh", "chmod +x tools/decode.sh && ./decode.sh"),
                alternatives=("sh tools/decode.sh — без права на запуск",
                              "chmod +x tools/decode.sh && ans $(./tools/decode.sh) — сдать "
                              "вывод сразу")),
        Variant("В папке bin — скрипт decode.sh, право на запуск у него уже есть, chmod не "
                "нужен. Но слово он печатает, только если ты стоишь в папке bin. Добудь "
                "слово и сдай: ans WORD (WORD — сюда подставь это слово)",
                hints=("Скрипт ищет свои данные в текущей папке — стоять нужно рядом с ним.",
                       "Сначала cd bin, потом ./decode.sh.",
                       "cd bin && ./decode.sh — и ans WORD"),
                solution="cd bin && ./decode.sh",
                wrong=("./bin/decode.sh", "sh bin/decode.sh"),
                alternatives=("cd bin && ans $(./decode.sh) — сдать вывод сразу",)),
    )
    par = 40
    hints = ("Файл нельзя запустить, пока у него нет права на запуск.",
             "Право даёт chmod +x decode.sh, запуск — ./decode.sh",
             "chmod +x decode.sh && ./decode.sh — и ans WORD")
    solution = "chmod +x decode.sh && ./decode.sh"
    explain = ("./ — «отсюда»: без него zsh ищет команду среди установленных программ. "
               "chmod +x даёт право на запуск.")
    spell = "./FILE — запустить файл отсюда; chmod +x FILE — разрешить запуск"
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
        Variant("Выгрузке за месяц {month} {year} года нужен дом: data/{year}/{month}/raw. "
                "Папки data и data/{year} уже есть, остального нет. Проложи путь за один "
                "заход.",
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
    # новичок 24.10: «его копию — draft или final?», «одной командой или двумя?»; SOURCE DEST
    scroll = ("cp SOURCE DEST — копия, mv SOURCE DEST — перенос (SOURCE — что, DEST — куда). "
              "mv старое новое — переименование. Перенос с новым именем: mv a.txt "
              "folder/b.txt\n"
              "Несколько файлов за раз: mv a.txt b.txt folder/ — перечисли их через пробел, "
              "а последней в строке поставь папку. cp умеет так же.\n"
              "Сюда, где стоишь, — точка: cp inbox/a.txt . (та самая «эта самая папка» из "
              "урока про скрытые файлы).")
    variants = (
        Variant("Сделай копию contract.txt в папку backup/, а черновик draft.txt перенеси "
                "в archive/ и назови там contract_v2.txt. Нужны две команды: cp для копии и "
                "один mv — он перенесёт и переименует сразу.",
                wrong=("mv contract.txt backup/ && mv draft.txt archive/contract_v2.txt",),
                alternatives=("cp contract.txt backup/contract.txt — имя в пути назначения "
                              "можно написать и явно",)),
        Variant("Черновик готов: переименуй draft.txt прямо здесь в final.txt, а копию "
                "готового final.txt положи в backup/{year}/ — папка уже есть. Нужны две "
                "команды: сначала mv, потом cp.",
                hints=("Переименование — тот же mv, только без папки в пути назначения.",
                       "Сначала mv draft.txt final.txt, потом cp готового файла в папку копий.",
                       "mv draft.txt final.txt && cp final.txt backup/{year}/"),
                solution="mv draft.txt final.txt && cp final.txt backup/{year}/",
                wrong=("cp draft.txt final.txt && cp final.txt backup/{year}/",
                       "mv draft.txt final.txt && mv final.txt backup/{year}/"),
                alternatives=("cp draft.txt backup/{year}/final.txt && mv draft.txt final.txt "
                              "— сначала копия, потом имя",)),
        Variant("Таблицы {a}.csv, {b}.csv и index.csv лежат в inbox/, а нужны здесь, в этой "
                "папке. {a}.csv и {b}.csv перенеси сюда, а index.csv — копией: в inbox/ он "
                "тоже нужен.",
                hints=("Две таблицы переносит mv, а для index.csv нужен cp — оригинал останется.",
                       "«Сюда, где стоишь» в команде пишут точкой: последней в строке — . "
                       "вместо папки.",
                       "mv inbox/{a}.csv inbox/{b}.csv . && cp inbox/index.csv ."),
                solution="mv inbox/{a}.csv inbox/{b}.csv . && cp inbox/index.csv .",
                wrong=("mv inbox/{a}.csv inbox/{b}.csv inbox/index.csv .",
                       "cp inbox/{a}.csv inbox/{b}.csv inbox/index.csv ."),
                alternatives=("cp inbox/index.csv . && mv inbox/{a}.csv inbox/{b}.csv . — "
                              "порядок не важен",
                              "mv inbox/{a}.csv inbox/{b}.csv ./ — ./ значит то же, что .")),
    )
    par = 45
    hints = ("Копирует cp, переносит и переименовывает mv.",
             "cp contract.txt backup/ — копия; mv умеет перенести и сразу переименовать.",
             "cp contract.txt backup/ && mv draft.txt archive/contract_v2.txt")
    solution = "cp contract.txt backup/ && mv draft.txt archive/contract_v2.txt"
    explain = ("cp оригинал оставляет, mv — забирает с собой; новое имя в конце пути — сразу "
               "и переименование. Несколько файлов — одной командой: mv a.csv b.csv data/ "
               "(последней идёт папка), отдельная команда на каждый файл не нужна.")
    spell = "cp SOURCE DEST — копия; mv SOURCE DEST — перенос и переименование"

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
            sha = {n: kit.sha(kit.write(box / "inbox" / n, f"id,{n}\n{rng.randint(1, 99)},x\n"))
                   for n in names}
            kit.write(box / "inbox" / "notes.txt", "Not a table.\n")
            want = {n: sha[n] for n in names}
            want["inbox/index.csv"] = sha["index.csv"]
            return {"a": a, "b": b, "csv": names, "want": want,
                    "gone": [f"inbox/{a}.csv", f"inbox/{b}.csv"]}
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

    def parts_for(self, state):
        """FB5 п. 68: «сделал копию — игра молчит». Каждый нужный файл и каждое убранное имя."""
        return ([f"{rel} на месте" for rel in state["want"]]
                + [f"{rel} убран со старого места" for rel in state["gone"]])

    def progress(self, ctx):
        b, s = ctx.box, ctx.state
        return ([kit.sha_in_box(b, rel) == h for rel, h in s["want"].items()]
                + [not (b / rel).exists() for rel in s["gone"]])

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
              "file NAME — что внутри на самом деле: текст (file ответит text), картинка, "
              "архив (NAME — имя файла). ext — копилка: что значат расширения, что тебе уже попадались.")
    variants = (
        Variant("Здесь, в этой папке, свалены файлы разного сорта — ls их покажет. Какой из "
                "них — таблица с данными? Сдай его полное имя, вместе с "
                "расширением: ans NAME — вместо NAME вставь имя.",
                hints=("Что значит расширение, подскажет ext; список файлов — ls.",
                       ".csv — таблица: строки, поля через запятую.",
                       "ls — найди файл .csv, file NAME.csv подтвердит: CSV text. Сдай имя: "
                       "ans NAME.csv"),
                solution="ls && file {name}.csv", solution_script="ls *.csv",
                wrong=("ls *.json",),
                alternatives=("ext — копилка расширений скажет, что .csv — это таблица",)),
        Variant("Нужна записка — файл с именем {stem} и расширением .txt; в ней слово. Рядом "
                "лежит её старая резервная копия (.bak — backup, «запасная копия»), слово в "
                "ней устарело. Прочти записку и сдай слово: ans WORD — вместо WORD вставь "
                "слово.",
                hints=("Расширение — часть имени: файла с именем ровно {stem} здесь нет.",
                       "ls покажет полные имена. .bak — резервная копия (что значит "
                       "расширение, подскажет ext).",
                       "ls, затем cat {stem}.txt — и ans WORD"),
                solution="ls && cat {stem}.txt", solution_script="cat {stem}.txt | cut -d: -f2",
                wrong=("cat {stem}.bak | cut -d: -f2",),
                alternatives=("двойной щелчок по слову в выводе cat, Cmd+C, потом ans, пробел "
                              "и Cmd+V — слово не перепечатывать",),
                explain="Расширение — часть имени: cat без .txt ищет файл ровно с таким "
                        "именем и не находит. ls показывает полные имена, а .bak — старая "
                        "копия."),
        Variant("В папке {folder} три файла без расширений: {a}, {b} и {c}. Только один из них "
                "— текст, остальные — картинка и архив. Узнай командой file, какой текстовый "
                "(file ответит text): войди в папку cd {folder} или пиши путь {folder}/имя. "
                "Сдай слово из него: ans WORD — вместо WORD вставь "
                "слово.",
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
             "ls — найди файл .csv и сдай его имя: ans NAME.csv")
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
    # заголовок JFIF и конец снимка: file узнаёт JPEG, cat печатает мусор
    JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")

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
                 "server.log": "12:00 start\n"}
        for fname, body in files.items():
            kit.write(box / fname, body)
        # практик 25.10: заглушки-тексты file звал ASCII text — урок обещал картинку и архив
        (box / "photo.jpg").write_bytes(self.JPEG)
        packed = io.BytesIO()
        with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("old_notes.txt", "Old notes.\n" * 3)
        (box / "backup.zip").write_bytes(packed.getvalue())
        traps = [["stem", name]] + [["other", f] for f in [*files, "photo.jpg", "backup.zip"]
                                    if not f.endswith(".csv")]
        return {"name": name, "answer": f"{name}.csv", "traps": traps}


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
        Variant("Здесь главы chapter1.txt, chapter2.txt и дальше по порядку до chapter{n}.txt. "
                "Перенеси в part1/ только главы с однозначным номером — ровно одна цифра "
                "после chapter.",
                wrong=("mv chapter*.txt part1/",),
                alternatives=("mv chapter[1-9].txt part1/ — диапазон цифр в скобках",)),
        Variant("Скопируй в short/ все .txt, у которых имя до .txt ровно из трёх букв (как "
                "abc.txt) — не короче и не длиннее. Оригиналы пусть остаются на месте.",
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
        Variant("Ты стоишь там, где лежат две папки: archive и collected. archive — свалка: "
                "отчёты .pdf разбросаны по её вложенным папкам. Скопируй все .pdf в collected "
                "— все файлы прямо в неё, без подпапок (cp так и кладёт). Оригиналы пусть "
                "остаются на местах.",
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
                "Где именно — неизвестно. Скопируй его сюда, в текущую папку: «сюда» — это "
                "точка последним словом команды.",
                hints=("Путь неизвестен, а имя — да: ** найдёт файл на любой глубине.",
                       "notes/**/{name} — от папки notes вниз; скрытые — с (D). Проверь ls.",
                       "ls notes/**/{name}(D) — проверить, затем cp notes/**/{name}(D) ."),
                solution="cp notes/**/{name}(D) .",
                # cp /**/… (маска от корня) в wrong не гоняем: обход всего диска — минуты;
                # отклик на него проверяет tests/test_fb18_early.py
                wrong=("cp notes/{name} .", "cp notes/**/{name} ."),
                alternatives=("ls -R notes — всё дерево: где лежит файл, видно глазами",),
                explain="Имя известно, путь — нет: notes/**/NAME ищет от папки notes на "
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

    MSG_ROOT = ("/ в начале пути — корень всего Mac, а не эта папка: туда задание не пускает. "
                "Убери / впереди — **/NAME ищет отсюда вглубь (NAME — имя файла).")
    MSG_NO_DEST = ("cp не знает, куда копировать: последним словом нужно место. Сюда, в "
                   "текущую папку, — точка: cp SOURCE . (SOURCE — что копируешь)")

    def _slip(self, ctx) -> Optional[str]:
        """FB18: промахи владельца — маска от корня (/**) и cp без «куда»."""
        last = ctx.cmds[-1].line.split() if ctx.cmds else []
        if any(w.startswith("/**") for w in last[1:]):
            return self.MSG_ROOT
        if last[:1] == ["cp"] and len([w for w in last[1:] if not w.startswith("-")]) == 1:
            return self.MSG_NO_DEST
        return None

    def check(self, ctx):
        verdict = self._check(ctx)
        if verdict.solved or verdict.message:
            return verdict
        return Verdict(False, self._slip(ctx)) if self._slip(ctx) else verdict

    def _check(self, ctx):
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
              "Папку голый rm не удаляет. rm -r DIR — папку DIR со всем содержимым, и скрытым "
              "тоже: -r — recursive (рекурсивно, вглубь). Навсегда, мимо Корзины.\n"
              "Привычка: сначала ls с той же маской (или ls -aR DIR — со скрытым) — "
              "посмотреть, что исчезнет, — и только потом rm. При успехе rm молчит.")
    variants = (
        Variant("Ты стоишь в папке сборки. Сотри все файлы *.tmp — отсюда и на любой глубине, "
                "в том числе в скрытых папках. Всё остальное не трогай.",
                wrong=("rm *.tmp", "rm **/*.tmp"),
                alternatives=("ls **/*.tmp(D) && rm **/*.tmp(D) — с проверкой",)),
        Variant("Ты стоишь там, где лежат две папки: project и trash. В project на любой "
                "глубине валяются временные файлы *.tmp — есть они и в скрытых папках. Сотри "
                "их все, остальное в project не трогай. А папку trash удали целиком, со всем, "
                "что внутри.",
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
                              "ls -aR trash — что исчезнет вместе с папкой, и скрытое тоже"),
                explain="rm берёт те же маски, что ls: **/*.tmp(D) — на любой глубине, со "
                        "скрытыми. rm -r удаляет папку со всем, что внутри. Сначала ls той "
                        "же маской."),
        Variant("Папка old — старый проект: внутри вложенные папки и скрытые файлы. Снеси её "
                "целиком одной командой — со всем, что внутри, и скрытым тоже. Соседнюю new "
                "не трогай.",
                hints=("Голый rm папку не удаляет — ему нужен флаг.",
                       "-r — со всем содержимым, на любую глубину. Сначала посмотри, что "
                       "исчезнет, со скрытым: ls -aR old",
                       "ls -aR old — проверить, затем rm -r old"),
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
    spell = "rm **/*.tmp(D) — удалить по маске вглубь; rm -r DIR — папку целиком"
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


# --- FB4: уроки навигации по терминалу (FB18: места — в TASKS внизу) ------------------------
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
    # новичок 24.10: «чем править букву в начале», «пресет — заклинание», Ctrl+K и Ctrl+U
    # здесь не нужны (они — в «Кармане деки»)
    scroll = ("↑ — прошлая команда из истории (история — список команд, что ты уже набирал). "
              "Ctrl+A / Ctrl+E — в начало / в конец строки, ← → — на букву, Option+← → — "
              "через слово.\n"
              "Backspace — стереть букву слева от курсора. Ctrl+W — стереть слово слева (W — "
              "Word); точка, _, / и - тоже могут обрывать слово — тогда жми ещё.")
    variants = (
        Variant("Последнюю команду в истории набрали с опечаткой в самом начале — mkdri "
                "вместо mkdir (mkdir — make directory, «создай папки»), и она не сработала. Не "
                "перепечатывай: ↑ вернёт строку, Ctrl+A прыгнет в её начало. Стрелкой → дойди "
                "до конца слова mkdri, Backspace сотри две последние буквы, набери ir и нажми "
                "Enter.",
                wrong=("mkdir -p archive/{year}/reports/q1",),
                alternatives=("Ctrl+A, Option+→ — курсор за первым словом; Ctrl+W сотрёт его, "
                              "остаётся набрать mkdir",)),
        Variant("Последняя команда в истории копирует три отчёта (cp — copy, «скопируй»: "
                "сначала что, последним словом — куда) в папку shared/, но такой папки нет — "
                "нужна outbox/ (она уже есть). Верни строку стрелкой ↑, сотри последнее "
                "слово Ctrl+W, допиши outbox/ и нажми Enter.",
                hints=("Строка уже набрана — она в истории: ↑ вернёт её целиком.",
                       "Курсор после ↑ стоит в конце: Ctrl+W стирает слово слева от него. "
                       "Стёрлось не всё — нажми ещё раз.",
                       "↑, Ctrl+W, допиши outbox/ и Enter"),
                solution="↑, Ctrl+W, допиши outbox/, Enter",
                solution_script=("cp reports/{year}/summary.txt reports/{year}/figures.csv "
                                 "reports/{year}/notes.txt outbox/"),
                wrong=("cp reports/{year}/summary.txt outbox/",),
                alternatives=("↑ и Backspace по букве, пока не уйдёт shared/, — тоже верно, "
                              "но дольше",)),
        Variant("Последняя команда в истории переносит в archive/ четыре файла (mv — move, "
                "«перенеси»: сначала что, последним словом — куда), но фото {photo} должно "
                "остаться в inbox. Достань строку (↑), прыжками Option+← встань перед inbox/ "
                "файла, что идёт сразу после фото, стирай Ctrl+W, пока путь inbox/{photo} не "
                "исчезнет целиком, и нажми Enter. Option — клавиша ⌥ рядом с Cmd.",
                hints=("Строка — в истории: ↑. Перепечатывать её не нужно.",
                       "Option+← прыгает через слово влево. Встань в начало имени после фото и "
                       "жми Ctrl+W, пока путь фото не исчезнет: точка и _ обрывают слово, за "
                       "раз уходит кусок.",
                       "↑, Option+← до начала имени после фото, Ctrl+W — пока путь фото не "
                       "исчезнет, Enter"),
                solution="↑, Option+← до начала имени после фото, Ctrl+W — пока путь фото не "
                         "исчезнет, Enter",
                solution_script=("mv inbox/report_{year}.txt inbox/budget_{year}.csv "
                                 "inbox/contacts.txt archive/"),
                wrong=("mv inbox/report_{year}.txt inbox/budget_{year}.csv inbox/{photo} "
                       "inbox/contacts.txt archive/",),
                alternatives=("набрать строку заново без фото — тоже верно, но долго",)),
    )
    par = 40
    hints = ("Строка уже набрана — она в истории: ↑ вернёт её целиком.",
             "Опечатка в самом начале: Ctrl+A прыгает в начало строки, там исправь.",
             "↑, Ctrl+A, стрелка вправо до конца mkdri, Backspace дважды, набери ir и Enter")
    solution = "↑, Ctrl+A, стрелка вправо до конца mkdri, Backspace дважды, набери ir, Enter"
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


class CursorClip(AnswerTask):
    """FB13 (FB5 п. 47), FB18: мышь и курсор — «курсор ведёт себя не как в Ворде». Строка
    ввода и вывод — разные зоны: курсор живёт только в строке, Option+клик ставит его туда
    (вариант 0); мышью из вывода копируют — двойной клик берёт слово (1), тройной — строку
    (2), Cmd+C и Cmd+V. Карман zsh — отдельная задача cut_paste, pbcopy — pbcopy_list (после
    трубы). id прежний: решённое владельцем «Курсор и буфер» остаётся решённым. Проверка —
    по результату: файлы (0) или сданный ответ (1, 2)."""
    id = "cursor_clip"
    track = "basics"
    title = "Мышь и курсор"
    start_dir = "{start}"
    scroll = ("Курсор — только в строке ввода: Option+клик ставит его туда, куда кликнул "
              "(iTerm2: галочка Option-Click moves cursor). Всё, что выше, — вывод: его читают "
              "и копируют, но не правят.\n"
              "Копировать из вывода мышью: двойной клик — слово, тройной — вся строка; Cmd+C — "
              "скопировать, Cmd+V — вставить в строку ввода.")
    variants = (
        Variant("Последняя команда в истории копирует в outbox/ три черновика (cp — copy, "
                "«скопируй»: сначала что, последним словом — куда), но в середине строки "
                "опечатка: invoce вместо invoice — не хватает буквы i. Верни строку (↑), "
                "Option+кликом по букве c поставь курсор перед ней, набери i и нажми Enter. Промахнулся "
                "на букву — подвинь курсор стрелкой ← или →.",
                wrong=("cp drafts/{year}/contract_final.txt outbox/",),
                alternatives=("↑ и Option+← прыжками до опечатки — тоже верно",)),
        Variant("Код доступа лежит в переменной ACCESS_CODE — длинный, из букв и цифр. "
                "Выведи его: echo $ACCESS_CODE. Не перепечатывай: дважды кликни по коду — он "
                "выделится, Cmd+C — скопирован. Набери ans и пробел, вставь Cmd+V и нажми "
                "Enter.",
                hints=("Код печатает echo $ACCESS_CODE. Набирать его руками не нужно.",
                       "Двойной клик выделяет слово целиком — код без пробелов, это одно слово. "
                       "Потом Cmd+C.",
                       "echo $ACCESS_CODE, двойной клик по коду, Cmd+C, ans, пробел, Cmd+V, "
                       "Enter"),
                solution="echo $ACCESS_CODE, двойной клик, Cmd+C, ans и Cmd+V",
                solution_script="echo $ACCESS_CODE",
                wrong=("echo {decoy}",),
                alternatives=("ans $ACCESS_CODE — $ подставит код сам, без мыши",)),
        Variant("Тебя забросило в глубокую папку. Сдай её полный путь, не перепечатывая: "
                "pwd напечатает его, тройной клик по строке выделит её целиком, Cmd+C — "
                "скопирует. Набери ans и пробел, вставь Cmd+V и нажми Enter.",
                hints=("Путь печатает pwd. Набирать его руками не нужно.",
                       "Тройной клик выделяет всю строку вывода — путь целиком. Потом Cmd+C.",
                       "pwd, тройной клик по пути, Cmd+C, ans, пробел, Cmd+V, Enter"),
                solution="pwd, тройной клик, Cmd+C, ans и Cmd+V",
                solution_script="pwd",
                wrong=("echo {decoy}",),
                alternatives=("ans $(pwd) — $( ) подставит путь сам, без мыши",)),
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
               "Вывод выше не правят, а копируют: двойной клик — слово, тройной — строка, "
               "Cmd+C и Cmd+V.")
    spell = ("Option+клик — курсор в строку; двойной клик — слово, тройной — строка; "
             "Cmd+C — скопировать, Cmd+V — вставить")
    trap_messages = {"decoy": "Это не тот текст — скопируй то, что напечатала команда из "
                              "задания."}

    def env_for(self, state):
        code = state.get("code")
        return {"ACCESS_CODE": code} if code else {}

    def expected(self, state):
        """Код и путь игрок и должен видеть (echo $ACCESS_CODE, pwd), поэтому они лежат не под
        секретным ключом answer: код — в окружении задачи, путь — её стартовая папка."""
        return str(state.get("code") or state.get("where") or state["answer"])

    def takes_answer(self, state):
        return "want" not in state

    def answer_kind(self, state):
        return "path" if state.get("mode") == "path" else "text"

    def setup_variant(self, box, rng, variant):
        year = str(rng.randint(2724, 2726))
        decoy = kit.word(rng)
        if variant == 1:
            alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
            code = "".join(rng.choice(alphabet) for _ in range(20))
            return {"year": year, "start": ".", "code": code,
                    "decoy": decoy, "traps": [["decoy", decoy]]}
        if variant == 2:
            start = f"archive/{year}/clients/{kit.latin(rng)}/contracts"
            (box / start).mkdir(parents=True)
            kit.write(box / start / "readme.txt", "Signed contracts.\n")
            return {"year": year, "start": start, "where": start, "mode": "path",
                    "decoy": decoy, "traps": [["decoy", decoy]]}
        fill = list(rng.sample(FILLER, 8))
        want = {}
        (box / "outbox").mkdir()
        (box / ".termit").mkdir(exist_ok=True)      # история песочницы — в .termit
        for name in ("contract_final.txt", "invoice_final.txt", "letter_final.txt"):
            f = kit.write(box / "drafts" / year / name, f"{name}: {kit.word(rng)}\n")
            want[f"outbox/{name}"] = kit.sha(f)
        _history(box, fill + [f"cp drafts/{year}/contract_final.txt "
                              f"drafts/{year}/invoce_final.txt "
                              f"drafts/{year}/letter_final.txt outbox/"])
        return {"year": year, "start": ".", "want": want}

    def check(self, ctx):
        if "want" in ctx.state:
            return _files_check(ctx)
        return super().check(ctx)


class CutPaste(Task):
    """FB18 (FB5 п. 47, часть «вырезать и вставить»): карман zsh. Ctrl+W/U/K не теряют стёртое,
    а кладут в карман; Ctrl+Y вставляет его туда, где курсор, сколько угодно раз. Это не буфер
    обмена Mac. Строка заготовлена в истории; проверка — по результату (файлы)."""
    id = "cut_paste"
    track = "basics"
    title = "Карман zsh"
    # новичок 24.10: Ctrl+K, Esc y, Ctrl+_ — лишнее; «как не перебрать Ctrl+W»; «Option+→
    # дважды» зависит от настройки — до места ведут стрелкой, «пока не…»
    scroll = ("Карман zsh — куда zsh откладывает стёртое: Ctrl+W текст не теряет, а кладёт "
              "туда.\n"
              "Ctrl+Y — вставить из кармана, где курсор (Y — Yank), хоть много раз.\n"
              "Карман — не буфер обмена Mac: Cmd+V его не видит. Ctrl+K (K — Kill) тоже "
              "стирает в карман — всё справа от курсора.")
    variants = (
        Variant("Сделай запасную копию отчёта quarterly_report_{year}.txt в этой же папке под "
                "именем quarterly_report_{year}.txt.bak. Хвост .bak (от backup — «запасная "
                "копия») — обычная пометка: это копия на всякий случай, оригинал можно "
                "править смело.\n"
                "Команда уже начата и лежит в истории: cp quarterly_report_{year}.txt. cp "
                "(copy — «скопируй») ждёт два слова: что копировать и куда. Второго нет — его "
                "и допиши. Длинное имя не перепечатывай, возьми из кармана: ↑, Ctrl+W — имя "
                "ушло в карман, Ctrl+Y — вернулось, пробел, ещё раз Ctrl+Y, допиши .bak и "
                "Enter.\n"
                "Ctrl+W рвёт имя на точке и _ — жми, пока оно не сотрётся целиком, но не "
                "дальше: «cp » оставь. Куски, стёртые подряд, лягут в карман одним именем.",
                wrong=("cp quarterly_report_{year}.txt copy.txt",),
                alternatives=("↑, пробел и набрать имя заново с .bak — верно, но долго",)),
        Variant("Последняя команда в истории переносит отчёт в outbox/ (mv — move, "
                "«перенеси»: сначала что, потом куда), но слова перепутаны: сначала папка, "
                "потом файл. Переставь их через карман: ↑, Ctrl+W — вырезать имя файла (жми, "
                "пока не уйдёт целиком), Option+← — к началу outbox/ (Option — клавиша ⌥), "
                "Ctrl+Y — вставить, пробел, Enter.",
                hints=("Строка — в истории: ↑. Порядок у mv такой: что переносим, потом куда.",
                       "Ctrl+W вырезает слово слева и кладёт его в карман zsh; Ctrl+Y вставляет "
                       "его там, где курсор.",
                       "↑, Ctrl+W до конца имени, Option+←, Ctrl+Y, пробел, Enter"),
                solution="↑, Ctrl+W до конца имени, Option+←, Ctrl+Y, пробел, Enter",
                solution_script="mv report_{year}.txt outbox/",
                wrong=("mv outbox/ report_{year}.txt",),
                alternatives=("набрать mv report_{year}.txt outbox/ заново — верно, но "
                              "дольше",)),
        Variant("Последняя команда в истории переносит два файла (mv — move, «перенеси»), но "
                "папка outbox/ стоит первой, а должна быть последней. Унеси её в конец через "
                "карман: ↑, Ctrl+A, стрелкой → встань сразу за outbox/, жми Ctrl+W, пока "
                "outbox/ не уйдёт в карман целиком, Ctrl+E — в конец, пробел, Ctrl+Y и Enter.",
                hints=("Строка — в истории: ↑. Последним словом у mv идёт папка — куда.",
                       "Курсор встань сразу за outbox/ и жми Ctrl+W, пока слово не уйдёт "
                       "целиком: оно ляжет в карман. Ctrl+E унесёт курсор в конец, Ctrl+Y "
                       "выложит слово там.",
                       "↑, Ctrl+A, стрелка вправо до конца outbox/, Ctrl+W до конца слова, Ctrl+E, пробел, "
                       "Ctrl+Y, Enter"),
                solution="↑, Ctrl+A, стрелка вправо до конца outbox/, Ctrl+W до конца слова, Ctrl+E, пробел, "
                         "Ctrl+Y, Enter",
                solution_script="mv report_{year}.txt notes_{year}.txt outbox/",
                wrong=("mv outbox/ report_{year}.txt notes_{year}.txt",),
                alternatives=("набрать строку заново в нужном порядке — верно, но дольше",)),
    )
    par = 40
    hints = ("Строка уже набрана — она в истории: ↑ вернёт её целиком.",
             "Ctrl+W кладёт стёртое в карман, а Ctrl+Y выкладывает его — хоть два раза "
             "подряд. Имя уходит кусками (точка и _ обрывают слово) — жми Ctrl+W, пока "
             "не сотрётся всё: куски лягут в карман одним целым.",
             "↑, Ctrl+W до конца имени, Ctrl+Y, пробел, Ctrl+Y, допиши .bak и Enter")
    solution = "↑, Ctrl+W до конца имени, Ctrl+Y, пробел, Ctrl+Y, допиши .bak, Enter"
    solution_script = "cp quarterly_report_{year}.txt quarterly_report_{year}.txt.bak"
    explain = ("Стёртое Ctrl+W не пропадает: оно в кармане zsh, Ctrl+Y "
               "вставляет его, где курсор, хоть десять раз. Буфер Mac (Cmd+C, Cmd+V) — "
               "отдельный.")
    spell = "Ctrl+W — стереть слово в карман zsh; Ctrl+Y — Yank, вставить из кармана"

    def setup_variant(self, box, rng, variant):
        year = str(rng.randint(2724, 2726))
        fill = list(rng.sample(FILLER, 8))
        if variant == 1:
            f = kit.write(box / f"report_{year}.txt", f"report {year}: {kit.word(rng)}\n")
            (box / "outbox").mkdir()
            _history(box, fill + [f"mv outbox/ report_{year}.txt"])
            return {"year": year, "want": {f"outbox/report_{year}.txt": kit.sha(f)}}
        if variant == 2:
            want = {}
            for name in (f"report_{year}.txt", f"notes_{year}.txt"):
                f = kit.write(box / name, f"{name}: {kit.word(rng)}\n")
                want[f"outbox/{name}"] = kit.sha(f)
            (box / "outbox").mkdir()
            _history(box, fill + [f"mv outbox/ report_{year}.txt notes_{year}.txt"])
            return {"year": year, "want": want}
        name = f"quarterly_report_{year}.txt"
        f = kit.write(box / name, f"Quarterly report {year}: {kit.word(rng)}\n")
        _history(box, fill + [f"cp {name}"])
        return {"year": year, "want": {name: kit.sha(f), f"{name}.bak": kit.sha(f)}}

    def check(self, ctx):
        return _files_check(ctx)


class HistoryRecall(Task):
    """FB4: история — Ctrl+R (поиск), history и !N, !!. В истории песочницы — заготовленная
    длинная команда: достать, поправить и выполнить."""
    id = "history_recall"
    track = "basics"
    title = "Поиск в истории"
    # новичок 24.10: «как править конец», «!! после моего ls повторит ls», hist_verify и
    # Oh My Zsh — жаргон; заготовка DIR вместо «папка»
    scroll = ("↑ ↓ — прошлые команды. Ctrl+R и кусок — поиск: ещё Ctrl+R — постарше; Enter — "
              "выполнить, → — поставить в строку и поправить, Ctrl+G — отмена.\n"
              "history — свежие команды с номерами; !N — команда номер N: !42.\n"
              "!! — самая последняя команда целиком. Не в той папке: cd DIR && !! (DIR — имя "
              "папки) — сначала войти, потом та команда. Встала в строку и ждёт — Enter ещё "
              "раз.")
    variants = (
        Variant("Когда-то ты уже копировал три шаблона из templates в папку клиента {old}: "
                "команда лежит в истории. Теперь те же шаблоны нужны клиенту {new} — папка "
                "clients/{new} уже есть. Найди ту команду Ctrl+R (набери кусок, например "
                "templates; нашлась не та — ещё Ctrl+R), нажми → и Ctrl+E — курсор в конце. "
                "Жми Ctrl+W, пока не сотрётся {old}, допиши, чтобы конец стал clients/{new}/, и "
                "нажми Enter.",
                wrong=("cp templates/invoice_base.txt clients/{new}/",),
                alternatives=("history — найти строку глазами и !N по её номеру; потом ↑ и "
                              "поправить конец",)),
        Variant("Последняя команда в истории копирует отчёты в shared/{month}/, но набрали "
                "её не в той папке: отчёты лежат в {project}, а ты стоишь снаружи — команда "
                "упала. Войди в {project} и повтори ту команду одной строкой, не "
                "перепечатывая: cd, && и !! — самая последняя команда истории. Ничего не "
                "набирай до этого: после ls, pwd или отдельного cd !! повторит уже их.",
                hints=("Войти в папку — cd {project}.",
                       "!! подставит последнюю команду истории — даже в той же строке, после "
                       "&&. Уже что-то набрал — тогда ↑ ↑ найдёт её.",
                       "cd {project} && !!"),
                solution="cd {project} && !!",
                solution_script=("cd {project} && cp reports/summary.txt "
                                 "reports/figures.csv reports/notes.txt shared/{month}/"),
                wrong=("cd {project}",),
                alternatives=("cd {project}, затем ↑ ↑ и Enter — та же команда стрелкой",)),
        Variant("В истории есть команда, которая переносила снимки и скриншоты из downloads "
                "в photos (mv — move, «перенеси»): она кончается на photos/. Сегодня снимков "
                "снова набежало. Найди её номер командой history и запусти по номеру: !N — "
                "вместо N впиши номер.",
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
             ("Ctrl+R и набери кусок templates, затем →, Ctrl+W — пока старый путь clients/… не "
              "сотрётся целиком, допиши clients/{new}/ и Enter"))
    solution = ("Ctrl+R и кусок templates, стрелка →, Ctrl+W до конца старого пути, допиши "
                "clients/{new}/, Enter")
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
            project = f"project_{kit.latin(rng)}"
            want = {}
            for name in ("summary.txt", "figures.csv", "notes.txt"):
                f = kit.write(box / project / "reports" / name, f"{name}: {kit.word(rng)}\n")
                want[f"{project}/reports/{name}"] = kit.sha(f)
                want[f"{project}/shared/{month}/{name}"] = kit.sha(f)
            (box / project / "shared" / month).mkdir(parents=True)
            _history(box, fill + ["cp reports/summary.txt reports/figures.csv "
                                  f"reports/notes.txt shared/{month}/"])
            return {"month": month, "project": project, "want": want}
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
    scroll = ("Вывод уехал вверх — колесо мыши или два пальца по трекпаду: так крутится и "
              "Terminal.app, и iTerm2.\n"
              "Клавиши iTerm2 (клавиша fn — в левом нижнем углу, на новых Mac с глобусом 🌐): "
              "Cmd+↑ ↓ — по строке, Shift+fn+↑ ↓ — по странице, Cmd+fn+← → — в начало и конец. "
              "Голые fn+↑ ↓ (Page Up/Down) iTerm2 отдаёт программе — окно не крутится. "
              "Cmd+Shift+↑ — к прошлой команде, только в настроенном iTerm2.\n"
              "Очистить экран — clear или Ctrl+L (L — «новый лист» у принтеров). Cmd+K стирает и всю прокрутку — пока ищешь "
              "слово, не жми.")
    variants = (
        Variant("Журнал journal.txt длинный: cat вывалит его, и начало убежит за край окна. "
                "Слово дня — в самой первой строке, после Today's word: («слово дня»). "
                "Выведи журнал командой cat, прокрути к началу и сдай слово: ans WORD (WORD "
                "— сюда подставь это слово)",
                wrong=("echo {old}",),
                alternatives=("cat journal.txt, затем Cmd+fn+← — сразу в самое начало "
                              "вывода",)),
        Variant("Выведи по очереди два длинных файла: cat part1.txt, затем cat part2.txt. "
                "Нужное слово — в последней строке первого файла, после Word: — после второй "
                "команды оно уедет далеко вверх. Прокрути к нему и сдай: ans WORD, где WORD — "
                "найденное слово",
                hints=("Слово — в конце первого вывода, прямо над строкой с командой cat "
                       "part2.txt.",
                       "Cmd+↑ — на строку вверх (iTerm2); колесо мыши или трекпад тоже годятся.",
                       "cat part1.txt, cat part2.txt, прокрути вверх до строки над cat "
                       "part2.txt — ans WORD"),
                solution="cat part1.txt && cat part2.txt",
                solution_script="tail -n 1 part1.txt | cut -d' ' -f2",
                wrong=("echo {old}",),
                alternatives=("cat part1.txt — одного первого файла хватит: слово в конце, "
                              "прямо над приглашением",)),
        Variant("Где-то в середине длинного отчёта report.txt есть строка «Tag: …» (метка). "
                "Выведи отчёт командой cat и листай вверх страницами, пока не найдёшь. Сдай "
                "слово, что стоит после Tag:, — ans WORD (вместо WORD — это слово)",
                hints=("Вывод длиннее окна — его прокручивают вверх.",
                       "Shift+fn+↑ — страница вверх, Shift+fn+↓ — вниз; колесо мыши тоже "
                       "годится.",
                       "cat report.txt, затем Shift+fn+↑ до строки «Tag:» — ans WORD"),
                solution="cat report.txt",
                solution_script="grep 'Tag:' report.txt | cut -d' ' -f2",
                wrong=("echo {old}",),
                alternatives=("cat report.txt, затем Cmd+F в iTerm2 — поиск по экрану",)),
    )
    par = 40
    hints = ("Вывод длиннее окна — начало уехало вверх, его можно прокрутить.",
             "Колесо мыши, Cmd+↑ — по строке, Shift+fn+↑ — по странице, Cmd+fn+← — в самое "
             "начало.",
             "cat journal.txt, затем Cmd+fn+← — первая строка, ans WORD")
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
              "Cmd+Shift+↑ ↓ — от команды к команде: метки iTerm2, только после настройки (меню "
              "iTerm2 → Install Shell Integration).\n"
              "Cmd+Shift+A — выделить вывод последней команды (тоже после этой настройки).")
    variants = (
        Variant("Склад выдал опись stock.txt на сотни строк. Где-то в середине одна строка "
                "помечена словом MISSING (пропуск). Выведи опись командой cat, найди метку поиском "
                "Cmd+F и сдай слово, что стоит после неё: ans WORD (WORD — сюда подставь это "
                "слово)",
                wrong=("echo {old}",),
                alternatives=("cat stock.txt, затем Cmd+F и MISSING — Enter прыгает к "
                              "совпадению",)),
        Variant("Выведи три журнала по очереди: cat day1.txt, cat day2.txt, cat day3.txt. "
                "Слово дня — в первой строке второго журнала, после Today's word:. После "
                "третьей команды оно уедет далеко вверх: вернись к строке cat day2.txt — "
                "слово сразу под ней — и сдай его: ans WORD",
                hints=("Слово — сразу под командой cat day2.txt.",
                       "Поиск Cmd+F по cat day2 прыгнет к этой строке — так работает везде. В "
                       "настроенном iTerm2 к прошлой команде прыгает и Cmd+Shift+↑.",
                       "cat day1.txt, cat day2.txt, cat day3.txt, Cmd+F и cat day2 — слово "
                       "под этой строкой, ans WORD"),
                solution="cat day1.txt && cat day2.txt && cat day3.txt",
                solution_script="head -n 1 day2.txt | cut -d' ' -f3",
                wrong=("echo {old}",),
                alternatives=("cat day2.txt одной командой — слово в первой строке, Cmd+Shift+↑ "
                              "сразу к ней",)),
        Variant("В файле ticket.txt — код доступа: длинный, из цифр и латиницы. Перепечатывать "
                "долго, а ошибка в одном знаке — и код не тот. Выведи его командой cat, "
                "выдели двойным щелчком по коду, скопируй Cmd+C и сдай: ans CODE (CODE — "
                "сюда вставь код: Cmd+V)",
                hints=("Код печатает cat ticket.txt. Набирать его руками не нужно.",
                       "Двойной щелчок по коду выделит его целиком; в настроенном iTerm2 весь "
                       "вывод выделяет и Cmd+Shift+A.",
                       "cat ticket.txt, двойной щелчок по коду, Cmd+C, ans, пробел и Cmd+V"),
                solution="cat ticket.txt",
                solution_script="cat ticket.txt",
                wrong=("echo {old}",),
                alternatives=("ans $(cat ticket.txt) — подстановка тоже сдаст код без "
                              "перепечатки",)),
    )
    par = 40
    hints = ("Вывод длинный, читать глазами долго — пусть ищет терминал.",
             "Cmd+F открывает поиск: набери MISSING, Enter — к совпадению.",
             "cat stock.txt, затем Cmd+F и MISSING — ans WORD, слово после метки")
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
              "постарше. Option+. — то же, если в настройках терминала Option работает как "
              "Esc+; не настроено — жми Esc, отпусти, потом точку.\n"
              "!$ — то же слово набором: cd !$. ^OLD^NEW — прошлая команда, где кусок OLD "
              "заменён на NEW: ^q1^q2 (^ — Shift+6).")
    variants = (
        Variant("Игра уже набрала за тебя прошлую команду — она создала папку с длинным путём "
                "(нажми ↑ — увидишь её, Ctrl+U сотрёт строку). Перейди в эту папку, не набирая "
                "путь: cd, пробел, Esc, потом точка — путь встанет сам — и Enter.",
                wrong=("cd projects/{client}",),
                alternatives=("cd !$ — то же слово набором; zsh подставит путь сам",)),
        Variant("Игра уже набрала за тебя прошлую команду — она скопировала в архив отчёт "
                "первого квартала, summary_q1.txt (нажми ↑ — увидишь её, Ctrl+U сотрёт "
                "строку). Сделай то же для второго квартала, не перепечатывая: набери ^q1^q2 "
                "и Enter.",
                hints=("Команда почти та же — поменять надо одно: q1 на q2.",
                       "^OLD^NEW повторит прошлую команду, заменив OLD на NEW. ↑ жать не "
                       "нужно: прошлая — та, что надо.",
                       "^q1^q2"),
                solution="^q1^q2",
                solution_script="cp reports/{year}/summary_q2.txt archive/{year}/",
                wrong=("cp reports/{year}/summary_q1.txt archive/{year}/",),
                alternatives=("↑, Option+← к q1, поправь на q2 и Enter — тоже верно, но "
                              "дольше",)),
        Variant("Игра уже набрала за тебя прошлую команду — она показала лог с длинным путём "
                "(нажми ↑ — увидишь её, Ctrl+U сотрёт строку). Скопируй именно этот лог в "
                "outbox/: cp, пробел, Esc, потом точка — путь встанет сам, — пробел, outbox/ "
                "и Enter.",
                hints=("Путь — последнее слово прошлой команды: Esc . вставит его.",
                       "cp, пробел, Esc . (или !$), пробел, outbox/",
                       "cp, пробел, Esc, потом точка, пробел, outbox/ и Enter"),
                solution="cp, пробел, Esc ., пробел, outbox/, Enter",
                solution_script="cp logs/{year}/october/server_{name}.log outbox/",
                wrong=("cp logs/{year}/october/*.log outbox/",),
                alternatives=("cp !$ outbox/ — то же слово набором",)),
    )
    par = 40
    hints = ("Путь — последнее слово прошлой команды. Набирать его не нужно.",
             "Esc, отпусти, потом точка — вставит последнее слово прошлой команды. Или !$ — то "
             "же набором.",
             "cd, пробел, Esc, потом точка — и Enter")
    solution = "cd, пробел, Esc ., Enter"
    solution_script = "cd projects/{client}/drafts/{year}/final"
    explain = ("Что уже набрано, не набирают снова: Esc . и !$ берут последнее слово прошлой "
               "команды, ^OLD^NEW повторяет её с заменой.")
    spell = "Esc . и !$ — последний аргумент; ^OLD^NEW — повтор с заменой"

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
              "вглубь) копирует папку со всем содержимым: cp -r SOURCE DEST (SOURCE — папка, "
              "DEST — имя копии или папка, куда класть).\n"
              "-n — no clobber: не затирать то, что уже лежит там, куда копируешь: cp -r -n site "
              "site_old; -v — "
              "verbose: печатать каждый скопированный файл. cp -r -v и cp -rv — одно и то "
              "же.\n"
              "Слеш в конце имени папки стирай: на Mac cp -r site/ site_old скопирует не папку, а "
              "только то, что внутри (Tab дописывает / сам).")
    variants = (
        Variant("Сделай копию папки {proj} целиком — рядом с ней, под именем {proj}_backup.",
                wrong=("mkdir {proj}_backup",),
                alternatives=("cp -rv {proj} {proj}_backup — то же, и cp покажет каждый файл",
                              "cp -R {proj} {proj}_backup — большая -R у cp значит то же, что -r")),
        Variant("Папки {a} и {b} нужны и в archive/ (эта папка уже есть) — скопируй обе "
                "целиком, одной командой. Оригиналы остаются на месте.",
                hints=("Папки копирует только cp с флагом -r — и одну, и две.",
                       "cp, как и mv, берёт сразу несколько имён: последней идёт папка.",
                       "cp -r {a} {b} archive/"),
                solution="cp -r {a} {b} archive/",
                wrong=("mv {a} {b} archive/",),
                alternatives=("cp -rv {a} {b} archive/ — -v покажет, что скопировано",)),
        Variant("Скопируй файлы, что лежат в папке photos, прямо в папку backup — не саму "
                "папку photos, а то, что внутри неё. В backup уже лежит свой cover.jpg — его "
                "не затирай, пусть останется как был.",
                hints=("Обычный cp затирает файл с тем же именем молча, без вопроса.",
                       "Все файлы из photos — маска photos/*; «не затирать то, что уже есть» — "
                       "флаг -n.",
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
    spell = "cp -r SOURCE DEST — копия папки; -n — не затирать; -v — показать"

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
        return self._spilled(b, want) or self._moved(b, want) or Verdict(False)

    MSG_SPILLED = ("В {dest}/ легло содержимое папок, а не сами папки: на Mac слеш в конце "
                   "(cp -r {name}/ …) значит «скопируй то, что внутри». Набери reset — песочница "
                   "вернётся как была, — и снова, без слеша: cp -r {names} {dest}/")

    def _spilled(self, b, want):
        """Владелец 23.10: cp -r drafts/ notes/ archive — BSD cp со слешем в конце копирует
        содержимое, и игра молчала. Файл ждали в dest/папка/…, а он лежит в dest/… ."""
        names = []
        for rel, h in want.items():
            parts = Path(rel).parts
            if len(parts) < 3 or kit.sha_in_box(b, rel) == h:
                continue
            if kit.sha_in_box(b, str(Path(parts[0], *parts[2:]))) == h and parts[1] not in names:
                names.append(parts[1])
        if not names:
            return None
        deep = [Path(r).parts for r in want if len(Path(r).parts) >= 3]
        dest = deep[0][0]
        all_names = sorted({parts[1] for parts in deep if parts[0] == dest})
        return Verdict(False, self.MSG_SPILLED.format(dest=dest, name=names[0],
                                                      names=" ".join(all_names)))

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


class Quotes(AnswerTask):
    """Владелец 23.10 (fzf_pick): «про кавычки надо отдельно рассказывать — когда их применять,
    зачем и почему тут двойные, а в других командах одинарные». Пробел режет строку на слова;
    "…" склеивает и пускает $ внутрь; '…' — всё буквально; \\ — один знак (так пишет Tab)."""
    id = "quotes"
    track = "basics"
    title = "Кавычки"
    # новичок 24.10: «как набрать " и '», «ёлочки набирать?», $(…) в уроке — лишнее
    scroll = ("Пробел режет команду на отдельные слова: cat march report.txt — два файла, «march» "
              "и «report.txt».\n"
              "\"…\" — двойные кавычки: всё внутри — одна строка (str), а $ показывает, что на "
              "ярлыке: cat \"march report.txt\", echo \"$SHELL\" → /bin/zsh.\n"
              "'…' — одинарные: $ внутри — просто доллар: echo '$SHELL' → $SHELL. Кавычка ' — "
              "клавиша рядом с Enter, \" — она же с Shift (раскладка английская).")
    variants = (
        Variant("В этой папке лежит файл «{name}» — с пробелом в имени. Прочти его и сдай "
                "слово, что в нём записано: ans WORD — вместо WORD вставь это слово. "
                "Ёлочки «» вокруг имени не набирай.",
                hints=("Без кавычек cat получит два имени — {a} и {b}.txt — и не найдёт ни "
                       "одного.",
                       "Возьми имя в кавычки целиком: «{name}» в \"…\" — одно слово.",
                       "cat \"{name}\", затем ans WORD"),
                solution="cat \"{name}\"",
                solution_script="cat \"{name}\"",
                wrong=("cat {name}",),
                alternatives=("cat '{name}' — одинарные тоже подходят: в имени нет $",)),
        Variant("Папка «{dir}» — с пробелом в имени. Сколько в ней файлов — столько, сколько "
                "имён покажет ls? Ответ — число: ans NUMBER — вместо NUMBER впиши его. Ёлочки «» "
                "вокруг имени не набирай.",
                hints=("ls покажет, что внутри папки, — но имя с пробелом zsh разрежет на два.",
                       "Склей имя папки кавычками: ls \"{dir}\".",
                       "ls \"{dir}\", посчитай файлы и ans NUMBER"),
                solution="ls \"{dir}\"",
                solution_script="ls \"{dir}\" | wc -l",
                wrong=("ls {dir} | wc -l",),
                alternatives=("ls '{d1} {d2}' — одинарные тоже подходят: в имени нет $",)),
        Variant("Клиент в сером диктует пароль: {code} — буквы, знак доллара и цифра. Сдай его "
                "ответом ровно так, со знаком доллара: ans PASSWORD — вместо PASSWORD вставь "
                "его (можно скопировать из этого текста мышью). Осторожно: $ терминал "
                "считает особым знаком — проверь, что дошло, и загляни в урок (lesson).",
                hints=("Сдай как есть и посмотри, что дошло: $7 zsh принимает за ярлык с "
                       "именем 7 — такого нет, и на его месте пусто.",
                       "Двойные кавычки $ не спасут — в них $ по-прежнему ищет ярлык. Нужны "
                       "одинарные '…': в них $ — просто знак доллара.",
                       "ans '{code}'"),
                solution="ans '{code}'",
                solution_script="echo '{code}'",
                wrong=("echo {code}", "echo \"{code}\""),
                alternatives=("ans '{code}' — пароль можно не набирать, а скопировать мышью из "
                              "задания; главное — одинарные кавычки вокруг",)),
    )
    par = 30
    hints = ("Без кавычек zsh режет команду по пробелам.",
             "Имя с пробелом бери в кавычки целиком.",
             "cat \"client notes.txt\", затем ans WORD")
    solution = "cat \"client notes.txt\""
    explain = ("Пробел делит команду на слова, кавычки склеивают текст в одну строку (str). "
               "В \"…\" $ показывает, что на ярлыке; в '…' $ — просто знак доллара.")
    spell = "\"…\" — одна строка, $ показывает ярлык; '…' — одна строка, $ — просто доллар"
    trap_messages = {
        "eaten": "Доллар с цифрой пропал: без кавычек и в \"…\" zsh принял $ с цифрой за "
                 "ярлык, а такого нет — пусто. В одинарных '…' $ — просто доллар: ans '…'.",
        "split": "Это кусок имени до пробела. Возьми имя в кавычки целиком.",
    }
    kinds = ("text", "number", "text")

    def answer_kind(self, state):
        return self.kinds[variant_index(state.get("_variant"), 3)]

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            d1, d2 = rng.sample(("Client", "Old", "Shared", "Team", "Tax", "Photo"), 2)
            folder = f"{d1} {d2}"
            n = rng.randint(3, 6)
            for name in rng.sample(kit.LATIN, n):
                kit.write(Path(box) / folder / f"{name}.txt", f"{kit.word(rng)}\n")
            return {"dir": folder, "d1": d1, "d2": d2, "answer": n}
        if variant == 2:
            head = "".join(rng.choice("abdfghkmnpqrstvxz") for _ in range(2))
            digit = rng.randint(1, 9)
            return {"code": f"{head}${digit}", "head": head, "digit": digit,
                    "answer": f"{head}${digit}", "traps": [["eaten", head]]}
        a, b = rng.sample(("march", "budget", "client", "final", "team", "notes"), 2)
        name = f"{a} {b}.txt"
        w = kit.word(rng)
        kit.write(Path(box) / name, f"{w}\n")
        decoy = kit.word(rng)
        while decoy == w:
            decoy = kit.word(rng)
        kit.write(Path(box) / f"{a}.txt", f"{decoy}\n")       # приманка: кусок имени до пробела
        return {"name": name, "a": a, "b": b, "answer": w, "traps": [["split", decoy]],
                "sources": sources(box, name)}


class FzfPick(AnswerTask):
    id = "fzf_pick"
    track = "basics"
    title = "Три обрывка имени"
    implant = "fzf"
    after = ("climb_down", "boss_basics")
    start_dir = "{start}"
    scroll = ("ls | grep WORD — только строки, где есть WORD (кусок имени); grep -i — ignore "
              "case, не различать большие и маленькие буквы. Труба (по-английски pipe) отдаёт "
              "вывод левой команды на вход правой: ls | grep a | grep b — два сита подряд.\n"
              "cat \"$(COMMAND)\" — подставит имя, которое напечатала COMMAND; двойные кавычки "
              "— чтобы имя с пробелом не развалилось на куски. Пусто — cat ждёт ввода: Ctrl+C.\n"
              "Утилита (маленькая отдельная программа) fzf — выбор кусками имени: ls | fzf.")
    variants = (
        Variant("Ты стоишь в папке reports: тут под три сотни отчётов с похожими именами. "
                "Нужен тот, в имени которого есть {y}, {m} и {k} — в любом порядке, буквы "
                "могут быть большими. В нём одно слово — сдай его: ans WORD (WORD — сюда "
                "подставь это слово)",
                wrong=("cat *{y}*{m}*{k}*",
                       "cat $(ls | grep {y} | grep {m} | grep {k}) </dev/null"),
                alternatives=("cat \"$(ls | fzf)\" — набрать {y} {m} {k} и Enter",
                              "ls *{y}* | grep -i {m} | grep -i {k} — первый фильтр маской")),
        Variant("Ты стоишь в папке projects: тут три сотни папок, и названия похожи как "
                "близнецы. В названии нужной папки есть {y}, {m} и {k}, порядок любой, регистр "
                "любой. Внутри неё лежит readme.txt с одним словом — сдай его: ans WORD",
                hints=("Отфильтруй список папок: ls | grep {y} оставит только с {y}.",
                       "Цепочка фильтров через |, а -i у grep не различает большие и маленькие "
                       "буквы. К найденной папке допиши /readme.txt.",
                       "cat \"$(ls | grep {y} | grep -i {m} | grep -i {k})/readme.txt\" — "
                       "утилитой: cd \"$(ls | fzf)\" и набрать {y} {m} {k}"),
                solution="cat \"$(ls | grep {y} | grep -i {m} | grep -i {k})/readme.txt\"",
                implant_script="cat \"$(ls | fzf -e --filter '{y} {m} {k}')/readme.txt\"",
                wrong=("cat \"$(ls | grep {y} | grep {m} | grep {k})/readme.txt\" </dev/null",),
                alternatives=("cd \"$(ls | fzf)\" && cat readme.txt",)),
        # новичок 24.10: правка в nano требовала редактора, которого игрок ещё не видел
        # (nano_config — в «Инструментах») — теперь найденное имя уходит в mv
        Variant("Ты стоишь в папке drafts: тут три сотни черновиков с похожими именами. Тот, в "
                "имени которого есть {y}, {m} и {k} (в любом порядке, регистр любой), готов — "
                "перенеси его в папку done: она лежит рядом с drafts, путь к ней отсюда — "
                "../done/. Остальные не трогай. Сдавать ничего не надо — игра проверит папки.",
                hints=("Найди имя фильтрами: ls | grep {y} | grep -i {m} | grep -i {k}.",
                       "Найденное имя подставь в mv через \"$(…)\", а куда — последним словом: "
                       "../done/",
                       "mv \"$(ls | grep {y} | grep -i {m} | grep -i {k})\" ../done/ — утилитой: "
                       "mv \"$(ls | fzf)\" ../done/ и набрать {y} {m} {k}"),
                solution="mv \"$(ls | grep {y} | grep -i {m} | grep -i {k})\" ../done/",
                implant_script="mv \"$(ls | fzf -e --filter '{y} {m} {k}')\" ../done/",
                wrong=("mv *{y}* ../done/",),
                alternatives=("mv \"$(ls | fzf)\" ../done/ — выбрать набором {y} {m} {k}",)),
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
        rng.choice(self.SWAPS)          # бывшая правка в nano: поток зерна не сдвигаем
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
                kit.write(root / f"{name}.txt", "draft\n")
            else:
                kit.write(root / f"{name}.txt", f"{other()}\n")
        if variant == 1:
            kit.write(root / target / "readme.txt", f"{word}\n")
        else:
            kit.write(root / f"{target}.txt", f"{word}\n" if variant == 0 else "ready\n")
        if variant == 2:
            (box / "done").mkdir()
        st = {"start": start, "y": y, "m": m, "k": k, "count": len(found),
              "target": target + ("" if variant == 1 else ".txt"), "answer": word}
        if variant != 2:
            src = f"{start}/{target}/readme.txt" if variant == 1 else f"{start}/{target}.txt"
            st["sources"] = sources(box, src)
        return st

    def takes_answer(self, state):
        """Вариант с переносом — «сделай»: карточка не зовёт сдавать слово (FB6)."""
        return variant_index(state.get("_variant"), 3) != 2

    def check(self, ctx):
        if variant_index(ctx.state.get("_variant"), 3) != 2:
            return super().check(ctx)
        start, target = Path(ctx.state["start"]), ctx.state["target"]
        # проверку зовёт судья у родителя: папки и файлы — только внутри песочницы, по
        # звеньям без симлинков (sandbox.files_in_box, read_in_box)
        left = sandbox.files_in_box(ctx.box, start)
        done = sandbox.files_in_box(ctx.box, "done")
        if left is None or done is None:
            return Verdict(False)
        moved = sandbox.read_in_box(ctx.box, Path("done") / target, kit.BOX_READ_CAP)
        if target not in left and moved != b"ready\n":
            return Verdict(False, "Нужного черновика нет ни в drafts, ни в done. "
                                  + kit.RESET_TAIL)
        extra = sorted(n for n in done if n != target)
        if extra:
            return Verdict(False, f"В done лишнее: {kit.names_line(extra)} — верни обратно: "
                                  f"mv ../done/{extra[0]} .")
        if target in left:
            return Verdict(False)
        return Verdict(len(left) == ctx.state.get("count", 299))


class ZJump(Task):
    """Пара к back_up: прыжок назад по стеку каталогов zsh (auto_pushd включён в песочном
    .zshrc), утилита zoxide — по куску имени. Проверка: стоишь в цели, все четыре папки
    посещены, а команда, которая привела в цель, короче 15 знаков и без пути цели."""
    id = "z_jump"
    track = "basics"
    title = "Прыжок назад"
    implant = "zoxide"
    after = ("back_up", "boss_basics")
    scroll = ("Здесь, в игре, оболочка помнит, где ты был: каждый cd кладёт прежнюю папку в стек (стопку, "
              "свежее — сверху). dirs -v — стек с номерами (v — verbose, подробно): 0 — где "
              "стоишь сейчас, 1 — откуда пришёл, дальше — старше. cd ~3 — прыжок в папку номер "
              "3, cd - — на шаг назад.\n"
              "Вне игры стек включает строка в ~/.zshrc (setopt auto_pushd). Утилита zoxide "
              "запоминает папки сама: z NAME (кусок имени папки) — и ты там.")
    variants = (
        Variant("Обойди четыре папки по порядку, в каждую — одной командой cd с путём целиком: "
                "{d1}, {d2}, {d3}, {d4} (Tab допишет путь). Затем вернись в первую из четырёх, "
                "{d1}, — одной командой короче 15 знаков и без её пути.",
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
                "по дороге набирай ls в каждой, чтобы увидеть, где лежит marker.txt. Закончи "
                "там, где он лежит, а "
                "последнюю команду сделай короче 15 знаков и без пути.",
                hints=("ls в каждой папке покажет, где marker.txt; запомни, которая по счёту.",
                       "dirs -v перечислит пройденные папки с номерами — от свежих к старым.",
                       "dirs -v, затем cd ~N — N: номер папки с marker.txt; утилитой: z и "
                       "кусок её имени"),
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

    @staticmethod
    def _same(home, p, rel):
        try:
            return Path(p).resolve() == (home / rel).resolve()
        except (OSError, RuntimeError):
            return False

    def _went(self, home, line, rel):     # cd/pushd с путём папки: через ~ или полностью
        return any(seg.split()[:1] in (["cd"], ["pushd"]) and
                   (f"~/{rel}" in seg or str(home / rel) in seg)
                   for seg in self._segments(line))

    def _seen(self, ctx):
        home = kit.home(ctx.box)
        return [any(self._same(home, c.pwd, d) or self._went(home, c.line, d) for c in ctx.cmds)
                for d in ctx.state["dirs"]]

    def parts_for(self, state):
        """FB5 п. 68: маршрут из четырёх папок и прыжок — сколько пройдено."""
        return [f"папка {Path(d).name}" for d in state["dirs"]] + ["прыжок назад"]

    def progress(self, ctx):
        return self._seen(ctx) + [self.check(ctx).solved]

    def check(self, ctx):
        st = ctx.state
        home = kit.home(ctx.box)

        def same(p, rel):
            return self._same(home, p, rel)

        if ctx.pwd is None or not same(ctx.pwd, st["target"]):
            return Verdict(False)
        seen = self._seen(ctx)
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
        # z NAME, где NAME — папка рядом: zoxide тогда просто делает cd — это шаг, не прыжок
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
              "ls -R DIR — показать всё дерево папки DIR разом.\n"
              "rm -r DIR — удалить папку DIR со всем содержимым (навсегда, мимо Корзины).")
    steps = ("создать папку для копий",
             "скопировать туда все настоящие файлы-ключи (оригиналы оставить на месте)",
             "не забыть спрятанный",
             "убрать ловушку")
    variants = (
        Variant("На старом диске old_disk спрятаны ключи *.key. Собери КОПИИ всех настоящих "
                "ключей в новую папку keys — все прямо в неё, без подпапок (cp так и кладёт, "
                "имена ключей не повторяются). Подделки .key.fake и .key~ (хвост ~ в конце "
                "имени — копия редактора) не брать. Потом удали папку-ловушку trap — ключей в "
                "ней нет.",
                wrong=("mkdir keys && cp old_disk/**/*.key keys/ && rm -r old_disk/**/trap",
                       "mkdir keys && mv old_disk/**/*.key(D) keys/ && rm -r old_disk/**/trap(D)"),
                alternatives=("mkdir -p keys — не ругается, если папка уже создана",)),
        Variant("Со старого диска old_disk выносим сертификаты *.cert. Сложи копии каждого "
                "подлинного в новую папку certs — все прямо в неё, без подпапок; хвосты "
                ".cert.old и .cert~ — фальшивки. Где-то внутри сидит папка decoy — снеси её, "
                "сертификатов в ней нет.",
                hints=("Начни с mkdir certs. Сертификаты лежат глубоко — всё дерево покажет "
                       "ls -laR old_disk",
                       "** — любые вложенные папки, (D) — и скрытые тоже: "
                       "ls old_disk/**/*.cert(D)",
                       "mkdir certs && cp old_disk/**/*.cert(D) certs/ && "
                       "rm -r old_disk/**/decoy(D)"),
                solution="mkdir certs && cp old_disk/**/*.cert(D) certs/ && "
                         "rm -r old_disk/**/decoy(D)",
                wrong=("mkdir certs && cp old_disk/**/*.cert certs/ && rm -r old_disk/**/decoy",
                       "mkdir certs && cp old_disk/**/*.cert*(D) certs/ && "
                       "rm -r old_disk/**/decoy(D)"),
                alternatives=("ls old_disk/**/*.cert(D) — сначала увидеть всю добычу, потом "
                              "копировать",)),
        Variant("В old_disk лежат ключи *.key, а вокруг — резервные копии *.bak, которым на "
                "диске не место. Собери копии настоящих ключей в новую папку keys — все прямо "
                "в неё, без подпапок и без подделок .key.fake и .key~, — и сотри с диска все "
                "*.bak до единого.",
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
             "mkdir keys && cp old_disk/**/*.key(D) keys/ && rm -r old_disk/**/trap(D)")
    solution = "mkdir keys && cp old_disk/**/*.key(D) keys/ && rm -r old_disk/**/trap(D)"
    explain = ("** спускается во все вложенные папки, (D) добавляет скрытые; rm -r удаляет папку "
               "вместе с содержимым.")
    spell = "**/*.key(D) — все .key во всех вложенных папках, включая скрытые (zsh); rm -r DIR"

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
# FB18 (владелец 21.10): строку ввода правят с первых минут — правка строки, мышь и карман zsh
# сразу за первыми командами (pwd); история — когда в ней уже есть свои cd и ls; прокрутка и
# поиск по экрану — к первому длинному выводу (за ls -R в задачах на глубину), быстрая правка
# — за ними.
# Владелец 23.10 (разбор геймдизайнера, Р4): сначала действие — где я, войти, прочесть, выйти,
# дом, скрытое; потом оболочка и $, кавычки; клавиши строки — после первых шести дел.
TASKS = [WhereAmI(), ClimbDown(), BackUp(), HomeTilde(), HiddenCache(),
         MeetTerminal(), Quotes(),
         LineEdit(), CursorClip(), CutPaste(), HistoryRecall(),
         MkdirP(), CopyMove(), FileExt(), StarMask(), QuestionMask(),
         RunScript(), DeepDig(), DeepRm(),
         ScreenScroll(), ScreenFind(), QuickFix(),
         CopyDir(),
         FzfPick(), ZJump(), BossBasics()]
