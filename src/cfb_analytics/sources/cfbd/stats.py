def fetch_season(client, season: int, **kwargs):
    return client.team_season_stats(season, **kwargs)


def fetch_advanced(client, season: int, **kwargs):
    return client.team_season_advanced_stats(season, **kwargs)

