"""
Regexp entity model.

Represents a regex pattern used for transaction classification.
"""

from dataclasses import dataclass


@dataclass
class Regexp:
    """
    Regex pattern entity for transaction classification.

    Attributes:
        id: Unique identifier for the pattern
        raw: The compiled regex pattern string
        name: Human-readable pattern name
        visual_description: JSON-encoded visual rules from pattern builder UI
        internal_category: Category ID to assign when pattern matches
        order_index: Pattern priority (lower value = higher priority)
    """
    id: str
    raw: str
    name: str
    visual_description: str
    internal_category: str
    order_index: int
