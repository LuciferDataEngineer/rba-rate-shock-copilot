with bounds as (
    select
        date '2022-01-01' as start_month,
        date_trunc('month', max(cash_rate_date))::date as end_month
    from {{ ref('int_cash_rate_monthly') }}
),
months as (
    select unnest(generate_series(
        (select start_month from bounds),
        (select end_month from bounds),
        interval 1 month
    ))::date as month_start
),
baseline as (
    select
        (select cash_rate_target from {{ ref('int_cash_rate_monthly') }} where month_start = date '2026-01-01') as cash_rate_jan_2026,
        (select housing_variable_rate from {{ ref('int_housing_monthly') }} where month_start = date '2026-01-01') as housing_rate_jan_2026
),
joined as (
    select
        months.month_start,
        cash.cash_rate_date,
        cash.cash_rate_target,
        housing.housing_rate_date,
        housing.housing_variable_rate,
        labour.labour_date,
        labour.unemployment_rate,
        inflation.cpi_yoy_monthly,
        inflation.trimmed_mean_yoy_monthly,
        inflation.cpi_yoy_quarterly,
        inflation.trimmed_mean_yoy_quarterly,
        payments.scheduled_repayments_to_income,
        (
            select awe.weekly_earnings
            from {{ ref('stg_abs_awe') }} as awe
            where awe.period_start <= months.month_start
            order by awe.period_start desc
            limit 1
        ) as weekly_ordinary_earnings,
        baseline.cash_rate_jan_2026,
        baseline.housing_rate_jan_2026
    from months
    cross join baseline
    left join {{ ref('int_cash_rate_monthly') }} as cash using (month_start)
    left join {{ ref('int_housing_monthly') }} as housing using (month_start)
    left join {{ ref('int_labour_monthly') }} as labour using (month_start)
    left join {{ ref('int_inflation_monthly') }} as inflation using (month_start)
    left join {{ ref('int_payments_quarterly') }} as payments using (month_start)
)
select
    month_start,
    cash_rate_date,
    cash_rate_target,
    housing_rate_date,
    housing_variable_rate,
    labour_date,
    unemployment_rate,
    cpi_yoy_monthly,
    trimmed_mean_yoy_monthly,
    cpi_yoy_quarterly,
    trimmed_mean_yoy_quarterly,
    coalesce(trimmed_mean_yoy_monthly, trimmed_mean_yoy_quarterly) as trimmed_mean_yoy,
    coalesce(cpi_yoy_monthly, cpi_yoy_quarterly) as headline_inflation_yoy,
    cash_rate_target - coalesce(trimmed_mean_yoy_monthly, trimmed_mean_yoy_quarterly) as real_cash_rate,
    coalesce(trimmed_mean_yoy_monthly, trimmed_mean_yoy_quarterly) - 2.5 as inflation_gap,
    round((cash_rate_target - cash_rate_jan_2026) * 100)::integer as cumulative_hike_bp,
    {{ monthly_repayment(100000, 'housing_variable_rate') }} as repayment_per_100k,
    {{ monthly_repayment(600000, 'housing_variable_rate') }} as repayment_600k,
    {{ monthly_repayment(600000, 'housing_rate_jan_2026') }} as repayment_600k_jan_2026,
    {{ monthly_repayment(600000, 'housing_variable_rate') }}
        - {{ monthly_repayment(600000, 'housing_rate_jan_2026') }} as extra_repayment_600k_since_jan,
    weekly_ordinary_earnings,
    case
        when weekly_ordinary_earnings is null or housing_variable_rate is null then null
        else {{ monthly_repayment(600000, 'housing_variable_rate') }}
            / (weekly_ordinary_earnings * 52.0 / 12.0)
    end as mortgage_repayment_to_income,
    scheduled_repayments_to_income,
    cash_rate_jan_2026,
    housing_rate_jan_2026
from joined
