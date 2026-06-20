import sys
import os
import json
import unittest
import io
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometry.types import Point, Ring, Polygon, MultiPolygon, geometry_from_geojson
from geometry.algorithms import (
    ray_casting, winding_number, polygon_contains, multipolygon_contains,
    geometry_contains, PointLocation, bbox_contains_point
)
from geometry.index import BoundingBoxIndex, GridIndex
from geometry.wkt import parse_wkt, to_wkt
from storage.repository import PolygonRepository
from api import server as api_server
from api.server import PolygonServiceHandler, reset_repository


def make_square(x0=0, y0=0, x1=1, y1=1) -> Polygon:
    ring = Ring(points=[
        Point(x0, y0), Point(x1, y0),
        Point(x1, y1), Point(x0, y1)
    ])
    return Polygon(exterior=ring)


def make_square_with_hole() -> Polygon:
    exterior = Ring(points=[
        Point(0, 0), Point(4, 0),
        Point(4, 4), Point(0, 4)
    ])
    hole = Ring(points=[
        Point(1, 1), Point(3, 1),
        Point(3, 3), Point(1, 3)
    ])
    return Polygon(exterior=exterior, holes=[hole])


class TestPointClass(unittest.TestCase):

    def test_create_point(self):
        p = Point(1.5, 2.5)
        self.assertEqual(p.x, 1.5)
        self.assertEqual(p.y, 2.5)

    def test_point_from_list(self):
        p = Point.from_list([3.0, 4.0])
        self.assertEqual(p.x, 3.0)
        self.assertEqual(p.y, 4.0)

    def test_point_to_list(self):
        p = Point(1.0, 2.0)
        self.assertEqual(p.to_list(), [1.0, 2.0])

    def test_point_equality(self):
        self.assertEqual(Point(1.0, 2.0), Point(1.0, 2.0))
        self.assertNotEqual(Point(1.0, 2.0), Point(1.0, 3.0))

    def test_invalid_coords(self):
        with self.assertRaises(ValueError):
            Point.from_list([1.0])


class TestRingClass(unittest.TestCase):

    def test_create_from_coords(self):
        ring = Ring.from_coords([[0,0],[1,0],[1,1],[0,1],[0,0]])
        self.assertEqual(len(ring), 4)

    def test_too_few_points(self):
        with self.assertRaises(ValueError):
            Ring.from_coords([[0,0],[1,0],[0,0]])

    def test_bounding_box(self):
        ring = Ring(points=[Point(1,2), Point(3,2), Point(3,5), Point(1,5)])
        bbox = ring.bounding_box()
        self.assertEqual(bbox, (1, 2, 3, 5))

    def test_to_coords_closes_ring(self):
        ring = Ring(points=[Point(0,0), Point(1,0), Point(1,1)])
        coords = ring.to_coords()
        self.assertEqual(coords[0], coords[-1])


class TestPolygonClass(unittest.TestCase):

    def test_geojson_roundtrip(self):
        original = make_square()
        geojson = original.to_geojson()
        restored = Polygon.from_geojson(geojson)

        self.assertEqual(len(original.exterior), len(restored.exterior))
        for orig_pt, rest_pt in zip(original.exterior.points, restored.exterior.points):
            self.assertAlmostEqual(orig_pt.x, rest_pt.x)
            self.assertAlmostEqual(orig_pt.y, rest_pt.y)

    def test_polygon_with_holes(self):
        poly = make_square_with_hole()
        self.assertTrue(poly.has_holes())
        self.assertEqual(len(poly.holes), 1)

    def test_invalid_type(self):
        with self.assertRaises(ValueError):
            Polygon.from_geojson({"type": "Point", "coordinates": [0, 0]})

    def test_feature_wrapper(self):
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]
            }
        }
        poly = Polygon.from_geojson(feature)
        self.assertEqual(len(poly.exterior), 4)


class _AlgorithmMixin:

    def _check(self, point: Point, ring: Ring) -> PointLocation:
        raise NotImplementedError

    def setUp(self):
        self.square = make_square(0, 0, 4, 4)
        self.ring = self.square.exterior

    def test_point_clearly_inside(self):
        result = self._check(Point(2, 2), self.ring)
        self.assertEqual(result, PointLocation.INSIDE)

    def test_point_clearly_outside(self):
        result = self._check(Point(10, 10), self.ring)
        self.assertEqual(result, PointLocation.OUTSIDE)

    def test_point_outside_negative(self):
        result = self._check(Point(-1, 2), self.ring)
        self.assertEqual(result, PointLocation.OUTSIDE)

    def test_point_on_edge(self):
        result = self._check(Point(2, 0), self.ring)
        self.assertEqual(result, PointLocation.ON_BOUNDARY)

    def test_point_on_vertex(self):
        result = self._check(Point(0, 0), self.ring)
        self.assertEqual(result, PointLocation.ON_BOUNDARY)

    def test_point_on_top_edge(self):
        result = self._check(Point(2, 4), self.ring)
        self.assertEqual(result, PointLocation.ON_BOUNDARY)

    def test_point_just_inside(self):
        result = self._check(Point(0.001, 0.001), self.ring)
        self.assertEqual(result, PointLocation.INSIDE)

    def test_point_just_outside(self):
        result = self._check(Point(-0.001, 2), self.ring)
        self.assertEqual(result, PointLocation.OUTSIDE)


class TestRayCasting(_AlgorithmMixin, unittest.TestCase):
    def _check(self, point, ring):
        return ray_casting(point, ring)


class TestWindingNumber(_AlgorithmMixin, unittest.TestCase):
    def _check(self, point, ring):
        return winding_number(point, ring)


class TestPolygonContains(unittest.TestCase):

    def setUp(self):
        self.square = make_square(0, 0, 4, 4)
        self.square_with_hole = make_square_with_hole()

    def test_inside_simple(self):
        result = polygon_contains(Point(2, 2), self.square)
        self.assertEqual(result, PointLocation.INSIDE)

    def test_outside_simple(self):
        result = polygon_contains(Point(5, 5), self.square)
        self.assertEqual(result, PointLocation.OUTSIDE)

    def test_inside_polygon_with_hole(self):
        result = polygon_contains(Point(0.5, 0.5), self.square_with_hole)
        self.assertEqual(result, PointLocation.INSIDE)

    def test_inside_hole(self):
        result = polygon_contains(Point(2, 2), self.square_with_hole)
        self.assertEqual(result, PointLocation.OUTSIDE)

    def test_on_outer_boundary(self):
        result = polygon_contains(Point(2, 0), self.square_with_hole)
        self.assertEqual(result, PointLocation.ON_BOUNDARY)

    def test_on_hole_boundary(self):
        result = polygon_contains(Point(2, 1), self.square_with_hole)
        self.assertEqual(result, PointLocation.ON_BOUNDARY)

    def test_both_algorithms_agree(self):
        test_points = [
            Point(2, 2), Point(0.5, 0.5), Point(5, 5),
            Point(2, 0), Point(0, 0), Point(2, 1)
        ]
        for p in test_points:
            rc = polygon_contains(p, self.square_with_hole, "ray_casting")
            wn = polygon_contains(p, self.square_with_hole, "winding_number")
            self.assertEqual(rc, wn, msg=f"point {p}")


class TestBboxContainsPoint(unittest.TestCase):

    def test_inside_bbox(self):
        self.assertTrue(bbox_contains_point((0, 0, 10, 10), Point(5, 5)))

    def test_outside_bbox(self):
        self.assertFalse(bbox_contains_point((0, 0, 10, 10), Point(15, 5)))

    def test_on_bbox_boundary(self):
        self.assertTrue(bbox_contains_point((0, 0, 10, 10), Point(0, 5)))
        self.assertTrue(bbox_contains_point((0, 0, 10, 10), Point(10, 10)))


class TestBoundingBoxIndex(unittest.TestCase):

    def setUp(self):
        self.index = BoundingBoxIndex()
        self.poly1 = make_square(0, 0, 5, 5)
        self.poly2 = make_square(10, 10, 20, 20)
        self.index.add("p1", self.poly1)
        self.index.add("p2", self.poly2)

    def test_point_in_first_polygon(self):
        candidates = self.index.candidates(Point(2, 2))
        self.assertIn("p1", candidates)
        self.assertNotIn("p2", candidates)

    def test_point_in_second_polygon(self):
        candidates = self.index.candidates(Point(15, 15))
        self.assertIn("p2", candidates)
        self.assertNotIn("p1", candidates)

    def test_point_outside_both(self):
        candidates = self.index.candidates(Point(50, 50))
        self.assertEqual(candidates, [])

    def test_remove(self):
        self.index.remove("p1")
        candidates = self.index.candidates(Point(2, 2))
        self.assertNotIn("p1", candidates)

    def test_update(self):
        new_poly = make_square(100, 100, 110, 110)
        self.index.update("p1", new_poly)
        self.assertEqual(self.index.candidates(Point(2, 2)), [])
        self.assertIn("p1", self.index.candidates(Point(105, 105)))


class TestGridIndex(unittest.TestCase):

    def setUp(self):
        self.index = GridIndex(cell_size=5.0)
        self.poly = make_square(0, 0, 4, 4)
        self.index.add("p1", self.poly)

    def test_finds_polygon(self):
        self.assertIn("p1", self.index.candidates(Point(2, 2)))

    def test_no_false_positive(self):
        candidates = self.index.candidates(Point(20, 20))
        self.assertNotIn("p1", candidates)

    def test_stats(self):
        stats = self.index.stats()
        self.assertEqual(stats["type"], "GridIndex")
        self.assertEqual(stats["polygon_count"], 1)

    def test_remove_clears_grid_cells(self):
        self.index.remove("p1")
        self.assertEqual(self.index.candidates(Point(2, 2)), [])
        self.assertEqual(self.index.stats()["occupied_cells"], 0)

    def test_update_relocates_polygon(self):
        new_poly = make_square(100, 100, 110, 110)
        self.index.update("p1", new_poly)
        self.assertEqual(self.index.candidates(Point(2, 2)), [])
        self.assertIn("p1", self.index.candidates(Point(105, 105)))


class TestMultiPolygon(unittest.TestCase):

    def setUp(self):
        self.mp = MultiPolygon(polygons=[
            make_square(0, 0, 4, 4),
            make_square(10, 10, 14, 14),
        ])

    def test_geojson_roundtrip(self):
        gj = self.mp.to_geojson()
        self.assertEqual(gj["type"], "MultiPolygon")
        restored = MultiPolygon.from_geojson(gj)
        self.assertEqual(len(restored), 2)

    def test_bounding_box_covers_all_parts(self):
        bbox = self.mp.bounding_box()
        self.assertEqual(bbox, (0, 0, 14, 14))

    def test_point_in_first_part(self):
        result = multipolygon_contains(Point(2, 2), self.mp)
        self.assertEqual(result, PointLocation.INSIDE)

    def test_point_in_second_part(self):
        result = multipolygon_contains(Point(12, 12), self.mp)
        self.assertEqual(result, PointLocation.INSIDE)

    def test_point_between_parts(self):
        result = multipolygon_contains(Point(7, 7), self.mp)
        self.assertEqual(result, PointLocation.OUTSIDE)

    def test_geometry_dispatch(self):
        self.assertEqual(geometry_contains(Point(2, 2), self.mp), PointLocation.INSIDE)
        self.assertEqual(geometry_contains(Point(50, 50), self.mp), PointLocation.OUTSIDE)

    def test_geometry_from_geojson_dispatch(self):
        poly_gj = {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}
        self.assertIsInstance(geometry_from_geojson(poly_gj), Polygon)
        self.assertIsInstance(geometry_from_geojson(self.mp.to_geojson()), MultiPolygon)

    def test_unsupported_type_rejected(self):
        with self.assertRaises(ValueError):
            geometry_from_geojson({"type": "Point", "coordinates": [0, 0]})


class TestWKT(unittest.TestCase):

    def test_parse_simple_polygon(self):
        geom = parse_wkt("POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))")
        self.assertIsInstance(geom, Polygon)
        self.assertEqual(len(geom.exterior), 4)
        self.assertFalse(geom.has_holes())

    def test_parse_polygon_with_hole(self):
        wkt = "POLYGON ((0 0, 20 0, 20 20, 0 20, 0 0), (5 5, 15 5, 15 15, 5 15, 5 5))"
        geom = parse_wkt(wkt)
        self.assertTrue(geom.has_holes())
        self.assertEqual(len(geom.holes), 1)

    def test_parse_multipolygon(self):
        wkt = "MULTIPOLYGON (((0 0, 1 0, 1 1, 0 1, 0 0)), ((10 10, 11 10, 11 11, 10 11, 10 10)))"
        geom = parse_wkt(wkt)
        self.assertIsInstance(geom, MultiPolygon)
        self.assertEqual(len(geom), 2)

    def test_parse_floats_and_negatives(self):
        geom = parse_wkt("POLYGON ((-1.5 0, 2.5 0, 1.0 3.5, -1.5 0))")
        self.assertIsInstance(geom, Polygon)
        self.assertEqual(geom.exterior.points[0], Point(-1.5, 0))

    def test_invalid_wkt_raises(self):
        with self.assertRaises(ValueError):
            parse_wkt("CIRCLE (0 0 10)")

    def test_unbalanced_parens_raises(self):
        with self.assertRaises(ValueError):
            parse_wkt("POLYGON ((0 0, 1 0, 1 1, 0 0")

    def test_polygon_to_wkt_roundtrip(self):
        original = make_square(0, 0, 5, 5)
        wkt = to_wkt(original)
        restored = parse_wkt(wkt)
        self.assertEqual(len(original.exterior), len(restored.exterior))
        for o, r in zip(original.exterior.points, restored.exterior.points):
            self.assertAlmostEqual(o.x, r.x)
            self.assertAlmostEqual(o.y, r.y)

    def test_multipolygon_to_wkt_roundtrip(self):
        original = MultiPolygon(polygons=[
            make_square(0, 0, 1, 1),
            make_square(10, 10, 11, 11),
        ])
        restored = parse_wkt(to_wkt(original))
        self.assertEqual(len(original), len(restored))


class TestRepository(unittest.TestCase):

    def setUp(self):
        self.repo = PolygonRepository(index_cell_size=1.0)
        self.poly = make_square(0, 0, 10, 10)

    def test_create_and_get(self):
        record = self.repo.create("test", self.poly, owner_id="user-a")
        fetched = self.repo.get(record.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "test")
        self.assertEqual(fetched.owner_id, "user-a")

    def test_get_nonexistent(self):
        result = self.repo.get("nonexistent-id")
        self.assertIsNone(result)

    def test_list_all(self):
        self.repo.create("poly1", make_square(0, 0, 5, 5), owner_id="user-a")
        self.repo.create("poly2", make_square(10, 10, 15, 15), owner_id="user-a")
        self.assertEqual(self.repo.count(), 2)
        self.assertEqual(len(self.repo.list_all()), 2)

    def test_list_by_owner(self):
        self.repo.create("mine", make_square(0, 0, 5, 5), owner_id="user-a")
        self.repo.create("theirs", make_square(10, 10, 15, 15), owner_id="user-b")
        self.assertEqual(len(self.repo.list_by_owner("user-a")), 1)
        self.assertEqual(self.repo.list_by_owner("user-a")[0].name, "mine")
        self.assertEqual(self.repo.count_by_owner("user-b"), 1)

    def test_update(self):
        record = self.repo.create("old name", self.poly, owner_id="user-a")
        updated = self.repo.update(record.id, name="new name")
        self.assertEqual(updated.name, "new name")
        self.assertEqual(self.repo.get(record.id).name, "new name")

    def test_delete(self):
        record = self.repo.create("to delete", self.poly, owner_id="user-a")
        result = self.repo.delete(record.id)
        self.assertTrue(result)
        self.assertIsNone(self.repo.get(record.id))

    def test_delete_nonexistent(self):
        result = self.repo.delete("no-such-id")
        self.assertFalse(result)

    def test_find_containing_point_inside(self):
        self.repo.create("big square", make_square(0, 0, 10, 10), owner_id="user-a")
        results = self.repo.find_containing_point(Point(5, 5), owner_id="user-a")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "big square")

    def test_find_containing_point_outside(self):
        self.repo.create("square", make_square(0, 0, 10, 10), owner_id="user-a")
        results = self.repo.find_containing_point(Point(20, 20), owner_id="user-a")
        self.assertEqual(len(results), 0)

    def test_find_multiple_matching(self):
        self.repo.create("large", make_square(0, 0, 10, 10), owner_id="user-a")
        self.repo.create("small", make_square(3, 3, 7, 7), owner_id="user-a")
        results = self.repo.find_containing_point(Point(5, 5), owner_id="user-a")
        self.assertEqual(len(results), 2)

    def test_find_with_boundary_excluded(self):
        self.repo.create("square", make_square(0, 0, 10, 10), owner_id="user-a")
        results = self.repo.find_containing_point(
            Point(5, 0), owner_id="user-a", include_boundary=False
        )
        self.assertEqual(len(results), 0)

    def test_find_ignores_other_users(self):
        self.repo.create("mine", make_square(0, 0, 10, 10), owner_id="user-a")
        self.repo.create("theirs", make_square(0, 0, 10, 10), owner_id="user-b")
        results = self.repo.find_containing_point(Point(5, 5), owner_id="user-a")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "mine")

    def test_properties_stored(self):
        props = {"region": "Moscow", "zone": "A"}
        record = self.repo.create("zone", self.poly, owner_id="user-a", properties=props)
        self.assertEqual(self.repo.get(record.id).properties, props)

    def test_index_stats(self):
        self.repo.create("p1", make_square(0, 0, 5, 5), owner_id="user-a")
        stats = self.repo.index_stats()
        self.assertIn("polygon_count", stats)
        self.assertEqual(stats["polygon_count"], 1)


class _MockHandler:
    def __init__(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        user_id: str = "test-user",
    ):
        self.command = method
        self.path = path
        self.status = None
        self._chunks: list[bytes] = []
        if body is not None:
            raw = json.dumps(body).encode()
            self.rfile = io.BytesIO(raw)
            self.headers = {
                "Content-Length": str(len(raw)),
                "X-User-Id": user_id,
            }
        else:
            self.rfile = io.BytesIO(b"")
            self.headers = {
                "Content-Length": "0",
                "X-User-Id": user_id,
            }

    def send_response(self, code: int) -> None:
        self.status = code

    def send_header(self, *_args) -> None:
        pass

    def end_headers(self) -> None:
        pass

    def log_date_time_string(self) -> str:
        return "test"

    def address_string(self) -> str:
        return "127.0.0.1"

    @property
    def wfile(self):
        return self

    def write(self, data: bytes) -> None:
        self._chunks.append(data)


class TestAPI(unittest.TestCase):

    def setUp(self):
        reset_repository(cell_size=1.0)

    def _call(self, method: str, path: str, body: dict | None = None, user_id: str = "test-user") -> tuple[int, dict]:
        handler = _MockHandler(method, path, body, user_id=user_id)
        try:
            PolygonServiceHandler._dispatch(handler)
        except ValueError as e:
            api_server._json(handler, 400, {"error": str(e)})
        except Exception:
            api_server._json(handler, 500, {"error": "Внутренняя ошибка сервера"})
        payload = json.loads(b"".join(handler._chunks).decode()) if handler._chunks else {}
        return handler.status, payload

    def _create_polygon(self, name="test", x0=0, y0=0, x1=10, y1=10, user_id="test-user"):
        return self._call("POST", "/polygons", {
            "name": name,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]
                ]
            }
        }, user_id=user_id)

    def test_create_polygon(self):
        status, body = self._create_polygon("my polygon")
        self.assertEqual(status, 201)
        self.assertIn("id", body)
        self.assertEqual(body["name"], "my polygon")

    def test_list_polygons(self):
        self._create_polygon("p1")
        self._create_polygon("p2")
        status, body = self._call("GET", "/polygons")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 2)

    def test_health(self):
        status, body = self._call("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_point_in_polygon_hit(self):
        self._create_polygon("zone")
        status, body = self._call("POST", "/query/point-in-polygon", {
            "point": [5, 5]
        })
        self.assertEqual(status, 200)
        self.assertEqual(body["matching_count"], 1)

    def test_point_in_polygon_miss(self):
        self._create_polygon("zone")
        status, body = self._call("POST", "/query/point-in-polygon", {
            "point": [50, 50]
        })
        self.assertEqual(status, 200)
        self.assertEqual(body["matching_count"], 0)

    def test_missing_geometry(self):
        status, body = self._call("POST", "/polygons", {"name": "no-geom"})
        self.assertEqual(status, 400)

    def test_missing_point(self):
        status, body = self._call("POST", "/query/point-in-polygon", {})
        self.assertEqual(status, 400)

    def test_create_polygon_from_wkt(self):
        status, body = self._call("POST", "/polygons", {
            "name": "wkt-poly",
            "wkt": "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))",
        })
        self.assertEqual(status, 201)
        self.assertIn("wkt", body)
        self.assertIn("geometry", body)
        self.assertEqual(body["geometry"]["type"], "Polygon")

    def test_create_multipolygon(self):
        status, body = self._call("POST", "/polygons", {
            "name": "mp",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[0,0],[1,0],[1,1],[0,1],[0,0]]],
                    [[[5,5],[6,5],[6,6],[5,6],[5,5]]],
                ],
            },
        })
        self.assertEqual(status, 201)
        self.assertEqual(body["geometry"]["type"], "MultiPolygon")

    def test_create_without_geometry_or_wkt(self):
        status, body = self._call("POST", "/polygons", {"name": "x"})
        self.assertEqual(status, 400)

    def test_get_polygon_by_id(self):
        _, created = self._create_polygon("one")
        status, body = self._call("GET", f"/polygons/{created['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(body["name"], "one")

    def test_get_polygon_not_found(self):
        status, body = self._call("GET", "/polygons/no-such-id")
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_update_polygon_name(self):
        _, created = self._create_polygon("old")
        status, body = self._call("PUT", f"/polygons/{created['id']}", {"name": "new"})
        self.assertEqual(status, 200)
        self.assertEqual(body["name"], "new")

    def test_delete_polygon(self):
        _, created = self._create_polygon("gone")
        status, _ = self._call("DELETE", f"/polygons/{created['id']}")
        self.assertEqual(status, 200)
        status, _ = self._call("GET", f"/polygons/{created['id']}")
        self.assertEqual(status, 404)

    def test_stats(self):
        self._create_polygon("a")
        status, body = self._call("GET", "/stats")
        self.assertEqual(status, 200)
        self.assertEqual(body["polygon_count"], 1)
        self.assertEqual(body["index"]["type"], "GridIndex")

    def test_list_trailing_slash(self):
        self._create_polygon("a")
        status, body = self._call("GET", "/polygons/")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)

    def test_options(self):
        status, body = self._call("OPTIONS", "/polygons")
        self.assertEqual(status, 204)
        self.assertEqual(body, {})

    def test_missing_user_id(self):
        status, body = self._call("GET", "/polygons", user_id="")
        self.assertEqual(status, 400)
        self.assertIn("X-User-Id", body["error"])

    def test_user_isolation(self):
        self._create_polygon("dev polygon", user_id="developer")
        status, body = self._call("GET", "/polygons", user_id="other-user")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 0)

    def test_cannot_get_other_users_polygon(self):
        _, created = self._create_polygon("secret", user_id="developer")
        status, body = self._call("GET", f"/polygons/{created['id']}", user_id="other-user")
        self.assertEqual(status, 404)
        self.assertIn("error", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)