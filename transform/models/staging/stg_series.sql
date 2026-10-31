select
    table_id,
    series_id,
    series_title,
    cast(obs_date as date) as obs_date,
    cast(value as double) as value,
    unit,
    frequency,
    source,
    publication_date
from {{ source('tidy', 'series_long') }}
