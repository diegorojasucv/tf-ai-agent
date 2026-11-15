
    
    

with all_values as (

    select
        customer_type as value_field,
        count(*) as n_records

    from `analytics`.`diego_rojas`.`customers`
    group by customer_type

)

select *
from all_values
where value_field not in (
    'new','returning'
)


