from __future__ import annotations

import os
import secrets
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend import database as database_module
from backend import seed_data
from backend.kvkk_security import verify_password


class InitialAdministratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "lavox.db"
        self.database_patches = (
            patch.object(database_module, "DATABASE_PATH", self.database_path),
            patch.object(
                database_module,
                "LEGACY_DATABASE_PATH",
                Path(self.temporary_directory.name) / "legacy.sqlite3",
            ),
        )
        for database_patch in self.database_patches:
            database_patch.start()
            self.addCleanup(database_patch.stop)
        self.environment_patch = patch.dict(os.environ, {}, clear=True)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _user_count(self) -> int:
        with closing(sqlite3.connect(self.database_path)) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def test_requires_explicit_credentials_without_creating_a_default_account(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "LAVOX_INITIAL_ADMIN_PASSWORD"):
            seed_data.seed()

        self.assertEqual(self._user_count(), 0)

    def test_rejects_a_short_initial_password(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LAVOX_INITIAL_ADMIN_USERNAME": "operator",
                "LAVOX_INITIAL_ADMIN_EMAIL": "operator" + "@example.invalid",
                "LAVOX_INITIAL_ADMIN_PASSWORD": "short",
            },
        ):
            with self.assertRaisesRegex(ValueError, "at least 14 characters"):
                seed_data.seed()

        self.assertEqual(self._user_count(), 0)

    def test_creates_only_a_hashed_admin_and_preserves_existing_users(self) -> None:
        password = secrets.token_urlsafe(24)
        with patch.dict(
            os.environ,
            {
                "LAVOX_INITIAL_ADMIN_USERNAME": "operator",
                "LAVOX_INITIAL_ADMIN_EMAIL": "operator" + "@example.invalid",
                "LAVOX_INITIAL_ADMIN_PASSWORD": password,
            },
        ):
            seed_data.seed()

        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                "SELECT username, email, role, password_hash FROM users"
            ).fetchone()
        self.assertEqual(row[:3], ("operator", "operator" + "@example.invalid", "Admin"))
        self.assertNotEqual(row[3], password)
        self.assertTrue(verify_password(password, row[3]))

        with patch.dict(os.environ, {}, clear=True):
            seed_data.seed()
        self.assertEqual(self._user_count(), 1)


if __name__ == "__main__":
    unittest.main()
