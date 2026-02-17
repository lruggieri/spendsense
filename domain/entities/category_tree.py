from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from domain.entities.category import Category
from domain.entities.transaction import Transaction
from domain.services.amount_utils import to_major_units_float

logger = logging.getLogger(__name__)

ALL_CATEGORY_ID: str = "all"
UNKNOWN_CATEGORY_ID: str = "unknown"

@dataclass
class CategoryNode:
    category: Category
    children: List['CategoryNode']
    total_expense: float = 0.0


class CategoryTree:
    def __init__(self, categories: Dict[str, list[Category]]):
        self.categories = {cat.id: cat for cat in categories["internal"]}
        self.root = self._build_tree()
        self.filtered_transactions = None  # Initialize attribute

    def _build_tree(self) -> CategoryNode:
        # Create the root category
        root_category = Category(ALL_CATEGORY_ID, "All", "Root category for all expenses", "")
        root_node = CategoryNode(root_category, [])

        # Create unknown category
        unknown_category = Category(UNKNOWN_CATEGORY_ID, "Unknown", "Unknown categories", ALL_CATEGORY_ID)
        self.categories[UNKNOWN_CATEGORY_ID] = unknown_category

        # Create mapping of category_id to node
        nodes = {ALL_CATEGORY_ID: root_node}

        # Create nodes for all categories (including unknown)
        for cat_id, category in self.categories.items():
            nodes[cat_id] = CategoryNode(category, [])

        # Build parent-child relationships
        for cat_id, category in self.categories.items():
            node = nodes[cat_id]
            parent_id = category.parent_id if category.parent_id else ALL_CATEGORY_ID

            if parent_id in nodes:
                nodes[parent_id].children.append(node)
            else:
                # If parent doesn't exist, attach to root
                root_node.children.append(node)

        return root_node

    def _filter_transactions_by_date(self, transactions: List[Transaction], from_date: Optional[str], to_date: Optional[str]) -> List[Transaction]:
        if not from_date and not to_date:
            return transactions

        filtered = []
        for tx in transactions:
            # tx.date is already a datetime object
            tx_date = tx.date if isinstance(tx.date, datetime) else self._parse_date(tx.date)
            if tx_date is None:
                continue

            include_tx = True

            if from_date:
                from_datetime = self._parse_date(from_date)
                # from_date is inclusive from start of day (00:00:00)
                if from_datetime and tx_date < from_datetime:
                    include_tx = False

            if to_date and include_tx:
                to_datetime = self._parse_date(to_date)
                # to_date should be inclusive through end of day (23:59:59)
                if to_datetime:
                    # If parsed date is midnight (day-only format), extend to end of day
                    if to_datetime.hour == 0 and to_datetime.minute == 0 and to_datetime.second == 0:
                        to_datetime = to_datetime.replace(hour=23, minute=59, second=59)
                    if tx_date > to_datetime:
                        include_tx = False

            if include_tx:
                filtered.append(tx)

        return filtered

    def _parse_date(self, date_input: any) -> Optional[datetime]:
        # If already a datetime object, return it
        if isinstance(date_input, datetime):
            return date_input

        # Otherwise try to parse as string
        if not isinstance(date_input, str):
            return None

        # Try ISO 8601 format first (e.g. "2026-02-15T15:00:00.000Z" or "2026-02-15T15:00:00+00:00")
        if 'T' in date_input:
            try:
                dt = datetime.fromisoformat(date_input.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except (ValueError, AttributeError):
                pass

        formats = [
            "%Y-%m-%d",      # 2025-09-26
            "%Y/%m/%d",      # 2025/09/26
            "%m/%d/%Y",      # 09/26/2025
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_input, fmt)
                # Make timezone-aware (assume UTC) for comparison with transaction dates
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        return None

    def _reset_expenses(self, node: CategoryNode) -> None:
        node.total_expense = 0.0
        for child in node.children:
            self._reset_expenses(child)

    def _add_expense_to_category_and_parents(self, category_id: str, amount: float) -> None:
        current_id = category_id

        while current_id:
            node = self._find_node_by_id(self.root, current_id)
            if node:
                node.total_expense += amount
                # Move to parent
                if current_id == ALL_CATEGORY_ID:
                    break
                elif current_id in self.categories:
                    parent_id = self.categories[current_id].parent_id
                    current_id = parent_id if parent_id else ALL_CATEGORY_ID
                else:
                    current_id = ALL_CATEGORY_ID
            else:
                break

    def _find_node_by_id(self, node: CategoryNode, category_id: str) -> Optional[CategoryNode]:
        if node.category.id == category_id:
            return node

        for child in node.children:
            result = self._find_node_by_id(child, category_id)
            if result:
                return result

        return None

    def calculate_expenses(self, transactions: List[Transaction], from_date: Optional[str] = None, to_date: Optional[str] = None, user_currency: Optional[str] = None, converter=None) -> None:
        """
        Calculate expenses with optional currency conversion.

        Args:
            transactions: List of transactions to process
            from_date: Optional start date filter (YYYY-MM-DD)
            to_date: Optional end date filter (YYYY-MM-DD)
            user_currency: Optional target currency for conversion (e.g., 'USD')
            converter: Optional CurrencyConverterService instance
        """
        # Reset all expenses to 0
        self._reset_expenses(self.root)

        # Filter transactions by date if specified
        filtered_transactions = self._filter_transactions_by_date(transactions, from_date, to_date)

        # Store filtered transactions for later use
        self.filtered_transactions = filtered_transactions

        # Calculate direct expenses for each category
        category_expenses = {}
        for tx in filtered_transactions:
            # Use the category if it exists, otherwise use "unknown"
            cat_id = tx.category if tx.category in self.categories else UNKNOWN_CATEGORY_ID

            # Convert amount if converter provided
            if converter and user_currency:
                # Convert from minor units to major units, then convert currency
                amount_major = to_major_units_float(tx.amount, tx.currency)
                converted_amount = converter.convert(amount_major, tx.currency, user_currency, tx.date)
            else:
                # Convert from minor units to major units
                converted_amount = to_major_units_float(tx.amount, tx.currency)

            if cat_id not in category_expenses:
                category_expenses[cat_id] = 0
            category_expenses[cat_id] += converted_amount

        # Set direct expenses and propagate to parents
        for cat_id, expense in category_expenses.items():
            self._add_expense_to_category_and_parents(cat_id, expense)

    def print_uncategorized_transactions(self) -> None:
        """Prints uncategorized transactions grouped by description, ordered by total descending"""
        if self.filtered_transactions is None:
            logger.info("No transactions to analyze")
            return

        uncategorized = {}
        for tx in self.filtered_transactions:
            if tx.category is None or tx.category not in self.categories:
                if tx.description not in uncategorized:
                    uncategorized[tx.description] = {
                        'count': 0,
                        'total': 0.0,
                        'tx_ids': []
                    }
                uncategorized[tx.description]['count'] += 1
                uncategorized[tx.description]['total'] += to_major_units_float(tx.amount, tx.currency)
                uncategorized[tx.description]['tx_ids'].append(tx.id)

        if not uncategorized:
            logger.info("No uncategorized transactions")
            return

        # Sort by total descending
        sorted_items = sorted(uncategorized.items(), key=lambda x: x[1]['total'], reverse=True)

        logger.info("Uncategorized transactions (sorted by total):")
        for description, data in sorted_items:
            logger.info(f"  {description}: ${data['total']:.2f} ({data['count']} transactions)")
            logger.info(f"    IDs: {', '.join(data['tx_ids'])}")

        total_uncategorized = sum(data['total'] for _, data in sorted_items)
        logger.info(f"Total uncategorized: ${total_uncategorized:.2f}")

    def print_tree(self, node: Optional[CategoryNode] = None, indent: int = 0, total: Optional[float] = None) -> None:
        if node is None:
            node = self.root
            total = node.total_expense

        indent_str = "  " * indent
        percentage = (node.total_expense / total * 100) if total > 0 else 0
        logger.debug(f"{indent_str}{node.category.name}: ${node.total_expense:.2f} ({percentage:.1f}%)")

        # Sort children by name for consistent output
        sorted_children = sorted(node.children, key=lambda x: x.total_expense, reverse=True)
        for child in sorted_children:
            self.print_tree(child, indent + 1, total)