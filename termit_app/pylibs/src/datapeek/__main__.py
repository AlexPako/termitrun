"""Командная строка datapeek: datapeek ФАЙЛ.csv [--top N]."""
import argparse
import sys

import datapeek


def main(argv=None) -> int:
    """Точка входа консольной команды datapeek (и python3 -m datapeek)."""
    ap = argparse.ArgumentParser(prog="datapeek",
                                 description="Сводка CSV: колонки, строки, частые значения.")
    ap.add_argument("file", help="CSV-файл с шапкой")
    ap.add_argument("--top", type=int, default=3, help="сколько частых значений (по умолчанию 3)")
    ap.add_argument("--version", action="version", version="datapeek " + datapeek.__version__)
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        print(datapeek.report(args.file, max(1, args.top)))
    except OSError as e:
        print(f"datapeek: {args.file}: {e.strerror or e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
