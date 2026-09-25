-- HHI lies on the 0-10,000 scale and is never null.

select canonical_product_id, year, hhi
from {{ ref('fct_concentration') }}
where hhi is null or hhi < 0 or hhi > 10000
