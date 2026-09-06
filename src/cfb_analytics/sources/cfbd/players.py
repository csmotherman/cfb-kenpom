def fetch_roster(client, season: int, team: str):
    return client.get_json("/roster", {"year": season, "team": team})

