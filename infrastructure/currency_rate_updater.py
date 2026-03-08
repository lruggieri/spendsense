"""
Background scheduler to keep ECB exchange rates updated.
"""

import fcntl
import logging
import os
import os.path as op
import ssl
import urllib.request
from datetime import date, datetime

import certifi
from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]
from currency_converter import ECB_URL

from config import get_currency_data_file
from domain.services.currency_converter import CurrencyConverterService


class CurrencyRateUpdater:
    """Background scheduler to keep ECB exchange rates updated."""

    def __init__(self):
        self.data_file = get_currency_data_file()
        self.lock_file = f"{self.data_file}.lock"
        self.scheduler = BackgroundScheduler(timezone="Europe/Brussels")  # CET/CEST
        os.makedirs(op.dirname(self.data_file), exist_ok=True)

    def start(self):
        """Start the background scheduler."""
        # Check/download on startup
        self._check_and_update()

        # Schedule daily checks at 16:10 CET (10 min after ECB publishes)
        # Then retry every 10 minutes until 16:50
        self.scheduler.add_job(
            self._check_and_update,
            "cron",
            hour=16,
            minute="10,20,30,40,50",  # 16:10, 16:20, 16:30, 16:40, 16:50
            timezone="Europe/Brussels",
        )

        self.scheduler.start()
        logging.info("CurrencyRateUpdater scheduler started")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()

    def _check_and_update(self):
        """Check if update needed and download if necessary.

        Uses file locking to prevent race conditions when multiple
        gunicorn workers try to update simultaneously.
        """
        # Use a lock file to ensure only one worker updates at a time
        lock_fd = None
        try:
            # Open/create lock file
            lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR)

            # Try to acquire exclusive lock (will block if another worker holds it)
            logging.debug("Attempting to acquire update lock...")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            logging.debug("Lock acquired")

            # Check if file is current (another worker might have just updated it)
            if self._is_file_current():
                logging.debug("Exchange rate data is current")
                # Still reload in case another worker updated it
                if op.exists(self.data_file):
                    CurrencyConverterService.reload_data(self.data_file)
                return

            # Download fresh data
            temp_file = f"{self.data_file}.tmp.{os.getpid()}"
            try:
                logging.info("Downloading ECB exchange rates...")

                # Create SSL context with certifi certificates for macOS compatibility
                ssl_context = ssl.create_default_context(cafile=certifi.where())

                # Download to temporary file first with SSL context
                with urllib.request.urlopen(ECB_URL, context=ssl_context) as response:  # nosec B310 - ECB_URL is a hardcoded trusted constant
                    with open(temp_file, "wb") as out_file:
                        out_file.write(response.read())

                # Atomic rename (prevents partial reads)
                os.replace(temp_file, self.data_file)

                # Reload converter with new data
                CurrencyConverterService.reload_data(self.data_file)

                logging.info(f"Successfully updated exchange rates: {self.data_file}")
            except Exception as e:
                logging.error(f"Failed to update exchange rates: {e}", exc_info=True)
                # Clean up temp file if it exists
                if op.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
        finally:
            # Release lock and close file descriptor
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    os.close(lock_fd)
                    logging.debug("Lock released")
                except:
                    pass

    def _is_file_current(self) -> bool:
        """Check if local file exists and was modified today."""
        if not op.exists(self.data_file):
            return False

        # Get file modification time
        mtime = datetime.fromtimestamp(op.getmtime(self.data_file))
        file_date = mtime.date()
        today = date.today()

        return file_date == today

    def get_data_file(self) -> str:
        """Get path to current data file, downloading if needed."""
        if not op.exists(self.data_file):
            self._check_and_update()
        return self.data_file
