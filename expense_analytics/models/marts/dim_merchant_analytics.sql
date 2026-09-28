{{ config(materialized='table') }}

with transactions as (
    select * from {{ ref('stg_gpay_transactions') }}
)

select
    merchant_name,
    count(transaction_id) as visitation_frequency,
    sum(case when transaction_direction = 'DEBIT' then transaction_amount else 0 end) as lifetime_spent_at_merchant
from transactions
group by 1
order by 3 desc
