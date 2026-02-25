"""
Session entity model.

Represents a user authentication session.
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
        user_profile: User profile data (Dict with user_name, user_picture)
        created_at: Session creation timestamp (UTC)
    """

    session_token: str
    user_id: str
    expiration: datetime
    user_profile: Dict
    created_at: datetime
