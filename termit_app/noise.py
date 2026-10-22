"""«Шум» — правдоподобное рабочее окружение в песочнице (FB5 п. 70, владелец 22.10: «в
заданиях крайне мало папок и файлов — не похоже на рабочее окружение»).

Два слоя extras (story.extra):
  home — дом песочницы (~): Documents, Downloads, Desktop, Pictures, соседние проекты в
         ~/projects (.git, README, src, логи, node_modules), старые бэкапы *_final_v2;
  box  — одна-две посторонние папки рядом с файлами задачи.
Кто какой слой получает — story.SAFE_HOSTS["noise_home"] и ["noise_box"]: хозяин проверен
tests/test_extras_hosts.py (без действий не решено, эталон с шумом решает). Пусто — только в
первых уроках «Основ» и у стражей.

Раскладка детерминирована зерном рана: одно зерно — один и тот же «компьютер». Имена —
английские (п. 42), годы — мира игры (2724–2726). Объём умеренный: дом до ~70 файлов,
папка задачи — до 6."""
import random
import time
from typing import List

from termit_app import story

SALT_HOME = 0x5A1E
SALT_BOX = 0xB0C5
DAY = 86400

_FIRST = ("anna", "max", "olga", "ivan", "kate", "leo", "nina", "paul")
_DOCS = ("meeting_notes.txt", "budget_2725.xlsx", "contract_final.docx",
         "contract_final_v2.docx", "contract_final_v2 (1).docx", "cv_2724.pdf",
         "passport_scan.pdf", "plan_q3.txt", "lease_agreement.pdf", "receipts_2725.csv")
_DOWNLOADS = ("installer_v3.2.dmg", "invoice_0425.pdf", "invoice_0425 (1).pdf",
              "photo_2725_08_14.jpg", "report (1).pdf", "data_export.csv", "archive.zip",
              "slides_final_v3.pptx", "font_pack.zip", "music_mix.mp3", "setup_tool.pkg")
_PICTURES = ("IMG_0412.jpg", "IMG_0413.jpg", "IMG_0977.HEIC", "beach_2725.jpg",
             "avatar.png", "wallpaper.jpg")
_PROJECTS = {
    "site": ("index.html", "style.css", "app.js"),
    "parser": ("main.py", "utils.py", "requirements.txt"),
    "notes-app": ("index.js", "package.json", "db.js"),
    "scripts": ("backup.sh", "cleanup.sh", "sync.sh"),
}
_BOX_DIRS = {
    "old_stuff": ("readme_old.txt", "todo_2724.txt", "draft_v1.txt"),
    "shared": ("team_list.txt", "phones.txt"),
    "tmp_export": ("export_2725_03.tsv", "export_2725_04.tsv"),
    "misc": ("notes.md", "links.txt", "ideas.txt"),
}


def _ago(rng: random.Random, lo: int, hi: int) -> float:
    """Время изменения «давно»: от lo до hi дней назад — шум не новее файлов задачи. Отсчёт —
    от начала суток: в один день одно зерно даёт ту же раскладку до секунды."""
    today = time.time() // DAY * DAY
    return today - rng.randint(lo, hi) * DAY - rng.randint(0, DAY - 1)


def _text(rng: random.Random, name: str) -> str:
    who = rng.choice(_FIRST)
    if name.endswith((".txt", ".md")):
        return "\n".join([f"# {name}", f"owner: {who}",
                          *(f"- item {i}: {rng.choice(('ok', 'later', 'ask ' + who, 'done'))}"
                            for i in range(1, rng.randint(3, 7)))]) + "\n"
    if name.endswith((".csv", ".tsv")):
        sep = "," if name.endswith(".csv") else "\t"
        rows = [sep.join(("date", "item", "sum"))]
        rows += [sep.join((f"2725-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                           rng.choice(("coffee", "taxi", "books", "cloud")),
                           str(rng.randint(3, 400)))) for _ in range(rng.randint(3, 8))]
        return "\n".join(rows) + "\n"
    if name.endswith(".log"):
        return "\n".join(f"2725-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d} "
                         f"{rng.choice(('INFO', 'INFO', 'DEBUG', 'WARN'))} "
                         f"{rng.choice(('started', 'request ok', 'cache hit', 'retry'))}"
                         for _ in range(rng.randint(5, 15))) + "\n"
    if name.endswith((".sh",)):
        return f"#!/bin/sh\n# {name}: {who}'s helper\necho '{name} done'\n"
    if name.endswith((".py",)):
        return f'"""{name}"""\n\n\ndef run():\n    return "{who}"\n'
    if name.endswith((".js",)):
        return f"// {name}\nmodule.exports = () => '{who}';\n"
    if name.endswith(".json"):
        return '{\n  "name": "notes-app",\n  "version": "0.3.1"\n}\n'
    if name.endswith((".html", ".css")):
        return f"<!-- {name} by {who} -->\n"
    if name in ("requirements.txt",):
        return "requests==2.31.0\n"
    # «бинарные» документы, картинки и архивы: заглушка с подписью формата
    return f"{name.rsplit('.', 1)[-1].upper()} placeholder · {who}\n"


def _mark(e: dict) -> dict:
    """Пометка «шум»: копилка расширений такие файлы не считает (extensions._noise_paths)."""
    e["noise"] = True
    return e


def _file(root: str, path: str, rng: random.Random, lo: int = 20, hi: int = 700) -> dict:
    name = path.rsplit("/", 1)[-1]
    return _mark(story.extra(root, path, _text(rng, name), mtime=_ago(rng, lo, hi),
                             mode=0o755 if name.endswith(".sh") else None))


def home(seed: int) -> List[dict]:
    """Дом песочницы: обычные папки пользователя и пара соседних проектов."""
    rng = random.Random(seed ^ SALT_HOME)
    out = []
    for name in rng.sample(_DOCS, rng.randint(4, 7)):
        out.append(_file("home", f"Documents/{name}", rng))
    for name in rng.sample(_DOWNLOADS, rng.randint(5, 9)):
        out.append(_file("home", f"Downloads/{name}", rng, 3, 200))
    out.append(_file("home", f"Desktop/Screenshot 2725-{rng.randint(1, 12):02d}-"
                             f"{rng.randint(1, 28):02d} at {rng.randint(9, 20)}.{rng.randint(10, 59)}"
                             f".{rng.randint(10, 59)}.png", rng, 3, 60))
    out.append(_file("home", "Desktop/todo.txt", rng, 1, 30))
    for name in rng.sample(_PICTURES, rng.randint(3, 5)):
        out.append(_file("home", f"Pictures/{name}", rng))
    for proj in rng.sample(sorted(_PROJECTS), rng.randint(2, 3)):
        base = f"projects/{proj}"
        for rel, body, lo, hi in ((".git/HEAD", "ref: refs/heads/main\n", 5, 90),
                                  (".git/config", "[core]\n\trepositoryformatversion = 0\n"
                                                  "\tbare = false\n", 90, 400),
                                  (".gitignore", "node_modules/\n*.log\n.env\n", 90, 400),
                                  ("README.md", f"# {proj}\n\nSmall {proj} project. Run it and "
                                                "see.\n", 30, 400)):
            out.append(_mark(story.extra("home", f"{base}/{rel}", body, mtime=_ago(rng, lo, hi))))
        for name in _PROJECTS[proj]:
            folder = "" if name in ("package.json", "requirements.txt") else "src/"
            out.append(_file("home", f"{base}/{folder}{name}", rng, 5, 300))
        out.append(_file("home", f"{base}/logs/app.log", rng, 1, 40))
        if proj == "notes-app":
            for pkg in ("left-pad", "lodash"):
                out.append(_file("home", f"{base}/node_modules/{pkg}/index.js", rng, 60, 300))
    for name in ("site_backup_2724-11.tar.gz", "report_final_v2_OLD.docx"):
        if rng.random() < 0.7:
            out.append(_file("home", f"old_backups/{name}", rng, 300, 900))
    return out


def box(seed: int) -> List[dict]:
    """Одна-две посторонние папки рядом с файлами задачи: сами файлы — только внутри папок,
    чтобы маски по корню задачи (*.txt, *(.)) их не цепляли."""
    rng = random.Random(seed ^ SALT_BOX)
    out = []
    for folder in rng.sample(sorted(_BOX_DIRS), rng.randint(1, 2)):
        for name in _BOX_DIRS[folder]:
            out.append(_file("box", f"{folder}/{name}", rng, 30, 500))
    return out
