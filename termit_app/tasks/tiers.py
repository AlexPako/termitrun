"""Ступени повтора (Р1, владелец 23.10): 0 — базовая, 1 — с подвохом (пробел в имени, скрытое,
ловушка, приём со значением), 2 — связка с прошлым приёмом. Ступень варианта — по номеру
варианта задачи; задачи нет в таблице — ступень из Variant.tier (по умолчанию 0)."""
from typing import List

TIERS = {
    # «Основы»
    "where_am_i": (0, 0, 1), "climb_down": (0, 1, 1), "back_up": (0, 1, 0),
    "home_tilde": (0, 1, 1), "hidden_cache": (0, 1, 1), "quotes": (0, 0, 1),
    "line_edit": (0, 1, 1), "cut_paste": (0, 1, 1), "history_recall": (0, 2, 1),
    "mkdir_p": (0, 1, 1), "copy_move": (0, 1, 1), "file_ext": (0, 1, 1), "star_mask": (0, 1, 0),
    "question_mask": (0, 0, 1), "run_script": (0, 1, 1), "deep_dig": (0, 1, 1),
    "deep_rm": (0, 2, 0), "screen_scroll": (0, 1, 0), "screen_find": (0, 1, 0),
    "quick_fix": (0, 1, 1), "cp_dir": (0, 1, 1), "fzf_pick": (0, 1, 1), "z_jump": (0, 1, 1),
    # «Инструменты»
    "man_flag": (0, 0, 1), "flag_use": (0, 1, 0), "less_search": (0, 1, 1),
    "nano_config": (0, 1, 1), "vim_trap": (0, 1, 0), "vim_escape": (0, 1, 0),
    "vim_purge": (0, 1, 1), "job_control": (0, 0, 1), "brew_lesson": (0, 0, 1),
    "tldr_tar": (0, 1, 0), "json_check": (0, 1, 2), "bat_lines": (0, 0, 1),
    # «Вместо Finder»
    "open_gui": (0, 0, 1), "find_name": (0, 1, 1), "grep_r": (0, 1, 2), "du_heavy": (0, 0, 1),
    "ls_newest": (0, 0, 1), "recent_move": (0, 1, 1), "batch_rename": (0, 1, 1),
    "zip_pack": (0, 1, 1), "pbcopy_list": (0, 0, 1), "kill_frozen": (0, 1, 1),
    "top_hog": (0, 1, 1), "disk_sweep": (0, 2, 1), "dup_sort": (0, 2, 1), "rg_hunt": (0, 1, 2),
    "fd_hunt": (0, 1, 2), "csv_by_hand": (0, 0, 1), "csv_top": (0, 1, 2), "csv_sum": (0, 2, 1),
}


def of(task) -> List[int]:
    """Ступень каждого варианта задачи; таблица неполная — недостающие из Variant.tier."""
    own = [getattr(v, "tier", 0) for v in task.variants]
    table = TIERS.get(task.id, ())
    return [table[i] if i < len(table) else t for i, t in enumerate(own)]
