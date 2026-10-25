import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geometry.types import Point, geometry_from_geojson
from geometry.index import GridIndex
from geometry.rtree_index import RTreeIndex
from benchmarks.bench_index import benchmark, print_table, save_csv

DEFAULT_DATA = Path(__file__).resolve().parent / "data" / "moscow_districts.geojson"


def load_polygons(path: str):
    with open(path, encoding="utf-8") as f:
        fc = json.load(f)
    return [(str(feat["properties"]["osm_id"]), geometry_from_geojson(feat)) for feat in fc["features"]]


def total_bounds(polygons):
    boxes = [g.bounding_box() for _, g in polygons]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def main():
    p = argparse.ArgumentParser(description="Compare GridIndex vs RTreeIndex on Moscow districts")
    p.add_argument("--data", type=str, default=str(DEFAULT_DATA))
    p.add_argument("-q", "--queries", type=int, default=10_000)
    p.add_argument("--cell-size", type=float, default=0.05, help="GridIndex cell size in degrees")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=str, default=None)
    args = p.parse_args()

    polygons = load_polygons(args.data)
    x0, y0, x1, y1 = total_bounds(polygons)
    rng = random.Random(args.seed)
    points = [Point(rng.uniform(x0, x1), rng.uniform(y0, y1)) for _ in range(args.queries)]

    print(f"\nBenchmark: Moscow districts N={len(polygons)}, Q={args.queries}, "
          f"cell_size={args.cell_size}, seed={args.seed}\n")

    results = {
        "GridIndex": benchmark(GridIndex(cell_size=args.cell_size), polygons, points),
        "RTreeIndex": benchmark(RTreeIndex(), polygons, points),
    }
    print_table(results)

    rtree_q = results["RTreeIndex"]["query_ms"]
    if rtree_q > 0:
        print(f"\nQuery speedup (grid / rtree): {results['GridIndex']['query_ms'] / rtree_q:.2f}x")

    if args.out:
        params = {"dataset": "moscow", "n": len(polygons), "q": args.queries,
                  "cell_size": args.cell_size, "seed": args.seed}
        save_csv(args.out, params, results)
        print(f"\nraw data: {args.out}")


if __name__ == "__main__":
    main()
