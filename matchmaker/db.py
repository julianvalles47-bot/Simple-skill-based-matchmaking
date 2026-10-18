"""SQLite storage helpers (DO NOT FORGET THIS DUMBASS)"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = os.getenv("MATCHMAKER_DB", "matchmaker.sqlite3")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = DB_PATH
    if path != ":memory:":
        Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
                access_hash TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE TABLE IF NOT EXISTS player_stats (
                game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
                player_id TEXT NOT NULL,
                rating INTEGER NOT NULL DEFAULT 1000,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                matches INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (game_id, player_id)
            );
            CREATE TABLE IF NOT EXISTS queue (
                game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
                player_id TEXT NOT NULL,
                rating INTEGER NOT NULL,
                joined_at REAL NOT NULL,
                PRIMARY KEY (game_id, player_id)
            );
            CREATE INDEX IF NOT EXISTS queue_search ON queue(game_id, joined_at);
            CREATE TABLE IF NOT EXISTS matches (
                match_id TEXT PRIMARY KEY,
                game_id TEXT NOT NULL REFERENCES games(game_id),
                player1_id TEXT NOT NULL,
                player2_id TEXT NOT NULL,
                player1_rating_before INTEGER NOT NULL,
                player2_rating_before INTEGER NOT NULL,
                player1_rating_after INTEGER,
                player2_rating_after INTEGER,
                winner_id TEXT,
                status TEXT NOT NULL CHECK (status IN ('awaiting_result', 'complete')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS matches_players ON matches(game_id, player1_id, player2_id, status);
            """
        )
