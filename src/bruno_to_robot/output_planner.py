"""Planner for mapping Bruno trees to output file layouts."""

from __future__ import annotations

import fnmatch
import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from bruno_to_robot.models.bruno import BrunoCollection, BrunoFolder, BrunoRequest


class SplitMode(str, Enum):
    """Supported output layout strategies."""

    SINGLE = "single"
    TOP_FOLDER = "top-folder"
    REQUEST_TREE = "request-tree"
    FLOW_FOLDER = "flow-folder"


@dataclass(frozen=True, slots=True)
class LayoutRule:
    """Routing rule for selecting a split mode by source path prefix."""

    path_prefix: str
    mode: SplitMode


@dataclass(frozen=True, slots=True)
class PlannedOutputFile:
    """Planned output file produced by the output planner."""

    relative_output_path: Path
    mode: SplitMode
    request_paths: list[str]
    preserve_test_order: bool


def plan_collection_outputs(
    collection: BrunoCollection,
    default_mode: SplitMode,
    rules: list[LayoutRule],
) -> list[PlannedOutputFile]:
    """Plan output files for a parsed Bruno collection."""
    planned: list[PlannedOutputFile] = []

    if default_mode == SplitMode.SINGLE:
        request_paths = [
            request.path
            for request in _iter_requests(collection)
            if request.path
        ]
        planned.append(
            PlannedOutputFile(
                relative_output_path=Path(f"{_slugify(collection.name)}.robot"),
                mode=SplitMode.SINGLE,
                request_paths=request_paths,
                preserve_test_order=False,
            )
        )
        return _deduplicate_output_paths(planned)

    if default_mode == SplitMode.TOP_FOLDER:
        planned.extend(_plan_top_folder_outputs(collection))
        return _deduplicate_output_paths(planned)

    planned.extend(_plan_request_tree_requests(collection.requests))
    for folder in collection.folders:
        _plan_folder(folder, rules, default_mode, planned)

    sorted_plans = sorted(planned, key=lambda plan: plan.relative_output_path.as_posix().lower())
    return _deduplicate_output_paths(sorted_plans)


def _plan_folder(
    folder: BrunoFolder,
    rules: list[LayoutRule],
    default_mode: SplitMode,
    planned: list[PlannedOutputFile],
) -> None:
    """Plan outputs for one Bruno folder subtree."""
    mode = _resolve_mode(folder.path, rules, default_mode)

    if mode == SplitMode.FLOW_FOLDER:
        if folder.requests:
            planned.append(_plan_flow_folder_output(folder))
        for nested in folder.folders:
            _plan_folder(nested, rules, mode, planned)
        return

    if mode == SplitMode.REQUEST_TREE:
        planned.extend(_plan_request_tree_requests(folder.requests))
        for nested in folder.folders:
            _plan_folder(nested, rules, mode, planned)
        return

    if mode == SplitMode.TOP_FOLDER:
        planned.append(_plan_top_folder_output(folder))
        return

    raise ValueError(f"Unsupported split mode for folder planning: {mode}")


def _plan_request_tree_requests(requests: list[BrunoRequest]) -> list[PlannedOutputFile]:
    """Plan one output file per request."""
    planned = []
    for request in requests:
        request_path = request.path or f"{request.name}.bru"
        source_path = Path(request_path)
        output_path = source_path.with_suffix(".robot")
        planned.append(
            PlannedOutputFile(
                relative_output_path=_slugify_path(output_path),
                mode=SplitMode.REQUEST_TREE,
                request_paths=[request_path],
                preserve_test_order=False,
            )
        )
    return planned


def _plan_flow_folder_output(folder: BrunoFolder) -> PlannedOutputFile:
    """Plan one output file per folder of ordered requests."""
    request_paths = [
        request.path
        for request in sorted(
            folder.requests,
            key=lambda request: (
                request.seq,
                (request.path or request.name).lower(),
            ),
        )
        if request.path
    ]
    return PlannedOutputFile(
        relative_output_path=_slugify_path(Path(folder.path).with_suffix(".robot")),
        mode=SplitMode.FLOW_FOLDER,
        request_paths=request_paths,
        preserve_test_order=True,
    )


def _plan_top_folder_outputs(collection: BrunoCollection) -> list[PlannedOutputFile]:
    """Plan compatibility outputs that match the current top-folder split behavior."""
    planned = []
    for folder in collection.folders:
        planned.append(_plan_top_folder_output(folder))
    if collection.requests:
        request_paths = [request.path for request in collection.requests if request.path]
        planned.append(
            PlannedOutputFile(
                relative_output_path=Path(f"{_slugify(collection.name)}.robot"),
                mode=SplitMode.TOP_FOLDER,
                request_paths=request_paths,
                preserve_test_order=False,
            )
        )
    return planned


def _plan_top_folder_output(folder: BrunoFolder) -> PlannedOutputFile:
    """Plan one compatibility suite per top-level folder."""
    request_paths = [
        request.path
        for request in _iter_folder_requests(folder)
        if request.path
    ]
    return PlannedOutputFile(
        relative_output_path=Path(f"{_slugify(folder.name)}.robot"),
        mode=SplitMode.TOP_FOLDER,
        request_paths=request_paths,
        preserve_test_order=False,
    )


def _iter_requests(collection: BrunoCollection) -> list[BrunoRequest]:
    """Return all requests in the collection tree."""
    requests = list(collection.requests)
    for folder in collection.folders:
        requests.extend(_iter_folder_requests(folder))
    return requests


def _iter_folder_requests(folder: BrunoFolder) -> list[BrunoRequest]:
    """Return all requests in one folder subtree."""
    requests = list(folder.requests)
    for nested in folder.folders:
        requests.extend(_iter_folder_requests(nested))
    return requests


def _resolve_mode(path: str, rules: list[LayoutRule], default_mode: SplitMode) -> SplitMode:
    """Resolve a split mode for a source path."""
    normalized_path = _normalize_source_path(path)
    for rule in rules:
        prefix = _normalize_source_path(rule.path_prefix)
        if _path_matches_rule(normalized_path, prefix):
            return rule.mode
    return default_mode


def _path_matches_rule(path: str, rule_path: str) -> bool:
    """Return whether a source path matches one routing rule."""
    normalized_path = path.casefold()
    normalized_rule = rule_path.casefold()

    if _is_glob_rule(normalized_rule):
        return fnmatch.fnmatchcase(normalized_path, normalized_rule)

    return normalized_path == normalized_rule or normalized_path.startswith(
        f"{normalized_rule}/"
    )


def _is_glob_rule(rule_path: str) -> bool:
    """Return whether a layout rule path uses wildcard syntax."""
    return any(char in rule_path for char in ("*", "?", "["))


def _normalize_source_path(path: str) -> str:
    """Normalize a Bruno source path for deterministic matching."""
    return Path(path).as_posix().strip("/")


def _slugify_path(path: Path) -> Path:
    """Slugify every part of a relative output path."""
    parent_parts = [_slugify(part) for part in path.parent.parts if part not in ("", ".")]
    stem = _slugify(path.stem)
    return Path(*parent_parts, f"{stem}{path.suffix.lower()}")


def _slugify(value: str) -> str:
    """Convert a source name into a stable output slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "unnamed"


def _deduplicate_output_paths(plans: list[PlannedOutputFile]) -> list[PlannedOutputFile]:
    """Ensure planner output paths are unique, including on case-insensitive filesystems."""
    resolved: list[PlannedOutputFile] = []
    seen_paths: set[str] = set()

    for plan in plans:
        output_path = plan.relative_output_path
        normalized = output_path.as_posix().lower()

        if normalized in seen_paths:
            output_path = _append_hash_suffix(output_path, _plan_identity(plan))
            normalized = output_path.as_posix().lower()
            counter = 1
            while normalized in seen_paths:
                output_path = _append_hash_suffix(output_path, f"{_plan_identity(plan)}:{counter}")
                normalized = output_path.as_posix().lower()
                counter += 1

            plan = PlannedOutputFile(
                relative_output_path=output_path,
                mode=plan.mode,
                request_paths=plan.request_paths,
                preserve_test_order=plan.preserve_test_order,
            )

        seen_paths.add(normalized)
        resolved.append(plan)

    return resolved


def _append_hash_suffix(path: Path, source_identity: str) -> Path:
    """Append a short deterministic hash to a file stem."""
    suffix = hashlib.sha1(source_identity.encode("utf-8")).hexdigest()[:8]
    return path.with_name(f"{path.stem}_{suffix}{path.suffix}")


def _plan_identity(plan: PlannedOutputFile) -> str:
    """Build a stable identity for hash-based collision fallback."""
    request_part = "|".join(plan.request_paths)
    return f"{plan.mode.value}:{request_part}:{plan.relative_output_path.as_posix()}"
