"""
Tests for UserSettingsService (application/services/user_settings_service.py).

Tests cover:
- get_user_settings (default and existing)
- update_user_settings (language, currency, invalid values)
- get_supported_currencies
- get_currency_symbol
- validate_currency (valid and invalid)
- get_default_currency
- _validate_setting
"""

import os
import sqlite3
import tempfile
import unittest

from application.services.user_settings_service import SETTINGS_SCHEMA, UserSettingsService
from domain.entities.user_settings import UserSettings
from infrastructure.persistence.sqlite.repositories.user_settings_repository import (
    SQLiteUserSettingsDataSource,
)

USER_ID = "test_user"


class TestUserSettingsServiceDDD(unittest.TestCase):
    """Test suite for UserSettingsService with real SQLite database."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.db_path = self.temp_db.name
        self.temp_db.close()
        os.environ["DATABASE_PATH"] = self.db_path

        # Create needed tables
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
            parent_id TEXT DEFAULT '', user_id TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY, date TEXT NOT NULL, amount INTEGER NOT NULL,
            description TEXT NOT NULL, source TEXT NOT NULL, comment TEXT DEFAULT '',
            user_id TEXT, groups TEXT DEFAULT '[]', updated_at TEXT,
            mail_id TEXT, currency TEXT NOT NULL DEFAULT 'JPY',
            created_at TEXT NOT NULL DEFAULT (datetime('now')), fetcher_id TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS manual_assignments (
            tx_id TEXT PRIMARY KEY, category_id TEXT NOT NULL, user_id TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS regexps (
            id TEXT PRIMARY KEY, raw TEXT NOT NULL, name TEXT NOT NULL,
            internal_category TEXT NOT NULL, user_id TEXT,
            order_index INTEGER NOT NULL DEFAULT 0, visual_description TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS groups (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, user_id TEXT NOT NULL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS embeddings (
            tx_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            embedding BLOB NOT NULL, description_hash TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY, display_language TEXT DEFAULT 'en',
            default_currency TEXT DEFAULT 'USD', browser_settings TEXT,
            created_at TEXT, updated_at TEXT, llm_call_timestamps TEXT DEFAULT '[]')""")
        conn.commit()
        conn.close()

        # Create datasource instance
        self.us_ds = SQLiteUserSettingsDataSource(self.db_path, user_id=USER_ID)

        # Create service
        self.service = UserSettingsService(
            user_id=USER_ID, user_settings_datasource=self.us_ds, db_path=self.db_path
        )

    def tearDown(self):
        if "DATABASE_PATH" in os.environ:
            del os.environ["DATABASE_PATH"]
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    # --- get_user_settings ---

    def test_get_user_settings_default(self):
        """Test getting default settings when none exist."""
        settings = self.service.get_user_settings()
        self.assertIsNotNone(settings)
        self.assertIsInstance(settings, UserSettings)
        self.assertEqual(settings.user_id, USER_ID)
        self.assertEqual(settings.language, "en")
        self.assertEqual(settings.currency, "USD")

    def test_get_user_settings_after_update(self):
        """Test getting settings after an update."""
        self.service.update_user_settings(language="ja", currency="JPY")
        settings = self.service.get_user_settings()
        self.assertEqual(settings.language, "ja")
        self.assertEqual(settings.currency, "JPY")

    # --- update_user_settings ---

    def test_update_language(self):
        """Test updating just the language."""
        success, error = self.service.update_user_settings(language="fr")
        self.assertTrue(success)
        self.assertEqual(error, "")

        settings = self.service.get_user_settings()
        self.assertEqual(settings.language, "fr")
        # Currency should remain default
        self.assertEqual(settings.currency, "USD")

    def test_update_currency(self):
        """Test updating just the currency."""
        success, error = self.service.update_user_settings(currency="EUR")
        self.assertTrue(success)
        self.assertEqual(error, "")

        settings = self.service.get_user_settings()
        self.assertEqual(settings.currency, "EUR")
        # Language should remain default
        self.assertEqual(settings.language, "en")

    def test_update_both_language_and_currency(self):
        """Test updating both language and currency."""
        success, error = self.service.update_user_settings(language="ja", currency="JPY")
        self.assertTrue(success)

        settings = self.service.get_user_settings()
        self.assertEqual(settings.language, "ja")
        self.assertEqual(settings.currency, "JPY")

    def test_update_invalid_language(self):
        """Test updating with an invalid language code."""
        success, error = self.service.update_user_settings(language="invalid_lang")
        self.assertFalse(success)
        self.assertIn("Invalid value for language", error)

    def test_update_invalid_currency(self):
        """Test updating with an invalid currency code."""
        success, error = self.service.update_user_settings(currency="INVALID")
        self.assertFalse(success)
        self.assertIn("Invalid value for currency", error)

    def test_update_no_changes(self):
        """Test updating with no parameters is a no-op success."""
        # First set some values
        self.service.update_user_settings(language="ja", currency="JPY")

        # Update with no changes
        success, error = self.service.update_user_settings()
        self.assertTrue(success)

        # Values should remain unchanged
        settings = self.service.get_user_settings()
        self.assertEqual(settings.language, "ja")
        self.assertEqual(settings.currency, "JPY")

    def test_update_preserves_existing_values(self):
        """Test that updating one field preserves other fields."""
        self.service.update_user_settings(language="ja", currency="JPY")

        # Update only language
        self.service.update_user_settings(language="ko")

        settings = self.service.get_user_settings()
        self.assertEqual(settings.language, "ko")
        self.assertEqual(settings.currency, "JPY")  # Preserved

    # --- get_supported_currencies ---

    def test_get_supported_currencies(self):
        """Test getting list of supported currencies."""
        currencies = self.service.get_supported_currencies()
        self.assertIsInstance(currencies, list)
        self.assertGreater(len(currencies), 0)

        # Check structure
        first = currencies[0]
        self.assertIn("code", first)
        self.assertIn("symbol", first)
        self.assertIn("name", first)

    def test_get_supported_currencies_includes_common(self):
        """Test that common currencies are included."""
        currencies = self.service.get_supported_currencies()
        codes = [c["code"] for c in currencies]
        self.assertIn("USD", codes)
        self.assertIn("EUR", codes)
        self.assertIn("JPY", codes)
        self.assertIn("GBP", codes)

    # --- get_currency_symbol ---

    def test_get_currency_symbol_usd(self):
        """Test getting USD symbol."""
        symbol = self.service.get_currency_symbol("USD")
        self.assertEqual(symbol, "$")

    def test_get_currency_symbol_jpy(self):
        """Test getting JPY symbol."""
        symbol = self.service.get_currency_symbol("JPY")
        self.assertEqual(symbol, "¥")

    def test_get_currency_symbol_eur(self):
        """Test getting EUR symbol."""
        symbol = self.service.get_currency_symbol("EUR")
        self.assertEqual(symbol, "€")

    def test_get_currency_symbol_unknown(self):
        """Test getting symbol for unknown currency returns the code."""
        symbol = self.service.get_currency_symbol("XYZ")
        self.assertEqual(symbol, "XYZ")

    # --- validate_currency ---

    def test_validate_currency_valid(self):
        """Test validating supported currencies."""
        self.assertTrue(self.service.validate_currency("USD"))
        self.assertTrue(self.service.validate_currency("JPY"))
        self.assertTrue(self.service.validate_currency("EUR"))
        self.assertTrue(self.service.validate_currency("GBP"))

    def test_validate_currency_invalid(self):
        """Test validating unsupported currencies."""
        self.assertFalse(self.service.validate_currency("INVALID"))
        self.assertFalse(self.service.validate_currency(""))
        self.assertFalse(self.service.validate_currency("XYZ"))

    # --- get_default_currency ---

    def test_get_default_currency_no_settings(self):
        """Test default currency when no settings exist."""
        currency = self.service.get_default_currency()
        # Default from UserSettings entity
        self.assertEqual(currency, "USD")

    def test_get_default_currency_after_update(self):
        """Test default currency after changing settings."""
        self.service.update_user_settings(currency="JPY")
        currency = self.service.get_default_currency()
        self.assertEqual(currency, "JPY")

    # --- _validate_setting ---

    def test_validate_setting_valid_language(self):
        """Test validating a valid language setting."""
        is_valid, error = self.service._validate_setting("language", "en")
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

    def test_validate_setting_invalid_language(self):
        """Test validating an invalid language setting."""
        is_valid, error = self.service._validate_setting("language", "zz")
        self.assertFalse(is_valid)
        self.assertIn("Invalid value", error)

    def test_validate_setting_valid_currency(self):
        """Test validating a valid currency setting."""
        is_valid, error = self.service._validate_setting("currency", "USD")
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

    def test_validate_setting_invalid_currency(self):
        """Test validating an invalid currency setting."""
        is_valid, error = self.service._validate_setting("currency", "FAKE")
        self.assertFalse(is_valid)
        self.assertIn("Invalid value", error)

    def test_validate_setting_unknown_field(self):
        """Test validating an unknown setting field."""
        is_valid, error = self.service._validate_setting("unknown_field", "value")
        self.assertFalse(is_valid)
        self.assertIn("Unknown setting", error)

    # --- datasource property ---

    def test_datasource_property(self):
        """Test that datasource property returns the settings datasource."""
        ds = self.service.datasource
        self.assertEqual(ds, self.us_ds)

    # --- Multiple updates ---

    def test_multiple_sequential_updates(self):
        """Test multiple sequential updates work correctly."""
        self.service.update_user_settings(language="en", currency="USD")
        self.service.update_user_settings(language="ja")
        self.service.update_user_settings(currency="JPY")
        self.service.update_user_settings(language="fr", currency="EUR")

        settings = self.service.get_user_settings()
        self.assertEqual(settings.language, "fr")
        self.assertEqual(settings.currency, "EUR")

    # --- All supported languages ---

    def test_all_supported_languages_are_valid(self):
        """Test that all languages in the schema are accepted."""
        for lang in SETTINGS_SCHEMA["language"]["valid_values"]:
            is_valid, error = self.service._validate_setting("language", lang)
            self.assertTrue(is_valid, f"Language '{lang}' should be valid but got: {error}")


if __name__ == "__main__":
    unittest.main()
