{% snapshot snp_gpay_transactions %}

{{
    config(
      target_database='ANALYTICS_DB',
      target_schema='snapshots',
      unique_key='transaction_id',
      strategy='check',
      check_cols=['type', 'amount'],
    )
}}

-- The underlying query dbt will monitor for changes
select 
    transaction_id,
    transaction_timestamp,
    amount,
    type,
    recipient_name
from {{ source('bronze_gpay', 'GPAY_TRANSACTIONS') }}

{% endsnapshot %}
