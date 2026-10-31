from rba_copilot.paths import TABLES
from rba_copilot.pipeline import hikes_in_year, latest_value
from rba_copilot.tables import parse_rba_csv, series_catalogue, source_allowed


def test_third_party_sources_are_blocked():
    assert source_allowed("RBA")
    assert source_allowed("ABS / RBA")
    assert source_allowed("APRA, RBA")
    assert source_allowed("RBA; Securitisation System")
    assert not source_allowed("CANSTAR data; RBA")
    assert not source_allowed("ASX")
    assert not source_allowed("FENICS")


def test_f5_drops_canstar_and_keeps_apra():
    catalogue = series_catalogue(TABLES / "f5-data.csv", "f5")
    allowed = {row["series_id"] for row in catalogue if row["allowed"]}
    blocked = {row["series_id"] for row in catalogue if not row["allowed"]}
    assert "FILRHLBVS" in blocked
    assert "FILRSBVWA" in allowed


def test_latest_cash_rate_target_is_4_60():
    obs, value = latest_value("FIRMMCRTD")
    assert value == 4.6
    assert obs.isoformat() >= "2026-10-01"


def test_four_cash_rate_increases_in_2026():
    hikes = hikes_in_year(2026)
    assert [item["change_bp"] for item in hikes] == [25, 25, 25, 25]
    assert hikes[-1]["to_rate"] == 4.6


def test_parser_returns_dated_rows():
    rows = parse_rba_csv(TABLES / "h5-data.csv", "h5")
    september = [row for row in rows if row["series_id"] == "GLFSURSA" and row["obs_date"] == "2026-09-30"]
    assert september[0]["value"] == 4.7
