"""
Session entity model.

Represents a user authentication session with Google OAuth tokens.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass
class Session:
    """
    User session entity.

    Attributes:
        session_token: Unique session identifier
        user_id: User identifier (email or Google ID)
        expiration: Session expiration datetime (UTC)
        google_token: Google OAuth token bundle (Dict with access_token, refresh_token, etc.)
        created_at: Session creation timestamp (UTC)
    """

    session_token: str
    user_id: str
    expiration: datetime
    google_token: Dict
    created_at: datetime
