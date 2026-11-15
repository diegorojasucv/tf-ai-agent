-- Build actual result given inputs
WITH
            	analytics_raw_raw_stores as (SELECT CAST(1 AS string) AS id, CAST('Vice City' AS string) AS name, CAST('2016-09-01T00:00:00' AS timestamp) AS opened_at, CAST(0.2 AS double) AS tax_rate
UNION ALL
SELECT CAST(2 AS string) AS id, CAST('San Andreas' AS string) AS name, CAST('2079-10-27T23:59:59.9999' AS timestamp) AS opened_at, CAST(0.1 AS double) AS tax_rate),
  	analytics_diego_rojas_stg_locations_expect as (SELECT CAST(1 AS string) AS location_id, CAST('Vice City' AS string) AS location_name, CAST(0.2 AS double) AS tax_rate, CAST('2016-09-01' AS timestamp) AS opened_date
UNION ALL
SELECT CAST(2 AS string) AS location_id, CAST('San Andreas' AS string) AS location_name, CAST(0.1 AS double) AS tax_rate, CAST('2079-10-27' AS timestamp) AS opened_date),
  	analytics_diego_rojas_stg_locations_actual as (with

source as (

    select * from analytics_raw_raw_stores

),

renamed as (

    select

        ----------  ids
        id as location_id,

        ---------- text
        name as location_name,

        ---------- numerics
        tax_rate,

        ---------- timestamps
        date_trunc('day', opened_at) as opened_date

    from source

)

select * from renamed
)
        SELECT * FROM (
        (SELECT location_id, location_name, tax_rate, opened_date, 'actual' AS actual_or_expected FROM analytics_diego_rojas_stg_locations_actual)
        UNION ALL
        (SELECT location_id, location_name, tax_rate, opened_date, 'expected' AS actual_or_expected FROM analytics_diego_rojas_stg_locations_expect)
        ) unit_test_diff
        ORDER BY location_id, location_name, tax_rate, opened_date