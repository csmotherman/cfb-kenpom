"""Play-level "what scores next" labels for a gradient-boosted multinomial
Expected Points model -- see .claude/plans/snazzy-foraging-blossom.md for
the full design and the validation gate this must clear before it ships.

Labels are anchored to game_story.drive_result.classify_drive_result's
already-validated, play-signal-based drive classification (`scoring`,
`playType`, `isTurnover`, `hasInterceptionContext`/`hasFumbleContext`), NOT
raw per-play scoreboard score fields -- that module's own docstring documents
those fields as unreliable (verified: they tracked one fixed side's
cumulative score all game regardless of who was actually driving). This
module does not reimplement drive-outcome classification; it only extends
that drive-grain result to play grain (walk forward from each play to the
next drive, own or opponent's, that resolves to a real score, within the
same half) and adds the feature/model layer classify_drive_result has no
reason to need.

Kept separate from epa_v1_research.py (which production epa.py already
imports from and relies on) until this is proven better, per the plan.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from cfb_analytics.analytics.game_story.drive_result import classify_drive_result

EPA_V2_GBT_VERSION = "epa-v2-gbt-next-score-v1"

# classify_drive_result's own result vocabulary that represents a real score.
# TURNOVER_SCORE (a defensive/return TD during what was nominally the other
# team's drive) belongs here too -- it's a touchdown, just not the offense's.
SCORING_RESULTS = {"TOUCHDOWN", "FIELD_GOAL", "SAFETY", "TURNOVER_SCORE"}
HALF_END_RESULTS = {"END_OF_HALF", "END_OF_GAME"}

# classify_drive_result hardcodes points=0 on its TURNOVER_SCORE branch
# (scoredBy is correct -- the play's own "offense" field flips to the
# returning team on a return-TD play -- but points isn't populated there).
# A return touchdown is worth the same base 6 as any other touchdown.
_POINTS_OVERRIDE = {"TURNOVER_SCORE": 6}

CLASSES = ("OWN_TD", "OWN_FG", "OWN_SAFETY", "NONE", "OPP_SAFETY", "OPP_FG", "OPP_TD")


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _half_of_period(period: Any) -> int | None:
    if period in (1, 2):
        return 1
    if period in (3, 4):
        return 2
    return None


def _classify_relative(result: str, scored_by: str | None, offense: str | None) -> str:
    is_own = scored_by == offense
    if result in ("TOUCHDOWN", "TURNOVER_SCORE"):
        return "OWN_TD" if is_own else "OPP_TD"
    if result == "FIELD_GOAL":
        return "OWN_FG" if is_own else "OPP_FG"
    if result == "SAFETY":
        # classify_drive_result's SAFETY scoredBy is the defense (the team
        # that gets the points) -- correctly the *other* side from `offense`
        # in the overwhelming majority of real plays.
        return "OWN_SAFETY" if is_own else "OPP_SAFETY"
    raise ValueError(f"not a scoring result: {result}")


def game_drive_labels(drives: list[dict], plays: list[dict]) -> dict[str, dict]:
    """driveId -> classify_drive_result(...) output, for every drive of one game."""
    plays_by_drive: dict[str, list[dict]] = defaultdict(list)
    for p in plays:
        did = p.get("driveId")
        if did:
            plays_by_drive[did].append(p)
    return {d["driveId"]: classify_drive_result(d, plays_by_drive) for d in drives}


def _group_by_game(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        gid = r.get("gameId")
        if gid is not None:
            out[str(gid)].append(r)
    return out


def next_score_class_examples(all_drives: list[dict], all_plays: list[dict]):
    """Yield (play, class_name, points, scored_by) for every play with a
    resolvable down/distance/yardsToGoal state -- one label per play, class
    oriented to that play's own offense, points already override-corrected.
    """
    drives_by_game = _group_by_game(all_drives)
    plays_by_game = _group_by_game(all_plays)

    for gid, drives in drives_by_game.items():
        plays = plays_by_game.get(gid, [])
        drives_sorted = sorted(drives, key=lambda d: d.get("driveNumber") or 0)
        if not drives_sorted:
            continue
        labels = game_drive_labels(drives_sorted, plays)

        plays_by_drive: dict[str, list[dict]] = defaultdict(list)
        for p in plays:
            did = p.get("driveId")
            if did:
                plays_by_drive[did].append(p)
        for did in plays_by_drive:
            plays_by_drive[did].sort(key=lambda p: p.get("playNumber") or 0)

        n = len(drives_sorted)
        # resolved[i] = ("score", j) -- the next drive at-or-after i, same
        # half, that resolves to a real score, index j -- or ("halfend", i)
        # if a half boundary comes first with no intervening score.
        resolved: list[tuple[str, int] | None] = [None] * n
        for i in range(n - 1, -1, -1):
            d = drives_sorted[i]
            result = labels[d["driveId"]]["result"]
            if result in SCORING_RESULTS:
                resolved[i] = ("score", i)
                continue
            if result in HALF_END_RESULTS:
                resolved[i] = ("halfend", i)
                continue
            nxt = drives_sorted[i + 1] if i + 1 < n else None
            if nxt is not None and _half_of_period(nxt.get("startPeriod")) == _half_of_period(d.get("startPeriod")):
                resolved[i] = resolved[i + 1]
            else:
                # Unknown/ambiguous drive result at a half boundary (or the
                # last drive of the corpus) -- can't resolve past it either
                # way; treat like a half-end rather than guessing.
                resolved[i] = ("halfend", i)

        for i, d in enumerate(drives_sorted):
            outcome = resolved[i]
            for p in plays_by_drive.get(d["driveId"], []):
                if not p.get("down") or not _num(p.get("distance")) or not _num(p.get("yardsToGoal")):
                    continue
                offense = p.get("offense")
                if outcome is None or outcome[0] == "halfend":
                    yield p, "NONE", 0.0, None
                    continue
                score_drive = drives_sorted[outcome[1]]
                score_label = labels[score_drive["driveId"]]
                scored_by = score_label["scoredBy"]
                pts = _POINTS_OVERRIDE.get(score_label["result"], score_label["points"] or 0)
                cls = _classify_relative(score_label["result"], scored_by, offense)
                yield p, cls, float(pts), scored_by


# --------------------------------------------------------------------------
# Features + model. All continuous, no bucketing -- the main fix over
# epa_v1_research.py's coarse-bucket empirical averaging. scoreDifferential
# in particular is entirely new: NextScoreExpectedPoints's state_keys() never
# included it, despite down-3-and-9 meaning something completely different
# at 0-0 than at down-21.
# --------------------------------------------------------------------------

FEATURE_NAMES = (
    "down", "distance", "yardsToGoal", "secondsRemaining",
    "scoreDifferential", "offenseTimeouts", "defenseTimeouts",
)


def clock_seconds(clock: Any) -> int | None:
    if isinstance(clock, dict):
        m, s = clock.get("minutes"), clock.get("seconds")
        if _num(m) and _num(s):
            return int(m) * 60 + int(s)
    return None


def seconds_remaining_in_half(play: dict) -> int | None:
    period = play.get("period")
    c = clock_seconds(play.get("clock"))
    if period not in (1, 2, 3, 4) or c is None or c < 0 or c > 900:
        return None
    return c + (900 if period in (1, 3) else 0)


def extract_features(play: dict) -> dict[str, float] | None:
    down = play.get("down")
    distance, ytg = play.get("distance"), play.get("yardsToGoal")
    off_score, def_score = play.get("offenseScore"), play.get("defenseScore")
    sec = seconds_remaining_in_half(play)
    if down not in (1, 2, 3, 4) or not _num(distance) or not _num(ytg):
        return None
    if not _num(off_score) or not _num(def_score) or sec is None:
        return None
    off_to, def_to = play.get("offenseTimeouts"), play.get("defenseTimeouts")
    return {
        "down": float(down),
        "distance": float(distance),
        "yardsToGoal": float(ytg),
        "secondsRemaining": float(sec),
        "scoreDifferential": float(off_score) - float(def_score),
        "offenseTimeouts": float(off_to) if _num(off_to) else 3.0,
        "defenseTimeouts": float(def_to) if _num(def_to) else 3.0,
    }


class NextScoreGBT:
    """Multinomial EP model: P(next score class | state) via
    HistGradientBoostingClassifier, then EP(state) = sum_c P(c) * avg_points(c).
    avg_points is the empirical per-class average FROM THE TRAINING SET ONLY
    (e.g. real TD value averages under 7 once missed/blocked PATs and failed
    2-point tries are folded in -- not assumed).

    early_stopping=True + a fatal check on whether it actually triggered
    mirrors drive_outcome_model.py's "a ConvergenceWarning is fatal"
    discipline -- this should never silently report scores from a model that
    ran out of iterations without its validation loss plateauing.
    """

    def __init__(self, **hgb_kwargs):
        defaults = dict(
            max_iter=1000, max_leaf_nodes=31, early_stopping=True,
            validation_fraction=0.15, n_iter_no_change=15,
            random_state=0,
        )
        defaults.update(hgb_kwargs)
        self._max_iter = defaults["max_iter"]
        self._kwargs = defaults
        self.clf = None
        self.classes_: list[str] = []
        self.avg_points: dict[str, float] = {}

    def fit(self, examples) -> "NextScoreGBT":
        from sklearn.ensemble import HistGradientBoostingClassifier

        rows, y = [], []
        pts_by_class: dict[str, list[float]] = defaultdict(list)
        for play, cls, pts, _scored_by in examples:
            feats = extract_features(play)
            if feats is None:
                continue
            rows.append([feats[f] for f in FEATURE_NAMES])
            y.append(cls)
            pts_by_class[cls].append(pts)
        if not rows:
            raise ValueError("no eligible training examples")

        import numpy as np

        X = np.asarray(rows, dtype=float)
        y_arr = np.asarray(y)
        self.clf = HistGradientBoostingClassifier(**self._kwargs)
        self.clf.fit(X, y_arr)

        if self.clf.n_iter_ >= self._max_iter:
            raise RuntimeError(
                f"NextScoreGBT hit max_iter={self._max_iter} without early stopping "
                f"triggering (n_iter_={self.clf.n_iter_}) -- the model may still be "
                "improving; raise max_iter and refit rather than trust this fit."
            )

        self.classes_ = list(self.clf.classes_)
        self.avg_points = {cls: (sum(v) / len(v) if v else 0.0) for cls, v in pts_by_class.items()}
        return self

    def predict_proba(self, play: dict):
        feats = extract_features(play)
        if feats is None or self.clf is None:
            return None
        import numpy as np

        x = np.asarray([[feats[f] for f in FEATURE_NAMES]], dtype=float)
        return dict(zip(self.classes_, self.clf.predict_proba(x)[0].tolist()))

    def predict(self, play: dict) -> float | None:
        """EP(state) -- same .predict() shape as epa_v1_research's models,
        so play_epa_v2-style transition logic can be reused unchanged."""
        probs = self.predict_proba(play)
        if probs is None:
            return None
        return sum(p * self.avg_points.get(cls, 0.0) for cls, p in probs.items())

    def batch_predict(self, plays: list[dict]) -> "PrecomputedGBT":
        """Precompute predict()/predict_proba() for many plays with ONE
        HistGradientBoostingClassifier.predict_proba(X) call instead of one
        Python-level call per row -- at 150K+ rows/fold the per-call overhead
        (array construction, dict work) dominates. Returns a thin lookup
        wrapper with the same .predict()/.predict_proba() shape, keyed by
        object identity, so callers (play_epa_v2, classification_diagnostics)
        need no changes -- just pass the SAME play dict objects back in."""
        import numpy as np

        idxs, rows = [], []
        for i, p in enumerate(plays):
            feats = extract_features(p)
            if feats is not None:
                idxs.append(i)
                rows.append([feats[f] for f in FEATURE_NAMES])

        ep_by_id: dict[int, float] = {}
        proba_by_id: dict[int, dict] = {}
        if rows:
            X = np.asarray(rows, dtype=float)
            proba = self.clf.predict_proba(X)
            for j, i in enumerate(idxs):
                p = plays[i]
                probs = dict(zip(self.classes_, proba[j].tolist()))
                proba_by_id[id(p)] = probs
                ep_by_id[id(p)] = sum(pr * self.avg_points.get(c, 0.0) for c, pr in probs.items())
        return PrecomputedGBT(ep_by_id, proba_by_id)


class PrecomputedGBT:
    """Lookup-only stand-in for NextScoreGBT, backed by a precomputed batch
    of predictions keyed by object identity. See NextScoreGBT.batch_predict."""

    def __init__(self, ep_by_id: dict[int, float], proba_by_id: dict[int, dict]):
        self._ep = ep_by_id
        self._proba = proba_by_id
        self.classes_ = list({c for probs in proba_by_id.values() for c in probs})

    def predict(self, play: dict) -> float | None:
        return self._ep.get(id(play))

    def predict_proba(self, play: dict):
        return self._proba.get(id(play))
