# LLM Integration Tests

This directory contains expensive integration tests that make actual LLM API calls to verify pattern generation works correctly with real emails.

## Overview

LLM tests are marked with `@pytest.mark.llm` and are **skipped by default** to:
- Save API costs (each test makes real Gemini API calls)
- Speed up regular test runs
- Only run when explicitly needed (e.g., after changing LLM prompts)

## Running Tests

### Regular tests (without LLM)
```bash
make test              # Skips LLM tests (default)
pytest tests/          # Same as above
```

### LLM tests only
```bash
make test-llm          # Run only LLM integration tests
pytest -m llm          # Same as above
```

### All tests including LLM
```bash
make test-all          # Run ALL tests including expensive LLM tests
pytest -m ""           # Same as above (empty marker = no filtering)
```

### Run specific LLM test file
```bash
pytest tests/test_llm_integration.py -v
```

## Requirements

LLM tests require:
1. `GEMINI_API_KEY` environment variable set
2. Internet connection
3. Valid Gemini API access

### Setting up GEMINI_API_KEY

**Option 1: Using .env file (recommended for local development)**
```bash
# Copy example and edit
cp .env.example .env

# Edit .env and add your key
GEMINI_API_KEY=your-actual-api-key-here
```

The tests will automatically load from `.env` file using `python-dotenv`.

**Option 2: Using environment variable**
```bash
export GEMINI_API_KEY='your-actual-api-key-here'
pytest -m llm
```

**Option 3: Inline for one-time use**
```bash
GEMINI_API_KEY='your-key' pytest -m llm
```

If `GEMINI_API_KEY` is not set (by any method), all LLM tests are automatically skipped.

## Configuration

Configuration is in `pytest.ini`:
```ini
[pytest]
markers =
    llm: marks tests as requiring LLM API calls (expensive, run with -m llm)

# By default, skip LLM tests unless explicitly requested
addopts = -m "not llm"
```

## Writing New LLM Tests

### Example Test

```python
import pytest
from logic.llm.gemini_provider import GeminiProvider

@pytest.mark.llm
class TestLLMPatterns:
    """LLM integration tests."""

    @pytest.fixture
    def provider(self):
        return GeminiProvider()

    def test_email_pattern_generation(self, provider):
        """Test specific email generates correct patterns."""
        email_text = """
        You spent 10.00 EUR at Coffee Shop.
        """

        patterns = provider.generate_patterns(email_text)

        # Verify patterns
        assert patterns['amount_pattern'] is not None
        assert '[A-Z]{3}' in patterns['currency_pattern']  # Generic currency
```

### Test Categories

1. **Pattern Generation Tests** (`TestLLMPatternGeneration`)
   - Verify specific emails generate correct patterns
   - Check patterns use generic currency matching (not hardcoded)
   - Verify patterns include context to avoid HTML/CSS matching
   - Test edge cases (no transaction data, HTML-heavy emails)

2. **End-to-End Parsing Tests** (`TestLLMPatternParsing`)
   - Generate patterns AND parse transactions
   - Verify correct amounts, merchants, currencies extracted
   - Ensure full merchant names captured (not truncated)

## Use Cases

### When to run LLM tests

✅ **Do run LLM tests when:**
- Changing the LLM prompt in `logic/llm/gemini_provider.py`
- Adding new example emails to the prompt
- Modifying pattern generation guidelines
- Before releasing changes to production
- Investigating why specific emails fail to parse

❌ **Don't run LLM tests when:**
- Running quick local tests during development
- Running CI/CD on every commit (too expensive)
- Testing non-LLM code changes
- You don't have GEMINI_API_KEY set

### Cost Management

Each LLM test makes 1 API call to Gemini. Current test suite:
- 7 LLM integration tests
- ~$0.01 per test run (approximate, depends on pricing)
- Total: ~$0.07 per full LLM test run

**Tip:** When working on LLM prompt changes, run specific tests instead of the full suite:
```bash
pytest tests/test_llm_integration.py::TestLLMPatternGeneration::test_smbc_japanese_bank_email -v
```

## Adding Test Cases for New Email Formats

When you discover an email that doesn't parse correctly:

1. Add a test case to `test_llm_integration.py`:
```python
def test_new_email_format(self, provider):
    """Test [describe email type]."""
    email_text = """
    [paste actual email text]
    """

    patterns = provider.generate_patterns(email_text)

    # Add assertions based on what should happen
    assert patterns['amount_pattern'] is not None
    # ... more assertions
```

2. Run the test to verify current behavior:
```bash
pytest -m llm -k test_new_email_format -v
```

3. If it fails, update the LLM prompt in `logic/llm/gemini_provider.py`

4. Re-run the test to verify the fix

5. Run all LLM tests to ensure no regressions:
```bash
make test-llm
```

## Continuous Integration

For CI/CD pipelines, consider:

1. **Fast CI**: Run only regular tests on every commit
   ```bash
   make test  # Skips LLM tests
   ```

2. **Nightly CI**: Run all tests including LLM once per day
   ```bash
   make test-all  # Includes LLM tests
   ```

3. **Pre-release**: Always run LLM tests before deploying
   ```bash
   make test-llm
   ```

## Troubleshooting

### Tests are skipped

If you see "7 deselected" when running `pytest`, it means LLM tests were skipped (expected behavior).

To run them:
```bash
pytest -m llm
```

### "GEMINI_API_KEY not set" error

**Solution 1: Use .env file (easiest)**
```bash
cp .env.example .env
# Edit .env and add your key
```

**Solution 2: Export environment variable**
```bash
export GEMINI_API_KEY='your-api-key'
pytest -m llm
```

**Solution 3: Inline**
```bash
GEMINI_API_KEY='your-key' pytest -m llm
```

### Tests fail after prompt changes

This is expected! The tests catch regressions. Options:

1. **Fix the prompt** - Adjust the prompt to make tests pass
2. **Update test expectations** - If the new behavior is correct, update test assertions
3. **Add more context** - The prompt may need more specific guidance for that email type

## Best Practices

1. **Keep tests focused** - Each test should verify one aspect
2. **Use descriptive names** - Test names should explain what email type is tested
3. **Add comments** - Explain what specific behavior is being verified
4. **Test edge cases** - Include tests for no-transaction emails, HTML-heavy emails, etc.
5. **Verify generic patterns** - Always check patterns don't hardcode currencies or other values
6. **Test full parsing** - Include end-to-end tests that verify extracted values, not just patterns

## Example Test Session

```bash
# Regular development - quick feedback
$ make test
✓ 223 tests passed in 2.1s (7 LLM tests skipped)

# After changing LLM prompt - verify it works
$ make test-llm
⚠️  Running LLM tests - this will make API calls and may incur costs
✓ 7 LLM tests passed in 15.3s

# Before committing - run everything
$ make test-all
⚠️  Running all tests including LLM tests - this may incur costs
✓ 230 tests passed in 17.5s
```
