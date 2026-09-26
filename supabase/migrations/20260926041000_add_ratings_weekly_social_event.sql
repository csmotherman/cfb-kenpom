alter table public.social_posts
  drop constraint if exists social_posts_event_type_check;

alter table public.social_posts
  add constraint social_posts_event_type_check check (event_type in (
    'rankings_weekly',
    'ratings_weekly',
    'game_final_graded',
    'market_disagreement',
    'upset_call_pregame',
    'upset_hit',
    'rank_mover',
    'top25_shakeup',
    'weekly_accuracy_recap'
  ));
