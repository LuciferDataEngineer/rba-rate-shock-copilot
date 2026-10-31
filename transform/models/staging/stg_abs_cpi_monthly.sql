select
    series_name,
    cast(month_start as date) as month_start,
    cast(value as double) as value
from {{ source('tidy', 'abs_cpi_monthly') }}
