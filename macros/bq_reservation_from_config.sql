{% macro bq_reservation_from_config(prefix='SET @@reservation=') -%}
{%- set cfg = var('RESERVATION_CONFIG', default=[]) -%}
{%- set model_id = (model.unique_id if (model is defined and model.unique_id is defined) else (this.identifier if (this is defined) else None)) -%}

{%- if not model_id -%}
-- bq_reservation_from_config: no model id available
{%- else -%}
  {%- set ns = namespace(matched=None) -%}
  {%- for entry in cfg -%}
    {%- set models = entry.get('models') or [] -%}
    {%- if ns.matched is none and model_id in models -%}
      {%- set ns.matched = entry -%}
    {%- endif -%}
  {%- endfor -%}
  {%- set matched = ns.matched -%}

  {%- if matched is none -%}
-- bq_reservation_from_config: no matching reservation rule for {{ model_id }}
  {%- else -%}
    {%- set reservation = matched.get('reservation') -%}
    {%- if reservation is none or reservation == 'none' -%}
-- bq_reservation_from_config: reservation explicitly none for {{ model_id }}
    {%- else -%}
{{ prefix }} "{{ reservation }}"
    {%- endif -%}
  {%- endif -%}
{%- endif -%}
{%- endmacro %}
