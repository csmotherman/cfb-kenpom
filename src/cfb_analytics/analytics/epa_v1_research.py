"""Independent Expected Points / EPA research models.

CFBD ``ppa`` is never used for training. It is an external benchmark only.

v1 uses realized net points through the end of the half as the EP target.
v2 uses the next observed scoring value before halftime and aligns score changes
with the scoring play row, based on the corpus score-timing audit.
"""
from __future__ import annotations
from collections import defaultdict
from math import sqrt
from typing import Any

from cfb_analytics.raw.sequence import _candidate_sort_key

EPA_RESEARCH_VERSION = "epa-v1-research-empirical"
EPA_V2_RESEARCH_VERSION = "epa-v2-research-next-score"


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def clock_seconds(clock: Any) -> int | None:
    if isinstance(clock, dict):
        m, s = clock.get("minutes"), clock.get("seconds")
        if _num(m) and _num(s):
            return int(m) * 60 + int(s)
    if isinstance(clock, str) and ":" in clock:
        try:
            m, s = clock.split(":", 1)
            return int(m) * 60 + int(float(s))
        except ValueError:
            return None
    return None


def seconds_remaining_in_half(play: dict[str, Any]) -> int | None:
    period = play.get("period")
    c = clock_seconds(play.get("clock"))
    if period not in (1, 2, 3, 4) or c is None or c < 0 or c > 900:
        return None
    return c + (900 if period in (1, 3) else 0)


def half_number(play: dict[str, Any]) -> int | None:
    p = play.get("period")
    if p in (1, 2):
        return 1
    if p in (3, 4):
        return 2
    return None


def oriented_score(play: dict[str, Any]) -> tuple[float, float] | None:
    offense, home, away = play.get("offense"), play.get("home"), play.get("away")
    os, ds = play.get("offenseScore"), play.get("defenseScore")
    if not (_num(os) and _num(ds) and offense and home and away):
        return None
    if offense == home:
        return float(os), float(ds)
    if offense == away:
        return float(ds), float(os)
    return None


def state_eligible(play: dict[str, Any]) -> bool:
    if half_number(play) is None or seconds_remaining_in_half(play) is None:
        return False
    d, dist, ytg = play.get("down"), play.get("distance"), play.get("yardsToGoal")
    return d in (1, 2, 3, 4) and _num(dist) and dist >= 0 and _num(ytg) and 0 <= ytg <= 100 and bool(play.get("offense")) and oriented_score(play) is not None


def _distance_bucket(v: float) -> int:
    if v <= 1: return 1
    if v <= 3: return 3
    if v <= 6: return 6
    if v <= 10: return 10
    return 11


def _bucket(v: float, width: int) -> int:
    return int(v // width) * width


def state_keys(play: dict[str, Any]) -> list[tuple[Any, ...]]:
    sec = seconds_remaining_in_half(play)
    down, dist, ytg = int(play["down"]), float(play["distance"]), float(play["yardsToGoal"])
    db = _distance_bucket(dist)
    return [
        ("exact", down, db, _bucket(ytg, 5), _bucket(sec, 120)),
        ("coarse", down, db, _bucket(ytg, 10), _bucket(sec, 300)),
        ("field", down, db, _bucket(ytg, 10)),
        ("down_field", down, _bucket(ytg, 20)),
        ("down", down),
        ("global",),
    ]


def _game_groups(plays):
    by = defaultdict(list)
    for p in plays:
        if p.get("gameId") is not None:
            by[str(p.get("gameId"))].append(p)
    for rows in by.values():
        rows.sort(key=_candidate_sort_key)
    return by


def training_examples(plays):
    """Yield v1 ``(play, realized future net points to end of half)``."""
    for rows in _game_groups(plays).values():
        finals = {}
        for p in rows:
            h = half_number(p); score = oriented_score(p)
            if h is not None and score is not None:
                finals[h] = score
        for p in rows:
            if not state_eligible(p):
                continue
            h = half_number(p); final = finals.get(h); cur = oriented_score(p)
            if final is None or cur is None:
                continue
            home_delta, away_delta = final[0] - cur[0], final[1] - cur[1]
            if p.get("offense") == p.get("home"):
                target = home_delta - away_delta
            else:
                target = away_delta - home_delta
            yield p, float(target)


class EmpiricalExpectedPoints:
    def __init__(self, min_count: int = 50):
        self.min_count = min_count
        self.stats = defaultdict(lambda: [0, 0.0])

    def fit(self, plays):
        for p, target in training_examples(plays):
            for key in state_keys(p):
                self.stats[key][0] += 1
                self.stats[key][1] += target
        return self

    def predict(self, play):
        if not state_eligible(play):
            return None
        keys = state_keys(play)
        for i, key in enumerate(keys):
            n, total = self.stats.get(key, (0, 0.0))
            if n >= self.min_count or (i == len(keys) - 1 and n):
                return total / n
        return None


def scoreboard_delta(a, b, offense):
    sa, sb = oriented_score(a), oriented_score(b)
    if sa is None or sb is None:
        return None
    hd, ad = sb[0] - sa[0], sb[1] - sa[1]
    home, away = a.get("home"), a.get("away")
    if offense == home: return hd - ad
    if offense == away: return ad - hd
    return None


def transition_epa(start, end, model):
    """v1 EPA for a recorded-state transition, from start offense view."""
    ep0, ep1 = model.predict(start), model.predict(end)
    if ep0 is None or ep1 is None:
        return None
    offense = start.get("offense")
    points = scoreboard_delta(start, end, offense)
    if points is None:
        return None
    sign = 1.0 if end.get("offense") == offense else -1.0
    return points + sign * ep1 - ep0


def scoring_timing_counts(plays):
    """Compare score changes entering vs leaving source-marked scoring rows."""
    c = defaultdict(int)
    for rows in _game_groups(plays).values():
        eligible = [p for p in rows if oriented_score(p) is not None]
        for i, p in enumerate(eligible):
            scoring = p.get("scoring") is True or str(p.get("eventSubtype") or "").upper() in {"RUSH_TD", "PASS_TD", "FIELD_GOAL_GOOD", "SAFETY"}
            if not scoring:
                continue
            c["scoring_rows"] += 1
            if i > 0:
                d = scoreboard_delta(eligible[i - 1], p, eligible[i - 1].get("offense"))
                if d: c["score_change_entering_scoring_row"] += 1
            if i + 1 < len(eligible):
                d = scoreboard_delta(p, eligible[i + 1], p.get("offense"))
                if d: c["score_change_leaving_scoring_row"] += 1
    return dict(c)


def ppa_coverage(plays):
    c = defaultdict(int)
    for p in plays:
        if state_eligible(p):
            c["eligible_states"] += 1
            if _num(p.get("ppa")): c["eligible_with_ppa"] += 1
        if p.get("isScrimmagePlay") is True and p.get("isOffensivePlay") is True and not p.get("hasNoPlayContext"):
            c["clean_scrimmage"] += 1
            if _num(p.get("ppa")): c["clean_scrimmage_with_ppa"] += 1
    return dict(c)


def pearson(xs, ys):
    n = len(xs)
    if n < 2: return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs); sy = sum((y - my) ** 2 for y in ys)
    if not sx or not sy: return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sqrt(sx * sy)


def compare_to_ppa(train_plays, validation_plays, score_timing="pre", min_count=50):
    """Benchmark v1 against CFBD PPA."""
    model = EmpiricalExpectedPoints(min_count=min_count).fit(train_plays)
    ours, source = [], []
    for rows in _game_groups(validation_plays).values():
        states = [p for p in rows if state_eligible(p)]
        for i in range(len(states) - 1):
            if score_timing == "pre":
                play, start, end = states[i], states[i], states[i + 1]
            elif score_timing == "post":
                if i == 0: continue
                play, start, end = states[i], states[i - 1], states[i]
            else:
                raise ValueError("score_timing must be 'pre' or 'post'")
            if play.get("isScrimmagePlay") is not True or play.get("isOffensivePlay") is not True or play.get("hasNoPlayContext"):
                continue
            if not _num(play.get("ppa")):
                continue
            epa = transition_epa(start, end, model)
            if epa is None:
                continue
            ours.append(float(epa)); source.append(float(play["ppa"]))
    n = len(ours)
    return {
        "version": EPA_RESEARCH_VERSION,
        "score_timing": score_timing,
        "comparison_plays": n,
        "correlation": pearson(ours, source),
        "mae": sum(abs(a - b) for a, b in zip(ours, source)) / n if n else None,
        "mean_epa": sum(ours) / n if n else None,
        "mean_ppa": sum(source) / n if n else None,
    }


# EPA v2: next-score target and scoring-row point alignment.

def _same_half(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ha, hb = half_number(a), half_number(b)
    return ha is not None and ha == hb


def _score_delta_for_offense(a: dict[str, Any], b: dict[str, Any], offense: Any) -> float | None:
    sa, sb = oriented_score(a), oriented_score(b)
    if sa is None or sb is None:
        return None
    hd, ad = sb[0] - sa[0], sb[1] - sa[1]
    home, away = b.get("home"), b.get("away")
    if offense == home:
        return float(hd - ad)
    if offense == away:
        return float(ad - hd)
    return None


def next_score_examples(plays):
    """Yield v2 ``(play, next scoring value before end of half)``.

    Score changes entering a row are treated as belonging to that row because
    the full-corpus timing audit overwhelmingly supports that alignment.
    """
    for rows in _game_groups(plays).values():
        states = [p for p in rows if state_eligible(p)]
        for i, play in enumerate(states):
            offense = play.get("offense")
            if i > 0 and _same_half(states[i - 1], play):
                entering = _score_delta_for_offense(states[i - 1], play, offense)
                if entering:
                    yield play, float(entering)
                    continue
            target = 0.0
            for j in range(i + 1, len(states)):
                nxt = states[j]
                if not _same_half(play, nxt):
                    break
                delta = _score_delta_for_offense(states[j - 1], nxt, offense)
                if delta:
                    target = float(delta)
                    break
            yield play, target


class NextScoreExpectedPoints:
    def __init__(self, min_count: int = 50):
        self.min_count = min_count
        self.stats = defaultdict(lambda: [0, 0.0])

    def fit(self, plays):
        for p, target in next_score_examples(plays):
            for key in state_keys(p):
                self.stats[key][0] += 1
                self.stats[key][1] += target
        return self

    def predict(self, play):
        if not state_eligible(play):
            return None
        keys = state_keys(play)
        for i, key in enumerate(keys):
            n, total = self.stats.get(key, (0, 0.0))
            if n >= self.min_count or (i == len(keys) - 1 and n):
                return total / n
        return None


def play_epa_v2(previous, play, next_play, model):
    """EPA v2 for ``play`` using scoring-row point alignment."""
    ep0, ep1 = model.predict(play), model.predict(next_play)
    if ep0 is None or ep1 is None:
        return None
    offense = play.get("offense")
    points = 0.0
    if previous is not None and _same_half(previous, play):
        observed = _score_delta_for_offense(previous, play, offense)
        if observed is not None:
            points = observed
    sign = 1.0 if next_play.get("offense") == offense else -1.0
    return points + sign * ep1 - ep0


def compare_v2_to_ppa(train_plays, validation_plays, min_count=50):
    model = NextScoreExpectedPoints(min_count=min_count).fit(train_plays)
    ours, source = [], []
    for rows in _game_groups(validation_plays).values():
        states = [p for p in rows if state_eligible(p)]
        for i in range(len(states) - 1):
            play = states[i]
            if play.get("isScrimmagePlay") is not True or play.get("isOffensivePlay") is not True or play.get("hasNoPlayContext"):
                continue
            if not _num(play.get("ppa")):
                continue
            previous = states[i - 1] if i > 0 else None
            epa = play_epa_v2(previous, play, states[i + 1], model)
            if epa is None:
                continue
            ours.append(float(epa)); source.append(float(play["ppa"]))
    n = len(ours)
    return {
        "version": EPA_V2_RESEARCH_VERSION,
        "comparison_plays": n,
        "correlation": pearson(ours, source),
        "mae": sum(abs(a - b) for a, b in zip(ours, source)) / n if n else None,
        "mean_epa": sum(ours) / n if n else None,
        "mean_ppa": sum(source) / n if n else None,
    }


def main(argv=None):
    import argparse
    import json
    from pathlib import Path
    from cfb_analytics.raw.audit import discover_partitions
    from cfb_analytics.canonical.materialize import canonical_partition_dir

    parser = argparse.ArgumentParser(description="Independent EPA research benchmarks")
    parser.add_argument("command", choices=("compare",))
    parser.add_argument("--validation-season", type=int, default=2025)
    parser.add_argument("--min-count", type=int, default=50)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-root", type=Path, default=Path("data/processed"))
    args = parser.parse_args(argv)

    seasons = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)

    def load(selected):
        out = []
        for season in selected:
            for st, w in discover_partitions(args.raw_root, season):
                path = canonical_partition_dir(args.processed_root, season, st, w) / "plays.json"
                out.extend(json.loads(path.read_text()))
        return out

    validation = load((args.validation_season,))
    train = load(tuple(s for s in seasons if s != args.validation_season))
    v1 = compare_to_ppa(train, validation, "pre", args.min_count)
    v2 = compare_v2_to_ppa(train, validation, args.min_count)

    print(f"EPA RESEARCH HOLDOUT COMPARISON: {args.validation_season}")
    print()
    for label, result in (("V1 END-HALF", v1), ("V2 NEXT-SCORE", v2)):
        print(label)
        print(f"Version: {result['version']}")
        print(f"Comparison plays: {result['comparison_plays']:,}")
        print(f"Correlation vs PPA: {result['correlation']:.6f}")
        print(f"MAE vs PPA: {result['mae']:.6f}")
        print(f"Mean EPA: {result['mean_epa']:.6f}")
        print(f"Mean PPA: {result['mean_ppa']:.6f}")
        print()
    if v1["correlation"] is not None and v2["correlation"] is not None:
        print(f"Correlation delta (v2-v1): {v2['correlation'] - v1['correlation']:+.6f}")
    if v1["mae"] is not None and v2["mae"] is not None:
        print(f"MAE delta (v2-v1): {v2['mae'] - v1['mae']:+.6f}")


if __name__ == "__main__":
    main()
