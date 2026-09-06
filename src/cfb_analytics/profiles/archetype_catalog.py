"""Deterministic 2,000-name college-football archetype ontology.

Each candidate name carries a target profile over v3 opponent-adjusted team-state
attributes.  The catalog is a naming/search space, not 2,000 forced classes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

CATALOG_VERSION = "cfb-archetype-catalog-v1-2000"

# All targets live on a 0..100 scale except signed gaps/fit, which live on -100..100.
ATTR_RANGES: dict[str, float] = {
    "identity_rushing_attack": 100.0,
    "identity_passing_attack": 100.0,
    "identity_rushing_defense": 100.0,
    "identity_passing_defense": 100.0,
    "identity_offense_quality": 100.0,
    "identity_defense_quality": 100.0,
    "rush_rate": 100.0,
    "plays_per_possession": 100.0,
    "identity_explosive_vs_methodical": 200.0,
    "identity_offense_vs_defense": 200.0,
    "identity_run_vs_pass_off": 200.0,
    "identity_run_vs_pass_def": 200.0,
    "identity_predictability": 100.0,
    "identity_one_dimensionality": 100.0,
    "identity_playcalling_fit": 200.0,
    "identity_scheme_constraint": 100.0,
}


@dataclass(frozen=True)
class ArchetypeRoot:
    family: str
    name: str
    targets: Mapping[str, float]
    weights: Mapping[str, float]


@dataclass(frozen=True)
class ArchetypeCandidate:
    id: str
    family: str
    name: str
    root_name: str
    modifier: str | None
    targets: Mapping[str, float]
    weights: Mapping[str, float]


def _r(family: str, name: str, **targets: float) -> ArchetypeRoot:
    return ArchetypeRoot(family, name, targets, {k: 1.0 for k in targets})


ROOTS: tuple[ArchetypeRoot, ...] = (
    # Whole-team balance / imbalance.
    _r("whole_team", "Complete Team", identity_offense_quality=82, identity_defense_quality=82, identity_offense_vs_defense=0),
    _r("whole_team", "Offense First", identity_offense_quality=82, identity_defense_quality=48, identity_offense_vs_defense=34),
    _r("whole_team", "Defense First", identity_offense_quality=48, identity_defense_quality=82, identity_offense_vs_defense=-34),
    _r("whole_team", "Defense or Bust", identity_offense_quality=28, identity_defense_quality=84, identity_offense_vs_defense=-56),
    _r("whole_team", "Outscore the Problem", identity_offense_quality=86, identity_defense_quality=25, identity_offense_vs_defense=61),
    _r("whole_team", "Paper Tiger", identity_offense_quality=72, identity_defense_quality=35),
    _r("whole_team", "Sleeping Giant", identity_offense_quality=58, identity_defense_quality=58),
    _r("whole_team", "One-Sided Contender", identity_offense_vs_defense=48, identity_offense_quality=78),
    # Run offense.
    _r("run_offense", "Ground & Pound", identity_rushing_attack=78, identity_passing_attack=48, rush_rate=80, plays_per_possession=65),
    _r("run_offense", "Run or Die", identity_rushing_attack=70, identity_passing_attack=22, rush_rate=90, identity_one_dimensionality=55),
    _r("run_offense", "Trench Warfare", identity_rushing_attack=84, rush_rate=88, identity_predictability=72, plays_per_possession=72),
    _r("run_offense", "Power Spread", identity_rushing_attack=82, identity_passing_attack=62, rush_rate=72, identity_run_vs_pass_off=20),
    _r("run_offense", "Possession Vampire", identity_rushing_attack=80, rush_rate=84, plays_per_possession=88, identity_predictability=68),
    _r("run_offense", "Three Yards and a Cloud", identity_rushing_attack=48, identity_passing_attack=28, rush_rate=90, identity_explosive_vs_methodical=-30),
    _r("run_offense", "Run to Set Up the Bomb", identity_rushing_attack=76, identity_passing_attack=66, rush_rate=78, identity_explosive_vs_methodical=28),
    _r("run_offense", "Run Into a Wall", identity_rushing_attack=22, identity_passing_attack=20, rush_rate=88, identity_scheme_constraint=76),
    # Pass offense.
    _r("pass_offense", "Air It Out", identity_passing_attack=82, identity_rushing_attack=45, rush_rate=20, identity_run_vs_pass_off=-38),
    _r("pass_offense", "Air Raid", identity_passing_attack=84, rush_rate=15, identity_predictability=72, identity_explosive_vs_methodical=8),
    _r("pass_offense", "Bombs Away", identity_passing_attack=80, rush_rate=20, identity_explosive_vs_methodical=42),
    _r("pass_offense", "Quick Game Machine", identity_passing_attack=78, rush_rate=24, identity_explosive_vs_methodical=-28, plays_per_possession=70),
    _r("pass_offense", "Pass to Control", identity_passing_attack=80, rush_rate=22, plays_per_possession=82, identity_explosive_vs_methodical=-18),
    _r("pass_offense", "YAC Factory", identity_passing_attack=82, identity_explosive_vs_methodical=18, plays_per_possession=68),
    _r("pass_offense", "Sling and Pray", identity_passing_attack=30, rush_rate=15, identity_predictability=78, identity_scheme_constraint=72),
    _r("pass_offense", "Broken Passing Game", identity_passing_attack=12, identity_rushing_attack=55, identity_one_dimensionality=50, identity_scheme_constraint=72),
    # Efficiency / explosiveness.
    _r("offensive_shape", "Death by a Thousand Cuts", identity_offense_quality=82, identity_explosive_vs_methodical=-38, plays_per_possession=84),
    _r("offensive_shape", "Metronome", identity_offense_quality=78, identity_explosive_vs_methodical=-18, plays_per_possession=74),
    _r("offensive_shape", "Home Run Hunter", identity_offense_quality=68, identity_explosive_vs_methodical=48),
    _r("offensive_shape", "Boom or Bust", identity_offense_quality=52, identity_explosive_vs_methodical=58, identity_predictability=56),
    _r("offensive_shape", "Efficient but Toothless", identity_offense_quality=66, identity_explosive_vs_methodical=-52),
    _r("offensive_shape", "Pretty but Empty", identity_offense_quality=58, identity_explosive_vs_methodical=25),
    _r("offensive_shape", "Stuck in Mud", identity_offense_quality=20, identity_explosive_vs_methodical=-35, plays_per_possession=35),
    _r("offensive_shape", "Three-and-Out Factory", identity_offense_quality=12, plays_per_possession=12),
    # Scheme/playcalling.
    _r("scheme", "Predictable Grinder", rush_rate=86, identity_predictability=82, identity_scheme_constraint=58),
    _r("scheme", "Constraint Master", identity_playcalling_fit=42, identity_scheme_constraint=12, identity_predictability=40),
    _r("scheme", "Tendency Breaker", identity_predictability=18, identity_one_dimensionality=18),
    _r("scheme", "Playcalling Prison", identity_predictability=82, identity_scheme_constraint=84, identity_playcalling_fit=-28),
    _r("scheme", "Identity Crisis", identity_playcalling_fit=-18, identity_one_dimensionality=12, identity_offense_quality=30),
    _r("scheme", "Talent Over Scheme", identity_offense_quality=82, identity_playcalling_fit=-12),
    _r("scheme", "Scheme Over Talent", identity_offense_quality=52, identity_playcalling_fit=38, identity_scheme_constraint=15),
    _r("scheme", "Conservative Caller", rush_rate=72, identity_explosive_vs_methodical=-25, identity_predictability=62),
    # Run defense.
    _r("run_defense", "Run Wall", identity_rushing_defense=88, identity_passing_defense=62, identity_run_vs_pass_def=26),
    _r("run_defense", "Interior Fortress", identity_rushing_defense=90, identity_defense_quality=78),
    _r("run_defense", "Run Funnel", identity_rushing_defense=30, identity_passing_defense=82, identity_run_vs_pass_def=-52),
    _r("run_defense", "Open Highway", identity_rushing_defense=12, identity_passing_defense=52, identity_run_vs_pass_def=-40),
    # Pass defense.
    _r("pass_defense", "No Fly Zone", identity_passing_defense=90, identity_rushing_defense=65, identity_run_vs_pass_def=-25),
    _r("pass_defense", "Coverage Blanket", identity_passing_defense=85, identity_defense_quality=78),
    _r("pass_defense", "Pass Funnel", identity_passing_defense=28, identity_rushing_defense=84, identity_run_vs_pass_def=56),
    _r("pass_defense", "Open Skies", identity_passing_defense=12, identity_rushing_defense=52, identity_run_vs_pass_def=40),
    # Defensive philosophy.
    _r("defense", "Brick Wall", identity_rushing_defense=86, identity_passing_defense=86, identity_defense_quality=88),
    _r("defense", "Rock Fight", identity_defense_quality=86, identity_offense_quality=32, plays_per_possession=42),
    _r("defense", "Bend Don't Break", identity_defense_quality=72, identity_passing_defense=66, identity_rushing_defense=66),
    _r("defense", "Paper Wall", identity_defense_quality=18, identity_rushing_defense=25, identity_passing_defense=25),
    _r("defense", "Defense in Name Only", identity_defense_quality=8),
    # Tempo / possession.
    _r("tempo", "All Gas", plays_per_possession=35, identity_offense_quality=72, identity_explosive_vs_methodical=24),
    _r("tempo", "Slow Cooker", plays_per_possession=82, identity_explosive_vs_methodical=-24),
    _r("tempo", "Clock Eater", plays_per_possession=88, rush_rate=82),
    _r("tempo", "Possession Roulette", plays_per_possession=35, identity_offense_quality=50),
    # Bad / survival builds.
    _r("survival", "Searching for Answers", identity_offense_quality=15, identity_defense_quality=25),
    _r("survival", "Field Goal Dependency", identity_offense_quality=36, identity_explosive_vs_methodical=-32),
    _r("survival", "Punt Merchant", identity_offense_quality=12, plays_per_possession=22),
    _r("survival", "No Easy Yards", identity_offense_quality=30, identity_explosive_vs_methodical=-44),
    _r("survival", "Low Ceiling", identity_offense_quality=32, identity_defense_quality=48),
    _r("survival", "Ugly but Effective", identity_offense_quality=66, identity_defense_quality=72, identity_explosive_vs_methodical=-35),
)


# Modifiers alter an existing football identity rather than creating arbitrary prose.
MODIFIERS: tuple[tuple[str, Mapping[str, float]], ...] = (
    ("Elite", {"identity_offense_quality": 15, "identity_defense_quality": 15}),
    ("Strong", {"identity_offense_quality": 8, "identity_defense_quality": 8}),
    ("Limited", {"identity_offense_quality": -18}),
    ("Broken", {"identity_offense_quality": -30}),
    ("Explosive", {"identity_explosive_vs_methodical": 28}),
    ("Methodical", {"identity_explosive_vs_methodical": -28, "plays_per_possession": 12}),
    ("Volatile", {"identity_explosive_vs_methodical": 22, "identity_predictability": 12}),
    ("Stable", {"identity_explosive_vs_methodical": -10, "identity_scheme_constraint": -12}),
    ("Aggressive", {"identity_explosive_vs_methodical": 18}),
    ("Conservative", {"identity_explosive_vs_methodical": -22, "rush_rate": 10}),
    ("Predictable", {"identity_predictability": 22, "identity_scheme_constraint": 12}),
    ("Adaptive", {"identity_predictability": -18, "identity_playcalling_fit": 16}),
    ("Physical", {"identity_rushing_attack": 12, "identity_rushing_defense": 12}),
    ("Finesse", {"identity_passing_attack": 12, "identity_passing_defense": 8, "rush_rate": -12}),
    ("Run-Leaning", {"rush_rate": 18, "identity_rushing_attack": 8}),
    ("Pass-Leaning", {"rush_rate": -18, "identity_passing_attack": 8}),
    ("Defense-Led", {"identity_defense_quality": 18, "identity_offense_vs_defense": -25}),
    ("Offense-Led", {"identity_offense_quality": 18, "identity_offense_vs_defense": 25}),
    ("High-Floor", {"identity_offense_quality": 8, "identity_scheme_constraint": -10}),
    ("Low-Floor", {"identity_offense_quality": -12, "identity_scheme_constraint": 12}),
    ("High-Ceiling", {"identity_explosive_vs_methodical": 20, "identity_offense_quality": 8}),
    ("Low-Ceiling", {"identity_explosive_vs_methodical": -24, "identity_offense_quality": -8}),
    ("Efficient", {"identity_offense_quality": 14}),
    ("Inefficient", {"identity_offense_quality": -18}),
    ("Possession", {"plays_per_possession": 18, "rush_rate": 8}),
    ("Chaos", {"identity_explosive_vs_methodical": 18, "identity_predictability": -8}),
    ("Control", {"plays_per_possession": 14, "identity_explosive_vs_methodical": -16}),
    ("One-Dimensional", {"identity_one_dimensionality": 24, "identity_scheme_constraint": 18}),
    ("Balanced", {"identity_one_dimensionality": -20, "identity_predictability": -12}),
    ("Miscast", {"identity_playcalling_fit": -30, "identity_scheme_constraint": 20}),
    ("Well-Fit", {"identity_playcalling_fit": 30, "identity_scheme_constraint": -15}),
    ("Run-Dependent", {"rush_rate": 22, "identity_run_vs_pass_off": 28}),
    ("Pass-Dependent", {"rush_rate": -22, "identity_run_vs_pass_off": -28}),
)


def _clip(key: str, value: float) -> float:
    if key.startswith("identity_") and key in {
        "identity_explosive_vs_methodical", "identity_offense_vs_defense",
        "identity_run_vs_pass_off", "identity_run_vs_pass_def", "identity_playcalling_fit",
    }:
        return max(-100.0, min(100.0, value))
    return max(0.0, min(100.0, value))


def _modified(root: ArchetypeRoot, modifier: str, deltas: Mapping[str, float]) -> ArchetypeCandidate:
    targets = dict(root.targets)
    for key, delta in deltas.items():
        base = targets.get(key, 50.0 if key not in {"identity_offense_vs_defense", "identity_run_vs_pass_off", "identity_run_vs_pass_def", "identity_playcalling_fit", "identity_explosive_vs_methodical"} else 0.0)
        targets[key] = _clip(key, base + float(delta))
    weights = dict(root.weights)
    for key in deltas:
        weights.setdefault(key, 0.75)
    return ArchetypeCandidate("", root.family, f"{modifier} {root.name}", root.name, modifier, targets, weights)


def build_catalog(limit: int = 2000) -> tuple[ArchetypeCandidate, ...]:
    if limit < 1:
        raise ValueError("limit must be positive")
    out: list[ArchetypeCandidate] = []
    seen: set[str] = set()
    for root in ROOTS:
        if root.name not in seen:
            out.append(ArchetypeCandidate("", root.family, root.name, root.name, None, dict(root.targets), dict(root.weights)))
            seen.add(root.name)
    modifier_round = 0
    while len(out) < limit:
        modifier, deltas = MODIFIERS[modifier_round % len(MODIFIERS)]
        for root in ROOTS:
            name = f"{modifier} {root.name}"
            if name in seen or modifier.lower() in root.name.lower():
                continue
            out.append(_modified(root, modifier, deltas))
            seen.add(name)
            if len(out) >= limit:
                break
        modifier_round += 1
        if modifier_round > len(MODIFIERS) * 3 and len(out) < limit:
            # Deterministic compound modifiers extend the vocabulary while keeping
            # every candidate tied to two explicit attribute adjustments.
            i = (modifier_round - len(MODIFIERS) * 3 - 1) % len(MODIFIERS)
            j = (i + 7) % len(MODIFIERS)
            ma, da = MODIFIERS[i]; mb, db = MODIFIERS[j]
            for root in ROOTS:
                name = f"{ma} {mb} {root.name}"
                if name in seen:
                    continue
                merged = dict(da)
                for key, value in db.items():
                    merged[key] = merged.get(key, 0.0) + float(value)
                out.append(_modified(root, f"{ma} {mb}", merged))
                seen.add(name)
                if len(out) >= limit:
                    break
        if modifier_round > 500:
            raise RuntimeError("unable to generate requested catalog size")
    numbered = []
    for i, candidate in enumerate(out[:limit], 1):
        numbered.append(ArchetypeCandidate(
            f"A{i:04d}", candidate.family, candidate.name, candidate.root_name,
            candidate.modifier, candidate.targets, candidate.weights,
        ))
    return tuple(numbered)


CATALOG = build_catalog(2000)
