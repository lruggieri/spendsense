/**
 * Timezone utility functions for converting between UTC and client timezone.
 * All dates are stored in the database as UTC, and this utility helps convert them
 * for display in the user's local timezone.
 */

/**
 * Parse a UTC datetime string from the server and return a Date object in client timezone.
 * @param {string} utcDateString - UTC datetime string in format "YYYY-MM-DD HH:MM:SS"
 * @returns {Date} - Date object in client's timezone
 */
function parseUTCDate(utcDateString) {
    if (!utcDateString) return null;

    // Add 'Z' to indicate UTC if not present
    let isoString = utcDateString.replace(' ', 'T');
    if (!isoString.endsWith('Z') && !isoString.includes('+') && !isoString.includes('-', 10)) {
        isoString += 'Z';
    }

    return new Date(isoString);
}

/**
 * Format a Date object for display in client timezone.
 * @param {Date} date - Date object
 * @param {Object} options - Formatting options
 * @param {boolean} options.includeTime - Whether to include time (default: true)
 * @param {boolean} options.includeSeconds - Whether to include seconds (default: true)
 * @returns {string} - Formatted date string in client timezone
 */
function formatDateInClientTimezone(date, options = {}) {
    if (!date || !(date instanceof Date)) return '';

    const includeTime = options.includeTime !== false;
    const includeSeconds = options.includeSeconds !== false;

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');

    let formatted = `${year}-${month}-${day}`;

    if (includeTime) {
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        formatted += ` ${hours}:${minutes}`;

        if (includeSeconds) {
            const seconds = String(date.getSeconds()).padStart(2, '0');
            formatted += `:${seconds}`;
        }
    }

    return formatted;
}

/**
 * Format a UTC datetime string for display in client timezone.
 * @param {string} utcDateString - UTC datetime string from server
 * @param {Object} options - Formatting options (see formatDateInClientTimezone)
 * @returns {string} - Formatted date string in client timezone
 */
function formatUTCDateForDisplay(utcDateString, options = {}) {
    const date = parseUTCDate(utcDateString);
    return formatDateInClientTimezone(date, options);
}

/**
 * Convert a Date object to ISO string for sending to server.
 * The server expects ISO 8601 format with timezone information.
 * @param {Date} date - Date object in client timezone
 * @returns {string} - ISO 8601 datetime string
 */
function dateToServerISO(date) {
    if (!date || !(date instanceof Date)) return '';
    return date.toISOString();
}

/**
 * Get date value for date input fields (YYYY-MM-DD format only).
 * @param {string} utcDateString - UTC datetime string from server
 * @returns {string} - Date in YYYY-MM-DD format for date inputs
 */
function getDateInputValue(utcDateString) {
    const date = parseUTCDate(utcDateString);
    if (!date) return '';

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');

    return `${year}-${month}-${day}`;
}

/**
 * Get datetime-local value for datetime-local input fields.
 * @param {string} utcDateString - UTC datetime string from server
 * @returns {string} - Datetime in format YYYY-MM-DDTHH:MM for datetime-local inputs
 */
function getDateTimeLocalValue(utcDateString) {
    const date = parseUTCDate(utcDateString);
    if (!date) return '';

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');

    return `${year}-${month}-${day}T${hours}:${minutes}`;
}

/**
 * Convert date input value to start of day in UTC for server queries.
 * @param {string} dateInputValue - Date string from date input (YYYY-MM-DD)
 * @returns {string} - ISO 8601 datetime string at start of day in client timezone
 */
function dateInputToStartOfDayUTC(dateInputValue) {
    if (!dateInputValue) return '';

    // Create date at start of day in client timezone
    const date = new Date(dateInputValue + 'T00:00:00');
    return date.toISOString();
}

/**
 * Convert date input value to end of day in UTC for server queries.
 * @param {string} dateInputValue - Date string from date input (YYYY-MM-DD)
 * @returns {string} - ISO 8601 datetime string at end of day in client timezone
 */
function dateInputToEndOfDayUTC(dateInputValue) {
    if (!dateInputValue) return '';

    // Create date at end of day in client timezone
    const date = new Date(dateInputValue + 'T23:59:59');
    return date.toISOString();
}

/**
 * Get today's date in the user's local timezone as YYYY-MM-DD string.
 * @returns {string} - Today's date in YYYY-MM-DD format
 */
function getLocalDateString() {
    var now = new Date();
    var year = now.getFullYear();
    var month = String(now.getMonth() + 1).padStart(2, '0');
    var day = String(now.getDate()).padStart(2, '0');
    return year + '-' + month + '-' + day;
}

/**
 * Get the first day of the current month in the user's local timezone as YYYY-MM-DD.
 * @returns {string} - First day of month in YYYY-MM-DD format
 */
function getLocalFirstDayOfMonth() {
    var now = new Date();
    var year = now.getFullYear();
    var month = String(now.getMonth() + 1).padStart(2, '0');
    return year + '-' + month + '-01';
}

/**
 * Get the last day of the current month in the user's local timezone as YYYY-MM-DD.
 * @returns {string} - Last day of month in YYYY-MM-DD format
 */
function getLocalLastDayOfMonth() {
    var now = new Date();
    var year = now.getFullYear();
    var month = now.getMonth() + 1;
    var lastDay = new Date(year, month, 0).getDate();
    return year + '-' + String(month).padStart(2, '0') + '-' + String(lastDay).padStart(2, '0');
}

/**
 * Ensure a date string is in ISO 8601 format for timezone-aware server queries.
 * If already ISO (contains 'T'), returns as-is. Otherwise converts using local timezone.
 * @param {string} dateStr - Date string (YYYY-MM-DD or ISO 8601)
 * @param {boolean} isEndOfDay - If true, convert to end of day; otherwise start of day
 * @returns {string} - ISO 8601 datetime string, or original string if empty/null
 */
function ensureISODate(dateStr, isEndOfDay) {
    if (!dateStr || dateStr.indexOf('T') !== -1) return dateStr;
    return isEndOfDay ? dateInputToEndOfDayUTC(dateStr) : dateInputToStartOfDayUTC(dateStr);
}

/**
 * Initialize all date displays on the page to show in client timezone.
 * Looks for elements with data-utc-date attribute and updates their text content.
 */
function initializeDateDisplays() {
    const elements = document.querySelectorAll('[data-utc-date]');

    elements.forEach(el => {
        const utcDateString = el.getAttribute('data-utc-date');
        const includeTime = el.getAttribute('data-include-time') !== 'false';
        const includeSeconds = el.getAttribute('data-include-seconds') !== 'false';

        const formatted = formatUTCDateForDisplay(utcDateString, {
            includeTime,
            includeSeconds
        });

        el.textContent = formatted;
    });
}

// Auto-initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeDateDisplays);
} else {
    initializeDateDisplays();
}
