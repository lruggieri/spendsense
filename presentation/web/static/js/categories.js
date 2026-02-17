let editMode = false;
let editingCategoryId = null;

// Wizard mode callback - set by onboarding-wizard.js
let categorySaveCallback = null;

function openCreateModal() {
    editMode = false;
    editingCategoryId = null;

    document.getElementById('modal-title').textContent = 'Create Category';
    document.getElementById('edit-mode').value = 'false';
    document.getElementById('category-id').value = '';
    document.getElementById('category-id-display').style.display = 'none';
    document.getElementById('category-name').value = '';
    document.getElementById('category-description').value = '';
    document.getElementById('category-parent').value = '';

    // Enable all parent options
    const options = document.getElementById('category-parent').options;
    for (let option of options) {
        option.disabled = false;
    }

    document.getElementById('category-modal').style.display = 'flex';
}

function openEditModal(id, name, description, parentId) {
    editMode = true;
    editingCategoryId = id;

    document.getElementById('modal-title').textContent = 'Edit Category';
    document.getElementById('edit-mode').value = 'true';
    document.getElementById('category-id').value = id;
    document.getElementById('category-id-display').style.display = 'block';
    document.getElementById('category-id-readonly').value = id;
    document.getElementById('category-name').value = name;
    document.getElementById('category-description').value = description;
    document.getElementById('category-parent').value = parentId;

    // Disable self-selection in parent dropdown
    const options = document.getElementById('category-parent').options;
    for (let option of options) {
        option.disabled = (option.value === id);
    }

    document.getElementById('category-modal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('category-modal').style.display = 'none';
}

function closeModalOnOverlay(event) {
    if (event.target.classList.contains('modal-overlay')) {
        closeModal();
    }
}

/**
 * Save category with optional callback support for wizard mode
 * @param {Object} options - Optional configuration
 * @param {string} options.context - 'modal' (default) or 'wizard'
 */
async function saveCategory(options = {}) {
    const context = options.context || 'modal';

    const isEdit = document.getElementById('edit-mode').value === 'true';
    const name = document.getElementById('category-name').value.trim();
    const description = document.getElementById('category-description').value.trim();
    const parentId = document.getElementById('category-parent').value;

    if (!name) {
        showToast('Category Name is required', 'error');
        return;
    }

    const endpoint = isEdit ? '/api/update-category' : '/api/create-category';
    const payload = {
        name: name,
        description: description,
        parent_id: parentId
    };

    // Only include category_id for edit mode
    if (isEdit) {
        const categoryId = document.getElementById('category-id').value.trim();
        payload.category_id = categoryId;
    }

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.success) {
            showToast(`Category ${isEdit ? 'updated' : 'created'} successfully`, 'success');

            // In wizard context, call callback instead of reloading
            if (context === 'wizard' && categorySaveCallback) {
                categorySaveCallback(data);
                resetCategoryForm();
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
 * Reset the category form (used in wizard mode)
 */
function resetCategoryForm() {
    document.getElementById('edit-mode').value = 'false';
    document.getElementById('category-id').value = '';
    document.getElementById('category-name').value = '';
    document.getElementById('category-description').value = '';
    document.getElementById('category-parent').value = '';

    const idDisplay = document.getElementById('category-id-display');
    if (idDisplay) {
        idDisplay.style.display = 'none';
    }
}

/**
 * Set callback for wizard mode
 * @param {Function} callback - Function to call after save
 */
function setCategorySaveCallback(callback) {
    categorySaveCallback = callback;
}

async function deleteCategory(id, name) {
    const confirmed = await showConfirm(
        `Are you sure you want to delete "${name}"? This cannot be undone.`,
        'Delete Category'
    );

    if (!confirmed) return;

    try {
        const response = await fetch('/api/delete-category', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category_id: id })
        });

        const data = await response.json();

        if (data.success) {
            showToast('Category deleted successfully', 'success');
            setTimeout(() => window.location.reload(), 500);
        } else {
            showToast('Cannot delete: ' + data.error, 'error');
        }
    } catch (error) {
        showToast('Network error: ' + error.message, 'error');
    }
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
    }
});
