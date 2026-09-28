{% macro clean_amount(column_name) %}
    -- A reusable macro that ensures absolute data normalization for currencies
    coalesce(cast(replace(cast({{ column_name }} as string), ',', '') as number(10,2)), 0.00)
{% endmacro %}
