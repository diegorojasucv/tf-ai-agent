
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  



select
    1
from `analytics`.`diego_rojas`.`stg_orders`

where not(order_total - tax_paid = subtotal)


  
  
      
    ) dbt_internal_test