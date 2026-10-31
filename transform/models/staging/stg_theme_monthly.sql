select
    cast(month_start as date) as month_start,
    theme,
    theme_label,
    cast(chunks as integer) as chunks,
    cast(hits as integer) as hits,
    cast(share as double) as share
from {{ source('tidy', 'theme_monthly') }}
