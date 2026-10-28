{% snapshot slots_snapshot %}

{{
    config(
      target_database=var('target_database', target.project),
      target_schema=var('target_schema', target.dataset),
      unique_key='get_name_from_config',
      strategy='check',
      check_cols='all',
      hard_deletes='invalidate'
    )
}}

{% if reservation_method() == 'native' %}
    {{ config(reservation=bq_reservations.get_name_from_config()) }}
{% elif (dbt_version.split('.')[0] | int) < 2 %}
    {# dbt v2 rejects sql_header on snapshots (dbt1060), so there is no sql_header fallback there #}
    {{ config(sql_header=bq_reservations.assign_from_config()) }}
{% endif %}

select
    model_id,
    assign_from_config,
    get_name_from_config
from {{ ref('slots_ephemeral') }}

{% endsnapshot %}
