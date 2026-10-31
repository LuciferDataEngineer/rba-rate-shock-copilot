"""Parse Reserve Bank statistical-table CSVs into tidy rows.

Only series whose source is the RBA, the ABS, or APRA are kept. Third-party
feeds (Canstar, ASX, FENICS and similar) stay in the raw snapshot and are
dropped here.
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path

ALLOWED_ORGS = {"RBA", "ABS", "APRA"}
BLOCKED_ORGS = {"CANSTAR", "ASX", "FENICS", "BLOOMBERG", "REFINITIV", "YIELDBROKER", "MARKIT"}
NULL_TOKENS = {"", "na", "n/a", "null", "-"}
LABELS = {
    "Title",
    "Description",
    "Frequency",
    "Type",
    "Units",
    "Source",
    "Publication date",
    "Series ID",
}


def _org_tokens(source: str) -> list[str]:
    parts = re.split(r"[;/|,]", source)
    return [part.strip() for part in parts if part.strip()]


def source_allowed(source: str) -> bool:
    """True when every named publisher is RBA, ABS, or APRA."""
    tokens = _org_tokens(source)
    if not tokens:
        return False
    upper = [token.upper() for token in tokens]
    if any(any(blocked in token for blocked in BLOCKED_ORGS) for token in upper):
        return False
    # "Securitisation System" is the RBA's own system, not another publisher.
    orgs = [token for token in upper if token not in {"SECURITISATION SYSTEM", "DATA"}]
    if not orgs:
        return False
    return all(token in ALLOWED_ORGS for token in orgs)


def parse_obs_date(value: str) -> date | None:
    text = value.strip()
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_number(value: str) -> float | None:
    text = value.strip().replace(",", "")
    if text.lower() in NULL_TOKENS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_rba_csv(path: Path, table_id: str) -> list[dict]:
    """Return tidy observations for allowed series in one RBA CSV."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    meta: dict[str, list[str]] = {}
    data_start = None
    for index, row in enumerate(rows):
        if not row:
            continue
        label = row[0].strip()
        if label in LABELS:
            meta[label] = row[1:]
            continue
        if parse_obs_date(label) is not None:
            data_start = index
            break
    if data_start is None or "Series ID" not in meta:
        raise ValueError(f"Could not parse RBA table {path}")

    series_ids = meta["Series ID"]
    titles = meta.get("Title", [""] * len(series_ids))
    sources = meta.get("Source", [""] * len(series_ids))
    units = meta.get("Units", [""] * len(series_ids))
    frequencies = meta.get("Frequency", [""] * len(series_ids))
    published = meta.get("Publication date", [""] * len(series_ids))
    width = len(series_ids)
    kept = [source_allowed(sources[i] if i < len(sources) else "") for i in range(width)]

    observations: list[dict] = []
    for row in rows[data_start:]:
        if not row or parse_obs_date(row[0]) is None:
            continue
        obs_date = parse_obs_date(row[0])
        for index in range(width):
            if not kept[index]:
                continue
            raw = row[index + 1] if index + 1 < len(row) else ""
            value = parse_number(raw)
            if value is None:
                continue
            pub = published[index] if index < len(published) else ""
            observations.append(
                {
                    "table_id": table_id,
                    "series_id": series_ids[index].strip(),
                    "series_title": (titles[index] if index < len(titles) else "").strip(),
                    "obs_date": obs_date.isoformat(),
                    "value": value,
                    "unit": (units[index] if index < len(units) else "").strip(),
                    "frequency": (frequencies[index] if index < len(frequencies) else "").strip(),
                    "source": (sources[index] if index < len(sources) else "").strip(),
                    "publication_date": pub.strip(),
                }
            )
    return observations


def series_catalogue(path: Path, table_id: str) -> list[dict]:
    """One row per series, including those excluded for licensing."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    meta: dict[str, list[str]] = {}
    for row in rows:
        if row and row[0].strip() in LABELS:
            meta[row[0].strip()] = row[1:]
    catalogue = []
    for index, series_id in enumerate(meta.get("Series ID", [])):
        source = meta.get("Source", [""])[index] if index < len(meta.get("Source", [])) else ""
        title = meta.get("Title", [""])[index] if index < len(meta.get("Title", [])) else ""
        catalogue.append(
            {
                "table_id": table_id,
                "series_id": series_id.strip(),
                "series_title": title.strip(),
                "source": source.strip(),
                "allowed": source_allowed(source),
            }
        )
    return catalogue
