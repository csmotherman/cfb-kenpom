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
    snapshots = {row["slug"]: row for row in advanced_payload["byWeek"].get(str(final_week), [])}
    totals = {}

    for week in weeks:
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
        ("adjustedExplosivenessOffense", "adjustedExplosivenessOffenseRank", True),
        ("adjustedExplosivenessDefense", "adjustedExplosivenessDefenseRank", True),
        ("adjustedFinishingOffense", "adjustedFinishingOffenseRank", True),
        ("adjustedFinishingDefense", "adjustedFinishingDefenseRank", True),
    )
    for key, out_key, higher_better in rank_defs:
        _assign_public_rank(rows, key, out_key, higher_better=higher_better)

    rows.sort(key=lambda row: row["team"])
    return {
        "week": final_week,
        "weekLabel": advanced_payload.get("weekLabels", {}).get(str(final_week), f"Week {final_week}"),
        "teams": rows,
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
