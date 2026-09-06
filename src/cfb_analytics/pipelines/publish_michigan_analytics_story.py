"""Publish the compact 2025 Michigan/Utah evidence used by the Analytics page."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _rate(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def build(michigan: dict[str, Any], utah: dict[str, Any]) -> dict[str, Any]:
    def offense(team: dict[str, Any]) -> dict[str, Any]:
        rush_attempts = int(team["rushAttempts"])
        dropbacks = int(team["dropbacks"])
        return {
            "team": team["team"],
            "rushAttempts": rush_attempts,
            "dropbacks": dropbacks,
            "designedBalanceRushShare": _rate(rush_attempts, rush_attempts + dropbacks),
            "rushSuccessRate": team["rushSuccessRate"],
            "rushYardsPerAttempt": team["rushYardsPerAttempt"],
            "rushExplosivePlayRate": team["rushExplosivePlayRate"],
            "successRate": team["successRate"],
            "successRateNationalRank": team["national_successRate_rank"],
            "thirdDownConversionRate": team["thirdDownConversionRate"],
            "fourthDownConversionRate": team["fourthDownConversionRate"],
            "pointsPerOpportunity": team["pointsPerOpportunity"],
            "pointsPerOpportunityNationalRank": team["national_pointsPerOpportunity_rank"],
            "pointsPerResolvedPossession": team["pointsPerResolvedPossession"],
            "pointsPerResolvedPossessionNationalRank": team["national_pointsPerResolvedPossession_rank"],
        }

    return {
        "season": 2025,
        "valueType": "ACTUAL",
        "comparisonType": "STAFF_CONTEXT",
        "definitionVersion": "michigan-utah-staff-context-v1",
        "runShareDefinition": "rushAttempts / (rushAttempts + dropbacks)",
        "teams": {"michigan": offense(michigan), "utah": offense(utah)},
        "michiganDefense": {
            "explosivePlayRateAllowed": michigan["explosivePlayRateAllowed"],
            "explosivePlayRateAllowedNationalRank": michigan["national_explosivePlayRateAllowed_rank"],
            "yardsPerSuccessfulPlayAllowed": michigan["yardsPerSuccessfulPlayAllowed"],
            "yardsPerSuccessfulPlayAllowedNationalRank": michigan["national_yardsPerSuccessfulPlayAllowed_rank"],
            "pointsPerResolvedPossessionAllowed": michigan["pointsPerResolvedPossessionAllowed"],
            "pointsPerResolvedPossessionAllowedNationalRank": michigan["national_pointsPerResolvedPossessionAllowed_rank"],
        },
        "interpretation": {
            "michigan": "Efficient and explosive on the ground, with finishing drives the clearest offensive gap.",
            "utah": "Run-led, efficient on late downs, and substantially stronger at turning opportunities into points.",
            "boundary": "Utah 2025 is staff context, not a projection that Michigan 2026 will reproduce the same tendencies or results.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published-root", type=Path, default=Path("data/published"))
    parser.add_argument("--output", type=Path, default=Path("data/published/2026/michigan/analytics-story.json"))
    args = parser.parse_args()
    michigan = json.loads((args.published_root / "2025/teams/michigan/season.json").read_text())[0]
    utah = json.loads((args.published_root / "2025/teams/utah/season.json").read_text())[0]
    result = build(michigan, utah)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "output": str(args.output)}))


if __name__ == "__main__":
    main()
