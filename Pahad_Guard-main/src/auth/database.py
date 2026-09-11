"""Lightweight SQLite user store for the login / signup feature.

Kept dependency-free (uses Python's built-in sqlite3) so the rest of the
project's requirements don't need to change just to support authentication.

Roles
-----
Every account belongs to one of three roles (see src/config.py:ROLES):

* ``user``       — public/citizen view: personal alert, risk map, alerts
* ``department`` — full operational dashboard (all information pages)
* ``admin``      — everything the department sees, plus the database/admin
                   panel where roles can be managed.

The role is a column on the existing ``users`` table (no parallel auth
system). Existing databases are migrated on startup by adding the column
with a default of ``user``.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.auth.security import hash_password, verify_password
from src.config import AUTH_DB_FILE, DEFAULT_ROLE, ROLES


def _get_connection() -> sqlite3.Connection:
    AUTH_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(AUTH_DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def init_user_db() -> None:
    """Create the users table (with its role/dept_id columns) if it doesn't
    already exist, migrate legacy databases that predate them, and make sure
    the audit-log tables (auth logs + prediction/geo history) exist."""
    with _get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                dept_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        columns = [row[1] for row in connection.execute("PRAGMA table_info(users)")]
        if "role" not in columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
            )
        if "dept_id" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN dept_id TEXT")

        # Audit log: every login/signup attempt (success or failure).
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                email TEXT,
                full_name TEXT,
                role TEXT,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT
            )
            """
        )

        # Geographic + prediction history: every risk lookup made anywhere
        # in the app (coordinate analysis, simulator, personal location).
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS prediction_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_email TEXT,
                user_role TEXT,
                source TEXT NOT NULL,
                zone_id TEXT,
                latitude REAL,
                longitude REAL,
                location_description TEXT,
                rainfall_24h REAL,
                rainfall_3day REAL,
                rainfall_7day REAL,
                soil_moisture REAL,
                elevation REAL,
                slope REAL,
                land_cover TEXT,
                historical_landslide INTEGER,
                risk_score REAL,
                risk_level TEXT,
                alert_level TEXT,
                model_probability REAL
            )
            """
        )

    seed_demo_accounts()


def _validate_role(role: str) -> str:
    return role if role in ROLES else DEFAULT_ROLE


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    with _get_connection() as connection:
        cursor = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        )
        return cursor.fetchone()


def get_user_role(email: str) -> str:
    """Return the role for an email address (defaults to 'user')."""
    user = get_user_by_email(email)
    return user["role"] if user is not None else DEFAULT_ROLE


def get_user_dept_id(email: str) -> Optional[str]:
    """Return the stored Department ID for an email address, if any."""
    user = get_user_by_email(email)
    return user["dept_id"] if user is not None else None


def verify_department_id(email: str, dept_id: str) -> bool:
    """Check a login-time Department ID against the one stored at signup."""
    stored = (get_user_dept_id(email) or "").strip().lower()
    supplied = (dept_id or "").strip().lower()
    return bool(stored) and stored == supplied


def create_user(
    full_name: str,
    email: str,
    password: str,
    role: str = DEFAULT_ROLE,
    dept_id: Optional[str] = None,
) -> tuple[bool, str]:
    """Create a new user. Returns (success, message).

    ``dept_id`` is required (by the UI layer) for Department signups and is
    stored so the same ID must be re-entered on every future login.
    """
    email = email.strip().lower()

    if get_user_by_email(email) is not None:
        return False, "An account with this email already exists."

    password_hash = hash_password(password)
    created_at = datetime.now(timezone.utc).isoformat()
    validated_role = _validate_role(role)
    clean_dept_id = dept_id.strip() if dept_id and dept_id.strip() else None

    with _get_connection() as connection:
        connection.execute(
            "INSERT INTO users (full_name, email, password_hash, role, dept_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                full_name.strip(),
                email,
                password_hash,
                validated_role,
                clean_dept_id,
                created_at,
            ),
        )

    return True, "Account created successfully."


def authenticate_user(email: str, password: str) -> tuple[bool, str]:
    """Verify credentials. Returns (success, message)."""
    user = get_user_by_email(email)

    if user is None:
        return False, "No account found with this email."

    if not verify_password(password, user["password_hash"]):
        return False, "Incorrect password."

    return True, "Login successful."


def list_users() -> list[dict]:
    """All users (id, full_name, email, role, dept_id, created_at) for the
    admin panel."""
    with _get_connection() as connection:
        rows = connection.execute(
            "SELECT id, full_name, email, role, dept_id, created_at "
            "FROM users ORDER BY created_at"
        ).fetchall()
    return [dict(row) for row in rows]


def update_user_role(user_id: int, role: str) -> tuple[bool, str]:
    """Change a user's role. Returns (success, message).

    Refuses to demote the last remaining admin so the system can never be
    locked out of admin access.
    """
    role = _validate_role(role)

    with _get_connection() as connection:
        target = connection.execute(
            "SELECT id, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target is None:
            return False, "No user found with that id."

        if target["role"] == "admin" and role != "admin":
            admin_count = connection.execute(
                "SELECT COUNT(*) AS n FROM users WHERE role = 'admin'"
            ).fetchone()["n"]
            if admin_count <= 1:
                return False, (
                    "Cannot change the last admin's role — the system would "
                    "have no administrators left."
                )

        connection.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))

    return True, "Role updated."


# ---------------------------------------------------------------------------
# Audit log: every login/signup attempt
# ---------------------------------------------------------------------------


def log_auth_event(
    email: str,
    full_name: Optional[str],
    role: str,
    action: str,
    status: str,
    details: str = "",
) -> None:
    """Record one login/signup attempt (successful or not) for the admin
    audit trail shown on the Database page. Never raises."""
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with _get_connection() as connection:
            connection.execute(
                "INSERT INTO auth_logs (timestamp, email, full_name, role, action, "
                "status, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    timestamp,
                    (email or "").strip().lower(),
                    full_name,
                    role,
                    action,
                    status,
                    details,
                ),
            )
    except sqlite3.Error:
        pass


def list_auth_logs() -> list[dict]:
    """All login/signup attempts, most recent first, for the admin panel."""
    with _get_connection() as connection:
        rows = connection.execute(
            "SELECT id, timestamp, email, full_name, role, action, status, details "
            "FROM auth_logs ORDER BY timestamp DESC"
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Geographic + prediction history (downloadable as an invoice/report)
# ---------------------------------------------------------------------------


def log_prediction(record: dict) -> None:
    """Persist one geographic/prediction lookup (coordinate analysis,
    rainfall simulation, personal-location alert, ...) for history and
    invoice export. Never raises — a logging failure must not break the
    dashboard."""
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with _get_connection() as connection:
            connection.execute(
                """
                INSERT INTO prediction_logs (
                    timestamp, user_email, user_role, source, zone_id, latitude,
                    longitude, location_description, rainfall_24h, rainfall_3day,
                    rainfall_7day, soil_moisture, elevation, slope, land_cover,
                    historical_landslide, risk_score, risk_level, alert_level,
                    model_probability
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    record.get("user_email"),
                    record.get("user_role"),
                    record.get("source"),
                    record.get("zone_id"),
                    record.get("latitude"),
                    record.get("longitude"),
                    record.get("location_description"),
                    record.get("rainfall_24h"),
                    record.get("rainfall_3day"),
                    record.get("rainfall_7day"),
                    record.get("soil_moisture"),
                    record.get("elevation"),
                    record.get("slope"),
                    record.get("land_cover"),
                    record.get("historical_landslide"),
                    record.get("risk_score"),
                    record.get("risk_level"),
                    record.get("alert_level"),
                    record.get("model_probability"),
                ),
            )
    except sqlite3.Error:
        pass


def list_prediction_logs() -> list[dict]:
    """All stored geographic/prediction history, most recent first."""
    with _get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM prediction_logs ORDER BY timestamp DESC"
        ).fetchall()
    return [dict(row) for row in rows]


DEMO_ACCOUNTS = [
    ("Demo Admin", "admin@pahadguard.com", "admin123", "admin", None),
    (
        "Demo Department Officer",
        "department@pahadguard.com",
        "dept123",
        "department",
        "DEPT-0001",
    ),
    ("Demo Citizen", "user@pahadguard.com", "user123", "user", None),
]


def seed_demo_accounts() -> None:
    """Seed one demo account per role when no admin account exists yet.

    This keeps the three-role demo ready to log in for evaluations while
    never touching an existing user base — if a real admin already exists,
    nothing is created.
    """
    with _get_connection() as connection:
        admin_count = connection.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'admin'"
        ).fetchone()["n"]

    if admin_count > 0:
        return

    for full_name, email, password, role, dept_id in DEMO_ACCOUNTS:
        create_user(full_name, email, password, role=role, dept_id=dept_id)


# Ensure the schema (and migration) exists as soon as the module is imported;
# this also keeps tests that call create_user() directly working without an
# explicit init_user_db() call.
init_user_db()
