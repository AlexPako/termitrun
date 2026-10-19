"""Повторная проверка открытой задачи (P2 fix1 I1). Запуск — только так (session._recheck_child):
python3 -I -c "…sys.path.insert(0, ROOT)…" ROOT BOX, cwd — корень игры: ни песочница, ни cwd в
sys.path не попадают, код грузится только из ROOT и интерпретатора (P2 fix2 C1).

Запускает родитель после выхода из zsh — под sandbox-exec (shell_run.recheck_profile: запись
запрещена, чтение данных — только песочница и системное) и с таймаутом. На вход (stdin) —
JSON {"task": id, "state": состояние родителя}; на выход — одна строка MARK + "1" или "0".
Всё остальное (исключение, мусор, тишина) родитель считает «не подтверждено»."""
import json
import sys
from pathlib import Path

MARK = "TERMIT-RECHECK:"


def main(argv) -> int:
    ok = False
    try:
        from termit_app import sandbox
        from termit_app.tasks import registry
        req = json.loads(sys.stdin.read(4 * 1024 * 1024))
        task = registry.get(str(req["task"]))
        state = req["state"]
        if isinstance(state, dict):
            ok = bool(task.check(sandbox.make_ctx(Path(argv[0]), state)).solved)
    except BaseException:       # noqa: BLE001 — любая поломка — «не подтверждено»
        ok = False
    sys.stdout.write(MARK + ("1" if ok else "0") + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
