import argparse
import errno
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.server import configure_repository, run_server

HOST = "127.0.0.1"
INDEX_CHOICES = ("grid", "rtree")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    p.add_argument("--cell-size", type=float, default=float(os.environ.get("CELL_SIZE", "1.0")),
                   dest="cell_size")
    p.add_argument("--index", choices=INDEX_CHOICES,
                   default=os.environ.get("INDEX_TYPE", "grid"))
    args = p.parse_args()

    if args.index not in INDEX_CHOICES:
        print(f"INDEX_TYPE должен быть одним из: {', '.join(INDEX_CHOICES)}", file=sys.stderr)
        raise SystemExit(2)

    configure_repository(index_type=args.index, cell_size=args.cell_size)
    print(f"http://{HOST}:{args.port}  (index={args.index})")

    try:
        run_server(host=HOST, port=args.port)
    except OSError as e:
        if getattr(e, "errno", None) == errno.EADDRINUSE:
            print(f"порт {args.port} занят, попробуйте --port 9090", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
