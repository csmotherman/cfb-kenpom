-- The completed-game Game Results view (single-game Advanced/Exploratory
-- breakdown behind the matchup page) publishes dataset_type='team_game_advanced'
-- rows through the same premium_datasets table; widen the check constraint.
alter table public.premium_datasets
  drop constraint if exists premium_datasets_dataset_type_check;

alter table public.premium_datasets
  add constraint premium_datasets_dataset_type_check
  check (dataset_type in ('advanced', 'predictions', 'exploratory', 'exploratory_matchups', 'team_game_advanced'));
