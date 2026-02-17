"""
User settings datasource abstraction.

This module provides an abstract interface for user settings storage, allowing easy migration from one database to another.
"""

from abc import ABC, abstractmethod
from typing import Tuple, List
from datetime import datetime
from domain.entities.user_settings import UserSettings


class UserSettingsRepository(ABC):
    """Abstract interface for user settings storage."""

    @abstractmethod
    def get_settings(self) -> UserSettings:
        """
        Get user settings entity.

        Returns defaults if no record exists for this user.

        Returns:
            UserSettings entity with current or default values
        """
        pass

    @abstractmethod
    def update_settings(self, settings: UserSettings) -> Tuple[bool, str]:
        """
        Update user settings entity.

        Args:
            settings: UserSettings entity to save

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        pass

    @abstractmethod
    def get_llm_call_timestamps(self) -> List[datetime]:
        """
        Get LLM call timestamps for the current user.

        Returns:
            List of datetime objects representing when LLM calls were made
        """
        pass

    @abstractmethod
    def update_llm_call_timestamps(self, timestamps: List[datetime]) -> bool:
        """
        Update LLM call timestamps for the current user.

        Args:
            timestamps: List of datetime objects to store

        Returns:
            True if update was successful, False otherwise
        """
        pass
