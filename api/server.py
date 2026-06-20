import json
import os
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlparse

from geometry.types import Point, geometry_from_geojson
from geometry.wkt import parse_wkt, to_wkt
from storage.repository import PolygonRepository

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

_repository: PolygonRepository | None = None

CORS_ORIGIN = "*"
CORS_METHODS = "GET, POST, PUT, DELETE, OPTIONS"
CORS_HEADERS = "Content-Type, X-User-Id"
USER_COOKIE = "ps_uid"


def configure_repository(cell_size: float = 1.0) -> PolygonRepository:
    global _repository
    _repository = PolygonRepository(index_cell_size=cell_size)
    return _repository


def get_repository() -> PolygonRepository:
    if _repository is None:
        configure_repository()
    return _repository


def reset_repository(cell_size: float = 1.0) -> PolygonRepository:
    return configure_repository(cell_size)  # alias for tests


def _send_cors(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
    handler.send_header("Access-Control-Allow-Methods", CORS_METHODS)
    handler.send_header("Access-Control-Allow-Headers", CORS_HEADERS)


def _json(
    handler: BaseHTTPRequestHandler,
    status: int,
    data: dict,
    *,
    user_id: str | None = None,
    set_user_cookie: bool = False,
) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    if set_user_cookie and user_id:
        _set_user_cookie(handler, user_id)
    _send_cors(handler)
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    try:
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Невалидный JSON: {e}")


def _parse_cookies(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    raw = handler.headers.get("Cookie")
    if not raw:
        return {}
    jar = SimpleCookie()
    jar.load(raw)
    return {key: morsel.value for key, morsel in jar.items()}


def _set_user_cookie(handler: BaseHTTPRequestHandler, user_id: str) -> None:
    cookie = SimpleCookie()
    cookie[USER_COOKIE] = user_id
    cookie[USER_COOKIE]["path"] = "/"
    cookie[USER_COOKIE]["httponly"] = True
    cookie[USER_COOKIE]["samesite"] = "Lax"
    handler.send_header("Set-Cookie", cookie.output(header="", sep="").strip())


def _resolve_user_id(handler: BaseHTTPRequestHandler, *, create: bool = False) -> tuple[str, bool]:
    header_id = handler.headers.get("X-User-Id", "").strip()
    if header_id:
        return header_id, False

    cookie_id = _parse_cookies(handler).get(USER_COOKIE, "").strip()
    if cookie_id:
        return cookie_id, False

    if create:
        return str(uuid.uuid4()), True

    raise ValueError("Заголовок 'X-User-Id' обязателен")


def _get_user_id(handler: BaseHTTPRequestHandler) -> str:
    user_id, _ = _resolve_user_id(handler, create=False)
    return user_id


def _owned_record(handler: BaseHTTPRequestHandler, polygon_id: str):
    user_id = _get_user_id(handler)
    record = get_repository().get(polygon_id)
    if record is None or record.owner_id != user_id:
        return user_id, None
    return user_id, record


def _parse_path(path: str) -> tuple[str, str | None]:
    parts = path.strip("/").split("/")
    if not parts or parts == [""]:
        return "", None
    rid = parts[1] if len(parts) > 1 else None
    return parts[0], rid or None


def _render(template: str, **kwargs) -> str:
    with open(os.path.join(TEMPLATES_DIR, template), encoding="utf-8") as f:
        content = f.read()
    for key, val in kwargs.items():
        content = content.replace("{" + key + "}", str(val))
    return content


def _parse_geometry(body: dict):
    if body.get("wkt"):
        return parse_wkt(body["wkt"])
    if body.get("geometry"):
        return geometry_from_geojson(body["geometry"])
    raise ValueError("Нужно поле geometry или wkt")


def _record_payload(record_dict: dict, geometry) -> dict:
    record_dict["wkt"] = to_wkt(geometry)
    return record_dict


def handle_root(handler: BaseHTTPRequestHandler) -> None:
    html = _render("index.html", polygon_count="—")
    body = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    _send_cors(handler)
    handler.end_headers()
    handler.wfile.write(body)


def handle_options(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(204)
    _send_cors(handler)
    handler.end_headers()


def handle_health(handler: BaseHTTPRequestHandler) -> None:
    _json(handler, 200, {"status": "ok", "polygon_count": get_repository().count()})


def handle_stats(handler: BaseHTTPRequestHandler) -> None:
    user_id = _get_user_id(handler)
    repo = get_repository()
    _json(handler, 200, {
        "polygon_count": repo.count_by_owner(user_id),
        "index": repo.index_stats(),
    })


def handle_list(handler: BaseHTTPRequestHandler) -> None:
    user_id = _get_user_id(handler)
    records = get_repository().list_by_owner(user_id)
    _json(handler, 200, {
        "count": len(records),
        "polygons": [_record_payload(r.to_dict(), r.geometry) for r in records],
    })


def handle_create(handler: BaseHTTPRequestHandler) -> None:
    user_id, is_new = _resolve_user_id(handler, create=True)
    body = _read_body(handler)
    name = body.get("name", "")
    if not name:
        raise ValueError("Поле 'name' обязательно")
    geometry = _parse_geometry(body)
    record = get_repository().create(
        name=name,
        geometry=geometry,
        owner_id=user_id,
        properties=body.get("properties") or {},
    )
    _json(
        handler,
        201,
        _record_payload(record.to_dict(), record.geometry),
        user_id=user_id,
        set_user_cookie=is_new,
    )


def handle_get(handler: BaseHTTPRequestHandler, polygon_id: str) -> None:
    _, record = _owned_record(handler, polygon_id)
    if record is None:
        _json(handler, 404, {"error": f"Полигон '{polygon_id}' не найден"})
        return
    _json(handler, 200, _record_payload(record.to_dict(), record.geometry))


def handle_update(handler: BaseHTTPRequestHandler, polygon_id: str) -> None:
    _, record = _owned_record(handler, polygon_id)
    if record is None:
        _json(handler, 404, {"error": f"Полигон '{polygon_id}' не найден"})
        return
    body = _read_body(handler)
    geometry = None
    if body.get("wkt") or body.get("geometry"):
        geometry = _parse_geometry(body)
    updated = get_repository().update(
        polygon_id=polygon_id,
        name=body.get("name"),
        geometry=geometry,
        properties=body.get("properties"),
    )
    _json(handler, 200, _record_payload(updated.to_dict(), updated.geometry))


def handle_delete(handler: BaseHTTPRequestHandler, polygon_id: str) -> None:
    _, record = _owned_record(handler, polygon_id)
    if record is None:
        _json(handler, 404, {"error": f"Полигон '{polygon_id}' не найден"})
        return
    get_repository().delete(polygon_id)
    _json(handler, 200, {"message": f"Полигон '{polygon_id}' удалён"})


def handle_pip(handler: BaseHTTPRequestHandler) -> None:
    user_id = _get_user_id(handler)
    body = _read_body(handler)
    raw_point = body.get("point")
    if not raw_point or len(raw_point) < 2:
        raise ValueError("Поле 'point' обязательно: [x, y]")
    algorithm = body.get("algorithm", "ray_casting")
    if algorithm not in ("ray_casting", "winding_number"):
        raise ValueError("algorithm: 'ray_casting' или 'winding_number'")
    point = Point.from_list(raw_point)
    include = body.get("include_boundary", True)
    records = get_repository().find_containing_point(point, user_id, algorithm, include)
    _json(handler, 200, {
        "point": raw_point,
        "algorithm": algorithm,
        "include_boundary": include,
        "matching_count": len(records),
        "matching_polygons": [_record_payload(r.to_dict(), r.geometry) for r in records],
    })


class PolygonServiceHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def _dispatch(self) -> None:
        path = urlparse(self.path).path
        method = self.command

        if method == "OPTIONS":
            return handle_options(self)
        if method == "GET" and path == "/":
            return handle_root(self)
        if method == "GET" and path == "/health":
            return handle_health(self)
        if method == "GET" and path == "/stats":
            return handle_stats(self)
        if method == "POST" and path == "/query/point-in-polygon":
            return handle_pip(self)

        resource, rid = _parse_path(path)
        if resource == "polygons":
            if method == "GET" and rid is None:
                return handle_list(self)
            if method == "POST" and rid is None:
                return handle_create(self)
            if method == "GET" and rid:
                return handle_get(self, rid)
            if method == "PUT" and rid:
                return handle_update(self, rid)
            if method == "DELETE" and rid:
                return handle_delete(self, rid)

        _json(self, 404, {"error": f"Маршрут не найден: {method} {path}"})

    def _handle(self) -> None:
        try:
            self._dispatch()
        except ValueError as e:
            _json(self, 400, {"error": str(e)})
        except Exception:
            print(f"[ERROR]\n{traceback.format_exc()}")
            _json(self, 500, {"error": "Внутренняя ошибка сервера"})

    do_GET = do_POST = do_PUT = do_DELETE = do_OPTIONS = _handle


def run_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    repository: PolygonRepository | None = None,
) -> None:
    global _repository
    if repository is not None:
        _repository = repository
    elif _repository is None:
        configure_repository()
    server = HTTPServer((host, port), PolygonServiceHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
