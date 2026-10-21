"""datapeek: a quick look at a CSV file: columns, row count, most common values.

    $ datapeek sales.csv
    $ python3 -m datapeek sales.csv --top 2

Prints the table with tabprint (a dependency: pip installs it too). In code:

    >>> import datapeek
    >>> datapeek.summary("sales.csv")["rows"]
    12"""
from collections import Counter

import tabprint

__version__ = "0.2.0"
__all__ = ["summary", "report", "__version__"]


def summary(path, top=3) -> dict:
    """CSV summary: {"file", "rows", "columns": [{"name", "filled", "unique", "top"}]}.

    top is how many common values per column: a list of (value, count) pairs, most common
    first, ties in alphabetical order. Empty cells are not counted as values."""
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
    """Text summary: a line "file: N rows, M columns" and a table of columns."""
    s = summary(path, top)
    head = f"{s['file']}: {s['rows']} rows, {len(s['columns'])} columns"
    grid = [["column", "filled", "unique", "top"]]
    for c in s["columns"]:
        grid.append([c["name"], c["filled"], c["unique"],
                     ", ".join(f"{v} ({n})" for v, n in c["top"])])
    return head + "\n" + tabprint.table(grid)
