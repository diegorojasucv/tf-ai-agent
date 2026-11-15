
  
  
  
  create or replace view `analytics`.`diego_rojas`.`stg_customers`
  
  as (
    with

source as (

    select * from `analytics`.`raw`.`raw_customers`

),

renamed as (

    select

        ----------  ids
        id as customer_id,

        ---------- text
        name as customer_name

    from source

)

select * from renamed
  )
