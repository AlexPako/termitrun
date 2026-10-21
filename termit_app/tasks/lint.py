"""Линтер поручений: статические проверки контента без zsh.

Каждая проверка — код ошибки (V001, H001, …) и уровень error|warn. Динамические проверки
(D001–D003: эталон и неверные решения в настоящем zsh) — dynamic_issues, прогон через
tests/refrun.Run; их зовут tests/test_reference.py и tools/lint_tasks.py.

Подготовка задачи (setup) идёт во временной песочнице /private/tmp/termit-lint-* с
отложенным запуском процессов: kit.spawn_detached только запишет команду в spawn.json,
настоящие процессы kill_frozen/top_hog не поднимаются.

T001 «не пишет наружу» видит только соседей песочницы в корне линтера: запись в ~, /tmp
или по абсолютному пути мимо box он не ловит."""
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from termit_app.tasks import base

# Слова сеттинга: в текстах поручений их быть не должно (сеттинг живёт только в темах).
FORBIDDEN: Tuple[str, ...] = (
    "свит", "заклин", "гильди", "гримуар", "дозор", "чудовищ", "мимик", "голем",
    "гидр", "башн", "кладов", "сундук", "сокровищ", "имплант", "раннер", "хонипот",
    "всеволод", "гордей", "бром", "ворон", "гайка", "шнырь", "неоград", "сан-франциско",
    # часть 9: Картотека и Хранилище — персонажи и корпорация живут только в темах
    "пломб", "дубров", "дубрав", "мерид")

# L001: транслит в именах. Имена файлов, папок, ключей и таблиц в задачах — понятные
# английские слова, а не русские слова латиницей (FB4, владелец): имя должно читаться на
# любом языке. Две сети: корни частых транслит-слов (по началу слова) и буквосочетания,
# которых в английском почти не бывает.
TRANSLIT_ROOTS: Tuple[str, ...] = (
    "adres", "arhiv", "birzh", "chek", "dengi", "dogovor", "dokument", "dozhd", "ekran",
    "etazh", "foto", "glava", "glubzh", "hvost", "itog", "kadr", "kartin", "kartotek",
    "khranil", "kniga", "kopii", "lichn", "lyudi", "musor", "muzyk", "novoe", "oboi", "opis",
    "oskolok", "otchet", "papk", "pesn", "pismo", "prochee", "proekt", "pust", "rabot",
    "raznoe", "sbor", "semya", "skrin", "sklad", "smeta", "snimok", "spisok", "staroe",
    "staryi", "svalk", "svezh", "tablic", "tajn", "vazhn", "vrazbros", "vypisk", "zagruz",
    "zakat", "zametk", "zapis", "zavis",
)
TRANSLIT_MARKS = re.compile(r"shch|zh|kh|yj|yy|iy$|aya$|oye$|yye$|ii$")
# Слова, где эти буквосочетания честные: технические и имена собственные данных (люди,
# города, улицы — их латинская запись и есть английское имя). Имена из генераторов
# добавляет translit_ok(), чтобы списки не расходились.
TRANSLIT_OK: Set[str] = {"ascii", "yyyy", "sockhttp", "frosya"}
# треки без проверки транслита (было: basics на время правок FB4; сейчас — все проверяются)
TRANSLIT_SKIP_TRACKS: Tuple[str, ...] = ()
_LATIN_WORD = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")
_TRANSLIT_OK_CACHE: Optional[Set[str]] = None

# Что игрок знает с первого дня: команды тренажёра и самые первые команды оболочки.
BASE_COMMANDS: Set[str] = {
    "ans", "cd", "ls", "cat", "pwd",
    "task", "hint", "reset", "giveup", "skip", "quit", "bug", "ask",
}

# Команды из эталона и третьей подсказки, которые не преподаются scroll и это нормально.
EXTRA_OK: Dict[str, Set[str]] = {
    # «debug false», «true на false» — ключи и значения JSON в описании правки, не команды
    "boss_tools": {"debug", "true"},
    # вариант B: копия домой и обратно — cp вводится подсказками 2–3 (карточка — про ~,
    # а сам cp преподаёт copy_move чуть позже; в варианте A он не нужен)
    "home_tilde": {"cp"},
    # вариант C: nano назван в тексте, клавиши (Ctrl+O, Enter, Ctrl+X) — во 2-й подсказке;
    # пара открывается после стража основ, а nano_config (трек инструментов) — не раньше
    "fzf_pick": {"nano"},
    # stamp — учебная программа задачи в ~/tools/bin (её и ищут по PATH), а не команда урока
    "path_which": {"stamp"},
    # rep и mkcd — короткие имена, которые игрок заводит сам (alias, функция); eval — только в
    # скрипте прогона: alias из source в той же строке zsh -c не видит
    "alias_rc": {"rep", "mkcd", "eval"},
    # графы sku и note в списках «(sku, qty)», «…, note = …» — не команды
    "merge_into": {"sku", "qty", "note"},
    # py_test: discount — имя функции в prices.py; py_types: from — строка Python
    # «from typing import Optional», которую игрок вписывает в nano
    "py_test": {"discount", "price"},
    "py_types": {"from"},
    # datapeek — учебный пакет задачи: его консольную команду игрок сам и ставит (pip)
    "pip_offline": {"datapeek"},
}

# D005: показанный эталон (shown_solution) — то, что игрок видит в разборе и копирует. Если он
# отличается от скрипта для тестов (reference), его гоняют в zsh как есть, и он обязан решать
# задачу. Исключения — только здесь и с причиной. Ключ — id задачи или «id:вариант».
# Режим: skip — не исполняется по природе; read — команда показывает ответ, игрок сдаёт его
# сам: ответ обязан быть в выводе; look — показывает данные для подсчёта: команда обязана
# отработать без ошибки. Часть: first/last — гонять только первый/последний шаг (шаги — через
# «→» или «, »).
SHOWN_RULES: Dict[str, Tuple[str, Optional[str], str]] = {
    "meet_terminal:0": ("skip", None, "$SHELL приходит из окружения терминала, а прогон эталонов "
                                   "идёт без него (zsh -f); та же оболочка — эталон echo $0"),
    "meet_terminal:1": ("skip", None, "$TERM_PROGRAM приходит из окружения терминала, а прогон "
                                   "эталонов идёт без него (zsh -f)"),
    "climb_down": ("read", None, "cat печатает записку, слово из неё игрок сдаёт сам"),
    "home_tilde": ("read", None, "cat печатает записку, слово из неё игрок сдаёт сам"),
    "hidden_cache": ("read", None, "ls -la && cat печатает тайник, ответ игрок сдаёт сам"),
    "file_ext": ("read", None, "ls печатает имена, cat — записку, file — что внутри: ответ "
                           "игрок сдаёт сам"),
    # FB9b: блок прав в «Окружении» — команда печатает ответ, игрок сдаёт его сам
    "perm_basics": ("read", None, "whoami, groups и id печатают имя, группу и номер — ответ "
                                  "игрок сдаёт сам"),
    "perm_rwx": ("read", None, "после chmod cat печатает слово — ответ игрок сдаёт сам"),
    "perm_rwx:2": ("look", None, "после chmod ls показывает файлы, сосчитать их — работа "
                                 "игрока"),
    "read_long_list": ("read", None, "ls -l печатает строки с правами и владельцем, имя "
                                     "игрок сдаёт сам"),
    "hidden_cache:2": ("look", None, "ls -la показывает файлы, сосчитать их — работа игрока"),
    "man_flag": ("skip", None, "клавиши внутри man: /слово, n, q"),
    "columnar:1": ("look", None, "три суммы pg_column_size рядом — самую большую графу игрок "
                                 "называет сам"),
    "segments": ("look", None, "GROUP BY печатает узлы и число строк на каждом — наибольшее "
                               "или наименьшее игрок выбирает сам"),
    "alias_rc:0": ("skip", None, "alias, заведённый source в той же строке, zsh -c прогона не "
                                 "видит (разбирает строку целиком заранее); у игрока команды "
                                 "идут по одной — скрипт прогона зовёт rep через eval"),
    "alias_rc:1": ("skip", None, "alias, заведённый source в той же строке, zsh -c прогона не "
                                 "видит; скрипт прогона зовёт rep через eval"),
    "flag_review:2": ("read", None, "grep -n -m 1 печатает строку с номером, номер игрок "
                                 "сдаёт сам"),
    "flag_use": ("read", None, "grep -c и ls -r печатают ответ, игрок сдаёт его сам"),
    "less_search": ("skip", None, "клавиши внутри less: /слово, G, q"),
    "nano_config": ("skip", None, "правка руками в nano, Ctrl+O, Ctrl+X"),
    "vim_trap": ("skip", None, "клавиши внутри vim"),
    "vim_escape": ("skip", None, "клавиши внутри vim"),
    "vim_purge": ("skip", None, "клавиши внутри vim"),
    "boss_tools": ("skip", None, "правка JSON руками в редакторе, описана словами"),
    "json_check": ("skip", None, "jq . на сломанном файле по природе пишет parse error и "
                                 "выходит с ошибкой; номер из сообщения игрок сдаёт сам"),
    "json_check:1": ("skip", None, "jq . по каждому файлу: у сломанных — parse error и код "
                                   "ошибки; имя целого игрок сдаёт сам"),
    "json_check:2": ("skip", None, "правка JSON руками в редакторе, описана словами"),
    "json_config": ("skip", None, "ошибку синтаксиса чинят руками в nano, описано словами; "
                                  "jq и mv — после правки (скрипт с готовым текстом — в "
                                  "reference)"),
    "script_audit:0": ("read", None, "grep -n печатает ФАЙЛ:СТРОКА:текст опасных мест, имя "
                                     "скрипта игрок сдаёт сам"),
    "script_audit:1": ("skip", None, "shasum -c при несовпадении по природе выходит с кодом 1; "
                                     "имя со словом FAILED игрок сдаёт сам"),
    "script_audit:2": ("look", None, "grep -n печатает ФАЙЛ:СТРОКА:текст, имя и номер игрок "
                                     "сдаёт сам (эталон режет их cut и tr)"),
    "boss_env": ("skip", None, "ошибку синтаксиса и чужие строки ~/.zshrc чинят руками в nano, "
                               "описано словами (скрипт с готовым текстом — в reference)"),
    "boss_py": ("skip", None, "подмену и враньё report.py чинят руками в nano, описано словами "
                              "(скрипт с готовым текстом — в reference)"),
    # FB15: «Аналитика» — эталон печатает таблицу pandas, число из неё игрок сдаёт сам
    "pd_dates:1": ("look", None, "resample печатает итоги по месяцам, наибольший игрок выбирает "
                                 "сам (эталон для тестов зовёт .max())"),
    "pd_pivot": ("look", None, "печать сводной (или строки города): клетку или наименьший канал "
                               "игрок находит сам (эталон для тестов берёт клетку кодом)"),
    "pd_sql:1": ("read", None, "head(3) печатает лидеров с суммами, имя первого игрок сдаёт сам"),
    "boss_pylib": ("skip", None, "враньё pipeline.py чинят руками в nano, описано словами "
                                 "(скрипт с готовым текстом — в reference)"),
    "py_run:1": ("skip", None, "скрипт падает по природе (traceback в stderr, код 1); тип и "
                               "номер строки игрок сдаёт сам (эталон режет их tail и grep)"),
    "py_repl:0": ("look", None, "dir() печатает список имён, сосчитать имена без _ — работа "
                                "игрока (эталон считает grep -vc)"),
    "py_repl:1": ("read", None, "help() печатает подпись функции, имя второго параметра игрок "
                                "сдаёт сам"),
    "pip_offline:1": ("look", None, "pip list печатает таблицу пакетов с колонками в "
                                    "пробелах, имя и версию зависимости игрок сдаёт сам"),
    "brew_lesson": ("read", "first", "учебный brew печатает формулу или квитанцию, игрок сдаёт "
                                     "её сам через ans"),
    "tldr_tar": ("solve", "last", "первый шаг — подсмотреть tldr, последний — сама команда"),
    "find_name:2": ("read", "first", "find печатает все config.yaml, путь с /prod/ выбирает "
                                     "игрок"),
    "du_heavy": ("read", None, "du | sort печатает список, имя из нужной строки сдаёт игрок"),
    "kill_frozen": ("skip", None, "PID берётся с экрана; а pkill по шаблону вне песочницы задел "
                                  "бы чужие процессы — эталон D001 бьёт по $TERMIT_BOX"),
    "top_hog": ("skip", None, "PID берётся с экрана top/ps"),
    "boss_finder:0": ("skip", None, "схема «mkdir + mv по маскам», точный скрипт — в reference"),
    "rg_hunt:0": ("read", None, "grep -rn печатает ФАЙЛ:СТРОКА:текст, ФАЙЛ:СТРОКА игрок сдаёт "
                                "сам (эталон отрезает текст через cut)"),
    # FB12 (N25): эталон разбора совпадает с третьей подсказкой — правка первой строки в nano
    "shebang_run:0": ("skip", None, "первую строку правят руками в nano; скрипт для тестов "
                                    "(reference) делает то же sed'ом"),
    "shebang_run:2": ("skip", None, "первую строку дописывают руками в nano; скрипт для тестов "
                                    "(reference) делает то же через временный файл"),
    "bat_lines:0": ("read", None, "cat -n печатает весь файл с номерами, номер timeout под "
                                  "нужным блоком игрок сдаёт сам"),
    "bat_lines:2": ("read", None, "grep -n '' | grep ':N:' печатает строку N всех трёх файлов, "
                                  "непохожую выбирает игрок"),
    "fzf_pick:2": ("skip", None, "правка слова руками в nano, Ctrl+O, Ctrl+X"),
    "z_jump": ("skip", None, "стек каталогов включает setopt auto_pushd в песочном .zshrc; "
                             "показан маршрут со стрелками, скрипт с setopt — в reference"),
    # FB4: уроки навигации — клавиши строки ввода и истории (↑, Ctrl+A, Ctrl+R, !!, !N): в
    # zsh -c их нет; показан путь клавишами, скрипт с готовой строкой — в reference
    "line_edit": ("skip", None, "клавиши строки ввода: ↑, Ctrl+A, Ctrl+W, Option+←"),
    # FB13: курсор и буфер — Option+клик и карман zsh (Ctrl+W, Ctrl+Y) — клавиши и мышь
    "cursor_clip:0": ("skip", None, "Option+клик по опечатке — мышь в строке ввода"),
    # FB18: мышь — двойной и тройной клик по выводу echo/pwd: первый шаг печатает ответ
    "cursor_clip:1": ("read", "first", "echo печатает код, игрок копирует его мышью и сдаёт"),
    "cursor_clip:2": ("read", "first", "pwd печатает путь, игрок копирует его мышью и сдаёт"),
    "cut_paste": ("skip", None, "карман zsh: Ctrl+W, Ctrl+Y, Ctrl+A/E, Option+← → — клавиши "
                                "строки ввода"),
    "history_recall": ("skip", None, "поиск и подстановка из истории (Ctrl+R, !!, !N) — в "
                                     "zsh -c истории нет"),
    "screen_scroll": ("read", None, "cat печатает длинный вывод, слово из нужной строки игрок "
                                    "находит прокруткой и сдаёт сам"),
    # FB10: лайфхаки — поиск по экрану (клавиши iTerm2), быстрая правка (Esc ., !$, ^a^b —
    # в zsh -c истории нет), задачи в фоне (Ctrl+Z и fg — клавиши; скрипт с & — в reference)
    "screen_find": ("read", None, "cat печатает длинный вывод, слово или код игрок находит "
                                  "поиском Cmd+F или метками и сдаёт сам"),
    "quick_fix": ("skip", None, "Esc ., !$ и ^старое^новое берут прошлую команду из истории — "
                                "в zsh -c её нет"),
    "job_control": ("skip", None, "Ctrl+Z и fg — клавиши; показан путь клавишами, скрипт с & — "
                                  "в reference"),
    "fd_hunt:1": ("read", "first", "find печатает все .env.example, самый глубокий путь "
                                   "выбирает игрок"),
    "csv_by_hand:1": ("read", None, "grep -n печатает НОМЕР:amount, номер игрок сдаёт сам "
                                    "(эталон отрезает имя через cut)"),
    "csv_top:0": ("read", None, "uniq -c печатает «ЧИСЛО ГОРОД», город игрок сдаёт сам"),
    "csv_top:2": ("read", None, "uniq -c печатает «ЧИСЛО СТАТУС», статус игрок сдаёт сам"),
    "csv_sum:1": ("read", None, "печатает «СУММА МЕСЯЦ», месяц игрок сдаёт сам"),
    # трек «Данные»: края и счёт строк — ответ собирает игрок по выводу
    "head_tail": ("look", None, "wc -l печатает строки вместе с заголовком, head/tail — края "
                                "файла; вычесть заголовки и взять поле до запятой — работа "
                                "игрока (эталон считает через $(( )) и cut)"),
    "curl_api:2": ("look", None, "curl -i печатает заголовки, число из Content-Length и счёт "
                                 "лотов игрок сдаёт сам (эталон вырезает его grep и tr)"),
    # трек «Базы данных» (9а): первая база — смотреть .tables/.schema, считать — игроку
    "sqlite_open": ("look", None, "sqlite3 печатает .tables и .schema, число таблиц или "
                                  "колонок и имя игрок собирает сам"),
    # трек «SQL и PostgreSQL» (9б): опись сервера и корзины — смотреть и считать игроку
    "psql_nav": ("look", None, "psql печатает \\dt, \\d и \\l, число таблиц или баз, тип и "
                               "имя графы игрок собирает сам"),
    "case_when": ("read", None, "запрос печатает все корзины с итогами, число нужной корзины "
                                "игрок сдаёт сам"),
    "window_lag:0": ("look", None, "запрос печатает рост каждого месяца, наибольший — месяц и "
                                   "число — игрок выбирает сам"),
    "window_lag:1": ("read", None, "запрос печатает накопительный итог каждого месяца, итог "
                                   "нужного игрок сдаёт сам"),
}
SHOWN_MODES = ("skip", "read", "look", "solve")

HINTS_N = 3
HINT_MAX = 220
JACCARD_MAX = 0.7


@dataclass
class Issue:
    task: str
    code: str
    level: str          # error | warn
    message: str


# --- Общие помощники (их же берёт test_theme) -------------------------------------------

# Токены команд в карточке scroll: латинские слова-команды (не имена файлов и не расширения)
# и ключи вида -x / --help. Каждый обязан прозвучать в мини-уроке персонажа.
_WORD = re.compile(r"(?<![\w./$~{%*:\\(|-])[a-z][a-z0-9_]*(?![\w./?*|(])")
_FLAG = re.compile(r"(?<![\w-])--?[A-Za-z0-9]+")


def scroll_tokens(text: str) -> set:
    words = {m.group() for m in _WORD.finditer(text) if len(m.group()) > 1}
    return words | {m.group() for m in _FLAG.finditer(text)}


# Разделители команд в эталоне и подсказках: операторы оболочки, стрелки и связки прозы.
_CMD_SEP = re.compile(r"&&|\|\||[;|\n,→—(){}`]|\$\(|\s(?:затем|потом|и|или|а)\s")
_CMD_WORD = re.compile(r"^[a-z][a-z0-9_-]*$")


# Раскрытие скобок zsh «{q1,q2}» / «a.{txt,md}»: внутри — куски имён, а не команды.
_BRACE_LIST = re.compile(r"\{[^{}\s]*,[^{}\s]*\}")
# Выбор в маске zsh «*.(#i)(jpg|png|heic)»: внутри — расширения, а не команды.
_ALT_GROUP = re.compile(r"\([^()\s]*\|[^()\s]*\)")
# Строка в одинарных кавычках — аргумент (шаблон grep «',kazan,'», программа awk): запятые и
# палки внутри не разделяют команды.
_SINGLE_QUOTED = re.compile(r"'[^'\n]*'")
_SHELL_C = re.compile(r"(?<![\w-])(?:sh|zsh|bash)\s+-c\s+(?:'([^'\n]*)'|\"([^\"\n]*)\")")


# --- SQL в текстах (часть 9) ------------------------------------------------------------
# Ключевые слова SQL — токены «сначала учим» (их ловят заглавными: S006 требует заглавные в
# SQL-строках). Фразы считаются целиком: LEFT JOIN — не то же, что JOIN.
SQL_PHRASES = ("IS NOT NULL", "IS NULL", "NOT NULL", "ORDER BY", "GROUP BY", "PRIMARY KEY",
               "FOREIGN KEY", "LEFT JOIN", "INNER JOIN", "FULL JOIN", "CROSS JOIN",
               "UNION ALL", "ON CONFLICT", "INSERT INTO", "DELETE FROM", "CREATE TABLE",
               "CREATE INDEX", "CREATE VIEW", "IF NOT EXISTS", "DO NOTHING", "DO UPDATE")
SQL_KEYWORDS = frozenset((
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "IS", "NULL", "LIKE", "ILIKE",
    "BETWEEN", "DISTINCT", "AS", "ON", "JOIN", "LIMIT", "OFFSET", "HAVING", "DESC", "ASC",
    "VALUES", "SET", "UPDATE", "DELETE", "INSERT", "INTO", "CREATE", "TABLE", "INDEX", "VIEW",
    "DROP", "ALTER", "BEGIN", "COMMIT", "ROLLBACK", "TRANSACTION", "UNIQUE", "CHECK",
    "REFERENCES", "DEFAULT", "CASE", "WHEN", "THEN", "ELSE", "END", "UNION", "ALL", "WITH",
    "EXISTS", "RETURNING", "EXPLAIN", "PRAGMA", "INTEGER", "TEXT", "REAL", "BOOLEAN",
    "SERIAL", "IDENTITY", "JSONB", "OVER", "PARTITION", "WINDOW", "TRUE", "FALSE"))
# начало SQL-строки (команда в двойных кавычках): оператор или точечная/мета-команда
SQL_STATEMENTS = frozenset(("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER",
                            "BEGIN", "COMMIT", "ROLLBACK", "WITH", "PRAGMA", "EXPLAIN",
                            "VALUES", "TABLE"))
# функции SQL строчными (как в документации SQLite) — остальные узнаются по ЗАГЛАВНЫМ(
SQL_LOWER_FUNCS = frozenset(("changes", "total_changes", "last_insert_rowid", "strftime",
                             "datetime", "date_trunc", "typeof", "json_extract", "ifnull",
                             "to_char", "jsonb_array_elements", "jsonb_array_elements_text"))
SQL_DOT = ("tables", "schema", "headers", "mode", "import", "backup", "quit", "once", "output",
           "read")
SQL_META = ("copy", "dt", "dn", "l", "d", "x", "q")
_SQL_PHRASE = re.compile(r"(?<![\w])(" + "|".join(re.escape(p).replace(r"\ ", r"\s+")
                                                   for p in SQL_PHRASES) + r")(?![\w])")
_SQL_WORD = re.compile(r"(?<![\w.$-])([A-Z][A-Z_]*)(?![\w])")
_SQL_FUNC = re.compile(r"(?<![\w.$])([A-Za-z_][A-Za-z0-9_]*)\(")
_SQL_OP = re.compile(r"::|->>|->|@>")
_SQL_DOTCMD = re.compile(r"(?<![\w./-])\.(" + "|".join(SQL_DOT) + r")(?![\w])")
_SQL_METACMD = re.compile(r"(?<![\w\\])\\(" + "|".join(SQL_META) + r")(?![\w])")
# строка в двойных кавычках: SQL, если начинается оператором SQL (любым регистром), точкой
# sqlite3 или мета-командой psql
_DOUBLE_QUOTED = re.compile(r'"([^"\n]*)"')


def is_sql(body: str) -> bool:
    b = body.lstrip()
    if b.startswith(".") or b.startswith("\\"):
        return bool(re.match(r"[.\\][a-z]", b))
    first = re.match(r"[A-Za-z]+", b)
    return bool(first) and first.group().upper() in SQL_STATEMENTS


def sql_strings(text: str) -> List[str]:
    """Тела SQL-строк в двойных кавычках (без кавычек)."""
    return [m.group(1) for m in _DOUBLE_QUOTED.finditer(text) if is_sql(m.group(1))]


def strip_sql(text: str) -> str:
    """Текст, где SQL-строки в двойных кавычках заменены пустыми \"\"."""
    return _DOUBLE_QUOTED.sub(lambda m: '""' if is_sql(m.group(1)) else m.group(0), text)


def sql_tokens(text: str) -> Set[str]:
    """SQL-токены текста: фразы (ORDER BY…), ключевые слова ЗАГЛАВНЫМИ, функции NAME( (ЗАГЛАВНЫЕ
    и SQL_LOWER_FUNCS), операторы :: ->> -> @>, точечные команды sqlite3 (.tables…) и
    мета-команды psql (\\dt…). Литералы в одинарных кавычках — данные, не токены."""
    text = _SINGLE_QUOTED.sub("''", text)
    out = set()
    for m in _SQL_PHRASE.finditer(text):
        out.add(re.sub(r"\s+", " ", m.group(1)))
    rest = _SQL_PHRASE.sub(" ", text)
    for m in _SQL_FUNC.finditer(rest):
        name = m.group(1)
        if name in SQL_KEYWORDS:
            continue
        if (name.isupper() and len(name) > 1) or name in SQL_LOWER_FUNCS:
            out.add(name + "(")
    out |= {m.group(1) for m in _SQL_WORD.finditer(rest) if m.group(1) in SQL_KEYWORDS}
    out |= set(_SQL_OP.findall(text))
    out |= {"." + m.group(1) for m in _SQL_DOTCMD.finditer(text)}
    out |= {"\\" + m.group(1) for m in _SQL_METACMD.finditer(text)}
    return out


_SQL_LOWER_KW = re.compile(r"(?<![\w.])(" + "|".join(sorted(
    (k.lower() for k in SQL_KEYWORDS | {"order", "group", "by", "primary", "key", "left",
                                        "inner", "join"}), key=len, reverse=True))
    + r")(?![\w(])")


def lower_sql_keywords(body: str) -> List[str]:
    """Строчные ключевые слова в теле SQL-строки (литералы '…' не в счёт) — для S006."""
    return sorted(set(_SQL_LOWER_KW.findall(_SINGLE_QUOTED.sub("''", body))))


def command_words(text: str) -> Set[str]:
    """Первые слова команд. Однобуквенные слова — клавиши внутри man/less/vim (n, q, i, u),
    а не команды оболочки, их не считаем. Раскрытие скобок {a,b} и выбор (a|b) в маске
    выбрасываются, строки в одинарных кавычках — тоже, как и SQL в двойных кавычках
    («SELECT name, city …», «.tables»): запятая в нём — не граница команды."""
    out = set()
    # программа оболочки внутри кавычек (zsh -c '…', -exec sh -c '…') — тоже команды
    for single, double in _SHELL_C.findall(text):
        out |= command_words(single or double)
    text = strip_sql(text)
    text = _SINGLE_QUOTED.sub("''", text)
    for seg in _CMD_SEP.split(_ALT_GROUP.sub("", _BRACE_LIST.sub("", text))):
        words = seg.strip().split()
        if (words and _CMD_WORD.match(words[0]) and len(words[0]) > 1
                and words[0] not in _FLAG_WORDS):
            out.add(words[0])
    return out


def _flag_word_set() -> Set[str]:
    """FB4: расшифровки флагов в карточках («-l — long», «(recursive — вглубь)») стоят там,
    где разбор ждёт команду, — их первые слова командами не считаем. file и kill — настоящие
    команды (file_ext, kill_frozen; у kill -9 слово KILL), их оставляем."""
    from termit_app import flag_words
    words = {w.split()[0].lower() for w, _ in flag_words.FLAG_WORDS.values()}
    words |= {w.split()[0].lower() for w, _ in flag_words.QUALIFIERS.values()}
    return words - {"file", "kill"}


_FLAG_WORDS = _flag_word_set()


def _first_words(text: str) -> Set[str]:
    """Первые слова всех сегментов, без фильтра длины: для программы импланта вроде z."""
    out = set()
    for seg in _CMD_SEP.split(text):
        words = seg.strip().split()
        if words:
            out.add(words[0])
    return out


def _jaccard(a: Set[str], b: Set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def _skeleton(text: str) -> Set[str]:
    """Слова текста варианта, где {поля} и числа заменены на #."""
    text = re.sub(r"\{[^{}]*\}", "#", text.lower())
    text = re.sub(r"\d+", "#", text)
    return set(re.findall(r"[\w#]+", text))


def _variants(task) -> List[base.Variant]:
    return [v if isinstance(v, base.Variant) else base.Variant(text=v) for v in task.variants]


def _raw_hints(task, v: base.Variant) -> Sequence[str]:
    return task.hints if v.hints is None else v.hints


# --- Тема по умолчанию (через функции: в тестах их подменяют) ---------------------------

def _theme_entry(task) -> dict:
    from termit_app import theme
    return theme.load(theme.DEFAULT).get("tasks", {}).get(task.id) or {}


def _lesson(task) -> Optional[str]:
    return _theme_entry(task).get("lesson") or None


def _variant_lessons(task) -> dict:
    """FB12 (п. 38): уроки вариантов {номер: текст} темы по умолчанию (без варианта 0)."""
    return dict(_theme_entry(task).get("variant_lessons") or {})


def _intro_lines(task) -> Sequence[str]:
    return _theme_entry(task).get("intro") or ()


# --- Что преподано к этой задаче --------------------------------------------------------

def taught_for(task) -> Set[str]:
    """BASE_COMMANDS + scroll этой задачи и всех задач раньше по реестру. Задача не из
    реестра (фиктивная) считается последней: ей преподано всё."""
    from termit_app.tasks import registry
    taught = set(BASE_COMMANDS)
    for t in registry.all_tasks().values():
        if t.id == task.id:
            break
        taught |= scroll_tokens(t.scroll or "")
    return taught | scroll_tokens(task.scroll or "") | EXTRA_OK.get(task.id, set())


# --- Подготовка в песочнице ---------------------------------------------------------------

class _Blank(base.Task):
    """Пустое поручение: sandbox.create готовит каркас песочницы, сам setup зовём отдельно,
    чтобы проверить state до записи в task.json."""
    id = "lint_blank"


def _archive_digest(path: Path, data: bytes) -> Optional[bytes]:
    """Архив сравниваем по именам и содержимому членов: метки времени не в счёт."""
    h = hashlib.sha1()
    try:
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for name in sorted(zf.namelist()):
                    h.update(name.encode() + b"\0" + zf.read(name))
            return h.digest()
        if path.name.endswith((".tar", ".tar.gz", ".tgz")):
            with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                for m in sorted(tf.getmembers(), key=lambda m: m.name):
                    f = tf.extractfile(m) if m.isfile() else None
                    h.update(m.name.encode() + b"\0" + (f.read() if f else b""))
            return h.digest()
    except (OSError, tarfile.TarError, zipfile.BadZipFile, EOFError):
        return None
    return None


def skip_heavy(rel_dir: str, name: str) -> bool:
    """Папки, которые не хэшируются и не обходятся: .venv* где угодно и .termit/stock."""
    return name.startswith(".venv") or (rel_dir == ".termit" and name == "stock")


def tree_hash(box: Path) -> str:
    """Хэш дерева «имя + содержимое» (ссылки — по цели), mtime не учитываются. Путь самой
    песочницы в содержимом и целях ссылок заменён меткой: он у каждой песочницы свой (В1)."""
    h = hashlib.sha1()
    box = Path(box)
    marks = sorted({os.fsencode(str(box)), os.fsencode(str(box.resolve()))}, key=len,
                   reverse=True)

    def norm(b: bytes) -> bytes:
        for m in marks:
            b = b.replace(m, b"<BOX>")
        return b
    for dirpath, dirnames, filenames in os.walk(box, followlinks=False):
        rel_dir = os.path.relpath(dirpath, box)
        # готовые venv (.venv*) и запас песочницы — десятки мегабайт чужого кода (часть 7, A4)
        dirnames[:] = sorted(d for d in dirnames if not skip_heavy(rel_dir, d))
        h.update(b"D" + rel_dir.encode() + b"\0")
        for name in sorted(filenames + [d for d in dirnames
                                        if os.path.islink(os.path.join(dirpath, d))]):
            p = Path(dirpath) / name
            rel = os.path.join(rel_dir, name).encode()
            if p.is_symlink():
                h.update(b"L" + rel + b"\0" + norm(os.readlink(p).encode()) + b"\0")
                continue
            try:
                data = p.read_bytes()
            except OSError:
                data = b"<unreadable>"
            digest = _archive_digest(p, data) or hashlib.sha1(norm(data)).digest()
            h.update(b"F" + rel + b"\0" + digest)
    return h.hexdigest()


def _progress_problems(task, box: Path, state: dict) -> List[Tuple[str, str]]:
    """T002: у схватки progress() на свежей песочнице — список той же длины, что steps."""
    if not task.steps:
        return []
    try:
        steps = task.steps_for(state)
        prog = task.progress(base.Ctx(box=Path(box), state=state))
    except Exception as e:      # noqa: BLE001 — упавший progress — тоже находка
        return [("T002", f"progress()/steps_for() упал: {type(e).__name__}: {e}")]
    if prog is None or len(prog) != len(steps):
        got = "None" if prog is None else f"{len(prog)} шагов"
        return [("T002", f"progress() даёт {got}, а steps — {len(steps)}")]
    return []


def db_engine(task, engine: Optional[str]) -> Optional[str]:
    """Движок для make_state: задачам БД (треки db, sql) — engine (None — SQLite), прочим —
    None. Картотека — всегда SQLite (dbkit.choose_engine), задача стенда (stand = "pg") —
    всегда PostgreSQL (без него её нет), общие задачи Хранилища — какой просили."""
    from termit_app.tasks import dbkit
    track = getattr(task, "track", "")
    if track not in dbkit.DB_TRACKS:
        return None
    if track == "db":
        return dbkit.DEFAULT_ENGINE
    if getattr(task, "stand", None) == "pg":
        return "pg"
    return engine or dbkit.DEFAULT_ENGINE


_STOCK_TPL: Dict[str, Path] = {}


def _stock_template(kind: str) -> Path:
    """.termit/stock вида kind — один на процесс линтера, во временной папке (убирается при
    выходе): рядом с песочницами её быть не должно (T001 «пишет рядом»). В имени PID: если
    процесс погибнет без atexit (воркер пула, kill), папку подберёт tmpdirs.sweep."""
    import atexit
    from termit_app import pyenvs, tmpdirs
    tpl = _STOCK_TPL.get(kind)
    if tpl is None or not (tpl / ".termit" / "stock").is_dir():
        tpl = Path(tmpdirs.mkdtemp(f"termit-lint-stock-{kind}", dir="/private/tmp"))
        atexit.register(shutil.rmtree, str(tpl), True)
        (tpl / ".termit").mkdir()
        pyenvs.stock_into(tpl, kind)
        _STOCK_TPL[kind] = tpl
    return tpl / ".termit" / "stock"


def _prepare(task, seed: int, variant: int, root: Path,
             engine: Optional[str] = None) -> Tuple[dict, str, List[Tuple[str, str]]]:
    """Один прогон setup: (state, хэш дерева, находки (код, текст)): T001 — подготовка,
    T002 — progress() схватки не совпадает с steps по длине. engine — движок задач БД."""
    from termit_app import sandbox
    box, _ = sandbox.create(_Blank(), 0, root=root, defer_spawn=True)
    if getattr(task, "stock", None):        # запас venv/колёс (часть 7, A4) — как create
        # один на корень прогона: setup запас только читает (клон venv, копии колёс), а
        # .termit/stock в хэш дерева не входит — ссылка вместо копии (I2 ревью P4)
        os.symlink(_stock_template(task.stock), box / ".termit" / "stock")
    # с TERMIT_LAUNCHED kit.spawn_detached минует очередь и запускает сразу — снимаем
    launched = os.environ.pop("TERMIT_LAUNCHED", None)
    try:
        try:
            state = task.make_state(box, seed, variant=variant, engine=db_engine(task, engine))
        finally:
            if launched is not None:
                os.environ["TERMIT_LAUNCHED"] = launched
        problems = []
        if os.path.lexists(box / ".termit" / "pids"):
            problems.append(("T001", "setup запустил процессы в родителе (есть .termit/pids): "
                                     "запуск обязан идти через отложенную очередь"))
        try:
            json.dumps(state, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            problems.append(("T001", f"state не сериализуется в JSON ({e})"))
        if task.start_dir:
            try:
                d = box / task.start_dir.format(**state)
            except (KeyError, IndexError, ValueError, AttributeError):
                d = None        # шаблон сломан — это скажет B001
            if d is not None and not d.is_dir():
                problems.append(("T001", f"start_dir {task.start_dir!r} не существует после setup"))
        digest = tree_hash(box)
        # видно только соседей песочницы в корне линтера; запись в ~, /tmp или по
        # абсолютному пути мимо box эта проверка не ловит
        outside = sorted(set(os.listdir(root)) - {box.name, box.name + ".owned"})
        if outside:
            problems.append(("T001", f"setup пишет рядом с песочницей: {', '.join(outside)}"))
        problems.extend(_progress_problems(task, box, state))
        for word in _tree_translit(task, box):
            problems.append(("L001", f"setup создал имя с транслитом «{word}» — "
                                     "нужно английское слово"))
        return state, digest, problems
    finally:
        sandbox.destroy(box)


def _states(task, seeds: Iterable[int], add: Callable,
            engine: Optional[str] = None) -> List[dict]:
    from termit_app import tmpdirs
    root = Path(tmpdirs.mkdtemp("termit-lint", dir="/private/tmp"))
    out = []
    try:
        for v in range(max(1, len(task.variants))):
            for seed in seeds:
                where = f"seed {seed}, вариант {v}"
                try:
                    st1, h1, problems = _prepare(task, seed, v, root, engine)
                    st2, h2, _ = _prepare(task, seed, v, root, engine)
                except Exception as e:      # noqa: BLE001 — любая поломка setup — находка
                    add("T001", "error", f"{where}: setup упал: {type(e).__name__}: {e}")
                    continue
                for code, p in problems:
                    add(code, "error", f"{where}: {p}")
                if st1 != st2 or h1 != h2:
                    what = "state" if st1 != st2 else "дерево файлов"
                    add("T001", "error", f"{where}: setup недетерминирован ({what} разное)")
                out.append(st1)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return out


# --- Проверки -----------------------------------------------------------------------------

def _check_variants(task, min_variants: int, level: str, add) -> None:
    vs = _variants(task)
    if len(vs) < min_variants:
        add("V001", level, f"вариантов {len(vs)}, нужно не меньше {min_variants}")
    for i in range(len(vs)):
        for j in range(i + 1, len(vs)):
            if _jaccard(_skeleton(vs[i].text), _skeleton(vs[j].text)) >= JACCARD_MAX:
                add("V002", "error", f"варианты {i} и {j} различаются только числами/полями")


def _check_hint_count(task, add) -> None:
    for i, v in enumerate(_variants(task) or [base.Variant("")]):
        n = len(_raw_hints(task, v))
        if getattr(task, "py_edit", False) and n == HINTS_N - 1:
            n += 1          # третья подсказка PyEditTask — точная правка, её строит движок
        if n != HINTS_N:
            add("H001", "error", f"вариант {i}: подсказок {n}, нужно ровно {HINTS_N}")


def neutral_texts(task) -> List[str]:
    texts = [task.title, task.scroll or "", task.solution, task.explain, task.spell,
             *task.hints, *task.steps, *task.alternatives]
    for i, v in enumerate(_variants(task)):
        texts += [v.text, v.solution or "", v.explain or "", *(v.hints or ()), *v.alternatives]
        try:        # шаги схватки по варианту (могут зависеть только от номера варианта)
            texts += task.steps_for({"_variant": i})
        except Exception:       # noqa: BLE001 — шагам нужен полный state: проверит T002
            pass
    return texts


def _check_variant_pairs(task, add) -> None:
    """S003: свой solution без своего solution_script при классовом скрипте — явно задать
    скрипт (движок классовый уже не наследует, но автор должен решить сам).
    H002 (warn): solution и hints у варианта заданы не парой — третья подсказка и эталон
    разъедутся."""
    for i, v in enumerate(_variants(task)):
        if v.solution is not None and v.solution_script is None and task.solution_script:
            add("S003", "error", f"вариант {i}: свой solution без своего solution_script, "
                                 "а у задачи solution_script есть — задай скрипт варианта")
        # у PyEditTask эталон и третью подсказку строит движок из правок: пары нет и не надо
        if (v.solution is None) != (v.hints is None) and not py_built(task, i):
            add("H002", "warn", f"вариант {i}: solution и hints заданы не парой")


def _check_neutral(task, add) -> None:
    for text in neutral_texts(task):
        low = text.lower()
        for bad in FORBIDDEN:
            if bad in low:
                add("N001", "error", f"слово сеттинга «{bad}» в тексте: {text[:60]!r}")


def translit_ok() -> Set[str]:
    """TRANSLIT_OK и имена собственные из генераторов данных (люди, города, улицы)."""
    global _TRANSLIT_OK_CACHE
    if _TRANSLIT_OK_CACHE is None:
        from termit_app.tasks import datakit, dbkit, pdkit, sheets
        names = [*datakit.CITIES, *dbkit.FIRST, *dbkit.LAST, *dbkit.CITIES, *dbkit.STREETS,
                 *sheets.CITY_STREET, *sheets.CITY_STREET.values(), *sheets.STREETS,
                 *sheets.EXTRA["manager"], *pdkit.CITIES]
        _TRANSLIT_OK_CACHE = TRANSLIT_OK | {n.lower() for n in names}
    return _TRANSLIT_OK_CACHE


def translit_words(text: str) -> List[str]:
    """Слова-транслит в тексте: латинские куски имён (snake_case, CamelCase и пути делятся
    на слова), которые начинаются с корня TRANSLIT_ROOTS или несут TRANSLIT_MARKS."""
    ok = translit_ok()
    out = []
    for word in _LATIN_WORD.findall(text):
        low = word.lower()
        if len(low) < 4 or low in ok or low in out:
            continue
        if low.startswith(TRANSLIT_ROOTS) or TRANSLIT_MARKS.search(low):
            out.append(low)
    return out


def _translit_texts(task) -> List[str]:
    texts = neutral_texts(task) + [task.solution_script or "", task.implant_script or "",
                                   *task.wrong, *task.man_flags]
    for v in _variants(task):
        texts += [v.solution_script or "", v.implant_script or "", *v.wrong]
    return texts


def _check_translit(task, add) -> None:
    if task.track in TRANSLIT_SKIP_TRACKS:
        return
    for text in _translit_texts(task):
        for word in translit_words(text):
            add("L001", "error", f"транслит «{word}» — нужно английское слово: {text[:60]!r}")


def _tree_translit(task, box: Path) -> List[str]:
    """Имена, которые setup создал в песочнице (и в её доме), с транслитом."""
    if task.track in TRANSLIT_SKIP_TRACKS:
        return []
    found = []
    termit = box / ".termit"
    for root, dirs, files in os.walk(box):
        here = Path(root)
        if here == termit:
            dirs[:] = [d for d in dirs if d == "home"]      # служебное игры — не имена задачи
            continue
        dirs[:] = [d for d in dirs if d not in ("site-packages", "node_modules", ".git")]
        for name in dirs + files:
            for word in translit_words(name):
                if word not in found:
                    found.append(word)
    return found


_SINGLE_FIELD = re.compile(r"(?<![{$])\{[A-Za-z_]\w*\}(?!\})")


def _check_plain_braces(task, add) -> None:
    for name, text in (("scroll", task.scroll or ""), ("explain", task.explain),
                       ("spell", task.spell), ("title", task.title),
                       *(("steps", s) for s in task.steps),
                       # FB6: «Почему» варианта тоже идёт на экран как есть
                       *((f"explain варианта {i}", v.explain)
                         for i, v in enumerate(task.variants)
                         if isinstance(v, base.Variant) and v.explain)):
        found = _SINGLE_FIELD.findall(text)
        if found:
            add("B002", "error", f"{name} не форматируется, а в нём поле {found[0]}")


def _format_checks(task, state: dict, add) -> None:
    where = f"seed {state.get('_seed')}, вариант {state.get('_variant')}"
    fields: List[Tuple[str, Callable[[], object]]] = [
        ("text", lambda: task.text(state)),
        ("hints", lambda: task.hints_for(state)),
        ("solution", lambda: task.shown_solution(state)),
        ("solution_script", lambda: task.reference(state)),
        ("wrong", lambda: task.wrong_scripts(state)),
        ("alternatives", lambda: task.alternatives_for(state)),
        ("implant_script", lambda: task.implant_reference(state)),
        ("start_dir", lambda: task.start_dir.format(**state)),
        ("autorun", lambda: (task.autorun or "").format(**state)),
    ]
    for name, get in fields:
        try:
            get()
        except (KeyError, IndexError, ValueError, AttributeError) as e:
            add("B001", "error", f"{where}: {name} не форматируется ({type(e).__name__}: {e})")
    for line in _intro_lines(task):
        try:
            line.format(**state)
        except (KeyError, IndexError, ValueError, AttributeError) as e:
            add("B003", "error", f"{where}: intro темы не форматируется ({type(e).__name__}: {e})")
    try:
        hints = task.hints_for(state)
    except (KeyError, IndexError, ValueError, AttributeError):
        return
    for i, h in enumerate(hints, 1):
        if "\n" in h:
            add("H001", "error", f"{where}: подсказка {i} — не одна строка")
        elif len(h) > HINT_MAX:     # FB17 (п. 50): длина — мягко, не толкать к телеграфу
            add("H003", "warn", f"{where}: подсказка {i} длиннее {HINT_MAX} симв. — "
                                "проверь, всё ли нужно")
    _taught_checks(task, state, hints, add)


def _taught_checks(task, state: dict, hints: List[str], add) -> None:
    try:
        sol = task.shown_solution(state)
        ref = task.reference(state)
    except (KeyError, IndexError, ValueError, AttributeError):
        return
    third = hints[2] if len(hints) > 2 else ""
    if py_built(task, state.get("_variant", 0)):
        # «nano report.py: `# TODO 1` → `total = …`»: в обратных кавычках — строки Python,
        # а не команды оболочки (их «сначала учим» проверяет P002)
        sol, third = _BACKTICKS.sub("''", sol), _BACKTICKS.sub("''", third)
    taught = taught_for(task)
    prog = _implant_program(task)
    used = command_words(sol) | command_words(third)
    for cmd in sorted(used - taught - ({prog} if prog else set())):
        add("S002", "error", f"команда {cmd!r} из эталона/3-й подсказки ещё не преподана")
    if prog:
        if prog in _first_words(ref):
            add("R002", "error", f"эталон зовёт программу импланта {prog!r}: "
                                 "задача обязана решаться встроенными командами")
        words = set(re.findall(r"[a-z][a-z0-9_-]*", third))
        if prog not in words or not (command_words(third) - {prog}):
            add("R002", "error", "3-я подсказка должна назвать и встроенный путь, и "
                                 f"утилиту {prog!r}")


_BACKTICKS = re.compile(r"`[^`\n]*`")


def _scroll_pairs(task, lesson: str) -> List[Tuple[str, str, str]]:
    """(где, карточка, урок): общая пара и пары движков БД (финал M3: карточка стража
    Хранилища и урок к ней — по движку, Task.scroll_for и lessons темы)."""
    out, seen = [("", task.scroll, lesson)], {(task.scroll, lesson)}
    by_engine = _theme_entry(task).get("lessons") or {}
    for engine in ("sqlite", "pg"):
        scroll_for = getattr(task, "scroll_for", None)
        pair = ((scroll_for({"_engine": engine}) if scroll_for else None) or task.scroll,
                by_engine.get(engine) or lesson)
        if pair not in seen:
            seen.add(pair)
            out.append((f" ({engine})",) + pair)
    return out


def _check_scroll(task, add) -> None:
    if not task.scroll:
        return
    lesson = _lesson(task)
    if not lesson:
        add("S001", "error", "у задачи со scroll нет урока в теме по умолчанию")
        return
    extra = "\n".join(_variant_lessons(task).values())    # FB12: уроки вариантов — тоже урок
    for where, scroll, text in _scroll_pairs(task, lesson):
        text = text + "\n" + extra
        for tok in sorted(scroll_tokens(scroll)):
            if not re.search(r"(?<![\w-])" + re.escape(tok) + r"(?!\w)", text):
                add("S001", "error", f"команда {tok!r} из scroll не прозвучала в уроке темы"
                                     + where)


def _check_sql_texts(task, add) -> None:
    """S005: «!» внутри "…" — в интерактивном zsh это подстановка из истории («event not
    found»; zsh -f -c тестов её не видит): вместо != — <>. S006: в SQL-строке ключевые
    слова — ЗАГЛАВНЫМИ (литералы '…' не в счёт)."""
    for text in neutral_texts(task):
        for m in _DOUBLE_QUOTED.finditer(text):
            if "!" in m.group(1):
                add("S005", "error", f"«!» внутри двойных кавычек (в zsh — подстановка из "
                                     f"истории; вместо != пишем <>): {m.group(0)[:60]!r}")
        for body in sql_strings(text):
            if body.lstrip()[:1] in (".", "\\"):
                continue        # точечные и мета-команды — не SQL: «.schema {table}»
            low = lower_sql_keywords(re.sub(r"\{\w+\}", "", body))     # {поле} — подстановка
            if low:
                add("S006", "error", f"строчные ключевые слова в SQL ({', '.join(low)}): "
                                     f"{body[:60]!r}")


def _check_scroll_sql(task, add) -> None:
    """S007: SQL-токены карточки (ключевые слова, функции, точечные и мета-команды) звучат
    в уроке темы — как S001 для команд."""
    if not task.scroll:
        return
    lesson = _lesson(task)
    if not lesson:
        return          # S001 уже сказал, что урока нет
    for where, scroll, text in _scroll_pairs(task, lesson):
        for tok in sorted(sql_tokens(scroll) - sql_tokens(text)):
            add("S007", "error", f"SQL {tok!r} из scroll не прозвучал в уроке темы" + where)


PY_EDIT_RULE = ("skip", None, "правка в редакторе: строки из # TODO вписывают руками в nano, "
                              "описано словами (скрипт с готовым текстом — в reference)")


def shown_rule(task, variant: int) -> Tuple[str, Optional[str], str]:
    """Как D005 проверяет показанный эталон этого варианта: (режим, часть, причина).
    PyEditTask («поправь скрипт», часть 10) — skip сам: правка в редакторе (взамен — P001)."""
    return (SHOWN_RULES.get(f"{task.id}:{variant}") or SHOWN_RULES.get(task.id) or
            (PY_EDIT_RULE if py_built(task, variant) else ("solve", None, "")))


def py_built(task, variant: int) -> bool:
    """Показанный эталон PyEditTask строит движок из правок («nano report.py: `# TODO 1` →
    `…`»): только тогда D005 — skip и код в обратных кавычках не команды (M1 ревью Q1).
    Свой solution варианта или задачи — обычная команда оболочки, правила общие."""
    if not getattr(task, "py_edit", False):
        return False
    v = task.variant({"_variant": variant})
    return v.solution is None and not task.solution


def shown_part(text: str, part: Optional[str]) -> str:
    """Первый или последний шаг показанного эталона. Шаги — через «→» или (FB6/FB7: стрелка
    путалась с клавишей →) через «, » вне кавычек; запятая разделителя (cut -d, и awk -F,) шагов не делит."""
    if part is None:
        return text
    if "→" in text:
        steps = [x.strip() for x in text.split("→")]
    else:
        steps, quote, start = [], "", 0
        for i, ch in enumerate(text):
            if quote:
                quote = "" if ch == quote else quote
            elif ch in "'\"`":
                quote = ch
            elif text.startswith(", ", i) and not text[:i].endswith(("-d", "-F")):
                steps.append(text[start:i].strip())
                start = i + 2
        steps.append(text[start:].strip())
    return steps[0] if part == "first" else steps[-1]


def _check_shown_rules(task, add) -> None:
    """S004: исключение D005 описано правильно — известный режим и причина."""
    for key, (mode, part, why) in SHOWN_RULES.items():
        if key.split(":")[0] != task.id:
            continue
        if mode not in SHOWN_MODES or part not in (None, "first", "last") or not why.strip():
            add("S004", "error", f"исключение D005 {key!r}: режим {mode!r}, часть {part!r}, "
                                 "причина обязательна")


def _implant_program(task) -> Optional[str]:
    """Что набирает игрок с утилитой задачи (zoxide → z); id не из каталога — как есть."""
    from termit_app import implants
    imp_id = getattr(task, "implant", None)
    if not imp_id:
        return None
    try:
        return implants.get(imp_id).cmd
    except KeyError:
        return imp_id


STANDS = ("pg",)


def _check_stand(task, add) -> None:
    """R004 (часть 9б): стенд (stand = "pg") — только у обычных задач трека sql. Страж трека
    и всё остальное идут без стенда: у стража есть запасной SQLite, звание достижимо без brew.
    Задача стенда сообщает о недоступности через missing(), а не через needs (R001)."""
    stand = getattr(task, "stand", None)
    if stand is None:
        return
    if stand not in STANDS:
        add("R004", "error", f"stand {stand!r}: известен только {', '.join(STANDS)}")
    if task.track != "sql":
        add("R004", "error", f"stand {stand!r} у задачи трека {task.track!r}: стенд — только "
                             "у задач трека sql")
    if task.boss:
        add("R004", "error", "у стража не бывает стенда: он идёт и без PostgreSQL (на SQLite)")
    if type(task).missing is base.Task.missing:
        add("R004", "error", "у задачи стенда нет missing(): без PostgreSQL она должна "
                             "сказать, чего не хватает")


def _check_rules(task, add) -> None:
    """R001: needs пуст у всех — любая задача решается встроенными. R002: у задачи с утилитой
    есть after с близнецом (сам близнец — исключение: его и делают руками). R003: у пары
    у каждого варианта есть implant_script, и он зовёт утилиту."""
    from termit_app import implants
    if task.needs:
        add("R001", "error", f"needs {sorted(task.needs)}: задача должна решаться встроенными")
    _check_stand(task, add)
    imp_id = getattr(task, "implant", None)
    if not imp_id:
        return
    try:
        twin = implants.get(imp_id).twin
    except KeyError:
        add("R002", "error", f"утилиты {imp_id!r} нет в каталоге termit_app/implants.py")
        return
    if task.id == twin:
        return
    if not getattr(task, "after", ()):
        add("R002", "error", f"у задачи с утилитой {imp_id!r} нет after с близнецом")
    prog = _implant_program(task)
    for i, v in enumerate(_variants(task) or [base.Variant("")]):
        script = v.implant_script if v.implant_script is not None else task.implant_script
        if not script:
            add("R003", "error", f"вариант {i}: нет implant_script — решения утилитой "
                                 f"{prog!r} (его гоняет тест при найденной программе)")
        elif prog not in _first_words(script):
            add("R003", "error", f"вариант {i}: implant_script не зовёт утилиту {prog!r}")


# --- Python (часть 10): P001 скелет и правки, P002 «сначала учим», P003 чтение .py ---------

PY_TRACKS = ("py", "pydata")
# трек → треки Python, чьи карточки и уроки тоже считаются преподанными (A10)
PY_PREREQ = {"py": (), "pydata": ("py",)}
# что из кода эталона не преподаётся карточкой и уроком — явно, с причиной: {id: {токен: why}}
PY_EXTRA_OK: Dict[str, Dict[str, str]] = {
    # вызов своей функции задачи (fee из mylib.py: её и пишут в варианте A), а не понятие Python
    "py_func": {"fee": "своя функция задачи из mylib.py, а не понятие Python"},
    # имя функции учебного пакета в help(модуль.функция): предмет вопроса, а не понятие
    "py_repl": {".table": "функция tabprint — о ней и спрашивают help()",
                ".from_csv": "функция tabprint — о ней и спрашивают help()",
                ".get": "функция sockhttp — о ней и спрашивают help()",
                ".post": "функция sockhttp — о ней и спрашивают help()",
                ".install": "функция sockhttp — о ней и спрашивают help()"},
    # подсказка 2 стража — нить JSON (план, «Нить JSON»): python3 -c в конвейере, приём
    # py_repl C; подсказка даёт команду целиком, sys.stdin в ней — только ради конвейера
    "boss_py": {".stdin": "python3 -c в конвейере (нить JSON): подсказка даёт команду целиком"},
}
PY_SKELETON_LINES = (6, 15)
PY_MARKS = (1, 3)

PY_KEYWORDS = frozenset(("for", "while", "if", "elif", "def", "return", "import", "with",
                         "try", "except", "lambda", "class", "yield"))
# понятие Python, которое учит текст варианта (виден игроку в любой теме), а не карточка: явно,
# с причиной; токен обязан стоять в py_tokens текста этого варианта (fix1 Q2, I3). Учит только
# свой вариант: следующим задачам не засчитывается (вариант мог и не выпасть)
PY_VARIANT_TEACHES: Dict[Tuple[str, int], Set[str]] = {
    # py_repl C: JSON из конвейера — json.load(sys.stdin) и len — только этому варианту
    ("py_repl", 2): {".load", ".stdin", "len"},
    # py_files B: re.search против re.match — понятие этого варианта (в тексте — обе формы)
    ("py_files", 1): {".search"},
    # py_stats C: дата из строки и разница дат — понятия этого варианта
    ("py_stats", 2): {".fromisoformat", ".days"},
    # py_csv_json B: все строки разом — w.writerows(rows); в карточке — только шапка (I2 ревью
    # Q4: с именованными аргументами newline= и fieldnames= карточка вышла за пять понятий)
    ("py_csv_json", 1): {".writerows"},
    # pd_read C: свой разделитель — именованный аргумент sep= (I2 ревью Q4)
    ("pd_read", 2): {"sep="},
    # pd_groupby B: среднее по группе — .mean() вместо .sum() и .round(2), понятия этого
    # варианта (I2 ревью Q4: ascending= в карточке — шестое понятие)
    ("pd_groupby", 1): {".mean", ".round"},
    # pd_missing B: среднее до двух знаков — .round(2) (в pd_groupby его учил только вариант B)
    ("pd_missing", 1): {".round"},
    # FB15: приёмы вариантов — в тексте варианта (карточка учит вариант 0, правило 4)
    ("pd_dates", 1): {".resample", "on=", ".max"},
    ("pd_dates", 2): {"format="},
    ("pd_pivot", 2): {"fill_value=", ".loc"},
    ("rq_get", 1): {"params="},
    ("rq_get", 2): {"headers=", ".environ"},
}
# python3 -c '…' / "…" в строке оболочки
_PY_DASH_C = re.compile(r"(?<![\w/.-])(?:\S*/)?python3?(?:\.\d+)?\s+(?:-\w+\s+)*-c\s+"
                        r"(?:'([^'\n]*)'|\"([^\"\n]*)\")")
# тело heredoc с кодом Python: cat > a.py <<'PYEOF' … PYEOF (эталоны и не-PyEditTask, M12)
_PY_HEREDOC = re.compile(r"<<-?\s*'?PYEOF'?[^\n]*\n(.*?)\n[ \t]*PYEOF\b", re.S)
_STR_PREFIX = re.compile(r"^([rRbBuUfF]*)(['\"]{1,3})")


def _fstring_exprs(token: str) -> List[str]:
    """Выражения в {…} f-строки (без {{ }}; формат после : и ! — отрезается)."""
    m = _STR_PREFIX.match(token)
    if not m or "f" not in m.group(1).lower():
        return []
    q = m.group(2)
    body = token[len(m.group(0)):len(token) - len(q)]
    out, depth, cur, i = [], 0, [], 0
    while i < len(body):
        ch = body[i]
        if depth == 0:
            if body.startswith("{{", i):
                i += 2
                continue
            if ch == "{":
                depth, cur = 1, []
        else:
            if ch in "{[(":
                depth += 1
            elif ch in "}])":
                depth -= 1
                if depth == 0:
                    expr = "".join(cur)
                    out.append(re.split(r"(?<![=!<>])[!:](?!=)", expr, 1)[0])
                    i += 1
                    continue
            cur.append(ch)
        i += 1
    return out


def py_tokens(code: str) -> Set[str]:
    """Понятия Python в коде (A10), разбор tokenize (код не исполняется): атрибуты и методы —
    «.имя» (json.dump → .dump, ",".join → .join), вызовы — «имя» (print, round), ключевые
    слова из PY_KEYWORDS; выражения внутри f-строк — тоже. Не вызов: ключевое слово перед
    скобкой (in (…), not (…), return (…)) и имя после def/class. Именованный аргумент вызова —
    «имя=» (sep=";", ascending=False: I2 ревью Q4). Имена не латиницей — не понятия (в тексте
    карточки «.venv. Поставь» — это точка в конце фразы). Строки, комментарии и переменные без
    вызова — не понятия. Ломаный или неполный код — что успели разобрать."""
    import io
    import keyword
    import textwrap
    import tokenize
    out: Set[str] = set()
    toks = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(textwrap.dedent(code)).readline):
            if tok.type in (tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT,
                            tokenize.ENDMARKER):
                continue
            toks.append(tok)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    in_import = False           # import os.path / from os.path import x: точка — не атрибут
    depth = 0                   # глубина круглых скобок: «имя=» внутри вызова
    for i, tok in enumerate(toks):
        prev = toks[i - 1] if i else None
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if tok.type == tokenize.OP and tok.string in "()":
            depth = depth + 1 if tok.string == "(" else max(depth - 1, 0)
        if tok.type == tokenize.NEWLINE or (tok.type == tokenize.OP and tok.string == ";"):
            in_import = False
            continue
        if tok.type == tokenize.NAME and tok.string in ("import", "from") and (
                prev is None or prev.type == tokenize.NEWLINE or prev.string in (";", ":")):
            in_import = True
        if in_import and tok.string == ".":
            continue
        if tok.type == tokenize.STRING:
            for expr in _fstring_exprs(tok.string):
                out |= py_tokens(expr)
        elif tok.type == tokenize.OP and tok.string == "." and nxt is not None \
                and nxt.type == tokenize.NAME and prev is not None:
            if nxt.string.isascii():
                out.add("." + nxt.string)
        elif tok.type == tokenize.NAME:
            if not tok.string.isascii():
                continue
            if tok.string in PY_KEYWORDS:
                out.add(tok.string)
            elif keyword.iskeyword(tok.string):
                continue
            elif (depth and nxt is not None and nxt.string == "=" and prev is not None
                  and prev.string in ("(", ",")):
                out.add(tok.string + "=")
            elif (nxt is not None and nxt.string == "("
                  and not (prev is not None and prev.string in (".", "def", "class"))):
                out.add(tok.string)
    return out


def py_snippets(task, state: dict) -> List[str]:
    """Код Python задачи: правки PyEditTask и тексты python3 -c из эталона и подсказок."""
    out: List[str] = []
    if getattr(task, "py_edit", False):
        try:
            out += [new for _, new in task.edits(state)]
        except Exception:       # noqa: BLE001 — сломанные правки покажет P001
            pass
    texts: List[str] = []
    for get in (lambda: task.shown_solution(state), lambda: task.reference(state),
                lambda: task.hints_for(state)):
        try:
            got = get()
        except Exception:       # noqa: BLE001 — форматирование проверяет B001
            continue
        texts += got if isinstance(got, list) else [got]
    for text in texts:
        out += [a or b for a, b in _PY_DASH_C.findall(text)]
        if not getattr(task, "py_edit", False):     # у PyEditTask тело heredoc — скелет
            out += _PY_HEREDOC.findall(text)
    return out


def _shown_lesson(task) -> str:
    """Урок, который увидит игрок в ЛЮБОЙ теме (fix1 Q2, I3): урок темы по умолчанию — только
    если он есть во всех темах; где урока нет, тема показывает карточку (scroll) — её P002
    и так считает. Урок одной темы (Соня) фэнтезийному игроку ничего не учит."""
    from termit_app import theme
    lesson = _lesson(task)
    if not lesson:
        return ""
    for name in theme.available():
        if not (theme.load(name).get("tasks", {}).get(task.id) or {}).get("lesson"):
            return ""
    return lesson


def py_taught_for(task) -> Set[str]:
    """Понятия Python из карточек и уроков задач трека (и треков PY_PREREQ) до этой
    включительно — по порядку реестра. Урок — только если он есть во всех темах
    (_shown_lesson). Задача не из реестра считается последней в треке."""
    from termit_app.tasks import registry
    tracks = (task.track,) + PY_PREREQ.get(task.track, ())
    taught: Set[str] = set()
    for t in registry.all_tasks().values():
        if t.id == task.id:
            break
        if t.track in tracks:
            taught |= py_tokens((t.scroll or "") + "\n" + _shown_lesson(t))
    return taught | py_tokens((task.scroll or "") + "\n" + _shown_lesson(task))


def py_variant_taught(task, variant: int) -> Set[str]:
    """Понятия, которые учит текст этого варианта (PY_VARIANT_TEACHES)."""
    return set(PY_VARIANT_TEACHES.get((task.id, variant), set()))


def _py_checks(task, state: dict, add) -> None:
    """P001 — скелет PyEditTask: каждая метка ровно один раз, их 1–3, скелет 6–15 строк,
    правки убирают все # TODO, а скрипт тестов (reference) — это скелет с правками (его и
    гоняет D001: «скелет с правками решает задачу»). P002 — «сначала учим» для Python: каждое
    понятие кода (py_tokens) было в карточке или уроке этой или более ранней задачи трека.
    P003 — задача, чья проверка читает .py, скрытая: в state есть ключ из secret_keys."""
    from termit_app import sandbox
    where = f"seed {state.get('_seed')}, вариант {state.get('_variant')}"
    if getattr(task, "py_edit", False):
        _p001(task, state, where, add)
    if task.track in PY_TRACKS:
        v = state.get("_variant", 0)
        extra = py_variant_taught(task, v)
        try:
            in_text = py_tokens(_variants(task)[v].text)
        except IndexError:
            in_text = set()
        for tok in sorted(extra - in_text):
            add("P002", "error", f"{where}: PY_VARIANT_TEACHES {tok!r} — нет в тексте варианта")
        ok = py_taught_for(task) | set(PY_EXTRA_OK.get(task.id, {})) | (extra & in_text)
        for code in py_snippets(task, state):
            for tok in sorted(py_tokens(code) - ok):
                add("P002", "error", f"понятие Python {tok!r} из эталона ещё не преподано "
                                     "(карточка или урок этой или более ранней задачи трека)")
    reads = getattr(task, "reads_script", None)
    if callable(reads) and reads() and sandbox.public_state(task, state) == state:
        add("P003", "error", f"{where}: проверка читает .py, а задача открытая — в state нет "
                             "ни одного ключа из secret_keys (recheck не прочтёт .py)")


def _p001(task, state: dict, where: str, add) -> None:
    try:
        skel = task.skeleton(state)
        edits = list(task.edits(state))
    except Exception as e:      # noqa: BLE001 — сломанный генератор — тоже находка
        add("P001", "error", f"{where}: скелет или правки не строятся ({type(e).__name__}: {e})")
        return
    lo, hi = PY_MARKS
    if not lo <= len(edits) <= hi:
        add("P001", "error", f"{where}: правок {len(edits)}, нужно {lo}–{hi}")
    lo, hi = PY_SKELETON_LINES
    n = len(skel.rstrip("\n").split("\n"))
    if not lo <= n <= hi:
        add("P001", "error", f"{where}: в скелете {n} строк, нужно {lo}–{hi}")
    for mark, _ in edits:
        from termit_app.tasks import pykit
        hits = sum(pykit.has_mark(line, mark) for line in skel.split("\n"))
        if hits != 1:
            add("P001", "error", f"{where}: метка {mark!r} в скелете {hits} раз, нужна одна")
    try:
        solved = task.solved_text(state)
    except ValueError as e:
        add("P001", "error", f"{where}: правки не ложатся на скелет ({e})")
        return
    if "# TODO" in solved:
        add("P001", "error", f"{where}: после правок в скрипте осталось # TODO")
    try:
        ref = task.reference(state)
    except Exception:           # noqa: BLE001 — форматирование проверяет B001
        return
    if solved.rstrip("\n") not in ref:
        add("P001", "error", f"{where}: скрипт тестов (reference) — не скелет с правками: "
                             "D001 не докажет, что правки решают задачу")


def static_issues(task, seeds=(1, 2, 3), min_variants: int = 3,
                  variants_level: str = "error", engine: Optional[str] = None) -> List[Issue]:
    """Все статические находки по задаче (без zsh). Повторы одной находки — один раз.
    V001 (вариантов меньше min_variants) — ошибка: после P5 у всех задач волны 1 их по 3."""
    found: List[Issue] = []
    seen = set()

    def add(code: str, level: str, message: str) -> None:
        key = (code, message)
        if key not in seen:
            seen.add(key)
            found.append(Issue(task.id, code, level, message))

    _check_variants(task, min_variants, variants_level, add)
    _check_hint_count(task, add)
    _check_variant_pairs(task, add)
    _check_neutral(task, add)
    _check_translit(task, add)
    _check_plain_braces(task, add)
    _check_rules(task, add)
    _check_shown_rules(task, add)
    _check_scroll(task, add)
    _check_sql_texts(task, add)
    _check_scroll_sql(task, add)
    from termit_app.tasks import lint_lessons     # FB12: E1, N10, N11, N21, N25
    lint_lessons.static_issues(task, _lesson(task), add)
    for state in _states(task, seeds, add, engine):
        _format_checks(task, state, add)
        _py_checks(task, state, add)
    return found


def lint_all(tasks=None, **kw) -> List[Issue]:
    if tasks is None:
        from termit_app.tasks import registry
        tasks = list(registry.all_tasks().values())
    out: List[Issue] = []
    for t in tasks:
        out.extend(static_issues(t, **kw))
    return out


# --- Динамика: настоящий zsh ---------------------------------------------------------------

def _tail(run) -> str:
    out = run.last_output
    if out is None:
        return ""
    return f"\nstdout: {out.stdout[-500:]}\nstderr: {out.stderr[-500:]}"


# zsh сам ругается на скрипт: опечатка или синтаксис — такое «неверное решение» не решит
# задачу ни при каких данных и ловушку не проверяет. «Нет такого файла» — честная ошибка.
_SHELL_BROKE = re.compile(r"command not found|parse error|bad substitution|bad pattern|"
                          r"unmatched|no such option|bad option")
# показанный эталон, набранный как есть: ещё и маска мимо всех файлов — тоже поломка
_SHOWN_BROKE = re.compile(_SHELL_BROKE.pattern + r"|no matches found|No such file")
# ans — функция игры (shell/.zshrc); в прогоне D005 она печатает ответ, его и сдаёт refrun
_ANS_FN = 'ans() { print -r -- "$*"; }\n'


def _shown_issue(task, run, v: int) -> Optional[str]:
    """D005 для одного прогона: None — показанный эталон в порядке (или не проверяется)."""
    mode, part, _ = shown_rule(task, v)
    shown, ref = task.shown_solution(run.state), task.reference(run.state)
    if mode == "skip" or shown == ref:
        return None
    script = shown_part(shown, part)
    verdict = run.solve(_ANS_FN + script)
    out = run.last_output
    broke = _SHOWN_BROKE.search(out.stderr or "")
    if mode == "solve":
        return None if verdict.solved else f"не решает: {verdict.message}{_tail(run)}"
    if broke or out.returncode != 0:
        return f"падает: {script!r}{_tail(run)}"
    if mode == "read" and str(task.expected(run.state)) not in out.stdout:
        return f"в выводе нет ответа: {script!r}{_tail(run)}"
    return None


def dynamic_issues(task, seeds: Sequence[int] = (1, 2, 3), sandboxed: bool = False,
                   wrong_seeds: Optional[Sequence[int]] = None,
                   timeout: float = 120, engine: Optional[str] = None) -> List[Issue]:
    """Каждый вариант × seed в настоящем zsh: D002 — решено без действий, D001 — эталон не
    решает, D003 — неверное решение (wrong_scripts) засчитано, D004 (warn) — неверное решение
    сломано само (zsh ругнулся на команду или синтаксис), D005 — показанный эталон, набранный
    как есть, не работает (на wrong_seeds; исключения — SHOWN_RULES). D000 — прогон упал: setup бросил
    исключение или скрипт завис дольше timeout; проверка остальных идёт дальше.
    wrong_seeds — на каких seed гонять неверные решения (None — на всех seeds). Нужен тестовый
    прогонщик tests/refrun (берётся из корня проекта); временные папки убираются всегда."""
    import subprocess
    from tests.refrun import Run
    found: List[Issue] = []
    wrong_seeds = tuple(seeds) if wrong_seeds is None else tuple(wrong_seeds)

    def add(code: str, message: str, level: str = "error") -> None:
        found.append(Issue(task.id, code, level, message))

    def crashed(where: str, what: str, e: BaseException) -> None:
        if isinstance(e, subprocess.TimeoutExpired):
            add("D000", f"{where}: {what} завис дольше {timeout:g} с")
        else:
            add("D000", f"{where}: {what} упал: {type(e).__name__}: {e}")

    for v in range(max(1, len(task.variants))):
        # число неверных решений от state не зависит: общие + свои у варианта
        n_wrong = len(task.wrong) + len(task.variant({"_variant": v}).wrong)
        for seed in sorted(set(seeds) | set(wrong_seeds)):
            where = f"seed {seed}, вариант {v}"
            if seed in seeds:
                run = None
                try:
                    run = Run(task, seed, sandboxed=sandboxed, variant=v, timeout=timeout,
                              engine=db_engine(task, engine))
                    if run.untouched().solved:
                        add("D002", f"{where}: решено без всяких действий")
                    verdict = run.solve()
                    if not verdict.solved:
                        add("D001", f"{where}: эталон не решает: {verdict.message}{_tail(run)}")
                except Exception as e:      # noqa: BLE001 — любая поломка прогона — находка
                    crashed(where, "прогон эталона" if run else "setup", e)
                    if run is None:
                        continue            # setup упал — неверные решения тут не прогнать
                finally:
                    if run is not None:
                        run.close()
            for i in range(n_wrong if seed in wrong_seeds else 0):
                run = None
                script = None
                try:
                    run = Run(task, seed, sandboxed=sandboxed, variant=v, timeout=timeout,
                              engine=db_engine(task, engine))
                    script = task.wrong_scripts(run.state)[i]
                    if run.solve(script).solved:
                        add("D003", f"{where}: неверное решение засчитано: {script!r}")
                    elif _SHELL_BROKE.search(run.last_output.stderr or ""):
                        add("D004", f"{where}: неверное решение сломано само и ловушку не "
                                    f"проверяет: {script!r}{_tail(run)}", level="warn")
                except Exception as e:      # noqa: BLE001
                    what = f"неверное решение {script!r}" if script is not None else "setup"
                    crashed(where, what, e)
                    if script is None:
                        break
                finally:
                    if run is not None:
                        run.close()
            if seed in wrong_seeds:
                run = None
                try:
                    run = Run(task, seed, sandboxed=sandboxed, variant=v, timeout=timeout,
                              engine=db_engine(task, engine))
                    problem = _shown_issue(task, run, v)
                    if problem:
                        add("D005", f"{where}: показанный эталон {problem}")
                except Exception as e:      # noqa: BLE001
                    crashed(where, "показанный эталон", e)
                finally:
                    if run is not None:
                        run.close()
    return found


SEED_CODES = ("T001", "T002", "B001", "B003")


def seed_issues(task, seeds: Iterable[int]) -> List[Issue]:
    """Находки, зависящие от seed (T001 setup, B001 форматирование, B003 intro темы), на
    каждом варианте × seed — без zsh. Это и есть fuzz по seed для tests/test_fuzz.py."""
    found: List[Issue] = []
    seen = set()

    def add(code: str, level: str, message: str) -> None:
        if code in SEED_CODES and (code, message) not in seen:
            seen.add((code, message))
            found.append(Issue(task.id, code, level, message))

    for state in _states(task, seeds, add):
        _format_checks(task, state, add)
    return found
