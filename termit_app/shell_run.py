"""Запуск интерактивного zsh в песочнице (под sandbox-exec, если он есть)."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from termit_app import implants, paths, theme


def _q(s) -> str:
    """Экранирование для строки в профиле sandbox-exec."""
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _rx(s) -> str:
    """Путь внутри регулярного выражения #"..." профиля (там обратная косая не экранируется)."""
    return re.escape(str(s)).replace('"', '.')


# Секреты дома: читать из песочницы нельзя (А2 отчёта 07, В2 приёмки-1). Пути — от настоящего
# дома. Сверх этого списка закрыты ВСЕ «точечные» записи в корне дома (HOME_DOT_ALLOW — что
# нужно zsh владельца с Oh My Zsh): новые .copilot, .mongodb, .yandex и т.п. закрыты сами.
SECRET_DIRS = (".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".config/gh",
               ".config/gcloud", ".config/git", ".config/hub", ".config/op", ".config/1Password",
               ".config/rclone", ".config/github-copilot", ".ollama", ".claude", ".copilot",
               ".mongodb", ".agent-browser", ".colima", ".lima", ".yandex", ".zsh_sessions",
               ".password-store", ".terraform.d", ".local/share/keyrings", "backups", "Library/Keychains", "Library/Mail", "Library/Messages",
               "Library/Cookies", "Library/Safari", "Library/Application Support",
               "Library/Containers", "Library/Group Containers", "Library/HTTPStorages",
               "Library/WebKit", "Library/Accounts", "Library/IdentityServices")
SECRET_FILES = (".zsh_history", ".bash_history", ".python_history", ".psql_history",
                ".node_repl_history", ".mysql_history", ".sqlite_history", ".lesshst",
                ".viminfo", ".vault-token")
# Секреты в любом месте дома, в т.ч. прямо в его корне (кроме самой песочницы).
SECRET_REGEX = (r"[^/]*\.env(\.[^/]*)?$",                 # .env, prod.env, .env.local
                r"[^/]*\.(pem|p12|pfx|key|kdbx|keychain-db)$",
                r"id_(rsa|ed25519|ecdsa|dsa)[^/]*$",
                r"secrets?(/|$)",
                r"\.(netrc|pgpass|npmrc|pypirc|git-credentials)$",
                r"[^/]*(token|credentials?)(\.json|\.txt)?$",
                r"\.claude\.json",                         # и копии .claude.json.bak-…
                r"[^/]*_history$",                          # истории оболочек и REPL
                r"[^/]*\.(ovpn|mobileconfig)$",             # VPN и профили с ключами
                r"(wg[0-9]*|[^/]*([Vv][Pp][Nn]|[Ww]ire[Gg]uard|[Bb]lanc)[^/]*)\.conf$")
# Что из «точечного» в корне дома нужно zsh владельца: ~/.zshrc, Oh My Zsh и популярные
# менеджеры плагинов, интеграция iTerm2, dump compinit, базовые настройки. Копии .zshrc
# (.zshrc.bak-…) сюда не входят: в них бывают экспорты токенов.
HOME_DOT_ALLOW_DIRS = (".oh-my-zsh", ".iterm2", ".homebrew", ".vim", ".config/termit", ".fzf",
                       ".zsh", ".zinit", ".antigen", ".zplug", ".zprezto", ".zim")
# ~/.gitconfig закрыт (Fix round 1): в игре HOME — дом песочницы, git его не читает, а
# старт OMZ и git-промпт без него те же (проверено на ~/.zshrc владельца); в нём бывают
# insteadOf с токеном.
HOME_DOT_ALLOW_FILES = (".zshrc", ".zshrc.zwc", ".iterm2_shell_integration.zsh",
                        ".vimrc", ".nanorc", ".inputrc", ".CFUserTextEncoding", ".p10k.zsh",
                        ".fzf.zsh", ".zimrc", ".zpreztorc", ".tmux.conf", ".editorconfig")
HOME_DOT_ALLOW_REGEX = (r"\.zcompdump[^/]*$",)
# Личные папки, проекты и Library владельца закрыты целиком (Fix round 1). Папка самой игры
# (paths.ROOT, папка игры) открыта: её читают хук и обёртки.
# Поверх списка закрыто всё нескрытое в корне дома (S-DB1, часть 9): список остаётся явным
# перечнем «что точно личное» — и на случай, если правило корня когда-нибудь ослабят.
HOME_PRIVATE_DIRS = ("Documents", "Desktop", "Downloads", "Pictures", "Movies", "Music",
                     "projects", "Library")
# Эти программы поручают работу службам вне песочницы (А5) — запускать нельзя.
DENY_EXEC = ("/bin/launchctl", "/usr/bin/osascript", "/usr/sbin/screencapture",
             "/usr/bin/automator", "/usr/bin/shortcuts", "/usr/bin/security",
             # В6: диски не нужны ни одной задаче — ни отмонтировать, ни извлечь
             "/usr/sbin/diskutil", "/usr/bin/hdiutil")


def _ancestors(targets, home: Path) -> list:
    """Папки между домом и targets (не включая дом и сами targets): им нужен stat, иначе
    mkdir -p, git и realpath не пройдут сквозь закрытую ~/projects к игре и песочнице."""
    out = []
    for t in targets:
        for parent in Path(t).parents:
            if parent == home or home not in parent.parents:
                break
            if str(parent) not in out:
                out.append(str(parent))
    return out


def _runtime_dirs() -> list:
    """Код игры и интерпретатор: читаются, даже если лежат в «точечной» папке дома (pyenv,
    uv и т.п.) — иначе песочница не запустит ни launch, ни учебный ps."""
    out = []
    for d in (paths.ROOT, sys.prefix, sys.base_prefix, Path(sys.executable).resolve().parent):
        try:
            r = str(Path(d).resolve())
        except OSError:
            continue
        if r not in out:
            out.append(r)
    return out


def own_ttys() -> list:
    """Свой терминал родителя (на нём и запустится zsh): настоящие пути /dev/ttysNNN."""
    out = []
    for fd in (0, 1, 2):
        try:
            if os.isatty(fd):
                t = os.path.realpath(os.ttyname(fd))
                if t not in out:
                    out.append(t)
        except OSError:
            continue
    return out


def sandbox_profile(box: Path, real_home: Path, clipboard: bool = True, gui: bool = True,
                    ttys=(), paste: bool = True) -> str:
    """Профиль sandbox-exec поручения (цель из отчёта 07, часть А):
    запись — только в песочницу (кэш Oh My Zsh и .zcompdump — тоже в ней); чтение секретов —
    нет; сети нет, кроме unix-сокетов в песочнице (на localhost живут SOCKS-туннель и базы
    владельца); сигналы — только процессам этой же песочницы; Apple Events,
    запись настроек, launchctl/osascript — нет; буфер обмена и LaunchServices (open) — только
    задачам, которым они нужны. sandbox-exec сравнивает настоящие пути, поэтому симлинки
    (/var, /tmp) раскрываем. ttys — свой терминал (own_ttys): писать и открывать из
    песочницы можно только его и /dev/tty, чужие вкладки /dev/ttys* — нет (В3)."""
    box = Path(box).resolve()
    real_home = Path(real_home).resolve()
    b, h, rh = _q(box), _q(real_home), _rx(real_home)
    mine = " ".join(f'(literal "{_q(t)}")' for t in ttys)
    anc = " ".join(f'(literal "{_q(d)}")'
                   for d in _ancestors([box] + [Path(x) for x in _runtime_dirs()], real_home))
    lines = [
        "(version 1)",
        "(allow default)",
        # А4: запись — белый список
        "(deny file-write*)",
        f'(allow file-write* (subpath "{b}")'
        ' (literal "/dev/null") (literal "/dev/zero") (literal "/dev/dtracehelper")'
        ' (literal "/dev/ptmx") (literal "/dev/tty") (regex #"^/dev/fd/")'
        + (" " + mine if mine else "") + ")",
        # В3: чужие терминалы не открывать даже на чтение (перехват ввода другой вкладки)
        '(deny file-read-data (regex #"^/dev/(tty[^/]+|pty[^/]+)$"))',
        *([f"(allow file-read-data {mine})"] if mine else []),
        # В2: всё «точечное» в корне дома — закрыто, кроме нужного оболочке (ниже)
        f'(deny file-read* (regex #"^{rh}/\\."))',
        "(deny file-read* "
        + " ".join(f'(subpath "{h}/{_q(d)}")' for d in HOME_PRIVATE_DIRS) + ")",
        # S-DB1 (часть 9, остаток В2): и всё нескрытое в корне дома — ~/inbox, ~/Apps,
        # ~/Public, новые папки и файлы. Перекрывают только разрешения ниже: точечное для
        # zsh, код игры, stat звеньев пути и сама песочница. Листинг самого дома — есть
        f'(deny file-read* (regex #"^{rh}/[^./][^/]*"))',
        "(allow file-read* "
        + " ".join(f'(subpath "{h}/{_q(d)}")' for d in HOME_DOT_ALLOW_DIRS) + " "
        + " ".join(f'(literal "{h}/{_q(f)}")' for f in HOME_DOT_ALLOW_FILES) + " "
        + " ".join(f'(regex #"^{rh}/{r}")' for r in HOME_DOT_ALLOW_REGEX) + " "
        + " ".join(f'(subpath "{_q(d)}")' for d in _runtime_dirs()) + ")",
        # путь до игры и песочницы сквозь закрытые папки: только stat звеньев, не листинг
        *([f"(allow file-read-metadata {anc})"] if anc else []),
        # А2: чтение секретов (и внутри разрешённого выше)
        "(deny file-read* "
        + " ".join(f'(subpath "{h}/{_q(d)}")' for d in SECRET_DIRS) + " "
        + " ".join(f'(literal "{h}/{_q(f)}")' for f in SECRET_FILES) + " "
        + " ".join(f'(regex #"^{rh}/(.*/)?{r}")' for r in SECRET_REGEX) + ")",
        f'(allow file-read* (subpath "{b}"))',      # внутри песочницы читать можно всё
        # А2: сеть — никуда, даже на localhost (там SOCKS-туннель, PAC, базы владельца);
        # только unix-сокеты внутри песочницы. Входящие и bind — тоже только в песочнице.
        "(deny network-outbound)",
        f'(allow network-outbound (subpath "{b}"))',
        "(deny network-inbound)",
        "(deny network-bind)",
        f'(allow network-bind (subpath "{b}"))',
        # А3: сигналы — только своим
        "(deny signal)",
        "(allow signal (target same-sandbox))",
        # А5: службы, которые исполняют команды вне песочницы
        "(deny appleevent-send)",
        "(deny user-preference-write)",
        "(deny process-exec " + " ".join(f'(literal "{x}")' for x in DENY_EXEC) + ")",
    ]
    if not clipboard:      # А7: буфер владельца — только задачам про буфер
        lines.append('(deny mach-lookup (global-name "com.apple.pasteboard.1"))')
    elif not paste:        # В6: pwd | pbcopy — можно, а читать буфер владельца (pbpaste) — нет
        lines.append('(deny process-exec (literal "/usr/bin/pbpaste"))')
    if not gui:            # А5: open/LaunchServices запускают программы вне песочницы
        lines.append('(deny mach-lookup (global-name "com.apple.coreservices.launchservicesd"))')
        # В6: служба дисков (её зовёт diskutil и любой его заменитель)
        lines.append('(deny mach-lookup (global-name "com.apple.DiskArbitration.diskarbitrationd"))')
    return "\n".join(lines) + "\n"


# Папка учебного сервера PostgreSQL в песочнице (часть 9б, termit_app/pgkit): данные кластера,
# pg_hba.conf, журнал сервера. Пишут в неё только родитель и сам сервер; zsh игрока — нет
# (B0, риск «файлы кластера доступны игроку»): иначе подменённый pg_hba.conf или
# postgresql.auto.conf подхватил бы следующий старт, а испорченные файлы данных — уронили сервер.
PG_DIR = ".termit/pg"


def _pg_guard(box: Path) -> str:
    """Запрет записи в папку сервера БД — во всех профилях zsh (и задачам без сервера: папки
    там нет, правило ничего не меняет). Сокет сервера лежит в ней же (ревью B1, M1): к нему
    игрок подключается (запись в папку для этого не нужна), а подложить свой — не может. Сам
    box/.termit тоже не переименовать, не удалить и не завести заново (иначе подмена шла бы
    через «mv .termit; mkdir -p .termit/pg»): запрещены только unlink и create самой папки —
    писать файлы внутри можно, и проверка [[ -w .termit ]] (compinit) по-прежнему истинна."""
    box = Path(box).resolve()
    return (f'(deny file-write* (subpath "{_q(box / PG_DIR)}"))\n'
            f'(deny file-write-unlink file-write-create (literal "{_q(box / ".termit")}"))\n')


def task_profile(box: Path, real_home: Path, task=None, ttys=None) -> str:
    """Профиль с учётом того, что нужно поручению (буфер, окна). Сети нет ни у одной задачи.
    ttys — свои терминалы; по умолчанию — терминал родителя (own_ttys)."""
    return sandbox_profile(box, real_home,
                           clipboard=bool(getattr(task, "uses_clipboard", True)),
                           gui=bool(getattr(task, "uses_gui", True)),
                           paste=bool(getattr(task, "uses_paste", True)),
                           ttys=own_ttys() if ttys is None else ttys) + _pg_guard(box)


def _exec_only(program: str) -> str:
    """Запуск программ — только program (настоящий путь: ядро сверяет его, а не симлинк).
    Последнее совпавшее правило побеждает, поэтому строки — в конце профиля."""
    return ("(deny process-exec)\n"
            f'(allow process-exec (literal "{_q(os.path.realpath(program))}"))\n')


def server_profile(box: Path, real_home: Path, postgres: str) -> str:
    """Учебный сервер PostgreSQL (часть 9б, спайк B0): профиль песочницы без буфера, окон и
    терминалов, и запуск программ — только сам postgres. postmaster на macOS делает fork без
    exec, а всё, что зовёт /bin/sh (COPY … TO/FROM PROGRAM, archive_command,
    restore_command), упирается в запрет. Сеть — как у zsh: только unix-сокеты в box; приём
    соединения на них профиль не режет (B0, Darwin 27), послаблений нет. postgres — настоящий
    путь (os.path.realpath): после brew upgrade он другой, профиль строится каждый раз."""
    return (sandbox_profile(Path(box), Path(real_home), clipboard=False, gui=False, ttys=())
            + _exec_only(postgres))


def reader_profile(box: Path, real_home: Path, psql: str) -> str:
    """Доверенный psql родителя (сид и снимок для проверки, часть 9б): писать нельзя ничего,
    запускать — только сам psql, сеть — только unix-сокеты в box (сервер задачи)."""
    return (sandbox_profile(Path(box), Path(real_home), clipboard=False, gui=False, ttys=())
            + "(deny file-write*)\n"
            + '(allow file-write* (literal "/dev/null"))\n'
            + _exec_only(psql))


# Повторная проверка родителя (P2 fix1 I1): check открытой задачи исполняется не в родителе, а
# в дочернем процессе под профилем задачи и с двумя ограничениями сверху: записывать нельзя
# ничего, а читать содержимое файлов — только в песочнице, в коде игры, интерпретаторе и
# системных папках. Симлинк из песочницы наружу, FIFO, гигант — забота таймаута и профиля.
RECHECK_READ_SYSTEM = ("/usr", "/System", "/Library", "/bin", "/sbin", "/private/var/db",
                       "/private/preboot", "/private/etc", "/private/var/select", "/opt/homebrew")
# из /dev — только нужное интерпретатору (P2 fix2 M9): /dev/zero и прочие — нет
RECHECK_READ_DEV = ("/dev/null", "/dev/urandom", "/dev/random", "/dev/dtracehelper")


def recheck_profile(box: Path, real_home: Path, task=None) -> str:
    """Профиль задачи + «только чтение» + чтение данных лишь из песочницы и системного."""
    b = _q(Path(box).resolve())
    keep = [f'(subpath "{b}")'] + [f'(subpath "{_q(d)}")' for d in _runtime_dirs()] + \
        [f'(subpath "{_q(d)}")' for d in RECHECK_READ_SYSTEM] + ['(literal "/")'] + \
        [f'(literal "{d}")' for d in RECHECK_READ_DEV] + ['(regex #"^/dev/fd/")']
    extra = ["(deny file-write*)",
             '(allow file-write* (literal "/dev/null"))',
             "(deny file-read-data (require-not (require-any " + " ".join(keep) + ")))",
             # код из песочницы не грузится и не исполняется (P2 fix2 C1): модули Python в
             # ней не читаются, программы из неё не запускаются
             f'(deny file-read-data (regex #"^{_rx(Path(box).resolve())}/.*\\.(py|pyc|pyo|pth|so)$"))',
             f'(deny process-exec (subpath "{b}"))']
    return task_profile(box, real_home, task, ttys=()) + "\n".join(extra) + "\n"


# А6: в песочницу попадает только белый список переменных (имена; значения не печатаем).
ENV_KEEP = {"PATH", "TERM", "LANG", "SHELL", "USER", "LOGNAME", "COLORTERM", "EDITOR",
            "VISUAL", "PAGER", "LESS", "LSCOLORS", "LS_COLORS", "CLICOLOR", "COLUMNS", "LINES",
            "SHLVL", "__CF_USER_TEXT_ENCODING"}
ENV_KEEP_PREFIX = ("LC_", "TERM_PROGRAM", "TERM_SESSION_ID", "ITERM_", "TERMIT_")
ENV_DROP = {"TERMIT_AUTORUN", "TERMIT_LAUNCHED", "TERMIT_SANDBOXED", "TERMIT_PROMPT",
            "TERMIT_RPROMPT", "TERMIT_ZOXIDE"}
SECRET_ENV = re.compile(r"TOKEN|KEY|SECRET|PASS|AUTH|CRED", re.I)


def scrub_env(env: dict) -> dict:
    return {k: v for k, v in env.items()
            if (k in ENV_KEEP or k.startswith(ENV_KEEP_PREFIX)) and k not in ENV_DROP
            and (k.startswith("TERMIT_") or not SECRET_ENV.search(k))}


BREW_DIRS = implants.BREW_DIRS
SYSTEM_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


def _add_brew_dirs(env: dict) -> None:
    """PATH песочницы: что было + базовый системный путь (даже из env -i — иначе в песочнице
    нет ни ls, ни cat), затем папки Homebrew в конце, если их нет, а папка есть: утилита
    видна, даже если termit запущен из урезанного окружения. Свои программы игрока не
    перекрывает."""
    parts = [x for x in env.get("PATH", "").split(":") if x]
    for d in SYSTEM_PATH:
        if d not in parts:
            parts.append(d)
    for d in BREW_DIRS:
        if d not in parts and os.path.isdir(d):
            parts.append(d)
    env["PATH"] = ":".join(parts)


def pg_env(box) -> dict:
    """Куда ходит psql игрока: сервер задачи в box (сокет box/.termit/pg, свой номер порта в имени
    сокета), роль runner, база vault. Песочный .zshrc выставляет это после ~/.zshrc владельца
    (там бывают PGHOST/PGPASSWORD облачной базы); tests/refrun — прямо в env (zsh -f)."""
    from termit_app import pgkit
    return {"PGHOST": str(pgkit.sock_dir(box)), "PGPORT": str(pgkit.PORT),
            "PGUSER": pgkit.RUNNER, "PGDATABASE": pgkit.DATABASE}


def build_env(box, label: str, real_home: Path, bare: bool = False,
              no_gui: bool = False, autorun: str = None, prompt: str = None,
              rprompt: str = None, task=None, db_engine: str = None) -> dict:
    """prompt/rprompt — своё приглашение игрока из деталей убежища (только для песочницы).
    task — поручение: у задачи с утилитой zoxide (z_jump) при найденном zoxide —
    TERMIT_ZOXIDE=1, и песочный .zshrc включит zoxide со своей базой внутри песочницы.
    db_engine — движок задачи БД (state["_engine"]): справка TERMIT_DB_ENGINE, а у
    PostgreSQL — TERMIT_PG* для песочного .zshrc (он экспортирует PGHOST и др.)."""
    env = scrub_env(dict(os.environ))
    env.update({
        "ZDOTDIR": str(paths.SHELL_DIR),
        "TERMIT_BOX": str(box),
        "TERMIT_PY": sys.executable,
        # PYTHONPATH=ROOT больше не ставим (часть 7, A1): sys.path игрока чистый, а хук,
        # обёртки и launch находят игру сами (paths.BOOT, корень — аргументом)
        "PYTHONDONTWRITEBYTECODE": "1",
        "TERMIT_LABEL": label,
        "TERMIT_THEME": theme.current(),
        "HOME": str(real_home),
        "TMPDIR": str(Path(box) / ".termit" / "tmp") + "/",    # А4: временные файлы — в песочнице
        "TMPPREFIX": str(Path(box) / ".termit" / "tmp" / "zsh"),   # here-doc и =(...) в zsh
        "GIT_CONFIG_NOSYSTEM": "1",                             # А6: без системного credential.helper
    })
    _add_brew_dirs(env)
    if bare:
        env["TERMIT_BARE"] = "1"
    if no_gui:
        env["TERMIT_NO_GUI"] = "1"
    if autorun:
        env["TERMIT_AUTORUN"] = autorun
    if prompt:
        env["TERMIT_PROMPT"] = prompt
    if rprompt:
        env["TERMIT_RPROMPT"] = rprompt
    if getattr(task, "implant", None) == "zoxide" and implants.which("zoxide"):
        env["TERMIT_ZOXIDE"] = "1"
    for k in [k for k in env if k.startswith("TERMIT_PG")]:
        env.pop(k)                      # только от родителя, не из окружения запуска
    env.pop("TERMIT_DB_ENGINE", None)
    if db_engine:
        env["TERMIT_DB_ENGINE"] = db_engine
    if db_engine == "pg":
        env.update({"TERMIT_" + k: v for k, v in pg_env(box).items()})
    return env


NO_SANDBOX_WARNING = ("⚠ sandbox-exec не найден — zsh запускается БЕЗ защиты песочницы: команды "
                      "могут менять и читать любые твои файлы. Будь осторожен.")


def argv(box, real_home: Path, use_sandbox: bool = True, task=None) -> list:
    """zsh стартует через termit_app.launch: тот сначала запускает процессы поручения —
    внутри той же песочницы, что и zsh (иначе их нельзя было бы ни запереть, ни убить)."""
    zsh = shutil.which("zsh") or "/bin/zsh"
    cmd = paths.py_argv("termit_app.launch", str(box), zsh, "-i")
    if use_sandbox:
        if shutil.which("sandbox-exec"):
            return ["sandbox-exec", "-p", task_profile(Path(box), Path(real_home), task)] + cmd
        print(NO_SANDBOX_WARNING, file=sys.stderr)    # молча — только по явному --no-sandbox
    return cmd


def mark_sandbox(env: dict, argv: list) -> dict:
    """Под sandbox-exec — метка TERMIT_SANDBOXED=1: учебный ps честно скажет «видны только
    процессы игры»; без песочницы он видит все процессы пользователя."""
    if argv and argv[0] == "sandbox-exec":
        env["TERMIT_SANDBOXED"] = "1"
    return env


def run(cwd, env: dict, argv: list) -> int:
    """Ctrl+C забирает себе zsh (у него своя группа процессов); родителя страхуем от случайного."""
    p = subprocess.Popen(argv, cwd=str(cwd), env=env)
    while True:
        try:
            return p.wait()
        except KeyboardInterrupt:
            continue
