{{config(
    materialized='incremental',
    unique_key='model_id'
)}}

{% if reservation_method() == 'native' %}
    {{ config(reservation=bq_reservations.get_name_from_config()) }}
{% else %}
    {{ config(sql_header=bq_reservations.assign_from_config()) }}
{% endif %}

SELECT
    '{{ model.unique_id }}' AS model_id,
    '{{ bq_reservations.assign_from_config() }}' AS assign_from_config,
    '{{ bq_reservations.get_name_from_config() }}' AS get_name_from_config
FROM (SELECT 1 AS dummy)

{% if is_incremental() %}
    WHERE '{{ model.unique_id }}' NOT IN (SELECT model_id FROM {{ this }})
{% endif %}
