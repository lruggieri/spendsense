/**
 * gmail-fetch.js — Client-side Gmail import pipeline.
 *
 * Sections:
 *   1. GmailApiClient  — thin wrappers around Gmail REST API
 *   2. FetcherEngine   — JS port of Python extraction logic
 *   3. ImportPipeline  — orchestrates the full import flow
 *   4. ProgressUI      — wires progress callbacks to DOM
 *
 * Depends on email-token.js (window.emailTokenManager).
 */

(function () {
  'use strict';

  const GMAIL_API = 'https://gmail.googleapis.com/gmail/v1/users/me';

  // =========================================================================
  // Gmail message ID normalisation
  // Port of infrastructure/email/gmail_utils.py:normalize_gmail_message_id()
  // Gmail URLs show a reduced-charset (consonant-only) ID; the API needs hex.
  // =========================================================================

  const _CHARSET_REDUCED = 'BCDFGHJKLMNPQRSTVWXZbcdfghjklmnpqrstvwxz';
  const _CHARSET_FULL    = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

  function _transformCharset(token, charsetIn, charsetOut) {
    const sizeIn  = charsetIn.length;
    const sizeOut = charsetOut.length;
    const alphMap = {};
    for (let i = 0; i < sizeIn; i++) alphMap[charsetIn[i]] = i;

    // Input string → index array (reversed)
    const inIdx = [];
    for (let i = token.length - 1; i >= 0; i--) inIdx.push(alphMap[token[i]]);

    const outIdx = [];
    for (let i = inIdx.length - 1; i >= 0; i--) {
      let offset = 0;
      for (let j = 0; j < outIdx.length; j++) {
        const v = sizeIn * outIdx[j] + offset;
        outIdx[j] = v % sizeOut;
        offset     = Math.floor(v / sizeOut);
      }
      while (offset) { outIdx.push(offset % sizeOut); offset = Math.floor(offset / sizeOut); }

      offset = inIdx[i];
      let j = 0;
      while (offset) {
        if (j >= outIdx.length) outIdx.push(0);
        const v = outIdx[j] + offset;
        outIdx[j] = v % sizeOut;
        offset     = Math.floor(v / sizeOut);
        j++;
      }
    }

    return outIdx.reverse().map(i => charsetOut[i]).join('');
  }

  function _normalizeMessageId(id) {
    id = id.trim();
    if ([...id].every(c => _CHARSET_REDUCED.includes(c))) {
      try {
        const transformed = _transformCharset(id, _CHARSET_REDUCED, _CHARSET_FULL);
        const padding  = '='.repeat((4 - transformed.length % 4) % 4);
        const decoded  = atob(transformed + padding);
        const m = decoded.match(/(?:msg-)?[a-z]:(\d+)/);
        // Use BigInt: Gmail decimal IDs are 64-bit integers and exceed
        // Number.MAX_SAFE_INTEGER, so parseInt() would lose precision.
        if (m) return BigInt(m[1]).toString(16);
      } catch (_) { /* fall through */ }
    }
    return id;
  }

  // Chunk sizes
  const DEDUP_CHUNK   = 500;   // mail IDs per check-imported request
  const IMPORT_CHUNK  = 200;   // transactions per import request
  const FETCH_CONCURRENCY = 20; // concurrent getMessage requests

  // =========================================================================
  // 1. GmailApiClient
  // =========================================================================

  const GmailApiClient = {
    /**
     * List message IDs matching a query (handles pagination).
     * @param {string} token  - GIS access token
     * @param {string} query  - Gmail search query string
     * @returns {Promise<string[]>} array of message IDs
     */
    async listMessages(token, query) {
      const ids = [];
      let pageToken = null;

      do {
        const params = new URLSearchParams({ q: query });
        if (pageToken) params.set('pageToken', pageToken);

        const resp = await fetch(`${GMAIL_API}/messages?${params}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(`Gmail list error ${resp.status}: ${err.error?.message || resp.statusText}`);
        }
        const data = await resp.json();
        if (data.messages) {
          data.messages.forEach(m => ids.push(m.id));
        }
        pageToken = data.nextPageToken || null;
      } while (pageToken);

      return ids;
    },

    /**
     * Fetch a single message in full format.
     * Accepts both API hex IDs and URL/UI consonant-charset IDs.
     * @param {string} token     - GIS access token
     * @param {string} messageId - Gmail message ID (either format)
     * @returns {Promise<object>} Gmail message object
     */
    async getMessage(token, messageId) {
      messageId = _normalizeMessageId(messageId);
      const resp = await fetch(
        `${GMAIL_API}/messages/${encodeURIComponent(messageId)}?format=full`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(`Gmail get error ${resp.status}: ${err.error?.message || resp.statusText}`);
      }
      return resp.json();
    },

    /**
     * Fetch multiple messages concurrently in batches of FETCH_CONCURRENCY.
     * Returns an array of settled results (use .status === 'fulfilled').
     * @param {string} token      - GIS access token
     * @param {string[]} ids      - message IDs
     * @param {Function} onProgress - called with (done, total) after each batch
     * @returns {Promise<PromiseSettledResult[]>}
     */
    async getMessages(token, ids, onProgress) {
      const results = [];
      let done = 0;
      for (let i = 0; i < ids.length; i += FETCH_CONCURRENCY) {
        const chunk = ids.slice(i, i + FETCH_CONCURRENCY);
        const settled = await Promise.allSettled(
          chunk.map(id => GmailApiClient.getMessage(token, id))
        );
        results.push(...settled);
        done += chunk.length;
        if (onProgress) onProgress(done, ids.length);
      }
      return results;
    },
  };

  // =========================================================================
  // 2. FetcherEngine — JS port of Python extraction logic
  // =========================================================================

  const FetcherEngine = {
    /**
     * Extract text body from a Gmail message object.
     * Port of infrastructure/email/gmail_utils.py:get_body_from_message()
     * @param {object} msg - Gmail API message object
     * @returns {string}
     */
    getBodyFromMessage(msg) {
      if (!msg || !msg.payload) return '';

      function decodeBase64(data) {
        try {
          // Gmail uses base64url; atob needs standard base64
          const standard = data.replace(/-/g, '+').replace(/_/g, '/');
          const binary = atob(standard);
          return new TextDecoder('utf-8').decode(
            Uint8Array.from(binary, c => c.charCodeAt(0))
          );
        } catch (e) {
          return '';
        }
      }

      function stripHtml(html) {
        try {
          // Remove style/script blocks and their content before parsing,
          // matching Python's re.sub(r'<style...>.*?</style>', ..., re.DOTALL)
          html = html.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
          html = html.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
          const doc = new DOMParser().parseFromString(html, 'text/html');
          const text = doc.body.textContent || '';
          // Collapse whitespace, matching Python's re.sub(r'\s+', ' ', text).strip()
          return text.replace(/\s+/g, ' ').trim();
        } catch (e) {
          return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
        }
      }

      function findPart(payload) {
        if (payload.mimeType === 'text/plain' && payload.body && payload.body.data) {
          return decodeBase64(payload.body.data);
        }
        if (payload.parts) {
          // Prefer text/plain
          for (const part of payload.parts) {
            if (part.mimeType === 'text/plain') {
              const text = findPart(part);
              if (text) return text;
            }
          }
          // Fall back to any part
          for (const part of payload.parts) {
            const text = findPart(part);
            if (text) return text;
          }
        }
        // If only HTML available, strip tags
        if (payload.mimeType === 'text/html' && payload.body && payload.body.data) {
          return stripHtml(decodeBase64(payload.body.data));
        }
        return '';
      }

      return findPart(msg.payload);
    },

    /**
     * Apply a regex pattern to text and return all first-non-empty group captures.
     * Port of infrastructure/email/fetchers/pattern_parser.py:flatten_regex_results()
     *
     * Uses matchAll() (NOT match() with /g) to preserve capture groups.
     *
     * Python named groups (?P<name>...) are incompatible with JS (?<name>...).
     * Caller should detect (?P< patterns and warn the user before calling this.
     *
     * @param {string} text
     * @param {string} pattern - regex pattern string
     * @returns {string[]} array of matched values
     */
    applyPattern(text, pattern) {
      if (!pattern || !text) return [];
      try {
        // m = re.MULTILINE, s = re.DOTALL (. matches newline)
        const re = new RegExp(pattern, 'gms');
        const results = [];
        for (const match of text.matchAll(re)) {
          if (match.length <= 1) {
            // No capture groups — use full match
            results.push(match[0]);
          } else {
            // Multiple groups: pick first non-empty (mirrors flatten_regex_results)
            const firstNonEmpty = Array.from(match).slice(1).find(g => g != null && g !== '');
            if (firstNonEmpty != null) results.push(firstNonEmpty);
          }
        }
        return results;
      } catch (e) {
        console.warn('applyPattern regex error:', e.message, 'pattern:', pattern);
        return [];
      }
    },

    /**
     * Parse an amount string to a normalised decimal string.
     * Port of domain/services/amount_parser.py
     * @param {string} amountStr
     * @returns {string} e.g. "15.99"
     */
    parseAmount(amountStr) {
      if (!amountStr) return '';
      // Remove currency symbols and spaces
      let s = amountStr.replace(/[^\d.,]/g, '');
      if (!s) return '';

      const commaCount = (s.match(/,/g) || []).length;
      const dotCount   = (s.match(/\./g) || []).length;
      const lastComma  = s.lastIndexOf(',');
      const lastDot    = s.lastIndexOf('.');

      if (commaCount === 0 && dotCount === 0) return s;

      if (commaCount > 1 || (commaCount >= 1 && dotCount === 0)) {
        // European thousands: 1,234,567 or 1,234 → comma is thousands sep
        return s.replace(/,/g, '');
      }
      if (dotCount > 1 || (dotCount >= 1 && commaCount === 0)) {
        // US thousands: 1,234.56 or bare 15.99 → dot is decimal
        return s.replace(/,/g, '');
      }
      // One comma and one dot
      if (lastDot > lastComma) {
        // 1,234.56 → dot is decimal
        return s.replace(/,/g, '');
      } else {
        // 1.234,56 → comma is decimal
        return s.replace(/\./g, '').replace(',', '.');
      }
    },

    /**
     * Check if a fetcher config has Python-style named groups (?P<name>...).
     * JS doesn't support this syntax and will silently match nothing.
     * @param {object} fetcher
     * @returns {string[]} list of pattern names that have (?P<
     */
    detectPythonNamedGroups(fetcher) {
      const patterns = [
        { name: 'amount_pattern',   value: fetcher.amount_pattern },
        { name: 'merchant_pattern', value: fetcher.merchant_pattern },
        { name: 'currency_pattern', value: fetcher.currency_pattern },
      ];
      return patterns
        .filter(p => p.value && p.value.includes('(?P<'))
        .map(p => p.name);
    },

    /**
     * Build a Gmail search filter string for a fetcher.
     * Port of infrastructure/email/fetchers/db_fetcher_adapter.py:get_gmail_filter()
     * @param {object} fetcher   - fetcher config from /api/email/config
     * @param {string} afterDate - YYYY-MM-DD
     * @returns {string}
     */
    buildGmailFilter(fetcher, afterDate) {
      const emails = fetcher.from_emails || [];
      let fromFilter;
      if (emails.length === 1) {
        fromFilter = `from:${emails[0]}`;
      } else {
        const parts = emails.map(e => `from:${e}`);
        fromFilter = `(${parts.join(' OR ')})`;
      }
      const subjectPart = fetcher.subject_filter ? ` subject:${fetcher.subject_filter}` : '';
      return `${fromFilter}${subjectPart} after:${afterDate}`;
    },

    /**
     * Extract transactions from a single email body using fetcher patterns.
     * Port of infrastructure/email/fetchers/pattern_parser.py:parse_transactions_with_patterns()
     * @param {string} body    - email plain-text body
     * @param {object} fetcher - fetcher config
     * @returns {Array<{amount:string, merchant:string|null, currency:string|null}>}
     */
    parseTransactionsWithPatterns(body, fetcher) {
      const amounts   = FetcherEngine.applyPattern(body, fetcher.amount_pattern);
      const merchants = fetcher.merchant_pattern
        ? FetcherEngine.applyPattern(body, fetcher.merchant_pattern)
        : [];
      const currencies = fetcher.currency_pattern
        ? FetcherEngine.applyPattern(body, fetcher.currency_pattern)
        : [];

      const maxTx = Math.max(amounts.length, merchants.length || 0);
      if (maxTx === 0) return [];

      const results = [];
      for (let i = 0; i < maxTx; i++) {
        const rawAmount  = amounts[i] || null;
        if (!rawAmount) continue;
        const parsedAmt  = FetcherEngine.parseAmount(rawAmount);
        const merchant   = merchants[i] || null;
        const currency   = currencies[i] || null;
        results.push({ amount: parsedAmt, merchant, currency });
      }

      // Apply negate_amount
      if (fetcher.negate_amount) {
        results.forEach(tx => {
          if (tx.amount && !tx.amount.startsWith('-')) {
            tx.amount = '-' + tx.amount;
          }
        });
      }

      return results;
    },
  };

  // =========================================================================
  // 3. ImportPipeline
  // =========================================================================

  /**
   * Run the full import for one or more fetchers.
   *
   * @param {string[]} selectedFetcherIds  - IDs to import (null/empty = all enabled)
   * @param {string}   afterDate           - YYYY-MM-DD lower bound
   * @param {Function} progressCallback    - called with progress objects (see plan)
   * @returns {Promise<void>}
   */
  async function runImport(selectedFetcherIds, afterDate, progressCallback) {
    const cb = progressCallback || (() => {});

    // 1. Fetch config from server
    cb({ phase: 'config', message: 'Loading configuration...' });
    const configResp = await fetch('/api/email/config');
    if (!configResp.ok) throw new Error('Failed to load email config');
    const config = await configResp.json();

    // 2. Initialise GIS token manager
    window.emailTokenManager.init(config.client_id);
    cb({ phase: 'auth', message: 'Requesting Gmail access...' });
    const token = await window.emailTokenManager.getOrRequestToken();

    // 3. Filter fetchers
    let fetchers = config.fetchers || [];
    if (selectedFetcherIds && selectedFetcherIds.length > 0) {
      const selectedSet = new Set(selectedFetcherIds);
      fetchers = fetchers.filter(f => selectedSet.has(f.id));
    }

    if (fetchers.length === 0) {
      cb({ phase: 'done_all', message: 'No fetchers selected.' });
      return;
    }

    const allResults = [];

    for (const fetcher of fetchers) {
      try {
        const result = await _runFetcherImport(fetcher, afterDate, token, cb);
        allResults.push(result);
      } catch (err) {
        cb({ phase: 'error', fetcher: fetcher.name, message: err.message });
        allResults.push({ fetcher: fetcher.name, imported: 0, skipped: 0, error: err.message });
      }
    }

    cb({ phase: 'done_all', results: allResults });
  }

  async function _runFetcherImport(fetcher, afterDate, token, cb) {
    // Warn about Python named group syntax incompatibility
    const badPatterns = FetcherEngine.detectPythonNamedGroups(fetcher);
    if (badPatterns.length > 0) {
      cb({
        phase: 'warning',
        fetcher: fetcher.name,
        message: `Fetcher "${fetcher.name}" uses Python-style named groups (?P<...>) in: ${badPatterns.join(', ')}. These will not match in the browser. Please update the patterns to use JS syntax (?<name>...).`,
      });
    }

    // a. List messages
    const query = FetcherEngine.buildGmailFilter(fetcher, afterDate);
    cb({ phase: 'listing', fetcher: fetcher.name, message: `Searching Gmail for "${fetcher.name}"...` });
    const allMailIds = await GmailApiClient.listMessages(token, query);
    cb({ phase: 'listing', fetcher: fetcher.name, found: allMailIds.length,
         message: `Found ${allMailIds.length} message(s) for "${fetcher.name}"` });

    if (allMailIds.length === 0) {
      cb({ phase: 'done', fetcher: fetcher.name, imported: 0, skipped: 0,
           message: `"${fetcher.name}": no messages found` });
      return { fetcher: fetcher.name, imported: 0, skipped: 0 };
    }

    // b. Dedup — chunk into DEDUP_CHUNK batches, send sequentially
    let importedIds = [];
    for (let i = 0; i < allMailIds.length; i += DEDUP_CHUNK) {
      const chunk = allMailIds.slice(i, i + DEDUP_CHUNK);
      const resp = await fetch('/api/email/check-imported', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mail_ids: chunk }),
      });
      if (!resp.ok) throw new Error('check-imported request failed');
      const dedupData = await resp.json();
      importedIds = importedIds.concat(dedupData.imported_ids || []);
    }

    const importedSet = new Set(importedIds);
    const newMailIds  = allMailIds.filter(id => !importedSet.has(id));
    cb({
      phase: 'dedup', fetcher: fetcher.name,
      new: newMailIds.length, skipped: importedIds.length,
      message: `${newMailIds.length} new, ${importedIds.length} already imported`,
    });

    if (newMailIds.length === 0) {
      cb({ phase: 'done', fetcher: fetcher.name, imported: 0, skipped: importedIds.length,
           message: `"${fetcher.name}": all messages already imported` });
      return { fetcher: fetcher.name, imported: 0, skipped: importedIds.length };
    }

    // c. Fetch messages concurrently (batches of FETCH_CONCURRENCY)
    cb({ phase: 'fetching', fetcher: fetcher.name, done: 0, total: newMailIds.length,
         message: `Fetching ${newMailIds.length} emails...` });
    const msgResults = await GmailApiClient.getMessages(token, newMailIds, (done, total) => {
      cb({ phase: 'fetching', fetcher: fetcher.name, done, total,
           message: `Fetching emails: ${done}/${total}` });
    });

    // d. Extract transactions
    const transactions = [];
    msgResults.forEach((settled, idx) => {
      if (settled.status !== 'fulfilled') {
        cb({ phase: 'warning', fetcher: fetcher.name,
             message: `Could not fetch message ${newMailIds[idx]}: ${settled.reason}` });
        return;
      }
      const msg  = settled.value;
      const body = FetcherEngine.getBodyFromMessage(msg);
      if (!body) return;

      const parsed = FetcherEngine.parseTransactionsWithPatterns(body, fetcher);
      parsed.forEach(tx => {
        // Get timestamp from internalDate (milliseconds)
        const ts   = msg.internalDate ? parseInt(msg.internalDate, 10) : Date.now();
        const date = new Date(ts);
        transactions.push({
          fetcher_id:  fetcher.id,
          mail_id:     msg.id,
          date_iso:    date.toISOString(),
          amount_str:  tx.amount,
          description: tx.merchant || 'Unknown',
          currency:    tx.currency || null,
          source:      fetcher.name,
        });
      });
    });

    cb({ phase: 'extracted', fetcher: fetcher.name, count: transactions.length,
         message: `Extracted ${transactions.length} transaction(s)` });

    // e. Import — chunk into IMPORT_CHUNK batches, send sequentially
    let totalImported = 0;
    let totalSkipped  = 0;
    for (let i = 0; i < transactions.length; i += IMPORT_CHUNK) {
      const chunk = transactions.slice(i, i + IMPORT_CHUNK);
      const resp = await fetch('/api/email/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transactions: chunk }),
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || 'import request failed');
      }
      const importData = await resp.json();
      totalImported += importData.imported || 0;
      totalSkipped  += importData.skipped  || 0;
      if (importData.warnings && importData.warnings.length) {
        importData.warnings.forEach(w =>
          cb({ phase: 'warning', fetcher: fetcher.name, message: w })
        );
      }
      cb({
        phase: 'importing', fetcher: fetcher.name,
        done: Math.min(i + IMPORT_CHUNK, transactions.length), total: transactions.length,
        message: `Saving transactions: ${Math.min(i + IMPORT_CHUNK, transactions.length)}/${transactions.length}`,
      });
    }

    cb({ phase: 'done', fetcher: fetcher.name, imported: totalImported, skipped: totalSkipped,
         message: `"${fetcher.name}": ${totalImported} imported, ${totalSkipped} skipped` });

    return { fetcher: fetcher.name, imported: totalImported, skipped: totalSkipped };
  }

  // =========================================================================
  // 4. ProgressUI
  // =========================================================================

  /**
   * Wire progress callbacks to the DOM elements in fetch_gmail_progress.html.
   *
   * @param {object} elements - { logContainer, statusMessage, spinner,
   *                              completeMessage, errorMessage, errorText,
   *                              resultsSummary }
   * @param {string} reviewUrl - URL to navigate to on completion
   * @returns {Function} progressCallback to pass to runImport()
   */
  function buildProgressCallback(elements, reviewUrl) {
    const {
      logContainer, statusMessage, spinner,
      completeMessage, errorMessage, errorText, resultsSummary,
    } = elements;

    function escapeHtml(str) {
      return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function addLog(message, type) {
      const entry = document.createElement('div');
      entry.className = `log-entry ${type || 'progress'}`;
      const ts = new Date().toLocaleTimeString();
      entry.innerHTML = `<span class="log-time">${ts}</span>${escapeHtml(message)}`;
      logContainer.appendChild(entry);
      logContainer.scrollTop = logContainer.scrollHeight;
    }

    function setStatus(message) {
      statusMessage.textContent = message;
    }

    return function onProgress(p) {
      switch (p.phase) {
        case 'config':
        case 'auth':
          setStatus(p.message);
          addLog(p.message);
          break;

        case 'listing':
        case 'dedup':
        case 'fetching':
        case 'extracted':
        case 'importing':
          setStatus(p.message || '');
          addLog(p.message || '');
          break;

        case 'warning':
          addLog(p.message, 'warning');
          break;

        case 'error':
          spinner.style.display = 'none';
          statusMessage.style.display = 'none';
          errorText.textContent = p.message;
          errorMessage.style.display = 'block';
          addLog(`ERROR: ${p.message}`, 'error');
          break;

        case 'done':
          addLog(`✓ ${p.message}`, 'success');
          break;

        case 'done_all': {
          spinner.style.display = 'none';
          statusMessage.style.display = 'none';

          if (p.results && p.results.some(r => !r.error)) {
            completeMessage.style.display = 'block';
            if (resultsSummary && p.results.length > 0) {
              let html = '<p><strong>Summary:</strong></p><ul>';
              p.results.forEach(r => {
                html += `<li><strong>${escapeHtml(r.fetcher)}:</strong> ${r.imported} imported`;
                if (r.skipped) html += `, ${r.skipped} skipped`;
                if (r.error) html += ` (error: ${escapeHtml(r.error)})`;
                html += '</li>';
              });
              html += '</ul>';
              resultsSummary.innerHTML = html;
            } else if (resultsSummary) {
              resultsSummary.innerHTML = '<p>Fetch complete.</p>';
            }
            setTimeout(() => { window.location.href = reviewUrl; }, 5000);
          } else if (!p.results || p.results.length === 0) {
            // No fetchers ran
            completeMessage.style.display = 'block';
            if (resultsSummary) resultsSummary.innerHTML = '<p>No fetchers to run.</p>';
          } else {
            // All fetchers errored
            errorText.textContent = p.message || 'Import failed.';
            errorMessage.style.display = 'block';
          }
          break;
        }

        default:
          if (p.message) addLog(p.message);
      }
    };
  }

  // Expose on window
  window.gmailFetch = {
    GmailApiClient,
    FetcherEngine,
    runImport,
    buildProgressCallback,
  };
})();
