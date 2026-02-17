// ========================================
// GROUP MANAGEMENT FUNCTIONS
// ========================================

// ========================================
// MODAL MANAGEMENT
// ========================================

function closeModalOnOverlay(event, modalId) {
    if (event.target.classList.contains('modal-overlay')) {
        document.getElementById(modalId).style.display = 'none';
    }
}

// ========================================
// CREATE GROUP
// ========================================

function openCreateGroupModal() {
    document.getElementById('create-group-modal').style.display = 'flex';
    document.getElementById('create-group-name').value = '';
    document.getElementById('create-group-message').textContent = '';
    document.getElementById('create-group-name').focus();
}

function closeCreateGroupModal() {
    document.getElementById('create-group-modal').style.display = 'none';
}

function createGroup(event) {
    event.preventDefault();

    const name = document.getElementById('create-group-name').value.trim();
    const messageEl = document.getElementById('create-group-message');

    if (!name) {
        messageEl.textContent = 'Group name is required';
        messageEl.style.color = 'var(--danger)';
        return;
    }

    fetch('/api/create-group', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: name })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Reload page to show new group
            window.location.reload();
        } else {
            messageEl.textContent = 'Error: ' + (data.error || 'Failed to create group');
            messageEl.style.color = 'var(--danger)';
        }
    })
    .catch(error => {
        console.error('Error:', error);
        messageEl.textContent = 'Error creating group';
        messageEl.style.color = 'var(--danger)';
    });
}

// ========================================
// EDIT GROUP
// ========================================

function openEditGroupModal(groupId, currentName) {
    document.getElementById('edit-group-modal').style.display = 'flex';
    document.getElementById('edit-group-id').value = groupId;
    document.getElementById('edit-group-name').value = currentName;
    document.getElementById('edit-group-message').textContent = '';
    document.getElementById('edit-group-name').focus();
}

function closeEditGroupModal() {
    document.getElementById('edit-group-modal').style.display = 'none';
}

function updateGroup(event) {
    event.preventDefault();

    const groupId = document.getElementById('edit-group-id').value;
    const name = document.getElementById('edit-group-name').value.trim();
    const messageEl = document.getElementById('edit-group-message');

    if (!name) {
        messageEl.textContent = 'Group name is required';
        messageEl.style.color = 'var(--danger)';
        return;
    }

    fetch('/api/update-group', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            group_id: groupId,
            name: name
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Reload page to show updated group
            window.location.reload();
        } else {
            messageEl.textContent = 'Error: ' + (data.error || 'Failed to update group');
            messageEl.style.color = 'var(--danger)';
        }
    })
    .catch(error => {
        console.error('Error:', error);
        messageEl.textContent = 'Error updating group';
        messageEl.style.color = 'var(--danger)';
    });
}

// ========================================
// DELETE GROUP
// ========================================

function openDeleteGroupModal(groupId, groupName, transactionCount) {
    document.getElementById('delete-group-modal').style.display = 'flex';
    document.getElementById('delete-group-id').value = groupId;
    document.getElementById('delete-group-name-display').textContent = groupName;

    const warningEl = document.getElementById('delete-group-warning');
    if (transactionCount > 0) {
        warningEl.textContent = `This group is assigned to ${transactionCount} transaction(s). The group will be removed from all these transactions.`;
    } else {
        warningEl.textContent = 'This group has no transactions.';
    }
}

function closeDeleteGroupModal() {
    document.getElementById('delete-group-modal').style.display = 'none';
}

function confirmDeleteGroup() {
    const groupId = document.getElementById('delete-group-id').value;

    fetch('/api/delete-group', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ group_id: groupId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Reload page to reflect deletion
            window.location.href = '/groups';
        } else {
            showToast('Error: ' + (data.error || 'Failed to delete group'), 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Error deleting group', 'error');
    });
}

// ========================================
// VIEW TRANSACTIONS
// ========================================

function viewGroupTransactions(groupId) {
    window.location.href = `/groups?group_id=${groupId}`;
}

// ========================================
// PAGE INITIALIZATION
// ========================================

// Note: All transaction modification functionality (category selection, edit modal,
// similarity investigation, etc.) is provided by review.js which is already included
// in groups.html. The functions work automatically since we use the same element IDs
// and HTML structure as the review page.

document.addEventListener('DOMContentLoaded', function() {
    // Initialize functions from review.js if we're viewing transactions
    if (document.getElementById('bulk-assign-form')) {
        // captureURLParams() is called in review.js DOMContentLoaded
        // initLiveSearch() is called in review.js DOMContentLoaded
        // initAddTransactionForm() is called in review.js DOMContentLoaded
        // initAutocomplete() is called in review.js DOMContentLoaded
        // All these functions are automatically initialized by review.js
        console.log('Groups page loaded with transaction editing capabilities');
    } else {
        console.log('Groups page loaded');
    }
});
