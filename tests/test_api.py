import os
import tempfile
import unittest
from fastapi.testclient import TestClient

os.environ["MATCHMAKER_ENV"] = "development"
from matchmaker import db
from matchmaker.app import app
from matchmaker.security import issue_player_token


class MatchmakerApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self.tmp.name, "test.sqlite3")
        db.init_db()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        response = self.client.post("/api/games", json={"game_id": "test-game", "name": "Test Game"})
        self.assertEqual(response.status_code, 201, response.text)

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def token(self, player, game="test-game"):
        return {"Authorization": "Bearer " + issue_player_token(game, player)}

    def test_pairing_and_elo_result(self):
        a = self.client.post("/api/games/test-game/queue", headers=self.token("alice"), json={})
        self.assertEqual(a.status_code, 200, a.text)
        self.assertEqual(a.json()["status"], "waiting")
        b = self.client.post("/api/games/test-game/queue", headers=self.token("bob"), json={})
        self.assertEqual(b.status_code, 200, b.text)
        match_id = b.json()["match_id"]
        self.assertEqual(set(b.json()["players"]), {"alice", "bob"})
        status = self.client.get("/api/games/test-game/queue", headers=self.token("alice"))
        self.assertEqual(status.json()["match_id"], match_id)
        repeated_join = self.client.post("/api/games/test-game/queue", headers=self.token("alice"), json={})
        self.assertEqual(repeated_join.json()["match_id"], match_id)
        result = self.client.post(
            f"/api/games/test-game/matches/{match_id}/result", json={"winner_id": "alice"}
        )
        self.assertEqual(result.status_code, 200, result.text)
        stats_a = self.client.get("/api/games/test-game/players/alice").json()
        stats_b = self.client.get("/api/games/test-game/players/bob").json()
        self.assertGreater(stats_a["rating"], 1000)
        self.assertLess(stats_b["rating"], 1000)
        self.assertEqual((stats_a["wins"], stats_a["losses"], stats_a["matches"]), (1, 0, 1))
        self.assertEqual((stats_b["wins"], stats_b["losses"], stats_b["matches"]), (0, 1, 1))
        duplicate = self.client.post(
            f"/api/games/test-game/matches/{match_id}/result", json={"winner_id": "alice"}
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_private_game_requires_code_and_is_not_listed(self):
        response = self.client.post("/api/games", json={
            "game_id": "private-game", "name": "Friends Only", "visibility": "private",
            "access_code": "invite-code-123"
        })
        self.assertEqual(response.status_code, 201, response.text)
        listed = self.client.get("/api/games").json()["games"]
        self.assertNotIn("private-game", [game["game_id"] for game in listed])
        token = self.token("alice", "private-game")
        denied = self.client.post("/api/games/private-game/queue", headers=token, json={})
        self.assertEqual(denied.status_code, 404)
        accepted = self.client.post("/api/games/private-game/queue", headers=token,
                                    json={"access_code": "invite-code-123"})
        self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_token_is_scoped_to_game_and_queue_can_be_left(self):
        wrong_scope = self.client.get("/api/games/other-game/queue", headers=self.token("alice"))
        self.assertEqual(wrong_scope.status_code, 401)
        joined = self.client.post("/api/games/test-game/queue", headers=self.token("alice"), json={})
        self.assertEqual(joined.status_code, 200)
        left = self.client.delete("/api/games/test-game/queue", headers=self.token("alice"))
        self.assertEqual(left.json()["status"], "left")
        self.assertEqual(self.client.get("/api/games/test-game/queue", headers=self.token("alice")).json()["status"], "idle")

    def test_production_privileged_calls_require_server_key(self):
        names = ("MATCHMAKER_ENV", "MATCHMAKER_SERVER_KEY", "MATCHMAKER_SECRET_KEY")
        previous = {name: os.environ.get(name) for name in names}
        os.environ["MATCHMAKER_ENV"] = "production"
        os.environ["MATCHMAKER_SERVER_KEY"] = "server-key-for-tests-with-at-least-32-chars"
        os.environ["MATCHMAKER_SECRET_KEY"] = "signing-key-for-tests-with-at-least-32-characters"
        try:
            denied = self.client.post("/api/games", json={"game_id": "prod-game", "name": "Prod"})
            self.assertEqual(denied.status_code, 401)
            allowed = self.client.post(
                "/api/games", json={"game_id": "prod-game", "name": "Prod"},
                headers={"X-Server-Key": os.environ["MATCHMAKER_SERVER_KEY"]},
            )
            self.assertEqual(allowed.status_code, 201, allowed.text)
            denied_token = self.client.post("/api/auth/token", json={"game_id": "prod-game", "player_id": "p"})
            self.assertEqual(denied_token.status_code, 401)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
