"""sockhttp — HTTP через unix-сокет: тот же разговор, что с сайтом, только без сети.

Сервер слушает файл-сокет (api.sock), а не порт. Так устроены, например, Docker API и
многие локальные службы. Три способа поговорить с ним:

    >>> import sockhttp
    >>> r = sockhttp.get("/items", params={"status": "open"})     # свой маленький клиент
    >>> r.status_code, r.json()

    >>> sockhttp.install()                     # дальше работает обычный urllib
    >>> import urllib.request, json
    >>> json.load(urllib.request.urlopen("http://api/items"))

    >>> s = sockhttp.session()                 # настоящий requests.Session (если он стоит)
    >>> s.get("http://api/items").json()

В жизни будет requests.get("https://…") или urlopen("https://…") — остальное один в один.
Без зависимостей; requests нужен только для session()."""
import http.client
import json as _json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

__version__ = "1.0.0"
__all__ = ["get", "post", "install", "session", "Response", "HTTPError", "__version__"]

DEFAULT_SOCK = "api.sock"
DEFAULT_HOST = "api"
TIMEOUT = 5.0
USER_AGENT = "sockhttp/" + __version__


class HTTPError(OSError):
    """Ответ с кодом 4xx или 5xx (raise_for_status)."""

    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class Headers(dict):
    """Заголовки ответа: имена без учёта регистра (r.headers["Content-Type"])."""

    def __init__(self, pairs=()):
        super().__init__((str(k).lower(), v) for k, v in pairs)

    def __getitem__(self, key):
        return super().__getitem__(str(key).lower())

    def __contains__(self, key):
        return super().__contains__(str(key).lower())

    def get(self, key, default=None):
        return super().get(str(key).lower(), default)


class Response:
    """Ответ сервера — поля как у requests.Response."""

    def __init__(self, status_code, headers, content, url=""):
        self.status_code = int(status_code)
        self.headers = Headers(headers)
        self.content = content
        self.url = url

    @property
    def ok(self) -> bool:
        """True, если код меньше 400."""
        return self.status_code < 400

    @property
    def text(self) -> str:
        """Тело ответа строкой (UTF-8)."""
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        """Тело ответа, разобранное как JSON."""
        return _json.loads(self.text)

    def raise_for_status(self) -> None:
        """Код 4xx или 5xx — исключение HTTPError; иначе ничего."""
        if not self.ok:
            raise HTTPError(f"{self.status_code} для {self.url or 'запроса'}", self)

    def __repr__(self):
        return f"<Response [{self.status_code}]>"


def _seconds(timeout) -> float:
    """urllib передаёт socket._GLOBAL_DEFAULT_TIMEOUT (объект-метку), а не число."""
    return float(timeout) if isinstance(timeout, (int, float)) else TIMEOUT


class UnixConnection(http.client.HTTPConnection):
    """http.client.HTTPConnection, который соединяется с файлом-сокетом, а не с портом."""

    def __init__(self, sock_path, host=DEFAULT_HOST, timeout=TIMEOUT):
        super().__init__(host, timeout=_seconds(timeout))
        self.sock_path = str(sock_path)

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(_seconds(self.timeout))
        try:
            s.connect(self.sock_path)
        except OSError:
            s.close()
            raise
        self.sock = s


def _target(path, params=None) -> str:
    """Путь запроса: "/items" или "http://api/items"; params — словарь для ?ключ=значение."""
    parts = urllib.parse.urlsplit(str(path))
    target = parts.path or "/"
    if not target.startswith("/"):
        target = "/" + target
    query = parts.query
    if params:
        extra = urllib.parse.urlencode(params, doseq=True)
        query = f"{query}&{extra}" if query else extra
    return target + ("?" + query if query else "")


def _request(method, path, sock, params=None, headers=None, json=None, timeout=TIMEOUT):
    target = _target(path, params)
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    body = None
    if json is not None:
        body = _json.dumps(json, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    conn = UnixConnection(sock, timeout=timeout)
    try:
        conn.request(method, target, body=body, headers=hdrs)
        r = conn.getresponse()
        return Response(r.status, r.getheaders(), r.read(), f"http://{DEFAULT_HOST}{target}")
    finally:
        conn.close()


def get(path, sock=DEFAULT_SOCK, params=None, headers=None, timeout=TIMEOUT) -> Response:
    """GET-запрос к серверу на сокете sock.

    path — "/items" (или "http://api/items"); params — {"status": "open"} даст
    ?status=open; headers — свои заголовки, например {"X-Api-Key": "…"}."""
    return _request("GET", path, sock, params=params, headers=headers, timeout=timeout)


def post(path, json=None, headers=None, sock=DEFAULT_SOCK, timeout=TIMEOUT) -> Response:
    """POST-запрос: json — данные (словарь или список), уходят телом в формате JSON с
    заголовками Content-Type: application/json и Content-Length."""
    return _request("POST", path, sock, headers=headers, json=json, timeout=timeout)


class UnixHandler(urllib.request.HTTPHandler):
    """Обработчик urllib: адреса http://<host>/… идут в сокет, другие хосты — отказ."""

    def __init__(self, sock, host=DEFAULT_HOST):
        super().__init__()
        self.sock = str(sock)
        self.host = host

    def http_open(self, req):
        if req.host != self.host:
            raise urllib.error.URLError(f"sockhttp: через сокет — только http://{self.host}/")

        def connect(host, timeout=TIMEOUT, **_kw):
            return UnixConnection(self.sock, host, timeout)
        return self.do_open(connect, req)


def install(sock=DEFAULT_SOCK, host=DEFAULT_HOST) -> None:
    """Подключить сокет к urllib: после этого urllib.request.urlopen("http://api/…") идёт
    в sock. Путь к сокету запоминается полным — можно потом сменить папку (cd)."""
    handler = UnixHandler(os.path.abspath(sock), host)
    urllib.request.install_opener(urllib.request.build_opener(handler))


def session(sock=DEFAULT_SOCK, host=DEFAULT_HOST):
    """Настоящий requests.Session, у которого адреса http://<host>/… идут в сокет.

    Нужен пакет requests: pip install requests (в игре — из склада, без сети)."""
    try:
        import requests
        from requests.adapters import HTTPAdapter
        import urllib3
    except ImportError:
        raise ImportError("нужен requests: pip install --no-index --find-links ~/wheels "
                          "requests") from None
    from sockhttp import _adapter
    s = requests.Session()
    s.trust_env = False                 # без прокси из окружения и без .netrc
    s.mount(f"http://{host}/", _adapter.make(HTTPAdapter, urllib3, os.path.abspath(sock)))
    return s
