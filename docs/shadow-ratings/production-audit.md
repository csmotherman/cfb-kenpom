# Production pipeline audit (before solver implementation)

The current published-field contract differs fundamentally from the research composite. `scripts/build_real_data.py::build_year` assigns SRS to `cff`, and the legacy YardsPerPlay offense/defense edges to `offYardsPerPlay`/`defYardsPerPlay`. `scripts/compile_site_data.py::build_season_payload` maps these to `adjEM`/`adjO`/`adjD`. `web/app/page.tsx` labels them AdjNet/AdjOff/AdjDef. There is no EPA/Success/Explosiveness composite in that path. Current AdjNet is not AdjOff + AdjDef.

## Exact calculation path

CFBD raw `data/raw/cfbd/season=*/season_type=*/week=*/plays.json` → `canonical/materialize.py::materialize_partition` (`normalize_play`, yardage corrections) → processed canonical plays → `derived/games.py::derive_team_games`, `_metric_counts`, `_metric_fields` → locked derived team-game metrics → `canonical/team_games.py::build_team_games` plus season-specific source-game identities → `data/canonical/season=*/team_games.json`.

`build_year` reloads authoritative source games, keeps completed games, re-enriches identity/site metadata, validates team-game integrity, assigns date/round-derived site weeks, and fits accumulated FBS-vs-FBS rows through each displayed week. Non-FBS opponents remain in records/raw counters but not the rating graph. `fit_all_ratings` uses the unchanged legacy solver; `fit_srs` independently fits scoring margin. The main published values are rounded to 3 decimals for yards/play and 2 decimals for SRS, then ranked descending.

`compile_site_data.py` writes `site/data.js`; `export_web_data.py` converts `CFB_DATA` to `web/public/data/rankings/<year>.json`; `web/lib/data.ts::getRankingsSeason` fetches that static JSON. The main ratings path has no database or premium API transformation. The refresh workflow separately publishes advanced/prediction data to premium storage, but that is not the source of these three main fields. This audit describes checked-in code and locally available publication artifacts; a remote live deployment is not assumed to equal this checkout.

## Reconciliation table

| Component | Production | Research study | Match? | Action required |
| --- | --- | --- | --- | --- |
| Garbage time | No garbage-time exclusion in `_metric_counts` | Heuristic filter before classifiers | No | Preserve production inputs in shadow; attribute this difference explicitly |
| FBS filter | Only FBS/FBS enters metric_history and SRS | FBS/FBS only | Yes | Assert closed graph |
| Aggregation | One team/game, complete source games, re-enriched identities | Cached team/game aggregations of filtered canonical plays | Grain only | Compare keys and counts, not just averages |
| EPA | CFBD PPA clean-play gate **plus** derived `_family` rush/pass gate | Same classifier, without additional `_family` gate | No | Separate family-gate effect from garbage exclusion |
| Success | Clean snaps; 50%/70%/100% by down | Same classifier after garbage filter | Definition yes, population no | Do not change thresholds |
| Explosiveness | `Explosive` solver uses explosive-play rate (rush≥10/pass≥20) | `Explosiveness` uses yards per successful play | No | New shadow spec must be named distinctly; never replace `Explosive` |
| Denominators | EPA eligible family snaps, Success eligible snaps; Explosive eligible snaps | EPA eligible snaps, Success eligible snaps; **successful snaps** for Explosiveness | Partial | Audit per-team/game numerators and denominators |
| Weighting | Eligible denominators in legacy fitting | Eligible denominators in ridge/hierarchy | Form yes | Preserve metric-specific weights |
| Adjustment | Legacy λ=50, fixed μ, no site/group term | Free μ, team=200, conference=400, free h | Intentional change | Separate opt-in solver; preserve legacy exactly |
| Defense sign | Higher positive fitted defense is better | Same | Yes | Test formula and output sign |
| Normalization | Main AdjO/AdjD are raw yards/play edges; no SD normalization | Population-SD z-scores per metric and side | No | Explicit shadow composite only |
| Composite | Main AdjNet=SRS; no supplied composite weights | Fixed 6.8693/1.7265/−0.1906; net=sum | No | Requires a reviewed publication-contract migration, not a solver toggle |
| Raw blends | Advanced EPA/Success mix raw deviation and fitted edge through 5 games | No blend in composite | No | Do not reuse advanced blended fields for neutral-field composite |
| Team universe | FBS/FBS graph, per-metric eligible teams; main display includes FBS record rows | Shared observed FBS universe across metrics | Needs numeric check | Enforce a common shadow universe and audit early missing metrics |
| Temporal cutoff | Main site snapshots through site week; postseason split into rounds | Forecast before CFBD week; postseason one block | No | Match full season for reproduction; never score forecasts using through-week snapshots |
| Conference/site | Correct-season source game metadata; neutralSite converted to bool | Cached same fields | Expected | Check raw boolean availability, paired consistency, historical transitions |
| Published fields | adjO/adjD=YPP edges; adjEM=SRS | AdjOff/AdjDef=three-metric composites; AdjNet=sum | No | Label comparisons as different scales, with rank movement only |

The shadow implementation will leave all current producers/consumers unchanged. Same-input solver parity can establish implementation correctness, but cannot by itself establish that the existing production input population reproduces the validated study. If the actual-input shadow diverges materially, the historical-production replay gate remains closed and the final status must not be READY TO SHIP.
