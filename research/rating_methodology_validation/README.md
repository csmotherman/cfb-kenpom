# LEILA Rating Methodology Validation

Research-only. **Nothing in this directory changes production.** No file
outside `research/rating_methodology_validation/` was modified by this
project except where noted in REPORT.md.

## What this answers

Whether opponent-adjusted points-per-resolved-possession (current LEILA
Adj. Net) is actually the best available foundation for a college football
rating, tested against MOV/SRS, raw (non-adjusted) possession efficiency,
opponent-adjusted EPA, Success Rate, and Explosiveness, plus learned
combinations of those — using a true week-by-week walk-forward harness
across 2014-2025 (2020 excluded, same as the rest of this repo), never
letting a model see a future game.

See `REPORT.md` for the full writeup and findings.

## How to reproduce

Run from this directory, in order (each step reads the previous step's
output; none require network access, only this repo's already-materialized
canonical/derived data for 2014-2025):

```
python build_dataset.py          # ~80s.  data/season=YYYY.json
python harness.py                # ~70s.  predictions/walk_forward_predictions.json,
                                  #        predictions/team_rating_snapshots.json
python run_production_model.py   # ~15s.  adds A2 (production-faithful, with
                                  #        prior-season taper) and A3 (same,
                                  #        taper forced off) to the predictions.
python garbage_time.py           # ~2m.   adds D2/E2 (EPA/Success with the
                                  #        existing garbage-time proxy applied).
python evaluate.py               # ~25s.  results/evaluation_summary.json
python composite.py              # ~5s.   results/composite_summary.json
                                  #        (Models G and H, learned weights)
python bootstrap_compare.py            # results/bootstrap_comparisons.json
python bootstrap_compare_hybrid.py     # results/bootstrap_hybrid_vs_production.json
python connectivity.py           # ~1s.   results/connectivity.json
python sos_stress_test.py        # ~1s.   results/sos_stress_test.json
python nebraska_case_study.py    # ~2s.   results/nebraska_case_study.json

python -m pytest test_leakage.py -q    # explicit leakage guards, run any time
```

## Directory map

| File | What it is |
|---|---|
| `build_dataset.py` | Builds the one shared per-team-game dataset every model reads (possession points, EPA, Success, Explosive raw counts, final score) from this repo's own canonical/derived layers. |
| `models.py` | Models A, B, C, D, E, F — every opponent-adjusted model calls the SAME production solver (`iterative_ratings.fit_metric_ratings` / `fit_srs`), pointed at a different spec. |
| `production_model.py` | Model A2/A3 — the real production `fit_publication_composite` function, called directly (not reimplemented), with and without the prior-season-opponent taper. |
| `harness.py` | The walk-forward loop: fit on strictly-prior weeks only, predict the next week, every season independently. |
| `evaluate.py` | Section 7 metrics (MAE, RMSE, correlation, win accuracy, Brier, log loss), calibrated via leave-one-season-out regression (training data only). |
| `composite.py` | Models G (learned EPA+Success+Explosive blend) and H (learned possession+process blend) — weights fit by ridge regression on training seasons only, never hand-assigned. |
| `bootstrap_compare.py`, `bootstrap_compare_hybrid.py` | Block-bootstrap significance tests (by season/week, not by game, to respect within-week correlation) for every head-to-head comparison in the report. |
| `garbage_time.py` | Re-derives EPA/Success with this repo's existing, already-validated garbage-time proxy applied, for direct comparison. |
| `connectivity.py` | Section 10 — FBS opponent-graph connected-components by week. |
| `sos_stress_test.py` | Section 8 — performance/opponent-strength cohort bias, calibrated to points. |
| `nebraska_case_study.py` | Section 9 — Nebraska's 2026 rating under every methodology at the same cutoff, plus its game log. |
| `test_leakage.py` | Explicit leakage tests (synthetic data): a corrupted future week must never change an earlier week's prediction; history must reset between seasons. |

## Key discipline

- **Leakage**: every fit uses `week < cutoff`, never `<=`. History resets
  to empty at week 1 of each season (no season-to-season leakage in the
  historical study; the ONE deliberate exception, matching production
  exactly, is Model A2's prior-season-opponent taper, which reads the
  PRIOR season's own final, fully-closed rating — see production_model.py's
  docstring for why that is not leakage).
- **Calibration**: every edge-to-margin or edge-to-win-probability
  conversion is fit on training seasons only (leave-one-season-out), never
  on the season being scored.
- **No hand-tuned weights**: Models G and H learn their component weights
  from training data via ridge regression, never an assigned split like
  40/30/30.
- **Significance**: every head-to-head comparison in the report is backed
  by a block-bootstrap 95% CI (resampled by season+week, not by individual
  game, since games in the same week share fit noise), not just a point
  estimate.
