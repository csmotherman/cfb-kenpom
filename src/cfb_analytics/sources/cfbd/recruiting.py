def fetch_teams(client, season: int):
    return client.get_json("/recruiting/teams", {"year": season})

