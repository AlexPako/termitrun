"""FB3 (6): копилка расширений. Расширение — хвост имени после последней точки (notes.txt →
.txt): договорённость для людей и программ, а не «тип» сам по себе. Копилка пополняется, когда
в песочнице задания впервые встречается файл с новым расширением; показывает её команда ext
(в задаче) и ./termit ext. Описания — только здесь, одним словарём; полноту по файлам задач
сторожит tests/test_fb3_teach."""
import os
import re
import textwrap
from pathlib import Path
from typing import Dict, Iterable, List

from termit_app import tui

# расширение → (группа, что внутри и где встречается). Одна строка, без сюжета.
EXTENSIONS: Dict[str, tuple] = {
    # текст
    ".txt": ("текст", "простой текст без оформления — заметки, записки, списки"),
    ".md": ("текст", "текст с простой разметкой Markdown (# заголовок, *курсив*) — README, "
                     "заметки, документация"),
    # данные
    ".csv": ("данные", "таблица: строка — запись, поля через запятую; открывают Excel и "
                       "Numbers, читают скрипты"),
    ".json": ("данные", "данные в фигурных и квадратных скобках — конфиги программ, ответы "
                        "веб-сервисов"),
    ".xml": ("данные", "данные в тегах <тег>…</тег> — старые конфиги, выгрузки, офисные "
                       "форматы изнутри"),
    ".yaml": ("данные", "данные отступами (ключ: значение) — конфиги серверов и программ"),
    ".yml": ("данные", "то же, что .yaml, короткое написание"),
    ".dat": ("данные", "«какие-то данные» программы — что внутри, знает только она (file "
                       "подскажет)"),
    ".db": ("данные", "база данных (чаще всего SQLite) — открывает sqlite3, а не cat"),
    ".sql": ("данные", "текст команд SQL — запросы и схемы баз; его скармливают sqlite3 и "
                       "psql"),
    # логи и временное
    ".log": ("логи", "журнал программы: строка — событие со временем; читают tail, less, grep"),
    ".tmp": ("временное", "временный файл — программа его бросила; обычно можно удалить"),
    ".bak": ("временное", "резервная копия (backup) — старая версия файла на всякий случай"),
    ".old": ("временное", "старая версия файла, оставленная рядом с новой"),
    ".part": ("временное", "недокачанный файл: загрузка оборвалась, целиком его нет"),
    # скрипты и код
    ".sh": ("код", "скрипт оболочки: команды терминала подряд; запуск — ./имя.sh"),
    ".zsh": ("код", "скрипт для zsh — та же оболочка, что в игре"),
    ".py": ("код", "программа на Python — запуск python3 имя.py"),
    ".js": ("код", "программа на JavaScript — сайты в браузере и node в терминале"),
    # конфиги и ключи
    ".conf": ("конфиг", "настройки программы, обычно «ключ = значение»; правят nano или vim"),
    ".ini": ("конфиг", "настройки по разделам [раздел] и строкам ключ=значение"),
    ".env": ("конфиг", "переменные окружения и секреты (пароли, ключи) — в чужие руки не "
                       "отдают"),
    ".toml": ("конфиг", "настройки в виде ключ = значение по разделам — проекты Python и Rust"),
    ".key": ("конфиг", "секретный ключ шифрования — его не показывают и не пересылают"),
    ".cert": ("конфиг", "сертификат: открытая часть ключа, подтверждает, кто есть кто"),
    ".sock": ("служебное", "сокет — не файл с текстом, а «дверь» для связи программ; cat его "
                           "не прочтёт"),
    # архивы
    ".zip": ("архив", "архив zip — много файлов в одном, сжатых; Finder открывает двойным "
                      "щелчком, терминал — unzip"),
    ".tar": ("архив", "архив tar — файлы склеены в один, без сжатия; распаковка tar -xf"),
    ".gz": ("архив", "сжатый gzip файл; .tar.gz — архив tar, сжатый gzip (tar -xzf)"),
    ".dmg": ("архив", "образ диска macOS — так раздают программы для Mac"),
    # документы
    ".pdf": ("документ", "документ для чтения и печати — Preview; cat покажет мусор"),
    ".docx": ("документ", "документ Word; внутри — zip с XML, cat покажет мусор"),
    ".xlsx": ("документ", "таблица Excel; внутри — zip с XML, для скрипта удобнее .csv"),
    # картинки, звук, видео
    ".png": ("медиа", "картинка без потерь качества — скриншоты, схемы"),
    ".jpg": ("медиа", "фотография, сжатая с небольшой потерей качества"),
    ".jpeg": ("медиа", "то же, что .jpg, длинное написание"),
    ".heic": ("медиа", "фото с iPhone в формате Apple — меньше .jpg при том же качестве"),
    ".mp3": ("медиа", "звук, музыка"),
    ".wav": ("медиа", "звук без сжатия — большой файл"),
    ".mp4": ("медиа", "видео"),
    ".mov": ("медиа", "видео в формате Apple — так снимает iPhone"),
    ".hsb": ("служебное", "база сигнатур антивируса ClamAV: отпечатки известных вредных "
                          "файлов"),
    # прочее
    ".bin": ("прочее", "двоичные данные «как есть» — прошивки, дампы; cat покажет мусор"),
    ".fake": ("прочее", "такого общепринятого расширения нет: имя может быть любым — что "
                        "внутри на самом деле, скажет file"),
}

NOTE_LIMIT = 3          # строк «в копилку» на одной карточке; остальное — «и ещё N»
_SCAN_LIMIT = 5000      # больше файлов в песочнице не смотрим: копилке хватит и этого
_EXT_RE = re.compile(r"\.[a-z][a-z0-9]{0,5}$")
SKIP_DIRS = {"venv", ".venv", "site-packages", "node_modules", "__pycache__"}


def ext_of(name: str) -> str:
    """Расширение имени в нижнем регистре или "" — у скрытого .secret расширения нет."""
    if name.startswith(".") and name.count(".") == 1:
        return ""
    m = _EXT_RE.search(name.lower())
    return m.group(0) if m else ""


def scan(box) -> List[str]:
    """Расширения файлов песочницы (и её дома), известные копилке, — по алфавиту.
    Служебная .termit (кроме дома) не смотрится: там файлы игры, а не задания."""
    box = Path(box)
    found = set()
    count = 0
    for root, dirs, files in os.walk(box):
        rel = Path(root).relative_to(box).parts
        if rel == (".termit",):                 # служебная папка: только дом
            dirs[:] = [d for d in dirs if d == "home"]
            continue
        if rel[:1] == (".termit",) and rel[1:2] != ("home",):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            count += 1
            ext = ext_of(name)
            if ext in EXTENSIONS:
                found.add(ext)
        if count > _SCAN_LIMIT:
            break
    return sorted(found)


def collect(p: dict, box) -> List[str]:
    """Новые для игрока расширения этой песочницы — в p["extensions"]; возвращает новые."""
    seen = p.setdefault("extensions", [])
    new = [e for e in scan(box) if e not in seen]
    seen.extend(new)
    return new


def describe(ext: str) -> str:
    return f"{ext} — {EXTENSIONS[ext][1]}"


def notes(new: Iterable[str]) -> List[str]:
    """Строки уведомления «в копилку» для карточки задачи."""
    new = list(new)
    lines = [f"📎 В копилку расширений: {describe(e)}" for e in new[:NOTE_LIMIT]]
    if len(new) > NOTE_LIMIT:
        rest = ", ".join(new[NOTE_LIMIT:])
        lines.append(f"📎 И ещё: {rest}")
    if lines:
        lines.append("   Вся копилка — набери ext.")
    return lines


HEAD = ("Копилка расширений. Расширение — хвост имени после точки (notes.txt → .txt): "
        "подсказка людям и программам, что внутри. Finder по нему выбирает, чем открыть, а "
        "терминалу всё равно — cat напечатает любой файл. Имя без расширения — другое имя: "
        "при файле notes.txt команда cat notes ответит No such file or directory. Что внутри "
        "на самом деле, скажет file ИМЯ.")


def sheet(seen: Iterable[str]) -> str:
    """Текст копилки: встреченные расширения по группам, в порядке словаря."""
    seen = set(seen)
    rows = [textwrap.fill(HEAD, tui.text_width(), break_long_words=False, break_on_hyphens=False), ""]
    if not seen:
        rows.append("Пока пусто: копилка пополняется сама, когда в задании встречается файл с "
                    "новым расширением.")
        return "\n".join(rows)
    group = None
    for ext, (kind, _) in EXTENSIONS.items():
        if ext not in seen:
            continue
        if kind != group:
            group = kind
            rows.append(f"{kind.capitalize()}:")
        rows.append(textwrap.fill(describe(ext), tui.text_width(), initial_indent="  ",
                                  subsequent_indent="        ", break_long_words=False,
                                  break_on_hyphens=False))
    left = len(EXTENSIONS) - len(seen & set(EXTENSIONS))
    if left:
        rows.append("")
        rows.append(f"Ещё не встречено: {left}.")
    return "\n".join(rows)


BOX_FILE = ".termit/extensions"     # копилка для команды ext внутри песочницы — по строке


def box_text(seen: Iterable[str]) -> str:
    return "\n".join(e for e in seen if e in EXTENSIONS) + "\n"


def read_box(box) -> List[str]:
    try:
        text = (Path(box) / BOX_FILE).read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip() in EXTENSIONS]
