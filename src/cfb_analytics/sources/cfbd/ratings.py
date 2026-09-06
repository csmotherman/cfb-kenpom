"""Benchmark endpoint adapter; values returned here are never SOAR inputs."""


def fetch_srs(client, season: int):
    return client.get_json("/ratings/srs", {"year": season})


def fetch_elo(client, season: int):
    return client.get_json("/ratings/elo", {"year": season})

