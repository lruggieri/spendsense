/**
 * Test setup: load the IIFE scripts into the jsdom window context.
 *
 * The production JS files are IIFEs that attach to `window`.  We read them
 * as text and eval them so vitest's jsdom `window` gets the exports.
 */

import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATIC_JS = resolve(__dirname, '../../presentation/web/static/js');

// gmail-fetch.js depends on window.emailTokenManager from email-token.js,
// but only at runtime (GIS calls). For unit-testing FetcherEngine we just
// need gmail-fetch.js loaded; stub the token manager to avoid GIS dependency.
globalThis.google = { accounts: { oauth2: { initTokenClient: () => ({}) } } };

const emailTokenSrc = readFileSync(resolve(STATIC_JS, 'email-token.js'), 'utf-8');
const gmailFetchSrc = readFileSync(resolve(STATIC_JS, 'gmail-fetch.js'), 'utf-8');

// eval in global scope so window.emailTokenManager / window.gmailFetch are set
// eslint-disable-next-line no-eval
eval(emailTokenSrc);
// eslint-disable-next-line no-eval
eval(gmailFetchSrc);

export const FetcherEngine = window.gmailFetch.FetcherEngine;
