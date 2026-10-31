"""Hybrid retrieval: Postgres full text, pgvector, and reciprocal rank fusion."""

from __future__ import annotations

import os
import re
from collections import defaultdict

STOP = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "from",
    "this",
    "have",
    "has",
    "was",
    "were",
    "are",
    "what",
    "when",
    "why",
    "how",
    "did",
    "does",
    "about",
    "into",
    "its",
    "their",
    "been",
    "than",
    "per",
    "cent",
    "board",
    "cash",
    "rate",
    "target",
    "increase",
    "increased",
    "inflation",
    "decision",
    "statement",
    "reserve",
    "bank",
    "monetary",
    "policy",
    "australia",
    "australian",
    "financial",
    "conditions",
    "economic",
    "expected",
    "meeting",
}

MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)

RRF_K = 60


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://rba:rba@localhost:5432/rba")


def connect():
    import psycopg
    from pgvector.psycopg import register_vector

    connection = psycopg.connect(database_url())
    connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
    connection.commit()
    register_vector(connection)
    return connection


BM25_STOP = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "from",
    "this",
    "have",
    "has",
    "was",
    "were",
    "are",
    "what",
    "when",
    "why",
    "how",
    "did",
    "does",
    "about",
    "into",
    "its",
    "their",
    "been",
    "than",
    "per",
    "cent",
}


def query_terms(question: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", question.lower())
    terms = []
    for word in words:
        if len(word) < 3 or word in BM25_STOP:
            continue
        if word not in terms:
            terms.append(word)
    return terms


def distinctive_tokens(question: str) -> list[str]:
    """Numbers, months and less common words. These separate one decision from another."""
    tokens: list[str] = []
    for number in re.findall(r"\d+\.\d+|\d{4}", question):
        if number not in tokens:
            tokens.append(number)
    lower = question.lower()
    for month in MONTHS:
        if re.search(rf"\b{month}\b", lower) and month not in tokens:
            tokens.append(month)
    for word in query_terms(question):
        if word in STOP or len(word) < 5:
            continue
        if word not in tokens:
            tokens.append(word)
    return tokens[:10]


def _rows_to_dicts(cursor) -> list[dict]:
    columns = [item.name for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def search_bm25(connection, question: str, limit: int = 20) -> list[dict]:
    terms = query_terms(question)
    if not terms:
        return []
    tsquery = " | ".join(terms)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT chunk_id, doc_id, title, doc_date::text AS doc_date, url, section, chunk_text,
                   ts_rank_cd(tsv, to_tsquery('english', %s)) AS score
            FROM chunks
            WHERE tsv @@ to_tsquery('english', %s)
            ORDER BY score DESC
            LIMIT %s
            """,
            (tsquery, tsquery, limit),
        )
        return _rows_to_dicts(cursor)


def _token_weight(token: str) -> int:
    if re.fullmatch(r"\d+\.\d+", token):
        return 5
    if token in MONTHS:
        return 3
    if re.fullmatch(r"\d{4}", token):
        return 1
    return 2


def search_overlap(connection, question: str, limit: int = 30) -> list[dict]:
    tokens = distinctive_tokens(question)
    if not tokens:
        return []
    weights = [_token_weight(token) for token in tokens]
    years = [token for token in tokens if re.fullmatch(r"\d{4}", token)]
    score_parts = [
        f"(CASE WHEN position(%s in haystack) > 0 THEN {weight} ELSE 0 END)" for weight in weights
    ]
    score_parts.extend(
        "(CASE WHEN to_char(doc_date, 'YYYY') = %s THEN 4 ELSE 0 END)" for _ in years
    )
    score_sql = " + ".join(score_parts)
    where_sql = " OR ".join("position(%s in haystack) > 0" for _ in tokens)
    params: list = [token.lower() for token in tokens]
    params.extend(years)
    params.extend(token.lower() for token in tokens)
    params.append(limit)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH hay AS (
              SELECT chunk_id, doc_id, title, doc_date, url, section, chunk_text,
                     lower(
                       chunk_text || ' ' || coalesce(title, '') || ' ' ||
                       to_char(doc_date, 'YYYY FMMonth')
                     ) AS haystack
              FROM chunks
            )
            SELECT chunk_id, doc_id, title, doc_date::text AS doc_date, url, section, chunk_text,
                   ({score_sql})::float AS score
            FROM hay
            WHERE {where_sql}
            ORDER BY score DESC, doc_date DESC
            LIMIT %s
            """,
            params,
        )
        return _rows_to_dicts(cursor)


def search_vector(connection, vector: list[float], limit: int = 20) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT chunk_id, doc_id, title, doc_date::text AS doc_date, url, section, chunk_text,
                   1 - (embedding <=> %s::vector) AS score
            FROM chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vector, vector, limit),
        )
        return _rows_to_dicts(cursor)


def reciprocal_rank_fusion(*rankings: list[dict], k: int = RRF_K, limit: int = 20) -> list[dict]:
    scores: dict[str, float] = defaultdict(float)
    records: dict[str, dict] = {}
    for ranking in rankings:
        for rank, row in enumerate(ranking, start=1):
            scores[row["chunk_id"]] += 1.0 / (k + rank)
            records[row["chunk_id"]] = row
    ordered = sorted(scores, key=scores.get, reverse=True)
    fused = []
    for chunk_id in ordered[:limit]:
        row = dict(records[chunk_id])
        row["score"] = scores[chunk_id]
        fused.append(row)
    return fused


def fuse_documents(
    bm25_rows: list[dict],
    dense_rows: list[dict],
    overlap_rows: list[dict],
    limit: int = 15,
) -> list[dict]:
    """Rank documents, not chunks.

    Full-text and vector lists contribute reciprocal rank. A direct phrase or
    number match adds its raw weight, which is what separates one decision
    from another written in the same language.
    """
    scores: dict[str, float] = defaultdict(float)
    best: dict[str, dict] = {}
    for rows in (bm25_rows, dense_rows):
        seen: set[str] = set()
        rank = 0
        for row in rows:
            if row["doc_id"] in seen:
                continue
            seen.add(row["doc_id"])
            rank += 1
            scores[row["doc_id"]] += 1.0 / (RRF_K + rank)
            best.setdefault(row["doc_id"], row)
    seen = set()
    for row in overlap_rows:
        if row["doc_id"] in seen:
            continue
        seen.add(row["doc_id"])
        scores[row["doc_id"]] += float(row.get("score") or 0)
        best.setdefault(row["doc_id"], row)
    ordered = sorted(scores, key=scores.get, reverse=True)
    fused = []
    for doc_id in ordered[:limit]:
        row = dict(best[doc_id])
        row["score"] = scores[doc_id]
        fused.append(row)
    return fused


def lexical_rerank(question: str, rows: list[dict], limit: int = 10) -> list[dict]:
    """Keep the fused order, and use extra term hits only to break ties."""
    terms = set(distinctive_tokens(question)) or set(query_terms(question))
    scored = []
    for row in rows:
        text = f"{row.get('section') or ''} {row['chunk_text']} {row.get('title') or ''}".lower()
        hits = sum(1 for term in terms if term.lower() in text)
        scored.append((float(row.get("score") or 0), hits, row))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [row for _, _, row in scored[:limit]]


def unique_docs(rows: list[dict]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        if row["doc_id"] not in seen:
            seen.append(row["doc_id"])
    return seen
