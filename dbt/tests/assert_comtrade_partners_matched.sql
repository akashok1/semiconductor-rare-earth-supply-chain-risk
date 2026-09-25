-- Every Comtrade partner code has a row in Comtrade's partner list, so no
-- partner reaches the marts without an ISO3 and name.

select distinct c.partner_code
from {{ ref('stg_comtrade') }} as c
left join {{ ref('stg_comtrade_partners') }} as p
    on p.partner_code = c.partner_code
where p.partner_code is null
