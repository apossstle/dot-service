from dataclasses import dataclass, field


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    @classmethod
    def from_list(cls, coords: list[float]) -> "Point":
        if len(coords) < 2:
            raise ValueError(f"Нужно 2 координаты, получено: {coords}")
        return cls(x=float(coords[0]), y=float(coords[1]))

    def to_list(self) -> list[float]:
        return [self.x, self.y]

    def __repr__(self) -> str:
        return f"Point({self.x}, {self.y})"


@dataclass
class Ring:
    points: list[Point] = field(default_factory=list)

    @classmethod
    def from_coords(cls, coords: list[list[float]]) -> "Ring":
        pts = [Point.from_list(c) for c in coords]
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) < 3:
            raise ValueError("Кольцо должно содержать минимум 3 точки")
        return cls(points=pts)

    def to_coords(self) -> list[list[float]]:
        """Сериализация в GeoJSON (с явным замыканием первая == последняя)."""
        coords = [p.to_list() for p in self.points]
        coords.append(coords[0])
        return coords

    def bounding_box(self) -> tuple[float, float, float, float]:
        """Вернуть (min_x, min_y, max_x, max_y)."""
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def __len__(self) -> int:
        return len(self.points)


@dataclass
class Polygon:
    exterior: Ring
    holes: list[Ring] = field(default_factory=list)

    @classmethod
    def from_geojson(cls, geojson: dict) -> "Polygon":
        if geojson.get("type") == "Feature":
            geojson = geojson["geometry"]

        if geojson.get("type") != "Polygon":
            raise ValueError(
                f"Ожидается тип 'Polygon', получен '{geojson.get('type')}'"
            )

        coords = geojson.get("coordinates")
        if not coords:
            raise ValueError("Пустые координаты полигона")

        return cls(
            exterior=Ring.from_coords(coords[0]),
            holes=[Ring.from_coords(c) for c in coords[1:]],
        )

    def to_geojson(self) -> dict:
        return {
            "type": "Polygon",
            "coordinates": [self.exterior.to_coords()] + [h.to_coords() for h in self.holes],
        }

    def bounding_box(self) -> tuple[float, float, float, float]:
        return self.exterior.bounding_box()

    def has_holes(self) -> bool:
        return bool(self.holes)

    def __repr__(self) -> str:
        return f"Polygon(points={len(self.exterior)}, holes={len(self.holes)})"