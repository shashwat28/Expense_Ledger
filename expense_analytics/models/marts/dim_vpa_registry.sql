{{ config(materialized='table') }}

with staging_data as (
    select distinct
        upi_vpa,
        merchant_name as extracted_gpay_name
    from {{ ref('stg_gpay_transactions') }}
    where upi_vpa is not null and upi_vpa != 'N/A'
)

select
    upi_vpa as vpa_address,
    extracted_gpay_name,
    -- Future Feedback Injection Point
    -- For now, initialized as a completely blank string text block for manual entry maps later
    cast(null as string) as customized_merchant_description,
    current_timestamp() as row_created_at
from staging_data
