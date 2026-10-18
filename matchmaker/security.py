"""Small HMAC token helpers; keep the signing key on the server only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from fastapi import HTTPException


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def environment() -> str:
    return os.getenv("MATCHMAKER_ENV", "development").strip().lower()


def production() -> bool:
    return environment() == "production"


def signing_key() -> str:
    return os.getenv("MATCHMAKER_SECRET_KEY", "development-only-change-this-key")


def issue_player_token(game_id: str, player_id: str, ttl_seconds: int = 3600) -> str:
    payload = {"game": game_id, "sub": player_id, "exp": int(time.time()) + ttl_seconds}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(signing_key().encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_player_token(token: str, game_id: str) -> str:
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(signing_key().encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(body))
        if payload.get("game") != game_id or int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired or wrong scope")
        player_id = payload.get("sub")
        if not isinstance(player_id, str) or not player_id:
            raise ValueError("missing player")
        return player_id
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired player token") from exc


def require_server_key(provided: str | None) -> None:
    if not production():
        return
    expected = os.getenv("MATCHMAKER_SERVER_KEY", "")
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Trusted game-server key required")


def require_player(authorization: str | None, game_id: str) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer player token required")
    return verify_player_token(authorization[7:].strip(), game_id)
