"""Auth endpoint tests: signup, signin, session restore, signout."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.server import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def creds():
    import uuid

    return {"name": "Ada Lovelace", "email": f"ada{uuid.uuid4().hex[:8]}@example.com", "password": "analytical-engine"}


def test_signup_creates_session(client, creds):
    res = client.post("/api/auth/signup", json=creds)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["token"]
    assert data["user"]["email"] == creds["email"]
    assert data["user"]["name"] == "Ada Lovelace"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == creds["email"]


def test_signup_validations(client):
    assert client.post("/api/auth/signup", json={"name": "", "email": "x@y.io", "password": "123456"}).status_code == 400
    assert client.post("/api/auth/signup", json={"name": "A", "email": "not-an-email", "password": "123456"}).status_code == 400
    assert client.post("/api/auth/signup", json={"name": "A", "email": "x@y.io", "password": "123"}).status_code == 400


def test_duplicate_email_rejected(client, creds):
    assert client.post("/api/auth/signup", json=creds).status_code == 200
    res = client.post("/api/auth/signup", json=creds)
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


def test_signin_roundtrip(client, creds):
    client.post("/api/auth/signup", json=creds)
    res = client.post("/api/auth/signin", json={"email": creds["email"], "password": creds["password"]})
    assert res.status_code == 200, res.text
    token = res.json()["token"]

    # wrong password rejected
    bad = client.post("/api/auth/signin", json={"email": creds["email"], "password": "wrong-pass"})
    assert bad.status_code == 401

    # unknown email rejected
    assert client.post("/api/auth/signin", json={"email": "nobody@example.com", "password": "x"}).status_code == 401

    # signout invalidates the token
    out = client.post("/api/auth/signout", headers={"Authorization": f"Bearer {token}"})
    assert out.status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_guest_mode_creates_demo_session(client):
    res = client.post("/api/auth/guest")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["token"]
    assert data["user"]["guest"] is True
    assert data["user"]["name"] == "Guest Explorer"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"].endswith("@local.demo")

    # guests can be signed out like any session
    out = client.post("/api/auth/signout", headers={"Authorization": f"Bearer {data['token']}"})
    assert out.status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"}).status_code == 401


def test_password_not_stored_in_plaintext(client, creds):
    client.post("/api/auth/signup", json=creds)
    from app.database.repository import _connect

    with _connect() as conn:
        row = conn.execute("SELECT pass_hash, pass_salt FROM users WHERE email = ?", (creds["email"],)).fetchone()
    assert row is not None
    assert row["pass_hash"] != creds["password"]
    assert len(row["pass_salt"]) == 32  # 16 random bytes hex
