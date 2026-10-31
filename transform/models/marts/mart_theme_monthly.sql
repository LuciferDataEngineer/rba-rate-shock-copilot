select
    month_start,
    theme,
    theme_label,
    chunks,
    hits,
    share
from {{ ref('stg_theme_monthly') }}
