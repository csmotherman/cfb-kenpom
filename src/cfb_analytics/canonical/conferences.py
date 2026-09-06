"""Canonical conference identities observed in season-aware membership."""
from cfb_analytics.config.teams import slugify


def build_conferences(teams: list[dict]) -> list[dict]:
    names = sorted({row.get("conference") for row in teams if row.get("conference")})
    return [{"conference": name, "conference_slug": slugify(name)} for name in names]

