"""JSON parser for Bruno collection format."""

from __future__ import annotations

import json
import logging

from bruno_to_robot.models.bruno import BrunoCollection

from .base import BaseParser
from .yaml_parser import ParseError, YamlParser

logger = logging.getLogger(__name__)


class JsonParser(BaseParser):
    """Parser for JSON-based Bruno collections.

    Delegates most parsing logic to YamlParser since the data model is the same.
    """

    def __init__(self, environment_name: str | None = None) -> None:
        self._yaml_parser = YamlParser(environment_name=environment_name)

    def parse(self, content: str) -> BrunoCollection:
        """Parse JSON content into BrunoCollection."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ParseError(f"Invalid JSON: {e}") from e

        if data is None:
            raise ParseError("Empty JSON content")

        if not isinstance(data, dict):
            raise ParseError(f"Expected dict, got {type(data).__name__}")

        return self._yaml_parser._parse_collection(data)
