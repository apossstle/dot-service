import argparse
import errno
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.server import configure_repository, run_server

def main() -> None:
    p = argparse.ArgumentParser()
    # Локально можно передать --host 127.0.0.1
    p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    p.add_argument("--cell-size", type=float, default=float(os.environ.get("CELL_SIZE", "1.0")),
                   dest="cell_size")
    args = p.parse_args()

    configure_repository(cell_size=args.cell_size)
    print(f"http://{args.host}:{args.port}")

    try:
        run_server(host=args.host, port=args.port)
    except OSError as e:
        if getattr(e, "errno", None) == errno.EADDRINUSE:
            print(f"порт {args.port} занят, попробуйте --port 9090", file=sys.stderr)
        raise SystemExit(1) from e

if __name__ == "__main__":
    main()
