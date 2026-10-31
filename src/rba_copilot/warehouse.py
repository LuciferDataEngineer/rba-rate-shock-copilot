"""Small helpers for writing parquet via DuckDB."""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb


def write_parquet(rows: list[dict], path: Path, casts: dict[str, str] | None = None) -> None:
    """Write rows to parquet. ``casts`` maps column names to DuckDB types."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"no rows for {path}")
    fields = list(rows[0].keys())
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    select_list = []
    for field in fields:
        if casts and field in casts:
            select_list.append(f'CAST("{field}" AS {casts[field]}) AS "{field}"')
        else:
            select_list.append(f'"{field}"')
    select_sql = ", ".join(select_list)
    escaped = temporary.as_posix().replace("'", "''")
    destination = path.as_posix().replace("'", "''")
    duckdb.connect().execute(
        f"COPY (SELECT {select_sql} FROM read_csv('{escaped}', header=true, all_varchar=true, quote='\"', escape='\"')) "
        f"TO '{destination}' (FORMAT PARQUET)"
    )
    temporary.unlink(missing_ok=True)
