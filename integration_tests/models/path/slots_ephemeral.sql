{{config(
    materialized='ephemeral',
    sql_header=bq_reservations.assign_from_config()
)}}
SELECT
    *,
    '{{ bq_reservations.assign_from_config() }}' AS reservation_toplevel
FROM {{ ref('slots') }}
