"""
Onboarding blueprint.

Handles user onboarding wizard routes for first-time setup.
Guides users through setting up fetchers, categories, and patterns.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session

from presentation.web.decorators import login_required
from presentation.web.utils import (
    get_user_settings_service,
    get_fetcher_service,
    get_category_service,
    get_pattern_service,
    get_encryption_service,
)


logger = logging.getLogger(__name__)

onboarding_bp = Blueprint('onboarding', __name__)

# Onboarding version - increment when adding new required steps for existing users
ONBOARDING_VERSION = 2

# Step definitions
ONBOARDING_STEPS = [
    {
        'number': 1,
        'key': 'fetchers',
        'title': 'Set Up Email Fetchers',
        'description': 'Configure email parsing to automatically import transactions from your bank notifications.',
        'icon': 'mail',
        'create_url_name': 'fetchers.create_fetcher',
        'list_url_name': 'fetchers.fetchers'
    },
    {
        'number': 2,
        'key': 'categories',
        'title': 'Configure Categories',
        'description': 'Set up expense categories to organize your transactions.',
        'icon': 'folder',
        'create_url_name': 'categories.categories',
        'list_url_name': 'categories.categories'
    },
    {
        'number': 3,
        'key': 'patterns',
        'title': 'Create Patterns',
        'description': 'Define regex patterns to automatically categorize transactions.',
        'icon': 'code',
        'create_url_name': 'patterns.patterns',
        'list_url_name': 'patterns.patterns'
    },
    {
        'number': 4,
        'key': 'encryption',
        'title': 'Protect Your Data',
        'description': 'Enable end-to-end encryption with a passkey.',
        'icon': 'shield',
        'optional': True,
    }
]


def _get_onboarding_status_for_user(settings_service) -> dict:
    """
    Get current onboarding status from browser_settings.

    Args:
        settings_service: UserSettingsService instance

    Returns:
        Dict with onboarding status fields
    """
    settings = settings_service.get_user_settings()
    browser_settings = settings.browser_settings or {}

    return {
        'step': browser_settings.get('onboarding_step', None),
        'started_at': browser_settings.get('onboarding_started_at'),
        'completed_at': browser_settings.get('onboarding_completed_at'),
        'skipped': browser_settings.get('onboarding_skipped', False),
        'banner_dismissed': browser_settings.get('onboarding_banner_dismissed', False)
    }


def _update_onboarding_status(settings_service, updates: dict) -> bool:
    """
    Update onboarding status in browser_settings.

    Args:
        settings_service: UserSettingsService instance
        updates: Dict with fields to update

    Returns:
        True if update was successful
    """
    settings = settings_service.get_user_settings()
    browser_settings = settings.browser_settings or {}
    browser_settings.update(updates)

    success, _ = settings_service.update_user_settings(browser_settings=browser_settings)
    return success


def _get_step_counts(fetcher_service, category_service, pattern_service) -> dict:
    """
    Get counts of fetchers, categories, and patterns for the user.

    Args:
        fetcher_service: FetcherService instance
        category_service: CategoryService instance
        pattern_service: PatternService instance

    Returns:
        Dict with counts for each step type
    """
    from flask import request

    encryption_service = get_encryption_service()
    user_id = getattr(request, 'user_id', '')
    has_encryption = encryption_service.has_encryption(user_id) if user_id else False

    return {
        'fetchers': fetcher_service.count_fetchers(),
        'categories': category_service.count_categories(),
        'patterns': pattern_service.count_patterns(),
        'encryption': 1 if has_encryption else 0,
    }


def needs_onboarding(settings_service) -> bool:
    """
    Check if user needs to go through onboarding.

    Returns True if:
    - onboarding_step is None (never started)
    - onboarding_step is > 0 (in progress)

    Returns False if:
    - onboarding_step is 0 (completed or skipped)

    Args:
        settings_service: UserSettingsService instance

    Returns:
        True if user should be redirected to onboarding
    """
    status = _get_onboarding_status_for_user(settings_service)
    step = status['step']

    # None means never started, > 0 means in progress
    if step is None or step > 0:
        return True

    return False


def initialize_onboarding(settings_service) -> int:
    """
    Initialize onboarding for a new user.

    Sets onboarding_step to 1 and records started_at timestamp.

    Args:
        settings_service: UserSettingsService instance

    Returns:
        The starting step number (1)
    """
    now = datetime.now(timezone.utc).isoformat()
    _update_onboarding_status(settings_service, {
        'onboarding_step': 1,
        'onboarding_started_at': now,
        'onboarding_completed_at': None,
        'onboarding_skipped': False
    })
    return 1


@onboarding_bp.route('/onboarding')
@login_required
def onboarding_index():
    """Redirect to current onboarding step."""
    settings_service = get_user_settings_service()
    status = _get_onboarding_status_for_user(settings_service)
    step = status['step']

    # If not started or completed, redirect appropriately
    if step is None:
        step = initialize_onboarding(settings_service)
    elif step == 0:
        # Completed or skipped - go to main
        return redirect(url_for('main.index'))

    return redirect(url_for('onboarding.step', step_num=step))


@onboarding_bp.route('/onboarding/step/<int:step_num>')
@login_required
def step(step_num: int):
    """Display onboarding step page."""
    # Validate step number
    if step_num < 1 or step_num > len(ONBOARDING_STEPS):
        return redirect(url_for('onboarding.onboarding_index'))

    settings_service = get_user_settings_service()
    status = _get_onboarding_status_for_user(settings_service)

    # If onboarding is completed, redirect to main
    if status['step'] == 0:
        return redirect(url_for('main.index'))

    # Get services for step counts
    fetcher_service = get_fetcher_service()
    category_service = get_category_service()
    pattern_service = get_pattern_service(category_service=category_service)

    # Get counts for all steps
    counts = _get_step_counts(fetcher_service, category_service, pattern_service)

    # Validate user can access this step (all previous required steps must be complete)
    for i in range(step_num - 1):
        prev_step = ONBOARDING_STEPS[i]
        if prev_step.get('optional'):
            continue  # Optional steps don't block access to later steps
        if counts[prev_step['key']] == 0:
            # Previous step not complete - redirect to first incomplete step
            return redirect(url_for('onboarding.step', step_num=i + 1))

    # Build step data with counts
    steps_data = []
    for step_def in ONBOARDING_STEPS:
        step_data = step_def.copy()
        step_data['count'] = counts[step_def['key']]
        step_data['is_complete'] = step_data['count'] > 0
        step_data['is_current'] = step_def['number'] == step_num
        step_data['is_past'] = step_def['number'] < step_num
        steps_data.append(step_data)

    current_step = steps_data[step_num - 1]

    # Determine template based on step
    template_map = {
        1: 'onboarding/step_fetchers.html',
        2: 'onboarding/step_categories.html',
        3: 'onboarding/step_patterns.html',
        4: 'onboarding/step_encryption.html',
    }

    # Optional steps can always be continued past (via Skip or after completing)
    is_optional = ONBOARDING_STEPS[step_num - 1].get('optional', False)

    # Build template context with step-specific data
    context = {
        'steps': steps_data,
        'current_step': current_step,
        'step_num': step_num,
        'total_steps': len(ONBOARDING_STEPS),
        'can_continue': current_step['count'] > 0 or is_optional,
        'hide_header': True  # Hide main navigation during onboarding
    }

    # Add step-specific data
    if step_num == 1:
        # Fetchers step - pass existing fetchers (enabled only)
        fetchers = fetcher_service.get_enabled_fetchers_for_list()
        context['fetchers'] = [{'id': f.id, 'name': f.name} for f in fetchers]

    elif step_num == 2:
        # Categories step - use service layer for consistency
        all_categories = category_service.get_categories_hierarchical()
        # Extract simple list for display, full list for parent dropdown
        context['categories'] = [{'id': c.id, 'name': c.name} for c, _ in all_categories]
        context['all_categories'] = all_categories

    elif step_num == 3:
        # Patterns step - pass existing patterns and all_categories for dropdown
        patterns = pattern_service.get_all_patterns()
        context['patterns'] = [
            {'id': p['id'], 'name': p['name'], 'category_name': p['category_name']}
            for p in patterns
        ]

        # all_categories with depth for category dropdown
        context['all_categories'] = category_service.get_categories_hierarchical()

    return render_template(template_map[step_num], **context)


@onboarding_bp.route('/api/onboarding/advance', methods=['POST'])
@login_required
def api_advance():
    """
    Advance to the next onboarding step.

    Request JSON:
        {
            "current_step": 1  // Current step number
        }

    Response JSON:
        {
            "success": true/false,
            "next_step": 2,  // Next step number or 0 if complete
            "redirect_url": "/onboarding/step/2" or "/onboarding/complete"
        }
    """
    try:
        data = request.get_json() or {}
        current_step = data.get('current_step', 1)

        # Get services
        settings_service = get_user_settings_service()
        fetcher_service = get_fetcher_service()
        category_service = get_category_service()
        pattern_service = get_pattern_service(category_service=category_service)

        # Validate current step has required items (skip check for optional steps)
        counts = _get_step_counts(fetcher_service, category_service, pattern_service)
        current_step_def = ONBOARDING_STEPS[current_step - 1]
        step_key = current_step_def['key']
        is_optional = current_step_def.get('optional', False)

        if counts[step_key] == 0 and not is_optional:
            return jsonify({
                'success': False,
                'error': 'Please create at least one item before continuing.'
            }), 400

        # Determine next step
        if current_step >= len(ONBOARDING_STEPS):
            # Completed!
            now = datetime.now(timezone.utc).isoformat()
            _update_onboarding_status(settings_service, {
                'onboarding_step': 0,
                'onboarding_completed_at': now
            })
            # Cache completion in session to avoid future DB checks
            session['onboarding_version'] = ONBOARDING_VERSION
            return jsonify({
                'success': True,
                'next_step': 0,
                'redirect_url': url_for('onboarding.complete')
            })
        else:
            next_step = current_step + 1
            _update_onboarding_status(settings_service, {
                'onboarding_step': next_step
            })
            return jsonify({
                'success': True,
                'next_step': next_step,
                'redirect_url': url_for('onboarding.step', step_num=next_step)
            })

    except Exception as e:
        logger.error(f"Error advancing onboarding: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@onboarding_bp.route('/api/onboarding/dismiss-banner', methods=['POST'])
@login_required
def api_dismiss_banner():
    """
    Dismiss the onboarding reminder banner.

    Response JSON:
        {
            "success": true/false
        }
    """
    try:
        settings_service = get_user_settings_service()
        _update_onboarding_status(settings_service, {
            'onboarding_banner_dismissed': True
        })

        return jsonify({
            'success': True
        })

    except Exception as e:
        logger.error(f"Error dismissing banner: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@onboarding_bp.route('/api/onboarding/status')
@login_required
def api_status():
    """
    Get current onboarding status and counts.

    Response JSON:
        {
            "success": true,
            "status": {
                "step": 1,
                "started_at": "...",
                "completed_at": null,
                "skipped": false,
                "banner_dismissed": false
            },
            "counts": {
                "fetchers": 0,
                "categories": 5,
                "patterns": 2
            }
        }
    """
    try:
        settings_service = get_user_settings_service()
        fetcher_service = get_fetcher_service()
        category_service = get_category_service()
        pattern_service = get_pattern_service(category_service=category_service)

        status = _get_onboarding_status_for_user(settings_service)
        counts = _get_step_counts(fetcher_service, category_service, pattern_service)

        return jsonify({
            'success': True,
            'status': status,
            'counts': counts
        })

    except Exception as e:
        logger.error(f"Error getting onboarding status: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@onboarding_bp.route('/onboarding/complete')
@login_required
def complete():
    """Display onboarding completion page."""
    settings_service = get_user_settings_service()
    status = _get_onboarding_status_for_user(settings_service)

    # If not actually complete, redirect to current step
    if status['step'] is None or status['step'] > 0:
        return redirect(url_for('onboarding.onboarding_index'))

    fetcher_service = get_fetcher_service()
    category_service = get_category_service()
    pattern_service = get_pattern_service(category_service=category_service)
    counts = _get_step_counts(fetcher_service, category_service, pattern_service)

    return render_template(
        'onboarding/complete.html',
        counts=counts,
        hide_header=True
    )
