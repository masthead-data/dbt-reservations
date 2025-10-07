{{config(
    materialized='table',
    sql_header=bq_reservations.assign_from_config()
)}}

select '{{ bq_reservations.assign_from_config() }}' as reservation
