"""Судья у родителя: проверяет ответ, которого в песочнице нет (Н приёмки-1).

Раньше ожидаемый ответ лежал в .termit/task.json, и `cat .termit/task.json` его показывал.
Теперь родитель пишет туда только открытую часть состояния (sandbox.public_state), а
секретные ключи задачи (Task.secret_keys: answer, accept, traps…) держит у себя в памяти.
Хук спрашивает судью через unix-сокет .termit/judge.sock — так же устроен мост Совы.

Что делает судья — проверку задачи по СВОЕМУ состоянию (task.json из песочницы он не
читает вовсе) и по тому, что хук пишет в песочницу: ответ, журнал команд, текущая папка.
Каждое чтение файла песочницы — sandbox.read_in_box / files_in_box: строго внутри корня,
ни одно звено не симлинк, только обычный файл с лимитом, FIFO не вешает. Пути, которые
сдаёт игрок, сравниваются лексически (textnorm.same_path), без обращения к диску.
Судья ничего не исполняет из песочницы и не отдаёт наружу ничего, кроме вердикта, текста
подсказки и квитанции учебного brew — того, что игрок и так увидит на экране.

Запросы — одна строка JSON:
  {"op": "check"}          → {"solved": bool, "message": str|None[, "marks": [bool, …]]}
                             или {"stale": str}; marks — шаги стража (Task.progress): у
                             скрытого стража хук иначе не покажет, какие шаги сделаны (P5)
  {"op": "hint"}           → {"hint": str, "n": int, "total": int} или {"done": true, …}
  {"op": "hint", "peek": true} → {"n": выдано, "total": int} — без выдачи
  {"op": "pids", "state": {…}}  → {"ok": n} — PID процессов задачи после launch или reset
  {"op": "service_reset"}  → {"ok": true} | {"busy": сек} | {"none": true} | {"failed": str}
                             — reset песочницы перезапускает сервис задачи (сервер БД)
  {"op": "stock"}          → {"ok": "same"|"restored"} | {"none": true} | {"failed": str}
                             — reset сверяет запас venv/колёс (.termit/stock) с кэшем родителя

Подсказки — по одной (P2 А3): «всё разом» больше не отдаётся, и счёт выданных живёт у
судьи (hints_served), а не в файле .termit/hints. Так же судья помнит, что check хоть раз
вернул solved (solved): родитель засчитывает решение по этой памяти, а не по .termit/result.
  {"op": "task"}           → {"text": str, "steps": [str, …]}
  {"op": "receipt"}        → {"receipt": str|None}
"""
import json
import os
import select
import socket
import stat
import threading
import time
from pathlib import Path
from typing import Optional

from termit_app import sandbox, theme

SOCK_NAME = "judge.sock"
MAX_SOCK_PATH = 100            # sun_path на macOS — 104 байта, берём с запасом
REQUEST_CAP = 4096
READ_TIMEOUT = 5.0
CONN_DEADLINE = 10.0
ACCEPT_TICK = 0.3
STOP_WAIT = 3.0
REPLY_CAP = 256 * 1024         # подсказки и текст задачи — не больше
RESET_EVERY = 2.0              # op service_reset — не чаще (сервер БД пересобирается ~0,3 с)


def sock_path(box) -> Path:
    return Path(box) / ".termit" / SOCK_NAME


def path_fits(box) -> bool:
    """Влезает ли путь сокета судьи в sun_path (иначе судья не поднимется: Judge.open)."""
    return len(os.fsencode(str(sock_path(box)))) < MAX_SOCK_PATH


class Judge(threading.Thread):
    """Поток родителя на время одной задачи. state — полное состояние (с секретами)."""

    def __init__(self, box, task, state: dict, service=None):
        super().__init__(daemon=True)
        self.box, self.task, self.state = Path(box), task, dict(state)
        # сервис родителя задачи (учебный API, сервер PostgreSQL): проверка получает его в
        # ctx.service, reset в песочнице просит перезапустить его (op service_reset)
        self.service = service
        self._last_reset = None
        self.path = sock_path(box)
        self._srv: Optional[socket.socket] = None
        self._ino = None
        self._halt = threading.Event()
        self._wake = None
        self.solved = False         # check хоть раз сказал «решено» (P2 А3)
        self.hints_served = 0       # сколько подсказок выдано — счёт родителя
        self._lock = threading.Lock()
        # пол долга (P2 fix1 M2): родитель ставит can_hint(n) в деле — выдать ли подсказку n
        self.can_hint = None
        # PID процессов задачи (P2 fix1 M1): метка очереди → PID, подтверждённый судьёй
        self.pids = {}
        self._pids_told = False     # launch уже сообщил PID (первое сообщение — только его)
        self.caged = True           # процессы под sandbox-exec (родитель снимает при --no-sandbox)
        self.spawns = self._read_spawns()

    # --- сокет ---------------------------------------------------------------------------

    def open(self) -> bool:
        """Сокет до запуска zsh; не вышло (длинный путь, чужой файл) — False."""
        if not path_fits(self.box) or not self._termit_dir_ok():
            return False
        try:
            st = os.lstat(self.path)
            if not stat.S_ISSOCK(st.st_mode):
                return False
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        except OSError:
            return False
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            # не через os.umask: он общий на процесс, а судей поднимают и из потоков
            # (тесты гоняют задачи параллельно) — права ставим сразу после bind
            srv.bind(str(self.path))
            os.chmod(self.path, 0o600)
            st = os.lstat(self.path)
            if not stat.S_ISSOCK(st.st_mode) or st.st_mode & 0o077:
                raise OSError("сокет не наш или открыт другим")
            srv.listen(4)
            srv.settimeout(ACCEPT_TICK)
            self._ino = (st.st_dev, st.st_ino)
            self._wake = os.pipe()
        except OSError:
            srv.close()
            return False
        self._srv = srv
        return True

    def _read_spawns(self) -> dict:
        """Очередь отложенного запуска (её пишет родитель до zsh): метка → команда."""
        raw = sandbox.read_in_box(self.box, ".termit/spawn.json", 256 * 1024)
        try:
            items = json.loads(raw.decode("utf-8")) if raw else []
            return {int(it["token"]): str(it["cmd"]) for it in items}
        except (ValueError, TypeError, KeyError, AttributeError):
            return {}

    def _pid_ok(self, token: int, pid) -> bool:
        """PID — живой процесс этой песочницы с командой из очереди для этой метки."""
        import shlex
        from termit_app.tasks import kit
        cmd = self.spawns.get(token)
        if cmd is None or not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            return False
        if self.caged and not sandbox.caged_in(pid, self.box):
            return False
        got = (kit._ps(pid, "command") or "").strip()
        try:
            want = shlex.split(cmd)
        except ValueError:
            return False
        if not got or not want:
            return False
        # программа может показаться другим путём (python из CommandLineTools перезапускает
        # себя из Python.app) — сверяем аргументы: в них путь песочницы, они и отличают своих
        tail = " ".join(want[1:])
        return got.endswith(" " + tail) if tail else os.path.basename(got) == \
            os.path.basename(want[0])

    def take_pids(self, public) -> int:
        """Сопоставить метки своего состояния с PID из присланного state (по месту ключа).
        Первое сообщение — от launch, до старта zsh: принимается (каждый PID — после сверки).
        Дальше — только reset (P2 fix2 M1'): все прежние подтверждённые PID уже погашены
        (rebuild гасит процессы задачи) и новый набор подтверждается целиком, для всех меток
        сразу. Поздняя или частичная запись — отказ: двойник, запущенный игроком, пока жив
        настоящий процесс, PID не подменит."""
        from termit_app.tasks import kit
        found = {}
        _pair(self.state, public, found)
        with self._lock:
            first = not self._pids_told
            self._pids_told = True
            old = dict(self.pids)
        if first:
            ok = {t: p for t, p in found.items() if self._pid_ok(t, p)}
        else:
            tokens = set(self.spawns)
            if (not old or set(found) != tokens or any(not kit.gone(p) for p in old.values())
                    or set(found.values()) & set(old.values())):
                return 0
            ok = {t: p for t, p in found.items() if self._pid_ok(t, p)}
            if set(ok) != tokens:
                return 0
        with self._lock:
            self.pids.update(ok)
        return len(ok)

    def _termit_dir_ok(self) -> bool:
        try:
            return stat.S_ISDIR(os.lstat(self.box / ".termit").st_mode)
        except OSError:
            return False

    def stop(self) -> None:
        self._halt.set()
        wake = self._wake
        if wake is not None:
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
            srv, wake = self._srv, self._wake
            if srv is None:
                return
            if wake is not None:
                try:
                    ready, _, _ = select.select([srv, wake[0]], [], [], ACCEPT_TICK)
                except (OSError, ValueError):
                    ready = [srv]
                if wake[0] in ready or self._halt.is_set():
                    return
                if not ready:
                    continue
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                self._serve(conn)
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def _serve(self, conn: socket.socket) -> None:
        deadline = time.monotonic() + CONN_DEADLINE
        data = b""
        try:
            while b"\n" not in data and len(data) <= REQUEST_CAP:
                left = deadline - time.monotonic()
                if left <= 0:
                    return
                conn.settimeout(min(READ_TIMEOUT, left))
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk
            req = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return
        out = self.handle(req if isinstance(req, dict) else {})
        raw = (json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8")
        if len(raw) > REPLY_CAP:
            raw = b'{"error": "big"}\n'
        conn.settimeout(READ_TIMEOUT)
        try:
            conn.sendall(raw)
        except OSError:
            pass

    # --- ответы --------------------------------------------------------------------------

    def service_reset(self) -> dict:
        """reset в песочнице (хук, после sandbox.rebuild): сервис задачи — заново (сервер
        PostgreSQL: стоп, данные из шаблона, старт, сид). Не чаще раза в RESET_EVERY секунд;
        сервиса без reset() нет — {"none": true}. Сбой — {"failed": текст для игрока}."""
        svc = self.service
        if svc is None or not hasattr(svc, "reset"):
            return {"none": True}
        # сервер БД пересобирается ~0,3 с — не чаще RESET_EVERY; журнал учебного API
        # чистится мгновенно (у него reset_every = 0)
        every = getattr(svc, "reset_every", RESET_EVERY)
        with self._lock:
            now = time.monotonic()
            if self._last_reset is not None and now - self._last_reset < every:
                return {"busy": round(every - (now - self._last_reset), 1)}
            self._last_reset = now
        try:
            svc.reset()
        except Exception as e:      # noqa: BLE001 — игроку — понятный отказ, родитель жив
            return {"failed": str(e) or repr(e)}
        return {"ok": True}

    def stock(self) -> dict:
        """reset в песочнице (хук, до sandbox.rebuild): запас задачи сверить с кэшем и, если
        испорчен, положить заново (M7 ревью P1). {"ok": "same"|"restored"} | {"none": true} —
        запаса у задачи нет | {"failed": текст для игрока}."""
        kind = getattr(self.task, "stock", None)
        if not kind:
            return {"none": True}
        from termit_app import pyenvs
        with self._lock:
            try:
                return {"ok": pyenvs.refresh_stock(self.box, kind)}
            except Exception as e:      # noqa: BLE001 — игроку — понятный отказ, родитель жив
                return {"failed": str(e) or repr(e)}

    def current_state(self) -> dict:
        """Только своё состояние, целиком (C1 ревью C1a): task.json пишется изнутри
        песочницы, и подменённые в нём пути (start, file, target…) превратили бы проверку
        у родителя в оракул по чужим файлам. Живых ключей (PID от launch/reset) у задач
        с секретами нет — это стережёт tests/test_judge."""
        return dict(self.state)

    def handle(self, req: dict) -> dict:
        op = req.get("op")
        st = self.current_state()
        try:
            if op == "check":
                ctx = sandbox.make_ctx(self.box, st, service=self.service)
                v, marks = self.task.check_marks(ctx)       # один подсчёт шагов (P5 M2)
                if v.solved:
                    self.solved = True
                out = {"solved": bool(v.solved),
                       "message": None if v.message is None else str(v.message)}
                if getattr(self.task, "boss", False) and marks is not None:
                    out["marks"] = [bool(m) for m in marks]
                return out
            if op == "hint":
                hints = [str(h) for h in self.task.hints_for(st)]
                with self._lock:
                    n = self.hints_served
                    if req.get("peek"):
                        return {"n": n, "total": len(hints)}
                    if n >= len(hints):
                        return {"done": True, "n": n, "total": len(hints)}
                    if self.can_hint is not None and not self.can_hint(n):
                        return {"refused": True, "n": n, "total": len(hints)}
                    self.hints_served = n + 1
                return {"hint": hints[n], "n": n, "total": len(hints)}
            if op == "task":
                return {"text": theme.task_text(self.task, st),
                        "steps": [str(s) for s in self.task.steps_for(st)]}
            if op == "pids":
                return {"ok": self.take_pids(req.get("state"))}
            if op == "service_reset":
                return self.service_reset()
            if op == "stock":
                return self.stock()
            if op == "receipt":
                r = st.get("receipt")
                return {"receipt": None if r is None else str(r)}
        except KeyError as e:
            return {"stale": repr(e)}
        except Exception as e:      # noqa: BLE001 — судья не роняет родителя
            return {"error": repr(e)}
        return {"error": "op"}


def _pair(before, after, out: dict) -> dict:
    """Метки отложенного запуска (kit.SPAWN_TOKEN и ниже) в before → значения after на том же
    месте (словари — по ключу, списки — по порядку)."""
    from termit_app.tasks import kit
    if isinstance(before, dict) and isinstance(after, dict):
        for k, v in before.items():
            _pair(v, after.get(k), out)
    elif isinstance(before, list) and isinstance(after, list):
        for a, b in zip(before, after):
            _pair(a, b, out)
    elif (isinstance(before, int) and not isinstance(before, bool)
          and before <= kit.SPAWN_TOKEN):
        out[before] = after
    return out


def start(box, task, state: dict, service=None) -> Optional[Judge]:
    """Открыть сокет и запустить судью; не вышло — None (родитель пишет полный task.json)."""
    j = Judge(box, task, state, service=service)
    if not j.open():
        return None
    j.start()
    return j


def attach(box, task, state: dict, service=None) -> Optional[Judge]:
    """Судья для песочницы задачи. Не поднялся (длинный путь сокета и т.п.) — полный
    task.json, как раньше: задача должна решаться, хоть ответ и виден изнутри. service —
    сервис родителя задачи (Task.service), судья отдаёт его проверке и перезапускает по reset."""
    j = start(box, task, state, service=service)
    if j is None and sandbox.public_state(task, state) != state:
        sandbox.unhide(box, task, state)
    return j


ASK_CONNECT = 3.0
ASK_TIMEOUT = 30.0


def ask(box, req: dict) -> Optional[dict]:
    """Из песочницы (хук, учебный brew): запрос судье. Судьи нет или он молчит — None."""
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        c.settimeout(ASK_CONNECT)
        c.connect(str(sock_path(box)))
        c.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
        c.settimeout(ASK_TIMEOUT)
        data = b""
        while b"\n" not in data and len(data) <= REPLY_CAP:
            chunk = c.recv(65536)
            if not chunk:
                break
            data += chunk
        reply = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
        return reply if isinstance(reply, dict) else None
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    finally:
        c.close()
