"""Dynamic team identity grammar v5.

Style describes how a team plays. Mechanism explains what drives that style.
Effectiveness determines whether strength language is earned. Structure describes
how the two units support the team. The final headline is composed dynamically
from those measured ideas rather than selected from a fixed archetype list.
"""
from __future__ import annotations

import math
from statistics import mean
from typing import Any

DYNAMIC_IDENTITY_VERSION = "dynamic-team-identity-v5-real-team-grammar-tuning"

CORE_SERIES_FIELDS = (
    "identity_offense_quality", "identity_defense_quality",
    "identity_rushing_attack", "identity_passing_attack",
    "identity_rushing_defense", "identity_passing_defense",
    "rush_rate", "plays_per_possession",
    "identity_explosive_vs_methodical", "identity_predictability",
    "identity_scheme_constraint", "identity_success_quality",
    "identity_explosiveness_quality", "identity_finishing_quality",
    "identity_third_down_quality",
)


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _quality_word(value: float | None) -> str:
    if value is None: return "Unknown"
    if value >= 90: return "Elite"
    if value >= 80: return "Excellent"
    if value >= 70: return "Strong"
    if value >= 60: return "Good"
    if value >= 45: return "Average"
    if value >= 30: return "Limited"
    return "Poor"


def _article(word: str) -> str:
    return "an" if word[:1].lower() in {"a", "e", "i", "o", "u"} else "a"


def _quality_phrase(value: float, noun: str) -> str:
    word = _quality_word(value).lower()
    return f"{_article(word)} {word} {noun}"


def _series_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"count": 0, "mean": None, "final": None, "min": None, "max": None,
                "slopePerSnapshot": None, "residualSd": None, "stabilityScore": None}
    n = len(values)
    avg = mean(values)
    if n == 1:
        slope = residual_sd = 0.0
    else:
        xbar = (n - 1) / 2.0
        denom = sum((i - xbar) ** 2 for i in range(n))
        slope = sum((i - xbar) * (v - avg) for i, v in enumerate(values)) / denom if denom else 0.0
        intercept = avg - slope * xbar
        residuals = [v - (intercept + slope * i) for i, v in enumerate(values)]
        residual_sd = math.sqrt(sum(r * r for r in residuals) / n)
    return {"count": n, "mean": avg, "final": values[-1], "min": min(values), "max": max(values),
            "slopePerSnapshot": slope, "residualSd": residual_sd,
            "stabilityScore": _clip(100.0 - 5.0 * residual_sd)}


def season_consistency(profiles: list[dict[str, float | None]]) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    for field in CORE_SERIES_FIELDS:
        values = [float(p[field]) for p in profiles
                  if isinstance(p.get(field), (int, float)) and not isinstance(p.get(field), bool)]
        out[field] = _series_stats(values)
    return out


def _usage(profile: dict[str, float | None]) -> str:
    rush = _number(profile.get("rush_rate"))
    if rush is None: return "balanced"
    if rush >= 80: return "run-heavy"
    if rush <= 20: return "pass-heavy"
    return "balanced"


def _pace_shape(profile: dict[str, float | None]) -> str:
    value = _number(profile.get("plays_per_possession"))
    if value is None: return "neutral"
    if value >= 75: return "long-drive"
    if value <= 25: return "quick-drive"
    return "neutral"


def _method(profile: dict[str, float | None]) -> str:
    value = _number(profile.get("identity_explosive_vs_methodical"))
    if value is None: return "neutral"
    if value <= -18: return "methodical"
    if value >= 18: return "explosive"
    return "neutral"


def _efficiency_shape(profile: dict[str, float | None]) -> str:
    success = _number(profile.get("identity_success_quality"))
    explosive = _number(profile.get("identity_explosiveness_quality"))
    if success is None or explosive is None: return "unknown"
    if success >= 75 and explosive >= 75: return "complete"
    if success >= 75 and explosive <= 55: return "efficient"
    if explosive >= 75 and success <= 55: return "boom-bust"
    if success >= 60 and explosive >= 60: return "balanced-efficient"
    if success < 45 and explosive < 45: return "stalled"
    return "mixed"


def _attack_balance(profile: dict[str, float | None]) -> str:
    run = _number(profile.get("identity_rushing_attack"))
    pas = _number(profile.get("identity_passing_attack"))
    if run is None or pas is None: return "unknown"
    if run - pas >= 18: return "run-driven"
    if pas - run >= 18: return "pass-driven"
    return "balanced"


def _commitment(profile: dict[str, float | None]) -> str:
    usage = _usage(profile)
    driver = _attack_balance(profile)
    run = _number(profile.get("identity_rushing_attack"))
    pas = _number(profile.get("identity_passing_attack"))
    if usage == "run-heavy" and driver == "pass-driven" and run is not None and pas is not None and pas - run >= 15:
        return "run-committed"
    if usage == "pass-heavy" and driver == "run-driven" and run is not None and pas is not None and run - pas >= 15:
        return "pass-committed"
    return "aligned"


def _structure(profile: dict[str, float | None]) -> str:
    off = _number(profile.get("identity_offense_quality"))
    defense = _number(profile.get("identity_defense_quality"))
    if off is None or defense is None: return "unknown"
    if off >= 80 and defense >= 80: return "two-way"
    # "Carried" is reserved for a genuinely poor partner unit. The carrying
    # unit need only be strong, not necessarily top-decile elite.
    if defense >= 70 and off < 45: return "defense-carried"
    if off >= 70 and defense < 45: return "offense-carried"
    gap = defense - off
    if gap >= 18 and defense >= 70: return "defense-supported"
    if gap <= -18 and off >= 70: return "offense-supported"
    if min(off, defense) >= 60: return "complementary"
    return "mixed"


def _effectiveness(profile: dict[str, float | None]) -> str:
    off = _number(profile.get("identity_offense_quality"))
    defense = _number(profile.get("identity_defense_quality"))
    success = _number(profile.get("identity_success_quality"))
    explosive = _number(profile.get("identity_explosiveness_quality"))
    finishing = _number(profile.get("identity_finishing_quality"))
    if off is None or defense is None: return "unknown"
    if min(off, defense) >= 80: return "power"
    if off >= 70 and success is not None and success >= 70:
        if explosive is not None and explosive >= 70: return "complete-offense"
        return "efficient-offense"
    if off >= 65 and explosive is not None and explosive >= 75: return "dangerous-attack"
    if defense >= 75 and _method(profile) == "methodical" and off >= 55: return "control"
    if finishing is not None and finishing >= 85 and off >= 55: return "finishing-driven"
    if max(off, defense) < 45: return "struggling"
    return "functional"


def _neutral_style_core(profile: dict[str, float | None]) -> str:
    usage = _usage(profile)
    method = _method(profile)
    efficiency = _efficiency_shape(profile)
    pace = _pace_shape(profile)
    if efficiency == "boom-bust": return "Boom-or-Bust"
    if efficiency == "complete" and usage == "balanced": return "Balanced Complete"
    if efficiency in {"efficient", "balanced-efficient"} and usage == "balanced": return "Balanced Efficiency"
    if method == "explosive" and usage == "run-heavy": return "Explosive Run-First"
    if method == "explosive" and usage == "pass-heavy": return "Explosive Pass-First"
    if method == "explosive": return "Quick-Strike"
    if method == "methodical" and usage == "run-heavy": return "Methodical Run-First"
    if method == "methodical" and usage == "pass-heavy": return "Methodical Pass-First"
    if method == "methodical" and pace == "long-drive": return "Methodical Possession"
    if method == "methodical": return "Methodical"
    if usage == "run-heavy": return "Run-First"
    if usage == "pass-heavy": return "Pass-First"
    if pace == "long-drive": return "Possession-Oriented"
    return "Balanced"


def _generic_secondary(profile: dict[str, float | None]) -> str | None:
    """Give otherwise-generic identities one honest secondary mechanism."""
    efficiency = _efficiency_shape(profile)
    driver = _attack_balance(profile)
    finishing = _number(profile.get("identity_finishing_quality"))
    structure = _structure(profile)
    if efficiency == "stalled": return "Low-Output"
    if finishing is not None and finishing >= 85: return "Finishing-Driven"
    if driver == "pass-driven": return "Pass-Driven"
    if driver == "run-driven": return "Run-Driven"
    if structure == "defense-supported": return "Defense-Supported"
    if structure == "offense-supported": return "Offense-Supported"
    return None


def _identity_name(profile: dict[str, float | None]) -> str:
    off = _number(profile.get("identity_offense_quality"))
    defense = _number(profile.get("identity_defense_quality"))
    if off is None or defense is None: return "Unresolved Team Identity"

    style = _neutral_style_core(profile)
    structure = _structure(profile)
    effectiveness = _effectiveness(profile)
    commitment = _commitment(profile)
    usage = _usage(profile)
    efficiency = _efficiency_shape(profile)

    if max(off, defense) < 45:
        if style == "Boom-or-Bust": return "Boom-or-Bust Struggler"
        if style.startswith("Explosive"): return f"{style} Struggler"
        if style.startswith("Methodical"): return f"{style} Survival"
        return "Searching for Answers" if style == "Balanced" else f"{style} Struggler"

    if commitment == "run-committed":
        if structure in {"defense-supported", "defense-carried"} and effectiveness == "control":
            return "Run-Committed Defensive Control"
        return "Run-Committed Football"
    if commitment == "pass-committed":
        if structure in {"defense-supported", "defense-carried"} and effectiveness == "control":
            return "Pass-Committed Defensive Control"
        return "Pass-Committed Football"

    if structure == "defense-carried":
        if efficiency == "stalled" and usage == "balanced": return "Defense-Carried Low-Output Balance"
        if _method(profile) == "methodical": return "Defense-Carried Methodical Football"
        if usage == "run-heavy": return "Defense-Carried Run-First Football"
        if usage == "pass-heavy": return "Defense-Carried Pass-First Football"
        return "Defense-Carried Balanced Football"

    if structure == "offense-carried":
        if effectiveness == "complete-offense":
            if usage == "run-heavy": return "Run-First Complete Offensive Carry"
            if usage == "pass-heavy": return "Pass-First Complete Offensive Carry"
            return "Complete Offensive Carry"
        if effectiveness == "dangerous-attack": return f"{style} Offensive Carry"
        return "Offense-Carried Football"

    if structure == "two-way" and effectiveness == "power":
        if efficiency in {"complete", "balanced-efficient", "efficient"}: return "Efficient Two-Way Power"
        return "Two-Way Power"

    if effectiveness == "control":
        if structure == "defense-supported":
            return "Methodical Defensive Control" if _method(profile) == "methodical" else "Defensive Control"
        if style == "Methodical Run-First": return "Methodical Ground Control"
        if style == "Methodical Pass-First": return "Methodical Air Control"
        return "Methodical Control"

    if effectiveness == "dangerous-attack":
        if usage == "run-heavy": return "Explosive Ground Attack"
        if usage == "pass-heavy": return "Quick-Strike Air Attack"
        return "Quick-Strike Attack"

    if effectiveness == "complete-offense":
        # Preserve extreme usage because a run-heavy and pass-heavy complete
        # offense should not collapse to the same headline.
        if usage == "run-heavy": return "Run-First Complete Attack"
        if usage == "pass-heavy": return "Pass-First Complete Attack"
        return "Balanced Complete Attack"

    if effectiveness == "efficient-offense":
        if usage == "run-heavy": return "Run-First Efficient Offense"
        if usage == "pass-heavy": return "Pass-First Efficient Offense"
        return "Balanced Efficiency"

    if effectiveness == "finishing-driven":
        return f"{style} Finishing Football"

    # Stalled is an outcome shape, so surface it when the identity would
    # otherwise sound healthier than the underlying offense actually was.
    if efficiency == "stalled":
        if usage == "run-heavy": return "Low-Output Run-First Football"
        if usage == "pass-heavy": return "Low-Output Pass-First Football"
        return "Low-Output Balanced Football"

    if structure == "defense-supported": return f"Defense-Supported {style} Football"
    if structure == "offense-supported": return f"Offense-Supported {style} Football"

    if style in {"Balanced", "Possession-Oriented"}:
        secondary = _generic_secondary(profile)
        if secondary:
            return f"{secondary} {style} Football"
    if style.endswith("Efficiency"): return style
    return f"{style} Football"


def _tags(profile, closing_form, consistency):
    tags: list[str] = []
    off = _number(profile.get("identity_offense_quality")); defense = _number(profile.get("identity_defense_quality"))
    rush = _number(profile.get("rush_rate")); method = _number(profile.get("identity_explosive_vs_methodical"))
    predict = _number(profile.get("identity_predictability")); run = _number(profile.get("identity_rushing_attack")); pas = _number(profile.get("identity_passing_attack"))
    success = _number(profile.get("identity_success_quality")); explosive = _number(profile.get("identity_explosiveness_quality")); finishing = _number(profile.get("identity_finishing_quality"))
    if rush is not None:
        if rush >= 80: tags.append("Run-Heavy")
        elif rush <= 20: tags.append("Pass-Heavy")
        elif 40 <= rush <= 60: tags.append("Balanced Usage")
    if method is not None:
        if method <= -18: tags.append("Methodical")
        elif method >= 18: tags.append("Explosive")
    if success is not None and success >= 75: tags.append("Highly Efficient")
    if explosive is not None and explosive >= 75: tags.append("Big-Play Threat")
    if finishing is not None and finishing >= 80: tags.append("Elite Finishing")
    if _efficiency_shape(profile) == "stalled": tags.append("Low-Output")
    if predict is not None and predict >= 70: tags.append("Predictable by Choice")
    if run is not None and pas is not None and rush is not None:
        if rush >= 75 and pas - run >= 15: tags.append("Run-Committed")
        elif rush <= 25 and run - pas >= 15: tags.append("Pass-Committed")
    if defense is not None and defense >= 90: tags.append("Elite Defense")
    elif defense is not None and defense >= 75: tags.append("Strong Defense")
    if off is not None and off >= 80: tags.append("High-Level Offense")
    elif off is not None and off >= 60: tags.append("Good Offense")
    off_traj = def_traj = None
    if closing_form:
        co = _number(closing_form.get("identity_offense_quality")); cd = _number(closing_form.get("identity_defense_quality"))
        if off is not None and co is not None:
            if co <= off - 12: off_traj = "Offense Faded Late"
            elif co >= off + 12: off_traj = "Offense Surged Late"
        if defense is not None and cd is not None:
            if cd <= defense - 12: def_traj = "Defense Faded Late"
            elif cd >= defense + 12: def_traj = "Defense Surged Late"
    if off_traj: tags.append(off_traj)
    if def_traj: tags.append(def_traj)
    ds = consistency.get("identity_defense_quality", {}).get("stabilityScore"); os = consistency.get("identity_offense_quality", {}).get("stabilityScore")
    if not def_traj and isinstance(ds, (int, float)) and ds >= 75 and defense is not None and defense >= 75: tags.append("Stable Defense")
    if not off_traj and isinstance(os, (int, float)) and os >= 75 and off is not None and off >= 60: tags.append("Stable Offense")
    return list(dict.fromkeys(tags))[:10]


def _summary(name, profile, closing_form, consistency):
    off = _number(profile.get("identity_offense_quality")); defense = _number(profile.get("identity_defense_quality"))
    rush = _number(profile.get("rush_rate")); method = _number(profile.get("identity_explosive_vs_methodical"))
    run = _number(profile.get("identity_rushing_attack")); pas = _number(profile.get("identity_passing_attack"))
    success = _number(profile.get("identity_success_quality")); explosive = _number(profile.get("identity_explosiveness_quality")); finishing = _number(profile.get("identity_finishing_quality"))
    parts: list[str] = []
    if rush is not None and rush >= 80:
        parts.append("heavy run commitment even though the passing attack graded better" if run is not None and pas is not None and pas - run >= 15 else "a strongly run-oriented approach")
    elif rush is not None and rush <= 20: parts.append("a strongly pass-oriented approach")
    else: parts.append("balanced run-pass usage")
    if method is not None and method <= -18: parts.append("methodical, low-explosive football")
    elif method is not None and method >= 18: parts.append("an explosive, big-play style")
    if success is not None and explosive is not None:
        if success >= 75 and explosive <= 55: parts.append("efficiency driven more by staying on schedule than by chunk plays")
        elif explosive >= 75 and success <= 55: parts.append("production heavily dependent on explosive plays")
        elif success >= 70 and explosive >= 70: parts.append("both efficient and explosive offensive production")
        elif success < 45 and explosive < 45: parts.append("an offense that struggled to create either steady efficiency or chunk gains")
    if finishing is not None and finishing >= 80: parts.append("excellent scoring-opportunity conversion")
    if off is not None and defense is not None:
        if defense - off >= 12: parts.append(f"{_quality_phrase(defense, 'defense')} paired with {_quality_phrase(off, 'offense')}")
        elif off - defense >= 12: parts.append(f"{_quality_phrase(off, 'offense')} paired with {_quality_phrase(defense, 'defense')}")
        else: parts.append(f"{_quality_word(off).lower()} offense and {_quality_word(defense).lower()} defense")
    ds = consistency.get("identity_defense_quality", {}).get("stabilityScore")
    if isinstance(ds, (int, float)) and ds >= 75 and defense is not None and defense >= 75: parts.append("defensive quality that stayed stable across the season")
    if closing_form and off is not None:
        co = _number(closing_form.get("identity_offense_quality"))
        if co is not None and co <= off - 12: parts.append("with the offense cooling substantially late")
        elif co is not None and co >= off + 12: parts.append("with the offense surging late")
    sentence = ", ".join(parts) if parts else name
    return sentence[0].upper() + sentence[1:] + "."


def build_dynamic_identity(profile, *, closing_form=None, season_profiles=None):
    season_profiles = season_profiles or [profile]
    consistency = season_consistency(season_profiles)
    name = _identity_name(profile)
    return {
        "version": DYNAMIC_IDENTITY_VERSION,
        "name": name,
        "tags": _tags(profile, closing_form, consistency),
        "summary": _summary(name, profile, closing_form, consistency),
        "consistency": consistency,
        "style": {
            "usage": _usage(profile),
            "method": _method(profile),
            "paceShape": _pace_shape(profile),
            "efficiencyShape": _efficiency_shape(profile),
            "attackDriver": _attack_balance(profile),
            "commitment": _commitment(profile),
            "teamStructure": _structure(profile),
            "effectiveness": _effectiveness(profile),
            "secondaryMechanism": _generic_secondary(profile),
        },
    }
