"""Пулы реплик персонажей «Сан-Франциско» (FB12-voices, FB5 п. 44 и 46): точная фраза не
звучит дважды за всю игру (termit_app/remarks.py), поэтому пулы большие и живут отдельно от
__init__.py.

Файл — один пул: <трек>_<вид>.py со словарём LINES = {мысль: [строки]}.
- вид реакции после разбора: solved, hard, slow, record, giveup;
- мысль — о чём реплика (похвала, город, байка, воспоминание, совет, ирония…): подряд одна
  мысль у персонажа не идёт, поэтому мыслей в пуле много и разных;
- строка с полями {…} — шаблон, поля описаны в remarks.context ({prog}, {za_time},
  {by_gain}, {streak}, {left}, {daypart}, {night}). Шаблон пишется так, чтобы падеж подстановки
  был верным: «{za_time}» — это «за 12 секунд», «{by_gain}» — «на 7 секунд» (предлог уже
  внутри: «быстрее {by_gain}», а не «срезал {by_gain}»). {daypart} — любое время суток, фраза
  должна быть верна и утром, и ночью; ночные фразы — с {night} (есть только ночью).

Голоса персонажей и ругань (библия §5, FB5 п. 31): Ворон — «дерьмо», «чёрт», редко и тяжело;
Гайка — «сука», «охренел» (злость на железо); Шнырь — «хрен», «блин», «сдохнешь», никогда не
«сука»; Фрося — «зараза», «чтоб тебя»; Марина, Пломба, Дубров, Соня — не ругаются вовсе.

Сливается в THEME в конце __init__.py: reactions[трек][вид] — плоский список (как раньше),
thoughts[строка] — мысль строки."""
import importlib
import pkgutil
from typing import Dict, List

KINDS = ("solved", "hard", "slow", "record", "giveup")


def _modules() -> Dict[str, object]:
    out = {}
    for info in pkgutil.iter_modules(__path__):
        out[info.name] = importlib.import_module(f"{__name__}.{info.name}")
    return out


def pool(name: str) -> Dict[str, List[str]]:
    """Словарь мыслей пула name (имя файла без .py); нет файла — пусто."""
    mod = _modules().get(name)
    return dict(getattr(mod, "LINES", {}) or {}) if mod else {}


def flat(lines: Dict[str, List[str]]) -> List[str]:
    return [x for xs in lines.values() for x in xs]


def merge(theme: dict) -> None:
    """Пулы реакций — в theme["reactions"], мысли строк — в theme["thoughts"]; пулы зацепок
    и голосов — в свои разделы (tomorrow_<трек>, voice_<трек>, master_<вид>)."""
    thoughts = theme.setdefault("thoughts", {})
    for name, mod in sorted(_modules().items()):
        lines = getattr(mod, "LINES", None) or {}
        for thought, xs in lines.items():
            for x in xs:
                thoughts[x] = thought
        head, _, kind = name.rpartition("_")
        if kind in KINDS and head:
            theme.setdefault("reactions", {}).setdefault(head, {})[kind] = flat(lines)
        elif head == "tomorrow":
            theme.setdefault("tomorrow", {}).setdefault("tracks", {})[kind] = flat(lines)
        elif head == "voice":
            voices = theme.setdefault("voices", {})
            voices.setdefault("tracks", {})[kind] = flat(lines)
        elif head == "master":
            theme.setdefault("master", {})[kind] = flat(lines)
