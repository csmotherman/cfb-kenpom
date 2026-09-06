"""Compatibility entry point for the current dynamic team identity engine."""
from .dynamic_identity_v6 import (
    CORE_SERIES_FIELDS,
    DYNAMIC_IDENTITY_VERSION,
    build_dynamic_identity,
    season_consistency,
)

__all__ = [
    "CORE_SERIES_FIELDS",
    "DYNAMIC_IDENTITY_VERSION",
    "build_dynamic_identity",
    "season_consistency",
]
