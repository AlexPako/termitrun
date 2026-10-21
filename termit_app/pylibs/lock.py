"""Пины склада колёс сторонних пакетов (часть 10, A3): pandas и requests с зависимостями;
FB14 — линтеры и тесты трека «Python» (flake8, pep8-naming, flake8-isort, pytest, mypy).

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
    # FB14 (FB5 п. 35, 37): линтеры и тесты трека «Python» — flake8 с pep8-naming и
    # flake8-isort, pytest, mypy (у mypy — собранные колёса cp39, его чистое колесо не берём:
    # ровно один файл на архитектуру). sha256 — из метаданных PyPI, как у остальных
    "flake8==7.1.2": (
        ("flake8-7.1.2-py2.py3-none-any.whl",
         "1cbc62e65536f65e6d754dfe6f1bada7f5cf392d6f5db3c2b85892466c3e7c1a"),
    ),
    "pycodestyle==2.12.1": (
        ("pycodestyle-2.12.1-py2.py3-none-any.whl",
         "46f0fb92069a7c28ab7bb558f05bfc0110dac69a0cd23c61ea0040283a9d78b3"),
    ),
    "pyflakes==3.2.0": (
        ("pyflakes-3.2.0-py2.py3-none-any.whl",
         "84b5be138a2dfbb40689ca07e2152deb896a65c3a3e24c251c5c62489568074a"),
    ),
    "mccabe==0.7.0": (
        ("mccabe-0.7.0-py2.py3-none-any.whl",
         "6c2d30ab6be0e4a46919781807b4f0d834ebdd6c6e3dca0bda5a15f863427b6e"),
    ),
    "pep8-naming==0.14.1": (
        ("pep8_naming-0.14.1-py3-none-any.whl",
         "63f514fc777d715f935faf185dedd679ab99526a7f2f503abb61587877f7b1c5"),
    ),
    "flake8-isort==6.1.1": (
        ("flake8_isort-6.1.1-py3-none-any.whl",
         "0fec4dc3a15aefbdbe4012e51d5531a2eb5fa8b981cdfbc882296a59b54ede12"),
    ),
    "isort==5.13.2": (
        ("isort-5.13.2-py3-none-any.whl",
         "8ca5e72a8d85860d5a3fa69b8745237f2939afe12dbf656afbcb47fe72d947a6"),
    ),
    "pytest==8.3.5": (
        ("pytest-8.3.5-py3-none-any.whl",
         "c69214aa47deac29fad6c2a4f590b9c4a9fdb16a403176fe154b79c0b4d4d820"),
    ),
    "iniconfig==2.0.0": (
        ("iniconfig-2.0.0-py3-none-any.whl",
         "b6a85871a79d2e3b22d2d1b94ac2824226a63c6b741c88f7ae975f18b6778374"),
    ),
    "packaging==24.2": (
        ("packaging-24.2-py3-none-any.whl",
         "09abb1bccd265c01f4a3aa3f7a7db064b36514d2cba19a2f694fe6150451a759"),
    ),
    "pluggy==1.5.0": (
        ("pluggy-1.5.0-py3-none-any.whl",
         "44e1ad92c8ca002de6377e165f3e0f1be63266ab4d554740532335b9d75ea669"),
    ),
    "exceptiongroup==1.2.2": (
        ("exceptiongroup-1.2.2-py3-none-any.whl",
         "3111b9d131c238bec2f8f516e123e14ba243563fb135d3fe885990585aa7795b"),
    ),
    "tomli==2.2.1": (
        ("tomli-2.2.1-py3-none-any.whl",
         "cb55c73c5f4408779d0cf3eef9f762b9c9f147a77de7b258bef0a5628adc85cc"),
    ),
    "mypy==1.14.1": (
        ("mypy-1.14.1-cp39-cp39-macosx_10_9_x86_64.whl",
         "3888a1816d69f7ab92092f785a462944b3ca16d7c470d564165fe703b0970c35"),
        ("mypy-1.14.1-cp39-cp39-macosx_11_0_arm64.whl",
         "46c756a444117c43ee984bd055db99e498bc613a70bbbc120272bd13ca579fbc"),
    ),
    "typing_extensions==4.12.2": (
        ("typing_extensions-4.12.2-py3-none-any.whl",
         "04e5ca0351e0f3f85c6853954072df659d0d13fac324d0072316b67d7794700d"),
    ),
    "mypy_extensions==1.0.0": (
        ("mypy_extensions-1.0.0-py3-none-any.whl",
         "4392f6c0eb8a5668a69e23d168ffa70f0be9ccfd32b5cc2d26a34ae5b844552d"),
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
