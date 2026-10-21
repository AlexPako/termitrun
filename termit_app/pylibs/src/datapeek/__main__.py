"""datapeek command line: datapeek FILE.csv [--top N]."""
import argparse
import sys

import datapeek


def main(argv=None) -> int:
    """Entry point of the datapeek command (and python3 -m datapeek)."""
    ap = argparse.ArgumentParser(prog="datapeek",
                                 description="CSV summary: columns, rows, most common values.")
    ap.add_argument("file", help="CSV file with a header row")
    ap.add_argument("--top", type=int, default=3, help="how many common values (default 3)")
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
