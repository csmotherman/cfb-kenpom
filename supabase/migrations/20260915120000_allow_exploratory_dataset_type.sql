-- premium_datasets originally allowed only ('advanced','predictions'). The
-- new LEILA Exploratory premium surface publishes dataset_type='exploratory'
-- rows through the same table; widen the check constraint to allow it.
alter table public.premium_datasets
  drop constraint if exists premium_datasets_dataset_type_check;

alter table public.premium_datasets
  add constraint premium_datasets_dataset_type_check
  check (dataset_type in ('advanced', 'predictions', 'exploratory'));
