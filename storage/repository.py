import uuid
from dataclasses import dataclass, field
from datetime import datetime

from geometry.types import Point, Polygon
from geometry.algorithms import polygon_contains, PointLocation
from geometry.index import GridIndex


@dataclass
class PolygonRecord:
    """Хранимая запись: полигон + метаданные."""
    id:         str
    name:       str
    polygon:    Polygon
    properties: dict         = field(default_factory=dict)
    created_at: datetime     = field(default_factory=datetime.utcnow)
    updated_at: datetime     = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "name":       self.name,
            "geometry":   self.polygon.to_geojson(),
            "properties": self.properties,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PolygonRepository:

    def __init__(self, index_cell_size: float = 1.0):
        self._store: dict[str, PolygonRecord] = {}
        self._index = GridIndex(cell_size=index_cell_size)

    # CRUD

    def create(self, name: str, polygon: Polygon, properties: dict | None = None) -> PolygonRecord:
        record = PolygonRecord(
            id=str(uuid.uuid4()),
            name=name,
            polygon=polygon,
            properties=properties or {},
        )
        self._store[record.id] = record
        self._index.add(record.id, polygon)
        return record

    def get(self, polygon_id: str) -> PolygonRecord | None:
        return self._store.get(polygon_id)

    def list_all(self) -> list[PolygonRecord]:
        return list(self._store.values())

    def update(
        self,
        polygon_id: str,
        name:       str | None     = None,
        polygon:    Polygon | None = None,
        properties: dict | None    = None,
    ) -> PolygonRecord | None:
        """Частичное обновление — меняются только переданные поля."""
        record = self._store.get(polygon_id)
        if record is None:
            return None

        if name       is not None: record.name       = name
        if properties is not None: record.properties = properties
        if polygon    is not None:
            record.polygon = polygon
            self._index.update(polygon_id, polygon)

        record.updated_at = datetime.utcnow()
        return record

    def delete(self, polygon_id: str) -> bool:
        if polygon_id not in self._store:
            return False
        del self._store[polygon_id]
        self._index.remove(polygon_id)
        return True

    # Пространственный поиск

    def find_containing_point(
        self,
        point:            Point,
        algorithm:        str  = "ray_casting",
        include_boundary: bool = True,
    ) -> list[PolygonRecord]:
        result = []
        for pid in self._index.candidates(point):
            record = self._store.get(pid)
            if record is None:
                continue
            loc = polygon_contains(point, record.polygon, algorithm)
            if loc == PointLocation.INSIDE or (loc == PointLocation.ON_BOUNDARY and include_boundary):
                result.append(record)
        return result

    # Утилиты

    def count(self) -> int:
        return len(self._store)

    def index_stats(self) -> dict:
        return self._index.stats()