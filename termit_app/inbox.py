"""Сообщения на деке (inbox, спека 2.5): то, что раньше вываливалось в итог рана, —
«Завтра», подарки, витрина, охота, срочный заказ, вопросы утилит, склада и «Сделал?».
Храним готовый текст на момент события, последние KEEP штук; открыл — прочитал.
При загрузке модуль ничего из игры не импортирует: его зовёт progress._normalize."""
import contextlib
import io
import re
import textwrap
import zlib
from datetime import date
from typing import Callable, Dict, List, Optional

KEEP = 30
MAX_TEXT = 2000
NAME_MAX = 12
SENDERS = {"raven": "Ворон", "gift": "Подарок", "shop": "Витрина", "system": "Система"}
# Отправитель — gift/shop/system или ключ персонажа темы (raven и др.). Тему при загрузке
# не импортируем, поэтому ключ — любой короткий ascii-ключ; имя для экрана — sender_name.
SENDER_KEY = re.compile(r"[a-z][a-z0-9_]{0,23}")
ANSI = re.compile(r"\033\[[0-9;?]*[A-Za-z]")
EMPTY = "На деке пусто. Сообщения приходят после ранов."
NO_NEW = "Новых сообщений нет. Весь список — inbox."
NO_SUCH = "Сообщения {n} нет. Весь список — inbox."
WAITS = "ждёт ответа"
ASK_PROMPT = "   Ответ (y — да, n — нет; Enter — решу потом): "
LIST_TAIL = "  inbox N — открыть · inbox next — следующее новое"
WIDTH = 78
SUMMARY = "✉ На деке {n} {word} — прочтёшь в убежище: inbox."


def _sender(key) -> str:
    ok = isinstance(key, str) and (key in SENDERS or SENDER_KEY.fullmatch(key))
    return key if ok else "system"


def sender_name(key: str) -> str:
    """Имя отправителя для экрана: из раздела characters темы (если он есть), из SENDERS,
    иначе сам ключ с заглавной. Тему берём только здесь, на экране."""
    from termit_app import theme
    chars = theme.story("characters")
    name = chars.get(key) if isinstance(chars, dict) else None
    if not (isinstance(name, str) and name):
        name = SENDERS.get(key) or key.capitalize()
    return name if len(name) <= NAME_MAX else name[:NAME_MAX - 1] + "…"


def _iso(d) -> bool:
    if not isinstance(d, str):
        return False
    try:
        date.fromisoformat(d)
    except ValueError:
        return False
    return True


def _trim(msgs: List[dict]) -> List[dict]:
    """Больше KEEP — уходят старые прочитанные, потом старые без вопроса; непрочитанный
    вопрос молча не выкидывается никогда."""
    out = list(msgs)
    extra = len(out) - KEEP
    for gone in (lambda m: m["read"], lambda m: m.get("ask") is None):
        i = 0
        while extra > 0 and i < len(out):
            if gone(out[i]):
                del out[i]
                extra -= 1
            else:
                i += 1
    return out


def clean(raw) -> List[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    ids = set()
    for m in raw:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if not isinstance(mid, int) or isinstance(mid, bool) or mid in ids:
            continue
        if not isinstance(m.get("text"), str):
            continue
        ask = m.get("ask")
        if (isinstance(ask, dict) and isinstance(ask.get("kind"), str)
                and isinstance(ask.get("id"), str)):
            ask = {"kind": ask["kind"], "id": ask["id"]}
        else:
            ask = None
        ids.add(mid)
        out.append({"id": mid,
                    "key": m["key"] if isinstance(m.get("key"), str) else "",
                    "kind": m["kind"] if isinstance(m.get("kind"), str) else "",
                    "from": _sender(m.get("from")),
                    "day": m["day"] if _iso(m.get("day")) else "",
                    "text": m["text"][:MAX_TEXT], "read": m.get("read") is True, "ask": ask})
    return _trim(out)


def next_id(p: dict) -> int:
    """Номера не повторяются, даже когда старое сообщение вытеснено: счётчик inbox_seq."""
    seq = p.get("inbox_seq")
    seq = seq if isinstance(seq, int) and not isinstance(seq, bool) and seq > 0 else 0
    box = p.get("inbox") if isinstance(p.get("inbox"), list) else []
    return max([seq] + [m["id"] for m in box if isinstance(m, dict)]) + 1


def post(p: dict, kind: str, sender: str, text: str, key: str, day: date,
         ask: Optional[dict] = None) -> Optional[dict]:
    """Новое сообщение; тот же key уже есть (повторный итог, перезапуск) — None."""
    box = p.setdefault("inbox", [])
    if key and any(m.get("key") == key for m in box):
        return None
    mid = next_id(p)
    p["inbox_seq"] = mid
    msg = {"id": mid, "key": key, "kind": kind,
           "from": _sender(sender), "day": day.isoformat(),
           "text": text.strip("\n")[:MAX_TEXT], "read": False, "ask": ask}
    box.append(msg)
    p["inbox"] = _trim(box)
    return msg if msg in p["inbox"] else None


def unread(p: dict) -> List[dict]:
    """Единственная реализация «непрочитанного»; hubview.unread_count берёт её длину.
    Терпит мусор в p["inbox"] (не список, не словари)."""
    box = p.get("inbox")
    if not isinstance(box, list):
        return []
    return [m for m in box if isinstance(m, dict) and not m.get("read")]


def get(p: dict, msg_id: int) -> Optional[dict]:
    return next((m for m in p.get("inbox") or [] if m["id"] == msg_id), None)


@contextlib.contextmanager
def collect(p: dict, kind: str, sender: str, key: str, day: date, on: bool = True,
            by_text: bool = False):
    """Всё, что блок напечатает, — одним сообщением на деку (а не в итог рана). on=False —
    печать как была (разовый ./termit). Блок может положить box["ask"] — вопрос y/n.
    by_text — к ключу дописывается отпечаток текста: источник с состоянием (флаг подсказки,
    завоз) второй раз за день скажет другое — и это новое сообщение, а не дубль."""
    if not on:
        yield {}
        return
    buf = io.StringIO()
    box = {}
    with contextlib.redirect_stdout(buf):
        yield box
    text = ANSI.sub("", buf.getvalue()).strip("\n")
    if text.strip():
        if by_text:
            key = f"{key}:{zlib.crc32(text.encode()):08x}"
        post(p, kind, sender, text, key, day, ask=box.get("ask"))


def when(day_iso: str, today: date) -> str:
    if not _iso(day_iso):
        return ""
    n = (today - date.fromisoformat(day_iso)).days
    return "сегодня" if n <= 0 else "вчера" if n == 1 else f"{n} дн. назад"


def _first_line(text: str) -> str:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    return lines[0] if lines else ""


def _fit(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def _shown(box: List[dict]) -> List[dict]:
    """Все непрочитанные и самые свежие прочитанные — до 10 всего (непрочитанных больше
    десяти — показываются все); порядок как в деке."""
    room = max(10 - sum(1 for m in box if not m["read"]), 0)
    read = [m for m in box if m["read"]]
    keep = {id(m) for m in (read[-room:] if room else [])}
    return [m for m in box if not m["read"] or id(m) in keep]


def list_lines(p: dict, today: date) -> List[str]:
    box = p.get("inbox") or []
    if not box:
        return [EMPTY]
    new = len(unread(p))
    out = [" ✉ ДЕКА · сообщения" + (f" · новых: {new}" if new else "")]
    for m in reversed(_shown(box)):
        dot = "●" if not m["read"] else " "
        right = WAITS if m["ask"] else when(m["day"], today)
        left = f"  {dot} {m['id']:>2}  {sender_name(m['from']):<8} {_fit(_first_line(m['text']), 40)}"
        out.append(left.ljust(62) + right)
    out.append(LIST_TAIL)
    return out


def open_lines(msg: dict, today: date) -> List[str]:
    head = f" ✉ {msg['id']} · {sender_name(msg['from'])}"
    stamp = when(msg["day"], today)
    out = [head + (f" · {stamp}" if stamp else "")]
    for line in msg["text"].splitlines():
        if not line.strip():
            out.append("")
            continue
        indent = "  " + line[:len(line) - len(line.lstrip())]
        out += textwrap.wrap(line.strip(), WIDTH, initial_indent=indent,
                             subsequent_indent=indent, break_on_hyphens=False)
    return out


def summary_line(n: int) -> str:
    word = ("новое" if n % 10 == 1 and n % 100 != 11 else "новых")
    return SUMMARY.format(n=n, word=word)


# Обработчики вопросов: kind -> (p, ask_id, reply, day, opts) -> принят ли ответ.
# Наполняются в Task 15 (implant, warehouse, field).
ANSWERS: Dict[str, Callable] = {}
# Необязательная пара к обработчику: kind -> (p, ask_id) -> вопрос уже неактуален
# (задание сделано, утилита куплена). Такое сообщение закрывается без выплаты.
STALE: Dict[str, Callable] = {}


def answer(p: dict, msg: dict, reply: str, day: date, opts) -> bool:
    """Ответ на вопрос прямо в сообщении. Принят - сообщение прочитано и закрыто; пусто
    или «?» - ждёт дальше. Неизвестный вид вопроса (старая версия) - просто прочитано;
    вопрос, который уже потерял смысл, закрывается без выплаты."""
    ask = msg.get("ask") or {}
    handler = ANSWERS.get(ask.get("kind"))
    stale = STALE.get(ask.get("kind"))
    if handler is None or (stale is not None and stale(p, ask.get("id"))):
        done = True
    else:
        done = handler(p, ask.get("id"), reply.strip().lower(), day, opts)
    if done:
        msg["ask"] = None
        msg["read"] = True
    return done
