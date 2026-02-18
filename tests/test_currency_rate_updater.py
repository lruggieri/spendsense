"""
Unit tests for CurrencyRateUpdater.
"""

import os
import tempfile
import time
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from infrastructure.currency_rate_updater import CurrencyRateUpdater


class TestCurrencyRateUpdater:
    """Test the CurrencyRateUpdater class."""

    def setup_method(self):
        """Set up test fixtures."""
        # Use a temporary directory for test data
        self.temp_dir = tempfile.mkdtemp()
        self.test_data_file = os.path.join(self.temp_dir, "test_ecb_rates.zip")

        # Mock the environment variable to use test path
        self.original_env = os.environ.get("CURRENCY_DATA_FILE")
        os.environ["CURRENCY_DATA_FILE"] = self.test_data_file

    def teardown_method(self):
        """Clean up test fixtures."""
        # Restore original environment
        if self.original_env is not None:
            os.environ["CURRENCY_DATA_FILE"] = self.original_env
        else:
            os.environ.pop("CURRENCY_DATA_FILE", None)

        # Clean up temp directory
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_scheduler_starts_and_stops(self):
        """Test that scheduler can start and stop."""
        with patch.object(CurrencyRateUpdater, "_check_and_update"):
            updater = CurrencyRateUpdater()
            updater.start()
            assert updater.scheduler.running
            updater.stop()
            assert not updater.scheduler.running

    def test_is_file_current_no_file(self):
        """Test _is_file_current returns False when file doesn't exist."""
        updater = CurrencyRateUpdater()
        assert not updater._is_file_current()

    def test_is_file_current_today(self):
        """Test _is_file_current returns True for today's file."""
        updater = CurrencyRateUpdater()

        # Create a file with today's modification time
        with open(self.test_data_file, "w") as f:
            f.write("test")

        assert updater._is_file_current()

    def test_is_file_current_old_file(self):
        """Test _is_file_current returns False for old file."""
        updater = CurrencyRateUpdater()

        # Create a file
        with open(self.test_data_file, "w") as f:
            f.write("test")

        # Set file modification time to yesterday
        yesterday = (datetime.now() - timedelta(days=1)).timestamp()
        os.utime(self.test_data_file, (yesterday, yesterday))

        assert not updater._is_file_current()

    def test_get_data_file_returns_path(self):
        """Test get_data_file returns the data file path."""
        with patch.object(CurrencyRateUpdater, "_check_and_update"):
            updater = CurrencyRateUpdater()
            path = updater.get_data_file()
            assert path == self.test_data_file

    def test_get_data_file_downloads_if_missing(self):
        """Test get_data_file triggers download if file missing."""
        updater = CurrencyRateUpdater()

        with patch.object(updater, "_check_and_update") as mock_update:
            updater.get_data_file()
            mock_update.assert_called_once()

    def test_check_and_update_skips_if_current(self):
        """Test _check_and_update skips download if file is current."""
        updater = CurrencyRateUpdater()

        # Create a current file
        with open(self.test_data_file, "w") as f:
            f.write("test")

        with patch("urllib.request.urlopen") as mock_open:
            updater._check_and_update()
            # Should not attempt download
            mock_open.assert_not_called()

    def test_check_and_update_downloads_if_missing(self):
        """Test _check_and_update downloads if file is missing."""
        updater = CurrencyRateUpdater()

        # Mock response object
        mock_response = MagicMock()
        mock_response.read.return_value = b"test data"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            with patch("domain.services.currency_converter.CurrencyConverterService.reload_data"):
                # Ensure file doesn't exist
                if os.path.exists(self.test_data_file):
                    os.remove(self.test_data_file)

                updater._check_and_update()
                # Should attempt download
                mock_open.assert_called_once()

    def test_check_and_update_cleans_up_on_error(self):
        """Test _check_and_update cleans up temp file on download error."""
        updater = CurrencyRateUpdater()

        with patch("urllib.request.urlopen", side_effect=Exception("Download failed")):
            # Ensure file doesn't exist
            if os.path.exists(self.test_data_file):
                os.remove(self.test_data_file)

            updater._check_and_update()

            # Temp file should be cleaned up
            temp_file = f"{self.test_data_file}.tmp"
            assert not os.path.exists(temp_file)

    def test_atomic_file_operations(self):
        """Test that file updates use atomic operations."""
        updater = CurrencyRateUpdater()

        # Mock response object
        mock_response = MagicMock()
        mock_response.read.return_value = b"test data"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("domain.services.currency_converter.CurrencyConverterService.reload_data"):
                with patch("os.replace") as mock_replace:
                    # Ensure file doesn't exist
                    if os.path.exists(self.test_data_file):
                        os.remove(self.test_data_file)

                    updater._check_and_update()

                    # Should use os.replace for atomic operation
                    mock_replace.assert_called_once()
                    call_args = mock_replace.call_args[0]
                    # Temp file should follow pattern: {data_file}.tmp.{pid}
                    assert ".tmp." in call_args[0]
                    assert call_args[0].startswith(self.test_data_file)
                    assert call_args[1] == self.test_data_file
