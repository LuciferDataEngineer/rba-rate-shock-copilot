select
    date_trunc('month', obs_date)::date as month_start,
    max(obs_date) as payments_date,
    arg_max(value, obs_date) as scheduled_repayments_to_income
from {{ ref('stg_series') }}
where series_id = 'LPHTSPRI'
group by 1
