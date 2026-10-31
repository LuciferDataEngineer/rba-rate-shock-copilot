"""Standard principal-and-interest repayment maths.

The comparison loan is a 30-year principal-and-interest mortgage, paid monthly.
The annual rate is converted to a monthly rate by dividing by 12. This is the
usual way Australian lenders quote a comparison repayment. It is not a quote
for any household's actual loan.
"""

from __future__ import annotations

TERM_YEARS = 30
TERM_MONTHS = TERM_YEARS * 12


def monthly_repayment(principal: float, annual_rate_percent: float, months: int = TERM_MONTHS) -> float:
    """Monthly principal-and-interest repayment.

    ``annual_rate_percent`` is the nominal annual rate, for example 6.2.
    """
    if principal < 0:
        raise ValueError("principal must be non-negative")
    if months <= 0:
        raise ValueError("months must be positive")
    if annual_rate_percent < 0:
        raise ValueError("rate must be non-negative")
    monthly = annual_rate_percent / 100.0 / 12.0
    if monthly == 0:
        return principal / months
    growth = (1.0 + monthly) ** months
    return principal * monthly * growth / (growth - 1.0)


def extra_repayment(
    principal: float,
    rate_from: float,
    rate_to: float,
    months: int = TERM_MONTHS,
) -> float:
    """How much the monthly repayment rises when the annual rate moves from one level to another."""
    return monthly_repayment(principal, rate_to, months) - monthly_repayment(principal, rate_from, months)
