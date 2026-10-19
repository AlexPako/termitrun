"""datapeek — быстрый взгляд на CSV: колонки, число строк, частые значения.

    $ datapeek sales.csv
    $ python3 -m datapeek sales.csv --top 2

Печатает таблицу через tabprint (зависимость пакета: pip ставит её сам). В коде:

    >>> import datapeek
    >>> datapeek.summary("sales.csv")["rows"]
    12"""
from collections import Counter

import tabprint

__version__ = "0.2.0"
__all__ = ["summary", "report", "__version__"]


def summary(path, top=3) -> dict:
    """Сводка CSV: {"file", "rows", "columns": [{"name", "filled", "unique", "top"}]}.

    top — сколько частых значений на колонку: список пар (значение, сколько раз), по
    убыванию, при равенстве — по алфавиту. Пустые клетки в частые не идут."""
    rows = tabprint.from_csv(path)
    names = list(rows[0]) if rows else []
    if not rows:
        import csv
        with open(path, newline="", encoding="utf-8") as f:
            names = next(csv.reader(f), [])
    cols = []
    for name in names:
        values = [(r.get(name) or "").strip() for r in rows]
        filled = [v for v in values if v]
        counts = Counter(filled)
        best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
        cols.append({"name": name, "filled": len(filled), "unique": len(counts),
                     "top": best})
    return {"file": str(path), "rows": len(rows), "columns": cols}


def report(path, top=3) -> str:
    """Сводка текстом: строка «файл: N rows, M columns» и таблица колонок."""
    s = summary(path, top)
    head = f"{s['file']}: {s['rows']} rows, {len(s['columns'])} columns"
    grid = [["column", "filled", "unique", "top"]]
    for c in s["columns"]:
        grid.append([c["name"], c["filled"], c["unique"],
                     ", ".join(f"{v} ({n})" for v, n in c["top"])])
    return head + "\n" + tabprint.table(grid)
