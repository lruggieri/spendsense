"""
Flask application factory for SpendSense.

This module provides the create_app() function for creating Flask application instances.
"""

import logging
import os
import sys
import time
import traceback

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from urllib.parse import unquote

from flask import Flask, g, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_flask_secret_key, get_log_level

# Load environment variables from .env file if present (for local development)
try:
    from dotenv import load_dotenv

    load_dotenv()
    print("[CONFIG] Loaded .env file")
except ImportError:
    print("[CONFIG] python-dotenv not installed, using system environment variables only")

# Configure logging before anything else
log_level_str = get_log_level()
logging.basicConfig(
    level=getattr(logging, log_level_str),
    format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Suppress OAuth library debug logs — they dump tokens, secrets, and auth codes
logging.getLogger("requests_oauthlib").setLevel(logging.WARNING)
logging.getLogger("oauthlib").setLevel(logging.WARNING)

# Allow OAuth over HTTP for local development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def create_app():
    """
    Application factory for creating Flask app instances.

    Returns:
        Flask application instance
    """
    app = Flask(__name__)
    app.secret_key = get_flask_secret_key()

    # Fix for reverse proxy HTTPS detection
    # This tells Flask to trust X-Forwarded-* headers from proxies
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # Initialize extensions
    from presentation.web.extensions import init_extensions

    init_extensions(app)

    # Register template filters
    from presentation.web.filters import register_filters

    register_filters(app)

    # Register context processors
    from presentation.web.context_processors import register_context_processors

    register_context_processors(app)

    # Register blueprints
    from presentation.web.blueprints import register_blueprints

    register_blueprints(app)

    # Encryption key extraction middleware
    ENCRYPTION_PUBLIC_PREFIXES = (
        "/static/",
        "/service-worker.js",
        "/api/webauthn/",
        "/favicon.ico",
        "/manifest.json",
    )

    # Suppress werkzeug access logs for static/public paths
    class _StaticFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage()
            return not any(p in msg for p in ENCRYPTION_PUBLIC_PREFIXES)

    logging.getLogger("werkzeug").addFilter(_StaticFilter())

    @app.before_request
    def extract_encryption_key():
        """Extract encryption key from X-Encryption-Key header or encryption_key cookie."""
        g.encryption_key = None

        # Skip for public endpoints
        if request.path.startswith(ENCRYPTION_PUBLIC_PREFIXES):
            return

        # Read from header first (fetch requests), then cookie (page navigations)
        key = request.headers.get("X-Encryption-Key")
        if not key:
            key = request.cookies.get("encryption_key")
            # Cookie value may be URL-encoded by client-side JS (encodeURIComponent)
            # which turns base64 padding '=' into '%3D'. Decode to get raw base64.
            if key:
                key = unquote(key)
        if key:
            g.encryption_key = key

    # Request timing middleware
    @app.before_request
    def before_request_timing():
        """Track request start time."""
        if request.path.startswith(ENCRYPTION_PUBLIC_PREFIXES):
            return
        request._start_time = time.time()
        logger.debug("")
        logger.debug("=" * 80)
        logger.debug(f"REQUEST START: {request.method} {request.path}")
        logger.debug("=" * 80)

    @app.after_request
    def after_request_timing(response):
        """Log request completion time."""
        start_time = getattr(request, "_start_time", None)
        if start_time:
            duration = (time.time() - start_time) * 1000
            logger.debug("=" * 80)
            logger.debug(
                f"REQUEST END: {request.method} {request.path} - Status: {response.status_code}"
            )
            logger.debug(f"REQUEST TIME: {duration:.2f}ms")
            logger.debug("=" * 80)
            logger.debug("")
        return response

    # Error handlers
    @app.errorhandler(404)
    def handle_404(error):
        """Handle 404 Not Found errors."""
        logger.warning(f"404 Not Found: {request.method} {request.path}")
        return (
            render_template(
                "error.html",
                error_code=404,
                error_message="Page Not Found",
                error_details="The page you're looking for doesn't exist. It may have been moved or deleted.",
            ),
            404,
        )

    @app.errorhandler(500)
    def handle_500(error):
        """Handle 500 Internal Server Error."""
        # Log full error with traceback
        logger.error("=" * 80)
        logger.error(f"500 Internal Server Error: {request.method} {request.path}")
        logger.error(f"Error: {error}")
        logger.error("Traceback:")
        logger.error(traceback.format_exc())
        logger.error("=" * 80)

        return (
            render_template(
                "error.html",
                error_code=500,
                error_message="Something Went Wrong",
                error_details="We encountered an unexpected error. Our team has been notified and will look into it.",
            ),
            500,
        )

    @app.errorhandler(Exception)
    def handle_exception(error):
        """Handle all uncaught exceptions."""
        # Log full error with traceback
        logger.error("=" * 80)
        logger.error(f"Uncaught Exception: {request.method} {request.path}")
        logger.error(f"Error type: {type(error).__name__}")
        logger.error(f"Error: {error}")
        logger.error("Traceback:")
        logger.error(traceback.format_exc())
        logger.error("=" * 80)

        return (
            render_template(
                "error.html",
                error_code=500,
                error_message="Something Went Wrong",
                error_details="We encountered an unexpected error. Our team has been notified and will look into it.",
            ),
            500,
        )

    return app


# Create the application instance
app = create_app()

if __name__ == "__main__":
    # Enable debug mode by default for local development
    # Set FLASK_DEBUG=0 to disable and see custom error pages
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"

    flask_port = os.environ.get("FLASK_PORT", 5000)
    flask_host = os.environ.get("FLASK_HOST", "127.0.0.1")

    app.run(debug=debug_mode, port=flask_port, host=flask_host)
