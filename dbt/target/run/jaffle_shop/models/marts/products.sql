
  
    
        create or replace table `analytics`.`diego_rojas`.`products`
      
      
    
      using delta
    
  
      
      
      
      
      
      
      
      
      as
      with

products as (

    select * from `analytics`.`diego_rojas`.`stg_products`

)

select * from products
  