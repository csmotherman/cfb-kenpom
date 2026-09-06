import json

from cfb_analytics.sources.cfbd.client import CfbdResponse


def filter_to_games(response: CfbdResponse, game_ids: set[str]) -> CfbdResponse:
    if not isinstance(response.payload, list):
        raise ValueError("unexpected CFBD entity payload")
    payload = [row for row in response.payload if str(row.get("gameId")) in game_ids]
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return CfbdResponse(response.url, response.status_code, payload, raw, response.headers)

