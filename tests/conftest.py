"""Pytest configuration and fixtures."""

from pathlib import Path
import shutil
from uuid import uuid4

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_path() -> Path:
    """Create a temporary directory inside the workspace.

    The default system temp directory is not reliable in this environment.
    """
    base_dir = Path(__file__).parent.parent / ".tmp_testdata"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"pytest-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


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


@pytest.fixture
def bruno_export_fixture(fixtures_dir: Path) -> str:
    """Return content of a sanitized Bruno OpenCollection export fixture."""
    return (fixtures_dir / "bruno_export_nested_items.yaml").read_text()


@pytest.fixture
def bruno_export_multi_env_fixture(fixtures_dir: Path) -> str:
    """Return content of a Bruno export fixture with multiple environments."""
    return (fixtures_dir / "bruno_export_multi_env.yaml").read_text()


@pytest.fixture
def split_helper_fixture(fixtures_dir: Path) -> str:
    """Return content of a collection fixture with before-request helper scripts."""
    return (fixtures_dir / "split_helper_collection.yaml").read_text()


@pytest.fixture
def bru_single_request_path(fixtures_dir: Path) -> Path:
    """Return path to a single Bruno `.bru` request fixture."""
    return fixtures_dir / "bru_single_request" / "Get Health.bru"


@pytest.fixture
def bru_collection_dir(fixtures_dir: Path) -> Path:
    """Return path to a Bruno collection directory fixture."""
    return fixtures_dir / "bru_collection"


@pytest.fixture
def bru_native_collection_dir(fixtures_dir: Path) -> Path:
    """Return path to a Bruno collection fixture using `collection.bru` and `folder.bru`."""
    return fixtures_dir / "bru_native_collection"
