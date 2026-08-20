select
    get_name_from_config
from {{ ref('on_demand') }}
WHERE get_name_from_config IS NULL
