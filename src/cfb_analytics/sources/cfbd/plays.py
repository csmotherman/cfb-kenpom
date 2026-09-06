def fetch(client, season: int, week: int, season_type: str):
    return client.plays(season, week, season_type)

