import importlib

import src.auth.database as auth_db
import src.config as config
from src.auth.security import hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")

    assert verify_password("correct-horse-battery-staple", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_password_hashes_are_salted():
    hashed_one = hash_password("same-password")
    hashed_two = hash_password("same-password")

    assert hashed_one != hashed_two


def test_signup_and_login_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUTH_DB_FILE", tmp_path / "users.db")
    importlib.reload(auth_db)

    created, message = auth_db.create_user("Jane Doe", "jane@example.com", "supersecret")
    assert created is True

    duplicate, dup_message = auth_db.create_user(
        "Jane Doe", "jane@example.com", "supersecret"
    )
    assert duplicate is False
    assert "already exists" in dup_message

    success, _ = auth_db.authenticate_user("jane@example.com", "supersecret")
    assert success is True

    failure, _ = auth_db.authenticate_user("jane@example.com", "wrong-password")
    assert failure is False
