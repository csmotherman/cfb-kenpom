from __future__ import annotations
from collections import defaultdict

TFL_VERSION = "tfl-v1"
VALID_TYPES = {"Rush", "Rushing Touchdown", "Pass Reception", "Pass Completion"}
RUSH_TYPES = {"Rush", "Rushing Touchdown"}

def _source(p):
    return str(p.get("sourcePlayType") or p.get("playType") or "UNKNOWN")

def _yards(p):
    return p.get("analyticsYardsGained", p.get("yardsGained"))

def _clock(p):
    c = p.get("clock")
    if isinstance(c, dict) and isinstance(c.get("minutes"), (int, float)) and isinstance(c.get("seconds"), (int, float)):
        return int(c["minutes"]) * 60 + int(c["seconds"])
    for key in ("clockSeconds", "secondsRemaining", "periodSecondsRemaining"):
        v = p.get(key)
        if isinstance(v, (int, float)):
            return int(v)
    return None

def _offense(p):
    return p.get("offense") or p.get("offenseTeam") or p.get("possessionTeam") or p.get("team")

def structural_candidate(p):
    y = _yards(p)
    scrimmage = bool(p.get("isScrimmagePlay")) or p.get("eventCategory") == "SCRIMMAGE"
    sack = p.get("eventSubtype") == "SACK" or _source(p).lower() == "sack"
    modified = bool(p.get("hasNoPlayContext") or p.get("isModifiedContext") or p.get("isNoPlay"))
    return scrimmage and isinstance(y, (int, float)) and y < 0 and not sack and not modified and _source(p) in VALID_TYPES

def high_confidence_kneel_ids(plays):
    games = defaultdict(list)
    for p in plays:
        games[str(p.get("gameId"))].append(p)
    excluded = set()
    for rows in games.values():
        rows = sorted(rows, key=lambda p: (p.get("period") or 0, -(_clock(p) if _clock(p) is not None else 9999), p.get("playSequence") or p.get("sequence") or 0))
        for i, p in enumerate(rows):
            y, sec = _yards(p), _clock(p)
            risk = structural_candidate(p) and _source(p) in RUSH_TYPES and -3 <= y <= -1 and p.get("period") in (2, 4) and sec is not None and sec <= 90
            if not risk:
                continue
            off = _offense(p)
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            nsec = _clock(nxt) if nxt else None
            drain = bool(nxt and _offense(nxt) == off and nxt.get("period") == p.get("period") and nsec is not None and sec - nsec >= 20)
            repeated = False
            for q in rows[i + 1:i + 4]:
                qy, qsec = _yards(q), _clock(q)
                if _offense(q) == off and q.get("period") == p.get("period") and _source(q) in RUSH_TYPES and isinstance(qy, (int, float)) and -3 <= qy <= -1 and qsec is not None and qsec < sec:
                    repeated = True
                    break
            if repeated and drain:
                excluded.add(id(p))
    return excluded

def classify_tfl(p, kneel_ids):
    return structural_candidate(p) and id(p) not in kneel_ids

def team_tfl_metrics(team, plays):
    kneels = high_confidence_kneel_ids(plays)
    made = sum(1 for p in plays if classify_tfl(p, kneels) and p.get("defense") == team)
    allowed = sum(1 for p in plays if classify_tfl(p, kneels) and p.get("offense") == team)
    return {"tacklesForLoss": made, "tacklesForLossAllowed": allowed, "tflDefinitionVersion": TFL_VERSION}

def corpus_tfl_audit(plays):
    kneels = high_confidence_kneel_ids(plays)
    structural = sum(1 for p in plays if structural_candidate(p))
    tfl = [p for p in plays if classify_tfl(p, kneels)]
    rush = sum(1 for p in tfl if _source(p) in RUSH_TYPES)
    return {"structural_candidates": structural, "high_confidence_kneels_excluded": len(kneels), "tackles_for_loss": len(tfl), "rush_tfls": rush, "completion_tfls": len(tfl) - rush}
