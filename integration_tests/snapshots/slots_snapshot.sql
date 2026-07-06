{% snapshot slots_snapshot %}

{{
    config(
      target_database=var('target_database', target.project),
      target_schema=var('target_schema', target.dataset),
      unique_key='reservation',
      strategy='check',
      check_cols='all',
      hard_deletes='invalidate'
    )
}}

{% if (dbt_version.split('.')[0] | int) >= 2 %}
    {{ config(reservation=bq_reservations.get_name_from_config()) }}
{% elif (dbt_version.split('.')[0] | int) == 1 %}
    {{ config(
        sql_header=bq_reservations.assign_from_config()
    ) }}
{% endif %}

select
    model_id,
    reservation
from {{ ref('slots_ephemeral') }}

{% endsnapshot %}
