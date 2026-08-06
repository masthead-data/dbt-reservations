{% macro default__get_bigquery_reservation_config(project_name=none) %}
    {%- set all_configs = {
        'centralized_integration_test': [
            {
                'reservation': 'projects/masthead-dev/locations/us/reservations/central-capacity',
                'models': [
                    'model.centralized_integration_test.central_model'
                ]
            },
            {
                'reservation': 'none',
                'models': [
                    'model.centralized_integration_test.central_on_demand_model'
                ]
            }
        ]
    } -%}

    {%- if project_name -%}
        {{ return(all_configs.get(project_name) or []) }}
    {%- else -%}
        {{ return(all_configs) }}
    {%- endif -%}
{% endmacro %}
