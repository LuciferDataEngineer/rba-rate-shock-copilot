{{ config(materialized='table') }}

select unnest(
    generate_series(date '2022-01-01', date '2026-12-31', interval 1 day)
)::date as date_day
