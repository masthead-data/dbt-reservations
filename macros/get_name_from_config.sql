{% macro get_name_from_config() -%}
{%- set cfg = var('RESERVATION_CONFIG', default=[]) -%}
{%- set model_id = (model.unique_id if (model is defined and model.unique_id is defined) else (this.identifier if (this is defined) else None)) -%}

{%- if model_id -%}
  {%- set parts = model_id.split('.') -%}
  {%- if parts | length > 1 and parts[0] in ('model', 'snapshot', 'test') -%}
    {%- set norm_id = parts[1:] | join('.') -%}
  {%- else -%}
    {%- set norm_id = model_id -%}
  {%- endif -%}

  {%- set ns = namespace(matched=false, reservation=none) -%}
  {%- for entry in cfg -%}
    {%- if not ns.matched -%}
      {%- for raw_m in (entry.get('models') or []) -%}
        {%- if not ns.matched -%}
          {%- set m_parts = raw_m.split('.') -%}
          {%- if m_parts | length > 1 and m_parts[0] in ('model', 'snapshot', 'test') -%}
            {%- set norm_m = m_parts[1:] | join('.') -%}
          {%- else -%}
            {%- set norm_m = raw_m -%}
          {%- endif -%}
          {%- if norm_id == norm_m or norm_id == raw_m -%}
            {%- set ns.matched = true -%}
            {%- set ns.reservation = entry.get('reservation') -%}
          {%- endif -%}
        {%- endif -%}
      {%- endfor -%}
    {%- endif -%}
  {%- endfor -%}
  {%- if ns.matched -%}
    {{ return(ns.reservation) }}
  {%- endif -%}
{%- endif -%}
{{ return(none) }}
{%- endmacro %}
