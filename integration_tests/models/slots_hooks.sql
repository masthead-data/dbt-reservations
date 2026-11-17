{{config(
    materialized='table',
    pre_hook="SELECT 1 /* pre_hook: {{ bq_reservations.get_name_from_config() }} */",
    post_hook="SELECT 1 /* post_hook: {{ bq_reservations.get_name_from_config() }} */"
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
