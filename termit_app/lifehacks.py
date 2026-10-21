"""FB10 (п. 21 FB5): лайфхаки терминала — единый каталог. Владелец: «передать наработки всего
человеческого опыта использования терминала в виде интересного тренажёра — управление с
кнопок, стирать слова, переходить от блока к блоку».

Запись Hack:
- keys — сочетание или команда, как её набирают;
- what — что делает (коротко: из этой строки собирается совет дня на доске, ≤ ui.BOARD_WIDTH клеток);
- when — когда выручает;
- origin — откуда имя или история, коротко (запоминать проще);
- learn — где в игре учится: id задачи или LEARN_CATALOG (только этот каталог);
- checked — где проверено на этом Mac: zsh, iTerm2, Terminal.app, macOS;
- how — как проверено (см. константы ниже: прогон zsh, меню из бандла, man, документация);
- setup — что нужно настроить, чтобы заработало вне игры ("" — работает сразу);
- level — сложность: 1 — с первого дня, 2 — освоившись, 3 — для любопытных;
- after — после какой задачи игрок уже может это применить (None — сразу): по нему совет
  дня и итог рана берут только то, что по силам.

Факты — только проверенные: zsh 5.9 — pty-прогоном `zsh -f -i` (emacs-раскладка), клавиши
iTerm2 3.7.4 и Terminal.app 2.15 — по меню и DefaultGlobalKeyMap.plist из бандлов (только
чтение, настройки владельца не читались); нажатием в GUI их проверить нельзя — так и
помечено в how. Что работает только с настройкой — сказано в setup."""
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

ZSH = "zsh"
ITERM = "iTerm2"
TERMINAL = "Terminal.app"
MACOS = "macOS"
PLACES = (ZSH, ITERM, TERMINAL, MACOS)

PTY = "pty-прогон zsh 5.9 -f на этом Mac"
BIND = "привязка в zsh 5.9 -f (bindkey), действие — по man zshzle"
OMZ = "прогон zsh 5.9 с настройкой из setup; привязка взята из Oh My Zsh (lib/*.zsh)"
ITERM_MENU = "меню iTerm2 3.7.4 (MainMenu.nib из бандла), нажатием не проверено"
ITERM_KEYMAP = "DefaultGlobalKeyMap.plist iTerm2 3.7.4, нажатием не проверено"
TERM_MENU = "меню Terminal.app 2.15 (MainMenu.nib из бандла), нажатием не проверено"
MAN = "man и запуск на этом Mac"
MAN_ONLY = "man на этом Mac; не запускалось (звук или окно)"
DOCS = "документация; без GUI нажатием не проверить"
# FB15: программы кластера и облака (pyspark, airflow, boto3) на этом Mac не ставились
DOCS_CLI = "документация; на этом Mac не ставилось — нужен кластер или облако"
GUI_HOW = (ITERM_MENU, ITERM_KEYMAP, TERM_MENU, DOCS)

LEARN_CATALOG = "catalog"        # учится только здесь: keys hacks, совет дня, итог рана

INTEGRATION = ("интеграция оболочки iTerm2: меню iTerm2 → Install Shell Integration "
               "(дописывает строку в ~/.zshrc — игра подхватывает её вместе с ним)")
OPTION_ESC = ("Option как Esc+: iTerm2 → Settings → Profiles → Keys → Left Option key: Esc+; "
              "в Terminal.app — Cmd+Option+O. Иначе — Esc, отпустить, потом клавиша")


@dataclass(frozen=True)
class Hack:
    keys: str
    what: str
    when: str
    origin: str
    learn: str
    checked: Tuple[str, ...]
    how: str
    setup: str
    level: int
    after: Optional[str]

    @property
    def gui(self) -> bool:
        """Нажатие проверить без GUI нельзя (клавиши окна, мышь)."""
        return self.how in GUI_HOW


def _h(keys, what, when, origin, learn, checked, how, level, after, setup=""):
    return Hack(keys, what, when, origin, learn, tuple(checked), how, setup, level, after)


SECTIONS: Dict[str, str] = {
    "line": "Строка ввода",
    "history": "История",
    "dirs": "Папки и пути",
    "masks": "Маски и раскрытие",
    "jobs": "Задачи и процессы",
    "output": "Вывод и экран",
    "macos": "macOS из терминала",
    "iterm": "iTerm2: окно, панели, метки",
    "terminal": "Terminal.app",
    "config": "Свой zsh (только объяснение: ~/.zshrc игра не трогает)",
    "cluster": "Данные за пределами Mac (только совет)",
}

Z, I, T, M = (ZSH,), (ITERM,), (TERMINAL,), (MACOS,)
IT = (ITERM, TERMINAL)

CATALOG: Dict[str, List[Hack]] = {
    "line": [
        _h("Ctrl+A, Ctrl+E", "в начало строки и в конец",
           "опечатка в самом начале длинной команды — не жми ← двадцать раз",
           "A — первая буква алфавита, E — End. Раскладка Emacs (1976), её взяли bash и zsh",
           "line_edit", Z, PTY, 1, "climb_down"),
        _h("Option+← →", "прыжок курсора через слово",
           "надо поправить слово в середине строки",
           "в Emacs это Meta+B и Meta+F — Back и Forward по словам; Option на Mac — бывший Meta",
           "line_edit", Z + I, PTY, 1, "mkdir_p",
           setup="в игре работает сразу; вне её — пресет Natural Text Editing в iTerm2 "
                 "(Profiles → Keys) или Option как Esc+"),
        _h("Ctrl+W", "стереть слово слева от курсора",
           "последнее слово набрано не то — сотри его целиком",
           "W — Word, «слово»", "line_edit", Z, PTY, 1, "home_tilde"),
        _h("Ctrl+U", "стереть всю строку (в bash — только до курсора)",
           "набрал не то — начни строку с чистого листа",
           "не Undo: у драйвера терминала Ctrl+U — символ kill (ASCII NAK), «сотри строку»",
           "line_edit", Z, PTY, 1, "home_tilde"),
        _h("Ctrl+K", "стереть от курсора до конца строки",
           "хвост команды лишний, а начало верное",
           "K — Kill: в Emacs «убить» текст — вырезать его, он не пропадает",
           "line_edit", Z, PTY, 1, "line_edit"),
        _h("Ctrl+Y", "вставить последнее стёртое Ctrl+W, Ctrl+U или Ctrl+K",
           "стёр лишнее — или нужно перенести кусок строки в другое место",
           "Y — Yank, «выдернуть» назад: в Emacs стёртое ложится в «кольцо» (kill ring)",
           "cut_paste", Z, PTY, 1, "cut_paste"),
        _h("Ctrl+_", "отменить последнюю правку строки (undo)",
           "стёр не то слово — верни, не набирая заново",
           "отмена из Emacs: там это тоже Ctrl+_ (и Ctrl+X u — работает и в zsh). На Mac — "
           "Ctrl+Shift+минус", LEARN_CATALOG, Z, PTY, 2, "cut_paste"),
        _h("Esc .", "вставить последний аргумент прошлой команды; ещё раз — старше",
           "сделал mkdir длинный/путь — теперь cd туда же: cd и Esc .",
           "insert-last-word. Esc — старая замена клавиши Meta: Esc, потом буква = Meta+буква",
           "quick_fix", Z, PTY, 1, "quick_fix", setup="Option+. — " + OPTION_ESC),
        _h("Esc q", "отложить строку: выполнить другую, отложенная вернётся сама",
           "набрал длинную команду и понял, что сначала нужен cd или ls",
           "push-line — «столкни строку в стопку»: zsh прячет её и возвращает после следующей "
           "команды",
           LEARN_CATALOG, Z, PTY, 2, "line_edit",
           setup="Ctrl+Q делает то же только с setopt no_flow_control: иначе Ctrl+Q ловит "
                 "сам терминал (см. Ctrl+S)"),
        _h("Ctrl+T", "поменять местами две буквы у курсора (ecoh → echo)",
           "пальцы обогнали друг друга — частая опечатка",
           "T — Transpose, «переставить»", LEARN_CATALOG, Z, PTY, 2, "line_edit"),
        _h("Esc d", "стереть слово справа от курсора",
           "встал в начало лишнего слова — убери его, не трогая остальное",
           "D — Delete word, «стереть слово» (Meta+D в Emacs)", LEARN_CATALOG, Z, PTY, 2,
           "line_edit"),
        _h("Ctrl+D", "стереть букву под курсором; на пустой строке — выход",
           "в середине строки — как Delete; в python3 или sqlite3 — «ввод окончен»",
           "D — Done: код EOT, «конец передачи» у телетайпов", LEARN_CATALOG, Z, PTY, 2,
           "line_edit"),
        _h("Ctrl+C", "бросить строку или остановить зависшую команду",
           "команда молчит и не возвращает приглашение",
           "запоминай как Cancel; на деле это сигнал SIGINT — interrupt, «прервись»",
           "climb_down", Z, PTY, 1, None),
        _h("Tab", "дописать имя файла или папки; дважды — показать варианты",
           "длинное имя — набери пару букв, остальное допишет zsh",
           "Tab — клавиша табуляции пишущих машинок; дополнение по ней пришло в оболочки из "
           "tcsh, а её «t» — от системы TENEX, где оно уже было", "climb_down", Z, PTY, 1, "climb_down"),
        _h("Tab после -", "флаги команды с описанием каждого (ls -<Tab>)",
           "забыл флаг — посмотри список, не открывая man",
           "это система дополнения zsh (compsys): у сотен команд есть свои описания флагов",
           LEARN_CATALOG, Z, OMZ, 2, "man_flag",
           setup="нужен compinit: в Oh My Zsh он уже включён; в чистом zsh — строка "
                 "autoload -Uz compinit && compinit в ~/.zshrc"),
        _h("Ctrl+X Ctrl+E", "открыть набранную строку в редакторе ($EDITOR)",
           "команда разрослась на три строки — правь её как текст, сохрани и выйди",
           "edit-command-line; Ctrl+X — префикс Emacs для «второго этажа» команд, E — Editor",
           LEARN_CATALOG, Z, OMZ, 3, "nano_config",
           setup="в Oh My Zsh уже есть; в чистом zsh — три строки в ~/.zshrc: "
                 "autoload -Uz edit-command-line; zle -N edit-command-line; "
                 "bindkey '^X^E' edit-command-line"),
        _h("Esc h", "открыть man по команде из строки, набранное не пропадёт",
           "набираешь команду и засомневался во флаге",
           "run-help, «помощь по команде»; q в man — и строка снова перед тобой",
           LEARN_CATALOG, Z, BIND, 2, "man_flag"),
        _h("Option+клик", "поставить курсор в строке мышью",
           "опечатка далеко — щёлкни по ней с Option, курсор прыгнет туда",
           "терминал сам «нажимает» ← → столько раз, сколько нужно", LEARN_CATALOG, IT, DOCS,
           1, "line_edit"),
        _h("файл из Finder в окно", "перетащи файл мышью — вставится полный путь",
           "путь длинный и с пробелами — не набирай, перетащи",
           "терминал сам ставит \\ перед пробелами, чтобы путь остался одним словом",
           LEARN_CATALOG, IT, DOCS, 1, "climb_down"),
    ],
    "history": [
        _h("↑ ↓", "листать прошлые команды",
           "нужна команда, которую набирал минуту назад", "история — history",
           "line_edit", Z, PTY, 1, None),
        _h("Ctrl+R", "поиск по истории: набери кусок команды",
           "команда была вчера, а ↑ жать сто раз лень",
           "R — Reverse, поиск назад, от свежих к старым", "history_recall", Z, PTY, 1,
           "back_up"),
        _h("Ctrl+G", "выйти из поиска Ctrl+R, ничего не выполняя",
           "нашлось не то — передумал",
           "G в ASCII — BEL, звонок: в старых терминалах это и был сигнал «стоп»",
           "history_recall", Z, PTY, 1, "back_up"),
        _h("!!", "повторить последнюю команду целиком",
           "команда упала без папки: mkdir -p папка && !!",
           "«bang bang»: ! в Unix зовут bang. Подстановки ! придумал Билл Джой в csh, 1978",
           "history_recall", Z, PTY, 1, "history_recall"),
        _h("!$", "последний аргумент прошлой команды",
           "ls длинный/путь, потом cd !$ — тот же путь, не набирая",
           "$ — «конец», как в регулярных выражениях; из той же csh", "quick_fix", Z, PTY,
           1, "quick_fix"),
        _h("!^, !*", "первый аргумент прошлой команды и все её аргументы",
           "touch a b c, потом ls -l !* — те же три файла",
           "^ — «начало», * — «всё», как в масках и регулярках", LEARN_CATALOG, Z, PTY, 2,
           "quick_fix"),
        _h("^старое^новое", "повторить прошлую команду, заменив кусок",
           "cp q1.txt archive/ — теперь то же для q2: ^q1^q2",
           "быстрая замена из csh: ^ — «крышка», знак вставки", "quick_fix", Z, PTY, 1,
           "quick_fix"),
        _h("!-2", "команда, набранная две назад (!-3 — три назад)",
           "нужна позапрошлая, а не последняя",
           "минус — «считай назад от свежей»", LEARN_CATALOG, Z, PTY, 2, "history_recall"),
        _h("!cp", "последняя команда, начинавшаяся с cp (!?кусок? — содержавшая кусок)",
           "помнишь, с чего команда начиналась, а номер — нет",
           "подстановка истории из csh: ! и начало команды", LEARN_CATALOG, Z, PTY, 2,
           "history_recall"),
        _h("!!:p", "показать, что подставит !!, но не выполнять",
           "страшно запускать вслепую — сначала глянь",
           "p — print, «напечатать»; потом ↑ — и строка готова к Enter", LEARN_CATALOG, Z,
           PTY, 2, "history_recall"),
        _h("Esc p, Esc n", "листать историю только по командам с тем же началом",
           "набери git и Esc p — пойдут только команды на git",
           "history-search: P — Previous, N — Next, как Ctrl+P и Ctrl+N", LEARN_CATALOG, Z,
           PTY, 2, "history_recall",
           setup="в Oh My Zsh так ведёт себя и ↑, если что-то уже набрано"),
        _h("Ctrl+O", "выполнить команду из истории и встать на следующую за ней",
           "повторить серию из пяти команд: ↑ до первой, дальше Ctrl+O, Ctrl+O…",
           "в bash это operate-and-get-next, «выполни и дай следующую»", LEARN_CATALOG, Z,
           PTY, 3, "history_recall"),
        _h("history 1 | grep слово", "найти старую команду по слову, с номером",
           "Ctrl+R показывает по одной, а тут — все сразу; потом !номер",
           "history 1 — вся история с первой команды; без 1 zsh покажет только свежие",
           LEARN_CATALOG, Z, PTY, 2, "grep_r"),
        _h("fc", "открыть прошлую команду в редакторе; fc -l — список с номерами",
           "длинную команду проще поправить как текст",
           "fc — fix command, «исправь команду», из ksh", LEARN_CATALOG, Z, PTY, 3,
           "nano_config"),
        _h("пробел перед командой", "команда не попадёт в историю",
           "в строке пароль или ключ — пусть не оседает в истории",
           "настройка zsh hist_ignore_space", LEARN_CATALOG, Z, PTY, 3, "dotenv",
           setup="в Oh My Zsh включено; в чистом zsh — setopt hist_ignore_space"),
        _h("sudo !!", "повторить прошлую команду с правами администратора",
           "система ответила Permission denied — повтори через sudo",
           "sudo — «superuser do», «сделай как суперпользователь»", LEARN_CATALOG, Z, PTY, 3,
           "history_recall"),
    ],
    "dirs": [
        _h("cd -", "вернуться в папку, где был до этого",
           "прыгаешь между двумя папками туда-обратно",
           "минус — «предыдущая»; та же папка лежит в переменной OLDPWD", "back_up", Z, PTY,
           1, "back_up"),
        _h("cd", "без пути — домой (то же, что cd ~)",
           "заблудился — домой одной командой", "~ — дом: на клавиатуре терминала ADM-3A "
           "тильда и Home были на одной клавише", "home_tilde", Z, PTY, 1, "home_tilde"),
        _h("dirs -v, cd ~2", "стопка недавних папок с номерами и прыжок по номеру",
           "прыгнуть на три папки назад, а не на одну", "v — verbose, «подробно»",
           "z_jump", Z, PTY, 2, "z_jump",
           setup="нужна setopt auto_pushd (в игре и в Oh My Zsh включена)"),
        _h("pushd, popd", "положить папку в стопку и вернуться по ней обратно",
           "отошёл в другую папку на минуту — popd вернёт",
           "push и pop — «положить» и «снять» со стопки; пришли из csh", LEARN_CATALOG, Z,
           PTY, 3, "z_jump"),
        _h("cd СТАРОЕ НОВОЕ", "заменить кусок текущего пути: из v1/src в v2/src",
           "две похожие папки в разных версиях проекта",
           "умеет только zsh: cd с двумя словами", LEARN_CATALOG, Z, PTY, 3, "z_jump"),
        _h("$_", "последний аргумент прошлой команды — для скриптов: mkdir -p x && cd $_",
           "создал папку и сразу в неё", "переменная с именем «_», «то, что было последним»",
           LEARN_CATALOG, Z, PTY, 2, "quick_fix"),
        _h("..", "имя папки без cd — и ты в ней; ... — на две вверх",
           "меньше набирать в каждом переходе", "настройка zsh auto_cd",
           LEARN_CATALOG, Z, OMZ, 2, "back_up",
           setup="в Oh My Zsh включено (auto_cd и алиасы ...); в чистом zsh — setopt auto_cd"),
        _h("open .", "открыть текущую папку в Finder",
           "нужно глянуть картинки глазами или перетащить файл в браузер",
           "точка — «здесь», текущая папка", "open_gui", M, MAN, 1, "open_gui"),
        _h("open -R файл", "показать файл в Finder, выделенным",
           "нашёл файл в терминале — покажи его в окне", "R — Reveal, «показать»",
           LEARN_CATALOG, M, MAN, 2, "open_gui"),
        _h("pwd | pbcopy", "путь текущей папки — в буфер обмена",
           "вставить путь в чат, письмо или окно «Открыть»",
           "pb — pasteboard, «доска для вставки»: так буфер звали в NeXTSTEP",
           LEARN_CATALOG, M, MAN_ONLY, 2, "pbcopy_list"),
        _h("Cmd+Shift+. в Finder", "показать и спрятать скрытые файлы в Finder",
           "в терминале видишь .env или .git, а Finder их прячет",
           "точка — потому что скрытые файлы в Unix начинаются с точки", LEARN_CATALOG, M,
           DOCS, 1, "hidden_cache"),
    ],
    "masks": [
        _h("{a,b}", "раскрыть в несколько слов: x/{a,b} — это x/a и x/b",
           "много похожих путей одной строкой", "фигурные скобки придумали в csh",
           "mkdir_p", Z, PTY, 1, "mkdir_p"),
        _h("файл{,.bak}", "копия с хвостом: cp conf{,.bak} — это cp conf conf.bak",
           "бэкап перед правкой — в одну короткую команду",
           "пустое место до запятой — «ничего не добавлять»", LEARN_CATALOG, Z, PTY, 2,
           "copy_move"),
        _h("{1..5}, {01..12}", "ряд чисел или букв: 1 2 3 4 5, с нулями — 01 02 … 12",
           "папки по месяцам: mkdir month_{01..12}",
           "две точки — «от и до», ещё ..2 — шаг: {1..10..3}", LEARN_CATALOG, Z, PTY, 2,
           "mkdir_p"),
        _h("Tab на маске", "развернуть маску в строке: видно, какие файлы попадут",
           "перед rm *.log — глянь, кого заденет, не запуская",
           "то же делает Ctrl+X * (expand-word, «раскрыть слово»)", LEARN_CATALOG, Z, PTY,
           2, "star_mask"),
        _h("**", "любые папки на любой глубине: **/*.log", "искать по всему дереву",
           "умеет zsh; в bash — только с shopt -s globstar", "deep_dig", Z, PTY, 2,
           "deep_dig"),
        _h("*(.) и *(/)", "только файлы или только папки (zsh)",
           "ls *(/) — одни папки, без файлов вперемешку",
           "квалификатор маски zsh: . — обычный файл, / — папка", LEARN_CATALOG, Z, PTY, 3,
           "deep_dig"),
        _h("*(om[1])", "самый свежий файл в папке (zsh)",
           "открыть последнюю скачанную картинку: open ~/Downloads/*(om[1])",
           "o — order, m — modified, по времени правки; [1] — первый", LEARN_CATALOG, Z,
           PTY, 3, "ls_newest"),
    ],
    "jobs": [
        _h("Ctrl+Z", "приостановить команду («замри») и вернуть приглашение",
           "открыл less или vim и понадобилось что-то сделать рядом",
           "Ctrl+Z — символ 26, последняя буква; zsh шлёт сигнал SIGTSTP — terminal stop. "
           "Управление задачами появилось в csh на рубеже 70–80-х", "job_control", Z, PTY, 2,
           "job_control"),
        _h("fg", "вернуть приостановленную задачу на экран",
           "сделал, что хотел, — продолжи vim с того же места",
           "foreground — «передний план»", "job_control", Z, PTY, 2, "job_control"),
        _h("bg", "пусть приостановленная задача работает дальше в фоне",
           "запустил долгую команду и понял, что ждать не хочешь",
           "background — «задний план, фон»", "job_control", Z, PTY, 2, "job_control"),
        _h("jobs", "список задач этой оболочки с номерами",
           "что у меня там висит в фоне?", "jobs — «задачи, работы»", "job_control", Z, PTY,
           2, "job_control"),
        _h("команда &", "запустить сразу в фоне", "долгая выгрузка, а работать надо дальше",
           "запоминай & как «и»: команда — и сразу приглашение", "job_control", Z, PTY, 2, "job_control"),
        _h("kill %2", "остановить задачу номер 2 из jobs",
           "в фоне лишняя задача — PID искать не нужно",
           "% — «номер задачи», а не процесса", "job_control", Z, PTY, 2, "job_control"),
        _h("Ctrl+S, Ctrl+Q", "заморозить вывод на экране и разморозить",
           "экран вдруг замер и не печатает — скорее всего, нажал Ctrl+S: жми Ctrl+Q",
           "XOFF и XON — коды телетайпов «стоп, лента» и «давай дальше»", LEARN_CATALOG, Z,
           PTY, 2, "screen_scroll"),
        _h("ps aux | grep имя, kill PID", "найти процесс и остановить его",
           "программа зависла, а Ctrl+C до неё не достаёт",
           "ps — process status; kill — «убить», хотя шлёт вежливый сигнал", "kill_frozen",
           Z, PTY, 2, "kill_frozen"),
        _h("time команда", "сколько шла команда", "сравнить, какой способ быстрее",
           "time — «время»; total в конце — сколько прошло по часам", LEARN_CATALOG, Z, PTY,
           2, "job_control"),
        _h("caffeinate -i команда", "Mac не уснёт, пока идёт команда",
           "долгая выгрузка на ночь, а Mac засыпает через десять минут",
           "caffeine — кофеин; -i — idle, не засыпать от бездействия", LEARN_CATALOG, M, MAN,
           2, "job_control"),
        _h("nohup команда &", "команда доработает, даже если закрыть окно",
           "долгая задача, а окно хочется закрыть",
           "no hang up — «не вешать трубку»: сигнал SIGHUP шлют при обрыве связи",
           LEARN_CATALOG, Z, MAN, 3, "job_control"),
        _h("exit", "закрыть оболочку (или Ctrl+D на пустой строке)",
           "закончил — выйди; logout работает только во «входной» оболочке",
           "exit — «выход»; в обычном zsh logout ответит not login shell", LEARN_CATALOG, Z,
           PTY, 2, "job_control"),
    ],
    "output": [
        _h("| less", "длинный вывод — постранично: пробел, b, /слово, q",
           "вывод не влезает в экран", "less is more: less сделали «больше, чем more»",
           "less_search", Z, MAN, 1, "less_search"),
        _h("less +F файл", "следить за растущим файлом; Ctrl+C — стоп, q — выйти",
           "лог пишется прямо сейчас — смотри, что прибывает",
           "F — Follow, «следуй за концом»; то же делает F внутри less", LEARN_CATALOG, Z,
           MAN, 3, "less_search"),
        _h("tail -f файл", "показывать новые строки файла, пока не нажмёшь Ctrl+C",
           "смотреть журнал программы вживую", "tail — «хвост», f — follow, «следуй»",
           LEARN_CATALOG, Z, MAN, 2, "less_search"),
        _h("| tee файл", "вывод и на экран, и в файл",
           "хочешь видеть ход и сохранить запись", "тройник T у сантехников: труба на две",
           "tee_log", Z, PTY, 2, "tee_log"),
        _h("| pbcopy", "вывод команды — в буфер обмена", "вставить список в письмо или чат",
           "pb — pasteboard, буфер обмена в NeXTSTEP и macOS", "pbcopy_list", M, MAN_ONLY, 2,
           "pbcopy_list"),
        _h("pbpaste | sort", "буфер обмена — на вход команде",
           "скопировал список из браузера — отсортируй его в терминале",
           "paste — «вставить»; результат можно снова | pbcopy", LEARN_CATALOG, M, MAN_ONLY, 2,
           "pbcopy_list"),
        _h("Ctrl+L", "очистить экран, набранная строка останется",
           "экран забит, а команду ты уже начал",
           "L — form feed, «новый лист» у принтеров", "screen_scroll", Z, PTY, 1,
           "screen_scroll"),
        _h("Cmd+K", "очистить окно вместе с прокруткой", "начать с чистого экрана",
           "в iTerm2 это Clear Buffer, в Terminal.app — Clear to Start", "screen_scroll", IT,
           ITERM_MENU, 1, "screen_scroll"),
        _h("reset", "привести терминал в чувство", "после cat картинки на экране кракозябры",
           "reset — «сброс»: заново настраивает терминал, clear только чистит экран",
           LEARN_CATALOG, Z, MAN, 2, "file_ext"),
        _h("Cmd+F, Cmd+G", "поиск по выводу; Cmd+G — следующее совпадение",
           "слово где-то в длинном выводе — не листай глазами", "F — Find, «найти»",
           "screen_find", IT, ITERM_MENU, 1, "screen_find"),
        _h("двойной и тройной клик", "выделить слово или всю строку",
           "забрать слово из вывода в ans: двойной клик, Cmd+C, Cmd+V",
           "в iTerm2 выделенное сразу копируется в буфер", LEARN_CATALOG, IT, DOCS, 1,
           "home_tilde"),
        _h("Cmd+плюс, Cmd+минус, Cmd+0", "крупнее, мельче, обычный размер текста",
           "буквы мелкие — или нужно уместить широкую таблицу",
           "как в браузере", LEARN_CATALOG, IT, ITERM_MENU, 1, None),
    ],
    "macos": [
        _h("open -a Имя файл", "открыть файл нужной программой",
           "open -a TextEdit notes.txt — не той, что по умолчанию",
           "a — application, «программа»", "open_gui", M, MAN, 2, "open_gui"),
        _h("qlmanage -p файл", "быстрый просмотр (как пробел в Finder)",
           "глянуть картинку или PDF, не открывая программу; q или Esc — закрыть",
           "Quick Look manager; -p — preview, «предпросмотр»", LEARN_CATALOG, M, MAN_ONLY, 3,
           "open_gui"),
        _h("mdfind слово", "поиск Spotlight из терминала — мгновенно, по индексу",
           "find ищет долго, а mdfind — сразу; -name — по имени, -onlyin папка",
           "md — metadata: Spotlight хранит данные о файлах", LEARN_CATALOG, M, MAN, 2,
           "find_name"),
        _h("say текст", "Mac произнесёт текст вслух",
           "долгая команда && say готово — услышишь, когда закончится",
           "say — «скажи»; say -v '?' — список голосов, русский — Milena",
           LEARN_CATALOG, M, MAN_ONLY, 2, "job_control"),
    ],
    "iterm": [
        _h("Cmd+Shift+↑ ↓", "прыжок к прошлой и следующей команде в выводе",
           "вывод длинный — перескакивай от команды к команде, а не листай",
           "метки (marks): iTerm2 ставит их у каждого приглашения", "screen_find", I,
           ITERM_MENU, 2, "screen_find", setup=INTEGRATION),
        _h("Cmd+Shift+A", "выделить вывод последней команды",
           "скопировать результат целиком: Cmd+Shift+A, Cmd+C",
           "Select Output of Last Command — «выделить вывод последней команды»", "screen_find", I, ITERM_MENU, 2,
           "screen_find", setup=INTEGRATION),
        _h("Cmd+D, Cmd+Shift+D", "разделить окно: панель справа и панель снизу",
           "в одной панели работаешь, в другой — шпаргалка или лог",
           "Split Vertically — разделитель стоит вертикально, панели рядом; с Shift — "
           "горизонтально, одна под другой", LEARN_CATALOG, I,
           ITERM_MENU, 2, "screen_find"),
        _h("Cmd+[, Cmd+]", "перейти в соседнюю панель (или Cmd+Option+стрелки)",
           "окно разделено — переключайся без мыши",
           "как в Safari: Cmd+[ — назад, Cmd+] — вперёд", LEARN_CATALOG, I, ITERM_MENU, 2,
           "screen_find"),
        _h("Cmd+T", "новая вкладка", "нужна вторая оболочка рядом, без нового окна",
           "T — Tab, «вкладка»", LEARN_CATALOG, IT, ITERM_MENU, 1, None),
        _h("Cmd+← →", "соседняя вкладка (Cmd+цифра — вкладка по номеру)",
           "вкладок несколько — переключайся с клавиатуры",
           "стрелка — куда идти", LEARN_CATALOG, I, ITERM_KEYMAP, 2, "screen_find"),
        _h("Cmd+Shift+T", "вернуть закрытую вкладку или панель",
           "закрыл Cmd+W не то", "Undo Close — «отменить закрытие»", LEARN_CATALOG, I,
           ITERM_MENU, 2, None),
        _h("Cmd+;", "дописать слово, которое уже есть на экране",
           "длинный хеш или имя из вывода — набери начало и Cmd+;",
           "Autocomplete iTerm2: берёт слова из того, что видно", LEARN_CATALOG, I,
           ITERM_MENU, 2, "screen_find"),
        _h("Cmd+Shift+H", "история того, что ты вставлял в окно",
           "вставлял что-то час назад — достань снова", "Paste History", LEARN_CATALOG, I,
           ITERM_MENU, 2, "screen_find"),
        _h("Cmd+Option+B", "Instant Replay: перемотать экран назад во времени",
           "что-то мелькнуло и стёрлось — отмотай и посмотри",
           "«мгновенный повтор», как в спортивной трансляции", LEARN_CATALOG, I, ITERM_MENU,
           3, "screen_find"),
        _h("Cmd+Option+A", "уведомить, когда долгая команда закончится",
           "запустил сборку и ушёл в браузер", "Alert on Next Mark — «сигнал на следующей "
           "метке»", LEARN_CATALOG, I, ITERM_MENU, 3, "job_control", setup=INTEGRATION),
        _h("Cmd+клик", "открыть путь или ссылку из вывода",
           "в выводе адрес сайта или путь к файлу", "Semantic History iTerm2",
           LEARN_CATALOG, I, DOCS, 2, "open_gui"),
    ],
    "terminal": [
        _h("Cmd+↑ ↓ в Terminal.app", "прыжок к прошлой и следующей команде",
           "то же, что Cmd+Shift+↑ ↓ в iTerm2; метки Terminal ставит сам",
           "Jump to Previous Mark — «к прошлой метке»", LEARN_CATALOG, T, TERM_MENU, 2,
           "screen_find"),
        _h("Cmd+Option+O в Terminal.app", "включить и выключить Option как Meta",
           "чтобы Option+. и Option+B/F работали без Esc",
           "Use Option as Meta Key — «Option как Meta»", LEARN_CATALOG, T, TERM_MENU, 2,
           "quick_fix"),
    ],
    "config": [
        _h("alias ll='ls -l'", "своё короткое имя для длинной команды",
           "набираешь одно и то же по десять раз в день",
           "alias — «псевдоним»; чтобы жил всегда, его пишут в ~/.zshrc", LEARN_CATALOG, Z,
           PTY, 3, "env_vars"),
        _h("функция в ~/.zshrc", "своя команда из нескольких шагов",
           "alias мал: mkcd() { mkdir -p \"$1\" && cd \"$1\" } — создать папку и войти",
           "$1 — первый аргумент, который ты дашь функции", LEARN_CATALOG, Z, PTY, 3,
           "env_vars"),
        _h("type имя", "кто это: программа, alias, функция или встроенная команда",
           "команда ведёт себя не так, как в справке", "type — «тип»", LEARN_CATALOG, Z, PTY,
           2, "path_which"),
        _h("source ~/.zshrc", "применить правку настроек без нового окна",
           "дописал alias — включи его сразу", "source — «источник»: прочитать файл как "
           "набранные команды", LEARN_CATALOG, Z, PTY, 3, "env_vars"),
    ],
    # FB15 (FB5 п. 49): pyspark, airflow и boto3 в игре не ставим — им нужен кластер или
    # облако; здесь только совет, как их запускают из терминала
    "cluster": [
        _h("spark-submit job.py", "задачу pyspark — на кластер, а не на свой Mac",
           "pyspark, airflow и boto3 живут на сервере: заходят туда по ssh и запускают "
           "spark-submit job.py, airflow dags list, aws s3 ls — дома pip install не нужен",
           "submit — «отправить»: считает кластер, а терминал только отдаёт ему задачу",
           LEARN_CATALOG, Z, DOCS_CLI, 3, "boss_pylib"),
    ],
}


def all_hacks() -> List[Hack]:
    return [h for hacks in CATALOG.values() for h in hacks]


def tip_line(h: Hack) -> str:
    """Строка совета дня: «💡 клавиши — что делает»."""
    return f"{TIP}{h.keys} — {h.what}"


TIP = "💡 "


def _solved(p: dict, task_id: str) -> bool:
    rec = (p.get("tasks") or {}).get(task_id)
    return isinstance(rec, dict) and bool(rec.get("solved"))


def _game_order() -> Dict[str, int]:
    from termit_app.tasks import registry
    return {tid: n for n, tid in enumerate(registry.all_tasks())}


def ready(p: dict) -> List[Hack]:
    """Приёмы по силам игроку (after решена или None) — от простых к сложным, внутри уровня
    — по порядку игры, где игрок до них дорос."""
    order = _game_order()
    pool = [h for h in all_hacks() if h.after is None or _solved(p, h.after)]
    return sorted(pool, key=lambda h: (h.level, order.get(h.after, -1) if h.after else -1))


def tips(p: dict) -> List[str]:
    """Советы дня по очереди: только из каталога и только то, что игрок может применить."""
    return [tip_line(h) for h in ready(p)]


def pick(p: dict, turn: int) -> Optional[Hack]:
    """Приём по очереди: turn — счётчик (номер рана, номер задачи)."""
    pool = ready(p)
    return pool[turn % len(pool)] if pool else None


def summary_line(p: dict, turn: int) -> str:
    """Строка под итогом рана: приём на завтра — что делает и когда выручает."""
    h = pick(p, turn)
    return f"{TIP}Приём на завтра: {h.keys} — {h.what}. {h.when[0].upper()}{h.when[1:]}" \
        + ("" if h.when[-1] in ".?!…" else ".") if h else ""


# --- показ: короткий раздел в keys и весь каталог в keys hacks ----------------------------

SHORT = ("Esc .", "Ctrl+Y", "Ctrl+_", "^старое^новое", "Ctrl+Z", "Cmd+F, Cmd+G",
         "Cmd+Shift+↑ ↓")
SHEET_CMD = "keys hacks"


def short_section() -> str:
    """Раздел «Лайфхаки» для шпаргалки keys: несколько самых ходовых, ссылкой на весь."""
    by_keys = {h.keys: h for h in all_hacks()}
    rows = ["Лайфхаки (все — keys hacks, вне задачи — ./termit keys hacks)"]
    for keys in SHORT:
        h = by_keys[keys]
        rows.append(_fill(f"{keys:<16}{h.what}", "  ").replace("\n  ", "\n" + " " * 18))
    return "\n".join(rows)


def _where(h: Hack) -> str:
    if h.learn == LEARN_CATALOG:
        return ""
    from termit_app import theme
    from termit_app.tasks import registry
    task = registry.all_tasks().get(h.learn)
    title = theme.title(task) if task is not None else h.learn
    return f"учится: «{title}»"


def _sentence(label: str, text: str) -> str:
    return f"{label}: {text}" + ("" if text[-1] in ".?!…" else ".")


def _fill(text: str, indent: str) -> str:
    import textwrap
    from termit_app import tui
    return textwrap.fill(text, tui.text_width(), initial_indent=indent, subsequent_indent=indent,
                         break_long_words=False, break_on_hyphens=False)


def sheet(section: Optional[str] = None) -> str:
    """Весь каталог (или один раздел): клавиши, что делает, когда выручает, откуда имя,
    где учится и что настроить."""
    out = [_fill("Лайфхаки терминала — опыт тех, кто сидит в нём годами. Пробуй сразу: в "
                 "задаче или в обычном окне. Длинно — листай: keys hacks | less", ""),
           _fill("Один раздел — keys hacks РАЗДЕЛ: " + ", ".join(SECTIONS) +
                 " (имя раздела — в конце его заголовка).", "")]
    keys = [section] if section in SECTIONS else list(SECTIONS)
    for key in keys:
        out += ["", f"{SECTIONS[key]} · keys hacks {key}"]
        for h in CATALOG[key]:
            out.append(f"  {h.keys} — {h.what}")
            extra = [_sentence("Когда", h.when), _sentence("Откуда", h.origin)]
            where = _where(h)
            if where:
                extra.append(where[0].upper() + where[1:] + ".")
            if h.setup:
                extra.append(_sentence("Настройка", h.setup))
            out.append(_fill(" ".join(extra), "      "))
    return "\n".join(out)


def sections_of(words: Iterable[str]) -> Optional[str]:
    """`keys hacks РАЗДЕЛ`: ключ раздела по слову (line, history…) или None — весь каталог."""
    for word in words:
        if word in SECTIONS:
            return word
    return None
