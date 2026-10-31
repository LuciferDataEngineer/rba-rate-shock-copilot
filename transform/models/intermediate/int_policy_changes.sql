with ordered as (
    select
        obs_date,
        value as cash_rate_target,
        lag(value) over (order by obs_date) as previous_target
    from {{ ref('stg_series') }}
    where series_id = 'FIRMMCRTD'
)
select
    obs_date as effective_date,
    previous_target,
    cash_rate_target as new_target,
    round((cash_rate_target - previous_target) * 100)::integer as change_bp
from ordered
where previous_target is not null
  and round((cash_rate_target - previous_target) * 100) <> 0
