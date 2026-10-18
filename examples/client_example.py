"""Tiny game integration example using only Python's standard library.

Run a local server, create the demo game (see README), then run:
    python examples/client_example.py http://127.0.0.1:8000 demo-game alice

This example is for local development. In production, request a player token
from your own trusted game backend; never put MATCHMAKER_SERVER_KEY in a game.
"""
from __future__ import annotations
import json
import sys
import urllib.error
import urllib.request


def request(base: str, path: str, method: str = "GET", data=None, token=None, server_key=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if server_key:
        headers["X-Server-Key"] = server_key
    payload = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"API returned {error.code}: {error.read().decode()}") from error


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    game_id = sys.argv[2] if len(sys.argv) > 2 else "demo-game"
    player_id = sys.argv[3] if len(sys.argv) > 3 else "alice"
    # In dev mode token minting is intentionally open. In production this call
    # must happen on your game backend with its server key, then pass the token
    # to this player via your normal authenticated game session.
    token_data = request(base, "/api/auth/token", "POST", {"game_id": game_id, "player_id": player_id})
    token = token_data["access_token"]
    result = request(base, f"/api/games/{game_id}/queue", "POST", {}, token=token)
    print("Queue result:", json.dumps(result, indent=2))
    print("Check status later with GET /api/games/{game_id}/queue using this same token.")


if __name__ == "__main__":
    main()
