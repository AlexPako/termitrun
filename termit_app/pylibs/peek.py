"""Сводка datapeek у родителя (часть 7, E16): эталон для проверки считает тот же код пакета
из src/ — функция на данных генератора, а не запуск чего-либо из песочницы.

Пакеты не ставятся и в sys.path не попадают: исходники tabprint и datapeek исполняются в
свои объекты модулей. datapeek делает «import tabprint» — на это мгновение (под замком)
sys.modules["tabprint"] — наш объект, потом всё как было. Код игрока сюда не попадает
никогда: файлы берутся только из termit_app/pylibs/src."""
import sys
import threading
import types

from termit_app.pylibs import SRC

_lock = threading.Lock()
_mods = {}
_MISSING = object()


def _module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    path = SRC / name / "__init__.py"
    mod.__file__ = str(path)
    exec(compile(path.read_text("utf-8"), str(path), "exec"), mod.__dict__)
    return mod


def datapeek() -> types.ModuleType:
    """Модуль datapeek из src/ (с tabprint из src/), один раз на процесс."""
    with _lock:
        if "datapeek" not in _mods:
            tab = _module("tabprint")
            saved = sys.modules.get("tabprint", _MISSING)
            sys.modules["tabprint"] = tab
            try:
                _mods["datapeek"] = _module("datapeek")
            finally:
                if saved is _MISSING:
                    del sys.modules["tabprint"]
                else:
                    sys.modules["tabprint"] = saved
        return _mods["datapeek"]


def report(path, shown: str) -> str:
    """Текст «datapeek FILE» по файлу path, как будто его назвали shown (первая строка
    сводки — «shown: N rows, M columns»)."""
    text = datapeek().report(str(path))
    head, nl, rest = text.partition("\n")
    return shown + head[len(str(path)):] + nl + rest
