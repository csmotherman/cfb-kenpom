"""Canonical fan-first product directory for the CFB Analytics website.

This module does not calculate football metrics. It defines how validated analytics
are turned into fan-facing pages, questions, insights, and shareable experiences.

The core rule is simple:

    ANSWER FIRST -> EVIDENCE SECOND -> METHODOLOGY THIRD

A fan should never need to understand SRS, success rate, opponent adjustment, or
model feature engineering before they understand what the site is telling them.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SITE_PRODUCT_VERSION = "michigan-season-architecture-v2"

SITE_TREE = (
    "app/page.tsx",
    "app/michigan/page.tsx",
    "app/football/[season]/page.tsx",
    "app/schedule/page.tsx",
    "app/teams/page.tsx",
    "app/teams/[team]/[season]/page.tsx",
    "app/rankings/page.tsx",
    "app/compare/page.tsx",
    "app/metrics/page.tsx",
    "components/MichiganHome.tsx",
    "components/Nav.tsx",
    "lib/michigan.ts",
)

PRODUCT_MANIFEST: dict[str, Any] = {
    "version": SITE_PRODUCT_VERSION,
    "positioning": {
        "promise": "Explain Michigan football using the entire FBS field as context.",
        "taglineOptions": [
            "Know exactly where Michigan stands.",
            "Michigan is the focus. The nation is the measuring stick.",
            "Maize and blue questions, national answers.",
        ],
        "northStar": (
            "A Michigan fan should understand the team, its opponents, and its national standing "
            "without needing advanced analytics terminology."
        ),
    },
    "productRules": [
        "Answer the football question before showing the metric.",
        "Use plain-English labels on the surface; advanced metric names live in tooltips or detail views.",
        "Show national percentile/rank whenever a raw number is hard to interpret.",
        "Separate team quality, team identity/style, and recent trajectory.",
        "Never present a model estimate as a historical fact.",
        "Resolve the current Michigan product to 2026 PRESEASON while 2025 remains the latest completed season.",
        "Label every performance value ACTUAL, PROJECTED, or PRESEASON.",
        "Explain why a team is ranked or favored with 2-4 concrete football reasons.",
        "Every major result should be easy to share as a compact visual card.",
        "Mobile-first: the first screen should answer one question, not display a dashboard wall.",
        "Use color and visual hierarchy to communicate strength; never rely on color alone.",
        "Methodology is available, transparent, and clickable, but never blocks the fan experience.",
    ],
    "navigation": [
        {"label": "Michigan", "route": "/football/2026", "question": "What is the current Michigan season state?"},
        {"label": "Seasons", "route": "/football/[season]", "question": "How did Michigan compare within each season from 2010 onward?"},
        {"label": "Schedule", "route": "/schedule", "question": "How did Michigan perform game by game?"},
        {"label": "Rankings", "route": "/rankings", "question": "Who are the best teams?"},
        {"label": "Compare", "route": "/compare", "question": "How does Michigan compare with another FBS team?"},
        {"label": "Methodology", "route": "/metrics", "question": "What does each Michigan metric mean?"},
    ],
    "landingPage": {
        "goal": "Hook a college-football fan in under five seconds and give them an immediate action.",
        "hero": {
            "eyebrow": "THE NATIONAL PICTURE, THROUGH A MAIZE & BLUE LENS",
            "headline": "Know exactly where Michigan stands.",
            "subheadline": (
                "See what Michigan does well, where it falls short, and how it compares nationally "
                "and inside the Big Ten."
            ),
            "primaryCta": {"label": "Explore Michigan", "route": "/michigan"},
            "secondaryCta": {"label": "View National Rankings", "route": "/rankings"},
            "requiredInteraction": "Open the latest Michigan profile directly from the hero.",
        },
        "modules": [
            {
                "order": 1,
                "id": "fan_questions",
                "title": "What do you want to know?",
                "purpose": "Let the fan choose a football question, not an analytics product.",
                "cards": [
                    {"label": "Who is the best?", "route": "/rankings"},
                    {"label": "Who would win?", "route": "/simulator"},
                    {"label": "What is my team's identity?", "route": "/teams"},
                    {"label": "Compare two teams", "route": "/compare"},
                ],
            },
            {
                "order": 2,
                "id": "power_snapshot",
                "title": "The Teams Everyone Is Chasing",
                "purpose": "Instantly surface the strongest teams with one-sentence reasons.",
                "data": "historical/current power rankings",
                "show": ["rank", "team", "season", "power label", "one reason", "trend or historical badge"],
            },
            {
                "order": 3,
                "id": "featured_simulation",
                "title": "Settle a College Football Argument",
                "purpose": "Show the simulator as entertainment, not a technical model demo.",
                "data": "historical game simulator",
                "show": ["matchup", "expected score", "win probability", "top matchup reason", "simulate CTA"],
            },
            {
                "order": 4,
                "id": "team_identity",
                "title": "Every Team Has a Personality",
                "purpose": "Introduce archetypes through recognizable football identities.",
                "data": "team archetype layers",
                "show": ["team", "primary identity", "offense identity", "defense identity", "plain-English description"],
            },
            {
                "order": 5,
                "id": "viral_debates",
                "title": "Debates Worth Fighting About",
                "purpose": "Preset shareable historical matchups and comparisons.",
                "examples": [
                    "Best champion of the era",
                    "Best Michigan team",
                    "Best Ohio State team",
                    "Elite offense vs elite defense",
                    "Same school, different era",
                ],
            },
            {
                "order": 6,
                "id": "leaderboards",
                "title": "What Teams Are Actually Elite At",
                "purpose": "Turn deeper metrics into understandable leaderboards.",
                "show": ["Big-Play Threat", "Staying on Schedule", "Finishing", "Run Game", "Passing Attack", "Run Defense", "Pass Defense", "Disruption"],
            },
            {
                "order": 7,
                "id": "methodology_tease",
                "title": "Built to Explain, Not Hide Behind a Formula",
                "purpose": "Earn trust without dumping methodology on casual fans.",
                "copy": "Every grade is traceable to the football underneath it. Tap any rating to see why.",
            },
        ],
    },
    "pageContracts": {
        "teamSeason": {
            "route": "/teams/[team]/[season]",
            "fanQuestions": [
                "How good was this team?",
                "What were they elite at?",
                "What could beat them?",
                "What style did they play?",
                "Who were they most similar to?",
                "Where do they rank historically?",
            ],
            "aboveFold": [
                "team + season",
                "overall quality grade/rank",
                "one-sentence identity",
                "primary strength",
                "primary weakness",
                "simulate / compare buttons",
            ],
            "sections": [
                "The 30-second answer",
                "Identity",
                "What they did best",
                "Where they were vulnerable",
                "Offense",
                "Defense",
                "Style and playcalling",
                "Season trajectory",
                "Historical similarity",
                "Schedule/results context",
                "Advanced breakdown",
            ],
        },
        "rankings": {
            "route": "/rankings",
            "defaultView": "Overall Power",
            "fanFilters": ["season", "all-time", "conference", "team", "offense", "defense", "style"],
            "rowMustAnswer": "Why is this team here?",
            "rowFields": ["rank", "team", "season", "grade", "record if available", "identity", "one-line reason"],
        },
        "simulator": {
            "route": "/simulator",
            "fanQuestions": ["Who wins?", "By how much?", "Why?", "How often?"],
            "inputs": ["home team", "home season", "away team", "away season"],
            "primaryOutput": ["expected score", "win probability", "spread", "simulation count"],
            "explanation": [
                "Biggest edge for home team",
                "Biggest edge for away team",
                "Matchup swing factor",
                "What an upset would require",
            ],
            "share": "Generate a matchup card optimized for social sharing.",
        },
        "compare": {
            "route": "/compare",
            "goal": "Show football differences before showing statistical differences.",
            "headlineComparisons": ["Overall", "Offense", "Defense", "Run", "Pass", "Explosiveness", "Finishing", "Style"],
            "verdicts": ["clear edge", "small edge", "even", "different styles"],
        },
        "archetype": {
            "route": "/archetypes/[slug]",
            "mustExplain": ["what it means", "how teams earn it", "what it looks like on Saturdays", "best examples", "common weakness"],
        },
        "metric": {
            "route": "/metrics/[metric]",
            "mustExplain": ["fan question", "plain-English definition", "why it matters", "what good looks like", "current/historical leaders", "technical definition"],
        },
    },
    "fanMetricLanguage": {
        "success_rate": {
            "surfaceLabel": "Staying on Schedule",
            "fanQuestion": "How often does this offense consistently win downs?",
            "technicalLabel": "Success Rate",
        },
        "explosiveness": {
            "surfaceLabel": "Big-Play Threat",
            "fanQuestion": "How dangerous is this team when one play can flip the field?",
            "technicalLabel": "Explosive Play Rate",
        },
        "yards_per_play": {
            "surfaceLabel": "Snap-to-Snap Production",
            "fanQuestion": "How much does this team get out of a typical play?",
            "technicalLabel": "Yards Per Play",
        },
        "yards_per_possession": {
            "surfaceLabel": "Drive Power",
            "fanQuestion": "How much offense does this team create each time it gets the ball?",
            "technicalLabel": "Yards Per Possession",
        },
        "finishing": {
            "surfaceLabel": "Cash In",
            "fanQuestion": "When this team gets a scoring chance, does it turn it into points?",
            "technicalLabel": "Points Per Opportunity",
        },
        "field_position": {
            "surfaceLabel": "Field Position Edge",
            "fanQuestion": "Does this team consistently make the opponent play on a longer field?",
            "technicalLabel": "Average Starting Field Position",
        },
        "havoc": {
            "surfaceLabel": "Disruption",
            "fanQuestion": "How often does this defense wreck a play before it develops?",
            "technicalLabel": "Havoc / TFL / Sack / Turnover indicators",
        },
        "rush_attack": {
            "surfaceLabel": "Run Game",
            "fanQuestion": "How good is this team at actually running the ball, not just how often it tries?",
            "technicalLabel": "Opponent-adjusted rushing attack composite",
        },
        "pass_attack": {
            "surfaceLabel": "Passing Attack",
            "fanQuestion": "How dangerous and efficient is this passing game?",
            "technicalLabel": "Opponent-adjusted passing attack composite",
        },
    },
    "insightGrammar": {
        "rule": "Every important number should be convertible into a sentence a fan would repeat to another fan.",
        "templates": [
            "{team} is elite at {strength}, ranking {rank_text} nationally.",
            "The biggest reason {team} wins is {reason}.",
            "The clearest weakness is {weakness}; opponents have their best chance when {counter}.",
            "This team plays like a {archetype}: {archetype_explanation}.",
            "Compared with {other_team}, the biggest difference is {difference}.",
            "The model favors {favorite} because {reason_1} and {reason_2}.",
        ],
    },
    "viralLoops": [
        "One-tap social cards for simulations, rankings, comparisons, and team identities.",
        "Stable share URLs that preserve team, season, and matchup selections.",
        "Preset rivalry and same-program-across-era comparisons.",
        "Debate prompts built around recognizable fan arguments, not obscure metrics.",
        "Every share card should include one provocative but defensible insight sentence.",
        "Allow fans to rerun a shared matchup with home field flipped or on a neutral field.",
    ],
    "dataProducts": {
        "teamProfiles": "team-season grades, identity, strengths, weaknesses, style, trajectory, similarity",
        "historicalPower": "cross-era tournament rankings and all-time team strength",
        "simulator": "cached head-to-head historical game simulation",
        "archetypes": "team/offense/defense/scheme identity assignments with confidence",
        "leaderboards": "production metric rankings and opponent-adjusted quality views",
        "comparisons": "two-team normalized comparison payloads",
    },
    "frontendTree": list(SITE_TREE),
}


def write_product_directory(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(PRODUCT_MANIFEST, indent=2, ensure_ascii=False) + "\n")
    return output


def print_tree() -> str:
    lines = ["website/"]
    for path in SITE_TREE:
        lines.append(f"  {path}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/derived/site/product_directory.json"),
    )
    parser.add_argument("--print-tree", action="store_true")
    args = parser.parse_args()

    path = write_product_directory(args.output)
    print(f"SITE PRODUCT DIRECTORY: {path}")
    print(f"Version: {SITE_PRODUCT_VERSION}")
    print(f"Routes: {len(PRODUCT_MANIFEST['navigation'])}")
    print(f"Landing modules: {len(PRODUCT_MANIFEST['landingPage']['modules'])}")
    if args.print_tree:
        print()
        print(print_tree())


if __name__ == "__main__":
    main()
