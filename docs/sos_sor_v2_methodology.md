# SOS/SOR v2: PRIME AdjNet-based Strength of Schedule / Strength of Record

Replaces the homepage Ratings page's SRS-based SOS/SOR (v1) with a
methodology anchored to PRIME's own published Overall Rating (AdjNet).
Scope: **only** the homepage Ratings page's `sos`/`sor`/`sosRank`/`sorRank`
fields in `scripts/build_real_data.py` and `scripts/compile_site_data.py`.
Not touched: APR, AdjOff, AdjDef, AdjNet itself, the prediction model, the
Advanced page's separate per-week-summable SOS (`wk.opponentSrsSum` /
`opponentSrsCount`, which intentionally stays on the older per-game SRS
dataset for a different reason -- see `build_real_data.py`'s own comment
above that block), `cff`, and `asm` (both still power the Advanced page and
the legacy-mode rollback contract).

## Root cause of the v1 failure mode

v1's SOS was the average SRS rating of opponents played, and SOR compared
actual wins to `Phi(-opponent_srs / current_week_fit_rmse)` summed across
the schedule. Two compounding problems:

1. **SRS is a nearly-unregularized simultaneous least-squares fit.** Early
   in a season, the number of games is barely larger than the number of
   teams (at the season's real 2026-week-2 cutoff: ~151 games, ~138 teams,
   3 disconnected schedule components). With that little data, the fit
   nearly interpolates results, producing exactly the kind of absurd values
   reproduced from the current code: California +64.5, UTEP -54.9, Syracuse
   +61.5. SOS then averages these meaningless numbers.
2. **SOR divided by the SAME fit's in-sample residual (~4.96 points).**
   Using an in-sample RMSE from a model that's nearly saturated is not a
   predictive standard deviation -- it collapses win probabilities toward
   0%/100%. Michigan's three actual 2026 opponents evaluated near
   -13/-12/-55 under this fit, making an "average FBS team" a ~99.99%-plus
   favorite in all three -- Michigan's real 3-0 record then produced
   SOR ≈ +0.01, a number with no useful meaning.
3. Two secondary bugs, also fixed here: SOS/SOR compared component-relative
   SRS values across disconnected schedule graphs as if they were on one
   national scale, and ranks were assigned to already-ROUNDED sos/sor
   values, so many teams landing on an identical rounded `0.00` still
   received different, arbitrary ranks from array order.

## New formulas

**SOS** (opponent quality; no location adjustment -- see rationale below):

```
SOS(team, week) = mean(opponent AdjNet)
                  over every game played through that site-week
```

`AdjNet` is `composite["AdjOff"][opponent] + composite["AdjDef"][opponent]`,
the exact walk-forward, full-precision snapshot already computed every
site-week for the published Off/Def/Net APR (`rating_model.
fit_publication_composite`, `possession-efficiency-field-position-adjusted-v5`)
-- not a second, separately-fit rating. Past opponents benefit from
what's known about them AT the selected cutoff (a week-1 win over a team
that proves excellent by week 8 improves week-8 SOS -- correct for a
résumé metric, not a leak, since a week-14 snapshot already legitimately
knows how week-3 opponents turned out).

**SOR** (wins above an average FBS team on the same schedule, location-aware):

```
for each game i:
    expected_margin_i = -opponent_AdjNet_i + SOR_HFA_POINTS * location_i
    P(win_i) = 1 / (1 + exp(-expected_margin_i / SOR_SCALE))

SOR = actual_wins - sum(P(win_i))
```

`location_i` is +1/-1/0 for home/away/neutral from the rated team's own
perspective. Margin of victory never enters SOR -- only the win/loss
indicator (`compute_sos_sor()`'s signature literally has no margin field).

## Overall Rating source (traced, not guessed)

`rating_model.fit_publication_composite()` → `build_real_data.build_year()`'s
`composite = {"AdjOff": {...}, "AdjDef": {...}}` (refit fresh every site-week
from every game played through that week) → `compile_site_data.py`'s
`RATING_SOURCE_KEYS["hierarchical_hfa"] = {"adjEM": "adjNet", ...}` →
published `web/public/data/rankings/<season>.json`'s `adjEM` field, shown on
the homepage as **Net APR**. SOS/SOR v2 reads `composite["AdjOff"]`/
`["AdjDef"]` directly (full precision, before the 3-decimal rounding
`adj_off`/`adj_def`/`adj_net` get for their OWN published fields), for the
exact opponents a team faced that week.

## Home-field advantage

`HFA_ENABLED = False` in `rating_model.py` -- the "hierarchical_hfa" name is
a historical compatibility label; the published Off/Def/Net APR model fits
**no** home-field term at all (asserted, not merely undocumented). There
was nothing internal to reuse. `SOR_HFA_POINTS = 3.0793` (AdjNet-scale
points) was calibrated jointly with the win-probability scale via
`scripts/calibrate_sos_sor.py` -- see below.

## Win-probability model and calibration

Logistic (Option A from the spec): `P(win) = 1 / (1 + exp(-expected_margin
/ SOR_SCALE))`. Chosen over probit because a 2-parameter logistic MLE is
the standard, well-understood tool for exactly this win/loss calibration
problem and has a clean likelihood to optimize directly; the two forms are
very close in practice for this kind of data, so there was no expectation
either would meaningfully out-calibrate the other.

**Fit**: `scripts/calibrate_sos_sor.py` replays `build_year()`'s existing,
UNCHANGED composite computation to get a walk-forward per-site-week AdjNet
snapshot for 2022-2025. For every FBS-vs-FBS game played in site-week `wk`,
both teams' AdjNet is read from the PREVIOUS site-week's snapshot (not
`wk`'s own -- that would leak the game's own result into its own
prediction), building a symmetric training set: `(adjNetDiff, location,
won)` from both team perspectives. A 2-parameter logistic MLE
(`scipy.optimize.minimize`, Nelder-Mead) fits `logit(P) = a * adjNetDiff +
c * location`; `SOR_SCALE = 1/a`, `SOR_HFA_POINTS = c/a`.

**Out-of-sample validation** (required before trusting the methodology,
not skipped): fit on 2022-2024 (4,246 training rows), evaluated on
held-out 2025 (1,450 rows).

| Metric | Value |
|---|--:|
| Holdout log-loss | 0.5699 |
| Holdout Brier score | 0.1945 |
| Holdout raw home-team win rate | 58.1% |

Decile calibration (predicted vs. observed win rate, held-out 2025, n=145/decile):

| Predicted | Observed |
|--:|--:|
| 0.117 | 0.097 |
| 0.224 | 0.241 |
| 0.316 | 0.310 |
| 0.392 | 0.379 |
| 0.464 | 0.503 |
| 0.536 | 0.497 |
| 0.608 | 0.621 |
| 0.684 | 0.690 |
| 0.776 | 0.759 |
| 0.883 | 0.903 |

No systematic bias across the probability range -- calibration holds.
After validating, refit on all four seasons combined (5,696 rows) for the
shipped constants: **`SOR_SCALE = 8.7999`**, **`SOR_HFA_POINTS = 3.0793`**.

## FCS baseline

No FCS team carries a PRIME AdjNet (FCS never enters the core opponent-
adjusted rating graph). Rather than compare AdjNet -- a points-per-10-
resolved-possessions efficiency scale -- to raw full-game point margins
directly (a unit mismatch that would make a naive least-squares baseline
meaningless), `SOR_FCS_BASELINE` is calibrated through the SAME logistic
model as everything else: a 1-parameter MLE (holding `SOR_SCALE`/
`SOR_HFA_POINTS` fixed) over every real FBS-vs-FCS game, 2022-2024 (227
games; 2025 had none land on a resolvable walk-forward snapshot in this
cut), using each FBS team's own pregame AdjNet. Result: **`SOR_FCS_BASELINE
= -23.7996`**, reproducing the empirical 93.0% FBS win rate against FCS
opponents in that sample. Frozen, not recalibrated every build -- exactly
what made the v1 FCS baseline unstable early in a season (recalibrating
from only the current season's thin FBS-vs-FCS sample).

## Ranking (full precision, not rounded)

`build_real_data.py` now stores `sos`/`sor` FULL PRECISION in `week_rows`.
`compile_site_data.py`'s `assign_rank()` ranks on those full-precision
values (unchanged function -- this alone fixes v1's rounding-then-ranking
bug), and only rounds to 2 decimals afterward, when building the published
`main_rows`. Ties are resolved by stable sort order among genuinely-equal
full-precision values; given continuous AdjNet-derived inputs, an exact
float tie is astronomically unlikely in practice. Full competition/dense
ranking (explicit same-rank-for-ties, skipping subsequent ranks) was
considered but not implemented: `validate_site_data.py`'s existing
publication gate hard-requires ranks to form an exact `1..N` sequence with
no skips for every metric in `METRICS` (`adjEM`/`adjO`/`adjD`/`sos`/`sor`
uniformly) -- changing that would have to touch AdjNet/AdjOff/AdjDef
ranking too, which is explicitly out of scope for this change.

## What was deliberately NOT changed

- APR, AdjOff, AdjDef, AdjNet, and the prediction model -- SOS/SOR
  **consume** the existing rating; they never feed back into it.
- `cff`/`asm`/`fit_srs`/`srs_ratings` -- still back the Advanced page and
  the legacy-mode rollback contract.
- The Advanced page's own SOS (`wk.opponentSrsSum`/`opponentSrsCount`) --
  a deliberately separate, week-range-summable metric built from
  `iterative_ratings.py`'s locked per-game pregame SRS dataset, outside
  this task's stated scope (the homepage Ratings page).
- `calibrate_fcs_baseline()`/`FCS_BASELINE_MIN_GAMES` -- kept, unused by
  v2, because `tests/test_publication.py` exercises the function directly.

## Files changed

- `scripts/build_real_data.py` -- new `SOS_VERSION`/`SOR_VERSION`/
  `SOR_SCALE`/`SOR_HFA_POINTS`/`SOR_FCS_BASELINE` constants,
  `_sor_win_probability()`, `compute_sos_sor()`; `team_game_log` now
  carries game location; old SRS-based `LEGACY_SOR_VERSION` block kept for
  `cff`/`asm`.
- `scripts/compile_site_data.py` -- rounds `sos`/`sor` for publication only
  AFTER `assign_rank()` has ranked the full-precision values.
- `scripts/calibrate_sos_sor.py` (new) -- the historical calibration
  research script; not part of the production build, rerun only for a
  deliberate, infrequent recalibration.
- `scripts/audit_sos_sor_v2.py` (new) -- old-vs-new 2026 comparison plus
  the 2022-2025 historical backtest.
- `data/models/sos_sor_calibration.json` (new) -- calibration provenance
  (full holdout evaluation, FCS fit details).
- `web/app/page.tsx` -- SOS/SOR tooltip text no longer mentions SRS.
- `tests/test_sos_sor.py` (new).
