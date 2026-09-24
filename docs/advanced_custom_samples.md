# Advanced custom game samples

Users can drop individual games from **one team's** Advanced Stats (e.g. Michigan without Western Michigan,
Iowa without Northern Iowa) and compare the recomputed rows. Selection is by **game**, per **team** -- a game's week
is never used, so two teams (or two games in one site-week) are always independent.

Official PRIME Ratings (Net/Off/Def, ASM), PRIME 25, every ranking, Strength of Record and predictions are **never**
recomputed; those cells stay official (marked with a small ring) and a banner labels every customized table.

## How each kind of number is recomputed

| Kind | Columns | Method |
|---|---|---|
| Raw rates | YPP, success, pass/rush SR, explosive %, finishing pts/opp, havoc %, pass\|run, pace, time of possession, field position, SOS | Sums of raw per-game counts over the chosen games, divided exactly as today. |
| Opponent-adjusted edges | Adj explosiveness / finishing / havoc; all 36 EPA and Success Rate (overall, pass/rush, by down, offense and defense, margin) | See below. |
| Turnovers & Penalties | every column on that tab | Per-game counts from the Exploratory export (when the season has them). |
| Official only | Net / Off / Def Rating, ASM, all ranks | Unchanged. |

### Opponent adjustment (why it is exact)

`iterative_ratings.fit_metric_ratings` is a ridge fit of `y_g = mu + off(team) - def(opp)` (weight = the game's own
denominator, lambda = 50). At convergence a team's edge is a weighted average of its own games:
`(sum a_g - k) / (sum w_g + lambda)`, with `a_g = num_g + den_g * (def_opp - mu)` (offense) or
`den_g * (mu + off_opp) - num_g` (defense). `scripts/custom_sample.py` publishes `num`, `den` and the opponent term
per game, plus three constants per spec, so any subset of games gives that team's edge **holding every opponent at
its official rating**. All games selected == the published value. EPA/Success edges are then confidence-blended
with the team's raw rate (`blend_edge`) using games played = games selected. FCS games are not in the fit (raw
stats only), exactly as in the official build.

## Data flow and egress

* `build_real_data.build_year(..., custom_sample_out=...)` builds the artifact from the same final-week fit that
  publishes the Advanced numbers; `compile_site_data.py` writes `web/public/data/advanced-games/<season>.json`
  (gitignored, removed before commit like the other private artifacts).
* `publish_premium_data.py` upserts it to `premium_datasets` as `dataset_type='advanced', week=1` (the season's main
  blob is week 0) -- same table, an already-allowed type, **no migration**. Failure to build or publish it is only a
  warning and never blocks the ratings refresh.
* `GET /api/premium/advanced/<season>/games/<teamId>` (entitlement-checked like the Advanced route) reads `meta` and
  `teams->t<teamId>` with a PostgREST JSON-path select, so only one team (~7-13 KB) leaves Supabase per request; if
  that select is rejected a 10-minute in-memory cache limits the fallback full read to one per instance. Nothing is
  fetched until a user opens a team's selector (or a shared link references it), and it is cached for the tab.
* All recomputation is in the browser (`web/lib/custom-sample.ts`).

## Guards

* `verifyParity` recomputes an all-games sample when a team's data loads and compares it to the official Advanced
  row; a stale or mismatched artifact disables the feature (fail closed).
* Custom samples apply only to the full season to date (start = first week, end = latest week) -- the range where
  an all-games selection is the official table. Narrowing the range pauses them.
* Tests: `web/tests/custom-sample.test.mjs` (`npm test`, uses a committed 2026 fixture) and
  `tests/test_custom_sample.py` (full 2026 build).

## Sharing

`/advanced?y=2026&x=michigan:<gameId>;iowa:<gameId>.<gameId>` -- the page reads and writes this with
`history.replaceState`, so a copied address restores the same samples (game ids are stable CFBD ids).

## Backfill

Only the current season is published by the hourly refresh. To publish a past season, run
`python scripts/compile_site_data.py --rating-model hierarchical_hfa --season <year>` then
`python scripts/publish_premium_data.py --season <year>` (needs the Supabase secret). Seasons without an artifact
show "not published yet" in the selector.
