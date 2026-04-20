from enum import Enum
from .types import Point, Ring, Polygon

EPSILON = 1e-10


class PointLocation(Enum):
    INSIDE      = "inside"
    OUTSIDE     = "outside"
    ON_BOUNDARY = "on_boundary"


# Вспомогательные функции

def _is_on_segment(p: Point, a: Point, b: Point) -> bool:
    """Лежит ли точка P на отрезке AB."""
    cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x)
    if abs(cross) > EPSILON:
        return False
    return (
        min(a.x, b.x) - EPSILON <= p.x <= max(a.x, b.x) + EPSILON and
        min(a.y, b.y) - EPSILON <= p.y <= max(a.y, b.y) + EPSILON
    )


def _cross_z(o: Point, a: Point, b: Point) -> float:
    """Z-компонента векторного произведения OA × OB."""
    return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)


# Алгоритм 1 Ray Casting

def ray_casting(point: Point, ring: Ring) -> PointLocation:
    """
    Из точки P проводим горизонтальный луч вправо.
    Считаем, сколько рёбер кольца он пересекает.
    Нечётно → INSIDE, чётно → OUTSIDE.
    """
    pts = ring.points
    n   = len(pts)
    px, py = point.x, point.y
    inside = False

    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]

        if _is_on_segment(point, a, b):
            return PointLocation.ON_BOUNDARY

        # Ребро пересекает горизонталь y = py?
        if (a.y > py) != (b.y > py):
            x_cross = a.x + (py - a.y) * (b.x - a.x) / (b.y - a.y)
            if px < x_cross:
                inside = not inside

    return PointLocation.INSIDE if inside else PointLocation.OUTSIDE


# Алгоритм 2 Winding Number

def winding_number(point: Point, ring: Ring) -> PointLocation:
    """
    Считаем сколько раз контур обматывается вокруг точки P.
    wn != 0 → INSIDE, wn == 0 → OUTSIDE.
    """
    pts = ring.points
    n   = len(pts)
    px, py = point.x, point.y
    wn = 0

    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]

        if _is_on_segment(point, a, b):
            return PointLocation.ON_BOUNDARY

        if a.y <= py:
            if b.y > py and _cross_z(a, b, point) > 0:   # ребро идёт вверх, P слева
                wn += 1
        else:
            if b.y <= py and _cross_z(a, b, point) < 0:  # ребро идёт вниз, P справа
                wn -= 1

    return PointLocation.INSIDE if wn != 0 else PointLocation.OUTSIDE


# Точка в полигоне с отверстиями

def polygon_contains(
    point: Point,
    polygon: Polygon,
    algorithm: str = "ray_casting",
) -> PointLocation:
    check = ray_casting if algorithm == "ray_casting" else winding_number

    location = check(point, polygon.exterior)
    if location != PointLocation.INSIDE:
        return location

    for hole in polygon.holes:
        hole_loc = check(point, hole)
        if hole_loc == PointLocation.ON_BOUNDARY:
            return PointLocation.ON_BOUNDARY
        if hole_loc == PointLocation.INSIDE:
            return PointLocation.OUTSIDE  # точка в дыре — снаружи полигона

    return PointLocation.INSIDE


def bbox_contains_point(bbox: tuple, point: Point) -> bool:
    """O(1) предфильтр: попадает ли точка в bounding box (min_x, min_y, max_x, max_y)."""
    min_x, min_y, max_x, max_y = bbox
    return min_x <= point.x <= max_x and min_y <= point.y <= max_y