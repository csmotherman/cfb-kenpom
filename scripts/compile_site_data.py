import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_real_data import build_year, YEARS

REPO = Path(__file__).resolve().parent.parent


def assign_rank(rows, key, out_key, reverse=True):
    ranked = [r for r in rows if r.get(key) is not None]
    ranked.sort(key=lambda r: r[key], reverse=reverse)
    for i, r in enumerate(ranked):
        r[out_key] = i + 1
    for r in rows:
        r.setdefault(out_key, None)


def main():
    main_data = {}   # CFB_DATA
    main_weeks = {}  # CFB_WEEKS
    adv_data = {}    # CFF_ADV_DATA
    adv_weeks = {}   # CFF_ADV_WEEKS

    for year in YEARS:
        weeks = build_year(year)
        if not weeks:
            print(f"season {year}: no data, skipping")
            continue

        week_nums = sorted(weeks.keys())
        main_weeks[str(year)] = week_nums
        adv_weeks[str(year)] = week_nums

        main_data[str(year)] = {}
        adv_data[str(year)] = {}

        prev_rank_by_slug = {}

        for wk in week_nums:
            rows = weeks[wk]

            assign_rank(rows, "cff", "rank")
            assign_rank(rows, "offYardsPerPlay", "adjORank")
            assign_rank(rows, "defYardsPerPlay", "adjDRank", reverse=True)  # higher = better defense (model convention)
            assign_rank(rows, "sos", "sosRank")

            main_rows = []
            adv_rows = []
            for r in rows:
                rank_change = None
                if r["rank"] is not None and r["slug"] in prev_rank_by_slug and prev_rank_by_slug[r["slug"]] is not None:
                    rank_change = prev_rank_by_slug[r["slug"]] - r["rank"]

                main_rows.append({
                    "team": r["team"], "slug": r["slug"], "teamId": r["teamId"], "conf": r["conf"],
                    "record": r["record"], "rank": r["rank"],
                    "adjEM": r["cff"], "adjO": r["offYardsPerPlay"], "adjD": r["defYardsPerPlay"],
                    "adjORank": r["adjORank"], "adjDRank": r["adjDRank"],
                    "sos": r["sos"], "sosRank": r["sosRank"],
                    "sor": None, "sorRank": None,
                    "rankChange": rank_change,
                })

                # Advanced Analytics: snapshot (model, "as of this week") fields
                # plus this week's own incremental raw counts (for correct
                # client-side range summation over [start,end]).
                adv_rows.append({
                    "team": r["team"], "slug": r["slug"], "teamId": r["teamId"], "conf": r["conf"],
                    "cff": r["cff"], "fieldPos": r["fieldPos"],
                    "off": r["off"], "def": r["def"],
                    "offExp": r["offExp"], "defExp": r["defExp"],
                    "offFin": r["offFin"], "defFin": r["defFin"],
                    "wk": r["wk"],
                })

                prev_rank_by_slug[r["slug"]] = r["rank"]

            main_rows.sort(key=lambda r: (r["rank"] is None, r["rank"]))

            main_data[str(year)][str(wk)] = main_rows
            adv_data[str(year)][str(wk)] = adv_rows

        print(f"season {year}: weeks {week_nums[0]}-{week_nums[-1]}, {len(weeks[week_nums[-1]])} teams in final week")

    # ---- write data.js ----
    js = (
        "// REAL data. Team identity, records, and per-game stats are sourced from\n"
        "// data/canonical/season=<year>/team_games.json (CFBD-derived, locked metrics).\n"
        "// AdjEM/CFF is the site's own opponent-adjusted Simple Rating System (SRS),\n"
        "// computed walk-forward (each week uses only games played before it).\n"
        "// AdjO/AdjD are a schedule-adjusted yards-per-play edge from a RESEARCH-ONLY\n"
        "// model -- independently validated in the source repo (6-12% MAE improvement\n"
        "// over naive baselines on 2025 and 2018 held-out weeks) but not a locked\n"
        "// production rating.\n"
        "// SOR has no defined methodology and is intentionally left null rather than\n"
        "// invented. Values are null wherever a team has not yet played enough games\n"
        "// for that computation -- not a bug.\n"
        "window.CFB_YEARS = " + json.dumps(YEARS) + ";\n"
        "window.CFB_WEEKS = " + json.dumps(main_weeks) + ";\n"
        "window.CFB_DATA = " + json.dumps(main_data, separators=(",", ":")) + ";\n"
    )
    with open(REPO / "site/data.js", "w") as f:
        f.write(js)

    adv_js = (
        "// REAL data -- see data.js header for methodology and validation notes.\n"
        "// Each entry has snapshot fields (cff/fieldPos/off/def/offExp/defExp/\n"
        "// offFin/defFin) from the walk-forward research model -- these reflect\n"
        "// the END of whatever week range is selected, since a model fit can't be\n"
        "// algebraically split into a sub-range. `wk` holds this single week's own\n"
        "// raw counts (wins/losses, success/pass/rush counts, plays, opponent SRS)\n"
        "// which the page sums across the selected range for genuinely rangeable\n"
        "// stats (Success/Pass/Run rates, Pace, SOS, record). Pace is real\n"
        "// (plays per game); Special Teams (st) has no real source and is\n"
        "// intentionally left out.\n"
        "window.CFF_ADV_YEARS = " + json.dumps(YEARS) + ";\n"
        "window.CFF_ADV_WEEKS = " + json.dumps(adv_weeks) + ";\n"
        "window.CFF_ADV_DATA = " + json.dumps(adv_data, separators=(",", ":")) + ";\n"
    )
    with open(REPO / "site/advanced-data.js", "w") as f:
        f.write(adv_js)

    print("wrote site/data.js and site/advanced-data.js")


if __name__ == "__main__":
    main()
