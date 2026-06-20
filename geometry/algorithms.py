from enum import Enum

from .types import Point, Ring, Polygon, MultiPolygon, Geometry

EPSILON = 1e-10


class PointLocation(Enum):
    INSIDE = "inside"
    OUTSIDE = "outside"
    ON_BOUNDARY = "on_boundary"


def _is_on_segment(p: Point, a: Point, b: Point) -> bool:
    cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x)
    if abs(cross) > EPSILON:
        return False
    return (
        min(a.x, b.x) - EPSILON <= p.x <= max(a.x, b.x) + EPSILON
        and min(a.y, b.y) - EPSILON <= p.y <= max(a.y, b.y) + EPSILON
    )


def _cross_z(o: Point, a: Point, b: Point) -> float:
    return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)


def ray_casting(point: Point, ring: Ring) -> PointLocation:
    pts = ring.points
    n = len(pts)
    px, py = point.x, point.y
    inside = False

    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]

        if _is_on_segment(point, a, b):
            return PointLocation.ON_BOUNDARY

        if (a.y > py) != (b.y > py):
            x_cross = a.x + (py - a.y) * (b.x - a.x) / (b.y - a.y)
            if px < x_cross:
                inside = not inside

    return PointLocation.INSIDE if inside else PointLocation.OUTSIDE


def winding_number(point: Point, ring: Ring) -> PointLocation:
    pts = ring.points
    n = len(pts)
    px, py = point.x, point.y
    wn = 0

    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]

        if _is_on_segment(point, a, b):
            return PointLocation.ON_BOUNDARY

        if a.y <= py:
            if b.y > py and _cross_z(a, b, point) > 0:
                wn += 1
        else:
            if b.y <= py and _cross_z(a, b, point) < 0:
                wn -= 1

    return PointLocation.INSIDE if wn != 0 else PointLocation.OUTSIDE


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
            return PointLocation.OUTSIDE

    return PointLocation.INSIDE


def multipolygon_contains(
    point: Point,
    multi: MultiPolygon,
    algorithm: str = "ray_casting",
) -> PointLocation:
    found_inside = False
    for part in multi.polygons:
        loc = polygon_contains(point, part, algorithm)
        if loc == PointLocation.ON_BOUNDARY:
            return PointLocation.ON_BOUNDARY
        if loc == PointLocation.INSIDE:
            found_inside = True
    return PointLocation.INSIDE if found_inside else PointLocation.OUTSIDE


def geometry_contains(
    point: Point,
    geometry: Geometry,
    algorithm: str = "ray_casting",
) -> PointLocation:
    if isinstance(geometry, Polygon):
        return polygon_contains(point, geometry, algorithm)
    if isinstance(geometry, MultiPolygon):
        return multipolygon_contains(point, geometry, algorithm)
    raise TypeError(f"Неизвестный тип геометрии: {type(geometry).__name__}")


def bbox_contains_point(bbox: tuple, point: Point) -> bool:
    min_x, min_y, max_x, max_y = bbox
    return min_x <= point.x <= max_x and min_y <= point.y <= max_y
