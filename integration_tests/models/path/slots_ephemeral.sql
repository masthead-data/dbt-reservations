{{config(
    materialized='ephemeral',
    sql_header=bq_reservations.assign_from_config()
)}}
SELECT
    *,
    '{{ bq_reservations.assign_from_config() }}' AS reservation
FROM {{ ref('slots') }}
