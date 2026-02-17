/**
 * Settings page JavaScript
 * Handles saving user preferences
 */

async function saveSettings() {
    const languageSelect = document.getElementById('language');
    const currencySelect = document.getElementById('currency');

    const payload = {
        language: languageSelect.value,  // Entity field name
        currency: currencySelect.value   // Entity field name
    };

    try {
        const response = await fetch('/api/update-settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.success) {
            showToast('Settings saved successfully', 'success');
            // Reset form changed flag
            formChanged = false;
        } else {
            showToast('Error: ' + data.error, 'error');
        }
    } catch (error) {
        showToast('Network error: ' + error.message, 'error');
    }
}

// Track form changes to warn user about unsaved changes
let formChanged = false;

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('settings-form');
    const inputs = form.querySelectorAll('select');

    inputs.forEach(input => {
        input.addEventListener('change', () => {
            formChanged = true;
        });
    });

    // Warn on navigation if changes made
    window.addEventListener('beforeunload', (e) => {
        if (formChanged) {
            e.preventDefault();
            e.returnValue = '';
        }
    });
});
