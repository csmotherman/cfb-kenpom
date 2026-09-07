create extension if not exists http with schema extensions;

create table if not exists public.premium_datasets (
  dataset_type text not null check (dataset_type in ('advanced','predictions')),
  season smallint not null check (season between 1900 and 2200),
  week smallint not null default 0 check (week between 0 and 30),
  payload jsonb not null,
  source_sha text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (dataset_type, season, week)
);

alter table public.premium_datasets enable row level security;

revoke all on table public.premium_datasets from anon, authenticated;
grant select, insert, update, delete on table public.premium_datasets to service_role;

create or replace function public.touch_premium_datasets_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists premium_datasets_touch_updated_at on public.premium_datasets;
create trigger premium_datasets_touch_updated_at
before update on public.premium_datasets
for each row execute function public.touch_premium_datasets_updated_at();
