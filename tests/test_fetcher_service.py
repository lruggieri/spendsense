"""Tests for the FetcherService application service."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from application.services.fetcher_service import FetcherService
from domain.entities.fetcher import Fetcher


class TestFetcherService(unittest.TestCase):
    """Tests for FetcherService business logic."""

    def setUp(self):
        self.user_id = "test_user"
        self.mock_ds = MagicMock()
        self.mock_settings = MagicMock()
        self.mock_settings.get_default_currency.return_value = "JPY"
        self.mock_settings.validate_currency.return_value = True

        self.service = FetcherService(
            user_id=self.user_id,
            fetcher_datasource=self.mock_ds,
            user_settings_service=self.mock_settings,
            db_path="/tmp/test.db",  # nosec B108 - hardcoded tmp path is fine in tests
        )

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
            subject_filter="",
            amount_pattern=r"\$(\d+)",
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

    def test_get_all_fetchers(self):
        """get_all_fetchers should delegate to the datasource."""
        expected = [self._make_fetcher("f1"), self._make_fetcher("f2")]
        self.mock_ds.get_all_fetchers.return_value = expected

        result = self.service.get_all_fetchers()
        self.assertEqual(result, expected)
        self.mock_ds.get_all_fetchers.assert_called_once()

    def test_get_enabled_fetchers(self):
        """get_enabled_fetchers should delegate to the datasource."""
        expected = [self._make_fetcher("f1")]
        self.mock_ds.get_enabled_fetchers.return_value = expected

        result = self.service.get_enabled_fetchers()
        self.assertEqual(result, expected)
        self.mock_ds.get_enabled_fetchers.assert_called_once()

    def test_count_fetchers(self):
        """count_fetchers should return the number of enabled fetchers for list."""
        self.mock_ds.get_enabled_fetchers_for_list.return_value = [
            self._make_fetcher("f1"),
            self._make_fetcher("f2"),
        ]
        self.assertEqual(self.service.count_fetchers(), 2)

    def test_get_fetcher_by_id(self):
        """get_fetcher_by_id should delegate to the datasource."""
        expected = self._make_fetcher("f1")
        self.mock_ds.get_fetcher_by_id.return_value = expected

        result = self.service.get_fetcher_by_id("f1")
        self.assertEqual(result, expected)
        self.mock_ds.get_fetcher_by_id.assert_called_once_with("f1")

    @patch("application.services.fetcher_service.uuid7")
    def test_create_fetcher_success(self, mock_uuid7):
        """create_fetcher should create a fetcher successfully with valid input."""
        mock_uuid7.return_value = "generated-uuid"
        self.mock_ds.create_fetcher.return_value = True

        success, error, fetcher_id = self.service.create_fetcher(
            name="My Fetcher",
            from_emails=["bank@example.com"],
            subject_filter="transaction",
            amount_pattern=r"\$(\d+)",
            merchant_pattern=r"at (.+)",
        )

        self.assertTrue(success)
        self.assertEqual(error, "")
        self.assertEqual(fetcher_id, "generated-uuid")
        self.mock_ds.create_fetcher.assert_called_once()

    def test_create_fetcher_missing_name(self):
        """create_fetcher should fail when name is missing."""
        success, error, fetcher_id = self.service.create_fetcher(
            name="",
            from_emails=["bank@example.com"],
            subject_filter="",
            amount_pattern=r"\$(\d+)",
            merchant_pattern=r"at (.+)",
        )

        self.assertFalse(success)
        self.assertIn("name", error.lower())
        self.assertEqual(fetcher_id, "")

    def test_create_fetcher_missing_emails(self):
        """create_fetcher should fail when from_emails is empty."""
        success, error, fetcher_id = self.service.create_fetcher(
            name="Fetcher",
            from_emails=[],
            subject_filter="",
            amount_pattern=r"\$(\d+)",
            merchant_pattern=r"at (.+)",
        )

        self.assertFalse(success)
        self.assertIn("email", error.lower())

    def test_create_fetcher_missing_amount_pattern(self):
        """create_fetcher should fail when amount_pattern is missing."""
        success, error, fetcher_id = self.service.create_fetcher(
            name="Fetcher",
            from_emails=["bank@example.com"],
            subject_filter="",
            amount_pattern="",
            merchant_pattern=r"at (.+)",
        )

        self.assertFalse(success)
        self.assertIn("amount", error.lower())

    def test_create_fetcher_missing_merchant_pattern(self):
        """create_fetcher should fail when merchant_pattern is missing."""
        success, error, fetcher_id = self.service.create_fetcher(
            name="Fetcher",
            from_emails=["bank@example.com"],
            subject_filter="",
            amount_pattern=r"\$(\d+)",
            merchant_pattern="",
        )

        self.assertFalse(success)
        self.assertIn("merchant", error.lower())

    def test_create_fetcher_invalid_currency(self):
        """create_fetcher should fail with unsupported currency."""
        self.mock_settings.validate_currency.return_value = False

        success, error, fetcher_id = self.service.create_fetcher(
            name="Fetcher",
            from_emails=["bank@example.com"],
            subject_filter="",
            amount_pattern=r"\$(\d+)",
            merchant_pattern=r"at (.+)",
            default_currency="INVALID",
        )

        self.assertFalse(success)
        self.assertIn("currency", error.lower())

    @patch("application.services.fetcher_service.uuid7")
    def test_update_fetcher_success(self, mock_uuid7):
        """update_fetcher should create a new version with updated fields."""
        mock_uuid7.return_value = "new-uuid"
        existing = self._make_fetcher("f1")
        self.mock_ds.get_fetcher_by_id.return_value = existing

        updated_fetcher = self._make_fetcher("new-uuid", "Updated")
        self.mock_ds.create_new_version.return_value = updated_fetcher

        success, error, new_id = self.service.update_fetcher("f1", name="Updated")

        self.assertTrue(success)
        self.assertEqual(error, "")
        self.assertEqual(new_id, "new-uuid")
        self.mock_ds.create_new_version.assert_called_once()

    def test_update_fetcher_not_found(self):
        """update_fetcher should fail when the fetcher doesn't exist."""
        self.mock_ds.get_fetcher_by_id.return_value = None

        success, error, new_id = self.service.update_fetcher("nonexistent", name="Updated")

        self.assertFalse(success)
        self.assertIn("not found", error.lower())

    def test_toggle_fetcher_enabled_success(self):
        """toggle_fetcher_enabled should return new state on success."""
        self.mock_ds.toggle_fetcher_enabled.return_value = False

        success, error, new_state = self.service.toggle_fetcher_enabled("f1")

        self.assertTrue(success)
        self.assertEqual(error, "")
        self.assertFalse(new_state)

    def test_toggle_fetcher_enabled_failure(self):
        """toggle_fetcher_enabled should return error on failure."""
        self.mock_ds.toggle_fetcher_enabled.return_value = None

        success, error, new_state = self.service.toggle_fetcher_enabled("f1")

        self.assertFalse(success)
        self.assertIn("failed", error.lower())

    def test_delete_fetcher_success(self):
        """delete_fetcher should return success on successful deletion."""
        self.mock_ds.delete_fetcher.return_value = True

        success, error = self.service.delete_fetcher("f1")

        self.assertTrue(success)
        self.assertEqual(error, "")

    def test_delete_fetcher_failure(self):
        """delete_fetcher should return error on failure."""
        self.mock_ds.delete_fetcher.return_value = False

        success, error = self.service.delete_fetcher("f1")

        self.assertFalse(success)
        self.assertIn("failed", error.lower())

    def test_delete_fetcher_group_all_deleted(self):
        """delete_fetcher_group should delete all versions successfully."""
        versions = [self._make_fetcher("f1", version=1), self._make_fetcher("f2", version=2)]
        self.mock_ds.get_fetcher_versions.return_value = versions
        self.mock_ds.delete_fetcher.return_value = True

        success, error, count = self.service.delete_fetcher_group("group_abc")

        self.assertTrue(success)
        self.assertEqual(count, 2)
        self.assertEqual(self.mock_ds.delete_fetcher.call_count, 2)

    def test_delete_fetcher_group_partial_failure(self):
        """delete_fetcher_group should report partial failure."""
        versions = [self._make_fetcher("f1", version=1), self._make_fetcher("f2", version=2)]
        self.mock_ds.get_fetcher_versions.return_value = versions
        # First succeeds, second fails
        self.mock_ds.delete_fetcher.side_effect = [True, False]

        success, error, count = self.service.delete_fetcher_group("group_abc")

        self.assertFalse(success)
        self.assertEqual(count, 1)
        self.assertIn("1", error)
        self.assertIn("2", error)

    def test_get_fetcher_versions(self):
        """get_fetcher_versions should delegate to datasource."""
        expected = [self._make_fetcher("f1"), self._make_fetcher("f2")]
        self.mock_ds.get_fetcher_versions.return_value = expected

        result = self.service.get_fetcher_versions("group_abc")
        self.assertEqual(result, expected)
        self.mock_ds.get_fetcher_versions.assert_called_once_with("group_abc")

    def test_get_enabled_version(self):
        """get_enabled_version should delegate to datasource."""
        expected = self._make_fetcher("f1")
        self.mock_ds.get_enabled_version.return_value = expected

        result = self.service.get_enabled_version("group_abc")
        self.assertEqual(result, expected)
        self.mock_ds.get_enabled_version.assert_called_once_with("group_abc")

    def test_get_enabled_fetchers_for_list(self):
        """get_enabled_fetchers_for_list should delegate to datasource."""
        expected = [self._make_fetcher("f1")]
        self.mock_ds.get_enabled_fetchers_for_list.return_value = expected

        result = self.service.get_enabled_fetchers_for_list()
        self.assertEqual(result, expected)
        self.mock_ds.get_enabled_fetchers_for_list.assert_called_once()

    @patch("application.services.fetcher_service.uuid7")
    def test_create_fetcher_uses_default_currency(self, mock_uuid7):
        """create_fetcher should use user's default currency when none provided."""
        mock_uuid7.return_value = "gen-uuid"
        self.mock_ds.create_fetcher.return_value = True

        success, error, fetcher_id = self.service.create_fetcher(
            name="My Fetcher",
            from_emails=["bank@example.com"],
            subject_filter="",
            amount_pattern=r"\$(\d+)",
            merchant_pattern=r"at (.+)",
            default_currency=None,
        )

        self.assertTrue(success)
        self.mock_settings.get_default_currency.assert_called_once()
        # The fetcher should be created with the default currency
        created = self.mock_ds.create_fetcher.call_args[0][0]
        self.assertEqual(created.default_currency, "JPY")


if __name__ == "__main__":
    unittest.main()
