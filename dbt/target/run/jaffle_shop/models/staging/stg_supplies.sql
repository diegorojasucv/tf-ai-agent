
  
  
  
  create or replace view `analytics`.`diego_rojas`.`stg_supplies`
  
  as (
    with

source as (

    select * from `analytics`.`raw`.`raw_supplies`

),

renamed as (

    select

        ----------  ids
        md5(cast(concat(coalesce(cast(id as string), '_dbt_utils_surrogate_key_null_'), '-', coalesce(cast(sku as string), '_dbt_utils_surrogate_key_null_')) as string)) as supply_uuid,
        id as supply_id,
        sku as product_id,

        ---------- text
        name as supply_name,

        ---------- numerics
        (cost / 100)::numeric(16, 2) as supply_cost,

        ---------- booleans
        perishable as is_perishable_supply

    from source

)

select * from renamed
  )
