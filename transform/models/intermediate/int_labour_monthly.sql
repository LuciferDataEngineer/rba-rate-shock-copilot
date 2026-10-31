select
    date_trunc('month', obs_date)::date as month_start,
    max(obs_date) as labour_date,
    arg_max(value, obs_date) as unemployment_rate
from {{ ref('stg_series') }}
where series_id = 'GLFSURSA'
group by 1
