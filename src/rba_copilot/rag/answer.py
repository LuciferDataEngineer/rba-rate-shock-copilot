"""Extractive answers: a quoted sentence, the document, the date and the URL."""

from __future__ import annotations

import json
import re

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
)

SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _terms(question: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", question)}


def best_sentence(question: str, rows: list[dict]) -> dict | None:
    wanted = _terms(question)
    best: tuple[float, dict] | None = None
    for row in rows[:5]:
        for sentence in SENTENCE.split(row["chunk_text"]):
            sentence = sentence.strip()
            if len(sentence) < 80:
                continue
            tokens = _terms(sentence)
            overlap = len(wanted & tokens) / max(len(wanted), 1)
            length_bonus = 0.05 if 120 <= len(sentence) <= 420 else 0
            score = overlap + length_bonus
            if best is None or score > best[0]:
                best = (
                    score,
                    {
                        "quote": sentence,
                        "doc_id": row["doc_id"],
                        "title": row["title"],
                        "doc_date": row["doc_date"],
                        "url": row["url"],
                        "section": row["section"],
                    },
                )
    if best and best[0] >= 0.15:
        return best[1]
    return None


def answer_question(connection, question: str) -> dict:
    vector = encode([question])[0].tolist()
    bm25 = search_bm25(connection, question, limit=40)
    dense = search_vector(connection, vector, limit=40)
    overlap = search_overlap(connection, question, limit=40)
    hybrid = fuse_documents(bm25, dense, overlap, limit=12)
    reranked = lexical_rerank(question, hybrid, limit=8)
    citation = best_sentence(question, reranked) or best_sentence(question, hybrid)
    return {"question": question, "citation": citation, "doc_ids": [row["doc_id"] for row in reranked[:5]]}


def build_page_answers() -> list[dict]:
    loaded = yaml.safe_load((EVAL_DIR / "page_questions.yml").read_text(encoding="utf-8"))
    questions = loaded["questions"]
    connection = connect()
    answers = []
    for item in questions:
        answer = answer_question(connection, item["question"])
        answer["question"] = item.get("display") or item["question"]
        answers.append(answer)
    connection.close()
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "answers.json").write_text(json.dumps(answers, indent=2), encoding="utf-8")
    return answers


def main() -> None:
    answers = build_page_answers()
    print(f"wrote {len(answers)} answers")


if __name__ == "__main__":
    main()
