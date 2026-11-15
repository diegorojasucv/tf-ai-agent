
  
    
        create or replace table `analytics`.`diego_rojas`.`supplies`
      
      
    
      using delta
    
  
      
      
      
      
      
      
      
      
      as
      with

supplies as (

    select * from `analytics`.`diego_rojas`.`stg_supplies`

)

select * from supplies
  