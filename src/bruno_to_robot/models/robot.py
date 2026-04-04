"""Pydantic models for Robot Framework output."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StepType(str, Enum):
    REQUEST = "request"
    ASSERTION = "assertion"
    VARIABLE = "variable"
    KEYWORD = "keyword"
    COMMENT = "comment"


class RobotVariable(BaseModel):
    """Robot Framework variable definition."""

    name: str  # e.g., "BASE_URL", "DEFAULT_HEADERS"
    value: str | dict[str, Any] | list[Any] | None
    is_dict: bool = False
    is_list: bool = False
    comment: str | None = None  # For TODOs or explanations

    def to_robot_line(self) -> str:
        """Generate the *** Variables *** line."""
        prefix = "&" if self.is_dict else "@" if self.is_list else "$"
        line = f"{prefix}{{{self.name}}}"

        if self.value is None:
            return f"{line}    # TODO: Set value"

        if self.is_dict and isinstance(self.value, dict):
            # Dictionary format: &{NAME}    key1=value1    key2=value2
            items = [f"{k}={v}" for k, v in sorted(self.value.items())]
            return f"{line}    {'    '.join(items)}"

        if isinstance(self.value, str):
            return f"{line}    {self.value}"

        return f"{line}    {self.value}"


class RobotAssertion(BaseModel):
    """Robot Framework assertion step."""

    keyword: str  # e.g., "Should Be Equal As Integers"
    args: list[str]
    comment: str | None = None


class RobotStep(BaseModel):
    """Single step in a Robot test case."""

    keyword: str
    args: list[str] = Field(default_factory=list)
    assign: str | None = None  # e.g., "${resp}"
    comment: str | None = None

    def to_robot_line(self) -> str:
        """Generate the step line."""
        parts = []

        if self.assign:
            parts.append(f"{self.assign}=")

        parts.append(self.keyword)

        if self.args:
            parts.extend(self.args)

        line = "    ".join(parts)

        if self.comment:
            line = f"{line}    # {self.comment}"

        return line


class RobotTestCase(BaseModel):
    """Robot Framework test case."""

    name: str
    tags: list[str] = Field(default_factory=list)
    setup: str | None = None
    teardown: str | None = None
    steps: list[RobotStep] = Field(default_factory=list)
    documentation: str | None = None

    def get_sorted_tags(self) -> list[str]:
        """Return sorted tags for idempotency."""
        return sorted(set(self.tags))


class RobotSuite(BaseModel):
    """Complete Robot Framework test suite."""

    name: str
    variables: list[RobotVariable] = Field(default_factory=list)
    test_cases: list[RobotTestCase] = Field(default_factory=list)
    keywords: dict[str, list[RobotStep]] = Field(default_factory=dict)
    settings: dict[str, str] = Field(default_factory=dict)
    imports: list[str] = Field(default_factory=lambda: ["RequestsLibrary"])

    def get_sorted_test_cases(self) -> list[RobotTestCase]:
        """Return test cases sorted by name for idempotency."""
        return sorted(self.test_cases, key=lambda tc: tc.name)

    def get_sorted_variables(self) -> list[RobotVariable]:
        """Return variables sorted by name for idempotency."""
        return sorted(self.variables, key=lambda v: v.name)


class RobotResource(BaseModel):
    """Robot Framework resource file (variables, keywords)."""

    name: str
    variables: list[RobotVariable] = Field(default_factory=list)
    keywords: dict[str, list[RobotStep]] = Field(default_factory=dict)
