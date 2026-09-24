create or replace function public.get_team_card_advanced(
  p_season smallint,
  p_week smallint,
  p_slug text
)
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  with dataset as (
    select payload
    from public.premium_datasets
    where dataset_type = 'advanced'
      and season = p_season
      and week = 0
    limit 1
  ),
  available_week as (
    select max(key::smallint) as week
    from dataset,
         lateral jsonb_object_keys(payload->'byWeek') as key
    where key ~ '^[0-9]+$'
      and key::smallint <= p_week
  ),
  rows as (
    select elem
    from dataset
    cross join available_week
    cross join lateral jsonb_array_elements(
      dataset.payload->'byWeek'->(available_week.week::text)
    ) as elem
  ),
  ranked as (
    select
      elem,
      rank() over (order by nullif(elem->>'asm','')::double precision desc nulls last) as asm_rank,
      rank() over (order by nullif(elem->>'epaAdj','')::double precision desc nulls last) as epa_adj_rank,
      rank() over (order by nullif(elem->>'passEpaAdj','')::double precision desc nulls last) as pass_epa_adj_rank,
      rank() over (order by nullif(elem->>'rushEpaAdj','')::double precision desc nulls last) as rush_epa_adj_rank,
      rank() over (order by nullif(elem->>'successAdj','')::double precision desc nulls last) as success_adj_rank,
      rank() over (order by nullif(elem->>'offExp','')::double precision desc nulls last) as off_exp_rank,
      rank() over (order by nullif(elem->>'offHavoc','')::double precision desc nulls last) as off_havoc_rank,
      rank() over (order by nullif(elem->>'epaAdjAllowed','')::double precision desc nulls last) as epa_adj_allowed_rank,
      rank() over (order by nullif(elem->>'passEpaAdjAllowed','')::double precision desc nulls last) as pass_epa_adj_allowed_rank,
      rank() over (order by nullif(elem->>'rushEpaAdjAllowed','')::double precision desc nulls last) as rush_epa_adj_allowed_rank,
      rank() over (order by nullif(elem->>'successAdjAllowed','')::double precision desc nulls last) as success_adj_allowed_rank,
      rank() over (order by nullif(elem->>'defExp','')::double precision desc nulls last) as def_exp_rank,
      rank() over (order by nullif(elem->>'defHavoc','')::double precision desc nulls last) as def_havoc_rank
    from rows
  ),
  selected as (
    select *
    from ranked
    where elem->>'slug' = p_slug
    limit 1
  )
  select case
    when selected.elem is null then null
    else jsonb_build_object(
      'week', (select week from available_week),
      'row', jsonb_build_object(
        'asm', selected.elem->'asm',
        'epaAdj', selected.elem->'epaAdj',
        'passEpaAdj', selected.elem->'passEpaAdj',
        'rushEpaAdj', selected.elem->'rushEpaAdj',
        'successAdj', selected.elem->'successAdj',
        'offExp', selected.elem->'offExp',
        'offHavoc', selected.elem->'offHavoc',
        'epaAdjAllowed', selected.elem->'epaAdjAllowed',
        'passEpaAdjAllowed', selected.elem->'passEpaAdjAllowed',
        'rushEpaAdjAllowed', selected.elem->'rushEpaAdjAllowed',
        'successAdjAllowed', selected.elem->'successAdjAllowed',
        'defExp', selected.elem->'defExp',
        'defHavoc', selected.elem->'defHavoc'
      ),
      'ranks', jsonb_build_object(
        'asm', selected.asm_rank,
        'epaAdj', selected.epa_adj_rank,
        'passEpaAdj', selected.pass_epa_adj_rank,
        'rushEpaAdj', selected.rush_epa_adj_rank,
        'successAdj', selected.success_adj_rank,
        'offExp', selected.off_exp_rank,
        'offHavoc', selected.off_havoc_rank,
        'epaAdjAllowed', selected.epa_adj_allowed_rank,
        'passEpaAdjAllowed', selected.pass_epa_adj_allowed_rank,
        'rushEpaAdjAllowed', selected.rush_epa_adj_allowed_rank,
        'successAdjAllowed', selected.success_adj_allowed_rank,
        'defExp', selected.def_exp_rank,
        'defHavoc', selected.def_havoc_rank
      )
    )
  end
  from selected;
$$;

revoke all on function public.get_team_card_advanced(smallint, smallint, text) from public;
revoke all on function public.get_team_card_advanced(smallint, smallint, text) from anon;
revoke all on function public.get_team_card_advanced(smallint, smallint, text) from authenticated;
grant execute on function public.get_team_card_advanced(smallint, smallint, text) to service_role;
