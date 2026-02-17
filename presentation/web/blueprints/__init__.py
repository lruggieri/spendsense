"""
Flask blueprints package.

This package contains all the Flask blueprints that organize the application routes
by functional domain.
"""

from presentation.web.blueprints.auth import auth_bp
from presentation.web.blueprints.main import main_bp
from presentation.web.blueprints.transactions import transactions_bp
from presentation.web.blueprints.gmail import gmail_bp
from presentation.web.blueprints.groups import groups_bp
from presentation.web.blueprints.categories import categories_bp
from presentation.web.blueprints.patterns import patterns_bp
from presentation.web.blueprints.fetchers import fetchers_bp
from presentation.web.blueprints.settings import settings_bp
from presentation.web.blueprints.onboarding import onboarding_bp
from presentation.web.blueprints.webauthn import webauthn_bp


def register_blueprints(app):
    """
    Register all blueprints with the Flask application.

    Args:
        app: Flask application instance
    """
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(gmail_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(patterns_bp)
    app.register_blueprint(fetchers_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(webauthn_bp)
