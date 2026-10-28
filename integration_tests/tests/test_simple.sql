{# Note: In dbt-core v1.x, the test runner wraps tests as a single SELECT query without
   sql_header injection, running tests on the project default. Reservation assignment for
   tests requires dbt-core v2+ native config. #}
{% if reservation_method() == 'native' %}
    {{ config(reservation=bq_reservations.get_name_from_config()) }}
{% endif %}

SELECT *
FROM (
    SELECT 1 AS id
)
WHERE id = 0
