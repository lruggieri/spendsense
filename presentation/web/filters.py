"""
Jinja2 template filters for the Flask application.

Contains custom template filters for formatting amounts and currencies.
"""

from domain.services.amount_utils import format_amount, format_major_amount, to_major_units_float


def register_filters(app):
    """
    Register all custom Jinja2 template filters with the Flask app.

    Args:
        app: Flask application instance
    """

    @app.template_filter("format_amount")
    def format_amount_filter(amount_minor, currency="JPY", decimals=True, thousands_sep=False):
        """
        Jinja2 filter: Convert minor units to formatted display string.

        Args:
            amount_minor: Amount in minor units (e.g., 599 cents)
            currency: ISO 4217 currency code (default: 'JPY')
            decimals: Whether to include decimal places (default: True)
            thousands_sep: Whether to include thousands separators (default: False)

        Returns:
            Formatted amount string (e.g., "5.99" for 599 USD cents, "1234567" for JPY)

        Usage in templates:
            {{ tx.amount|format_amount(tx.currency) }}
            {{ tx.amount|format_amount(tx.currency, False) }}  # No decimals
            {{ tx.amount|format_amount(tx.currency, True, True) }}  # With thousands separators
        """
        return format_amount(amount_minor, currency, decimals, thousands_sep)

    @app.template_filter("amount_major")
    def amount_major_filter(amount_minor, currency="JPY"):
        """
        Jinja2 filter: Convert minor units to major units as float.

        Args:
            amount_minor: Amount in minor units (e.g., 599 cents)
            currency: ISO 4217 currency code (default: 'JPY')

        Returns:
            Amount in major units as float (e.g., 5.99)

        Usage in templates:
            {{ tx.amount|amount_major(tx.currency) }}
            {{ "{:,.2f}".format(tx.amount|amount_major(tx.currency)) }}
        """
        return to_major_units_float(amount_minor, currency)

    @app.template_filter("format_major_amount")
    def format_major_amount_filter(amount_major, currency="JPY", thousands_sep=True):
        """
        Jinja2 filter: Format an amount that's already in major units.

        Useful for amounts from currency conversions or calculations that are
        already in major units (floats) rather than minor units (ints).

        Args:
            amount_major: Amount in major units as float or Decimal (e.g., 5.99)
            currency: ISO 4217 currency code (default: 'JPY')
            thousands_sep: Whether to include thousands separators (default: True)

        Returns:
            Formatted amount string respecting currency's decimal places

        Usage in templates:
            {{ total_amount|format_major_amount(default_currency) }}
            {{ converted_amount|format_major_amount('USD', True) }}
        """
        return format_major_amount(amount_major, currency, thousands_sep)
