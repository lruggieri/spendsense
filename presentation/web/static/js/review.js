// ========================================
// REVIEW PAGE - TRANSACTION MANAGEMENT
// ========================================
// Currency utilities (getCurrencyMinorUnits, toMajorUnits, formatAmount)
// are loaded from currency-utils.js

// State management
let pendingChanges = {}; // { txId: { categoryId, categoryName } }
let currentTxId = null;   // Transaction currently being edited in modal
let currentCategorySource = null; // Category source of current transaction
let autocompleteSuggestions = [];

// ========================================
// INITIALIZATION
// ========================================

// Capture and preserve URL parameters for form submissions
function captureURLParams() {
    const urlParams = new URLSearchParams(window.location.search);
    const paramsString = urlParams.toString();

    // Set the value for all forms that need to preserve params
    const redirectParamsEl = document.getElementById('redirect_params');
    if (redirectParamsEl) {
        redirectParamsEl.value = paramsString;
    }

    const recategorizeForm = document.getElementById('recategorize-form');
    if (recategorizeForm) {
        const redirectParamsInput = recategorizeForm.querySelector('.redirect_params');
        if (redirectParamsInput) {
            redirectParamsInput.value = paramsString;
        }
    }
}

// Initialize live search functionality
function initLiveSearch() {
    const searchInput = document.getElementById('search-input');
    if (!searchInput) return;

    const transactionCards = document.querySelectorAll('.transaction-card');
    const totalCountEl = document.getElementById('total-count');
    const totalAmountEl = document.getElementById('total-amount');
    const filteredInfoEl = document.getElementById('filtered-info');
    const originalCountEl = document.getElementById('original-count');
    const originalCount = transactionCards.length;

    // Get default currency info from the page (from first visible transaction)
    let defaultCurrency = 'JPY';
    let currencySymbol = '¥';
    const firstCard = transactionCards[0];
    if (firstCard) {
        defaultCurrency = firstCard.getAttribute('data-currency') || 'JPY';
        const amountEl = firstCard.querySelector('.info-value[data-amount]');
        if (amountEl) {
            const symbolMatch = amountEl.textContent.match(/^[^\d\s.,]+/);
            if (symbolMatch) {
                currencySymbol = symbolMatch[0];
            }
        }
    }

    searchInput.addEventListener('input', function() {
        const searchQuery = this.value.toLowerCase().trim();
        let visibleCount = 0;
        let visibleTotalMinor = 0;

        transactionCards.forEach(card => {
            const description = card.getAttribute('data-description').toLowerCase();
            const comment = card.getAttribute('data-comment').toLowerCase();
            const amountMinor = parseInt(card.getAttribute('data-amount'));
            const currency = card.getAttribute('data-currency') || defaultCurrency;

            if (!searchQuery || description.includes(searchQuery) || comment.includes(searchQuery)) {
                card.style.display = '';
                visibleCount++;
                // Note: This assumes all transactions are in the same currency
                // For multi-currency, would need currency conversion
                visibleTotalMinor += amountMinor;
            } else {
                card.style.display = 'none';
            }
        });

        // Convert total from minor units to major units and format
        const visibleTotalMajor = toMajorUnits(visibleTotalMinor, defaultCurrency);
        const formattedTotal = formatAmount(visibleTotalMajor, defaultCurrency);

        // Update count display
        totalCountEl.textContent = visibleCount;
        totalAmountEl.textContent = currencySymbol + formattedTotal;

        // Show/hide filtered info
        if (searchQuery && visibleCount < originalCount) {
            originalCountEl.textContent = originalCount;
            filteredInfoEl.style.display = '';
        } else {
            filteredInfoEl.style.display = 'none';
        }
    });

    // Trigger filter on page load if search query exists
    if (searchInput.value) {
        searchInput.dispatchEvent(new Event('input'));
    }
}

// ========================================
// CATEGORY MODAL FUNCTIONS
// ========================================

function openCategoryModal(txId, currentCategoryId, categorySource) {
    currentTxId = txId;
    currentCategorySource = categorySource;
    const modal = document.getElementById('category-modal');
    const items = modal.querySelectorAll('.modal-category-item');
    const clearBtn = document.getElementById('modal-clear-btn');

    // Show clear button only for manual assignments
    if (categorySource === 'manual') {
        clearBtn.style.display = 'block';
        clearBtn.textContent = 'Clear Manual Assignment';
    } else {
        clearBtn.style.display = 'none';
    }

    // Clear previous selection
    items.forEach(item => item.classList.remove('selected'));

    // Highlight current category (use pending change if exists, otherwise original)
    const activeCategoryId = pendingChanges[txId]?.categoryId || currentCategoryId;
    if (activeCategoryId && activeCategoryId !== '') {
        const selectedItem = modal.querySelector(`[data-category-id="${activeCategoryId}"]`);
        if (selectedItem) {
            selectedItem.classList.add('selected');
            selectedItem.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
    }

    modal.classList.add('active');
}

function closeCategoryModal() {
    const modal = document.getElementById('category-modal');
    modal.classList.remove('active');
    currentTxId = null;
}

function closeModalOnOverlay(event) {
    if (event.target.id === 'category-modal') {
        closeCategoryModal();
    }
}

function selectCategory(categoryId, categoryName) {
    if (!currentTxId) return;

    // Handle new transaction form
    if (currentTxId === '__NEW_TX__') {
        document.getElementById('add-tx-category').value = categoryId;
        document.getElementById('add-tx-category-text').textContent = categoryName;
        document.getElementById('add-tx-category-btn').classList.add('modified');
        closeCategoryModal();
        return;
    }

    // Handle existing transaction
    const button = document.querySelector(`button[data-tx-id="${currentTxId}"].category-select-btn`);
    const originalCategory = button.getAttribute('data-original-category');
    const originalSource = button.getAttribute('data-category-source');

    // Update button text
    button.querySelector('.selected-category-text').textContent = categoryName;

    // Track the change
    if (categoryId !== originalCategory) {
        pendingChanges[currentTxId] = { categoryId, categoryName };
        button.classList.add('modified');
        hideConfirmButton(currentTxId);
    } else {
        // Reverted to original - remove from pending changes
        delete pendingChanges[currentTxId];
        button.classList.remove('modified');
        if (originalSource === 'similarity') {
            showConfirmButton(currentTxId);
        }
    }

    updatePendingChangesBar();
    closeCategoryModal();
}

function clearCategory(event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }

    if (!currentTxId) return;

    // Handle new transaction form
    if (currentTxId === '__NEW_TX__') {
        document.getElementById('add-tx-category').value = '';
        document.getElementById('add-tx-category-text').textContent = 'Auto-classify (use system rules)';
        document.getElementById('add-tx-category-btn').classList.remove('modified');
        closeCategoryModal();
        return;
    }

    // Handle existing transaction
    const button = document.querySelector(`button[data-tx-id="${currentTxId}"].category-select-btn`);
    if (!button) return;

    const originalCategory = button.getAttribute('data-original-category');

    // Update button text
    button.querySelector('.selected-category-text').textContent = 'Category will be cleared';
    hideConfirmButton(currentTxId);

    // Track the change
    if (originalCategory !== '') {
        pendingChanges[currentTxId] = { categoryId: '', categoryName: 'Category will be cleared' };
        button.classList.add('modified');
    } else {
        delete pendingChanges[currentTxId];
        button.classList.remove('modified');
    }

    updatePendingChangesBar();
    closeCategoryModal();
}

// ========================================
// PENDING CHANGES MANAGEMENT
// ========================================

function updatePendingChangesBar() {
    const bar = document.getElementById('pending-changes-bar');
    const countEl = document.getElementById('pending-count');
    const changeCount = Object.keys(pendingChanges).length;

    countEl.textContent = changeCount;

    if (changeCount > 0) {
        bar.classList.add('visible');
        requestAnimationFrame(() => {
            document.body.style.setProperty('--pending-bar-offset', bar.offsetHeight + 'px');
        });
    } else {
        bar.classList.remove('visible');
        document.body.style.setProperty('--pending-bar-offset', '0px');
    }
}

function cancelPendingChanges() {
    // Revert all visual changes
    Object.keys(pendingChanges).forEach(txId => {
        const button = document.querySelector(`button[data-tx-id="${txId}"].category-select-btn`);
        const originalCategory = button.getAttribute('data-original-category');
        const originalSource = button.getAttribute('data-category-source');

        // Find original category name
        const modalItems = document.querySelectorAll('.modal-category-item');
        let originalName = 'Select category...';
        modalItems.forEach(item => {
            if (item.getAttribute('data-category-id') === originalCategory) {
                originalName = item.getAttribute('data-category-name');
            }
        });

        button.querySelector('.selected-category-text').textContent = originalName;
        button.classList.remove('modified');

        if (originalSource === 'similarity') {
            showConfirmButton(txId);
        }
    });

    pendingChanges = {};
    updatePendingChangesBar();
}

function submitPendingChanges() {
    if (Object.keys(pendingChanges).length === 0) {
        showToast('No changes to submit.', 'warning');
        return;
    }

    const form = document.getElementById('bulk-assign-form');

    // Remove existing hidden inputs
    form.querySelectorAll('input[name^="category_"]').forEach(input => input.remove());

    // Add hidden inputs for changed transactions
    Object.keys(pendingChanges).forEach(txId => {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = `category_${txId}`;
        const categoryId = pendingChanges[txId].categoryId;

        if (categoryId === '') {
            input.setAttribute('value', '');
            input.value = '';
        } else {
            input.value = categoryId;
        }
        form.appendChild(input);
    });

    // Capture params before submit
    captureURLParams();

    // Submit the form
    form.submit();
}

// ========================================
// HELPER FUNCTIONS
// ========================================

function hideConfirmButton(txId) {
    const confirmButton = document.querySelector(`button[data-tx-id="${txId}"].confirm-btn`);
    if (confirmButton) {
        confirmButton.style.display = 'none';
    }
}

function showConfirmButton(txId) {
    const confirmButton = document.querySelector(`button[data-tx-id="${txId}"].confirm-btn`);
    if (confirmButton) {
        confirmButton.style.display = '';
        confirmButton.classList.remove('confirmed');
        confirmButton.textContent = 'Confirm';
    }
}

function confirmSimilarityCategory(txId, categoryId, categoryName) {
    const selectButton = document.querySelector(`button[data-tx-id="${txId}"].category-select-btn`);

    // Force into pending changes to convert SIMILARITY → MANUAL
    pendingChanges[txId] = { categoryId, categoryName };
    selectButton.classList.add('modified');
    hideConfirmButton(txId);
    updatePendingChangesBar();
}

// ========================================
// ADD/EDIT TRANSACTION MODAL
// ========================================

let currentEditingTxId = null; // Track if we're editing (has ID) or adding (null)
let originalTxSeconds = null; // Store original seconds when editing (datetime-local doesn't support seconds)

function openAddTransactionModal() {
    currentEditingTxId = null; // Adding new transaction
    originalTxSeconds = null; // Reset seconds
    const modal = document.getElementById('add-transaction-modal');
    const form = document.getElementById('add-transaction-form');
    const messageDiv = document.getElementById('add-tx-message');
    const modalTitle = modal.querySelector('.modal-title');
    const submitBtn = form.querySelector('button[type="submit"]');
    const categoryGroup = document.getElementById('add-tx-category-group');

    form.reset();
    messageDiv.textContent = '';

    // Update modal title and button
    modalTitle.textContent = 'Add New Transaction';
    submitBtn.textContent = 'Add Transaction';

    // Show category selection for new transactions
    if (categoryGroup) {
        categoryGroup.style.display = '';
    }

    // Set default date & time to now in user's local timezone
    const now = new Date();
    now.setSeconds(0, 0);
    // Format as local time (not UTC) for datetime-local input
    const localDateTime = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    document.getElementById('add-tx-date').value = localDateTime;

    // Reset category
    document.getElementById('add-tx-category').value = '';
    document.getElementById('add-tx-category-text').textContent = 'Auto-classify (use system rules)';
    document.getElementById('add-tx-category-btn').classList.remove('modified');

    // Set default currency (first option or JPY if available)
    const currencySelect = document.getElementById('add-tx-currency');
    if (currencySelect) {
        // Try to default to JPY if available, otherwise use first option
        const jpyOption = Array.from(currencySelect.options).find(opt => opt.value === 'JPY');
        currencySelect.value = jpyOption ? 'JPY' : currencySelect.options[0].value;
    }

    modal.classList.add('active');
}

function openEditTransactionModal(txId) {
    currentEditingTxId = txId; // Editing existing transaction
    const modal = document.getElementById('add-transaction-modal');
    const form = document.getElementById('add-transaction-form');
    const messageDiv = document.getElementById('add-tx-message');
    const modalTitle = modal.querySelector('.modal-title');
    const submitBtn = form.querySelector('button[type="submit"]');
    const categoryGroup = document.getElementById('add-tx-category-group');

    messageDiv.textContent = '';

    // Update modal title and button
    modalTitle.textContent = 'Edit Transaction';
    submitBtn.textContent = 'Save Changes';

    // Hide category selection for editing (categories are managed separately)
    if (categoryGroup) {
        categoryGroup.style.display = 'none';
    }

    // Find the transaction data from the card
    const txCard = document.querySelector(`.transaction-card [data-tx-id="${txId}"]`)?.closest('.transaction-card');
    if (!txCard) {
        showToast('Transaction not found', 'error');
        return;
    }

    // Extract transaction data from the card
    // Use data-utc-date attribute instead of displayed text (which is in local time)
    const dateElement = txCard.querySelector('.info-item:nth-child(1) .info-value');
    const utcDateString = dateElement.getAttribute('data-utc-date');
    // Get amount from data-amount attribute (avoids including converted amount in parentheses)
    const amountElement = txCard.querySelector('.info-item:nth-child(2) .info-value');
    const amountText = amountElement.getAttribute('data-amount');
    const descriptionText = txCard.querySelector('.info-item:nth-child(3) .info-value').textContent.trim();
    const commentText = txCard.querySelector('.comment-display').textContent.trim();

    // Extract and store the original seconds from UTC date
    // utcDateString format: "YYYY-MM-DD HH:MM:SS"
    const dateTimeParts = utcDateString.split(' ');
    if (dateTimeParts.length === 2) {
        const timeParts = dateTimeParts[1].split(':');
        if (timeParts.length === 3) {
            originalTxSeconds = timeParts[2]; // Store seconds (e.g., "45")
        } else {
            originalTxSeconds = '00';
        }
    } else {
        originalTxSeconds = '00';
    }

    // Convert UTC date to datetime-local format (YYYY-MM-DDTHH:MM) in client timezone
    const localDateTime = getDateTimeLocalValue(utcDateString);

    // Get currency from card data attribute
    const currencyCode = txCard.getAttribute('data-currency') || 'JPY';

    // Convert amount from minor units to major units for editing
    // e.g., 54700 cents → 547.00 dollars
    const amountMinor = parseInt(amountText);
    const amountMajor = toMajorUnits(amountMinor, currencyCode);

    // Fill form with current values
    document.getElementById('add-tx-date').value = localDateTime;
    document.getElementById('add-tx-amount').value = amountMajor;
    document.getElementById('add-tx-description').value = descriptionText;
    document.getElementById('add-tx-comment').value = commentText === '(no comment)' ? '' : commentText;
    document.getElementById('add-tx-currency').value = currencyCode;

    modal.classList.add('active');
}

function openCategoryModalForNewTx() {
    currentTxId = '__NEW_TX__';
    currentCategorySource = 'new';
    const modal = document.getElementById('category-modal');
    const items = modal.querySelectorAll('.modal-category-item');
    const clearBtn = document.getElementById('modal-clear-btn');

    clearBtn.style.display = 'block';
    clearBtn.textContent = 'Reset to Auto-classify';

    items.forEach(item => item.classList.remove('selected'));

    const currentCategoryId = document.getElementById('add-tx-category').value;
    if (currentCategoryId) {
        const selectedItem = modal.querySelector(`[data-category-id="${currentCategoryId}"]`);
        if (selectedItem) {
            selectedItem.classList.add('selected');
            selectedItem.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
    }

    modal.classList.add('active');
}

function closeAddTransactionModal() {
    document.getElementById('add-transaction-modal').classList.remove('active');
}

function closeAddModalOnOverlay(event) {
    if (event.target.id === 'add-transaction-modal') {
        closeAddTransactionModal();
    }
}

function initAddTransactionForm() {
    const form = document.getElementById('add-transaction-form');
    if (!form) return;

    form.addEventListener('submit', function(event) {
        event.preventDefault();

        const messageDiv = document.getElementById('add-tx-message');
        const submitBtn = event.target.querySelector('button[type="submit"]');

        const dateTimeValue = document.getElementById('add-tx-date').value.trim();
        // Convert datetime-local value to ISO string for server (server expects ISO 8601 with timezone)
        // datetime-local value is in format YYYY-MM-DDTHH:MM (no seconds)
        // Preserve original seconds when editing, use :00 when adding new
        const seconds = (currentEditingTxId !== null && originalTxSeconds) ? originalTxSeconds : '00';
        const dateTimeWithSeconds = dateTimeValue + ':' + seconds;
        const dateObj = new Date(dateTimeWithSeconds);
        const isoDate = dateToServerISO(dateObj);

        const formData = {
            date: isoDate,
            amount: document.getElementById('add-tx-amount').value.trim(),
            description: document.getElementById('add-tx-description').value.trim(),
            category: document.getElementById('add-tx-category').value.trim(),
            comment: document.getElementById('add-tx-comment').value.trim(),
            currency: document.getElementById('add-tx-currency').value.trim()
        };

        if (!formData.date || !formData.amount || !formData.description) {
            messageDiv.textContent = 'Date, amount, and description are required';
            messageDiv.classList.remove('form-success');
            messageDiv.classList.add('form-error');
            return;
        }

        // Determine if we're adding or editing
        const isEditing = currentEditingTxId !== null;
        const endpoint = isEditing ? '/update-transaction' : '/add-transaction';
        const actionText = isEditing ? 'Updating' : 'Adding';
        const successText = isEditing ? 'updated' : 'added';

        // Add tx_id to formData if editing
        if (isEditing) {
            formData.tx_id = currentEditingTxId;
        }

        submitBtn.disabled = true;
        messageDiv.textContent = `${actionText} transaction...`;
        messageDiv.classList.remove('form-error');
        messageDiv.classList.add('form-success');

        fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                messageDiv.textContent = `Transaction ${successText} successfully! Reloading...`;
                setTimeout(() => window.location.reload(), 1000);
            } else {
                messageDiv.textContent = 'Error: ' + (data.error || `Failed to ${actionText.toLowerCase()} transaction`);
                messageDiv.classList.remove('form-success');
                messageDiv.classList.add('form-error');
                submitBtn.disabled = false;
            }
        })
        .catch(error => {
            console.error(`Error ${actionText.toLowerCase()} transaction:`, error);
            messageDiv.textContent = `Error: Failed to ${actionText.toLowerCase()} transaction`;
            messageDiv.classList.remove('form-success');
            messageDiv.classList.add('form-error');
            submitBtn.disabled = false;
        });
    });
}

// ========================================
// SIMILARITY INVESTIGATION
// ========================================

function investigateSimilarity(txId, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    const modal = document.getElementById('similarity-modal');
    const contentDiv = document.getElementById('similarity-modal-content');

    contentDiv.innerHTML = '<div class="loading">Loading similar transactions...</div>';
    modal.classList.add('active');

    fetch(`/api/investigate-similarity/${txId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                displaySimilarityResults(data);
            } else {
                contentDiv.innerHTML = `<div class="empty-state">${data.error || 'Failed to load similar transactions'}</div>`;
            }
        })
        .catch(error => {
            console.error('Error fetching similarity data:', error);
            contentDiv.innerHTML = '<div class="empty-state">Error loading similar transactions. Please try again.</div>';
        });
}

function displaySimilarityResults(data) {
    const contentDiv = document.getElementById('similarity-modal-content');
    const tx = data.transaction;
    const similarTxs = data.similar_transactions;
    const threshold = data.threshold;

    if (!similarTxs || similarTxs.length === 0) {
        contentDiv.innerHTML = `<div class="empty-state"><p>No similar transactions found above the threshold (${threshold}).</p></div>`;
        return;
    }

    let html = `
        <div style="background-color: var(--bg-info); padding: var(--spacing-md); border-radius: var(--radius-sm); margin-bottom: var(--spacing-lg);">
            <div style="font-weight: bold; margin-bottom: var(--spacing-xs);">Current Transaction:</div>
            <div style="color: var(--text-secondary); margin-bottom: var(--spacing-xs);"><strong>Description:</strong> ${escapeHtml(tx.description)}</div>
            <div style="color: var(--text-secondary);"><strong>Category:</strong> ${escapeHtml(tx.category_name)}</div>
        </div>
        <div style="margin-bottom: var(--spacing-md); color: var(--text-secondary); font-size: 0.875rem;">
            Found <strong>${similarTxs.length}</strong> similar transaction(s) (threshold: ${threshold}):
        </div>
        <div class="similarity-results">
    `;

    similarTxs.forEach(simTx => {
        // Convert UTC date to client timezone for display
        const localDate = formatUTCDateForDisplay(simTx.date);

        html += `
            <div class="similarity-item">
                <div class="similarity-header">
                    <div class="similarity-description">${escapeHtml(simTx.description)}</div>
                    <div class="similarity-score">${(simTx.similarity_score * 100).toFixed(1)}%</div>
                </div>
                <div class="similarity-details">
                    <div class="similarity-label">Date:</div><div>${localDate}</div>
                    <div class="similarity-label">Amount:</div><div>$${simTx.amount}</div>
                    <div class="similarity-label">Category:</div><div>${escapeHtml(simTx.category_name)}</div>
                </div>
            </div>
        `;
    });

    html += '</div>';
    contentDiv.innerHTML = html;
}

function closeSimilarityModal() {
    document.getElementById('similarity-modal').classList.remove('active');
}

function closeSimilarityModalOnOverlay(event) {
    if (event.target.id === 'similarity-modal') {
        closeSimilarityModal();
    }
}

// ========================================
// AUTOCOMPLETE FUNCTIONALITY
// ========================================

function fetchAutocompleteSuggestions() {
    fetch('/api/manual-transaction-autocomplete')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                autocompleteSuggestions = data.suggestions;
            }
        })
        .catch(error => console.error('Error fetching autocomplete suggestions:', error));
}

function showAutocompleteSuggestions(inputValue) {
    const suggestionsDiv = document.getElementById('autocomplete-suggestions');

    if (!inputValue || inputValue.length < 2) {
        suggestionsDiv.classList.remove('visible');
        return;
    }

    const filteredSuggestions = autocompleteSuggestions.filter(s =>
        s.description.toLowerCase().includes(inputValue.toLowerCase())
    );

    if (filteredSuggestions.length === 0) {
        suggestionsDiv.classList.remove('visible');
        return;
    }

    let html = '';
    filteredSuggestions.slice(0, 10).forEach(suggestion => {
        const categoryText = suggestion.category_name || 'No category';
        const amountText = suggestion.amount ? `$${suggestion.amount}` : '';

        html += `
            <div class="autocomplete-item"
                 data-description="${escapeHtml(suggestion.description)}"
                 data-amount="${suggestion.amount}"
                 data-category-id="${suggestion.category_id}"
                 data-category-name="${escapeHtml(suggestion.category_name)}"
                 onclick="selectAutocompleteSuggestion(this)">
                <div class="autocomplete-description">${escapeHtml(suggestion.description)}</div>
                <div class="autocomplete-details">
                    <span class="autocomplete-category">${escapeHtml(categoryText)}</span>
                    ${amountText ? ' • ' + amountText : ''}
                </div>
            </div>
        `;
    });

    suggestionsDiv.innerHTML = html;
    suggestionsDiv.classList.add('visible');
}

function selectAutocompleteSuggestion(element) {
    const description = element.getAttribute('data-description');
    const amount = element.getAttribute('data-amount');
    const categoryId = element.getAttribute('data-category-id');
    const categoryName = element.getAttribute('data-category-name');

    document.getElementById('add-tx-description').value = description;

    if (amount) {
        document.getElementById('add-tx-amount').value = amount;
    }

    if (categoryId) {
        document.getElementById('add-tx-category').value = categoryId;
        document.getElementById('add-tx-category-text').textContent = categoryName;
        document.getElementById('add-tx-category-btn').classList.add('modified');
    }

    document.getElementById('autocomplete-suggestions').classList.remove('visible');
}

function initAutocomplete() {
    fetchAutocompleteSuggestions();

    const descriptionInput = document.getElementById('add-tx-description');
    const suggestionsDiv = document.getElementById('autocomplete-suggestions');

    if (!descriptionInput || !suggestionsDiv) return;

    descriptionInput.addEventListener('input', function() {
        showAutocompleteSuggestions(this.value);
    });

    document.addEventListener('click', function(event) {
        if (!event.target.closest('.autocomplete-wrapper')) {
            suggestionsDiv.classList.remove('visible');
        }
    });

    descriptionInput.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            suggestionsDiv.classList.remove('visible');
        }
    });
}

// ========================================
// GROUP MANAGEMENT
// ========================================

let currentTransactionIdForGroup = null;

// Navigate to groups page filtered by specific group
function navigateToGroup(groupId) {
    window.location.href = `/groups?group_id=${groupId}`;
}

// Update bulk selection UI
function updateBulkSelectionUI() {
    const checkboxes = document.querySelectorAll('.tx-checkbox');
    const checkedBoxes = document.querySelectorAll('.tx-checkbox:checked');
    const bulkActionsBar = document.getElementById('bulk-actions-bar');
    const selectedCountEl = document.getElementById('selected-count');
    const selectAllCheckbox = document.getElementById('select-all-checkbox');

    // Defensive check: if elements don't exist (e.g., on groups page), return early
    if (!bulkActionsBar || !selectedCountEl || !selectAllCheckbox) return;

    const checkedCount = checkedBoxes.length;
    const totalCount = checkboxes.length;

    // Update selected count
    selectedCountEl.textContent = `${checkedCount} selected`;

    // Show/hide bulk actions bar
    if (checkedCount > 0) {
        bulkActionsBar.style.display = 'flex';
    } else {
        bulkActionsBar.style.display = 'none';
    }

    // Update select all checkbox state
    if (checkedCount === 0) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
    } else if (checkedCount === totalCount) {
        selectAllCheckbox.checked = true;
        selectAllCheckbox.indeterminate = false;
    } else {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = true;
    }
}

// Toggle select all
function toggleSelectAll(checked) {
    const checkboxes = document.querySelectorAll('.tx-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = checked;
    });
    updateBulkSelectionUI();
}

// Get selected transaction IDs
function getSelectedTransactionIds() {
    const checkedBoxes = document.querySelectorAll('.tx-checkbox:checked');
    return Array.from(checkedBoxes).map(cb => cb.dataset.txId);
}

// Open add group modal (individual)
function openAddGroupModal(txId) {
    currentTransactionIdForGroup = txId;
    document.getElementById('add-group-modal').style.display = 'flex';
}

// Close add group modal
function closeAddGroupModal() {
    currentTransactionIdForGroup = null;
    document.getElementById('add-group-modal').style.display = 'none';
}

// Add group to transaction (individual)
function addGroupToTransaction(groupId, groupName) {
    if (!currentTransactionIdForGroup) return;

    const txId = currentTransactionIdForGroup;

    fetch('/api/add-group-to-transaction', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            tx_id: txId,
            group_id: groupId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Add badge to UI
            const txCard = document.querySelector(`.transaction-card[data-tx-id="${txId}"]`);
            const groupsDisplay = txCard.querySelector('.groups-display');
            const addBtn = groupsDisplay.querySelector('.btn-add-group');

            const badge = document.createElement('span');
            badge.className = 'group-badge';
            badge.dataset.groupId = groupId;
            badge.dataset.txId = txId;
            badge.innerHTML = `
                ${groupName}
                <button type="button" class="group-badge-remove" onclick="removeGroupFromTransaction('${txId}', '${groupId}')" title="Remove group">×</button>
            `;

            groupsDisplay.insertBefore(badge, addBtn);

            closeAddGroupModal();
            showToast('Group added successfully', 'success');
        } else {
            showToast('Failed to add group: ' + (data.error || 'Unknown error'), 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to add group', 'error');
    });
}

// Remove group from transaction (individual)
async function removeGroupFromTransaction(txId, groupId) {
    const confirmed = await showConfirm('Remove this group from the transaction?', 'Remove Group');
    if (!confirmed) return;

    fetch('/api/remove-group-from-transaction', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            tx_id: txId,
            group_id: groupId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Remove badge from UI
            const badge = document.querySelector(`.group-badge[data-tx-id="${txId}"][data-group-id="${groupId}"]`);
            if (badge) {
                badge.remove();
            }
            showToast('Group removed successfully', 'success');
        } else {
            showToast('Failed to remove group: ' + (data.error || 'Unknown error'), 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to remove group', 'error');
    });
}

// Open bulk add group modal
function openBulkAddGroupModal() {
    const selectedIds = getSelectedTransactionIds();
    if (selectedIds.length === 0) {
        showToast('Please select at least one transaction', 'warning');
        return;
    }

    document.getElementById('bulk-add-group-modal').style.display = 'flex';
}

// Close bulk add group modal
function closeBulkAddGroupModal() {
    document.getElementById('bulk-add-group-modal').style.display = 'none';
}

// Bulk add group
function bulkAddGroup(groupId, groupName) {
    const selectedIds = getSelectedTransactionIds();

    if (selectedIds.length === 0) {
        showToast('Please select at least one transaction', 'warning');
        return;
    }

    fetch('/api/bulk-add-group', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            tx_ids: selectedIds,
            group_id: groupId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(`Added group "${groupName}" to ${data.count} transaction(s)`, 'success');
            // Reload page to reflect changes
            window.location.reload();
        } else {
            showToast('Failed to add group: ' + (data.error || 'Unknown error'), 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to add group', 'error');
    });
}

// Open bulk remove group modal
function openBulkRemoveGroupModal() {
    const selectedIds = getSelectedTransactionIds();
    if (selectedIds.length === 0) {
        showToast('Please select at least one transaction', 'warning');
        return;
    }

    document.getElementById('bulk-remove-group-modal').style.display = 'flex';
}

// Close bulk remove group modal
function closeBulkRemoveGroupModal() {
    document.getElementById('bulk-remove-group-modal').style.display = 'none';
}

// Bulk remove group
async function bulkRemoveGroup(groupId, groupName) {
    const selectedIds = getSelectedTransactionIds();

    if (selectedIds.length === 0) {
        showToast('Please select at least one transaction', 'warning');
        return;
    }

    const confirmed = await showConfirm(`Remove group "${groupName}" from ${selectedIds.length} transaction(s)?`, 'Remove Group');
    if (!confirmed) {
        return;
    }

    fetch('/api/bulk-remove-group', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            tx_ids: selectedIds,
            group_id: groupId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(`Removed group "${groupName}" from ${data.count} transaction(s)`, 'success');
            // Reload page to reflect changes
            window.location.reload();
        } else {
            showToast('Failed to remove group: ' + (data.error || 'Unknown error'), 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to remove group', 'error');
    });
}

// ========================================
// PAGE INITIALIZATION
// ========================================

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', function() {
    captureURLParams();
    initLiveSearch();
    initAddTransactionForm();
    initAutocomplete();
    updateBulkSelectionUI();
});
