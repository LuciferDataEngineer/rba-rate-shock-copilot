"""Retrieval evaluation for BM25, vector search, hybrid fusion and a rerank."""

from __future__ import annotations

import json
import math

import yaml

from rba_copilot.paths import EVAL_DIR, REPORTS
from rba_copilot.rag.embed import encode
from rba_copilot.rag.retrieve import (
    connect,
    fuse_documents,
    lexical_rerank,
    search_bm25,
    search_overlap,
    search_vector,
    unique_docs,
)

try:
    from sentence_transformers import CrossEncoder
except Exception:  # pragma: no cover - optional model
    CrossEncoder = None


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def mean_reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for index, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    def dcg(items: list[str]) -> float:
        score = 0.0
        for index, doc_id in enumerate(items[:k], start=1):
            if doc_id in relevant:
                score += 1.0 / math.log2(index + 1)
        return score

    ideal = dcg(list(relevant))
    if ideal == 0:
        return 0.0
    return dcg(retrieved) / ideal


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _cross_rerank(question: str, rows: list[dict], limit: int = 10) -> list[dict]:
    if CrossEncoder is None or not rows:
        return lexical_rerank(question, rows, limit=limit)
    model = _cross_rerank.model
    if model is None:
        return lexical_rerank(question, rows, limit=limit)
    pairs = [(question, f"{row.get('section') or ''}. {row['chunk_text'][:800]}") for row in rows]
    scores = model.predict(pairs)
    ordered = sorted(zip(scores, rows, strict=True), key=lambda item: float(item[0]), reverse=True)
    return [row for _, row in ordered[:limit]]


_cross_rerank.model = None


def evaluate(use_cross_encoder: bool = False) -> dict:
    questions = yaml.safe_load((EVAL_DIR / "golden.yml").read_text(encoding="utf-8"))["questions"]
    threshold = yaml.safe_load((EVAL_DIR / "threshold.yml").read_text(encoding="utf-8"))
    if use_cross_encoder and CrossEncoder is not None:
        _cross_rerank.model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu")
    connection = connect()
    texts = [item["question"] for item in questions]
    vectors = encode(texts)
    methods = {"bm25": [], "vector": [], "hybrid": [], "hybrid_rerank": []}
    per_question = []
    for item, vector in zip(questions, vectors, strict=True):
        relevant = set(item["relevant_docs"])
        bm25_rows = search_bm25(connection, item["question"], limit=40)
        dense_rows = search_vector(connection, vector.tolist(), limit=40)
        overlap_rows = search_overlap(connection, item["question"], limit=40)
        bm25 = unique_docs(bm25_rows)
        dense = unique_docs(dense_rows)
        hybrid_rows = fuse_documents(bm25_rows, dense_rows, overlap_rows, limit=15)
        hybrid = unique_docs(hybrid_rows)
        if use_cross_encoder:
            reranked = unique_docs(_cross_rerank(item["question"], hybrid_rows, limit=15))
        else:
            reranked = unique_docs(lexical_rerank(item["question"], hybrid_rows, limit=15))
        runs = {"bm25": bm25, "vector": dense, "hybrid": hybrid, "hybrid_rerank": reranked}
        detail = {"id": item["id"], "question": item["question"]}
        for name, retrieved in runs.items():
            scores = {
                "recall_at_5": recall_at_k(retrieved, relevant, 5),
                "mrr": mean_reciprocal_rank(retrieved, relevant),
                "ndcg_at_5": ndcg_at_k(retrieved, relevant, 5),
            }
            methods[name].append(scores)
            detail[name] = scores["recall_at_5"]
        per_question.append(detail)
    connection.close()
    summary = {}
    for name, rows in methods.items():
        summary[name] = {
            "recall_at_5": round(_mean([row["recall_at_5"] for row in rows]), 4),
            "mrr": round(_mean([row["mrr"] for row in rows]), 4),
            "ndcg_at_5": round(_mean([row["ndcg_at_5"] for row in rows]), 4),
        }
    minimum = float(threshold["hybrid_recall_at_5"])
    summary["questions"] = len(questions)
    summary["reranker"] = "cross-encoder" if use_cross_encoder else "lexical"
    summary["hybrid_recall_at_5_min"] = minimum
    summary["passed"] = summary["hybrid"]["recall_at_5"] >= minimum
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "retrieval_eval.json").write_text(
        json.dumps({"summary": summary, "per_question": per_question}, indent=2),
        encoding="utf-8",
    )
    print(f"{'method':16} {'recall@5':>10} {'MRR':>8} {'nDCG@5':>8}")
    for name in ("bm25", "vector", "hybrid", "hybrid_rerank"):
        row = summary[name]
        print(f"{name:16} {row['recall_at_5']:10.3f} {row['mrr']:8.3f} {row['ndcg_at_5']:8.3f}")
    if not summary["passed"]:
        raise SystemExit(
            f"hybrid recall@5 {summary['hybrid']['recall_at_5']:.3f} is below {minimum:.2f}"
        )
    return summary


def main() -> None:
    import os

    evaluate(use_cross_encoder=os.environ.get("RBA_RERANK") == "cross")


if __name__ == "__main__":
    main()
