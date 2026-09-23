with source as (

    select * from {{ source('raw', 'comtrade_imports') }}

),

casted as (

    select
        cast(ref_year as integer) as ref_year,
        cast(partner_code as integer) as partner_code,
        cmd_code as hs6_code,
        cast(primary_value as numeric) as import_value_usd,
        cast(net_wgt as numeric) as net_wgt,
        hs_version,

        type_code,
        freq_code,
        ref_period_id,
        ref_month,
        period,
        reporter_code,
        flow_code,
        partner2_code,
        classification_code,
        classification_search_code,
        is_original_classification,
        customs_code,
        mos_code,
        mot_code,
        qty_unit_code,
        qty,
        is_qty_estimated,
        alt_qty_unit_code,
        alt_qty,
        is_alt_qty_estimated,
        is_net_wgt_estimated,
        gross_wgt,
        is_gross_wgt_estimated,
        cifvalue,
        fobvalue,
        legacy_estimation_flag,
        is_reported,
        is_aggregate,

        source_file,
        ingested_at

    from source

)

select *
from casted
-- partner_code 0 is the World aggregate row, not a real trading partner.
where partner_code != 0
