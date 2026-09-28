-- Business Rule validation: Total daily spend must always be zero or a positive amount.
-- If any row returns a negative value, this test will trigger a failure flag.
select
    execution_date,
    total_amount_spent
from {{ ref('fct_daily_spend_metrics') }}
where total_amount_spent < 0
