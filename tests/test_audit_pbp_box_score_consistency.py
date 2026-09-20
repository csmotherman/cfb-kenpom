"""Regression tests for the PBP vs. official-box-score audit
(scripts/audit_pbp_box_score_consistency.py).

Fixtures are built by running realistic raw-CFBD-shaped play dicts through
`normalize_play`, the same function the production canonicalization pipeline
uses -- not hand-built canonical dicts -- so these tests exercise the real
taxonomy in canonical/play_types.py, not a reimplementation of it. Several
fixtures are lightly-edited real examples pulled from the 2025/2026 corpus
during the audit (see comments); they are not invented toy strings.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from cfb_analytics.canonical.plays import normalize_play  # noqa: E402
from cfb_analytics.analytics.turnover_forensics import (  # noqa: E402
    classify_drive_turnover_from_plays,
)

from audit_pbp_box_score_consistency import (  # noqa: E402
    reconstruct_rush_pass,
    duplicate_play_ids,
    classify_drive_turnover_scoped_from_plays,
    _effective_subtype,
    RUSH_SUBTYPES,
)


def play(play_type, play_text, offense="Home", defense="Away", **overrides):
    row = {
        "gameId": "g1", "driveId": "d1", "id": "p1", "driveNumber": 1, "playNumber": 1,
        "offense": offense, "defense": defense, "period": 1,
        "clock": {"minutes": 10, "seconds": 0}, "down": 1, "distance": 10, "yardsToGoal": 50,
        "yardsGained": 0, "scoring": False, "playType": play_type, "playText": play_text,
        "ppa": None, "offenseScore": 0, "defenseScore": 0, "wallclock": "2026-01-01T00:00:00.000Z",
    }
    row.update(overrides)
    return normalize_play(row)


def game_of(*plays):
    return list(plays)


def recon(plays_for_game, team="Home"):
    return reconstruct_rush_pass(plays_for_game, team, "analyticsYardsGained", text_inference=True)


# --------------------------------------------------------------------------
# Basic offensive plays
# --------------------------------------------------------------------------

def test_normal_rush_counts_as_rush_attempt():
    p = play("Rush", "J.Smith run for 4 yds to the H45", yardsGained=4, down=1, distance=10)
    r = recon(game_of(p))
    assert r["rush_attempts_sackAsRush"] == 1
    assert r["rush_yards_sackAsRush"] == 4
    assert r["pass_attempts_sackAsRush"] == 0


def test_normal_completion_counts_as_pass_attempt_and_completion():
    p = play("Pass Reception", "J.Smith pass complete to T.Jones for 12 yards", yardsGained=12)
    r = recon(game_of(p))
    assert r["pass_attempts_sackAsRush"] == 1
    assert r["completions"] == 1
    assert r["net_pass_yards_sackAsRush"] == 12


def test_incompletion_counts_as_attempt_not_completion():
    p = play("Pass Incompletion", "J.Smith pass incomplete short right", yardsGained=0)
    r = recon(game_of(p))
    assert r["pass_attempts_sackAsRush"] == 1
    assert r["completions"] == 0


def test_touchdown_counts_in_correct_bucket():
    rush_td = play("Rushing Touchdown", "J.Smith run for 5 yds TOUCHDOWN", yardsGained=5, down=1, distance=5)
    pass_td = play("Passing Touchdown", "J.Smith pass complete TOUCHDOWN", yardsGained=20)
    r = recon(game_of(rush_td, pass_td))
    assert r["rush_attempts_sackAsRush"] == 1
    assert r["pass_attempts_sackAsRush"] == 1
    assert r["completions"] == 1


# --------------------------------------------------------------------------
# Sack / scramble convention (empirically validated: NCAA box scores treat
# sacks as rushing plays with a loss, not pass attempts -- see summary.json
# sackConvention, winner="sackAsRush" for all 4 convention-dependent stats).
# --------------------------------------------------------------------------

def test_sack_counts_as_rush_attempt_not_pass_attempt():
    p = play("Sack", "J.Smith sacked for a loss of 7 yards", yardsGained=-7, down=2, distance=8)
    r = recon(game_of(p))
    assert r["rush_attempts_sackAsRush"] == 1
    assert r["rush_yards_sackAsRush"] == -7
    assert r["pass_attempts_sackAsRush"] == 0
    assert r["sacks"] == 1


def test_scramble_is_a_plain_rush_not_a_dropback():
    # CFBD records a scramble as playType "Rush" -- there is no separate
    # "scramble" playType. It is indistinguishable from a called run in the
    # structured feed and correctly counts as a rush attempt.
    p = play("Rush", "J.Smith run for 15 yds (scramble)", yardsGained=15)
    r = recon(game_of(p))
    assert r["rush_attempts_sackAsRush"] == 1


# --------------------------------------------------------------------------
# Kneels / spikes -- validated NOT to be excluded (corpus test: excluding
# kneels from rush attempts made only 5/116 kneel-containing team-games match
# the official box score better; most kneel-tagged mismatches had a
# different real cause). Kneels and spikes count like any other rush/pass.
# --------------------------------------------------------------------------

def test_kneel_counts_as_rush_attempt():
    p = play("Rush", "J.Smith kneels for a loss of 1 yard", yardsGained=-1, down=1, distance=10)
    r = recon(game_of(p))
    assert r["rush_attempts_sackAsRush"] == 1
    assert r["rush_yards_sackAsRush"] == -1


def test_spike_counts_as_pass_attempt_incompletion():
    p = play("Pass Incompletion", "J.Smith spiked the ball to stop the clock", yardsGained=0)
    r = recon(game_of(p))
    assert r["pass_attempts_sackAsRush"] == 1
    assert r["completions"] == 0


# --------------------------------------------------------------------------
# Turnovers
# --------------------------------------------------------------------------

def test_interception_counts_as_pass_attempt_and_turnover_signal():
    p = play("Interception", "J.Smith pass intercepted by #7 D.Cook", yardsGained=0, down=3, distance=9)
    r = recon(game_of(p))
    assert r["pass_attempts_sackAsRush"] == 1
    assert p["eventSubtype"] == "INTERCEPTION"
    assert p["isTurnover"] is True


def test_fumble_lost_recovers_underlying_rush_via_text_inference():
    # Real corpus example (2026 wk1, TCU @ UNC, game 401856766): CFBD files
    # the ENTIRE snap under playType "Fumble Recovery (Own)" even though the
    # play text shows a sack, and under "Fumble Recovery (Opponent)"-style
    # rows the underlying play is similarly swallowed. Structured playType
    # alone would drop these from rush/pass/sack counting entirely.
    p = play(
        "Fumble Recovery (Opponent)",
        "J.Craig sacked for loss of 9 yards to the H31, fumble by J.Craig recovered by AWAY #11 J.Harvey at H31",
        yardsGained=-9, down=2, distance=24,
    )
    assert p["eventSubtype"] == "FUMBLE_RECOVERY_OPPONENT"
    r = recon(game_of(p))
    assert r["sacks"] == 1
    assert r["rush_attempts_sackAsRush"] == 1  # sack -> rush bucket under sackAsRush convention
    assert r["rush_yards_sackAsRush"] == -9


def test_fumble_recovered_by_offense_still_counts_the_underlying_rush():
    # Real corpus pattern: "Fumble Recovery (Own)" where the offense keeps
    # the ball -- not a turnover, but the rush attempt underneath it still
    # happened and must still be counted.
    p = play(
        "Fumble Recovery (Own)",
        "J.Craig rush middle for 1 yard loss to the H41 fumbled by J.Craig recovered by HOME #1 J.Craig at H41",
        yardsGained=-1, down=1, distance=10,
    )
    r = recon(game_of(p))
    assert r["rush_attempts_sackAsRush"] == 1
    assert r["rush_yards_sackAsRush"] == -1


def test_safety_recovers_underlying_rush_with_negative_yards():
    # Real corpus example (2026 wk1, game 401856766): a rush tackled in the
    # endzone is filed under playType "Safety", not "Rush".
    p = play(
        "Safety",
        "T.TEAM rush middle for 31 yards loss to the H00, End Of Play. AWAY SAFETY",
        yardsGained=-31, down=4, distance=9,
    )
    assert p["eventSubtype"] == "SAFETY"
    r = recon(game_of(p))
    assert r["rush_attempts_sackAsRush"] == 1
    assert r["rush_yards_sackAsRush"] == -31


# --------------------------------------------------------------------------
# Penalties
# --------------------------------------------------------------------------

def test_no_play_penalty_excludes_the_underlying_snap():
    p = play(
        "Penalty",
        "J.Smith run for 6 yards PENALTY HOME Holding 10 yards from H44 to H34. NO PLAY",
        yardsGained=10, down=2, distance=10,
    )
    assert p["hasNoPlayContext"] is True
    r = recon(game_of(p))
    assert r["rush_attempts_sackAsRush"] == 0
    assert r["pass_attempts_sackAsRush"] == 0


def test_accepted_penalty_without_no_play_text_keeps_underlying_play_type():
    # A penalty enforced on a play that still stands (no "NO PLAY" marker)
    # keeps its real playType and should still count as an attempt.
    p = play("Rush", "J.Smith run for 20 yds PENALTY AWAY Facemask 15 yards enforced", yardsGained=20, down=1, distance=10)
    assert p.get("hasNoPlayContext", False) is False
    r = recon(game_of(p))
    assert r["rush_attempts_sackAsRush"] == 1


def test_declined_penalty_keeps_underlying_play_and_yardage():
    p = play("Pass Reception", "J.Smith pass complete for 8 yards PENALTY HOME Offside declined", yardsGained=8)
    r = recon(game_of(p))
    assert r["pass_attempts_sackAsRush"] == 1
    assert r["net_pass_yards_sackAsRush"] == 8


# --------------------------------------------------------------------------
# Replay reversal
# --------------------------------------------------------------------------

def test_replay_reversal_context_flagged_but_play_still_counts():
    # Real corpus example (2026 wk1, West Georgia @ Arkansas State,
    # game 401868241): an interception under review that was upheld.
    p = play(
        "Interception",
        "J.Smith pass intercepted by #23 R.Stevens. The previous play is under automatic review - \"Interception\". CALL UPHELD",
        yardsGained=0, down=1, distance=10,
    )
    assert p["hasReviewContext"] is True
    r = recon(game_of(p))
    assert r["pass_attempts_sackAsRush"] == 1


# --------------------------------------------------------------------------
# Two-point attempts, special teams
# --------------------------------------------------------------------------

def test_two_point_attempts_excluded_from_pass_and_rush_attempts():
    two_pt_pass = play("Two Point Pass", "J.Smith pass complete for two-point conversion", yardsGained=2)
    two_pt_rush = play("Two Point Rush", "J.Smith run for two-point conversion", yardsGained=2)
    r = recon(game_of(two_pt_pass, two_pt_rush))
    assert r["pass_attempts_sackAsRush"] == 0
    assert r["rush_attempts_sackAsRush"] == 0
    assert r["two_point_count"] == 2


def test_special_teams_plays_are_not_offensive_scrimmage_plays():
    punt = play("Punt", "#48 J.Chance punt 40 yards to the H09", yardsGained=0)
    kickoff = play("Kickoff", "#48 J.Chance kickoff 65 yards, Touchback", yardsGained=0)
    fg = play("Field Goal Good", "#34 K.Kicker field goal attempt from 31 yards GOOD", yardsGained=0)
    r = recon(game_of(punt, kickoff, fg))
    assert r["total_plays"] == 0


# --------------------------------------------------------------------------
# Duplicate plays (source data-quality bug -- see README "KNOWN BUG":
# duplicate_play_ids() requires driveId + wallclock + content to all match,
# which correctly rejects two genuinely different plays that merely share
# identical generic text, e.g. two separate "run for 3 yds" plays.)
# --------------------------------------------------------------------------

def test_duplicate_play_ids_detects_same_instant_duplicate():
    # Real corpus pattern (2025 wk8, Marshall @ Texas State, game 401761632):
    # a kickoff recorded twice with different play ids, same driveId and
    # wallclock.
    p1 = play("Kickoff", "L.Quinn kickoff for 65 yds for a touchback", id="id1", wallclock="2025-10-18T19:34:43.000Z")
    p2 = play("Kickoff", "L.Quinn kickoff for 65 yds for a touchback", id="id2", wallclock="2025-10-18T19:34:43.000Z", playNumber=2)
    dup_ids = duplicate_play_ids(game_of(p1, p2))
    assert dup_ids == {"id2"}


def test_duplicate_play_ids_does_not_flag_coincidentally_identical_text():
    # Same generic text, different drive and different wallclock -- a real,
    # distinct play, not a duplicate. (This is the case that made a looser
    # text-only dedup key unsafe during the audit.)
    p1 = play("Rush", "A.Roberts run for 3 yds to the H40", id="id1", driveId="d1", wallclock="2025-10-18T19:34:00.000Z")
    p2 = play("Rush", "A.Roberts run for 3 yds to the H40", id="id2", driveId="d2", wallclock="2025-10-18T20:18:00.000Z")
    dup_ids = duplicate_play_ids(game_of(p1, p2))
    assert dup_ids == set()


# --------------------------------------------------------------------------
# Turnover no-play-scope bug (production cfb_analytics.analytics
# .turnover_forensics.classify_drive_turnover_from_plays computes its
# no-play signal across the WHOLE drive; an unrelated no-play penalty
# earlier in the drive wrongly nullifies a clean turnover later in it).
# Corpus check: 112/114 MODIFIED_CONTEXT_REVIEW exclusions in 2026 wk1-2
# were this false-positive pattern; only 2/114 were genuine same-play
# nullifications. This test is a regression fixture for that exact shape,
# built from the real West Georgia / Arkansas State drive (game 401868241,
# driveId 40186824110).
# --------------------------------------------------------------------------

def test_unrelated_no_play_penalty_incorrectly_nullifies_later_turnover_in_production():
    false_start = play("Penalty", "PENALTY HOME False Start 5 yards. NO PLAY", down=1, distance=10, playNumber=1)
    false_start["hasNoPlayContext"] = True
    clean_completion = play("Pass Reception", "J.Smith pass complete for 23 yards, 1ST DOWN", yardsGained=23, playNumber=2)
    fumble_return_td = play("Fumble Return Touchdown", "N.Player 68 Yd Fumble Return", yardsGained=0, playNumber=3)
    fumble_return_td["eventSubtype"] = "FUMBLE_RETURN_TD"
    fumble_return_td["isTurnover"] = True

    drive_plays = [false_start, clean_completion, fumble_return_td]

    # Production behavior: the drive-wide no-play signal (from the unrelated
    # false start) wrongly suppresses this clean fumble-lost turnover.
    assert classify_drive_turnover_from_plays(drive_plays) == "MODIFIED_CONTEXT_REVIEW"

    # Candidate fix: scoping the no-play check to the turnover-signal play
    # itself correctly classifies it as a real giveaway.
    assert classify_drive_turnover_scoped_from_plays(drive_plays) == "FUMBLE_LOST"


def test_no_play_directly_on_the_turnover_play_is_still_excluded_by_the_fix():
    # The fix must still exclude a turnover when the no-play penalty is ON
    # the turnover play itself -- only the false-positive (unrelated,
    # earlier-in-drive) case should be recovered.
    nullified_int = play("Interception", "J.Smith pass intercepted PENALTY AWAY Defensive Holding. NO PLAY", playNumber=1)
    nullified_int["hasNoPlayContext"] = True
    nullified_int["eventSubtype"] = "INTERCEPTION"
    drive_plays = [nullified_int]
    assert classify_drive_turnover_from_plays(drive_plays) == "MODIFIED_CONTEXT_REVIEW"
    assert classify_drive_turnover_scoped_from_plays(drive_plays) == "MODIFIED_CONTEXT_REVIEW"
