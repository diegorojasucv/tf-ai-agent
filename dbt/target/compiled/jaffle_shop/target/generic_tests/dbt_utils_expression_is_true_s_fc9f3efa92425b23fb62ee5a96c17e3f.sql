



select
    1
from `analytics`.`diego_rojas`.`stg_orders`

where not(order_total - tax_paid = subtotal)

