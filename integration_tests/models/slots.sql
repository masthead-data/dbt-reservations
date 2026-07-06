{{config(
    materialized='table'
)}}

{% if (dbt_version.split('.')[0] | int) >= 2 %}
    {{ config(reservation=bq_reservations.get_name_from_config()) }}
{% elif (dbt_version.split('.')[0] | int) == 1 %}
    {{ config(
        sql_header=bq_reservations.assign_from_config()
    ) }}
{% endif %}

SELECT
    '{{model.unique_id}}' AS model_id,
    '{{ bq_reservations.get_name_from_config() }}' AS reservation
