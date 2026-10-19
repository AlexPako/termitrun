"""Детерминированная сборка колёс и sdist учебных пакетов (часть 7, A2) — только stdlib.

Колесо py3-none-any через zipfile: записи по алфавиту (RECORD — последней, как у
bdist_wheel), date_time 2026-01-01, права 0644, без сжатия (ZIP_STORED: байты не зависят от
сборки zlib — M4 ревью P1; пакеты маленькие); METADATA 2.1 (Name, Version, Summary,
Requires-Python, Requires-Dist), WHEEL (Root-Is-Purelib, Tag), entry_points.txt, RECORD с
sha256 (urlsafe base64 без «=») и размерами. Тот же вход — те же байты: sha256 колеса
стабилен, и shasum в уроке совпадает с опубликованным. sdist (tar.gz, mtime/uid 0) — только
посмотреть внутрь (tar -tzf): офлайн-сборки из него у pip 21 без wheel нет (решение 6);
gzip — без имени файла и с нулевым временем.

Правило для задач и уроков: sha256 колеса — только из wheelmake.sha256() (в состоянии задачи),
никогда литералом в тексте или тесте: на другой машине (другой zlib у sdist, другая версия
пакета) литерал разойдётся.

Колёса кладутся в .cache/wheels/local/ (paths.CACHE_DIR) при первой нужде; сети не нужно."""
import base64
import gzip
import hashlib
import io
import os
import re
import secrets
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

from termit_app import paths
from termit_app.pylibs import SRC

DATE = (2026, 1, 1, 0, 0, 0)
GENERATOR = "wheelmake 1.0"
LOCAL_DIR = ("wheels", "local")         # в paths.CACHE_DIR
_VERSION_LINE = re.compile(r'^__version__ = "[^"]*"$', re.M)


@dataclass(frozen=True)
class Pkg:
    name: str
    version: str
    summary: str
    src: str = ""                                   # папка в src/ (по умолчанию — name)
    requires: Tuple[str, ...] = ()
    entry_points: Dict[str, Dict[str, str]] = field(default_factory=dict)

    @property
    def key(self) -> Tuple[str, str]:
        return (self.name, self.version)

    @property
    def wheel_name(self) -> str:
        return f"{self.name}-{self.version}-py3-none-any.whl"

    @property
    def sdist_name(self) -> str:
        return f"{self.name}-{self.version}.tar.gz"


# Каталог учебных пакетов. tabprint 1.1.0 (новее) — ловушка урока pip_freeze: зависимость без
# версии pip берёт новейшую.
PKGS: Dict[Tuple[str, str], Pkg] = {p.key: p for p in (
    Pkg("sockhttp", "1.0.0", "HTTP over a unix socket: get, post, urllib and requests"),
    Pkg("tabprint", "1.0.0", "Print tables in the terminal"),
    Pkg("tabprint", "1.1.0", "Print tables in the terminal"),
    Pkg("datapeek", "0.2.0", "Quick look at a CSV file: columns, rows, top values",
        requires=("tabprint>=1.0",),
        entry_points={"console_scripts": {"datapeek": "datapeek.__main__:main"}}),
)}


def stub(name: str, version: str,
         summary: str = "Makes the terminal start faster") -> Pkg:
    """Пакет-пустышка вне каталога (страж env, E18): исходник — src/_stub (только
    __version__), имя — любое нейтральное. В склад колёс (build_all) не входит."""
    return Pkg(name, version, summary, src="_stub")


def get(pkg: Union[Pkg, str], version: Optional[str] = None) -> Pkg:
    """Пакет каталога: Pkg, "имя", "имя==версия" или имя и версия (без версии — новейшая)."""
    if isinstance(pkg, Pkg):
        return pkg
    name, _, ver = str(pkg).partition("==")
    ver = version or ver
    if ver:
        return PKGS[(name, ver)]
    found = [p for p in PKGS.values() if p.name == name]
    if not found:
        raise KeyError(name)
    return max(found, key=lambda p: tuple(int(x) for x in p.version.split(".")))


def _record_hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def sources(pkg: Pkg) -> Dict[str, bytes]:
    """Файлы пакета {путь в колесе: байты}: *.py из src/<папка>/, по алфавиту; строка
    __version__ = "…" в __init__.py — версия каталога."""
    root = SRC / (pkg.src or pkg.name)
    out = {}
    for f in sorted(root.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        rel = f.relative_to(SRC / (pkg.src or pkg.name)).as_posix()
        text = f.read_text("utf-8")
        if rel == "__init__.py":
            text, n = _VERSION_LINE.subn(f'__version__ = "{pkg.version}"', text)
            if n != 1:
                raise ValueError(f"{pkg.name}: в __init__.py нет строки __version__")
        out[f"{pkg.name}/{rel}"] = text.encode("utf-8")
    if f"{pkg.name}/__init__.py" not in out:
        raise ValueError(f"{pkg.name}: нет __init__.py")
    return out


def metadata(pkg: Pkg) -> str:
    lines = ["Metadata-Version: 2.1", f"Name: {pkg.name}", f"Version: {pkg.version}",
             f"Summary: {pkg.summary}", "Requires-Python: >=3.9"]
    lines += [f"Requires-Dist: {r}" for r in pkg.requires]
    return "\n".join(lines) + "\n"


def _entry_points(pkg: Pkg) -> str:
    out = ""
    for group, items in sorted(pkg.entry_points.items()):
        out += f"[{group}]\n" + "".join(f"{k} = {v}\n" for k, v in sorted(items.items())) + "\n"
    return out


def wheel_files(pkg: Pkg) -> Dict[str, bytes]:
    """Все файлы колеса, включая RECORD, — в порядке записи в zip."""
    dist = f"{pkg.name}-{pkg.version}.dist-info"
    files = dict(sources(pkg))
    files[f"{dist}/METADATA"] = metadata(pkg).encode("utf-8")
    files[f"{dist}/WHEEL"] = (f"Wheel-Version: 1.0\nGenerator: {GENERATOR}\n"
                              "Root-Is-Purelib: true\nTag: py3-none-any\n").encode("ascii")
    if pkg.entry_points:
        files[f"{dist}/entry_points.txt"] = _entry_points(pkg).encode("utf-8")
    order = sorted(files)
    record = "".join(f"{p},{_record_hash(files[p])},{len(files[p])}\n" for p in order)
    record += f"{dist}/RECORD,,\n"
    out = {p: files[p] for p in order}
    out[f"{dist}/RECORD"] = record.encode("utf-8")
    return out


def wheel_bytes(pkg) -> bytes:
    """Байты колеса — одинаковые при каждой сборке."""
    pkg = get(pkg)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name, data in wheel_files(pkg).items():
            zi = zipfile.ZipInfo(name, DATE)
            zi.external_attr = 0o644 << 16
            zi.create_system = 3                    # Unix: права из external_attr
            zi.compress_type = zipfile.ZIP_STORED
            z.writestr(zi, data)
    return buf.getvalue()


def sdist_bytes(pkg) -> bytes:
    """sdist tar.gz: PKG-INFO, pyproject.toml и исходники под «имя-версия/»; mtime, uid и gid
    — нули, права 0644, порядок — по алфавиту, gzip без имени и времени."""
    pkg = get(pkg)
    top = f"{pkg.name}-{pkg.version}"
    files = {f"{top}/PKG-INFO": metadata(pkg).encode("utf-8"),
             f"{top}/pyproject.toml": (
                 "[build-system]\nrequires = [\"setuptools\"]\n"
                 "build-backend = \"setuptools.build_meta\"\n\n"
                 f"[project]\nname = \"{pkg.name}\"\nversion = \"{pkg.version}\"\n"
                 f"description = \"{pkg.summary}\"\nrequires-python = \">=3.9\"\n"
                 f"dependencies = {list(pkg.requires)!r}\n".replace("'", '"')).encode("utf-8")}
    for rel, data in sources(pkg).items():
        files[f"{top}/src/{rel}"] = data
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name in sorted(files):
            info = tarfile.TarInfo(name)
            info.size = len(files[name])
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(files[name]))
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def local_dir() -> Path:
    return Path(paths.CACHE_DIR).joinpath(*LOCAL_DIR)


def _put(path: Path, data: bytes) -> Path:
    """Записать файл, если его нет или он другой: временный рядом + rename."""
    try:
        if path.read_bytes() == data:
            return path
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        with open(tmp, "xb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def build_wheel(pkg, out: Optional[Path] = None) -> Path:
    """Собрать колесо в out (по умолчанию .cache/wheels/local) и вернуть путь."""
    pkg = get(pkg)
    return _put(Path(out or local_dir()) / pkg.wheel_name, wheel_bytes(pkg))


def build_sdist(pkg, out: Optional[Path] = None) -> Path:
    """Собрать sdist в out (по умолчанию .cache/wheels/local) и вернуть путь."""
    pkg = get(pkg)
    return _put(Path(out or local_dir()) / pkg.sdist_name, sdist_bytes(pkg))


def build_all(out: Optional[Path] = None) -> Dict[Tuple[str, str], Path]:
    """Все колёса каталога в out — склад учебных пакетов."""
    return {key: build_wheel(p, out) for key, p in sorted(PKGS.items())}


def sha256(path) -> str:
    """Тот же хэш, что печатает shasum -a 256."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
