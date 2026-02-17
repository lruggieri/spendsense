"""
SQLite implementation of the DataSource Factory.

This module provides a concrete factory for creating SQLite datasource instances with caching.
"""

from typing import Optional

from infrastructure.persistence.factory import DataSourceFactory
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
from infrastructure.persistence.sqlite.repositories.category_repository import SQLiteCategoryDataSource
from infrastructure.persistence.sqlite.repositories.transaction_repository import SQLiteTransactionDataSource
from infrastructure.persistence.sqlite.repositories.manual_assignment_repository import SQLiteManualAssignmentDataSource
from infrastructure.persistence.sqlite.repositories.regexp_repository import SQLiteRegexpDataSource
from infrastructure.persistence.sqlite.repositories.session_repository import SQLiteSessionDataSource
from infrastructure.persistence.sqlite.repositories.user_settings_repository import SQLiteUserSettingsDataSource
from infrastructure.persistence.sqlite.repositories.fetcher_repository import SQLiteFetcherDataSource
from infrastructure.persistence.sqlite.repositories.group_repository import SQLiteGroupDataSource
from infrastructure.persistence.sqlite.repositories.embedding_repository import SQLiteEmbeddingDataSource
from infrastructure.persistence.sqlite.repositories.encryption_repository import SQLiteEncryptionRepository


class SQLiteDataSourceFactory(DataSourceFactory):
    """SQLite implementation of datasource factory with instance caching."""

    def __init__(self, db_path: str, user_id: str, encryption_key: Optional[str] = None):
        """
        Initialize the SQLite factory.

        Args:
            db_path: Path to the SQLite database file
            user_id: User ID for multi-tenancy filtering
            encryption_key: Optional base64-encoded encryption key for field encryption
        """
        self.db_path = db_path
        self.user_id = user_id
        self.encryption_key = encryption_key
        self._cache = {}

    def get_category_datasource(self) -> CategoryRepository:
        """Get cached or create new SQLite category datasource."""
        if 'category' not in self._cache:
            self._cache['category'] = SQLiteCategoryDataSource(self.db_path, self.user_id)
        return self._cache['category']

    def get_transaction_datasource(self) -> TransactionRepository:
        """Get cached or create new SQLite transaction datasource."""
        if 'transaction' not in self._cache:
            self._cache['transaction'] = SQLiteTransactionDataSource(
                self.db_path, self.user_id, encryption_key=self.encryption_key
            )
        return self._cache['transaction']

    def get_manual_assignment_datasource(self) -> ManualAssignmentRepository:
        """Get cached or create new SQLite manual assignment datasource."""
        if 'manual_assignment' not in self._cache:
            self._cache['manual_assignment'] = SQLiteManualAssignmentDataSource(self.db_path, self.user_id)
        return self._cache['manual_assignment']

    def get_regexp_datasource(self) -> RegexpRepository:
        """Get cached or create new SQLite regexp datasource."""
        if 'regexp' not in self._cache:
            self._cache['regexp'] = SQLiteRegexpDataSource(self.db_path, self.user_id)
        return self._cache['regexp']

    def get_session_datasource(self) -> SessionRepository:
        """
        Get cached or create new SQLite session datasource.

        Note: Session datasource only requires db_path, not user_id.
        """
        if 'session' not in self._cache:
            self._cache['session'] = SQLiteSessionDataSource(self.db_path)
        return self._cache['session']

    def get_user_settings_datasource(self) -> UserSettingsRepository:
        """Get cached or create new SQLite user settings datasource."""
        if 'user_settings' not in self._cache:
            self._cache['user_settings'] = SQLiteUserSettingsDataSource(self.db_path, self.user_id)
        return self._cache['user_settings']

    def get_fetcher_datasource(self) -> FetcherRepository:
        """Get cached or create new SQLite fetcher datasource."""
        if 'fetcher' not in self._cache:
            self._cache['fetcher'] = SQLiteFetcherDataSource(self.db_path, self.user_id)
        return self._cache['fetcher']

    def get_group_datasource(self) -> GroupRepository:
        """Get cached or create new SQLite group datasource."""
        if 'group' not in self._cache:
            self._cache['group'] = SQLiteGroupDataSource(self.db_path, self.user_id)
        return self._cache['group']

    def get_embedding_datasource(self) -> EmbeddingRepository:
        """Get cached or create new SQLite embedding datasource."""
        if 'embedding' not in self._cache:
            self._cache['embedding'] = SQLiteEmbeddingDataSource(self.db_path, self.user_id)
        return self._cache['embedding']

    def get_encryption_datasource(self) -> EncryptionRepository:
        """Get cached or create new SQLite encryption datasource."""
        if 'encryption' not in self._cache:
            self._cache['encryption'] = SQLiteEncryptionRepository(self.db_path)
        return self._cache['encryption']
