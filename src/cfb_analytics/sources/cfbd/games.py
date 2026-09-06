def fetch(client, season: int, week: int, season_type: str):
    return client.games(season, week, season_type)

