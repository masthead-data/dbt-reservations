{{config(
    materialized='materialized_view',
    enable_refresh=false,
)}}

{% if (dbt_version.split('.')[0] | int) >= 2 %}
    {{ config(reservation=bq_reservations.get_name_from_config()) }}
{% elif (dbt_version.split('.')[0] | int) == 1 %}
    {{ config( sql_header=bq_reservations.assign_from_config()) }}
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
