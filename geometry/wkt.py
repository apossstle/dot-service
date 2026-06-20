import re

from .types import Point, Ring, Polygon, MultiPolygon, Geometry

_NUM = r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
_POINT_PAIR = re.compile(rf"\s*({_NUM})\s+({_NUM})\s*")


def _parse_ring(text: str) -> Ring:
    points = []
    for chunk in text.split(","):
        m = _POINT_PAIR.fullmatch(chunk)
        if not m:
            raise ValueError(f"Невалидная точка WKT: '{chunk.strip()}'")
        points.append(Point(float(m.group(1)), float(m.group(2))))
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 3:
        raise ValueError("Кольцо WKT должно содержать минимум 3 уникальные точки")
    return Ring(points=points)


def _split_rings(body: str) -> list[str]:
    rings = []
    depth = 0
    start = None
    for i, ch in enumerate(body):
        if ch == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                rings.append(body[start:i])
    if depth != 0:
        raise ValueError("Несбалансированные скобки в WKT")
    return rings


def parse_wkt(text: str) -> Geometry:
    text = text.strip()
    upper = text.upper()

    if upper.startswith("POLYGON"):
        body = text[len("POLYGON"):].strip()
        if not (body.startswith("(") and body.endswith(")")):
            raise ValueError("Ожидаются внешние скобки у POLYGON")
        rings = _split_rings(body[1:-1])
        if not rings:
            raise ValueError("POLYGON без колец")
        exterior = _parse_ring(rings[0])
        holes = [_parse_ring(r) for r in rings[1:]]
        return Polygon(exterior=exterior, holes=holes)

    if upper.startswith("MULTIPOLYGON"):
        body = text[len("MULTIPOLYGON"):].strip()
        if not (body.startswith("(") and body.endswith(")")):
            raise ValueError("Ожидаются внешние скобки у MULTIPOLYGON")
        parts = _split_rings(body[1:-1])
        polygons = []
        for part in parts:
            rings = _split_rings(part)
            if not rings:
                raise ValueError("Часть MULTIPOLYGON без колец")
            polygons.append(Polygon(
                exterior=_parse_ring(rings[0]),
                holes=[_parse_ring(r) for r in rings[1:]],
            ))
        return MultiPolygon(polygons=polygons)

    raise ValueError(f"Неизвестный тип WKT: '{text[:30]}...'")


def _ring_to_wkt(ring: Ring) -> str:
    coords = ring.to_coords()
    return "(" + ", ".join(f"{x} {y}" for x, y in coords) + ")"


def _polygon_body(poly: Polygon) -> str:
    rings = [_ring_to_wkt(poly.exterior)] + [_ring_to_wkt(h) for h in poly.holes]
    return "(" + ", ".join(rings) + ")"


def to_wkt(geom: Geometry) -> str:
    if isinstance(geom, Polygon):
        return "POLYGON " + _polygon_body(geom)
    if isinstance(geom, MultiPolygon):
        parts = [_polygon_body(p) for p in geom.polygons]
        return "MULTIPOLYGON (" + ", ".join(parts) + ")"
    raise TypeError(f"Не умею сериализовать в WKT: {type(geom).__name__}")
