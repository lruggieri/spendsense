"""
User settings service for managing user preferences.

Handles user settings CRUD and currency management.
"""

import logging
from datetime import datetime
from typing import Tuple, List, Optional, Dict

from application.services.base_service import BaseService
from domain.repositories.user_settings_repository import UserSettingsRepository
from domain.entities.user_settings import UserSettings
from config import get_supported_currency_codes

logger = logging.getLogger(__name__)


# Settings schema - metadata for validation and UI generation
SETTINGS_SCHEMA: Dict[str, Dict] = {
    'language': {
        'db_column': 'display_language',  # DB mapping
        'type': 'select',
        'default': 'en',
        'valid_values': {
            'en', 'es', 'fr', 'de', 'it', 'pt', 'ja', 'zh', 'ko',
            'ru', 'ar', 'hi', 'nl', 'sv', 'no', 'da', 'fi', 'pl',
            'tr', 'th', 'vi'
        },
        'label': 'Display Language',
        'help_text': 'Language for UI labels and messages (feature not yet active)'
    },
    'currency': {
        'db_column': 'default_currency',  # DB mapping
        'type': 'select',
        'default': 'USD',
        'valid_values': set(get_supported_currency_codes()),
        'label': 'Default Currency',
        'help_text': 'Default currency for new transactions and display'
    }
}


class UserSettingsService(BaseService):
    """
    Service for managing user settings and preferences.

    Provides methods for user settings CRUD, currency management,
    and currency conversion.
    """

    def __init__(self, user_id: str, user_settings_datasource: UserSettingsRepository, db_path: str = None):
        """
        Initialize UserSettingsService.

        Args:
            user_id: User ID for data isolation
            user_settings_datasource: User settings datasource implementation
            db_path: Optional database path
        """
        super().__init__(user_id, db_path)
        self._settings_datasource = user_settings_datasource

    @property
    def datasource(self) -> UserSettingsRepository:
        """Get the user settings datasource (for external components like rate limiter)."""
        return self._settings_datasource

    def _validate_setting(self, field_name: str, value: any) -> Tuple[bool, str]:
        """
        Validate a setting value using SETTINGS_SCHEMA.

        Args:
            field_name: Entity field name (e.g., 'language', not 'display_language')
            value: Value to validate

        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        if field_name not in SETTINGS_SCHEMA:
            return False, f"Unknown setting: {field_name}"

        schema = SETTINGS_SCHEMA[field_name]

        if schema['type'] == 'select':
            if value not in schema['valid_values']:
                return False, f"Invalid value for {field_name}: {value}"

        # Future: Add validation for other types (text, number, boolean, etc.)

        return True, ""

    def get_user_settings(self) -> UserSettings:
        """
        Get user settings entity.

        Returns:
            UserSettings entity with current or default values
        """
        return self._settings_datasource.get_settings()

    def update_user_settings(self, language: str = None, currency: str = None, browser_settings: dict = None) -> Tuple[bool, str]:
        """
        Update user settings.

        Args:
            language: ISO 639-1 language code (optional)
            currency: ISO 4217 currency code (optional)
            browser_settings: Browser-specific settings dict (optional)

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        # Get current settings
        current = self._settings_datasource.get_settings()

        # Determine final values
        final_language = language if language is not None else current.language
        final_currency = currency if currency is not None else current.currency

        # Validate settings before saving
        if language is not None:
            is_valid, error = self._validate_setting('language', final_language)
            if not is_valid:
                return False, error

        if currency is not None:
            is_valid, error = self._validate_setting('currency', final_currency)
            if not is_valid:
                return False, error

        # Create updated settings entity
        updated = UserSettings(
            user_id=self.user_id,
            language=final_language,
            currency=final_currency,
            browser_settings=browser_settings if browser_settings is not None else current.browser_settings,
            created_at=current.created_at,
            updated_at=current.updated_at
        )

        # Save through datasource
        return self._settings_datasource.update_settings(updated)

    def get_supported_currencies(self) -> List[dict]:
        """
        Get list of all supported currencies from config.

        Returns:
            List of dictionaries with 'code', 'symbol', and 'name' keys
        """
        from config import SUPPORTED_CURRENCIES
        return SUPPORTED_CURRENCIES

    def get_currency_symbol(self, currency_code: str) -> str:
        """
        Get currency symbol for a given code.

        Args:
            currency_code: ISO 4217 currency code (e.g., 'JPY', 'USD')

        Returns:
            Currency symbol (e.g., '¥', '$'), or the code itself if not found
        """
        from config import get_currency_symbol
        return get_currency_symbol(currency_code)

    def validate_currency(self, currency_code: str) -> bool:
        """
        Validate currency against project's supported currencies.

        Args:
            currency_code: ISO 4217 currency code to validate

        Returns:
            True if currency is supported, False otherwise
        """
        from config import get_supported_currency_codes
        return currency_code in get_supported_currency_codes()

    def get_currency_converter(self):
        """
        Get currency converter singleton instance.

        Returns:
            CurrencyConverterService instance for currency conversion
        """
        from domain.services.currency_converter import CurrencyConverterService
        return CurrencyConverterService.get_instance()

    def convert_to_user_currency(self, amount: float, from_currency: str, tx_date: datetime) -> float:
        """
        Convert transaction amount to user's default currency.

        Args:
            amount: Amount in original currency
            from_currency: Original currency code (ISO 4217)
            tx_date: Transaction date

        Returns:
            Amount converted to user's default currency
        """
        user_settings = self.get_user_settings()
        to_currency = user_settings.currency if user_settings else 'JPY'
        converter = self.get_currency_converter()
        return converter.convert(amount, from_currency, to_currency, tx_date)

    def get_default_currency(self) -> str:
        """
        Get user's default currency.

        Returns:
            ISO 4217 currency code (defaults to 'JPY')
        """
        settings = self.get_user_settings()
        return settings.currency if settings else 'JPY'
