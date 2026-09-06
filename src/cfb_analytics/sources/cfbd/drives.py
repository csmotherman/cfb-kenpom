def fetch(client, season: int, week: int, season_type: str):
    return client.drives(season, week, season_type)

