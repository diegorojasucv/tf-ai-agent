-- Build actual result given inputs
WITH
            	analytics_diego_rojas_order_items as (SELECT CAST(1 AS string) AS order_item_id, CAST(1 AS string) AS order_id, CAST(NULL AS string) AS product_id, CAST(NULL AS timestamp) AS ordered_at, CAST(NULL AS string) AS product_name, CAST(NULL AS decimal(16,2)) AS product_price, CAST(true AS boolean) AS is_food_item, CAST(false AS boolean) AS is_drink_item, CAST(NULL AS decimal(26,2)) AS supply_cost
UNION ALL
SELECT CAST(2 AS string) AS order_item_id, CAST(1 AS string) AS order_id, CAST(NULL AS string) AS product_id, CAST(NULL AS timestamp) AS ordered_at, CAST(NULL AS string) AS product_name, CAST(NULL AS decimal(16,2)) AS product_price, CAST(false AS boolean) AS is_food_item, CAST(true AS boolean) AS is_drink_item, CAST(NULL AS decimal(26,2)) AS supply_cost
UNION ALL
SELECT CAST(3 AS string) AS order_item_id, CAST(2 AS string) AS order_id, CAST(NULL AS string) AS product_id, CAST(NULL AS timestamp) AS ordered_at, CAST(NULL AS string) AS product_name, CAST(NULL AS decimal(16,2)) AS product_price, CAST(true AS boolean) AS is_food_item, CAST(false AS boolean) AS is_drink_item, CAST(NULL AS decimal(26,2)) AS supply_cost),
  	analytics_diego_rojas_stg_orders as (SELECT CAST(1 AS string) AS order_id, CAST(NULL AS string) AS location_id, CAST(NULL AS string) AS customer_id, CAST(NULL AS bigint) AS subtotal_cents, CAST(NULL AS bigint) AS tax_paid_cents, CAST(NULL AS bigint) AS order_total_cents, CAST(NULL AS decimal(16,2)) AS subtotal, CAST(NULL AS decimal(16,2)) AS tax_paid, CAST(NULL AS decimal(16,2)) AS order_total, CAST(NULL AS timestamp) AS ordered_at
UNION ALL
SELECT CAST(2 AS string) AS order_id, CAST(NULL AS string) AS location_id, CAST(NULL AS string) AS customer_id, CAST(NULL AS bigint) AS subtotal_cents, CAST(NULL AS bigint) AS tax_paid_cents, CAST(NULL AS bigint) AS order_total_cents, CAST(NULL AS decimal(16,2)) AS subtotal, CAST(NULL AS decimal(16,2)) AS tax_paid, CAST(NULL AS decimal(16,2)) AS order_total, CAST(NULL AS timestamp) AS ordered_at),
  	analytics_diego_rojas_orders_expect as (SELECT CAST(1 AS string) AS order_id, CAST(NULL AS string) AS location_id, CAST(NULL AS string) AS customer_id, CAST(NULL AS bigint) AS subtotal_cents, CAST(NULL AS bigint) AS tax_paid_cents, CAST(NULL AS bigint) AS order_total_cents, CAST(NULL AS decimal(16,2)) AS subtotal, CAST(NULL AS decimal(16,2)) AS tax_paid, CAST(NULL AS decimal(16,2)) AS order_total, CAST(NULL AS timestamp) AS ordered_at, CAST(NULL AS decimal(36,2)) AS order_cost, CAST(NULL AS decimal(26,2)) AS order_items_subtotal, CAST(1 AS bigint) AS count_food_items, CAST(1 AS bigint) AS count_drink_items, CAST(NULL AS bigint) AS count_order_items, CAST(true AS boolean) AS is_food_order, CAST(true AS boolean) AS is_drink_order, CAST(NULL AS int) AS customer_order_number
UNION ALL
SELECT CAST(2 AS string) AS order_id, CAST(NULL AS string) AS location_id, CAST(NULL AS string) AS customer_id, CAST(NULL AS bigint) AS subtotal_cents, CAST(NULL AS bigint) AS tax_paid_cents, CAST(NULL AS bigint) AS order_total_cents, CAST(NULL AS decimal(16,2)) AS subtotal, CAST(NULL AS decimal(16,2)) AS tax_paid, CAST(NULL AS decimal(16,2)) AS order_total, CAST(NULL AS timestamp) AS ordered_at, CAST(NULL AS decimal(36,2)) AS order_cost, CAST(NULL AS decimal(26,2)) AS order_items_subtotal, CAST(1 AS bigint) AS count_food_items, CAST(0 AS bigint) AS count_drink_items, CAST(NULL AS bigint) AS count_order_items, CAST(true AS boolean) AS is_food_order, CAST(false AS boolean) AS is_drink_order, CAST(NULL AS int) AS customer_order_number),
  	analytics_diego_rojas_orders_actual as (with

orders as (

    select * from analytics_diego_rojas_stg_orders

),

order_items as (

    select * from analytics_diego_rojas_order_items

),

order_items_summary as (

    select
        order_id,

        sum(supply_cost) as order_cost,
        sum(product_price) as order_items_subtotal,
        count(order_item_id) as count_order_items,
        sum(
            case
                when is_food_item then 1
                else 0
            end
        ) as count_food_items,
        sum(
            case
                when is_drink_item then 1
                else 0
            end
        ) as count_drink_items

    from order_items

    group by 1

),

compute_booleans as (

    select
        orders.*,

        order_items_summary.order_cost,
        order_items_summary.order_items_subtotal,
        order_items_summary.count_food_items,
        order_items_summary.count_drink_items,
        order_items_summary.count_order_items,
        order_items_summary.count_food_items > 0 as is_food_order,
        order_items_summary.count_drink_items > 0 as is_drink_order

    from orders

    left join
        order_items_summary
        on orders.order_id = order_items_summary.order_id

),

customer_order_count as (

    select
        *,

        row_number() over (
            partition by customer_id
            order by ordered_at asc
        ) as customer_order_number

    from compute_booleans

)

select * from customer_order_count
)
        SELECT * FROM (
        (SELECT order_id, count_food_items, count_drink_items, is_food_order, is_drink_order, 'actual' AS actual_or_expected FROM analytics_diego_rojas_orders_actual)
        UNION ALL
        (SELECT order_id, count_food_items, count_drink_items, is_food_order, is_drink_order, 'expected' AS actual_or_expected FROM analytics_diego_rojas_orders_expect)
        ) unit_test_diff
        ORDER BY order_id, count_food_items, count_drink_items, is_food_order, is_drink_order