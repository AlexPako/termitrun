"""Процедурный синтез звука (часть 7а, K8): музыка кассет и звуки редких событий.

Только stdlib (wave, math, array, random): ни сети, ни чужих файлов. Всё детерминировано —
один и тот же (стиль, seed) даёт те же сэмплы байт в байт, поэтому кэш WAV можно
пересоздать в любой момент (версия алгоритма — SYNTH_VERSION в имени файла).

Модуль ничего не играет: он только считает сэмплы и пишет WAV. Играют sound и music.

Петля рендерится «по кругу»: хвосты нот, вылезшие за конец, складываются в начало, эхо
и фильтр тоже идут по кругу, — так последний сэмпл переходит в первый без щелчка
(вместо кроссфейда последнего такта: шов просто отсутствует).

Скорость: таблицы волн (без math.sin в цикле), сегменты огибающей с линейным шагом,
сборка в списке float и одна конвертация в array('h') в конце."""
import math
import os
import random
import sys
import wave
from array import array
from pathlib import Path
from typing import Dict, List, Optional, Tuple

RATE = 22050
SYNTH_VERSION = 1
STYLES = ("darkwave", "chiptune", "synthwave", "drone", "noir", "boss")
PACKS = ("synth", "chip", "noir")
EVENT_NAMES = ("boss_down", "record", "milestone")

PEAK = 16383                  # нормализация к −6 dB (32767 / 2, вниз)

# --- Таблицы волн --------------------------------------------------------------------------

TSIZE = 2048
_MASK = TSIZE - 1
_TABLES: Dict[str, List[float]] = {}


def _table(name: str) -> List[float]:
    """Таблица волны (лениво): sine, saw, tri, sq50, sq25, sq12."""
    t = _TABLES.get(name)
    if t is not None:
        return t
    n = TSIZE
    if name == "sine":
        t = [math.sin(2 * math.pi * i / n) for i in range(n)]
    elif name == "saw":
        # пила, сглаженная тремя гармониками сверху: меньше алиасинга на 22 кГц
        t = [sum(math.sin(2 * math.pi * k * i / n) / k for k in range(1, 12)) * 0.55
             for i in range(n)]
    elif name == "tri":
        t = [1 - 4 * abs(i / n - 0.5) for i in range(n)]
    elif name.startswith("sq"):
        duty = {"sq50": 0.5, "sq25": 0.25, "sq12": 0.125}[name]
        t = [0.6 if i < n * duty else -0.6 for i in range(n)]
    else:
        raise ValueError(name)
    _TABLES[name] = t
    return t


def _noise(seed: int, n: int) -> List[float]:
    rnd = random.Random(seed * 7919 + 13)
    return [rnd.uniform(-1.0, 1.0) for _ in range(n)]


def _freq(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


# --- Голоса ---------------------------------------------------------------------------------

def _tone(buf: List[float], start: int, length: int, freq: float, wave_name: str, amp: float,
          adsr: Tuple[float, float, float, float]) -> None:
    """Нота в buf (прибавить): таблица волны × ADSR. adsr — (атака с, спад с, уровень, хвост с);
    длина — время удержания до хвоста. Индексы за концом buf не пишутся (у buf есть запас)."""
    table = _table(wave_name)
    a, d, s, r = adsr
    na = max(1, int(a * RATE))
    nd = max(1, int(d * RATE))
    nr = max(1, int(r * RATE))
    hold = max(length, na + nd)
    inc = freq * TSIZE / RATE
    ph = 0.0
    pos = start
    limit = len(buf)
    # (сколько сэмплов, огибающая в начале, шаг огибающей)
    segs = ((na, 0.0, amp / na), (nd, amp, (amp * s - amp) / nd),
            (hold - na - nd, amp * s, 0.0), (nr, amp * s, -amp * s / nr))
    for count, env, step in segs:
        if count <= 0:
            continue
        end = min(pos + count, limit)
        for i in range(pos, end):
            buf[i] += table[int(ph) & _MASK] * env
            ph += inc
            env += step
        pos += count
        if pos >= limit:
            return


def _kick(buf: List[float], start: int, amp: float) -> None:
    """Синус с падением тона 140 → 45 Гц за ~0,25 с."""
    table = _table("sine")
    n = int(0.28 * RATE)
    ph = 0.0
    f = 140.0
    fall = (45.0 / 140.0) ** (1.0 / n)
    env = amp
    dec = 0.00012 ** (1.0 / n)
    end = min(start + n, len(buf))
    k = TSIZE / RATE
    for i in range(start, end):
        buf[i] += table[int(ph) & _MASK] * env
        ph += f * k
        f *= fall
        env *= dec


def _hit(buf: List[float], start: int, noise: List[float], amp: float, length: float,
         bright: bool) -> None:
    """Шум с экспоненциальным затуханием: snare (bright=False) или hat через ФВЧ (True)."""
    n = int(length * RATE)
    env = amp
    dec = 0.001 ** (1.0 / n)
    end = min(start + n, len(buf))
    m = len(noise)
    j = (start * 31) % m
    lp = 0.0
    att = max(1, int(0.002 * RATE))      # 2 мс атаки: шум не прыгает с нуля (щелчок)
    for i in range(start, end):
        x = noise[j]
        j += 1
        if j == m:
            j = 0
        if bright:           # ФВЧ: шум минус его сглаженная копия
            lp += 0.35 * (x - lp)
            x -= lp
        k = i - start
        buf[i] += x * (env * k / att if k < att else env)
        env *= dec


# --- Стили ----------------------------------------------------------------------------------
# bpm — темп (8 тактов по 4/4 = 14–20 с); bass/lead/pad — волна и огибающая; lp — ФНЧ на
# миксе (0..1, больше — ярче); echo — (доля задержки в шестнадцатых, обратная связь, уровень);
# drums — рисунок на 16 шагов: k — бочка, s — малый, h — хэт; density — вероятность ноты лида.

STYLE: Dict[str, dict] = {
    "darkwave": {"bpm": 104, "bass": ("saw", 0.40, (0.005, 0.10, 0.6, 0.06), 8),
                 "lead": ("sq50", 0.16, (0.01, 0.12, 0.4, 0.15), "arp"),
                 "pad": ("tri", 0.10), "lp": 0.22, "echo": (3, 0.38, 0.30),
                 "drums": "k...h...s...h.h.", "density": 0.8, "octave": 2},
    "chiptune": {"bpm": 132, "bass": ("tri", 0.45, (0.002, 0.05, 0.8, 0.02), 8),
                 "lead": ("sq25", 0.18, (0.002, 0.06, 0.5, 0.03), "arp"),
                 "pad": None, "lp": 0.9, "echo": (2, 0.2, 0.15),
                 "drums": "k.h.s.h.k.h.s.hh", "density": 0.9, "octave": 3},
    "synthwave": {"bpm": 112, "bass": ("saw", 0.38, (0.004, 0.08, 0.7, 0.05), 8),
                  "lead": ("sq50", 0.15, (0.02, 0.2, 0.6, 0.2), "melody"),
                  "pad": ("saw", 0.08), "lp": 0.35, "echo": (3, 0.42, 0.32),
                  "drums": "k.h.s.h.k.h.s.h.", "density": 0.55, "octave": 2},
    "drone": {"bpm": 98, "bass": ("sine", 0.55, (0.6, 0.5, 0.8, 1.2), 1),
              "lead": ("sine", 0.14, (0.15, 0.3, 0.5, 0.8), "melody"),
              "pad": ("tri", 0.16), "lp": 0.12, "echo": (6, 0.55, 0.4),
              "drums": "........h.......", "density": 0.18, "octave": 2},
    "noir": {"bpm": 100, "bass": ("tri", 0.50, (0.01, 0.2, 0.5, 0.15), 4),
             "lead": ("tri", 0.20, (0.005, 0.35, 0.25, 0.4), "melody"),
             "pad": ("sine", 0.08), "lp": 0.3, "echo": (3, 0.3, 0.22),
             "drums": "h..h..h.s..h..h.", "density": 0.35, "octave": 3},
    "boss": {"bpm": 136, "bass": ("sq50", 0.34, (0.002, 0.05, 0.7, 0.03), 16),
             "lead": ("saw", 0.14, (0.003, 0.08, 0.5, 0.05), "arp"),
             "pad": None, "lp": 0.4, "echo": (3, 0.25, 0.18),
             "drums": "k.h.k.h.s.h.k.hk", "density": 1.0, "octave": 2},
}

MINOR = (0, 2, 3, 5, 7, 8, 10)
# ступени (от 0) натурального минора; аккорд на каждый такт, 4 такта × 2
PROGRESSIONS = ((0, 5, 2, 6), (0, 3, 5, 4), (0, 6, 5, 6), (0, 5, 3, 4), (0, 2, 6, 5))


def loop_seconds(style: str, bars: int = 8) -> float:
    return bars * 16 * _step_len(style) / RATE


def _step_len(style: str) -> int:
    """Длина шестнадцатой в сэмплах (целая — петля без дробного дрейфа)."""
    return int(RATE * 60 / STYLE[style]["bpm"] / 4)


def _degree(root: int, deg: int) -> int:
    """MIDI ноты ступени минора (deg может выходить за октаву)."""
    return root + 12 * (deg // 7) + MINOR[deg % 7]


def _sequence(style: str, seed: int, steps: int) -> List[tuple]:
    """События (шаг, голос, нота/вид, длина в шагах) по seed: тональность, прогрессия, бас,
    арпеджио или мелодия случайным блужданием, барабаны по рисунку стиля."""
    st = STYLE[style]
    rnd = random.Random(seed)
    root = 36 + rnd.randrange(0, 8)               # C2..G2
    prog = PROGRESSIONS[rnd.randrange(len(PROGRESSIONS))]
    events: List[tuple] = []
    per_bar = st["bass"][3]
    blen = 16 // per_bar
    walk = rnd.randrange(0, 5)
    for step in range(steps):
        bar, pos = divmod(step, 16)
        chord = prog[bar % 4]
        if pos % blen == 0:
            note = _degree(root, chord)
            if per_bar >= 8 and (pos // blen) % 2 == 1 and rnd.random() < 0.3:
                note += 12                         # октавный подскок
            events.append((step, "bass", note, blen))
        if pos == 0 and st["pad"]:
            for d in (0, 2, 4):
                events.append((step, "pad", _degree(root + 12, chord + d), 16))
        kind = st["lead"][3]
        lead_root = root + 12 * st["octave"]
        if kind == "arp":
            if rnd.random() < st["density"]:
                d = (0, 2, 4, 7)[pos % 4]
                events.append((step, "lead", _degree(lead_root, chord + d), 1))
        elif pos % 2 == 0 and rnd.random() < st["density"]:
            walk = max(-2, min(9, walk + rnd.choice((-2, -1, -1, 1, 1, 2, 0))))
            events.append((step, "lead", _degree(lead_root, walk), 2 if rnd.random() < 0.7 else 4))
        hit = st["drums"][pos]
        if hit != ".":
            events.append((step, hit, None, 1))
    return events


def _fold(buf: List[float], n: int) -> List[float]:
    """Хвосты за концом петли — в начало (по кругу, сколько бы раз ни обернулось)."""
    out = buf[:n]
    for off in range(n, len(buf), n):
        chunk = buf[off:off + n]
        for i, x in enumerate(chunk):
            out[i] += x
    return out


def _lowpass(buf: List[float], a: float) -> List[float]:
    """Однополюсный ФНЧ по кругу: первый проход прогревает состояние, второй пишет."""
    y = 0.0
    for x in buf:
        y += a * (x - y)
    out = [0.0] * len(buf)
    for i, x in enumerate(buf):
        y += a * (x - y)
        out[i] = y
    return out


def _echo(buf: List[float], delay: int, fb: float, level: float) -> List[float]:
    """Эхо с обратной связью по кругу: wet[i] = buf[i−d] + fb·wet[i−d] (два оборота)."""
    n = len(buf)
    if n == 0 or delay <= 0:
        return buf
    wet = [0.0] * n
    for _ in range(2):
        for i in range(n):
            j = (i - delay) % n
            wet[i] = buf[j] + fb * wet[j]
    return [x + level * w for x, w in zip(buf, wet)]


def _finish(buf: List[float]) -> array:
    """Мягкое ограничение (tanh) и нормализация к −6 dB → int16."""
    peak = max((abs(x) for x in buf), default=0.0) or 1.0
    drive = 1.6
    norm = math.tanh(drive)
    shaped = [math.tanh(drive * x / peak) / norm for x in buf]
    top = max((abs(x) for x in shaped), default=0.0) or 1.0
    k = PEAK / top
    return array("h", (int(round(x * k)) for x in shaped))


def mix_floats(style: str, seed: int, bars: int = 8, steps: Optional[int] = None) -> List[float]:
    """Сведение петли во float (до ограничения): для render и тестов."""
    if style not in STYLE:
        raise ValueError(f"нет стиля {style!r}")
    st = STYLE[style]
    steps = bars * 16 if steps is None else max(1, steps)
    sl = _step_len(style)
    n = steps * sl
    tail = int(1.6 * RATE)
    buf = [0.0] * (n + tail)
    hats = [0.0] * (n + tail)
    noise = _noise(seed, 4096)
    bw, bamp, badsr, _ = st["bass"]
    lw, lamp, ladsr, _ = st["lead"]
    for step, voice, note, length in _sequence(style, seed, steps):
        at = step * sl
        if voice == "bass":
            _tone(buf, at, length * sl - int(badsr[3] * RATE * 0.5), _freq(note), bw, bamp, badsr)
        elif voice == "lead":
            _tone(buf, at, length * sl, _freq(note), lw, lamp, ladsr)
        elif voice == "pad":
            pw, pamp = st["pad"]
            _tone(buf, at, length * sl, _freq(note), pw, pamp, (0.3, 0.4, 0.7, 0.5))
        elif voice == "k":
            _kick(buf, at, 0.8)
        elif voice == "s":
            _hit(buf, at, noise, 0.32, 0.16, bright=False)
        elif voice == "h":
            _hit(hats, at, noise, 0.14, 0.05, bright=True)
    mixed = _lowpass(_fold(buf, n), st["lp"])
    mixed = [x + h for x, h in zip(mixed, _fold(hats, n))]
    eq, fb, level = st["echo"]
    return _echo(mixed, eq * sl, fb, level)


def render(style: str, seed: int, bars: int = 8, steps: Optional[int] = None) -> array:
    """Петля: int16, моно, RATE; steps — длина в шестнадцатых (тесты режут до коротких)."""
    return _finish(mix_floats(style, seed, bars, steps))


# --- События --------------------------------------------------------------------------------
# пакет: волна, огибающая, ФНЧ, эхо; событие: ноты (полутоны от корня, задержка в с, длина в с)

PACK: Dict[str, dict] = {
    "synth": {"wave": "saw", "adsr": (0.01, 0.15, 0.5, 0.35), "lp": 0.3, "echo": 0.12, "root": 57},
    "chip": {"wave": "sq25", "adsr": (0.002, 0.05, 0.6, 0.05), "lp": 1.0, "echo": 0.0, "root": 69},
    "noir": {"wave": "tri", "adsr": (0.003, 0.4, 0.2, 0.4), "lp": 0.4, "echo": 0.09, "root": 60},
}
EVENT_NOTES: Dict[str, Tuple[Tuple[int, float, float], ...]] = {
    # взлом стража: минорный аккорд разворачивается вверх и разрешается в мажор
    "boss_down": ((0, 0.0, 0.5), (3, 0.08, 0.42), (7, 0.16, 0.34), (12, 0.24, 0.5),
                  (16, 0.40, 0.45)),
    "record": ((0, 0.0, 0.12), (7, 0.12, 0.25)),                       # два шага вверх
    "milestone": ((0, 0.0, 0.18), (4, 0.15, 0.18), (7, 0.30, 0.3)),    # три ступени
}


def event(pack: str, event_name: str) -> array:
    """Короткий звук события (0,3–1,5 с), затухает в ноль."""
    if pack not in PACK:
        raise ValueError(f"нет пакета {pack!r}")
    if event_name not in EVENT_NOTES:
        raise ValueError(f"нет события {event_name!r}")
    pk = PACK[pack]
    notes = EVENT_NOTES[event_name]
    a, d, s, r = pk["adsr"]
    total = max(at + ln for _, at, ln in notes) + r + (0.25 if pk["echo"] else 0.02)
    n = int(total * RATE)
    buf = [0.0] * n
    for semi, at, ln in notes:
        _tone(buf, int(at * RATE), int(ln * RATE), _freq(pk["root"] + semi), pk["wave"], 0.3,
              pk["adsr"])
    if pk["lp"] < 1.0:
        y = 0.0
        a_lp = pk["lp"]
        for i, x in enumerate(buf):
            y += a_lp * (x - y)
            buf[i] = y
    if pk["echo"]:
        dl = int(pk["echo"] * RATE)
        for i in range(dl, n):
            buf[i] += 0.35 * buf[i - dl]
    fade = min(n, int(0.03 * RATE))          # последние 30 мс — в ноль: без щелчка в конце
    for j in range(fade):
        buf[n - fade + j] *= 1 - (j + 1) / fade
    return _finish(buf)


# --- WAV ------------------------------------------------------------------------------------

def write_wav(path: Path, samples: array) -> None:
    """WAV моно 16 бит RATE; атомарно: временный файл рядом и os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = samples
    if data.itemsize != 2:
        raise ValueError("нужен array('h')")
    try:
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            if sys.byteorder == "big":          # WAV — little-endian
                data = array("h", data)
                data.byteswap()
            w.writeframes(data.tobytes())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
