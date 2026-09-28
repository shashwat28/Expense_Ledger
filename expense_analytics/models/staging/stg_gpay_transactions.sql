{{ config(materialized='view') }}

with raw_source as (
    select * from {{ source('bronze_gpay', 'GPAY_TRANSACTIONS') }}
)

select
    -- Standardise business tracking fields and enforce strict casting types
    md5(cast(transaction_id as string)) as transaction_key, -- Surrogate hash key
    cast(transaction_id as string) as transaction_id,
    CASE WHEN LEFT(CAST(TRANSACTION_TIMESTAMP AS STRING), 4) = '2026' THEN
    TO_CHAR(TO_TIMESTAMP_NTZ(CAST(TRANSACTION_TIMESTAMP AS STRING), 'YYYY-MM-DD HH24:MI:SS.FF3'),'DD-MM-YY HH24:MI:SS.FF3')
    ELSE
    TO_CHAR(TO_TIMESTAMP_NTZ('20' 
    || SUBSTR(CAST(TRANSACTION_TIMESTAMP AS STRING), 9, 2)   -- Year (26)
    || '-' || SUBSTR(CAST(TRANSACTION_TIMESTAMP AS STRING), 6, 2)   -- Month (09)
    || '-' || SUBSTR(CAST(TRANSACTION_TIMESTAMP AS STRING), 3, 2)   -- Day (25)
    || SUBSTR(CAST(TRANSACTION_TIMESTAMP AS STRING), 11),           -- Time component
    'YYYY-MM-DD HH24:MI:SS.FF3'),'DD-MM-YY HH24:MI:SS.FF3')
    END AS transaction_at,
    {{ clean_amount('amount') }} as transaction_amount, -- Macro to ensure absolute data normalization for currencies
    trim(upper(recipient_name)) as merchant_name,
    lower(vpa_address) as upi_vpa,
    trim(source_account) as source_bank,
    trim(type) as transaction_direction, -- DEBIT vs CREDIT
    email_subject
from raw_source
where transaction_id is not null 
  and transaction_id != 'N/A' -- Data cleansing rule
