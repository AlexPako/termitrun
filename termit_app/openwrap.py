"""Обёртка тренажёра над open (.termit/bin/open): python3 -m termit_app.openwrap АРГУМЕНТЫ...

Запускается внутри песочницы. open — единственная команда, которой песочница по замыслу
разрешает дойти до LaunchServices (задача open_gui, uses_gui): она открывает окна программ
вне песочницы. Поэтому обёртка пропускает только то, что нужно уроку (В5 приёмки-1):
  * папки — только в Finder: open ПАПКА, open -a Finder ПАПКА, open -R ПАПКА;
  * обычные файлы безопасных типов (DOC_APPS) — только явной программой: txt, md, csv, log,
    json — TextEdit, png, jpg, gif, pdf — Preview; -a TextEdit|Preview, -e, -t, -R.
Каждый путь раскрывается (realpath) и обязан остаться внутри песочницы. Отказ — пакеты (.app,
.bundle и любая папка с расширением), .command, .tool, .terminal, .html, .webloc, .inetloc и
прочие типы, файлы без расширения, файлы с битом x, FIFO и устройства, ссылки (URL), другие
программы, -b, -n, --args и пути наружу. Отказ в журнал не пишется.

Настоящему /usr/bin/open уходит не то, что набрал игрок, а план: раскрытый путь и явная
программа (-a Finder / TextEdit / Preview или -R) — LaunchServices не выбирает обработчик сам.
Разрешённый вызов пишется в .termit/open.log как набран (его читает check задачи).

Полностью путь наружу так не закрыть: /usr/bin/open можно вызвать напрямую. Это сознательное
исключение одной задачи, оно описано в спеке (раздел «Защита настоящих файлов»)."""
import os
import stat
import sys
from typing import List, Optional, Tuple

DOC_APPS = {"txt": "TextEdit", "md": "TextEdit", "csv": "TextEdit", "log": "TextEdit",
            "json": "TextEdit", "png": "Preview", "jpg": "Preview", "jpeg": "Preview",
            "gif": "Preview", "pdf": "Preview"}
APPS = {"finder": "Finder", "textedit": "TextEdit", "preview": "Preview"}
REFUSE = ("open в тренажёре открывает только папки задачи (в Finder) и документы txt, md, csv, "
          "log, json, png, jpg, gif, pdf (в TextEdit или Preview).")

Plan = Tuple[Optional[List[List[str]]], str]


def _inside(real: str, box: str) -> bool:
    b = os.path.realpath(box).rstrip("/")
    return real == b or real.startswith(b + "/")


def _target(arg: str, cwd: str, box: str) -> Tuple[Optional[str], str, str]:
    """(раскрытый путь, вид: dir|doc, программа для документа) или (None, причина, '')."""
    if "://" in arg or arg.startswith("file:"):
        return None, f"{arg}: ссылки open здесь не открывает", ""
    try:
        real = os.path.realpath(os.path.join(cwd, arg))
        st = os.stat(real)
    except OSError:
        return None, f"{arg}: такого файла или папки нет", ""
    if not _inside(real, box):
        return None, f"{arg}: путь ведёт за пределы задачи", ""
    name = os.path.basename(real)
    ext = name.rsplit(".", 1)[1].lower() if "." in name.lstrip(".") else ""
    if stat.S_ISDIR(st.st_mode):
        if ext or os.path.exists(os.path.join(real, "Contents", "Info.plist")):
            return None, f"{arg}: это пакет программы, а не папка", ""
        return real, "dir", "Finder"
    if not stat.S_ISREG(st.st_mode):
        return None, f"{arg}: это не обычный файл", ""
    if st.st_mode & 0o111:
        return None, f"{arg}: исполняемый файл open здесь не запускает", ""
    if ext not in DOC_APPS:
        return None, f"{arg}: такой тип файла open здесь не открывает", ""
    return real, "doc", DOC_APPS[ext]


def plan(args: List[str], cwd: str, box: str) -> Plan:
    """Что передать настоящему open (список вызовов) или (None, причина отказа)."""
    if not box:
        return None, "нет песочницы"
    app = None          # явная программа -a / -e / -t
    reveal = False
    paths = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-a":
            if i + 1 >= len(args):
                return None, "после -a нужно имя программы"
            name = args[i + 1].lower()
            name = name[:-4] if name.endswith(".app") else name
            if name not in APPS:
                return None, f"-a {args[i + 1]}: здесь можно только Finder, TextEdit или Preview"
            app = APPS[name]
            i += 2
            continue
        if a in ("-e", "-t"):
            app = "TextEdit"
        elif a == "-R":
            reveal = True
        elif a.startswith("-"):
            return None, f"ключ {a} здесь не поддерживается"
        else:
            paths.append(a)
        i += 1
    if not paths:
        if reveal or app in (None, "Finder"):
            return None, "укажи, что открыть"
        return [["-a", app]], ""
    cmds = []
    for a in paths:
        real, kind, default = _target(a, cwd, box)
        if real is None:
            return None, kind
        if reveal:
            cmds.append(["-R", real])
        elif kind == "dir":
            if app not in (None, "Finder"):
                return None, f"{a}: папки открывает Finder, а не {app}"
            cmds.append(["-a", "Finder", real])
        else:
            if app == "Finder":
                return None, f"{a}: документ открывают TextEdit или Preview, а не Finder"
            cmds.append(["-a", app or default, real])
    return cmds, ""


def _log(box: str, cwd: str, args: List[str]) -> None:
    fd = os.open(os.path.join(box, ".termit", "open.log"),
                 os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(f"{cwd}\t{' '.join(args)}\n")


def main(args: List[str]) -> int:
    box = os.environ.get("TERMIT_BOX", "")
    cwd = os.getcwd()
    pwd = os.environ.get("PWD", "")
    try:                        # в журнал — путь, как его видит игрок (без раскрытия /var)
        if pwd and os.path.samefile(pwd, cwd):
            cwd = pwd
    except OSError:
        pass
    cmds, why = plan(args, cwd, box)
    if cmds is None:
        print(f"{why}. {REFUSE}", file=sys.stderr)
        return 1
    try:
        _log(box, cwd, args)
    except OSError:
        pass
    if os.environ.get("TERMIT_NO_GUI"):
        return 0
    import subprocess
    code = 0
    for c in cmds:
        code = subprocess.run(["/usr/bin/open"] + c).returncode or code
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
