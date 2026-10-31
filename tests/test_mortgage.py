from rba_copilot.mortgage import extra_repayment, monthly_repayment


def test_repayment_at_published_august_rate():
    # 30-year principal-and-interest at 6.2% on $100,000.
    assert abs(monthly_repayment(100_000, 6.2) - 612.47) < 0.05


def test_quarter_point_on_600k():
    step = extra_repayment(600_000, 6.2, 6.45)
    assert 90 < step < 110
