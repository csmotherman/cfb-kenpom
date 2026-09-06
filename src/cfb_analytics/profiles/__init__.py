"""Fan-facing team profile research layer.

Raw metrics remain authoritative; this package converts them into comparable
season-relative grades, historical fingerprints, and explainable archetypes.
"""

from .archetypes import classify_archetypes
from .archetype_catalog import CATALOG, CATALOG_VERSION
from .contract import PROFILE_METRICS, PROFILE_VERSION
from .grades import grade_percentile, percentile_rank
from .similarity import historical_comparables


def match_snapshot(*args, **kwargs):
    """Lazy wrapper that avoids importing the CLI module during package init."""
    from .match_archetypes import match_snapshot as _match_snapshot
    return _match_snapshot(*args, **kwargs)


__all__ = [
    "CATALOG",
    "CATALOG_VERSION",
    "PROFILE_METRICS",
    "PROFILE_VERSION",
    "classify_archetypes",
    "grade_percentile",
    "historical_comparables",
    "match_snapshot",
    "percentile_rank",
]
