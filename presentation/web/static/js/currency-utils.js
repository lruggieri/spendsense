// ========================================
// SHARED CURRENCY UTILITIES
// ========================================

/**
 * Get currency minor units (0=JPY/KRW/ISK, 2=USD/EUR/etc.)
 * Uses configuration from backend (window.CURRENCY_CONFIG) - single source of truth
 */
function getCurrencyMinorUnits(currency) {
    // Use configuration injected from backend (config/__init__.py)
    if (window.CURRENCY_CONFIG && window.CURRENCY_CONFIG[currency] !== undefined) {
        return window.CURRENCY_CONFIG[currency];
    }
    // Fallback to 2 decimals if currency not found (same as backend)
    return 2;
}

/**
 * Convert minor units to major units (e.g., 599 cents → 5.99 dollars)
 */
function toMajorUnits(amountMinor, currency) {
    const minorUnits = getCurrencyMinorUnits(currency);
    return amountMinor / Math.pow(10, minorUnits);
}

/**
 * Format amount with proper decimal places for a given currency
 * @param {number} amountMajor - Amount in major units
 * @param {string} currency - ISO currency code (e.g. 'JPY', 'USD')
 * @param {boolean} includeDecimals - Whether to include decimals (default: true)
 * @returns {string} Formatted amount string
 */
function formatAmount(amountMajor, currency, includeDecimals = true) {
    const minorUnits = getCurrencyMinorUnits(currency);
    if (!includeDecimals || minorUnits === 0) {
        return Math.round(amountMajor).toLocaleString();
    }
    return amountMajor.toLocaleString(undefined, {
        minimumFractionDigits: minorUnits,
        maximumFractionDigits: minorUnits
    });
}
