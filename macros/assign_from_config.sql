{% macro assign_from_config(prefix='SET @@reservation=') -%}
{%- set reservation = bq_reservations.get_name_from_config() if (bq_reservations is defined and bq_reservations.get_name_from_config is defined) else (get_name_from_config() if get_name_from_config is defined else none) -%}
{%- if reservation is not none and reservation | string | trim != '' -%}
  {%- if reservation == 'none' -%}
    {{ prefix }} "none";
  {%- else -%}
    {{ prefix }} "{{ reservation }}";
  {%- endif -%}
{%- endif -%}
{%- endmacro %}
