"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_get_fixture(fixtures_dir: Path) -> str:
    """Return content of simple_get.yaml fixture."""
    return (fixtures_dir / "simple_get.yaml").read_text()


@pytest.fixture
def simple_post_fixture(fixtures_dir: Path) -> str:
    """Return content of simple_post.yaml fixture."""
    return (fixtures_dir / "simple_post.yaml").read_text()


@pytest.fixture
def collection_fixture(fixtures_dir: Path) -> str:
    """Return content of collection.yaml fixture."""
    return (fixtures_dir / "collection.yaml").read_text()
