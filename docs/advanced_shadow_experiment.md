# CFBD aggregate-only prediction shadow experiment

Question: can PRIME's prediction model be improved or simplified by replacing its play-by-play (PBP) derived
inputs with CFBD's official aggregate statistics (`/stats/game/advanced`, `/game/box/advanced`, the official team
box score)? Method: build the same model from aggregates only, backtest both under identical leak-safe
walk-forward rules on an identical population, and let the numbers decide. Nothing here changes a published
prediction, rating or APR.

Code: `src/cfb_analytics/analytics/advanced_shadow.py` (data + features), `advanced_shadow_eval.py`
(walk-forward, metrics, paired bootstrap), `advanced_shadow_predict.py` (shadow predictions, not wired to any
output). Runners: `scripts/run_advanced_shadow_experiment.py`, `run_advanced_box_ablation.py`,
`audit_apr_aggregate_reconstruction.py`, `audit_advanced_metric_parity.py`. Results: `data/audits/advanced_shadow/`.
Tests: `tests/test_advanced_shadow.py`.

## 1. What actually publishes predictions (Phase 1 audit)

The prediction model that publishes today does **not** use PBP data.

| Layer | What it is | PBP? |
|---|---|---|
| **Published** (`pipelines/early_season_predictions.py`, freeze `early-season-blend-2026-v1`) | Ridge power score from prior-season points ratings (3 yrs), 3-yr recruiting, returning-QB flag, blended with the team's raw scoring margin using the 100/75/50/25/0% prior taper; fitted HFA; 1-D logistic on margin for confidence. Weeks 1-5, all FBS games. | **No.** Reads only `games.json`, canonical `team_games.json` (points), and the frozen artifact. Verified by test with `plays.json`/`drives.json` reads made fatal. |
| **Dormant** Prediction v2 (`analytics/prediction_v2.py`, 55 features) | OLS on scoring margin, standardized, ridge 1e-6; site-aware SRS+HFA plus 24 opponent-adjusted iterative metric edges (`fit_metric_ratings`, shrinkage 50, exposure-weighted), MWDR edges, and three "volume" interactions. Trained on all earlier seasons; min 3 games. | **Yes**, almost entirely. Its frozen manifest (`prediction-v2-2026-frozen.json`) is not in the repo, so the weekly v2 job is a no-op. |

Because the published model has no PBP inputs, there are no published PBP features to migrate. The meaningful
comparison is therefore *dormant PBP v2 (Model A)* vs *the same architecture from aggregates (Model B)*, with the
scores-only site-aware SRS as the floor. Model A here is v2 exactly as its harness runs it
(`prediction_v1_site_aware_challenger.evaluate`); the harness was reproduced to the third decimal
(2022-25 MAE 12.53/13.10/12.48/12.38).

### Feature lineage (v2 features vs CFBD aggregates)

Class: **A** exact CFBD aggregate, **B** close but definition differs, **C** PRIME proprietary, **D** raw
play-sequence dependent. Measured parity is in `data/audits/advanced_shadow/metric_parity.json`.

| Feature family | PRIME source | CFBD source | Class | Used in same-stats Model B? |
|---|---|---|---|---|
| `siteAwareSrsMargin` (SRS + HFA) | official final scores | `games` | **A** (same function, identical values) | yes |
| Success rate (overall, pass, rush) | PBP, PRIME thresholds | `successRate` x plays | **B** (corr 0.985-0.99, never bit-identical) | yes |
| EPA (overall, pass, rush) | summed CFBD play PPA, PRIME play population | `totalPPA` (+ pass/rush) | **B** (corr 0.90-0.95; PRIME's includes turnover handling) | yes |
| Yards per play | PBP yards / PBP plays | box `totalYards` / CFBD plays | **B** (corr 0.74-0.96) | yes |
| Yards per possession | yards / validated possessions | box yards / CFBD drives | **B** (corr 0.85-0.97; drive populations differ) | yes |
| Success/EPA/Yds by down (1/2/3) | PBP by down | only standard/passing-down splits | **D** | no |
| Explosive rate | PRIME v2: success-gated, pass >= 15, rush >= 10 | CFBD `explosiveness` = mean PPA of successful plays | **C** (different concept) | no (separate ablation) |
| Finishing (points/scoring opportunity) | drive adjudication | `/game/box/advanced` scoring opportunities | **B/C** | no (2023+ ablation only) |
| Field position | drive start yards | `/game/box/advanced` average start | **B** (corr 0.65-0.80) | no (ablation only) |
| Havoc | PRIME locked Havoc v1 | `/game/box/advanced` havoc | **B/C** | no (ablation only) |
| MWDR edges, MWDR x possessions | sandbox components | none | **C** | no |
| Success / turnover volume edge | raw net edge x expected possessions | rebuilt from adjusted success + box turnovers per CFBD drive | **B** | yes (re-implemented, flagged) |
| Explosive volume edge | explosive net edge | none | **C** | no |

**A-lite** is the control that makes the comparison fair: the *PBP-derived* values of exactly the 19 concepts
Model B reproduces (SRS margin, 8 adjusted metrics x 2 sides, 2 volume edges). Model B differs from A-lite only in
the source of the numerators and denominators.

## 2. Backtest design (Phases 2-5)

- Seasons 2014-2025 (2020 has no season), test 2022-2025, training = strictly earlier seasons, expanding window.
- Population: the games Model A is eligible for (both teams >= 3 games, all 55 features finite, FBS vs FBS) that
  Model B also covers. **No game was dropped**: every Model-A-eligible game in all 11 seasons (2,481 test games) had a complete Model B feature row.
- Margin = OLS on scoring margin (standardized, ridge 1e-6), the same for every model. Win probability =
  Phi(margin / sigma_train). Same rule everywhere.
- Leakage: features for a game use only team-games from strictly earlier (season type, week) partitions; the
  training set is strictly earlier seasons; ridge for expanded models is chosen using only the last training
  season. Tests mutate the future and assert unchanged pregame features.
- Paired bootstrap: 5,000 game resamples, 95% percentile intervals of (B - A).

### Results, 2022-2025, min 3 games, n = 2,481

| Model | Accuracy | Log loss | Brier | MAE | RMSE | Median AE |
|---|---|---|---|---|---|---|
| Scores-only SRS (floor) | 69.33% | 0.5904 | 0.2014 | 13.14 | 16.68 | 10.87 |
| **A** PBP, 55 features (dormant v2) | 69.57% | 0.5736 | 0.1962 | 12.63 | 15.91 | 10.82 |
| **A-lite** PBP, same 19 concepts | 69.45% | 0.5749 | 0.1969 | 12.71 | 15.96 | 10.76 |
| **B** aggregates, same 19 concepts | 69.53% | 0.5736 | 0.1963 | 12.68 | 15.93 | 10.84 |

Paired differences (B minus comparator; 95% CI). Lower is better for MAE/log loss.

| Comparison | Accuracy | MAE | Log loss |
|---|---|---|---|
| B - A-lite (same stats) | +0.08 pp [-0.69, +0.81] | -0.028 [-0.085, +0.030] | -0.0013 [-0.0040, +0.0013] |
| B - A (55 features) | -0.04 pp [-1.05, +0.93] | +0.050 [-0.035, +0.135] | -0.0001 [-0.0041, +0.0039] |
| B - SRS floor | +0.20 pp [-1.13, +1.57] | -0.461 [-0.638, -0.290] | -0.0169 [-0.0267, -0.0074] |
| A - A-lite (value of PBP-only features) | +0.12 pp [-0.77, +1.01] | -0.078 [-0.150, -0.005] | -0.0013 [-0.0046, +0.0022] |

Model B is statistically indistinguishable from PBP Model A on accuracy, MAE and log loss, and is
significantly better than the scores-only floor. The PBP-only features (explosiveness, finishing, field
position, havoc, down splits, MWDR) are worth about 0.08 points of MAE together (the CI just excludes zero) and
nothing measurable on accuracy or log loss.

### By season (accuracy / MAE)

| Season | n | SRS | A | A-lite | B |
|---|---|---|---|---|---|
| 2022 | 620 | 67.9 / 13.00 | 69.7 / 12.53 | 69.8 / 12.64 | 68.5 / 12.55 |
| 2023 | 636 | 69.7 / 13.68 | 68.7 / 13.10 | 69.8 / 13.11 | 69.8 / 13.02 |
| 2024 | 638 | 68.8 / 13.17 | 70.1 / 12.48 | 68.8 / 12.62 | 69.4 / 12.60 |
| 2025 | 587 | 71.0 / 12.68 | 69.8 / 12.38 | 69.3 / 12.45 | 70.4 / 12.54 |

### By game type and season phase (accuracy / MAE)

| Segment | n | SRS | A | A-lite | B |
|---|---|---|---|---|---|
| FBS vs FBS (all rows) | 2,481 | 69.3 / 13.14 | 69.6 / 12.63 | 69.4 / 12.71 | 69.5 / 12.68 |
| Conference | 2,036 | 69.6 / 13.01 | 69.6 / 12.51 | 69.7 / 12.57 | 69.9 / 12.54 |
| Non-conference | 445 | 68.1 / 13.74 | 69.2 / 13.20 | 68.1 / 13.33 | 67.9 / 13.31 |
| Home site | 2,246 | 70.1 / 13.19 | 70.2 / 12.65 | 70.3 / 12.72 | 70.5 / 12.68 |
| Neutral site | 235 | 61.7 / 12.64 | 63.8 / 12.41 | 61.7 / 12.63 | 60.4 / 12.67 |
| Model picks home | ~1,520 | 71.3 / 13.18 | 71.8 / 12.76 | 71.8 / 12.69 | 71.7 / 12.75 |
| Model picks away | ~950 | 66.1 / 13.08 | 66.0 / 12.43 | 65.8 / 12.74 | 66.0 / 12.57 |
| Clear favorite (abs margin >= 7) | ~1,330 | 79.0 / 13.53 | 78.9 / 12.91 | 77.9 / 13.21 | 78.8 / 12.93 |
| Toss-up (abs margin < 7) | ~1,150 | 60.3 / 12.78 | 58.5 / 12.30 | 59.1 / 12.09 | 58.8 / 12.40 |
| Weeks 4-6 | 543 | 70.2 / 14.23 | 69.2 / 12.73 | 70.3 / 12.81 | 69.6 / 12.68 |
| Weeks 7+ | 1,762 | 70.0 / 12.85 | 70.4 / 12.58 | 70.1 / 12.64 | 70.6 / 12.63 |
| Postseason | 176 | 60.2 / 12.73 | 61.9 / 12.86 | 60.2 / 13.06 | 58.5 / 13.15 |

The A-eligible population is FBS-vs-FBS only, so there is no FBS-vs-non-FBS row. Weeks 1-3 are empty at min 3
games by construction; see the early-season stress test below. Postseason and neutral-site samples are small
(n = 176 and 235): B is 1-4 pp lower there than the PBP models, inside sampling noise but worth watching.

Calibration (confidence bucket: mean confidence / realized accuracy, B): 0.5-0.6: 54.9 / 55.2 (n=723),
0.6-0.7: 64.9 / 65.5 (638), 0.7-0.8: 74.7 / 75.2 (548), 0.8-0.9: 84.4 / 83.1 (384), 0.9-1.0: 93.9 / 94.1 (188).
A-lite is within the same +/-1.5 pp everywhere.

### Early-season stress test (weeks 1-3 included)

Lowering the eligibility floor to 1 or 2 completed games (`results_early_season.json`):

| min games | n | A | A-lite | B | B - A-lite MAE | B - A MAE |
|---|---|---|---|---|---|---|
| 1 | 2,956 | 70.1 / 13.14 | 69.8 / 13.20 | 69.8 / 13.13 | -0.076 [-0.137, -0.016] | -0.009 [-0.094, +0.074] |
| 2 | 2,675 | 69.5 / 12.75 | 70.1 / 12.84 | 69.9 / 12.76 | -0.075 [-0.138, -0.011] | +0.010 [-0.080, +0.099] |

In weeks 1-3 specifically (n = 343 at min 1): accuracy A 69.4%, A-lite 70.3%, B 72.3%; MAE 16.33 / 16.32 / 16.10.
B is at least as good as PBP early in the season, and slightly better than the A-lite control on MAE and log loss
in the pooled early-season samples. It does not beat the full 55-feature model there.

### Why B can match A-lite

Success-rate parity is near exact (corr 0.985-0.992) and CFBD's PPA is the same underlying quantity PRIME sums
from play-level PPA. The differences that remain (play populations, turnover handling, yard sources) are noise
relative to the opponent-adjustment and the SRS term that dominate the margin prediction.

## 3. Feature-expansion ablations (Phase 6)

Incremental, out-of-sample, ridge chosen on the last training season only; same rows for every variant
(n = 2,481, `results.json` -> `phase6`). Deltas are versus B (same-stats), 95% paired-bootstrap CI.

| Added to B | Accuracy | MAE | Log loss |
|---|---|---|---|
| Rushing efficiency (line yards, second-level, open-field, stuff rate, power success; rush-play exposure) | -0.04 pp | -0.008 [-0.043, +0.028] | +0.0005 |
| Game shape (plays/drive, rush rate, points/drive) | +0.24 pp | -0.072 [-0.134, -0.009] | -0.0024 [-0.0052, +0.0003] |
| CFBD explosiveness (mean PPA of successful plays) | +0.12 pp | -0.004 [-0.018, +0.011] | -0.0001 |
| Havoc proxy from the box score (TFL + PBU + INT + FR) | +0.08 pp | -0.006 [-0.034, +0.021] | -0.0006 |
| All four groups | +0.16 pp | -0.103 [-0.172, -0.032] | -0.0025 [-0.0056, +0.0006] |

Only game shape and the combined set show a CI that excludes zero on MAE, at about 0.07-0.10 points, and neither moves
accuracy or log loss significantly. With five comparisons unadjusted for multiplicity, treat this as a hint,
not a result. Rushing efficiency, CFBD explosiveness and box-score havoc add nothing measurable.

### 3b. Box-advanced-only features (real havoc, field position, scoring-opportunity finishing)

`/game/box/advanced` exists locally only for 2023-2025 (backfilled for this experiment; the 2022 backfill was stopped), so the walk-forward is short: train 2023, test 2024; train 2023-24, test 2025 (n = 1,225, all rows used). Same rows for every variant (`box_advanced_ablation.json`).

| Added to B | MAE, ridge 1e-6 | MAE, ridge 100 | Accuracy (ridge 100) |
|---|---|---|---|
| none (B) | 12.775 | 12.592 | 69.47% |
| CFBD havoc | 12.783 | 12.595 | 69.80% |
| Field position | 12.813 | 12.583 | 69.39% |
| Scoring-opportunity finishing | 12.789 | 12.588 | 69.63% |
| Box-score havoc proxy | 12.753 | 12.581 | 69.55% |
| All three real | 12.826 | 12.587 | 69.71% |

None of the box-advanced-only features improves out-of-sample error; differences are within +/-0.05 MAE and no CI excludes zero (see JSON). The features that only `/game/box/advanced` provides are not needed.


## 4. Opponent adjustment and exposure weighting (Phase 7)

Same B feature set with the adjustment changed (`phase7`; ratings are `y = mean + off(team) - def(opponent)`,
observations weighted by their denominator = play/drive count):

| Variant | Accuracy | MAE | vs shrinkage-50 MAE [95% CI] |
|---|---|---|---|
| Adjusted, exposure-weighted, shrinkage 50 (default, = production) | 69.53% | 12.681 | -- |
| Adjusted, shrinkage 25 | 69.81% | 12.684 | +0.004 [-0.017, +0.025] |
| Adjusted, shrinkage 100 | 69.69% | 12.689 | +0.009 [-0.011, +0.029] |
| Raw exposure-weighted season averages (no opponent adjustment) | 69.69% | 12.850 | +0.170 [+0.069, +0.265] |
| Raw per-game rate averages (no adjustment, no exposure weighting) | 69.81% | 12.845 | +0.164 [+0.058, +0.267] |

Opponent adjustment is worth about 0.17 points of MAE and 0.006 log loss (both significant). Shrinkage in 25-100 is
flat. Exposure weighting itself is not separable here (the two raw variants tie), because play counts vary
little across FBS team-games.

## 5. APR audit (Phase 8)

APR = opponent-adjusted **field-position-adjusted drive value per resolved possession**:
`V = sum over resolved drives d of (P_d - f(s_d))`, `N = |resolved drives|`, fit as
`V/N = mean + off(team) - def(opp)` with a ridge of 10 possessions (`analytics/rating_model.py`).
`P_d` is adjudicated offensive points only; `s_d` is the drive's starting yards-to-goal; `f` is a monotone
10-bin expected-points curve refit at every cutoff.

### It cannot be reconstructed exactly from aggregates

1. **`N` is unobservable.** The resolved-possession count comes from validated, adjudicated drives. CFBD's
   `drives` equals it in only 79-85% of team-games (mean abs gap 0.17-0.32; corr 0.90-0.96).
2. **`P_d` is not the official score.** Official points equal offensive drive points in only 66-78% of team-games
   (MAE 1.8-3.8 points). Subtracting 7 per non-offensive TD (defensive, kick/punt return, from the box) makes 73-85%
   exact (MAE 0.9-2.9), leaving safeties, two-point plays and unresolved drives unrecoverable.
3. **`sum f(s_d) != D * f(mean s)`.** `f` is not linear, and only the *mean* start is published (and only in
   `/game/box/advanced`). Concrete counterexample using the fitted 2025 curve: two offenses, each 12 drives, 24 points,
   mean start 50 yards to goal; one starts 6 drives at its 25 and 6 at the opponent's 25, the other starts all 12 at
   midfield. APR numerators are -8.79 vs -7.54, a gap of **1.05 APR points per 10 possessions** from identical
   aggregates. Across 1,613 real 2025 team-games the Jensen gap `E f(s) - f(E s)` averages 0.073 points/drive (max 0.29).
4. The published mean start is itself a different quantity: correlation with the drive-derived mean start is
   only 0.65 (2024, partial coverage) to 0.80 (2025), MAE 4.6-5.5 yards.

So no aggregate formula reproduces APR. What is available is a *different* metric. Candidates
(`APR_CANDIDATE_SPECS`, `scripts/audit_apr_aggregate_reconstruction.py`), fit with the same solver and ridge,
compared to current APR on final regular-season Net APR:

| Season | Candidate | corr | MAE (affine) | max err | mean / max rank change | top-25 overlap |
|---|---|---|---|---|---|---|
| 2022 | Points/drive (official points less non-offensive TDs) | 0.992 | 0.90 | 3.2 | 3.8 / 13 | 24 |
| 2022 | Total PPA/drive | 0.972 | 1.65 | 5.5 | 6.7 / 37 | 24 |
| 2022 | Fitted latent (regression of true drive value on aggregates) | 0.992 | 0.90 | 2.8 | 3.6 / 21 | 24 |
| 2023 | Points/drive | 0.990 | 0.96 | 3.3 | 4.5 / 23 | 22 |
| 2023 | Fitted latent | 0.991 | 0.91 | 2.8 | 4.2 / 23 | 24 |
| 2024 | Points/drive | 0.992 | 0.90 | 4.2 | 3.8 / 18 | 23 |
| 2024 | Fitted latent | 0.993 | 0.82 | 3.6 | 3.8 / 16 | 23 |
| 2025 | Points/drive | 0.985 | 1.33 | 4.9 | 5.7 / 23 | 22 |
| 2025 | Fitted latent | 0.983 | 1.35 | 4.9 | 5.8 / 23 | 21 |
| 2024 | Points above linear start expectation (box-advanced start) | 0.989 | 0.97 | 5.6 | 4.3 / 30 | 23 |
| 2025 | Points above linear start expectation (box-advanced start) | 0.976 | 1.61 | 5.9 | 7.1 / 29 | 23 |

All are highly correlated with APR but differ by ~1 APR point on average and up to 3-5 for individual teams, with typical
rank moves of 4-6 places (max 13-38). That is far too large to describe as "the same APR." The field-position
candidate is no better than plain points/drive (worse in 2025) because the published average start does not match PRIME's
drive-derived start. In 2024 it is roughly on par with points/drive (MAE 0.97 vs 0.90), still not equivalent.

### Does APR help predict games? (2022-2025, n = 2,305 regular-season games)

APR features are home/away matchup edges (off - opposing def) from the ratings as of the prior week; old APR is the
current production code recomputed weekly. B (no APR) is the reference.

| Model | Accuracy | MAE | Log loss | MAE vs B [95% CI] |
|---|---|---|---|---|
| B (no APR) | 70.37% | 12.645 | 0.5655 | -- |
| B + old APR | 70.41% | 12.610 | 0.5634 | -0.035 [-0.088, +0.021] |
| B + APR-agg points/drive | 70.76% | 12.612 | 0.5632 | -0.033 [-0.069, +0.004] |
| B + APR-agg total PPA/drive | 70.46% | 12.645 | 0.5654 | -0.000 [-0.013, +0.013] |
| B + APR-agg latent | 70.50% | 12.616 | 0.5637 | -0.029 [-0.072, +0.016] |
| Scores-only SRS | 69.93% | 13.177 | 0.5853 | -- |
| SRS + old APR | 69.63% | 12.901 | 0.5701 | -0.276 vs SRS [-0.428, -0.123] |

**Honest reading:** APR is a good *standalone* signal (it improves a scores-only model by 0.28 points MAE, significant),
but on top of the success/EPA/yardage edges it adds about 0.03 points of MAE with a CI that includes zero. Nothing in
the aggregate family is distinguishable from old APR in the prediction test, and total PPA/drive adds nothing beyond
the PPA edges already in B. APR earns its place as a *rating* (interpretable, possession-based, exact
field-position accounting), not as a prediction feature.

### APR v2 (proposal; not adopted)

If a PBP-free rating is ever wanted it should be named **APR v2 = opponent-adjusted (official offensive points less
non-offensive TDs) per CFBD drive, ridge 10 drives**, with no field-position term until `/game/box/advanced` is
backfilled for history and its start definition is reconciled. It correlates 0.985-0.992 with APR but is not APR
and would change every published Net APR and rank. It was **not** migrated: the standing rule is not to change APR
without an explicit decision, and the audit shows no accuracy reason to.

## 6. Decision

- **Prediction model (Phase 5 gate):** *non-inferior/equivalent.* B is indistinguishable from PBP Model A on
  accuracy, log loss and MAE (CIs symmetric about zero, upper MAE bound +0.135), better than the scores-only
  floor by 0.46 MAE, and at least as good as PBP early in the season. **A PBP-free mature-season prediction model
  is viable**, and it is the recommended replacement for the dormant, currently broken v2 stack.
- **What was lost by dropping PBP:** only ~0.08 MAE from PRIME's proprietary explosiveness, finishing, field
  position, havoc, down-level splits and MWDR; game-shape and box-score features recover about that much.
- **Published predictions:** not altered. They were already PBP-free.
- **APR:** not migrated (cannot be reconstructed; no predictive reason).
- **PBP remains required** for APR and Off/Def APR, the drive-based ratings, and PRIME's proprietary metrics;
  it can be treated as optional for the prediction stack only.

## 7. Recommended architecture

```
games.json + game_team_stats.json + /stats/game/advanced (+ /game/box/advanced when present)
   -> canonical team-game observations   (advanced_shadow.load_aggregate_games)
   -> opponent adjustment                (fit_metric_ratings, exposure-weighted, prior partitions only)
   -> site-aware SRS + matchup edges     (advanced_shadow.build_shadow_rows)
   -> OLS margin -> win probability      (advanced_shadow_eval / advanced_shadow_predict)
PBP layer (plays/drives) -> optional: APR, proprietary metrics only
```

## 8. Operational benefit

For one season (2024): `plays.json` 99.8 MB raw (337 MB canonical) plus `drives.json` 12 MB raw = ~112 MB; the aggregate
inputs are `games` 0.7 MB + `game_team_stats` 2.6 MB + `advanced_game_stats` 3.4 MB = 6.7 MB (~17x less; ~6x less even
with the optional `advanced_box_scores` 10.7 MB), and no PBP canonicalisation, drive validation, or play-classification heuristics on the
prediction path (success thresholds, explosive rules, drive/possession adjudication, PPA turnover handling,
field-position bins). API cost for Model B is one `/stats/game/advanced` call and one `/games/teams` call per week, plus `/games`
(`/plays` and `/drives` weekly calls are no longer needed for prediction; `/game/box/advanced` is one call per game and optional; it is never required by Model B). Failure modes shift from "PBP
missing/misparsed for a game" to "CFBD has no advanced row for a team-game": 0-38 team-games per season (0-2.2%), listed
in `coverage_by_season.json`. `/game/box/advanced` returned HTTP 500 for at least one 2024 game during the backfill.

Missing data by season (team-games with an advanced-stats row / total): 2014 1698/1736, 2015 1726/1740, 2016 1714/1746,
2017 1738/1748, 2018 1762/1768, 2019 1774/1776, 2021-2023 complete, 2024 1830/1838, 2025 1616/1616. A missing
team-game row is simply absent from the rating fits; the game itself is still predicted from the other rows. No test
game was dropped and every gap is listed in `coverage_by_season.json`.

## 9. Limits

- Test window is 2022-2025 (2020 has no season); ~620 games per season, so single-season differences are noisy.
- Model A's stored PBP features were built with PRIME definitions at the time they were saved; the explosive
  redefinition (success-gated, 15/10) is not in them. The comparison is against the model as it stands.
- The published early-season blend was not re-scored against Model B; it depends on preseason priors Model B does
  not have. Testing "blend + B in-season term" for weeks 2-5 is the natural next step.
- `/game/box/advanced` exists locally only for 2023-2025, so box-only feature tests use a short window.
- Historical Net APR published for 2014-2025 is the pre-v5 model; the APR audit recomputes the current code.

Field-position APR candidate in the prediction test (2025 only, n = 541; slope from the prior season): MAE vs B -0.002 [-0.039, +0.034]; versus old APR -0.025 [-0.157, +0.113]. No signal beyond B.

## 10. Production decision (Option A) and feature selection

**Decision.** Current APR stays exactly as it is, on plays + drives: same methodology, version, historical values and rankings. It is not
migrated to drives-only. Everything else that can be PBP-free moves to CFBD aggregate sources.

**Why APR stays on plays + drives.** Rebuilding APR from `/drives` alone with the unchanged production fit does not reproduce it
(`data/audits/advanced_shadow/apr_drives_only.json`, `scripts/audit_apr_drives_only.py`, 2014-2026): the average team moves 0.9-2.4 APR
points, correlation is 0.93-0.99, the average rank shift is about 3 places in the best season and about 10 in 2025-26, and individual
shifts reach roughly 20-60 places. Two source limitations cause it: CFBD drive score fields are sometimes stale or not updated, and
`/drives` cannot tell an offensive turnover from a special-teams one, while production uses plays to decide possession eligibility and
to attribute touchdown points (extra point, two-point try, missed). The earlier "reproduces for all 138 teams" audit
(section 5) used the production code, which reads plays; it proves the published numbers are correct, not that drives suffice.
A future no-PBP possession rating would be a separate project, paired with a full historical rebuild, and would take a new name unless
it measures materially the same concept.

**The live production migration is scores-only -> aggregate model**, not PBP -> aggregate: the 55-feature PBP model (Prediction v2) is
not publishing. The published early-season blend covers weeks 1-5; the aggregate model covers weeks 6+.

**Feature selection** (`scripts/run_aggregate_feature_selection.py`, `feature_selection.json`; identical walk-forward populations, test
2022-2025, train strictly earlier seasons, ridge chosen on the last training season only):

| Candidate (main population, n = 2,481) | k | SU | MAE | RMSE | Log loss | Brier | Max calibration gap | MAE vs best [95% CI] |
|---|---|---|---|---|---|---|---|---|
| lean-9 (SRS, EPA, success, YPP, 2 volume) | 9 | 69.13% | 12.677 | 15.95 | 0.5735 | 0.1965 | 1.5 pp | +0.095 [+0.022, +0.170] |
| S19 (source-parity set) | 19 | 69.33% | 12.683 | 15.94 | 0.5733 | 0.1963 | 0.7 pp | +0.101 [+0.034, +0.170] |
| **S19 + game shape (selected)** | 25 | 69.57% | 12.615 | 15.86 | 0.5709 | 0.1954 | 1.1 pp | +0.033 [-0.004, +0.070] |
| S19 + shape + havoc proxy | 27 | 69.45% | 12.599 | 15.86 | 0.5708 | 0.1954 | 1.9 pp | +0.017 [-0.014, +0.049] |
| S19 + shape + explosiveness | 27 | 69.49% | 12.616 | 15.86 | 0.5710 | 0.1955 | 1.3 pp | +0.034 [-0.000, +0.070] |
| S19 + shape + rushing | 35 | 69.77% | 12.587 | 15.85 | 0.5711 | 0.1953 | 1.3 pp | +0.005 [-0.007, +0.019] |
| S19 + all four groups (best MAE) | 39 | 69.65% | 12.582 | 15.83 | 0.5708 | 0.1952 | 0.9 pp | reference |

Early-season stress (min 1 game, n = 2,939) ranks the candidates the same way. Game shape and the larger sets **reduce** MAE (improvements,
about 0.07 for shape and 0.10 for everything versus S19). The selection rule was changed after the first run and that change is recorded
in the script: the first rule (within one paired standard error of the best) picked 39 features in the main population and 27 in the
early-season one, because near-identical models have tiny paired standard errors. The rule used is "the simplest candidate whose paired
MAE difference to the best is statistically indistinguishable from zero, with calibration within 3 pp and MAE no worse than S19 in
every test season," which selects **S19 + game shape (25 features)** in both populations. It captures about 70% of the gain from the
full set, uses only official box + `/stats/game/advanced` (no `/game/box/advanced`, no rush-play reconstruction), and was better than
S19 in each of 2022, 2023, 2024 and 2025. APR is not a model input.

**Frozen model.** `prospective/2026/aggregate-model-frozen.json` (version `aggregate-advanced-2026-v1`): feature contract hash, training
cutoff (through 2025, 6,754 games), ridge 10, coefficients and standardization, logistic calibration fit on walk-forward
out-of-sample predictions 2018-2025 (4,325 games; every confidence bucket within about 2 pp), and the walk-forward backtest of the frozen
configuration (2022-2025: 69.7% SU, MAE 12.62, log loss 0.570). Weekly snapshots are exclusive-create and start at week 6.

**Source-failure contract.** Failed `/game/box/advanced` requests and non-object responses are never stored (they are skipped and
retried); an HTTP-success empty answer is stored with `sourceStatus: "empty_response"`. The shadow loader reports invalid, empty and
absent games instead of reading them as null statistics. The scratch 2022-2024 box backfill used a local wrapper that stored empty
placeholders; the 4 affected 2024 games are now reported as `invalid_payload` (results were unchanged, and that data is not evidence).
