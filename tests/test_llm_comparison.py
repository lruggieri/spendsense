"""
Comparison tests: OpenAI gpt-4o-mini vs Gemini Flash.

Runs both providers on the same emails and compares:
  - Correctness (do extracted values match expected?)
  - Latency (wall-clock time per call)
  - Estimated cost per call

To run:
    pytest tests/test_llm_comparison.py -s   # -s to see print output

Requires both GEMINI_API_KEY and OPENAI_API_KEY to be set.
"""

import os
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from domain.services.amount_parser import parse_amount
from infrastructure.llm.base_llm_provider import BaseLLMProvider

# Skip entire file unless both keys are present
pytestmark = pytest.mark.skipif(
    not (os.getenv("GEMINI_API_KEY") and os.getenv("OPENAI_API_KEY")),
    reason="Both GEMINI_API_KEY and OPENAI_API_KEY required for comparison tests",
)


# ---------------------------------------------------------------------------
# Pricing (per 1M tokens, as of March 2026)
# ---------------------------------------------------------------------------
# gpt-4o-mini:    $0.15 input / $0.60 output
# gemini-flash:   $0.075 input / $0.30 output  (free tier up to 15 RPM)
# ---------------------------------------------------------------------------
PRICING = {
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gemini-flash-latest": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
}

# Rough token estimation: 1 token ~ 4 chars (English), ~1.5 chars (Japanese)
PROMPT_CHARS = 12_000  # approximate prompt template + email
OUTPUT_CHARS = 200  # approximate response
EST_INPUT_TOKENS = PROMPT_CHARS // 4
EST_OUTPUT_TOKENS = OUTPUT_CHARS // 4


@dataclass
class ProviderResult:
    provider: str
    test_name: str
    passed: bool
    latency_s: float
    error: Optional[str] = None
    patterns: Optional[Dict[str, Optional[str]]] = None


@dataclass
class ComparisonSummary:
    results: List[ProviderResult] = field(default_factory=list)

    def add(self, result: ProviderResult) -> None:
        self.results.append(result)

    def print_summary(self) -> None:
        print("\n" + "=" * 80)
        print("LLM PROVIDER COMPARISON SUMMARY")
        print("=" * 80)

        providers = sorted(set(r.provider for r in self.results))
        tests = sorted(set(r.test_name for r in self.results))

        # Per-test results
        print(f"\n{'Test':<40} | {'Provider':<20} | {'Pass':>4} | {'Latency':>8}")
        print("-" * 80)
        for test in tests:
            for provider in providers:
                matches = [r for r in self.results if r.test_name == test and r.provider == provider]
                if matches:
                    r = matches[0]
                    status = "OK" if r.passed else "FAIL"
                    print(f"{test:<40} | {provider:<20} | {status:>4} | {r.latency_s:>7.2f}s")
                    if r.error:
                        print(f"{'':>40}   Error: {r.error[:60]}")

        # Aggregate stats
        print("\n" + "-" * 80)
        print(f"{'TOTALS':<40} | {'Provider':<20} | {'Pass':>4} | {'Avg(s)':>8} | {'Est$/call':>9}")
        print("-" * 80)
        for provider in providers:
            pr = [r for r in self.results if r.provider == provider]
            passed = sum(1 for r in pr if r.passed)
            total = len(pr)
            avg_lat = sum(r.latency_s for r in pr) / total if total else 0

            # Estimate cost
            model = "gpt-4o-mini" if "openai" in provider.lower() else "gemini-flash-latest"
            pricing = PRICING.get(model, {"input": 0, "output": 0})
            est_cost = (EST_INPUT_TOKENS * pricing["input"]) + (
                EST_OUTPUT_TOKENS * pricing["output"]
            )

            print(
                f"{'':40} | {provider:<20} | {passed}/{total:>2} "
                f"| {avg_lat:>7.2f}s | ${est_cost:>8.5f}"
            )
        print("=" * 80)


summary = ComparisonSummary()


def _run_provider(provider: BaseLLMProvider, provider_name: str, test_name: str, email_text: str) -> ProviderResult:
    """Run a provider and record timing."""
    start = time.time()
    try:
        patterns = provider.generate_patterns(email_text)
        latency = time.time() - start
        return ProviderResult(
            provider=provider_name,
            test_name=test_name,
            passed=True,
            latency_s=latency,
            patterns=patterns,
        )
    except Exception as e:
        latency = time.time() - start
        return ProviderResult(
            provider=provider_name,
            test_name=test_name,
            passed=False,
            latency_s=latency,
            error=str(e),
        )


@pytest.fixture(scope="module")
def gemini_provider():
    from infrastructure.llm.gemini_provider import GeminiProvider

    return GeminiProvider()


@pytest.fixture(scope="module")
def openai_provider():
    from infrastructure.llm.openai_provider import OpenAIProvider

    return OpenAIProvider()


@pytest.fixture(scope="module")
def providers(gemini_provider, openai_provider):
    return [
        ("Gemini Flash", gemini_provider),
        ("OpenAI gpt-4o-mini", openai_provider),
    ]


# ---------------------------------------------------------------------------
# Test emails (shared with test_llm_integration.py)
# ---------------------------------------------------------------------------

SMBC_EMAIL = """
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

WISE_EMAIL = """
Hello User,

You spent 0.23 EUR at Google Cloud.
This used 43 JPY from your account.

Want to see all your transactions in one place?
Just log back into your account.

Thanks,
The Wise team
"""

AMAZON_EMAIL = """
View or edit order
https://www.amazon.co.jp/your-orders/order-details?orderID=123-1231234-1234123

* DVD Drive, External USB3.0, Portable Drive, TypeC/USB Port
  Quantity: 1
  1577 JPY

Order Total: 1577 JPY
"""

NO_TRANSACTION_EMAIL = """
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


# ---------------------------------------------------------------------------
# Comparison tests
# ---------------------------------------------------------------------------

@pytest.mark.llm
class TestLLMComparison:
    """Side-by-side comparison of Gemini Flash vs OpenAI gpt-4o-mini."""

    def test_smbc_japanese_bank(self, providers):
        """SMBC multi-transaction Japanese bank email."""
        for name, provider in providers:
            result = _run_provider(provider, name, "smbc_japanese", SMBC_EMAIL)
            summary.add(result)

            if result.patterns and result.passed:
                p = result.patterns
                # Validate extracted values
                try:
                    amounts = re.findall(p["amount_pattern"], SMBC_EMAIL) if p["amount_pattern"] else []
                    merchants = re.findall(p["merchant_pattern"], SMBC_EMAIL) if p["merchant_pattern"] else []

                    assert len(amounts) == 2, f"[{name}] Expected 2 amounts, got {len(amounts)}: {amounts}"
                    assert len(merchants) == 2, f"[{name}] Expected 2 merchants, got {len(merchants)}: {merchants}"

                    parsed = [parse_amount(a) for a in amounts]
                    assert float(parsed[0]) == 123000, f"[{name}] First amount: {parsed[0]}"
                    assert float(parsed[1]) == 456, f"[{name}] Second amount: {parsed[1]}"

                    assert "ABC Medical Clinic" in merchants[0], f"[{name}] Merchant 1: {merchants[0]}"
                    assert "ラクテンモバイル" in merchants[1], f"[{name}] Merchant 2: {merchants[1]}"
                except AssertionError:
                    raise
                except Exception as e:
                    result.passed = False
                    result.error = f"Pattern validation: {e}"

    def test_wise_international(self, providers):
        """Wise international payment email."""
        for name, provider in providers:
            result = _run_provider(provider, name, "wise_international", WISE_EMAIL)
            summary.add(result)

            if result.patterns and result.passed:
                p = result.patterns
                try:
                    amounts = re.findall(p["amount_pattern"], WISE_EMAIL) if p["amount_pattern"] else []
                    merchants = re.findall(p["merchant_pattern"], WISE_EMAIL) if p["merchant_pattern"] else []

                    assert len(amounts) == 1, f"[{name}] Expected 1 amount, got {len(amounts)}: {amounts}"
                    assert len(merchants) == 1, f"[{name}] Expected 1 merchant, got {len(merchants)}: {merchants}"

                    assert float(parse_amount(amounts[0])) == 43, f"[{name}] Amount: {amounts[0]}"
                    assert merchants[0].strip() == "Google Cloud", f"[{name}] Merchant: {merchants[0]}"
                except AssertionError:
                    raise
                except Exception as e:
                    result.passed = False
                    result.error = f"Pattern validation: {e}"

    def test_amazon_purchase(self, providers):
        """Amazon purchase with line-item vs order total."""
        for name, provider in providers:
            result = _run_provider(provider, name, "amazon_purchase", AMAZON_EMAIL)
            summary.add(result)

            if result.patterns and result.passed:
                p = result.patterns
                try:
                    amounts = re.findall(p["amount_pattern"], AMAZON_EMAIL) if p["amount_pattern"] else []

                    assert len(amounts) == 1, f"[{name}] Expected 1 amount, got {len(amounts)}: {amounts}"
                    assert float(parse_amount(amounts[0])) == 1577, f"[{name}] Amount: {amounts[0]}"
                except AssertionError:
                    raise
                except Exception as e:
                    result.passed = False
                    result.error = f"Pattern validation: {e}"

    def test_no_transaction(self, providers):
        """Marketing email with no transaction data."""
        for name, provider in providers:
            result = _run_provider(provider, name, "no_transaction", NO_TRANSACTION_EMAIL)
            summary.add(result)

            if result.patterns and result.passed:
                p = result.patterns
                try:
                    assert p["amount_pattern"] is None, f"[{name}] amount should be None"
                    assert p["merchant_pattern"] is None, f"[{name}] merchant should be None"
                except AssertionError:
                    raise
                except Exception as e:
                    result.passed = False
                    result.error = f"Pattern validation: {e}"


def test_print_summary():
    """Print the comparison summary (runs last due to naming)."""
    summary.print_summary()
