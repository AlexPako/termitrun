"""sockhttp: HTTP over a unix socket, the same talk as with a website, only without a network.

The server listens on a socket file (api.sock), not on a port. The Docker API and many local
services work like this. Three ways to talk to it:

    >>> import sockhttp
    >>> r = sockhttp.get("/items", params={"status": "open"})     # a small client of its own
    >>> r.status_code, r.json()

    >>> sockhttp.install()                     # plain urllib works after this
    >>> import urllib.request, json
    >>> json.load(urllib.request.urlopen("http://api/items"))

    >>> s = sockhttp.session()                 # a real requests.Session (if installed)
    >>> s.get("http://api/items").json()

In real life it is requests.get("https://...") or urlopen("https://..."), the rest is the same.
No dependencies; requests is needed only for session()."""
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
    """A response with a 4xx or 5xx code (raise_for_status)."""

    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class Headers(dict):
    """Response headers: names are case-insensitive (r.headers["Content-Type"])."""

    def __init__(self, pairs=()):
        super().__init__((str(k).lower(), v) for k, v in pairs)

    def __getitem__(self, key):
        return super().__getitem__(str(key).lower())

    def __contains__(self, key):
        return super().__contains__(str(key).lower())

    def get(self, key, default=None):
        return super().get(str(key).lower(), default)


class Response:
    """Server response with the same fields as requests.Response."""

    def __init__(self, status_code, headers, content, url=""):
        self.status_code = int(status_code)
        self.headers = Headers(headers)
        self.content = content
        self.url = url

    @property
    def ok(self) -> bool:
        """True if the code is below 400."""
        return self.status_code < 400

    @property
    def text(self) -> str:
        """Response body as a string (UTF-8)."""
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        """Response body parsed as JSON."""
        return _json.loads(self.text)

    def raise_for_status(self) -> None:
        """Raise HTTPError on a 4xx or 5xx code; otherwise do nothing."""
        if not self.ok:
            raise HTTPError(f"{self.status_code} for {self.url or 'the request'}", self)

    def __repr__(self):
        return f"<Response [{self.status_code}]>"


def _seconds(timeout) -> float:
    """urllib passes socket._GLOBAL_DEFAULT_TIMEOUT (a marker object), not a number."""
    return float(timeout) if isinstance(timeout, (int, float)) else TIMEOUT


class UnixConnection(http.client.HTTPConnection):
    """http.client.HTTPConnection that connects to a socket file, not to a port."""

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
    """Request path: "/items" or "http://api/items"; params is a dict for ?key=value."""
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
    """GET request to the server on socket sock.

    path is "/items" (or "http://api/items"); params {"status": "open"} gives
    ?status=open; headers are your own headers, for example {"X-Api-Key": "..."}."""
    return _request("GET", path, sock, params=params, headers=headers, timeout=timeout)


def post(path, json=None, headers=None, sock=DEFAULT_SOCK, timeout=TIMEOUT) -> Response:
    """POST request: json is the data (a dict or a list), sent as a JSON body with the
    headers Content-Type: application/json and Content-Length."""
    return _request("POST", path, sock, headers=headers, json=json, timeout=timeout)


class UnixHandler(urllib.request.HTTPHandler):
    """urllib handler: http://<host>/... addresses go to the socket, other hosts are refused."""

    def __init__(self, sock, host=DEFAULT_HOST):
        super().__init__()
        self.sock = str(sock)
        self.host = host

    def http_open(self, req):
        if req.host != self.host:
            raise urllib.error.URLError(
                f"sockhttp: only http://{self.host}/ goes through the socket")

        def connect(host, timeout=TIMEOUT, **_kw):
            return UnixConnection(self.sock, host, timeout)
        return self.do_open(connect, req)


def install(sock=DEFAULT_SOCK, host=DEFAULT_HOST) -> None:
    """Plug the socket into urllib: after this urllib.request.urlopen("http://api/...") goes
    to sock. The socket path is stored in full, so you can change folders (cd) later."""
    handler = UnixHandler(os.path.abspath(sock), host)
    urllib.request.install_opener(urllib.request.build_opener(handler))


def session(sock=DEFAULT_SOCK, host=DEFAULT_HOST):
    """A real requests.Session whose http://<host>/... addresses go to the socket.

    Needs the requests package: pip install requests (in the game, from the warehouse,
    without a network)."""
    try:
        import requests
        from requests.adapters import HTTPAdapter
        import urllib3
    except ImportError:
        raise ImportError("requests is required: pip install --no-index --find-links ~/wheels "
                          "requests") from None
    from sockhttp import _adapter
    s = requests.Session()
    s.trust_env = False                 # no proxy from the environment and no .netrc
    s.mount(f"http://{host}/", _adapter.make(HTTPAdapter, urllib3, os.path.abspath(sock)))
    return s
