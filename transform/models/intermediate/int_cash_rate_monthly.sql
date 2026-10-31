with daily as (
    select obs_date, value as cash_rate_target
    from {{ ref('stg_series') }}
    where series_id = 'FIRMMCRTD'
),
month_end as (
    select
        date_trunc('month', obs_date)::date as month_start,
        arg_max(cash_rate_target, obs_date) as cash_rate_target,
        max(obs_date) as cash_rate_date
    from daily
    group by 1
)
select * from month_end
