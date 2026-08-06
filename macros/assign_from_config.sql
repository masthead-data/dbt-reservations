{% macro assign_from_config(prefix='SET @@reservation=') -%}
{%- set getter = (bq_reservations.get_name_from_config if (bq_reservations is defined and bq_reservations.get_name_from_config is defined) else get_name_from_config) -%}
{%- set reservation = getter() -%}
{%- if reservation is not none and reservation and reservation != 'None' -%}
  {{ prefix }} "{{ reservation }}";
{%- else -%}
  {{ return(none) }}
{%- endif -%}
{%- endmacro %}
