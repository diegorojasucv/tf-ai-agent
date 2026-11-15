
    
    
    
    create  table `analytics`.`raw`.`raw_products` (`sku` string ,`name` string ,`type` string ,`price` bigint ,`description` string )
    
    
      using delta
    
  
    
    
    
    
    
  ;
    -- dbt seed --
    
          insert overwrite `analytics`.`raw`.`raw_products` values
          (%s,%s,%s,%s,%s),(%s,%s,%s,%s,%s),(%s,%s,%s,%s,%s),(%s,%s,%s,%s,%s),(%s,%s,%s,%s,%s),(%s,%s,%s,%s,%s),(%s,%s,%s,%s,%s),(%s,%s,%s,%s,%s),(%s,%s,%s,%s,%s),(%s,%s,%s,%s,%s)
      

;
  