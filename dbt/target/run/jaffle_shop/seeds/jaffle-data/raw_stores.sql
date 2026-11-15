
    
    
    
    create  table `analytics`.`raw`.`raw_stores` (`id` string ,`name` string ,`opened_at` timestamp ,`tax_rate` double )
    
    
      using delta
    
  
    
    
    
    
    
  ;
    -- dbt seed --
    
          insert overwrite `analytics`.`raw`.`raw_stores` values
          (%s,%s,%s,%s),(%s,%s,%s,%s),(%s,%s,%s,%s),(%s,%s,%s,%s),(%s,%s,%s,%s),(%s,%s,%s,%s)
      

;
  