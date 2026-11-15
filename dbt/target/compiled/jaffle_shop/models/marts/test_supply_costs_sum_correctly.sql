-- Build actual result given inputs
WITH
            	analytics_diego_rojas_stg_supplies as (SELECT CAST(NULL AS string) AS supply_uuid, CAST(NULL AS string) AS supply_id, CAST(1 AS string) AS product_id, CAST(NULL AS string) AS supply_name, CAST(4.5 AS decimal(16,2)) AS supply_cost, CAST(NULL AS boolean) AS is_perishable_supply
UNION ALL
SELECT CAST(NULL AS string) AS supply_uuid, CAST(NULL AS string) AS supply_id, CAST(2 AS string) AS product_id, CAST(NULL AS string) AS supply_name, CAST(3.5 AS decimal(16,2)) AS supply_cost, CAST(NULL AS boolean) AS is_perishable_supply
UNION ALL
SELECT CAST(NULL AS string) AS supply_uuid, CAST(NULL AS string) AS supply_id, CAST(2 AS string) AS product_id, CAST(NULL AS string) AS supply_name, CAST(5.0 AS decimal(16,2)) AS supply_cost, CAST(NULL AS boolean) AS is_perishable_supply),
  	analytics_diego_rojas_stg_products as (SELECT CAST(1 AS string) AS product_id, CAST(NULL AS string) AS product_name, CAST(NULL AS string) AS product_type, CAST(NULL AS string) AS product_description, CAST(NULL AS decimal(16,2)) AS product_price, CAST(NULL AS boolean) AS is_food_item, CAST(NULL AS boolean) AS is_drink_item
UNION ALL
SELECT CAST(2 AS string) AS product_id, CAST(NULL AS string) AS product_name, CAST(NULL AS string) AS product_type, CAST(NULL AS string) AS product_description, CAST(NULL AS decimal(16,2)) AS product_price, CAST(NULL AS boolean) AS is_food_item, CAST(NULL AS boolean) AS is_drink_item),
  	analytics_diego_rojas_stg_order_items as (SELECT CAST(NULL AS string) AS order_item_id, CAST(1 AS string) AS order_id, CAST(1 AS string) AS product_id
UNION ALL
SELECT CAST(NULL AS string) AS order_item_id, CAST(2 AS string) AS order_id, CAST(2 AS string) AS product_id
UNION ALL
SELECT CAST(NULL AS string) AS order_item_id, CAST(2 AS string) AS order_id, CAST(2 AS string) AS product_id),
  	analytics_diego_rojas_stg_orders as (SELECT CAST(1 AS string) AS order_id, CAST(NULL AS string) AS location_id, CAST(NULL AS string) AS customer_id, CAST(NULL AS bigint) AS subtotal_cents, CAST(NULL AS bigint) AS tax_paid_cents, CAST(NULL AS bigint) AS order_total_cents, CAST(NULL AS decimal(16,2)) AS subtotal, CAST(NULL AS decimal(16,2)) AS tax_paid, CAST(NULL AS decimal(16,2)) AS order_total, CAST(NULL AS timestamp) AS ordered_at
UNION ALL
SELECT CAST(2 AS string) AS order_id, CAST(NULL AS string) AS location_id, CAST(NULL AS string) AS customer_id, CAST(NULL AS bigint) AS subtotal_cents, CAST(NULL AS bigint) AS tax_paid_cents, CAST(NULL AS bigint) AS order_total_cents, CAST(NULL AS decimal(16,2)) AS subtotal, CAST(NULL AS decimal(16,2)) AS tax_paid, CAST(NULL AS decimal(16,2)) AS order_total, CAST(NULL AS timestamp) AS ordered_at),
  	analytics_diego_rojas_order_items_expect as (SELECT CAST(NULL AS string) AS order_item_id, CAST(1 AS string) AS order_id, CAST(1 AS string) AS product_id, CAST(NULL AS timestamp) AS ordered_at, CAST(NULL AS string) AS product_name, CAST(NULL AS decimal(16,2)) AS product_price, CAST(NULL AS boolean) AS is_food_item, CAST(NULL AS boolean) AS is_drink_item, CAST(4.5 AS decimal(26,2)) AS supply_cost
UNION ALL
SELECT CAST(NULL AS string) AS order_item_id, CAST(2 AS string) AS order_id, CAST(2 AS string) AS product_id, CAST(NULL AS timestamp) AS ordered_at, CAST(NULL AS string) AS product_name, CAST(NULL AS decimal(16,2)) AS product_price, CAST(NULL AS boolean) AS is_food_item, CAST(NULL AS boolean) AS is_drink_item, CAST(8.5 AS decimal(26,2)) AS supply_cost
UNION ALL
SELECT CAST(NULL AS string) AS order_item_id, CAST(2 AS string) AS order_id, CAST(2 AS string) AS product_id, CAST(NULL AS timestamp) AS ordered_at, CAST(NULL AS string) AS product_name, CAST(NULL AS decimal(16,2)) AS product_price, CAST(NULL AS boolean) AS is_food_item, CAST(NULL AS boolean) AS is_drink_item, CAST(8.5 AS decimal(26,2)) AS supply_cost),
  	analytics_diego_rojas_order_items_actual as (with

order_items as (

    select * from analytics_diego_rojas_stg_order_items

),


orders as (

    select * from analytics_diego_rojas_stg_orders

),

products as (

    select * from analytics_diego_rojas_stg_products

),

supplies as (

    select * from analytics_diego_rojas_stg_supplies

),

order_supplies_summary as (

    select
        product_id,

        sum(supply_cost) as supply_cost

    from supplies

    group by 1

),

joined as (

    select
        order_items.*,

        orders.ordered_at,

        products.product_name,
        products.product_price,
        products.is_food_item,
        products.is_drink_item,

        order_supplies_summary.supply_cost

    from order_items

    left join orders on order_items.order_id = orders.order_id

    left join products on order_items.product_id = products.product_id

    left join order_supplies_summary
        on order_items.product_id = order_supplies_summary.product_id

)

select * from joined
)
        SELECT * FROM (
        (SELECT order_id, product_id, supply_cost, 'actual' AS actual_or_expected FROM analytics_diego_rojas_order_items_actual)
        UNION ALL
        (SELECT order_id, product_id, supply_cost, 'expected' AS actual_or_expected FROM analytics_diego_rojas_order_items_expect)
        ) unit_test_diff
        ORDER BY order_id, product_id, supply_cost