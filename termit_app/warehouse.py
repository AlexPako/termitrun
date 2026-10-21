"""Склад колёс pandas/requests глазами игрока (часть 10, A3): ./termit wheels status|get|
verify|clean и вопрос в конце рана. Сам склад — termit_app.pyenvs (пины, сверка, скачивание).

Скачивает только родитель и только после явного «y». Вопрос в конце рана — когда открыт трек
«Python» (повержен страж «Окружения»), а склада нет: не чаще раза в день; n — больше не
спрашиваем (вернуть: ./termit wheels get), l/пусто — спросим через LATER_DAYS дней. Денег не
берём: учёбу кредитами не запираем. Без склада трек «Аналитика» виден, но закрыт честно
(missing задачи называет команду)."""
from datetime import date, timedelta
from typing import Callable, List, Optional

from termit_app import pyenvs

LATER_DAYS = 3
YES = ("y", "yes", "д", "да")
NO = ("n", "no", "н", "нет")
OPENS_AFTER = "boss_env"        # трек «Python» открыт — пора предложить склад «Аналитики»

# сколько качать (M3 ревью Q4): оценка по известным размерам колёс PyPI для пинов lock.py —
# numpy 1.26.4 cp39 ≈ 14 МБ на arm64 и ≈ 21 МБ на x86_64, pandas 2.2.3 cp39 ≈ 11 и ≈ 13 МБ,
# прочие (requests, urllib3, dateutil, pytz, tzdata…) вместе ≈ 1,6 МБ; FB14 — линтеры и
# тесты трека «Python» (mypy cp39 ≈ 9 и ≈ 10 МБ, flake8, pytest и их зависимости ≈ 2 МБ) —
# ещё ≈ 11 и ≈ 12 МБ. Не замер: сеть в сборке и тестах запрещена; размеры в lock.py не хранятся
APPROX_MB = {"arm64": 38, "x86_64": 47}

TEXT = {
    "card": "📦 Для «Аналитики» и линтеров трека «Python» нужен склад пакетов: pandas, "
            "requests, flake8, pytest и mypy с зависимостями (около {mb} МБ, один раз, с "
            "официального PyPI).",
    "how": "   Скачаю только колёса по списку с проверкой хэшей — чужой код при этом не "
           "запускается. Команда:",
    "ask": "Скачать? y — да, n — не надо, l — позже [y/n/l] ",
    "ask_yn": "Скачать? [y/n] ",
    "declined": "   Понял, больше не спрошу. «Аналитика» и линтеры трека «Python» (py_lint, "
                "py_test, py_types) закрыты; вернуть: ./termit wheels get",
    "later": "   Ладно, спрошу через пару дней.",
    "not_now": "   Не качаю.",
    "getting": "   Качаю, это займёт минуту-другую…",
    "failed": "   Не вышло: {why}. Остальной трек «Python» от склада не зависит, без него "
              "закрыты только py_lint, py_test, py_types и «Аналитика»; попробуй позже: "
              "./termit wheels get",
    "done": "✓ {msg}",
    "unusable": "Склад здесь не поможет: {why}",
    "st_title": "Склад пакетов (pandas, requests; flake8, pytest, mypy):",
    "st_ready": "   на месте: {n} колёс в {path}",
    "st_missing": "   нет {absent} из {n} колёс — скачать: ./termit wheels get",
    "st_bad": "   испорчено: {bad} — ./termit wheels verify, потом ./termit wheels get",
    "st_full": "   готовое окружение с pandas: {state}",
    "st_cmd": "   скачивание: {cmd}",
    "verify_ok": "✓ Все {n} колёс сходятся с пинами (sha256).",
    "verify_bad": "Не сходятся с пинами (удалил): {bad}. Скачать заново: ./termit wheels get",
    "verify_missing": "Нет {absent} из {n} колёс: ./termit wheels get",
    "clean_ask": "Удалить склад и готовое окружение с pandas? Снова — только с сетью [y/N] ",
    "cleaned": "✓ Удалил: {what}",
    "nothing": "Удалять нечего.",
    "usage": "./termit wheels · status · get · verify · clean",
}


def _state(p: dict) -> dict:
    st = p.setdefault("wheels", {})
    if not isinstance(st, dict):
        st = p["wheels"] = {}
    return st


def _ask(ask: Callable, prompt: str) -> str:
    try:
        return (ask(prompt) or "").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _later_passed(st: dict, today: date) -> bool:
    try:
        return date.fromisoformat(str(st.get("later") or "")) <= today
    except ValueError:
        return True


def command_line() -> str:
    """Ровно то, что запустит get (карточка показывает правду)."""
    info = pyenvs.track_python()
    if info is None:
        return "pip download …"
    argv = pyenvs.download_argv(info, pyenvs.third_dir().parent / "<пины>.txt",
                                pyenvs.third_dir())
    return " ".join(argv)


def usable() -> Optional[str]:
    """Почему склад на этой машине бесполезен (не 3.9, чужая архитектура); None — годен."""
    try:
        pyenvs.warehouse_files()
    except (pyenvs.WarehouseError, ValueError) as e:
        return str(e)
    return None


def eligible(p: dict, today: date) -> bool:
    """Пора спросить: трек «Python» открыт, склада нет, машина годится, не отказано, «позже»
    истекло, сегодня ещё не спрашивали."""
    st = _state(p)
    if OPENS_AFTER not in p.get("bosses", ()) or st.get("declined"):
        return False
    if st.get("offered") == today.isoformat() or not _later_passed(st, today):
        return False
    return usable() is None and not pyenvs.warehouse_ready()


def goes_first(p: dict, today: date) -> bool:
    """Конец рана — не больше одного вопроса (M1 ревью Q4): склад спрашивает, если пора и
    либо трек «Аналитика» открыт (без склада его задачи закрыты — он важнее), либо импланты
    сегодня молчат; иначе спрашивают импланты, а склад ждёт следующего рана."""
    from termit_app import implants
    from termit_app.tasks import registry
    if not eligible(p, today):
        return False
    if any(t.key == "pydata" for t in registry.unlocked(p.get("bosses", []))):
        return True
    return not implants.would_ask(p, today)


def _get(getter: Optional[Callable]) -> bool:
    from termit_app import ui
    ui.say(TEXT["getting"])
    try:
        ok, msg = (getter or pyenvs.get_wheels)()
    except KeyboardInterrupt:
        print()
        ok, msg = False, "прервано"
    except (pyenvs.WarehouseError, OSError, ValueError, RuntimeError) as e:
        ok, msg = False, str(e)
    if ok:
        ui.ok(TEXT["done"].format(msg=msg))
    else:
        ui.say(TEXT["failed"].format(why=msg))
    return ok


def approx_mb() -> int:
    """Оценка размера склада для этой машины, МБ (по большему, если архитектура неизвестна)."""
    info = pyenvs.track_python()
    return APPROX_MB.get(info.arch if info else "", max(APPROX_MB.values()))


def _card() -> None:
    from termit_app import ui
    ui.say()
    ui.say(ui.story_fill(TEXT["card"].format(mb=approx_mb()), "", "   "))
    ui.say(TEXT["how"])
    ui.say("   " + command_line())


def offer(p: dict, ask: Callable, today: date, getter: Optional[Callable] = None) -> bool:
    """Конец рана: не больше одного вопроса в день. y — качаем (getter, по умолчанию
    pyenvs.get_wheels), n — больше не спрашиваем, l/пусто/прочее — через LATER_DAYS дней.
    Вернуть True, если склад теперь на месте."""
    from termit_app import ui
    if not eligible(p, today):
        return False
    st = _state(p)
    st["offered"] = today.isoformat()
    _card()
    answer = _ask(ask, TEXT["ask"])
    if answer in YES:
        ok = _get(getter)
        if not ok:
            st["later"] = (today + timedelta(days=LATER_DAYS)).isoformat()
        return ok
    if answer in NO:
        st["declined"] = True
        ui.say(TEXT["declined"])
        return False
    st["later"] = (today + timedelta(days=LATER_DAYS)).isoformat()
    ui.say(TEXT["later"])
    return False


def status_lines() -> List[str]:
    why = usable()
    if why:
        return [TEXT["st_title"], TEXT["unusable"].format(why=why)]
    files = pyenvs.warehouse_files()
    good, absent, bad = pyenvs.verify()
    out = [TEXT["st_title"]]
    if bad:
        out.append(TEXT["st_bad"].format(bad=", ".join(bad)))
    elif absent:
        out.append(TEXT["st_missing"].format(absent=len(absent), n=len(files)))
    else:
        out.append(TEXT["st_ready"].format(n=len(good), path=pyenvs.third_dir()))
        built = pyenvs.full_path().is_dir()
        out.append(TEXT["st_full"].format(
            state="собрано" if built else "соберу при первой задаче (около 20 с)"))
    out.append(TEXT["st_cmd"].format(cmd=command_line()))
    return out


def get_cmd(p: dict, ask: Callable, getter: Optional[Callable] = None) -> int:
    """./termit wheels get: карточка и [y/n]; y снимает прежний отказ. 0 — склад на месте
    или «не надо», 1 — не вышло."""
    from termit_app import ui
    why = usable()
    if why:
        ui.say(TEXT["unusable"].format(why=why))
        return 1
    if pyenvs.warehouse_ready():
        ui.ok(TEXT["st_ready"].format(n=len(pyenvs.warehouse_files()),
                                      path=pyenvs.third_dir()).strip())
        return 0
    _card()
    if _ask(ask, TEXT["ask_yn"]) not in YES:
        ui.say(TEXT["not_now"])
        return 0
    st = _state(p)
    st.pop("declined", None)
    st.pop("later", None)
    return 0 if _get(getter) else 1


def verify_cmd() -> int:
    from termit_app import ui
    why = usable()
    if why:
        ui.say(TEXT["unusable"].format(why=why))
        return 1
    files = pyenvs.warehouse_files()
    _, absent, bad = pyenvs.verify(remove_bad=True)
    if bad:
        ui.bad(TEXT["verify_bad"].format(bad=", ".join(bad)))
        return 1
    if absent:
        ui.say(TEXT["verify_missing"].format(absent=len(absent), n=len(files)))
        return 1
    ui.ok(TEXT["verify_ok"].format(n=len(files)))
    return 0


def clean_cmd(ask: Callable) -> int:
    from termit_app import ui
    if _ask(ask, TEXT["clean_ask"]) not in YES:
        ui.say(TEXT["not_now"].replace("качаю", "удаляю"))
        return 0
    removed = pyenvs.clean()
    ui.say(TEXT["cleaned"].format(what=", ".join(removed)) if removed else TEXT["nothing"])
    return 0
