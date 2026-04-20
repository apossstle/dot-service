#ЗАПУСК ПО ЛОКАЛКЕ------------------------------------------------------------------------------------


# import argparse
# import sys
# import os

# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# from api.server import run_server


# def main():
#     parser = argparse.ArgumentParser(description="Polygon Service")
#     parser.add_argument("--host",      default="127.0.0.1")
#     parser.add_argument("--port",      type=int, default=8080)
#     parser.add_argument("--cell-size", type=float, default=1.0, dest="cell_size",
#                         help="Размер ячейки пространственного индекса")
#     args = parser.parse_args()
#     run_server(host=args.host, port=args.port)


# if __name__ == "__main__":
#     main()

#ЗАПУСК ЧЕРЕЗ СЕРВЕР------------------------------------------------------------------------------------------------

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.server import run_server

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    run_server(host="0.0.0.0", port=port)
