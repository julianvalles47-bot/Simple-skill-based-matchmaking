from __future__ import annotations

import hashlib
import hmac
import math
import os
import time
import uuid
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from . import db
from .security import issue_player_token, production, require_player, require_server_key

app = FastAPI(
    title="Indie Matchmaker",
    description="A small, game-agnostic 1v1 ranked matchmaking service for indie games.",
    version="0.1.0",
)
cors_origins = [origin.strip() for origin in os.getenv("MATCHMAKER_CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Server-Key", "X-Game-Access-Code"],
)


def _access_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _check_private_access(game: db.sqlite3.Row, code: Optional[str]) -> None:
    if game["visibility"] == "private":
        if not code or not game["access_hash"] or not hmac.compare_digest(_access_hash(code), game["access_hash"]):
            raise HTTPException(status_code=404, detail="Game not found or access code is invalid")


def _get_game(conn, game_id: str):
    game = conn.execute("SELECT * FROM games WHERE game_id = ? AND active = 1", (game_id,)).fetchone()
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


def _stats(conn, game_id: str, player_id: str):
    row = conn.execute(
        "SELECT * FROM player_stats WHERE game_id = ? AND player_id = ?", (game_id, player_id)
    ).fetchone()
    return dict(row) if row else {
        "game_id": game_id, "player_id": player_id, "rating": 1000,
        "wins": 0, "losses": 0, "matches": 0,
    }


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    if production():
        weak = [name for name in ("MATCHMAKER_SERVER_KEY", "MATCHMAKER_SECRET_KEY")
                if len(os.getenv(name, "")) < 32 or os.getenv(name, "") in
                ("dev-only-not-a-secret", "development-only-change-this-key")]
        if weak:
            raise RuntimeError("Production mode requires unique server secrets of at least 32 characters: " + ", ".join(weak))


class GameCreate(BaseModel):
    game_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    visibility: str = Field(default="public", pattern=r"^(public|private)$")
    access_code: Optional[str] = Field(default=None, min_length=8, max_length=128)


class TokenRequest(BaseModel):
    game_id: str = Field(min_length=2, max_length=64)
    player_id: str = Field(min_length=1, max_length=128)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class QueueJoin(BaseModel):
    access_code: Optional[str] = Field(default=None, max_length=128)


class MatchResult(BaseModel):
    winner_id: str = Field(min_length=1, max_length=128)


@app.get("/health")
def health():
    return {"ok": True, "environment": "production" if production() else "development"}


@app.get("/api/games")
def list_games():
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT game_id, name, visibility, created_at FROM games WHERE active = 1 AND visibility = 'public' ORDER BY name"
        ).fetchall()
        return {"games": [dict(row) for row in rows]}


@app.post("/api/games", status_code=201)
def create_game(body: GameCreate, x_server_key: Optional[str] = Header(default=None)):
    require_server_key(x_server_key)
    if body.visibility == "private" and not body.access_code:
        raise HTTPException(status_code=422, detail="Private games need an access_code (at least 8 characters)")
    if body.visibility == "public" and body.access_code:
        raise HTTPException(status_code=422, detail="Public games do not use an access_code")
    with db.connect() as conn:
        try:
            conn.execute(
                "INSERT INTO games(game_id, name, visibility, access_hash) VALUES (?, ?, ?, ?)",
                (body.game_id, body.name, body.visibility, _access_hash(body.access_code) if body.access_code else None),
            )
        except db.sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="That game_id already exists") from exc
    return {"game_id": body.game_id, "name": body.name, "visibility": body.visibility}


@app.get("/api/games/{game_id}")
def get_game(game_id: str, x_game_access_code: Optional[str] = Header(default=None)):
    with db.connect() as conn:
        game = _get_game(conn, game_id)
        _check_private_access(game, x_game_access_code)
        return {"game_id": game["game_id"], "name": game["name"], "visibility": game["visibility"]}


@app.post("/api/auth/token")
def mint_player_token(body: TokenRequest, x_server_key: Optional[str] = Header(default=None)):
    """Trusted game backend only in production; open convenience endpoint in development."""
    require_server_key(x_server_key)
    with db.connect() as conn:
        _get_game(conn, body.game_id)
    token = issue_player_token(body.game_id, body.player_id, body.ttl_seconds)
    return {"access_token": token, "token_type": "bearer", "expires_in": body.ttl_seconds}


@app.post("/api/games/{game_id}/queue")
def join_queue(
    game_id: str,
    body: QueueJoin,
    authorization: Optional[str] = Header(default=None),
):
    player_id = require_player(authorization, game_id)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        game = _get_game(conn, game_id)
        _check_private_access(game, body.access_code)
        active_match = conn.execute(
            "SELECT match_id, player1_id, player2_id, player1_rating_before, player2_rating_before "
            "FROM matches WHERE game_id = ? AND (player1_id = ? OR player2_id = ?) "
            "AND status = 'awaiting_result' ORDER BY created_at DESC LIMIT 1",
            (game_id, player_id, player_id),
        ).fetchone()
        if active_match:
            conn.commit()
            return {"status": "matched", "game_id": game_id, "match_id": active_match["match_id"],
                    "players": [active_match["player1_id"], active_match["player2_id"]],
                    "ratings": [active_match["player1_rating_before"], active_match["player2_rating_before"]]}
        current = conn.execute(
            "SELECT * FROM queue WHERE game_id = ? AND player_id = ?", (game_id, player_id)
        ).fetchone()
        if current is None:
            rating = _stats(conn, game_id, player_id)["rating"]
            conn.execute(
                "INSERT INTO queue(game_id, player_id, rating, joined_at) VALUES (?, ?, ?, ?)",
                (game_id, player_id, rating, time.time()),
            )
            current = conn.execute(
                "SELECT * FROM queue WHERE game_id = ? AND player_id = ?", (game_id, player_id)
            ).fetchone()
        candidates = conn.execute(
            "SELECT * FROM queue WHERE game_id = ? AND player_id != ? ORDER BY joined_at",
            (game_id, player_id),
        ).fetchall()
        chosen = None
        for candidate in candidates:
            wait_seconds = max(0, time.time() - candidate["joined_at"])
            allowed_gap = min(500, 100 + int(wait_seconds / 30) * 25)
            if abs(current["rating"] - candidate["rating"]) <= allowed_gap:
                if chosen is None or abs(current["rating"] - candidate["rating"]) < abs(current["rating"] - chosen["rating"]):
                    chosen = candidate
        if chosen is None:
            conn.commit()
            return {"status": "waiting", "game_id": game_id, "player_id": player_id,
                    "rating": current["rating"], "joined_at": current["joined_at"]}
        match_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO matches(match_id, game_id, player1_id, player2_id, player1_rating_before, player2_rating_before, status) VALUES (?, ?, ?, ?, ?, ?, 'awaiting_result')",
            (match_id, game_id, player_id, chosen["player_id"], current["rating"], chosen["rating"]),
        )
        conn.execute("DELETE FROM queue WHERE game_id = ? AND player_id IN (?, ?)",
                     (game_id, player_id, chosen["player_id"]))
        conn.commit()
    return {"status": "matched", "game_id": game_id, "match_id": match_id,
            "players": [player_id, chosen["player_id"]],
            "ratings": [current["rating"], chosen["rating"]]}


@app.delete("/api/games/{game_id}/queue")
def leave_queue(game_id: str, authorization: Optional[str] = Header(default=None)):
    player_id = require_player(authorization, game_id)
    with db.connect() as conn:
        cursor = conn.execute("DELETE FROM queue WHERE game_id = ? AND player_id = ?", (game_id, player_id))
        return {"status": "left" if cursor.rowcount else "not_queued", "player_id": player_id}


@app.get("/api/games/{game_id}/queue")
def queue_status(game_id: str, authorization: Optional[str] = Header(default=None)):
    player_id = require_player(authorization, game_id)
    with db.connect() as conn:
        _get_game(conn, game_id)
        queued = conn.execute(
            "SELECT rating, joined_at FROM queue WHERE game_id = ? AND player_id = ?", (game_id, player_id)
        ).fetchone()
        if queued:
            return {"status": "waiting", "game_id": game_id, "player_id": player_id,
                    "rating": queued["rating"], "joined_at": queued["joined_at"]}
        match = conn.execute(
            "SELECT match_id, player1_id, player2_id, status, winner_id FROM matches "
            "WHERE game_id = ? AND (player1_id = ? OR player2_id = ?) AND status = 'awaiting_result' "
            "ORDER BY created_at DESC LIMIT 1", (game_id, player_id, player_id)
        ).fetchone()
        if match:
            return {"status": "matched", "game_id": game_id, "match_id": match["match_id"],
                    "players": [match["player1_id"], match["player2_id"]]}
        return {"status": "idle", "game_id": game_id, "player_id": player_id}


@app.get("/api/games/{game_id}/leaderboard")
def leaderboard(
    game_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    x_game_access_code: Optional[str] = Header(default=None),
):
    with db.connect() as conn:
        game = _get_game(conn, game_id)
        _check_private_access(game, x_game_access_code)
        rows = conn.execute(
            "SELECT player_id, rating, wins, losses, matches FROM player_stats WHERE game_id = ? "
            "ORDER BY rating DESC, wins DESC, player_id ASC LIMIT ?", (game_id, limit)
        ).fetchall()
        return {"game_id": game_id, "leaderboard": [dict(row) for row in rows]}


@app.get("/api/games/{game_id}/players/{player_id}")
def player_stats(game_id: str, player_id: str, x_game_access_code: Optional[str] = Header(default=None)):
    with db.connect() as conn:
        game = _get_game(conn, game_id)
        _check_private_access(game, x_game_access_code)
        return _stats(conn, game_id, player_id)


def _elo(rating_a: int, rating_b: int, score_a: float, k: int = 32) -> tuple[int, int]:
    expected_a = 1 / (1 + math.pow(10, (rating_b - rating_a) / 400))
    new_a = round(rating_a + k * (score_a - expected_a))
    return new_a, rating_a + rating_b - new_a


@app.post("/api/games/{game_id}/matches/{match_id}/result")
def report_result(
    game_id: str,
    match_id: str,
    body: MatchResult,
    x_server_key: Optional[str] = Header(default=None),
):
    require_server_key(x_server_key)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        match = conn.execute("SELECT * FROM matches WHERE match_id = ? AND game_id = ?", (match_id, game_id)).fetchone()
        if match is None:
            raise HTTPException(status_code=404, detail="Match not found")
        if match["status"] != "awaiting_result":
            raise HTTPException(status_code=409, detail="A result has already been recorded")
        if body.winner_id not in (match["player1_id"], match["player2_id"]):
            raise HTTPException(status_code=422, detail="winner_id must be one of the match players")
        score1 = 1.0 if body.winner_id == match["player1_id"] else 0.0
        new1, new2 = _elo(match["player1_rating_before"], match["player2_rating_before"], score1)
        p1, p2 = match["player1_id"], match["player2_id"]
        for player_id, new_rating, won in ((p1, new1, score1 == 1.0), (p2, new2, score1 == 0.0)):
            conn.execute(
                "INSERT INTO player_stats(game_id, player_id, rating, wins, losses, matches) VALUES (?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(game_id, player_id) DO UPDATE SET rating=excluded.rating, "
                "wins=player_stats.wins + excluded.wins, losses=player_stats.losses + excluded.losses, "
                "matches=player_stats.matches + 1",
                (game_id, player_id, new_rating, int(won), int(not won)),
            )
        conn.execute(
            "UPDATE matches SET winner_id=?, player1_rating_after=?, player2_rating_after=?, status='complete', "
            "completed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE match_id=?",
            (body.winner_id, new1, new2, match_id),
        )
        conn.commit()
    return {"status": "complete", "match_id": match_id, "winner_id": body.winner_id,
            "ratings": {p1: new1, p2: new2}}
