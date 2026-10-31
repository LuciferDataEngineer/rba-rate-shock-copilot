"""Load chunk embeddings into Postgres with an HNSW index."""

from __future__ import annotations

import json

import duckdb
import numpy as np

from rba_copilot.paths import REPORTS, TIDY
from rba_copilot.rag.embed import encode, model_name
from rba_copilot.rag.retrieve import connect

EMBEDDINGS = TIDY / "embeddings.npz"


def _chunks() -> list[dict]:
    connection = duckdb.connect()
    path = (TIDY / "chunks.parquet").as_posix().replace("'", "''")
    cursor = connection.execute(f"SELECT * FROM read_parquet('{path}') ORDER BY chunk_id")
    columns = [item[0] for item in cursor.description]
    rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    connection.close()
    return rows


def _load_or_encode(rows: list[dict], refresh: bool) -> np.ndarray:
    ids = [row["chunk_id"] for row in rows]
    if EMBEDDINGS.exists() and not refresh:
        saved = np.load(EMBEDDINGS, allow_pickle=True)
        if list(saved["ids"]) == ids:
            return saved["vectors"]
    vectors = encode([row["embed_text"] for row in rows])
    EMBEDDINGS.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(EMBEDDINGS, ids=np.array(ids), vectors=vectors)
    return vectors


def build_index(refresh_embeddings: bool = False) -> dict:
    rows = _chunks()
    vectors = _load_or_encode(rows, refresh_embeddings)
    if vectors.shape[1] != 384:
        raise SystemExit(f"expected 384 dimensions, got {vectors.shape[1]}")
    connection = connect()
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute("DROP TABLE IF EXISTS chunks")
        cursor.execute(
            """
            CREATE TABLE chunks (
              chunk_id text PRIMARY KEY,
              doc_id text NOT NULL,
              doc_type text,
              title text,
              doc_date date,
              url text,
              section text,
              chunk_text text NOT NULL,
              embedding vector(384) NOT NULL
            )
            """
        )
        cursor.execute(
            """
            ALTER TABLE chunks
            ADD COLUMN tsv tsvector
            GENERATED ALWAYS AS (to_tsvector('english', coalesce(section, '') || ' ' || chunk_text)) STORED
            """
        )
        payload = []
        for row, vector in zip(rows, vectors, strict=True):
            payload.append(
                (
                    row["chunk_id"],
                    row["doc_id"],
                    row["doc_type"],
                    row["title"],
                    row["doc_date"],
                    row["url"],
                    row["section"],
                    row["chunk_text"],
                    vector.tolist(),
                )
            )
        cursor.executemany(
            """
            INSERT INTO chunks (
              chunk_id, doc_id, doc_type, title, doc_date, url, section, chunk_text, embedding
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            payload,
        )
        cursor.execute("CREATE INDEX chunks_tsv ON chunks USING gin (tsv)")
        cursor.execute(
            "CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
        )
    connection.commit()
    connection.close()
    summary = {"chunks": len(rows), "dimensions": int(vectors.shape[1]), "model": model_name()}
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "index_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return summary


def main() -> None:
    build_index()


if __name__ == "__main__":
    main()
