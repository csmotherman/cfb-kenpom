"""Audit CFBD advanced-stats coverage across every completed 2026 team-game.

Two things, both requested after the Alabama/Kentucky (game 401856674)
production blanks investigation:

1. Reconcile /stats/game/advanced vs /game/box/advanced for every concept
   both endpoints publish: coverage rate, null rate, and numeric agreement.
   This is what justified /stats/game/advanced as primary with /game/box/
   advanced as fallback (not the reverse) in export_team_game_advanced.py.

2. SOURCE NULL vs PIPELINE NULL for every displayed advanced field:
   - SOURCE NULL: neither CFBD endpoint has the value (or, for PRIME-only
     fields, PRIME's own PBP pipeline genuinely has nothing for this
     team-game).
   - PIPELINE NULL: at least one CFBD source has the value but the
     exported site JSON does not. Target is 0; any nonzero count here is a
     real bug, not a source gap, and is printed with example game IDs.

Read-only: makes no CFBD API calls, does not modify data/raw, data/canonical,
or web/public/data. Run scripts/export_team_game_advanced.py first if you
want the audit to reflect a fresh export.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from cfb_analytics.canonical.cfbd_advanced import (  # noqa: E402
    load_game_box_advanced_season,
    load_stats_game_advanced_season,
)

import export_team_game_advanced as exporter  # noqa: E402

SEASON = 2026
OUT_DIR = REPO / "data/audits/cfbd_advanced_coverage"

# (site field, CFBD-populated predicate over (cfbd_stats, cfbd_box), PRIME-only?)
# CFBD-populated predicate returns True iff at least one accepted CFBD
# source actually has this concept for this team-game.
def _cfbd_has(*keys):
    def check(cfbd_stats, cfbd_box):
        return any((cfbd_stats or {}).get(k) is not None for k in keys[0]) or \
            any((cfbd_box or {}).get(k) is not None for k in keys[1])
    return check


FIELD_SPECS = [
    ("ppa_per_play", _cfbd_has(["offense_ppa_per_play"], ["box_ppa_per_play"]), False),
    ("total_ppa", _cfbd_has(["offense_total_ppa"], ["box_total_ppa"]), False),
    ("success_rate", _cfbd_has(["offense_success_rate"], ["box_success_rate"]), False),
    ("passing_total_ppa", _cfbd_has(["offense_passing_total_ppa"], ["box_passing_total_ppa"]), False),
    ("passing_ppa_per_play", _cfbd_has(["offense_passing_ppa_per_play"], ["box_passing_ppa_per_play"]), False),
    ("pass_success_rate", _cfbd_has(["offense_passing_success_rate"], []), False),
    ("rushing_total_ppa", _cfbd_has(["offense_rushing_total_ppa"], ["box_rushing_total_ppa"]), False),
    ("rushing_ppa_per_play", _cfbd_has(["offense_rushing_ppa_per_play"], ["box_rushing_ppa_per_play"]), False),
    ("rush_success_rate", _cfbd_has(["offense_rushing_success_rate"], []), False),
    ("stuff_rate", _cfbd_has(["offense_stuff_rate"], ["box_stuff_rate"]), False),
    ("power_success", _cfbd_has(["offense_power_success"], ["box_power_success"]), False),
    ("line_yards_per_play", _cfbd_has(["offense_line_yards_per_play"], ["box_line_yards_per_play"]), False),
    ("second_level_yards_per_play", _cfbd_has(["offense_second_level_yards_per_play"], ["box_second_level_yards_per_play"]), False),
    ("open_field_yards_per_play", _cfbd_has(["offense_open_field_yards_per_play"], ["box_open_field_yards_per_play"]), False),
    ("cfbd_explosiveness", _cfbd_has(["offense_explosiveness"], ["box_explosiveness"]), False),
    ("offensive_drives", _cfbd_has(["offense_drives"], []), False),
    ("avg_start_yards_to_goal", _cfbd_has([], ["average_start_yards_to_goal"]), False),
    ("scoring_opportunities", _cfbd_has([], ["scoring_opportunities"]), False),
    ("points_per_opportunity", _cfbd_has([], ["points_per_scoring_opportunity"]), False),
    ("havoc_allowed", _cfbd_has([], ["havoc_allowed"]), False),
    ("havoc_forced", _cfbd_has([], ["havoc_forced"]), False),
    # PRIME-only: "CFBD populated" is meaningless; track PRIME's own
    # pipeline output directly instead (see main()).
    ("down1_ppa_per_play", None, True),
    ("down2_ppa_per_play", None, True),
    ("down3_ppa_per_play", None, True),
    ("ppa_per_play_without_explosives", None, True),
    ("explosive_dependency", None, True),
    ("series_conversion_rate", None, True),
    ("recovery_rate", None, True),
    ("clean_drive_rate", None, True),
    ("drive_killer_rate", None, True),
    ("failure_rate", None, True),
]

# Dual-source reconciliation: (label, stats-side key, box-side key).
RECONCILE_PAIRS = [
    ("PPA/play", "offense_ppa_per_play", "box_ppa_per_play"),
    ("Total PPA", "offense_total_ppa", "box_total_ppa"),
    ("Passing PPA (total)", "offense_passing_total_ppa", "box_passing_total_ppa"),
    ("Rushing PPA (total)", "offense_rushing_total_ppa", "box_rushing_total_ppa"),
    ("Success Rate", "offense_success_rate", "box_success_rate"),
    ("Explosiveness", "offense_explosiveness", "box_explosiveness"),
    ("Stuff Rate", "offense_stuff_rate", "box_stuff_rate"),
    ("Power Success", "offense_power_success", "box_power_success"),
    ("Line Yards/play", "offense_line_yards_per_play", "box_line_yards_per_play"),
    ("2nd-Level Yards/play", "offense_second_level_yards_per_play", "box_second_level_yards_per_play"),
    ("Open-Field Yards/play", "offense_open_field_yards_per_play", "box_open_field_yards_per_play"),
]


def reconcile_endpoints(cfbd_stats_all, cfbd_box_all):
    print("\n=== ENDPOINT RECONCILIATION: /stats/game/advanced vs /game/box/advanced ===")
    keys = sorted(set(cfbd_stats_all) | set(cfbd_box_all))
    print(f"team-games with either source present: {len(keys)}")
    results = {}
    for label, stats_key, box_key in RECONCILE_PAIRS:
        stats_n = box_n = both_n = 0
        diffs = []
        for key in keys:
            sv = (cfbd_stats_all.get(key) or {}).get(stats_key)
            bv = (cfbd_box_all.get(key) or {}).get(box_key)
            if sv is not None:
                stats_n += 1
            if bv is not None:
                box_n += 1
            if sv is not None and bv is not None:
                both_n += 1
                diffs.append(bv - sv)
        row = {
            "stats_game_advanced_coverage": stats_n,
            "game_box_advanced_coverage": box_n,
            "both_present": both_n,
        }
        if diffs:
            row["mean_abs_diff"] = statistics.fmean(abs(d) for d in diffs)
            row["mean_signed_diff"] = statistics.fmean(diffs)
            row["max_abs_diff"] = max(diffs, key=abs)
        results[label] = row
        diff_str = f"mean|diff|={row.get('mean_abs_diff', 0):.4f}" if diffs else "n/a"
        print(
            f"  {label:24s} stats={stats_n:4d}/{len(keys)}  box={box_n:4d}/{len(keys)}  "
            f"both={both_n:4d}  {diff_str}"
        )
    return results


def audit_coverage(rows, cfbd_stats_all, cfbd_box_all):
    print("\n=== SOURCE NULL vs PIPELINE NULL (2026, every completed team-game) ===")
    print(f"{'Field':32s} {'Eligible':>9s} {'CFBD/PRIME pop':>15s} {'Site pop':>9s} {'Source-null':>12s} {'Pipeline loss':>14s}")
    coverage_table = {}
    pipeline_loss_examples = defaultdict(list)
    for field, cfbd_predicate, is_prime_only in FIELD_SPECS:
        eligible = len(rows)
        cfbd_populated = 0
        site_populated = 0
        pipeline_loss = 0
        source_null = 0
        for row in rows:
            key = (row["game_id"], row["team"])
            site_value = row.get(field)
            if is_prime_only:
                # For PRIME-only fields, "source" is PRIME's own PBP pipeline;
                # there is no independent CFBD signal to check against, so
                # source-populated == site-populated by construction and
                # pipeline loss is always 0 for these by definition. Reported
                # for completeness, not as a pipeline-loss check.
                if site_value is not None:
                    cfbd_populated += 1
                    site_populated += 1
                else:
                    source_null += 1
                continue
            cfbd_stats = cfbd_stats_all.get(key)
            cfbd_box = cfbd_box_all.get(key)
            has_cfbd = cfbd_predicate(cfbd_stats, cfbd_box)
            if has_cfbd:
                cfbd_populated += 1
            else:
                source_null += 1
            if site_value is not None:
                site_populated += 1
            if has_cfbd and site_value is None:
                pipeline_loss += 1
                if len(pipeline_loss_examples[field]) < 5:
                    pipeline_loss_examples[field].append(key)
        coverage_table[field] = {
            "eligible": eligible,
            "cfbd_populated": cfbd_populated,
            "site_populated": site_populated,
            "source_null": source_null,
            "pipeline_loss": pipeline_loss,
        }
        flag = "  <-- INVESTIGATE" if pipeline_loss else ""
        print(
            f"{field:32s} {eligible:9d} {cfbd_populated:15d} {site_populated:9d} "
            f"{source_null:12d} {pipeline_loss:14d}{flag}"
        )
    return coverage_table, pipeline_loss_examples


def main() -> None:
    canon = exporter.load_canonical_season(SEASON)
    exp = exporter.load_exploratory_season(SEASON)
    box = exporter.load_box_score_season(SEASON)
    cfbd_stats_all = load_stats_game_advanced_season(REPO / "data/raw", SEASON)
    cfbd_box_all = load_game_box_advanced_season(REPO / "data/raw", SEASON)

    rows = [
        exporter.build_row(SEASON, canon_row, exp.get(key), box.get(key), cfbd_stats_all.get(key), cfbd_box_all.get(key))
        for key, canon_row in canon.items()
    ]
    print(f"Total team-game rows: {len(rows)}")

    reconciliation = reconcile_endpoints(cfbd_stats_all, cfbd_box_all)
    coverage_table, pipeline_loss_examples = audit_coverage(rows, cfbd_stats_all, cfbd_box_all)

    total_pipeline_loss = sum(v["pipeline_loss"] for v in coverage_table.values())
    print(f"\nTOTAL PIPELINE LOSS (target 0): {total_pipeline_loss}")
    if pipeline_loss_examples:
        print("Examples (field: [(game_id, team), ...]):")
        for field, examples in pipeline_loss_examples.items():
            print(f"  {field}: {examples}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{SEASON}_summary.json").write_text(json.dumps({
        "season": SEASON,
        "teamGames": len(rows),
        "endpointReconciliation": reconciliation,
        "fieldCoverage": coverage_table,
        "pipelineLossExamples": {k: [list(x) for x in v] for k, v in pipeline_loss_examples.items()},
        "totalPipelineLoss": total_pipeline_loss,
    }, indent=2, sort_keys=True))
    print(f"\nWrote {OUT_DIR / f'{SEASON}_summary.json'}")


if __name__ == "__main__":
    main()
