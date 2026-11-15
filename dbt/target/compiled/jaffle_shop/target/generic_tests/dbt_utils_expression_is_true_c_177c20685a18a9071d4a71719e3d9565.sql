



select
    1
from `analytics`.`diego_rojas`.`customers`

where not(lifetime_spend_pretax + lifetime_tax_paid = lifetime_spend)

