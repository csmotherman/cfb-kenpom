# Whole-site no-PBP / degraded-mode audit

Question: if raw `/plays` (or play-derived data) is unavailable, what still refreshes, what fails, and does anything fail *silently*?
Method: an isolated checkout of the repo with the real 2026 data, each refresh step run in order with file-read/write tracing
(`data/audits/degraded_mode/`), then re-run with 2026 plays removed (all weeks) and with only week 3's plays and drives removed
(scores present). `export_web_data.py` cannot run outside CI (it needs the hydrated private history), so it is not traced.

## 1. The refresh is one linear job

`.github/workflows/refresh.yml` runs 40+ steps in a single job; step 5 fetches games, box scores, drives **and plays** in one command.
The first failing step aborts the job. Consequence: when new games complete and `/plays` is unavailable, *nothing* updates, including
data that never needed plays (final scores in the schedule, records, prediction grading and the track record, aggregate predictions,
market odds, CFP markers). The site simply stays stale. Not incorrect, but a plays outage stops the whole product.

## 2. What each product actually depends on (from the traces)

| Product / artifact | Reads plays or play-derived data? | Notes |
|---|---|---|
| Ratings page: APR, SOS, SOR (`compile_site_data`) | **Yes, hard** | canonical plays + raw/derived drives; refuses to run without plays |
| Advanced page standard metrics (`site/advanced-data.js`) | Yes | built from play-derived canonical team_games; most standard concepts exist in CFBD aggregates and can move |
| Team-game advanced export | Partly | canonical team_games (population) plus CFBD advanced, box and box-advanced |
| Game-log drill-down | Yes | play-derived team_games + raw drives (possession time) |
| Exploratory | Yes | play-derived |
| Aggregate predictions (weeks 6+) | **No** | official games + `/stats/game/advanced` + box only; tested with plays/drives poisoned |
| Early-season blend (weeks 1-5) | **Was hidden: yes; now no** | see finding 3 |
| Schedule, market lines, CFP markers, track-record grading | No | games only |

## 3. Findings

1. **A "PBP-free" path had a hidden dependency (fixed).** The published early-season blend read scores from canonical
   `team_games.json`, which is built from the play-derived layer. In the outage run that file silently lost week 3 (370 rows instead of
   520) with exit code 0, so week 5's blend would have used stale margins without any error. The blend now reads results from raw
   `games.json`. Recomputing weeks 1-4 with the new path reproduces every published prediction exactly (0 mismatches in 200 games), and
   the results match canonical team_games for all 228 teams at every week (test added). The test now forbids the blend from touching
   `team_games.json`, `plays.json` or `drives.json`.
2. **Missing plays does not fail loudly until late.** With 2026 plays removed, the canonical-plays, derived-drives, metrics, all
   propagation steps, canonical build and ratings steps each exit 0 in about 0.2 s (they do nothing). The first failure is
   `compile_site_data` (`RatingModelError: ... requires canonical plays`). With only week 3's plays and drives missing it fails safely
   with `Refresh would erase adjEM for northwestern`, so the rating build's data-loss guard works. **Gap:** `build_canonical` has no
   such guard: it wrote a canonical `team_games.json` missing a completed week and returned success.
3. **The guards that worked:** `compile_site_data` (plays required; refuses to erase published values); the publication and data-contract
   validators. Nothing was published in either outage run because the job would have stopped at step 20.
4. **Everything after the rating build passes in the outage run**, i.e. the aggregate-only outputs could publish independently if the
   job were split.

## 4. Recommended restructure (not yet implemented)

- **Stage A, core (aggregate, no plays):** games, box, `/stats/game/advanced`, `/game/box/advanced` -> schedule/results/records, aggregate
  and blend predictions, track record, market and CFP markers, aggregate-based standard Advanced metrics. Must succeed with `/plays` down.
- **Stage B, play-level:** plays + drives -> APR, SOS/SOR (they depend on APR), play-derived research metrics, drive-based drill-down.
  If it fails, keep the last published Ratings and mark them stale with the existing freshness stamp; never overwrite with partial data.
- Add a completed-game-count guard to `build_canonical` (and any writer of an output that can lose completed weeks).
- Add a whole-site degraded-mode contract test: Stage A must complete with plays/drives absent, and Stage B must fail closed without
  changing published files.
- Move standard Advanced concepts to CFBD aggregates as they qualify: PPA/EPA, success rate, pass/rush EPA, explosiveness, stuff rate,
  power success, line/second-level/open-field yards, havoc, field position, scoring opportunities, drives. `/game/box/advanced`
  fields exist only for 2025+, so historical havoc/field position/finishing stay play-derived until that history is backfilled.
