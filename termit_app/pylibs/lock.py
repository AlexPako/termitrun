"""Пины склада колёс сторонних пакетов (часть 10, A3): pandas и requests с зависимостями.

Только колёса (--only-binary=:all:): sdist не собирается, ничей setup.py не исполняется. Для
пакетов с машинным кодом (pandas, numpy) — два файла: cp39 под macOS arm64 и x86_64; чистый
Python — один py3-none-any. sha256 взяты из метаданных PyPI
(https://pypi.org/pypi/<имя>/<версия>/json), без скачивания самих файлов. Тест проверяет
только формат; совпадение с настоящими файлами проверяет pip (--require-hashes) при
./termit wheels get и сама игра (pyenvs.verify) — несовпавший файл удаляется.

Склад качает только родитель и только по явному «y» владельца (pyenvs.get_wheels)."""
import re
from typing import Dict, List, Optional, Sequence, Tuple

# что ставит эталонный venv full поверх light (зависимости — ниже, тоже с пинами)
TOP = ("pandas==2.2.3", "requests==2.32.4")

LOCK: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "pandas==2.2.3": (
        ("pandas-2.2.3-cp39-cp39-macosx_10_9_x86_64.whl",
         "bc6b93f9b966093cb0fd62ff1a7e4c09e6d546ad7c1de191767baffc57628f39"),
        ("pandas-2.2.3-cp39-cp39-macosx_11_0_arm64.whl",
         "5dbca4c1acd72e8eeef4753eeca07de9b1db4f398669d5994086f788a5d7cc30"),
    ),
    "numpy==1.26.4": (
        ("numpy-1.26.4-cp39-cp39-macosx_10_9_x86_64.whl",
         "7349ab0fa0c429c82442a27a9673fc802ffdb7c7775fad780226cb234965e53c"),
        ("numpy-1.26.4-cp39-cp39-macosx_11_0_arm64.whl",
         "52b8b60467cd7dd1e9ed082188b4e6bb35aa5cdd01777621a1658910745b90be"),
    ),
    "requests==2.32.4": (
        ("requests-2.32.4-py3-none-any.whl",
         "27babd3cda2a6d50b30443204ee89830707d396671944c998b5975b031ac2b2c"),
    ),
    "urllib3==1.26.20": (
        ("urllib3-1.26.20-py2.py3-none-any.whl",
         "0ed14ccfbf1c30a9072c7ca157e4319b70d65f623e91e7b32fadb2853431016e"),
    ),
    "idna==3.10": (
        ("idna-3.10-py3-none-any.whl",
         "946d195a0d259cbba61165e88e65941f16e9b36ea6ddb97f00452bae8b1287d3"),
    ),
    "certifi==2025.8.3": (
        ("certifi-2025.8.3-py3-none-any.whl",
         "f6c12493cfb1b06ba2ff328595af9350c65d6644968e5d3a2ffd78699af217a5"),
    ),
    "charset-normalizer==3.4.2": (
        ("charset_normalizer-3.4.2-py3-none-any.whl",
         "7f56930ab0abd1c45cd15be65cc741c28b1c9a34876ce8c17a2fa107810c0af0"),
    ),
    "python-dateutil==2.9.0.post0": (
        ("python_dateutil-2.9.0.post0-py2.py3-none-any.whl",
         "a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427"),
    ),
    "pytz==2025.2": (
        ("pytz-2025.2-py2.py3-none-any.whl",
         "5ddf76296dd8c44c26eb8f4b6f35488f3ccbf6fbbd7adee0b7262d43f0ec2f00"),
    ),
    "tzdata==2025.2": (
        ("tzdata-2025.2-py2.py3-none-any.whl",
         "1a403fada01ff9221ca8044d701868fa132215d84beb92242d9acd2147f667a8"),
    ),
    "six==1.17.0": (
        ("six-1.17.0-py2.py3-none-any.whl",
         "4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274"),
    ),
}

ARCHES = ("arm64", "x86_64")
# метка платформы колеса под архитектуру (macOS)
_PLATFORM = {"arm64": "macosx_11_0_arm64", "x86_64": "macosx_10_9_x86_64"}
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9.]+)$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_WHEEL = re.compile(r"^([A-Za-z0-9_.]+)-([A-Za-z0-9.]+)-([a-z0-9.]+)-([a-z0-9_]+)-([a-z0-9_.]+)"
                    r"\.whl$")


def norm(name: str) -> str:
    """Имя пакета для сравнения (PEP 503): регистр и -_. — одно и то же."""
    return re.sub(r"[-_.]+", "-", name).lower()


def split_pin(pin: str) -> Tuple[str, str]:
    m = _PIN.match(pin)
    if not m:
        raise ValueError(f"не пин имя==версия: {pin!r}")
    return m.group(1), m.group(2)


def _fits(fname: str, arch: str) -> bool:
    """Колесо годится для cp39 под эту архитектуру: чистое (none-any) или с её меткой."""
    m = _WHEEL.match(fname)
    if not m:
        return False
    py, abi, plat = m.group(3), m.group(4), m.group(5)
    if abi == "none" and plat == "any":
        return py in ("py3", "py2.py3")
    return py == "cp39" and abi == "cp39" and plat == _PLATFORM.get(arch)


def files_for(arch: str, lock: Optional[dict] = None) -> List[Tuple[str, str, str]]:
    """[(пин, файл, sha256)] склада под архитектуру — ровно один файл на пин. Нет файла —
    ValueError (архитектура не поддержана)."""
    lock = LOCK if lock is None else lock
    out = []
    for pin in sorted(lock):
        hits = [(f, h) for f, h in lock[pin] if _fits(f, arch)]
        if len(hits) != 1:
            raise ValueError(f"{pin}: для {arch} колёс {len(hits)}, нужно одно")
        out.append((pin, hits[0][0], hits[0][1]))
    return out


def requirements(arch: str, lock: Optional[dict] = None) -> str:
    """Файл требований для pip --require-hashes: «имя==версия --hash=sha256:…» на строку."""
    return "".join(f"{pin} --hash=sha256:{sha}\n" for pin, _, sha in files_for(arch, lock))


def problems(lock: Optional[dict] = None, top: Sequence[str] = TOP) -> List[str]:
    """Ошибки формата пинов (пусто — всё в порядке): пин, имя и версия файла, sha256, по
    файлу на архитектуру, верхние пакеты есть в пинах."""
    lock = LOCK if lock is None else lock
    out = []
    for pin, files in sorted(lock.items()):
        try:
            name, ver = split_pin(pin)
        except ValueError as e:
            out.append(str(e))
            continue
        for fname, sha in files:
            m = _WHEEL.match(fname)
            if not m:
                out.append(f"{pin}: не имя колеса: {fname}")
                continue
            if norm(m.group(1)) != norm(name) or m.group(2) != ver:
                out.append(f"{pin}: файл другого пакета или версии: {fname}")
            if not _SHA.match(sha):
                out.append(f"{pin}: sha256 не 64 hex: {fname}")
        for arch in ARCHES:
            if len([f for f, _ in files if _fits(f, arch)]) != 1:
                out.append(f"{pin}: для {arch} нужен ровно один файл")
    for pin in top:
        if pin not in lock:
            out.append(f"верхнего пакета нет в пинах: {pin}")
    return out
