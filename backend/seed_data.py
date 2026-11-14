from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from backend.database import database, initialize_database
    from backend.kvkk_security import hash_password
except ImportError:
    from database import database, initialize_database
    from kvkk_security import hash_password


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ADMIN_ENVIRONMENT = (
    "LAVOX_INITIAL_ADMIN_USERNAME",
    "LAVOX_INITIAL_ADMIN_EMAIL",
    "LAVOX_INITIAL_ADMIN_PASSWORD",
)


def _initial_admin() -> tuple[str, str, str]:
    username = os.environ.get(_ADMIN_ENVIRONMENT[0], "").strip()
    email = os.environ.get(_ADMIN_ENVIRONMENT[1], "").strip()
    password = os.environ.get(_ADMIN_ENVIRONMENT[2], "")
    if not username or not email or not password:
        raise RuntimeError(
            "Set LAVOX_INITIAL_ADMIN_USERNAME, LAVOX_INITIAL_ADMIN_EMAIL, and "
            "LAVOX_INITIAL_ADMIN_PASSWORD before first-time initialization."
        )
    if len(username) > 64 or len(username) < 3:
        raise ValueError("The initial administrator username must be 3 to 64 characters.")
    if len(email) > 254 or not _EMAIL_PATTERN.fullmatch(email):
        raise ValueError("The initial administrator email address is invalid.")
    if len(password) < 14:
        raise ValueError("The initial administrator password must contain at least 14 characters.")
    return username, email, password


def seed() -> None:
    initialize_database()
    with database() as connection:
        if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return

        username, email, password = _initial_admin()
        connection.execute(
            """
            INSERT INTO users (username, email, password_hash, role, is_active, created_at)
            VALUES (?, ?, ?, 'Admin', 1, strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
            """,
            (username, email, hash_password(password)),
        )
    print("Initial administrator created.")


if __name__ == "__main__":
    seed()
