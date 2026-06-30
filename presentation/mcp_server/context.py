"""Builds application services for an MCP request from a resolved identity + DEK.

Reuses the framework-agnostic application/infrastructure layers directly — does NOT
use presentation/web/utils.py (that reads Flask g/request)."""
from dataclasses import dataclass
from typing import Optional

from application.services.category_service import CategoryService
from application.services.classification_service import ClassificationService
from application.services.group_service import GroupService
from application.services.pattern_service import PatternService
from application.services.transaction_service import TransactionService
from application.services.user_settings_service import UserSettingsService
from infrastructure.persistence.sqlite.factory import SQLiteDataSourceFactory


@dataclass
class MCPServices:
    transaction: TransactionService
    category: CategoryService
    classification: ClassificationService
    pattern: PatternService
    group: GroupService
    user_settings: UserSettingsService


def build_services(db_path: str, user_id: str, dek_b64: Optional[str]) -> MCPServices:
    factory = SQLiteDataSourceFactory(db_path, user_id, encryption_key=dek_b64)

    category = CategoryService(user_id, factory.get_category_datasource(), db_path=db_path)
    pattern = PatternService(
        user_id, factory.get_regexp_datasource(), category, db_path=db_path
    )
    user_settings = UserSettingsService(
        user_id, factory.get_user_settings_datasource(), db_path=db_path
    )
    transaction = TransactionService(
        user_id,
        factory.get_transaction_datasource(),
        factory.get_manual_assignment_datasource(),
        category,
        user_settings,
        db_path=db_path,
    )
    embedding_ds = factory.get_embedding_datasource()
    classification = ClassificationService(
        user_id,
        factory.get_manual_assignment_datasource(),
        factory.get_regexp_datasource(),
        embedding_ds,
        db_path=db_path,
        skip_similarity=embedding_ds is None,
    )
    group = GroupService(
        user_id, factory.get_group_datasource(), transaction, db_path=db_path
    )
    return MCPServices(transaction, category, classification, pattern, group, user_settings)
