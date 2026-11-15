

with days as (

    
    select (
        timestampadd(day, row_number() over (order by 1) - 1, cast('2000-01-01' as date))
    ) as date_day
    from explode(sequence(1, timestampdiff(day, date_trunc('day', cast('2000-01-01' as date)), date_trunc('day', cast('2030-01-01' as date))) ))


),

final as (
    select cast(date_day as date) as date_day
    from days
)

select * from final