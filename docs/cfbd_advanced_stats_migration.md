# CFBD advanced-stats migration (standard box score + standard advanced stats)

> **2026-09-20 addendum: production blanks incident and fix.** See
> "Incident: production advanced data rendering blank (2026-09-20)" near the
> end of this document for the full root-cause writeup. One-line summary:
> the CI refresh pipeline never called the ingestion this migration added,
> so production's raw corpus never had CFBD's advanced sources at all. The
> export/canonical code itself was already correct. Fixed by wiring
> `scripts/ingest_advanced_game_stats.py` into `.github/workflows/refresh.yml`.
> Also: `/game/box/advanced`'s `teams.ppa`/`cumulativePpa`/`successRates`/
> `explosiveness`/`rushing` sections are now parsed too, enabling a real
> CFBD -> CFBD field-level fallback; and PPA is now displayed as "EPA" on
> the site (a branding decision) while staying named `ppa_*` internally.

Migrates PRIME's Results/Matchup "Efficiency" and "Game Shape" display data
away from PBP-derived reconstructions and onto CFBD's own authoritative
advanced endpoints, wherever CFBD already publishes the concept. Ratings,
APR, opponent adjustment, and predictions were **not** touched -- see
"What was deliberately NOT changed" below.

## Source hierarchy

| Tier | Source | Used for |
|---|---|---|
| 1 | CFBD `/games/teams` | Official box score (points, yards, attempts, downs, penalties, turnovers, possession). Unchanged by this migration -- already correct. |
| 2 | CFBD `/stats/game/advanced` + `/game/box/advanced` | Standard advanced stats: PPA, Success Rate, explosiveness, rushing efficiency, havoc, scoring opportunities, field position. |
| 3 | CFBD `/stats/game/advanced` (offense/defense drive counts) | Drive counts, drive share, yards/drive. |
| 4 | PRIME's own PBP pipeline | Genuinely sequence-level, proprietary metrics with no CFBD equivalent: Series Control, Possession Quality (Clean Drive/Drive Killer/Failure*), Explosive Dependency, Turnover EPA, by-down PPA splits, sacks/TFLs allowed. |

Two CFBD endpoints are used for two **non-overlapping** concept sets, chosen
so no concept is ever sourced from two different CFBD endpoints at once:

- **`/stats/game/advanced`**: one API call per season/week (cheap -- fully
  backfilled for every historical season, 2014-2026). Source for plays,
  drives, PPA, Success Rate, explosiveness, and rushing efficiency
  (stuff rate, power success, line/second-level/open-field yards).
- **`/game/box/advanced`**: one API call **per game** (not cheap). The only
  CFBD source for havoc, scoring opportunities, and field position at the
  team-game grain. Backfilled for 2025-2026 only in this pass (see
  "Historical coverage" below).

## Files changed / added

- `src/cfb_analytics/sources/cfbd/client.py` -- added `game_advanced_stats()`
  (`/stats/game/advanced`) and `advanced_box_score()` (`/game/box/advanced`).
- `src/cfb_analytics/raw/acquire_advanced.py` (new) -- week-aware acquisition
  for both sources, following the existing `raw/acquire.py` immutable-source
  pattern. Persists progress after every `/game/box/advanced` call (not only
  at the end), so an interrupted backfill can resume without re-fetching
  already-acquired games.
- `src/cfb_analytics/canonical/cfbd_advanced.py` (new) -- parses both raw
  sources into flat, clearly-named, provenance-tagged (gameId, team) rows.
  Cross-maps CFBD's defense-keyed `havoc` field into each team's own
  `havoc_allowed`/`havoc_forced`.
- `scripts/ingest_advanced_game_stats.py` (new) -- CLI driver: acquires both
  sources for one or more seasons, restricted to completed games only.
- `scripts/export_team_game_advanced.py` -- `TEAM_GAME_ADVANCED_VERSION`
  bumped to `team-game-advanced-v4-cfbd-advanced-source`. Standard advanced
  fields now come from `cfbd_stats`/`cfbd_box` instead of PRIME's canonical/
  exploratory PBP output. Legacy `epa_*` field names removed (see "Naming"
  below).
- `scripts/audit_game_results_contract.py` -- updated to the new field
  contract, added `FORBIDDEN_LEGACY_KEYS` (fails if any pre-migration `epa_*`
  name reappears), and a new cross-check validating exported CFBD-sourced
  values directly against the raw `advanced_game_stats.json` response.
- `web/lib/team-game-advanced.ts` -- Efficiency/Game Shape sections repointed
  at the new field names; tooltips explicitly say CFBD-sourced vs.
  PRIME-derived; added new rows for stuff rate, power success, line/
  second-level/open-field yards, and CFBD's own explosiveness metric.
- Tests: `tests/test_cfbd_advanced.py`, `tests/test_acquire_advanced.py`,
  `tests/test_export_team_game_advanced.py` (rewritten for the new
  contract).

## Naming: PPA vs. EPA

`canonical/analytics/epa.py`'s own docstring already said it plainly: *"ppa
is CFBD's own play-level model output, not one this repo fits."* PRIME has
never fit an independent expected-points model -- "EPA" on the Results page
was CFBD's PPA, filtered by PRIME's own eligibility rules, relabeled. Every
field this migration touches is renamed accordingly: `epa_per_play` ->
`ppa_per_play`, `total_epa` -> `total_ppa`, `passing_epa` ->
`passing_total_ppa`, `epa_per_dropback` -> `passing_ppa_per_play`,
`rushing_epa` -> `rushing_total_ppa`, `epa_per_rush` -> `rushing_ppa_per_play`,
`epa_without_explosives` -> `ppa_per_play_without_explosives`, and the
by-down splits `down{1,2,3}_epa*` -> `down{1,2,3}_ppa_per_play*`.

**This migration does not rename "EPA" anywhere outside this one export.**
`analytics/epa.py`, `analytics/epa_v1_research.py`, `analytics/epa_v2_research.py`,
the `EPA`/`PassEPA`/`RushEPA`/... rating specs fit by
`analytics/iterative_ratings.py`, and every "Adj EPA" label on the Ratings
page are all the **same underlying issue** (PPA relabeled as EPA) but were
deliberately left untouched here -- renaming a metric that's fitted into a
live opponent-adjustment model touches far more surface area and risk than
this display-only migration, and doing it well requires its own scoped
effort (see "What was deliberately NOT changed").

## CFBD's "explosiveness" is not PRIME's "Explosive Play Rate"

CFBD's `explosiveness` field is the **average PPA on successful/explosive
plays only** (a magnitude). PRIME's existing `explosive_play_rate` is the
**share of plays** gaining 15+ yards through the air or 10+ on the ground (a
frequency). These are different concepts that happen to share a similar
name. Both are now exposed side by side (`cfbd_explosiveness` alongside
`explosive_play_rate`/`explosive_pass_rate`/`explosive_rush_rate`) rather
than one silently replacing the other.

## Havoc cross-mapping

CFBD's `/game/box/advanced` `havoc` array is keyed by the **defense that
created it**: team X's row is the share of X's opponent's plays that X's
defense disrupted. Naively keying by team name would silently swap which
team's offense each havoc rate describes. `canonical/cfbd_advanced.py`
cross-maps this explicitly: a team's `havoc_allowed` (its own offense) reads
the **opponent's** havoc row; its `havoc_forced` (its own defense) reads its
**own** row. Verified against a real payload (2026 wk1, TCU @ UNC) in
`tests/test_cfbd_advanced.py::test_havoc_is_cross_mapped_between_offense_and_defense`.

## Historical coverage

`/stats/game/advanced` (PPA, Success Rate, explosiveness, rushing
efficiency, drives) is backfilled for **every** historical season
(2014-2026) -- cheap (~180 calls total across 12 seasons).

`/game/box/advanced` (havoc, scoring opportunities, field position) is
backfilled for **2025 and 2026 only** in this pass. Full historical backfill
would cost ~10,500 additional API calls (one per historical game, 2014-2024)
against a shared 30,000/month quota -- not attempted here. Older seasons
correctly show `null` for these three fields with
`field_availability["...] == "game_box_advanced_not_backfilled"`, following
the exact same pattern this export already used for PRIME's own
not-yet-backfilled Havoc/sacks-allowed pipeline (`CURRENT_SEASON_FIELDS_WIRED`).
To extend coverage: `python scripts/ingest_advanced_game_stats.py --season
<year>` for each additional season, budgeting ~1 call per completed game.

## Old vs. new: measured differences (2026, 372 comparable team-games)

Generated by diffing this migration's export against the pre-migration
script's output for the identical underlying canon/exp/box data (see
methodology note below).

| Metric | Mean abs diff | Mean signed diff | Max abs diff | Notes |
|---|--:|--:|--:|---|
| Success Rate | 0.014 | -0.006 | 0.081 | Small; different play-eligibility population (CFBD's own vs. PRIME's classifier). |
| Total PPA/EPA | 2.65 | -0.20 | 22.0 | Same-ish scale; individual-game outliers exist. |
| PPA/EPA per play | 0.041 | -0.009 | 0.31 | Small on average. |
| Explosive Play Rate (unchanged field, sanity check) | **0.000** | **0.000** | **0.000** | Confirms the refactor didn't perturb untouched PRIME fields. |
| Scoring Opportunities | 0.41 | +0.31 | 4.0 | CFBD counts slightly more opportunities on average than PRIME's 40-yard-line PBP heuristic. |
| Points / Opportunity | 0.50 | -0.11 | 5.25 | Follows from the opportunities-count difference. |
| Avg Start Field Position | 4.96 yd | **+4.64 yd** | 26.4 yd | Large, systematic. Investigated below. |
| Havoc Allowed | 0.116 | **+0.115** | 0.72 | Large, systematic. Investigated below. |
| Offensive Drives | 0.16 | +0.12 | 2.0 | Close agreement between CFBD's own count and PRIME's validated-possession count. |
| Yards / Drive | 1.05 | -0.24 | 9.1 | Small; formula also changed (official yards / CFBD drives vs. PBP yards / PRIME drives). |

### Investigated: Havoc Allowed's large systematic difference

The single largest outlier is Virginia Tech @ VMI (game `401858211`, a 73-3
blowout): CFBD's own `havoc.total` for Virginia Tech is **1.048** -- over
100%. Confirmed directly against the raw `/game/box/advanced` payload (not
a parsing bug in this migration): CFBD's havoc-rate formula can exceed 1.0
in extreme blowout/garbage-time games with very few real offensive snaps
for one side. This is a genuine CFBD source characteristic to be aware of,
not a bug introduced here. Removing this and a handful of similar blowouts
from the diff population substantially reduces (but does not eliminate) the
mean difference -- the remainder reflects a real definitional difference
between PRIME's own play-level havoc classifier (TFL/sack/turnover on a
clean scrimmage snap) and CFBD's own model-based havoc rate.

### Investigated: Avg Start Field Position's systematic difference

No sign-convention bug (both sides use the same "yards to opponent's goal
line" convention; values are in the same 50-80 range throughout). The most
likely explanation is a population difference: PRIME's prior
`averageStartYardsToGoal` averaged over `validatedPossessions` only (a
stricter drive-validation gate), while CFBD's `averageStart` includes every
offensive drive CFBD recognizes, including some PRIME's own validation
would flag unresolved. Not independently confirmed play-by-play in this
migration; flagged as a plausible explanation, not a proven one.

**Methodology note:** the old output was regenerated from the current
canon/exp/box inputs using the pre-migration version of
`export_team_game_advanced.py` (via `git show HEAD:...`), run against the
same 2026 raw corpus as the new export -- an apples-to-apples comparison of
the two versions of the script, not an artifact of unrelated data drift. No
team-season rank comparison was produced: this migration does not touch any
rating computation, so there are no new ranks to compare (see below).

## What was deliberately NOT changed

- **APR.** Untouched. Per instruction: do not replace or restructure APR
  unless a drive-only reproduction has been thoroughly validated; that
  validation was not attempted in this pass.
- **Opponent-adjusted ratings** (Adj EPA/Success/PassEPA/RushEPA/... fitted
  by `analytics/iterative_ratings.py` via `scripts/build_real_data.py`).
  These are fit from `data/canonical/season={year}/team_games.json`, a
  completely separate file from `web/public/data/team-game-advanced/`
  (confirmed: nothing in `build_real_data.py` or any `prediction_*` module
  reads `team-game-advanced` at all). Swapping their raw inputs to CFBD's
  advanced stats would require CFBD's `/game/box/advanced` backfilled
  consistently across the model's **entire** fitted population (2014-2026)
  -- not done here, both because of the API-quota cost noted above and
  because mixing PBP-defined and CFBD-defined inputs within one fit is
  explicitly the failure mode to avoid. This is real follow-up work, not
  completed in this pass.
- **Predictions.** Unaffected -- they consume ratings (unchanged) and/or
  their own feature pipelines, never `team-game-advanced`.
- **The PBP pipeline itself** (`canonical/`, `derived/`, most of
  `analytics/`). Nothing was deleted. `canonical/play_types.py`,
  `analytics/epa.py`, `analytics/havoc.py`, etc. are unchanged and still
  power the rating fit and the genuinely-proprietary Tier 4 metrics still
  displayed on Results (Series Control, Possession Quality, Explosive
  Dependency, Turnover EPA, by-down PPA).
- **`web/lib/team-game-percentile-baseline.ts` regeneration.** The
  historical p10/p30/p70/p90 conditional-formatting cut points still
  reflect PRIME's old PBP-derived distributions. Renamed-but-equivalent
  fields (`ppa_per_play`, `total_ppa`, etc.) point at their old baseline
  keys via the `Spec.baselineKey` override so existing coloring keeps
  working; genuinely new fields (stuff rate, power success, line/second-
  level/open-field yards, CFBD explosiveness) are marked `neutral: true`
  (uncolored) since no baseline exists for them yet. Regenerating this
  baseline requires Supabase-hosted historical data access
  (`scripts/export_team_game_percentile_baseline.py`) this session did not
  have, plus full historical `/game/box/advanced` backfill for `havoc`'s
  baseline specifically -- flagged as follow-up, not attempted.

## Known unresolved source-data concerns

1. **29 games (58 team-games) in the current 2026 season have no official
   CFBD `/games/teams` box score at all** (e.g. Alabama/Florida State week
   1, Arkansas/Georgia week 1, and others) -- confirmed with a fresh,
   uncached live API call, not a local staleness issue. This is **entirely
   unrelated to this migration** (box-score ingestion/parsing was not
   touched) and pre-dates it. It causes `scripts/audit_game_results_contract.py`
   to fail (by design -- it fails closed on a missing box score for an
   FBS-vs-FBS game) until either CFBD publishes these box scores or someone
   confirms they are permanently absent and adds them to
   `KNOWN_BOX_SCORE_SOURCE_GAPS` with the same verification rigor as the
   existing 2016 entry. Left failing rather than silently added to that
   list, since 29 unverified games is not "a documented, verified
   exception."
2. **CFBD's havoc rate can exceed 100%** in extreme blowout games (see
   above) -- not clamped or hidden here; displayed as-is, since inventing a
   clamp would itself be an unrequested transformation of an authoritative
   source value.
3. Historical `/game/box/advanced` backfill (havoc, scoring opportunities,
   field position for 2014-2024) remains a scoped, not-yet-done follow-up.

## Incident: production advanced data rendering blank (2026-09-20)

**Report:** `https://www.primecfb.com/matchup/2026/401856674` (Alabama 45,
Kentucky 17) showed Success Rate, Havoc, drives, and field position
populated, but PPA/Play, Total PPA, passing/rushing PPA, Stuff Rate, Power
Success, all three rushing-efficiency yardage rows, CFBD Explosiveness,
every by-down PPA row, and PPA w/o Explosives as an em dash for both teams.

### Investigation

Inspected the real stored raw payload for game `401856674` directly (both
`/stats/game/advanced` and `/game/box/advanced`, `data/raw/cfbd/season=2026/
season_type=regular/week=02/`). Both endpoints had **complete, non-null**
data for both teams for every field the user listed as blank. Ran the
current `export_team_game_advanced.py` against that raw data locally: every
field the user listed as blank was already populated -- `ppa_per_play`,
`total_ppa`, `stuff_rate`, `power_success`, `line_yards_per_play`,
`cfbd_explosiveness`, `down1_ppa_per_play` (and pass/rush splits),
`ppa_per_play_without_explosives` all had real values for both Alabama and
Kentucky in a fresh local build.

This means the specific hypotheses in the original bug report --
`_normalize_game_box_advanced()` missing sections, a by-down PPA field-name
mismatch, `exp.get("nonExplosiveEpaPerPlay")` being the wrong producer field
-- **did not reproduce** against the current code and current raw data.
`ppa`/`cumulativePpa` semantics were still validated and are documented
below since that groundwork is valuable regardless, and the missing
`/game/box/advanced` sections were still added (a real gap, just not what
was causing this specific incident) so the same class of bug can't recur
for a field that's only in one of the two endpoints.

### Root cause (confirmed)

`.github/workflows/refresh.yml` -- the actual production refresh pipeline --
never called `scripts/ingest_advanced_game_stats.py`. Its ingestion step
runs only `python -m cfb_analytics.pipelines.ingest --season "$SEASON"`
(`src/cfb_analytics/pipelines/ingest.py`), which calls `raw/acquire.py`'s
`acquire_season`/`acquire_week` for games, drives, plays, and the official
box score -- and nothing else. The prior migration built
`raw/acquire_advanced.py` and `scripts/ingest_advanced_game_stats.py` as a
standalone script and ran it manually once, locally. It was never wired into
the automated pipeline, so production's `data/raw` (restored via
`actions/cache@v4` between runs) never had `advanced_game_stats.json` or
`advanced_box_scores.json` at all -- CFBD's advanced sources were never
acquired in production, ever, regardless of how many times the scheduled
refresh ran. `export_team_game_advanced.py` running in CI against that
corpus would correctly find no CFBD advanced data and export nulls for
every field sourced from it.

(Success Rate/drives/havoc/field position appearing populated on the live
site is consistent with production currently serving a build from before
this gap existed, or a mix of old and new field names across a stale
publish -- not independently verified against live CI run history, which
this environment cannot access. The concrete, fixable defect, regardless of
that ambiguity, is #1 below.)

**Fix:** added a step to `.github/workflows/refresh.yml`, right after the
existing games/drives/plays/box-score fetch step, that runs
`python scripts/ingest_advanced_game_stats.py --season "$SEASON"` with the
same `--refresh-partition` list `detect-new-games` already resolves for the
primary ingestion step. Already-cached partitions are free (manifest-checked,
no API call), so this is safe to run on every refresh, not just bootstrap.
Also extended `scripts/ingest_advanced_game_stats.py` with `--refresh-partition`
support (previously only had a blanket `--refresh`) to match.

### Other things fixed while investigating (real, but not this incident's cause)

1. **`_normalize_game_box_advanced()` now parses `teams.ppa`, `teams.
   cumulativePpa`, `teams.successRates`, `teams.explosiveness`, and `teams.
   rushing`** (previously only `havoc`/`scoringOpportunities`/`fieldPosition`).
   Validated against game 401856674's real payload that `ppa[].overall.
   total` is the per-play average and `cumulativePpa[]`'s equivalent is the
   total/sum (not guessed from field names -- cross-checked against
   `/stats/game/advanced`'s independently-computed `offense.ppa`/
   `offense.totalPPA` for the same team-game: 0.1359 vs 0.1317 per-play,
   8 vs 8.296 total). This enables a genuine CFBD -> CFBD field-level
   fallback in `export_team_game_advanced.py`'s new `_cfbd_fallback()`:
   prefer `/stats/game/advanced`, use `/game/box/advanced`'s equivalent only
   if that specific field is null there. Never falls back to PRIME PBP.
2. **Reconciled the two endpoints** across all 372 real 2026 team-games with
   both sources present (`scripts/audit_cfbd_advanced_coverage.py`):
   coverage is 372/372 (100%) on both sides for every dual-source concept
   checked (PPA/play, total PPA, passing/rushing PPA, Success Rate,
   Explosiveness, Stuff Rate, Power Success, and all three rushing-yardage
   splits) -- neither endpoint has a coverage edge over the other in this
   corpus. Numeric agreement is close but not exact (e.g. mean |diff| on
   Total PPA is 3.71, on PPA/play is 0.06) -- a real, minor definitional/
   rounding difference between CFBD's two endpoints, not a bug in either
   parser. `/stats/game/advanced` stays primary (it's the cheap, fully-
   backfilled-historically source); `/game/box/advanced` is fallback only.
3. **Full coverage audit, all 448 2026 team-games, 30 displayed advanced
   fields:** total pipeline loss = **0**. Every field where CFBD (or PRIME,
   for the 10 genuinely-proprietary fields) has a value, the site export has
   it too. 76 team-games are source-null across the board (CFBD-advanced
   fields) -- these are the same pre-existing, unrelated 58-of-372
   missing-official-box-score team-games documented in the original
   migration's report, plus a handful with no PBP graded yet. Full table:
   `data/audits/cfbd_advanced_coverage/2026_summary.json`.
4. **`field_availability` now distinguishes** `advanced_game_stats_missing`
   (the whole `/stats/game/advanced` partition was never ingested for this
   game), `advanced_box_not_ingested` (same, for `/game/box/advanced`, when
   the season is otherwise wired), `cfbd_source_missing` (both endpoints
   were ingested but genuinely lack this specific concept for this
   team-game), and `prime_pbp_missing` (a PRIME-only field with no CFBD
   equivalent, and PRIME's own pipeline has nothing for this team-game) --
   replacing a single generic `cfbd_source_missing`-only reason and an
   entirely untracked category for the PRIME-only fields.
5. **PPA is now displayed as "EPA"** on the Results/Matchup page (a
   PRIME branding decision, not a claim that PRIME fits its own model).
   `web/lib/team-game-advanced.ts`'s `label` strings changed ("PPA / Play" ->
   "EPA / Play", etc.); the underlying export field names stay `ppa_per_play`/
   `total_ppa`/etc. -- deliberately not renamed back to `epa_*`, so the
   honest internal provenance from the original migration (PPA is CFBD's own
   model output, not one PRIME fits) is never lost. Every tooltip touched by
   this change says explicitly that CFBD's PPA is the underlying source.
6. **`by-down PPA` and `PPA w/o Explosives` were investigated and found
   already correct** -- `canon.get("passDown1EpaPerPlay")` etc. and
   `exp.get("nonExplosiveEpaPerPlay")` both resolve to real values for game
   401856674 in the current canonical/exploratory corpus. No code change was
   needed for these two; `field_availability` tracking was added for them
   regardless (item 4) so a genuine future regression would be visible
   rather than a silent null.

### Regression coverage

`tests/test_game_401856674_regression.py` reads the real raw corpus for
this exact game and asserts every field the bug report listed as blank is
non-null for both teams, that `field_availability` is empty for this game,
and that the `ppa`/`cumulativePpa` per-play-vs-total semantics hold against
an independent source. `tests/test_cfbd_advanced.py` gained coverage for
the five newly-parsed `/game/box/advanced` sections using this game's real
magnitudes. `tests/test_export_team_game_advanced.py` gained a
`CfbdFallbackTests` class covering `_cfbd_fallback()`'s four outcomes
(stats-preferred, box-fallback, and both missing-reason branches).
