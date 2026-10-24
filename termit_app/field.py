"""Задания в реале: одно безопасное дело в настоящих папках (смотреть, искать, считать).

Каждое — после урока, который учит его приём (П3.9 приёмки-1): цель и «зачем» без готовой
команды; сама команда — по «?» при вопросе «Сделал?», а приём напомнит ./termit book."""
from datetime import date, timedelta

from termit_app import progress, theme, ui
from termit_app.textnorm import YES

# отказ или молчание на «Сделал?» — то же задание не раньше чем через столько дней, а пока
# приходят следующие (P2 Б2: раньше первое повторялось каждый день и держало остальные)
RETRY_DAYS = 3

# id → цель (без команды), зачем это в настоящем терминале
FIELD = [
    ("f_home_pwd", "Открой обычный терминал — не игру — и узнай, в какой папке он стоит, "
                   "когда только открылся."),
    ("f_hidden_home", "Посмотри, какие скрытые файлы лежат в твоей домашней папке. Только "
                      "смотреть, ничего не трогать."),
    ("f_downloads_size", "Узнай, сколько весит твоя папка Загрузки."),
    ("f_newest_download", "Найди три самых свежих файла в Загрузках."),
    ("f_open_here", "Открой из терминала папку проектов в Finder."),
    ("f_count_desktop", "Посчитай, сколько файлов лежит на Рабочем столе."),
    ("f_top_cpu", "Посмотри, кто у тебя ест процессор. Только смотреть — ничего не "
                  "останавливать."),
    ("f_find_pdf", "Найди PDF в своих Документах."),
    ("f_big_dirs", "Найди пять самых тяжёлых папок у себя дома."),
    ("f_copy_path", "Скопируй путь текущей папки в буфер и вставь его в заметку."),
    ("f_grep_docs", "Найди документы, где встречается слово «отчёт»."),
    ("f_brew_list", "Посмотри, что у тебя стоит из Homebrew. Только смотреть, ничего не "
                    "ставить."),
    ("f_top_commands", "Узнай пять своих самых частых команд."),
    ("f_download_types", "Узнай, каких файлов больше всего в Загрузках."),
    ("f_sqlite_date", "Спроси у sqlite3, какое число будет через 100 дней. Базу заводить не "
                      "нужно."),
    ("f_sqlite_csv", "Возьми любую свою таблицу CSV и сосчитай в ней строки запросом SQL — "
                     "файл при этом не меняется."),
    # часть 7 (E21): окружение своего терминала и проверка скачанного — только смотреть
    ("f_env_path", "Посмотри, в каких папках твой терминал ищет команды: сколько их и какая "
                   "первая."),
    ("f_which_python", "Узнай, сколько у тебя python3 и какой из них запускается первым."),
    ("f_shasum", "Возьми любой скачанный установщик и сверь его отпечаток с тем, что написан "
                 "на сайте автора."),
]
WHY = {
    "f_home_pwd": "это твой настоящий дом, ~ — от него считаются пути на этом Mac.",
    "f_hidden_home": "там живут настройки программ — .zshrc, .ssh, — их стоит знать в лицо.",
    "f_downloads_size": "Загрузки пухнут незаметно — так видно, пора ли чистить.",
    "f_newest_download": "так находят «что я только что скачал» без Finder.",
    "f_open_here": "начал руками в терминале — показал глазами в окне.",
    "f_count_desktop": "цифра честнее взгляда: захламлённый стол видно сразу.",
    "f_top_cpu": "так понимают, почему Mac греется и шумит.",
    "f_find_pdf": "поиск по имени на всю глубину быстрее, чем листать папки.",
    "f_big_dirs": "так ищут, что съело диск; 2>/dev/null прячет ругань на закрытые папки.",
    "f_copy_path": "путь из терминала — в письмо или чат без перепечатывания.",
    "f_grep_docs": "поиск по содержимому выручает, когда имя файла забыто.",
    "f_brew_list": "свой склад программ полезно знать в лицо.",
    "f_top_commands": "твоя история — карта привычек: частое стоит ускорить.",
    "f_download_types": "видно, что ты качаешь чаще всего и что чистить первым.",
    "f_sqlite_date": "sqlite3 — калькулятор дат под рукой: сроки, дедлайны, отпуск.",
    "f_sqlite_csv": "любой CSV — уже таблица: SQL к нему без Excel и без своей базы; шапка "
                    "станет именами граф, в счёт строк она не идёт.",
    "f_env_path": "по этим папкам слева направо ищется каждая команда: кто первый — тот и "
                  "запустится.",
    "f_which_python": "у многих их два-три — от Apple, Homebrew, pyenv; по имени запустится "
                      "первый в списке, и venv встаёт как раз впереди.",
    "f_shasum": "отпечаток совпал — файл тот, что выложил автор; добрый ли он — решаешь сам. "
                "Антивирус ClamAV ставится brew install clamav — по желанию, не через игру.",
}
# команда — только по просьбе («?»), чтобы задание не было строкой для копирования
CMD = {
    "f_home_pwd": "pwd",
    "f_hidden_home": "ls -la ~",
    "f_downloads_size": "du -sh ~/Downloads",
    "f_newest_download": "ls -t ~/Downloads | head -3",
    "f_open_here": "cd ~/projects && open .",
    "f_count_desktop": "ls ~/Desktop | wc -l",
    "f_top_cpu": "top -o cpu",
    "f_find_pdf": "find ~/Documents -name '*.pdf' | head",
    "f_big_dirs": "du -sh ~/* 2>/dev/null | sort -h | tail -5",
    "f_copy_path": "pwd | pbcopy",
    "f_grep_docs": "grep -ril 'отчёт' ~/Documents | head",
    "f_brew_list": "brew list | head -20",
    "f_top_commands": "history 1 | awk '{print $2}' | sort | uniq -c | sort -rn | head -5",
    "f_download_types": "ls ~/Downloads | awk -F. 'NF>1 {print $NF}' | sort | uniq -c | "
                        "sort -rn | head -5",
    "f_sqlite_date": "sqlite3 :memory: \"SELECT date('now', 'localtime', '+100 days')\"",
    # ~ в кавычках не раскрывается, $HOME — да (финальное ревью I1)
    "f_sqlite_csv": "sqlite3 :memory: -cmd \".import --csv $HOME/Downloads/файл.csv t\" "
                    "\"SELECT COUNT(*) FROM t\"",
    "f_env_path": "echo $PATH | tr : '\\n'",
    "f_which_python": "which -a python3",
    "f_shasum": "shasum -a 256 ~/Downloads/файл.dmg",
}
# пояснение к команде — отдельной строкой: «Команда:» копируют целиком, хвост-комментарий
# стал бы лишними словами команды (финальное ревью I1)
NOTE = {
    "f_top_cpu": "q — выход; цифры %CPU уточняются за пару секунд.",
    "f_copy_path": "потом Cmd+V в заметке.",
    "f_brew_list": "про одну формулу — brew info NAME.",
    "f_sqlite_csv": "файл.csv — имя твоего CSV в Загрузках.",
    "f_env_path": "папки — по одной на строке, первая строка — первая папка; сосчитать — "
                  "добавь | wc -l.",
    "f_shasum": "файл.dmg — имя твоего установщика; отпечаток на сайте обычно подписан "
                "SHA-256.",
}
# задание в реале — после урока, где учат его приём
FIELD_AFTER = {
    "f_home_pwd": "where_am_i", "f_hidden_home": "hidden_cache",
    "f_downloads_size": "du_heavy", "f_newest_download": "ls_newest",
    "f_open_here": "open_gui", "f_count_desktop": "grep_r", "f_top_cpu": "top_hog",
    "f_find_pdf": "find_name", "f_big_dirs": "du_heavy", "f_copy_path": "pbcopy_list",
    "f_grep_docs": "grep_r", "f_brew_list": "brew_lesson",
    "f_top_commands": "top_values", "f_download_types": "top_values",
    "f_sqlite_date": "select_where", "f_sqlite_csv": "csv_sql",
    "f_env_path": "path_which", "f_which_python": "path_which", "f_shasum": "script_audit",
}


def _solved(p: dict, task_id: str) -> bool:
    rec = p.get("tasks", {}).get(task_id)
    return isinstance(rec, dict) and (rec.get("solved") or 0) > 0


def _ready(p: dict, fid: str) -> bool:
    """После своего урока; f_brew_list — ещё и если настоящий brew вообще есть."""
    if not _solved(p, FIELD_AFTER[fid]):
        return False
    if fid != "f_brew_list":
        return True
    from termit_app import implants
    return bool(implants.brew_path())


def lesson_title(fid: str) -> str:
    from termit_app.tasks import registry
    return theme.title(registry.get(FIELD_AFTER[fid]))


def _later(p: dict) -> dict:
    later = p["field"].get("later")
    if not isinstance(later, dict):
        later = p["field"]["later"] = {}
    return later




def show_command(fid: str) -> None:
    ui.say(f"   Команда: {progress.clean_text(CMD[fid])}")
    if fid in NOTE:
        ui.say(f"   ({progress.clean_text(NOTE[fid])})")


def answer(p: dict, fid: str, reply: str, today: date = None) -> None:
    """Ответ на «Сделал?»: y — награда (один раз на задание), иначе — отложить без упрёка."""
    today = today or date.today()
    if p["field"].get("pending") == fid:
        p["field"]["pending"] = None
    if fid in p["field"]["done"]:
        return          # уже засчитано (старый дубль вопроса) — второй раз не платим
    if reply.strip().lower() in YES:
        p["xp"] += progress.FIELD_KARMA
        p["money"] += progress.FIELD_MONEY
        p["field"]["done"].append(fid)
        ui.ok("   " + theme.msg("field_bonus", xp=progress.FIELD_KARMA))
        ui.ok(f"   +{progress.FIELD_MONEY} {theme.word('money')}")
        _later(p).pop(fid, None)
    else:           # «нет» или молчание — отложить, без упрёка; придёт следующее
        _later(p)[fid] = (today + timedelta(days=RETRY_DAYS)).isoformat()


def ask_pending(p: dict, ask, today: date = None) -> None:
    today = today or date.today()
    pend = p["field"].get("pending")
    if not pend:
        return
    p["field"]["pending"] = None
    text = dict(FIELD).get(pend)
    if text is None:
        return
    prompt = (ui.story_fill(f"{theme.word('field_icon')} {theme.word('field')} с прошлого "
                            f"раза: {text}", "", "   ") +
              "\n   Сделал? [y/n, ? — показать команду] ")
    for _ in range(2):
        try:
            a = ask(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            a = ""
        if a.strip() != "?":
            break
        show_command(pend)
        prompt = "   Сделал? [y/n] "
    answer(p, pend, a, today)


def give(p: dict, today: date = None) -> None:
    today = (today or date.today()).isoformat()
    later = _later(p)
    for fid, text in FIELD:
        wait = later.get(fid)
        if isinstance(wait, str) and today < wait:
            continue
        if fid not in p["field"]["done"] and _ready(p, fid):
            p["field"]["pending"] = fid
            ui.say()
            ui.say(ui.story_fill(f"{theme.word('field_icon')} {theme.word('field')} на сегодня — "
                                 f"в обычном терминале, с настоящими папками:", "", "   "))
            ui.say(ui.story_fill(text, "   ", "   "))
            ui.say(ui.story_fill(f"Зачем: {WHY[fid]}", "   ", "   "))
            ui.say(ui.story_fill(f"Приём — из урока «{lesson_title(fid)}». Забудешь — "
                                 "./termit book; команду покажу, когда спрошу «Сделал?».",
                                 "   ", "   "))
            return
