# Roadmap

Decisions locked in on 2026-09-20. Status: **done**, **in progress**, **next**, **later**.

## Architecture

```text
CFBD official games / team box + /stats/game/advanced + /game/box/advanced
        -> standard advanced metrics -> opponent adjustment -> aggregate prediction model -> Projection, simulations

CFBD /drives + /plays  -> current APR (unchanged: plays + drives)
CFBD /plays            -> optional proprietary / detailed analytics (exact-down splits, Series Control, Drive Killers, Explosive Dependency)
```

Core principle: a `/plays` failure must not stop standard Advanced metrics, prediction training and scoring, Projection, simulation
inputs, standard matchup data, or Ratings rendering. APR and the play-level metrics may be stale or unavailable in that case.
APR methodology, version, history and rankings are not changed. A no-PBP possession rating is a later, separate project paired with a
full historical rebuild, and would be renamed unless it measures materially the same concept as APR.

## Now

- Finish aggregate shadow experiment and feature selection: **done** (`docs/advanced_shadow_experiment.md`, section 10)
- Provisional/trust state on Ratings (week-level only): **done**
- Teams and Learn in nav; template route noindexed: **done**
- Metric versions by era documented on Methodology: **done**
- `/game/box/advanced` failure handling (CI skip+retry, explicit empty-answer marker, loader reports invalid games): **done**

## Core engineering

- Select feature set (S19 + game shape), freeze model, manifest/version, calibration, prospective snapshots: **done**
  (`prospective/2026/aggregate-model-frozen.json`, `pipelines/aggregate_predictions.py`, snapshots begin week 6)
- Core-no-PBP contract tests for the prediction path: **done** (`tests/test_aggregate_prediction.py`)
- Replace the scores-only mature-season path: **in progress**. Weeks 1-5 stay on the early-season blend; week 6 is the first
  aggregate snapshot and needs week 5 complete.
- Remove dormant Prediction v2: **next**, after the first prospective aggregate snapshot exists. Its own commit.
- Whole-site degraded-mode audit: **done** (`docs/degraded_mode_audit.md`); found and fixed a hidden PBP dependency in the early-season blend. Restructuring the refresh into a core (aggregate) stage and a play-level stage: **next**
- APR stays on plays + drives: **unchanged**

## Trust / beta

- Market data acquisition (closing lines for completed games, and history): **next**
- PRIME vs market benchmark (SU, margin MAE, calibration, model-market disagreement, not only ATS): **next**
- Expanded Model Performance (SU, margin MAE, market MAE, weekly, conference, calibration, disagreement, history, prospective): **next**
- Secondary Projection (prior-informed, labelled differently from the Rating, visually secondary): **done** (`analytics/projection.py`, `pipelines/publish_projection.py`, muted `Proj` column on Ratings for seasons that have it; weeks 1-3 of 2026 published)
- Advanced default core view (Net/Off/Def APR, EPA/play, success, YPP, explosive rate, plus havoc and points/opportunity; SOS/SOR stay on Ratings and team pages): **done** (Core is the default; the All metrics switch opens the existing research tabs)
- Standard Advanced concepts move to CFBD aggregates where not already: **ongoing**

## Next product

- Team-page remaining-game win probabilities (first consumer of the frozen model)
- Season simulation: expected wins, win-total distribution, conference/CFP/national-title probability
- Automated weekly recap

## Later

- Decide whether to design a genuinely new no-PBP possession rating (with a full historical rebuild)
- Rebuild historical metric contracts (APR, SOS/SOR, explosive rate) on one modern definition
- Decide Exploratory from real usage analytics
