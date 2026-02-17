from abc import ABC, abstractmethod


class ManualAssignmentSource(ABC):
    """Abstract base class for manual category assignment data sources."""

    @abstractmethod
    def get_assignments(self) -> dict[str, str]:
        """
        Fetch manual category assignments.

        Returns:
            dict[str, str]: A dictionary mapping transaction IDs to category IDs
        """
