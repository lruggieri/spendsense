"""
Hermetic SpendSense server for Playwright end-to-end tests.

Boots the real Flask app against a throw-away SQLite database, with the
pieces that need network access or heavy resources replaced by
deterministic fakes:

- SentenceTransformer -> hashed character-trigram embeddings (no model download)
- CurrencyRateUpdater -> no-op (uses the rates bundled with CurrencyConverter)
- FallbackLLMProvider -> canned regex patterns (no LLM API calls)

It also registers a test-only ``/__e2e__`` blueprint used by the Playwright
fixtures to create sessions and seed data for a user. This blueprint only
exists in this script; the production app never registers it.

Usage:
    python tests/e2e/server.py            # listens on E2E_PORT (default 5055)
"""

import hashlib
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

# --- Environment (must be set before the app/config modules are imported) ---
_tmp_dir = tempfile.mkdtemp(prefix="spendsense-e2e-")
os.environ.setdefault("DATABASE_PATH", os.path.join(_tmp_dir, "e2e.db"))
os.environ.setdefault("CURRENCY_DATA_FILE", os.path.join(_tmp_dir, "currency", "ecb.zip"))
os.environ.setdefault("FLASK_SECRET_KEY", "e2e-secret-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "e2e-client-id.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "e2e-client-secret")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.pop("ALLOWED_EMAILS", None)


# --- Fakes ------------------------------------------------------------------
class FakeSentenceTransformer:
    """Deterministic stand-in for SentenceTransformer.

    Embeds text as a normalised bag of hashed character trigrams so that
    similar descriptions still get similar vectors.
    """

    DIM = 128

    def __init__(self, *args, **kwargs):
        pass

    def _embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.DIM, dtype=np.float32)
        padded = f"  {text.lower()}  "
        for i in range(len(padded) - 2):
            h = int(hashlib.md5(padded[i : i + 3].encode("utf-8")).hexdigest(), 16)
            vec[h % self.DIM] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    def encode(self, sentences, *args, **kwargs):
        if isinstance(sentences, str):
            return self._embed(sentences)
        return np.array([self._embed(s) for s in sentences], dtype=np.float32)


class FakeLLMProvider:
    """Returns fixed patterns matching the sample emails used in the tests."""

    def generate_patterns(self, email_text: str) -> dict:
        return {
            "amount_pattern": r"Amount:\s*\$?([\d,]+\.?\d*)",
            "merchant_pattern": r"Merchant:\s*(.+)",
            "currency_pattern": None,
        }


import sentence_transformers  # noqa: E402

sentence_transformers.SentenceTransformer = FakeSentenceTransformer

from infrastructure import currency_rate_updater  # noqa: E402

currency_rate_updater.CurrencyRateUpdater.start = lambda self: None
currency_rate_updater.CurrencyRateUpdater.stop = lambda self: None

from flask import Blueprint, jsonify, request  # noqa: E402

from presentation.web import app as app_module  # noqa: E402
from presentation.web.blueprints import fetchers as fetchers_module  # noqa: E402

fetchers_module.FallbackLLMProvider = FakeLLMProvider  # type: ignore[misc]

from application.services.oauth_service import OAuthService  # noqa: E402
from config import get_database_path  # noqa: E402
from domain.entities.transaction import Transaction  # noqa: E402
from presentation.web.extensions import get_session_datasource  # noqa: E402
from presentation.web.utils import (  # noqa: E402
    get_category_service,
    get_fetcher_service,
    get_group_service,
    get_pattern_service,
    get_transaction_service,
    get_user_settings_service,
)

app = app_module.app
e2e_bp = Blueprint("e2e", __name__, url_prefix="/__e2e__")


def _update_browser_settings(updates: dict):
    settings_service = get_user_settings_service()
    browser_settings = settings_service.get_user_settings().browser_settings or {}
    browser_settings.update(updates)
    settings_service.update_user_settings(browser_settings=browser_settings)


def _complete_onboarding():
    _update_browser_settings(
        {
            "onboarding_step": 0,
            "onboarding_completed_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _seed_basic() -> dict:
    """Seed a realistic data set and return the created IDs by name."""
    ids: dict = {"categories": {}, "patterns": {}, "groups": {}, "transactions": {}, "fetchers": {}}

    settings_service = get_user_settings_service()
    settings_service.update_user_settings(currency="USD")

    category_service = get_category_service()
    for name, parent in [
        ("Food", ""),
        ("Groceries", "Food"),
        ("Restaurants", "Food"),
        ("Transport", ""),
        ("Entertainment", ""),
    ]:
        ok, err, cat_id = category_service.create_category(
            name, f"{name} expenses", ids["categories"].get(parent, "")
        )
        assert ok, err
        ids["categories"][name] = cat_id

    pattern_service = get_pattern_service(category_service=category_service)
    ok, err, pattern_id = pattern_service.create_pattern(
        [{"operator": "OR", "keyword": "SUPERMARKET"}],
        ids["categories"]["Groceries"],
        "Supermarket",
    )
    assert ok, err
    ids["patterns"]["Supermarket"] = pattern_id
    ok, err, pattern_id = pattern_service.create_pattern(
        [{"operator": "OR", "keyword": "METRO"}, {"operator": "OR", "keyword": "TAXI"}],
        ids["categories"]["Transport"],
        "Transit",
    )
    assert ok, err
    ids["patterns"]["Transit"] = pattern_id

    fetcher_service = get_fetcher_service(user_settings_service=settings_service)
    ok, err, fetcher_id = fetcher_service.create_fetcher(
        name="Test Bank",
        from_emails=["alerts@testbank.example"],
        subject_filter="transaction",
        amount_pattern=r"Amount:\s*\$?([\d,]+\.?\d*)",
        merchant_pattern=r"Merchant:\s*(.+)",
        default_currency="USD",
    )
    assert ok, err
    ids["fetchers"]["Test Bank"] = fetcher_id

    tx_service = get_transaction_service(
        category_service=category_service, user_settings_service=settings_service
    )
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1)

    def this_month(days_ago: int) -> datetime:
        return max(now - timedelta(days=days_ago), month_start)

    # (key, description, amount in minor units, date, manual category, source)
    rows = [
        ("supermarket", "CITY SUPERMARKET", 4520, this_month(0), None, "Test Bank"),
        ("metro", "METRO CARD TOPUP", 2000, this_month(1), None, "Test Bank"),
        ("cinema", "Cinema Paradiso", 1500, this_month(2), "Entertainment", "Manual"),
        ("bistro", "Le Petit Bistro", 6400, this_month(2), "Restaurants", "Test Bank"),
        ("bistro2", "Le Petit Bistro Downtown", 3800, this_month(3), None, "Test Bank"),
        ("taxi_old", "TAXI RIDE AIRPORT", 5200, month_start - timedelta(days=20), None, "Test Bank"),
        ("market_old", "SUPERMARKET EXPRESS", 3100, month_start - timedelta(days=40), None, "Test Bank"),
    ]
    txs = []
    manual: dict = {}
    for key, desc, amount, date, manual_cat, source in rows:
        tx_id = f"{key}-{hashlib.sha1((request.user_id + key).encode()).hexdigest()[:12]}"
        ids["transactions"][key] = tx_id
        txs.append(
            Transaction(
                id=tx_id,
                date=date,
                amount=amount,
                description=desc,
                category="",
                source=source,
                currency="USD",
                created_at=now,
                fetcher_id=fetcher_id if source == "Test Bank" else None,
            )
        )
        if manual_cat:
            manual[tx_id] = ids["categories"][manual_cat]
    tx_service.add_transactions_batch(txs)
    tx_service.assign_categories_bulk(manual)

    group_service = get_group_service(transaction_service=tx_service)
    ok, err, group_id = group_service.create_group("Summer Trip")
    assert ok, err
    ids["groups"]["Summer Trip"] = group_id
    group_service.add_transactions_to_group(
        [ids["transactions"]["bistro"], ids["transactions"]["taxi_old"]], group_id
    )
    ok, err, group_id = group_service.create_group("Work")
    assert ok, err
    ids["groups"]["Work"] = group_id

    return ids


@e2e_bp.route("/session", methods=["POST"])
def create_session():
    """Create a logged-in session for ``user_id`` and optionally seed data.

    JSON body:
        user_id: str (required) - unique per test for isolation
        onboarded: bool (default true) - mark onboarding as completed
        seed: "none" | "basic" (default "none")
        user_name: str (optional)
        show_encryption_banner: bool (default false)
        onboarding_step: int (optional) - put the user mid-onboarding at this step
    """
    data = request.get_json() or {}
    user_id = data["user_id"]
    token = get_session_datasource().create_session(
        user_id=user_id,
        user_profile={"user_name": data.get("user_name", "E2E User"), "user_picture": ""},
        expiration=datetime.now(timezone.utc) + timedelta(days=1),
    )
    request.user_id = user_id  # type: ignore[attr-defined]
    seeded: dict = {}
    if data.get("seed") == "basic":
        seeded = _seed_basic()
    if data.get("onboarding_step") is not None:
        _update_browser_settings({"onboarding_step": int(data["onboarding_step"])})
    elif data.get("onboarded", True):
        _complete_onboarding()
    if not data.get("show_encryption_banner", False):
        _update_browser_settings({"encryption_banner_dismissed": True})
    return jsonify({"session_token": token, "user_id": user_id, "ids": seeded})


@e2e_bp.route("/mcp-pending", methods=["POST"])
def mcp_pending():
    """Register an OAuth client and start a pending MCP authorization.

    Returns the consent URL the MCP server would redirect the browser to.
    """
    data = request.get_json() or {}
    oauth_service = OAuthService(get_database_path())
    client_id = data.get("client_id", "e2e-client")
    redirect_uri = request.host_url + "__e2e__/oauth-callback"
    oauth_service.register_client(
        client_id, [redirect_uri], json.dumps({"client_name": data.get("client_name", "E2E Client")})
    )
    txn = oauth_service.begin_authorization(
        client_id,
        {
            "scopes": data.get("scopes", ["read"]),
            "code_challenge": "e2e-challenge",
            "redirect_uri": redirect_uri,
            "redirect_uri_provided_explicitly": True,
            "resource": None,
            "state": "e2e-state",
        },
    )
    return jsonify({"txn": txn, "consent_url": f"/mcp-consent?txn={txn}"})


@e2e_bp.route("/oauth-callback")
def oauth_callback():
    """Fake OAuth client redirect target: echoes the query parameters."""
    return jsonify(dict(request.args))


@e2e_bp.route("/health")
def health():
    return jsonify({"ok": True})


app.register_blueprint(e2e_bp)


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    port = int(os.environ.get("E2E_PORT", "5055"))
    print(f"[e2e] SpendSense test server on http://127.0.0.1:{port} (db: {os.environ['DATABASE_PATH']})")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True, use_reloader=False)
