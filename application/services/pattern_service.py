"""
Pattern service for managing regex patterns.

Handles pattern CRUD operations, rule validation, and regex generation.
"""

import json
import logging
import re
from typing import List, Dict, Tuple, Optional
from uuid6 import uuid7

from application.services.base_service import BaseService
from application.services.category_service import CategoryService
from domain.repositories.regexp_repository import RegexpRepository

logger = logging.getLogger(__name__)


class PatternService(BaseService):
    """
    Service for managing regex patterns for transaction categorization.

    Provides CRUD operations for patterns with visual rule support,
    validation, and human-readable description generation.
    """

    def __init__(self, user_id: str, regexp_datasource: RegexpRepository,
                 category_service: CategoryService, db_path: str = None):
        """
        Initialize PatternService.

        Args:
            user_id: User ID for data isolation
            regexp_datasource: Regexp datasource implementation
            category_service: CategoryService for category validation
            db_path: Optional database path
        """
        super().__init__(user_id, db_path)
        self.datasource = regexp_datasource
        self._category_service = category_service

    @property
    def categories(self) -> Dict:
        """Get categories from category service."""
        return self._category_service.categories

    def get_pattern_by_id(self, pattern_id: str) -> Tuple[bool, str, dict]:
        """
        Get a single pattern by ID with full details for editing.

        Args:
            pattern_id: Pattern ID to lookup

        Returns:
            Tuple of (success, error_message, pattern_dict)
            pattern_dict contains: id, name, category_id, rules
        """
        regexp_datasource = self.datasource
        pattern = regexp_datasource.get_regexp_by_id(pattern_id)

        if not pattern:
            return False, "Pattern not found", {}

        # Parse visual description from the regexp
        rules = []
        if pattern.visual_description:
            try:
                visual_data = json.loads(pattern.visual_description)
                rules = visual_data.get('rules', [])
            except json.JSONDecodeError:
                pass

        return True, "", {
            'id': pattern.id,
            'name': pattern.name,
            'category_id': pattern.internal_category,
            'rules': rules
        }

    def get_all_patterns(self) -> List[dict]:
        """
        Get all patterns with parsed rules and metadata for UI display.

        Returns:
            List of pattern dicts with id, name, human_description, category_name, order_index
        """
        regexp_datasource = self.datasource
        patterns = regexp_datasource.get_all_regexps_with_metadata()
        categories = self.categories

        result = []
        for pattern in patterns:
            # Parse visual description to get rules
            rules = []
            if pattern.visual_description:
                try:
                    visual_data = json.loads(pattern.visual_description)
                    rules = visual_data.get('rules', [])
                except json.JSONDecodeError:
                    pass

            # Generate human-readable description
            human_desc = self.generate_human_description(rules) if rules else pattern.name

            # Get category name
            from domain.entities.category import Category
            category_name = categories.get(pattern.internal_category, Category(pattern.internal_category, pattern.internal_category, "", "")).name

            result.append({
                'id': pattern.id,
                'name': pattern.name,
                'human_description': human_desc,
                'category_name': category_name,
                'category_id': pattern.internal_category,
                'order_index': pattern.order_index,
                'rules': rules
            })

        return result

    def count_patterns(self) -> int:
        """
        Get the count of patterns for this user.

        Returns:
            Number of patterns
        """
        regexp_datasource = self.datasource
        patterns = regexp_datasource.get_all_regexps()
        return len(patterns)

    def create_pattern(self, rules: List[dict], category_id: str, name: str = "") -> Tuple[bool, str, str]:
        """
        Create a new pattern from visual rules.

        Args:
            rules: List of rule dicts with 'operator' and 'keyword'
            category_id: Category ID to assign matches to
            name: Optional pattern name (auto-generated if empty)

        Returns:
            Tuple of (success: bool, error_message: str, pattern_id: str)
        """
        # Validate rules
        success, error = self.validate_rules(rules)
        if not success:
            return (False, error, "")

        # Validate category exists
        if category_id not in self.categories:
            return (False, "Category does not exist", "")

        # Generate regex from rules
        try:
            raw_regex = self.rules_to_regex(rules)
        except Exception as e:
            return (False, f"Failed to generate regex: {str(e)}", "")

        # Test regex compilation
        try:
            re.compile(raw_regex, re.IGNORECASE)
        except re.error as e:
            return (False, f"Invalid regex pattern generated: {str(e)}", "")

        # Generate name if not provided
        if not name:
            name = self.generate_human_description(rules)[:40]  # Max 40 chars

        # Create visual description JSON
        visual_desc = json.dumps({
            "type": "visual_rule",
            "version": 1,
            "rules": rules
        })

        # Get next order_index
        regexp_datasource = self.datasource
        max_order = regexp_datasource.get_max_order_index()
        next_order = max_order + 1

        # Generate pattern ID
        pattern_id = str(uuid7())

        # Create pattern
        if regexp_datasource.create_regexp(pattern_id, raw_regex, name, visual_desc, category_id, next_order):
            return (True, "", pattern_id)
        else:
            return (False, "Failed to save pattern to database", "")

    def update_pattern(self, pattern_id: str, rules: List[dict], category_id: str, name: str = "") -> Tuple[bool, str]:
        """
        Update an existing pattern.

        Args:
            pattern_id: ID of pattern to update
            rules: New list of rule dicts
            category_id: New category ID
            name: New pattern name

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        # Validate rules
        success, error = self.validate_rules(rules)
        if not success:
            return (False, error)

        # Validate category exists
        if category_id not in self.categories:
            return (False, "Category does not exist")

        # Generate regex from rules
        try:
            raw_regex = self.rules_to_regex(rules)
        except Exception as e:
            return (False, f"Failed to generate regex: {str(e)}")

        # Test regex compilation
        try:
            re.compile(raw_regex, re.IGNORECASE)
        except re.error as e:
            return (False, f"Invalid regex pattern generated: {str(e)}")

        # Generate name if not provided
        if not name:
            name = self.generate_human_description(rules)[:40]

        # Create visual description JSON
        visual_desc = json.dumps({
            "type": "visual_rule",
            "version": 1,
            "rules": rules
        })

        # Update pattern
        regexp_datasource = self.datasource

        if regexp_datasource.update_regexp(pattern_id, raw_regex, name, visual_desc, category_id):
            return (True, "")
        else:
            return (False, "Failed to update pattern in database")

    def delete_pattern(self, pattern_id: str) -> Tuple[bool, str]:
        """
        Delete a pattern.

        Args:
            pattern_id: ID of pattern to delete

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        regexp_datasource = self.datasource

        if regexp_datasource.delete_regexp(pattern_id):
            return (True, "")
        else:
            return (False, "Pattern not found or failed to delete")

    def reorder_patterns(self, order_map: Dict[str, int]) -> Tuple[bool, str]:
        """
        Reorder patterns after drag-and-drop.

        Args:
            order_map: Dict mapping pattern_id -> new_order_index

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        if not order_map:
            return (True, "")

        # Convert to list of tuples
        order_updates = [(pattern_id, order_idx) for pattern_id, order_idx in order_map.items()]

        regexp_datasource = self.datasource

        if regexp_datasource.reorder_regexps(order_updates):
            return (True, "")
        else:
            return (False, "Failed to update pattern order")

    def validate_rules(self, rules: List[dict]) -> Tuple[bool, str]:
        """
        Validate rule structure and constraints.

        Args:
            rules: List of rule dicts with 'operator' and 'keyword'

        Returns:
            Tuple of (valid: bool, error_message: str)
        """
        if not rules:
            return (False, "At least one rule is required")

        # Count rule types
        positive_count = 0
        has_start = False
        has_end = False

        for rule in rules:
            if 'operator' not in rule or 'keyword' not in rule:
                return (False, "Each rule must have 'operator' and 'keyword'")

            operator = rule['operator']
            keyword = rule['keyword'].strip()

            # Check keyword is not empty
            if not keyword:
                return (False, "Keywords cannot be empty")

            # Check keyword length
            if len(keyword) > 100:
                return (False, "Keywords must be under 100 characters")

            # Count positive rules
            if operator in ['OR', 'AND', 'START_WITH', 'END_WITH']:
                positive_count += 1

            # Check for multiple START_WITH or END_WITH
            if operator == 'START_WITH':
                if has_start:
                    return (False, "Only one START_WITH rule allowed")
                has_start = True

            if operator == 'END_WITH':
                if has_end:
                    return (False, "Only one END_WITH rule allowed")
                has_end = True

        # Must have at least one positive rule
        if positive_count == 0:
            return (False, "Pattern must have at least one positive rule (OR, AND, START_WITH, or END_WITH)")

        # Check rule count
        if len(rules) > 20:
            return (False, "Maximum 20 rules per pattern")

        return (True, "")

    def rules_to_regex(self, rules: List[dict]) -> str:
        """
        Convert visual rules to regex pattern string.

        Supports 6 operators: NOT_START_WITH, START_WITH, OR, AND, NOT, END_WITH

        Args:
            rules: List of rule dicts with 'operator' and 'keyword'

        Returns:
            Regex pattern string
        """
        not_start = [r['keyword'] for r in rules if r['operator'] == 'NOT_START_WITH']
        start = [r['keyword'] for r in rules if r['operator'] == 'START_WITH']
        or_kw = [r['keyword'] for r in rules if r['operator'] == 'OR']
        and_kw = [r['keyword'].lower() for r in rules if r['operator'] == 'AND']
        not_kw = [r['keyword'].lower() for r in rules if r['operator'] == 'NOT']
        end = [r['keyword'] for r in rules if r['operator'] == 'END_WITH']

        # Use positional pattern (with lookaheads at start) if:
        # - Has positional operators (START_WITH, END_WITH, NOT_START_WITH), OR
        # - Has AND/NOT operators (need lookaheads to check entire string)
        has_positional = bool(start or end or not_start or and_kw or not_kw)
        parts = []

        if has_positional:
            # Positional pattern (no word boundaries)
            parts.append('^')

            # NOT_START_WITH: negative lookaheads at start
            for kw in not_start:
                parts.append(f"(?!{re.escape(kw)})")

            # START_WITH: match at beginning
            if start:
                if len(start) == 1:
                    parts.append(re.escape(start[0]))
                else:
                    escaped = [re.escape(kw) for kw in start]
                    parts.append(f"({'|'.join(escaped)})")

            # OR keywords: lookahead to check presence anywhere
            if or_kw:
                escaped_or = [re.escape(kw) for kw in or_kw]
                if len(escaped_or) == 1:
                    parts.append(f"(?=.*{escaped_or[0]})")
                else:
                    parts.append(f"(?=.*({'|'.join(escaped_or)}))")

            # AND keywords: lookahead assertions
            for kw in and_kw:
                parts.append(f"(?=.*{re.escape(kw)})")

            # NOT keywords: negative lookahead assertions
            for kw in not_kw:
                parts.append(f"(?!.*{re.escape(kw)})")

            # Match any text up to end
            parts.append('.*')

            # END_WITH: match at end
            if end:
                if len(end) == 1:
                    parts.append(re.escape(end[0]))
                else:
                    escaped = [re.escape(kw) for kw in end]
                    parts.append(f"({'|'.join(escaped)})")

            parts.append('$')

        else:
            # Pure contains pattern (with word boundaries)
            parts.append(r"(^|\s)")

            # OR keywords: (keyword1|keyword2)
            if or_kw:
                escaped_or = [re.escape(kw) for kw in or_kw]
                parts.append(f"({'|'.join(escaped_or)})")

            # AND keywords: (?=.*keyword)
            for kw in and_kw:
                parts.append(f"(?=.*{re.escape(kw)})")

            # NOT keywords: (?!.*keyword)
            for kw in not_kw:
                parts.append(f"(?!.*{re.escape(kw)})")

            # Match any text if no OR keywords
            if not or_kw:
                parts.append(r".*")

            parts.append(r"(\s|$)")

        return "".join(parts)

    def visual_description_to_rules(self, visual_description: str) -> List[dict]:
        """
        Parse JSON visual_description back to rules list.

        Args:
            visual_description: JSON string

        Returns:
            List of rule dicts
        """
        try:
            visual_data = json.loads(visual_description)
            return visual_data.get('rules', [])
        except json.JSONDecodeError:
            return []

    def generate_human_description(self, rules: List[dict]) -> str:
        """
        Generate human-readable description from rules.

        Args:
            rules: List of rule dicts with 'operator' and 'keyword'

        Returns:
            Human-readable string like "Starts with amazon, contains grocery OR vegetables, must NOT contain gift"
        """
        if not rules:
            return "No rules defined"

        parts = []

        not_start = [r['keyword'] for r in rules if r['operator'] == 'NOT_START_WITH']
        start = [r['keyword'] for r in rules if r['operator'] == 'START_WITH']
        or_kw = [r['keyword'] for r in rules if r['operator'] == 'OR']
        and_kw = [r['keyword'] for r in rules if r['operator'] == 'AND']
        not_kw = [r['keyword'] for r in rules if r['operator'] == 'NOT']
        end = [r['keyword'] for r in rules if r['operator'] == 'END_WITH']

        if not_start:
            parts.append(f"Not starts with {' or '.join(not_start)}")

        if start:
            parts.append(f"Starts with {' or '.join(start)}")

        if or_kw:
            parts.append(f"Contains {' OR '.join(or_kw)}")

        if and_kw:
            parts.append(f"Must contain {' AND '.join(and_kw)}")

        if not_kw:
            parts.append(f"Must NOT contain {' or '.join(not_kw)}")

        if end:
            parts.append(f"Ends with {' or '.join(end)}")

        return ", ".join(parts)
