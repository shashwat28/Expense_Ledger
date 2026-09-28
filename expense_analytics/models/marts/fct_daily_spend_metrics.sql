{{
    config(
        materialized='incremental',
        unique_key='execution_date'
    )
}}

with transactions as (
    select * from {{ ref('stg_gpay_transactions') }}
)

select
    cast(transaction_at as date) as execution_date,
    count(case when transaction_direction = 'DEBIT' then 1 end) as total_debit_count,
    sum(case when transaction_direction = 'DEBIT' then transaction_amount else 0 end) as total_amount_spent,
    sum(case when transaction_direction = 'CREDIT' then transaction_amount else 0 end) as total_amount_received,
    avg(case when transaction_direction = 'DEBIT' then transaction_amount end) as average_transaction_value
from transactions

{% if is_incremental() %}
  -- This compilation condition only executes on subsequent runs to protect performance boundaries
  where cast(transaction_at as date) >= (select max(execution_date) from {{ this }})
{% endif %}

group by 1
order by 1 desc
