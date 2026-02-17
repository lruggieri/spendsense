"""
DataSource Factory abstraction.

This module provides an abstract factory interface for creating datasource instances,
enabling database-agnostic architecture.
"""

from abc import ABC, abstractmethod
from domain.repositories.category_repository import CategoryRepository
from domain.repositories.transaction_repository import TransactionRepository
from domain.repositories.manual_assignment_repository import ManualAssignmentRepository
from domain.repositories.regexp_repository import RegexpRepository
from domain.repositories.session_repository import SessionRepository
from domain.repositories.user_settings_repository import UserSettingsRepository
from domain.repositories.fetcher_repository import FetcherRepository
from domain.repositories.group_repository import GroupRepository
from domain.repositories.embedding_repository import EmbeddingRepository
from domain.repositories.encryption_repository import EncryptionRepository


class DataSourceFactory(ABC):
    """Abstract factory for creating datasource instances."""

    @abstractmethod
    def get_category_datasource(self) -> CategoryRepository:
        """
        Get category datasource instance.

        Returns:
            CategoryRepository implementation
        """
        pass

    @abstractmethod
    def get_transaction_datasource(self) -> TransactionRepository:
        """
        Get transaction datasource instance.

        Returns:
            TransactionRepository implementation
        """
        pass

    @abstractmethod
    def get_manual_assignment_datasource(self) -> ManualAssignmentRepository:
        """
        Get manual assignment datasource instance.

        Returns:
            ManualAssignmentRepository implementation
        """
        pass

    @abstractmethod
    def get_regexp_datasource(self) -> RegexpRepository:
        """
        Get regexp datasource instance.

        Returns:
            RegexpRepository implementation
        """
        pass

    @abstractmethod
    def get_session_datasource(self) -> SessionRepository:
        """
        Get session datasource instance.

        Returns:
            SessionRepository implementation
        """
        pass

    @abstractmethod
    def get_user_settings_datasource(self) -> UserSettingsRepository:
        """
        Get user settings datasource instance.

        Returns:
            UserSettingsRepository implementation
        """
        pass

    @abstractmethod
    def get_fetcher_datasource(self) -> FetcherRepository:
        """
        Get fetcher datasource instance.

        Returns:
            FetcherRepository implementation
        """
        pass

    @abstractmethod
    def get_group_datasource(self) -> GroupRepository:
        """
        Get group datasource instance.

        Returns:
            GroupRepository implementation
        """
        pass

    @abstractmethod
    def get_embedding_datasource(self) -> EmbeddingRepository:
        """
        Get embedding datasource instance.

        Returns:
            EmbeddingRepository implementation
        """
        pass

    @abstractmethod
    def get_encryption_datasource(self) -> EncryptionRepository:
        """
        Get encryption datasource instance.

        Returns:
            EncryptionRepository implementation
        """
        pass
