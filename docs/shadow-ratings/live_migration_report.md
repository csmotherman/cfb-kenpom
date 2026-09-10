# Live AdjOff / AdjDef / AdjNet migration report

**Decision: READY TO PUBLISH.** This means the source migration and staged 2025 payload are ready for human review. Nothing was committed, pushed, deployed, or copied over the currently published data.

## 1. Current publication contract

The current path is `build_real_data.py::build_year` → `compile_site_data.py::build_season_payload` → `site/data.js` → `export_web_data.py` → `web/public/data/rankings/<season>.json`. The Next.js ratings, team, matchup and this-week pages consume the public keys through `web/lib/data.ts`; the older static ratings and team pages consume the same keys from `site/data.js`.

Before this migration, `adjEM` was the scoring-margin SRS (`cff`), while `adjO` and `adjD` were the iterative YardsPerPlay offense and defense edges. SOS and SOR genuinely depend on SRS. They continue to use the separate SRS fit and were not redirected to the composite. The Advanced payload also retains `cff` as SRS, now labeled SRS in its UI. Validation was changed from requiring `adjEM == cff` in every mode to applying that invariant only in legacy mode and applying `adjEM == adjO + adjD` in hierarchical mode.

No API arithmetic or frontend scale assumption was found. Consumers display, rank, sort or compare the three generic numeric fields. Visible descriptions that tied them to SRS/YPP were updated.

## 2. Field contract

The public field names remain unchanged:

| Public key | New meaning |
| --- | --- |
| `adjO` | AdjOff composite |
| `adjD` | AdjDef composite |
| `adjEM` | AdjNet = AdjOff + AdjDef |

Higher is better for all three. The separate Advanced `cff` field remains SRS. No speculative legacy fields were added because no downstream consumer needs the old values under a second name; rollback regenerates the original contract through explicit legacy mode.

## 3. Rating input path

`build_year` builds a parallel, FBS-vs-FBS-only metric history from canonical plays through `metric_fields_by_team_game(..., exclude_garbage_time=True)`. It supplies EPA sum/plays, successful plays/eligible plays, and successful-play yards. Existing cumulative Advanced rows, raw weekly counters, derived partitions, team stats and legacy fits continue to use their prior unfiltered inputs.

The garbage-time classifier exists once, in `derived/games.py`. Missing canonical play rows become explicit zero-weight observations and are counted in metadata; filtered values never fall back to unfiltered metrics.

## 4. Hierarchical solver wiring

`analytics/rating_model.py` is the live publication wrapper around the validated `analytics/shadow_ratings.py` solver. It freezes λ_team=200, λ_conf=400, HFA enabled, and weights 6.8693 / 1.7265 / −0.1906. It validates season-specific team and opponent conference mappings, refuses unknown or conflicting membership, preserves named small groups and independents, recenters team+conference offense and defense, uses population-SD z-scores, and excludes HFA from the neutral-field composite.

Non-convergence, an empty/invalid graph, unidentified HFA, inconsistent team universes, or a failed composite identity raises a publication-blocking error.

## 5. Weekly temporal behavior

The filtered history is accumulated in the same chronological loop as the legacy histories. Each displayed site week gets a new three-metric fit from games through that week only. Each snapshot computes its own recentering and z-score normalization, so final-season normalization cannot leak backward. Tests isolate the first 2026 site week and reproduce its published snapshot from only that week's rows.

## 6. Model versioning

Each rankings season now carries a `ratingModel` block, and `meta.json` records the model ID by season. The migrated stable ID is `adj-rating-hierarchical-hfa-v1`; the rollback ID is `adj-rating-legacy-srs-ypp-v1`. Metadata includes penalties, HFA settings and fitted values, garbage-time version and exclusion flag, composite version/weights/metrics, normalization, season, final cutoff, refit weeks, input version, convergence iterations, observations, team count and missing-play-row count.

A first migration publish must rebuild the full catalog so every existing season receives explicit metadata. Subsequent `--season` refreshes preserve and validate that catalog.

## 7. Legacy mode

Both `build_real_data.py` and `compile_site_data.py` require an explicit model selection. `--rating-model legacy` continues to use SRS for `adjEM` and the original YardsPerPlay edges for `adjO`/`adjD`. Real 2026 integration tests reproduce every currently published legacy value and rank exactly. The refresh workflow names `hierarchical_hfa` explicitly.

## 8. Tests

`python -m unittest discover -s tests -v` ran **104 tests: 104 passed, 0 failed, 0 errors, 0 skipped** in 164.824 seconds. Migration coverage includes exact 2025 shadow parity below 1e−9, composite identity before and after publication rounding, directionality, 1,616-row filtered input totals, neutral-site H=0, season-specific conference transitions, non-convergence failures, temporal isolation, block-local normalization, legacy reproduction and Advanced equality.

After removing the last implicit Python default, the nine configuration/publication-contract tests passed again. Python compilation passed for every changed rating/build module. `npx tsc --noEmit` passed. `npm run build` passed and generated all 14 Next.js routes. `npm run lint` reported zero errors and two pre-existing warnings in untouched files (`team/[slug]/page.tsx:528` and `lib/supabase/server.ts:13`).

## 9. Pre-publication shadow build

The compiler and exporter now accept explicit shadow destinations. The staged 2025 build is at `/private/tmp/cfb-rating-migration-20260909/`; it contains 24 weekly snapshots, 136 unique final-week FBS teams and 808 games. Validation found no null/non-finite final ratings, duplicate slugs, duplicate IDs, missing ranks or composite-identity failures.

| Rating | Mean absolute rank movement | Maximum |
| --- | ---: | ---: |
| AdjOff | 11.10 | 46 |
| AdjDef | 12.03 | 45 |
| AdjNet | 8.74 | 28 |

The new AdjNet top five are Ohio State, Notre Dame, Texas A&M, Oregon and Miami. Auburn, Arkansas, Louisville and Florida enter the top 25; Penn State, BYU, Illinois and Arizona leave it. These are visibility checks, not evidence for correctness. `live_migration_comparison.csv` contains old/new values and ranks for all 136 teams.

The all-years compiler successfully completed 2014–2024 before a manual interruption during the already separately validated 2025 computation. The focused 2025 build then completed and exported; 2026 is covered by the live integration tests. Seasons 2014–2018 are implementation-tested but remain outside the six-season research-validation set.

## 10. Frontend audit

A disposable Next.js copy served the staged data. `/`, `/team/ohio-state` and `/methodology` returned HTTP 200 with no server errors. The rendered HTML contains AdjNet/AdjOff/AdjDef and the approved definitions. The production build and TypeScript checks pass. Payload checks prove all 136 teams are present once, ranks 1–136 are contiguous and agree with descending values, and AdjNet equals AdjOff+AdjDef.

The ratings table, team history, matchup and this-week consumers continue to use the same public keys, so their sorting and lookup contracts are unchanged. Both frontends were searched for stale SRS/YPP definitions and old visible AdjEM/AdjO/AdjD labels; only deliberate terminology-normalization code still contains those legacy strings.

No controllable browser backend was connected, so a screenshot-based mobile interaction check could not be performed. The request permits payload validation as the fallback; responsive source was unchanged, the staged routes rendered, and the production build passed. This is a documented UI-verification limitation, not a data or build failure.

## 11. Advanced defaults

Verified: `exclude_garbage_time=False` remains the default. The new live ratings path makes exactly one opt-in filtered call; legacy makes none. Comparing hierarchical and legacy builds gives byte-identical Advanced JSON, public team-stats JSON and public weekly team-stats JSON for 2025. The currently published `site/data.js`, `site/advanced-data.js` and `web/public/data/**` remain untouched.

## 12. Pre-ship checklist

| Check | Result |
| --- | --- |
| Full relevant Python suite | PASS — 104/104 |
| Exact validated-shadow parity | PASS — max error <1e−9 |
| Legacy mode | PASS — exact current reproduction |
| Advanced/team-stat isolation | PASS — byte-identical |
| Staged frontend routes/build | PASS |
| Visual mobile browser check | LIMITED — no browser backend connected |
| Teams/ranks/finite values | PASS — 136/136 |
| Model metadata | PASS |
| Published outputs unchanged | PASS |
| `git diff --check` | PASS |
| Commit/push/deploy | NOT PERFORMED |

Source and review files changed:

- `.github/workflows/refresh.yml`
- `scripts/build_real_data.py`
- `scripts/build_shadow_ratings.py`
- `scripts/compile_site_data.py`
- `scripts/export_web_data.py`
- `scripts/report_rating_migration.py`
- `scripts/validate_site_data.py`
- `src/cfb_analytics/analytics/rating_model.py`
- `src/cfb_analytics/analytics/shadow_ratings.py`
- `src/cfb_analytics/derived/games.py`
- `tests/test_publication.py`
- `tests/test_rating_migration.py`
- `tests/test_shadow_ratings.py`
- `web/app/page.tsx`
- `web/app/advanced/page.tsx`
- `web/app/methodology/page.tsx`
- `web/lib/types.ts`
- `site/app.js`
- `site/index.html`
- `site/team.js`
- `site/methodology.html`
- `docs/shadow-ratings/production-audit.md`
- `docs/shadow-ratings/live_migration_comparison.csv`
- `docs/shadow-ratings/live_migration_report.md`

A real first publish would content-change `site/data.js`, `web/public/data/meta.json`, and `web/public/data/rankings/{2014,2015,2016,2017,2018,2019,2021,2022,2023,2024,2025,2026}.json`. The compiler/exporter also rewrites `site/advanced-data.js`, `site/search-index.js`, and the Advanced, team-stats, team-stats-weekly, schedule and search-index JSON outputs, but controlled comparisons show their content remains unchanged outside metadata generated time/version effects. The first publish should use the full-catalog command, not a partial refresh, so every season receives model metadata atomically.

Known accepted model limitations carry forward: Notre Dame is more underpredicted; scoring-margin RMSE worsens on cross-conference games (17.321→17.424) and P4/G5 games (17.289→17.639); aggregate margin evidence is weaker than metric evidence; weeks 1–3 and seasons 2014–2018 were outside the research validation; HFA does not fully remove site residual bias.

Proposed commit message after explicit approval: `Migrate Adj. Net ratings to hierarchical HFA model`

**READY TO PUBLISH**
