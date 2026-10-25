import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
QUERY = """
[out:json][timeout:170];
area["ISO3166-2"="RU-MOW"][admin_level=4]->.m;
rel(area.m)["boundary"="administrative"]["admin_level"="8"];
out geom;
"""
DEFAULT_OUT = Path(__file__).resolve().parent / "data" / "moscow_districts.geojson"


def fetch(url: str) -> dict:
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "dot-service/1.0"})
    with urllib.request.urlopen(req, timeout=200) as resp:
        return json.load(resp)


def stitch_rings(ways: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    pending = [list(w) for w in ways if len(w) >= 2]
    rings = []
    while pending:
        ring = pending.pop()
        while ring[0] != ring[-1]:
            for i, w in enumerate(pending):
                if w[0] == ring[-1]:
                    ring.extend(w[1:])
                elif w[-1] == ring[-1]:
                    ring.extend(reversed(w[:-1]))
                elif w[-1] == ring[0]:
                    ring[:0] = w[:-1]
                elif w[0] == ring[0]:
                    ring[:0] = list(reversed(w[1:]))
                else:
                    continue
                pending.pop(i)
                break
            else:
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def relation_to_geometry(rel: dict) -> dict | None:
    outer, inner = [], []
    for m in rel.get("members", []):
        if m.get("type") != "way" or "geometry" not in m:
            continue
        coords = [(p["lon"], p["lat"]) for p in m["geometry"]]
        (inner if m.get("role") == "inner" else outer).append(coords)
    outers = stitch_rings(outer)
    if not outers:
        return None
    polygons = [[o] for o in outers]
    for hole in stitch_rings(inner):
        hx, hy = hole[0]
        for poly in polygons:
            if point_in_ring(hx, hy, poly[0]):
                poly.append(hole)
                break
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def main():
    p = argparse.ArgumentParser(description="Download Moscow district boundaries from OSM into GeoJSON")
    p.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    p.add_argument("--url", type=str, default=OVERPASS_URL)
    p.add_argument("--input", type=str, default=None, help="raw Overpass JSON instead of downloading")
    args = p.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = fetch(args.url)
    features = []
    for rel in data.get("elements", []):
        if rel.get("type") != "relation":
            continue
        geom = relation_to_geometry(rel)
        if geom is None:
            continue
        tags = rel.get("tags", {})
        features.append({
            "type": "Feature",
            "properties": {"osm_id": rel["id"], "name": tags.get("name", "")},
            "geometry": geom,
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)
    print(f"{len(features)} districts -> {out}")


if __name__ == "__main__":
    main()
