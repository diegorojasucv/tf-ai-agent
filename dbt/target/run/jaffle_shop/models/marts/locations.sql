
  
    
        create or replace table `analytics`.`diego_rojas`.`locations`
      
      
    
      using delta
    
  
      
      
      
      
      
      
      
      
      as
      with

locations as (

    select * from `analytics`.`diego_rojas`.`stg_locations`

)

select * from locations
  