{% macro assign_from_config(prefix='SET @@reservation=') -%}
{%- set cfg = var('RESERVATION_CONFIG', default=[]) -%}
{%- set model_id = (model.unique_id if (model is defined and model.unique_id is defined) else (this.identifier if (this is defined) else None)) -%}

{%- if not model_id -%}
{%- else -%}
  {%- set parts = model_id.split('.') -%}
  {%- if parts | length > 1 and parts[0] in ('model', 'snapshot', 'seed', 'test') -%}
    {%- set parts = parts[1:] -%}
  {%- endif -%}
  {%- set norm_id = parts | join('.') -%}

  {%- set ns = namespace(matched=None) -%}
  {%- for entry in cfg -%}
    {%- set models = entry.get('models') or [] -%}
    {%- for raw_m in models -%}
      {%- if ns.matched is none -%}
        {%- set m_parts = raw_m.split('.') -%}
        {%- if m_parts | length > 1 and m_parts[0] in ('model', 'snapshot', 'seed', 'test') -%}
          {%- set m_parts = m_parts[1:] -%}
        {%- endif -%}
        {%- set norm_m = m_parts | join('.') -%}
        {%- if norm_id == norm_m or norm_id == norm_m.split('.')[-1] or norm_m == norm_id.split('.')[-1] -%}
          {%- set ns.matched = entry -%}
        {%- endif -%}
      {%- endif -%}
    {%- endfor -%}
  {%- endfor -%}
  {%- set matched = ns.matched -%}
  {%- if matched is none -%}
  {%- else -%}
    {%- set reservation = matched.get('reservation') -%}
    {%- if reservation is none -%}
    {%- elif reservation == 'none' -%}
      {{ prefix }} "none";
    {%- else -%}
      {{ prefix }} "{{ reservation }}";
    {%- endif -%}
  {%- endif -%}
{%- endif -%}
{%- endmacro %}
