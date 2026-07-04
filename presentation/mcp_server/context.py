"""Builds application services for an MCP request from a resolved identity + DEK.

Reuses the framework-agnostic application/infrastructure layers directly — does NOT
use presentation/web/utils.py (that reads Flask g/request)."""
import logging
from dataclasses import dataclass
from typing import Optional

from application.services.category_service import CategoryService
from application.services.classification_service import ClassificationService
from application.services.group_service import GroupService
from application.services.pattern_service import PatternService
from application.services.transaction_service import TransactionService
from application.services.user_settings_service import UserSettingsService
from domain.services.embedding_similarity_calculator import EmbeddingSimilarityCalculator
from infrastructure.persistence.sqlite.factory import SQLiteDataSourceFactory

logger = logging.getLogger(__name__)


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
    try:
        from presentation.web.extensions import get_sentence_model
        loaded_model = get_sentence_model()
    except ImportError:
        logger.warning(
            "presentation.web.extensions unavailable; MCP falling back to "
            "manual/regex-only classification (skip_similarity=True)"
        )
        loaded_model = None
    if loaded_model is None:
        logger.warning(
            "no pre-loaded sentence model available; MCP falling back to "
            "manual/regex-only classification (skip_similarity=True)"
        )
    similarity_calc = (
        EmbeddingSimilarityCalculator(model=loaded_model, embedding_datasource=embedding_ds)
        if loaded_model is not None and embedding_ds is not None
        else None
    )
    classification = ClassificationService(
        user_id,
        factory.get_manual_assignment_datasource(),
        factory.get_regexp_datasource(),
        embedding_ds,
        db_path=db_path,
        similarity_calculator=similarity_calc,
        skip_similarity=similarity_calc is None,
    )
    group = GroupService(
        user_id, factory.get_group_datasource(), transaction, db_path=db_path
    )
    return MCPServices(transaction, category, classification, pattern, group, user_settings)
