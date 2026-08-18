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

-- Gamification (LearnPath XP)
CREATE TABLE IF NOT EXISTS xp_transactions (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    base_xp INTEGER NOT NULL DEFAULT 0,
    bonus_xp INTEGER NOT NULL DEFAULT 0,
    multiplier REAL NOT NULL DEFAULT 1.0,
    final_xp INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_xp_learner ON xp_transactions(learner_id);
CREATE INDEX IF NOT EXISTS idx_xp_learner_time ON xp_transactions(learner_id, created_at);
CREATE INDEX IF NOT EXISTS idx_xp_activity ON xp_transactions(learner_id, activity_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_xp_dup ON xp_transactions(learner_id, activity_type, activity_id);

CREATE TABLE IF NOT EXISTS learner_gamification (
    learner_id TEXT PRIMARY KEY,
    total_xp INTEGER NOT NULL DEFAULT 0,
    weekly_xp INTEGER NOT NULL DEFAULT 0,
    monthly_xp INTEGER NOT NULL DEFAULT 0,
    current_streak INTEGER NOT NULL DEFAULT 0,
    longest_streak INTEGER NOT NULL DEFAULT 0,
    last_learning_date TEXT,
    rank TEXT,
    level INTEGER NOT NULL DEFAULT 1,
    leaderboard_opt_out INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS learner_badges (
    learner_id TEXT NOT NULL,
    badge_id TEXT NOT NULL,
    earned_at TEXT,
    PRIMARY KEY (learner_id, badge_id)
);
CREATE INDEX IF NOT EXISTS idx_learner_badges ON learner_badges(learner_id);

CREATE TABLE IF NOT EXISTS weekly_challenges (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    challenge_type TEXT NOT NULL,
    target REAL NOT NULL,
    xp_reward INTEGER NOT NULL DEFAULT 0,
    start_date TEXT,
    end_date TEXT
);

CREATE TABLE IF NOT EXISTS learner_challenges (
    learner_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    claimed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (learner_id, challenge_id)
);
CREATE INDEX IF NOT EXISTS idx_learner_challenges ON learner_challenges(learner_id);
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
            conn.execute("DELETE FROM xp_transactions WHERE learner_id = ?", (learner_id,))
            conn.execute("DELETE FROM learner_gamification WHERE learner_id = ?", (learner_id,))
            conn.execute("DELETE FROM learner_badges WHERE learner_id = ?", (learner_id,))
            conn.execute("DELETE FROM learner_challenges WHERE learner_id = ?", (learner_id,))

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
    # Gamification — XP transactions
    # ------------------------------------------------------------------
    def add_xp_transaction(self, learner_id: str, data: dict) -> str:
        """Insert an XP transaction. Returns None if the (learner, type, activity)
        triple already exists (duplicate protection at the storage layer)."""
        tx_id = new_id("xp")
        with _connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO xp_transactions "
                    "(id, learner_id, activity_id, activity_type, base_xp, bonus_xp, multiplier, final_xp, reason, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tx_id,
                        learner_id,
                        data.get("activity_id", ""),
                        data.get("activity_type", ""),
                        int(data.get("base_xp", 0)),
                        int(data.get("bonus_xp", 0)),
                        float(data.get("multiplier", 1.0)),
                        int(data.get("final_xp", 0)),
                        data.get("reason", ""),
                        data.get("created_at", _now()),
                    ),
                )
            except sqlite3.IntegrityError:
                return ""  # duplicate
        return tx_id

    def xp_transactions(self, learner_id: str, limit: int = 200) -> list[dict]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id, learner_id, activity_id, activity_type, base_xp, bonus_xp, "
                "multiplier, final_xp, reason, created_at FROM xp_transactions "
                "WHERE learner_id = ? ORDER BY created_at DESC LIMIT ?",
                (learner_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def xp_since(self, learner_id: str, since_iso: str) -> int:
        with _connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(final_xp), 0) AS total FROM xp_transactions "
                "WHERE learner_id = ? AND created_at >= ?",
                (learner_id, since_iso),
            ).fetchone()
        return int(row["total"] or 0)

    def xp_breakdown(self, learner_id: str) -> list[dict]:
        """XP grouped by activity type (for analytics charts)."""
        with _connect() as conn:
            rows = conn.execute(
                "SELECT activity_type, SUM(final_xp) AS xp, COUNT(*) AS n "
                "FROM xp_transactions WHERE learner_id = ? GROUP BY activity_type "
                "ORDER BY xp DESC",
                (learner_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def best_attempt_for(self, learner_id: str, assessment_id: str) -> dict | None:
        """Highest-scoring attempt for an assessment (for improvement bonus)."""
        with _connect() as conn:
            row = conn.execute(
                "SELECT data FROM assessment_attempts WHERE learner_id = ? AND assessment_id = ? "
                "ORDER BY score DESC LIMIT 1",
                (learner_id, assessment_id),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            return None

    def first_attempt_for(self, learner_id: str, assessment_id: str) -> dict | None:
        """Earliest attempt for an assessment (for improvement bonus)."""
        with _connect() as conn:
            row = conn.execute(
                "SELECT data FROM assessment_attempts WHERE learner_id = ? AND assessment_id = ? "
                "ORDER BY timestamp ASC LIMIT 1",
                (learner_id, assessment_id),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Gamification — aggregate state
    # ------------------------------------------------------------------
    def get_gamification(self, learner_id: str) -> dict | None:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM learner_gamification WHERE learner_id = ?", (learner_id,)
            ).fetchone()
        return dict(row) if row else None

    def upsert_gamification(self, learner_id: str, data: dict) -> None:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO learner_gamification "
                "(learner_id, total_xp, weekly_xp, monthly_xp, current_streak, longest_streak, "
                "last_learning_date, rank, level, leaderboard_opt_out, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(learner_id) DO UPDATE SET "
                "total_xp=excluded.total_xp, weekly_xp=excluded.weekly_xp, "
                "monthly_xp=excluded.monthly_xp, current_streak=excluded.current_streak, "
                "longest_streak=excluded.longest_streak, last_learning_date=excluded.last_learning_date, "
                "rank=excluded.rank, level=excluded.level, "
                "leaderboard_opt_out=excluded.leaderboard_opt_out, updated_at=excluded.updated_at",
                (
                    learner_id,
                    int(data.get("total_xp", 0)),
                    int(data.get("weekly_xp", 0)),
                    int(data.get("monthly_xp", 0)),
                    int(data.get("current_streak", 0)),
                    int(data.get("longest_streak", 0)),
                    data.get("last_learning_date"),
                    data.get("rank"),
                    int(data.get("level", 1)),
                    int(data.get("leaderboard_opt_out", 0)),
                    data.get("updated_at", _now()),
                ),
            )

    # ------------------------------------------------------------------
    # Gamification — badges
    # ------------------------------------------------------------------
    def earn_badge(self, learner_id: str, badge_id: str, earned_at: str | None = None) -> bool:
        """Insert a learner badge. Returns True if newly earned (not a duplicate)."""
        with _connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO learner_badges (learner_id, badge_id, earned_at) VALUES (?, ?, ?)",
                    (learner_id, badge_id, earned_at or _now()),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def learner_badges(self, learner_id: str) -> list[dict]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT badge_id, earned_at FROM learner_badges "
                "WHERE learner_id = ? ORDER BY earned_at",
                (learner_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def all_learners_with_badges(self) -> dict[str, list[str]]:
        """learner_id -> badge ids (for the mastery leaderboard)."""
        with _connect() as conn:
            rows = conn.execute(
                "SELECT learner_id, badge_id FROM learner_badges ORDER BY earned_at"
            ).fetchall()
        out: dict[str, list[str]] = {}
        for r in rows:
            out.setdefault(r["learner_id"], []).append(r["badge_id"])
        return out

    # ------------------------------------------------------------------
    # Gamification — weekly challenges
    # ------------------------------------------------------------------
    def list_weekly_challenges(self) -> list[dict]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM weekly_challenges ORDER BY start_date DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_challenge(self, challenge_id: str) -> dict | None:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM weekly_challenges WHERE id = ?", (challenge_id,)
            ).fetchone()
        return dict(row) if row else None

    def upsert_weekly_challenge(self, data: dict) -> None:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO weekly_challenges "
                "(id, title, description, challenge_type, target, xp_reward, start_date, end_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, description=excluded.description, "
                "challenge_type=excluded.challenge_type, target=excluded.target, "
                "xp_reward=excluded.xp_reward, start_date=excluded.start_date, end_date=excluded.end_date",
                (
                    data["id"], data["title"], data["description"], data["challenge_type"],
                    float(data["target"]), int(data["xp_reward"]),
                    data.get("start_date"), data.get("end_date"),
                ),
            )

    def get_learner_challenge(self, learner_id: str, challenge_id: str) -> dict | None:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM learner_challenges WHERE learner_id = ? AND challenge_id = ?",
                (learner_id, challenge_id),
            ).fetchone()
        return dict(row) if row else None

    def upsert_learner_challenge(self, learner_id: str, data: dict) -> None:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO learner_challenges "
                "(learner_id, challenge_id, progress, completed, completed_at, claimed) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(learner_id, challenge_id) DO UPDATE SET "
                "progress=excluded.progress, completed=excluded.completed, "
                "completed_at=excluded.completed_at, claimed=excluded.claimed",
                (
                    learner_id, data["challenge_id"], float(data.get("progress", 0)),
                    int(data.get("completed", 0)), data.get("completed_at"),
                    int(data.get("claimed", 0)),
                ),
            )

    # ------------------------------------------------------------------
    # Gamification — leaderboard + cohort helpers
    # ------------------------------------------------------------------
    def all_gamification_rows(self) -> list[dict]:
        """All learner gamification rows joined with names (for leaderboards)."""
        with _connect() as conn:
            rows = conn.execute(
                "SELECT g.learner_id, g.total_xp, g.weekly_xp, g.monthly_xp, g.current_streak, "
                "g.longest_streak, g.rank, g.level, g.leaderboard_opt_out, "
                "COALESCE(u.name, 'Learner ' || substr(g.learner_id, -4)) AS name "
                "FROM learner_gamification g LEFT JOIN users u ON u.id = g.learner_id "
                "ORDER BY g.total_xp DESC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            # demo learners carry their display name in the id (demo_alex -> Alex)
            if str(d["learner_id"]).startswith("demo_"):
                d["name"] = str(d["learner_id"])[5:].replace("_", " ").title()
            out.append(d)
        return out

    def learner_ids_in_cohort(self, learner_id: str) -> list[str]:
        """Simple cohort: learners created within 14 days of this learner (fallback: all)."""
        with _connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM learners WHERE id = ?", (learner_id,)
            ).fetchone()
        if row is None or not row["created_at"]:
            return self._all_learner_ids()
        created = row["created_at"]
        rows = conn.execute(
            "SELECT id FROM learners WHERE created_at BETWEEN datetime(?, '-14 days') "
            "AND datetime(?, '+14 days')",
            (created, created),
        ).fetchall()
        ids = [r["id"] for r in rows]
        return ids or self._all_learner_ids()

    def _all_learner_ids(self) -> list[str]:
        with _connect() as conn:
            rows = conn.execute("SELECT id FROM learners").fetchall()
        return [r["id"] for r in rows]

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
