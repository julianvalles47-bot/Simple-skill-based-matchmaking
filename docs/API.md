# HTTP API reference

Base URL for a local server: `http://127.0.0.1:8000`. JSON is used for request and response bodies. The interactive OpenAPI page at `/docs` is generated from the running app.

## Authentication

`POST /api/auth/token` returns a short-lived bearer token scoped to one `game_id` and `player_id`. Send it as `Authorization: Bearer <access_token>` to player queue endpoints. A production game backend must send `X-Server-Key` to mint tokens. The development server intentionally allows token minting without that header; do not expose development mode publicly.

Game creation and result reporting also require `X-Server-Key` in production. This header contains a secret that belongs only on a trusted game backend. Never put it in an itch.io download or another public client.

Browser-based games need their website origin in the server's `MATCHMAKER_CORS_ORIGINS` setting (comma-separated exact origins, such as `https://studio.itch.io`). The development default is `*`; restrict it for hosted deployments. CORS does not replace authentication.

## Health and games

### `GET /health`

Returns `{ "ok": true, "environment": "development" }`.

### `GET /api/games`

Lists active public games. Private games are not listed.

### `POST /api/games`

Creates a game. In production, trusted backend only. `game_id` uses letters, numbers, `_`, or `-`.

```json
{ "game_id": "my-fighter", "name": "My Fighter", "visibility": "public" }
```

For a private game, use `"visibility":"private"` and an `access_code` of at least 8 characters. The stored value is a hash, not the original code. Creation returns `409` for a duplicate ID.

### `GET /api/games/{game_id}`

Returns game metadata. For private games send `X-Game-Access-Code: <invite-code>`.

## Player token

### `POST /api/auth/token`

Request:

```json
{ "game_id": "my-fighter", "player_id": "player-123", "ttl_seconds": 3600 }
```

`ttl_seconds` can be 60–86400. Response:

```json
{ "access_token": "<signed-token>", "token_type": "bearer", "expires_in": 3600 }
```

The token is signed by the service and cannot be edited without the signing secret. It is not proof that a person owns an account: your backend must authenticate the player before minting it.

## Queue and matches

### `POST /api/games/{game_id}/queue`

Requires a player bearer token for that same game. For private games, send the invite code in the JSON body.

```json
{}
```

Private game body:

```json
{ "access_code": "your-invite-code" }
```

Returns `status: waiting` or, if a compatible opponent is present, `status: matched` with `match_id`, player IDs, and ratings.

### `GET /api/games/{game_id}/queue`

Requires the same bearer token. Returns `waiting`, `matched` (while awaiting a result), or `idle`. Poll at a sensible interval such as every few seconds, not every frame.

### `DELETE /api/games/{game_id}/queue`

Removes the authenticated player from the waiting queue. It does not cancel a match that has already been made.

## Reporting a result

### `POST /api/games/{game_id}/matches/{match_id}/result`

Trusted game backend only in production. Request:

```json
{ "winner_id": "player-123" }
```

`winner_id` must be one of the two matched players. Results can only be submitted once. Replays return `409`. The API updates each player's rating, win/loss counts, and match count atomically. This service trusts the backend that reports the winner; it cannot validate game simulation or client claims itself.

## Ratings and leaderboards

### `GET /api/games/{game_id}/leaderboard?limit=50`

Returns players ordered by rating, then wins. Limit is 1–100. Private games require `X-Game-Access-Code`.

### `GET /api/games/{game_id}/players/{player_id}`

Returns rating, wins, losses, and matches; a new player starts at 1000. Private games require `X-Game-Access-Code`.

## Status codes

- `200` successful request
- `201` game created
- `401` missing/invalid token or server key
- `404` missing game/match or invalid private game code
- `409` duplicate game or result already submitted
- `422` invalid request data or winner not in the match

## Minimal flow

1. Your backend authenticates a player and requests their scoped token.
2. Client sends `POST .../queue` with its bearer token.
3. Client polls `GET .../queue` until matched; your game can use the returned match ID to coordinate gameplay separately.
4. After a trusted game backend verifies the winner, it sends the result POST with its server key.
