
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select supply_uuid
from `analytics`.`diego_rojas`.`stg_supplies`
where supply_uuid is null



  
  
      
    ) dbt_internal_test