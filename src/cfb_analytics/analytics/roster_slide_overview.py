from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from cfb_analytics.analytics.returning_ppa import build_returning_ppa_report
from cfb_analytics.sources.cfbd.client import CfbdClient


DEFAULT_TEAM = "Western Michigan"
DEFAULT_SEASON = 2026
DEFAULT_ROSTER_URL_TEMPLATE = "https://wmubroncos.com/sports/football/roster/{year}"

OFFENSE_GROUPS = {"QB", "RB", "WR", "TE", "OL"}
DEFENSE_GROUPS = {"DL", "LB", "DB"}


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._cell_parts is not None and self._row is not None:
            text = " ".join(" ".join(self._cell_parts).split())
            self._row.append(text)
            self._cell_parts = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z]+", "", value.lower())


def _position_group(position: Any) -> str:
    pos = str(position or "").upper().strip()
    if pos == "QB":
        return "QB"
    if pos in {"RB", "HB", "FB"}:
        return "RB"
    if pos in {"WR", "SB"}:
        return "WR"
    if pos == "TE":
        return "TE"
    if pos in {"OL", "OT", "T", "OG", "G", "C", "OC", "IOL"}:
        return "OL"
    if pos in {"DL", "DE", "DT", "NT", "EDGE"}:
        return "DL"
    if pos in {"LB", "ILB", "OLB"}:
        return "LB"
    if pos in {"DB", "CB", "S", "FS", "SS", "NB"}:
        return "DB"
    if pos in {"K", "PK", "P", "LS"}:
        return "ST"
    return "OTHER"


def _side(group: str) -> str:
    if group in OFFENSE_GROUPS:
        return "Offense"
    if group in DEFENSE_GROUPS:
        return "Defense"
    if group == "ST":
        return "Special Teams"
    return "Other"


def _class_label(value: str) -> str:
    raw = value.strip()
    mapping = {
        "Fr.": "Freshman",
        "R-Fr.": "Redshirt Freshman",
        "So.": "Sophomore",
        "R-So.": "Redshirt Sophomore",
        "Jr.": "Junior",
        "R-Jr.": "Redshirt Junior",
        "Sr.": "Senior",
        "R-Sr.": "Redshirt Senior",
        "Gr.": "Graduate",
        "Grad.": "Graduate",
    }
    return mapping.get(raw, raw or "Unknown")


def _eligibility_bucket(class_label: str) -> str:
    if class_label in {"Freshman", "Redshirt Freshman"}:
        return "Freshman eligibility"
    if class_label in {"Sophomore", "Redshirt Sophomore"}:
        return "Sophomore eligibility"
    if class_label in {"Junior", "Redshirt Junior"}:
        return "Junior eligibility"
    if class_label in {"Senior", "Redshirt Senior", "Graduate"}:
        return "Senior / Graduate"
    return "Unknown"


def _height_inches(value: str) -> float | None:
    text = value.strip()
    match = re.search(r"(\d+)\s*[-'′]\s*(\d+)", text)
    if not match:
        return None
    return 12 * int(match.group(1)) + int(match.group(2))


def _weight(value: str) -> float | None:
    match = re.search(r"\d+", value or "")
    return float(match.group()) if match else None


def _share(count: int, total: int) -> float | None:
    return count / total if total else None


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def parse_official_roster_html(
    html: str,
    *,
    required: set[str] | None = None,
    header_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Parse an official-site roster table.

    Some athletics sites (e.g. wmubroncos.com) publish a "Previous School"
    column that makes transfer/newcomer classification straightforward.
    Others (e.g. mgoblue.com) publish only Name/Pos./Ht./Wt./Yr., with no
    transfer-origin column at all. `required` and `header_aliases` let a
    caller parse the latter shape (e.g. required={"name","pos","yr","ht","wt"},
    header_aliases={"yr": "class"}) without weakening the default, fully
    audited wmubroncos-style path used elsewhere.
    """
    required = required or {"name", "pos", "class", "ht", "wt", "previousschool"}
    header_aliases = header_aliases or {}
    parser = _TableParser()
    parser.feed(html)

    for table in parser.tables:
        if len(table) < 2:
            continue
        header = [header_aliases.get(_header_key(value), _header_key(value)) for value in table[0]]
        if not required.issubset(set(header)):
            continue

        indexes = {key: header.index(key) for key in required}
        previous_school_idx = header.index("previousschool") if "previousschool" in header else None
        number_idx = header.index("number") if "number" in header else 0
        rows: list[dict[str, Any]] = []
        for cells in table[1:]:
            if len(cells) <= max(indexes.values()):
                continue
            name = cells[indexes["name"]].strip()
            if not name or _header_key(name) == "name":
                continue
            position = cells[indexes["pos"]].strip()
            raw_class = cells[indexes["class"]].strip()
            height = cells[indexes["ht"]].strip()
            weight = cells[indexes["wt"]].strip()
            previous_school = cells[previous_school_idx].strip() if previous_school_idx is not None and previous_school_idx < len(cells) else ""
            number = cells[number_idx].strip() if number_idx < len(cells) else ""
            group = _position_group(position)
            label = _class_label(raw_class)
            rows.append(
                {
                    "number": number,
                    "name": name,
                    "position": position,
                    "positionGroup": group,
                    "side": _side(group),
                    "classRaw": raw_class,
                    "classLabel": label,
                    "eligibilityBucket": _eligibility_bucket(label),
                    "height": height,
                    "heightInches": _height_inches(height),
                    "weight": weight,
                    "weightPounds": _weight(weight),
                    "previousSchool": previous_school or None,
                }
            )
        if rows:
            return rows

    raise RuntimeError("Could not find an official roster table with Name/Pos./Class/Ht./Wt./Previous School columns.")


def fetch_official_roster(
    url: str,
    *,
    required: set[str] | None = None,
    header_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    response = httpx.get(
        url,
        timeout=60.0,
        follow_redirects=True,
        headers={"User-Agent": "cfb-analytics-roster-audit/1.0"},
    )
    response.raise_for_status()
    rows = parse_official_roster_html(response.text, required=required, header_aliases=header_aliases)
    names = [_norm(row["name"]) for row in rows]
    if len(rows) < 40:
        raise RuntimeError(f"Official roster parse returned only {len(rows)} rows from {url}; refusing to publish.")
    if len(set(names)) != len(names):
        duplicates = [name for name, count in Counter(names).items() if count > 1]
        raise RuntimeError(f"Duplicate player names in parsed official roster: {duplicates}")
    return rows


def classify_roster_sources(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    older: list[dict[str, Any]],
    *,
    previous_school_available: bool = True,
) -> list[dict[str, Any]]:
    """Classify each current-roster player by where they came from.

    `previous_school_available` must be set False for official roster pages
    that don't publish a "Previous School" column (e.g. mgoblue.com). In that
    case a non-returning, non-rejoining player can't be reliably split into
    college_newcomer vs. first_time_college -- rather than guessing, they are
    labeled "newcomer_unclassified" so the gap is visible in the output
    instead of silently defaulting to "first_time_college".
    """
    previous_names = {_norm(row["name"]) for row in previous}
    older_names = {_norm(row["name"]) for row in older}

    classified: list[dict[str, Any]] = []
    for row in current:
        key = _norm(row["name"])
        if key in previous_names:
            source = "returning_2025"
        elif key in older_names:
            source = "rejoining_program"
        elif not previous_school_available:
            source = "newcomer_unclassified"
        elif row.get("previousSchool"):
            source = "college_newcomer"
        else:
            source = "first_time_college"
        classified.append({**row, "rosterSource": source})
    return classified


def _size_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[row["positionGroup"]].append(row)

    def summarize(group_rows: list[dict[str, Any]]) -> dict[str, Any]:
        heights = [float(row["heightInches"]) for row in group_rows if isinstance(row.get("heightInches"), (int, float))]
        weights = [float(row["weightPounds"]) for row in group_rows if isinstance(row.get("weightPounds"), (int, float))]
        return {
            "players": len(group_rows),
            "averageHeightInches": sum(heights) / len(heights) if heights else None,
            "averageWeightPounds": sum(weights) / len(weights) if weights else None,
        }

    return {group: summarize(group_rows) for group, group_rows in sorted(by_group.items())}


def _signed_and_positive_ppa(players: list[dict[str, Any]], value_key: str) -> dict[str, Any]:
    eligible = [row for row in players if isinstance(row.get(value_key), (int, float)) and math.isfinite(float(row[value_key]))]
    total = sum(float(row[value_key]) for row in eligible)
    returning = sum(float(row[value_key]) for row in eligible if row.get("returning"))
    positive_total = sum(max(float(row[value_key]), 0.0) for row in eligible)
    positive_returning = sum(max(float(row[value_key]), 0.0) for row in eligible if row.get("returning"))
    return {
        "signedPriorPPA": total,
        "signedReturningPPA": returning,
        "signedReturningShare": returning / total if abs(total) > 1e-12 else None,
        "positivePriorPPA": positive_total,
        "positiveReturningPPA": positive_returning,
        "positiveReturningShare": positive_returning / positive_total if positive_total > 1e-12 else None,
        "positivePPALost": positive_total - positive_returning,
    }


def build_slide_overview(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    older: list[dict[str, Any]],
    ppa_report: dict[str, Any],
    *,
    team: str,
    season: int,
    roster_urls: dict[str, str],
    previous_school_available: bool = True,
) -> dict[str, Any]:
    players = classify_roster_sources(current, previous, older, previous_school_available=previous_school_available)
    total = len(players)
    source_counts = Counter(row["rosterSource"] for row in players)
    class_counts = Counter(row["classLabel"] for row in players)
    eligibility_counts = Counter(row["eligibilityBucket"] for row in players)
    position_counts = Counter(row["positionGroup"] for row in players)

    position_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    side_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for row in players:
        position_by_source[row["positionGroup"]][row["rosterSource"]] += 1
        side_by_source[row["side"]][row["rosterSource"]] += 1

    returning = source_counts.get("returning_2025", 0)
    college_new = source_counts.get("college_newcomer", 0)
    first_time = source_counts.get("first_time_college", 0)
    rejoining = source_counts.get("rejoining_program", 0)
    newcomer_unclassified = source_counts.get("newcomer_unclassified", 0)
    if returning + college_new + first_time + rejoining + newcomer_unclassified != total:
        raise RuntimeError("Roster source classification does not reconcile to current roster total.")

    upperclassmen = sum(
        class_counts.get(label, 0)
        for label in ("Junior", "Redshirt Junior", "Senior", "Redshirt Senior", "Graduate")
    )
    senior_grad = sum(class_counts.get(label, 0) for label in ("Senior", "Redshirt Senior", "Graduate"))
    redshirted = sum(count for label, count in class_counts.items() if label.startswith("Redshirt "))

    ppa_players = ppa_report.get("players", [])
    ppa_views = {
        "overallPlayerAttributedPPA": _signed_and_positive_ppa(ppa_players, "totalPPA"),
        "qbPassingPPA": _signed_and_positive_ppa(ppa_players, "passingPPA"),
        "nonQBPassPlayPPA": _signed_and_positive_ppa(ppa_players, "receivingAttributedPPA"),
        "rushingPPA": _signed_and_positive_ppa(ppa_players, "rushingPPA"),
    }

    side_summary: dict[str, Any] = {}
    for side, counts in sorted(side_by_source.items()):
        side_total = sum(counts.values())
        side_returning = counts.get("returning_2025", 0)
        side_summary[side] = {
            "players": side_total,
            "returning": side_returning,
            "returningShare": _share(side_returning, side_total),
            "collegeNewcomers": counts.get("college_newcomer", 0),
            "firstTimeCollege": counts.get("first_time_college", 0),
            "rejoiningProgram": counts.get("rejoining_program", 0),
        }

    top_returning = ppa_report.get("topReturningProducers", [])
    top_lost = ppa_report.get("topLostProducers", [])
    top_returning_player = top_returning[0] if top_returning else None
    top_returning_share = None
    if top_returning_player and ppa_report.get("overallPlayerAttributedPPA", {}).get("returningPPA"):
        denominator = float(ppa_report["overallPlayerAttributedPPA"]["returningPPA"])
        if abs(denominator) > 1e-12 and isinstance(top_returning_player.get("totalPPA"), (int, float)):
            top_returning_share = float(top_returning_player["totalPPA"]) / denominator

    slide_metrics = {
        "rosterSize": total,
        "returnedFrom2025": returning,
        "returnedFrom2025Share": _share(returning, total),
        "collegeNewcomers": college_new,
        "collegeNewcomerShare": _share(college_new, total),
        "firstTimeCollegeNewcomers": first_time,
        "rejoiningProgram": rejoining,
        "newcomerUnclassified": newcomer_unclassified,
        "newcomerUnclassifiedShare": _share(newcomer_unclassified, total),
        "upperclassmen": upperclassmen,
        "upperclassmenShare": _share(upperclassmen, total),
        "seniorGraduatePlayers": senior_grad,
        "seniorGraduateShare": _share(senior_grad, total),
        "redshirtedPlayers": redshirted,
        "offenseReturningShare": side_summary.get("Offense", {}).get("returningShare"),
        "defenseReturningShare": side_summary.get("Defense", {}).get("returningShare"),
        "signedPlayerPpaReturningShare": ppa_views["overallPlayerAttributedPPA"]["signedReturningShare"],
        "positiveQbPassPpaReturningShare": ppa_views["qbPassingPPA"]["positiveReturningShare"],
        "positiveRushPpaReturningShare": ppa_views["rushingPPA"]["positiveReturningShare"],
        "positiveNonQbPassPlayPpaReturningShare": ppa_views["nonQBPassPlayPPA"]["positiveReturningShare"],
        "topReturningPpaProducer": top_returning_player,
        "topReturningPpaProducerShareOfReturningSignedPpa": top_returning_share,
        "topLostPpaProducer": top_lost[0] if top_lost else None,
    }

    return {
        "definitionVersion": "audited-roster-slide-overview-v1",
        "team": team,
        "season": season,
        "sourceOfTruth": {
            "rosters": "Official team roster tables",
            "playerPPA": "CFBD /ppa/players/season for prior season",
            "rosterUrls": roster_urls,
            "ppaProductionSeason": season - 1,
            "garbageTimeExcluded": ppa_report.get("excludeGarbageTime"),
        },
        "roster": {
            "currentPlayers": total,
            "previousRosterPlayers": len(previous),
            "sourceCounts": dict(source_counts),
            "classDistribution": dict(class_counts),
            "eligibilityDistribution": dict(eligibility_counts),
            "positionGroupDistribution": dict(sorted(position_counts.items())),
            "positionBySource": {group: dict(counts) for group, counts in sorted(position_by_source.items())},
            "sideBySource": side_summary,
            "sizeByPositionGroup": _size_summary(players),
        },
        "returningPPA": {
            "contributorsReturning": ppa_report.get("returningPPAContributors"),
            "contributorsPrior": ppa_report.get("priorSeasonPPAContributors"),
            "views": ppa_views,
            "topReturningProducers": top_returning,
            "topLostProducers": top_lost,
        },
        "slide1RecommendedMetrics": slide_metrics,
        "players": players,
        "notes": [
            "Roster continuity is headcount continuity, not returning production. A backup and a star each count as one returning roster player.",
            "College newcomer means a current player who was not on the prior-season roster and whose official current roster lists a Previous School. It includes transfers, JUCO additions, and other prior-college players; it is intentionally broader than the transfer portal feed.",
            "First-time college newcomer means a current player who was not on the prior-season or older team roster and whose official current roster has no Previous School listed.",
            "Rejoining program means a player appears on the older team roster, not the immediately prior roster, and returns on the current roster.",
            "Exact age is not reported by the official roster, so the report uses official class/eligibility labels rather than invented ages.",
            "Signed PPA retention can exceed 100% when departed players had negative PPA. Positive-PPA retention is also reported for audience-facing use.",
            "Non-QB pass-play PPA is CFBD totalPPA.pass on RB/FB/WR/TE player rows. It should not be added to QB passing PPA because player-attribution views can overlap on the same passing play.",
        ]
        + (
            [
                "This team's official roster page does not publish a Previous School column, so non-returning players could not be split into college_newcomer vs. first_time_college -- they are grouped as newcomer_unclassified instead of guessing. Returning-vs-not-returning headcount is unaffected by this gap."
            ]
            if newcomer_unclassified
            else []
        ),
    }


def _print_report(report: dict[str, Any]) -> None:
    roster = report["roster"]
    metrics = report["slide1RecommendedMetrics"]
    source_counts = roster["sourceCounts"]

    print("=" * 96)
    print(f"{report['team'].upper()} {report['season']} AUDITED ROSTER OVERVIEW — SLIDE 1 INPUT")
    print("=" * 96)
    print("OFFICIAL ROSTER COMPOSITION")
    print("---------------------------")
    print(f"Current roster:                  {roster['currentPlayers']}")
    print(f"Returned from {report['season'] - 1}:              {source_counts.get('returning_2025', 0):>3}  ({_pct(metrics['returnedFrom2025Share'])})")
    print(f"Newcomers from another college:  {source_counts.get('college_newcomer', 0):>3}  ({_pct(metrics['collegeNewcomerShare'])})")
    print(f"First-time college newcomers:     {source_counts.get('first_time_college', 0):>3}")
    print(f"Rejoining program:                {source_counts.get('rejoining_program', 0):>3}")

    print("\nCONTINUITY BY SIDE")
    print("------------------")
    for side in ("Offense", "Defense", "Special Teams"):
        row = roster["sideBySource"].get(side)
        if not row:
            continue
        print(
            f"{side:<18} {row['returning']:>2}/{row['players']:<2} returning "
            f"({_pct(row['returningShare'])}) | {row['collegeNewcomers']} college newcomers"
        )

    print("\nOFFICIAL CLASS / ELIGIBILITY DISTRIBUTION")
    print("-----------------------------------------")
    for label, count in roster["classDistribution"].items():
        print(f"{label:<24} {count:>3}")
    print(f"Upperclassmen (Jr/R-Jr/Sr/R-Sr/Gr): {metrics['upperclassmen']:>3} ({_pct(metrics['upperclassmenShare'])})")
    print(f"Senior / graduate:                       {metrics['seniorGraduatePlayers']:>3} ({_pct(metrics['seniorGraduateShare'])})")

    print("\nPOSITION GROUP x ROSTER SOURCE")
    print("------------------------------")
    print(f"{'GROUP':<8} {'RETURN':>7} {'COLLEGE NEW':>12} {'FIRST-TIME':>12} {'REJOIN':>8} {'TOTAL':>7}")
    for group, counts in roster["positionBySource"].items():
        total = sum(counts.values())
        print(
            f"{group:<8} {counts.get('returning_2025', 0):>7} {counts.get('college_newcomer', 0):>12} "
            f"{counts.get('first_time_college', 0):>12} {counts.get('rejoining_program', 0):>8} {total:>7}"
        )

    print("\n2025 PLAYER-PPA RETENTION (GARBAGE TIME EXCLUDED)")
    print("-------------------------------------------------")
    ppa = report["returningPPA"]["views"]
    labels = (
        ("overallPlayerAttributedPPA", "Overall player-attributed PPA"),
        ("qbPassingPPA", "QB passing PPA"),
        ("nonQBPassPlayPPA", "Non-QB pass-play PPA"),
        ("rushingPPA", "Rushing PPA"),
    )
    for key, label in labels:
        row = ppa[key]
        print(
            f"{label:<30} signed {_pct(row['signedReturningShare']):>7} | "
            f"positive PPA retained {_pct(row['positiveReturningShare']):>7}"
        )

    print("\nBIGGEST 2025 PPA PRODUCERS RETURNING")
    print("------------------------------------")
    for row in report["returningPPA"]["topReturningProducers"][:8]:
        print(f"{row['position']:<4} {row['name']:<28} total PPA {row['totalPPA']:>8.2f}")

    print("\nBIGGEST 2025 PPA PRODUCERS LOST")
    print("-------------------------------")
    for row in report["returningPPA"]["topLostProducers"][:8]:
        print(f"{row['position']:<4} {row['name']:<28} total PPA {row['totalPPA']:>8.2f}")

    print("\nSLIDE 1 NUMBERS I WOULD ACTUALLY USE")
    print("------------------------------------")
    print(f"Roster: {metrics['rosterSize']} players")
    print(f"2025 roster returners: {metrics['returnedFrom2025']} ({_pct(metrics['returnedFrom2025Share'])})")
    print(f"College-experience newcomers: {metrics['collegeNewcomers']} ({_pct(metrics['collegeNewcomerShare'])})")
    print(f"Offensive roster continuity: {_pct(metrics['offenseReturningShare'])}")
    print(f"Defensive roster continuity: {_pct(metrics['defenseReturningShare'])}")
    print(f"Upperclassmen: {metrics['upperclassmen']} ({_pct(metrics['upperclassmenShare'])})")
    print(f"2025 signed player-PPA retained: {_pct(metrics['signedPlayerPpaReturningShare'])}")
    print(f"Positive QB passing PPA retained: {_pct(metrics['positiveQbPassPpaReturningShare'])}")
    print(f"Positive rushing PPA retained: {_pct(metrics['positiveRushPpaReturningShare'])}")
    print(f"Positive non-QB pass-play PPA retained: {_pct(metrics['positiveNonQbPassPlayPpaReturningShare'])}")
    top = metrics.get("topReturningPpaProducer")
    if top:
        print(
            f"Top returning PPA producer: {top['name']} ({top['totalPPA']:.2f}); "
            f"{_pct(metrics['topReturningPpaProducerShareOfReturningSignedPpa'])} of returning signed player-PPA"
        )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an audited, audience-ready roster overview using official team rosters plus prior-season CFBD player PPA."
    )
    parser.add_argument("--team", default=DEFAULT_TEAM)
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--roster-url-template", default=DEFAULT_ROSTER_URL_TEMPLATE)
    parser.add_argument("--output-dir", type=Path, default=Path("data/research/roster-overview"))
    parser.add_argument(
        "--roster-schema",
        choices=["standard", "no-transfer-column"],
        default="standard",
        help=(
            "'standard' expects Name/Pos./Class/Ht./Wt./Previous School (wmubroncos.com-style). "
            "'no-transfer-column' is for official sites that publish Name/Pos./Ht./Wt./Yr. with no "
            "transfer-origin column at all (e.g. mgoblue.com) -- newcomers are labeled "
            "newcomer_unclassified instead of guessing college_newcomer vs. first_time_college."
        ),
    )
    args = parser.parse_args()

    if args.roster_schema == "no-transfer-column":
        parse_kwargs: dict[str, Any] = {
            "required": {"name", "pos", "class", "ht", "wt"},
            "header_aliases": {"yr": "class"},
        }
        previous_school_available = False
    else:
        parse_kwargs = {}
        previous_school_available = True

    urls = {
        "current": args.roster_url_template.format(year=args.season),
        "previous": args.roster_url_template.format(year=args.season - 1),
        "older": args.roster_url_template.format(year=args.season - 2),
    }
    current = fetch_official_roster(urls["current"], **parse_kwargs)
    previous = fetch_official_roster(urls["previous"], **parse_kwargs)
    older = fetch_official_roster(urls["older"], **parse_kwargs)

    production_season = args.season - 1
    with CfbdClient() as client:
        prior_player_ppa = client.get_json(
            "/ppa/players/season",
            {
                "year": production_season,
                "team": args.team,
                "excludeGarbageTime": True,
            },
        ).payload

    if not isinstance(prior_player_ppa, list):
        raise RuntimeError("Unexpected CFBD player-PPA response; expected an array.")

    official_current_for_match = [{"name": row["name"]} for row in current]
    ppa_report = build_returning_ppa_report(
        official_current_for_match,
        prior_player_ppa,
        team=args.team,
        season=args.season,
        exclude_garbage_time=True,
    )
    report = build_slide_overview(
        current,
        previous,
        older,
        ppa_report,
        team=args.team,
        season=args.season,
        roster_urls=urls,
        previous_school_available=previous_school_available,
    )
    _print_report(report)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", args.team.lower()).strip("-")
    json_path = args.output_dir / f"{args.season}-{slug}-audited-roster-overview.json"
    csv_path = args.output_dir / f"{args.season}-{slug}-audited-roster-players.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(csv_path, report["players"])
    print(f"\nWrote JSON: {json_path}")
    print(f"Wrote CSV:  {csv_path}")


if __name__ == "__main__":
    main()
