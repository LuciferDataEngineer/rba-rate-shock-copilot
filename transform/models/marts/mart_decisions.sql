select
    effective_date,
    previous_target,
    new_target,
    change_bp,
    case when change_bp > 0 then 'increase' else 'decrease' end as direction,
    extract(year from effective_date)::integer as effective_year
from {{ ref('int_policy_changes') }}
where effective_date >= date '2024-01-01'
