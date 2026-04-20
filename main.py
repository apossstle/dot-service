import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.server import run_server

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    run_server(host="0.0.0.0", port=port)
