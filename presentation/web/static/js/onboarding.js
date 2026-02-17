/**
 * Onboarding Wizard JavaScript
 *
 * Handles navigation between steps and banner dismissal.
 */

let currentStep = 1;
let totalSteps = 3;

/**
 * Initialize the onboarding wizard
 * @param {number} stepNum - Current step number
 * @param {number} total - Total number of steps
 */
function initOnboarding(stepNum, total) {
    currentStep = stepNum;
    totalSteps = total;

    // Set up event listeners
    const continueBtn = document.getElementById('continue-btn');
    const backBtn = document.getElementById('back-btn');

    if (continueBtn) {
        continueBtn.addEventListener('click', handleContinue);
    }

    if (backBtn) {
        backBtn.addEventListener('click', handleBack);
    }
}

/**
 * Handle continue button click
 */
async function handleContinue() {
    const continueBtn = document.getElementById('continue-btn');

    if (continueBtn.disabled) {
        return;
    }

    // Disable button and show loading state
    continueBtn.disabled = true;
    const originalText = continueBtn.textContent;
    continueBtn.innerHTML = '<span class="btn-spinner"></span> ' + originalText;

    try {
        const response = await fetch('/api/onboarding/advance', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                current_step: currentStep
            })
        });

        const data = await response.json();

        if (data.success) {
            // Redirect to next step or completion page
            window.location.href = data.redirect_url;
        } else {
            showToast(data.error || 'Failed to advance', 'error');
            continueBtn.disabled = false;
            continueBtn.textContent = originalText;
        }
    } catch (error) {
        console.error('Error advancing onboarding:', error);
        showToast('Network error. Please try again.', 'error');
        continueBtn.disabled = false;
        continueBtn.textContent = originalText;
    }
}

/**
 * Handle back button click
 */
function handleBack() {
    if (currentStep > 1) {
        window.location.href = `/onboarding/step/${currentStep - 1}`;
    }
}

/**
 * Dismiss the onboarding reminder banner
 */
async function dismissOnboardingBanner() {
    try {
        const response = await fetch('/api/onboarding/dismiss-banner', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success) {
            const banner = document.getElementById('onboarding-banner');
            if (banner) {
                banner.style.opacity = '0';
                banner.style.transform = 'translateY(-100%)';
                setTimeout(() => {
                    banner.remove();
                }, 300);
            }
        }
    } catch (error) {
        console.error('Error dismissing banner:', error);
    }
}

/**
 * Refresh the current step to check for updated counts
 * Called when returning from creating items
 */
async function refreshOnboardingStatus() {
    try {
        const response = await fetch('/api/onboarding/status');
        const data = await response.json();

        if (data.success) {
            // Update continue button state based on counts
            const continueBtn = document.getElementById('continue-btn');
            const stepKey = getStepKey(currentStep);

            if (continueBtn && data.counts[stepKey] > 0) {
                continueBtn.disabled = false;
            }

            // Update status badge if it exists
            updateStatusBadge(data.counts[stepKey]);
        }
    } catch (error) {
        console.error('Error refreshing status:', error);
    }
}

/**
 * Get the step key for a given step number
 * @param {number} stepNum - Step number (1-3)
 * @returns {string} Step key (fetchers, categories, patterns)
 */
function getStepKey(stepNum) {
    const keys = ['fetchers', 'categories', 'patterns'];
    return keys[stepNum - 1] || 'fetchers';
}

/**
 * Update the status badge with new count
 * @param {number} count - New count to display
 */
function updateStatusBadge(count) {
    const badge = document.querySelector('.status-badge');
    if (!badge) return;

    if (count > 0) {
        badge.classList.remove('status-badge--pending');
        badge.classList.add('status-badge--success');
        badge.innerHTML = `
            <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
            </svg>
            ${count} item(s) configured
        `;
    }
}

// Check for returning from item creation
document.addEventListener('DOMContentLoaded', function() {
    // If URL has onboarding=1 param and we're on an item page, set up return handling
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('onboarding') === '1') {
        // Store that we came from onboarding
        sessionStorage.setItem('onboarding_return', 'true');
    }

    // If we're on the onboarding page and have a return flag, refresh status
    if (sessionStorage.getItem('onboarding_return') === 'true' &&
        window.location.pathname.startsWith('/onboarding/step/')) {
        sessionStorage.removeItem('onboarding_return');
        refreshOnboardingStatus();
    }
});

// Export functions for global use
window.initOnboarding = initOnboarding;
window.dismissOnboardingBanner = dismissOnboardingBanner;
window.refreshOnboardingStatus = refreshOnboardingStatus;
