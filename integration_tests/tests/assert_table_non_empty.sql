select
    reservation
from {{ ref('on_demand') }}
WHERE reservation IS NULL
