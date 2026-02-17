"""
Integration tests for LLM-based pattern generation.

These tests actually call the LLM API and are expensive to run.
They are skipped by default and only run when explicitly requested.

To run these tests:
    pytest -m llm                          # Run all LLM tests
    pytest tests/test_llm_integration.py   # Run this specific file
    make test-llm                          # If added to Makefile

To run all tests including LLM:
    pytest -m ""                           # Run all tests, no marker filtering
"""

import os
import pytest

# Load environment variables from .env file (if present)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, will use system env vars only

from infrastructure.llm.gemini_provider import GeminiProvider


# Skip all tests in this file if GEMINI_API_KEY is not set
pytestmark = pytest.mark.skipif(
    not os.getenv('GEMINI_API_KEY'),
    reason="GEMINI_API_KEY not set - LLM tests require API access"
)


@pytest.mark.llm
class TestLLMPatternGeneration:
    """Test actual LLM pattern generation with real emails."""

    @pytest.fixture
    def provider(self):
        """Create GeminiProvider instance."""
        return GeminiProvider()

    def test_smbc_japanese_bank_email(self, provider):
        """Test SMBC Japanese bank transaction email (excerpt)."""
        import re
        from domain.services.amount_parser import parse_amount

        email_text = """
口座引落予定日： 2021年07月27日

◆明細１
引落金額：　123,000円
内容　　：　ABC Medical Clinic

（2021年07月21日17時23分現在（配信番号：　0123000123-1234））

◆明細２
引落金額：　456円
内容　　：　DF.ラクテンモバイル

（2021年07月21日17時23分現在（配信番号：　0123000123-1234））
"""
        patterns = provider.generate_patterns(email_text)

        # Print patterns for debugging
        print(f"\n[SMBC] Generated patterns:")
        print(f"  AMOUNT_PATTERN: {patterns['amount_pattern']}")
        print(f"  MERCHANT_PATTERN: {patterns['merchant_pattern']}")
        print(f"  CURRENCY_PATTERN: {patterns['currency_pattern']}")

        # Verify patterns were generated
        assert patterns['amount_pattern'] is not None, "Amount pattern should be generated"
        assert patterns['merchant_pattern'] is not None, "Merchant pattern should be generated"
        assert patterns['currency_pattern'] is not None, "Currency pattern should be generated"

        # Actually run the patterns and verify results
        amounts = re.findall(patterns['amount_pattern'], email_text)
        merchants = re.findall(patterns['merchant_pattern'], email_text)
        currencies = re.findall(patterns['currency_pattern'], email_text)

        # Verify correct number of matches
        assert len(amounts) == 2, f"Should extract 2 amounts, got {len(amounts)}: {amounts}"
        assert len(merchants) == 2, f"Should extract 2 merchants, got {len(merchants)}: {merchants}"
        assert len(currencies) == 2, f"Should extract 2 currencies, got {len(currencies)}: {currencies}"

        # Verify extracted amounts are correct
        parsed_amounts = [parse_amount(amt) for amt in amounts]
        assert float(parsed_amounts[0]) == 123000, f"First amount should be 123000, got {parsed_amounts[0]}"
        assert float(parsed_amounts[1]) == 456, f"Second amount should be 456, got {parsed_amounts[1]}"

        # Verify merchants are complete (not truncated)
        assert 'ABC Medical Clinic' in merchants[0], f"First merchant should contain 'ABC Medical Clinic', got: {merchants[0]}"
        assert 'ラクテンモバイル' in merchants[1], f"Second merchant should contain 'ラクテンモバイル', got: {merchants[1]}"

        # Verify currencies
        assert all(c == '円' for c in currencies), f"All currencies should be '円', got: {currencies}"

    def test_wise_international_payment_email(self, provider):
        """Test Wise international payment email."""
        import re
        from domain.services.amount_parser import parse_amount

        email_text = """
Hello User,

You spent 0.23 EUR at Google Cloud.
This used 43 JPY from your account.

Want to see all your transactions in one place?
Just log back into your account.

Thanks,
The Wise team
"""
        patterns = provider.generate_patterns(email_text)

        # Print patterns for debugging
        print(f"\n[Wise] Generated patterns:")
        print(f"  AMOUNT_PATTERN: {patterns['amount_pattern']}")
        print(f"  MERCHANT_PATTERN: {patterns['merchant_pattern']}")
        print(f"  CURRENCY_PATTERN: {patterns['currency_pattern']}")

        # Verify patterns were generated
        assert patterns['amount_pattern'] is not None, "Amount pattern should be generated"
        assert patterns['merchant_pattern'] is not None, "Merchant pattern should be generated"
        assert patterns['currency_pattern'] is not None, "Currency pattern should be generated"

        # Actually run the patterns and verify results
        amounts = re.findall(patterns['amount_pattern'], email_text)
        merchants = re.findall(patterns['merchant_pattern'], email_text)
        currencies = re.findall(patterns['currency_pattern'], email_text)

        # Should extract exactly 1 transaction (the JPY charge, not the EUR display)
        assert len(amounts) == 1, f"Should extract exactly 1 amount (43 JPY), got {len(amounts)}: {amounts}"
        assert len(merchants) == 1, f"Should extract exactly 1 merchant (Google Cloud), got {len(merchants)}: {merchants}"
        assert len(currencies) == 1, f"Should extract exactly 1 currency (JPY), got {len(currencies)}: {currencies}"

        # Verify exact values
        assert float(parse_amount(amounts[0])) == 43, f"Should extract 43, got: {parse_amount(amounts[0])}"
        assert merchants[0].strip() == 'Google Cloud', f"Should extract 'Google Cloud', got: '{merchants[0].strip()}'"
        assert currencies[0] == 'JPY', f"Should extract 'JPY', got: '{currencies[0]}'"

        # Verify pattern uses generic matching (not hardcoded)
        assert '[A-Z]{3}' in patterns['currency_pattern'] or \
               '([A-Z]{3})' == patterns['currency_pattern'], \
            f"Currency pattern should use generic [A-Z]{{3}}, got: {patterns['currency_pattern']}"

    def test_amazon_purchase_email(self, provider):
        """Test Amazon purchase confirmation email."""
        import re
        from domain.services.amount_parser import parse_amount

        email_text = """
View or edit order
https://www.amazon.co.jp/your-orders/order-details?orderID=123-1231234-1234123

* DVD Drive, External USB3.0, Portable Drive, TypeC/USB Port
  Quantity: 1
  1577 JPY

Order Total: 1577 JPY
"""
        patterns = provider.generate_patterns(email_text)

        # Print patterns for debugging
        print(f"\n[Amazon] Generated patterns:")
        print(f"  AMOUNT_PATTERN: {patterns['amount_pattern']}")
        print(f"  MERCHANT_PATTERN: {patterns['merchant_pattern']}")
        print(f"  CURRENCY_PATTERN: {patterns['currency_pattern']}")

        # Verify patterns were generated
        assert patterns['amount_pattern'] is not None, "Amount pattern should be generated"
        assert patterns['merchant_pattern'] is not None, "Merchant pattern should be generated"

        # Actually run the patterns and verify results
        amounts = re.findall(patterns['amount_pattern'], email_text)
        merchants = re.findall(patterns['merchant_pattern'], email_text)

        # Should extract exactly 1 transaction (item only, not "Order Total")
        assert len(amounts) == 1, f"Should extract exactly 1 amount (not Order Total), got {len(amounts)}: {amounts}"
        assert len(merchants) == 1, f"Should extract exactly 1 merchant/product, got {len(merchants)}: {merchants}"

        # Verify exact values
        assert float(parse_amount(amounts[0])) == 1577, f"Should extract 1577, got: {parse_amount(amounts[0])}"

        expected_product = "DVD Drive, External USB3.0, Portable Drive, TypeC/USB Port"
        assert merchants[0].strip() == expected_product, \
            f"Should extract full product '{expected_product}', got: '{merchants[0].strip()}'"

        # Verify currency if extracted
        if patterns['currency_pattern']:
            currencies = re.findall(patterns['currency_pattern'], email_text)
            assert len(currencies) == 1, f"Should extract exactly 1 currency, got {len(currencies)}: {currencies}"
            assert currencies[0] == 'JPY', f"Should extract 'JPY', got: '{currencies[0]}'"

            # Should use generic pattern
            assert '[A-Z]{3}' in patterns['currency_pattern'] or \
                   '([A-Z]{3})' == patterns['currency_pattern'], \
                f"Should use generic [A-Z]{{3}}, got: {patterns['currency_pattern']}"

    def test_no_transaction_data_email(self, provider):
        """Test email with no transaction data returns None patterns."""
        email_text = """
Hello,

Thank you for subscribing to our newsletter!

Here are this week's top articles:
- 10 Tips for Better Cooking
- How to Save Money on Groceries
- Best Kitchen Gadgets of 2025

Visit our website: https://example.com

Best regards,
The Team
"""
        patterns = provider.generate_patterns(email_text)

        # Print patterns for debugging
        print(f"\n[No Transaction] Generated patterns:")
        print(f"  AMOUNT_PATTERN: {patterns['amount_pattern']}")
        print(f"  MERCHANT_PATTERN: {patterns['merchant_pattern']}")
        print(f"  CURRENCY_PATTERN: {patterns['currency_pattern']}")

        # Should return None for all patterns (no transaction data)
        assert patterns['amount_pattern'] is None, \
            "Amount pattern should be None when no transaction data"
        assert patterns['merchant_pattern'] is None, \
            "Merchant pattern should be None when no transaction data"
        assert patterns['currency_pattern'] is None, \
            "Currency pattern should be None when no transaction data"

    def test_html_heavy_email(self, provider):
        """Test email with heavy HTML/CSS doesn't generate generic patterns."""
        email_text = """
<html>
<head>
<style>
body { margin: 0; padding: 0; }
.container { width: 600px; }
</style>
</head>
<body>
<div class="container">
<p>This is a marketing email.</p>
</div>
</body>
</html>
"""
        patterns = provider.generate_patterns(email_text)

        # Print patterns for debugging
        print(f"\n[HTML Heavy] Generated patterns:")
        print(f"  AMOUNT_PATTERN: {patterns['amount_pattern']}")
        print(f"  MERCHANT_PATTERN: {patterns['merchant_pattern']}")
        print(f"  CURRENCY_PATTERN: {patterns['currency_pattern']}")

        # Should return None patterns (no real transaction data)
        assert patterns['amount_pattern'] is None, \
            "Should not generate patterns for HTML-only email"
        assert patterns['merchant_pattern'] is None, \
            "Should not generate patterns for HTML-only email"

    def test_currency_word_pattern(self, provider):
        """Test email with currency word uses generic pattern."""
        import re
        from domain.services.amount_parser import parse_amount

        email_text = """
Amount: 1,500 Yen
Merchant: Coffee Shop Tokyo
Date: 2025-01-10
"""
        patterns = provider.generate_patterns(email_text)

        # Print patterns for debugging
        print(f"\n[Currency Word] Generated patterns:")
        print(f"  AMOUNT_PATTERN: {patterns['amount_pattern']}")
        print(f"  MERCHANT_PATTERN: {patterns['merchant_pattern']}")
        print(f"  CURRENCY_PATTERN: {patterns['currency_pattern']}")

        # Verify patterns were generated
        assert patterns['amount_pattern'] is not None
        assert patterns['merchant_pattern'] is not None

        # Actually run the patterns and verify results
        amounts = re.findall(patterns['amount_pattern'], email_text)
        merchants = re.findall(patterns['merchant_pattern'], email_text)

        # Verify exactly 1 transaction
        assert len(amounts) == 1, f"Should extract exactly 1 amount, got {len(amounts)}: {amounts}"
        assert len(merchants) == 1, f"Should extract exactly 1 merchant, got {len(merchants)}: {merchants}"

        # Verify amount is 1500
        assert float(parse_amount(amounts[0])) == 1500, f"Should extract 1500, got: {parse_amount(amounts[0])}"

        # Verify merchant is exactly "Coffee Shop Tokyo"
        assert merchants[0].strip() == 'Coffee Shop Tokyo', \
            f"Should extract 'Coffee Shop Tokyo', got: '{merchants[0].strip()}'"

        # Verify currency if extracted
        if patterns['currency_pattern']:
            currencies = re.findall(patterns['currency_pattern'], email_text)
            assert len(currencies) == 1, f"Should extract exactly 1 currency, got {len(currencies)}: {currencies}"
            assert currencies[0] == 'Yen', f"Should extract 'Yen', got: '{currencies[0]}'"

            # Should use generic pattern for currency words (not hardcode "Yen")
            assert '[A-Z]' in patterns['currency_pattern'] or \
                   '[a-z]' in patterns['currency_pattern'] or \
                   patterns['currency_pattern'] == '([A-Z][a-z]+)', \
                f"Currency pattern should be generic for words, got: {patterns['currency_pattern']}"

    def test_rakuten_bank_no_merchant_email(self, provider):
        """Test Rakuten Bank debit card email with amount but no merchant."""
        import re
        from domain.services.amount_parser import parse_amount

        email_text = """
ｍａｒｉｏ　ｒｏｓｓｉ様

Mastercardデビットカードのご利用による引落を行いました。

■今回のご利用金額
840円
（ポイント利用分：0ポイント、口座引落分：840円）

■今回のご利用で獲得予定のポイント数（仮確定）
8ポイント

■月間累計の獲得予定のポイント数（仮確定）
72ポイント
"""
        patterns = provider.generate_patterns(email_text)

        # Print patterns for debugging
        print(f"\n[Rakuten Bank] Generated patterns:")
        print(f"  AMOUNT_PATTERN: {patterns['amount_pattern']}")
        print(f"  MERCHANT_PATTERN: {patterns['merchant_pattern']}")
        print(f"  CURRENCY_PATTERN: {patterns['currency_pattern']}")

        # Verify patterns were generated correctly
        assert patterns['amount_pattern'] is not None, "Amount pattern should be generated"
        assert patterns['merchant_pattern'] is None, "Merchant pattern should be None (no actual merchant in email)"
        assert patterns['currency_pattern'] is not None, "Currency pattern should be generated"

        # Actually run the patterns and verify results
        amounts = re.findall(patterns['amount_pattern'], email_text)
        currencies = re.findall(patterns['currency_pattern'], email_text)

        # Should extract the amount
        assert len(amounts) >= 1, f"Should extract at least 1 amount, got {len(amounts)}: {amounts}"

        # Check if first amount is 840
        parsed_amount = float(parse_amount(amounts[0]))
        assert parsed_amount == 840, f"Amount should be 840, got {parsed_amount}"

        # Verify currency
        assert '円' in currencies, f"Should extract '円', got: {currencies}"


@pytest.mark.llm
class TestLLMPatternParsing:
    """Test end-to-end pattern generation and parsing."""

    @pytest.fixture
    def provider(self):
        """Create GeminiProvider instance."""
        return GeminiProvider()

    def test_smbc_email_extracts_correct_transactions(self, provider):
        """Test full SMBC email with multiple transactions and noise is parsed correctly."""
        import re
        from domain.services.amount_parser import parse_amount

        email_text = """
三井住友銀行より、以下の口座引き落としについて事前にお知らせします。

口座引落予定日： 2021年06月28日

◆明細１
引落金額：　123,000円
内容　　：　ABC Medical Clinic

（2021年06月24日17時20分現在（配信番号：　0625000417-0010））

◆明細２
引落金額：　456円
内容　　：　DF.ラクテンモバイル

（2021年06月24日17時20分現在（配信番号：　0625000417-0010））

―――■SMBCダイレクトで残高確認■―――
ATMに行かなくても残高をご確認いただけます。
https://www.smbc.co.jp/kojin/app/smbcapp.html?aff=dirct_mlODM1902003
―――――――――――――――――――――

※メールでお知らせすることが出来ない場合や、お知らせした明細と実際の手続が異なる場合があります。詳細は当行ホームページをご確認ください。
※本メールは、お客さまお届けのメールアドレスへお送りしています（本メールの再送依頼は受け付けておりません）。
"""
        patterns = provider.generate_patterns(email_text)

        # Print patterns for debugging
        print(f"\n[SMBC End-to-End] Generated patterns:")
        print(f"  AMOUNT_PATTERN: {patterns['amount_pattern']}")
        print(f"  MERCHANT_PATTERN: {patterns['merchant_pattern']}")
        print(f"  CURRENCY_PATTERN: {patterns['currency_pattern']}")

        # Parse transactions using generated patterns
        amounts = re.findall(patterns['amount_pattern'], email_text)
        merchants = re.findall(patterns['merchant_pattern'], email_text)
        currencies = re.findall(patterns['currency_pattern'], email_text) if patterns['currency_pattern'] else []

        # Verify we extracted 2 transactions
        assert len(amounts) == 2, f"Should extract 2 amounts, got {len(amounts)}: {amounts}"
        assert len(merchants) == 2, f"Should extract 2 merchants, got {len(merchants)}: {merchants}"

        # Verify amount values are correct
        parsed_amounts = [parse_amount(amt) for amt in amounts]
        assert float(parsed_amounts[0]) == 123000, f"First amount should be 123000, got {parsed_amounts[0]}"
        assert float(parsed_amounts[1]) == 456, f"Second amount should be 456, got {parsed_amounts[1]}"

        # Verify merchant names are complete (not truncated)
        assert 'ABC Medical Clinic' in merchants[0], f"First merchant incomplete: {merchants[0]}"
        assert 'ラクテンモバイル' in merchants[1], f"Second merchant incomplete: {merchants[1]}"

        # Verify full merchant name captured (should include prefix for second merchant)
        assert merchants[0].strip() == 'ABC Medical Clinic', \
            f"First merchant should be 'ABC Medical Clinic', got '{merchants[0].strip()}'"
        assert merchants[1].strip() == 'DF.ラクテンモバイル', \
            f"Second merchant should be 'DF.ラクテンモバイル', got '{merchants[1].strip()}'"
