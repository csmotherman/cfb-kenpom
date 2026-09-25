-- Draft ledger for automated PRIME social content. Every row is a candidate/draft
-- post; nothing here implies anything has been (or will be) posted -- `status`
-- and `publish_policy` gate that separately, and every publish_policy starts
-- (and today stays) at DRAFT_ONLY. See src/cfb_analytics/social/policy.py.

create table if not exists public.social_posts (
  id uuid primary key default gen_random_uuid(),
  platform text not null default 'twitter' check (platform in ('twitter')),

  -- The generator kinds this table is designed for. Only 'rankings_weekly' is
  -- implemented today; the rest are reserved for the event-driven candidates
  -- phase so that phase does not require a schema migration to land.
  event_type text not null check (event_type in (
    'rankings_weekly',
    'game_final_graded',
    'market_disagreement',
    'upset_call_pregame',
    'upset_hit',
    'rank_mover',
    'top25_shakeup',
    'weekly_accuracy_recap'
  )),

  season smallint not null check (season between 1900 and 2200),
  week smallint check (week between 0 and 30),
  game_ids text[],
  team_slugs text[],

  -- Idempotency key, e.g. "rankings_weekly:2026:4". Unique constraint makes a
  -- duplicate insert for the same event/season/week fail at the DB level even
  -- if an application-level check is ever skipped or races.
  dedupe_key text not null unique,

  status text not null default 'candidate' check (status in (
    'candidate', 'draft', 'scheduled', 'published', 'rejected', 'failed'
  )),
  publish_policy text not null default 'DRAFT_ONLY' check (publish_policy in (
    'DRAFT_ONLY', 'BUFFER_DRAFT', 'SCHEDULED_AUTO', 'MANUAL_APPROVAL'
  )),

  text_content text not null,
  alt_text text,

  -- Image location. image_storage_path is the object key a future Storage
  -- upload would use (or, while nothing is uploaded yet, the local/workflow
  -- artifact path the PNG was written to); image_url is only populated once
  -- that upload actually happens.
  image_storage_path text,
  image_url text,

  -- Which generator code produced this row, for audit when templates/renderers change.
  caption_version text,
  render_version text,

  -- Hash of text_content + sources, so a later regeneration of the same
  -- dedupe_key can be compared against what was actually generated before.
  content_hash text,

  -- Fine-grained provenance: one entry per numeric/factual claim in text_content,
  -- e.g. [{"file": "...", "field": "...", "team": "...", "value": ...}, ...].
  sources jsonb not null default '[]'::jsonb,
  -- Fuller snapshot of the source data at generation time, for reproducibility
  -- even if the upstream public JSON is later corrected/regenerated.
  source_snapshot jsonb not null default '{}'::jsonb,
  -- Free-form generation context (counts, timing, git sha, omissions, etc.).
  metadata jsonb not null default '{}'::jsonb,

  buffer_post_id text,
  buffer_channel_id text,

  approved_at timestamptz,
  scheduled_at timestamptz,
  published_at timestamptz,
  error text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists social_posts_event_season_week_idx
  on public.social_posts (event_type, season, week);
create index if not exists social_posts_status_idx on public.social_posts (status);

alter table public.social_posts enable row level security;

revoke all on table public.social_posts from anon, authenticated;
grant select, insert, update, delete on table public.social_posts to service_role;

-- Reuses the existing touch-updated_at function from the premium_datasets migration.
drop trigger if exists social_posts_touch_updated_at on public.social_posts;
create trigger social_posts_touch_updated_at
before update on public.social_posts
for each row execute function public.touch_premium_datasets_updated_at();
