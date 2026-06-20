import math
from .types import Point, Geometry


class BoundingBoxIndex:

    def __init__(self):
        self._bboxes: dict[str, tuple[float, float, float, float]] = {}

    def add(self, polygon_id: str, geometry: Geometry) -> None:
        self._bboxes[polygon_id] = geometry.bounding_box()

    def remove(self, polygon_id: str) -> None:
        self._bboxes.pop(polygon_id, None)

    def update(self, polygon_id: str, geometry: Geometry) -> None:
        self.remove(polygon_id)
        self.add(polygon_id, geometry)

    def candidates(self, point: Point) -> list[str]:
        px, py = point.x, point.y
        return [
            pid for pid, (x0, y0, x1, y1) in self._bboxes.items()
            if x0 <= px <= x1 and y0 <= py <= y1
        ]

    def size(self) -> int:
        return len(self._bboxes)

    def stats(self) -> dict:
        return {"type": "BoundingBoxIndex", "polygon_count": self.size()}


class GridIndex(BoundingBoxIndex):

    def __init__(self, cell_size: float = 1.0):
        super().__init__()
        self._cell_size = cell_size
        self._grid: dict[tuple[int, int], set[str]] = {}

    def _to_cell(self, x: float, y: float) -> tuple[int, int]:
        return (math.floor(x / self._cell_size), math.floor(y / self._cell_size))

    def _bbox_cells(self, x0: float, y0: float, x1: float, y1: float) -> list[tuple[int, int]]:
        cx0, cy0 = self._to_cell(x0, y0)
        cx1, cy1 = self._to_cell(x1, y1)
        return [(gx, gy) for gx in range(cx0, cx1 + 1) for gy in range(cy0, cy1 + 1)]

    def add(self, polygon_id: str, geometry: Geometry) -> None:
        super().add(polygon_id, geometry)
        for cell in self._bbox_cells(*geometry.bounding_box()):
            self._grid.setdefault(cell, set()).add(polygon_id)

    def remove(self, polygon_id: str) -> None:
        bbox = self._bboxes.get(polygon_id)
        if bbox is None:
            return
        for cell in self._bbox_cells(*bbox):
            ids = self._grid.get(cell)
            if ids is None:
                continue
            ids.discard(polygon_id)
            if not ids:
                del self._grid[cell]
        super().remove(polygon_id)

    def update(self, polygon_id: str, geometry: Geometry) -> None:
        self.remove(polygon_id)
        self.add(polygon_id, geometry)

    def candidates(self, point: Point) -> list[str]:
        cell = self._to_cell(point.x, point.y)
        px, py = point.x, point.y
        result = []
        for pid in self._grid.get(cell, ()):
            x0, y0, x1, y1 = self._bboxes[pid]
            if x0 <= px <= x1 and y0 <= py <= y1:
                result.append(pid)
        return result

    def stats(self) -> dict:
        occupied = len(self._grid)
        total = sum(len(ids) for ids in self._grid.values())
        return {
            "type": "GridIndex",
            "cell_size": self._cell_size,
            "polygon_count": self.size(),
            "occupied_cells": occupied,
            "avg_polygons_per_cell": round(total / occupied, 2) if occupied else 0,
        }
