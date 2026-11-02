import math
from functools import reduce

import shapely
from shapely.geometry import GeometryCollection as ShpCollection
from shapely.geometry import MultiPolygon as ShpMultiPolygon
from shapely.geometry import Polygon as ShpPolygon

from .types import Geometry, MultiPolygon, Polygon, Ring


def to_shapely(geometry: Geometry):
    if isinstance(geometry, Polygon):
        return _polygon_to_shapely(geometry)
    if isinstance(geometry, MultiPolygon):
        return ShpMultiPolygon([_polygon_to_shapely(p) for p in geometry.polygons])
    raise TypeError(f"Неизвестный тип геометрии: {type(geometry).__name__}")


def from_shapely(shp) -> Geometry | None:
    polygons = [_polygon_from_shapely(part) for part in _polygonal_parts(shp)]
    if not polygons:
        return None
    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons=polygons)


def union(geometries: list[Geometry]) -> Geometry | None:
    _require_count(geometries, 2, "union")
    return from_shapely(shapely.union_all([_prepare(g) for g in geometries]))


def intersection(geometries: list[Geometry]) -> Geometry | None:
    _require_count(geometries, 2, "intersection")
    return from_shapely(reduce(shapely.intersection, [_prepare(g) for g in geometries]))


def difference(base: Geometry, others: list[Geometry]) -> Geometry | None:
    _require_count(others, 1, "difference")
    subtrahend = shapely.union_all([_prepare(g) for g in others])
    return from_shapely(shapely.difference(_prepare(base), subtrahend))


def buffer(geometry: Geometry, distance: float) -> Geometry | None:
    if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance):
        raise ValueError("distance должен быть конечным числом")
    return from_shapely(_prepare(geometry).buffer(distance))


def _polygon_to_shapely(polygon: Polygon) -> ShpPolygon:
    return ShpPolygon(
        [p.to_list() for p in polygon.exterior.points],
        [[p.to_list() for p in hole.points] for hole in polygon.holes],
    )


def _polygon_from_shapely(shp: ShpPolygon) -> Polygon:
    return Polygon(
        exterior=Ring.from_coords(list(shp.exterior.coords)),
        holes=[Ring.from_coords(list(ring.coords)) for ring in shp.interiors],
    )


def _polygonal_parts(shp) -> list[ShpPolygon]:
    if shp.is_empty:
        return []
    if isinstance(shp, ShpPolygon):
        return [shp]
    if isinstance(shp, (ShpMultiPolygon, ShpCollection)):
        return [part for geom in shp.geoms for part in _polygonal_parts(geom)]
    return []


def _prepare(geometry: Geometry):
    shp = to_shapely(geometry)
    if shp.is_valid:
        return shp
    parts = _polygonal_parts(shapely.make_valid(shp))
    return ShpMultiPolygon(parts) if parts else ShpPolygon()


def _require_count(geometries: list[Geometry], minimum: int, operation: str) -> None:
    if len(geometries) < minimum:
        raise ValueError(f"Для {operation} нужно минимум {minimum} геометрии")
