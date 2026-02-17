/**
 * Onboarding Wizard Orchestration
 *
 * Manages item lists, form state, and "Add Another" functionality
 * for the embedded onboarding wizard.
 */

// Track created items for each step
let createdFetchers = [];
let createdCategories = [];
let createdPatterns = [];

/**
 * Initialize wizard step based on current step number
 * @param {number} stepNum - Current step number (1, 2, or 3)
 * @param {Object} initialData - Initial data for the step (e.g., existing items)
 */
function initWizardStep(stepNum, initialData = {}) {
    switch (stepNum) {
        case 1:
            initFetcherStep(initialData);
            break;
        case 2:
            initCategoryStep(initialData);
            break;
        case 3:
            initPatternStep(initialData);
            break;
    }
}

/* ===== STEP 1: FETCHERS ===== */

/**
 * Initialize fetcher step
 */
function initFetcherStep(initialData) {
    // Initialize fetcher form in wizard mode
    if (typeof initFetchers === 'function') {
        initFetchers('wizard');
    }

    // Set up save callback
    if (typeof setFetcherSaveCallback === 'function') {
        setFetcherSaveCallback(handleFetcherSaved);
    }

    // Load existing fetchers
    if (initialData.fetchers) {
        createdFetchers = initialData.fetchers;
        renderFetcherList();
    }

    updateContinueButton();
}

/**
 * Handle fetcher save callback
 */
function handleFetcherSaved(data) {
    // Add to list
    createdFetchers.push({
        id: data.fetcher_id,
        name: document.getElementById('fetcher-name').value.trim()
    });

    // Re-render list
    renderFetcherList();

    // Update continue button
    updateContinueButton();

    // Show "Add Another" section
    showAddAnotherButton('fetcher');
}

/**
 * Render the fetcher item list
 */
function renderFetcherList() {
    const list = document.getElementById('fetcher-item-list');
    if (!list) return;

    const count = createdFetchers.length;
    const countEl = document.getElementById('fetcher-count');
    if (countEl) {
        countEl.textContent = count;
    }

    if (count === 0) {
        list.innerHTML = '<div class="item-list__empty">No fetchers created yet</div>';
        return;
    }

    list.innerHTML = createdFetchers.map(f => `
        <div class="item-list__item">
            <span class="item-list__name">${escapeHtml(f.name)}</span>
        </div>
    `).join('');
}

/* ===== STEP 2: CATEGORIES ===== */

/**
 * Initialize category step
 */
function initCategoryStep(initialData) {
    // Set up save callback
    if (typeof setCategorySaveCallback === 'function') {
        setCategorySaveCallback(handleCategorySaved);
    }

    // Load existing categories
    if (initialData.categories) {
        createdCategories = initialData.categories;
        renderCategoryList();
    }

    updateContinueButton();
}

/**
 * Handle category save callback
 */
function handleCategorySaved(data) {
    // Add to list
    createdCategories.push({
        id: data.category_id,
        name: document.getElementById('category-name').value.trim()
    });

    // Re-render list
    renderCategoryList();

    // Update continue button
    updateContinueButton();

    // Update category dropdown for pattern step (if available)
    updateCategoryDropdowns();

    // Show "Add Another" section
    showAddAnotherButton('category');
}

/**
 * Render the category item list
 */
function renderCategoryList() {
    const list = document.getElementById('category-item-list');
    if (!list) return;

    const count = createdCategories.length;
    const countEl = document.getElementById('category-count');
    if (countEl) {
        countEl.textContent = count;
    }

    if (count === 0) {
        list.innerHTML = '<div class="item-list__empty">No categories created yet</div>';
        return;
    }

    list.innerHTML = createdCategories.map(c => `
        <div class="item-list__item">
            <span class="item-list__name">${escapeHtml(c.name)}</span>
        </div>
    `).join('');
}

/**
 * Update category dropdowns after adding a new category
 */
function updateCategoryDropdowns() {
    // This will be called to refresh the category dropdowns
    // when on the patterns step (step 3) if user goes back and adds more categories
    // For now, we handle this by reloading the page data
}

/* ===== STEP 3: PATTERNS ===== */

/**
 * Initialize pattern step
 */
function initPatternStep(initialData) {
    // Initialize pattern form for wizard
    
    if (typeof initPatternFormForWizard === 'function') {
        initPatternFormForWizard();
    }

    // Set up save callback
    if (typeof setPatternSaveCallback === 'function') {
        setPatternSaveCallback(handlePatternSaved);
    }

    // Load existing patterns
    if (initialData.patterns) {
        createdPatterns = initialData.patterns;
        renderPatternList();
    }

    updateContinueButton();
}

/**
 * Handle pattern save callback
 */
function handlePatternSaved(data) {
    // Get category name from dropdown
    const categorySelect = document.getElementById('pattern-category');
    const categoryName = categorySelect.options[categorySelect.selectedIndex]?.text || 'Unknown';

    // Add to list
    createdPatterns.push({
        id: data.pattern_id,
        name: document.getElementById('pattern-name').value.trim(),
        category_name: categoryName.trim()
    });

    // Re-render list
    renderPatternList();

    // Update continue button
    updateContinueButton();

    // Show "Add Another" section
    showAddAnotherButton('pattern');
}

/**
 * Render the pattern item list
 */
function renderPatternList() {
    const list = document.getElementById('pattern-item-list');
    if (!list) return;

    const count = createdPatterns.length;
    const countEl = document.getElementById('pattern-count');
    if (countEl) {
        countEl.textContent = count;
    }

    if (count === 0) {
        list.innerHTML = '<div class="item-list__empty">No patterns created yet</div>';
        return;
    }

    list.innerHTML = createdPatterns.map(p => `
        <div class="item-list__item">
            <span class="item-list__name">${escapeHtml(p.name)}</span>
            <span class="item-list__meta">${escapeHtml(p.category_name)}</span>
        </div>
    `).join('');
}

/* ===== COMMON FUNCTIONS ===== */

/**
 * Update continue button state based on created items
 */
function updateContinueButton() {
    const continueBtn = document.getElementById('continue-btn');
    if (!continueBtn) return;

    // Determine current step from URL
    const pathParts = window.location.pathname.split('/');
    const stepNum = parseInt(pathParts[pathParts.length - 1]) || 1;

    let canContinue = false;

    switch (stepNum) {
        case 1:
            canContinue = createdFetchers.length > 0;
            break;
        case 2:
            canContinue = createdCategories.length > 0;
            break;
        case 3:
            canContinue = createdPatterns.length > 0;
            break;
    }

    continueBtn.disabled = !canContinue;
}

/**
 * Show the "Add Another" button after successful save
 * @param {string} itemType - Type of item (fetcher, category, pattern)
 */
function showAddAnotherButton(itemType) {
    const addAnotherBtn = document.getElementById(`add-another-${itemType}-btn`);
    if (addAnotherBtn) {
        addAnotherBtn.classList.remove('hidden');
    }

    // Collapse the form to show user they can add another
    const formContainer = document.getElementById(`${itemType}-form-container`);
    if (formContainer) {
        formContainer.classList.add('collapsed');
    }
}

/**
 * Show the form again when "Add Another" is clicked
 * @param {string} itemType - Type of item (fetcher, category, pattern)
 */
function showFormForAnotherItem(itemType) {
    const formContainer = document.getElementById(`${itemType}-form-container`);
    if (formContainer) {
        formContainer.classList.remove('collapsed');
    }

    // Hide the add another button
    const addAnotherBtn = document.getElementById(`add-another-${itemType}-btn`);
    if (addAnotherBtn) {
        addAnotherBtn.classList.add('hidden');
    }

    // Reset form based on type
    switch (itemType) {
        case 'fetcher':
            if (typeof resetFetcherForm === 'function') {
                resetFetcherForm();
            }
            break;
        case 'category':
            if (typeof resetCategoryForm === 'function') {
                resetCategoryForm();
            }
            break;
        case 'pattern':
            if (typeof resetPatternForm === 'function') {
                resetPatternForm();
            }
            break;
    }

    // Scroll form into view
    formContainer?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Escape HTML for safe display
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Export functions for global use
window.initWizardStep = initWizardStep;
window.showFormForAnotherItem = showFormForAnotherItem;
window.updateContinueButton = updateContinueButton;
