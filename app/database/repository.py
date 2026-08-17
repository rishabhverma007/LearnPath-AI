"""SQLite repository for LearnPath AI.

Schema:
- learners(id TEXT PRIMARY KEY, data TEXT /* JSON twin */, created_at, updated_at)
- assessment_attempts(id TEXT PRIMARY KEY, learner_id, assessment_id, skill_id, score, correct, total, weak_concepts, data TEXT, timestamp)
- feedback(id TEXT PRIMARY KEY, learner_id, item_id, item_type, signal, comment, timestamp)
- recommendations(id TEXT PRIMARY KEY, learner_id, item_id, item_type, score, status, data TEXT, timestamp)
- users(id TEXT PRIMARY KEY, name, email, pass_hash, pass_salt, created_at)
- sessions(token TEXT PRIMARY KEY, user_id, created_at)

Thread-safety: each call opens its own connection (fine for a demo app).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.database.models import Learner
from app.utils import get_logger

log = get_logger("repository")

SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS assessment_attempts (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    score REAL NOT NULL,
    correct INTEGER NOT NULL,
    total INTEGER NOT NULL,
    weak_concepts TEXT,
    data TEXT,
    timestamp TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    signal TEXT NOT NULL,
    comment TEXT,
    timestamp TEXT
);
CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    score REAL NOT NULL,
    status TEXT NOT NULL,
    data TEXT,
    timestamp TEXT
);
CREATE INDEX IF NOT EXISTS idx_attempts_learner ON assessment_attempts(learner_id);
CREATE INDEX IF NOT EXISTS idx_feedback_learner ON feedback(learner_id);
CREATE INDEX IF NOT EXISTS idx_recs_learner ON recommendations(learner_id);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    pass_hash TEXT NOT NULL,
    pass_salt TEXT NOT NULL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


def _connect() -> sqlite3.Connection:
    Path(config.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class LearnerRepository:
    # ------------------------------------------------------------------
    # Learners
    # ------------------------------------------------------------------
    def save_learner(self, learner: Learner) -> Learner:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO learners (id, data, created_at, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (learner.learner_id, json.dumps(learner.to_dict()), learner.created_at, learner.updated_at),
            )
        return learner

    def get_learner(self, learner_id: str) -> Learner | None:
        with _connect() as conn:
            row = conn.execute(
                "SELECT data FROM learners WHERE id = ?", (learner_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return Learner.from_json(row["data"])
        except (json.JSONDecodeError, TypeError) as exc:
            log.error("corrupt learner row %s: %s", learner_id, exc)
            return None

    def list_learners(self) -> list[Learner]:
        with _connect() as conn:
            rows = conn.execute("SELECT data FROM learners ORDER BY updated_at DESC").fetchall()
        learners = []
        for row in rows:
            try:
                learners.append(Learner.from_json(row["data"]))
            except (json.JSONDecodeError, TypeError):
                continue
        return learners

    def delete_learner(self, learner_id: str) -> None:
        with _connect() as conn:
            conn.execute("DELETE FROM learners WHERE id = ?", (learner_id,))
            conn.execute("DELETE FROM assessment_attempts WHERE learner_id = ?", (learner_id,))
            conn.execute("DELETE FROM feedback WHERE learner_id = ?", (learner_id,))
            conn.execute("DELETE FROM recommendations WHERE learner_id = ?", (learner_id,))

    # ------------------------------------------------------------------
    # Assessment attempts
    # ------------------------------------------------------------------
    def add_attempt(self, learner_id: str, data: dict) -> str:
        attempt_id = new_id("attempt")
        with _connect() as conn:
            conn.execute(
                "INSERT INTO assessment_attempts "
                "(id, learner_id, assessment_id, skill_id, score, correct, total, weak_concepts, data, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt_id,
                    learner_id,
                    data.get("assessment_id", ""),
                    data.get("skill_id", ""),
                    float(data.get("score", 0)),
                    int(data.get("correct", 0)),
                    int(data.get("total", 0)),
                    json.dumps(data.get("weak_concepts", [])),
                    json.dumps(data, default=str),
                    data.get("timestamp", _now()),
                ),
            )
        return attempt_id

    def attempts_for(self, learner_id: str) -> list[dict]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT data FROM assessment_attempts WHERE learner_id = ? ORDER BY timestamp",
                (learner_id,),
            ).fetchall()
        out = []
        for row in rows:
            try:
                out.append(json.loads(row["data"]))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------
    def add_feedback(self, learner_id: str, data: dict) -> str:
        feedback_id = new_id("fb")
        with _connect() as conn:
            conn.execute(
                "INSERT INTO feedback "
                "(id, learner_id, item_id, item_type, signal, comment, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    feedback_id,
                    learner_id,
                    data.get("item_id", ""),
                    data.get("item_type", ""),
                    data.get("signal", ""),
                    data.get("comment", ""),
                    data.get("timestamp", _now()),
                ),
            )
        return feedback_id

    def feedback_for(self, learner_id: str) -> list[dict]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT item_id, item_type, signal, comment, timestamp FROM feedback "
                "WHERE learner_id = ? ORDER BY timestamp",
                (learner_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------
    def add_recommendation(self, learner_id: str, data: dict) -> str:
        rec_id = new_id("rec")
        with _connect() as conn:
            conn.execute(
                "INSERT INTO recommendations "
                "(id, learner_id, item_id, item_type, score, status, data, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rec_id,
                    learner_id,
                    data.get("item_id", ""),
                    data.get("item_type", ""),
                    float(data.get("score", 0)),
                    data.get("status", "recommended"),
                    json.dumps(data, default=str),
                    data.get("timestamp", _now()),
                ),
            )
        return rec_id

    def update_recommendation_status(self, learner_id: str, item_id: str, status: str) -> None:
        with _connect() as conn:
            conn.execute(
                "UPDATE recommendations SET status = ? WHERE learner_id = ? AND item_id = ?",
                (status, learner_id, item_id),
            )

    def rec_acceptance_rate(self, learner_id: str) -> float:
        with _connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN status IN ('accepted','complete') THEN 1 ELSE 0 END) AS accepted "
                "FROM recommendations WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
        total = int(row["total"] or 0)
        accepted = int(row["accepted"] or 0)
        return accepted / total if total else 0.0

    # ------------------------------------------------------------------
    # Users / auth
    # ------------------------------------------------------------------
    def create_user(self, user_id: str, name: str, email: str, pass_hash: str, pass_salt: str) -> dict:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO users (id, name, email, pass_hash, pass_salt, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, name, email, pass_hash, pass_salt, _now()),
            )
        return {"user_id": user_id, "name": name, "email": email}

    def get_user_by_email(self, email: str) -> dict | None:
        with _connect() as conn:
            row = conn.execute(
                "SELECT id, name, email, pass_hash, pass_salt FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        if row is None:
            return None
        return {
            "user_id": row["id"], "name": row["name"], "email": row["email"],
            "pass_hash": row["pass_hash"], "pass_salt": row["pass_salt"],
        }

    def get_user(self, user_id: str) -> dict | None:
        with _connect() as conn:
            row = conn.execute(
                "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_user(self, user_id: str) -> None:
        with _connect() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def create_session(self, user_id: str) -> str:
        import secrets

        token = secrets.token_hex(32)
        with _connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                (token, user_id, _now()),
            )
        return token

    def get_user_by_token(self, token: str) -> dict | None:
        if not token:
            return None
        with _connect() as conn:
            row = conn.execute(
                "SELECT u.id, u.name, u.email FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token = ?",
                (token,),
            ).fetchone()
        return dict(row) if row else None

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with _connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
