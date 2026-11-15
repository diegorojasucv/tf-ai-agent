



select
    1
from `analytics`.`diego_rojas`.`orders`

where not(order_total = subtotal + tax_paid)

