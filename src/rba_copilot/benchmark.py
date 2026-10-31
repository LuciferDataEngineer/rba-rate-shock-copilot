"""Latency and recall of exact search, pgvector HNSW and DuckDB VSS.

The real corpus is a couple of thousand chunks, which is too small to separate
the engines. The timed index repeats those real vectors with a little noise so
the comparison is about index behaviour, still at a $0 local cost.
"""

from __future__ import annotations

import json
import time

import numpy as np

from rba_copilot.paths import REPORTS, TIDY

SCALE = 8_000
QUERIES = 25
SEED = 7


def _load_vectors() -> np.ndarray:
    saved = np.load(TIDY / "embeddings.npz")
    return np.asarray(saved["vectors"], dtype=np.float32)


def _scale(vectors: np.ndarray, n: int) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    repeats = int(np.ceil(n / len(vectors)))
    tiled = np.vstack([vectors + rng.normal(0, 0.01, vectors.shape).astype(np.float32) for _ in range(repeats)])
    tiled = tiled[:n]
    norms = np.linalg.norm(tiled, axis=1, keepdims=True)
    return tiled / np.clip(norms, 1e-8, None)


def _exact_topk(matrix: np.ndarray, queries: np.ndarray, k: int = 10) -> np.ndarray:
    scores = queries @ matrix.T
    return np.argpartition(-scores, kth=k - 1, axis=1)[:, :k]


def _recall(approx: np.ndarray, exact: np.ndarray) -> float:
    hits = 0
    total = 0
    for left, right in zip(approx, exact, strict=True):
        hits += len(set(left.tolist()) & set(right.tolist()))
        total += len(right)
    return hits / total if total else 0.0


def _time_call(fn, repeats: int = 5) -> dict:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {"p50_ms": round(samples[len(samples) // 2], 3), "p95_ms": round(samples[max(int(len(samples) * 0.95) - 1, 0)], 3)}


def _duckdb_vss(matrix: np.ndarray, queries: np.ndarray) -> dict | None:
    try:
        import duckdb
    except ImportError:
        return None
    try:
        connection = duckdb.connect()
        connection.execute("INSTALL vss; LOAD vss;")
        connection.execute("SET hnsw_enable_experimental_persistence = true")
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    start = time.perf_counter()
    connection.execute("CREATE TABLE vecs (id INTEGER, embedding FLOAT[384])")
    connection.executemany("INSERT INTO vecs VALUES (?, ?)", [(i, row.tolist()) for i, row in enumerate(matrix)])
    connection.execute("CREATE INDEX vecs_hnsw ON vecs USING HNSW (embedding) WITH (metric = 'cosine')")
    build_s = time.perf_counter() - start
    exact = _exact_topk(matrix, queries)
    approx = []

    def search_once() -> None:
        approx.clear()
        for query in queries:
            rows = connection.execute(
                """
                SELECT id FROM vecs
                ORDER BY array_cosine_distance(embedding, ?::FLOAT[384])
                LIMIT 10
                """,
                [query.tolist()],
            ).fetchall()
            approx.append([row[0] for row in rows])

    timing = _time_call(search_once, repeats=3)
    return {
        "available": True,
        "build_seconds": round(build_s, 3),
        "latency": timing,
        "recall_at_10": round(_recall(np.array(approx), exact), 4),
    }


def _pgvector(matrix: np.ndarray, queries: np.ndarray) -> dict | None:
    try:
        from rba_copilot.rag.retrieve import connect
    except ImportError:
        return None
    try:
        connection = connect()
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    start = time.perf_counter()
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute("DROP TABLE IF EXISTS bench_vecs")
        cursor.execute("CREATE TABLE bench_vecs (id integer PRIMARY KEY, embedding vector(384))")
        cursor.executemany(
            "INSERT INTO bench_vecs VALUES (%s, %s)",
            [(i, row.tolist()) for i, row in enumerate(matrix)],
        )
        cursor.execute("CREATE INDEX bench_hnsw ON bench_vecs USING hnsw (embedding vector_cosine_ops)")
    connection.commit()
    build_s = time.perf_counter() - start
    exact = _exact_topk(matrix, queries)
    approx: list[list[int]] = []

    def search_once() -> None:
        approx.clear()
        with connection.cursor() as cursor:
            for query in queries:
                cursor.execute(
                    "SELECT id FROM bench_vecs ORDER BY embedding <=> %s::vector LIMIT 10",
                    (query.tolist(),),
                )
                approx.append([row[0] for row in cursor.fetchall()])

    timing = _time_call(search_once, repeats=3)
    connection.close()
    return {
        "available": True,
        "build_seconds": round(build_s, 3),
        "latency": timing,
        "recall_at_10": round(_recall(np.array(approx), exact), 4),
    }


def run_benchmark(n: int = SCALE) -> dict:
    base = _load_vectors()
    matrix = _scale(base, n)
    rng = np.random.default_rng(SEED + 1)
    queries = matrix[rng.choice(n, size=QUERIES, replace=False)]
    exact = _exact_topk(matrix, queries)

    def numpy_search() -> None:
        _exact_topk(matrix, queries)

    numpy_latency = _time_call(numpy_search, repeats=5)
    report = {
        "cost_aud": 0,
        "note": "All engines ran locally. No paid vector database and no cloud warehouse.",
        "real_chunks": int(len(base)),
        "scaled_vectors": n,
        "queries": QUERIES,
        "dimensions": int(base.shape[1]),
        "numpy_exact": {"latency": numpy_latency, "recall_at_10": 1.0, "neighbours": exact.shape[1]},
        "pgvector_hnsw": _pgvector(matrix, queries),
        "duckdb_vss_hnsw": _duckdb_vss(matrix, queries),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    destination = REPORTS / "benchmark.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("real_chunks", "scaled_vectors", "numpy_exact", "pgvector_hnsw", "duckdb_vss_hnsw")}, indent=2))
    return report


def main() -> None:
    run_benchmark()


if __name__ == "__main__":
    main()
