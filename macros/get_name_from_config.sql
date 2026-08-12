{% macro get_bigquery_reservation_config(project_name=none) -%}
  {{- return(adapter.dispatch('get_bigquery_reservation_config', 'bq_reservations')(project_name=project_name)) -}}
{%- endmacro %}

{% macro default__get_bigquery_reservation_config(project_name=none) -%}
  {{ return(var('RESERVATION_CONFIG', default=[])) }}
{%- endmacro %}

{% macro match_reservation_from_entries(entries, model_id) -%}
  {%- if entries and model_id -%}
    {%- set parts = model_id.split('.') -%}
    {%- if parts | length > 1 and parts[0] in ('model', 'snapshot', 'seed', 'test') -%}
      {%- set parts = parts[1:] -%}
    {%- endif -%}
    {%- set norm_id = parts | join('.') -%}

    {%- set ns = namespace(found=False, reservation=none) -%}
    {%- for entry in entries -%}
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
  {%- else -%}
    {{ return(none) }}
  {%- endif -%}
{%- endmacro %}

{% macro get_name_from_config() -%}
{%- set scope = var('reservation_project', (model.package_name if (model is defined and model.package_name is defined) else project_name)) -%}
{%- set getter = (bq_reservations.get_bigquery_reservation_config if (bq_reservations is defined and bq_reservations.get_bigquery_reservation_config is defined) else get_bigquery_reservation_config) -%}
{%- set raw_cfg = getter(project_name=scope) -%}

{%- if raw_cfg is string and fromyaml is defined -%}
  {%- set raw_cfg = fromyaml(raw_cfg) -%}
{%- endif -%}

{%- set cfg = none -%}
{%- if raw_cfg is mapping -%}
  {%- set cfg = raw_cfg.get(scope) -%}
{%- elif raw_cfg is iterable and raw_cfg is not string -%}
  {%- set cfg = raw_cfg -%}
{%- endif -%}

{%- set model_id = (model.unique_id if (model is defined and model.unique_id is defined) else (this.identifier if (this is defined) else None)) -%}

{# 1. Check central configuration #}
{%- set matcher = (bq_reservations.match_reservation_from_entries if (bq_reservations is defined and bq_reservations.match_reservation_from_entries is defined) else match_reservation_from_entries) -%}
{%- set res = matcher(cfg, model_id) -%}
{%- if res is not none and res != '' and res != 'None' -%}
  {{ return(res) }}
{%- else -%}
  {# 2. Fallback to local project variables #}
  {%- set local_cfg = var('RESERVATION_CONFIG', default=[]) -%}
  {%- set local_res = matcher(local_cfg, model_id) -%}
  {%- if local_res is not none and local_res != '' and local_res != 'None' -%}
    {{ return(local_res) }}
  {%- else -%}
    {{ return(none) }}
  {%- endif -%}
{%- endif -%}
{%- endmacro %}
