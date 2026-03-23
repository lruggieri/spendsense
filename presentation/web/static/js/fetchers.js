/* Fetchers Testing Page JavaScript */

// Track email examples
let exampleCounter = 0;

// Track test email examples
let testExampleCounter = 0;

// Track from email inputs
let fromEmailCounter = 0;

// Store current patterns for testing
let currentPatterns = {
    amount_pattern: null,
    merchant_pattern: null,
    currency_pattern: null,
    negate_amount: false
};

// Expert mode state
let expertModeEnabled = false;
let originalPatterns = {
    amount_pattern: null,
    merchant_pattern: null,
    currency_pattern: null,
    negate_amount: false
};

// Wizard mode callback - set by onboarding-wizard.js
let fetcherSaveCallback = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Skip initialization for list mode
    if (window.FETCHER_MODE === 'list') {
        return; // No initialization needed for list mode
    }

    // For wizard mode, initialization is handled by initFetchers()
    if (window.FETCHER_MODE === 'wizard') {
        return;
    }

    // Pre-init GIS token manager so it's ready before the user clicks
    // "Generate patterns" or "Test patterns". Non-blocking — ignore errors.
    // Note: initFetchers() also calls this for wizard mode; init() is idempotent.
    fetch('/api/email/config')
        .then(r => r.json())
        .then(config => window.emailTokenManager.init(config.client_id))
        .catch(err => console.warn('Failed to load email config:', err));


    // Set up form submit handler
    const form = document.getElementById('fetcher-form');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            submitForm();
        });
    }

    // Initialize with one from email input
    addFromEmail();

    // Populate currency dropdown
    populateCurrencyDropdown();

    // Add initial email example
    addEmailExample();

    // Initialize expert mode from database, then load fetcher data
    // This ensures expert mode state is loaded before we check it
    (async () => {
        await initializeExpertMode();

        // If in edit mode, load fetcher data after expert mode is initialized
        if (window.FETCHER_MODE === 'edit' && window.FETCHER_DATA) {
            loadFetcherData(window.FETCHER_DATA);
        }

        // In create mode with expert mode on, show patterns for manual entry
        if (window.FETCHER_MODE === 'create' && expertModeEnabled) {
            showManualPatternEntry();
        }
    })();
});

/**
 * Initialize fetchers for a specific context
 * @param {string} context - 'standalone' (default) or 'wizard'
 */
function initFetchers(context = 'standalone') {
    window.FETCHER_MODE = context;

    // Pre-init GIS token manager so it's ready before the user submits the form.
    fetch('/api/email/config')
        .then(r => r.json())
        .then(config => window.emailTokenManager.init(config.client_id))
        .catch(err => console.warn('Failed to load email config:', err));

    // Set up form submit handler
    const form = document.getElementById('fetcher-form');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            submitForm();
        });
    }

    // Initialize with one from email input
    addFromEmail();

    // Populate currency dropdown
    populateCurrencyDropdown();

    // Add initial email example
    addEmailExample();

    // Initialize expert mode from database
    (async () => {
        await initializeExpertMode();

        // In wizard/create mode with expert mode on, show patterns for manual entry
        if (expertModeEnabled) {
            showManualPatternEntry();
        }
    })();
}

/**
 * Set callback for wizard mode
 * @param {Function} callback - Function to call after save
 */
function setFetcherSaveCallback(callback) {
    fetcherSaveCallback = callback;
}

/**
 * Reset the fetcher form (used in wizard mode)
 */
function resetFetcherForm() {
    // Reset basic fields
    document.getElementById('fetcher-name').value = '';
    document.getElementById('subject-filter').value = '';
    document.getElementById('default-currency').value = 'USD';
    document.getElementById('negate-amount').checked = false;

    // Clear from emails
    const fromEmailsContainer = document.getElementById('from-emails-container');
    fromEmailsContainer.innerHTML = '';
    fromEmailCounter = 0;
    addFromEmail();

    // Clear email examples
    const examplesContainer = document.getElementById('email-examples-container');
    examplesContainer.innerHTML = '';
    exampleCounter = 0;
    addEmailExample();

    // Hide results section
    const resultsSection = document.getElementById('results-section');
    if (resultsSection) {
        resultsSection.classList.add('hidden');
    }

    // Hide pattern test section
    const patternTestSection = document.getElementById('pattern-test-section');
    if (patternTestSection) {
        patternTestSection.classList.add('hidden');
    }

    // Hide save button section
    const saveSection = document.getElementById('save-fetcher-section');
    if (saveSection) {
        saveSection.classList.add('hidden');
    }

    // Clear test results
    const testResultsContainer = document.getElementById('test-results-container');
    if (testResultsContainer) {
        testResultsContainer.classList.add('hidden');
    }

    const testExamplesContainer = document.getElementById('test-email-examples-container');
    if (testExamplesContainer) {
        testExamplesContainer.innerHTML = '';
    }
    testExampleCounter = 0;

    // Reset patterns
    currentPatterns = {
        amount_pattern: null,
        merchant_pattern: null,
        currency_pattern: null,
        negate_amount: false
    };
}

/**
 * Add a new email example input
 */
function addEmailExample() {
    const container = document.getElementById('email-examples-container');
    const id = exampleCounter++;

    const exampleDiv = document.createElement('div');
    exampleDiv.className = 'email-example-card';
    exampleDiv.id = `email-example-${id}`;

    exampleDiv.innerHTML = `
        <div class="example-header">
            <span class="example-title">Email Example ${id + 1}</span>
            <button type="button" class="btn-icon remove-btn" onclick="removeEmailExample(${id})" title="Remove">
                ✕
            </button>
        </div>

        <div class="form-group">
            <label class="form-label">Input Mode</label>
            <div class="input-mode-toggle">
                <label class="radio-label">
                    <input type="radio" name="input_mode_${id}" value="text" checked onchange="toggleInputMode(${id}, 'text')">
                    <span>Raw Email Text</span>
                </label>
                <label class="radio-label">
                    <input type="radio" name="input_mode_${id}" value="email_id" onchange="toggleInputMode(${id}, 'email_id')">
                    <span>Gmail Message ID</span>
                </label>
            </div>
        </div>

        <div class="form-group" id="email-text-group-${id}">
            <label class="form-label" for="email-text-${id}">Email Text</label>
            <textarea
                id="email-text-${id}"
                name="email_text_${id}"
                class="form-input email-textarea"
                placeholder="Paste your transaction email text here...&#10;&#10;Example:&#10;◆明細１&#10;引落金額：　1,232円&#10;内容　　：　水道料"
                rows="8"
            ></textarea>
        </div>

        <div class="form-group hidden" id="email-id-group-${id}">
            <label class="form-label" for="email-id-${id}">Gmail Message ID</label>
            <input
                type="text"
                id="email-id-${id}"
                name="email_id_${id}"
                class="form-input"
                placeholder="e.g., CANLLRpb...@mail.gmail.com"
            >
            <small class="form-help">
                Open the email in Gmail &rarr; three-dot menu &rarr;
                "Show original" &rarr; copy the <strong>Message ID</strong> value.
            </small>
        </div>
    `;

    container.appendChild(exampleDiv);
}

/**
 * Remove an email example
 */
function removeEmailExample(id) {
    const exampleDiv = document.getElementById(`email-example-${id}`);
    if (exampleDiv) {
        exampleDiv.remove();
    }

    // Ensure at least one example remains
    const container = document.getElementById('email-examples-container');
    if (container.children.length === 0) {
        addEmailExample();
    }
}

/**
 * Toggle between email text and email ID input modes for a specific example
 */
function toggleInputMode(id, mode) {
    const emailTextGroup = document.getElementById(`email-text-group-${id}`);
    const emailIdGroup = document.getElementById(`email-id-group-${id}`);
    const emailTextInput = document.getElementById(`email-text-${id}`);
    const emailIdInput = document.getElementById(`email-id-${id}`);

    if (mode === 'text') {
        emailTextGroup.classList.remove('hidden');
        emailIdGroup.classList.add('hidden');
        if (emailIdInput) emailIdInput.value = '';  // Clear the hidden field
    } else {
        emailTextGroup.classList.add('hidden');
        emailIdGroup.classList.remove('hidden');
        if (emailTextInput) emailTextInput.value = '';  // Clear the hidden field
    }
}

/**
 * Collect all email examples from the form
 */
function collectEmailExamples() {
    const container = document.getElementById('email-examples-container');
    const examples = [];

    for (const exampleDiv of container.children) {
        // Extract ID from element ID (e.g., "email-example-0" -> 0)
        const id = parseInt(exampleDiv.id.split('-')[2]);

        const mode = document.querySelector(`input[name="input_mode_${id}"]:checked`).value;
        const emailText = document.getElementById(`email-text-${id}`).value.trim();
        const emailId = document.getElementById(`email-id-${id}`).value.trim();

        if (mode === 'text' && emailText) {
            examples.push({ type: 'text', value: emailText });
        } else if (mode === 'email_id' && emailId) {
            examples.push({ type: 'email_id', value: emailId });
        }
    }

    return examples;
}

/**
 * Add a new from email input field
 */
function addFromEmail(value = '') {
    const container = document.getElementById('from-emails-container');
    const id = `from-email-${fromEmailCounter++}`;

    const wrapper = document.createElement('div');
    wrapper.className = 'from-email-input-wrapper';
    wrapper.id = id;
    wrapper.innerHTML = `
        <input type="email" class="form-input from-email-input"
               placeholder="noreply@bank.com" value="${value}">
        <button type="button" class="btn-icon" onclick="removeFromEmail('${id}')"
                ${fromEmailCounter === 1 ? 'disabled' : ''}>
            ✕
        </button>
    `;
    container.appendChild(wrapper);

    // Re-enable/disable remove buttons based on count
    updateFromEmailButtons();
}

/**
 * Remove a from email input field
 */
function removeFromEmail(id) {
    const container = document.getElementById('from-emails-container');
    if (container.children.length > 1) {
        document.getElementById(id).remove();
        updateFromEmailButtons();
    }
}

/**
 * Update remove button states based on email count
 */
function updateFromEmailButtons() {
    const container = document.getElementById('from-emails-container');
    const removeButtons = container.querySelectorAll('.btn-icon');
    const hasMultiple = container.children.length > 1;

    removeButtons.forEach(button => {
        button.disabled = !hasMultiple;
    });
}

/**
 * Load existing fetcher data into form (edit mode)
 */
function loadFetcherData(fetcher) {
    // Set basic fields
    document.getElementById('fetcher-name').value = fetcher.name || '';
    document.getElementById('subject-filter').value = fetcher.subject_filter || '';
    document.getElementById('default-currency').value = fetcher.default_currency || 'USD';
    document.getElementById('negate-amount').checked = fetcher.negate_amount || false;

    // Load from emails
    if (fetcher.from_emails && fetcher.from_emails.length > 0) {
        // Clear the initial empty from email input
        const container = document.getElementById('from-emails-container');
        container.innerHTML = '';
        fromEmailCounter = 0;

        // Add all from emails
        fetcher.from_emails.forEach((email) => {
            addFromEmail(email);
        });
    }

    // Load patterns if they exist
    if (fetcher.amount_pattern || fetcher.merchant_pattern || fetcher.currency_pattern) {
        // Store patterns
        currentPatterns = {
            amount_pattern: fetcher.amount_pattern,
            merchant_pattern: fetcher.merchant_pattern,
            currency_pattern: fetcher.currency_pattern,
            negate_amount: fetcher.negate_amount
        };

        // Store as original patterns for reset functionality
        originalPatterns = { ...currentPatterns };

        // Display patterns in UI
        displayPatternsForEdit();

        // Show pattern test section
        showPatternTestSection();

        // Show save button section since we have valid patterns
        const saveSection = document.getElementById('save-fetcher-section');
        if (saveSection) {
            saveSection.classList.remove('hidden');
        }
    }
}

/**
 * Display pre-loaded patterns (for edit mode initialization)
 */
function displayPatternsForEdit() {
    const resultsSection = document.getElementById('results-section');
    if (resultsSection) {
        resultsSection.classList.remove('hidden');
    }

    // Populate pattern textareas
    document.getElementById('amount-pattern').value = currentPatterns.amount_pattern || '';
    document.getElementById('merchant-pattern').value = currentPatterns.merchant_pattern || '';
    document.getElementById('currency-pattern').value = currentPatterns.currency_pattern || '';

    // Apply expert mode state to patterns
    if (expertModeEnabled) {
        makePatternEditable('amount', true);
        makePatternEditable('merchant', true);
        makePatternEditable('currency', true);
    }
}

/**
 * Show pattern test section
 */
function showPatternTestSection() {
    const testSection = document.getElementById('pattern-test-section');
    if (testSection) {
        testSection.classList.remove('hidden');
    }
}

/**
 * Collect all from email addresses
 */
function collectFromEmails() {
    const inputs = document.querySelectorAll('.from-email-input');
    const emails = Array.from(inputs).map(input => input.value.trim()).filter(e => e);
    return emails;
}

/**
 * Validate fetcher configuration
 */
function validateFetcherConfig() {
    const name = document.getElementById('fetcher-name').value.trim();
    const fromEmails = collectFromEmails();
    const defaultCurrency = document.getElementById('default-currency').value;

    if (!name) {
        showToast('Please enter a fetcher name', 'error');
        return false;
    }

    if (fromEmails.length === 0) {
        showToast('At least one from email is required', 'error');
        return false;
    }

    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    for (const email of fromEmails) {
        if (!emailRegex.test(email)) {
            showToast(`Invalid email format: ${email}`, 'error');
            return false;
        }
    }

    if (!defaultCurrency) {
        showToast('Please select a default currency', 'error');
        return false;
    }

    return true;
}

/**
 * Populate currency dropdown from backend
 */
async function populateCurrencyDropdown() {
    try {
        const response = await fetch('/api/supported-currencies');
        const data = await response.json();

        if (data.success) {
            const select = document.getElementById('default-currency');
            data.currencies.forEach(currency => {
                const option = document.createElement('option');
                option.value = currency.code;
                option.textContent = `${currency.code} - ${currency.name} (${currency.symbol})`;
                select.appendChild(option);
            });

            // Set default to USD
            select.value = 'USD';
        }
    } catch (error) {
        console.error('Error loading currencies:', error);
    }
}

/**
 * Fetch email bodies client-side using the GIS token.
 * Handles both manual email-ID entries and Gmail search (from_emails).
 * Returns an array of plain-text email body strings.
 */
async function fetchEmailTextsClientSide(examples, fromEmails, subjectFilter) {
    const token = await window.emailTokenManager.getOrRequestToken();
    const { GmailApiClient, FetcherEngine } = window.gmailFetch;
    const emailTexts = [];

    if (examples.length > 0) {
        for (const ex of examples) {
            if (ex.type === 'text') {
                emailTexts.push(ex.value);
            } else {
                const msg = await GmailApiClient.getMessage(token, ex.value);
                const body = FetcherEngine.getBodyFromMessage(msg);
                if (body) emailTexts.push(body);
            }
        }
    } else if (fromEmails.length > 0) {
        const fromFilter = fromEmails.length === 1
            ? `from:${fromEmails[0]}`
            : `(${fromEmails.map(e => `from:${e}`).join(' OR ')})`;
        const query = subjectFilter ? `${fromFilter} subject:${subjectFilter}` : fromFilter;
        const ids = await GmailApiClient.listMessages(token, query);
        const settled = await GmailApiClient.getMessages(token, ids.slice(0, 10), () => {});
        settled.forEach(s => {
            if (s.status === 'fulfilled') {
                const body = FetcherEngine.getBodyFromMessage(s.value);
                if (body) emailTexts.push(body);
            }
        });
    }

    return emailTexts;
}

/**
 * Submit the form and call the API
 */
async function submitForm() {
    // Validate fetcher configuration
    if (!validateFetcherConfig()) {
        return;
    }

    const examples = collectEmailExamples();
    const fromEmails = collectFromEmails();
    const subjectFilter = document.getElementById('subject-filter').value.trim();
    const negateAmount = document.getElementById('negate-amount').checked;

    if (examples.length === 0 && fromEmails.length === 0) {
        showToast('Please add training emails or configure from email addresses', 'error');
        return;
    }

    showLoading(true);

    let emailTexts;
    try {
        emailTexts = await fetchEmailTextsClientSide(examples, fromEmails, subjectFilter);
    } catch (err) {
        showToast('Failed to fetch emails: ' + err.message, 'error');
        showLoading(false);
        return;
    }

    if (emailTexts.length === 0) {
        showToast('No email text could be retrieved', 'error');
        showLoading(false);
        return;
    }

    try {
        const response = await fetch('/api/fetchers/generate-patterns', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email_texts: emailTexts, negate_amount: negateAmount })
        });

        const data = await response.json();

        // Handle rate limit exceeded (429)
        if (response.status === 429) {
            let errorMessage = data.error || 'Rate limit exceeded';
            if (data.rate_limit && data.rate_limit.reset_at) {
                const resetTime = new Date(data.rate_limit.reset_at);
                const timeUntilReset = formatTimeUntilReset(resetTime);
                errorMessage += `. Try again in ${timeUntilReset}.`;
            }
            showToast(errorMessage, 'error');
            return;
        }

        if (data.success) {
            displayResults(data);
            if (data.rate_limit && data.rate_limit.remaining <= 10) {
                showToast(`${data.rate_limit.remaining} LLM calls remaining today`, 'warning');
            }
        } else {
            showToast(data.error || 'Failed to generate patterns', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showToast('Network error: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

/**
 * Format time until rate limit reset in human-readable form
 */
function formatTimeUntilReset(resetTime) {
    const now = new Date();
    const diffMs = resetTime - now;

    if (diffMs <= 0) {
        return 'a moment';
    }

    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));

    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
        return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
    } else {
        return 'less than a minute';
    }
}

/**
 * Display the API results
 */
function displayResults(data) {
    // Populate pattern textareas
    document.getElementById('amount-pattern').value = data.patterns.amount_pattern || '(none)';
    document.getElementById('merchant-pattern').value = data.patterns.merchant_pattern || '(none)';
    document.getElementById('currency-pattern').value = data.patterns.currency_pattern || '(none)';

    // Show training results (may have been hidden by manual pattern entry)
    showTrainingResults();

    // Render transaction tables for each email
    const transactionsContainer = document.getElementById('transactions-container');
    transactionsContainer.innerHTML = '';

    if (data.emails_data && data.emails_data.length > 0) {
        data.emails_data.forEach((emailData, emailIndex) => {
            const emailSection = document.createElement('div');
            emailSection.className = 'email-transactions-section';

            const headerText = emailData.transactions.length === 1
                ? '1 transaction'
                : `${emailData.transactions.length} transactions`;

            emailSection.innerHTML = `
                <h4>Email ${emailIndex + 1} (${headerText})</h4>
                <div class="table-wrapper">
                    <table class="transaction-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Amount</th>
                                <th>Merchant</th>
                                <th>Currency</th>
                            </tr>
                        </thead>
                        <tbody id="transactions-tbody-${emailIndex}"></tbody>
                    </table>
                </div>
            `;

            transactionsContainer.appendChild(emailSection);

            // Populate table
            const tbody = document.getElementById(`transactions-tbody-${emailIndex}`);
            if (emailData.transactions && emailData.transactions.length > 0) {
                emailData.transactions.forEach((tx, txIndex) => {
                    const row = tbody.insertRow();
                    row.innerHTML = `
                        <td>${txIndex + 1}</td>
                        <td>${escapeHtml(tx.amount || 'N/A')}</td>
                        <td>${escapeHtml(tx.merchant || 'N/A')}</td>
                        <td>${escapeHtml(tx.currency || 'N/A')}</td>
                    `;
                });
            } else {
                const row = tbody.insertRow();
                row.innerHTML = '<td colspan="4" style="text-align: center; color: var(--text-muted);">No transactions found</td>';
            }
        });
    } else {
        transactionsContainer.innerHTML = '<p style="text-align: center; color: var(--text-muted);">No emails processed</p>';
    }

    // Render email preview sections
    const emailPreviewsContainer = document.getElementById('email-previews-container');
    emailPreviewsContainer.innerHTML = '';

    if (data.emails_data && data.emails_data.length > 0) {
        data.emails_data.forEach((emailData, emailIndex) => {
            const previewCard = document.createElement('div');
            previewCard.className = 'email-preview-card';
            previewCard.innerHTML = `
                <button class="collapsible-header" onclick="toggleEmailPreview(${emailIndex})">
                    <span>Email ${emailIndex + 1} Text</span>
                    <span class="chevron">▼</span>
                </button>
                <div id="email-preview-content-${emailIndex}" class="collapsible-content">
                    <pre id="email-text-display-${emailIndex}" class="email-text-display"></pre>
                </div>
            `;
            emailPreviewsContainer.appendChild(previewCard);

            // Set email text using textContent to preserve newlines
            const preElement = document.getElementById(`email-text-display-${emailIndex}`);
            preElement.textContent = emailData.email_text || '';
        });
    }

    // Show results section
    document.getElementById('results-section').classList.remove('hidden');

    // Store patterns globally for testing (including negate_amount from checkbox)
    currentPatterns = {
        amount_pattern: data.patterns.amount_pattern,
        merchant_pattern: data.patterns.merchant_pattern,
        currency_pattern: data.patterns.currency_pattern,
        negate_amount: document.getElementById('negate-amount').checked
    };

    // Store original patterns for expert mode
    originalPatterns = {
        amount_pattern: data.patterns.amount_pattern,
        merchant_pattern: data.patterns.merchant_pattern,
        currency_pattern: data.patterns.currency_pattern,
        negate_amount: document.getElementById('negate-amount').checked
    };

    // If expert mode is enabled, make patterns editable
    if (expertModeEnabled) {
        makePatternEditable('amount', true);
        makePatternEditable('merchant', true);
        makePatternEditable('currency', true);
        document.getElementById('reset-patterns-btn').style.display = 'inline-block';
    } else {
        // Make sure patterns are readonly
        makePatternEditable('amount', false);
        makePatternEditable('merchant', false);
        makePatternEditable('currency', false);
        document.getElementById('reset-patterns-btn').style.display = 'none';
    }

    // Show pattern test section
    const patternTestSection = document.getElementById('pattern-test-section');
    patternTestSection.classList.remove('hidden');

    // Initialize with one test example if empty
    const testContainer = document.getElementById('test-email-examples-container');
    if (testContainer.children.length === 0) {
        addTestEmailExample();
    }

    // Scroll to results
    document.getElementById('results-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Copy pattern to clipboard
 */
async function copyPattern(type) {
    const patternId = `${type}-pattern`;
    const textarea = document.getElementById(patternId);
    const button = document.querySelector(`button[onclick="copyPattern('${type}')"]`);

    if (!textarea || !textarea.value) {
        return;
    }

    try {
        await navigator.clipboard.writeText(textarea.value);

        // Visual feedback
        const originalText = button.innerHTML;
        button.innerHTML = '✓';
        button.classList.add('copied');

        setTimeout(() => {
            button.innerHTML = originalText;
            button.classList.remove('copied');
        }, 2000);

        // Show success toast if available
        if (typeof showToast !== 'undefined') {
            showToast('Pattern copied to clipboard', 'success');
        }
    } catch (error) {
        console.error('Failed to copy:', error);
        showToast('Failed to copy to clipboard', 'error');
    }
}

/**
 * Toggle email preview collapse
 */
function toggleEmailPreview(emailIndex) {
    const content = document.getElementById(`email-preview-content-${emailIndex}`);
    const header = content.previousElementSibling;

    header.classList.toggle('active');
    content.classList.toggle('open');
}

/**
 * Clear the form
 */
function clearForm() {
    // Clear all email examples
    const container = document.getElementById('email-examples-container');
    container.innerHTML = '';

    // Reset counter
    exampleCounter = 0;

    // Add a fresh example
    addEmailExample();

    // Hide results
    document.getElementById('results-section').classList.add('hidden');

    // Clear test section
    document.getElementById('pattern-test-section').classList.add('hidden');
    document.getElementById('test-results-container').classList.add('hidden');
    const testContainer = document.getElementById('test-email-examples-container');
    testContainer.innerHTML = '';
    testExampleCounter = 0;

    // Clear stored patterns
    currentPatterns = {
        amount_pattern: null,
        merchant_pattern: null,
        currency_pattern: null,
        negate_amount: false
    };

    // Close error
}

/**
 * Show loading overlay
 */
function showLoading(show) {
    const overlay = document.getElementById('loading-overlay');
    if (show) {
        overlay.classList.remove('hidden');
    } else {
        overlay.classList.add('hidden');
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Add a new test email example input
 */
function addTestEmailExample() {
    const container = document.getElementById('test-email-examples-container');
    const id = testExampleCounter++;

    const exampleDiv = document.createElement('div');
    exampleDiv.className = 'email-example-card';
    exampleDiv.id = `test-email-example-${id}`;

    exampleDiv.innerHTML = `
        <div class="example-header">
            <span class="example-title">Test Email ${id + 1}</span>
            <button type="button" class="btn-icon remove-btn" onclick="removeTestEmailExample(${id})" title="Remove">
                ✕
            </button>
        </div>

        <div class="form-group">
            <label class="form-label">Input Mode</label>
            <div class="input-mode-toggle">
                <label class="radio-label">
                    <input type="radio" name="test_input_mode_${id}" value="text" checked onchange="toggleTestInputMode(${id}, 'text')">
                    <span>Raw Email Text</span>
                </label>
                <label class="radio-label">
                    <input type="radio" name="test_input_mode_${id}" value="email_id" onchange="toggleTestInputMode(${id}, 'email_id')">
                    <span>Gmail Message ID</span>
                </label>
            </div>
        </div>

        <div class="form-group" id="test-email-text-group-${id}">
            <label class="form-label" for="test-email-text-${id}">Email Text</label>
            <textarea
                id="test-email-text-${id}"
                name="test_email_text_${id}"
                class="form-input email-textarea"
                placeholder="Paste your test email text here..."
                rows="6"
            ></textarea>
        </div>

        <div class="form-group hidden" id="test-email-id-group-${id}">
            <label class="form-label" for="test-email-id-${id}">Gmail Message ID</label>
            <input
                type="text"
                id="test-email-id-${id}"
                name="test_email_id_${id}"
                class="form-input"
                placeholder="e.g., CANLLRpb...@mail.gmail.com"
            >
            <small class="form-help">
                Open the email in Gmail &rarr; three-dot menu &rarr;
                "Show original" &rarr; copy the <strong>Message ID</strong> value.
            </small>
        </div>
    `;

    container.appendChild(exampleDiv);
}

/**
 * Remove a test email example
 */
function removeTestEmailExample(id) {
    const exampleDiv = document.getElementById(`test-email-example-${id}`);
    if (exampleDiv) {
        exampleDiv.remove();
    }
}

/**
 * Toggle between email text and email ID input modes for test examples
 */
function toggleTestInputMode(id, mode) {
    const emailTextGroup = document.getElementById(`test-email-text-group-${id}`);
    const emailIdGroup = document.getElementById(`test-email-id-group-${id}`);
    const emailTextInput = document.getElementById(`test-email-text-${id}`);
    const emailIdInput = document.getElementById(`test-email-id-${id}`);

    if (mode === 'text') {
        emailTextGroup.classList.remove('hidden');
        emailIdGroup.classList.add('hidden');
        if (emailIdInput) emailIdInput.value = '';
    } else {
        emailTextGroup.classList.add('hidden');
        emailIdGroup.classList.remove('hidden');
        if (emailTextInput) emailTextInput.value = '';
    }
}

/**
 * Collect all test email examples
 */
function collectTestEmailExamples() {
    const container = document.getElementById('test-email-examples-container');
    const examples = [];

    for (const exampleDiv of container.children) {
        const id = parseInt(exampleDiv.id.split('-')[3]); // "test-email-example-0" -> 0

        const mode = document.querySelector(`input[name="test_input_mode_${id}"]:checked`)?.value;
        if (!mode) continue;

        const emailText = document.getElementById(`test-email-text-${id}`)?.value.trim();
        const emailId = document.getElementById(`test-email-id-${id}`)?.value.trim();

        if (mode === 'text' && emailText) {
            examples.push({ type: 'text', value: emailText });
        } else if (mode === 'email_id' && emailId) {
            examples.push({ type: 'email_id', value: emailId });
        }
    }

    return examples;
}

/**
 * Submit test emails for pattern testing
 */
async function submitTestEmails() {
    // Read current values from UI elements first
    // This ensures we capture manually entered patterns (expert mode) and checkbox state
    currentPatterns = {
        amount_pattern: document.getElementById('amount-pattern').value.trim() || null,
        merchant_pattern: document.getElementById('merchant-pattern').value.trim() || null,
        currency_pattern: document.getElementById('currency-pattern').value.trim() || null,
        negate_amount: document.getElementById('negate-amount').checked
    };

    // Validate we have at least one pattern
    if (!currentPatterns.amount_pattern && !currentPatterns.merchant_pattern) {
        showToast('Please enter at least an amount or merchant pattern', 'error');
        return;
    }

    // Validate pattern syntax if in expert mode
    if (expertModeEnabled) {
        const amountPattern = currentPatterns.amount_pattern;
        const merchantPattern = currentPatterns.merchant_pattern;
        const currencyPattern = currentPatterns.currency_pattern;

        const amountValidation = amountPattern ? validateRegexPattern(amountPattern) : { valid: true };
        const merchantValidation = merchantPattern ? validateRegexPattern(merchantPattern) : { valid: true };
        const currencyValidation = currencyPattern ? validateRegexPattern(currencyPattern) : { valid: true };

        if (!amountValidation.valid) {
            showToast('Invalid amount pattern: ' + amountValidation.error, 'error');
            return;
        }
        if (!merchantValidation.valid) {
            showToast('Invalid merchant pattern: ' + merchantValidation.error, 'error');
            return;
        }
        if (!currencyValidation.valid) {
            showToast('Invalid currency pattern: ' + currencyValidation.error, 'error');
            return;
        }
    }

    // Collect test examples
    const testExamples = collectTestEmailExamples();
    const fromEmails = collectFromEmails();
    const subjectFilter = document.getElementById('subject-filter').value.trim();

    if (testExamples.length === 0 && fromEmails.length === 0) {
        showToast('Please add test emails or ensure from emails are configured', 'error');
        return;
    }

    showLoading(true);

    let emailTexts;
    try {
        emailTexts = await fetchEmailTextsClientSide(testExamples, fromEmails, subjectFilter);
    } catch (err) {
        showToast('Failed to fetch emails: ' + err.message, 'error');
        showLoading(false);
        return;
    }

    if (emailTexts.length === 0) {
        showToast('No email text could be retrieved', 'error');
        showLoading(false);
        return;
    }

    try {
        // Run pattern matching entirely client-side — no server call needed
        const fetcher = {
            amount_pattern:   currentPatterns.amount_pattern,
            merchant_pattern: currentPatterns.merchant_pattern,
            currency_pattern: currentPatterns.currency_pattern,
            negate_amount:    currentPatterns.negate_amount,
        };
        const emailsData = emailTexts.map(text => ({
            email_text: text,
            transactions: window.gmailFetch.FetcherEngine.parseTransactionsWithPatterns(text, fetcher),
        }));

        displayTestResults({ success: true, emails_data: emailsData });

        if (emailsData.some(e => e.transactions.length > 0)) {
            showSaveButton();
        }
    } catch (error) {
        console.error('Error:', error);
        showToast('Error running patterns: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

/**
 * Display test results
 */
function displayTestResults(data) {
    const testResultsContainer = document.getElementById('test-results-container');
    const testTransactionsContainer = document.getElementById('test-transactions-container');
    const testEmailPreviewsContainer = document.getElementById('test-email-previews-container');

    // Clear previous test results
    testTransactionsContainer.innerHTML = '';
    testEmailPreviewsContainer.innerHTML = '';

    // Render transaction tables for each test email
    if (data.emails_data && data.emails_data.length > 0) {
        data.emails_data.forEach((emailData, emailIndex) => {
            const emailSection = document.createElement('div');
            emailSection.className = 'email-transactions-section';

            const headerText = emailData.transactions.length === 1
                ? '1 transaction'
                : `${emailData.transactions.length} transactions`;

            emailSection.innerHTML = `
                <h4>Test Email ${emailIndex + 1} (${headerText})</h4>
                <div class="table-wrapper">
                    <table class="transaction-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Amount</th>
                                <th>Merchant</th>
                                <th>Currency</th>
                            </tr>
                        </thead>
                        <tbody id="test-transactions-tbody-${emailIndex}"></tbody>
                    </table>
                </div>
            `;

            testTransactionsContainer.appendChild(emailSection);

            // Populate table
            const tbody = document.getElementById(`test-transactions-tbody-${emailIndex}`);
            if (emailData.transactions && emailData.transactions.length > 0) {
                emailData.transactions.forEach((tx, txIndex) => {
                    const row = tbody.insertRow();
                    row.innerHTML = `
                        <td>${txIndex + 1}</td>
                        <td>${escapeHtml(tx.amount || 'N/A')}</td>
                        <td>${escapeHtml(tx.merchant || 'N/A')}</td>
                        <td>${escapeHtml(tx.currency || 'N/A')}</td>
                    `;
                });
            } else {
                const row = tbody.insertRow();
                row.innerHTML = '<td colspan="4" style="text-align: center; color: var(--text-muted);">No transactions found</td>';
            }
        });

        // Render test email preview sections
        data.emails_data.forEach((emailData, emailIndex) => {
            const previewCard = document.createElement('div');
            previewCard.className = 'email-preview-card';
            previewCard.innerHTML = `
                <button class="collapsible-header" onclick="toggleTestEmailPreview(${emailIndex})">
                    <span>Test Email ${emailIndex + 1} Text</span>
                    <span class="chevron">▼</span>
                </button>
                <div id="test-email-preview-content-${emailIndex}" class="collapsible-content">
                    <pre id="test-email-text-display-${emailIndex}" class="email-text-display"></pre>
                </div>
            `;
            testEmailPreviewsContainer.appendChild(previewCard);

            // Set email text
            const preElement = document.getElementById(`test-email-text-display-${emailIndex}`);
            preElement.textContent = emailData.email_text || '';
        });
    } else {
        testTransactionsContainer.innerHTML = '<p style="text-align: center; color: var(--text-muted);">No test emails processed</p>';
    }

    // Show test results section
    testResultsContainer.classList.remove('hidden');

    // Scroll to test results
    testResultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Toggle test email preview collapse
 */
function toggleTestEmailPreview(emailIndex) {
    const content = document.getElementById(`test-email-preview-content-${emailIndex}`);
    const header = content.previousElementSibling;

    header.classList.toggle('active');
    content.classList.toggle('open');
}

/* ===== MANUAL PATTERN ENTRY (EXPERT MODE) ===== */

/**
 * Show pattern fields for manual entry when expert mode is enabled on page load.
 * Allows users to write regex patterns without running the LLM step first.
 */
function showManualPatternEntry() {
    // Show results section
    const resultsSection = document.getElementById('results-section');
    if (resultsSection) {
        resultsSection.classList.remove('hidden');
    }

    // Hide training results (no LLM-generated data yet)
    hideTrainingResults();

    // Make patterns editable and empty
    makePatternEditable('amount', true);
    makePatternEditable('merchant', true);
    makePatternEditable('currency', true);

    // No original patterns to reset to
    document.getElementById('reset-patterns-btn').style.display = 'none';

    // Show test section with one test example
    showPatternTestSection();
    const testContainer = document.getElementById('test-email-examples-container');
    if (testContainer && testContainer.children.length === 0) {
        addTestEmailExample();
    }
}

/**
 * Hide training results section (used when patterns are entered manually)
 */
function hideTrainingResults() {
    const trainingHeader = document.querySelector('.training-results-header');
    const transactionsCard = document.querySelector('.transactions-card');
    const emailPreviews = document.getElementById('email-previews-container');

    if (trainingHeader) trainingHeader.style.display = 'none';
    if (transactionsCard) transactionsCard.style.display = 'none';
    if (emailPreviews) emailPreviews.style.display = 'none';
}

/**
 * Show training results section (used when LLM generates patterns)
 */
function showTrainingResults() {
    const trainingHeader = document.querySelector('.training-results-header');
    const transactionsCard = document.querySelector('.transactions-card');
    const emailPreviews = document.getElementById('email-previews-container');

    if (trainingHeader) trainingHeader.style.display = '';
    if (transactionsCard) transactionsCard.style.display = '';
    if (emailPreviews) emailPreviews.style.display = '';
}

/* ===== EXPERT MODE FUNCTIONS ===== */

/**
 * Initialize expert mode on page load
 */
async function initializeExpertMode() {
    try {
        const response = await fetch('/api/user-settings/browser');
        if (response.ok) {
            const browserSettings = await response.json();
            const enabled = browserSettings.fetcher_advanced_mode || false;

            expertModeEnabled = enabled;
            const toggle = document.getElementById('expert-mode-toggle');
            if (toggle) {
                toggle.checked = enabled;
            }
        }
    } catch (error) {
        console.error('Failed to load expert mode preference:', error);
    }
}

/**
 * Load expert mode preference from database
 */
async function loadExpertModePreference() {
    try {
        const response = await fetch('/api/user-settings/browser');
        if (!response.ok) throw new Error('Failed to load settings');

        const browserSettings = await response.json();
        return browserSettings.fetcher_advanced_mode || false;
    } catch (error) {
        console.error('Error loading expert mode preference:', error);
        return false;
    }
}

/**
 * Save expert mode preference to database
 */
async function saveExpertModePreference(enabled) {
    try {
        const response = await fetch('/api/user-settings/browser', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                browser_settings: {
                    fetcher_advanced_mode: enabled
                }
            })
        });

        if (!response.ok) {
            throw new Error('Failed to save preference');
        }

        return true;
    } catch (error) {
        console.error('Error saving expert mode preference:', error);
        showToast('Failed to save expert mode preference', 'error');
        return false;
    }
}

/**
 * Toggle expert mode with confirmation
 */
async function toggleExpertMode(enabled) {
    if (enabled) {
        // Show confirmation dialog
        const confirmed = await showExpertModeConfirmation();

        if (!confirmed) {
            // User canceled, revert toggle
            document.getElementById('expert-mode-toggle').checked = false;
            return;
        }

        // Save preference to database
        const saved = await saveExpertModePreference(true);
        if (!saved) {
            // Failed to save, revert toggle
            document.getElementById('expert-mode-toggle').checked = false;
            return;
        }

        // Enable expert mode
        expertModeEnabled = true;
        makePatternEditable('amount', true);
        makePatternEditable('merchant', true);
        makePatternEditable('currency', true);

        // Show reset button
        document.getElementById('reset-patterns-btn').style.display = 'inline-block';

        // Store original patterns if not already stored
        if (!originalPatterns.amount_pattern) {
            originalPatterns = { ...currentPatterns };
        }

        showToast('Expert mode enabled. You can now edit patterns manually.', 'warning');
    } else {
        // Save preference to database
        await saveExpertModePreference(false);

        // Disable expert mode
        expertModeEnabled = false;
        makePatternEditable('amount', false);
        makePatternEditable('merchant', false);
        makePatternEditable('currency', false);

        // Hide reset button
        document.getElementById('reset-patterns-btn').style.display = 'none';

        // Clear any errors
        clearPatternError('amount');
        clearPatternError('merchant');
        clearPatternError('currency');

        showToast('Expert mode disabled.', 'info');
    }
}

/**
 * Show confirmation dialog for expert mode
 */
async function showExpertModeConfirmation() {
    const message = 'Expert mode enables you to manually edit regex patterns. This is an advanced feature that allows you to fine-tune pattern matching. Incorrect patterns may prevent transactions from being extracted correctly. Use the testing section to verify your changes.';
    const title = 'Enable Expert Mode?';

    return await showConfirm(message, title);
}

/**
 * Make a pattern textarea editable or readonly
 */
function makePatternEditable(patternType, editable) {
    const textarea = document.getElementById(`${patternType}-pattern`);
    if (!textarea) return;

    if (editable) {
        textarea.removeAttribute('readonly');
        textarea.classList.add('pattern-display--editable');

        // Add event listeners
        textarea.addEventListener('blur', () => handlePatternBlur(patternType));
        textarea.addEventListener('input', () => handlePatternInput(patternType));
    } else {
        textarea.setAttribute('readonly', 'readonly');
        textarea.classList.remove('pattern-display--editable', 'pattern-display--error');

        // Remove event listeners by cloning (removes all listeners)
        const newTextarea = textarea.cloneNode(true);
        textarea.parentNode.replaceChild(newTextarea, textarea);
    }
}

/**
 * Handle pattern textarea blur (validate on blur)
 */
function handlePatternBlur(patternType) {
    const textarea = document.getElementById(`${patternType}-pattern`);
    const pattern = textarea.value.trim();

    if (!pattern) {
        clearPatternError(patternType);
        return;
    }

    const validation = validateRegexPattern(pattern);

    if (validation.valid) {
        // Update currentPatterns
        const patternKey = `${patternType}_pattern`;
        currentPatterns[patternKey] = pattern;

        // Clear error
        clearPatternError(patternType);
        textarea.classList.remove('pattern-display--error');
    } else {
        // Show error
        showPatternError(patternType, validation.error);
        textarea.classList.add('pattern-display--error');
    }
}

/**
 * Handle pattern textarea input (clear errors on input)
 */
function handlePatternInput(patternType) {
    clearPatternError(patternType);
    document.getElementById(`${patternType}-pattern`).classList.remove('pattern-display--error');
}

/**
 * Validate regex pattern syntax
 */
function validateRegexPattern(pattern) {
    try {
        new RegExp(pattern);
        return { valid: true };
    } catch (e) {
        return {
            valid: false,
            error: e.message
        };
    }
}

/**
 * Show pattern validation error
 */
function showPatternError(patternType, errorMessage) {
    const errorDiv = document.getElementById(`${patternType}-pattern-error`);
    if (errorDiv) {
        errorDiv.innerHTML = `<span class="pattern-error-icon">⚠</span>${escapeHtml(errorMessage)}`;
        errorDiv.classList.add('visible');
    }
}

/**
 * Clear pattern validation error
 */
function clearPatternError(patternType) {
    const errorDiv = document.getElementById(`${patternType}-pattern-error`);
    if (errorDiv) {
        errorDiv.classList.remove('visible');
        errorDiv.innerHTML = '';
    }
}

/**
 * Reset patterns to original LLM-generated values
 */
async function resetToOriginalPatterns() {
    const confirmed = await showConfirm(
        'Reset all patterns to the original LLM-generated values?',
        'Reset Patterns'
    );

    if (!confirmed) return;

    // Restore original patterns
    currentPatterns = { ...originalPatterns };

    // Update textareas
    document.getElementById('amount-pattern').value = originalPatterns.amount_pattern || '';
    document.getElementById('merchant-pattern').value = originalPatterns.merchant_pattern || '';
    document.getElementById('currency-pattern').value = originalPatterns.currency_pattern || '';

    // Clear all errors
    clearPatternError('amount');
    clearPatternError('merchant');
    clearPatternError('currency');

    document.getElementById('amount-pattern').classList.remove('pattern-display--error');
    document.getElementById('merchant-pattern').classList.remove('pattern-display--error');
    document.getElementById('currency-pattern').classList.remove('pattern-display--error');

    showToast('Patterns reset to original values', 'success');
}

/**
 * Capitalize first letter of string
 */
function capitalizeFirst(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Show the save fetcher button
 */
function showSaveButton() {
    const saveSection = document.getElementById('save-fetcher-section');
    if (saveSection) {
        saveSection.classList.remove('hidden');
    }
}

/**
 * Save or update fetcher configuration
 */
async function saveFetcher() {
    try {
        // Validate fetcher config
        if (!validateFetcherConfig()) {
            return;
        }

        const name = document.getElementById('fetcher-name').value.trim();
        const fromEmails = collectFromEmails();
        const subjectFilter = document.getElementById('subject-filter').value.trim();
        const defaultCurrency = document.getElementById('default-currency').value;
        const negateAmount = document.getElementById('negate-amount').checked;

        // Get patterns
        const amountPattern = document.getElementById('amount-pattern').value.trim();
        const merchantPattern = document.getElementById('merchant-pattern').value.trim();
        const currencyPattern = document.getElementById('currency-pattern').value.trim();

        if (!amountPattern) {
            showToast('Amount pattern is required', 'error');
            return;
        }

        // Show loading
        showLoading(true);

        // Determine if we're in edit mode
        const isEditMode = window.FETCHER_MODE === 'edit';
        const fetcherId = isEditMode ? document.getElementById('fetcher-id')?.value : null;

        // Build request URL and method
        const url = isEditMode ? `/api/fetchers/${fetcherId}` : '/api/fetchers/save';
        const method = isEditMode ? 'PUT' : 'POST';

        const requestBody = {
            name,
            from_emails: fromEmails,
            subject_filter: subjectFilter,
            amount_pattern: amountPattern,
            merchant_pattern: merchantPattern || null,
            currency_pattern: currencyPattern || null,
            default_currency: defaultCurrency,
            negate_amount: negateAmount
        };

        // Make API call
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();

        if (data.success) {
            let message = isEditMode
                ? `Fetcher updated to version ${data.version}!`
                : 'Fetcher saved successfully!';
            showToast(message, 'success');

            // Hide the save button after successful save
            const saveSection = document.getElementById('save-fetcher-section');
            if (saveSection) {
                saveSection.classList.add('hidden');
            }

            // In wizard mode, call callback instead of redirecting
            if (window.FETCHER_MODE === 'wizard' && fetcherSaveCallback) {
                fetcherSaveCallback(data);
                resetFetcherForm();
                return;
            }

            // In edit mode, redirect to the new version's edit page after a short delay
            if (isEditMode && data.fetcher_id) {
                setTimeout(() => {
                    window.location.href = `/settings/fetchers/${data.fetcher_id}`;
                }, 1500);
            }
        } else {
            const action = isEditMode ? 'update' : 'save';
            showToast(data.error || `Failed to ${action} fetcher`, 'error');
        }

    } catch (error) {
        console.error('Error:', error);
        const action = window.FETCHER_MODE === 'edit' ? 'updating' : 'saving';
        showToast(`Error ${action} fetcher: ${error.message}`, 'error');
    } finally {
        showLoading(false);
    }
}

/**
 * Toggle fetcher enabled status
 */
async function toggleFetcher(fetcherId, currentlyEnabled) {
    try {
        const response = await fetch(`/api/fetchers/${fetcherId}/toggle`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });

        const data = await response.json();

        if (data.success) {
            const newStatus = data.enabled;
            showToast(newStatus ? 'Fetcher enabled' : 'Fetcher disabled', 'success');

            // Update UI elements
            const row = document.querySelector(`tr[data-fetcher-id="${fetcherId}"]`);
            if (row) {
                const statusBadge = row.querySelector('.status-badge');
                const toggleBtn = row.querySelector('button[title*="Enable"], button[title*="Disable"]');

                if (statusBadge) {
                    statusBadge.className = `status-badge ${newStatus ? 'status-enabled' : 'status-disabled'}`;
                    statusBadge.textContent = newStatus ? 'Enabled' : 'Disabled';
                }

                if (toggleBtn) {
                    toggleBtn.textContent = newStatus ? '🔕' : '🔔';
                    toggleBtn.title = newStatus ? 'Disable' : 'Enable';
                    toggleBtn.setAttribute('onclick', `toggleFetcher('${fetcherId}', ${newStatus})`);
                }
            }
        } else {
            showToast(data.error || 'Failed to toggle fetcher', 'error');
        }
    } catch (error) {
        console.error('Error toggling fetcher:', error);
        showToast('Network error: ' + error.message, 'error');
    }
}
