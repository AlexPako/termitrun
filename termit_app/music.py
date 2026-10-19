"""Кассетная дека (часть 7а, K9): ./termit music — своя музыка в убежище.

Играет только по явной команде игрока (music play, music run on); покупка ничего не включает.
Музыка — сгенерированные synth петли (кэш WAV в paths.CACHE_DIR/music, в проекте и в
.gitignore). Фон — /bin/sh с ограниченным циклом afplay (не дольше MAX_SECONDS) в своей
группе процессов; в CACHE_DIR/music.json — pid, pgid, время старта процесса и случайный
токен (он же в argv цикла: termit-music-<токен>). stop гасит группу, только если сошлось всё:
процесс жив, лидер записанной группы, это не группа самого termit, его argv — ровно наш цикл
с нашим токеном и нашим файлом, время старта то же. Иначе — только удаляет pid-файл: чужой
процесс (в том числе получивший тот же PID) не тронется.

Под TERMIT_NO_SOUND и при ./termit sound off всё молчит (muted), _popen не вызывается.
Песочница о музыке не знает: играет только родитель. afplay запускают только этот модуль
и sound (статический тест)."""
import json
import os
import secrets
import signal
import stat
import subprocess
import time
import wave
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from termit_app import paths, synth, theme

AFPLAY = "/usr/bin/afplay"
TAG = "termit-music"
MAX_SECONDS = 30 * 60           # ничто не играет вечно: цикл кончится сам через ~30 минут
PREVIEW_SECONDS = 6
# $0 — метка с токеном (видна в ps), $1 — файл, $2 — громкость, $3 — сколько раз, $4 — предел
# в секундах: стена по часам, даже если afplay вдруг играет дольше файла; afplay упал — выход
LOOP = ('i=0; end=$(( $(/bin/date +%s) + $4 )); '
        'while [ "$i" -lt "$3" ] && [ "$(/bin/date +%s)" -lt "$end" ]; do '
        '/usr/bin/afplay -v "$2" "$1" || exit 0; i=$((i+1)); done')
PID_MAX_BYTES = 4096
KILL_WAIT = 0.5               # сколько повторять SIGTERM, пока группа не опустеет

# кассеты лестницы → (стиль synth, seed); бутлег bootN → (STYLES[N % 6], 1000 + N)
TAPES = {
    "tape_rain": ("darkwave", 11),
    "tape_8bit": ("chiptune", 23),
    "tape_chase": ("synthwave", 37),
    "tape_ice": ("drone", 41),
    "tape_neon": ("noir", 53),
    "tape_boss": ("boss", 67),
}

_popen = subprocess.Popen       # подменяются в тестах: ни один тест не играет звук
_killpg = os.killpg
_sleep = time.sleep
_child: Optional[subprocess.Popen] = None     # фон, запущенный этим процессом (чтобы прибрать)


def _taskinfo(pid: int) -> Optional[dict]:
    """pgid и время старта процесса из libproc (как procview); None — нет такого."""
    from termit_app import procview
    try:
        return procview.taskinfo(pid)
    except (OSError, ValueError, AttributeError):
        return None


def _procargs(pid: int) -> Optional[list]:
    from termit_app import procview
    try:
        return procview.procargs(pid)
    except (OSError, ValueError, AttributeError):
        return None


# нейтральные тексты; сеттинг — в теме (раздел cosmetics → music)
TEXTS = {
    "rewind": "Готовлю запись…",
    "title": "Проигрыватель",
    "no_player": "Проигрывателя нет — он на витрине: ./termit shop",
    "playing": "Играет: {name}.",
    "silent": "Тишина.",
    "volume": "Громкость: {n} из 10.",
    "run_on": "В ране: играет {name}, после рана замолкает.",
    "run_off": "В ране: тишина (./termit music run on — играть).",
    "tapes": "Записи:",
    "no_tapes": "Записей пока нет — они появятся на витрине.",
    "shelf": "На витрине, послушать даром: {ids}",
    "usage": "./termit music [play ID|stop|vol 1..10|preview ID|run on|off]",
    "ok": "Играет {name}. Остановить: ./termit music stop",
    "muted": "Звук выключен: ./termit sound on (или снята переменная TERMIT_NO_SOUND).",
    "missing": "Нет такой записи: {id}.",
    "not_owned": "{name} не куплено: ./termit shop",
    "error": "Не вышло запустить проигрыватель.",
    "stopped": "Остановлено.",
    "survived": "Почти: один процесс проигрывателя ещё жив — замолкнет сам, как доиграет петлю.",
    "unsure": "Проигрыватель не проверить — запись о нём пока держу. Повтори через пару "
              "секунд: ./termit music stop",
    "not_playing": "И так тихо.",
    "vol_set": "Громкость {n} из 10.",
    "run_set_on": "Теперь в ране будет играть {name}; после рана — тишина.",
    "run_set_off": "В ране — тишина.",
    "preview": "Шесть секунд: {name}.",
    "no_tape": "Нечего играть: записи — на витрине, ./termit shop",
}


def text(key: str, **kw) -> str:
    t = ((theme.story("cosmetics") or {}).get("music") or {}).get(key) or TEXTS[key]
    return t.format(**kw) if kw else t


# --- Кассеты и кэш --------------------------------------------------------------------------

def tape_spec(item_id) -> Optional[Tuple[str, int]]:
    if item_id in TAPES:
        return TAPES[item_id]
    from termit_app import cosmetics
    n = cosmetics.boot_n(item_id)
    return (synth.STYLES[n % len(synth.STYLES)], 1000 + n) if n is not None else None


def _dir() -> Path:
    return Path(paths.CACHE_DIR)


def wav_path(item_id: str) -> Path:
    return _dir() / "music" / f"{item_id}-v{synth.SYNTH_VERSION}.wav"


def cached(item_id: str) -> bool:
    return wav_path(item_id).is_file()


def ensure(item_id: str) -> Path:
    """WAV кассеты в кэше; нет — сгенерировать (с репликой «перематывает»)."""
    path = wav_path(item_id)
    if not path.is_file():
        from termit_app import ui
        ui.say(text("rewind"))
        style, seed = tape_spec(item_id)
        synth.write_wav(path, synth.render(style, seed))
    return path


def event_path(pack: str, event: str) -> Path:
    return _dir() / "sfx" / f"{pack}-{event}-v{synth.SYNTH_VERSION}.wav"


def ensure_event(pack: str, event: str) -> Path:
    """WAV звука события пакета (короткий, генерируется молча)."""
    path = event_path(pack, event)
    if not path.is_file():
        synth.write_wav(path, synth.event(pack, event))
    return path


def _seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except (OSError, EOFError, wave.Error):
        return 0.0


# --- Настройки ------------------------------------------------------------------------------

def _settings(p: dict) -> dict:
    s = p.get("settings")
    return s if isinstance(s, dict) else {}


def volume_level(p: dict) -> int:
    v = _settings(p).get("volume")
    return v if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 10 else 5


def volume(p: dict) -> float:
    """settings["volume"] 1..10 → 0.1..1.0; нет или мусор — 5 (0.5)."""
    return volume_level(p) / 10


def set_volume(p: dict, n) -> bool:
    if not (isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 10):
        return False
    p.setdefault("settings", {})["volume"] = n
    return True


def muted(p: dict) -> bool:
    from termit_app import sound
    return bool(os.environ.get("TERMIT_NO_SOUND")) or not sound.enabled(p)


def _owned(p: dict) -> List[str]:
    return [x for x in (p.get("owned") or ()) if isinstance(x, str)]


def owned_tapes(p: dict) -> List[str]:
    """Купленные записи: кассеты лестницы и бутлеги, в порядке покупки."""
    return [x for x in _owned(p) if tape_spec(x) is not None]


def chosen_tape(p: dict) -> Optional[str]:
    """Последняя сыгранная (если куплена), иначе первая купленная."""
    have = owned_tapes(p)
    t = _settings(p).get("tape")
    return t if t in have else (have[0] if have else None)


def run_enabled(p: dict) -> bool:
    return _settings(p).get("music_run") is True


def set_run(p: dict, on: bool) -> None:
    p.setdefault("settings", {})["music_run"] = bool(on)


# --- PID-файл -------------------------------------------------------------------------------

def _pid_file() -> Path:
    return _dir() / "music.json"


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _read() -> Optional[dict]:
    """pid-файл: не по симлинку, обычный файл ≤ PID_MAX_BYTES, все поля на месте."""
    try:
        fd = os.open(str(_pid_file()), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > PID_MAX_BYTES:
            return None
        info = json.loads(os.read(fd, PID_MAX_BYTES + 1).decode("utf-8"))
    except (OSError, ValueError):
        return None
    finally:
        os.close(fd)
    if not isinstance(info, dict):
        return None
    pid, pgid, start, token, track = (info.get(k) for k in
                                      ("pid", "pgid", "start", "token", "track"))
    if not (_int(pid) and pid > 1 and _int(pgid) and pgid == pid
            and isinstance(start, (int, float)) and not isinstance(start, bool)
            and isinstance(token, str) and len(token) == 16
            and all(c in "0123456789abcdef" for c in token)
            and isinstance(track, str) and tape_spec(track) is not None):
        return None
    return info


def _write(info: dict) -> None:
    path = _pid_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(info), encoding="utf-8")
    os.replace(tmp, path)


def _forget() -> None:
    try:
        _pid_file().unlink()
    except OSError:
        pass


def _argv(token: str, track: str) -> list:
    """argv цикла без хвоста (громкость и счётчики сверять незачем)."""
    return ["/bin/sh", "-c", LOOP, f"{TAG}-{token}", str(wav_path(track))]


def _verdict(info: dict) -> str:
    """Процесс из pid-файла: "ours" — наш цикл (жив, лидер записанной группы, не группа
    termit, время старта то же, argv — наш цикл с нашим токеном и файлом); "unknown" — жив,
    pid, группа и время старта сошлись, а argv так и не удалось прочитать или сверить;
    "no" — мёртв или это точно другой процесс (иное время старта, иная группа)."""
    pid = info["pid"]
    if pid in (os.getpid(), os.getpgrp()) or info["pgid"] == os.getpgrp():
        return "no"

    def same(ti) -> bool:
        return bool(ti) and ti.get("pgid") == info["pgid"] == pid and \
            abs(float(ti.get("start", -1)) - float(info["start"])) <= 1e-6
    if not same(_taskinfo(pid)):
        return "no"
    want = _argv(info["token"], info["track"])
    for attempt in range(40):   # /bin/sh на macOS — прослойка, она exec'ает bash: в этот миг
        argv = _procargs(pid)   # argv не читается — подождать, пока процесс жив
        if argv is not None and argv[:len(want)] == want:
            return "ours"
        if attempt == 39:
            break
        _sleep(0.05)
        if not same(_taskinfo(pid)):
            return "no"         # умер (или PID уже чужой) — ждать нечего
    return "unknown"


def _ours(info: dict) -> bool:
    return _verdict(info) == "ours"


def playing() -> Optional[str]:
    """Что играет (id записи) или None."""
    info = _read()
    return info["track"] if info is not None and _ours(info) else None


def is_playing() -> bool:
    return playing() is not None


def _reap() -> None:
    """Прибрать свой фон (без зомби)."""
    global _child
    if _child is None:
        return
    try:
        _child.wait(timeout=2)
    except (subprocess.SubprocessError, OSError, AttributeError):
        pass
    _child = None


def _halt_group(pg: int) -> bool:
    """Погасить группу: SIGTERM повторяется, пока группа не опустеет (ESRCH), но не дольше
    KILL_WAIT; потом SIGKILL. Повтор нужен: сигнал, пришедший в миг fork очередной команды
    цикла, новорождённый ребёнок не получает и переживает sh. Повторять безопасно: пока в
    группе есть хоть один процесс, её номер не достанется новому. True — группа пуста."""
    sig, end = signal.SIGTERM, time.monotonic() + KILL_WAIT
    while True:
        try:
            _killpg(pg, sig)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass                # macOS: в группе остались только зомби — ждём, пока приберут
        if _child is not None and _child.pid == pg:
            try:                # прибрать зомби своего лидера: он держит группу «живой»
                _child.poll()
            except (OSError, AttributeError):
                pass
        if time.monotonic() >= end:
            if sig == signal.SIGKILL:
                break
            sig, end = signal.SIGKILL, time.monotonic() + 0.2
        _sleep(0.01)
    try:
        _killpg(pg, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return _zombies_only(pg)
    except OSError:
        pass
    return False


def _zombies_only(pg: int) -> bool:
    """EPERM от killpg на macOS — группа из одних зомби (звука в ней нет). Проверить по
    списку процессов: живых участников группы нет."""
    from termit_app import procview
    try:
        for pid in procview.list_pids():
            ti = procview.taskinfo(pid)
            if ti and ti.get("pgid") == pg and ti.get("status") != 5:     # 5 — зомби
                return False
    except (OSError, ValueError, AttributeError):
        return False
    return True


def _kill_child() -> bool:
    """Погасить фон, запущенный этим процессом, по объекту Popen: пока мы его не прибрали,
    PID не может достаться другому процессу. Нужен, когда pid-файла ещё нет (Ctrl+C между
    запуском и записью) или его argv так и не прочитался. True — группа пуста."""
    if _child is None:
        return True
    empty = True
    try:
        if _child.poll() is None:
            empty = _halt_group(_child.pid)
    except (OSError, AttributeError):
        pass
    _reap()
    return empty


def _alive_child() -> bool:
    try:
        return _child is not None and _child.poll() is None
    except (OSError, AttributeError):
        return False


def halt() -> str:
    """Погасить фон (sh и afplay — одной группой). Код: idle — гасить нечего; stopped —
    группа пуста; survived — что-то пережило и SIGKILL (честно сказать игроку); unsure —
    процесс жив, но проверить, что он наш, не вышло: pid-файл оставлен, повторить позже."""
    info = _read()
    if info is None:
        if os.path.lexists(str(_pid_file())):
            _forget()           # мусор в файле: убрать, ничего не трогая
        return "idle"
    mine = _child is not None and _child.pid == info["pid"] and _alive_child()
    if mine:                    # свой неприбранный ребёнок: личность — сам объект Popen
        code = "stopped" if _kill_child() else "survived"
    else:
        verdict = _verdict(info)
        if verdict == "ours":
            code = "stopped" if _halt_group(info["pid"]) else "survived"
        elif verdict == "unknown":
            return "unsure"     # учёт не теряем: pid-файл остаётся, повторить позже
        else:
            code = "idle"
    _forget()
    return code


def stop() -> bool:
    """Погасить фон. True — было что гасить (группа пуста или почти: см. halt)."""
    return halt() in ("stopped", "survived")


# --- Игра -----------------------------------------------------------------------------------

def _check(p: dict, item_id: str) -> str:
    if tape_spec(item_id) is None:
        return "missing"
    if "player" not in _owned(p):
        return "no_player"
    if item_id not in _owned(p):
        return "not_owned"
    return "ok"


def play(p: dict, item_id: str, loops: Optional[int] = None) -> str:
    """Включить запись в фоне. Код: ok|muted|missing|no_player|not_owned|error.
    loops — сколько раз прокрутить (по умолчанию — сколько влезает в MAX_SECONDS)."""
    global _child
    code = _check(p, item_id)
    if code != "ok":
        return code
    if muted(p):
        return "muted"
    try:
        path = ensure(item_id)
    except OSError:
        return "error"
    dur = _seconds(path) or 1.0
    cap = max(1, int(MAX_SECONDS // dur))
    loops = cap if loops is None else max(1, min(int(loops), cap))
    stop()
    _kill_child()
    token = secrets.token_hex(8)
    try:
        _child = _popen(_argv(token, item_id) + [f"{volume(p):.1f}", str(loops), str(MAX_SECONDS)],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        _child = None
        return "error"
    try:
        ti = _taskinfo(_child.pid)
        if not ti or ti.get("pgid") != _child.pid:
            _kill_child()       # не смогли запомнить «кто это» — значит, и не оставляем
            return "error"
        _write({"pid": _child.pid, "pgid": ti["pgid"], "start": ti["start"], "token": token,
                "track": item_id})
    except BaseException:       # Ctrl+C между запуском и записью: фон не должен остаться
        _kill_child()
        raise
    p.setdefault("settings", {})["tape"] = item_id
    return "ok"


def can_preview(p: dict, item_id: str) -> str:
    """Послушать можно купленное и то, что лежит на витрине (бутлег — даром до покупки)."""
    if tape_spec(item_id) is None:
        return "missing"
    from termit_app import cosmetics
    if item_id in _owned(p) or item_id in cosmetics.offers(p):
        return "ok"
    return "not_owned"


def preview(p: dict, item_id: str) -> str:
    """Шесть секунд записи (afplay -t 6), без цикла и без PID-файла. Фон дека гасится."""
    code = can_preview(p, item_id)
    if code != "ok":
        return code
    if muted(p):
        return "muted"
    try:
        path = ensure(item_id)
    except OSError:
        return "error"
    stop()
    try:
        _popen([AFPLAY, "-t", str(PREVIEW_SECONDS), "-v", f"{volume(p):.1f}", str(path)],
               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
               start_new_session=True)
    except OSError:
        return "error"
    return "ok"


def run_start(p: dict) -> bool:
    """Начало рана: run on и есть что играть — включить. True — включили мы (гасить в конце).
    Уже играет то, что игрок включил сам, — не трогаем."""
    if not run_enabled(p) or muted(p) or is_playing():
        return False
    tape = chosen_tape(p)
    return bool(tape) and play(p, tape) == "ok"


@contextmanager
def in_run(p: dict) -> Iterator[None]:
    """Музыка на время рана: стоп — в finally, в том числе по Ctrl+C."""
    before = _child
    started = False
    try:
        started = run_start(p)
        yield
    finally:
        if started:
            stop()
        if _child is not None and _child is not before:
            _kill_child()       # запущен в этом ране, но pid-файл не успел (Ctrl+C)

