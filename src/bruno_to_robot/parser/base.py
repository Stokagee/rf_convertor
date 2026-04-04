"""Abstract base parser for Bruno collections."""

from abc import ABC, abstractmethod
from pathlib import Path

from bruno_to_robot.models.bruno import BrunoCollection


class BaseParser(ABC):
    """Abstract base class for Bruno collection parsers."""

    @abstractmethod
    def parse(self, content: str) -> BrunoCollection:
        """Parse raw content into BrunoCollection model.

        Args:
            content: Raw file content (YAML or JSON)

        Returns:
            Validated BrunoCollection model

        Raises:
            ParseError: If content cannot be parsed
            ValidationError: If content doesn't match schema
        """
        ...

    def parse_file(self, path: str | Path) -> BrunoCollection:
        """Parse a file into BrunoCollection.

        Args:
            path: Path to Bruno collection file

        Returns:
            Validated BrunoCollection model
        """
        path = Path(path)
        content = path.read_text(encoding="utf-8")
        return self.parse(content)
