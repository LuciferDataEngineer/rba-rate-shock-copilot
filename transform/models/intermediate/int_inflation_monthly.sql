with quarterly as (
    select
        date_trunc('month', obs_date)::date as month_start,
        max(case when series_id = 'GCPIAGYP' then value end) as cpi_yoy_quarterly,
        max(case when series_id = 'GCPIOCPMTMYP' then value end) as trimmed_mean_yoy_quarterly
    from {{ ref('stg_series') }}
    where series_id in ('GCPIAGYP', 'GCPIOCPMTMYP')
    group by 1
),
monthly as (
    select
        month_start,
        max(case when series_name = 'headline_yoy' then value end) as cpi_yoy_monthly,
        max(case when series_name = 'trimmed_mean_yoy' then value end) as trimmed_mean_yoy_monthly
    from {{ ref('stg_abs_cpi_monthly') }}
    group by 1
)
select
    coalesce(monthly.month_start, quarterly.month_start) as month_start,
    quarterly.cpi_yoy_quarterly,
    quarterly.trimmed_mean_yoy_quarterly,
    monthly.cpi_yoy_monthly,
    monthly.trimmed_mean_yoy_monthly
from monthly
full outer join quarterly using (month_start)
