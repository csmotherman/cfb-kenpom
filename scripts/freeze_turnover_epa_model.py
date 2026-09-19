"""Freeze the validated turnover-EPA model once.

Fits epa_v1_research.NextScoreExpectedPoints on the full 2014-2025 canonical
play corpus and serializes its state-bucket stats to a committed JSON
artifact. This is the ONLY expensive step -- src/cfb_analytics/analytics/epa.py
loads the frozen artifact at runtime (a fast JSON read), it never refits.

Rerun only if epa_v1_research.state_keys()/NextScoreExpectedPoints changes, or
to extend the training window to a newly-completed season -- not on every
refresh. Mirrors prospective/2026/preseason-power-frozen.json's freeze/publish
split (see early_season_predictions.py) and this session's
prospective/2026/cfp-chance-calibration.json.

Validated in research_turnover_epa_validation.py (2025 holdout, leave-one-
season-out style): 99.1% of real turnovers correctly signed negative, mean
-4.35, vs. CFBD ppa's 87.6% on a live sample. This freeze folds 2025 back into
training since that validation is already done -- this is the production
artifact, not another holdout run.
"""
from __future__ import annotations

import json
from pathlib import Path

from cfb_analytics.analytics.epa_v1_research import EPA_V2_RESEARCH_VERSION, NextScoreExpectedPoints
from cfb_analytics.canonical.materialize import canonical_partition_dir
from cfb_analytics.raw.audit import discover_partitions

RAW_ROOT = Path("data/raw")
PROCESSED_ROOT = Path("data/processed")
SEASONS = (2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
MIN_COUNT = 50
OUT_PATH = Path("prospective/turnover-epa-model-frozen.json")


def load_all(seasons):
    out = []
    for season in seasons:
        for st, w in discover_partitions(RAW_ROOT, season):
            path = canonical_partition_dir(PROCESSED_ROOT, season, st, w) / "plays.json"
            out.extend(json.loads(path.read_text()))
    return out


def main() -> None:
    print(f"Loading canonical plays for {SEASONS}...")
    plays = load_all(SEASONS)
    print(f"{len(plays):,} plays loaded. Fitting NextScoreExpectedPoints...")
    model = NextScoreExpectedPoints(min_count=MIN_COUNT).fit(plays)

    # Tuple keys -> JSON-safe list-of-lists; state_keys()'s first element is a
    # literal string tag ("exact"/"coarse"/"field"/"down_field"/"down"/"global"),
    # the rest are ints -- store each key as [tag, *ints] to round-trip exactly.
    stats = [{"key": list(key), "count": n, "total": total} for key, (n, total) in model.stats.items()]

    artifact = {
        "modelVersion": EPA_V2_RESEARCH_VERSION,
        "trainedOnSeasons": list(SEASONS),
        "minCount": MIN_COUNT,
        "nPlaysTrained": len(plays),
        "nStateBuckets": len(stats),
        "stats": stats,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(artifact, separators=(",", ":")) + "\n")
    print(f"Wrote {OUT_PATH} ({len(stats):,} state buckets)")


if __name__ == "__main__":
    main()
