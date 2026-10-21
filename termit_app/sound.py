"""Редкие звуки: только у купленных примочек и только на значимых событиях.

Играет всегда родитель, после события — никогда не песочница. Купленная примочка звучит
сразу, но редко: взлом стража, рекорд, веха серии, не чаще раза на событие за ран.
Выключить — ./termit sound off; переменная TERMIT_NO_SOUND глушит всё (ею пользуются тесты).

Звуковые пакеты (K10): купленный пакет звучит сам (покупка и есть согласие — это звук тех же
редких событий), WAV события синтезируется в кэш (music.ensure_event). Порядок: пакет →
кассета (системный звук) → звонок. ./termit sound pack off возвращает кассету. Громкость
общая с декой (settings["volume"], afplay -v); пока игрок её не задал — системный уровень,
как было до пакетов."""
import os
import subprocess
from typing import Optional, Set

EVENTS = {"boss_down": "Hero", "record": "Glass", "milestone": "Purr"}
# купленная позиция → пакет synth
PACKS = {"snd_synth": "synth", "snd_chip": "chip", "snd_noir": "noir"}
AFPLAY = "/usr/bin/afplay"
BELL_FILE = "/System/Library/Sounds/Tink.aiff"
SOUNDS_DIR = "/System/Library/Sounds"

_popen = subprocess.Popen       # подменяется в тестах
_exists = os.path.exists        # и это: тесты не зависят от файлов системы


def enabled(p: dict) -> bool:
    """Звук не выключен руками. По умолчанию включён, но без покупки звучать нечему."""
    return (p.get("settings") or {}).get("sound", True) is not False


def gadgets(p: dict) -> list:
    """Что звучит: выбранный пакет, кассета, звонок (в порядке очереди)."""
    chosen = pack(p)
    return ([chosen] if chosen else []) + [i for i in ("cassette", "bell")
                                           if i in p.get("owned", [])]


def owned_packs(p: dict) -> list:
    return [i for i in (p.get("owned") or ()) if i in PACKS]


def pack(p: dict) -> Optional[str]:
    """Выбранный пакет: ключа нет — первый купленный; None — выключен (sound pack off);
    выбран, но не куплен (правка руками) — первый купленный."""
    have = owned_packs(p)
    s = p.get("settings") if isinstance(p.get("settings"), dict) else {}
    if "sound_pack" in s and s["sound_pack"] is None:
        return None
    return s["sound_pack"] if s.get("sound_pack") in have else (have[0] if have else None)


def resolve_pack(want: str) -> Optional[str]:
    """id пакета: полный (snd_chip) или короткий (chip)."""
    if want in PACKS:
        return want
    return next((i for i, short in PACKS.items() if short == want), None)


def set_pack(p: dict, want: str) -> str:
    """Выбрать пакет: ok | off | unknown | not_owned."""
    settings = p.setdefault("settings", {})
    if want == "off":
        settings["sound_pack"] = None
        return "off"
    iid = resolve_pack(want)
    if iid is None:
        return "unknown"
    if iid not in owned_packs(p):
        return "not_owned"
    settings["sound_pack"] = iid
    return "ok"


def _vol_args(p: dict) -> list:
    """-v общей громкости, если игрок её задал; иначе — системный уровень (как раньше)."""
    from termit_app import music
    s = p.get("settings") if isinstance(p.get("settings"), dict) else {}
    if "volume" not in s:
        return []
    return ["-v", f"{music.volume(p):.1f}"]


def sound_file(event: str) -> str:
    return f"{SOUNDS_DIR}/{EVENTS[event]}.aiff"


def _event_wav(item_id: str, event: str) -> str:
    from termit_app import music
    return str(music.ensure_event(PACKS[item_id], event))


def _run(p: dict, path: str) -> bool:
    if not (_exists(AFPLAY) and _exists(path)):
        return False
    try:        # без ожидания: звук не держит игру
        _popen([AFPLAY] + _vol_args(p) + [path], stdin=subprocess.DEVNULL,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True


def ring(p: dict, event: str) -> Optional[str]:
    """Сыграть звук события: пакет → кассета → звонок, одно из них, не вместе.
    Вернуть, что прозвучало (id пакета | cassette | bell), или None."""
    owned = p.get("owned", [])
    chosen = pack(p)
    if chosen:
        try:
            path = _event_wav(chosen, event)
        except (OSError, ValueError):
            path = None
        if path and _run(p, path):
            return chosen
    if "cassette" in owned and _run(p, sound_file(event)):
        return "cassette"
    if "bell" in owned:
        # владелец 21.10: «нажимал test — никакого звука»: символ звонка \a iTerm2 часто глушит
        # или заменяет миганием, поэтому звонок — системный «дзинь» через afplay, \a — запасной
        if not _run(p, BELL_FILE):
            print("\a", end="", flush=True)
        return "bell"
    return None


def play(p: dict, event: str, played: Set[str]) -> Optional[str]:
    """Звук значимого события: включено, не глушится окружением, в этом ране ещё не звучало."""
    if (event not in EVENTS or event in played or not enabled(p)
            or os.environ.get("TERMIT_NO_SOUND")):
        return None
    got = ring(p, event)
    if got:
        played.add(event)
    return got
