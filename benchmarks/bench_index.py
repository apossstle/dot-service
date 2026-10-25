import argparse
import csv
import gc
import os
import random
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geometry.types import Point, Ring, Polygon
from geometry.index import GridIndex
from geometry.rtree_index import RTreeIndex


BOUNDS = (0.0, 0.0, 1000.0, 1000.0)
_proc = psutil.Process(os.getpid())


def gen_synthetic_polygons(n: int, min_size: float, max_size: float, seed: int):
    rng = random.Random(seed)
    polygons = []
    x0, y0, x1, y1 = BOUNDS
    for i in range(n):
        cx = rng.uniform(x0, x1 - max_size)
        cy = rng.uniform(y0, y1 - max_size)
        w = rng.uniform(min_size, max_size)
        h = rng.uniform(min_size, max_size)
        ring = Ring(points=[Point(cx, cy), Point(cx + w, cy), Point(cx + w, cy + h), Point(cx, cy + h)])
        polygons.append((f"p{i}", Polygon(exterior=ring)))
    return polygons


def gen_query_points(count: int, seed: int):
    rng = random.Random(seed)
    x0, y0, x1, y1 = BOUNDS
    return [Point(rng.uniform(x0, x1), rng.uniform(y0, y1)) for _ in range(count)]


def _rss_kb() -> float:
    return _proc.memory_info().rss / 1024


def benchmark(index, polygons, points) -> dict:
    gc.collect()
    rss_before = _rss_kb()

    t0 = time.perf_counter()
    for pid, poly in polygons:
        index.add(pid, poly)
    build_s = time.perf_counter() - t0

    gc.collect()
    rss_after_build = _rss_kb()

    t0 = time.perf_counter()
    total_candidates = 0
    for pt in points:
        total_candidates += len(index.candidates(pt))
    query_s = time.perf_counter() - t0

    return {
        "build_ms": build_s * 1000,
        "query_ms": query_s * 1000,
        "query_us_per_point": (query_s / len(points)) * 1_000_000,
        "query_per_sec": len(points) / query_s if query_s > 0 else float("inf"),
        "mem_delta_kb": rss_after_build - rss_before,
        "avg_candidates": total_candidates / len(points),
    }


def print_table(results: dict):
    header = f"{'Index':<12} {'build (ms)':>12} {'query (ms)':>12} {'µs/point':>10} {'q/sec':>10} {'mem (KB)':>10} {'avg cand':>10}"
    print(header)
    print("-" * len(header))
    for name, r in results.items():
        print(
            f"{name:<12} "
            f"{r['build_ms']:>12.2f} "
            f"{r['query_ms']:>12.2f} "
            f"{r['query_us_per_point']:>10.2f} "
            f"{r['query_per_sec']:>10.0f} "
            f"{r['mem_delta_kb']:>10.1f} "
            f"{r['avg_candidates']:>10.2f}"
        )


def save_csv(path: str, params: dict, results: dict):
    row_keys = ["build_ms", "query_ms", "query_us_per_point", "query_per_sec", "mem_delta_kb", "avg_candidates"]
    param_keys = list(params.keys())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(param_keys + ["index"] + row_keys)
        for name, r in results.items():
            writer.writerow([params[k] for k in param_keys] + [name] + [r[k] for k in row_keys])


def main():
    p = argparse.ArgumentParser(description="Compare GridIndex vs RTreeIndex on synthetic polygons")
    p.add_argument("-n", "--polygons", type=int, default=1000, help="number of polygons to insert")
    p.add_argument("-q", "--queries", type=int, default=10_000, help="number of point-in-polygon queries")
    p.add_argument("--cell-size", type=float, default=20.0, help="GridIndex cell size")
    p.add_argument("--min-size", type=float, default=1.0, help="minimum polygon side")
    p.add_argument("--max-size", type=float, default=20.0, help="maximum polygon side")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=str, default=None, help="optional CSV output path")
    args = p.parse_args()

    polygons = gen_synthetic_polygons(args.polygons, args.min_size, args.max_size, args.seed)
    points = gen_query_points(args.queries, args.seed + 1)

    print(f"\nBenchmark: N={args.polygons} polygons, Q={args.queries} queries, "
          f"size={args.min_size}-{args.max_size}, cell_size={args.cell_size}, seed={args.seed}\n")

    results = {
        "GridIndex": benchmark(GridIndex(cell_size=args.cell_size), polygons, points),
        "RTreeIndex": benchmark(RTreeIndex(), polygons, points),
    }
    print_table(results)

    grid_q = results["GridIndex"]["query_ms"]
    rtree_q = results["RTreeIndex"]["query_ms"]
    if rtree_q > 0:
        print(f"\nQuery speedup (grid / rtree): {grid_q / rtree_q:.2f}x")

    if args.out:
        params = {
            "n": args.polygons, "q": args.queries, "cell_size": args.cell_size,
            "min_size": args.min_size, "max_size": args.max_size, "seed": args.seed,
        }
        save_csv(args.out, params, results)
        print(f"\nraw data: {args.out}")


if __name__ == "__main__":
    main()
