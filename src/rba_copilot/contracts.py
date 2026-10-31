"""Validate domain data contracts against the tidy parquet tables."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import duckdb
import yaml
from pydantic import BaseModel, Field

from rba_copilot.paths import CONTRACTS, MANIFEST, ROOT


class ColumnSpec(BaseModel):
    name: str
    type: str


class QualityRule(BaseModel):
    rule: str
    column: str | None = None
    min: float | None = None
    max: float | None = None
    value: int | None = None
    series_id: str | None = None


class Freshness(BaseModel):
    column: str
    max_age_days: int
    series_id: str | None = None


class Contract(BaseModel):
    domain: str
    owner: str
    description: str
    dataset: str
    schema_: list[ColumnSpec] = Field(alias="schema")
    quality: list[QualityRule]
    freshness: Freshness

    model_config = {"populate_by_name": True}


def _access_date() -> date:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return datetime.fromisoformat(manifest["access_timestamp_utc"]).date()


def _connect(dataset: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    escaped = dataset.as_posix().replace("'", "''")
    connection.execute(f"CREATE VIEW dataset AS SELECT * FROM read_parquet('{escaped}')")
    return connection


def validate_contract(path: Path) -> list[str]:
    contract = Contract.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    dataset = ROOT / contract.dataset
    errors: list[str] = []
    if not dataset.exists():
        return [f"{contract.domain}: missing {dataset}"]
    connection = _connect(dataset)
    columns = {
        row[0]: row[1].upper()
        for row in connection.execute("DESCRIBE SELECT * FROM dataset").fetchall()
    }
    for column in contract.schema_:
        if column.name not in columns:
            errors.append(f"{contract.domain}: missing column {column.name}")
            continue
        actual = columns[column.name]
        expected = column.type.upper()
        if expected not in actual and actual not in expected:
            errors.append(f"{contract.domain}: {column.name} is {actual}, expected {expected}")
    for rule in contract.quality:
        where = f"WHERE series_id = '{rule.series_id}'" if rule.series_id else ""
        if rule.rule == "min_rows":
            count = connection.execute(f"SELECT count(*) FROM dataset {where}").fetchone()[0]
            if count < (rule.value or 0):
                errors.append(f"{contract.domain}: expected at least {rule.value} rows, found {count}")
        elif rule.rule == "not_null" and rule.column:
            count = connection.execute(
                f"SELECT count(*) FROM dataset {where} {'AND' if where else 'WHERE'} "
                f"{rule.column} IS NULL"
            ).fetchone()[0]
            if count:
                errors.append(f"{contract.domain}: {rule.column} has {count} nulls")
        elif rule.rule == "accepted_range" and rule.column:
            count = connection.execute(
                f"""
                SELECT count(*) FROM dataset
                {where if where else 'WHERE 1=1'}
                AND {rule.column} IS NOT NULL
                AND ({rule.column} < {rule.min} OR {rule.column} > {rule.max})
                """
            ).fetchone()[0]
            if count:
                errors.append(f"{contract.domain}: {rule.column} has {count} values outside range")
        elif rule.rule == "unique" and rule.column:
            dupes = connection.execute(
                f"""
                SELECT count(*) FROM (
                  SELECT {rule.column} FROM dataset GROUP BY 1 HAVING count(*) > 1
                )
                """
            ).fetchone()[0]
            if dupes:
                errors.append(f"{contract.domain}: {rule.column} has {dupes} duplicate keys")
    fresh = contract.freshness
    where = f"WHERE series_id = '{fresh.series_id}'" if fresh.series_id else ""
    latest = connection.execute(f"SELECT max({fresh.column}) FROM dataset {where}").fetchone()[0]
    if latest is None:
        errors.append(f"{contract.domain}: no dates for freshness")
    else:
        latest_date = latest if isinstance(latest, date) else date.fromisoformat(str(latest)[:10])
        age = (_access_date() - latest_date).days
        if age > fresh.max_age_days:
            errors.append(
                f"{contract.domain}: {fresh.column} is {age} days behind the snapshot (limit {fresh.max_age_days})"
            )
    connection.close()
    return errors


def validate_all() -> None:
    errors: list[str] = []
    for path in sorted(CONTRACTS.glob("*.yaml")):
        errors.extend(validate_contract(path))
    if errors:
        raise SystemExit("contract checks failed:\n" + "\n".join(errors))
    print(f"contracts ok ({len(list(CONTRACTS.glob('*.yaml')))} domains)")


def main() -> None:
    validate_all()


if __name__ == "__main__":
    main()
