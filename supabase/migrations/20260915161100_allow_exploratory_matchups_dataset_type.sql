-- The new Matchup Edges surface (validated offense-vs-defense pairing effects
-- for the public matchup preview) publishes dataset_type='exploratory_matchups'
-- rows through the same premium_datasets table; widen the check constraint.
alter table public.premium_datasets
  drop constraint if exists premium_datasets_dataset_type_check;

alter table public.premium_datasets
  add constraint premium_datasets_dataset_type_check
  check (dataset_type in ('advanced', 'predictions', 'exploratory', 'exploratory_matchups'));
