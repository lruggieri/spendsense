"""Tests for SQLiteUserSettingsDataSource."""
import unittest
import tempfile
import os
import sqlite3
from infrastructure.persistence.sqlite.repositories.user_settings_repository import SQLiteUserSettingsDataSource
from domain.entities.user_settings import UserSettings


class TestUserSettingsDataSource(unittest.TestCase):
    def setUp(self):
        """Create temporary database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()
        self.user_id = "test_user@example.com"
        self.datasource = SQLiteUserSettingsDataSource(self.db_path, self.user_id)

    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_table_creation(self):
        """Should create user_settings table on initialization."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='user_settings'
        """)
        table_exists = cursor.fetchone() is not None
        self.assertTrue(table_exists)

        # Check columns
        cursor.execute("PRAGMA table_info(user_settings)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        self.assertIn('user_id', columns)
        self.assertIn('display_language', columns)
        self.assertIn('default_currency', columns)
        self.assertIn('created_at', columns)
        self.assertIn('updated_at', columns)

        conn.close()

    def test_get_settings_returns_defaults_when_not_found(self):
        """Should return default settings for users without a record."""
        settings = self.datasource.get_settings()

        self.assertIsInstance(settings, UserSettings)
        self.assertEqual(settings.user_id, self.user_id)
        self.assertEqual(settings.language, 'en')
        self.assertEqual(settings.currency, 'USD')
        self.assertIsNone(settings.created_at)
        self.assertIsNone(settings.updated_at)

    def test_get_settings_returns_entity_with_correct_field_names(self):
        """Should return UserSettings with entity field names (not DB column names)."""
        # Insert directly to DB with DB column names
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_settings
            (user_id, display_language, default_currency, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (self.user_id, 'es', 'EUR', '2025-01-04T10:00:00Z', '2025-01-04T10:00:00Z'))
        conn.commit()
        conn.close()

        # Get settings through datasource
        settings = self.datasource.get_settings()

        # Should use entity field names, not DB column names
        self.assertEqual(settings.language, 'es')  # Not display_language
        self.assertEqual(settings.currency, 'EUR')  # Not default_currency
        self.assertIsNotNone(settings.created_at)
        self.assertIsNotNone(settings.updated_at)

    def test_update_settings_creates_new_record(self):
        """Should insert new settings when they don't exist."""
        settings = UserSettings(
            user_id=self.user_id,
            language='es',
            currency='EUR'
        )

        success, error = self.datasource.update_settings(settings)

        self.assertTrue(success)
        self.assertEqual(error, "")

        # Verify in database
        retrieved = self.datasource.get_settings()
        self.assertEqual(retrieved.language, 'es')
        self.assertEqual(retrieved.currency, 'EUR')
        self.assertIsNotNone(retrieved.created_at)
        self.assertIsNotNone(retrieved.updated_at)

    def test_update_settings_updates_existing_record(self):
        """Should update existing settings."""
        # Create initial settings
        initial = UserSettings(user_id=self.user_id, language='en', currency='USD')
        self.datasource.update_settings(initial)

        # Update settings
        updated = UserSettings(user_id=self.user_id, language='fr', currency='EUR')
        success, error = self.datasource.update_settings(updated)

        self.assertTrue(success)
        self.assertEqual(error, "")

        # Verify update
        retrieved = self.datasource.get_settings()
        self.assertEqual(retrieved.language, 'fr')
        self.assertEqual(retrieved.currency, 'EUR')

    def test_update_settings_maps_entity_fields_to_db_columns(self):
        """Should map entity field names to DB column names."""
        settings = UserSettings(
            user_id=self.user_id,
            language='ja',  # Entity field
            currency='JPY'  # Entity field
        )

        success, error = self.datasource.update_settings(settings)
        self.assertTrue(success)

        # Verify DB has correct column names
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT display_language, default_currency FROM user_settings WHERE user_id = ?',
                      (self.user_id,))
        row = cursor.fetchone()
        conn.close()

        self.assertEqual(row[0], 'ja')  # DB column: display_language
        self.assertEqual(row[1], 'JPY')  # DB column: default_currency

    def test_repository_persists_without_validation(self):
        """
        Repository should persist any values without validation.
        Validation is now handled at the service layer.
        """
        # Test that repository accepts and persists any language value
        settings1 = UserSettings(
            user_id=self.user_id,
            language='invalid',
            currency='USD'
        )
        success1, error1 = self.datasource.update_settings(settings1)
        self.assertTrue(success1)
        self.assertEqual(error1, "")

        # Test that repository accepts and persists any currency value
        settings2 = UserSettings(
            user_id=self.user_id,
            language='en',
            currency='INVALID'
        )
        success2, error2 = self.datasource.update_settings(settings2)
        self.assertTrue(success2)
        self.assertEqual(error2, "")

    def test_validation_accepts_valid_values(self):
        """Should accept all valid language and currency codes."""
        valid_combinations = [
            ('en', 'USD'), ('es', 'EUR'), ('fr', 'GBP'),
            ('de', 'CHF'), ('it', 'JPY'), ('pt', 'CNY')
        ]

        for language, currency in valid_combinations:
            settings = UserSettings(
                user_id=self.user_id,
                language=language,
                currency=currency
            )

            success, error = self.datasource.update_settings(settings)
            self.assertTrue(success, f"Failed for {language}/{currency}: {error}")

    def test_multi_user_isolation(self):
        """Should isolate settings per user."""
        user1_id = "user1@example.com"
        user2_id = "user2@example.com"

        datasource1 = SQLiteUserSettingsDataSource(self.db_path, user1_id)
        datasource2 = SQLiteUserSettingsDataSource(self.db_path, user2_id)

        # Set different settings for each user
        settings1 = UserSettings(user_id=user1_id, language='en', currency='USD')
        settings2 = UserSettings(user_id=user2_id, language='es', currency='EUR')

        datasource1.update_settings(settings1)
        datasource2.update_settings(settings2)

        # Verify isolation
        retrieved1 = datasource1.get_settings()
        retrieved2 = datasource2.get_settings()

        self.assertEqual(retrieved1.language, 'en')
        self.assertEqual(retrieved1.currency, 'USD')
        self.assertEqual(retrieved2.language, 'es')
        self.assertEqual(retrieved2.currency, 'EUR')

    def test_timestamps_are_set_correctly(self):
        """Should set created_at and updated_at timestamps."""
        settings = UserSettings(user_id=self.user_id, language='en', currency='USD')

        self.datasource.update_settings(settings)
        retrieved = self.datasource.get_settings()

        self.assertIsNotNone(retrieved.created_at)
        self.assertIsNotNone(retrieved.updated_at)

        # Timestamps should be roughly equal for new records
        time_diff = abs((retrieved.updated_at - retrieved.created_at).total_seconds())
        self.assertLess(time_diff, 1.0)  # Less than 1 second difference

    def test_llm_call_timestamps_column_exists(self):
        """Should have llm_call_timestamps column."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(user_settings)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        self.assertIn('llm_call_timestamps', columns)

    def test_get_llm_call_timestamps_returns_empty_list_for_new_user(self):
        """Should return empty list for user without timestamps."""
        timestamps = self.datasource.get_llm_call_timestamps()
        self.assertEqual(timestamps, [])

    def test_update_llm_call_timestamps_stores_timestamps(self):
        """Should store and retrieve LLM call timestamps."""
        from datetime import datetime as dt, timezone
        now = dt.now(timezone.utc)
        timestamps = [now]

        success = self.datasource.update_llm_call_timestamps(timestamps)
        self.assertTrue(success)

        retrieved = self.datasource.get_llm_call_timestamps()
        self.assertEqual(len(retrieved), 1)
        # Allow 1 second tolerance for serialization
        time_diff = abs((retrieved[0] - now).total_seconds())
        self.assertLess(time_diff, 1.0)

    def test_update_llm_call_timestamps_creates_record_if_not_exists(self):
        """Should create user settings record if it doesn't exist."""
        from datetime import datetime as dt, timezone
        new_user_id = "new_user@example.com"
        new_datasource = SQLiteUserSettingsDataSource(self.db_path, new_user_id)

        now = dt.now(timezone.utc)
        success = new_datasource.update_llm_call_timestamps([now])

        self.assertTrue(success)

        # Verify record was created with default values
        settings = new_datasource.get_settings()
        self.assertEqual(settings.user_id, new_user_id)
        self.assertEqual(settings.language, 'en')
        self.assertEqual(settings.currency, 'USD')
        self.assertEqual(len(settings.llm_call_timestamps), 1)

    def test_update_llm_call_timestamps_preserves_multiple_timestamps(self):
        """Should correctly store and retrieve multiple timestamps."""
        from datetime import datetime as dt, timezone, timedelta
        base_time = dt.now(timezone.utc)
        timestamps = [base_time - timedelta(hours=i) for i in range(5)]

        success = self.datasource.update_llm_call_timestamps(timestamps)
        self.assertTrue(success)

        retrieved = self.datasource.get_llm_call_timestamps()
        self.assertEqual(len(retrieved), 5)

    def test_settings_entity_includes_llm_call_timestamps(self):
        """Should include llm_call_timestamps in UserSettings entity."""
        from datetime import datetime as dt, timezone
        now = dt.now(timezone.utc)

        # Update timestamps
        self.datasource.update_llm_call_timestamps([now])

        # Get full settings
        settings = self.datasource.get_settings()

        self.assertEqual(len(settings.llm_call_timestamps), 1)

    def test_update_settings_preserves_llm_call_timestamps(self):
        """Should preserve llm_call_timestamps when updating other settings."""
        from datetime import datetime as dt, timezone
        now = dt.now(timezone.utc)

        # First, add some timestamps
        self.datasource.update_llm_call_timestamps([now])

        # Then update language/currency
        settings = UserSettings(
            user_id=self.user_id,
            language='es',
            currency='EUR',
            llm_call_timestamps=[now]
        )
        self.datasource.update_settings(settings)

        # Verify timestamps are preserved
        retrieved = self.datasource.get_settings()
        self.assertEqual(retrieved.language, 'es')
        self.assertEqual(len(retrieved.llm_call_timestamps), 1)


if __name__ == '__main__':
    unittest.main()
