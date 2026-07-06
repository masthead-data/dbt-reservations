{% if (dbt_version.split('.')[0] | int) >= 2 %}
    {{ config(reservation=bq_reservations.get_name_from_config()) }}
{% endif %}

SELECT *
FROM (
    SELECT 1 AS id
)
WHERE id = 0
