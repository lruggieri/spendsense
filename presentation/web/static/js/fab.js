/**
 * Context-Aware Floating Action Button (FAB)
 * Displays page-specific actions in a fan-out menu
 */

// FAB configuration per page
const FAB_CONFIG = {
    '/review': [
        {
            id: 'add-transaction',
            label: 'Add Transaction',
            icon: '+',
            action: 'openAddTransactionModal',
            class: 'success'
        },
        {
            id: 'recategorize-all',
            label: 'Re-categorize All',
            icon: '⟳',
            action: () => {
                const form = document.getElementById('recategorize-form');
                if (form) form.submit();
            },
            class: 'success'
        }
    ],
    '/groups': [
        {
            id: 'create-group',
            label: 'Create Group',
            icon: '+',
            action: 'openCreateGroupModal',
            class: 'success'
        }
    ],
    '/patterns': [
        {
            id: 'create-pattern',
            label: 'Create Pattern',
            icon: '+',
            action: 'openCreateModal',
            class: 'success'
        }
    ],
    '/categories': [
        {
            id: 'create-category',
            label: 'Create Category',
            icon: '+',
            action: 'openCreateModal',
            class: 'success'
        }
    ],
    '/settings/fetchers': [
        {
            id: 'create-fetcher',
            label: 'Create Fetcher',
            icon: '+',
            action: () => {
                window.location.href = '/settings/fetchers/new';
            },
            class: 'success'
        }
    ]
};

class FAB {
    constructor() {
        this.container = document.getElementById('fab-container');
        this.fabMain = document.getElementById('fab-main');
        this.fabBackdrop = document.getElementById('fab-backdrop');
        this.fabActions = document.getElementById('fab-actions');
        this.isOpen = false;

        this.init();
    }

    init() {
        if (!this.container) return;

        // Get current page actions
        const currentPath = window.location.pathname;
        const actions = FAB_CONFIG[currentPath];

        // Hide FAB if no actions for this page
        if (!actions || actions.length === 0) {
            this.container.style.display = 'none';
            return;
        }

        // Show FAB and render actions
        this.container.style.display = 'block';
        this.renderActions(actions);
        this.attachEventListeners();
    }

    renderActions(actions) {
        this.fabActions.innerHTML = '';

        actions.forEach(action => {
            const actionEl = document.createElement('div');
            actionEl.className = 'fab-action';

            const label = document.createElement('span');
            label.className = 'fab-action__label';
            label.textContent = action.label;

            const button = document.createElement('button');
            button.className = `fab-action__button ${action.class || ''}`;
            button.innerHTML = action.icon;
            button.setAttribute('aria-label', action.label);
            button.setAttribute('data-action-id', action.id);

            // Attach click handler
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                this.handleActionClick(action);
            });

            actionEl.appendChild(label);
            actionEl.appendChild(button);
            this.fabActions.appendChild(actionEl);
        });
    }

    handleActionClick(action) {
        // Close FAB
        this.close();

        // Execute action
        if (typeof action.action === 'string') {
            // Call global function
            if (typeof window[action.action] === 'function') {
                window[action.action]();
            }
        } else if (typeof action.action === 'function') {
            // Call inline function
            action.action();
        }
    }

    attachEventListeners() {
        // Toggle FAB on main button click
        this.fabMain.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });

        // Close on backdrop click
        this.fabBackdrop.addEventListener('click', () => {
            this.close();
        });

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) {
                this.close();
            }
        });

        // Close when clicking outside
        document.addEventListener('click', (e) => {
            if (this.isOpen && !this.container.contains(e.target)) {
                this.close();
            }
        });
    }

    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    }

    open() {
        this.container.classList.add('active');
        this.fabMain.setAttribute('aria-expanded', 'true');
        this.isOpen = true;
    }

    close() {
        this.container.classList.remove('active');
        this.fabMain.setAttribute('aria-expanded', 'false');
        this.isOpen = false;
    }
}

// Initialize FAB when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new FAB();
});
