"""Game-team Basic Yardage v1 metrics from the fully reconciled corpus.

Policy:
- Rush attempts/yards come from clean canonical RUSH scrimmage records.
- Standard Dropbacks v1 contribute one dropback and their canonical yardage.
- Recovered residual interception attempts contribute one dropback but zero
  passing yards because their source yardage is interception-return movement.
- Standalone FUMBLE records, TWO_POINT_PASS, and PASS_UNSPECIFIED are excluded.
"""
from __future__ import annotations

from collections import defaultdict

from cfb_analytics.analytics.basic_yardage_forensics import _clean, _family, _yards
from cfb_analytics.analytics.dropback_v1_candidate import (
    VALID_CLASSES,
    _explicit_interception_text,
    classify_standard_dropback,
)
from cfb_analytics.analytics.havoc import turnover_play_ids

BASIC_YARDAGE_VERSION = "basic-yardage-v1"


def _rate(n, d):
    return n / d if d else None


def partition_game_team_basic_yardage_metrics(plays, drives):
    metrics = defaultdict(lambda: defaultdict(float))
    by_drive = defaultdict(list)

    for p in plays:
        by_drive[(str(p.get("gameId")), str(p.get("driveId")))].append(p)
        if not _clean(p):
            continue
        gid = str(p.get("gameId"))
        offense = p.get("offense")
        defense = p.get("defense")
        fam = _family(p)
        cls = classify_standard_dropback(p)
        yards = _yards(p) or 0.0

        if fam == "RUSH":
            if offense:
                x = metrics[(gid, offense)]
                x["rushAttempts"] += 1
                x["rushYards"] += yards
            if defense:
                x = metrics[(gid, defense)]
                x["rushAttemptsFaced"] += 1
                x["rushYardsAllowed"] += yards

        if cls:
            if offense:
                x = metrics[(gid, offense)]
                x["dropbacks"] += 1
                x["netPassYards"] += yards
            if defense:
                x = metrics[(gid, defense)]
                x["dropbacksFaced"] += 1
                x["netPassYardsAllowed"] += yards

    turn_ids, outcomes, _, _ = turnover_play_ids(drives, plays)
    for d in drives:
        if not (
            d.get("isPossessionDrive") is True
            and d.get("driveValidationStatus") == "PASS"
        ):
            continue
        gid = str(d.get("gameId"))
        rows = by_drive[(gid, str(d.get("driveId")))]
        if not any(
            id(p) in turn_ids and outcomes.get(id(p)) == "INTERCEPTION"
            for p in rows
        ):
            continue
        if any(classify_standard_dropback(p) in VALID_CLASSES for p in rows):
            continue
        explicit = [p for p in rows if _explicit_interception_text(p)]
        if not explicit:
            continue
        offense = d.get("offense")
        defense = d.get("defense")
        if offense:
            x = metrics[(gid, offense)]
            x["dropbacks"] += 1
            x["recoveredInterceptionDropbacks"] += 1
        if defense:
            x = metrics[(gid, defense)]
            x["dropbacksFaced"] += 1
            x["recoveredInterceptionDropbacksFaced"] += 1

    out = {}
    for key, raw in metrics.items():
        d = dict(raw)
        for k in (
            "rushAttempts",
            "rushAttemptsFaced",
            "dropbacks",
            "dropbacksFaced",
            "recoveredInterceptionDropbacks",
            "recoveredInterceptionDropbacksFaced",
        ):
            d[k] = int(d.get(k, 0))
        d["basicYardagePlays"] = d.get("rushAttempts", 0) + d.get("dropbacks", 0)
        d["basicYardageYards"] = d.get("rushYards", 0.0) + d.get("netPassYards", 0.0)
        d["basicYardagePlaysFaced"] = d.get("rushAttemptsFaced", 0) + d.get("dropbacksFaced", 0)
        d["basicYardageYardsAllowed"] = d.get("rushYardsAllowed", 0.0) + d.get("netPassYardsAllowed", 0.0)
        d["yardsPerPlay"] = _rate(d["basicYardageYards"], d["basicYardagePlays"])
        d["yardsPerPlayAllowed"] = _rate(d["basicYardageYardsAllowed"], d["basicYardagePlaysFaced"])
        d["rushYardsPerAttempt"] = _rate(d.get("rushYards", 0.0), d.get("rushAttempts", 0))
        d["rushYardsPerAttemptAllowed"] = _rate(d.get("rushYardsAllowed", 0.0), d.get("rushAttemptsFaced", 0))
        d["netPassYardsPerDropback"] = _rate(d.get("netPassYards", 0.0), d.get("dropbacks", 0))
        d["netPassYardsPerDropbackAllowed"] = _rate(d.get("netPassYardsAllowed", 0.0), d.get("dropbacksFaced", 0))
        d["basicYardageDefinitionVersion"] = BASIC_YARDAGE_VERSION
        out[key] = d
    return out
