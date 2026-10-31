"""Build tidy parquet tables from the committed snapshot. No network."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

from rba_copilot.paths import ABS_DIR, DOCS, REPORTS, TABLES, TIDY
from rba_copilot.rag.chunk import build_chunks, load_catalogue
from rba_copilot.tables import parse_rba_csv, series_catalogue
from rba_copilot.themes import monthly_theme_share
from rba_copilot.warehouse import write_parquet

SERIES_CASTS = {
    "obs_date": "DATE",
    "value": "DOUBLE",
}
ABS_CASTS = {"month_start": "DATE", "value": "DOUBLE"}
AWE_CASTS = {"period_start": "DATE", "weekly_earnings": "DOUBLE"}
DOC_CASTS = {"doc_date": "DATE", "n_chars": "INTEGER"}
CHUNK_CASTS = {"doc_date": "DATE"}
THEME_CASTS = {"month_start": "DATE", "chunks": "INTEGER", "hits": "INTEGER", "share": "DOUBLE"}

TABLE_FILES = {
    "f1": "f1-data.csv",
    "f1_1": "f1.1-data.csv",
    "f5": "f5-data.csv",
    "f6": "f6-data.csv",
    "g1": "g1-data.csv",
    "h5": "h5-data.csv",
    "e13": "e13-data.csv",
}


def _abs_rows(path: Path, series_name: str) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            period = raw.get("TIME_PERIOD: Time Period") or raw.get("TIME_PERIOD")
            value = raw.get("OBS_VALUE")
            if not period or value in (None, ""):
                continue
            if "-S" in period:
                continue
            year, month = period.split("-")
            rows.append(
                {
                    "series_name": series_name,
                    "month_start": f"{year}-{month}-01",
                    "value": value,
                }
            )
    return rows


def _awe_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            period = raw.get("TIME_PERIOD: Time Period") or raw.get("TIME_PERIOD")
            value = raw.get("OBS_VALUE")
            if not period or "-S" not in period or value in (None, ""):
                continue
            year, semester = period.split("-S")
            # First half is the May survey; second half is the November survey.
            month = "05" if semester == "1" else "11"
            rows.append({"period_start": f"{year}-{month}-01", "weekly_earnings": value, "period_label": period})
    return rows


def build_tidy() -> dict:
    TIDY.mkdir(parents=True, exist_ok=True)
    observations: list[dict] = []
    catalogue_rows: list[dict] = []
    for table_id, filename in TABLE_FILES.items():
        path = TABLES / filename
        observations.extend(parse_rba_csv(path, table_id))
        catalogue_rows.extend(series_catalogue(path, table_id))
    write_parquet(observations, TIDY / "series_long.parquet", SERIES_CASTS)
    write_parquet(
        catalogue_rows,
        TIDY / "series_catalogue.parquet",
        {"allowed": "BOOLEAN"},
    )

    cpi_rows = _abs_rows(ABS_DIR / "cpi_headline_yoy.csv", "headline_yoy")
    cpi_rows.extend(_abs_rows(ABS_DIR / "cpi_trimmed_mean_yoy.csv", "trimmed_mean_yoy"))
    cpi_rows.extend(_abs_rows(ABS_DIR / "cpi_headline_index.csv", "headline_index"))
    write_parquet(cpi_rows, TIDY / "abs_cpi_monthly.parquet", ABS_CASTS)
    write_parquet(_awe_rows(ABS_DIR / "awe_ordinary_time.csv"), TIDY / "abs_awe.parquet", AWE_CASTS)

    documents = load_catalogue(DOCS / "catalogue.json")
    doc_rows = [
        {
            "doc_id": doc["doc_id"],
            "doc_type": doc["doc_type"],
            "title": doc["title"],
            "doc_date": doc["doc_date"],
            "url": doc["url"],
            "n_chars": doc["n_chars"],
        }
        for doc in documents
    ]
    write_parquet(doc_rows, TIDY / "documents.parquet", DOC_CASTS)

    chunks = build_chunks(documents)
    write_parquet(chunks, TIDY / "chunks.parquet", CHUNK_CASTS)
    themes = monthly_theme_share(chunks)
    write_parquet(themes, TIDY / "theme_monthly.parquet", THEME_CASTS)

    summary = {
        "series_rows": len(observations),
        "series_kept": sum(1 for row in catalogue_rows if row["allowed"]),
        "series_excluded": sum(1 for row in catalogue_rows if not row["allowed"]),
        "documents": len(documents),
        "chunks": len(chunks),
        "theme_rows": len(themes),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "tidy_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_lineage(summary)
    print(json.dumps(summary))
    return summary


def _write_lineage(summary: dict) -> None:
    """OpenLineage-compatible run event. No collector is required."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    event = {
        "eventType": "COMPLETE",
        "eventTime": now,
        "run": {"runId": "snapshot-tidy", "facets": {"nominalTime": {"nominalStartTime": now}}},
        "job": {
            "namespace": "rba-rate-shock-copilot",
            "name": "tidy_snapshot",
            "facets": {
                "documentation": {
                    "description": "Tidy RBA and ABS snapshot tables, document chunks, and theme shares."
                }
            },
        },
        "inputs": [
            {"namespace": "snapshot", "name": "data/snapshot/tables"},
            {"namespace": "snapshot", "name": "data/snapshot/abs"},
            {"namespace": "snapshot", "name": "data/snapshot/documents"},
        ],
        "outputs": [
            {"namespace": "warehouse", "name": "data/warehouse/tidy/series_long.parquet"},
            {"namespace": "warehouse", "name": "data/warehouse/tidy/documents.parquet"},
            {"namespace": "warehouse", "name": "data/warehouse/tidy/chunks.parquet"},
            {"namespace": "warehouse", "name": "data/warehouse/tidy/theme_monthly.parquet"},
        ],
        "producer": "rba_copilot.pipeline",
        "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json",
        "summary": summary,
    }
    destination = REPORTS / "openlineage"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "tidy_run.json").write_text(json.dumps(event, indent=2), encoding="utf-8")


def latest_value(series_id: str, on_or_before: date | None = None) -> tuple[date, float] | None:
    """Helper for tests and the headline check. Reads the snapshot, not the mart."""
    found: list[tuple[date, float]] = []
    for table_id, filename in TABLE_FILES.items():
        for row in parse_rba_csv(TABLES / filename, table_id):
            if row["series_id"] != series_id:
                continue
            obs = date.fromisoformat(row["obs_date"])
            if on_or_before and obs > on_or_before:
                continue
            found.append((obs, row["value"]))
    if not found:
        return None
    return max(found)


def hikes_in_year(year: int) -> list[dict]:
    """Target changes during a calendar year, from the daily cash-rate series."""
    points = []
    for row in parse_rba_csv(TABLES / "f1-data.csv", "f1"):
        if row["series_id"] == "FIRMMCRTD":
            points.append((date.fromisoformat(row["obs_date"]), row["value"]))
    points.sort()
    changes = []
    previous = None
    for obs, value in points:
        if previous is not None and obs.year == year and round((value - previous) * 100) != 0:
            changes.append(
                {
                    "effective_date": obs.isoformat(),
                    "from_rate": previous,
                    "to_rate": value,
                    "change_bp": int(round((value - previous) * 100)),
                }
            )
        previous = value
    return changes


def main() -> None:
    build_tidy()


if __name__ == "__main__":
    main()
