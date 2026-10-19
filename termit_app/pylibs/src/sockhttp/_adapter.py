"""Транспортный адаптер requests на unix-сокет (как в requests-unixsocket и docker-py).

Пул — urllib3.HTTPConnectionPool, его соединение делает connect() через AF_UNIX. Адаптер
переопределяет get_connection и get_connection_with_tls_context (requests 2.32.2+ зовёт
второй) и отдаёт серверу путь без хоста (request_url)."""
import socket


def make(HTTPAdapter, urllib3, sock_path: str):
    """Собрать адаптер (классы берутся из уже импортированных requests и urllib3)."""

    class UnixHTTPConnection(urllib3.connection.HTTPConnection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.sock_path = sock_path

        def connect(self):
            t = self.timeout if isinstance(self.timeout, (int, float)) else 5.0
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(t)
            try:
                s.connect(self.sock_path)
            except OSError:
                s.close()
                raise
            self.sock = s

    class UnixHTTPConnectionPool(urllib3.connectionpool.HTTPConnectionPool):
        ConnectionCls = UnixHTTPConnection

    class UnixAdapter(HTTPAdapter):
        def __init__(self):
            super().__init__()
            self._unix_pool = UnixHTTPConnectionPool("localhost", maxsize=4)

        def get_connection(self, url, proxies=None):
            return self._unix_pool

        def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
            return self._unix_pool

        def request_url(self, request, proxies):
            return request.path_url

        def close(self):
            self._unix_pool.close()
            super().close()

    return UnixAdapter()
