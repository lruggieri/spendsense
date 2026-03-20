"""Configuration module for loading credentials and settings."""

import os
import json
import logging
from typing import Dict, Optional
from pathlib import Path

# Note: Can't use logger = logging.getLogger(__name__) here yet because
# logging isn't configured when config is imported. Use root logger instead.
logger = logging.getLogger()


class CredentialsLoader:
    """
    Load Google OAuth credentials from environment variables or config file.

    Priority:
    1. Environment variables (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_PROJECT_ID)
    2. config/credentials.json file (for local development)

    Best practices:
    - Use environment variables in production (Docker, cloud deployments)
    - Use config file for local development (add to .gitignore)
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize credentials loader.

        Args:
            config_dir: Path to config directory. If None, uses default (./config)
        """
        if config_dir is None:
            # Default to config/ directory relative to this file
            config_dir = Path(__file__).parent

        self.config_dir = Path(config_dir)
        self.credentials_file = self.config_dir / 'credentials.json'

    def get_credentials(self) -> Dict[str, str]:
        """
        Get Google OAuth credentials.

        Returns:
            Dictionary with structure matching Google's credentials.json format
            (Web application type — top-level key must be 'web').

        Raises:
            FileNotFoundError: If neither env vars nor config file are available
            ValueError: If credentials are invalid or incomplete
        """
        # Try environment variables first (production)
        client_id = os.getenv('GOOGLE_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        project_id = os.getenv('GOOGLE_PROJECT_ID', 'spendsense')

        if client_id and client_secret:
            logger.info("Using credentials from environment variables")
            return {
                'web': {
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'project_id': project_id,
                    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
                    'redirect_uris': ['http://localhost']
                }
            }

        # Fall back to config file (local development)
        if not self.credentials_file.exists():
            raise FileNotFoundError(
                f"Credentials not found. Either:\n"
                f"1. Set environment variables: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET\n"
                f"2. Create config file: {self.credentials_file}\n"
                f"\nSee .env.example for reference."
            )

        logger.info(f"Using credentials from {self.credentials_file}")

        try:
            with open(self.credentials_file, 'r') as f:
                credentials = json.load(f)

            if 'web' not in credentials:
                raise ValueError(
                    "Invalid credentials.json: expected a top-level 'web' key. "
                    "Download a 'Web application' OAuth 2.0 client from "
                    "Google Cloud Console → APIs & Services → Credentials."
                )

            required_fields = ['client_id', 'client_secret']
            for field in required_fields:
                if field not in credentials['web']:
                    raise ValueError(f"Invalid credentials.json: missing '{field}' in 'web' section")

            return credentials

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in credentials file: {e}")

    def get_client_config(self) -> Dict[str, str]:
        """
        Get just the client credentials (client_id and client_secret).

        Returns:
            Dictionary with 'client_id' and 'client_secret' keys
        """
        credentials = self.get_credentials()
        return {
            'client_id': credentials['web']['client_id'],
            'client_secret': credentials['web']['client_secret']
        }


def get_gis_client_id() -> Optional[str]:
    """
    Get the OAuth 2.0 client_id to use for the browser-side GIS Token Client.

    GIS Token Client only works with a *Web application* OAuth client (not a
    Desktop app client).  If your main credentials.json uses a Desktop app
    client for the server-side login flow, set this environment variable to
    the client_id of a separate Web application OAuth client that has the
    app's origin added to 'Authorized JavaScript origins' in Google Cloud
    Console.

    If not set, falls back to the main client_id from credentials.json (which
    works only when that client is already a Web application type).

    Environment variable:
        GIS_CLIENT_ID: Web application OAuth 2.0 client_id for browser GIS use
    """
    return os.getenv('GIS_CLIENT_ID')


def get_database_path() -> str:
    """
    Get database path from environment variable or use default.

    Returns:
        Absolute path to SQLite database file
    """
    # Try environment variable first
    db_path = os.getenv('DATABASE_PATH')

    if db_path:
        logger.info(f"Using database from environment: {db_path}")
        return db_path

    # Default to data/transactions.db relative to project root
    project_root = Path(__file__).parent.parent
    default_path = project_root / 'data' / 'transactions.db'
    logger.info(f"Using default database path: {default_path}")
    return str(default_path)


def get_flask_secret_key() -> str:
    """
    Get Flask secret key from environment or use default (insecure for production).

    Returns:
        Secret key string
    """
    secret_key = os.getenv('FLASK_SECRET_KEY')

    if secret_key:
        return secret_key

    logger.warning("Using default Flask secret key. Set FLASK_SECRET_KEY in production!")
    return 'dev-secret-key-change-in-production'


def get_allowed_emails() -> Optional[set]:
    """
    Get allowed email addresses from environment variable.

    Returns:
        Set of allowed email addresses (lowercase), or None if unrestricted
    """
    allowed_emails_str = os.getenv('ALLOWED_EMAILS')

    if not allowed_emails_str:
        logger.info("ALLOWED_EMAILS not set - login is unrestricted")
        return None

    # Parse comma-separated list and normalize to lowercase
    emails = {email.strip().lower() for email in allowed_emails_str.split(',') if email.strip()}

    if not emails:
        logger.info("ALLOWED_EMAILS is empty - login is unrestricted")
        return None

    logger.info(f"Access restricted to {len(emails)} email(s)")
    return emails


def get_redis_host() -> str:
    """
    Get Redis host from environment variable or use default.

    Returns:
        Redis hostname (default: 'localhost')
    """
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    logger.info(f"Redis host: {redis_host}")
    return redis_host


def get_redis_port() -> int:
    """
    Get Redis port from environment variable or use default.

    Returns:
        Redis port number (default: 6379)
    """
    redis_port = int(os.getenv('REDIS_PORT', '6379'))
    logger.info(f"Redis port: {redis_port}")
    return redis_port


def get_redis_db() -> int:
    """
    Get Redis database number from environment variable or use default.

    Returns:
        Redis database number (default: 0, range: 0-15)
    """
    redis_db = int(os.getenv('REDIS_DB', '0'))
    if redis_db < 0 or redis_db > 15:
        logger.warning(f"Invalid REDIS_DB={redis_db}, using default 0")
        redis_db = 0
    logger.info(f"Redis DB: {redis_db}")
    return redis_db


def get_cache_ttl() -> int:
    """
    Get cache TTL (time-to-live) from environment variable or use default.

    Returns:
        Cache TTL in seconds (default: 1800 = 30 minutes)
        Special values: 0 or negative = cache never expires
    """
    cache_ttl = int(os.getenv('CACHE_TTL', '1800'))
    if cache_ttl <= 0:
        logger.info(f"Cache TTL: NEVER EXPIRES (set to {cache_ttl})")
    else:
        logger.info(f"Cache TTL: {cache_ttl} seconds")
    return cache_ttl


def get_log_level() -> str:
    """
    Get logging level from environment variable or use default.

    Returns:
        Log level string (default: 'INFO')
        Valid values: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'

    Environment variable:
        LOG_LEVEL: Set to one of DEBUG, INFO, WARNING, ERROR, CRITICAL

    Examples:
        LOG_LEVEL=DEBUG python app.py    # Show all logs including debug
        LOG_LEVEL=WARNING python app.py  # Show only warnings and errors
        LOG_LEVEL=INFO python app.py     # Default: show info, warnings, errors
    """
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}

    if log_level not in valid_levels:
        # Use print here because logging isn't configured yet when this runs
        print(f"Invalid LOG_LEVEL '{log_level}', using INFO. Valid levels: {', '.join(valid_levels)}")
        return 'INFO'

    return log_level


def get_currency_data_file() -> str:
    """
    Get currency exchange rate data file path from environment variable or use default.

    Returns:
        Absolute path to currency data file (default: data/currency_rates/ecb_rates.zip)

    Environment variable:
        CURRENCY_DATA_FILE: Set to custom path for ECB exchange rate data file

    Examples:
        CURRENCY_DATA_FILE=/app/data/ecb_rates.zip python app.py  # Docker
        CURRENCY_DATA_FILE=./data/currency_rates/ecb_rates.zip    # Local development
    """
    data_file = os.getenv('CURRENCY_DATA_FILE')

    if data_file:
        logger.info(f"Using currency data file from environment: {data_file}")
        return data_file

    # Default to data/currency_rates/ecb_rates.zip relative to project root
    project_root = Path(__file__).parent.parent
    default_path = project_root / 'data' / 'currency_rates' / 'ecb_rates.zip'
    logger.info(f"Using default currency data file: {default_path}")
    return str(default_path)


def get_app_version() -> str:
    """
    Get application version from environment variable.

    Set at Docker build time via APP_VERSION build arg.
    Falls back to 'dev' for local development.

    Returns:
        Version string (e.g., 'v1.2.3', 'sha-abc1234', 'dev')
    """
    return os.getenv('APP_VERSION', 'dev')


def get_gemini_api_key() -> Optional[str]:
    """
    Get Gemini API key from environment variable.

    Returns:
        API key string or None if not set

    Environment variable:
        GEMINI_API_KEY: Set to your Gemini API key for LLM-based pattern generation

    Examples:
        GEMINI_API_KEY=your_api_key_here python app.py
    """
    api_key = os.getenv('GEMINI_API_KEY')

    if api_key:
        logger.info("Gemini API key configured")
    else:
        logger.info("Gemini API key not set - fetcher testing will not work")

    return api_key


# Supported currencies with their symbols
# Updated to match ECB (European Central Bank) supported currencies (30 active as of 2026)
# Note: RUB suspended since March 2022, BGN removed Jan 2026, HRK removed 2023
# "aliases" field contains alternative representations (kanji, alternative symbols, etc.)
SUPPORTED_CURRENCIES = [
    {"code": "USD", "symbol": "$", "name": "US Dollar", "minor_units": 2, "aliases": ["＄"]},
    {"code": "EUR", "symbol": "€", "name": "Euro", "minor_units": 2, "aliases": []},
    {"code": "GBP", "symbol": "£", "name": "British Pound", "minor_units": 2, "aliases": ["￡"]},
    {"code": "JPY", "symbol": "¥", "name": "Japanese Yen", "minor_units": 0, "aliases": ["円", "￥"]},
    {"code": "CNY", "symbol": "元", "name": "Chinese Yuan Renminbi", "minor_units": 2, "aliases": []},
    {"code": "CAD", "symbol": "C$", "name": "Canadian Dollar", "minor_units": 2, "aliases": []},
    {"code": "AUD", "symbol": "A$", "name": "Australian Dollar", "minor_units": 2, "aliases": []},
    {"code": "CHF", "symbol": "Fr", "name": "Swiss Franc", "minor_units": 2, "aliases": []},
    {"code": "INR", "symbol": "₹", "name": "Indian Rupee", "minor_units": 2, "aliases": []},
    {"code": "BRL", "symbol": "R$", "name": "Brazilian Real", "minor_units": 2, "aliases": []},
    {"code": "MXN", "symbol": "Mex$", "name": "Mexican Peso", "minor_units": 2, "aliases": []},
    {"code": "KRW", "symbol": "₩", "name": "South Korean Won", "minor_units": 0, "aliases": []},
    {"code": "ZAR", "symbol": "R", "name": "South African Rand", "minor_units": 2, "aliases": []},
    {"code": "SGD", "symbol": "S$", "name": "Singapore Dollar", "minor_units": 2, "aliases": []},
    {"code": "HKD", "symbol": "HK$", "name": "Hong Kong Dollar", "minor_units": 2, "aliases": []},
    {"code": "SEK", "symbol": "kr", "name": "Swedish Krona", "minor_units": 2, "aliases": []},
    {"code": "NOK", "symbol": "kr", "name": "Norwegian Krone", "minor_units": 2, "aliases": []},
    {"code": "DKK", "symbol": "kr", "name": "Danish Krone", "minor_units": 2, "aliases": []},
    {"code": "PLN", "symbol": "zł", "name": "Polish Zloty", "minor_units": 2, "aliases": []},
    {"code": "THB", "symbol": "฿", "name": "Thai Baht", "minor_units": 2, "aliases": []},
    {"code": "IDR", "symbol": "Rp", "name": "Indonesian Rupiah", "minor_units": 2, "aliases": []},
    {"code": "MYR", "symbol": "RM", "name": "Malaysian Ringgit", "minor_units": 2, "aliases": []},
    {"code": "PHP", "symbol": "₱", "name": "Philippine Peso", "minor_units": 2, "aliases": []},
    {"code": "CZK", "symbol": "Kč", "name": "Czech Koruna", "minor_units": 2, "aliases": []},
    {"code": "HUF", "symbol": "Ft", "name": "Hungarian Forint", "minor_units": 2, "aliases": []},
    {"code": "RON", "symbol": "lei", "name": "Romanian Leu", "minor_units": 2, "aliases": []},
    {"code": "ISK", "symbol": "kr", "name": "Icelandic Króna", "minor_units": 0, "aliases": []},
    {"code": "TRY", "symbol": "₺", "name": "Turkish Lira", "minor_units": 2, "aliases": []},
    {"code": "ILS", "symbol": "₪", "name": "Israeli Shekel", "minor_units": 2, "aliases": []},
    {"code": "NZD", "symbol": "NZ$", "name": "New Zealand Dollar", "minor_units": 2, "aliases": []},
]


# Create lookup dictionaries for O(1) access (computed once at module load)
_CURRENCY_SYMBOL_MAP = {c["code"]: c["symbol"] for c in SUPPORTED_CURRENCIES}
_CURRENCY_NAME_MAP = {c["code"]: c["name"] for c in SUPPORTED_CURRENCIES}
_CURRENCY_MINOR_UNITS_MAP = {c["code"]: c["minor_units"] for c in SUPPORTED_CURRENCIES}
_CURRENCY_CODE_LIST = [c["code"] for c in SUPPORTED_CURRENCIES]

# Reverse lookups: symbol/name -> code (for normalization)
_SYMBOL_TO_CODE = {}
_NAME_TO_CODE = {}
for currency in SUPPORTED_CURRENCIES:
    code = currency["code"]
    symbol = currency["symbol"]
    name = currency["name"]
    aliases = currency.get("aliases", [])

    # Primary symbol to code (case-sensitive for symbols)
    _SYMBOL_TO_CODE[symbol] = code

    # Aliases (alternative symbols/kanji) to code
    for alias in aliases:
        _SYMBOL_TO_CODE[alias] = code

    # Name to code (case-insensitive)
    _NAME_TO_CODE[name.lower()] = code
    # Also map short name (e.g., "Yen" from "Japanese Yen")
    if " " in name:
        short_name = name.split()[-1]  # Last word (e.g., "Yen", "Dollar")
        if short_name.lower() not in _NAME_TO_CODE:  # Avoid overwriting (USD takes precedence for "Dollar")
            _NAME_TO_CODE[short_name.lower()] = code


def normalize_currency_code(currency_input: str) -> str:
    """
    Normalize currency input to ISO 4217 code.

    Handles various formats:
    - ISO codes: "JPY" → "JPY", "jpy" → "JPY"
    - Symbols: "¥" → "JPY", "$" → "USD", "€" → "EUR"
    - Aliases: "円" → "JPY", "元" → "CNY" (from SUPPORTED_CURRENCIES)
    - Names: "Yen" → "JPY", "yen" → "JPY", "Japanese Yen" → "JPY"

    Args:
        currency_input: Currency in any format (code, symbol, name, alias)

    Returns:
        ISO 4217 currency code, or original input if not recognized

    Examples:
        normalize_currency_code("JPY") -> "JPY"
        normalize_currency_code("jpy") -> "JPY"
        normalize_currency_code("¥") -> "JPY"
        normalize_currency_code("円") -> "JPY"
        normalize_currency_code("Yen") -> "JPY"
        normalize_currency_code("yen") -> "JPY"
        normalize_currency_code("Japanese Yen") -> "JPY"
        normalize_currency_code("$") -> "USD"
        normalize_currency_code("Dollar") -> "USD"
    """
    if not currency_input:
        return currency_input

    # Strip whitespace
    currency_input = currency_input.strip()

    # 1. Check if already a valid ISO code (case-insensitive)
    if currency_input.upper() in _CURRENCY_CODE_LIST:
        return currency_input.upper()

    # 2. Check symbol to code mapping (includes primary symbol + aliases)
    if currency_input in _SYMBOL_TO_CODE:
        return _SYMBOL_TO_CODE[currency_input]

    # 3. Check name to code mapping (case-insensitive)
    if currency_input.lower() in _NAME_TO_CODE:
        return _NAME_TO_CODE[currency_input.lower()]

    # 4. Not recognized - return original and log warning
    logger.warning(f"Could not normalize currency '{currency_input}' to ISO code")
    return currency_input


def get_supported_currency_codes() -> list:
    """
    Get list of supported currency codes.

    Returns:
        List of ISO 4217 currency codes (e.g., ['JPY', 'USD', 'EUR', ...])
    """
    return _CURRENCY_CODE_LIST


def get_currency_symbol(currency_code: str) -> str:
    """
    Get currency symbol for a given code (O(1) lookup).

    Args:
        currency_code: ISO 4217 currency code (e.g., 'JPY', 'USD')

    Returns:
        Currency symbol (e.g., '¥', '$'), or the code itself if not found
    """
    return _CURRENCY_SYMBOL_MAP.get(currency_code, currency_code)


def get_currency_name(currency_code: str) -> str:
    """
    Get currency name for a given code (O(1) lookup).

    Args:
        currency_code: ISO 4217 currency code (e.g., 'JPY', 'USD')

    Returns:
        Currency name (e.g., 'Japanese Yen'), or the code itself if not found
    """
    return _CURRENCY_NAME_MAP.get(currency_code, currency_code)


def get_currency_minor_units(currency_code: str) -> int:
    """
    Get number of decimal places (minor units) for a currency.

    Based on ISO 4217 standard:
    - 0 decimals: JPY, KRW, ISK (no fractional units)
    - 2 decimals: USD, EUR, GBP, etc. (most currencies)
    - 3 decimals: BHD, KWD, OMR (not in current list)

    Args:
        currency_code: ISO 4217 currency code (e.g., 'JPY', 'USD')

    Returns:
        Number of minor units (decimal places). Defaults to 2 if unknown.

    Examples:
        get_currency_minor_units('USD') -> 2  # $1.00 = 100 cents
        get_currency_minor_units('JPY') -> 0  # ¥100 = 100 yen (no sen)
        get_currency_minor_units('EUR') -> 2  # €1.00 = 100 cents
    """
    minor_units = _CURRENCY_MINOR_UNITS_MAP.get(currency_code)
    if minor_units is None:
        logger.warning(f"Unknown currency '{currency_code}', defaulting to 2 decimal places")
        return 2
    return minor_units


# Singleton instance for easy import
_credentials_loader = None


def get_credentials_loader() -> CredentialsLoader:
    """Get singleton credentials loader instance."""
    global _credentials_loader
    if _credentials_loader is None:
        _credentials_loader = CredentialsLoader()
    return _credentials_loader
