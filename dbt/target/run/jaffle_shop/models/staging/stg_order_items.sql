
  
  
  
  create or replace view `analytics`.`diego_rojas`.`stg_order_items`
  
  as (
    with

source as (

    select * from `analytics`.`raw`.`raw_items`

),

renamed as (

    select

        ----------  ids
        id as order_item_id,
        order_id,
        sku as product_id

    from source

)

select * from renamed
  )
