"""Трек «Вместо Finder»: найти, разложить, упаковать, остановить."""
import os
import re
import shlex
import shutil
import struct
import sys
import time
import zipfile
import zlib
from pathlib import Path

from termit_app import textnorm
from termit_app.tasks import kit
from termit_app.tasks.base import AnswerTask, Task, Variant, Verdict, sources, variant_index


def maze(root: Path, rng, n: int):
    """Дерево из n папок глубиной до 4; возвращает список папок (первая — корень)."""
    root.mkdir(parents=True, exist_ok=True)
    dirs = [root]
    for i in range(n):
        parent = rng.choice(dirs)
        if len(parent.relative_to(root).parts) >= 4:
            parent = root
        d = parent / f"{kit.latin(rng)}_{i}"
        d.mkdir()
        dirs.append(d)
    return dirs


def png(width: int, height: int, rgb) -> bytes:
    """Настоящий PNG одного цвета (Preview откроет его без жалоб)."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    row = b"\x00" + bytes(rgb) * width
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


def _open_log(ctx):
    """Вызовы open из журнала обёртки: (папка, где набрали, аргументы)."""
    log = ctx.box / ".termit" / "open.log"
    if not log.exists():
        return []
    out = []
    for raw in log.read_text("utf-8", errors="replace").splitlines():
        pwd, _, args = raw.partition("\t")
        out.append((Path(pwd), args.split()))
    return out


def _resolve(pwd: Path, tok: str) -> Path:
    try:
        return (pwd / tok).resolve()
    except (OSError, RuntimeError):
        return pwd / tok


class OpenGui(Task):
    id = "open_gui"
    track = "finder"
    uses_gui = True      # open — суть урока: здесь песочница по определению проницаема (А5)
    title = "Покажи глазами"
    scroll = ("open . — показать текущую папку в Finder; open DIR — папку по имени. "
              "open -a APP FILE — открыть файл в нужной программе (a — application): "
              "open -a TextEdit notes.txt. open -R FILE — показать файл в Finder выделенным "
              "(R — Reveal). Сдавать ничего не надо: игра видит, какие окна ты открыл.")
    variants = (
        Variant("Покажи эту папку в Finder, а опись inventory.txt открой в TextEdit. "
                "Всё — из терминала; сдавать ничего не надо, игра увидит окна сама.",
                wrong=("open . && open inventory.txt",),
                alternatives=("open -e inventory.txt — флаг -e (e — editor, «редактор») сразу "
                              "открывает в TextEdit, без -a",)),
        Variant("Покажи в Finder папку reports, а картинку plan.png открой именно в программе "
                "Preview. Всё — из терминала; сдавать ничего не надо, игра увидит окна сама.",
                hints=("Окна открывает open: папку — по её имени, как точку.",
                       "Программу выбирает флаг -a: open -a Preview файл",
                       "open reports && open -a Preview plan.png"),
                solution="open reports && open -a Preview plan.png",
                wrong=("open reports && open plan.png",),
                alternatives=("open reports/ — с косой чертой на конце тоже папка",)),
        Variant("Опись лежит глубоко: docs/{year}/{month}/inventory.txt. Покажи её в Finder — "
                "чтобы открылось окно её папки и опись в нём была выделена. Сам файл "
                "открывать не нужно, сдавать тоже ничего — игра увидит окно сама.",
                hints=("Показать файл в Finder, а не открыть его, — отдельный флаг open.",
                       "Флаг -R: open -R путь/к/файлу",
                       "open -R docs/{year}/{month}/inventory.txt"),
                solution="open -R docs/{year}/{month}/inventory.txt",
                wrong=("open docs/{year}/{month}/inventory.txt", "open docs/{year}/{month}"),
                alternatives=("cd docs/{year}/{month} && open -R inventory.txt — сначала дойти, "
                              "потом показать",)),
    )
    par = 25
    hints = ("Окна открывает команда open.",
             "Точка . — это текущая папка; флаг -a выбирает программу.",
             "open . && open -a TextEdit inventory.txt")
    solution = "open . && open -a TextEdit inventory.txt"
    explain = "open — мост из терминала в обычные программы: папки, файлы, ссылки."
    spell = "open . — папка в Finder; open -a Программа файл; open -R файл — показать в Finder"

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            for i in range(rng.randint(3, 6)):
                kit.write(box / "reports" / f"{kit.latin(rng)}_{i}.txt", f"{kit.word(rng)}\n")
            rgb = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
            p = box / "plan.png"
            p.write_bytes(png(rng.randint(40, 80), rng.randint(30, 60), rgb))
            kit.write(box / "plan.txt", "The plan is in the picture.\n")
            return {}
        if variant == 2:
            year = rng.randint(2722, 2726)
            months = rng.sample(range(1, 13), 3)
            for m in months:
                for i in range(rng.randint(2, 4)):
                    kit.write(box / "docs" / str(year) / f"{m:02d}" / f"{kit.latin(rng)}_{i}.txt",
                              f"{kit.word(rng)}\n")
            month = f"{months[0]:02d}"
            path = f"docs/{year}/{month}/inventory.txt"
            kit.write(box / path,
                      "Inventory:\n" + "".join(f"- {kit.word(rng)}\n" for _ in range(5)))
            return {"year": year, "month": month, "path": path}
        kit.write(box / "inventory.txt", "Inventory:\n" +
                  "".join(f"- {kit.word(rng)}\n" for _ in range(5)))
        return {}

    def check(self, ctx):
        entries = _open_log(ctx)
        if not entries:
            return Verdict(False)
        v = ctx.state.get("_variant", 0)
        if v == 2:
            target = _resolve(ctx.box, ctx.state["path"])
            shown = opened = folder = False
            for pwd, toks in entries:
                if any(_resolve(pwd, t) == target for t in toks if not t.startswith("-")):
                    if "-R" in toks:
                        shown = True
                    else:
                        opened = True
                elif any(_resolve(pwd, t) == target.parent for t in toks
                         if not t.startswith("-")):
                    folder = True
            if shown:
                return Verdict(True)
            if opened:
                return Verdict(False, "Опись открылась сама, а нужно показать её в Finder — "
                                      "это флаг -R: open -R путь")
            if folder:
                return Verdict(False, "Папка открылась, но опись в ней не выделена. Открыть "
                                      "папку и сразу выделить файл — open -R путь/к/файлу.")
            return Verdict(False)
        if v == 1:
            folder, name, app = _resolve(ctx.box, "reports"), "plan.png", "preview"
        else:
            folder, name, app = ctx.box.resolve(), "inventory.txt", "textedit"
        shown = right = default = False
        for pwd, toks in entries:
            if len(toks) == 1 and _resolve(pwd, toks[0]) == folder:
                shown = True
            if any(t.endswith(name) for t in toks):
                if ("-e" in toks and app == "textedit") or (
                        "-a" in toks and any(app in t.lower() for t in toks)):
                    right = True
                elif "-a" not in toks:
                    default = True
        if shown and right:
            return Verdict(True)
        # владелец 21.10: сделал половину (open -e) — игра молчала; говорим, что осталось
        where = "open reports" if v == 1 else "open . (точка — эта папка)"
        prog = "open -a Preview plan.png" if v == 1 else "open -a TextEdit inventory.txt"
        if right and not shown:
            return Verdict(False, f"{name} открыт где надо ✓. Осталось показать папку в Finder: "
                                  f"{where}")
        if shown and not right and not default:
            return Verdict(False, f"Папка в Finder открыта ✓. Осталось открыть {name}: {prog}")
        if default and not right:
            prog = "Preview: open -a Preview" if v == 1 else "TextEdit: open -a TextEdit (или -e)"
            return Verdict(False, f"{name} открылся в программе по умолчанию, а нужна {prog}")
        return Verdict(False)


class FindName(AnswerTask):
    id = "find_name"
    track = "finder"
    title = "Потерянный файл"
    kind_answer = "path"
    scroll = ("find DIR -name 'PATTERN' — искать файлы по имени во всех вложенных папках "
              "(DIR — откуда искать, PATTERN — маска имени); find DIR -iname 'PATTERN' — то же "
              "без учёта больших и маленьких букв (i — insensitive).\n"
              "Маску всегда бери в одинарные кавычки. Один путь — сразу в ответ: ans $(find …); "
              "несколько — выбери свой, тройной щелчок, Cmd+C, ans и Cmd+V.")
    variants = (
        Variant("Файл потерялся где-то в storage/. Имя начинается на license, но неизвестно, "
                "большими буквами или маленькими. Расширение — .dat. Где он? "
                "Ответ: ans PATH — путь, как его напечатает find.",
                wrong=("find storage -name 'license*.dat'",),
                alternatives=("ans $(find storage -iname 'license*.dat') — путь сразу в ответ",)),
        Variant("Где-то в глубине storage/ лежит единственный файл с расширением .sql — дамп "
                "базы. Как он называется, неизвестно. Где он? "
                "Ответ: ans PATH — путь, как его напечатает find.",
                hints=("Имя неизвестно, известно только окончание — нужна маска со звёздочкой.",
                       "find storage -name '*.sql' — кавычки обязательны, иначе звёздочку "
                       "раскроет сам zsh.",
                       "find storage -name '*.sql' — или сразу ans $(find storage -name '*.sql')"),
                solution="find storage -name '*.sql'",
                wrong=("find storage -name *.sql", "find storage -name '*sql*'"),
                alternatives=("find storage -iname '*.sql' — найдёт и .SQL большими",)),
        Variant("В storage/ раскиданы файлы config.yaml — по одному на каждую среду: dev, test, "
                "preprod и prod. Нужен тот, что лежит в папке prod. "
                "Ответ: ans PATH — путь, как его напечатает find.",
                hints=("Имя известно точно — найди сначала все config.yaml.",
                       "find storage -name config.yaml покажет все пути. Нужен тот, где папка "
                       "называется ровно prod, а не preprod.",
                       "find storage -name config.yaml — путь с /prod/ скопируй тройным щелчком "
                       "и сдай: ans PATH"),
                solution="find storage -name config.yaml, путь с /prod/",
                solution_script="find storage -name config.yaml | grep /prod/",
                wrong=("find storage -name config.yaml | grep prod",
                       "find storage -name config.yaml"),
                alternatives=("find storage -path '*/prod/config.yaml' — -path сверяет весь "
                              "путь, а не только имя",)),
    )
    par = 40
    hints = ("По имени файлы ищет find.",
             "Без учёта регистра — -iname; маску бери в кавычки.",
             "find storage -iname 'license*.dat'")
    solution = "find storage -iname 'license*.dat'"
    explain = ("find прочёсывает все вложенные папки; -iname плевать на большие и маленькие "
               "буквы; кавычки прячут маску от zsh.")
    spell = "find DIR -iname 'PATTERN' — найти файл по имени где угодно внутри"

    ENVS = ("dev", "test", "preprod", "prod")
    trap_messages = {
        "list": "Это список лицензий, а нужен файл .dat — и имя может начинаться с большой "
                "буквы: -iname не смотрит на регистр.",
        "notdump": "Это не дамп: расширение должно быть ровно .sql, в самом конце имени.",
        "preprod": "Это preprod, а нужна папка, которая называется ровно prod.",
        "env": "Это config.yaml другой среды, а нужен тот, что лежит в папке prod.",
    }

    def setup_variant(self, box, rng, variant):
        dirs = maze(box / "storage", rng, rng.randint(40, 60))
        for i in range(rng.randint(150, 220)):
            kit.write(rng.choice(dirs) / f"record_{i}.txt", f"{kit.word(rng)}\n")
        if variant == 1:
            decoys = [kit.write(rng.choice(dirs) / name, "not a dump\n") for name in
                      ("sql_notes.txt", f"{kit.latin(rng)}.sql.gz", "old_sql.bak")]
            target = kit.write(rng.choice(dirs[1:]) / f"{kit.latin(rng)}_dump.sql",
                               "-- database dump\n")
            return {"answer": str(target.relative_to(box)),
                    "traps": [["notdump", str(d.relative_to(box))] for d in decoys],
                    "sources": sources(box, target.relative_to(box))}
        if variant == 2:
            answer, traps = "", []
            for env, d in zip(self.ENVS, rng.sample(dirs[1:], len(self.ENVS))):
                p = kit.write(d / env / "config.yaml", f"env: {env}\n")
                if env == "prod":
                    answer = str(p.relative_to(box))
                else:
                    traps.append(["preprod" if env == "preprod" else "env",
                                  str(p.relative_to(box))])
            kit.write(rng.choice(dirs) / "config.yaml.example", "env: ?\n")
            return {"answer": answer, "traps": traps, "sources": sources(box, answer)}
        kit.write(box / "storage" / "lists" / "license_list.txt", "List of licenses.\n")
        # не маленькими: иначе find -name 'license*' находил бы файл, а ловушка — нет
        base = rng.choice(["License", "LICENSE"])
        target = kit.write(rng.choice(dirs[1:]) / f"{base}_{kit.latin(rng)}.dat", "License!\n")
        return {"answer": str(target.relative_to(box)),
                "traps": [["list", "storage/lists/license_list.txt"]],
                "sources": sources(box, target.relative_to(box))}


class GrepR(AnswerTask):
    accepts_name = True        # имя файла засчитывается и без пути
    id = "grep_r"
    track = "finder"
    title = "Иголка в архиве"
    kind_answer = "path"
    scroll = ("grep -rl 'PATTERN' DIR — пути файлов в папке DIR и глубже, где есть текст "
              "PATTERN (r — recursive, вглубь; l — list). Текст — в одинарных кавычках, буквы — "
              "как в задании. Ответ сразу: ans $(grep -rl 'PATTERN' DIR)\n"
              "… | wc -l — сколько строк вывода, то есть файлов (l — lines).")
    variants = (
        Variant("В каком из файлов папки archive/ записан пароль от сейфа? Известна только "
                "фраза целиком: «safe password» (пароль от сейфа). Ответ: ans PATH — путь к "
                "файлу.",
                wrong=("grep -rl 'password' archive",),
                alternatives=("grep -rl 'safe pass' archive — хватит и куска фразы, если он "
                              "редкий",)),
        Variant("В каком файле архива archive/ упомянут заказ «order #{n}» — "
                "ровно такой фразой? Ответ: ans PATH — путь к файлу.",
                hints=("Искать внутри файлов умеет grep: -r — во всех подпапках, -l — только "
                       "имена.",
                       "Число {n} есть и в другом файле — ищи фразу целиком, в кавычках. # — это "
                       "Shift+3 на английской раскладке. Или grep -r '{n}' archive без -l: "
                       "увидишь обе строки и выберешь глазами.",
                       "grep -rl 'order #{n}' archive"),
                solution="grep -rl 'order #{n}' archive",
                wrong=("grep -rl '{n}' archive",),
                alternatives=("grep -rl '#{n}' archive — хватит и номера со значком",)),
        Variant("Сколько файлов в archive/ упоминают слово «{word}» (в файлах оно "
                "написано так же, маленькими)? Ответ — число: ans NUMBER. Посчитать строки "
                "поможет | wc -l",
                hints=("Список файлов, где есть слово, даёт grep -rl.",
                       "Строки считает wc -l — поставь его после |. Без -l grep печатает "
                       "каждую найденную строку, а не файл: в одном файле их бывает две.",
                       "grep -rl '{word}' archive | wc -l — или ans $(grep -rl '{word}' archive "
                       "| wc -l)"),
                solution="grep -rl '{word}' archive | wc -l",
                wrong=("grep -r '{word}' archive | wc -l",),
                alternatives=("grep -rl '{word}' archive — и посчитать строки глазами, их "
                              "немного",)),
    )
    par = 40
    hints = ("Искать внутри файлов умеет grep.",
             "Во всех подпапках сразу — флаг -r, только имена файлов — -l.",
             "grep -rl 'safe password' archive")
    solution = "grep -rl 'safe password' archive"
    explain = "grep -r ищет по содержимому всех файлов — Spotlight в одну строку."
    spell = "grep -rl 'PATTERN' DIR — в каких файлах встречается текст"

    WORDS_C = ("raid", "smuggling", "cipher", "alarm")
    trap_messages = {
        "content": "Это то, что записано в файле, а нужен путь к самому файлу: grep -rl "
                   "печатает пути.",
        "decoy": "В этом файле пароль сменён — это не тот. Ищи фразу целиком, в кавычках.",
        "invoice": "Тут номер есть, но без «order #» — ищи фразу целиком.",
        "lines": "Посчитаны строки, а не файлы: в одном файле слово встречается дважды. -l "
                 "печатает каждый файл один раз.",
    }

    def answer_kind(self, state):
        return "number" if state.get("_variant") == 2 else "path"

    def _notes(self, box, rng):
        dirs = maze(box / "archive", rng, rng.randint(8, 14))
        files = []
        for i in range(rng.randint(30, 60)):
            lines = [f"{kit.word(rng)} {kit.word(rng)}" for _ in range(rng.randint(3, 12))]
            files.append((rng.choice(dirs) / f"note_{i}.txt", lines))
        return files

    @staticmethod
    def _save(files):
        for path, lines in files:
            kit.write(path, "\n".join(lines) + "\n")

    def setup_variant(self, box, rng, variant):
        files = self._notes(box, rng)
        if variant == 1:
            n = rng.randint(1000, 9999)
            others = rng.sample([x for x in range(1000, 10000) if x != n], 12)
            for k in others:
                lines = rng.choice(files)[1]
                lines.insert(rng.randrange(len(lines) + 1), f"order #{k}: {kit.word(rng)}")
            target, decoy = rng.sample(files, 2)
            target[1].append(f"order #{n}: {kit.word(rng)}, shipped")
            decoy[1].append(f"invoice {n}, no order")
            self._save(files)
            return {"n": n, "answer": str(target[0].relative_to(box)),
                    "traps": [["invoice", str(decoy[0].relative_to(box))]],
                    "sources": sources(box, target[0].relative_to(box))}
        if variant == 2:
            word = rng.choice(self.WORDS_C)
            hits = rng.sample(files, rng.randint(3, 5))
            for k, (_, lines) in enumerate(hits):
                for _ in range(2 if k == 0 else 1):     # в первом — дважды: строк больше файлов
                    lines.insert(rng.randrange(len(lines) + 1), f"{kit.word(rng)} — {word}")
            self._save(files)
            return {"word": word, "answer": len(hits), "traps": [["lines", len(hits) + 1]]}
        decoys = []
        for path, lines in files:
            if rng.random() < 0.3:
                lines.insert(rng.randrange(len(lines) + 1), "safe is empty, password changed")
                decoys.append(path)
        target = rng.choice(files)
        if not [d for d in decoys if d != target[0]]:     # ловушка «пароль» есть всегда
            other = rng.choice([f for f in files if f is not target])
            other[1].append("safe is empty, password changed")
        secret = kit.word(rng)
        target[1].append(f"safe password: {secret}")
        self._save(files)
        traps = [["content", secret]] + [["decoy", str(d.relative_to(box))]
                                         for d in decoys if d != target[0]]
        return {"answer": str(target[0].relative_to(box)), "traps": traps,
                "sources": sources(box, target[0].relative_to(box))}

    def matches(self, given, ctx):
        if ctx.state.get("_variant") == 2:
            return textnorm.same_number(given, ctx.state["answer"])
        return (super().matches(given, ctx) or
                textnorm.same_text(given, Path(self.expected(ctx.state)).name))


class DuHeavy(AnswerTask):
    accepts_name = True        # имя файла засчитывается и без пути
    id = "du_heavy"
    track = "finder"
    title = "Кто сколько весит"
    kind_answer = "path"
    scroll = ("du -sh * — сколько весит каждая папка и файл здесь (s — summarize, итогом; h — "
              "human-readable, в K, M, G). | — труба: отдать напечатанное следующей команде. "
              "sort -h — по весу, самое тяжёлое последним: du -sh * | sort -h\n"
              "Имя из последней строки — двойным щелчком, Cmd+C, ans NAME. Второе место — "
              "предпоследняя строка: du -sh * | sort -h | tail -2 | head -1 (tail -2 — две "
              "последние строки, head -1 — первая из них).")
    variants = (
        Variant("Диск трещит по швам. Какая из папок здесь весит больше всех? "
                "Ответ: ans NAME — имя папки.",
                wrong=("ls -S | head -1",),
                alternatives=("du -sh * | sort -h | tail -1 — сразу одна строка",)),
        Variant("В media/ лежат одни файлы. Какой из них весит больше всех? "
                "Ответ: ans NAME — имя файла (можно и с media/ впереди).",
                hints=("Размер файлов тоже показывает du: du -sh media/*",
                       "Отсортируй с -h: | sort -h. Без -h sort сравнивает буквы, и 900K у него "
                       "окажется «больше», чем 2M.",
                       "du -sh media/* | sort -h — самый тяжёлый внизу; сдай ans NAME"),
                solution="du -sh media/* | sort -h",
                solution_script="du -sk media/* | sort -n | tail -1 | cut -f2",
                wrong=("du -sh media/* | sort | tail -1 | cut -f2",),
                alternatives=("ls -lS media — у файлов размер видит и ls: -S сортирует по "
                              "размеру, тяжёлые сверху",)),
        Variant("Самую тяжёлую папку здесь уже чистят. Какая папка вторая по весу — тяжелее "
                "всех, кроме одной? Ответ: ans NAME — имя папки. Две последние строки даёт tail -2, "
                "а первую из них — head -1",
                hints=("Размеры папок — du -sh *, по порядку — | sort -h.",
                       "Самая тяжёлая — последняя строка, вторая — над ней: | tail -2 | head -1",
                       "du -sh * | sort -h | tail -2 | head -1"),
                solution="du -sh * | sort -h | tail -2 | head -1",
                solution_script="du -sk * | sort -n | tail -2 | head -1 | cut -f2",
                wrong=("du -sk * | sort -n | tail -1 | cut -f2",),
                alternatives=("du -sh * | sort -rh | head -2 — -r переворачивает порядок: "
                              "тяжёлые сверху, нужна вторая строка",)),
    )
    par = 35
    hints = ("Размер папок показывает du.",
             "du -sh * — по каждой; отсортировать — | sort -h",
             "du -sh * | sort -h — самая тяжёлая внизу")
    solution = "du -sh * | sort -h"
    solution_script = "du -sk * | sort -n | tail -1 | cut -f2"
    explain = "du считает место на диске, sort -h понимает K/M/G — вместе это «что съело диск»."
    spell = "du -sh * | sort -h — что сколько весит, по возрастанию"
    trap_messages = {
        "crowd": "Тут куча мелких файлов: записей больше всех, а весу мало. ls -S (по размеру) меряет "
                 "саму запись папки, а не её содержимое — вес считает du.",
        "text": "Без -h sort сравнивает как текст: 9xxK у него «больше» 2M. Нужен sort -h.",
        "first": "Это самая тяжёлая, а нужна вторая по весу — строка над ней.",
    }

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            media = box / "media"
            names = [f"{kit.latin(rng)}_{i}.{rng.choice(['mov', 'mp4', 'jpg', 'wav'])}"
                     for i in range(rng.randint(6, 9))]
            heavy, trap = rng.sample(names, 2)
            for n in names:
                if n == heavy:
                    size = rng.randint(1_300_000, 2_500_000)
                elif n == trap:     # «9xxK» — без -h sort поставит его после «2.1M»
                    size = rng.randint(880_000, 990_000)
                else:
                    size = rng.randint(20_000, 700_000)
                kit.write_random(media / n, size, rng)
            return {"answer": f"media/{heavy}",
                    "traps": [["text", f"media/{trap}"], ["text", trap]]}
        names = rng.sample(kit.LATIN, rng.randint(6, 9))
        if variant == 2:
            first, second = rng.sample(names, 2)
            for n in names:
                if n == first:
                    sizes = [rng.randint(4_200_000, 5_000_000)]
                elif n == second:
                    sizes = [rng.randint(500_000, 800_000) for _ in range(4)]
                else:
                    sizes = [rng.randint(10_000, 250_000) for _ in range(rng.randint(1, 4))]
                for i, s in enumerate(sizes):
                    kit.write_random(box / n / f"file_{i}.bin", s, rng)
            return {"answer": second, "traps": [["first", first]]}
        heavy = rng.choice(names)
        # толпа мелочи: больше всех записей в каталоге (ls -S), но лёгкая
        crowd = rng.choice([n for n in names if n != heavy])
        for n in names:
            d = box / n
            d.mkdir()
            if n == heavy and rng.random() < 0.5:
                kit.write_random(d / "video.bin", rng.randint(3_000_000, 4_000_000), rng)
            elif n == heavy:
                for i in range(300):
                    kit.write_random(d / f"part_{i}.bin", 12_000, rng)
            elif n == crowd:
                for i in range(400):
                    kit.write(d / f"t_{i}.txt", "x")
            else:
                for i in range(rng.randint(1, 5)):
                    kit.write_random(d / f"file_{i}.bin", rng.randint(10_000, 250_000), rng)
        return {"answer": heavy, "traps": [["crowd", crowd]]}

    def matches(self, given, ctx):
        return (super().matches(given, ctx) or
                textnorm.same_text(given, Path(self.expected(ctx.state)).name))


class LsNewest(AnswerTask):
    id = "ls_newest"
    track = "finder"
    title = "По времени изменения"
    scroll = ("ls -t — свежие файлы сверху (t — time, по времени); ls -tr — наоборот, старые "
              "сверху (r — reverse); ls -t *.pdf — только PDF. | head -1 — оставить одну "
              "первую строку.\n"
              "Сразу в ответ: ans $(ls -t | head -1)")
    variants = (
        Variant("Какой файл здесь появился последним? Назови его: ans NAME — имя файла.",
                wrong=("ls | head -1",),
                alternatives=("ls -lt | head -3 — с датами, чтобы видеть разницу",)),
        Variant("Какой файл здесь самый старый — дольше всех не менялся? Назови его: ans NAME — имя файла. "
                "Флаг -r у ls переворачивает порядок",
                hints=("ls -t сортирует по времени: свежие сверху, старые — внизу.",
                       "-r переворачивает порядок: ls -tr — старые сверху.",
                       "ls -tr | head -1 — или сразу ans $(ls -tr | head -1)"),
                solution="ls -tr | head -1",
                wrong=("ls -t | head -1",),
                alternatives=("ls -t | tail -1 — последняя строка списка «свежие сверху»",)),
        Variant("Какой PDF здесь появился последним? Остальные файлы не в счёт. "
                "Назови его: ans NAME — имя файла.",
                hints=("ls можно дать маску: ls *.pdf — только PDF.",
                       "Маска и сортировка вместе: ls -t *.pdf — свежие PDF сверху.",
                       "ls -t *.pdf | head -1 — или сразу ans $(ls -t *.pdf | head -1)"),
                solution="ls -t *.pdf | head -1",
                wrong=("ls -t | head -1",),
                alternatives=("ls -lt *.pdf — с датами, чтобы видеть разницу",)),
    )
    par = 20
    hints = ("ls умеет сортировать по времени изменения.",
             "ls -t — свежие сверху.",
             "ls -t | head -1 — или сразу ans $(ls -t | head -1)")
    solution = "ls -t | head -1"
    explain = "-t сортирует по времени изменения — так находят «что я только что скачал»."
    spell = "ls -t — свежие сверху; ls -t | head -3 — три последних"
    trap_messages = {
        "abc": "Это первый по алфавиту: обычный ls сортирует по имени. По времени — ls -t.",
        "newest": "Это самый свежий, а нужен самый старый: -r переворачивает порядок.",
        "notpdf": "Это не PDF: дай ls маску *.pdf — остальные файлы не в счёт.",
    }

    def setup_variant(self, box, rng, variant):
        now = time.time()
        names = [f"{kit.latin(rng)}_{i}.{rng.choice(['txt', 'pdf', 'csv', 'jpg'])}"
                 for i in range(rng.randint(20, 30))]
        if variant == 2:        # PDF не меньше трёх, а самый свежий файл — не PDF
            for i in rng.sample(range(len(names)), 3):
                names[i] = names[i].rsplit(".", 1)[0] + ".pdf"
        ages = rng.sample(range(3600, 60 * 86400, 3600), len(names))
        order = sorted(range(len(names)), key=lambda i: ages[i])     # от свежего к старому
        if variant == 0:
            # по алфавиту первым не должен оказаться самый свежий (ловушка ls | head -1)
            first = min(names)[0]
            if names[order[0]][0] == first:
                j = next((i for i in order if names[i][0] != first), None)
                if j is not None:
                    ages[order[0]], ages[j] = ages[j], ages[order[0]]
        if variant == 2:
            newest = min(range(len(names)), key=lambda i: ages[i])
            if names[newest].endswith(".pdf"):
                j = min((i for i in range(len(names)) if not names[i].endswith(".pdf")),
                        key=lambda i: ages[i])
                ages[newest], ages[j] = ages[j], ages[newest]
        for n, age in zip(names, ages):
            p = kit.write(box / n, "data\n")
            os.utime(p, (now - age, now - age))
        newest = names[ages.index(min(ages))]
        if variant == 1:
            return {"answer": names[ages.index(max(ages))], "traps": [["newest", newest]]}
        if variant == 2:
            pdfs = [i for i in range(len(names)) if names[i].endswith(".pdf")]
            return {"answer": names[min(pdfs, key=lambda i: ages[i])],
                    "traps": [["notpdf", newest]]}
        return {"answer": newest, "traps": [["abc", min(names)]]}


class RecentMove(Task):
    id = "recent_move"
    track = "finder"
    title = "Разбор по датам"
    scroll = ("В zsh у маски бывают уточнения в скобках: ls *(.m-3) — обычные файлы, изменённые "
              "меньше 3 дней назад (m — от modified, «изменён»). Плюс вместо минуса — старше: "
              "*(.m+30); h после m — в часах: *(.mh-5).")
    variants = (
        Variant("Всё, что появилось за последние 3 дня, — в fresh/ (папка уже есть). Старое не "
                "трогать. Сдавать ничего не надо — игра посмотрит, что где лежит.",
                wrong=("mv * fresh/",),
                alternatives=("find . -maxdepth 1 -type f -mtime -3 -exec mv {{}} fresh/ \\; "
                              "— то же без zsh",)),
        Variant("Всё, что не менялось больше 30 дней, — в archive/ (папка уже есть). Свежее "
                "не трогать. В скобках маски минус значит «моложе», а плюс — «старше». Сдавать "
                "ничего не надо — игра посмотрит, что где лежит.",
                hints=("Отбор по дате — уточнение маски в скобках, как *(.m-3).",
                       "Плюс вместо минуса — «старше»: *(.m+30). Проверь: ls -l *(.m+30)",
                       "mv *(.m+30) archive/"),
                solution="mv *(.m+30) archive/",
                solution_script="mv *(.m+30) archive/",
                wrong=("mv *(.m-30) archive/",),
                alternatives=("find . -maxdepth 1 -type f -mtime +30 -exec mv {{}} archive/ \\; "
                              "— то же без zsh",)),
        Variant("Всё, что изменилось за последние 24 часа, — в fresh/ (папка уже есть). "
                "Остальное не трогать. Буква h после m считает в часах: *(.mh-5) — моложе пяти "
                "часов, а тебе нужно своё число. Сдавать ничего не надо — игра посмотрит, что "
                "где лежит.",
                hints=("Нужны файлы по времени изменения — и считать в часах, а не в днях.",
                       "*(.mh-24) — моложе 24 часов. Проверь: ls -l *(.mh-24)",
                       "mv *(.mh-24) fresh/"),
                solution="mv *(.mh-24) fresh/",
                solution_script="mv *(.mh-24) fresh/",
                wrong=("mv *(.m-24) fresh/",),
                alternatives=("mv *(.m-1) fresh/ — «моложе одного дня» даёт то же самое",)),
    )
    par = 60
    hints = ("Нужны файлы по дате изменения, а не по имени.",
             "В zsh: *(.m-3) — файлы моложе 3 дней. Проверь: ls -l *(.m-3)",
             "mv *(.m-3) fresh/")
    solution = "mv *(.m-3) fresh/"       # путь через find — в «можно и так»
    solution_script = "mv *(.m-3) fresh/"
    explain = "Отбор по дате — частая уборка: «всё за неделю — в архив». В bash — через find."
    spell = "*(.m-3) — файлы моложе 3 дней (zsh); find -mtime -3 — то же везде"

    # вариант → (папка, возраст переносимых и остающихся в часах)
    RANGES = {1: ("archive", (33 * 24, 120 * 24), (2, 27 * 24)),
              2: ("fresh", (0.5, 20), (30, 10 * 24))}

    def setup_variant(self, box, rng, variant):
        now = time.time()
        if variant in self.RANGES:
            dest, (m_lo, m_hi), (s_lo, s_hi) = self.RANGES[variant]
            move, stay = [], []
            for i in range(rng.randint(25, 40)):
                go = i < 3 or (i >= 6 and rng.random() < 0.4)
                age = rng.uniform(m_lo, m_hi) if go else rng.uniform(s_lo, s_hi)
                if variant == 2 and i in (3, 4):        # день-полтора: m-2 их захватит
                    age = rng.uniform(30, 44)
                n = f"{kit.latin(rng)}_{i}.txt"
                p = kit.write(box / n, f"{n}\n")
                os.utime(p, (now - age * 3600, now - age * 3600))
                (move if go else stay).append(n)
            (box / dest).mkdir()
            return {"dest": dest, "move": move, "stay": stay}
        fresh, old = [], []
        for i in range(rng.randint(25, 40)):
            young = i < 2 or (i >= 4 and rng.random() < 0.4)
            age = rng.choice([0.1, 0.5, 1, 1.5, 2]) if young else rng.uniform(4, 30)
            if i in (2, 3):
                age = rng.uniform(4, 30)
            n = f"{kit.latin(rng)}_{i}.txt"
            p = kit.write(box / n, f"{n}\n")
            os.utime(p, (now - age * 86400, now - age * 86400))
            (fresh if age <= 2 else old).append(n)
        (box / "fresh").mkdir()
        return {"fresh": fresh, "old": old}

    def check(self, ctx):
        s = ctx.state
        dest = s.get("dest", "fresh")             # старый task.json варианта A — без dest
        move, stay = s.get("move", s.get("fresh", [])), s.get("stay", s.get("old", []))
        d = ctx.box / dest
        inside = {p.name for p in d.iterdir()} if d.is_dir() else set()
        if inside == set(move) and all((ctx.box / n).exists() for n in stay):
            return Verdict(True)
        lost = [n for n in move + stay if not (ctx.box / n).exists() and n not in inside]
        if lost:
            return Verdict(False, f"Стёрто то, что нужно было разложить: {kit.names_line(lost)}. "
                           + kit.RESET_TAIL)
        extra = sorted(inside & set(stay))
        if extra:
            names = kit.names_line(extra)
            end = "" if names.endswith("…") else "."
            return Verdict(False, f"В {dest}/ попало то, что надо было оставить: {names}{end} "
                                  "Сначала проверь отбор: ls -l с той же маской — потом mv. "
                                  + kit.RESET_TAIL)
        return Verdict(False)


def _lost_files(box, shas) -> Verdict:
    """Не решено; если чьё-то содержимое пропало отовсюду (стёрто, затёрто при mv поверх) —
    это тупик, и об этом надо сказать (Н3.1 приёмки-1)."""
    if kit.lost(box, shas):
        return Verdict(False, "Часть файлов пропала: стёрта или затёрта другим при "
                              "переименовании. " + kit.RESET_TAIL)
    return Verdict(False)


class BatchRename(Task):
    """Первый цикл игры. FB12 (N10, N17): первая встреча — приставка "2725_$f" (один приём:
    цикл); отрезать хвост ${f%.ext} — повторы 1 и 2."""
    id = "batch_rename"
    track = "finder"
    title = "Пакетное переименование"
    scroll = ('for f in *.txt; do COMMAND; done — COMMAND между do и done повторится для '
              'каждого файла по маске, $f — имя очередного. Кавычки "$f" спасают имена с '
              'пробелами. "${f%.JPEG}" — имя без хвоста .JPEG.\n'
              'Проверь без риска: поставь echo перед mv — цикл только напечатает команды; '
              'потом убери echo и запусти один раз.')
    variants = (
        Variant("Ко всем .txt здесь допиши спереди 2725_: «report march.txt» → «2725_report "
                "march.txt». Другие файлы не трогай. Новое имя склеивается прямо в кавычках: "
                "\"2725_$f\".",
                wrong=('for f in *; do mv "$f" "2725_$f"; done',),
                alternatives=('for f in *.txt; do cp "$f" "2725_$f" && rm "$f"; done — копия под '
                              'новым именем, потом старый стереть',)),
        Variant("Снимки пришли как «Photo 12.JPEG». Переименуй все в .jpg — имена "
                "сохрани, пробелы тоже. Скриншоты .png не трогай.",
                wrong=("mv *.JPEG *.jpg",),
                alternatives=('for f in *.JPEG; do cp "$f" "${{f%.JPEG}}.jpg" && rm "$f"; done — '
                              'копия под новым именем, потом старый стереть',),
                hints=("Одной командой mv много файлов не переименовать — нужен цикл for.",
                       "Внутри цикла: mv \"$f\" \"${{f%.JPEG}}.jpg\" — отрезать хвост и "
                       "приклеить новый.",
                       "for f in *.JPEG; do mv \"$f\" \"${{f%.JPEG}}.jpg\"; done"),
                solution='for f in *.JPEG; do mv "$f" "${{f%.JPEG}}.jpg"; done',
                explain="Цикл for и отрезанный хвост ${f%.ext} — и сотня файлов переименована "
                        "без всяких программ."),
        Variant("Копии пришли с лишним хвостом: «report.txt.bak». Убери у всех хвост .bak — "
                "должно стать «report.txt». Расширение перед .bak у всех разное, остальные "
                "файлы не трогай.",
                hints=("Цикл for по *.bak — по одному файлу за раз.",
                       "Отрезать хвост — ${{f%.bak}}: mv \"$f\" \"${{f%.bak}}\"",
                       "for f in *.bak; do mv \"$f\" \"${{f%.bak}}\"; done"),
                solution='for f in *.bak; do mv "$f" "${{f%.bak}}"; done',
                wrong=('for f in *.bak; do mv "$f" "${{f%.bak}}.txt"; done',),
                alternatives=('for f in *.bak; do cp "$f" "${{f%.bak}}" && rm "$f"; done — копия '
                              'под новым именем, потом старый стереть',)),
    )
    par = 75
    hints = ("Много файлов — цикл for по *.txt, как в карточке.",
             "Внутри цикла: mv \"$f\" \"2725_$f\" — приставка просто пишется перед $f.",
             "for f in *.txt; do mv \"$f\" \"2725_$f\"; done")
    solution = 'for f in *.txt; do mv "$f" "2725_$f"; done'
    explain = ("Цикл for повторяет mv для каждого файла по маске, $f — имя текущего; кавычки "
               "\"2725_$f\" склеивают приставку с именем и берегут пробелы.")
    spell = 'for f in *.JPEG; do mv "$f" "${f%.JPEG}.jpg"; done — переименовать все разом'

    def setup_variant(self, box, rng, variant):
        if variant == 0:
            stems = rng.sample(["report march", "plan", "todo list", "results", "notes",
                                "contract 7", "estimate"], rng.randint(4, 6))
            want, keep, gone = {}, {}, []
            for st in stems:
                p = kit.write_random(box / f"{st}.txt", rng.randint(200, 900), rng)
                want[f"2725_{st}.txt"] = kit.sha(p)
                gone.append(p.name)
            for name in ("photo 1.jpg", "list.md", "report.csv"):
                p = kit.write_random(box / name, rng.randint(200, 900), rng)
                keep[name] = kit.sha(p)
            return {"want": want, "keep": keep, "gone": gone}
        if variant == 2:
            stems = rng.sample(["report", "table", "photo 3", "contract", "estimate", "song"],
                               rng.randint(4, 5))
            exts = ["txt", "csv", "jpg", "docx", "mp3"]
            want, keep, gone = {}, {}, []
            for st in stems:
                name = f"{st}.{rng.choice(exts)}"
                p = kit.write_random(box / f"{name}.bak", rng.randint(200, 900), rng)
                want[name] = kit.sha(p)
                gone.append(p.name)
            for name in ("plan.bak.txt", "note.txt"):
                p = kit.write_random(box / name, rng.randint(200, 900), rng)
                keep[name] = kit.sha(p)
            return {"want": want, "keep": keep, "gone": gone}
        want = {}
        for n in rng.sample(range(1, 400), rng.randint(10, 20)):
            p = kit.write_random(box / f"Photo {n}.JPEG", rng.randint(1000, 5000), rng)
            want[f"Photo {n}.jpg"] = kit.sha(p)
        png = {}
        for i in range(2):
            p = kit.write_random(box / f"Screen {i}.png", 2000, rng)
            png[p.name] = kit.sha(p)
        return {"want": want, "png": png}

    def check(self, ctx):
        b, s = ctx.box, ctx.state
        gone = s.get("gone")
        # снимки .JPEG (вариант 1, старый task.json): не осталось ни одного .JPEG
        if gone is None:
            files = {**s["want"], **s.get("png", {})}
            if any(p.name.endswith(".JPEG") for p in b.iterdir()):
                return _lost_files(b, files.values())
        else:
            if any((b / n).exists() for n in gone):
                return _lost_files(b, {**s["want"], **s["keep"]}.values())
            files = {**s["want"], **s["keep"]}
        if all((b / n).is_file() and kit.sha(b / n) == h for n, h in files.items()):
            return Verdict(True)
        lost = _lost_files(b, files.values())
        if lost.message:
            return lost
        keep = {**s.get("keep", {}), **s.get("png", {})}
        renamed = sorted(n for n, h in keep.items()
                         if not ((b / n).is_file() and kit.sha(b / n) == h))
        if renamed:
            return Verdict(False, f"Переименовано лишнее: {renamed[0]} должен был остаться как "
                                  "есть. Цикл бери только по нужной маске. " + kit.RESET_TAIL)
        missing = sorted(n for n, h in s["want"].items()
                         if not ((b / n).is_file() and kit.sha(b / n) == h))
        return Verdict(False, f"Имена пока не те: нет, например, «{missing[0]}». Сравни с ls — "
                              "что лишнее или чего не хватает в новом имени. " + kit.RESET_TAIL)


class ZipPack(Task):
    id = "zip_pack"
    track = "finder"
    title = "Упаковать в zip"
    scroll = ("zip -r NAME.zip DIR — упаковать папку целиком (r — recursive); zip -r NAME.zip "
              "DIR -x '*.tmp' — exclude, без файлов по маске; масок после -x можно несколько. "
              "unzip -l NAME.zip — list: посмотреть, что внутри.\n"
              "Маску после -x — в одинарные кавычки. Ошибся — удали архив (rm NAME.zip) и упакуй "
              "заново: zip дописывает в старый архив.")
    variants = (
        Variant("Упакуй report/ в report.zip. Архив — здесь, где стоишь; мусор Finder .DS_Store "
                "(он есть и во вложенных папках) в архив не класть.",
                wrong=("zip report.zip report",),
                alternatives=("unzip -l report.zip — проверить посылку перед отправкой",)),
        Variant("Упакуй project/ в project.zip (здесь, где стоишь) без временных файлов *.tmp и "
                "без папки cache/ со всем, что в ней. Папка в -x исключается маской с путём: 'project/cache/*'.",
                hints=("Как всегда: zip -r для папки, а лишнее — после -x.",
                       "После -x можно перечислить несколько масок подряд, каждую в кавычках.",
                       "zip -r project.zip project -x '*.tmp' 'project/cache/*'"),
                solution="zip -r project.zip project -x '*.tmp' 'project/cache/*'",
                wrong=("zip -r project.zip project -x '*.tmp'",
                       "zip -r project.zip project -x '*.tmp' 'project/cache'"),
                alternatives=("zip -r project.zip project -x '*.tmp' -x '*/cache/*' — -x можно "
                              "и повторить",)),
        Variant("Собери в pdf.zip — здесь, рядом с docs/ — только PDF-файлы из папки docs/, "
                "больше ничего. Папку целиком паковать не нужно: zip принимает и маску файлов.",
                hints=("zip NAME.zip FILE… — файлы можно перечислить маской, без -r.",
                       "Маска docs/*.pdf — все PDF в папке docs.",
                       "zip pdf.zip docs/*.pdf"),
                solution="zip pdf.zip docs/*.pdf",
                wrong=("zip -r pdf.zip docs",),
                alternatives=("zip -r pdf.zip docs -i '*.pdf' — папкой, но только PDF "
                              "(-i — «включить»)",)),
    )
    par = 45
    hints = ("Упаковывает zip, папку целиком — с флагом -r.",
             "Исключить файлы — флаг -x и маска в кавычках.",
             "zip -r report.zip report -x '*.DS_Store'")
    solution = "zip -r report.zip report -x '*.DS_Store'"
    explain = "-r — вместе с подпапками, -x — без мусора. Проверить посылку — unzip -l."
    spell = "zip -r NAME.zip DIR -x '*.DS_Store' — упаковать без мусора"

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            files = []
            for i in range(rng.randint(6, 10)):
                sub = rng.choice(["", "src", "src/lib", "docs"])
                p = kit.write(box / "project" / sub / f"{kit.latin(rng)}_{i}.txt",
                              f"{rng.random()}\n")
                files.append(str(p.relative_to(box)))
            for i, sub in enumerate(["", "src", "docs"]):
                kit.write(box / "project" / sub / f"~black_{i}.tmp", "temporary\n")
            for i in range(rng.randint(3, 5)):
                kit.write(box / "project" / "cache" / f"{kit.latin(rng)}_{i}.dat", "cache\n")
            kit.write(box / "project" / "cache" / "old.tmp", "temporary\n")
            return {"zip": "project.zip", "files": sorted(files)}
        if variant == 2:
            pdfs = []
            for i in range(rng.randint(3, 6)):
                name = f"{kit.latin(rng)}_{i}.pdf"
                kit.write(box / "docs" / name, "%PDF-1.4 placeholder\n")
                pdfs.append(name)
            for i in range(rng.randint(3, 6)):
                ext = rng.choice(["docx", "txt", "jpg", "xlsx"])
                kit.write(box / "docs" / f"{kit.latin(rng)}_{10 + i}.{ext}", "not a pdf\n")
            return {"zip": "pdf.zip", "pdfs": sorted(pdfs)}
        files = []
        for i in range(rng.randint(5, 10)):
            sub = rng.choice(["", "part1", "part2/img"])
            p = kit.write(box / "report" / sub / f"{kit.latin(rng)}_{i}.txt", f"{rng.random()}\n")
            files.append(str(p.relative_to(box)))
        for sub in ("", "part1", "part2"):
            kit.write(box / "report" / sub / ".DS_Store", "Finder junk")
        return {"files": sorted(files)}

    def check(self, ctx):
        s = ctx.state
        name = s.get("zip", "report.zip")
        z = ctx.box / name
        src = s.get("files") or [f"docs/{n}" for n in s.get("pdfs", ())]
        lost = [Path(r).name for r in src if not (ctx.box / r).is_file()]
        if lost:
            return Verdict(False, f"Стёрто то, что надо упаковать: {kit.names_line(lost)}. "
                           + kit.RESET_TAIL)
        if not z.is_file():
            return Verdict(False)
        try:
            with zipfile.ZipFile(z) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
        except zipfile.BadZipFile:
            return Verdict(False, f"{name} повреждён — удали его и упакуй заново.")
        redo = f"удали архив (rm {name}) и упакуй заново"
        if "pdfs" in s:
            got = sorted(Path(n).name for n in names)
            extra = sorted(n for n in got if not n.endswith(".pdf"))
            if extra:
                return Verdict(False, f"В архив попало не только PDF ({extra[0]}…) — {redo}.")
            return Verdict(got == s["pdfs"])
        if any(n.endswith(".DS_Store") for n in names):
            return Verdict(False, "В архив попал мусор .DS_Store — удали архив и упакуй с -x '*.DS_Store'.")
        if any(n.endswith(".tmp") for n in names):
            return Verdict(False, f"В архив попали временные *.tmp — {redo} с -x '*.tmp'.")
        if any("/cache/" in "/" + n for n in names):
            return Verdict(False, f"В архив попало содержимое cache/ — {redo}: маска для папки — "
                                  "'project/cache/*'.")
        if not names:
            return Verdict(False, f"В {name} одна пустая папка: без -r zip не заходит внутрь. "
                                  f"Так что {redo} с -r.")
        return Verdict(sorted(names) == s["files"])


class PbcopyList(Task):
    id = "pbcopy_list"
    track = "finder"
    title = "Через буфер обмена"
    uses_clipboard = True
    uses_paste = True       # check читает буфер (kit.read_clipboard), карточка учит pbpaste
    scroll = ("COMMAND | pbcopy — положить в буфер обмена то, что напечатала команда (потом "
              "Cmd+V куда угодно); pbcopy < FILE — в буфер содержимое файла; pbpaste — "
              "напечатать, что лежит в буфере. Сдавать ничего не надо: игра заглянет в буфер.")
    variants = (
        Variant("Нужен список всех PDF здесь — в буфере обмена, чтобы вставить в письмо. "
                "(Текст из твоего буфера тренажёр вернёт после задачи.)",
                wrong=("ls | pbcopy",),
                alternatives=("ls *.pdf | pbcopy && pbpaste — положить и сразу проверить, что легло",)),
        Variant("Положи в буфер обмена всё содержимое файла address.txt — вставлю его в письмо. "
                "(Текст из твоего буфера тренажёр вернёт после задачи.)",
                hints=("Содержимое файла печатает cat — а любой вывод можно отправить в буфер.",
                       "| pbcopy после команды — или pbcopy < файл, совсем без cat.",
                       "pbcopy < address.txt — проверить: pbpaste"),
                solution="pbcopy < address.txt",
                wrong=("echo address.txt | pbcopy",),
                alternatives=("cat address.txt | pbcopy — то же через трубу",)),
        Variant("Положи в буфер обмена полный путь этой папки — от самого корня /, его ждёт "
                "коллега. (Текст из твоего буфера тренажёр вернёт после задачи.)",
                hints=("Полный путь текущей папки печатает pwd.",
                       "Вывод любой команды отправляет в буфер | pbcopy.",
                       "pwd | pbcopy — проверить: pbpaste"),
                solution="pwd | pbcopy",
                wrong=("echo . | pbcopy",),
                alternatives=("pwd | pbcopy && pbpaste — положить и сразу проверить, что легло",)),
    )
    par = 25
    hints = ("Сначала получи список: ls *.pdf",
             "Вывод любой команды можно отправить в буфер через | pbcopy",
             "ls *.pdf | pbcopy — проверить: pbpaste")
    solution = "ls *.pdf | pbcopy"
    explain = "pbcopy/pbpaste связывают терминал с обычным буфером Mac — Cmd+C/Cmd+V для команд."
    spell = "COMMAND | pbcopy — в буфер обмена; pbpaste — что в буфере"

    def setup_variant(self, box, rng, variant):
        pdfs = [f"{kit.latin(rng)}_{i}.pdf" for i in range(rng.randint(4, 8))]
        others = [f"{kit.latin(rng)}_{100 + i}.{rng.choice(['txt', 'csv', 'jpg'])}"
                  for i in range(rng.randint(6, 12))]
        for n in pdfs + others:
            kit.write(box / n, "x\n")
        if variant == 1:
            text = (f"{rng.randint(100, 2999)} {kit.word(rng).capitalize()} Street, "
                    "San Francisco\n"
                    f"Apt {rng.randint(1, 300)}, intercom {rng.randint(10, 99)}#\n"
                    f"Recipient: {kit.word(rng)}\n")
            kit.write(box / "address.txt", text)
            kit.write(box / "address_old.txt", "Old address, not needed.\n")
            return {"text": text}
        if variant == 2:
            return {"path": True}
        return {"pdfs": sorted(pdfs)}

    def check(self, ctx):
        clip = kit.read_clipboard(ctx.box)
        s = ctx.state
        if "text" in s:
            got = [l.rstrip() for l in clip.strip().splitlines()]
            if got == [l.rstrip() for l in s["text"].strip().splitlines()]:
                return Verdict(True)
            if clip.strip() == "address.txt":
                return Verdict(False, "В буфере имя файла, а нужно то, что в нём написано.")
            return Verdict(False)
        if s.get("path"):
            got = clip.strip()
            if not got:
                return Verdict(False)
            p = Path(got)
            try:
                if p.is_absolute() and p.resolve() == ctx.box.resolve():
                    return Verdict(True)
            except (OSError, RuntimeError):
                pass
            if not p.is_absolute():
                return Verdict(False, "В буфере не полный путь: он начинается с / — его "
                                      "печатает pwd.")
            return Verdict(False, "В буфере путь другой папки — нужна та, где началась задача.")
        got = sorted(l.strip() for l in clip.splitlines() if l.strip())
        if got == s["pdfs"]:
            return Verdict(True)
        if set(s["pdfs"]) < set(got):
            return Verdict(False, "В буфере не только PDF: отбери их маской *.pdf, а потом "
                                  "| pbcopy.")
        return Verdict(False)


class KillFrozen(Task):
    id = "kill_frozen"
    track = "finder"
    title = "Зависший процесс"
    scroll = ("pgrep -fl NAME — найти процесс (запущенную программу) по куску имени: PID в "
              "начале строки, дальше команда (f — full, по всей команде; l — list). kill PID — "
              "вежливо попросить завершиться; kill -9 PID — оборвать сразу.\n"
              "Проверить — тот же pgrep -fl ещё раз; pkill -f NAME гасит всех, в ком есть этот "
              "кусок, — сначала посмотри через pgrep, кого заденет.")
    variants = (
        Variant("Процесс {name} завис и не отвечает. Найди его и останови.",
                # ловушка «без -f не видна командная строка»: pgrep без -f сверяет имя процесса
                # (у зависших оно sh) и ничего не находит — kill не вызывается вовсе, сигналов нет
                # путь песочницы в шаблоне: и неверное решение не заденет чужой stuck_
                wrong=("pgrep \"$TERMIT_BOX/stuck_\" && kill -9 $(pgrep \"$TERMIT_BOX/stuck_\")",),
                alternatives=("pgrep -fl stuck_ && pkill -f stuck_ — сначала посмотреть, кого "
                              "заденет",
                              "ps aux | grep stuck_, kill PID — по-старому: PID во втором "
                              "столбце ps",)),
        Variant("Зависли два похожих скрипта: {name} и {backup_name}. Останови только {name} — "
                "резервная копия {backup_name} должна работать дальше.",
                hints=("Сначала посмотри, что совпадает: pgrep -fl {base}",
                       "pkill -f {base} заденет обоих — у копии в имени то же начало. Бей по "
                       "номеру: kill PID нужной строки.",
                       "pgrep -fl {base}, kill PID строки с {name} (не с _backup)"),
                solution="pgrep -fl {base}, kill PID строки с {name}",
                solution_script=("kill $(ps aux | grep \"$TERMIT_BOX/{name}\" | grep -v grep | "
                                 "awk '{{print $2}}')"),
                wrong=("pkill -f \"$TERMIT_BOX/{base}\"",),
                alternatives=("pkill -f '{base}\\.sh' — \\. значит именно точку, и копия "
                              "_backup не совпадёт",)),
        Variant("Зависли сразу два скрипта: {name} и {name2}. Останови оба. Учти: один из них "
                "вежливый kill не слушает.",
                hints=("pgrep -fl stuck_ покажет обоих вместе с номерами.",
                       "Упрямого вежливый kill не возьмёт — нужен -9: kill -9 PID или "
                       "pkill -9 -f NAME.",
                       "pgrep -fl stuck_, pkill -9 -f stuck_ (или kill -9 PID1 PID2)"),
                solution="pgrep -fl stuck_, pkill -9 -f stuck_",
                solution_script=("kill -9 $(ps aux | grep \"$TERMIT_BOX/stuck_\" | grep -v grep "
                                 "| awk '{{print $2}}')"),
                wrong=("pkill -f \"$TERMIT_BOX/stuck_\"", "pkill -9 -f \"$TERMIT_BOX/{name}\""),
                alternatives=("kill -9 PID1 PID2 — kill принимает несколько номеров сразу",)),
    )
    par = 40
    hints = ("Процесс по куску имени находит pgrep -fl.",
             "PID — число в начале строки pgrep. Останавливает kill PID.",
             "pgrep -fl stuck_, kill PID (не помогло — kill -9 PID)")
    solution = "pgrep -fl stuck_, kill PID   (упрямого — kill -9 PID)"
    solution_script = ("kill -9 $(ps aux | grep \"$TERMIT_BOX/{name}\" | grep -v grep | "
                       "awk '{{print $2}}')")
    explain = ("pgrep выследит процесс, kill его остановит; -9 — для тех, кто по-хорошему "
               "не понимает.")
    spell = "pgrep -fl NAME — найти процесс; kill PID; kill -9 PID — насильно"

    LIFE = 900          # секунд висит «зависший»; копия в B живёт дольше — её уход не ошибка игрока
    BACKUP_LIFE = 1800

    def _spawn(self, box, name: str, stubborn: bool, life: int) -> int:
        body = ("#!/bin/sh\n# Hangs and does nothing.\n" +
                ("trap '' TERM\n" if stubborn else "") +
                f'end=$(( $(date +%s) + {life} ))\n'
                f'while [ "$(date +%s)" -lt "$end" ] && [ -d {kit.quote(box / ".termit")} ]; '
                'do sleep 1; done\n')
        p = kit.write(box / name, body)
        os.chmod(p, 0o755)
        return kit.spawn_detached(box, f"/bin/sh {shlex.quote(str(p))}")

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            base = f"stuck_{kit.latin(rng)}"
            name, backup_name = f"{base}.sh", f"{base}_backup.sh"
            backup = self._spawn(box, backup_name, False, self.BACKUP_LIFE)
            pid = self._spawn(box, name, False, self.LIFE)
            return {"pid": pid, "name": name, "stubborn": False, "base": base,
                    "backup": backup, "backup_name": backup_name}
        if variant == 2:
            a, b = rng.sample(kit.LATIN, 2)
            name, name2 = f"stuck_{a}.sh", f"stuck_{b}.sh"
            pid = self._spawn(box, name, False, self.LIFE)
            pid2 = self._spawn(box, name2, True, self.LIFE)
            return {"pid": pid, "name": name, "stubborn": False, "pid2": pid2, "name2": name2}
        name = f"stuck_{kit.latin(rng)}.sh"
        stubborn = rng.random() < 0.5
        pid = self._spawn(box, name, stubborn, self.LIFE)
        return {"pid": pid, "name": name, "stubborn": stubborn}

    @staticmethod
    def _killed(ctx) -> bool:
        return kit.used_kill(ctx.cmds)

    TIMEOUT = ("Время вышло — процесс сам отвалился, ты его не трогал. Набери reset и начни "
               "заново.")

    def check(self, ctx):
        s = ctx.state
        killed = self._killed(ctx)
        if "backup" in s:
            if not kit.gone(s["pid"]):
                return Verdict(False)
            if not kit.alive(s["backup"]):
                return Verdict(False, f"Копия {s['backup_name']} тоже остановлена, а её надо "
                                      "было оставить. Набери reset и бей точнее — по номеру: "
                                      "kill PID.")
            return Verdict(True) if killed else Verdict(False, self.TIMEOUT)
        if "pid2" in s:
            first, second = kit.gone(s["pid"]), kit.gone(s["pid2"])
            if first and second:
                return Verdict(True) if killed else Verdict(False, self.TIMEOUT)
            if killed and not second:
                return Verdict(False, f"{s['name2']} не послушался вежливого kill. Есть приказ "
                                      "посильнее: kill -9 PID (или pkill -9 -f stuck_)")
            if killed:
                return Verdict(False, f"{s['name2']} готов, а {s['name']} ещё висит. "
                                      "Глянь: pgrep -fl stuck_")
            return Verdict(False)
        if kit.gone(s["pid"]):
            return Verdict(True) if killed else Verdict(False, self.TIMEOUT)
        if s["stubborn"] and killed:
            return Verdict(False, "Процесс не послушался вежливого kill. Есть приказ посильнее: "
                                  "kill -9 PID (или pkill -9 -f stuck_)")
        last = ctx.cmds[-1].line if ctx.cmds else ""
        if re.search(r"\bp(grep|kill)\b", last) and not re.search(r"\s-\w*f", last):
            return Verdict(False, "pgrep и pkill без -f сверяют только имя программы — у "
                                  "скрипта это sh, а не его файл. С -f они смотрят всю команду.")
        return Verdict(False)


class TopHog(Task):
    id = "top_hog"
    track = "finder"
    title = "Пожиратель ресурсов"
    scroll = ("top -o cpu — живой список процессов, прожорливые сверху (o — order; top -o mem — "
              "по памяти, M в колонке MEM — мегабайты); q — выход.\n"
              "ps aux -r | grep procs — то же разом, без прыжков (r — по процессору; ps aux -m — по "
              "памяти, m — memory): PID — второй столбец, полная команда — в конце, у нужного "
              "путь .termit/procs. Потом kill PID; двоих — kill PID PID.")
    variants = (
        Variant("Какой-то процесс съедает процессор. Найди его в top и останови. "
                "Остальных не трогай!",
                # «первый попавшийся процесс игры»: приманка _0 — явно, без опоры на порядок PID
                wrong=("kill $(pgrep -f \"$TERMIT_BOX/.termit/procs/.*_0\\.py\")",),
                alternatives=("top -l 1 -o cpu -n 5 — -l 1 — один снимок вместо живого экрана, "
                              "-n 5 — пять верхних строк",)),
        Variant("Какой-то процесс съедает память — сотни мегабайт. Найди его и останови. "
                "Остальных не трогай! В top сортировка по памяти — top -o mem; в колонке MEM "
                "буква M — мегабайты.",
                hints=("Кто ест память, показывает top -o mem — виновник в первой строке, PID — "
                       "в первом столбце. Выход — q.",
                       "Сверь кандидата: ps aux -m | grep procs — у нужного в команде путь "
                       ".termit/procs. PID — во втором столбце.",
                       "top -o mem или ps aux -m | grep procs, строка с .termit/procs наверху, "
                       "kill PID"),
                solution=("top -o mem, PID в первой строке; сверка: ps aux -m | grep procs (в команде "
                          ".termit/procs), kill PID"),
                solution_script=("sleep 1; kill $(ps aux -m | grep \"$TERMIT_BOX/.termit/procs\" "
                                 "| grep -v grep | head -1 | awk '{{print $2}}')"),
                wrong=("sleep 1; kill $(ps aux -r | grep \"$TERMIT_BOX/.termit/procs\" | "
                       "grep -v grep | head -1 | awk '{{print $2}}')",),
                alternatives=("top -l 1 -o mem -n 5 — один снимок вместо живого экрана",)),
        Variant("Процессор едят сразу два процесса. Найди обоих в top и останови. "
                "Остальных не трогай! kill принимает несколько номеров через пробел.",
                hints=("top -o cpu — прожорливые сверху; сегодня виновников двое — смотри две "
                       "верхние строки. Выход — q.",
                       "Сверь: ps aux -r | grep procs — у обоих в команде путь .termit/procs. kill "
                       "принимает несколько PID сразу.",
                       "top -o cpu или ps aux -r | grep procs, два PID с .termit/procs наверху, kill "
                       "PID1 PID2"),
                solution=("top -o cpu, два PID сверху; сверка: ps aux -r | grep procs (в команде "
                          ".termit/procs), kill PID1 PID2"),
                solution_script=("kill $(ps aux -r | grep \"$TERMIT_BOX/.termit/procs\" | "
                                 "grep -v grep | head -2 | awk '{{print $2}}')"),
                wrong=("kill $(ps aux -r | grep \"$TERMIT_BOX/.termit/procs\" | grep -v grep | "
                       "head -1 | awk '{{print $2}}')",),
                alternatives=("top -l 1 -o cpu -n 5 — -l 1 — один снимок вместо живого экрана, "
                              "-n 5 — пять верхних строк",)),
    )
    par = 45
    hints = ("Кто ест процессор, показывает top -o cpu — виновник в первой строке, PID — в "
             "первом столбце. Выход — q.",
             "Сверь кандидата: ps aux -r | grep procs — у нужного процесса в команде путь "
             ".termit/procs. PID — во втором столбце.",
             "top -o cpu или ps aux -r | grep procs, строка с .termit/procs наверху, kill PID")
    solution = ("top -o cpu, PID в первой строке; сверка: ps aux -r | grep procs (в команде "
                ".termit/procs), kill PID")
    solution_script = ("kill $(ps aux -r | grep \"$TERMIT_BOX/.termit/procs\" | grep -v grep | "
                       "head -1 | awk '{{print $2}}')")
    explain = "top — «Мониторинг системы» в терминале: виден виновник тормозов и его PID."
    spell = "top -o cpu — кто ест процессор (q — выход); top -o mem — память"

    HOG_LIFE = 600       # секунд; приманки живут дольше пожирателя,
    DECOY_LIFE = 1200    # чтобы их уход сам по себе не выглядел ошибкой игрока
    HOG_MEM = 160 * 1024 * 1024     # байт: «сотни мегабайт» против десятка у приманок

    # Тела процессов. Все уходят сами, когда истёк срок или пропала папка .termit.
    _LOOP = ("import os, time\n{pre}end = time.time() + {life}\n"
             "while time.time() < end and os.path.isdir({mark}):\n")
    _BUSY = "    t = time.time() + 0.5\n    while time.time() < t:\n        pass\n"
    _IDLE = "    time.sleep(1)\n"
    _LIGHT = ("    t = time.time() + 0.2\n    while time.time() < t:\n        pass\n"
              "    time.sleep(0.8)\n")

    def _proc(self, box, rng, life, tail, suffix="", pre=""):
        procs = box / ".termit" / "procs"
        py = shlex.quote(sys.executable)
        src = self._LOOP.format(pre=pre, life=life, mark=repr(str(box / ".termit"))) + tail
        p = kit.write(procs / f"{kit.latin(rng)}_{rng.randint(10, 99)}{suffix}.py", src)
        return f"{py} {shlex.quote(str(p))}"

    def setup_variant(self, box, rng, variant):
        if variant == 1:
            # приманки: спящая и слегка жующая процессор (её top -o cpu ставит первой)
            decoy_cmds = [self._proc(box, rng, self.DECOY_LIFE, self._IDLE, "_0"),
                          self._proc(box, rng, self.DECOY_LIFE, self._LIGHT, "_1")]
            mem = self.HOG_MEM
            # 1 МБ случайных байт, повторённый: компрессор памяти macOS такие страницы не ужмёт,
            # а ЦП уходит ~0,03 с (os.urandom на все 160 МБ грел бы процессор дольше приманки, и
            # top -o cpu ставил бы пожирателя первым). bytes * n — без второй копии в памяти.
            pre = f"b = os.urandom(1 << 20) * {mem >> 20}\n"
            hog_cmd = self._proc(box, rng, self.HOG_LIFE, self._IDLE, pre=pre)
            decoys = [kit.spawn_detached(box, c) for c in decoy_cmds]
            return {"pid": kit.spawn_detached(box, hog_cmd), "decoys": decoys, "mode": "mem"}
        if variant == 2:
            decoy_cmds = [self._proc(box, rng, self.DECOY_LIFE, self._IDLE, f"_{i}")
                          for i in range(2)]
            hog_cmds = [self._proc(box, rng, self.HOG_LIFE, self._BUSY) for _ in range(2)]
            decoys = [kit.spawn_detached(box, c) for c in decoy_cmds]
            pid, pid2 = (kit.spawn_detached(box, c) for c in hog_cmds)
            return {"pid": pid, "pid2": pid2, "decoys": decoys}
        hog_cmd = self._proc(box, rng, self.HOG_LIFE, self._BUSY)
        decoy_cmds = [self._proc(box, rng, self.DECOY_LIFE, self._IDLE, f"_{i}")
                      for i in range(2)]
        decoys = [kit.spawn_detached(box, c) for c in decoy_cmds]
        pid = kit.spawn_detached(box, hog_cmd)
        return {"pid": pid, "decoys": decoys}

    def check(self, ctx):
        s = ctx.state
        if any(not kit.alive(d) for d in s["decoys"]):
            return Verdict(False, "Ты остановил не тот процесс! Набери reset и сверься с top: "
                                  "останавливать только того, кто ест.")
        hogs = [s["pid"]] + ([s["pid2"]] if "pid2" in s else [])
        down = [kit.gone(p) for p in hogs]
        if not any(down):
            return Verdict(False)
        if not all(down):
            return Verdict(False, "Один пожиратель остановлен, а процессор ест второй. "
                                  "Глянь top ещё раз.")
        killed = kit.used_kill(ctx.cmds)
        if killed:
            return Verdict(True)
        return Verdict(False, "Время вышло — процесс сам отвалился. Набери reset и начни "
                              "заново.")


PIC, DOC, TAB, OTHER = ["jpg", "JPG", "jpeg", "png", "heic"], ["pdf", "docx", "txt"], \
    ["csv", "xlsx"], ["dmg", "zip", "mp3"]
FOLDER = {**{e.lower(): "pictures" for e in PIC}, **{e: "documents" for e in DOC},
          **{e: "tables" for e in TAB}}


def folder_for(name: str) -> str:
    return FOLDER.get(name.rsplit(".", 1)[-1].lower(), "other")


# --- Пары «до/после» (часть 5): rg_hunt и fd_hunt ------------------------------------------
# Решаются встроенными (grep, find); rg и fd дают только скорость и точность. rg и fd сами
# пропускают скрытое (а с ним .git) и всё из .gitignore/.ignore. .gitignore они читают только
# внутри git-репозитория, .ignore — всегда; здесь лежат оба, одинаковые, и есть .git/. Скрытых
# файлов с ответом нет (кроме того, о чём задача говорит прямо), бинарники ответа не содержат:
# честный grep/find с исключениями и rg/fd дают один ответ.

PROJ = "proj"


def _proj_match(given: str, ctx, rel: str) -> bool:
    """Путь rel (от proj/) сдан относительно proj/, песочницы, текущей папки или абсолютным."""
    target = Path(ctx.box) / PROJ / rel
    bases = [Path(ctx.box) / PROJ, Path(ctx.box)] + ([Path(ctx.pwd)] if ctx.pwd else [])
    return any(textnorm.same_path(given, target, b) for b in bases)


def _git_project(proj: Path, rng, ignore: str) -> None:
    """Каркас: .git/ (по нему rg и fd узнают репозиторий), .gitignore и .ignore, бинарники."""
    kit.write(proj / ".git" / "HEAD", "ref: refs/heads/main\n")
    kit.write(proj / ".git" / "config", "[core]\n\trepositoryformatversion = 0\n\tbare = false\n")
    for name in (".gitignore", ".ignore"):
        kit.write(proj / name, ignore)
    kit.write_random(proj / "assets" / "logo.png", rng.randint(2000, 4000), rng)
    kit.write_random(proj / "bin" / "helper", rng.randint(3000, 6000), rng)


class DiskSweep(Task):
    """Практика перед «Уборкой Загрузок» (П3.1 приёмки-1): find -type -empty -delete,
    ls -S и вывод в файл через > — до стража, а не на нём. FB12 (N10, п. 34): первая встреча
    — один приём (ls -S в файл), вся уборка — вариант-практика 1: страж ждёт, пока он выпадет
    (practice_variant), а первый повтор выдаёт именно его. Маска без регистра — вариант 2."""
    id = "disk_sweep"
    track = "finder"
    title = "Чистка диска"
    scroll = ("ls -S DIR — тяжёлые сверху (S — Size); | head -1 — первая строка; COMMAND > FILE — "
              "вывод в файл (прежнее пропадёт).\n"
              "find DIR -type f -empty — пустые файлы, -type d -empty — пустые папки; "
              "find DIR -type f -empty -delete — найдёт и удалит.\n"
              "Без учёта регистра (zsh): setopt extendedglob, потом ls *.(#i)jpg (i — "
              "insensitive) — и jpg, и JPG.")
    variants = (
        Variant("В папке docs свалены файлы. Запиши имя самого тяжёлого из них в файл "
                "heavy.txt — рядом с docs (там, где стоишь, а не внутри docs), одной строкой.",
                wrong=("ls docs | head -1 > heavy.txt", "ls -S docs | tail -1 > heavy.txt"),
                alternatives=("ls -lS docs — с размерами, чтобы сверить глазами",)),
        Variant("Диск junk — помойка. Наведи порядок по правилам: недокачанные *.part — "
                "стереть во всех папках; пустые файлы (0 байт) — стереть, а потом убрать "
                "опустевшие папки. Имя самого тяжёлого из оставшихся файлов, что лежат прямо в "
                "junk (не во вложенных папках), запиши в heavy.txt рядом с junk — там, где "
                "стоишь.",
                wrong=("find junk -name '*.part' -delete; find junk -type f -empty -delete; "
                       "ls -S junk | head -1 > heavy.txt",
                       "find junk -name '*.part' -delete; find junk -type f -empty -delete; "
                       "find junk -type d -empty -delete; ls junk | head -1 > heavy.txt"),
                alternatives=("find junk -empty -delete — пустые файлы и папки за один "
                              "проход",
                              "ls -lS junk | head -3 — с размерами, чтобы сверить глазами"),
                hints=("Иди по правилам: find junk -name '*.part' -delete, потом пустые файлы "
                       "— find junk -type f -empty -delete, потом пустые папки — -type d.",
                       "Самый тяжёлый — ls -S, первая строка — | head -1, в файл — > heavy.txt.",
                       "find junk -name '*.part' -delete; find junk -type f -empty -delete; "
                       "find junk -type d -empty -delete; ls -S junk | head -1 > heavy.txt"),
                solution="find junk -name '*.part' -delete; find junk -type f -empty -delete; "
                         "find junk -type d -empty -delete; ls -S junk | head -1 > heavy.txt",
                explain="find не только ищет, но и сносит найденное (-delete); ls -S ставит "
                        "тяжёлых сверху; > сваливает вывод в файл.",
                par=120),
        Variant("В папке mixed снимки вперемешку с документами, а расширения у снимков кто "
                "как написал: .jpg, .JPG, .Jpg. Перенеси все снимки .jpg любым регистром в "
                "папку photos (она уже есть, рядом с mixed). Остальное не трогай.",
                hints=("Маска *.jpg видит только маленькие буквы — нужна маска без учёта "
                       "регистра.",
                       "В zsh её включает setopt extendedglob, а (#i) в маске отключает регистр.",
                       "setopt extendedglob; mv mixed/*.(#i)jpg photos/"),
                solution="setopt extendedglob; mv mixed/*.(#i)jpg photos/",
                wrong=("mv mixed/*.jpg photos/",
                       "setopt extendedglob; mv mixed/*(#i)jpg* photos/"),
                alternatives=("find mixed -iname '*.jpg' -exec mv {{}} photos/ \\; — то же "
                              "без zsh: -exec выполнит mv для каждого найденного, -iname — как "
                              "в поиске файла",)),
    )
    practice_variant = 1
    par = 60
    hints = ("Размер покажет ls с флагом: -S ставит тяжёлые сверху.",
             "Первая строка — | head -1, а > файл запишет вывод в файл.",
             "ls -S docs | head -1 > heavy.txt")
    solution = "ls -S docs | head -1 > heavy.txt"
    explain = ("ls -S ставит тяжёлых сверху, head -1 берёт первую строку, а > сваливает "
               "вывод в файл.")
    spell = ("find DIR -type f -empty -delete — стереть пустышки; ls -S — тяжёлые сверху; "
             "COMMAND > FILE")

    def setup_variant(self, box, rng, variant):
        rel = lambda p: str(p.relative_to(box))
        if variant == 0:
            names = [f"{kit.latin(rng)}_{i}.{rng.choice(['pdf', 'txt', 'zip'])}"
                     for i in range(rng.randint(6, 9))]
            sizes = sorted(rng.sample(range(2, 60), len(names)))
            # самый тяжёлый — не первый по алфавиту: иначе ls без -S угадал бы его
            heavy = rng.choice(sorted(names)[1:])
            rest = [n for n in names if n != heavy]
            rng.shuffle(rest)
            for name, kb in zip(rest + [heavy], sizes):
                kit.write_random(box / "docs" / name, kb * 1024, rng)
            return {"heavy": heavy}
        if variant == 2:
            shots = [f"{kit.latin(rng)}_{i}.{ext}"
                     for i, ext in enumerate(rng.sample(["jpg", "JPG", "Jpg", "jpg", "JPG"], 5))]
            keep = [f"{kit.latin(rng)}_{i}.{ext}" for i, ext in
                    enumerate(["pdf", "txt", "png", "PNG"], start=10)] + ["list_jpg.txt"]
            for n in shots + keep:
                kit.write(box / "mixed" / n, f"{n}\n")
            (box / "photos").mkdir()
            return {"move": shots, "keep": keep}
        root = box / "junk"
        dirs = maze(root, rng, rng.randint(8, 12))
        empty_files = [kit.write(rng.choice(dirs) / f"{kit.latin(rng)}_{i}.tmp", "")
                       for i in range(rng.randint(5, 8))]
        full = [kit.write(rng.choice(dirs[1:]) / f"{kit.latin(rng)}_{i}.txt", "keep\n")
                for i in range(rng.randint(5, 8))]
        # недокачанные — только рядом с настоящими файлами: их папки не опустеют
        parts = [kit.write(p.parent / f"{kit.latin(rng)}_{i}.part", "partial download\n")
                 for i, p in enumerate(rng.sample(full, min(3, len(full))))]
        # папка, где только пустышки: опустеет после файлов; и пустая с самого начала
        ghost = root / "blanks"
        empty_files += [kit.write(ghost / f"nol_{i}.log", "") for i in range(3)]
        (root / "empty" / "deeper").mkdir(parents=True)
        # корень: документы; самый тяжёлый по алфавиту не первый (ls без -S его не угадает)
        sizes = sorted(rng.sample(range(3, 60), 8))
        docs = [f"{kit.latin(rng)}_{i}.{rng.choice(['pdf', 'txt', 'jpg'])}" for i in range(7)]
        heavy = f"notes_{kit.latin(rng)}.pdf"
        rng.shuffle(docs)
        for name, kb in zip(docs + [heavy], sizes):
            full.append(kit.write_random(root / name, kb * 1024, rng))
        return {"empty": [rel(p) for p in empty_files + parts],
                "full": [rel(p) for p in full], "heavy": heavy}

    def check(self, ctx):
        b, s = ctx.box, ctx.state
        # вид варианта — по ключам state (FB12: номера 0 и 1 поменялись местами, а task.json
        # старой песочницы помнит прежний номер)
        if "empty" in s:
            return self._sweep(b, s)
        if "keep" not in s:
            if self._heavy_ok(b, s["heavy"]):
                return Verdict(True)
            if (b / "heavy.txt").is_file():
                return Verdict(False, "В heavy.txt не то имя: нужен самый тяжёлый файл из docs. "
                                      "ls -S ставит тяжёлые сверху, первую строку берёт head -1.")
            return Verdict(False)
        photos = b / "photos"
        inside = {p.name for p in photos.iterdir()} if photos.is_dir() else set()
        if inside == set(s["move"]) and all((b / "mixed" / n).exists() for n in s["keep"]):
            return Verdict(True)
        lost = [n for n in s["keep"] + s["move"]
                if not (b / "mixed" / n).exists() and n not in inside]
        if lost:
            return Verdict(False, f"Стёрто то, что трогать было нельзя: "
                                  f"{kit.names_line(lost)}. " + kit.RESET_TAIL)
        extra = sorted(inside - set(s["move"]))
        if extra:
            return Verdict(False, f"В photos попало не то: {kit.names_line(extra)} — верни "
                                  f"обратно: mv photos/{extra[0]} mixed/")
        if inside:
            return Verdict(False, self.RULES["move"])
        return Verdict(False)

    # вариант 1 (практика стража) — правила уборки (N1 ревью C1a): нарушение, которое не
    # исправить, — reset;
    # лишнее в photos — сразу; а когда невыполненное правило осталось одно — назвать его
    # правило и инструмент, без готовой строки: в «деле» команда стоит денег (M1 ревью C1b)
    RULES = {
        "parts": "Остались недокачанные *.part — их тоже убирает find, по имени.",
        "empty": "Остались пустые файлы (0 байт) — find умеет найти пустые и удалить их.",
        "dirs": "Остались пустые папки — их убирают после файлов, тем же find.",
        "move": "Не все снимки в photos: обычная маска видит только маленькие буквы — нужна "
                "маска без учёта регистра.",
        "heavy": "Осталось записать в heavy.txt имя самого тяжёлого файла из корня junk.",
        "heavy_bad": "В heavy.txt не то имя: нужен самый тяжёлый файл из корня junk — по "
                     "размеру, а не по алфавиту.",
    }

    def _sweep(self, b: Path, s: dict) -> Verdict:
        root = b / "junk"
        lost = [Path(r).name for r in s["full"] if not (b / r).is_file()]
        if lost:
            return Verdict(False, f"Стёрт нужный файл: {kit.names_line(lost)} — это не "
                                  "пустышка. " + kit.RESET_TAIL)
        moves = "move" in s                 # FB12: снимки в варианте 0 больше не переносят
        inside = ({p.name for p in (b / "photos").iterdir()}
                  if moves and (b / "photos").is_dir() else set())
        extra = sorted(inside - set(s.get("move", ())))
        if extra:
            return Verdict(False, f"В photos попало не то: {kit.names_line(extra)} — верни в "
                                  f"junk: mv photos/{extra[0]} junk/")
        left = []
        if any((b / r).exists() for r in s["empty"] if r.endswith(".part")):
            left.append("parts")
        if any((b / r).exists() for r in s["empty"] if not r.endswith(".part")):
            left.append("empty")
        try:
            if any(not any(d.iterdir())
                   for d in [root] + [p for p in root.rglob("*") if p.is_dir()]):
                left.append("dirs")
        except OSError:
            left.append("dirs")
        if moves and inside != set(s["move"]):
            left.append("move")
        if "heavy" in s and not self._heavy_ok(b, s["heavy"]):
            left.append("heavy_bad" if (b / "heavy.txt").exists() else "heavy")
        if not left:
            return Verdict(True)
        if len(left) == 1 or left == ["heavy_bad"]:
            return Verdict(False, self.RULES[left[0]])
        return Verdict(False)

    @staticmethod
    def _heavy_ok(b: Path, heavy: str) -> bool:
        f = b / "heavy.txt"
        try:
            got = f.read_text("utf-8", errors="replace").strip() if f.is_file() else ""
        except OSError:
            return False
        return Path(got).name == heavy and "\n" not in got

class DupSort(Task):
    """Практика перед «Уборкой Загрузок» (P2 Б9, psych 3.1): экранирование скобок \\(1\\),
    «a или b» — (jpg|png) — и *(.) «только файлы» до стража, а не впервые на нём. FB12 (N10,
    п. 34): первая встреча — один приём, экранирование; все три сразу — вариант-практика 1,
    страж ждёт, пока он выпадет."""
    id = "dup_sort"
    track = "finder"
    title = "Дубли и снимки"
    scroll = ("Скобки и пробел в имени для zsh особые — экранируй (поставь \\ перед знаком) или бери в кавычки: "
              "rm *\\ \\(1\\).* или rm *' (1).'*\n"
              "(a|b) в маске — «a или b»: ls *.(pdf|docx). Без учёта регистра: setopt "
              "extendedglob, потом ls *.(#i)(jpg|png).\n"
              "*(.) — только файлы, без папок: ls *.jpg(.) не зацепит папку с именем на .jpg.")
    variants = (
        Variant("В downloads лежат дубли «имя (1).расширение» — точные копии. Сотри их все, "
                "оригиналы не трогай.",
                wrong=("rm downloads/*1*",),
                alternatives=("rm downloads/*' (1).'* — то же в кавычках",)),
        Variant("В downloads бардак: у части файлов есть дубли «имя (1).расширение» — точные "
                "копии, их сотри. Потом все снимки .jpg и .png — любым регистром — перенеси в "
                "новую папку downloads/photos — её ещё нет, заведи. Папку wallpaper.jpg не "
                "трогай: это папка, а не снимок.",
                wrong=("setopt extendedglob; rm downloads/*\\ \\(1\\).*; mkdir downloads/photos; "
                       "mv downloads/*.(#i)(jpg|png) downloads/photos/",
                       "rm downloads/*\\ \\(1\\).*; mkdir downloads/photos; "
                       "mv downloads/*.(jpg|png)(.) downloads/photos/"),
                alternatives=("rm downloads/*' (1).'* — кавычки вместо \\ перед пробелом и "
                              "скобками",
                              "ls downloads/*.(#i)(jpg|png)(.) — сначала увидеть, кого заденет"),
                hints=("Начни с дублей: скобки и пробел в имени экранируй — "
                       "rm downloads/*\\ \\(1\\).*",
                       "Снимки любым регистром: setopt extendedglob и маска *.(#i)(jpg|png). "
                       "Папку wallpaper.jpg маска тоже заденет — допиши (.) «только файлы».",
                       "setopt extendedglob; rm downloads/*\\ \\(1\\).*; mkdir downloads/photos; "
                       "mv downloads/*.(#i)(jpg|png)(.) downloads/photos/"),
                solution="setopt extendedglob; rm downloads/*\\ \\(1\\).*; "
                         "mkdir downloads/photos; mv downloads/*.(#i)(jpg|png)(.) downloads/photos/",
                explain="\\ снимает с пробела и скобок особый смысл; (a|b) — «a или b» прямо в "
                        "маске; с (#i) всё равно, большие буквы или маленькие, а (.) в конце "
                        "маски оставляет только файлы.",
                par=120),
        Variant("В downloads документы вперемешку с остальным. Перенеси все .pdf и .docx в "
                "папку downloads/documents (она есть) одной командой mv. Расширения у них "
                "маленькими буквами. Остальное не трогай.",
                hints=("Две маски можно слить в одну: (a|b) значит «a или b».",
                       "Скобки — вокруг расширений: *.(pdf|docx)",
                       "mv downloads/*.(pdf|docx) downloads/documents/"),
                solution="mv downloads/*.(pdf|docx) downloads/documents/",
                wrong=("mv downloads/*.pdf downloads/documents/",),
                alternatives=("mv downloads/*.pdf downloads/*.docx downloads/documents/ — "
                              "две маски подряд",)),
    )
    practice_variant = 1
    par = 60
    hints = ("Маска *(1)* zsh не поймёт: скобки в маске — особые знаки.",
             "Пробел и скобки экранируй обратной косой: \\ перед каждым.",
             "rm downloads/*\\ \\(1\\).*")
    solution = "rm downloads/*\\ \\(1\\).*"
    explain = ("\\ снимает с пробела и скобок особый смысл: zsh видит в них просто буквы "
               "имени, и маска ловит только «(1)».")
    spell = "rm *\\ \\(1\\).* — дубли; *.(jpg|png) — «или»; *(.) — только файлы (zsh)"

    PICS = ("jpg", "JPG", "Jpg", "png", "PNG")
    OTHER = ("pdf", "txt", "docx", "zip", "mp3")

    def setup_variant(self, box, rng, variant):
        z = box / "downloads"
        z.mkdir()
        used = set()

        def name(exts):
            while True:
                n = f"{rng.choice(['IMG', 'Scan', 'photo', 'doc', 'report'])} {rng.randint(100, 999)}"
                n = f"{n}.{rng.choice(exts)}"
                if n.lower() not in used:
                    used.add(n.lower())
                    return n

        if variant == 2:
            docs = ([name(("pdf",)), name(("docx",))] +
                    [name(("pdf", "docx")) for _ in range(rng.randint(2, 4))])
            rest = [name(("txt", "zip", "jpg", "docx.bak")) for _ in range(4)]
            for n in docs + rest:
                kit.write(z / n, f"{n}\n")
            (z / "documents").mkdir()
            return {"move": sorted(docs), "keep": sorted(rest)}
        exts = self.PICS + self.OTHER if variant == 1 else self.OTHER + ("jpg", "png")
        orig = [name(exts) for _ in range(rng.randint(10, 14))]
        keep = {}
        for n in orig:
            p = kit.write_random(z / n, rng.randint(500, 4_000), rng)
            keep[n] = kit.sha(p)
        dups = []
        for n in rng.sample(orig, rng.randint(4, 6)):
            stem, ext = n.rsplit(".", 1)
            d = f"{stem} (1).{ext}"
            shutil.copyfile(z / n, z / d)
            dups.append(d)
        # имя с «1» без скобок — не дубль: маска *1* его заденет, *\ \(1\).* — нет
        tricky = name(("txt",)).replace(".txt", " 1.txt")
        keep[tricky] = kit.sha(kit.write(z / tricky, "not a duplicate\n"))
        if variant == 0:
            return {"keep": keep, "dups": dups}
        # снимки обоих видов, и хоть один — большими буквами: без (#i) маска его не увидит
        for exts in (("JPG", "PNG", "Jpg"), ("jpg",), ("png", "PNG")):
            n = name(exts)
            keep[n] = kit.sha(kit.write_random(z / n, 900, rng))
        wallpaper = z / "wallpaper.jpg"
        kit.write(wallpaper / "sunset.png", "wallpaper\n")
        return {"keep": keep, "dups": dups, "dir": "wallpaper.jpg",
                "pics": sorted(n for n in keep if n.rsplit(".", 1)[1].lower() in ("jpg", "png"))}

    def check(self, ctx):
        b, s = ctx.box, ctx.state
        z = b / "downloads"
        # вид варианта — по ключам state (FB12: номера 0 и 1 поменялись местами, а task.json
        # старой песочницы помнит прежний номер)
        if "move" in s:
            d = z / "documents"
            inside = {p.name for p in d.iterdir()} if d.is_dir() else set()
            lost = [n for n in s["move"] + s["keep"]
                    if not (z / n).exists() and n not in inside]
            if lost:
                return Verdict(False, "Пропали файлы: " + kit.names_line(lost) + ". " +
                               kit.RESET_TAIL)
            extra = sorted(inside - set(s["move"]))
            if extra:
                return Verdict(False, f"В documents попало не то: {kit.names_line(extra)} — "
                                      f"верни: mv 'downloads/documents/{extra[0]}' downloads/")
            if inside == set(s["move"]):
                return Verdict(True)
            left = sorted(n for n in s["move"] if n not in inside)
            if inside and left:
                return Verdict(False, f"Перенесено не всё: {kit.names_line(left)} ещё в downloads. "
                                      "Обе маски сразу — (pdf|docx).")
            return Verdict(False)
        photos = z / "photos"
        where = {}
        for n in s["keep"]:
            for place in (z, photos):
                if (place / n).is_file():
                    where[n] = place
        lost = [n for n, h in s["keep"].items() if n not in where or kit.sha(where[n] / n) != h]
        if lost:
            return Verdict(False, "Стёрто то, что трогать было нельзя: " + kit.names_line(lost) +
                           " — это не дубль. " + kit.RESET_TAIL)
        dups_left = [d for d in s["dups"] if (z / d).exists() or (photos / d).exists()]
        if "dir" not in s:
            return Verdict(not dups_left)
        if (photos / s["dir"]).exists():
            return Verdict(False, f"Папка {s['dir']} уехала в photos: маска захватила и папку. "
                                  "(.) в конце маски — только файлы. Верни: "
                                  f"mv downloads/photos/{s['dir']} downloads/")
        if not (z / s["dir"] / "sunset.png").is_file():
            return Verdict(False, f"Папку {s['dir']} трогать было нельзя. " + kit.RESET_TAIL)
        inside = {p.name for p in photos.iterdir()} if photos.is_dir() else set()
        extra = sorted(inside - set(s["pics"]) - set(s["dups"]))
        if extra:
            return Verdict(False, f"В photos попало не то: {kit.names_line(extra)} — верни: "
                                  f"mv 'downloads/photos/{extra[0]}' downloads/")
        if dups_left:
            return Verdict(False, "Дубли «(1)» ещё на месте — их тоже убери." if inside else None)
        pics_ok = all(where.get(n) == photos for n in s["pics"])
        if not pics_ok and inside:
            return Verdict(False, "Не все снимки в photos: регистр у расширений разный — нужна "
                                  "маска без учёта регистра.")
        return Verdict(pics_ok)


class RgHunt(AnswerTask):
    id = "rg_hunt"
    track = "finder"
    title = "Охота по исходникам"
    implant = "rg"
    after = ("grep_r", "boss_finder")
    start_dir = PROJ
    scroll = ("grep -rn 'PATTERN' . — где встречается текст: путь:номер строки (n — number); "
              "чужое отрежь: grep -rn 'PATTERN' . --exclude-dir=.git --exclude-dir=vendor. "
              "grep -rl … | wc -l — сколько файлов; | xargs grep -l 'TWO' — из найденных "
              "оставит те, где есть и второе.\n"
              "rg -n 'PATTERN' . — то же отдельной программой (её ставят отдельно): сама идёт "
              "мимо .git и всего из .gitignore.")
    variants = (
        Variant("Ты стоишь в проекте proj/. Где определена функция {fn} (кусок кода с именем) — в "
                "каком файле и на "
                "какой строке? Определение в Python начинается со слова def — строка вида "
                "def {fn}(order, rate). "
                ".git и vendor/ не в счёт: там старые копии и чужой код. Ответ: ans FILE:LINE — "
                "путь и номер строки через двоеточие, как их печатает grep -n, например ans "
                "src/app/main.py:12",
                wrong=("grep -rn 'def {fn}(' . | cut -d: -f1,2",),
                alternatives=("rg -nF --no-heading 'def {fn}(' . — -F ищет текст как есть, "
                              "--no-heading печатает FILE:LINE в одну строку, как grep",)),
        Variant("Сколько файлов проекта proj/ упоминают {fn}( — вызов или определение, "
                "неважно? Служебная .git и чужой код в vendor/ не считаются. "
                "Ты стоишь в proj/. Ответ — число: ans NUMBER",
                hints=("Список файлов с текстом даёт grep -rl, а | wc -l посчитает строки.",
                       "Ищи вместе со скобкой: '{fn}(' — иначе попадутся похожие имена. "
                       "А .git и vendor/ отрежь --exclude-dir.",
                       "grep -rl --exclude-dir=.git --exclude-dir=vendor '{fn}(' . | wc -l — "
                       "программой rg: rg -lF '{fn}(' . | wc -l"),
                solution="grep -rl --exclude-dir=.git --exclude-dir=vendor '{fn}(' . | wc -l",
                solution_script="grep -rl --exclude-dir=.git --exclude-dir=vendor '{fn}(' . "
                                "| wc -l",
                implant_script="rg -lF '{fn}(' . | wc -l",
                wrong=("grep -rl '{fn}(' . | wc -l",
                       "grep -rl --exclude-dir=.git --exclude-dir=vendor '{fn}' . | wc -l"),
                alternatives=("rg -c -F '{fn}(' . — -c: сколько раз в каждом файле",)),
        Variant("Нужен файл проекта, где сошлись сразу три настройки: {k1}, {k2} и {k3}. "
                "Такой один, если не смотреть в .git и vendor/. Ты стоишь в proj/. Где он? "
                "Ответ: ans PATH — путь, как его напечатает grep.",
                hints=("Файлы с первой настройкой даст grep -rl; .git и vendor/ отрежь "
                       "--exclude-dir.",
                       "Список можно процедить ещё раз: | xargs grep -l '{k2}' оставит файлы, "
                       "где есть и вторая. Потом так же третья.",
                       "grep -rl --exclude-dir=.git --exclude-dir=vendor '{k1}' . | xargs grep "
                       "-l '{k2}' | xargs grep -l '{k3}' — программой rg: rg -l вместо grep -rl"),
                solution="grep -rl --exclude-dir=.git --exclude-dir=vendor '{k1}' . | "
                         "xargs grep -l '{k2}' | xargs grep -l '{k3}'",
                solution_script="grep -rl --exclude-dir=.git --exclude-dir=vendor '{k1}' . | "
                                "xargs grep -l '{k2}' | xargs grep -l '{k3}'",
                implant_script="rg -l '{k1}' . | xargs rg -l '{k2}' | xargs rg -l '{k3}'",
                wrong=("grep -rl '{k1}' . | xargs grep -l '{k2}' | xargs grep -l '{k3}'",
                       "grep -rl --exclude-dir=.git --exclude-dir=vendor '{k1}' . | "
                       "xargs grep -l '{k2}'"),
                alternatives=("rg -l '{k1}' . | xargs rg -l '{k2}' | xargs rg -l '{k3}' — "
                              "программой rg: -l (list) — только пути, .git и vendor/ она "
                              "обходит сама",)),
    )
    par = 60
    hints = ("Номер строки к находке grep -r добавит флагом -n. Ищи само определение: "
             "'def {fn}('.",
             "grep -r лезет и в .git, и в vendor/ — отрежь их: --exclude-dir=.git "
             "--exclude-dir=vendor.",
             "grep -rn --exclude-dir=.git --exclude-dir=vendor 'def {fn}(' . — путь:номер "
             "сдай: ans FILE:LINE; программой rg: rg -n --no-heading 'def {fn}\\(' .")
    solution = "grep -rn --exclude-dir=.git --exclude-dir=vendor 'def {fn}(' ."
    solution_script = ("grep -rn --exclude-dir=.git --exclude-dir=vendor 'def {fn}(' . "
                       "| cut -d: -f1,2")
    implant_script = "rg -nF 'def {fn}(' . | cut -d: -f1,2"
    explain = ("grep -r ищет везде, даже там, где не просили: в .git и чужих библиотеках — "
               "их отрезают --exclude-dir. rg то же делает сам и быстрее. Видит rg больше, чем "
               "grep, — загляни в ~/.ripgreprc: --hidden и --no-ignore меняют правила, "
               "rg --no-config работает по умолчанию.")
    spell = "grep -rn --exclude-dir=.git 'PATTERN' . — где в проекте встречается текст"

    FUNCS = ("calc_tax", "send_invoice", "parse_order", "sync_stock", "close_shift",
             "load_prices", "merge_carts", "check_limit")
    KEYS = ("retry_limit", "audit_log", "legacy_auth", "rate_cap", "dry_run", "batch_size")

    @staticmethod
    def _filler(rng, i):
        """Модуль-заглушка: блоки «def имя(x): return …», между блоками пустая строка."""
        lines = ["import os", ""]
        for k in range(rng.randint(2, 5)):
            lines += [f"def {kit.latin(rng)}_{i}_{k}(x):", f"    return x + {k}", ""]
        return lines

    def _tree(self, rng):
        files = {}
        pkgs = rng.sample(kit.LATIN, 4)
        for i in range(rng.randint(16, 22)):
            files[f"src/{rng.choice(pkgs)}/{kit.latin(rng)}_{i}.py"] = self._filler(rng, i)
        for i in range(rng.randint(3, 5)):
            files[f"tests/test_{kit.latin(rng)}_{i}.py"] = self._filler(rng, 100 + i)
        files["README.md"] = ["# Project", "", "Sources are in src/, tests are in tests/."]
        return files

    @staticmethod
    def _foreign(proj, rng, lines):
        """Те же строки в чужом: vendor/ (библиотека) и .git (потерянная копия)."""
        kit.write(proj / "vendor" / kit.latin(rng) / "compat.py",
                  "\n".join(["# third-party library"] + lines) + "\n")
        kit.write(proj / ".git" / "lost-found" / "other" / f"{rng.getrandbits(40):010x}",
                  "\n".join(lines) + "\n")

    @staticmethod
    def _save(proj, files):
        for rel, lines in files.items():
            kit.write(proj / rel, "\n".join(lines) + "\n")

    def setup_variant(self, box, rng, variant):
        proj = box / PROJ
        _git_project(proj, rng, "vendor/\n")
        files = self._tree(rng)
        code = [p for p in files if p.endswith(".py")]
        if variant == 2:
            k1, k2, k3 = rng.sample(self.KEYS, 3)
            target, d12, d13, d23, s1, s3 = rng.sample(code, 6)
            for rel, keys in ((target, (k1, k2, k3)), (d12, (k1, k2)), (d13, (k1, k3)),
                              (d23, (k2, k3)), (s1, (k1,)), (s3, (k3,))):
                files[rel] += [f"{k.upper()} = {k!r}" for k in keys] + [""]
            self._foreign(proj, rng, [f"{k.upper()} = {k!r}" for k in (k1, k2, k3)])
            self._save(proj, files)
            return {"k1": k1, "k2": k2, "k3": k3, "answer": target}
        fn = rng.choice(self.FUNCS)
        home, *rest = rng.sample(code, 8)
        callers = rest[:rng.randint(3, 5)]
        for k, rel in enumerate(callers):
            files[rel] += [f"def use_{k}(order):", f"    return {fn}(order, 0.2)", ""]
        defn = [f"def {fn}(order, rate):", "    return order * rate", ""]
        blocks = range(2, len(files[home]) + 1, 3)          # границы блоков заглушки
        pos = rng.choice(list(blocks))
        files[home][pos:pos] = defn
        self._foreign(proj, rng, defn + [f"total = {fn}(10, 0.2)"])
        if variant == 1:
            for k, rel in enumerate(rest[len(callers):]):   # похожее имя без «{fn}(»
                files[rel] += [f"def {fn}_total(items):", "    return sum(items)", ""]
            self._save(proj, files)
            n = len(callers) + 1
            similar = len(rest) - len(callers)
            traps = [["foreign", n + 2], ["similar", n + similar],
                     ["foreign", n + similar + 2]]
            if similar == 2:        # чужих копий тоже две: по числу их не различить
                traps = [["either", n + 2], ["foreign", n + similar + 2]]
            return {"fn": fn, "answer": n, "traps": traps}
        self._save(proj, files)
        return {"fn": fn, "answer": f"{home}:{pos + 1}"}

    def matches(self, given, ctx):
        v = variant_index(ctx.state.get("_variant"), len(self.variants))
        exp = str(ctx.state["answer"])
        if v == 1:
            return textnorm.same_number(given, exp)
        if v == 2:
            return _proj_match(given, ctx, exp)
        # FILE:LINE — можно с ./ или proj/ и с хвостом строки из вывода grep
        path, _, line = exp.rpartition(":")
        m = re.match(r"\s*(\S+?):(\d+)(?::.*)?\s*$", textnorm.clean(given or ""))
        return bool(m) and m.group(2) == line and _proj_match(m.group(1), ctx, path)

    trap_messages = {
        "foreign": "В счёт попали .git и vendor/ — это чужие копии. Отрежь их --exclude-dir.",
        "similar": "Посчитаны и похожие имена: ищи вместе со скобкой — '{fn}('.",
        "either": "Лишние файлы в счёте: или чужие копии из .git и vendor/ (отрежь их "
                  "--exclude-dir), или похожие имена (ищи вместе со скобкой — '{fn}(').",
    }

    def answer_kind(self, state):
        return ("text", "number", "path")[variant_index(state.get("_variant"), 3)]

    def wrong_message(self, given, ctx):
        if "vendor" in (given or "") or ".git" in (given or ""):
            return "Это чужая копия — из vendor/ или .git. Нужен свой код проекта."
        if (variant_index(ctx.state.get("_variant"), 3) == 0
                and re.fullmatch(r"\S+\.py", textnorm.clean(given or ""))):
            return ("Файл назван, а строки нет: нужно FILE:LINE — номер даёт grep -n, "
                    "допиши его через двоеточие.")
        return super().wrong_message(given, ctx)


class FdHunt(AnswerTask):
    id = "fd_hunt"
    track = "finder"
    title = "Перепись файлов"
    implant = "fd"
    after = ("find_name", "boss_finder")
    start_dir = PROJ
    scroll = ("find . -name '*.sql' -not -path '*/node_modules/*' -not -path '*/.*' — мимо "
              "node_modules и скрытого (имена с точки); -path сверяет маску со всем путём. "
              "find . -size +0 — только непустые.\n"
              "fd -e sql — то же отдельной программой (её ставят отдельно): по расширению (e — "
              "extension), сама мимо скрытого и .gitignore.")
    variants = (
        Variant("Сколько в проекте proj/ файлов .sql? Чужой скачанный код в node_modules и всё "
                "скрытое (файлы и папки, чьё имя начинается с точки) не считаются. Ты стоишь в "
                "proj/. Ответ — число: ans NUMBER",
                wrong=("find . -name '*.sql' | wc -l",
                       "find . -name '*.sql' -not -path '*/node_modules/*' | wc -l"),
                alternatives=("fd -e sql — и посчитать глазами",)),
        Variant("В проекте разбросаны файлы .env.example — образцы настроек. Какой из них "
                "лежит глубже всех? node_modules не в счёт. Ты стоишь в proj/. "
                "Ответ: ans PATH — путь, как его напечатает find.",
                hints=("Все образцы покажет find . -name .env.example, а node_modules отрежет "
                       "-not -path.",
                       "Глубже всех — путь, где больше всего косых /. Имя начинается с точки: "
                       "fd без -H такие файлы не видит.",
                       "find . -name .env.example -not -path '*/node_modules/*' — и выбрать "
                       "самый длинный путь; утилитой: fd -H -g .env.example"),
                solution="find . -name .env.example -not -path '*/node_modules/*', самый "
                         "глубокий путь",
                solution_script="find . -name .env.example -not -path '*/node_modules/*' | "
                                "awk -F/ '{{print NF, $0}}' | sort -n | tail -1 | cut -d' ' -f2",
                implant_script="fd -H -g .env.example | awk -F/ '{{print NF, $0}}' | sort -n | "
                               "tail -1 | cut -d' ' -f2",
                wrong=("find . -name .env.example | awk -F/ '{{print NF, $0}}' | sort -n | "
                       "tail -1 | cut -d' ' -f2",),
                alternatives=("fd -H -g .env.example — тот же список короче",)),
        Variant("Сколько непустых логов .log в проекте? Пустые (0 байт), node_modules и "
                "скрытое (имена с точки) — не в счёт. Ты стоишь в proj/. Ответ — число: "
                "ans NUMBER",
                hints=("Логи найдёт find . -name '*.log'; лишнее отрежь, как всегда: "
                       "-not -path.",
                       "-size +0 оставит только непустые файлы, | wc -l посчитает.",
                       "find . -name '*.log' -size +0 -not -path '*/node_modules/*' -not -path "
                       "'*/.*' | wc -l — утилитой: fd -e log -S +1b | wc -l"),
                solution="find . -name '*.log' -size +0 -not -path '*/node_modules/*' "
                         "-not -path '*/.*' | wc -l",
                implant_script="fd -e log -S +1b | wc -l",
                wrong=("find . -name '*.log' -not -path '*/node_modules/*' -not -path '*/.*' "
                       "| wc -l",
                       "find . -name '*.log' -size +0 | wc -l"),
                alternatives=("find . -name '*.log' -not -empty … — то же, что -size +0",)),
    )
    par = 60
    hints = ("По имени ищет find; маску '*.sql' бери в кавычки.",
             "Лишнее отрежь: -not -path '*/node_modules/*' -not -path '*/.*'; посчитает | wc -l.",
             "find . -name '*.sql' -not -path '*/node_modules/*' -not -path '*/.*' | wc -l — "
             "утилитой: fd -e sql | wc -l")
    solution = "find . -name '*.sql' -not -path '*/node_modules/*' -not -path '*/.*' | wc -l"
    implant_script = "fd -e sql | wc -l"
    explain = ("find видит всё: и node_modules, и скрытое — лишнее режут -not -path. fd по "
               "умолчанию пропускает скрытое и .gitignore, -H возвращает скрытое.")
    spell = "find . -name '*.x' -not -path '*/node_modules/*' — искать мимо чужих пакетов"

    def setup_variant(self, box, rng, variant):
        proj = box / PROJ
        _git_project(proj, rng, "node_modules/\n")
        pkgs = rng.sample(kit.LATIN, 3)
        nm = proj / "node_modules"
        # .sql: свои, скрытые (файл и папка), в node_modules, и похожие, но не .sql
        own = rng.randint(4, 9)
        for i in range(own):
            d = rng.choice(["db/migrations", "db/seeds", "scripts", f"db/{pkgs[0]}"])
            kit.write(proj / d / f"{i:03d}_{kit.latin(rng)}.sql", "-- migration\n")
        kit.write(proj / "db" / ".draft.sql", "-- draft\n")
        kit.write(proj / ".cache" / f"q_{kit.latin(rng)}.sql", "-- cache\n")
        for p in pkgs:
            kit.write(nm / p / "sql" / f"{kit.latin(rng)}.sql", "-- package\n")
        kit.write(proj / "db" / "dump.sql.gz", "not sql\n")
        kit.write(proj / "docs" / "sql_notes.txt", "notes\n")
        # .env.example: две мельче и одна глубже всех (ответ); в node_modules — ещё глубже
        deep = rng.randint(4, 5)
        target = ""
        for depth in sorted(rng.sample(range(0, deep), 2)) + [deep]:
            dirs = ["services"] + [f"{kit.latin(rng)}_{depth}{k}" for k in range(depth - 1)]
            target = "/".join(dirs[:depth] + [".env.example"])
            kit.write(proj / target, "PORT=8080\n")
        kit.write(nm / pkgs[1] / "examples" / "a" / "b" / "c" / "d" / ".env.example", "X=1\n")
        # .log: непустые и пустые свои, непустые в node_modules, в .cache и скрытый файл
        full = rng.randint(3, 7)
        for i in range(full):
            kit.write(proj / "logs" / rng.choice(["", "archive", "jobs"]) / f"run_{i}.log",
                      f"run {i}: ok\n")
        for i in range(rng.randint(1, 3)):
            kit.write(proj / "logs" / f"empty_{i}.log", "")
        kit.write(nm / pkgs[2] / "npm-debug.log", "error\n")
        kit.write(proj / ".cache" / "old.log", "old\n")
        kit.write(proj / "logs" / ".last.log", "latest\n")
        if variant == 1:
            nm_env = f"node_modules/{pkgs[1]}/examples/a/b/c/d/.env.example"
            return {"answer": target, "traps": [["deep_nm", f"{PROJ}/{nm_env}"]]}
        if variant == 2:
            empties = sum(1 for p in (proj / "logs").glob("empty_*.log"))
            return {"answer": full, "traps": [["empty", full + empties],
                                              ["all", full + empties + 3],
                                              ["empty", full + 3]]}
        return {"answer": own, "traps": [["all", own + 2 + len(pkgs)], ["nm", own + 2],
                                         ["hidden", own + len(pkgs)]]}

    trap_messages = {
        "all": "В счёт попали node_modules и скрытое — отрежь их: -not -path.",
        "nm": "node_modules отрезан, а скрытое — нет: ещё -not -path '*/.*'.",
        "hidden": "Скрытое отрезано, а node_modules — нет: ещё -not -path '*/node_modules/*'.",
        "empty": "В счёт попали пустые логи: -size +0 оставит только непустые.",
        "deep_nm": "Это образец из node_modules — чужой скачанный код, он не в счёт.",
    }

    def answer_kind(self, state):
        return "path" if variant_index(state.get("_variant"), 3) == 1 else "number"

    def matches(self, given, ctx):
        if variant_index(ctx.state.get("_variant"), len(self.variants)) == 1:
            return _proj_match(given, ctx, str(ctx.state["answer"]))
        return textnorm.same_number(given, ctx.state["answer"])


class BossFinder(Task):
    id = "boss_finder"
    track = "finder"
    title = "Уборка Загрузок"
    boss = True
    par = 360
    scroll = ("Пробел и скобки в имени экранируй (поставь \\ перед знаком) или бери в кавычки: "
              "rm Downloads/*\\ \\(1\\).* или rm Downloads/*' (1).'*\n"
              "find DIR -type f -empty -delete — удалить пустые файлы, -type d -empty — папки. "
              "ls -S — тяжёлые сверху. COMMAND > FILE — вывод в файл.\n"
              "Без учёта регистра (zsh): setopt extendedglob, потом *.(#i)(jpg|png) — "
              "(a|b) значит «a или b»; *(.) — только файлы, без папок.")
    steps = ("удалить все пустые файлы (нулевого размера)",
             "удалить дубли «имя (1).расширение» (они точные копии)",
             "разложить всё по папкам pictures, documents, tables, other — в корне Downloads "
             "ни одного файла",
             "имя самого тяжёлого файла записать в biggest.txt (рядом с Downloads)")
    variants = (
        Variant("Папка Downloads разрослась: пустые файлы, дубли «(1)», всё вперемешку. "
                "Картинки (jpg, jpeg, png, heic — любым регистром) — в pictures, документы "
                "(pdf, docx, txt) — в documents, таблицы (csv, xlsx) — в tables, остальное — "
                "в other. Имя самого тяжёлого файла запиши в biggest.txt рядом с Downloads (можно "
                "и путь к нему).",
                wrong=("rm Downloads/*(1)*",),
                alternatives=("ls -S Downloads/**/*(.) | head -1 — тяжёлый ищется по всем "
                              "вложенным папкам разом",)),
        Variant("Загрузки забиты мусором браузера. Правила уборки: недокачанные *.crdownload — "
                "стереть везде, и во вложенных папках тоже; дубли «имя copy.расширение» — стереть, "
                "это точные копии; пустые папки — убрать. Остальное не трогать. Имя самого "
                "тяжёлого из оставшихся файлов запиши в biggest.txt рядом с Downloads (можно и путь "
                "к нему).",
                hints=("Иди по шагам: недокачанные — find Downloads -name '*.crdownload' -delete; "
                       "дубли — rm Downloads/*\\ copy.*",
                       "Пустые папки — find Downloads -type d -empty -delete. Недокачанные сотри "
                       "раньше: после них опустеют и папки.",
                       "Самый тяжёлый: ls -S Downloads/**/*(.) | head -1 > biggest.txt"),
                solution=("find Downloads -name '*.crdownload' -delete; rm Downloads/*\\ copy.*; "
                          "find Downloads -type d -empty -delete; "
                          "ls -S Downloads/**/*(.) | head -1 > biggest.txt"),
                solution_script="\n".join([
                    "cd Downloads",
                    "find . -name '*.crdownload' -delete",
                    "rm -f -- *\\ copy.*(N)",
                    "find . -type d -empty -delete",
                    "cd ..",
                    "ls -S Downloads/**/*(.) | head -1 | xargs basename > biggest.txt",
                ]),
                wrong=("\n".join([
                    "cd Downloads",
                    "find . -name '*.crdownload' -delete",
                    "rm -f -- *copy*(N)",
                    "find . -type d -empty -delete",
                    "cd ..",
                    "ls -S Downloads/**/*(.) | head -1 | xargs basename > biggest.txt",
                ]),),
                alternatives=("rm Downloads/**/*.crdownload — то же, что find -delete, "
                              "маской zsh",)),
        Variant("Загрузки после фотосессии: снимки вперемешку с документами. Убери дубли «(1)» "
                "и пустые файлы, все снимки (jpg, jpeg, png, heic — любым регистром) перенеси в "
                "папку photos, а все остальные файлы оставь в Downloads как есть. Имя самого "
                "тяжёлого СНИМКА запиши в biggest.txt рядом с Downloads (можно и путь к нему).",
                hints=("Иди по шагам: дубли — rm Downloads/*\\ \\(1\\).*; пустые — "
                       "find Downloads -type f -empty -delete",
                       "Сначала mkdir Downloads/photos. Регистр расширений разный — маска без учёта "
                       "регистра: setopt extendedglob, потом mv Downloads/*.(#i)(jpg|jpeg|png|heic)"
                       " Downloads/photos/",
                       "Самый тяжёлый снимок: ls -S Downloads/photos | head -1 > biggest.txt"),
                solution=("setopt extendedglob; "
                          "rm Downloads/*\\ \\(1\\).*; find Downloads -type f -empty -delete; "
                          "mkdir Downloads/photos; mv Downloads/*.(#i)(jpg|jpeg|png|heic) "
                          "Downloads/photos/; ls -S Downloads/photos | head -1 > biggest.txt"),
                solution_script="\n".join([
                    "setopt extendedglob",
                    "cd Downloads",
                    "rm -f -- *\\ \\(1\\).*(N)",
                    "find . -type f -empty -delete",
                    "mkdir -p photos",
                    "mv -- *.(#i)(jpg|jpeg|png|heic)(N) photos/",
                    "cd ..",
                    "ls -S Downloads/photos/*(.) | head -1 | xargs basename > biggest.txt",
                ]),
                wrong=("\n".join([
                    "cd Downloads",
                    "rm -f -- *\\ \\(1\\).*(N)",
                    "find . -type f -empty -delete",
                    "mkdir -p photos",
                    "mv -- *.(jpg|jpeg|png|heic)(N) photos/",
                    "cd ..",
                    "ls -S Downloads/photos/*(.) | head -1 | xargs basename > biggest.txt",
                ]), "\n".join([
                    "setopt extendedglob",
                    "cd Downloads",
                    "rm -f -- *\\ \\(1\\).*(N)",
                    "find . -type f -empty -delete",
                    "mkdir -p photos",
                    "mv -- *.(#i)(jpg|jpeg|png|heic)(N) photos/",
                    "cd ..",
                    "ls -S Downloads/**/*(.) | head -1 | xargs basename > biggest.txt",
                ])),
                alternatives=("ls -S Downloads/photos | head -1 — посмотреть имя, потом echo "
                              "и это имя > biggest.txt",)),
    )
    hints = ("Иди по шагам: пустые — find Downloads -type f -empty -delete; "
             "дубли — rm Downloads/*\\ \\(1\\).*",
             "Разложить: mkdir нужные папки и mv по маскам. Маска без учёта регистра в zsh: "
             "setopt extendedglob, потом *.(#i)(jpg|jpeg|png|heic)",
             "Самый тяжёлый: ls -S Downloads/*/* | head -1 > biggest.txt")
    solution = ("find Downloads -type f -empty -delete; rm Downloads/*\\ \\(1\\).*; "
                "mkdir + mv по маскам *.(#i)(jpg|png|…); ls -S Downloads/*/* | head -1 > biggest.txt")
    solution_script = "\n".join([
        "setopt extendedglob",
        "cd Downloads",
        "find . -type f -empty -delete",
        "rm -f -- *\\ \\(1\\).*(N)",
        "mkdir -p pictures documents tables other",
        "mv -- *.(#i)(jpg|jpeg|png|heic)(N) pictures/",
        "mv -- *.(#i)(pdf|docx|txt)(N) documents/",
        "mv -- *.(#i)(csv|xlsx)(N) tables/",
        "mv -- *(.N) other/",
        "cd ..",
        "ls -S Downloads/*/*(.) | head -1 | xargs basename > biggest.txt",
    ])
    explain = ("find -empty находит пустые, маски с (#i) не смотрят на регистр, ls -S сортирует "
               "по размеру — вместе это генеральная уборка Загрузок за минуту.")
    spell = "find -empty -delete; mv *.(#i)jpg DIR/ (zsh); ls -S — самые тяжёлые сверху"

    # шаги под вариант (общие steps — для шпаргалки и T002)
    MODE_STEPS = (
        None,
        ("стереть все недокачанные *.crdownload — и во вложенных папках",
         "стереть дубли «имя copy.расширение» (они точные копии)",
         "убрать пустые папки",
         "имя самого тяжёлого файла записать в biggest.txt (рядом с Downloads)"),
        ("удалить дубли «имя (1).расширение» (они точные копии)",
         "удалить все пустые файлы (нулевого размера)",
         "все снимки (jpg, jpeg, png, heic — любым регистром) — в photos, остальное оставить "
         "в Downloads",
         "имя самого тяжёлого снимка записать в biggest.txt (рядом с Downloads)"),
    )

    def steps_for(self, state):
        steps = self.MODE_STEPS[variant_index(state.get("_variant", 0), len(self.MODE_STEPS))]
        return list(steps or self.steps)

    def setup_variant(self, box, rng, variant):
        dl = box / "Downloads"
        dl.mkdir()
        used = set()

        def unique(name):
            while name.lower() in used:
                stem, ext = name.rsplit(".", 1)
                name = f"{stem}_{rng.randint(10, 99)}.{ext}"
            used.add(name.lower())
            return name

        stems = ["IMG_{n}", "Scan 2726-09-{d}", "statement {n}", "report_{n}",
                 "Screenshot {n}", "contract_{n}", "track_{n}"]

        def stem_name(exts):
            stem = rng.choice(stems).format(n=rng.randint(1000, 9999), d=rng.randint(10, 28))
            return unique(f"{stem}.{rng.choice(exts)}")

        if variant == 1:
            return self._setup_crdl(box, dl, rng, unique, stem_name)
        if variant == 2:
            return self._setup_mix(box, dl, rng, unique, stem_name)
        keep = {}
        for _ in range(rng.randint(90, 110)):
            name = stem_name(PIC + DOC + TAB + OTHER)
            kit.write_random(dl / name, rng.randint(1_000, 60_000), rng)
            keep[name] = folder_for(name)
        for name in rng.sample(sorted(keep), rng.randint(12, 18)):
            stem, ext = name.rsplit(".", 1)
            shutil.copyfile(dl / name, dl / f"{stem} (1).{ext}")
        for i in range(rng.randint(8, 12)):
            (dl / unique(f"empty_{i}.{rng.choice(DOC + OTHER)}")).touch()
        heavy = unique(f"video_{rng.randint(1000, 9999)}.mov")
        kit.write_random(dl / heavy, rng.randint(3_000_000, 5_000_000), rng)
        keep[heavy] = "other"
        return {"keep": keep, "heavy": heavy}

    def _setup_crdl(self, box, dl, rng, unique, stem_name):
        keep, crdl, top = {}, [], []
        for _ in range(rng.randint(40, 55)):
            name = stem_name(PIC + DOC + TAB + OTHER)
            p = kit.write_random(dl / name, rng.randint(1_000, 60_000), rng)
            keep[str(p.relative_to(box))] = kit.sha(p)
            top.append(name)
        for name in (unique(f"photocopy_{rng.randint(100, 999)}.pdf"),
                     unique(f"copywriting_{rng.randint(100, 999)}.docx")):
            p = kit.write_random(dl / name, rng.randint(1_000, 20_000), rng)     # «copy» без пробела
            keep[str(p.relative_to(box))] = kit.sha(p)
        for name in rng.sample(top, rng.randint(5, 8)):
            stem, ext = name.rsplit(".", 1)
            shutil.copyfile(dl / name, dl / f"{stem} copy.{ext}")
        project = dl / f"project_{rng.randint(10, 99)}"
        for i in range(rng.randint(2, 4)):
            p = kit.write_random(project / f"{kit.latin(rng)}_{i}.txt", rng.randint(500, 5_000), rng)
            keep[str(p.relative_to(box))] = kit.sha(p)
        targets = [dl, dl, dl, project, dl / f"download_{rng.randint(10, 99)}"]
        for i, d in enumerate(targets):
            name = stem_name(DOC + OTHER) + ".crdownload"
            size = rng.randint(6_000_000, 7_000_000) if i == 0 else rng.randint(5_000, 400_000)
            p = kit.write_random(d / name, size, rng)       # первый — тяжелее всех
            crdl.append(str(p.relative_to(box)))
        for rel in ("blank", "old/empty", f"old/{kit.latin(rng)}"):
            (dl / rel).mkdir(parents=True, exist_ok=True)
        heavy = unique(f"video_{rng.randint(1000, 9999)}.mov")
        p = kit.write_random(dl / heavy, rng.randint(3_000_000, 5_000_000), rng)
        keep[str(p.relative_to(box))] = kit.sha(p)
        return {"mode": "crdl", "keep": keep, "heavy": heavy, "crdl": crdl}

    def _setup_mix(self, box, dl, rng, unique, stem_name):
        pics = ["jpg", "JPG", "jpeg", "Jpeg", "png", "PNG", "heic", "HEIC"]
        keep = {}
        for _ in range(rng.randint(45, 60)):
            name = stem_name(pics + DOC + TAB + OTHER)
            kit.write_random(dl / name, rng.randint(1_000, 60_000), rng)
            keep[name] = "photos" if folder_for(name) == "pictures" else ""
        for name in rng.sample(sorted(keep), rng.randint(8, 12)):
            stem, ext = name.rsplit(".", 1)
            shutil.copyfile(dl / name, dl / f"{stem} (1).{ext}")
        for i in range(rng.randint(5, 8)):     # пустышки — и с расширением снимка
            ext = "JPG" if i == 0 else rng.choice(pics + DOC)
            (dl / unique(f"empty_{i}.{ext}")).touch()
        heavy = unique(f"IMG_{rng.randint(1000, 9999)}.HEIC")
        kit.write_random(dl / heavy, rng.randint(2_000_000, 3_000_000), rng)
        keep[heavy] = "photos"
        video = unique(f"video_{rng.randint(1000, 9999)}.mov")       # тяжелее, но не снимок
        kit.write_random(dl / video, rng.randint(4_000_000, 5_000_000), rng)
        keep[video] = ""
        return {"mode": "mix", "keep": keep, "heavy": heavy}

    def _named(self, ctx) -> bool:
        biggest = ctx.box / "biggest.txt"
        return biggest.is_file() and Path(
            biggest.read_text("utf-8", errors="replace").strip()).name == ctx.state["heavy"]

    def progress(self, ctx):
        dl = ctx.box / "Downloads"
        if not dl.is_dir():
            return [False, False, False, False]
        files = [p for p in dl.rglob("*") if p.is_file() and p.name != ".DS_Store"]
        mode = ctx.state.get("mode", "sort")        # старый task.json варианта A — без mode
        if mode == "crdl":
            dirs = [d for d in dl.rglob("*") if d.is_dir()]
            return [not any(p.name.endswith(".crdownload") for p in files),
                    not any(" copy." in p.name for p in files),
                    not any(not any(d.iterdir()) for d in dirs),
                    self._named(ctx)]
        if mode == "mix":
            placed = {p.name: ("" if p.parent == dl else p.parent.name) for p in files}
            return [not any(" (1)." in p.name for p in files),
                    all(p.stat().st_size > 0 for p in files),
                    placed == ctx.state["keep"],
                    self._named(ctx)]
        placed = {p.name: p.parent.name for p in files if p.parent != dl}
        return [all(p.stat().st_size > 0 for p in files),
                not any(" (1)." in p.name for p in files),
                not any(p.parent == dl for p in files) and placed == ctx.state["keep"],
                self._named(ctx)]

    def check(self, ctx):
        done = all(self.progress(ctx))
        if ctx.state.get("mode") == "crdl":
            lost = sorted(Path(rel).name for rel, h in ctx.state["keep"].items()
                          if not (ctx.box / rel).is_file() or kit.sha(ctx.box / rel) != h)
            if lost:
                return Verdict(False, "Пропали файлы, которые надо было оставить: " +
                               ", ".join(lost[:3]) + ("…" if len(lost) > 3 else "") +
                               ". Набери reset и бей точнее.")
        return Verdict(done)


# трио «Вместо Excel» (I8) — в своём модуле; временно в этом треке (журнал решений, п. 7)
from termit_app.tasks import sheets  # noqa: E402

TASKS = [OpenGui(), FindName(), GrepR(), DuHeavy(), LsNewest(), RecentMove(), BatchRename(),
         ZipPack(), PbcopyList(), KillFrozen(), TopHog(), DiskSweep(), DupSort(), RgHunt(), FdHunt(),
         *sheets.TASKS, BossFinder()]
