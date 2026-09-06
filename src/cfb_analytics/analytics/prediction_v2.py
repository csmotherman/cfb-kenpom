"""Prediction v2 research benchmark contract.

Prediction v2 keeps the corrected Prediction-v1 VOLUME + OLS architecture and
replaces only the legacy `srsEdge` input with leakage-safe site-aware SRS/HFA
expected margin. The underlying site-aware implementation lives in the promoted
challenger module so the research result and benchmark use the same code path.
"""
from __future__ import annotations

from cfb_analytics.analytics.prediction_v1_site_aware_challenger import (
    SITE_AWARE,
    SITE_AWARE_FEATURE,
    build_site_aware_srs_rows,
    eligible_site,
    fit_site_aware_srs,
    load_data,
    site_aware_margin,
)

PREDICTION_V2_VERSION = "prediction-v2-site-aware-srs-hfa-v1"
PREDICTION_V2_FEATURES = SITE_AWARE
PREDICTION_V2_SITE_FEATURE = SITE_AWARE_FEATURE

__all__ = [
    "PREDICTION_V2_VERSION",
    "PREDICTION_V2_FEATURES",
    "PREDICTION_V2_SITE_FEATURE",
    "fit_site_aware_srs",
    "site_aware_margin",
    "build_site_aware_srs_rows",
    "load_data",
    "eligible_site",
]
