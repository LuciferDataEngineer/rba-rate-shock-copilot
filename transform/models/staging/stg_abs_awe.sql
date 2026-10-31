select
    cast(period_start as date) as period_start,
    period_label,
    cast(weekly_earnings as double) as weekly_earnings
from {{ source('tidy', 'abs_awe') }}
