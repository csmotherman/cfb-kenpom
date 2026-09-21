# PRIME vs the market

The market is itself a predictive model, so it is the benchmark. Judged on winner accuracy, margin error, probability quality and whether
model-market disagreements carry signal. Against-the-spread record is a diagnostic only.

Data: CFBD `/lines` for 2014-2025 (`scripts/ingest_market_lines_history.py`, `data/market/history/season=<year>.json`), one primary quote per
game chosen by the same rule as the live exporter, ~99% of completed games. CFBD does not label a quote "closing"; the last quote it holds
(`spread`) is used, `spreadOpen` is kept. Market home margin = -spread. Failed requests are recorded in `failedPartitions` and retried, never
stored as "no line"; games with no usable line in a successful response are listed under `noLine`.

Method (`scripts/build_market_benchmark.py`): the frozen aggregate model's walk-forward out-of-sample margins (each season predicted from earlier
seasons only) versus the line, on identical FBS-vs-FBS games (both teams at least 3 games) that have a spread. Paired bootstrap, 5,000 resamples.

## 2022-2025 backtest, 2,481 games

| Measure | PRIME | Market | PRIME minus market (95% CI) |
|---|---|---|---|
| Winner accuracy | 69.8% | 71.8% | -2.0 pp (-3.4, -0.6) |
| Margin MAE | 12.62 | 12.00 | +0.62 (+0.44, +0.81) |
| Margin RMSE | 15.86 | 15.24 | |
| Log loss (1,849 games with moneylines) | 0.572 | 0.544 | +0.028 (+0.017, +0.038) |

The closing line is more accurate than PRIME on every measure, and the gaps are statistically clear. It was ahead in each of the four seasons
on MAE (2022 11.99 vs 12.58, 2023 12.29 vs 12.90, 2024 11.84 vs 12.56, 2025 11.86 vs 12.40).

## Do disagreements contain signal?

Regressing actual-minus-line on PRIME-minus-line through the origin gives a slope of 0.10 (95% CI -0.02 to 0.22): indistinguishable from zero
(no signal) and far from one (PRIME fully right). The PRIME side covers 49-52% in every disagreement bucket from 0 to 9+ points (all 95% ranges
include 50%), so large disagreements are not a betting edge either.

## 2026 so far (live)

146 graded picks have a line: winner accuracy PRIME 73.3% vs market 83.6%, MAE 13.6 vs 11.0. Small sample, all from the early-season
blend (weeks 1-4).

## What it means

PRIME's aggregate model is a good, calibrated, PBP-free model, but it does not beat the market and does not identify where the market is wrong.
The line embeds information PRIME does not have (injuries, depth charts, weather, sharp money). Published as-is on the Model Performance page.
