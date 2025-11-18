{{config(
    materialized='table',
    sql_header=bq_reservations.assign_from_config()
)}}
SELECT
    '{{model.unique_id}}' AS model_id,
    '{{ bq_reservations.assign_from_config() }}' AS reservation
