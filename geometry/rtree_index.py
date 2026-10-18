import itertools

from rtree import index as _rtree

from .types import Point, Geometry
from .spatial_index import SpatialIndex


class RTreeIndex(SpatialIndex):
    """
    Пространственный индекс на основе R-Tree (библиотека rtree поверх libspatialindex).
    Запрос кандидатов за O(log N), устойчив к неравномерному распределению и
    разноразмерным полигонам — в отличие от GridIndex.
    """

    def __init__(self):
        self._tree = _rtree.Index()
        self._bboxes: dict[str, tuple[float, float, float, float]] = {}
        self._str_to_int: dict[str, int] = {}
        self._int_to_str: dict[int, str] = {}
        self._next_int_id = itertools.count()

    def add(self, polygon_id: str, geometry: Geometry) -> None:
        bbox = geometry.bounding_box()
        int_id = next(self._next_int_id)
        self._bboxes[polygon_id] = bbox
        self._str_to_int[polygon_id] = int_id
        self._int_to_str[int_id] = polygon_id
        self._tree.insert(int_id, bbox)

    def remove(self, polygon_id: str) -> None:
        int_id = self._str_to_int.pop(polygon_id, None)
        if int_id is None:
            return
        bbox = self._bboxes.pop(polygon_id)
        del self._int_to_str[int_id]
        self._tree.delete(int_id, bbox)

    def update(self, polygon_id: str, geometry: Geometry) -> None:
        self.remove(polygon_id)
        self.add(polygon_id, geometry)

    def candidates(self, point: Point) -> list[str]:
        px, py = point.x, point.y
        return [self._int_to_str[int_id] for int_id in self._tree.intersection((px, py, px, py))]

    def size(self) -> int:
        return len(self._bboxes)

    def stats(self) -> dict:
        return {
            "type": "RTreeIndex",
            "polygon_count": self.size(),
        }
