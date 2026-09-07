import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_real_data import build_year, YEARS
from validate_site_data import validate_season

REPO = Path(__file__).resolve().parent.parent


def assign_rank(rows, key, out_key, reverse=True):
    ranked = [r for r in rows if r.get(key) is not None]
    ranked.sort(key=lambda r: r[key], reverse=reverse)
    for i, r in enumerate(ranked):
        r[out_key] = i + 1
    for r in rows:
        r.setdefault(out_key, None)


def read_js_assignment(path, variable):
    """Read a JSON value assigned as `window.<variable> = ...;` from a site file."""
    if not path.exists():
        return None
    text = path.read_text()
    prefix = f"window.{variable} = "
    start = text.find(prefix)
    if start == -1:
        return None
    start += len(prefix)
    value, _ = json.JSONDecoder().raw_decode(text[start:])
    return value


def load_existing_site_data():
    main_path = REPO / "site/data.js"
    adv_path = REPO / "site/advanced-data.js"
    return (
        read_js_assignment(main_path, "CFB_WEEKS") or {},
        read_js_assignment(main_path, "CFB_DATA") or {},
        read_js_assignment(adv_path, "CFF_ADV_WEEKS") or {},
        read_js_assignment(adv_path, "CFF_ADV_DATA") or {},
        read_js_assignment(main_path, "CFB_WEEK_LABELS") or {},
    )


def build_season_payload(year):
    weeks, week_labels = build_year(year)
    if not weeks:
        return None

    week_nums = sorted(weeks.keys())
    latest_rows = weeks[week_nums[-1]]
    rated_count = sum(1 for r in latest_rows if r.get("cff") is not None)

    # A refresh with teams but zero calculated ratings is not publishable. This
    # is exactly what caused the Sep. 6 refresh to blank the site. Let callers
    # preserve the previously published season instead of shipping nulls.
    if latest_rows and rated_count == 0:
        print(
            f"season {year}: {len(latest_rows)} teams but zero non-null CFF ratings; "
            "refusing to publish this season"
        )
        return None

    season_main = {}
    season_adv = {}
    prev_rank_by_slug = {}

    for wk in week_nums:
        rows = weeks[wk]

        assign_rank(rows, "cff", "rank")
        assign_rank(rows, "offYardsPerPlay", "adjORank")
        assign_rank(rows, "defYardsPerPlay", "adjDRank", reverse=True)
        assign_rank(rows, "sos", "sosRank")
        assign_rank(rows, "sor", "sorRank")

        main_rows = []
        adv_rows = []
        for r in rows:
            rank_change = None
            if (
                r["rank"] is not None
                and r["slug"] in prev_rank_by_slug
                and prev_rank_by_slug[r["slug"]] is not None
            ):
                rank_change = prev_rank_by_slug[r["slug"]] - r["rank"]

            main_rows.append({
                "team": r["team"], "slug": r["slug"], "teamId": r["teamId"], "conf": r["conf"],
                "record": r["record"], "rank": r["rank"],
                "adjEM": r["cff"], "adjO": r["offYardsPerPlay"], "adjD": r["defYardsPerPlay"],
                "adjORank": r["adjORank"], "adjDRank": r["adjDRank"],
                "sos": r["sos"], "sosRank": r["sosRank"],
                "sor": r["sor"], "sorRank": r["sorRank"],
                "rankChange": rank_change,
            })

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
        season_main[str(wk)] = main_rows
        season_adv[str(wk)] = adv_rows

    print(
        f"season {year}: weeks {week_nums[0]}-{week_nums[-1]}, "
        f"{len(latest_rows)} teams, {rated_count} rated in final week"
    )
    return week_nums, season_main, season_adv, week_labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--season",
        type=int,
        help="Refresh only this season and preserve all other published seasons.",
    )
    args = parser.parse_args()

    if args.season:
        main_weeks, main_data, adv_weeks, adv_data, week_labels = load_existing_site_data()
        target_years = [args.season]
    else:
        main_weeks, main_data, adv_weeks, adv_data, week_labels = {}, {}, {}, {}, {}
        target_years = YEARS

    for year in target_years:
        built = build_season_payload(year)
        key = str(year)
        if built is None:
            raise RuntimeError(f"season {year}: no valid ratings payload available")

        week_nums, season_main, season_adv, season_week_labels = built
        validate_season(
            {"weeks": week_nums, "byWeek": season_main},
            {"weeks": week_nums, "byWeek": season_adv},
            previous={"weeks": main_weeks[key], "byWeek": main_data[key]} if key in main_data else None,
        )
        main_weeks[key] = week_nums
        adv_weeks[key] = week_nums
        main_data[key] = season_main
        adv_data[key] = season_adv
        week_labels[key] = season_week_labels

    published_years = sorted(int(y) for y in main_data.keys())
    published_adv_years = sorted(int(y) for y in adv_data.keys())

    js = (
        "// REAL data. Team identity, records, and per-game stats are sourced from\n"
        "// data/canonical/season=<year>/team_games.json (CFBD-derived, locked metrics).\n"
        "// AdjEM/CFF is the site's own opponent-adjusted Simple Rating System (SRS),\n"
        "// computed through each published week (no later-week games included).\n"
        "// AdjO/AdjD are a schedule-adjusted yards-per-play edge from a RESEARCH-ONLY\n"
        "// model -- independently validated in the source repo but not yet the locked\n"
        "// production rating. SOR (Strength of Record, sor-v1-wins-above-average)\n"
        "// is wins above what an exactly-average FBS team would be expected to\n"
        "// get on that same schedule -- see scripts/build_real_data.py for the\n"
        "// full derivation. It answers a different question than AdjEM: résumé\n"
        "// (won/lost, given the schedule) rather than performance strength.\n"
        "// Postseason site-weeks are grouped by CFBD's own playoff round field\n"
        "// (not by date gaps), so e.g. \"Week 17\" for a finished season is really\n"
        "// one of Bowl Season / CFP First Round / Quarterfinal / Semifinal /\n"
        "// National Championship -- see CFB_WEEK_LABELS for the human label.\n"
        "window.CFB_YEARS = " + json.dumps(published_years) + ";\n"
        "window.CFB_WEEKS = " + json.dumps(main_weeks) + ";\n"
        "window.CFB_WEEK_LABELS = " + json.dumps(week_labels) + ";\n"
        "window.CFB_DATA = " + json.dumps(main_data, separators=(",", ":"), allow_nan=False) + ";\n"
    )
    (REPO / "site/data.js").write_text(js)

    adv_js = (
        "// REAL data -- see data.js header for methodology and validation notes.\n"
        "// Snapshot model fields reflect the selected end week; `wk` contains the\n"
        "// single-week raw counts used for genuinely rangeable Advanced metrics.\n"
        "// CFF_ADV_WEEK_LABELS names postseason weeks (see data.js's CFB_WEEK_LABELS).\n"
        "window.CFF_ADV_YEARS = " + json.dumps(published_adv_years) + ";\n"
        "window.CFF_ADV_WEEKS = " + json.dumps(adv_weeks) + ";\n"
        "window.CFF_ADV_WEEK_LABELS = " + json.dumps(week_labels) + ";\n"
        "window.CFF_ADV_DATA = " + json.dumps(adv_data, separators=(",", ":"), allow_nan=False) + ";\n"
    )
    (REPO / "site/advanced-data.js").write_text(adv_js)

    print("wrote site/data.js and site/advanced-data.js")


if __name__ == "__main__":
    main()
