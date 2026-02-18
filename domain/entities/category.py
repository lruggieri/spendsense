from dataclasses import dataclass


@dataclass
class Category:
    id: str
    name: str
    description: str
    parent_id: str
