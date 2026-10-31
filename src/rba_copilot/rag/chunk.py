"""Section-aware chunks with overlap."""

from __future__ import annotations

import json
import re
from pathlib import Path

from rba_copilot.paths import MANIFEST

MAX_CHARS = 850
OVERLAP = 140
MIN_CHARS = 80


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _tail(text: str, size: int) -> str:
    if len(text) <= size:
        return text
    snippet = text[-size:]
    space = snippet.find(" ")
    if 0 <= space < 40:
        snippet = snippet[space + 1 :]
    return snippet


def chunk_section(heading: str, text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> list[str]:
    """Split one section into overlapping windows on sentence boundaries."""
    sentences = _sentences(text)
    if not sentences:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        addition = len(sentence) if not current else len(sentence) + 1
        if current and current_len + addition > max_chars:
            body = " ".join(current).strip()
            if body:
                chunks.append(body)
            carry = _tail(body, overlap)
            current = [carry, sentence] if carry else [sentence]
            current_len = len(" ".join(current))
        else:
            current.append(sentence)
            current_len += addition
    if current:
        body = " ".join(current).strip()
        if body:
            chunks.append(body)
    # A single huge sentence still needs a hard cut.
    normalised: list[str] = []
    for body in chunks:
        if len(body) <= max_chars * 2:
            normalised.append(body)
            continue
        start = 0
        while start < len(body):
            normalised.append(body[start : start + max_chars])
            start += max_chars - overlap
    return [body for body in normalised if len(body) >= MIN_CHARS or len(chunks) == 1]


def chunks_for_document(doc: dict) -> list[dict]:
    sections_path = MANIFEST.parents[1] / doc["sections_path"]
    sections = json.loads(sections_path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    number = 0
    for section in sections:
        heading = re.sub(r"\s+", " ", section.get("heading") or "Document").strip()
        for body in chunk_section(heading, section.get("text") or ""):
            number += 1
            rows.append(
                {
                    "chunk_id": f"{doc['doc_id']}-{number:04d}",
                    "doc_id": doc["doc_id"],
                    "doc_type": doc["doc_type"],
                    "title": doc["title"],
                    "doc_date": doc["doc_date"],
                    "url": doc["url"],
                    "section": heading,
                    "chunk_text": body,
                    "embed_text": f"{heading}. {body}",
                }
            )
    return rows


def build_chunks(catalogue: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for doc in catalogue:
        rows.extend(chunks_for_document(doc))
    return rows


def load_catalogue(path: Path | None = None) -> list[dict]:
    catalogue_path = path or (MANIFEST.parents[1] / "data" / "snapshot" / "documents" / "catalogue.json")
    return json.loads(catalogue_path.read_text(encoding="utf-8"))
