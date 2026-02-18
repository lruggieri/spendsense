"""Tests for the SQLite fetcher repository."""

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from domain.entities.fetcher import Fetcher
from infrastructure.persistence.sqlite.repositories.fetcher_repository import (
    SQLiteFetcherDataSource,
)


class TestSQLiteFetcherRepository(unittest.TestCase):
    """Tests for SQLiteFetcherDataSource CRUD operations."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.temp_db.name
        self.temp_db.close()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE fetchers (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                from_emails TEXT NOT NULL DEFAULT '[]',
                subject_filter TEXT DEFAULT '',
                amount_pattern TEXT NOT NULL,
                merchant_pattern TEXT NOT NULL,
                currency_pattern TEXT DEFAULT '',
                default_currency TEXT DEFAULT 'JPY',
                negate_amount INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                group_id TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()

        self.user_id = "test_user"
        self.ds = SQLiteFetcherDataSource(self.db_path, self.user_id)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _make_fetcher(
        self, fetcher_id="f1", name="Test Fetcher", enabled=True, group_id=None, version=1
    ):
        """Helper to create a Fetcher entity."""
        now = datetime.now(timezone.utc)
        return Fetcher(
            id=fetcher_id,
            user_id=self.user_id,
            name=name,
            from_emails=["bank@example.com"],
            subject_filter="transaction",
            amount_pattern=r"\$(\d+\.\d{2})",
            merchant_pattern=r"at (.+)",
            currency_pattern="",
            default_currency="JPY",
            negate_amount=False,
            enabled=enabled,
            created_at=now,
            updated_at=now,
            group_id=group_id or fetcher_id,
            version=version,
        )

    def test_create_fetcher(self):
        """Creating a fetcher should persist it and return True."""
        fetcher = self._make_fetcher()
        result = self.ds.create_fetcher(fetcher)
        self.assertTrue(result)

        # Verify it was stored
        stored = self.ds.get_fetcher_by_id("f1")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.name, "Test Fetcher")
        self.assertEqual(stored.from_emails, ["bank@example.com"])
        self.assertEqual(stored.version, 1)

    def test_get_all_fetchers(self):
        """get_all_fetchers should return all fetchers for the user."""
        self.ds.create_fetcher(self._make_fetcher("f1", "Fetcher 1"))
        self.ds.create_fetcher(self._make_fetcher("f2", "Fetcher 2"))

        fetchers = self.ds.get_all_fetchers()
        self.assertEqual(len(fetchers), 2)
        names = {f.name for f in fetchers}
        self.assertIn("Fetcher 1", names)
        self.assertIn("Fetcher 2", names)

    def test_get_all_fetchers_filters_by_user(self):
        """get_all_fetchers should only return fetchers for the current user."""
        self.ds.create_fetcher(self._make_fetcher("f1"))

        # Insert fetcher for another user directly
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO fetchers (id, user_id, name, from_emails, subject_filter,
                amount_pattern, merchant_pattern, currency_pattern, default_currency,
                negate_amount, enabled, created_at, updated_at, group_id, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                "other_f1",
                "other_user",
                "Other",
                "[]",
                "",
                "p",
                "p",
                "",
                "USD",
                0,
                1,
                now,
                now,
                "other_f1",
                1,
            ),
        )
        conn.commit()
        conn.close()

        fetchers = self.ds.get_all_fetchers()
        self.assertEqual(len(fetchers), 1)
        self.assertEqual(fetchers[0].id, "f1")

    def test_get_enabled_fetchers(self):
        """get_enabled_fetchers should return only enabled fetchers."""
        self.ds.create_fetcher(self._make_fetcher("f1", "Enabled", enabled=True))
        self.ds.create_fetcher(self._make_fetcher("f2", "Disabled", enabled=False))

        enabled = self.ds.get_enabled_fetchers()
        self.assertEqual(len(enabled), 1)
        self.assertEqual(enabled[0].name, "Enabled")

    def test_get_enabled_fetchers_for_list(self):
        """get_enabled_fetchers_for_list should return only enabled fetchers."""
        self.ds.create_fetcher(self._make_fetcher("f1", "Active", enabled=True))
        self.ds.create_fetcher(self._make_fetcher("f2", "Inactive", enabled=False))

        fetchers = self.ds.get_enabled_fetchers_for_list()
        self.assertEqual(len(fetchers), 1)
        self.assertEqual(fetchers[0].name, "Active")

    def test_get_fetcher_by_id_found(self):
        """get_fetcher_by_id should return the fetcher when it exists."""
        self.ds.create_fetcher(self._make_fetcher("f1", "My Fetcher"))
        fetcher = self.ds.get_fetcher_by_id("f1")
        self.assertIsNotNone(fetcher)
        self.assertEqual(fetcher.id, "f1")
        self.assertEqual(fetcher.name, "My Fetcher")

    def test_get_fetcher_by_id_not_found(self):
        """get_fetcher_by_id should return None for non-existent ID."""
        fetcher = self.ds.get_fetcher_by_id("nonexistent")
        self.assertIsNone(fetcher)

    def test_get_fetcher_versions(self):
        """get_fetcher_versions should return all versions with the same group_id."""
        group = "group_abc"
        self.ds.create_fetcher(self._make_fetcher("f1", "V1", group_id=group, version=1))
        self.ds.create_fetcher(self._make_fetcher("f2", "V2", group_id=group, version=2))

        versions = self.ds.get_fetcher_versions(group)
        self.assertEqual(len(versions), 2)
        # Should be ordered by version DESC
        self.assertEqual(versions[0].version, 2)
        self.assertEqual(versions[1].version, 1)

    def test_get_enabled_version(self):
        """get_enabled_version should return the enabled version in a group."""
        group = "group_abc"
        self.ds.create_fetcher(
            self._make_fetcher("f1", "V1", enabled=False, group_id=group, version=1)
        )
        self.ds.create_fetcher(
            self._make_fetcher("f2", "V2", enabled=True, group_id=group, version=2)
        )

        enabled = self.ds.get_enabled_version(group)
        self.assertIsNotNone(enabled)
        self.assertEqual(enabled.id, "f2")
        self.assertEqual(enabled.version, 2)

    def test_get_enabled_version_none(self):
        """get_enabled_version should return None if no enabled version exists."""
        group = "group_abc"
        self.ds.create_fetcher(
            self._make_fetcher("f1", "V1", enabled=False, group_id=group, version=1)
        )

        enabled = self.ds.get_enabled_version(group)
        self.assertIsNone(enabled)

    def test_create_new_version(self):
        """create_new_version should disable old and create new version."""
        # Create original
        self.ds.create_fetcher(self._make_fetcher("f1", "Original"))

        # Create new version
        new_fetcher = self._make_fetcher("f2", "Updated")
        result = self.ds.create_new_version("f1", new_fetcher)
        self.assertIsNotNone(result)
        self.assertEqual(result.version, 2)
        self.assertTrue(result.enabled)
        self.assertEqual(result.group_id, "f1")  # group_id should be original fetcher's group

        # Old version should be disabled
        old = self.ds.get_fetcher_by_id("f1")
        self.assertFalse(old.enabled)

    def test_create_new_version_not_found(self):
        """create_new_version should return None when old fetcher not found."""
        new_fetcher = self._make_fetcher("f2", "New")
        result = self.ds.create_new_version("nonexistent", new_fetcher)
        self.assertIsNone(result)

    def test_toggle_fetcher_enabled(self):
        """toggle_fetcher_enabled should flip enabled state."""
        self.ds.create_fetcher(self._make_fetcher("f1", enabled=True))

        # Toggle to disabled
        result = self.ds.toggle_fetcher_enabled("f1")
        self.assertFalse(result)

        # Toggle back to enabled
        result = self.ds.toggle_fetcher_enabled("f1")
        self.assertTrue(result)

    def test_toggle_fetcher_enabled_disables_others_in_group(self):
        """Enabling a fetcher should disable other enabled versions in the group."""
        group = "group_abc"
        self.ds.create_fetcher(
            self._make_fetcher("f1", "V1", enabled=True, group_id=group, version=1)
        )
        self.ds.create_fetcher(
            self._make_fetcher("f2", "V2", enabled=False, group_id=group, version=2)
        )

        # Enable f2 -- should disable f1
        result = self.ds.toggle_fetcher_enabled("f2")
        self.assertTrue(result)

        f1 = self.ds.get_fetcher_by_id("f1")
        self.assertFalse(f1.enabled)
        f2 = self.ds.get_fetcher_by_id("f2")
        self.assertTrue(f2.enabled)

    def test_toggle_fetcher_enabled_not_found(self):
        """toggle_fetcher_enabled should return None for non-existent fetcher."""
        result = self.ds.toggle_fetcher_enabled("nonexistent")
        self.assertIsNone(result)

    def test_delete_fetcher(self):
        """delete_fetcher should remove the fetcher."""
        self.ds.create_fetcher(self._make_fetcher("f1"))
        result = self.ds.delete_fetcher("f1")
        self.assertTrue(result)

        # Verify it's gone
        fetcher = self.ds.get_fetcher_by_id("f1")
        self.assertIsNone(fetcher)

    def test_update_fetcher(self):
        """update_fetcher should update fields in place."""
        self.ds.create_fetcher(self._make_fetcher("f1", "Original"))

        fetcher = self.ds.get_fetcher_by_id("f1")
        fetcher.name = "Updated Name"
        fetcher.from_emails = ["new@example.com", "other@example.com"]
        result = self.ds.update_fetcher(fetcher)
        self.assertTrue(result)

        updated = self.ds.get_fetcher_by_id("f1")
        self.assertEqual(updated.name, "Updated Name")
        self.assertEqual(updated.from_emails, ["new@example.com", "other@example.com"])

    def test_negate_amount_roundtrip(self):
        """negate_amount boolean should survive create/read cycle."""
        fetcher = self._make_fetcher("f1")
        fetcher.negate_amount = True
        self.ds.create_fetcher(fetcher)

        stored = self.ds.get_fetcher_by_id("f1")
        self.assertTrue(stored.negate_amount)


if __name__ == "__main__":
    unittest.main()
