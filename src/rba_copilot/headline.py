"""Assemble the stakeholder figures from the dbt mart. No network."""

from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import duckdb

from rba_copilot.mortgage import extra_repayment, monthly_repayment
from rba_copilot.paths import MANIFEST, REPORTS, WAREHOUSE

MELBOURNE = ZoneInfo("Australia/Melbourne")


def _rows(sql: str) -> list[dict]:
    connection = duckdb.connect(str(WAREHOUSE / "rba.duckdb"), read_only=True)
    cursor = connection.execute(sql)
    columns = [item[0] for item in cursor.description]
    records = []
    for row in cursor.fetchall():
        item = {}
        for column, value in zip(columns, row, strict=True):
            if isinstance(value, date):
                item[column] = value.isoformat()
            elif isinstance(value, float):
                item[column] = round(value, 6)
            else:
                item[column] = value
        records.append(item)
    connection.close()
    return records


def _latest(rows: list[dict], field: str) -> dict | None:
    for row in reversed(rows):
        if row.get(field) is not None:
            return row
    return None


def _fmt_money(value: float) -> str:
    return f"${value:,.0f}"


def _melbourne_stamp(moment: datetime) -> str:
    local = moment.astimezone(MELBOURNE)
    hour = local.strftime("%I").lstrip("0") or "12"
    return local.strftime(f"%A %-d %B %Y, {hour}:%M%p %Z").replace("AM", "am").replace("PM", "pm")


def build_headline() -> dict:
    months = _rows(
        """
        select *
        from mart_household_month
        where month_start >= date '2023-01-01'
        order by month_start
        """
    )
    decisions = _rows(
        """
        select effective_date, previous_target, new_target, change_bp, direction
        from mart_decisions
        where effective_year = 2026 and direction = 'increase'
        order by effective_date
        """
    )
    themes = _rows(
        """
        select month_start, theme, theme_label, chunks, hits, share
        from mart_theme_monthly
        where month_start >= date '2025-01-01'
        order by month_start, theme
        """
    )
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    accessed = datetime.fromisoformat(manifest["access_timestamp_melbourne"])

    cash = _latest(months, "cash_rate_target")
    housing = _latest(months, "housing_variable_rate")
    prices = _latest(months, "cpi_yoy_monthly")
    trimmed = _latest(months, "trimmed_mean_yoy_monthly")
    jobs = _latest(months, "unemployment_rate")
    january = next(row for row in months if row["month_start"] == "2026-01-01")
    payments = _latest(months, "scheduled_repayments_to_income")

    rate_now = housing["housing_variable_rate"]
    rate_jan = january["housing_variable_rate"]
    extra_600 = housing["extra_repayment_600k_since_jan"]
    step_600 = extra_repayment(600_000, rate_now, rate_now + 0.25)
    step_100 = extra_repayment(100_000, rate_now, rate_now + 0.25)
    real = cash["cash_rate_target"] - trimmed["trimmed_mean_yoy_monthly"]
    gap_top = trimmed["trimmed_mean_yoy_monthly"] - 3.0
    wage = housing["weekly_ordinary_earnings"]
    share = housing["mortgage_repayment_to_income"]
    jobs_jan = january["unemployment_rate"]

    hero = []
    for row in months:
        if row["month_start"] < "2024-01-01":
            continue
        hero.append(
            {
                "month": row["month_start"][:7],
                "cash_rate": row["cash_rate_target"],
                "headline_inflation": row["cpi_yoy_monthly"],
                "trimmed_mean": row["trimmed_mean_yoy_monthly"],
            }
        )
    repayments = [
        {
            "month": row["month_start"][:7],
            "repayment": None if row["repayment_600k"] is None else round(row["repayment_600k"], 2),
            "rate": row["housing_variable_rate"],
        }
        for row in months
        if row["month_start"] >= "2025-01-01" and row["repayment_600k"] is not None
    ]
    unemployment = [
        {"month": row["month_start"][:7], "unemployment": row["unemployment_rate"]}
        for row in months
        if row["month_start"] >= "2024-01-01" and row["unemployment_rate"] is not None
    ]

    payload = {
        "as_of_melbourne": _melbourne_stamp(accessed),
        "next_decision": "Tuesday 3 November 2026, 2:30pm AEDT",
        "kpis": {
            "cash_rate": cash["cash_rate_target"],
            "cash_rate_date": cash["cash_rate_date"],
            "hikes_2026": len(decisions),
            "cumulative_hike_bp": cash["cumulative_hike_bp"],
            "housing_rate": rate_now,
            "housing_rate_date": housing["housing_rate_date"],
            "housing_rate_january": rate_jan,
            "repayment_600k": round(housing["repayment_600k"], 2),
            "repayment_600k_january": round(monthly_repayment(600_000, rate_jan), 2),
            "extra_repayment_600k": round(extra_600, 2),
            "extra_repayment_100k": round(extra_600 / 6, 2),
            "step_25bp_600k": round(step_600, 2),
            "step_25bp_100k": round(step_100, 2),
            "cpi_yoy": prices["cpi_yoy_monthly"],
            "cpi_month": prices["month_start"],
            "trimmed_mean_yoy": trimmed["trimmed_mean_yoy_monthly"],
            "trimmed_mean_month": trimmed["month_start"],
            "real_cash_rate": round(real, 2),
            "inflation_gap_vs_top": round(gap_top, 2),
            "inflation_gap_vs_midpoint": round(trimmed["trimmed_mean_yoy_monthly"] - 2.5, 2),
            "unemployment": jobs["unemployment_rate"],
            "unemployment_month": jobs["month_start"],
            "unemployment_january": jobs_jan,
            "weekly_earnings": wage,
            "repayment_share_of_one_wage": round(share, 4),
            "scheduled_repayments_to_income": payments["scheduled_repayments_to_income"],
            "scheduled_repayments_month": payments["month_start"],
        },
        "decisions_2026": decisions,
        "series": {"hero": hero, "repayments": repayments, "unemployment": unemployment, "themes": themes},
        "checks": {
            "cash_rate_is_4_60": cash["cash_rate_target"] == 4.6,
            "four_hikes": len(decisions) == 4,
            "cpi_is_4_3": prices["cpi_yoy_monthly"] == 4.3,
            "trimmed_mean_is_3_6": trimmed["trimmed_mean_yoy_monthly"] == 3.6,
            "unemployment_is_4_7": jobs["unemployment_rate"] == 4.7,
            "extra_repayment_near_268": abs(extra_600 - 268) < 2,
        },
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "headline.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        "cash",
        payload["kpis"]["cash_rate"],
        "extra600",
        _fmt_money(payload["kpis"]["extra_repayment_600k"]),
        "step",
        round(step_600, 2),
        "share",
        round(share, 3),
    )
    return payload


def assert_headline(payload: dict | None = None) -> None:
    payload = payload or build_headline()
    failed = [name for name, ok in payload["checks"].items() if not ok]
    if failed:
        raise SystemExit(f"headline checks failed: {', '.join(failed)}")


def main() -> None:
    assert_headline()


if __name__ == "__main__":
    main()
