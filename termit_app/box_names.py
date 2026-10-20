"""Имена папок песочниц (FB3, 9): по заданию, английскими словами, понятными любому человеку.

Игрок видит имя в pwd и в приглашении — вместо box-3f9a1c2e там теперь, например,
copy-move-3f2a. Имя — по теме задания, а не по приёму решения: оно не подсказывает больше,
чем карточка (стражи — нейтральное exam-<трек>). Хвост из 4 шестнадцатеричных знаков — чтобы
папка каждый раз была новой (профиль sandbox-exec привязан к пути, В1 приёмки-1).

Длина имени ограничена: путь сокета учебного сервера внутри песочницы обязан влезть в sun_path
(104 байта), поэтому тема — не длиннее TOPIC_MAX, а sandbox.sample_box меряет по NAME_MAX.
"""
import re

TOPIC_MAX = 12
SUFFIX_LEN = 4
NAME_MAX = TOPIC_MAX + 1 + SUFFIX_LEN

# Задача без записи — тема из id (подчёркивания — дефисы, не длиннее TOPIC_MAX).
TOPICS = {
    # Основы
    "meet_terminal": "terminal",
    "where_am_i": "where-am-i",
    "climb_down": "climb-down",
    "back_up": "go-back",
    "home_tilde": "home-note",
    "hidden_cache": "secret-note",
    "mkdir_p": "nested-dirs",
    "copy_move": "copy-move",
    "star_mask": "masks",
    "question_mask": "numbered",
    "run_script": "run-script",
    "deep_dig": "deep-search",
    "deep_rm": "deep-delete",
    "line_edit": "edit-line",
    "history_recall": "history",
    "screen_scroll": "scroll-back",
    "screen_find": "screen-find",
    "quick_fix": "quick-fix",
    "fzf_pick": "three-scraps",
    "z_jump": "jump-back",
    # Инструменты
    "man_flag": "manual",
    "less_search": "flight-log",
    "nano_config": "edit-config",
    "vim_trap": "vim-trap",
    "vim_escape": "vim-exit",
    "vim_purge": "weed-lines",
    "job_control": "bg-jobs",
    "brew_lesson": "supply-store",
    "tldr_tar": "archive",
    "json_check": "bad-config",
    "bat_lines": "find-line",
    # Вместо Finder
    "open_gui": "open-window",
    "find_name": "lost-file",
    "grep_r": "needle",
    "du_heavy": "disk-space",
    "ls_newest": "newest",
    "recent_move": "by-date",
    "batch_rename": "rename",
    "zip_pack": "parcel",
    "pbcopy_list": "clipboard",
    "kill_frozen": "frozen",
    "top_hog": "cpu-hog",
    "disk_sweep": "big-cleanup",
    "dup_sort": "duplicates",
    "rg_hunt": "code-search",
    "fd_hunt": "file-census",
    "csv_by_hand": "csv-by-hand",
    "csv_top": "csv-top",
    "csv_sum": "csv-sum",
    # Данные
    "head_tail": "first-look",
    "grep_count": "log-count",
    "pipe_count": "tag-count",
    "redirect_report": "report-file",
    "cut_uniq": "column",
    "top_values": "hit-parade",
    "awk_sum": "cash-sum",
    "log_period": "crash-time",
    "join_parts": "join-parts",
    "stderr_split": "two-streams",
    "tee_log": "call-log",
    "sed_fix": "text-fix",
    "jq_field": "json-field",
    "jq_deep": "nested-json",
    "curl_api": "direct-line",
    # Базы данных
    "sqlite_open": "first-db",
    "select_where": "namesakes",
    "order_limit": "top-rows",
    "distinct_like": "by-pattern",
    "in_between": "from-to",
    "null_coalesce": "empty-cells",
    "group_count": "summary",
    "group_having": "group-filter",
    "join_inner": "join-cases",
    "join_left": "missing-ones",
    "sql_pipe": "sql-report",
    "import_csv": "import-csv",
    "create_insert": "own-table",
    "backup_update": "safe-update",
    "tx_delete": "safe-delete",
    "csv_sql": "csv-query",
    # SQL и PostgreSQL
    "psql_nav": "pg-entry",
    "psql_pipe": "pg-export",
    "pg_dialect": "pg-dialect",
    "pg_identity": "pg-ids",
    "case_when": "buckets",
    "subquery": "subquery",
    "cte_with": "named-totals",
    "window_rank": "ranking",
    "window_lag": "month-check",
    "joins_more": "both-sides",
    "constraints_fk": "table-rules",
    "upsert": "upsert",
    "view_index": "saved-query",
    "jsonb_query": "json-fields",
    "copy_dump": "dump-files",
    # Окружение и скрипты
    "env_vars": "env-vars",
    "export_child": "inherit",
    "perm_basics": "who-am-i",
    "perm_rwx": "no-access",
    "read_long_list": "long-list",
    "perm_digits": "permissions",
    "dotenv": "dotenv",
    "path_which": "path",
    "shebang_run": "launch",
    "exit_codes": "exit-codes",
    "json_config": "json-config",
    "script_audit": "script-check",
    "av_scan": "virus-scan",
    "venv_basics": "own-room",
    "pip_offline": "offline-pip",
    "pip_freeze": "pkg-list",
    # Python
    "py_run": "py-first",
    "py_vars": "py-prices",
    "py_loop": "py-counting",
    "py_dict": "py-labels",
    "py_func": "py-module",
    "py_repl": "py-explore",
    "py_json": "py-invoices",
    "py_csv_json": "py-tables",
    "py_files": "py-stock",
    "py_stats": "py-summary",
    "py_urllib": "py-server",
    # Аналитика
    "pd_install": "pd-install",
    "pd_read": "pd-first",
    "pd_filter": "pd-filter",
    "pd_groupby": "pd-leaders",
    "pd_missing": "pd-gaps",
}

_TOPIC = re.compile(r"^[a-z][a-z0-9-]*$")


def topic(task) -> str:
    """Тема папки песочницы задачи: из словаря, у стража — exam-<трек>, иначе — из id."""
    if task is None:
        return "task"
    tid = str(getattr(task, "id", "") or "")
    if tid in TOPICS:
        return TOPICS[tid]
    if getattr(task, "boss", False):
        raw = "exam-" + str(getattr(task, "track", "") or "")
    else:
        raw = tid
    raw = re.sub(r"[^a-z0-9]+", "-", raw.lower())[:TOPIC_MAX].strip("-")
    return raw if _TOPIC.match(raw) else "task"
