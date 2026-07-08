{% macro get_name_from_config() -%}
{%- set cfg = var('RESERVATION_CONFIG_NATIVE', default=[]) -%}
{%- set model_id = (model.unique_id if (model is defined and model.unique_id is defined) else (this.identifier if (this is defined) else None)) -%}

{%- if not model_id -%}
  {{ return(none) }}
{%- else -%}
  {%- set parts = model_id.split('.') -%}
  {%- if parts | length > 1 and parts[0] in ('model', 'snapshot', 'seed', 'test') -%}
    {%- set parts = parts[1:] -%}
  {%- endif -%}
  {%- set norm_id = parts | join('.') -%}

  {%- set ns = namespace(found=False, reservation=none) -%}
  {%- for entry in cfg -%}
    {%- if not ns.found -%}
      {%- set models = entry.get('models') or [] -%}
      {%- for raw_m in models -%}
        {%- if not ns.found -%}
          {%- set m_parts = raw_m.split('.') -%}
          {%- if m_parts | length > 1 and m_parts[0] in ('model', 'snapshot', 'seed', 'test') -%}
            {%- set m_parts = m_parts[1:] -%}
          {%- endif -%}
          {%- set norm_m = m_parts | join('.') -%}
          {%- if norm_id == norm_m or norm_id == norm_m.split('.')[-1] or norm_m == norm_id.split('.')[-1] -%}
            {%- set ns.found = True -%}
            {%- set ns.reservation = entry.get('reservation') -%}
          {%- endif -%}
        {%- endif -%}
      {%- endfor -%}
    {%- endif -%}
  {%- endfor -%}
  {%- if ns.found -%}
    {{ return(ns.reservation) }}
  {%- else -%}
    {{ return(none) }}
  {%- endif -%}
{%- endif -%}
{%- endmacro %}
