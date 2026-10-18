from abc import ABC, abstractmethod

from .types import Point, Geometry


class SpatialIndex(ABC):
    """
    Общий интерфейс пространственного индекса.
    Любая реализация (GridIndex, RTreeIndex, ...) обязана поддерживать эти операции,
    чтобы PolygonRepository мог переключаться между стратегиями без изменения кода.
    """

    @abstractmethod
    def add(self, polygon_id: str, geometry: Geometry) -> None: ...

    @abstractmethod
    def remove(self, polygon_id: str) -> None: ...

    @abstractmethod
    def update(self, polygon_id: str, geometry: Geometry) -> None: ...

    @abstractmethod
    def candidates(self, point: Point) -> list[str]: ...

    @abstractmethod
    def size(self) -> int: ...

    @abstractmethod
    def stats(self) -> dict: ...
