{{config(
    materialized='table',
    reservation='',
    tags=['dbt_core_v1', 'dbt_core_latest', 'dbt_core_v2', 'dbt_core_fusion_latest']
)}}
SELECT
    '{{model.unique_id}}' AS model_id
