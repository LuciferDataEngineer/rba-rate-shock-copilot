select
    date_trunc('month', obs_date)::date as month_start,
    max(obs_date) as housing_rate_date,
    arg_max(value, obs_date) as housing_variable_rate
from {{ ref('stg_series') }}
where series_id = 'FLRHOOVA'
group by 1
