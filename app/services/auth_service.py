"""Auth service for LearnPath AI.

Lightweight, dependency-free account + session management:
  - passwords hashed with PBKDF2-HMAC-SHA256 + per-user random salt (stdlib)
  - sessions are random bearer tokens stored in SQLite
Good enough for a demo prototype; swap for OAuth2/JWT in production.
"""
from __future__ import annotations

import hashlib
import re
import secrets

from app.database.repository import LearnerRepository, new_id

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PBKDF2_ITERATIONS = 100_000


class AuthError(Exception):
    """Raised with a user-facing message when signup/signin fails."""


def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERATIONS
    ).hex()


def _new_salt() -> str:
    return secrets.token_bytes(16).hex()


class AuthService:
    def __init__(self, repo: LearnerRepository | None = None) -> None:
        self.repo = repo or LearnerRepository()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def signup(self, name: str, email: str, password: str) -> dict:
        name = (name or "").strip()
        email = (email or "").strip().lower()
        if not name:
            raise AuthError("Please tell us your name.")
        if not _EMAIL_RE.match(email):
            raise AuthError("That email address doesn't look right.")
        if len(password) < 6:
            raise AuthError("Password must be at least 6 characters.")
        if self.repo.get_user_by_email(email):
            raise AuthError("An account with that email already exists — sign in instead.")

        salt = _new_salt()
        user = self.repo.create_user(
            new_id("user"), name, email, _hash_password(password, salt), salt
        )
        token = self.repo.create_session(user["user_id"])
        return {"token": token, "user": {"user_id": user["user_id"], "name": name, "email": email}}

    def signin(self, email: str, password: str) -> dict:
        email = (email or "").strip().lower()
        if not email or not password:
            raise AuthError("Enter your email and password.")
        user = self.repo.get_user_by_email(email)
        if user is None:
            raise AuthError("No account found with that email.")
        expected = _hash_password(password, user["pass_salt"])
        if not secrets.compare_digest(expected, user["pass_hash"]):
            raise AuthError("Incorrect password — try again.")
        token = self.repo.create_session(user["user_id"])
        return {
            "token": token,
            "user": {"user_id": user["user_id"], "name": user["name"], "email": user["email"]},
        }

    def me(self, token: str) -> dict | None:
        return self.repo.get_user_by_token(token)

    def signout(self, token: str) -> None:
        self.repo.delete_session(token)

    def guest(self) -> dict:
        """Anonymous demo session — lets evaluators explore personas without an account.

        Creates a throwaway user (unusable random password) with a real session token,
        so every existing auth path (me/signout) works unchanged.
        """
        email = f"guest_{secrets.token_hex(8)}@local.demo"
        salt = _new_salt()
        random_pw = secrets.token_hex(24)
        user = self.repo.create_user(
            new_id("guest"), "Guest Explorer", email,
            _hash_password(random_pw, salt), salt,
        )
        token = self.repo.create_session(user["user_id"])
        return {
            "token": token,
            "user": {"user_id": user["user_id"], "name": "Guest Explorer", "email": email, "guest": True},
        }
