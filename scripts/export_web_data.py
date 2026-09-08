"""Validate and export the compiled site datasets for Next.js.

All inputs are validated before any published file is replaced. Metadata is
content-versioned, so unchanged runs do not create meaningless daily commits.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from build_real_data import build_site_week_map
from compile_site_data import read_js_assignment
from validate_site_data import require, validate_season

WEB_DATA = REPO / "web/public/data"


def encode(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _rate(num, den):
    return num / den if den else None


def _schedule_team_maps(year):
    path = REPO / f"data/canonical/season={year}/teams.json"
    if not path.exists():
        return {}, {}
    rows = json.loads(path.read_text())
    fbs = [row for row in rows if str(row.get("classification", "")).lower() == "fbs"]
    by_id = {str(row["team_id"]): row for row in fbs if row.get("team_id") is not None}
    by_name = {str(row["team"]): row for row in fbs if row.get("team")}
    return by_id, by_name


def _resolve_schedule_team(game, side, by_id, by_name):
    team_id = game.get(f"{side}Id")
    if team_id is not None and str(team_id) in by_id:
        return by_id[str(team_id)]
    name = game.get(f"{side}Team")
    if name is not None:
        return by_name.get(str(name))
    return None


def build_schedule_payload(year):
    """Build a small public FBS-vs-FBS schedule from the trusted CFBD refresh.

    Raw source files stay gitignored. This intentionally publishes only the
    fields needed by the fan-facing weekly slate and matchup pages. Site-week
    numbering reuses the same mapping as the ratings pipeline, including GRID's
    Week 0 split and CFBD-backed postseason labels.
    """
    raw_root = REPO / f"data/raw/cfbd/season={year}"
    if not raw_root.exists():
        return None

    by_id, by_name = _schedule_team_maps(year)
    if not by_id and not by_name:
        return None

    source_games = []
    for path in sorted(raw_root.glob("season_type=*/week=*/games.json")):
        payload = json.loads(path.read_text())
        if isinstance(payload, list):
            source_games.extend(game for game in payload if isinstance(game, dict))
    if not source_games:
        return None

    site_week_by_game, _, week_labels = build_site_week_map(year)
    games = []
    for game in source_games:
        game_id = game.get("id")
        if game_id is None:
            continue
        game_id = str(game_id)
        week = site_week_by_game.get(game_id)
        if week is None:
            continue

        home = _resolve_schedule_team(game, "home", by_id, by_name)
        away = _resolve_schedule_team(game, "away", by_id, by_name)
        # The ratings universe is FBS-vs-FBS, so the weekly page uses the same
        # comparison universe rather than mixing unrated FCS opponents into it.
        if home is None or away is None:
            continue

        completed = bool(game.get("completed"))
        start_time_tbd = bool(game.get("startTimeTBD"))
        games.append({
            "gameId": game_id,
            "week": int(week),
            "seasonType": str(game.get("seasonType") or "regular"),
            "startDate": game.get("startDate"),
            "startTimeTBD": start_time_tbd,
            "completed": completed,
            "neutralSite": bool(game.get("neutralSite")),
            "conferenceGame": bool(game.get("conferenceGame")),
            "venue": game.get("venue"),
            "homeTeam": home["team"],
            "homeTeamId": int(home["team_id"]),
            "homeSlug": home["slug"],
            "homeConference": game.get("homeConference"),
            "awayTeam": away["team"],
            "awayTeamId": int(away["team_id"]),
            "awaySlug": away["slug"],
            "awayConference": game.get("awayConference"),
            "homePoints": game.get("homePoints") if completed else None,
            "awayPoints": game.get("awayPoints") if completed else None,
        })

    if not games:
        return None

    # Scheduled games sort by kickoff; games with no confirmed time (TBD, or
    # simply not yet announced) sort after every scheduled game that week.
    games.sort(key=lambda row: (row["week"], bool(row["startTimeTBD"] or not row.get("startDate")), row.get("startDate") or "9999", row["gameId"]))
    by_week = {}
    for game in games:
        by_week.setdefault(str(game["week"]), []).append(game)
    weeks = sorted(int(week) for week in by_week)
    incomplete_weeks = sorted({game["week"] for game in games if not game["completed"]})
    current_week = incomplete_weeks[0] if incomplete_weeks else weeks[-1]

    return {
        "weeks": weeks,
        "weekLabels": {str(week): label for week, label in week_labels.items() if week in weeks},
        "currentWeek": current_week,
        "byWeek": by_week,
    }


def _assign_public_rank(rows, key, out_key, *, higher_better=True):
    ranked = [row for row in rows if row.get(key) is not None]
    ranked.sort(key=lambda row: row[key], reverse=higher_better)
    for index, row in enumerate(ranked, start=1):
        row[out_key] = index
    for row in rows:
        row.setdefault(out_key, None)


def _team_stats_rows_through_week(advanced_payload, upto_week):
    """Cumulative, ranked public team-stat rows using only games through
    upto_week -- shared by the season-to-date payload (upto_week = the final
    week) and the per-week payload (upto_week = each published week), which
    is what makes the per-week version safe to use as a pregame snapshot for
    a game played in a later week: it genuinely stops at upto_week rather
    than re-deriving from the season's current totals.
    """
    snapshots = {row["slug"]: row for row in advanced_payload["byWeek"].get(str(upto_week), [])}
    totals = {}

    for week in advanced_payload["weeks"]:
        if week > upto_week:
            break
        for row in advanced_payload["byWeek"].get(str(week), []):
            slug = row["slug"]
            if slug not in totals:
                totals[slug] = {
                    "team": row["team"],
                    "slug": slug,
                    "teamId": row["teamId"],
                    "conf": row["conf"],
                    "wk": {},
                }
            acc = totals[slug]["wk"]
            for key, value in (row.get("wk") or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    acc[key] = acc.get(key, 0) + value

    rows = []
    for slug, base in totals.items():
        wk = base["wk"]
        snapshot = snapshots.get(slug, {})
        pass_plays = wk.get("dropbacks", 0)
        rush_plays = wk.get("rushAttempts", 0)
        pass_faced = wk.get("dropbacksFaced", 0)
        rush_faced = wk.get("rushAttemptsFaced", 0)
        rows.append({
            "team": base["team"],
            "slug": slug,
            "teamId": base["teamId"],
            "conf": base["conf"],
            "successRate": _rate(wk.get("successNum", 0), wk.get("successDen", 0)),
            "passSuccessRate": _rate(wk.get("passSuccessNum", 0), wk.get("passSuccessDen", 0)),
            "rushSuccessRate": _rate(wk.get("rushSuccessNum", 0), wk.get("rushSuccessDen", 0)),
            "successRateAllowed": _rate(wk.get("successNumA", 0), wk.get("successDenA", 0)),
            "passSuccessRateAllowed": _rate(wk.get("passSuccessNumA", 0), wk.get("passSuccessDenA", 0)),
            "rushSuccessRateAllowed": _rate(wk.get("rushSuccessNumA", 0), wk.get("rushSuccessDenA", 0)),
            "yardsPerPlay": _rate(wk.get("yppNum", 0), wk.get("yppDen", 0)),
            "yardsPerPlayAllowed": _rate(wk.get("yppNumA", 0), wk.get("yppDenA", 0)),
            "explosivePlayRate": _rate(wk.get("explosiveNum", 0), wk.get("explosiveDen", 0)),
            "explosivePlayRateAllowed": _rate(wk.get("explosiveNumA", 0), wk.get("explosiveDenA", 0)),
            "passRate": _rate(pass_plays, pass_plays + rush_plays),
            "passRateAgainst": _rate(pass_faced, pass_faced + rush_faced),
            "pace": _rate(wk.get("offPlays", 0), wk.get("offGames", 0)),
            "fieldPositionEdge": snapshot.get("fieldPos"),
            "fieldPositionRaw": _rate(wk.get("fieldPosSum", 0), wk.get("fieldPosCount", 0)),
            "fieldPositionRawAllowed": _rate(wk.get("fieldPosSumA", 0), wk.get("fieldPosCountA", 0)),
            "finishingRate": _rate(wk.get("finNum", 0), wk.get("finDen", 0)),
            "finishingRateAllowed": _rate(wk.get("finNumA", 0), wk.get("finDenA", 0)),
            "adjustedExplosivenessOffense": snapshot.get("offExp"),
            "adjustedExplosivenessDefense": snapshot.get("defExp"),
            "adjustedFinishingOffense": snapshot.get("offFin"),
            "adjustedFinishingDefense": snapshot.get("defFin"),
        })

    rank_defs = (
        ("successRate", "successRateRank", True),
        ("passSuccessRate", "passSuccessRateRank", True),
        ("rushSuccessRate", "rushSuccessRateRank", True),
        ("successRateAllowed", "successRateAllowedRank", False),
        ("passSuccessRateAllowed", "passSuccessRateAllowedRank", False),
        ("rushSuccessRateAllowed", "rushSuccessRateAllowedRank", False),
        ("yardsPerPlay", "yardsPerPlayRank", True),
        ("yardsPerPlayAllowed", "yardsPerPlayAllowedRank", False),
        ("explosivePlayRate", "explosivePlayRateRank", True),
        ("explosivePlayRateAllowed", "explosivePlayRateAllowedRank", False),
        ("fieldPositionEdge", "fieldPositionEdgeRank", True),
        # Raw field position is yards-to-goal at drive start: lower is a
        # better starting spot for the offense, higher is better forced
        # onto the opponent by the defense -- opposite direction from each
        # other, and opposite the adjusted "edge" framing above.
        ("fieldPositionRaw", "fieldPositionRawRank", False),
        ("fieldPositionRawAllowed", "fieldPositionRawAllowedRank", True),
        ("finishingRate", "finishingRateRank", True),
        ("finishingRateAllowed", "finishingRateAllowedRank", False),
        ("adjustedExplosivenessOffense", "adjustedExplosivenessOffenseRank", True),
        ("adjustedExplosivenessDefense", "adjustedExplosivenessDefenseRank", True),
        ("adjustedFinishingOffense", "adjustedFinishingOffenseRank", True),
        ("adjustedFinishingDefense", "adjustedFinishingDefenseRank", True),
    )
    for key, out_key, higher_better in rank_defs:
        _assign_public_rank(rows, key, out_key, higher_better=higher_better)

    rows.sort(key=lambda row: row["team"])
    return rows


def build_team_stats_payload(advanced_payload):
    """Publish a free season-to-date team profile, not the Pro split builder.

    The private Advanced dataset stores single-week raw counts so arbitrary
    ranges can be rebuilt after entitlement checks. For the public team page we
    collapse those counts into one season-to-date snapshot and expose only a
    deliberate set of core fan-facing metrics.
    """
    weeks = advanced_payload["weeks"]
    if not weeks:
        return None
    final_week = weeks[-1]
    rows = _team_stats_rows_through_week(advanced_payload, final_week)
    if not rows:
        return None
    return {
        "week": final_week,
        "weekLabel": advanced_payload.get("weekLabels", {}).get(str(final_week), f"Week {final_week}"),
        "teams": rows,
    }


def build_team_stats_weekly_payload(advanced_payload):
    """Per-week cumulative team-stat snapshots, shaped like rankings.json
    ({weeks, weekLabels, byWeek}) so matchup/weekly pages can look up a
    team's stats as of the week strictly before a given game -- the same
    pregame-snapshot pattern already used for RPI/RPI-O/RPI-D. Publishing
    only the final week (as build_team_stats_payload does) would leak a
    later week's totals into an earlier game's matchup page once the season
    moves on; this keeps every week's numbers frozen at what was actually
    known through that week.
    """
    weeks = advanced_payload["weeks"]
    if not weeks:
        return None
    by_week = {}
    for week in weeks:
        rows = _team_stats_rows_through_week(advanced_payload, week)
        if rows:
            by_week[str(week)] = rows
    if not by_week:
        return None
    published_weeks = sorted(int(w) for w in by_week)
    return {
        "weeks": published_weeks,
        "weekLabels": {k: v for k, v in advanced_payload.get("weekLabels", {}).items() if int(k) in published_weeks},
        "byWeek": by_week,
    }


def main():
    site = REPO / "site"
    datasets = {}
    for kind, filename, prefix in [("rankings", "data.js", "CFB"), ("advanced", "advanced-data.js", "CFF_ADV")]:
        values = {key: read_js_assignment(site / filename, f"{prefix}_{key}") for key in ("YEARS", "WEEKS", "WEEK_LABELS", "DATA")}
        require(all(v is not None for v in values.values()), f"Missing required assignments in {filename}")
        require(values["YEARS"] == sorted(set(values["YEARS"])) and bool(values["YEARS"]), "Invalid season catalog")
        datasets[kind] = values
    years = datasets["rankings"]["YEARS"]
    require(years == datasets["advanced"]["YEARS"], "Season catalogs differ")
    outputs = {}
    summaries = {}
    search = {}
    schedule_years = []
    for year in years:
        key = str(year)
        payloads = {}
        for kind, data in datasets.items():
            payloads[kind] = {"weeks": data["WEEKS"][key], "weekLabels": data["WEEK_LABELS"].get(key, {}), "byWeek": data["DATA"][key]}
        previous_path = WEB_DATA / "rankings" / f"{key}.json"
        previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
        summaries[key] = validate_season(payloads["rankings"], payloads["advanced"], previous=previous)
        for kind, payload in payloads.items():
            outputs[f"{kind}/{key}.json"] = encode(payload)
        latest = payloads["rankings"]
        for row in latest["byWeek"][str(latest["weeks"][-1])]:
            search[row["slug"]] = {k: row[k] for k in ("team", "slug", "teamId", "conf")}

        public_team_stats = build_team_stats_payload(payloads["advanced"])
        if public_team_stats is not None:
            outputs[f"team-stats/{key}.json"] = encode(public_team_stats)

        team_stats_weekly = build_team_stats_weekly_payload(payloads["advanced"])
        if team_stats_weekly is not None:
            outputs[f"team-stats-weekly/{key}.json"] = encode(team_stats_weekly)

        schedule = build_schedule_payload(year)
        if schedule is not None:
            outputs[f"schedule/{key}.json"] = encode(schedule)
            schedule_years.append(year)

    index = sorted(search.values(), key=lambda row: row["team"])
    outputs["search-index.json"] = encode(index)
    version = hashlib.sha256(encode(outputs).encode()).hexdigest()
    old_meta_path = WEB_DATA / "meta.json"
    old_meta = json.loads(old_meta_path.read_text()) if old_meta_path.exists() else {}
    generated = old_meta.get("generatedAt") if old_meta.get("dataVersion") == version else datetime.now(timezone.utc).isoformat()
    meta = {
        "rankingsYears": years,
        "advancedYears": years,
        "scheduleYears": schedule_years,
        "dataVersion": version,
        "generatedAt": generated,
        "scope": "Completed FBS-vs-FBS games",
        "seasons": summaries,
    }
    for filename, text in outputs.items():
        atomic_write(WEB_DATA / filename, text)
    atomic_write(site / "search-index.js", "window.CFF_SEARCH_INDEX = " + encode(index) + ";\n")
    atomic_write(WEB_DATA / "meta.json", encode(meta))
    print(
        f"Validated and exported {len(years)} seasons; {len(index)} searchable teams; "
        f"{len(schedule_years)} schedule season(s); version {version[:12]}"
    )


if __name__ == "__main__":
    main()
