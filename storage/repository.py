import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from geometry.types import Point, Polygon, MultiPolygon, Geometry
from geometry.algorithms import geometry_contains, PointLocation
from geometry.index import GridIndex


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PolygonRecord:
    id: str
    name: str
    geometry: Geometry
    owner_id: str
    properties: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "owner_id": self.owner_id,
            "geometry": self.geometry.to_geojson(),
            "properties": self.properties,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PolygonRepository:

    def __init__(self, index_cell_size: float = 1.0):
        self._store: dict[str, PolygonRecord] = {}
        self._index = GridIndex(cell_size=index_cell_size)

    def create(
        self,
        name: str,
        geometry: Geometry,
        owner_id: str,
        properties: dict | None = None,
    ) -> PolygonRecord:
        record = PolygonRecord(
            id=str(uuid.uuid4()),
            name=name,
            geometry=geometry,
            owner_id=owner_id,
            properties=properties or {},
        )
        self._store[record.id] = record
        self._index.add(record.id, geometry)
        return record

    def get(self, polygon_id: str) -> PolygonRecord | None:
        return self._store.get(polygon_id)

    def list_all(self) -> list[PolygonRecord]:
        return list(self._store.values())

    def list_by_owner(self, owner_id: str) -> list[PolygonRecord]:
        return [record for record in self._store.values() if record.owner_id == owner_id]

    def count_by_owner(self, owner_id: str) -> int:
        return sum(1 for record in self._store.values() if record.owner_id == owner_id)

    def update(
        self,
        polygon_id: str,
        name: str | None = None,
        geometry: Geometry | None = None,
        properties: dict | None = None,
    ) -> PolygonRecord | None:
        record = self._store.get(polygon_id)
        if record is None:
            return None

        if name is not None:
            record.name = name
        if properties is not None:
            record.properties = properties
        if geometry is not None:
            record.geometry = geometry
            self._index.update(polygon_id, geometry)

        record.updated_at = _now()
        return record

    def delete(self, polygon_id: str) -> bool:
        if polygon_id not in self._store:
            return False
        del self._store[polygon_id]
        self._index.remove(polygon_id)
        return True

    def find_containing_point(
        self,
        point: Point,
        owner_id: str,
        algorithm: str = "ray_casting",
        include_boundary: bool = True,
    ) -> list[PolygonRecord]:
        result = []
        for pid in self._index.candidates(point):
            record = self._store.get(pid)
            if record is None or record.owner_id != owner_id:
                continue
            loc = geometry_contains(point, record.geometry, algorithm)
            if loc == PointLocation.INSIDE or (loc == PointLocation.ON_BOUNDARY and include_boundary):
                result.append(record)
        return result

    def count(self) -> int:
        return len(self._store)

    def index_stats(self) -> dict:
        return self._index.stats()
