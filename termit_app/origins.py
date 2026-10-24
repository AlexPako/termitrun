"""FB5 (12): откуда имена команд и буквы сочетаний клавиш. Владелец: «обязательно добавляй это
в курс и все исторические справки: во-первых интересно, во-вторых проще запомнить».

Единый источник: команда или клавиша → Origin(word, line).
- word — расшифровка, которую ищет охрана (tools/audit_origins.py): при первой встрече она
  стоит в строке карточки «🔤 …», в самом уроке, шпаргалке или разборе;
- line — то, что видит игрок: расшифровка и, где есть, короткая история-зацепка.

Факты — только проверенные; спорное помечено «говорят». Английские расшифровки — в «ёлочках»:
разбор lint (tasks/lint.command_words) принимает первое голое слово после тире за команду, а
«print» в кавычках — уже не команда.

Где звучит: FIRST_SEEN — задача → имена, чья строка «🔤» стоит в её карточке под уроком
(ui.task_card). Это задачи, где игрок впервые видит команду в уроке или шпаргалке; охрана
сверяет список с порядком игры."""
from dataclasses import dataclass
from typing import Dict, List, Tuple

from termit_app.implants import STUB_NAME     # «brew» — только из implants (охрана I-2)


@dataclass(frozen=True)
class Origin:
    word: str           # расшифровка: охрана ищет её при первой встрече (регистр не важен)
    line: str           # строка игроку, без имени команды впереди


COMMANDS: Dict[str, Origin] = {
    # «Основы»
    "pwd": Origin("print working directory",
                  "«print working directory» — «напечатай рабочую папку»: где ты стоишь."),
    "cd": Origin("change directory", "«change directory» — «смени папку»."),
    "ls": Origin("list",
                 "«list» — «список». Говорят, имена в Unix такие короткие из-за телетайпов "
                 "70-х: каждую букву там отбивала механика."),
    "cat": Origin("concatenate",
                  "«concatenate» — «склеить»: cat a b выдаст два файла подряд, одним куском. "
                  "Показать один файл — просто самый частый случай."),
    "echo": Origin("эхо", "по-английски «эхо» — повторяет, что ему сказали."),
    "mkdir": Origin("make directory", "«make directory» — «сделай папку»."),
    "cp": Origin("copy", "«copy» — «копировать»."),
    "mv": Origin("move", "«move» — «перенести»."),
    "rm": Origin("remove", "«remove» — «убрать». Корзины у него нет: убрал — значит, нет."),
    "file": Origin("file", "«file» — «файл»: смотрит внутрь и говорит, что это за файл."),
    "chmod": Origin("change mode",
                    "«change mode» — «сменить режим»: режимом в Unix зовут права файла — кому "
                    "можно читать, писать и запускать."),
    "zsh": Origin("Z shell",
                  "«Z shell», оболочка Z. Пол Фалстад написал её в 1990-м, студентом Принстона, "
                  "а имя взял у логина преподавателя Чжун Шао — zsh."),
    "bash": Origin("Bourne Again SHell",
                   "«Bourne Again SHell» — каламбур: born again («рождённый заново») и фамилия "
                   "Стивена Борна, автора старой оболочки sh. Брайан Фокс, 1989."),
    "history": Origin("history", "«history» — «история»: что ты набирал, с номерами."),
    "clear": Origin("clear", "«clear» — «очистить» экран. История при этом цела."),
    "fzf": Origin("fuzzy finder",
                  "«fuzzy finder» — «нечёткий искатель»: находит по обрывкам букв, хоть "
                  "вразбивку."),
    "grep": Origin("g/re/p",
                   "«g/re/p» — команда старого редактора ed: global / regular expression / print, "
                   "«по всему файлу найди шаблон и напечатай». Кен Томпсон в 1970-х вынес её в "
                   "отдельную программу."),
    "setopt": Origin("set option", "«set option» — «включить настройку» zsh."),
    "dirs": Origin("directories", "«directories» — «папки»: где ты недавно бывал."),
    # «Инструменты»
    "man": Origin("manual",
                  "«manual» — «руководство». Первое руководство Unix вышло в 1971-м — с тех пор "
                  "у каждой команды своя страница."),
    "tldr": Origin("too long; didn't read",
                   "«too long; didn't read» — «слишком длинно, не читал»: интернет-сленг. Тут — "
                   "короткие примеры вместо толстого man."),
    "jq": Origin("JSON query",
                 "обычно читают как «JSON query» — «запрос к JSON». Сам автор зовёт его "
                 "«sed для JSON»."),
    "less": Origin("less is more",
                   "шутка «less is more» — «меньше значит больше»: less пришёл на смену старой "
                   "листалке more и умеет больше — например, листать назад."),
    "nano": Origin("Pine composer",
                   "замена редактора pico (от «Pine composer» — редактор почтовика Pine). Нано "
                   "в тысячу раз больше пико — вот и шутка про «следующую ступень»."),
    "vim": Origin("Vi IMproved",
                  "«Vi IMproved» — «улучшенный vi» (Брам Моленар, 1991). А vi — от «visual», "
                  "«экранный»: Билл Джой в 1976-м сделал экранный режим строчному редактору ex."),
    STUB_NAME: Origin("домашнее пиво",
                   "от Homebrew — «домашнее пиво»: рецепты программ там зовут формулами, а "
                   "ставятся они в «погреб», папку Cellar."),
    "which": Origin("which", "«which» — «который»: какой именно файл запустится по этому имени."),
    "rg": Origin("наследник grep", "«ripgrep» — быстрый наследник grep."),
    "tar": Origin("tape archive",
                  "«tape archive» — «архив на ленту»: в конце 70-х бэкапы писали на магнитную "
                  "ленту."),
    "bat": Origin("cat с крыльями",
                  "bat — «летучая мышь»: автор так и пишет, что это cat с крыльями."),
    "sed": Origin("stream editor",
                  "«stream editor» — правит текст на лету, строку за строкой, не открывая файл "
                  "в окне. Ли Макмахон, Bell Labs, середина 70-х."),
    # «Свалка»
    "open": Origin("open", "«open» — «открыть», как двойной щелчок в Finder."),
    "find": Origin("find", "«find» — «найти»."),
    "du": Origin("disk usage", "«disk usage» — «сколько занято на диске»."),
    "sort": Origin("sort", "«sort» — «сортировать»."),
    "head": Origin("голова", "по-английски «голова»: начало файла."),
    "tail": Origin("хвост", "по-английски «хвост»: конец файла."),
    "wc": Origin("word count",
                 "«word count» — «счёт слов». Считает и строки (-l), и знаки — имя осталось "
                 "от слов."),
    "zip": Origin("мчаться",
                  "по-английски «мчаться», намёк на скорость. Формат придумал Фил Кац в "
                  "1989-м."),
    "unzip": Origin("un-zip", "«un-zip» — «рас-zip-овать», обратно из архива."),
    "pbcopy": Origin("pasteboard copy",
                     "«pasteboard copy» — «копировать в pasteboard»: так буфер обмена зовут в "
                     "macOS со времён NeXT."),
    "pbpaste": Origin("pasteboard paste", "«pasteboard paste» — «вставить из буфера обмена»."),
    "kill": Origin("убить",
                   "«убить», но на деле kill шлёт процессу сигнал: без флага — вежливый TERM, "
                   "«заверши работу», а -9 — KILL, от которого не отмахнёшься."),
    "pkill": Origin("process kill", "«process kill» — kill по имени процесса."),
    # FB10: задачи в фоне
    "fg": Origin("foreground", "«foreground» — «передний план»: задача снова на экране."),
    "bg": Origin("background", "«background» — «задний план, фон»: работает, экран не занимает."),
    "jobs": Origin("работы", "«jobs» — «работы, задачи»: что запущено из этой оболочки."),
    "wait": Origin("жди", "«wait» — «жди»: пока не закончатся фоновые задачи."),
    "pgrep": Origin("process grep", "«process grep» — grep по запущенным процессам."),
    "ps": Origin("process status", "«process status» — «состояние процессов»."),
    "top": Origin("верхушка", "«top» — «верхушка»: самые прожорливые процессы — сверху."),
    "xargs": Origin("arguments",
                    "от «arguments» — «аргументы»: строки, что пришли по трубе, xargs "
                    "подставляет словами после команды."),
    "cut": Origin("cut", "«cut» — «вырезать»: нужные столбцы из каждой строки."),
    "tr": Origin("translate", "«translate» — «перевести»: заменяет одни символы другими."),
    "uniq": Origin("уникальный",
                   "«unique» — «уникальный»: склеивает одинаковые соседние строки в одну."),
    "awk": Origin("Aho, Weinberger, Kernighan",
                  "по фамилиям авторов: «Aho, Weinberger, Kernighan» — Ахо, Вайнбергер и "
                  "Керниган, Bell Labs, 1977."),
    "qsv": Origin("Quicksilver",
                  "авторы просят читать «Quicksilver» — «ртуть», то есть быстрый. Наследник "
                  "xsv."),
    "duckdb": Origin("утк",
                     "«утиная база»: у её создателя Ханнеса Мюлейзена жила утка Уилбур."),
    "fd": Origin("короткий find", "короткий find: две буквы вместо четырёх и разумные привычки сразу."),
    "autoload": Origin("autoload",
                       "«autoload» — «подгрузить сам»: zsh достанет функцию, когда позовёшь."),
    "zmv": Origin("zsh mv", "«zsh mv» — mv от zsh: переименует пачку файлов по образцу."),
    # «Данные»
    "tee": Origin("тройник",
                  "от буквы T — тройник, как у труб: вывод идёт и дальше, и в файл."),
    "curl": Origin("client URL",
                   "«client URL» — «клиент для адресов». Читают и как «see URL» — «глянь "
                   "адрес»."),
    # «Картотека» и SQL
    "sqlite3": Origin("лёгкий",
                      "SQL + «lite» — «лёгкий»: вся база — один файл, без сервера. Ричард Хипп, "
                      "2000."),
    "psql": Origin("Post-Ingres",
                   "терминал PostgreSQL. Сам Postgres — «Post-Ingres», наследник базы Ingres "
                   "из Беркли."),
    "pg_dump": Origin("вывалить", "PostgreSQL + «dump» — «вывалить»: база целиком в файл."),
    # «Окружение»
    "env": Origin("environment",
                  "«environment» — «окружение»: переменные, с которыми стартует каждая "
                  "программа."),
    # FB9b: права — кто ты в системе
    "whoami": Origin("who am I", "«who am I» — «кто я»: имя, под которым тебя знает система."),
    "groups": Origin("groups", "«groups» — «группы»: в каких кругах пользователей ты состоишь."),
    "sudo": Origin("superuser do",
                   "«superuser do» — «сделай как суперпользователь»: команда от имени root. "
                   "Придумана в 1980 году в университете Буффало, чтобы не входить под root "
                   "целиком."),
    "printenv": Origin("print environment", "«print environment» — «напечатай окружение»."),
    "export": Origin("наружу",
                     "«экспорт»: переменная уходит наружу — детям, программам, что ты "
                     "запустишь отсюда."),
    "alias": Origin("псевдоним",
                    "«alias» — «псевдоним», другое имя: так по-английски говорят про "
                    "кличку или сценическое имя."),
    "set": Origin("set", "«set» — «задать»: настройки самой оболочки."),
    "source": Origin("источник",
                     "«источник»: прочитать файл и выполнить его строки здесь, в этой же "
                     "оболочке."),
    "python3": Origin("Монти Пайтона",
                      "не змея: Гвидо ван Россум назвал язык в честь «Летающего цирка Монти "
                      "Пайтона»."),
    "venv": Origin("virtual environment", "«virtual environment» — «виртуальное окружение»."),
    "deactivate": Origin("deactivate", "«deactivate» — «выключить» окружение."),
    "flake8": Origin("pyflakes",
                     "от pyflakes («хлопья» — мелкие соринки в коде) и PEP 8, свода правил "
                     "оформления Python: две проверки в одной."),
    "isort": Origin("import sort", "«import sort» — «сортировка импортов»."),
    "pytest": Origin("py test", "«py test» — «тесты для Python»; начинался в 2004-м как часть "
                     "проекта PyPy."),
    "mypy": Origin("Лехтосало",
                   "проверку типов для Python начал писать Юкка Лехтосало в 2012 году, ещё в "
                   "аспирантуре."),
    "pip": Origin("pip installs packages",
                  "«pip installs packages» — «pip ставит пакеты»: имя расшифровывается само "
                  "через себя, любимая шутка программистов."),
    "clamscan": Origin("Clam AntiVirus",
                       "проверка антивирусом ClamAV — «Clam AntiVirus», свободным антивирусом."),
    "exit": Origin("выход", "«exit» — «выход»: закончить скрипт (или закрыть оболочку) "
                            "прямо здесь."),
    "crontab": Origin("cron table",
                      "«cron table» — «таблица cron», а само слово cron — от греческого "
                      "chronos, «время». "
                      "Служба живёт в Unix с 1970-х."),
    "shellcheck": Origin("shell check",
                         "«shell check» — «проверка шелла»: читает скрипт и ищет грабли. "
                         "Видар Холен начал его в 2012-м."),
    "shasum": Origin("Secure Hash Algorithm",
                     "сумма по SHA — «Secure Hash Algorithm», «надёжный алгоритм хэша»."),
    # «Аналитика»
    "pandas": Origin("panel data",
                     "от «panel data» — «панельные данные» из эконометрики, и заодно «Python "
                     "data analysis». Так пишет автор, Уэс Маккинни."),
}


KEYS: Dict[str, Origin] = {
    "Ctrl+A": Origin("первая буква", "A — первая буква алфавита: начало строки."),
    "Ctrl+E": Origin("End", "E — End: конец строки."),
    "Ctrl+W": Origin("Word", "W — Word: стереть слово."),
    # FB5 п. 40: не «Undo» — отмена правки у zsh это Ctrl+_, а Ctrl+U стирает строку
    "Ctrl+U": Origin("NAK",
                     "Ctrl+U — 21-й символ ASCII, NAK, «отказ»: драйвер терминала Unix издавна "
                     "стирает им набранную строку. Отменить правку — Ctrl+_."),
    "Ctrl+K": Origin("Kill",
                     "K — Kill: так редактор Emacs зовёт вырезание. Стёртое не пропало — Ctrl+Y "
                     "вставит обратно."),
    "Ctrl+R": Origin("Reverse", "R — Reverse search: поиск назад, от свежих команд к старым."),
    "Ctrl+G": Origin("звонок",
                     "в таблице ASCII (общей таблице кодов знаков, 1963) это звонок (BEL); Emacs и zsh понимают его как «стоп, "
                     "передумал»."),
    "Ctrl+C": Origin("Cancel",
                     "запоминай как Cancel — «отмена»; на деле терминал шлёт программе сигнал "
                     "«прервись»."),
    "Ctrl+L": Origin("лист",
                     "в ASCII это прогон листа (form feed): старый принтер брал новый лист, "
                     "терминал чистит экран."),
    "Ctrl+D": Origin("Done",
                     "в ASCII это «конец передачи» (EOT): ввод окончен, запоминай как Done. На "
                     "пустой строке закрывает python3, sqlite3 или psql."),
    "Ctrl+Z": Origin("замри",
                     "Z — последняя буква, в ASCII символ 26. zsh шлёт программе сигнал SIGTSTP, "
                     "«terminal stop» — «замри». Управление задачами пришло из csh, рубеж 70–80-х."),
    "!!": Origin("bang",
                 "восклицательный знак программисты зовут bang: «bang bang». Приём из оболочки "
                 "csh Билла Джоя, конец 70-х."),
}

# Откуда вообще эти буквы — один раз, в уроке строки ввода
KEYS_STORY = ("Откуда буквы: из редактора Emacs (1976) и терминалов 70–80-х, где стрелок часто "
              "не было. Bash и zsh взяли раскладку Emacs, а macOS понимает Ctrl+A, E, K почти в "
              "любом поле ввода — потому и живо до сих пор.")
# Ctrl+B/F, Ctrl+P/N, Option+B/F — в шпаргалке; в уроках игры их нет
KEYS_EXTRA = ("Ctrl+B/F — Back/Forward (← →), Ctrl+P/N — Previous/Next (↑ ↓), "
              "Option+B/F — то же по словам")

# nano пишет свои сочетания внизу экрана словами — буквы из этих подписей
NANO_KEYS = ("В nano буквы — из подписей внизу: ^W — Where Is («где это»), ^O — Write Out "
             "(«записать»), ^X — eXit, ^K — вырезать, как Kill в Emacs.")


# Задача → имена (команды и клавиши), чья строка «🔤» стоит под уроком её карточки: здесь
# игрок впервые видит их в уроке или шпаргалке. Сверяет tools/audit_origins.py.
FIRST_SEEN: Dict[str, Tuple[str, ...]] = {
    # «Основы»
    "meet_terminal": ("echo",),
    "where_am_i": ("pwd",),
    # владелец 23.10 (Р4): клавиши строки — советами с первых задач, уроки клавиш — позже
    "climb_down": ("cd", "ls", "cat", "Ctrl+C", "Ctrl+A", "Ctrl+E"),
    "home_tilde": ("bash", "Ctrl+U"),
    "mkdir_p": ("mkdir",),
    "copy_move": ("cp", "mv"),
    "find_name": ("find",),
    "file_ext": ("file",),
    "star_mask": ("rm",),
    "run_script": ("chmod",),
    "history_recall": ("history", "!!", "zsh"),
    "screen_scroll": ("clear",),
    "fzf_pick": ("fzf", "grep"),
    "z_jump": ("dirs", "setopt"),
    # «Инструменты»
    "man_flag": ("man",),
    "less_search": ("less", "tail"),
    "nano_config": ("nano",),
    "vim_trap": ("vim",),
    "brew_lesson": (STUB_NAME, "which", "rg"),
    "flag_use": ("head",),
    "tldr_tar": ("tar", "tldr"),
    "json_check": ("jq",),
    "bat_lines": ("bat", "sed"),
    "job_control": ("Ctrl+Z", "fg", "bg", "kill"),
    # «Свалка»
    "open_gui": ("open",),
    "grep_r": ("wc",),
    "du_heavy": ("du", "sort", "head", "tail"),
    "batch_rename": ("autoload", "zmv"),
    "zip_pack": ("zip", "unzip"),
    "pbcopy_list": ("pbcopy", "pbpaste"),
    "kill_frozen": ("ps", "kill", "pgrep", "pkill"),
    "top_hog": ("top",),
    "rg_hunt": ("rg", "xargs"),
    "fd_hunt": ("fd",),
    "csv_by_hand": ("tr",),
    "csv_top": ("cut", "uniq", "awk", "qsv"),
    "csv_sum": ("duckdb",),
    # «Данные», базы
    "curl_api": ("curl",),
    "sqlite_open": ("sqlite3", "Ctrl+D"),
    "psql_nav": ("psql",),
    "copy_dump": ("pg_dump",),
    # «Окружение», Python
    "env_vars": ("env", "printenv"),
    "export_child": ("export",),
    "alias_rc": ("alias",),
    "perm_basics": ("whoami", "groups", "sudo"),
    "dotenv": ("set", "source"),
    "shebang_run": ("python3",),
    "script_audit": ("shasum",),
    "shell_lint": ("shellcheck",),
    "cron_line": ("crontab",),
    "av_scan": ("clamscan",),
    "venv_basics": ("venv", "deactivate"),
    "pip_offline": ("pip",),
    "py_lint": ("flake8",),
    "py_test": ("pytest",),
    "py_types": ("mypy",),
    "py_repl": ("Ctrl+D",),
    "pd_install": ("pandas",),
}

# Задача → готовые строки сверх расшифровок (история целиком)
EXTRA_LINES: Dict[str, Tuple[str, ...]] = {
    "line_edit": (KEYS_STORY,),
    "nano_config": (NANO_KEYS,),
}

MARK = "🔤 "


def origin(name: str) -> Origin:
    return COMMANDS.get(name) or KEYS[name]


def note(name: str) -> str:
    """Строка игроку: «🔤 pwd: «print working directory» — …»."""
    return f"{MARK}{name}: {origin(name).line}"


def notes(task_id: str) -> List[str]:
    """Строки «🔤» для карточки задачи: расшифровки того, что здесь впервые, и история."""
    out = [note(n) for n in FIRST_SEEN.get(task_id, ())]
    out += [MARK + line for line in EXTRA_LINES.get(task_id, ())]
    return out
