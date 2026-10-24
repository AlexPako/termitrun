"""Старт zsh поручения: python3 -m termit_app.launch BOX COMMAND...

Запускается родителем уже под sandbox-exec. Сначала поднимает процессы поручения, которые
setup отложил в .termit/spawn.json, — так они живут в ТОЙ ЖЕ песочнице, что и zsh: не могут
из неё выйти (А1 отчёта 07), а игрок может их остановить, хотя сигналы чужим процессам
запрещены (А3). Потом подставляет настоящие PID в task.json и заменяет себя командой (zsh -i)."""
import json
import os
import sys
from pathlib import Path

from termit_app import sandbox
from termit_app.tasks import kit


def start_deferred(box: Path) -> None:
    q = kit._queue(box)
    if not q.exists():
        return
    try:
        items = json.loads(q.read_text("utf-8") or "[]")
    finally:
        q.unlink()
    mapping = {}
    for it in items:
        mapping[int(it["token"])] = kit.spawn_now(box, str(it["cmd"]))
    if mapping:
        data = sandbox.read_task_json(box)
        state = kit.replace_tokens(data["state"], mapping)
        sandbox.write_task_json(box, data["id"], state, hidden=bool(data.get("hidden")))
        tell_judge(box, state)


def tell_judge(box: Path, state) -> None:
    """PID процессов — судье родителя (P2 fix1 M1): он сверит их с песочницей и очередью, и
    повторная проверка возьмёт PID у него, а не из task.json. Судьи нет — молча."""
    from termit_app import judge
    try:
        judge.ask(box, {"op": "pids", "state": state})
    except Exception:       # noqa: BLE001 — zsh должен стартовать в любом случае
        pass


def main(argv) -> int:
    box, cmd = Path(argv[0]), argv[1:]
    os.environ["TERMIT_LAUNCHED"] = "1"     # reset внутри zsh запускает процессы сразу
    try:
        start_deferred(box)
    except Exception as e:                  # zsh должен стартовать в любом случае
        print(f"[тренажёр] не удалось запустить процессы задачи: {e!r}", file=sys.stderr)
    (box / ".termit" / "tmp").mkdir(parents=True, exist_ok=True)
    os.execvp(cmd[0], cmd)
    return 127


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
