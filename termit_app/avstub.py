"""Учебный clamscan песочницы: python -I … termit_app.avstub АРГУМЕНТЫ (часть 7, A6).

Обёртка .termit/bin/clamscan есть только у задач с uses_av = True (настоящий ClamAV в
других задачах не перекрываем). Повторяет вывод ClamAV на урезанных настоящих форматах баз:
- .hsb — «sha256:размер:Имя» (по длине хэша годится и sha1);
- .hdb — «md5:размер:Имя»;
- .ndb — «Имя:0:*:hex» (?? — любой байт); другие типы цели и смещения — ошибка строки.
Размер в hsb/hdb — число или «*». Пустые строки и строки с «#» пропускаются. Плохая строка
базы — «LibClamAV Error: …» в stderr, и, как у настоящего ClamAV, вся база отвергнута: проверки
нет, код 2. По умолчанию база ~/av/main.hsb.

Ключи: -r/--recursive, -i/--infected, -d/--database БАЗА (можно несколько, можно папку),
--no-summary, -V/--version, -h/--help. Коды: 0 — чисто, 1 — найдено, 2 — ошибки.
Ничего не исполняет и не качает: только читает файлы. Файлы больше 4 МБ и не обычные файлы
пропускаются, симлинки не обходятся. Пометка «учебный clamscan: без сети» — в stderr (stdout
как у настоящего). Каждый вызов пишется в .termit/av.log (подделку проверка терпит: по нему
одному решение не засчитывается). Строки EICAR здесь нет: тестовый образец назван только
словами в уроке."""
import hashlib
import json
import os
import re
import stat
import sys
import time
from typing import List, Optional, Tuple

NOTE = "(учебный clamscan: без сети)"
LOG = "av.log"
MAX_FILE = 4 * 1024 * 1024          # файлы больше — мимо (как --max-filesize)
MAX_DB = 4 * 1024 * 1024            # база больше — не читаем
DEFAULT_DB = os.path.join("av", "main.hsb")     # от $HOME (дом песочницы)
VERSION = "ClamAV 1.4.3/учебная база"
DB_EXT = (".hsb", ".hdb", ".ndb")
_NAME = re.compile(r"^[A-Za-z0-9_.+-]{1,64}$")
_HEX = re.compile(r"^(?:[0-9a-fA-F]{2}|\?\?)+$")

USAGE = """Usage: clamscan [options] [file/directory/-]

    --help                -h             Show this help
    --version             -V             Print version number
    --database=FILE/DIR   -d FILE/DIR    Load virus database from FILE or load all
                                         supported db files from DIR
    --recursive           -r             Scan subdirectories recursively
    --infected            -i             Only print infected files
    --no-summary                         Disable summary at end of scanning
"""


class Usage(Exception):
    pass


def _err(text: str) -> None:
    print(text, file=sys.stderr)


def _read(path: str, cap: int) -> Optional[bytes]:
    """Обычный файл не больше cap, без симлинка в последнем звене и без зависания на FIFO."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            return None
        chunks, left = [], cap + 1
        while left > 0:
            chunk = os.read(fd, min(left, 1 << 16))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        data = b"".join(chunks)
        return data if len(data) <= cap else None
    except OSError:
        return None
    finally:
        os.close(fd)


def parse_hash_line(line: str, algo: Optional[str] = None):
    """Строка .hsb (algo None: sha256 или sha1 по длине) или .hdb (algo "md5"):
    ((алгоритм, хэш, размер или None, имя), None) или (None, причина как у LibClamAV). Тот же
    разбор берёт родитель, проверяя свою базу игрока (E14): только текст, без исполнения."""
    parts = line.strip().split(":")
    if len(parts) != 3:
        return None, "Malformed hash string"
    h, size, name = parts
    h = h.lower()
    lengths = {"md5": 32} if algo == "md5" else {"sha256": 64, "sha1": 40}
    algo = next((a for a, ln in lengths.items() if len(h) == ln), None)
    if algo is None or not re.fullmatch(r"[0-9a-f]+", h):
        return None, "Malformed hash string"
    if size != "*" and not size.isdigit():
        return None, "Malformed file size"
    if not _NAME.match(name):
        return None, "Malformed virus name"
    return (algo, h, None if size == "*" else int(size), name), None


def parse_hsb(text: str):
    """Текст базы .hsb: ([(алгоритм, хэш, размер, имя)], [(номер строки, строка, причина)]).
    Пустые строки и # — мимо; разбор по строкам, линейный."""
    entries, problems = [], []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entry, why = parse_hash_line(line)
        if entry is None:
            problems.append((n, line, why))
        else:
            entries.append(entry)
    return entries, problems


class Db:
    """Загруженные сигнатуры: хэши (алгоритм, хэш, размер или None, имя) и шаблоны ndb."""

    def __init__(self):
        self.hashes: List[Tuple[str, str, Optional[int], str]] = []
        self.patterns: List[Tuple["re.Pattern", str]] = []
        self.errors = 0

    @property
    def count(self) -> int:
        return len(self.hashes) + len(self.patterns)

    def _bad(self, func: str, path: str, n: int, why: str) -> None:
        self.errors += 1
        _err(f"LibClamAV Error: {func}: {why} at line {n} in {path}")

    def load(self, path: str) -> bool:
        """База-файл или папка с базами. Нет или не прочесть — False (ошибка уже в stderr)."""
        if os.path.isdir(path) and not os.path.islink(path):
            names = sorted(n for n in os.listdir(path) if n.endswith(DB_EXT))
            if not names:
                _err(f"LibClamAV Error: cli_loaddbdir: No supported database files found in {path}")
                return False
            return all([self.load(os.path.join(path, n)) for n in names])
        ext = os.path.splitext(path)[1]
        if ext not in DB_EXT:
            _err(f"LibClamAV Error: cli_load: Not supported database file {path}")
            return False
        data = _read(path, MAX_DB)
        if data is None:
            _err(f"LibClamAV Error: cl_load(): Can't get status of {path}")
            return False
        text = data.decode("utf-8", errors="replace")
        before = self.errors
        hashes, patterns = len(self.hashes), len(self.patterns)
        for n, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ext == ".ndb":
                self._ndb(line, path, n)
            else:
                self._hash(line, path, n, "md5" if ext == ".hdb" else None)
            if self.errors > before:
                # как настоящий ClamAV: одна сломанная строка — вся база отвергнута
                del self.hashes[hashes:], self.patterns[patterns:]
                _err(f"LibClamAV Error: cli_load(): Malformed database file {path}")
                return False
        return True

    def _hash(self, line: str, path: str, n: int, algo: Optional[str]) -> None:
        entry, why = parse_hash_line(line, algo)
        if entry is None:
            return self._bad("cli_loadhash", path, n, why)
        self.hashes.append(entry)

    def _ndb(self, line: str, path: str, n: int) -> None:
        parts = line.split(":")
        if len(parts) != 4:
            return self._bad("cli_loadndb", path, n, "Malformed database line")
        name, target, offset, sig = parts
        if not _NAME.match(name):
            return self._bad("cli_loadndb", path, n, "Malformed virus name")
        if target != "0" or offset != "*":
            return self._bad("cli_loadndb", path, n, "Unsupported target type or offset")
        if not _HEX.match(sig) or len(sig) < 4:
            return self._bad("cli_loadndb", path, n, "Malformed hex signature")
        pieces = [b"." if sig[i:i + 2] == "??" else re.escape(bytes.fromhex(sig[i:i + 2]))
                  for i in range(0, len(sig), 2)]
        self.patterns.append((re.compile(b"".join(pieces), re.S), name))

    def match(self, data: bytes) -> Optional[str]:
        digests = {}
        for algo, h, size, name in self.hashes:
            if size is not None and size != len(data):
                continue
            if algo not in digests:
                digests[algo] = hashlib.new(algo, data).hexdigest()
            if digests[algo] == h:
                return name
        for rx, name in self.patterns:
            if rx.search(data):
                return name
        return None


class Scan:
    def __init__(self, db: Db, recursive: bool, infected_only: bool):
        self.db, self.recursive, self.infected_only = db, recursive, infected_only
        self.dirs = self.files = self.found = self.errors = 0
        self.bytes = 0

    def say(self, path: str, what: str, infected: bool = False) -> None:
        if infected or not self.infected_only:
            print(f"{path}: {what}")

    def file(self, path: str) -> None:
        try:
            st = os.lstat(path)
        except OSError:
            self.errors += 1
            self.say(path, "No such file or directory")
            return
        if stat.S_ISLNK(st.st_mode):
            self.say(path, "Symbolic link")
            return
        if not stat.S_ISREG(st.st_mode):
            self.say(path, "Excluded (not a regular file)")
            return
        if st.st_size > MAX_FILE:
            self.say(path, "Excluded (larger than 4 MB)")
            return
        data = _read(path, MAX_FILE)
        if data is None:
            self.errors += 1
            self.say(path, "Can't read file")
            return
        self.files += 1
        self.bytes += len(data)
        name = self.db.match(data)
        if name:
            self.found += 1
            self.say(path, f"{name} FOUND", infected=True)
        else:
            self.say(path, "OK")

    def target(self, path: str, top: bool = True) -> None:
        """Аргумент или запись папки: папка — её файлы (вглубь — только с -r)."""
        try:
            st = os.lstat(path)
        except OSError:
            st = None
        if st is not None and stat.S_ISDIR(st.st_mode):
            if not top and not self.recursive:
                return
            self.dirs += 1
            try:
                names = sorted(os.listdir(path))
            except OSError:
                self.errors += 1
                self.say(path, "Can't open directory")
                return
            for n in names:
                self.target(os.path.join(path, n) if path != "." else "./" + n, top=False)
            return
        if st is not None and stat.S_ISLNK(st.st_mode) and not top:
            return                      # ссылки внутри папок не обходим и не называем
        self.file(path)


def _log(argv: List[str]) -> None:
    """Строка JSON на вызов в .termit/av.log песочницы. Ссылку вместо журнала не открываем."""
    box = os.environ.get("TERMIT_BOX")
    if not box:
        return
    line = json.dumps({"argv": argv, "cwd": os.getcwd()}, ensure_ascii=False) + "\n"
    try:
        fd = os.open(os.path.join(box, ".termit", LOG),
                     os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o644)
    except OSError:
        return
    try:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            os.write(fd, line.encode("utf-8"))
    except OSError:
        pass
    finally:
        os.close(fd)


def parse(argv: List[str]):
    """(базы, рекурсивно, только найденные, без сводки, цели); --help/--version — строкой."""
    dbs, rec, inf, nosum, targets = [], False, False, False, []
    it = iter(argv)
    for a in it:
        if a == "--":
            targets += list(it)
            break
        if a in ("-h", "--help"):
            return "help"
        if a in ("-V", "--version"):
            return "version"
        if a.startswith("--"):
            name, eq, value = a.partition("=")
            if name == "--recursive":
                rec = True
            elif name == "--infected":
                inf = True
            elif name == "--no-summary":
                nosum = True
            elif name == "--database":
                value = value if eq else next(it, None)
                if not value:
                    raise Usage("--database needs an argument")
                dbs.append(value)
            else:
                raise Usage(f"Unknown option passed: {a}")
            continue
        if a.startswith("-") and len(a) > 1:
            for i, ch in enumerate(a[1:], 1):
                if ch == "r":
                    rec = True
                elif ch == "i":
                    inf = True
                elif ch == "d":
                    value = a[i + 1:] or next(it, None)
                    if not value:
                        raise Usage("-d needs an argument")
                    dbs.append(value)
                    break
                else:
                    raise Usage(f"Unknown option passed: -{ch}")
            continue
        targets.append(a)
    return dbs, rec, inf, nosum, targets


def main(argv: List[str]) -> int:
    _log(list(argv))
    _err(NOTE)
    try:
        opts = parse(argv)
    except Usage as e:
        _err(f"ERROR: {e}")
        _err("ERROR: Can't parse command line options")
        return 2
    if opts == "help":
        print(USAGE, end="")
        return 0
    if opts == "version":
        print(VERSION)
        return 0
    dbs, rec, inf, nosum, targets = opts
    if not dbs:
        dbs = [os.path.join(os.path.expanduser("~"), DEFAULT_DB)]
    started = time.monotonic()
    db = Db()
    ok = all([db.load(p) for p in dbs])
    if not ok:
        _err("ERROR: Can't load database: Malformed database")    # как ClamAV: проверки нет
        return 2
    scan = Scan(db, rec, inf)
    for t in targets or [os.getcwd()]:
        scan.target(t)
    if not nosum:
        took = time.monotonic() - started
        print("\n----------- SCAN SUMMARY -----------")
        print(f"Known viruses: {db.count}")
        print("Engine version: 1.4.3 (учебный)")
        print(f"Scanned directories: {scan.dirs}")
        print(f"Scanned files: {scan.files}")
        print(f"Infected files: {scan.found}")
        print(f"Data scanned: {scan.bytes / 1048576:.2f} MB")
        print(f"Time: {took:.3f} sec (0 m {int(took)} s)")
    if scan.found:
        return 1
    return 2 if (scan.errors or not ok) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
