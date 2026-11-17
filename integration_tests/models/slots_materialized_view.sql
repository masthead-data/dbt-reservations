{{config(
    materialized='materialized_view',
    enable_refresh=false,
)}}

{% if reservation_method() == 'native' %}
    {{ config(reservation=bq_reservations.get_name_from_config()) }}
{% else %}
    {{ config(sql_header=bq_reservations.assign_from_config()) }}
{% endif %}

/*
    '{{ model.unique_id }}' AS model_id,
    '{{ bq_reservations.assign_from_config() }}' AS assign_from_config,
    '{{ bq_reservations.get_name_from_config() }}' AS get_name_from_config
*/

SELECT
    model_id,
    assign_from_config,
    get_name_from_config
FROM {{ ref('slots') }}
