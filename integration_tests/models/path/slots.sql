{{config(
    materialized='table',
    sql_header=bq_reservations.assign_from_config(),
    tags=['dbt_core_v1', 'dbt_core_latest', 'dbt_core_v2']
)}}
SELECT
    '{{model.unique_id}}' AS model_id,
    '{{ bq_reservations.assign_from_config() }}' AS reservation
