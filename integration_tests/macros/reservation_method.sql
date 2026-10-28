{# Which assignment mechanism the test models use: 'native' (config.reservation, dbt v2+)
   or 'sql_header' (SET @@reservation, works on any engine that renders sql_header).
   Override per run with --vars '{reservation_method: sql_header}'. #}
{% macro reservation_method() -%}
{%- set method = var('reservation_method', 'auto') -%}
{%- if method == 'auto' -%}
  {{ return('native' if (dbt_version.split('.')[0] | int) >= 2 else 'sql_header') }}
{%- endif -%}
{{ return(method) }}
{%- endmacro %}
