"""tabprint: print tables in the terminal.

    >>> import tabprint
    >>> print(tabprint.table([["city", "n"], ["Oakland", 3]]))
    city     n
    Oakland  3

Rows are lists (the first row is the header) or dicts (the header is the keys of the first
dict, or cols). Numbers are aligned right, text left. No dependencies, Python 3.9+ only."""
import csv

__version__ = "1.0.0"
__all__ = ["table", "show", "from_csv", "__version__"]


def _cell(value) -> str:
    return "" if value is None else str(value)


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _grid(rows, cols=None):
    """Table header and rows as lists of strings."""
    rows = list(rows)
    if rows and isinstance(rows[0], dict):
        head = list(cols) if cols is not None else list(rows[0])
        body = [[_cell(r.get(c)) for c in head] for r in rows]
        return [str(c) for c in head], body
    rows = [[_cell(x) for x in r] for r in rows]
    if cols is not None:
        return [str(c) for c in cols], rows
    if not rows:
        return [], []
    return rows[0], rows[1:]


def table(rows, cols=None) -> str:
    """The table as text.

    rows: a list of lists (the first one is the header unless cols is given) or a list of dicts.
    cols: column names; for dicts, which keys and in what order.
    Returns a string without a trailing newline; empty rows give an empty string."""
    head, body = _grid(rows, cols)
    if not head and not body:
        return ""
    width = len(head)
    body = [(r + [""] * width)[:width] for r in body]
    widths = [max([len(head[i])] + [len(r[i]) for r in body]) for i in range(width)]
    numeric = [bool(body) and all(_is_number(r[i]) for r in body if r[i] != "")
               for i in range(width)]

    def line(cells, align):
        out = [c.rjust(w) if (align and num) else c.ljust(w)
               for c, w, num in zip(cells, widths, numeric)]
        return "  ".join(out).rstrip()
    return "\n".join([line(head, False)] + [line(r, True) for r in body])


def show(rows, cols=None) -> None:
    """Print table(rows, cols)."""
    print(table(rows, cols))


def from_csv(path, delimiter=",") -> list:
    """Read a CSV file into a list of dicts (the header is the first line)."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=delimiter))
