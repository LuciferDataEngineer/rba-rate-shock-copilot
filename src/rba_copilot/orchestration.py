"""Dagster asset graph over the snapshot, the marts and the page."""

from __future__ import annotations

import json

from dagster import AssetCheckResult, Definitions, asset, asset_check

from rba_copilot.paths import REPORTS


@asset(group_name="policy_documents")
def tidy_snapshot() -> dict:
    from rba_copilot.pipeline import build_tidy

    return build_tidy()


@asset_check(asset=tidy_snapshot)
def enough_documents(tidy_snapshot: dict) -> AssetCheckResult:
    count = tidy_snapshot["documents"]
    return AssetCheckResult(passed=count >= 30, metadata={"documents": count})


@asset(group_name="household_finance", deps=[tidy_snapshot])
def household_headline() -> dict:
    from rba_copilot.headline import build_headline

    return build_headline()["kpis"]


@asset_check(asset=household_headline)
def cash_rate_is_current(household_headline: dict) -> AssetCheckResult:
    return AssetCheckResult(
        passed=household_headline["cash_rate"] == 4.6,
        metadata={"cash_rate": household_headline["cash_rate"]},
    )


@asset(group_name="policy_documents", deps=[household_headline])
def stakeholder_page() -> str:
    from rba_copilot.dashboard import build_site

    build_site()
    return str(REPORTS / "headline.json")


def lineage_note() -> dict:
    path = REPORTS / "openlineage" / "tidy_run.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


defs = Definitions(
    assets=[tidy_snapshot, household_headline, stakeholder_page],
    asset_checks=[enough_documents, cash_rate_is_current],
)
