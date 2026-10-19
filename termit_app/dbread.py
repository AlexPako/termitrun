"""Чтение базы задачи для проверки (9а A1): снимок базы SQLite из песочницы.

Кто читает: судья у родителя (задачи БД — со скрытым ответом), tests/refrun, хук в
песочнице, если судья не поднялся, и повторная проверка recheck под sandbox-exec. Из
песочницы ничего не исполняется: файл базы — данные, SQL игрока у родителя не выполняется.

Меры (план части 9, «Проверка»):
1. байты <db> и <db>-wal — через sandbox.read_in_box: внутри песочницы, ни одно
   звено не симлинк, только обычный файл, не больше DB_CAP;
2. копия — в своей закрытой папке (mkdtemp, 0700), убирается всегда;
3. Python sqlite3: PRAGMA trusted_schema=OFF, query_only=1, cell_size_check=ON, предел
   времени на запрос (set_progress_handler); enable_load_extension не вызывается никогда
   (tests/test_dbread проверяет по AST всего termit_app);
4. объект проверки берётся, только если в sqlite_master это type='table' и не virtual:
   VIEW или virtual на месте таблицы — отказ «таблица подменена»;
5. битая база — «база повреждена: reset»;
6. рядом живой -journal (незавершённая транзакция) — «база ещё открыта»: журнал не копируем и
   не откатываем (fix1 I1); таблицу с вычисляемыми графами (GENERATED) не читаем (fix1 M1).

Копию сделать негде (recheck: профиль запрещает запись вовсе) — запасной путь: базу без
-wal/-journal рядом открываем на месте через /dev/fd/N (дескриптор от sandbox.open_in_box,
mode=ro&immutable=1); есть -wal или -journal — «база ещё открыта». Это безопасно потому, что
такой процесс сам в песочнице: читает только её и системное, ничего не пишет.

Снимок — общий интерфейс (Snapshot): rows, columns, indexes, fks, checks, views, triggers,
count. PgSnapshot (PostgreSQL, текстовый снимок COPY) — ниже, часть 9б."""
import os
import re
import shutil
import sqlite3
import tempfile
import time
from typing import Dict, List, Optional, Sequence, Tuple

DB_CAP = 32 * 1024 * 1024       # файл базы (и каждый -wal/-journal) больше — не читаем
QUERY_BUDGET = 0.5              # секунд на один запрос; дольше — прерываем
PROGRESS_STEPS = 1000           # как часто SQLite спрашивает «не пора ли прервать»
MIN_SQLITE = (3, 37, 0)         # STRICT и прочее Apple-сборки 3.54: старше — не прочтём
MAGIC = b"SQLite format 3\x00"
# заголовок -journal: пустой файл (TRUNCATE) и обнулённый заголовок (PERSIST) — журнал
# закрытой транзакции; что-то ненулевое (магия, nonce) — транзакция идёт или оборвалась
JOURNAL_HEAD = 28

MSG_MISSING = "Файла {rel} нет (или это не обычный файл). Набери reset — соберу базу заново."
MSG_BROKEN = "База {rel} повреждена — набери reset, соберу её заново."
MSG_BIG = "База {rel} разрослась больше 32 МБ — так не бывает. Набери reset."
MSG_BUSY = "База {rel} ещё открыта в sqlite3: выйди (.quit) и проверь снова."
MSG_SLOW = "База {rel} отвечает слишком долго — набери reset."
MSG_OLD = ("Этот Python видит SQLite {ver}, а нужен 3.37 или новее: запусти игру через "
           "/usr/bin/python3.")
MSG_NO_TABLE = "В базе нет таблицы {table}. Набери reset — соберу базу заново."
MSG_SWAPPED = ("Таблица {table} подменена: на её месте {kind}. Набери reset — соберу базу "
               "заново.")
MSG_NO_COLUMN = "В таблице {table} нет графы {column}."
MSG_NO_VIEW = "В базе нет представления {view}."
MSG_VIEW_BAD = ("Представление {view} не читается — в нём ошибка (таблица или графа, которой "
                "нет). Пересоздай: DROP VIEW {view}, потом CREATE VIEW.")
MSG_VIEW_VIRTUAL = ("В базе есть виртуальная таблица — представления в такой базе проверка не "
                    "читает. Набери reset.")
MSG_VIEW_BIG = "Представление {view} даёт слишком много строк — сверь условие с заданием."
VIEW_ROWS_CAP = 2000            # строк представления больше — не читаем (задача — не про это)
VIEW_VALUE_CAP = 4096           # значение длиннее — NULL (огромная строка не уходит в память)
MSG_GENERATED = ("В таблице {table} есть вычисляемые графы (GENERATED) — такую таблицу "
                 "проверка не читает. Набери reset — соберу базу заново.")


class Broken(Exception):
    """Базу не прочесть как есть: текст — готовое сообщение игроку (Verdict.message)."""


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sqlite_ok() -> Optional[str]:
    """None — Python-SQLite годится; иначе — сообщение (версия старше MIN_SQLITE)."""
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        return MSG_OLD.format(ver=sqlite3.sqlite_version)
    return None


class Snapshot:
    """Что проверка задачи БД может спросить у базы. Реализации: SqliteSnapshot (здесь),
    PgSnapshot (B1). Все методы бросают Broken с сообщением для игрока."""

    def rows(self, table: str, cols: Optional[Sequence[str]] = None,
             order: Optional[Sequence[str]] = None) -> List[tuple]:
        raise NotImplementedError

    def columns(self, table: str) -> List[dict]:
        raise NotImplementedError

    def indexes(self, table: str) -> List[dict]:
        raise NotImplementedError

    def fks(self, table: str) -> List[dict]:
        raise NotImplementedError

    def checks(self, table: str) -> List[str]:
        raise NotImplementedError

    def views(self) -> List[str]:
        raise NotImplementedError

    def triggers(self) -> List[Tuple[str, str]]:
        raise NotImplementedError

    def trigger_sql(self) -> Dict[str, str]:
        """Имя триггера (строчными) → его текст CREATE TRIGGER."""
        raise NotImplementedError

    def journal_state(self) -> dict:
        """Что может заглушить правила журнала (9б B5, страж Хранилища, ревью I1):
        triggers — все не внутренние триггеры базы {имя: (таблица, режим)}, режим 'O' — обычный
        (в PostgreSQL ещё D — выключен, R — только REPLICA, A — всегда); rules — правила
        (CREATE RULE) на таблицах {таблица: [имена]}; funcs — у функций триггеров {имя:
        (есть SET в настройках, SECURITY DEFINER)}; settings — число настроек роли или базы
        (ALTER ROLE/DATABASE … SET, финал I1); shadows — «схема.audit_log» вне public (временные
        схемы не в счёт: временная таблица живёт до конца своей сессии). В SQLite режимов,
        правил, функций, настроек и схем нет."""
        return {"triggers": {str(n).lower(): (str(t).lower(), "O") for n, t in self.triggers()},
                "rules": {}, "funcs": {}, "settings": 0, "shadows": []}

    def count(self, table: str) -> int:
        raise NotImplementedError

    def view_columns(self, view: str) -> List[str]:
        """Имена граф представления (9б B4, view_index)."""
        raise NotImplementedError

    def view_rows(self, view: str, cols: Sequence[str]) -> List[tuple]:
        """Строки представления по графам cols (не больше VIEW_ROWS_CAP). Читать VIEW —
        значит исполнить его SELECT: в SQLite — у родителя в копии (trusted_schema=OFF, предел
        шагов, без расширений, без виртуальных таблиц в базе), в PostgreSQL — от runner, только
        чтение, с пределом времени: прав сверх игрока у этого чтения нет."""
        raise NotImplementedError

    def tables(self) -> List[str]:
        raise NotImplementedError


def _checks_of(sql: str) -> List[str]:
    """Тексты CHECK (…) из CREATE TABLE: по скобкам, строки в кавычках не мешают."""
    out = []
    for m in re.finditer(r"\bCHECK\s*\(", sql or "", re.I):
        depth, i, quote = 1, m.end(), None
        while i < len(sql) and depth:
            ch = sql[i]
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        out.append(sql[m.end():i - 1].strip())
    return out


class SqliteSnapshot(Snapshot):
    """Снимок файла базы rel песочницы box. Пользоваться через with:

        with dbread.SqliteSnapshot(ctx.box, "records.db") as snap:
            rows = snap.rows("people", ("id", "city"), order=("id",))

    Всё, что пошло не так, — Broken с готовым сообщением."""

    def __init__(self, box, rel: str, cap: int = DB_CAP):
        self.box, self.rel, self.cap = box, str(rel), cap
        self._con: Optional[sqlite3.Connection] = None
        self._tmp: Optional[str] = None
        self._fd: Optional[int] = None
        self._deadline = 0.0
        self._kinds: Optional[Dict[str, Tuple[str, str]]] = None

    # --- открыть и закрыть ----------------------------------------------------------------

    def __enter__(self) -> "SqliteSnapshot":
        try:
            self.open()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _msg(self, text: str, **kw) -> Broken:
        return Broken(text.format(rel=self.rel, **kw))

    def open(self) -> None:
        from termit_app import sandbox
        bad = sqlite_ok()
        if bad:
            raise Broken(bad)
        # fix1 I1: горячий -journal не копируем и не откатываем — откат ведёт файл игрока
        # (в нём бывает путь к super-journal вне копии); незавершённая правка — не в счёт
        if self._hot_journal():
            raise self._msg(MSG_BUSY)
        try:
            tmp = tempfile.mkdtemp(prefix="termit-dbread-")
        except OSError:
            tmp = None
        if tmp is None:
            self._open_in_place()
            return
        self._tmp = tmp
        main = sandbox.read_in_box(self.box, self.rel, self.cap)
        if main is None:
            raise self._msg(MSG_BIG if self._too_big() else MSG_MISSING)
        if not main.startswith(MAGIC):
            raise self._msg(MSG_BROKEN)
        path = os.path.join(tmp, "copy.db")
        self._write(path, main)
        wal = sandbox.read_in_box(self.box, self.rel + "-wal", self.cap)
        if wal:                         # WAL ссылок наружу не содержит — читаем в копии
            self._write(path + "-wal", wal)
        self._connect(path, uri=False)

    def _hot_journal(self) -> bool:
        """Рядом с базой живой -journal (ненулевой заголовок): транзакция не закончена или
        оборвалась. Пустой или обнулённый журнал (TRUNCATE, PERSIST) — не в счёт."""
        from termit_app import sandbox
        fd = sandbox.open_in_box(self.box, self.rel + "-journal", 1 << 62)
        if fd is None:
            return False
        try:
            head = os.pread(fd, JOURNAL_HEAD, 0)
        except OSError:
            return True
        finally:
            os.close(fd)
        return bool(head.strip(b"\x00"))

    def _too_big(self) -> bool:
        """Файл есть, обычный, но больше предела (для сообщения): те же правила пути."""
        from termit_app import sandbox
        fd = sandbox.open_in_box(self.box, self.rel, 1 << 62)
        if fd is None:
            return False
        try:
            return os.fstat(fd).st_size > self.cap
        finally:
            os.close(fd)

    @staticmethod
    def _write(path: str, data: bytes) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)

    def _open_in_place(self) -> None:
        """Запасной путь без записи (recheck): база на месте, через дескриптор."""
        from termit_app import sandbox
        fd = sandbox.open_in_box(self.box, self.rel + "-wal", self.cap)
        if fd is not None:
            os.close(fd)
            raise self._msg(MSG_BUSY)
        fd = sandbox.open_in_box(self.box, self.rel, self.cap)
        if fd is None:
            raise self._msg(MSG_BIG if self._too_big() else MSG_MISSING)
        self._fd = fd
        try:
            head = os.pread(fd, len(MAGIC), 0)
        except OSError:
            head = b""
        if head != MAGIC:
            raise self._msg(MSG_BROKEN)
        self._connect(f"file:/dev/fd/{fd}?mode=ro&immutable=1", uri=True)

    def _connect(self, target: str, uri: bool) -> None:
        try:
            con = sqlite3.connect(target, uri=uri, isolation_level=None, timeout=0)
        except sqlite3.Error:
            raise self._msg(MSG_BROKEN) from None
        self._con = con
        con.set_progress_handler(self._interrupt, PROGRESS_STEPS)
        try:
            con.execute("PRAGMA trusted_schema=OFF")
            con.execute("PRAGMA cell_size_check=ON")
            # первое чтение: SQLite прочтёт -wal (и соберёт -shm) — в своей копии
            self._ask("SELECT count(*) FROM sqlite_master")
            con.execute("PRAGMA query_only=1")
        except Broken:
            raise
        except sqlite3.Error:
            raise self._msg(MSG_BROKEN) from None

    def close(self) -> None:
        con, self._con = self._con, None
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass
        fd, self._fd = self._fd, None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        tmp, self._tmp = self._tmp, None
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)

    # --- запросы --------------------------------------------------------------------------

    def _interrupt(self) -> int:
        return 1 if time.monotonic() > self._deadline else 0

    def _ask(self, sql: str, params: Sequence = ()) -> List[tuple]:
        if self._con is None:
            raise self._msg(MSG_BROKEN)
        self._deadline = time.monotonic() + QUERY_BUDGET
        try:
            return self._con.execute(sql, tuple(params)).fetchall()
        except sqlite3.OperationalError as e:
            if "interrupt" in str(e).lower():
                raise self._msg(MSG_SLOW) from None
            raise self._msg(MSG_BROKEN) from None
        except sqlite3.Error:
            raise self._msg(MSG_BROKEN) from None

    def _objects(self) -> Dict[str, Tuple[str, str]]:
        """Имя → (type, sql) из sqlite_master (имена без учёта регистра, как в SQLite)."""
        if self._kinds is None:
            self._kinds = {str(n).lower(): (str(t), str(s or ""))
                           for t, n, s in self._ask("SELECT type, name, sql FROM sqlite_master")}
        return self._kinds

    def _table(self, table: str) -> str:
        """Имя проверенной таблицы: настоящая (type='table', не virtual), иначе Broken."""
        kind = self._objects().get(str(table).lower())
        if kind is None:
            raise self._msg(MSG_NO_TABLE, table=table)
        typ, sql = kind
        if typ != "table":
            raise self._msg(MSG_SWAPPED, table=table, kind={"view": "представление (VIEW)"}
                            .get(typ, typ))
        if re.match(r"\s*CREATE\s+VIRTUAL\b", sql, re.I):
            raise self._msg(MSG_SWAPPED, table=table, kind="виртуальная таблица")
        # fix1 M1: вычисляемая графа исполняет выражение схемы у читателя — не читаем
        hidden = self._ask(f"PRAGMA table_xinfo({quote_ident(table)})")
        if any(row[6] in (2, 3) for row in hidden):
            raise self._msg(MSG_GENERATED, table=table)
        return quote_ident(table)

    def tables(self) -> List[str]:
        return sorted(n for n, (t, s) in self._objects().items()
                      if t == "table" and not n.startswith("sqlite_")
                      and not re.match(r"\s*CREATE\s+VIRTUAL\b", s, re.I))

    def columns(self, table: str) -> List[dict]:
        name = self._table(table)
        return [{"name": n, "type": str(t or "").upper(), "notnull": bool(nn), "default": d,
                 "pk": int(pk)}
                for _, n, t, nn, d, pk in self._ask(f"PRAGMA table_info({name})")]

    def _cols(self, table: str, cols: Sequence[str]) -> str:
        have = {c["name"].lower() for c in self.columns(table)}
        for c in cols:
            if str(c).lower() not in have:
                raise self._msg(MSG_NO_COLUMN, table=table, column=c)
        return ", ".join(quote_ident(c) for c in cols)

    def rows(self, table: str, cols: Optional[Sequence[str]] = None,
             order: Optional[Sequence[str]] = None) -> List[tuple]:
        name = self._table(table)
        cols = list(cols) if cols else [c["name"] for c in self.columns(table)]
        sql = f"SELECT {self._cols(table, cols)} FROM {name}"
        if order:
            sql += f" ORDER BY {self._cols(table, order)}"
        return self._ask(sql)

    def count(self, table: str) -> int:
        return int(self._ask(f"SELECT count(*) FROM {self._table(table)}")[0][0])

    def indexes(self, table: str) -> List[dict]:
        name = self._table(table)
        out = []
        for _, iname, unique, origin, partial in self._ask(f"PRAGMA index_list({name})"):
            cols = [c for _, _, c in self._ask(f"PRAGMA index_info({quote_ident(iname)})")]
            out.append({"name": iname, "unique": bool(unique), "origin": origin,
                        "partial": bool(partial), "columns": cols})
        return out

    def fks(self, table: str) -> List[dict]:
        name = self._table(table)
        return [{"from": f, "table": t, "to": to}
                for _, _, t, f, to, *_ in self._ask(f"PRAGMA foreign_key_list({name})")]

    def checks(self, table: str) -> List[str]:
        self._table(table)
        return _checks_of(self._objects()[str(table).lower()][1])

    def views(self) -> List[str]:
        return sorted(n for n, (t, _) in self._objects().items() if t == "view")

    def triggers(self) -> List[Tuple[str, str]]:
        """(имя, таблица) триггеров — по sqlite_master."""
        return sorted((str(n), str(tb)) for n, tb in
                      self._ask("SELECT name, tbl_name FROM sqlite_master WHERE type='trigger'"))

    def trigger_sql(self) -> Dict[str, str]:
        """Имя триггера (строчными) → текст CREATE TRIGGER из sqlite_master (A7: страж сверяет
        тело правила журнала — пустое правило с тем же именем журнал не ведёт)."""
        return {n: s for n, (t, s) in self._objects().items() if t == "trigger"}

    def _view(self, view: str) -> str:
        objs = self._objects()
        kind = objs.get(str(view).lower())
        if kind is None or kind[0] != "view":
            raise Broken(MSG_NO_VIEW.format(view=view))
        # виртуальные таблицы (fts5 и др.) исполняют свой код над теневыми таблицами игрока —
        # через представление их у родителя не читаем вовсе
        if any(re.match(r"\s*CREATE\s+VIRTUAL\b", sq, re.I) for t, sq in objs.values()
               if t == "table"):
            raise Broken(MSG_VIEW_VIRTUAL)
        return quote_ident(view)

    def _view_ask(self, view: str, sql: str) -> List[tuple]:
        try:
            return self._ask(sql)
        except Broken as e:
            if str(e) == MSG_SLOW.format(rel=self.rel):
                raise
            raise Broken(MSG_VIEW_BAD.format(view=view)) from None

    def view_columns(self, view: str) -> List[str]:
        name = self._view(view)
        return [str(r[1]) for r in self._view_ask(view, f"PRAGMA table_info({name})")]

    def view_rows(self, view: str, cols: Sequence[str]) -> List[tuple]:
        name = self._view(view)
        have = {c.lower() for c in self.view_columns(view)}
        for c in cols:
            if str(c).lower() not in have:
                raise Broken(MSG_NO_COLUMN.format(table=view, column=c))
        picked = ", ".join(f"CASE WHEN length({quote_ident(c)}) > {VIEW_VALUE_CAP} THEN NULL "
                           f"ELSE {quote_ident(c)} END" for c in cols)
        rows = self._view_ask(view, f"SELECT {picked} FROM {name} LIMIT {VIEW_ROWS_CAP + 1}")
        if len(rows) > VIEW_ROWS_CAP:
            raise Broken(MSG_VIEW_BIG.format(view=view))
        return rows


# --- PostgreSQL (часть 9б): текстовый снимок через доверенный psql ---------------------------
# Копию файлов кластера без сервера не прочитать, поэтому «копия» здесь — текст COPY … TO
# STDOUT, который отдаёт сервер задачи (pgkit.PgService) доверенному psql родителя под
# профилем-читателем. Родитель только разбирает текст; SQL игрока у него не исполняется.
# Сессия снимка — только чтение, с пределами времени, без RLS (row_security=off: таблица,
# которую политика прячет от runner, даёт ошибку, а не «пустой» ответ), search_path —
# сначала pg_catalog. Перед каждым запросом — сокет тот самый, что поднял наш сервер (inode).

PG_OPTIONS = ("-c default_transaction_read_only=on -c statement_timeout=3000 "
              "-c lock_timeout=1000 -c search_path=pg_catalog,public -c row_security=off "
              "-c idle_in_transaction_session_timeout=5000")
MSG_PG_DOWN = "Сервер базы не отвечает — набери reset, подниму его заново."
MSG_PG_RLS = ("На таблице {table} включена защита строк (row level security) — проверка такую "
              "не читает. Набери reset — соберу базу заново.")
MSG_PG_DENIED = ("Таблицу {table} нельзя прочитать — права на неё отняты (REVOKE?). Набери "
                 "reset — соберу базу заново.")
MSG_PG_BIG = "Таблица {table} разрослась так, что проверка её не читает. Набери reset."
MSG_PG_SLOW = "База отвечает слишком долго — набери reset."
MSG_PG_BROKEN = "База повреждена — набери reset, соберу её заново."
MSG_PG_ONLY_GAME = ("Эту базу проверяет только сам тренажёр — выйди из задачи (quit) и зайди "
                    "снова.")

_INT_TYPES = {"smallint", "integer", "bigint", "oid"}
_FLOAT_TYPES = {"real", "double precision"}


def copy_unescape(field: str) -> Optional[str]:
    """Поле текстового формата COPY: \\N — NULL; \\t \\n \\r \\b \\f \\v \\\\, восьмеричные
    \\ddd и шестнадцатеричные \\xhh — как в документации PostgreSQL."""
    if field == "\\N":
        return None
    if "\\" not in field:
        return field
    out, i, n = [], 0, len(field)
    simple = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
    raw = bytearray()

    def flush():
        if raw:
            out.append(raw.decode("utf-8", errors="replace"))
            raw.clear()
    while i < n:
        ch = field[i]
        if ch != "\\" or i + 1 >= n:
            flush()
            out.append(ch)
            i += 1
            continue
        nxt = field[i + 1]
        if nxt in simple:
            flush()
            out.append(simple[nxt])
            i += 2
        elif nxt in "01234567":
            j = i + 1
            while j < n and j < i + 4 and field[j] in "01234567":
                j += 1
            raw.append(int(field[i + 1:j], 8) & 0xFF)
            i = j
        elif nxt == "x" and i + 2 < n and field[i + 2] in "0123456789abcdefABCDEF":
            j = i + 2
            while j < n and j < i + 4 and field[j] in "0123456789abcdefABCDEF":
                j += 1
            raw.append(int(field[i + 2:j], 16))
            i = j
        else:
            flush()
            out.append(nxt)
            i += 2
    flush()
    return "".join(out)


def parse_copy(text: str) -> List[List[Optional[str]]]:
    """Строки текстового COPY (разделитель — табуляция, строка — \\n)."""
    rows = []
    for line in text.split("\n"):
        if line == "":
            continue
        rows.append([copy_unescape(f) for f in line.split("\t")])
    return rows


def _pg_value(text: Optional[str], typ: str):
    """Значение из текста COPY — к виду, как у снимка SQLite: целые — int, дробные — float,
    numeric — Decimal, boolean — bool, остальное — строка (время — ISO-текст)."""
    if text is None:
        return None
    t = typ.split("(")[0].strip()
    try:
        if t in _INT_TYPES:
            return int(text)
        if t in _FLOAT_TYPES:
            return float(text)
        if t == "numeric":
            from decimal import Decimal
            return Decimal(text)
        if t == "boolean":
            return text == "t"
    except ValueError:
        return text
    return text


def _lit(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def split_table(table: str) -> Tuple[str, str]:
    """«ops.watch» → ("ops", "watch"); без схемы — public. Имена — как есть, строчными
    (PostgreSQL складывает имена без кавычек к нижнему регистру)."""
    schema, _, name = str(table).rpartition(".")
    return (schema or "public").lower(), name.lower()


class PgSnapshot(Snapshot):
    """Снимок базы vault сервера задачи (ctx.service — pgkit.PgService). Через with, как
    SqliteSnapshot; всё, что пошло не так, — Broken с готовым сообщением."""

    def __init__(self, service):
        self.svc = service
        self._kinds: Dict[Tuple[str, str], str] = {}
        self._cols: Dict[Tuple[str, str], List[dict]] = {}

    def __enter__(self) -> "PgSnapshot":
        if self.svc is None or not hasattr(self.svc, "run_psql"):
            raise Broken(MSG_PG_ONLY_GAME)
        return self

    def __exit__(self, *exc) -> None:
        return None

    # --- запрос --------------------------------------------------------------------------

    def _copy(self, sql: str, table: str = "") -> List[List[Optional[str]]]:
        from termit_app import pgkit
        if not self.svc.socket_ok():
            raise Broken(MSG_PG_DOWN)
        stamp = getattr(self.svc, "stamp", None)
        # тот ли сервер ответил (ревью B1, M1): первой строкой — время старта postmaster в
        # этом же соединении; не совпало с запомненным при старте — это не наш сервер
        pre = ["-c", f"COPY ({pgkit.STAMP_SQL}) TO STDOUT"] if stamp else []
        try:
            code, out, err = self.svc.run_psql(
                ["-U", pgkit.RUNNER, "-d", pgkit.DATABASE, "-v", "ON_ERROR_STOP=1"] + pre +
                ["-c", f"COPY ({sql}) TO STDOUT"],
                env_extra={"PGOPTIONS": PG_OPTIONS, "PGCLIENTENCODING": "UTF8",
                           "PGCONNECT_TIMEOUT": "3"})
        except pgkit.PgError:
            raise Broken(MSG_PG_DOWN) from None
        if code == -1:
            raise Broken((MSG_PG_BIG if len(out) >= pgkit.PSQL_CAP else MSG_PG_SLOW)
                         .format(table=table))
        if code != 0:
            e = err.decode("utf-8", "replace").lower()
            if "row-level security" in e or "row level security" in e:
                raise Broken(MSG_PG_RLS.format(table=table))
            if "permission denied" in e:
                raise Broken(MSG_PG_DENIED.format(table=table))
            if "statement timeout" in e or "lock timeout" in e:
                raise Broken(MSG_PG_SLOW)
            if "connection to server" in e or "could not connect" in e or \
                    "server closed" in e or "terminating connection" in e:
                raise Broken(MSG_PG_DOWN)
            raise Broken(MSG_PG_BROKEN)
        text = out.decode("utf-8", "replace")
        if stamp:
            first, _, text = text.partition("\n")
            if first != stamp:
                raise Broken(MSG_PG_DOWN)
        return parse_copy(text)

    def _kind(self, table: str) -> str:
        key = split_table(table)
        if key not in self._kinds:
            rows = self._copy(
                "SELECT c.relkind::text, c.relrowsecurity::text FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE n.nspname = {_lit(key[0])} AND c.relname = {_lit(key[1])}", table)
            self._kinds[key] = rows[0][0] + (":rls" if rows and rows[0][1] == "true" else "") \
                if rows else ""
        return self._kinds[key]

    def _table(self, table: str) -> str:
        kind = self._kind(table)
        if not kind:
            raise Broken(MSG_NO_TABLE.format(table=table))
        base = kind.split(":")[0]
        if base not in ("r", "p"):
            what = {"v": "представление (VIEW)", "m": "представление (MATERIALIZED VIEW)",
                    "f": "внешняя таблица"}.get(base, "не таблица")
            raise Broken(MSG_SWAPPED.format(table=table, kind=what))
        if kind.endswith(":rls"):
            raise Broken(MSG_PG_RLS.format(table=table))
        schema, name = split_table(table)
        return f"{quote_ident(schema)}.{quote_ident(name)}"

    def _regclass(self, table: str) -> str:
        return _lit(self._table(table)) + "::regclass"

    # --- интерфейс Snapshot ----------------------------------------------------------------

    def tables(self) -> List[str]:
        rows = self._copy("SELECT CASE WHEN n.nspname = 'public' THEN c.relname ELSE "
                          "n.nspname || '.' || c.relname END FROM pg_catalog.pg_class c JOIN "
                          "pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE "
                          "c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', "
                          "'information_schema') AND n.nspname NOT LIKE 'pg_toast%' "
                          "ORDER BY 1")
        return [r[0] for r in rows]

    def columns(self, table: str) -> List[dict]:
        key = split_table(table)
        if key not in self._cols:
            reg = self._regclass(table)
            rows = self._copy(
                "SELECT a.attname::text, pg_catalog.format_type(a.atttypid, a.atttypmod), "
                "a.attnotnull::text, pg_catalog.pg_get_expr(d.adbin, d.adrelid), "
                "a.attidentity::text, a.attgenerated::text, "
                "(SELECT count(*) FROM pg_catalog.pg_index i WHERE i.indrelid = a.attrelid "
                "AND i.indisprimary AND a.attnum = ANY (i.indkey))::text "
                "FROM pg_catalog.pg_attribute a LEFT JOIN pg_catalog.pg_attrdef d ON "
                "d.adrelid = a.attrelid AND d.adnum = a.attnum "
                f"WHERE a.attrelid = {reg} AND a.attnum > 0 AND NOT a.attisdropped "
                "ORDER BY a.attnum", table)
            self._cols[key] = [{"name": n, "type": (t or "").upper(), "notnull": nn == "true",
                                "default": d, "identity": ident or "", "generated": gen or "",
                                "pk": 1 if pk not in (None, "0") else 0}
                               for n, t, nn, d, ident, gen, pk in rows]
        return self._cols[key]

    def _names(self, table: str, cols: Sequence[str]) -> List[dict]:
        have = {c["name"].lower(): c for c in self.columns(table)}
        out = []
        for c in cols:
            col = have.get(str(c).lower())
            if col is None:
                raise Broken(MSG_NO_COLUMN.format(table=table, column=c))
            if col["generated"] == "v":     # вычисляется при чтении — не читаем (как SQLite)
                raise Broken(MSG_GENERATED.format(table=table))
            out.append(col)
        return out

    def rows(self, table: str, cols: Optional[Sequence[str]] = None,
             order: Optional[Sequence[str]] = None) -> List[tuple]:
        name = self._table(table)
        cols = list(cols) if cols else [c["name"] for c in self.columns(table)]
        picked = self._names(table, cols)
        sql = "SELECT " + ", ".join(quote_ident(c["name"]) for c in picked) + f" FROM {name}"
        if order:
            sql += " ORDER BY " + ", ".join(quote_ident(c["name"])
                                            for c in self._names(table, order))
        return [tuple(_pg_value(v, c["type"].lower()) for v, c in zip(r, picked))
                for r in self._copy(sql, table)]

    def count(self, table: str) -> int:
        return int(self._copy(f"SELECT count(*) FROM {self._table(table)}", table)[0][0])

    def indexes(self, table: str) -> List[dict]:
        reg = self._regclass(table)
        rows = self._copy(
            "SELECT ic.relname::text, i.indisunique::text, i.indisprimary::text, "
            "(SELECT count(*) FROM pg_catalog.pg_constraint k WHERE k.conindid = i.indexrelid "
            "AND k.contype = 'u')::text, (i.indpred IS NOT NULL)::text, "
            "(SELECT string_agg(COALESCE(a.attname::text, '?'), ',' ORDER BY s.n) FROM "
            "unnest(i.indkey::int2[]) WITH ORDINALITY AS s(k, n) LEFT JOIN "
            "pg_catalog.pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = s.k) "
            "FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class ic ON ic.oid = i.indexrelid "
            f"WHERE i.indrelid = {reg} ORDER BY 1", table)
        return [{"name": n, "unique": u == "true",
                 "origin": "pk" if pk == "true" else ("u" if uc not in (None, "0") else "c"),
                 "partial": part == "true", "columns": (cols or "").split(",") if cols else []}
                for n, u, pk, uc, part, cols in rows]

    def fks(self, table: str) -> List[dict]:
        reg = self._regclass(table)
        rows = self._copy(
            "SELECT a.attname::text, CASE WHEN rn.nspname = 'public' THEN rc.relname::text "
            "ELSE rn.nspname || '.' || rc.relname END, ra.attname::text FROM "
            "pg_catalog.pg_constraint k CROSS JOIN LATERAL unnest(k.conkey, k.confkey) AS "
            "u(f, t) JOIN pg_catalog.pg_attribute a ON a.attrelid = k.conrelid AND "
            "a.attnum = u.f JOIN pg_catalog.pg_class rc ON rc.oid = k.confrelid JOIN "
            "pg_catalog.pg_namespace rn ON rn.oid = rc.relnamespace JOIN "
            "pg_catalog.pg_attribute ra ON ra.attrelid = k.confrelid AND ra.attnum = u.t "
            f"WHERE k.conrelid = {reg} AND k.contype = 'f' ORDER BY k.conname, u.f", table)
        return [{"from": f, "table": t, "to": to} for f, t, to in rows]

    def checks(self, table: str) -> List[str]:
        reg = self._regclass(table)
        rows = self._copy("SELECT pg_catalog.pg_get_constraintdef(k.oid) FROM "
                          f"pg_catalog.pg_constraint k WHERE k.conrelid = {reg} AND "
                          "k.contype = 'c' ORDER BY k.conname", table)
        return [c for (d,) in rows for c in _checks_of(d or "")]

    def views(self) -> List[str]:
        rows = self._copy("SELECT c.relname::text FROM pg_catalog.pg_class c JOIN "
                          "pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE "
                          "n.nspname = 'public' AND c.relkind IN ('v', 'm') ORDER BY 1")
        return [r[0] for r in rows]

    def _view(self, view: str) -> str:
        if self._kind(view).split(":")[0] != "v":
            raise Broken(MSG_NO_VIEW.format(view=view))
        schema, name = split_table(view)
        return f"{quote_ident(schema)}.{quote_ident(name)}"

    def view_columns(self, view: str) -> List[str]:
        name = self._view(view)
        rows = self._copy("SELECT a.attname::text FROM pg_catalog.pg_attribute a WHERE "
                          f"a.attrelid = {_lit(name)}::regclass AND a.attnum > 0 AND NOT "
                          "a.attisdropped ORDER BY a.attnum", view)
        return [r[0] for r in rows]

    def view_rows(self, view: str, cols: Sequence[str]) -> List[tuple]:
        """Строки представления: SELECT исполняет сервер задачи от runner (права игрока),
        сессия только для чтения, statement_timeout; типы граф — из каталога."""
        name = self._view(view)
        have = {c.lower() for c in self.view_columns(view)}
        for c in cols:
            if str(c).lower() not in have:
                raise Broken(MSG_NO_COLUMN.format(table=view, column=c))
        typ = {}
        for c in cols:
            r = self._copy("SELECT pg_catalog.format_type(a.atttypid, a.atttypmod) FROM "
                           f"pg_catalog.pg_attribute a WHERE a.attrelid = {_lit(name)}::regclass "
                           f"AND a.attname = {_lit(str(c).lower())}", view)
            typ[c] = (r[0][0] if r else "text").lower()
        picked = ", ".join(f"CASE WHEN length({quote_ident(str(c).lower())}::text) > "
                           f"{VIEW_VALUE_CAP} THEN NULL ELSE {quote_ident(str(c).lower())} END"
                           for c in cols)
        try:
            rows = self._copy(f"SELECT {picked} FROM {name} LIMIT {VIEW_ROWS_CAP + 1}", view)
        except Broken as e:
            if str(e) in (MSG_PG_DOWN, MSG_PG_SLOW):
                raise
            raise Broken(MSG_VIEW_BAD.format(view=view)) from None
        if len(rows) > VIEW_ROWS_CAP:
            raise Broken(MSG_VIEW_BIG.format(view=view))
        return [tuple(_pg_value(v, typ[c]) for v, c in zip(r, cols)) for r in rows]

    def triggers(self) -> List[Tuple[str, str]]:
        rows = self._copy("SELECT t.tgname::text, c.relname::text FROM pg_catalog.pg_trigger t "
                          "JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid JOIN "
                          "pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE "
                          "NOT t.tgisinternal AND n.nspname IN ('public', 'ops') ORDER BY 1, 2")
        return [(n, t) for n, t in rows]

    def trigger_sql(self) -> Dict[str, str]:
        """Имя триггера (строчными) → CREATE TRIGGER и тело его функции (правило журнала)."""
        rows = self._copy("SELECT t.tgname::text, pg_catalog.pg_get_triggerdef(t.oid) || ' ' || "
                          "COALESCE(p.prosrc, '') FROM pg_catalog.pg_trigger t LEFT JOIN "
                          "pg_catalog.pg_proc p ON p.oid = t.tgfoid WHERE NOT t.tgisinternal "
                          "ORDER BY 1")
        return {str(n).lower(): s for n, s in rows}

    def journal_state(self) -> dict:
        trig = self._copy("SELECT t.tgname::text, c.relname::text, t.tgenabled::text FROM "
                          "pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = "
                          "t.tgrelid WHERE NOT t.tgisinternal ORDER BY 1, 2")
        rules = self._copy("SELECT tablename::text, rulename::text FROM pg_catalog.pg_rules "
                           "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
                           "ORDER BY 1, 2")
        funcs = self._copy("SELECT DISTINCT p.proname::text, (p.proconfig IS NOT NULL)::text, "
                           "p.prosecdef::text FROM pg_catalog.pg_trigger t JOIN "
                           "pg_catalog.pg_proc p ON p.oid = t.tgfoid WHERE NOT t.tgisinternal "
                           "ORDER BY 1")
        # финал I1: search_path роли или базы на свою audit_log — журнал заглушён надолго
        settings = self._copy("SELECT count(*)::text FROM pg_catalog.pg_db_role_setting")
        shadows = self._copy("SELECT n.nspname::text || '.' || c.relname::text FROM "
                             "pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = "
                             "c.relnamespace WHERE c.relname = 'audit_log' AND n.nspname <> "
                             "'public' AND n.nspname !~ '^pg_(toast_)?temp_' ORDER BY 1")
        out_rules: Dict[str, List[str]] = {}
        for table, name in rules:
            out_rules.setdefault(str(table).lower(), []).append(str(name))
        return {"triggers": {str(n).lower(): (str(t).lower(), str(m)) for n, t, m in trig},
                "rules": out_rules,
                "funcs": {str(n).lower(): (c == "true", d == "true") for n, c, d in funcs},
                "settings": int(settings[0][0]) if settings else 0,
                "shadows": [str(r[0]) for r in shadows]}

def snapshot(ctx, rel: str):
    """Снимок базы задачи по её движку: PostgreSQL (state _engine = pg) — через сервис
    родителя, иначе — файл rel песочницы (SQLite)."""
    if (ctx.state or {}).get("_engine") == "pg":
        return PgSnapshot(ctx.service)
    return SqliteSnapshot(ctx.box, rel)
