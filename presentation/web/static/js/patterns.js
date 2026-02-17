// State management
let editMode = false;
let editingPatternId = null;
let rules = [];
let currentPatterns = {}; // Store pattern data for editing

// Wizard mode callback - set by onboarding-wizard.js
let patternSaveCallback = null;

// Initialize drag-and-drop on page load
document.addEventListener('DOMContentLoaded', () => {
    initDragAndDrop();
    loadPatternData();
});

// Load pattern data from the DOM for editing
function loadPatternData() {
    const rows = document.querySelectorAll('#patterns-tbody tr');
    rows.forEach(row => {
        const id = row.dataset.patternId;
        if (id) {
            currentPatterns[id] = {
                id: id,
                order: row.dataset.order
            };
        }
    });
}

// Modal functions
function openCreateModal() {
    editMode = false;
    editingPatternId = null;
    rules = [];

    document.getElementById('modal-title').textContent = 'Create Pattern';
    document.getElementById('edit-mode').value = 'false';
    document.getElementById('pattern-id').value = '';
    document.getElementById('pattern-name').value = '';
    document.getElementById('pattern-category').value = '';
    document.getElementById('rules-container').innerHTML = '';
    document.getElementById('preview-description').textContent = 'No rules added yet';

    // Add one default OR rule
    addRuleRow('OR', '');

    document.getElementById('pattern-modal').style.display = 'flex';
}

async function openEditModal(patternId) {
    editMode = true;
    editingPatternId = patternId;

    document.getElementById('modal-title').textContent = 'Edit Pattern';
    document.getElementById('edit-mode').value = 'true';
    document.getElementById('pattern-id').value = patternId;

    // Fetch pattern data from server
    try {
        const row = document.querySelector(`tr[data-pattern-id="${patternId}"]`);
        const response = await fetch(`/api/get-pattern/${patternId}`);

        if (!response.ok) {
            // Fallback: try to reconstruct from DOM (won't work for full edit, but better than nothing)
            showToast('Unable to load pattern details for editing', 'error');
            closeModal();
            return;
        }

        const data = await response.json();

        if (data.success) {
            document.getElementById('pattern-name').value = data.pattern.name;
            document.getElementById('pattern-category').value = data.pattern.category_id;

            // Load rules
            rules = data.pattern.rules;
            renderRules();
            updatePreview();
        } else {
            showToast('Error loading pattern: ' + data.error, 'error');
            closeModal();
            return;
        }
    } catch (error) {
        showToast('Network error: ' + error.message, 'error');
        closeModal();
        return;
    }

    document.getElementById('pattern-modal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('pattern-modal').style.display = 'none';
}

function closeModalOnOverlay(event) {
    if (event.target.classList.contains('modal-overlay')) {
        closeModal();
    }
}

// Rule builder functions
function addRuleRow(operator = 'OR', keyword = '') {
    const rulesContainer = document.getElementById('rules-container');
    const index = rules.length;

    rules.push({ operator: operator, keyword: keyword });

    const ruleDiv = document.createElement('div');
    ruleDiv.className = 'rule-row';
    ruleDiv.dataset.index = index;

    ruleDiv.innerHTML = `
        <select class="rule-operator form-select" onchange="updateRuleOperator(${index}, this.value)">
            <option value="START_WITH" ${operator === 'START_WITH' ? 'selected' : ''}>Starts with</option>
            <option value="END_WITH" ${operator === 'END_WITH' ? 'selected' : ''}>Ends with</option>
            <option value="NOT_START_WITH" ${operator === 'NOT_START_WITH' ? 'selected' : ''}>Not starts with</option>
            <option value="OR" ${operator === 'OR' ? 'selected' : ''}>Contains (OR)</option>
            <option value="AND" ${operator === 'AND' ? 'selected' : ''}>Must contain (AND)</option>
            <option value="NOT" ${operator === 'NOT' ? 'selected' : ''}>Must not contain (NOT)</option>
        </select>
        <input type="text" class="rule-keyword form-input" placeholder="keyword"
               value="${keyword}" oninput="updateRuleKeyword(${index}, this.value)" maxlength="100">
        <button type="button" class="btn-icon" onclick="removeRuleRow(${index})" title="Remove rule">&times;</button>
    `;

    rulesContainer.appendChild(ruleDiv);
    updatePreview();
}

function removeRuleRow(index) {
    rules.splice(index, 1);
    renderRules();
    updatePreview();
}

function updateRuleOperator(index, operator) {
    if (rules[index]) {
        rules[index].operator = operator;
        updatePreview();
    }
}

function updateRuleKeyword(index, keyword) {
    if (rules[index]) {
        rules[index].keyword = keyword;
        updatePreview();
    }
}

function renderRules() {
    const rulesContainer = document.getElementById('rules-container');
    rulesContainer.innerHTML = '';

    rules.forEach((rule, index) => {
        const ruleDiv = document.createElement('div');
        ruleDiv.className = 'rule-row';
        ruleDiv.dataset.index = index;

        ruleDiv.innerHTML = `
            <select class="rule-operator form-select" onchange="updateRuleOperator(${index}, this.value)">
                <option value="START_WITH" ${rule.operator === 'START_WITH' ? 'selected' : ''}>Starts with</option>
                <option value="END_WITH" ${rule.operator === 'END_WITH' ? 'selected' : ''}>Ends with</option>
                <option value="NOT_START_WITH" ${rule.operator === 'NOT_START_WITH' ? 'selected' : ''}>Not starts with</option>
                <option value="OR" ${rule.operator === 'OR' ? 'selected' : ''}>Contains (OR)</option>
                <option value="AND" ${rule.operator === 'AND' ? 'selected' : ''}>Must contain (AND)</option>
                <option value="NOT" ${rule.operator === 'NOT' ? 'selected' : ''}>Must not contain (NOT)</option>
            </select>
            <input type="text" class="rule-keyword form-input" placeholder="keyword"
                   value="${rule.keyword}" oninput="updateRuleKeyword(${index}, this.value)" maxlength="100">
            <button type="button" class="btn-icon" onclick="removeRuleRow(${index})" title="Remove rule">&times;</button>
        `;

        rulesContainer.appendChild(ruleDiv);
    });
}

function updatePreview() {
    const previewBox = document.getElementById('preview-description');

    // Filter out empty keywords
    const validRules = rules.filter(r => r.keyword.trim() !== '');

    if (validRules.length === 0) {
        previewBox.textContent = 'No rules added yet';
        return;
    }

    // Generate human-readable description
    const parts = [];
    const notStartWith = validRules.filter(r => r.operator === 'NOT_START_WITH').map(r => r.keyword);
    const startWith = validRules.filter(r => r.operator === 'START_WITH').map(r => r.keyword);
    const orKeywords = validRules.filter(r => r.operator === 'OR').map(r => r.keyword);
    const andKeywords = validRules.filter(r => r.operator === 'AND').map(r => r.keyword);
    const notKeywords = validRules.filter(r => r.operator === 'NOT').map(r => r.keyword);
    const endWith = validRules.filter(r => r.operator === 'END_WITH').map(r => r.keyword);

    if (notStartWith.length > 0) {
        parts.push(`Not starts with ${notStartWith.join(' or ')}`);
    }

    if (startWith.length > 0) {
        parts.push(`Starts with ${startWith.join(' or ')}`);
    }

    if (orKeywords.length > 0) {
        parts.push(`Contains ${orKeywords.join(' OR ')}`);
    }

    if (andKeywords.length > 0) {
        parts.push(`Must contain ${andKeywords.join(' AND ')}`);
    }

    if (notKeywords.length > 0) {
        parts.push(`Must NOT contain ${notKeywords.join(' or ')}`);
    }

    if (endWith.length > 0) {
        parts.push(`Ends with ${endWith.join(' or ')}`);
    }

    previewBox.textContent = parts.join(', ');
}

function validateRules() {
    // Filter out empty keywords
    const validRules = rules.filter(r => r.keyword.trim() !== '');

    if (validRules.length === 0) {
        return { valid: false, error: 'At least one rule is required' };
    }

    // Check for positive rules (OR, AND, START_WITH, or END_WITH)
    const hasPositive = validRules.some(r =>
        r.operator === 'OR' || r.operator === 'AND' ||
        r.operator === 'START_WITH' || r.operator === 'END_WITH'
    );

    if (!hasPositive) {
        return { valid: false, error: 'Pattern must have at least one positive rule (OR, AND, START_WITH, or END_WITH)' };
    }

    // Check keyword length
    for (const rule of validRules) {
        if (rule.keyword.length > 100) {
            return { valid: false, error: 'Keywords must be under 100 characters' };
        }
    }

    // Check max rules
    if (validRules.length > 20) {
        return { valid: false, error: 'Maximum 20 rules per pattern' };
    }

    return { valid: true, error: '' };
}

// CRUD operations
/**
 * Save pattern with optional callback support for wizard mode
 * @param {Object} options - Optional configuration
 * @param {string} options.context - 'modal' (default) or 'wizard'
 */
async function savePattern(options = {}) {
    const context = options.context || 'modal';

    const isEdit = document.getElementById('edit-mode').value === 'true';
    const name = document.getElementById('pattern-name').value.trim();
    const categoryId = document.getElementById('pattern-category').value.trim();

    if (!name) {
        showToast('Pattern name is required', 'error');
        return;
    }

    if (!categoryId) {
        showToast('Target category is required', 'error');
        return;
    }

    // Validate rules
    const validation = validateRules();
    if (!validation.valid) {
        showToast(validation.error, 'error');
        return;
    }

    // Filter out empty keywords
    const validRules = rules.filter(r => r.keyword.trim() !== '');

    const endpoint = isEdit ? '/api/update-pattern' : '/api/create-pattern';
    const payload = {
        rules: validRules,
        category_id: categoryId,
        name: name
    };

    if (isEdit) {
        payload.pattern_id = document.getElementById('pattern-id').value.trim();
    }

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.success) {
            showToast(`Pattern ${isEdit ? 'updated' : 'created'} successfully`, 'success');

            // In wizard context, call callback instead of reloading
            if (context === 'wizard' && patternSaveCallback) {
                patternSaveCallback(data);
                resetPatternForm();
            } else {
                closeModal();
                setTimeout(() => window.location.reload(), 500);
            }
        } else {
            showToast('Error: ' + data.error, 'error');
        }
    } catch (error) {
        showToast('Network error: ' + error.message, 'error');
    }
}

/**
 * Reset the pattern form (used in wizard mode)
 */
function resetPatternForm() {
    document.getElementById('edit-mode').value = 'false';
    document.getElementById('pattern-id').value = '';
    document.getElementById('pattern-name').value = '';
    document.getElementById('pattern-category').value = '';

    // Clear rules
    rules = [];
    const rulesContainer = document.getElementById('rules-container');
    if (rulesContainer) {
        rulesContainer.innerHTML = '';
    }

    // Reset preview
    const previewBox = document.getElementById('preview-description');
    if (previewBox) {
        previewBox.textContent = 'No rules added yet';
    }

    // Add one default rule
    addRuleRow('OR', '');
}

/**
 * Set callback for wizard mode
 * @param {Function} callback - Function to call after save
 */
function setPatternSaveCallback(callback) {
    patternSaveCallback = callback;
}

/**
 * Initialize pattern form for wizard mode
 */
function initPatternFormForWizard() {
    rules = [];
    addRuleRow('OR', '');
}

async function deletePattern(id, name) {
    const confirmed = await showConfirm(
        `Are you sure you want to delete "${name}"? This cannot be undone.`,
        'Delete Pattern'
    );

    if (!confirmed) return;

    try {
        const response = await fetch('/api/delete-pattern', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pattern_id: id })
        });

        const data = await response.json();

        if (data.success) {
            showToast('Pattern deleted successfully', 'success');
            setTimeout(() => window.location.reload(), 500);
        } else {
            showToast('Cannot delete: ' + data.error, 'error');
        }
    } catch (error) {
        showToast('Network error: ' + error.message, 'error');
    }
}

// Drag-and-drop functionality
let draggedElement = null;

function initDragAndDrop() {
    const tbody = document.getElementById('patterns-tbody');
    const rows = tbody.querySelectorAll('tr[draggable="true"]');

    rows.forEach(row => {
        row.addEventListener('dragstart', handleDragStart);
        row.addEventListener('dragover', handleDragOver);
        row.addEventListener('drop', handleDrop);
        row.addEventListener('dragend', handleDragEnd);
        row.addEventListener('dragenter', handleDragEnter);
        row.addEventListener('dragleave', handleDragLeave);
    });
}

function handleDragStart(e) {
    draggedElement = this;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', this.innerHTML);
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    return false;
}

function handleDragEnter(e) {
    if (this !== draggedElement) {
        this.classList.add('drag-over');
    }
}

function handleDragLeave(e) {
    this.classList.remove('drag-over');
}

function handleDrop(e) {
    e.stopPropagation();
    e.preventDefault();

    if (draggedElement !== this) {
        const tbody = document.getElementById('patterns-tbody');
        const allRows = Array.from(tbody.querySelectorAll('tr'));
        const draggedIndex = allRows.indexOf(draggedElement);
        const targetIndex = allRows.indexOf(this);

        if (draggedIndex < targetIndex) {
            tbody.insertBefore(draggedElement, this.nextSibling);
        } else {
            tbody.insertBefore(draggedElement, this);
        }

        // Save new order
        saveOrder();
    }

    this.classList.remove('drag-over');
    return false;
}

function handleDragEnd(e) {
    this.classList.remove('dragging');

    // Remove drag-over class from all rows
    const rows = document.querySelectorAll('#patterns-tbody tr');
    rows.forEach(row => row.classList.remove('drag-over'));
}

async function saveOrder() {
    const rows = document.querySelectorAll('#patterns-tbody tr');
    const orderMap = {};

    rows.forEach((row, index) => {
        const patternId = row.dataset.patternId;
        if (patternId) {
            orderMap[patternId] = index;
        }
    });

    try {
        const response = await fetch('/api/reorder-patterns', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order_map: orderMap })
        });

        const data = await response.json();

        if (data.success) {
            showToast('Pattern order updated', 'success');
        } else {
            showToast('Error updating order: ' + data.error, 'error');
            // Reload to restore correct order
            setTimeout(() => window.location.reload(), 1000);
        }
    } catch (error) {
        showToast('Network error: ' + error.message, 'error');
        setTimeout(() => window.location.reload(), 1000);
    }
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
    }
});
