#!/bin/bash
# EPA/PPA research program: ingest 2014-2025 into a RESEARCH-ONLY data path
# (data/research/raw, data/research/processed) instead of data/raw and
# data/processed -- those paths get pruned back to current-season-only by
# production's data retention job, which was confirmed mid-session to have
# already deleted the prior identical ingest under data/raw|processed.
set -x
RAW_ROOT=data/research/raw
PROCESSED_ROOT=data/research/processed
for season in 2014 2015 2016 2017 2018 2019 2021 2022 2023 2024 2025; do
  echo "=== SEASON $season: ingest ==="
  .venv/Scripts/python.exe -m cfb_analytics.pipelines.ingest --season $season --raw-root $RAW_ROOT --force
  echo "=== SEASON $season: canonical-plays ==="
  .venv/Scripts/python.exe -m cfb_analytics.raw.cli --root $RAW_ROOT --processed-root $PROCESSED_ROOT canonical-plays --season $season
  echo "=== SEASON $season: derived-drives ==="
  .venv/Scripts/python.exe -m cfb_analytics.raw.cli --root $RAW_ROOT --processed-root $PROCESSED_ROOT derived-drives --season $season
  echo "=== SEASON $season: DONE ==="
done
echo "ALL SEASONS COMPLETE"
