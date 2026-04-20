import sys
import os
import json
import unittest
import io
from http.client import HTTPResponse
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometry.types import Point, Ring, Polygon
from geometry.algorithms import (
    ray_casting, winding_number, polygon_contains,
    PointLocation, bbox_contains_point
)
from geometry.index import BoundingBoxIndex, GridIndex
from storage.repository import PolygonRepository



# Фикстуры


def make_square(x0=0, y0=0, x1=1, y1=1) -> Polygon:
    """Создать прямоугольник как полигон."""
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


#  Тесты типов

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
            Point.from_list([1.0])  # только одна координата


class TestRingClass(unittest.TestCase):

    def test_create_from_coords(self):
        ring = Ring.from_coords([[0,0],[1,0],[1,1],[0,1],[0,0]])
        # GeoJSON-замыкание убирается, должно быть 4 точки
        self.assertEqual(len(ring), 4)

    def test_too_few_points(self):
        with self.assertRaises(ValueError):
            Ring.from_coords([[0,0],[1,0],[0,0]])  # только 2 уникальные точки

    def test_bounding_box(self):
        ring = Ring(points=[Point(1,2), Point(3,2), Point(3,5), Point(1,5)])
        bbox = ring.bounding_box()
        self.assertEqual(bbox, (1, 2, 3, 5))

    def test_to_coords_closes_ring(self):
        ring = Ring(points=[Point(0,0), Point(1,0), Point(1,1)])
        coords = ring.to_coords()
        self.assertEqual(coords[0], coords[-1])  # первая == последняя


class TestPolygonClass(unittest.TestCase):

    def test_geojson_roundtrip(self):
        """Полигон → GeoJSON → Полигон должен дать тот же результат."""
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
        """GeoJSON Feature должен распознаваться и парситься."""
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]
            }
        }
        poly = Polygon.from_geojson(feature)
        self.assertEqual(len(poly.exterior), 4)


#  Тесты алгоритмов

class _AlgorithmMixin:
    """
    Базовый миксин для тестирования алгоритмов PIP.
    Оба алгоритма (Ray Casting и Winding Number) должны давать одинаковые результаты.
    """

    def _check(self, point: Point, ring: Ring) -> PointLocation:
        raise NotImplementedError

    def setUp(self):
        self.square = make_square(0, 0, 4, 4)
        self.ring = self.square.exterior

    # ── Базовые случаи ──

    def test_point_clearly_inside(self):
        result = self._check(Point(2, 2), self.ring)
        self.assertEqual(result, PointLocation.INSIDE)

    def test_point_clearly_outside(self):
        result = self._check(Point(10, 10), self.ring)
        self.assertEqual(result, PointLocation.OUTSIDE)

    def test_point_outside_negative(self):
        result = self._check(Point(-1, 2), self.ring)
        self.assertEqual(result, PointLocation.OUTSIDE)

    # Граничные случаи 

    def test_point_on_edge(self):
        """Точка на середине ребра → ON_BOUNDARY."""
        result = self._check(Point(2, 0), self.ring)  # нижнее ребро
        self.assertEqual(result, PointLocation.ON_BOUNDARY)

    def test_point_on_vertex(self):
        """Точка в вершине → ON_BOUNDARY."""
        result = self._check(Point(0, 0), self.ring)
        self.assertEqual(result, PointLocation.ON_BOUNDARY)

    def test_point_on_top_edge(self):
        """Точка на верхнем ребре."""
        result = self._check(Point(2, 4), self.ring)
        self.assertEqual(result, PointLocation.ON_BOUNDARY)

    def test_point_just_inside(self):
        """Точка почти на границе, но внутри."""
        result = self._check(Point(0.001, 0.001), self.ring)
        self.assertEqual(result, PointLocation.INSIDE)

    def test_point_just_outside(self):
        """Точка почти на границе, но снаружи."""
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
        """Точка в «мясе» полигона с отверстием → INSIDE."""
        result = polygon_contains(Point(0.5, 0.5), self.square_with_hole)
        self.assertEqual(result, PointLocation.INSIDE)

    def test_inside_hole(self):
        """Точка в отверстии → OUTSIDE (снаружи реального полигона)."""
        result = polygon_contains(Point(2, 2), self.square_with_hole)
        self.assertEqual(result, PointLocation.OUTSIDE)

    def test_on_outer_boundary(self):
        result = polygon_contains(Point(2, 0), self.square_with_hole)
        self.assertEqual(result, PointLocation.ON_BOUNDARY)

    def test_on_hole_boundary(self):
        """Точка на границе отверстия → ON_BOUNDARY."""
        result = polygon_contains(Point(2, 1), self.square_with_hole)
        self.assertEqual(result, PointLocation.ON_BOUNDARY)

    def test_both_algorithms_agree(self):
        """Ray Casting и Winding Number должны давать одинаковые результаты."""
        test_points = [
            Point(2, 2), Point(0.5, 0.5), Point(5, 5),
            Point(2, 0), Point(0, 0), Point(2, 1)
        ]
        for p in test_points:
            rc = polygon_contains(p, self.square_with_hole, "ray_casting")
            wn = polygon_contains(p, self.square_with_hole, "winding_number")
            self.assertEqual(rc, wn, f"Алгоритмы расходятся для точки {p}")


class TestBboxContainsPoint(unittest.TestCase):

    def test_inside_bbox(self):
        self.assertTrue(bbox_contains_point((0, 0, 10, 10), Point(5, 5)))

    def test_outside_bbox(self):
        self.assertFalse(bbox_contains_point((0, 0, 10, 10), Point(15, 5)))

    def test_on_bbox_boundary(self):
        self.assertTrue(bbox_contains_point((0, 0, 10, 10), Point(0, 5)))
        self.assertTrue(bbox_contains_point((0, 0, 10, 10), Point(10, 10)))


# Тесты индексов

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
        # Перемещаем полигон p1 в другое место
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


#  Тесты репозитория

class TestRepository(unittest.TestCase):

    def setUp(self):
        self.repo = PolygonRepository(index_cell_size=1.0)
        self.poly = make_square(0, 0, 10, 10)

    def test_create_and_get(self):
        record = self.repo.create("test", self.poly)
        fetched = self.repo.get(record.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "test")

    def test_get_nonexistent(self):
        result = self.repo.get("nonexistent-id")
        self.assertIsNone(result)

    def test_list_all(self):
        self.repo.create("poly1", make_square(0, 0, 5, 5))
        self.repo.create("poly2", make_square(10, 10, 15, 15))
        self.assertEqual(self.repo.count(), 2)
        self.assertEqual(len(self.repo.list_all()), 2)

    def test_update(self):
        record = self.repo.create("old name", self.poly)
        updated = self.repo.update(record.id, name="new name")
        self.assertEqual(updated.name, "new name")
        self.assertEqual(self.repo.get(record.id).name, "new name")

    def test_delete(self):
        record = self.repo.create("to delete", self.poly)
        result = self.repo.delete(record.id)
        self.assertTrue(result)
        self.assertIsNone(self.repo.get(record.id))

    def test_delete_nonexistent(self):
        result = self.repo.delete("no-such-id")
        self.assertFalse(result)

    def test_find_containing_point_inside(self):
        self.repo.create("big square", make_square(0, 0, 10, 10))
        results = self.repo.find_containing_point(Point(5, 5))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "big square")

    def test_find_containing_point_outside(self):
        self.repo.create("square", make_square(0, 0, 10, 10))
        results = self.repo.find_containing_point(Point(20, 20))
        self.assertEqual(len(results), 0)

    def test_find_multiple_matching(self):
        """Точка может попасть в несколько перекрывающихся полигонов."""
        self.repo.create("large", make_square(0, 0, 10, 10))
        self.repo.create("small", make_square(3, 3, 7, 7))
        results = self.repo.find_containing_point(Point(5, 5))
        self.assertEqual(len(results), 2)

    def test_find_with_boundary_excluded(self):
        self.repo.create("square", make_square(0, 0, 10, 10))
        # Точка на границе
        results = self.repo.find_containing_point(
            Point(5, 0), include_boundary=False
        )
        self.assertEqual(len(results), 0)

    def test_properties_stored(self):
        props = {"region": "Moscow", "zone": "A"}
        record = self.repo.create("zone", self.poly, properties=props)
        self.assertEqual(self.repo.get(record.id).properties, props)

    def test_index_stats(self):
        self.repo.create("p1", make_square(0, 0, 5, 5))
        stats = self.repo.index_stats()
        self.assertIn("polygon_count", stats)
        self.assertEqual(stats["polygon_count"], 1)


#  Интеграционные тесты API (без сети)

class TestAPI(unittest.TestCase):
    """
    Тесты HTTP API через прямой вызов обработчиков.
    Создаём мок-объект handler вместо настоящего HTTP-соединения.
    """

    def setUp(self):
        import api.server as srv
        srv.reset_repository(cell_size=1.0)
        self.srv = srv

    def _make_handler(self, method: str, path: str, body: dict = None) -> tuple:
        """
        Создать мок-хендлер и захватить JSON-ответ.
        Возвращает (status_code, response_body).
        """
        handler = MagicMock()
        handler.command = method
        handler.path = path

        # Настраиваем тело запроса
        if body:
            raw = json.dumps(body).encode()
            handler.rfile = io.BytesIO(raw)
            handler.headers = {"Content-Length": str(len(raw))}
        else:
            handler.rfile = io.BytesIO(b"")
            handler.headers = {"Content-Length": "0"}

        # Захватываем отправленный ответ
        response_data = {"status": None, "body": None}
        raw_body_parts = []

        def send_response(code):
            response_data["status"] = code

        def wfile_write(data):
            raw_body_parts.append(data)

        handler.send_response = send_response
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()
        handler.wfile.write = wfile_write
        handler.address_string = lambda: "127.0.0.1"
        handler.log_date_time_string = lambda: "test"

        return handler, response_data, raw_body_parts

    def _call(self, method: str, path: str, body: dict = None) -> tuple:
        handler, response_data, raw_parts = self._make_handler(method, path, body)

        try:
            if method == "POST" and path == "/polygons":
                self.srv.handle_create(handler)
            elif method == "GET" and path == "/polygons":
                self.srv.handle_list(handler)
            elif method == "GET" and path == "/health":
                self.srv.handle_health(handler)
            elif method == "POST" and path == "/query/point-in-polygon":
                self.srv.handle_pip(handler)
            else:
                raise ValueError(f"Не знаю как обработать {method} {path} в тестах")
        except ValueError as e:
            # Воспроизводим поведение _handle: ValueError → 400
            self.srv._json(handler, 400, {"error": str(e)})

        status = response_data["status"]
        if raw_parts:
            body_json = json.loads(b"".join(raw_parts).decode())
        else:
            body_json = {}
        return status, body_json

    def _create_polygon(self, name="test", x0=0, y0=0, x1=10, y1=10):
        return self._call("POST", "/polygons", {
            "name": name,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]
                ]
            }
        })

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


if __name__ == "__main__":
    # Запуск с подробным выводом
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestPointClass, TestRingClass, TestPolygonClass,
        TestRayCasting, TestWindingNumber, TestPolygonContains,
        TestBboxContainsPoint,
        TestBoundingBoxIndex, TestGridIndex,
        TestRepository,
        TestAPI,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)