/**
 * Tests for gmail-fetch.js FetcherEngine business logic.
 *
 * Covers the JS ports of:
 *   - domain/services/amount_parser.py          → parseAmount()
 *   - infrastructure/email/fetchers/pattern_parser.py → applyPattern(), parseTransactionsWithPatterns()
 *   - infrastructure/email/gmail_utils.py       → getBodyFromMessage()
 *   - infrastructure/email/fetchers/db_fetcher_adapter.py → buildGmailFilter()
 */

import { describe, it, expect } from 'vitest';
import { FetcherEngine } from './setup.js';

// =========================================================================
// parseAmount — port of domain/services/amount_parser.py
// =========================================================================

describe('FetcherEngine.parseAmount', () => {
  describe('US format (dot as decimal)', () => {
    it('parses simple decimals', () => {
      expect(FetcherEngine.parseAmount('5.99')).toBe('5.99');
      expect(FetcherEngine.parseAmount('12.50')).toBe('12.5');
      expect(FetcherEngine.parseAmount('0.75')).toBe('0.75');
    });

    it('parses thousands with commas', () => {
      expect(FetcherEngine.parseAmount('1,234.56')).toBe('1234.56');
      expect(FetcherEngine.parseAmount('10,000.00')).toBe('10000');
      expect(FetcherEngine.parseAmount('123,456.78')).toBe('123456.78');
    });
  });

  describe('European format (comma as decimal)', () => {
    it('parses simple decimals', () => {
      expect(FetcherEngine.parseAmount('5,99')).toBe('5.99');
    });

    it('parses thousands with dots', () => {
      expect(FetcherEngine.parseAmount('1.234,56')).toBe('1234.56');
    });
  });

  describe('Japanese Yen format (no decimal, comma as thousands)', () => {
    it('parses amounts with comma thousands separator', () => {
      expect(FetcherEngine.parseAmount('1,232')).toBe('1232');
      expect(FetcherEngine.parseAmount('45,678')).toBe('45678');
      expect(FetcherEngine.parseAmount('184,000')).toBe('184000');
    });

    it('parses amounts with no separators', () => {
      expect(FetcherEngine.parseAmount('866')).toBe('866');
      expect(FetcherEngine.parseAmount('1234')).toBe('1234');
      expect(FetcherEngine.parseAmount('500')).toBe('500');
    });
  });

  describe('currency symbol stripping', () => {
    it('strips $ symbol', () => {
      expect(FetcherEngine.parseAmount('$5.99')).toBe('5.99');
    });

    it('strips € symbol', () => {
      expect(FetcherEngine.parseAmount('€5,99')).toBe('5.99');
    });

    it('strips ¥ symbol', () => {
      expect(FetcherEngine.parseAmount('¥1,234')).toBe('1234');
    });
  });

  describe('edge cases', () => {
    it('returns empty string for empty input', () => {
      expect(FetcherEngine.parseAmount('')).toBe('');
      expect(FetcherEngine.parseAmount(null)).toBe('');
      expect(FetcherEngine.parseAmount(undefined)).toBe('');
    });

    it('handles whitespace', () => {
      expect(FetcherEngine.parseAmount('  5.99  ')).toBe('5.99');
    });
  });
});

// =========================================================================
// applyPattern — port of flatten_regex_results + re.findall
// =========================================================================

describe('FetcherEngine.applyPattern', () => {
  it('returns empty array for null/empty inputs', () => {
    expect(FetcherEngine.applyPattern('', 'test')).toEqual([]);
    expect(FetcherEngine.applyPattern('text', '')).toEqual([]);
    expect(FetcherEngine.applyPattern('text', null)).toEqual([]);
  });

  it('extracts simple capture group matches', () => {
    const text = 'amount: $15.99 and $8.00';
    const pattern = '\\$(\\d+\\.\\d{2})';
    expect(FetcherEngine.applyPattern(text, pattern)).toEqual(['15.99', '8.00']);
  });

  it('extracts full match when no capture groups', () => {
    const text = 'JPY USD EUR';
    const pattern = '[A-Z]{3}';
    expect(FetcherEngine.applyPattern(text, pattern)).toEqual(['JPY', 'USD', 'EUR']);
  });

  it('handles alternation with multiple capture groups (flatten)', () => {
    // Python: re.findall(r'(\$[\d.]+)|(€[\d.]+)', text)
    //   → [('$15.99', ''), ('', '€8.00')]
    // JS matchAll must produce the same flattened result: ['$15.99', '€8.00']
    const text = 'paid $15.99 and €8.00';
    const pattern = '(\\$[\\d.]+)|(€[\\d.]+)';
    expect(FetcherEngine.applyPattern(text, pattern)).toEqual(['$15.99', '€8.00']);
  });

  it('handles multiline text with dotall flag', () => {
    const text = 'amount:\n  1,234\n  円';
    const pattern = 'amount:\\s*([\\d,]+)';
    expect(FetcherEngine.applyPattern(text, pattern)).toEqual(['1,234']);
  });

  it('returns empty array for invalid regex', () => {
    expect(FetcherEngine.applyPattern('text', '[')).toEqual([]);
  });

  it('handles real-world SMBC pattern', () => {
    const text = '◆明細１\n引落金額：　1,232円\n内容　　：　水道料\n◆明細２\n引落金額：　866円\n内容　　：　電気料';
    const amountPattern = '引落金額：\\s*([0-9,]+)円';
    expect(FetcherEngine.applyPattern(text, amountPattern)).toEqual(['1,232', '866']);

    const merchantPattern = '内容\\s*[：:]\\s*([^\\n]+)';
    expect(FetcherEngine.applyPattern(text, merchantPattern)).toEqual(['水道料', '電気料']);
  });

  it('handles Wise alternation pattern', () => {
    const text = 'You spent 19.99 EUR at Netflix. This used 16.20 EUR and 702 JPY from your account.';
    const amountPattern = '(?:This used\\s+([\\d,.]+)\\s+[A-Z]{3}|You spent\\s+([\\d,.]+)\\s+[A-Z]{3})';
    const results = FetcherEngine.applyPattern(text, amountPattern);
    // Should extract both amounts: 19.99 from "You spent" and 16.20 from "This used"
    expect(results).toContain('19.99');
    expect(results).toContain('16.20');
    expect(results.length).toBe(2);
  });
});

// =========================================================================
// parseTransactionsWithPatterns — port of pattern_parser.py
// =========================================================================

describe('FetcherEngine.parseTransactionsWithPatterns', () => {
  const baseFetcher = {
    amount_pattern: null,
    merchant_pattern: null,
    currency_pattern: null,
    negate_amount: false,
  };

  it('returns empty array when both patterns are null', () => {
    expect(FetcherEngine.parseTransactionsWithPatterns('text', baseFetcher)).toEqual([]);
  });

  it('extracts single transaction', () => {
    const body = 'You paid $15.99 at Starbucks';
    const fetcher = {
      ...baseFetcher,
      amount_pattern: '\\$([\\d.]+)',
      merchant_pattern: 'at (\\w+)',
    };
    const result = FetcherEngine.parseTransactionsWithPatterns(body, fetcher);
    expect(result).toEqual([{ amount: '15.99', merchant: 'Starbucks', currency: null }]);
  });

  it('extracts multiple transactions', () => {
    const body = '◆明細１\n引落金額：　1,232円\n内容　　：　水道料\n◆明細２\n引落金額：　866円\n内容　　：　電気料';
    const fetcher = {
      ...baseFetcher,
      amount_pattern: '引落金額：\\s*([0-9,]+)円',
      merchant_pattern: '内容\\s*[：:]\\s*([^\\n]+)',
    };
    const result = FetcherEngine.parseTransactionsWithPatterns(body, fetcher);
    expect(result).toHaveLength(2);
    expect(result[0].amount).toBe('1232');
    expect(result[0].merchant).toBe('水道料');
    expect(result[1].amount).toBe('866');
    expect(result[1].merchant).toBe('電気料');
  });

  it('handles per-transaction currency', () => {
    const body = 'Amount: 100 JPY, Amount: 50 USD';
    const fetcher = {
      ...baseFetcher,
      amount_pattern: 'Amount: (\\d+)',
      currency_pattern: 'Amount: \\d+ ([A-Z]{3})',
    };
    const result = FetcherEngine.parseTransactionsWithPatterns(body, fetcher);
    expect(result).toHaveLength(2);
    expect(result[0]).toEqual({ amount: '100', merchant: null, currency: 'JPY' });
    expect(result[1]).toEqual({ amount: '50', merchant: null, currency: 'USD' });
  });

  it('applies negate_amount', () => {
    const body = 'Received $25.00';
    const fetcher = {
      ...baseFetcher,
      amount_pattern: '\\$([\\d.]+)',
      negate_amount: true,
    };
    const result = FetcherEngine.parseTransactionsWithPatterns(body, fetcher);
    expect(result).toHaveLength(1);
    expect(result[0].amount).toBe('-25');
  });

  it('skips transactions with no amount match', () => {
    const body = 'No amounts here, merchant: Starbucks';
    const fetcher = {
      ...baseFetcher,
      amount_pattern: '\\$([\\d.]+)',
      merchant_pattern: 'merchant: (.+)',
    };
    const result = FetcherEngine.parseTransactionsWithPatterns(body, fetcher);
    // merchant count (1) > amount count (0), so maxTx = 1,
    // but the loop skips if rawAmount is null
    expect(result).toEqual([]);
  });
});

// =========================================================================
// getBodyFromMessage — port of gmail_utils.py:get_body_from_message
// =========================================================================

describe('FetcherEngine.getBodyFromMessage', () => {
  it('returns empty string for null message', () => {
    expect(FetcherEngine.getBodyFromMessage(null)).toBe('');
    expect(FetcherEngine.getBodyFromMessage({})).toBe('');
  });

  it('extracts text/plain from simple message', () => {
    const msg = {
      payload: {
        mimeType: 'text/plain',
        body: { data: btoa('Hello world') },
      },
    };
    expect(FetcherEngine.getBodyFromMessage(msg)).toBe('Hello world');
  });

  it('extracts text/plain from multipart message', () => {
    const msg = {
      payload: {
        mimeType: 'multipart/alternative',
        body: {},
        parts: [
          {
            mimeType: 'text/plain',
            body: { data: btoa('Plain text body') },
          },
          {
            mimeType: 'text/html',
            body: { data: btoa('<p>HTML body</p>') },
          },
        ],
      },
    };
    expect(FetcherEngine.getBodyFromMessage(msg)).toBe('Plain text body');
  });

  it('falls back to HTML and strips tags + collapses whitespace', () => {
    const html = '<html><head><style>body{color:red}</style></head><body><p>Hello</p>  <p>World</p></body></html>';
    const msg = {
      payload: {
        mimeType: 'text/html',
        body: { data: btoa(html) },
      },
    };
    const result = FetcherEngine.getBodyFromMessage(msg);
    // Style block should be removed, whitespace collapsed
    expect(result).not.toContain('color:red');
    expect(result).toContain('Hello');
    expect(result).toContain('World');
    expect(result).not.toMatch(/\s{2,}/);
  });

  it('strips script blocks from HTML', () => {
    const html = '<body><script>alert("xss")</script><p>Safe content</p></body>';
    const msg = {
      payload: {
        mimeType: 'text/html',
        body: { data: btoa(html) },
      },
    };
    const result = FetcherEngine.getBodyFromMessage(msg);
    expect(result).not.toContain('alert');
    expect(result).toContain('Safe content');
  });
});

// =========================================================================
// buildGmailFilter — port of db_fetcher_adapter.py:get_gmail_filter
// =========================================================================

describe('FetcherEngine.buildGmailFilter', () => {
  it('builds single-sender filter', () => {
    const fetcher = { from_emails: ['alerts@chase.com'], subject_filter: '' };
    expect(FetcherEngine.buildGmailFilter(fetcher, '2025-01-15'))
      .toBe('from:alerts@chase.com after:2025-01-15');
  });

  it('builds multi-sender filter with OR', () => {
    const fetcher = { from_emails: ['a@b.com', 'c@d.com'], subject_filter: '' };
    expect(FetcherEngine.buildGmailFilter(fetcher, '2025-01-15'))
      .toBe('(from:a@b.com OR from:c@d.com) after:2025-01-15');
  });

  it('includes subject filter', () => {
    const fetcher = { from_emails: ['alerts@chase.com'], subject_filter: 'Your transaction' };
    expect(FetcherEngine.buildGmailFilter(fetcher, '2025-01-15'))
      .toBe('from:alerts@chase.com subject:Your transaction after:2025-01-15');
  });
});

// =========================================================================
// detectPythonNamedGroups
// =========================================================================

describe('FetcherEngine.detectPythonNamedGroups', () => {
  it('returns empty for JS-compatible patterns', () => {
    const fetcher = {
      amount_pattern: '(?<amount>\\d+)',
      merchant_pattern: '(.+)',
      currency_pattern: null,
    };
    expect(FetcherEngine.detectPythonNamedGroups(fetcher)).toEqual([]);
  });

  it('detects Python-style named groups', () => {
    const fetcher = {
      amount_pattern: '(?P<amount>\\d+)',
      merchant_pattern: '(.+)',
      currency_pattern: '(?P<curr>[A-Z]{3})',
    };
    expect(FetcherEngine.detectPythonNamedGroups(fetcher)).toEqual([
      'amount_pattern',
      'currency_pattern',
    ]);
  });
});
