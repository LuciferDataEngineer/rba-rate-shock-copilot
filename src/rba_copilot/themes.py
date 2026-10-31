"""Share of document chunks that mention each theme.

Keyword hits are the figure on the public page. Embedding similarity is computed
later, once vectors exist, and is stored beside the keyword share.
"""

from __future__ import annotations

import re
from collections import defaultdict

THEMES: dict[str, re.Pattern[str]] = {
    "energy": re.compile(
        r"\b(energy|oil|petrol|fuel|electricity|gas|lng)\b",
        re.IGNORECASE,
    ),
    "ai_investment": re.compile(
        r"\b(?:artificial intelligence|ai-related|ai|data centres?|data centers?)\b",
        re.IGNORECASE,
    ),
    "capacity": re.compile(
        r"\b(capacity|productivity|potential output|spare capacity)\b",
        re.IGNORECASE,
    ),
    "labour_market": re.compile(
        r"\b(labour markets?|labor markets?|unemployment|wages?|employment|jobs)\b",
        re.IGNORECASE,
    ),
}

THEME_LABELS = {
    "energy": "Energy and fuel",
    "ai_investment": "AI and investment",
    "capacity": "Capacity and productivity",
    "labour_market": "Jobs and wages",
}


def theme_hits(text: str) -> dict[str, bool]:
    return {name: bool(pattern.search(text)) for name, pattern in THEMES.items()}


def monthly_theme_share(chunks: list[dict]) -> list[dict]:
    """Share of chunks in each month whose text matches a theme."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        month = (chunk.get("doc_date") or "")[:7]
        if month:
            buckets[month].append(chunk)
    rows: list[dict] = []
    for month in sorted(buckets):
        group = buckets[month]
        total = len(group)
        for name in THEMES:
            hits = sum(1 for chunk in group if theme_hits(chunk["chunk_text"]).get(name) or theme_hits(chunk.get("section") or "").get(name))
            rows.append(
                {
                    "month_start": f"{month}-01",
                    "theme": name,
                    "theme_label": THEME_LABELS[name],
                    "chunks": total,
                    "hits": hits,
                    "share": hits / total if total else 0.0,
                }
            )
    return rows
