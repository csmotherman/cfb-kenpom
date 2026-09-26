-- Public storage for rendered social-post images (e.g. the weekly PRIME 25
-- rankings PNG) so Buffer can fetch them by URL. Deferred from the original
-- Phase 1 design until an actual promotion path (scripts/promote_social_post.py)
-- needed it. Objects are content-addressed (path includes the row's
-- content_hash), so uploads are naturally idempotent -- see social/storage.py.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('social-assets', 'social-assets', true, 5242880, array['image/png'])
on conflict (id) do update set
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

alter table storage.objects enable row level security;

drop policy if exists "social-assets public read" on storage.objects;
create policy "social-assets public read"
  on storage.objects for select
  using (bucket_id = 'social-assets');

drop policy if exists "social-assets service role write" on storage.objects;
create policy "social-assets service role write"
  on storage.objects for insert with check (bucket_id = 'social-assets' and auth.role() = 'service_role');

drop policy if exists "social-assets service role update" on storage.objects;
create policy "social-assets service role update"
  on storage.objects for update using (bucket_id = 'social-assets' and auth.role() = 'service_role');

drop policy if exists "social-assets service role delete" on storage.objects;
create policy "social-assets service role delete"
  on storage.objects for delete using (bucket_id = 'social-assets' and auth.role() = 'service_role');
