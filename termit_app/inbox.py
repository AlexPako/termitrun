"""Сообщения на деке (inbox, спека 2.5): то, что раньше вываливалось в итог рана, —
«Завтра», подарки, витрина, охота, срочный заказ, вопросы утилит, склада и «Сделал?».
Храним готовый текст на момент события, последние KEEP штук; открыл — прочитал. Вопрос
без ответа («решу потом») тоже прочитан, но ask остаётся: в списке он «ждёт ответа», Enter
и inbox next его не открывают (финальное ревью В-1).
При загрузке модуль ничего из игры не импортирует: его зовёт progress._normalize."""
import contextlib
import io
import re
import textwrap
import zlib
from datetime import date
from typing import Callable, Dict, List, Optional

from termit_app import tui
from termit_app.textnorm import YES

KEEP = 30
MAX_TEXT = 2000
NAME_MAX = 12
SENDERS = {"raven": "Ворон", "gift": "Подарок", "shop": "Витрина", "system": "Система",
           "rabbit": "Связной"}
# Отправитель — gift/shop/system или ключ персонажа темы (raven и др.). Тему при загрузке
# не импортируем, поэтому ключ — любой короткий ascii-ключ; имя для экрана — sender_name.
SENDER_KEY = re.compile(r"[a-z][a-z0-9_]{0,23}")
ANSI = re.compile(r"\033\[[0-9;?]*[A-Za-z]")
EMPTY = "На деке пусто. Сообщения приходят после ранов."
NO_NEW = "Новых сообщений нет. Весь список — inbox."
NO_SUCH = "Сообщения {n} нет. Весь список — inbox."
WAITS = "ждёт ответа"
ASK_PROMPT = "   Ответ (y — да, n — нет; Enter — решу потом): "
# заказ в реале обещает команду «когда спрошу „Сделал?“» — значит, ? в вопросе назван (23.10)
FIELD_PROMPT = "   Сделал? (y — да, n — нет, ? — показать команду; Enter — решу потом): "


def ask_prompt(msg: dict) -> str:
    ask = msg.get("ask")
    return FIELD_PROMPT if isinstance(ask, dict) and ask.get("kind") == "field" else ASK_PROMPT
LIST_TAIL = "  inbox N — открыть · inbox next — следующее новое"
WHEN_COLUMN = 16
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
    """Больше KEEP — уходят старые прочитанные, потом старые непрочитанные; вопрос, который
    ждёт ответа (прочитанный или нет), молча не выкидывается никогда."""
    out = list(msgs)
    extra = len(out) - KEEP
    for gone in (lambda m: m["read"] and m.get("ask") is None,
                 lambda m: m.get("ask") is None):
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
    """Новое сообщение; тот же key уже есть (повторный итог, перезапуск) — None.
    Вопрос (ask) ключом не сверяется: его ключ без даты, и отложенный вопрос через пару
    дней приходит снова. Вместо этого старые с тем же ask (и отложенные, уже прочитанные)
    закрываются — на деке всегда один свежий вопрос о деле, и «y» на старый дубль не платит."""
    box = p.setdefault("inbox", [])
    if ask:
        for m in box:
            if isinstance(m, dict) and m.get("ask") == ask:
                m["read"] = True
                m["ask"] = None
    elif key and any(m.get("key") == key for m in box):
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
    завоз) второй раз за день скажет другое — и это новое сообщение, а не дубль.
    box["key"] — ключ, который стал известен только внутри блока."""
    if not on:
        yield {}
        return
    buf = io.StringIO()
    box = {}
    with contextlib.redirect_stdout(buf):
        yield box
    text = ANSI.sub("", buf.getvalue()).strip("\n")
    key = box.get("key") or key     # блок может уточнить ключ (id утилиты известен внутри)
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


def _pinned(m: dict) -> bool:
    """В списке всегда: непрочитанное и вопрос, который ждёт ответа."""
    return not m["read"] or m["ask"] is not None


def _shown(box: List[dict]) -> List[dict]:
    """Все непрочитанные и ждущие ответа и самые свежие прочитанные — до 10 всего (тех больше
    десяти — показываются все); порядок как в деке."""
    room = max(10 - sum(1 for m in box if _pinned(m)), 0)
    read = [m for m in box if not _pinned(m)]
    keep = {id(m) for m in (read[-room:] if room else [])}
    return [m for m in box if _pinned(m) or id(m) in keep]


def list_lines(p: dict, today: date) -> List[str]:
    box = p.get("inbox") or []
    if not box:
        return [EMPTY]
    new = len(unread(p))
    out = [" ✉ ДЕКА · сообщения" + (f" · новых: {new}" if new else "")]
    # FB17: колонки — от ширины окна: справа «когда» (до 16 знаков), первая строка — сколько влезет
    right_at = tui.width() - WHEN_COLUMN
    for m in reversed(_shown(box)):
        dot = "●" if not m["read"] else " "
        right = WAITS if m["ask"] else when(m["day"], today)
        head = f"  {dot} {m['id']:>2}  {sender_name(m['from']):<8} "
        left = head + _fit(_first_line(m["text"]), right_at - len(head) - 2)
        out.append(left.ljust(right_at) + right)
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
        out += textwrap.wrap(line.strip(), tui.width(), initial_indent=indent,
                             subsequent_indent=indent, break_on_hyphens=False)
    return out


def summary_line(n: int) -> str:
    word = ("новое" if n % 10 == 1 and n % 100 != 11 else "новых")
    return SUMMARY.format(n=n, word=word)


# Обработчики вопросов: kind -> (p, ask_id, reply, day, opts) -> принят ли ответ.
# Импорты модулей игры — внутри функций: inbox грузится из progress.
def _answer_implant(p, imp_id, reply, day, opts) -> bool:
    if not reply or reply == "?":
        return False
    from termit_app import implants
    implants.answer(p, imp_id, reply, day, getattr(opts, "installer", None))
    return True


def _answer_warehouse(p, ask_id, reply, day, opts) -> bool:
    if not reply or reply == "?":
        return False
    from termit_app import warehouse
    warehouse.answer(p, reply, day, getattr(opts, "wheels_getter", None))
    return True


def _answer_field(p, fid, reply, day, opts) -> bool:
    from termit_app import field
    if not reply:
        return False
    if fid not in field.CMD:
        return reply != "?"     # задания уже нет в игре — ответ просто закрывает
    if reply == "?":
        field.show_command(fid)
        return False
    if reply.strip().lower() in YES:      # владелец 23.10: сделал — а как делают, не увидел
        field.show_command(fid)
    field.answer(p, fid, reply, day)
    return True


ANSWERS: Dict[str, Callable] = {
    "implant": _answer_implant,
    "warehouse": _answer_warehouse,
    "field": _answer_field,
}


# Необязательная пара к обработчику: kind -> (p, ask_id) -> вопрос уже неактуален
# (задание сделано, утилита стоит, склад на месте). Такое сообщение закрывается без выплаты.
def _stale_implant(p, imp_id) -> bool:
    from termit_app import implants
    imp = implants.find(imp_id) if isinstance(imp_id, str) else None
    return imp is not None and implants.locate(imp) is not None


def _stale_warehouse(p, ask_id) -> bool:
    from termit_app import pyenvs
    return pyenvs.warehouse_ready()


def _stale_field(p, fid) -> bool:
    done = (p.get("field") or {}).get("done")
    return isinstance(done, list) and fid in done


STALE: Dict[str, Callable] = {
    "implant": _stale_implant,
    "warehouse": _stale_warehouse,
    "field": _stale_field,
}


def answer(p: dict, msg: dict, reply: str, day: date, opts) -> bool:
    """Ответ на вопрос прямо в сообщении. Принят - сообщение прочитано и закрыто; пусто
    или «?» - прочитано, но вопрос ждёт дальше (Enter его больше не открывает). Неизвестный вид вопроса (старая версия) - просто прочитано;
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
