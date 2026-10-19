"""Учебный сервер API: HTTP на unix-сокете песочницы, поток в РОДИТЕЛЕ (по образцу моста
Совы, owl.Bridge).

Зачем в родителе: профиль sandbox-exec запрещает входящие соединения ((deny
network-inbound)), а ослаблять его ради учебной задачи нельзя (отчёт 07). Исходящий connect
к unix-сокету внутри box профиль уже разрешает — так curl --unix-socket api.sock из
песочницы и достаёт до сервера. TCP нет вовсе, сети у песочницы по-прежнему нет.

Сокет — box/.termit/api.sock, в корне песочницы — симлинк api.sock -> .termit/api.sock
(его создаёт setup задачи через link(), поэтому reset восстанавливает и его).

Всё, что приходит из песочницы, — недоверенное: голова запроса не длиннее REQUEST_CAP, на
чтение стоят таймауты и общий срок (без «медленной капли»), путь — только ключ словаря
маршрутов (файлов сервер не открывает). Ответы — заранее собранные из state синтетические
данные; из песочницы сервер ничего не читает, в неё пишет только сам сокет. Живёт ровно
столько, сколько задача: stop() в finally.

Часть 10 (A5): методы GET, HEAD и POST. Тело POST — только по Content-Length (нет его или
chunked — 411), не больше BODY_CAP (иначе 413), разбор JSON — json.loads у родителя с
пределом глубины (иначе 400). Маршрут — статика (код, тело) или обработчик
fn(Request) -> (код, тело[, заголовки]); упавший обработчик — 500. Непрочитанное тело
сервер дочитывает и выбрасывает (не больше DRAIN_CAP): клиент дописывает запрос и читает
ответ, а не получает обрыв записи (EPIPE, спайк Q0). Журнал запросов — в памяти
родителя (journal(), не больше JOURNAL_CAP записей), его смотрят проверки задач;
reset() чистит журнал (reset в песочнице через судью, op service_reset)."""
import json
import os
import re
import select
import socket
import stat
import threading
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

SOCK_NAME = "api.sock"
LINK_NAME = "api.sock"
LINK_TARGET = ".termit/" + SOCK_NAME
MAX_SOCK_PATH = 100            # sun_path на macOS — 104 байта, берём с запасом
REQUEST_CAP = 8 * 1024         # байт в запросе (строка запроса и заголовки)
# curl шлёт запрос целиком сразу: молчащий клиент (nc -U api.sock) держит очередь недолго
READ_TIMEOUT = 1.0             # песочница должна прислать запрос быстро
CONN_DEADLINE = 2.5            # и весь запрос целиком — не дольше этого
BACKLOG = 16                   # очередь соединений: пара молчунов не забивает её
ACCEPT_RETRY = 0.05            # пауза после неожиданной ошибки accept (EMFILE и т.п.)
STOP_WAIT = 3.0                # stop() ждёт поток не дольше этого
ACCEPT_TICK = 0.3              # запасной тик ожидания accept (будит stop() через будильник)
MAX_PATH = 1024
BODY_CAP = 64 * 1024           # байт в теле POST
# непрочитанное тело дочитываем и выбрасываем — не больше (тело ещё больше — клиент получит
# обрыв записи, EPIPE: это предел против «пожирателя», M8 ревью Q1)
DRAIN_CAP = 8 * 1024 * 1024
JSON_DEPTH = 64                # вложенность JSON в теле
MAX_HEADERS = 50
HEADER_CAP = 1024              # байт в одной строке заголовка
JOURNAL_CAP = 1000             # записей журнала (старые уходят)
LOG_VALUE_CAP = 200            # знаков значения в записи журнала

REASONS = {200: "OK", 201: "Created", 400: "Bad Request", 401: "Unauthorized",
           404: "Not Found", 405: "Method Not Allowed", 411: "Length Required",
           413: "Payload Too Large", 431: "Request Header Fields Too Large",
           500: "Internal Server Error"}
METHODS = ("GET", "HEAD", "POST")
_REQUEST_LINE = re.compile(r"^([A-Z]{1,16}) (/[!-~]*) HTTP/1\.[01]$")
_QUERY_VALUE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
# обработчикам: ключи и значения query (после %-раскодирования) — только такие
_QUERY_ITEM = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,64}$")
_DIGITS = re.compile(r"^[0-9]{1,12}$")


@dataclass
class Request:
    """Запрос для обработчика маршрута. headers — имена в нижнем регистре; body — разобранный
    JSON (is_json True) или None; raw — байты тела как пришли (не больше BODY_CAP)."""
    method: str
    path: str
    query: Dict[str, List[str]] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    body: object = None             # числа — конечные: NaN, Infinity, 1e400 дают 400
    is_json: bool = False
    raw: bytes = b""


Handler = Callable[[Request], tuple]
Route = Union[Tuple[int, object], Handler]


class _Reject(Exception):
    """Запрос отклонён до маршрута: код и тело ответа."""

    def __init__(self, code: int, obj):
        super().__init__(code)
        self.code, self.obj = code, obj


def sock_path(box) -> Path:
    return Path(box) / ".termit" / SOCK_NAME


def path_fits(box) -> bool:
    """Влезает ли путь сокета в sun_path (иначе bind невозможен)."""
    return len(os.fsencode(str(sock_path(box)))) < MAX_SOCK_PATH


def link(box) -> None:
    """Симлинк api.sock -> .termit/api.sock в корне песочницы (зовёт setup задачи)."""
    target = Path(box) / LINK_NAME
    if os.path.lexists(target):
        target.unlink()
    os.symlink(LINK_TARGET, target)


def _plain(obj):
    """Тела ответов — только простые данные JSON (копия: state задачи не меняется)."""
    return json.loads(json.dumps(obj, ensure_ascii=False))


def render(code: int, obj, extra: Optional[Dict[str, str]] = None,
           allow: str = "GET, HEAD") -> Tuple[bytes, bytes]:
    """Ответ сервера по частям: (строка статуса с заголовками, тело). Задачи считают по ним
    Content-Length и размер с заголовками — тем же кодом, что отвечает сервер. extra — свои
    заголовки обработчика (уже проверенные _extra_headers)."""
    body = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    lines = [f"HTTP/1.0 {code} {REASONS.get(code, 'Error')}",
             "Content-Type: application/json",
             f"Content-Length: {len(body)}",
             "Connection: close"]
    if code == 405:
        lines.append("Allow: " + allow)
    lines += [f"{k}: {v}" for k, v in (extra or {}).items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii"), body


def _response(code: int, obj, head: bool = False, extra=None, allow: str = "GET, HEAD") -> bytes:
    out, body = render(code, obj, extra, allow)
    return out if head else out + body


def _extra_headers(hdrs) -> Dict[str, str]:
    """Заголовки от обработчика: словарь коротких строк ASCII без переводов строк; иначе
    ValueError (обработчик ошибся — 500)."""
    if not isinstance(hdrs, dict) or len(hdrs) > 10:
        raise ValueError("headers")
    out = {}
    for k, v in hdrs.items():
        k, v = str(k), str(v)
        if not _HEADER_NAME.match(k) or len(v) > 200 or not all(" " <= c <= "~" for c in v):
            raise ValueError("header")
        out[k] = v
    return out


def _no_constant(name):
    raise ValueError(f"не JSON: {name}")        # NaN, Infinity — не JSON (урок 3, M6 ревью Q1)


def _finite(text: str) -> float:
    """Число JSON — только конечное: 1e400 (inf) у обработчика сломал бы сравнение."""
    import math
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("не конечное число")
    return value


def json_depth_ok(obj, limit: int = JSON_DEPTH) -> bool:
    """Вложенность разобранного JSON не глубже limit — обход без рекурсии."""
    stack = [(obj, 1)]
    while stack:
        cur, d = stack.pop()
        if isinstance(cur, (dict, list)):
            if d > limit:
                return False
            items = cur.values() if isinstance(cur, dict) else cur
            stack.extend((x, d + 1) for x in items if isinstance(x, (dict, list)))
    return True


def parse_query(query: str) -> Dict[str, List[str]]:
    """?a=1&b=2&a=3 → {"a": ["1", "3"], "b": ["2"]}; ключи и значения после раскодирования —
    _QUERY_ITEM, иначе _Reject(400)."""
    out: Dict[str, List[str]] = {}
    if not query:
        return out
    for part in query.split("&"):
        key, eq, value = part.partition("=")
        if not _pct_ok(part):
            raise _Reject(400, {"error": "bad query"})
        try:
            key = urllib.parse.unquote_plus(key, errors="strict")
            value = urllib.parse.unquote_plus(value, errors="strict")
        except UnicodeDecodeError:
            raise _Reject(400, {"error": "bad query"}) from None
        if not eq or not _QUERY_ITEM.match(key) or not _QUERY_ITEM.match(value):
            raise _Reject(400, {"error": "bad query"})
        out.setdefault(key, []).append(value)
    return out


def _pct_ok(part: str) -> bool:
    """Каждый % — с двумя шестнадцатеричными цифрами (unquote молча терпит «%ZZ»)."""
    return re.fullmatch(r"(?:[^%]|%[0-9A-Fa-f]{2})*", part) is not None


class ApiServer(threading.Thread):
    """Сервер маршрутов {путь: (код, тело)}. Интерфейс как у моста Совы: open() до запуска
    zsh (False — сокет не поднять), start(), stop() — в finally, повторный вызов безопасен."""

    # reset журнала мгновенный: судья не придерживает его (judge.service_reset)
    reset_every = 0

    def __init__(self, box, routes: Dict[str, Route]):
        super().__init__(daemon=True, name="termit-api")
        self.box = Path(box)
        self.path = sock_path(self.box)
        self.routes: Dict[str, Route] = {}
        for k, route in routes.items():
            if callable(route):
                self.routes[str(k)] = route
            else:
                code, body = route
                self.routes[str(k)] = (int(code), _plain(body))
        self._log: deque = deque()
        self.total = 0                  # запросов с начала (или с reset), журнал хранит хвост
        self._srv: Optional[socket.socket] = None
        self._ino = None
        self._halt = threading.Event()
        self._lock = threading.Lock()
        self._conn: Optional[socket.socket] = None     # клиент, которого обслуживаем сейчас
        # будильник: stop() пишет байт, и поток выходит из ожидания accept сразу, а не по тику
        # таймаута (закрытый из другого потока сокет на macOS accept не будит)
        self._wake: Optional[Tuple[int, int]] = None

    # --- сокет ---------------------------------------------------------------------------

    def open(self) -> bool:
        if not path_fits(self.box):
            return False
        if not self._termit_dir_ok():
            return False
        try:
            st = os.lstat(self.path)
            if not stat.S_ISSOCK(st.st_mode):
                return False             # обычный файл или симлинк на месте сокета — не наше
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        except OSError:
            return False
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            old = os.umask(0o177)        # сокет рождается 0600 — без chmod по пути
            try:
                srv.bind(str(self.path))
            finally:
                os.umask(old)
            st = os.lstat(self.path)
            if not stat.S_ISSOCK(st.st_mode) or st.st_mode & 0o077:
                raise OSError("сокет не наш или открыт другим")
            srv.listen(BACKLOG)
            srv.settimeout(ACCEPT_TICK)
            self._ino = (st.st_dev, st.st_ino)
            if self._wake is None:
                self._wake = os.pipe()
        except OSError:
            srv.close()
            return False
        self._srv = srv
        return True

    def _termit_dir_ok(self) -> bool:
        try:
            return stat.S_ISDIR(os.lstat(self.box / ".termit").st_mode)
        except OSError:
            return False

    def stop(self) -> None:
        with self._lock:
            self._halt.set()
            conn = self._conn
        if conn is not None:             # будим recv/sendall: клиент не держит остановку
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        wake = self._wake
        if wake is not None:             # будим ожидание accept
            try:
                os.write(wake[1], b"x")
            except OSError:
                pass
        srv, self._srv = self._srv, None
        if srv is not None:
            try:
                srv.close()
            except OSError:
                pass
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout=STOP_WAIT)
        if wake is not None and not self.is_alive():
            self._wake = None
            for fd in wake:
                try:
                    os.close(fd)
                except OSError:
                    pass
        # удалить только свой сокет: .termit — настоящая папка, файл — тот самый сокет
        if self._ino is not None and self._termit_dir_ok():
            try:
                st = os.lstat(self.path)
                if stat.S_ISSOCK(st.st_mode) and (st.st_dev, st.st_ino) == self._ino:
                    os.unlink(self.path)
            except OSError:
                pass
        self._ino = None

    def run(self) -> None:
        while not self._halt.is_set():
            srv = self._srv
            if srv is None:
                return
            wake = self._wake
            if wake is not None:
                try:
                    ready, _, _ = select.select([srv, wake[0]], [], [], ACCEPT_TICK)
                except (OSError, ValueError):
                    ready = [srv]        # не выбрать — пусть решит accept со своим таймаутом
                if wake[0] in ready or self._halt.is_set():
                    return
                if not ready:
                    continue
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                # закрыт при остановке — выходим; иначе (EMFILE, ECONNABORTED) — служим дальше:
                # сокет слушает, и замолчавший поток повесил бы curl игрока
                if self._halt.is_set() or self._srv is None:
                    return
                self._halt.wait(ACCEPT_RETRY)
                continue
            with self._lock:
                if self._halt.is_set():
                    conn.close()
                    return
                self._conn = conn
            try:
                self._serve(conn)
            except Exception:            # noqa: BLE001 — недоверенный клиент не роняет поток
                pass
            finally:
                with self._lock:
                    self._conn = None
                try:
                    conn.close()
                except OSError:
                    pass

    # --- HTTP ------------------------------------------------------------------------------

    def _read_head(self, conn: socket.socket) -> Optional[bytes]:
        """Строка запроса и заголовки до пустой строки (и что пришло следом — начало тела);
        None — срок вышел или клиент ушёл, b"" — голова больше REQUEST_CAP."""
        self._deadline = time.monotonic() + CONN_DEADLINE
        data = b""
        while b"\r\n\r\n" not in data and b"\n\n" not in data:
            if len(data) > REQUEST_CAP:
                return b""
            chunk = self._recv(conn, 2048)
            if chunk is None:
                return None
            if not chunk:
                return data or None
            data += chunk
        if len(_split_head(data)[0]) > REQUEST_CAP:
            return b""
        return data

    def _recv(self, conn: socket.socket, n: int) -> Optional[bytes]:
        """Кусок от клиента в пределах общего срока соединения; None — срок или ошибка."""
        left = self._deadline - time.monotonic()
        if left <= 0 or self._halt.is_set():
            return None
        conn.settimeout(min(READ_TIMEOUT, left))
        try:
            return conn.recv(n)
        except OSError:
            return None

    # --- разбор ----------------------------------------------------------------------------

    @staticmethod
    def _headers(lines: List[bytes]) -> Dict[str, str]:
        if len(lines) > MAX_HEADERS:
            raise _Reject(431, {"error": "too many headers"})
        out: Dict[str, str] = {}
        for ln in lines:
            if len(ln) > HEADER_CAP:
                raise _Reject(431, {"error": "header too large"})
            try:
                text = ln.decode("latin-1")
            except UnicodeDecodeError:          # pragma: no cover — latin-1 читает всё
                raise _Reject(400, {"error": "bad header"}) from None
            name, colon, value = text.partition(":")
            if not colon or not _HEADER_NAME.match(name):
                raise _Reject(400, {"error": "bad header"})
            out[name.lower()] = value.strip()
        return out

    def parse(self, head: bytes) -> Tuple[str, str, str, Dict[str, str]]:
        """(метод, путь, query, заголовки) или _Reject."""
        lines = _split_head(head)[0].replace(b"\r\n", b"\n").split(b"\n")
        try:
            line = lines[0].decode("ascii")
        except UnicodeDecodeError:
            raise _Reject(400, {"error": "bad request"}) from None
        m = _REQUEST_LINE.match(line)
        if not m or len(m.group(2)) > MAX_PATH:
            raise _Reject(400, {"error": "bad request"})
        path, _, query = m.group(2).partition("?")
        return m.group(1), path, query, self._headers([x for x in lines[1:] if x])

    @staticmethod
    def body_length(method: str, headers: Dict[str, str]) -> int:
        """Сколько байт тела ждать: POST — строго по Content-Length; у остальных тело не
        читается (0)."""
        if method != "POST":
            return 0
        if "transfer-encoding" in headers or "content-length" not in headers:
            raise _Reject(411, {"error": "length required"})
        cl = headers["content-length"]
        if not _DIGITS.match(cl):
            raise _Reject(400, {"error": "bad content-length"})
        if int(cl) > BODY_CAP:
            raise _Reject(413, {"error": "body too large", "limit": BODY_CAP})
        return int(cl)

    @staticmethod
    def _json(raw: bytes, ctype: str) -> Tuple[object, bool]:
        """(разобранное, это JSON). Заявлен JSON, а разобрать нельзя (или слишком глубоко) —
        _Reject(400); не заявлен и не разбирается — (None, False)."""
        declared = "json" in ctype.lower()
        if not raw:
            if declared:
                raise _Reject(400, {"error": "empty json"})
            return None, False
        try:
            obj = json.loads(raw.decode("utf-8"), parse_constant=_no_constant,
                             parse_float=_finite)
        except (ValueError, RecursionError, UnicodeDecodeError):
            if declared:
                raise _Reject(400, {"error": "bad json"}) from None
            return None, False
        if not json_depth_ok(obj):
            raise _Reject(400, {"error": "json too deep", "limit": JSON_DEPTH})
        return obj, True

    # --- ответ -----------------------------------------------------------------------------

    def handle(self, head: bytes, body: bytes = b"") -> bytes:
        """Ответ на запрос (без сети: удобно для тестов). head — голова (с остатком после
        пустой строки или без), body — тело POST целиком (длина уже сверена)."""
        try:
            method, path, query, headers = self.parse(head)
        except _Reject as e:
            return _response(e.code, e.obj)
        entry = {"method": method, "path": path, "query": {}, "code": 0, "json": False,
                 "user_agent": _cap(headers.get("user-agent")),
                 "api_key": _cap(headers.get("x-api-key")),
                 "content_type": _cap(headers.get("content-type"))}
        head_only = method == "HEAD"
        try:
            code, obj, extra, allow = self._route(method, path, query, headers, body, entry)
        except _Reject as e:
            code, obj, extra, allow = e.code, e.obj, None, "GET, HEAD"
        entry["code"] = code
        self._journal_add(entry)
        return _response(code, obj, head_only, extra, allow)

    def _route(self, method, path, query, headers, body, entry):
        route = self.routes.get(path)
        allow = "GET, HEAD, POST" if callable(route) else "GET, HEAD"
        if method not in METHODS or (method == "POST" and not callable(route) and
                                     route is not None):
            return 405, {"error": "method not allowed", "allow": allow.split(", ")}, None, allow
        if callable(route):
            entry["query"] = parse_query(query)
        else:
            try:
                entry["query"] = parse_query(query)
            except _Reject:
                entry["query"] = {}
        if route is None:
            return 404, {"error": "not found", "try": "/"}, None, allow
        if not callable(route):
            code, obj = route
            if query:
                obj = self._filter(obj, query)
                if obj is None:
                    return 400, {"error": "bad query", "try": "?status=open"}, None, allow
            return code, obj, None, allow
        obj, is_json = (None, False)
        if method == "POST":
            if self.body_length(method, headers) != len(body):
                raise _Reject(400, {"error": "body length"})
            obj, is_json = self._json(body, headers.get("content-type", ""))
        entry["json"] = is_json
        req = Request(method, path, {k: list(v) for k, v in entry["query"].items()},
                      dict(headers), obj, is_json, bytes(body))
        try:
            out = route(req)
            if not isinstance(out, tuple) or len(out) not in (2, 3):
                raise ValueError("route result")
            code = int(out[0])
            if code not in REASONS:
                raise ValueError("code")
            res = _plain(out[1])
            extra = _extra_headers(out[2]) if len(out) == 3 else None
        except Exception:               # noqa: BLE001 — ошибка обработчика: 500, сервер жив
            return 500, {"error": "internal error"}, None, allow
        return code, res, extra, allow

    @staticmethod
    def _filter(body, query: str):
        """?status=X — только для списков записей; иначе None (400)."""
        key, eq, value = query.partition("=")
        if key != "status" or not eq or not _QUERY_VALUE.match(value):
            return None
        if not isinstance(body, list):
            return None
        return [x for x in body if isinstance(x, dict) and x.get("status") == value]

    # --- журнал ----------------------------------------------------------------------------

    def _journal_add(self, entry: dict) -> None:
        with self._lock:
            self._log.append(entry)
            while len(self._log) > JOURNAL_CAP:
                self._log.popleft()
            self.total += 1

    def journal(self) -> List[dict]:
        """Копия журнала: старые записи — первыми (не больше JOURNAL_CAP)."""
        with self._lock:
            items = list(self._log)
        return json.loads(json.dumps(items))

    def reset(self) -> None:
        """Журнал и счётчик — с нуля (reset задачи в песочнице, через судью)."""
        with self._lock:
            self._log = deque()
            self.total = 0

    # --- соединение ------------------------------------------------------------------------

    def _serve(self, conn: socket.socket) -> None:
        data = self._read_head(conn)
        if data is None:
            return                       # срок вышел или клиент ушёл — молча закрываем
        if data == b"":
            self._send(conn, _response(431, {"error": "request too large"}))
            self._drain(conn)
            return
        head, rest = _split_head(data)
        need = 0
        try:
            method, path, _, headers = self.parse(head)
            if method == "POST" and callable(self.routes.get(path)):
                need = self.body_length(method, headers)
        except _Reject:
            out = self.handle(head)      # тот же отказ — с записью в журнал, если разобран
            self._send(conn, out)
            self._drain(conn)
            return
        if need and headers.get("expect", "").lower() == "100-continue" and len(rest) < need:
            self._send(conn, b"HTTP/1.1 100 Continue\r\n\r\n")
        body = rest[:need]
        while len(body) < need:
            chunk = self._recv(conn, min(65536, need - len(body)))
            if not chunk:
                break                    # не дослал тело: 400 и запись в журнал (M7 ревью Q1)
            body += chunk
        self._send(conn, self.handle(head, body))
        # тело, которого сервер не читал (GET с телом, лишние байты): дочитать до закрытия
        if len(rest) > need or (not need and headers.get("content-length", "0") != "0"):
            self._drain(conn)

    def _send(self, conn: socket.socket, out: bytes) -> None:
        conn.settimeout(READ_TIMEOUT)
        try:
            conn.sendall(out)
        except OSError:
            pass

    def _drain(self, conn: socket.socket) -> None:
        """Ответ ушёл, а клиент, может быть, ещё пишет тело: закрыть свою сторону записи и
        дочитать (выбросить) остаток — не больше DRAIN_CAP и в пределах срока. Иначе клиент
        получает обрыв записи (EPIPE) вместо ответа."""
        try:
            conn.shutdown(socket.SHUT_WR)
        except OSError:
            return
        self._deadline = max(self._deadline, time.monotonic() + READ_TIMEOUT)
        got = 0
        while got < DRAIN_CAP:
            chunk = self._recv(conn, 65536)
            if not chunk:
                return
            got += len(chunk)


def _split_head(data: bytes) -> Tuple[bytes, bytes]:
    """(голова, остаток после пустой строки): разделитель — \r\n\r\n или \n\n, что раньше."""
    cuts = [(i, n) for i, n in ((data.find(b"\r\n\r\n"), 4), (data.find(b"\n\n"), 2))
            if i >= 0]
    if not cuts:
        return data, b""
    i, n = min(cuts)
    return data[:i], data[i + n:]


def _cap(value: Optional[str]) -> Optional[str]:
    return None if value is None else value[:LOG_VALUE_CAP]


def open_server(box, routes: Dict[str, Route]) -> ApiServer:
    """Открыть сокет и вернуть сервер (ещё не запущенный); не вышло — RuntimeError:
    задача без своего API не начнётся."""
    srv = ApiServer(box, routes)
    if not srv.open():
        raise RuntimeError("учебный API не поднялся")
    return srv
