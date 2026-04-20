import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.server import run_server


def main():
    parser = argparse.ArgumentParser(description="Polygon Service")
    parser.add_argument("--host",      default="127.0.0.1")
    parser.add_argument("--port",      type=int, default=8080)
    parser.add_argument("--cell-size", type=float, default=1.0, dest="cell_size",
                        help="Размер ячейки пространственного индекса")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()