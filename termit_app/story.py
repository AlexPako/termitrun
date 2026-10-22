"""Сюжетный слой: подкладка файлов в песочницу (extras), осколки памяти, улики, доска дела.

Тексты — только в теме (theme.story): если у выбранной темы нет своего раздела, сюжет молча
выключен, чужая атмосфера не подставляется. Код и имена файлов здесь нейтральны."""
import base64
import gzip
import hashlib
import io
import json
import os
import random
import stat
import tarfile
import textwrap
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from termit_app import remarks, textnorm, theme
from termit_app.tasks import kit

# Куда можно класть находку каждого вида, не ломая проверку задачи. Новый хозяин — только
# через tests/test_extras_hosts.py: эталон с подложенными файлами обязан решать задачу.
SAFE_HOSTS: Dict[str, Tuple[str, ...]] = {
    "hidden": ("hidden_cache", "climb_down", "back_up", "home_tilde"),
    "log_tail": ("nano_config", "vim_purge", "tldr_tar"),
    "deep_mem": ("find_name", "kill_frozen", "pbcopy_list"),
    # строка «NOL: …» в старых логах дома (~/old_logs): задачи трека «Данные», которые
    # работают с файлами корня песочницы и в дом не смотрят
    "nol_line": ("pipe_count", "log_period", "top_values"),
    # строка «NOL: …» в старой базе дома (~/archive/*.db): задачи Картотеки, которые работают
    # с records.db корня песочницы и файлы дома не считают
    "db_row": ("null_coalesce", "group_count",
               # Хранилище (9б B5): общая задача на vault.db корня (или сервере), дом не считает
               "subquery"),
    # строка «NOL: …» в комментарии старого скрипта в downloads/ корня (часть 7): задачи
    # трека env, которые с downloads/ не работают и файлы корня не считают
    "script_line": ("dotenv", "exit_codes"),
    # найденный скрипт в downloads/ корня (часть 7, E20): задачи трека env, которые с
    # downloads/ не работают и файлы корня не считают; запуск «грязного» их не ломает
    "found": ("env_vars", "export_child", "dotenv", "exit_codes"),
    # ~/drop — купленные страницы досье и фрагменты (E6)
    "drop": ("where_am_i", "climb_down", "back_up", "home_tilde", "hidden_cache", "run_script",
             "mkdir_p", "copy_move", "star_mask", "question_mask",
             "man_flag", "less_search", "nano_config", "vim_trap", "vim_escape", "vim_purge",
             "tldr_tar",
             "open_gui", "find_name", "grep_r", "du_heavy", "ls_newest", "recent_move",
             "batch_rename", "zip_pack", "pbcopy_list", "kill_frozen", "top_hog",
             # «Данные»: работают с файлами корня песочницы, дом не трогают
             "head_tail", "grep_count", "pipe_count", "redirect_report", "cut_uniq",
             "top_values", "awk_sum", "log_period", "join_parts", "stderr_split",
             "tee_log", "sed_fix", "jq_field", "jq_deep", "curl_api",
             # владелец 22.10: «в ране доступа к досье нет» — новые задачи Основ, Инструментов,
             # Вместо Finder и Данных (FB12–FB21) тоже держат ~/drop (проверено test_extras_hosts)
             "meet_terminal", "line_edit", "cursor_clip", "cut_paste", "history_recall",
             "file_ext", "deep_dig", "deep_rm", "screen_scroll", "screen_find", "quick_fix",
             "cp_dir", "fzf_pick", "z_jump", "flag_use", "job_control", "json_check",
             "bat_lines", "disk_sweep", "dup_sort", "rg_hunt", "fd_hunt", "csv_by_hand",
             "csv_top", "csv_sum", "regex_mask", "regex_anchor", "regex_class", "regex_repeat",
             "regex_group", "grep_only", "flag_review", "sed_groups", "regex_clean",
             "curl_post", "curl_pages",
             # Картотека: records.db и файлы корня песочницы, дом не трогают
             "sqlite_open", "select_where", "order_limit", "distinct_like", "in_between",
             "null_coalesce", "group_count", "group_having", "join_inner", "join_left",
             "sql_pipe", "import_csv", "create_insert", "backup_update", "tx_delete",
             # Хранилище: vault.db корня песочницы или учебный сервер, дом не трогают;
             # задачи стенда (только PostgreSQL) — не хозяева: без сервера их не
             # проверить (tests/test_extras_hosts)
             "case_when", "subquery", "cte_with", "window_rank", "window_lag",
             "joins_more", "constraints_fk", "upsert", "view_index"),
    # «шум» (FB5 п. 70): правдоподобное окружение — termit_app/noise.py. Хозяева отобраны
    # прогоном (без действий не решено, эталон с шумом решает); нет в списках: первые три урока
    # «Основ», стражи и задачи pandas/линтеров без склада колёс (их без ~/wheels не проверить,
    # fb16-wheels). В папку задачи — без ls_newest: посторонняя папка «свежее» файлов задачи
    "noise_home": (
             "cursor_clip", "cut_paste", "climb_down", "back_up", "home_tilde",
             "history_recall", "hidden_cache", "mkdir_p", "copy_move", "file_ext",
             "star_mask", "question_mask", "run_script", "deep_dig", "deep_rm",
             "screen_scroll", "screen_find", "quick_fix", "cp_dir", "fzf_pick",
             "z_jump", "man_flag", "flag_use", "less_search", "nano_config", "vim_trap",
             "vim_escape", "vim_purge", "job_control", "brew_lesson", "tldr_tar",
             "json_check", "bat_lines", "open_gui", "find_name", "grep_r", "du_heavy",
             "ls_newest", "recent_move", "batch_rename", "zip_pack", "pbcopy_list",
             "kill_frozen", "top_hog", "disk_sweep", "dup_sort", "rg_hunt", "fd_hunt",
             "csv_by_hand", "csv_top", "csv_sum", "head_tail", "grep_count",
             "pipe_count", "redirect_report", "cut_uniq", "top_values", "regex_mask",
             "regex_anchor", "regex_class", "regex_repeat", "regex_group", "grep_only",
             "flag_review", "awk_sum", "log_period", "join_parts", "stderr_split",
             "tee_log", "sed_fix", "sed_groups", "regex_clean", "jq_field", "jq_deep",
             "curl_api", "curl_post", "curl_pages", "sqlite_open", "select_where",
             "order_limit", "distinct_like", "in_between", "null_coalesce",
             "group_count", "group_having", "join_inner", "join_left", "sql_pipe",
             "import_csv", "create_insert", "backup_update", "tx_delete", "csv_sql",
             "psql_nav", "psql_pipe", "pg_dialect", "pg_identity", "case_when",
             "subquery", "cte_with", "window_rank", "window_lag", "joins_more",
             "constraints_fk", "upsert", "view_index", "jsonb_query", "copy_dump",
             "columnar", "copy_rejects", "merge_into", "segments", "env_vars",
             "export_child", "perm_basics", "perm_rwx", "read_long_list", "perm_digits",
             "dotenv", "alias_rc", "path_which", "shebang_run", "exit_codes",
             "cron_line", "json_config", "script_audit", "shell_lint", "av_scan",
             "venv_basics", "pip_offline", "pip_freeze", "py_run", "py_vars", "py_loop",
             "py_dict", "py_func", "py_repl", "py_json", "py_csv_json", "py_files",
             "py_stats", "py_regex", "py_urllib"),
    "noise_box": (
             "cursor_clip", "cut_paste", "climb_down", "back_up", "home_tilde",
             "history_recall", "hidden_cache", "mkdir_p", "copy_move", "file_ext",
             "star_mask", "question_mask", "run_script", "deep_dig", "deep_rm",
             "screen_scroll", "screen_find", "quick_fix", "cp_dir", "fzf_pick",
             "z_jump", "man_flag", "flag_use", "less_search", "nano_config", "vim_trap",
             "vim_escape", "vim_purge", "job_control", "brew_lesson", "tldr_tar",
             "json_check", "bat_lines", "open_gui", "find_name", "grep_r", "du_heavy",
             "recent_move", "batch_rename", "zip_pack", "pbcopy_list", "kill_frozen",
             "top_hog", "disk_sweep", "dup_sort", "rg_hunt", "fd_hunt", "csv_by_hand",
             "csv_top", "csv_sum", "head_tail", "grep_count", "pipe_count",
             "redirect_report", "cut_uniq", "top_values", "regex_mask", "regex_anchor",
             "regex_class", "regex_repeat", "regex_group", "grep_only", "flag_review",
             "awk_sum", "log_period", "join_parts", "stderr_split", "tee_log",
             "sed_fix", "sed_groups", "regex_clean", "jq_field", "jq_deep", "curl_api",
             "curl_post", "curl_pages", "sqlite_open", "select_where", "order_limit",
             "distinct_like", "in_between", "null_coalesce", "group_count",
             "group_having", "join_inner", "join_left", "sql_pipe", "import_csv",
             "create_insert", "backup_update", "tx_delete", "csv_sql", "psql_nav",
             "psql_pipe", "pg_dialect", "pg_identity", "case_when", "subquery",
             "cte_with", "window_rank", "window_lag", "joins_more", "constraints_fk",
             "upsert", "view_index", "jsonb_query", "copy_dump", "columnar",
             "copy_rejects", "merge_into", "segments", "env_vars", "export_child",
             "perm_basics", "perm_rwx", "read_long_list", "perm_digits", "dotenv",
             "alias_rc", "path_which", "shebang_run", "exit_codes", "cron_line",
             "json_config", "script_audit", "shell_lint", "av_scan", "venv_basics",
             "pip_offline", "pip_freeze", "py_run", "py_vars", "py_loop", "py_dict",
             "py_func", "py_repl", "py_json", "py_csv_json", "py_files", "py_stats",
             "py_regex", "py_urllib"),
    # хабар данных в скрытой .cache/.pd корня песочницы (E17). Без задач, где свежая
    # папка в корне или её вес могут сбить игрока: ls_newest, recent_move, du_heavy
    "paydata": ("where_am_i", "climb_down", "back_up", "home_tilde", "hidden_cache",
                "run_script", "mkdir_p", "copy_move", "star_mask", "question_mask",
                "man_flag", "less_search", "nano_config", "vim_trap", "vim_escape", "vim_purge",
                "tldr_tar",
                "open_gui", "find_name", "grep_r", "batch_rename", "zip_pack", "pbcopy_list",
                "kill_frozen", "top_hog",
                # «Данные»: маски *.csv и cut/grep по именованным файлам скрытую .cache не
                # цепляют; ни grep -r, ни find по корню в эталонах нет
                "head_tail", "grep_count", "pipe_count", "redirect_report", "cut_uniq",
                "top_values", "awk_sum", "log_period", "join_parts", "stderr_split",
                "tee_log", "sed_fix", "jq_field", "jq_deep", "curl_api",
                # Картотека: файлы по именам (records.db, *.csv), скрытую .cache не цепляют
                "sqlite_open", "select_where", "order_limit", "distinct_like", "in_between",
                "null_coalesce", "group_count", "group_having", "join_inner", "join_left",
                "sql_pipe", "import_csv", "create_insert", "backup_update", "tx_delete",
                # Хранилище: vault.db и файлы задачи — по именам, скрытую .cache не цепляют
                "case_when", "subquery", "cte_with", "window_rank", "window_lag",
                "joins_more", "constraints_fk", "upsert", "view_index"),
}


def has_story() -> bool:
    """Есть ли у выбранной темы свой сюжетный слой."""
    return bool(theme.story("shards") or theme.story("clues"))


def extra(root: str, path: str, data, mtime: float = None, mode: int = None) -> dict:
    """Одна запись extras: root — "box" (корень песочницы) или "home" (~ песочницы)."""
    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    return {"root": root, "path": path, "b64": base64.b64encode(raw).decode("ascii"),
            "mtime": mtime, "mode": mode}


def extras_for(task, state: dict, p: dict, seed: int) -> list:
    """Все подложенные файлы рана для этой задачи («шум», осколок, найденный скрипт, досье)."""
    from termit_app import noise
    out = []
    if task.id in SAFE_HOSTS["noise_home"]:
        out += noise.home(seed)
    if task.id in SAFE_HOSTS["noise_box"]:
        out += noise.box(seed)
    shard = shard_for(task, p, seed)
    if shard:
        out += shard_extras(shard, state, seed, have=len(p.get("shards", [])))
    found = found_for(task, p, seed)
    if found:
        out += found_extras(found, seed)
    if task.id in SAFE_HOSTS["drop"]:
        out += drop_extras(p)
    return out


# --- Найденные скрипты (часть 7, E20) -----------------------------------------------------
# После урока script_audit в downloads/ задач трека env иногда лежит «скачанный» скрипт:
# полезный (печатает, где искать находки) или учебный «грязный» (envkit.dirty_script, A8:
# только метка и только внутри игры). Игрок решает сам: прочесть, запустить или не трогать.
# Запуск «грязного» не штрафуется: в разборе — строка «запустил не читая», −0. Права 644 —
# как у всего скачанного. Тексты строк разбора — в теме (found_ui), иначе нейтральные.

FOUND_CHANCE = 0.35
FOUND_REQUIRES = "script_audit"
FOUND_DIR = "downloads"
FOUND_TIP = "tip: read a stranger's script first with head and grep -n, run it later"
FOUND_RAN = ("Найденный скрипт ты запустил, не читая: его строка легла в ~/.zshrc песочницы. "
             "Здесь она безвредна, штрафа нет. В жизни — сначала head и grep -n.")
FOUND_READ = "Найденный скрипт ты прочёл и не запустил — так и надо."
_READERS = ("head", "tail", "less", "more", "cat", "grep", "shasum", "nano", "vim", "bat",
            "wc", "clamscan")
_RUNNERS = ("sh", "bash", "zsh", "source", ".")


def found_for(task, p: dict, seed: int) -> Optional[dict]:
    """Найденный скрипт этой песочницы или None: хозяин из SAFE_HOSTS["found"], задача уже
    встречалась, урок script_audit пройден, и выпало зерно. {"kind": "dirty"|"useful",
    "name", "tip"} — tip: что напечатает полезный."""
    if (task.id not in SAFE_HOSTS["found"] or task.id not in p["tasks"]
            or not _learned(p, FOUND_REQUIRES)):
        return None
    rng = random.Random(seed ^ 0xF0F0)
    if rng.random() >= FOUND_CHANCE:
        return None
    from termit_app.tasks import envkit
    if rng.random() < 0.5:
        return {"kind": "dirty", "name": rng.choice(envkit.DIRTY_NAMES), "tip": None}
    return {"kind": "useful", "name": rng.choice(sorted(envkit.USEFUL)), "tip": found_tip(p)}


def found_tip(p: dict) -> str:
    """Что печатает полезный найденный скрипт: где искать первый ещё не найденный осколок,
    чей навык уже пройден (текст темы found_ui.tips[вид]); иначе — нейтральный совет."""
    ui_ = theme.story("found_ui") or {}
    tips = ui_.get("tips") or {}
    have = set(p.get("shards", ()))
    for s in SHARDS:
        if (s.id not in have and shard_text(s) is not None and s.kind in tips
                and _learned(p, KIND_REQUIRES[s.kind])):
            return (ui_.get("tip") or "{how}").format(how=tips[s.kind])
    return FOUND_TIP


def _sh_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def found_extras(found: dict, seed: int) -> list:
    """Файл найденного скрипта в downloads/ корня (права 644)."""
    from termit_app.tasks import envkit
    rng = random.Random(seed ^ 0xF1F1)
    name = found["name"]
    if found["kind"] == "dirty":
        text, _ = envkit.dirty_script(rng, name)
    else:
        lines = envkit.useful_script(name, rng.randint(3, 30)).split("\n")
        at = 4 + len(envkit._GUARD)          # сразу за охраной: печатает совет первым делом
        lines.insert(at, "echo " + _sh_quote(found["tip"] or FOUND_TIP))
        text = "\n".join(lines)
    return [extra("box", f"{FOUND_DIR}/{name}", text, mode=0o644)]


def found_lines(box, found: Optional[dict], cmds: List[str]) -> List[str]:
    """Строки разбора про найденный скрипт: «грязный» запущен (метка в ~/.zshrc песочницы) —
    без штрафа, одной строкой; прочитан и не запущен — одобрение; иначе — ничего."""
    if not found:
        return []
    from termit_app.tasks import env, envkit
    ui_ = theme.story("found_ui") or {}
    name = found["name"]
    ran = read = False
    for _, cmd, args in envkit.commands(cmds):
        if cmd is None:
            continue
        base = cmd.rsplit("/", 1)[-1]
        hit = any(a.rsplit("/", 1)[-1] == name for a in args)
        if base == name or (base in _RUNNERS and hit):
            ran = True
        elif base in _READERS and hit:
            read = True
    if found["kind"] == "dirty" and env.ran_dirty(box):
        return [ui_.get("ran") or FOUND_RAN]
    if read and not ran:
        return [ui_.get("read") or FOUND_READ]
    return []


# --- Осколки памяти -----------------------------------------------------------------------

@dataclass(frozen=True)
class Shard:
    id: str
    host: str       # задача, в песочницу которой кладётся осколок
    kind: str       # как спрятан: hidden | log_tail | deep_mem | nol_line | db_row


SHARDS: Tuple[Shard, ...] = (
    Shard("s01", "hidden_cache", "hidden"),
    Shard("s02", "climb_down", "hidden"),
    Shard("s03", "back_up", "hidden"),
    Shard("s04", "home_tilde", "hidden"),
    Shard("s05", "nano_config", "log_tail"),
    Shard("s06", "vim_purge", "log_tail"),
    Shard("s07", "tldr_tar", "log_tail"),
    Shard("s08", "find_name", "deep_mem"),
    Shard("s09", "kill_frozen", "deep_mem"),
    Shard("s10", "pbcopy_list", "deep_mem"),
    Shard("s11", "pipe_count", "nol_line"),
    Shard("s12", "log_period", "nol_line"),
    Shard("s13", "top_values", "nol_line"),
    Shard("s14", "null_coalesce", "db_row"),
    Shard("s15", "group_count", "db_row"),
    Shard("s16", "subquery", "db_row"),
    # Фабрика (часть 7, E19): строка «NOL: …» в комментарии старого скрипта в downloads/
    Shard("s17", "dotenv", "script_line"),
    Shard("s18", "exit_codes", "script_line"),
)
SHARD_TOTAL = 18
SHARD_PLANT_CHANCE = 0.5
# осколок кладётся, только когда урок навыка, которым его ищут, уже пройден
KIND_REQUIRES = {"hidden": "hidden_cache", "log_tail": "less_search", "deep_mem": "find_name",
                 "nol_line": "grep_count", "db_row": "distinct_like",
                 # чужой скрипт читают, не запуская: grep -n по downloads/ (E13)
                 "script_line": "script_audit"}
SHARD_META = ".termit/shard"        # пишет родитель: что лежит в этой песочнице
CLAIMED = ".termit/claimed"         # пишет хук: игрок сдал верный код
EMPTY = "Пусто. loot КОДОВОЕ_СЛОВО — сдать находку (или loot ПУТЬ_К_ФАЙЛУ)"
NO_ARG = ("Сдать находку: loot КОДОВОЕ_СЛОВО. Найденные осколки — после задачи: "
          "./termit memory")


def norm_code(code: str) -> str:
    """Код осколка без учёта регистра, пробелов по краям и ё/е."""
    return textnorm.norm(code).casefold().replace("ё", "е")


def code_sha(code: str) -> str:
    return hashlib.sha256(norm_code(code).encode("utf-8")).hexdigest()


def shard_text(shard: Shard) -> Optional[dict]:
    t = theme.story("shards").get(shard.id) or {}
    return t if t.get("code") and t.get("text") else None


def _learned(p: dict, task_id: str) -> bool:
    return p["tasks"].get(task_id, {}).get("solved", 0) > 0


def shard_for(task, p: dict, seed: int) -> Optional[Shard]:
    """Осколок этой песочницы или None: в теме есть текст, ещё не найден, задача уже
    встречалась, урок навыка пройден, и выпало зерно (или куплена наводка)."""
    shard = next((s for s in SHARDS if s.host == task.id), None)
    if (shard is None or shard_text(shard) is None or shard.id in p.get("shards", ())
            or task.id not in p["tasks"] or not _learned(p, KIND_REQUIRES[shard.kind])):
        return None
    if p.get("shard_tip") or random.Random(seed ^ 0x5A5A).random() < SHARD_PLANT_CHANCE:
        return shard
    return None


def _ui(key: str, default: str) -> str:
    return theme.story("shard_ui").get(key) or default


def shard_lines(shard: Shard, placeholder: bool = False) -> Optional[List[str]]:
    """Строки файла осколка: заголовок, текст, кодовое слово."""
    t = shard_text(shard)
    if t is None:
        if not placeholder:
            return None
        t = {"title": "check", "code": "CHECK", "text": ["line one", "line two"]}
    return ([_ui("head", "RECORD · {title}").format(title=t["title"]), ""] + list(t["text"]) +
            ["", _ui("code", "code: {code}").format(code=t["code"])])


def shard_extras(shard: Shard, state: dict, seed: int, have: int = 0,
                 placeholder: bool = False) -> list:
    """Файл осколка там, где его находят навыком, и служебная метка для хука."""
    lines = shard_lines(shard, placeholder)
    if lines is None:
        return []
    t = shard_text(shard) or {"title": "check", "code": "CHECK", "file": "record"}
    # в метке нет ни кода, ни его sha: скопировать её в .termit/claimed бесполезно
    meta = {"id": shard.id, "title": t["title"], "have": have, "total": SHARD_TOTAL}
    return (place(shard.kind, shard.host, t.get("file") or "record", lines, seed, state) +
            [extra("box", SHARD_META, json.dumps(meta, ensure_ascii=False))])


def _read_json(box, rel) -> Optional[dict]:
    """Служебный json из песочницы: ни одно звено пути не симлинк, без FIFO и гигантов
    (sandbox.read_in_box — та же защита, что у судьи)."""
    from termit_app import sandbox
    raw = sandbox.read_in_box(box, rel, 4096)
    try:
        data = json.loads(raw.decode("utf-8")) if raw is not None else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def claim(box, arg: str) -> Optional[dict]:
    """Хук: сданный код совпал с кодом осколка этой песочницы (из темы, по id метки) →
    метка .termit/claimed с sha, посчитанным хуком по СДАННОМУ коду. Родитель сверяет его
    с кодом из темы. Возвращает метку осколка или None. Запись — без симлинков."""
    meta = _read_json(box, SHARD_META)
    shard = next((s for s in SHARDS if meta and s.id == meta.get("id")), None)
    t = shard_text(shard) if shard else None
    if t is None or not norm_code(arg) or norm_code(arg) != norm_code(t["code"]):
        return None
    body = json.dumps({"id": shard.id, "code_sha": code_sha(arg)}).encode()
    return meta if write_mark(Path(box) / CLAIMED, body) else None


READERS = ("cat", "less", "more", "head", "tail", "bat", "nano", "vim", "grep", "sort")


def auto_claim(box, line: str, pwd: str) -> Optional[dict]:
    """Хук после команды: игрок прочитал файл, в котором лежит код осколка этой песочницы
    (cat/less/head… по пути к нему), — сдать код за него (владелец 21.10: «прочитал осколок,
    и он нигде не сохранился»). Уже сдан — None."""
    from termit_app import sandbox
    words = line.split()
    if not words or words[0] not in READERS or (Path(box) / CLAIMED).exists():
        return None
    meta = _read_json(box, SHARD_META)
    shard = next((s for s in SHARDS if meta and s.id == meta.get("id")), None)
    t = shard_text(shard) if shard else None
    if t is None:
        return None
    code = str(t["code"])
    for word in words[1:]:
        if word.startswith("-"):
            continue
        path = (Path(pwd) / os.path.expanduser(word)).resolve()
        if not path.is_file() or not sandbox.inside(path, box):
            continue
        try:
            text = path.read_text("utf-8", errors="replace")[:65536]
        except OSError:
            continue
        if code in text:
            return claim(box, code)
    return None


def write_mark(path: Path, body: bytes) -> bool:
    """Хук пишет служебную метку в .termit: без перехода по симлинкам, только обычный файл."""
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644)
    except OSError:
        return False
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return False
        os.ftruncate(fd, 0)
        os.write(fd, body)
    finally:
        os.close(fd)
    return True


def found_message(meta: dict) -> str:
    return _ui("found", "{n}/{total} — «{title}»").format(
        n=int(meta.get("have", 0)) + 1, total=meta.get("total", SHARD_TOTAL),
        title=meta.get("title", ""))


def collect(box, p: dict, expect: Optional[str]) -> dict:
    """Родитель после задачи (и при quit): переносит сданный осколок в прогресс.
    Засчитывается только осколок, положенный в эту песочницу (expect), с верным кодом;
    ничего не клали (expect=None) — ничего и не собираем."""
    if expect is None:
        return {"shard": None}
    got = _read_json(box, CLAIMED)
    sid = got.get("id") if got else None
    shard = next((s for s in SHARDS if s.id == sid), None)
    t = shard_text(shard) if shard else None
    if (shard is None or t is None or sid != expect
            or got.get("code_sha") != code_sha(t["code"]) or sid in p["shards"]):
        return {"shard": None}
    p["shards"].append(sid)
    p["shard_tip"] = False
    return {"shard": sid}


# Разовые подсказки охоты: флаг → урок, после которого охота этого вида имеет смысл.
HUNT_FLAGS = {"shard_hint": "hidden_cache", "nol_hint": "grep_count",
              "db_hint": "distinct_like", "script_hint": "script_audit"}


def hunt_hints(p: dict) -> List[str]:
    """Одноразовые реплики «охота существует»: каждая — один раз, после своего урока.
    Текста в теме нет — молчим (и флаг не ставим)."""
    out = []
    flags = theme.story("story_flags")
    for flag, lesson in HUNT_FLAGS.items():
        text = flags.get(flag)
        if text and flag not in p["flags"] and _learned(p, lesson):
            p["flags"].append(flag)
            out.append(text)
    return out


def memory_lines(p: dict) -> List[str]:
    """./termit memory: найденные осколки с текстом, ненайденные — место хозяина."""
    if not theme.story("shards"):
        return [NO_CASE]
    from termit_app.tasks import registry
    found = set(p.get("shards", ()))
    out = [_ui("memory_title", "Осколки: {n}/{total}").format(
        n=len(found & {s.id for s in SHARDS}), total=SHARD_TOTAL), ""]
    for s in SHARDS:
        t = shard_text(s)
        if s.id in found and t:
            out.append(f"🧩 {t['title']}")
            out.append(_fill(" ".join(t["text"]), "   ", "   "))   # строки файла — одним абзацем
        else:
            out.append(f"··· {theme.place(registry.get(s.host).track)}")
    return out


# --- Улики стражей и доска дела -----------------------------------------------------------

WAVE1_BOSSES = ("boss_basics", "boss_tools", "boss_finder")   # первый слой загадки
LAYER_D_BOSS = "boss_data"                                      # версия волны D
LAYER_DB_BOSS = "boss_db"                                       # версия Картотеки
LAYER_ENV_BOSS = "boss_env"                                     # версия Фабрики (слой 2)
NO_CASE = "В этой теме сюжетного дела нет."


def clue(boss_id: str) -> Optional[List[str]]:
    """Главная улика стража (3–4 строки) — бесплатно, при первой победе."""
    return list((theme.story("clues").get(boss_id) or {}).get("text") or ()) or None


def clue_tags(boss_id: str) -> List[str]:
    return list((theme.story("clues").get(boss_id) or {}).get("tags") or ())


def new_in_case(boss_id: str) -> Optional[str]:
    """Строка «Новое в деле: «метка»» под уликой."""
    fmt = theme.story("case").get("new")
    tags = clue_tags(boss_id)
    if not fmt or not tags:
        return None
    return fmt.format(tags=", ".join(f"«{t}»" for t in tags))


def _closed_by(until, bosses) -> bool:
    """Вопрос закрыт: until — страж или кортеж стражей (закрывают все вместе, B5)."""
    if until is None:
        return False
    if isinstance(until, (tuple, list)):
        return all(b in bosses for b in until)
    return until in bosses


def _open(q: dict, bosses) -> bool:
    return ((q.get("after") is None or q["after"] in bosses) and
            not _closed_by(q.get("until"), bosses) and
            not _closed_by(q.get("until_all"), bosses))


def sealed_line(boss_id: str, bosses) -> Optional[str]:
    """Запечатанная часть улики (B5, слой 3 библии): пока не взяты все стражи needs — метка
    печати; после — текст, если тема его уже написала (None — печать остаётся)."""
    seal = (theme.story("clues_sealed") or {}).get(boss_id)
    if not seal:
        return None
    if all(b in bosses for b in seal.get("needs") or ()) and seal.get("text"):
        return seal["text"]
    return seal.get("label") or None


def case_lines(p: dict) -> List[str]:
    """./termit case: улики, осколки, открытые вопросы и версия (первый слой — в волне 1)."""
    case = theme.story("case")
    if not case or not has_story():
        return [NO_CASE]
    bosses = p.get("bosses", [])
    out = [case.get("title", "Дело"), "", "Улики"]
    beaten = [b for b in bosses if clue(b)]
    if not beaten:
        out.append(_fill(case.get("empty", "пока пусто"), "  ", "  "))
    for b in beaten:
        tags = ", ".join(f"«{t}»" for t in clue_tags(b))
        out.append(f"  ⚔ {_boss_title(b)}" + (f" — {tags}" if tags else ""))
        out += [_fill(line, "     ", "     ") for line in clue(b)]
        seal = sealed_line(b, bosses)
        if seal:
            out.append(_fill(seal, "     ", "     "))
    out += _shard_case_lines(p)
    out += _fragment_case_lines(p)
    out += _home_case_lines(p)
    questions = [q["text"] for q in case.get("questions", ()) if _open(q, bosses)]
    if questions:
        out += ["", "Открытые вопросы"] + [f"  ? {q}" for q in questions]
    if case.get("layer1") and all(b in bosses for b in WAVE1_BOSSES):
        out += ["", "Версия", _fill(case["layer1"], "  ", "  ")]
    if case.get("layer_d") and LAYER_D_BOSS in bosses:
        out += ["", case.get("layer_d_title", "Версия"), _fill(case["layer_d"], "  ", "  ")]
    if case.get("layer_db") and LAYER_DB_BOSS in bosses:
        out += ["", case.get("layer_db_title", "Версия"), _fill(case["layer_db"], "  ", "  ")]
    if case.get("layer_env") and LAYER_ENV_BOSS in bosses:
        out += ["", case.get("layer_env_title", "Версия"), _fill(case["layer_env"], "  ", "  ")]
    return out


def _fill(text: str, first: str, rest: str) -> str:
    from termit_app import ui
    return ui.story_fill(text, first, rest)


def _boss_title(boss_id: str) -> str:
    from termit_app.tasks import registry
    tasks = registry.all_tasks()
    return theme.title(tasks[boss_id]) if boss_id in tasks else boss_id


def _shard_case_lines(p: dict) -> List[str]:
    """Осколки на доске дела: сколько найдено и какие."""
    if not theme.story("shards"):
        return []
    found = [s for s in SHARDS if s.id in p.get("shards", ()) and shard_text(s)]
    out = ["", _ui("case", "Осколки: {n}/{total}").format(n=len(found), total=SHARD_TOTAL)]
    if found:
        out.append(_fill(" · ".join(shard_text(s)["title"] for s in found), "  ", "  "))
    out.append("  ./termit memory")
    return out


# --- Досье и «Половина отдана» (E6) -------------------------------------------------------
# Стр. 1 досье читается сразу в ./termit dossier. Стр. 2–3 и фрагменты — файлы в ~/drop
# каждой песочницы из SAFE_HOSTS["drop"]: открыть их — повторить пройденный навык. Текст в
# ./termit dossier/case появляется, только когда игрок открыл файл руками (p["opened"]).

DROP = "drop"
DOSSIER_PAGES = 3
JUNK_FILES = 24             # пустышки вокруг фрагмента 3 (find по маске)


def _who_list() -> List[str]:
    """Досье темы, которые продаёт витрина (shop.DOSSIERS): текст досье может появиться в теме
    раньше, чем его страницы встанут на витрину (Фрося, часть 7: витрина — E22)."""
    from termit_app import shop
    return [w for w in theme.story("dossiers") if w in shop.DOSSIERS]


# src — откуда брать тексты (по умолчанию theme.story); заглушки для проверки хозяев
Source = Callable[[str], dict]


def _page_text(who: str, k: int, src: Optional[Source] = None) -> Optional[List[str]]:
    pages = ((src or theme.story)("dossiers").get(who) or {}).get("pages") or ()
    return list(pages[k - 1]) if len(pages) >= k and pages[k - 1] else None


def _fragment(k: int, src: Optional[Source] = None) -> Optional[dict]:
    t = (src or theme.story)("fragments").get(k) or {}
    return t if t.get("text") else None


def stem(item_id: str, src: Optional[Source] = None) -> Optional[str]:
    """Основа имени файла покупки: voron2 → voron_2, half1 → half_1; стр. 1 файла не имеет."""
    if item_id.startswith("half") and item_id[4:].isdigit():
        return f"half_{item_id[4:]}"
    who, k = item_id[:-1], item_id[-1:]
    if k in ("2", "3") and who in (src or theme.story)("dossiers"):
        return f"{who}_{k}"
    return None


def drop_path(item_id: str, src: Optional[Source] = None) -> Optional[str]:
    """Где лежит покупка внутри ~ песочницы."""
    st = stem(item_id, src)
    if st is None:
        return None
    if st.startswith("half_"):
        return {"half_1": f"{DROP}/.half/.night/.rain/.half_1.txt",
                "half_2": f"{DROP}/half_2.tar.gz", "half_3": f"{DROP}/junk/half_3.mem",
                "half_4": f"{DROP}/half_4.json", "half_5": f"{DROP}/half_5.db",
                "half_6": f"{DROP}/half_6.sql", "half_7": f"{DROP}/half_7.sh"}.get(st)
    return f"{DROP}/{st}.txt.gz" if st.endswith("_2") else f"{DROP}/{st}.tar.gz"


def _junk() -> list:
    rng = random.Random(0xD0C)
    names = sorted({f"{rng.choice(('dump', 'core', 'swap', 'trash', 'old', 'tmp'))}_"
                    f"{rng.randint(100, 999)}.{rng.choice(('bin', 'dat', 'log', 'bak'))}"
                    for _ in range(JUNK_FILES * 2)})[:JUNK_FILES]
    return [extra("home", f"{DROP}/junk/{n}", "\n".join(f"{rng.getrandbits(32):08x}"
                                                       for _ in range(4)) + "\n")
            for n in names]


def _file_extras(item_id: str, lines: List[str], src: Optional[Source] = None) -> list:
    st, path = stem(item_id, src), drop_path(item_id, src)
    body = "\n".join(lines) + "\n"
    if path.endswith(".txt.gz"):
        return [extra("home", path, _gz(body))]
    if path.endswith(".tar.gz"):
        return [extra("home", path, _tgz({f"{st}.txt": body}))]
    if path.endswith(".json"):        # одной строкой: читать — jq, как сводку лотов
        return [extra("home", path, json.dumps({"lines": lines}, ensure_ascii=False) + "\n")]
    if path.endswith(".db"):          # учебная база: читать — sqlite3 и SELECT по порядку
        return [extra("home", path, lines_db(lines))]
    if path.endswith(".sql"):         # файл команд SQL: .read в базу в памяти, потом SELECT
        return [extra("home", path, lines_sql(lines))]
    if path.endswith(".sh"):          # скрипт: прочти, потом chmod +x и запуск (часть 7)
        return [extra("home", path, lines_sh(lines), mode=0o644)]
    out = [extra("home", path, body)]
    return (_junk() + out) if st == "half_3" else out


def _file_lines(lines: List[str]) -> List[str]:
    """Строки файла по ширине терминала (cat не переносит слова сам)."""
    from termit_app import tui
    out = []
    for line in lines:
        out += textwrap.wrap(line, tui.story_width(), break_long_words=False,
                             break_on_hyphens=False) or [""]
    return out


def _lines_for(item_id: str, src: Optional[Source] = None) -> Optional[List[str]]:
    st = stem(item_id, src)
    if st is None:
        return None
    if st.startswith("half_"):
        t = _fragment(int(st[5:]), src)
        return _file_lines([t.get("title", ""), ""] + list(t["text"])) if t else None
    who, k = st.rsplit("_", 1)
    text = _page_text(who, int(k), src)
    name = ((src or theme.story)("dossiers").get(who) or {}).get("name", who)
    return _file_lines([f"{name} · p. {k}", ""] + text) if text else None


def drop_extras(p: dict, src: Optional[Source] = None) -> list:
    """Купленные стр. 2–3 досье и фрагменты — файлами в ~/drop."""
    out = []
    for item_id in p.get("owned", ()):
        lines = _lines_for(item_id, src)
        if lines:
            out += _file_extras(item_id, lines, src)
    return out


def _owned_stems(p: dict) -> Dict[str, str]:
    return {stem(i): i for i in p.get("owned", ()) if stem(i)}


def opened_name(p: dict, st: str) -> str:
    """Человеческое имя открытого файла (имя позиции витрины), а не основа имени."""
    from termit_app import shop
    item_id = _owned_stems(p).get(st)
    return shop.name(item_id).lstrip("🗂🩸 ") if item_id else st


def mark_opened(p: dict, cmds: List[str]) -> List[str]:
    """Команда игрока упоминает основу имени купленного файла → файл открыт."""
    got = []
    for st in _owned_stems(p):
        if st not in p["opened"] and any(st in c for c in cmds):
            p["opened"].append(st)
            got.append(st)
    return got


HOW = {   # чем открыть покупку: навык, который уже пройден
    # zcat на macOS ищет файл.Z, поэтому gunzip -c или zcat через перенаправление
    "_2": "gunzip -c ~/{path} (или zcat < ~/{path})",
    "_3": "tar -xzf ~/{path} -C ~/{drop} && cat ~/{drop}/{stem}.txt",
    "half_1": "в скрытых папках ~/{drop}: ls -laR ~/{drop} (или print -l ~/{drop}/**/*(D)), "
              "потом cat ПУТЬ",
    "half_2": "tar -tzf ~/{path} | grep half, потом tar -xzf ~/{path} -C ~/{drop}, "
              "потом cat ~/{drop}/{stem}.txt",
    "half_3": "среди мусора в ~/{drop}/junk: find ~/{drop} -name '*.mem', потом cat ПУТЬ",
    "half_4": "сводка одной строкой JSON: jq -r '.lines[]' ~/{path}",
    "half_5": "база SQLite: sqlite3 ~/{path} \"SELECT body FROM lines ORDER BY id\"",
    "half_6": "файл команд SQL: cd ~/{drop} && sqlite3 :memory: \".read {stem}.sql\" "
              "\"SELECT body FROM lines ORDER BY id\"",
    "half_7": "скрипт: сначала прочти — head ~/{path}, потом chmod +x ~/{path} && ~/{path}",
}

EXPLAIN = {   # одна строка объяснения: навык мог ещё не встретиться в уроках
    "_2": "gunzip -c — распаковать .gz и вывести на экран; сам архив остаётся как был.",
    "_3": "tar -xzf АРХИВ -C ПАПКА — распаковать tar.gz в папку: x — извлечь, z — gzip, "
          "f — вот этот файл, -C — куда.",
    "half_1": "ls -laR — все файлы, и скрытые (на точку), во всех вложенных папках сразу.",
    "half_2": "tar -tzf — только список файлов архива, без распаковки; -xzf … -C ПАПКА — "
              "распаковать в папку.",
    "half_3": "find ПАПКА -name 'маска' — искать файл по имени во всех вложенных папках.",
    "half_4": "jq -r '.lines[]' — каждый элемент списка lines отдельной строкой, без кавычек.",
    "half_5": "sqlite3 база \"SELECT …\" — запрос к базе; ORDER BY id — строки по порядку.",
    "half_6": "sqlite3 :memory: — база в памяти; \".read файл\" выполнит команды из файла, "
              "потом SELECT — по порядку.",
    "half_7": "chmod +x — право на запуск; ~/путь — запуск по пути. Чужой скрипт сначала "
              "читают: head.",
}


def explain(item_id: str) -> Optional[str]:
    st = stem(item_id)
    if st is None:
        return None
    return EXPLAIN[st if st.startswith("half_") else st[-2:]]


def how_to_open(item_id: str) -> Optional[str]:
    st, path = stem(item_id), drop_path(item_id)
    if st is None:
        return None
    key = st if st.startswith("half_") else st[-2:]
    return HOW[key].format(path=path, drop=DROP, stem=st)


def _ui6(key: str, default: str) -> str:
    return theme.story("dossier_ui").get(key) or default


OPEN_STEPS = ("Как прочитать: 1) зайди в любое задание (run или train, кроме стража); "
              "2) набери там {how}; 3) текст появится на экране и сохранится здесь. {explain} "
              "Через open не открывай: Mac отдаст файл своей программе «Архиватор», а читать "
              "нужно прямо в терминале.")


def where_line(item_id: str) -> str:
    """Куплено, но ещё не открыто: где лежит и чем открыть — по шагам (владелец 21.10:
    «досье открывается архиватором… непонятно, как его запустить»)."""
    how, path = how_to_open(item_id), drop_path(item_id)
    how = how.split(" (или ")[0]        # одна команда: запасной вариант новичка путает
    return f"куплено, лежит в ~/{path}. " + OPEN_STEPS.format(how=how,
                                                              explain=explain(item_id) or "")


def bought_lines(item_id: str) -> List[str]:
    """Строки после покупки сюжетной позиции: где лежит и чем открыть."""
    if not theme.story("dossiers"):
        return []
    if item_id[:-1] in theme.story("dossiers") and item_id.endswith("1"):
        return [_ui6("page1", "Читать: ./termit dossier {who}").format(who=item_id[:-1])]
    if stem(item_id) is None:
        return []
    return [_ui6("bought", "Лежит в ~/{path}. В любом ране (кроме стража): {how}").format(
        path=drop_path(item_id), how=how_to_open(item_id)), explain(item_id)]


def _who_key(arg: str) -> Optional[str]:
    a = textnorm.norm(arg).casefold().replace("ё", "е")
    dossiers = theme.story("dossiers")
    for who in _who_list():
        if a in (who, str(dossiers[who].get("name", "")).casefold().replace("ё", "е")):
            return who
    return None


def dossier_count(p: dict) -> Tuple[int, int]:
    whos = _who_list()
    have = sum(1 for w in whos for k in range(1, DOSSIER_PAGES + 1) if f"{w}{k}" in p["owned"])
    return have, len(whos) * DOSSIER_PAGES


def dossier_lines(p: dict, who: Optional[str] = None) -> List[str]:
    """./termit dossier [ИМЯ]: список персонажей или страницы одного."""
    dossiers = theme.story("dossiers")
    if not dossiers:
        return [NO_CASE]
    if who is None:
        have, total = dossier_count(p)
        out = [_ui6("title", "Досье: {n}/{total}").format(n=have, total=total), ""]
        for w in _who_list():
            d = dossiers[w]
            marks = " ".join(("✓" if f"{w}{k}" in p["owned"] else "·")
                             for k in range(1, DOSSIER_PAGES + 1))
            out.append(f"  {d.get('name', w):10} {marks}   ./termit dossier {w}")
        return out
    key = _who_key(who)
    if key is None:
        return [f"Нет такого досье: {who}. Есть: " + ", ".join(_who_list())]
    d = dossiers[key]
    out = [f"🗂 {d.get('name', key)}", ""]
    for k in range(1, DOSSIER_PAGES + 1):
        iid, text = f"{key}{k}", _page_text(key, k)
        out.append(f"Стр. {k}")
        if iid not in p["owned"] or not text:
            out.append(_fill(_ui6("locked", "не куплено — ./termit shop"), "  ", "  "))
        elif k == 1 or stem(iid) in p["opened"]:
            out.append(_fill(" ".join(text), "  ", "  "))      # строки файла — абзацем
        else:
            out.append(_fill(where_line(iid), "  ", "  "))
        out.append("")
    return out[:-1]


def _fragment_case_lines(p: dict) -> List[str]:
    """Доска дела: «Половина отдана» (выкупленные фрагменты) и счёт досье."""
    out = []
    frags = [k for k in sorted(theme.story("fragments")) if f"half{k}" in p["owned"]]
    if frags:
        out += ["", _ui6("half_title", "Половина отдана")]
        for k in frags:
            t, iid = _fragment(k), f"half{k}"
            out.append(f"  🩸 {t.get('title', k)}")
            if stem(iid) in p["opened"]:
                out.append(_fill(" ".join(t["text"]), "     ", "     "))
            else:
                out.append(_fill(where_line(iid), "     ", "     "))
    if theme.story("dossiers"):
        have, total = dossier_count(p)
        out += ["", _ui6("case", "Досье: {n}/{total}").format(n=have, total=total)
                + "  ./termit dossier"]
    return out


def _home_case_lines(p: dict) -> List[str]:
    """Доска дела: выкупленные вещи (убежище) и ключ — строка вместо отложенной сцены."""
    from termit_app import shop
    home = theme.story("home")
    have = [i for i in shop.SHNYR_ITEMS if i in p.get("owned", ())]
    if not have or not home.get("case"):
        return []
    out = ["", home["case"].format(n=len(have), total=len(shop.SHNYR_ITEMS))]
    if "key" in have and home.get("case_key"):
        out.append(_fill(home["case_key"], "  ", "  "))
    return out


# --- Раскладка находок по видам -----------------------------------------------------------

LOG_END = "--- end of log ---"
_NOISE = ("sync ok", "cache hit", "heartbeat", "queue empty", "retry 1/3 ok", "gc done",
          "session closed", "token refreshed", "disk check ok", "backup skipped")


def _climb_top(state: Optional[dict]) -> str:
    """Верхняя папка, куда ведёт вариант climb_down: путь к записке или папка из readme."""
    state = state or {}
    top = str(state.get("path") or state.get("target") or "").split("/")[0]
    return top or "old_projects_backup_2719"


def _back_up_place(state: Optional[dict], dot: str) -> Tuple[str, str]:
    """back_up: в папке, где вариант заканчивается (archive, archive/other или дом)."""
    target = str((state or {}).get("target") or "archive")
    if target == ".termit/home":
        return "home", dot
    return "box", f"{target}/{dot}"


def _hidden_place(host: str, name: str, state: Optional[dict] = None) -> Tuple[str, str]:
    """Скрытый файл: находится ls -a там, куда задача и так приводит (в любом варианте)."""
    dot = name if name.startswith(".") else "." + name
    return {"hidden_cache": ("box", dot),
            "climb_down": ("box", f"{_climb_top(state)}/{dot}"),
            "back_up": _back_up_place(state, dot),
            "home_tilde": ("home", dot)}[host]


def _deep_place(host: str, name: str, rng: random.Random) -> Tuple[str, str]:
    """Файл *.mem на глубине 3+: находится find . -name '*.mem'."""
    a, b, c = (f"{kit.latin(rng)}_{rng.randint(10, 99)}" for _ in range(3))
    top = "storage" if host == "find_name" else "old_sync"
    stem = name[:-4] if name.endswith(".mem") else name
    return "box", f"{top}/{a}/{b}/{c}/{stem}.mem"


def log_tail_body(lines: List[str], rng: random.Random) -> str:
    """Длинный журнал: 400–800 строк шума, строка конца лога и сама находка в хвосте
    (tail или less + G)."""
    n = rng.randint(400, 800)
    noise = [f"{h:02d}:{m:02d}:{s:02d} {rng.choice(_NOISE)}"
             for h, m, s in sorted((rng.randrange(24), rng.randrange(60), rng.randrange(60))
                                   for _ in range(n))]
    return "\n".join(noise + [LOG_END, ""] + list(lines)) + "\n"


OLD_LOGS = "old_logs"
NOL_MARK = "NOL: "
NOL_EDGE = 100              # строка находки не ближе к краям лога, чем столько строк


def nol_log_body(lines: List[str], year: int, rng: random.Random) -> str:
    """Старый лог биржи: 1500–3000 строк шума с датой и одна строка «NOL: …» (непустые
    строки находки через « · ») в случайном месте, не у краёв: head/tail её не покажут,
    найдёт grep NOL."""
    n = rng.randint(1500, 3000)
    stamps = sorted((rng.randint(1, 12), rng.randint(1, 28), rng.randrange(24),
                     rng.randrange(60), rng.randrange(60)) for _ in range(n))
    noise = [f"{year}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d} {rng.choice(_NOISE)}"
             for mo, d, h, mi, s in stamps]
    at = rng.randint(NOL_EDGE, n - NOL_EDGE)
    noise.insert(at, NOL_MARK + " · ".join(x for x in lines if x.strip()))
    return "\n".join(noise) + "\n"


ARCHIVE = "archive"
_NOTE_NOISE = ("form 7-N filed", "stamp renewed", "card moved", "duplicate removed",
               "photo replaced", "address checked", "signature ok", "queue closed")


def _notes_db(rows: List[tuple]) -> bytes:
    from termit_app.tasks import dbkit
    schema = ("CREATE TABLE notes (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, body TEXT NOT NULL)",)
    return dbkit.build_sqlite(schema, {"notes": (("id", "ts", "body"), rows)})


def notes_db(lines: List[str], year: int, rng: random.Random) -> bytes:
    """Старая база картотеки: таблица notes, 300–600 строк шума и одна «NOL: …» (непустые
    строки находки через « · ») в случайном месте — найдёт SELECT … WHERE body LIKE 'NOL:%'."""
    n = rng.randint(300, 600)
    stamps = sorted((rng.randint(1, 12), rng.randint(1, 28), rng.randrange(24),
                     rng.randrange(60)) for _ in range(n + 1))
    bodies = [rng.choice(_NOTE_NOISE) for _ in range(n)]
    bodies.insert(rng.randint(NOL_EDGE // 2, n - NOL_EDGE // 2),
                  NOL_MARK + " · ".join(x for x in lines if x.strip()))
    rows = [(i, f"{year}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}", body)
            for i, ((mo, d, h, mi), body) in enumerate(zip(stamps, bodies), start=1)]
    return _notes_db(rows)


def lines_db(lines: List[str]) -> bytes:
    """Фрагмент базой: таблица lines (id, body) — по строке файла на запись."""
    from termit_app.tasks import dbkit
    schema = ("CREATE TABLE lines (id INTEGER PRIMARY KEY, body TEXT NOT NULL)",)
    return dbkit.build_sqlite(schema, {"lines": (("id", "body"),
                                                 [(i, x) for i, x in enumerate(lines, 1)])})


def lines_sql(lines: List[str]) -> str:
    """Фрагмент файлом команд SQL: CREATE TABLE lines и по INSERT на строку (кавычки внутри
    — удвоены). Строки текста уже по ширине (_file_lines): их печатает SELECT."""
    out = ["CREATE TABLE lines (id INTEGER PRIMARY KEY, body TEXT NOT NULL);"]
    for i, x in enumerate(lines, 1):
        out.append(f"INSERT INTO lines VALUES ({i}, '" + x.replace("'", "''") + "');")
    return "\n".join(out) + "\n"


def lines_sh(lines: List[str]) -> str:
    """Фрагмент скриптом: #!/bin/sh и printf по строке в одинарных кавычках (кавычка внутри —
    '\\''). Ничего, кроме печати, не делает."""
    out = ["#!/bin/sh", "# prints text, nothing else"]
    for x in lines:
        out.append("printf '%s\\n' '" + x.replace("'", "'\\''") + "'")
    return "\n".join(out) + "\n"


SCRIPT_DIR = "downloads"
_SCRIPT_NOISE = ('echo "check: ok"', "# TODO: remove debug output", 'n=$(ls | wc -l)',
                 'echo "files: $n"', "# old way, do not touch", "sleep 0",
                 'echo "done"', "# author: unknown", 'date +%H:%M')


def script_line_body(lines: List[str], rng: random.Random, name: str = "old") -> str:
    """Старый скрипт: та же шапка и охрана, что у скриптов downloads/ (envkit), 12–20 строк
    безобидного шума и одна строка-комментарий «# NOL: …» (непустые строки находки через
    « · ») не в первых десяти: head её не покажет, найдёт grep -n NOL."""
    from termit_app.tasks import envkit
    head = ["#!/bin/sh", "# old script: checks the folder and prints a report",
            f"# Usage: ./{name}.sh",
            envkit.HONEST_NOTE] + list(envkit._GUARD)
    body = [rng.choice(_SCRIPT_NOISE) for _ in range(rng.randint(12, 20))]
    body.insert(rng.randint(3, len(body) - 2), "# " + NOL_MARK + " · ".join(
        x for x in lines if x.strip()))
    return "\n".join(head + body) + "\n"


def place(kind: str, host: str, name: str, lines: List[str], seed: int,
          state: Optional[dict] = None) -> list:
    """Extras одной находки вида kind в задаче host; lines — строки файла, state — данные
    рана (куда ведёт вариант)."""
    rng = random.Random(seed ^ 0x0A5C)
    if kind == "hidden":
        root, path = _hidden_place(host, name, state)
        return [extra(root, path, "\n".join(lines) + "\n")]
    if kind == "log_tail":
        return [extra("box", "journal.log", log_tail_body(lines, rng))]
    if kind == "deep_mem":
        root, path = _deep_place(host, name, rng)
        return [extra(root, path, "\n".join(lines) + "\n")]
    if kind == "nol_line":
        year = rng.randint(2719, 2724)
        return [extra("home", f"{OLD_LOGS}/{name}_{year}.log", nol_log_body(lines, year, rng))]
    if kind == "db_row":
        year = rng.randint(2718, 2724)
        return [extra("home", f"{ARCHIVE}/{name}_{year}.db", notes_db(lines, year, rng))]
    if kind == "script_line":
        return [extra("box", f"{SCRIPT_DIR}/{name}.sh", script_line_body(lines, rng, name),
                      mode=0o644)]
    raise KeyError(kind)


# --- Образцы для проверки хозяев (tests/test_extras_hosts.py) -----------------------------

def _gz(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"), mtime=0)


def _tgz(files: Dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, text in files.items():
            raw = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            tf.addfile(info, io.BytesIO(raw))
    return buf.getvalue()


_PLACEHOLDER = {   # заглушки досье и фрагментов: хозяев проверяем раскладкой, не сюжетом
    "dossiers": {w: {"name": w, "pages": [["p. 1"], ["p. 2"], ["p. 3"]]}
                 for w in ("x", "y", "z")},
    "fragments": {k: {"title": f"fragment {k}", "text": [f"half {k}"]}
                  for k in (1, 2, 3, 4, 5, 6, 7)},
}


def sample_extras(kind: str, host: str, seed: int) -> list:
    """Максимальный набор файлов вида kind для задачи host — заглушки-тексты: проверяем
    раскладку, а не сюжет."""
    lines = ["RECORD · check", "line one", "line two", "code: CHECK"]
    if kind in ("hidden", "log_tail", "deep_mem", "nol_line", "db_row", "script_line"):
        return place(kind, host, "record", lines, seed)
    if kind == "drop":     # настоящая раскладка ~/drop: все страницы и фрагменты куплены
        p = {"owned": ["x2", "x3", "y2", "y3", "z2", "z3", "half1", "half2", "half3",
                       "half4", "half5", "half6", "half7"]}
        return drop_extras(p, src=lambda section: _PLACEHOLDER.get(section) or {})
    if kind == "found":       # оба найденных скрипта сразу: «грязный» и полезный (E20)
        from termit_app.tasks import envkit
        return (found_extras({"kind": "dirty", "name": envkit.DIRTY_NAMES[0], "tip": None},
                             seed) +
                found_extras({"kind": "useful", "name": sorted(envkit.USEFUL)[0],
                              "tip": FOUND_TIP}, seed))
    if kind in ("noise_home", "noise_box"):     # «шум» (FB5 п. 70) — как в игре
        from termit_app import noise
        return noise.home(seed) if kind == "noise_home" else noise.box(seed)
    if kind == "paydata":     # настоящая раскладка хабара (E17)
        from termit_app import loot
        return loot.extras(loot.plan(seed))
    raise KeyError(kind)


# --- Таблицы базы стража (слой 4, шаг 2) -------------------------------------------------

def vault_tables(task_id: str) -> List[dict]:
    """Сюжетные таблицы базы стража task_id из темы: {"name", "cols", "sqlite", "pg",
    "rows"}. Нет раздела — пусто: в чужой теме таблицы нет. Строки статичны — зерно и данные
    варианта от темы не зависят."""
    return list((theme.story("vault_tables") or {}).get(task_id) or ())


# --- Внутренние голоса (E13) ---------------------------------------------------------------

VOICE_CHANCE = 0.4          # на задачу; не больше одного голоса за ран и не в первом ране
VOICE_OUTCOMES = ("solved", "giveup")


def recap_key(p: dict) -> Optional[str]:
    """Веха «Ранее…»: последний взломанный страж, у которого есть запись; до стражей — дальний
    решённый шаг первого трека; иначе start. Нет раздела в теме (фэнтези) — None."""
    beats = theme.story("recap").get("beats") or {}
    if not beats:
        return None
    key = next((b for b in reversed(p.get("bosses") or []) if b in beats), None)
    if key is None:
        from termit_app.tasks import registry   # здесь: реестр грузит модули задач
        tasks = p.get("tasks") or {}
        steps = [t.id for t in registry.tasks_of("basics")
                 if t.id in beats and (tasks.get(t.id) or {}).get("solved")]
        key = steps[-1] if steps else "start"
    return key


def recap_lines(p: dict) -> List[str]:
    """«Ранее…» при входе в игру (FB3): заголовок и строки вехи (recap_key). Нет раздела в
    теме (фэнтези) — пусто: сюжетных вех там нет."""
    recap = theme.story("recap")
    key = recap_key(p)
    lines = ((recap.get("beats") or {}).get(key) or []) if key else []
    return [recap.get("title", "")] + list(lines) if lines else []


# FB12 (S10): «Ранее…» слово в слово каждый день глаз учится пропускать — полное «Ранее…»
# только при новой вехе или после перерыва в столько дней без игры
RECAP_BREAK_DAYS = 3


def recap_due(p: dict, today: date) -> bool:
    """Показывать ли «Ранее…» сегодня: веха сменилась с прошлого показа или игрок не играл
    RECAP_BREAK_DAYS дней и больше. За день — не больше одного раза."""
    key = recap_key(p)
    if key is None or p.get("recap_day") == today.isoformat():
        return False
    if p.get("recap_seen") != key:
        return True
    played = [d for d in p.get("days") or () if isinstance(d, str) and d < today.isoformat()]
    if not played:
        return False
    try:
        gap = (today - date.fromisoformat(max(played))).days
    except ValueError:
        return False
    return gap >= RECAP_BREAK_DAYS


def recap_mark(p: dict, today: date) -> None:
    """«Ранее…» показано: запомнить веху и день."""
    p["recap_seen"] = recap_key(p)
    p["recap_day"] = today.isoformat()


def voice_name(track: str) -> Optional[str]:
    """Чей голос звучит в этом треке; None — у темы голосов нет."""
    return (theme.story("voices").get("names") or {}).get(track)


def voice(task, outcome, seed: int, p: dict, used: bool, fresh: bool = True) -> Optional[str]:
    """Редкая строка внутреннего голоса после разбора: приём или риск, никогда не оценка.
    Строки задачи — только при первой встрече или новом варианте (fresh), общие строки трека —
    у задач без своих (у задачи со своим пулом пул трека не звучит, библия §3). Каждая строка
    — один раз за игру (remarks); сказать нечего — тишина."""
    v = theme.story("voices")
    if (not v or task.boss or outcome not in VOICE_OUTCOMES or used or p.get("dozors", 0) <= 0
            or not voice_name(task.track)):
        return None
    rng = random.Random(seed ^ 0xC0FFEE)
    if rng.random() >= VOICE_CHANCE:
        return None
    own = (v.get("tasks") or {}).get(task.id)
    if own:
        return remarks.pick(p, f"voice.{task.id}", own, seed) if fresh else None
    return remarks.pick(p, f"voice.{task.track}", (v.get("tracks") or {}).get(task.track),
                        seed)
