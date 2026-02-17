# LLM Test Improvements

## Summary

Updated LLM integration tests to **verify actual extracted results**, not just pattern structure. Tests now run the generated regex patterns on the email text and assert the extracted values are correct.

## Changes Made

### Before (Pattern Structure Only)
```python
def test_smbc_email(self, provider):
    patterns = provider.generate_patterns(email_text)

    # Only checked pattern structure
    assert patterns['amount_pattern'] is not None
    assert '円' in patterns['currency_pattern']
    assert '.+' in patterns['merchant_pattern']  # Just checks greedy
```

**Problem:** Pattern might be technically correct but not work on the actual email.

### After (Actual Results Verification)
```python
def test_smbc_email(self, provider):
    patterns = provider.generate_patterns(email_text)

    # Actually RUN the patterns
    amounts = re.findall(patterns['amount_pattern'], email_text)
    merchants = re.findall(patterns['merchant_pattern'], email_text)
    currencies = re.findall(patterns['currency_pattern'], email_text)

    # Verify correct values extracted
    assert len(amounts) == 2
    assert parse_amount(amounts[0]) == 113
    assert parse_amount(amounts[1]) == 184000
    assert 'ラクテンモバイル' in merchants[0]
    assert 'チンリヨウナド' in merchants[1]
    assert all(c == '円' for c in currencies)
```

**Benefit:** Tests catch when patterns don't actually work on the email!

## Tests Updated

### 1. `test_smbc_japanese_bank_email` ✅
- Runs patterns on SMBC email with 2 transactions
- Verifies: 2 amounts (113, 184000), 2 merchants (full names), 2 currencies (円)
- Catches: Truncated merchants, wrong amounts, missing transactions

### 2. `test_wise_international_payment_email` ✅
- Runs patterns on Wise international payment email
- Verifies: Amount (43 JPY), merchant (Google Cloud), currency (JPY/EUR)
- Also checks: Generic currency pattern `[A-Z]{3}` used
- Catches: Hardcoded currencies, missing merchant context

### 3. `test_amazon_purchase_email` ✅
- Runs patterns on Amazon order confirmation
- Verifies: Amount (1577), product description (DVD Drive), currency (JPY)
- Also checks: Generic pattern used if currency extracted
- Catches: Wrong amounts, missing product info

### 4. `test_currency_word_pattern` ✅
- Runs patterns on email with "Yen" currency word
- Verifies: Amount (1500), merchant (Coffee Shop Tokyo), currency (Yen)
- Also checks: Generic word pattern `[A-Z][a-z]+` used
- Catches: Hardcoded "Yen" pattern

### 5. `test_no_transaction_data_email` ✅
- No changes needed (already tests for None patterns)

### 6. `test_html_heavy_email` ✅
- No changes needed (already tests for None patterns)

### 7. `test_smbc_email_extracts_correct_transactions` ✅
- Already had end-to-end verification (unchanged)

## What This Catches

### ✅ Catches Real Issues:
1. **Pattern doesn't match** - Regex is wrong, nothing extracted
2. **Wrong values extracted** - Pattern matches wrong text
3. **Incomplete extraction** - Pattern only captures part of merchant name
4. **Too many/few matches** - Pattern over/under-matches
5. **HTML/CSS noise** - Pattern matches formatting instead of data

### ❌ Misses (Intentionally):
- Pattern aesthetic preferences (still checked where critical)
- Performance issues (these are LLM tests, not performance tests)
- Edge cases not in test emails (add more tests for those)

## Example Test Run

When a test fails, you get actionable errors:

```bash
$ pytest -m llm -k test_smbc -v

FAILED: Should extract 2 amounts, got 1: ['113']
# → Pattern only matched first transaction

FAILED: Should extract 2 merchants, got 2: ['D', 'N']
# → Pattern is non-greedy, truncating merchant names

FAILED: First amount should be 113, got 1130
# → Pattern captured trailing zero or wrong amount

FAILED: First merchant should contain 'ラクテンモバイル', got: ['DF']
# → Pattern not capturing full merchant name
```

These errors tell you **exactly what went wrong** with the extraction.

## Running Tests

```bash
# Run all LLM tests (makes API calls)
make test-llm

# Run specific test
pytest -m llm -k test_smbc -v

# Run without API (regular tests only)
make test  # Skips LLM tests
```

## Benefits

1. **Catches real bugs** - Patterns that don't work on actual emails
2. **Clear failures** - Exact values shown in error messages
3. **Regression protection** - Ensures prompt changes don't break existing emails
4. **Documentation** - Tests show what values should be extracted
5. **Confidence** - Know the patterns actually work, not just "look right"

## Adding New Tests

When adding a new email test, follow this pattern:

```python
@pytest.mark.llm
def test_my_new_email(self, provider):
    """Test [describe email type]."""
    import re
    from logic.amount_parser import parse_amount

    email_text = """[paste actual email]"""

    patterns = provider.generate_patterns(email_text)

    # Verify patterns generated
    assert patterns['amount_pattern'] is not None
    assert patterns['merchant_pattern'] is not None

    # RUN the patterns
    amounts = re.findall(patterns['amount_pattern'], email_text)
    merchants = re.findall(patterns['merchant_pattern'], email_text)
    currencies = re.findall(patterns['currency_pattern'], email_text) if patterns['currency_pattern'] else []

    # Verify ACTUAL values
    assert len(amounts) == EXPECTED_COUNT, f"Got: {amounts}"
    assert parse_amount(amounts[0]) == EXPECTED_VALUE, f"Got: {parse_amount(amounts[0])}"
    assert EXPECTED_TEXT in merchants[0], f"Got: {merchants[0]}"
    assert EXPECTED_CURRENCY in currencies, f"Got: {currencies}"
```

## Cost Impact

No change in cost - same 7 tests, same 7 API calls (~$0.07 per run).

The additional `re.findall()` calls are local and free.

## Test Status

All tests collect and run successfully:
- ✅ 7 LLM tests with result verification
- ✅ 223 regular tests still pass
- ✅ Total: 230 tests
