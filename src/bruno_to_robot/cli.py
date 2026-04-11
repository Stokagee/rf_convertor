"""CLI entry point for bruno-to-robot converter."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click
import yaml

from bruno_to_robot import __version__
from bruno_to_robot.cache import BuildCache, BuildOptions
from bruno_to_robot.generator.robot_generator import RobotGenerator
from bruno_to_robot.mapper.request_mapper import RequestMapper
from bruno_to_robot.models.bruno import BrunoCollection
from bruno_to_robot.models.robot import RobotResource, RobotSuite
from bruno_to_robot.output_planner import (
    LayoutRule,
    PlannedOutputFile,
    SplitMode,
    plan_collection_outputs,
)
from bruno_to_robot.parser.bru_parser import BruParser
from bruno_to_robot.parser.json_parser import JsonParser
from bruno_to_robot.parser.yaml_parser import ParseError, YamlParser

logger = logging.getLogger(__name__)

AUTO_LAYOUT_CONFIG_FILENAMES = (
    "bruno-to-robot.layout.yaml",
    "bruno-to-robot.layout.yml",
    ".bruno-to-robot.layout.yaml",
    ".bruno-to-robot.layout.yml",
)


def get_output_path_for_suite(
    output_path: Path,
    suite_name: str,
    split: bool,
    suite_count: int,
) -> Path:
    """Resolve the output path for a suite."""
    if output_path.is_dir() or split or suite_count > 1:
        return output_path / f"{suite_name.lower().replace(' ', '_')}.robot"
    return output_path


def get_output_root(
    output_path: Path,
    split: bool,
    suite_count: int,
) -> Path:
    """Resolve the directory that holds generated files and cache metadata."""
    if output_path.suffix != ".robot" or split or suite_count > 1:
        return output_path
    return output_path.parent


def resolve_output_path_for_plan(
    output_path: Path,
    output_root: Path,
    plan: PlannedOutputFile,
    split_mode: SplitMode,
    suite_count: int,
) -> Path:
    """Resolve the final output file path for one planned suite."""
    if (
        split_mode == SplitMode.SINGLE
        and output_path.suffix == ".robot"
        and not output_path.is_dir()
        and suite_count == 1
    ):
        return output_path
    return output_root / plan.relative_output_path


def should_use_split_cache(input_format: str, input_path: Path, split: bool) -> bool:
    """Return whether per-suite cache should be active for this run."""
    return input_format == "bru" and input_path.is_dir() and split


def get_helpers_for_suite(mapper: RequestMapper, suite: RobotSuite) -> list:
    """Return only helper definitions referenced by a suite."""
    helper_names = set(getattr(suite, "helper_functions", []))
    if not helper_names:
        return []
    return [
        helper
        for helper in mapper.get_helpers()
        if helper.function_name in helper_names
    ]


def build_request_context_index(
    collection: BrunoCollection,
) -> dict[str, tuple]:
    """Return a lookup from Bruno request path to request and owning folder."""
    index: dict[str, tuple] = {}

    for request in collection.requests:
        if request.path:
            index[request.path] = (request, None)

    for folder in collection.folders:
        _add_folder_requests_to_index(folder, index)

    return index


def _add_folder_requests_to_index(folder, index: dict[str, tuple]) -> None:
    """Populate request context index recursively for one folder subtree."""
    for request in folder.requests:
        if request.path:
            index[request.path] = (request, folder)

    for nested in folder.folders:
        _add_folder_requests_to_index(nested, index)


def parse_layout_rules(rule_values: tuple[str, ...]) -> list[LayoutRule]:
    """Parse repeated CLI layout rules in the form PATH_PREFIX=SPLIT_MODE."""
    rules: list[LayoutRule] = []
    allowed_modes = {mode.value for mode in SplitMode}

    for raw_rule in rule_values:
        if raw_rule.count("=") != 1:
            raise click.ClickException(
                f"Invalid --layout-rule '{raw_rule}'. Expected PATH_PREFIX=SPLIT_MODE."
            )

        path_prefix, mode_value = raw_rule.split("=", 1)
        path_prefix = path_prefix.strip()
        mode_value = mode_value.strip()

        if not path_prefix or not mode_value:
            raise click.ClickException(
                f"Invalid --layout-rule '{raw_rule}'. Expected PATH_PREFIX=SPLIT_MODE."
            )

        if mode_value not in allowed_modes:
            allowed = ", ".join(sorted(allowed_modes))
            raise click.ClickException(
                f"Invalid split mode '{mode_value}' in --layout-rule '{raw_rule}'. "
                f"Expected one of: {allowed}."
            )

        rules.append(LayoutRule(path_prefix=path_prefix, mode=SplitMode(mode_value)))

    return rules


def load_layout_config(config_path: str | Path) -> tuple[SplitMode | None, list[LayoutRule]]:
    """Load optional layout planning config from YAML/JSON-like content."""
    path = Path(config_path)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ValueError(f"Invalid layout config '{path}': {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid layout config '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Invalid layout config '{path}': expected a mapping")

    default_mode = None
    default_mode_value = data.get("default_mode")
    if default_mode_value is not None:
        try:
            default_mode = SplitMode(str(default_mode_value))
        except ValueError as exc:
            raise ValueError(
                f"Invalid layout config '{path}': unknown default_mode '{default_mode_value}'"
            ) from exc

    rules_data = data.get("rules", [])
    if rules_data is None:
        rules_data = []
    if not isinstance(rules_data, list):
        raise ValueError(f"Invalid layout config '{path}': rules must be a list")

    rules: list[LayoutRule] = []
    for index, item in enumerate(rules_data):
        if not isinstance(item, dict):
            raise ValueError(
                f"Invalid layout config '{path}': rule #{index + 1} must be a mapping"
            )

        path_prefix = item.get("path_prefix")
        mode_value = item.get("mode")
        if not path_prefix or not mode_value:
            raise ValueError(
                f"Invalid layout config '{path}': each rule needs path_prefix and mode"
            )

        try:
            mode = SplitMode(str(mode_value))
        except ValueError as exc:
            raise ValueError(
                f"Invalid layout config '{path}': unknown mode '{mode_value}' in rules"
            ) from exc

        rules.append(LayoutRule(path_prefix=str(path_prefix), mode=mode))

    return default_mode, rules


def discover_layout_config_path(input_path: Path, input_format: str) -> Path | None:
    """Return the first supported implicit layout config in a Bruno directory input."""
    if input_format != "bru" or not input_path.is_dir():
        return None

    for file_name in AUTO_LAYOUT_CONFIG_FILENAMES:
        candidate = input_path / file_name
        if candidate.exists():
            return candidate

    return None


def build_cache_entry(
    build_cache: BuildCache,
    input_root: Path,
    plan: PlannedOutputFile,
) -> dict[str, str]:
    """Build one planner-driven cache entry for a planned output file."""
    fingerprint = build_cache.compute_request_paths_fingerprint(input_root, plan.request_paths)
    return {
        "fingerprint": fingerprint,
        "mode": plan.mode.value,
    }


def resolve_suite_output_paths(
    output_path: Path,
    output_root: Path,
    planned_outputs: list[PlannedOutputFile],
    split_mode: SplitMode,
) -> list[Path]:
    """Resolve output paths for all planned suites in deterministic order."""
    suite_count = len(planned_outputs)
    return [
        resolve_output_path_for_plan(
            output_path,
            output_root,
            plan,
            split_mode,
            suite_count,
        )
        for plan in planned_outputs
    ]


def to_resource_import_path(suite_output_path: Path, resource_path: Path) -> str:
    """Return a Robot-compatible resource import path relative to one suite file."""
    try:
        relative = Path(os.path.relpath(resource_path, start=suite_output_path.parent))
        return relative.as_posix()
    except ValueError:
        # Different drives on Windows cannot be relativized.
        return resource_path.resolve().as_posix()


def build_shared_resource_from_suites(suites: list[RobotSuite]) -> RobotResource:
    """Build one shared Robot resource containing deduplicated suite variables."""
    all_vars = {}
    for suite in suites:
        for var in suite.variables:
            if var.name not in all_vars:
                all_vars[var.name] = var

    return RobotResource(
        name="Shared Variables",
        variables=sorted(all_vars.values(), key=lambda variable: variable.name),
    )


def apply_shared_resource_to_suites(
    suites: list[RobotSuite],
    suite_output_paths: list[Path],
    resource_path: Path,
) -> RobotResource:
    """Attach a shared resource import to each suite and clear in-suite variables."""
    shared_resource = build_shared_resource_from_suites(suites)

    for suite, suite_output in zip(suites, suite_output_paths, strict=True):
        suite.settings["resource"] = to_resource_import_path(suite_output, resource_path)
        suite.variables = []

    return shared_resource


def remove_empty_output_dirs(path: Path, stop_at: Path) -> None:
    """Remove empty parent directories up to the output root."""
    current = path.parent
    while current != stop_at and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def detect_format(path: Path) -> str:
    """Detect file format from extension."""
    if path.is_dir():
        has_bru_manifest = (path / "bruno.json").exists()
        has_bru_files = any(path.rglob("*.bru"))
        if has_bru_manifest or has_bru_files:
            return "bru"
        raise click.ClickException(f"Unsupported directory format: {path}")

    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return "yaml"
    elif suffix == ".json":
        return "json"
    elif suffix == ".bru":
        return "bru"
    else:
        raise click.ClickException(f"Unsupported file format: {suffix}")


@click.command(context_settings={"max_content_width": 120})
@click.version_option(version=__version__)
@click.option(
    "-i",
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=True, path_type=Path),
    required=True,
    help="Path to Bruno request, or Bruno collection file/directory",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to output .robot file or directory",
)
@click.option(
    "--format",
    "input_format",
    type=click.Choice(["bru", "json", "yaml"]),
    default=None,
    help="Force input format (auto-detected by default)",
)
@click.option(
    "--session-name",
    default="api",
    help="Name for the RequestsLibrary session (default: api)",
)
@click.option(
    "--base-url",
    default=None,
    help="Override base URL from collection",
)
@click.option(
    "--env",
    "environment_name",
    default=None,
    help="Select a named Bruno environment from config.environments",
)
@click.option(
    "--split/--no-split",
    default=False,
    help="Split into multiple .robot files per folder",
)
@click.option(
    "--split-mode",
    type=click.Choice([mode.value for mode in SplitMode]),
    default=None,
    help="Output layout mode for generated .robot files",
)
@click.option(
    "--layout-rule",
    "layout_rules",
    multiple=True,
    help="Route one source path prefix to a split mode using PATH_PREFIX=SPLIT_MODE",
)
@click.option(
    "--layout-config",
    "layout_config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    metavar="PATH",
    help="Load default split mode and layout rules from a YAML config file",
)
@click.option(
    "--resource",
    "resource_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Generate separate resource file for variables",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be generated without writing files",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity (can be used multiple times)",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Decrease verbosity (only errors)",
)
def main(
    input_path: Path,
    output_path: Path,
    input_format: str | None,
    session_name: str,
    base_url: str | None,
    environment_name: str | None,
    split: bool,
    split_mode: str | None,
    layout_rules: tuple[str, ...],
    layout_config_path: Path | None,
    resource_path: Path | None,
    dry_run: bool,
    verbose: int,
    quiet: bool,
) -> None:
    """Convert Bruno API collections to Robot Framework test suites.

    Examples:

        bruno-to-robot -i collection.yaml -o tests/api.robot

        bruno-to-robot -i collection.json -o tests/ --split

        bruno-to-robot -i input.yaml -o tests/api.robot --resource resources/variables.robot
    """
    # Configure logging
    if quiet:
        log_level = logging.ERROR
    elif verbose >= 2:
        log_level = logging.DEBUG
    elif verbose == 1:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )

    try:
        # Detect format
        if input_format is None:
            input_format = detect_format(input_path)

        logger.info(f"Parsing {input_path} as {input_format.upper()}")

        # Parse input
        if input_format == "yaml":
            parser = YamlParser(environment_name=environment_name)
        elif input_format == "json":
            parser = JsonParser(environment_name=environment_name)
        else:
            parser = BruParser(environment_name=environment_name)

        collection = parser.parse_path(input_path)
        logger.info(f"Parsed collection: {collection.name} ({len(collection.requests)} requests)")

        # Override base URL if provided
        if base_url:
            collection.base_url = base_url

        config_default_mode = None
        config_rules: list[LayoutRule] = []
        if layout_config_path is None:
            layout_config_path = discover_layout_config_path(input_path, input_format)
        if layout_config_path is not None:
            try:
                config_default_mode, config_rules = load_layout_config(layout_config_path)
            except ValueError as exc:
                raise click.ClickException(str(exc)) from exc

        resolved_split_mode = split_mode or (
            config_default_mode.value
            if config_default_mode is not None
            else (SplitMode.TOP_FOLDER.value if split else SplitMode.SINGLE.value)
        )
        parsed_layout_rules = parse_layout_rules(layout_rules)
        combined_layout_rules = [*parsed_layout_rules, *config_rules]
        if resolved_split_mode not in (
            SplitMode.SINGLE.value,
            SplitMode.TOP_FOLDER.value,
            SplitMode.REQUEST_TREE.value,
            SplitMode.FLOW_FOLDER.value,
        ):
            raise click.ClickException(
                f"Split mode '{resolved_split_mode}' is planned but not wired to generation yet"
            )

        resolved_split_mode_enum = SplitMode(resolved_split_mode)
        planned_outputs = plan_collection_outputs(
            collection,
            default_mode=resolved_split_mode_enum,
            rules=combined_layout_rules,
        )

        split = resolved_split_mode_enum == SplitMode.TOP_FOLDER

        # Map to Robot model
        mapper = RequestMapper(session_name=session_name)
        if resolved_split_mode_enum in (SplitMode.REQUEST_TREE, SplitMode.FLOW_FOLDER):
            mapper.prepare_collection(collection)
            request_index = build_request_context_index(collection)
            suites = []
            for plan in planned_outputs:
                if not plan.request_paths:
                    raise click.ClickException("Planned output has no source request paths")

                request_contexts = []
                for request_path in plan.request_paths:
                    if request_path not in request_index:
                        raise click.ClickException(
                            f"Planned request path not found in collection: {request_path}"
                        )
                    request_contexts.append(request_index[request_path])

                if plan.mode == SplitMode.REQUEST_TREE:
                    if len(request_contexts) != 1:
                        raise click.ClickException(
                            "Request-tree mode expects exactly one source request per planned output"
                        )
                    request, folder = request_contexts[0]
                    suites.append(
                        mapper.map_request_suite(
                            collection,
                            request=request,
                            folder=folder,
                        )
                    )
                elif plan.mode == SplitMode.FLOW_FOLDER:
                    first_request, folder = request_contexts[0]
                    if folder is None:
                        raise click.ClickException(
                            "Flow-folder mode requires requests that belong to a Bruno folder"
                        )
                    requests = [request for request, _folder in request_contexts]
                    suites.append(
                        mapper.map_flow_suite(
                            collection,
                            requests=requests,
                            folder=folder,
                        )
                    )
                else:
                    raise click.ClickException(
                        f"Unsupported planned mode in planner-backed mapping: {plan.mode.value}"
                    )
        else:
            suites = mapper.map_collection(collection, split_by_folder=split)
            if len(planned_outputs) != len(suites):
                raise click.ClickException(
                    "Planned output count does not match mapped suite count for compatibility mode"
                )

        logger.info(f"Generated {len(suites)} suite(s)")

        # Generate output
        generator = RobotGenerator()
        output_root = get_output_root(output_path, split, len(suites))
        suite_output_paths = resolve_suite_output_paths(
            output_path,
            output_root,
            planned_outputs,
            resolved_split_mode_enum,
        )
        shared_resource = None
        if resource_path:
            shared_resource = apply_shared_resource_to_suites(
                suites,
                suite_output_paths,
                resource_path,
            )

        if dry_run:
            click.echo("Dry run - would generate:")
            for suite, out_file in zip(suites, suite_output_paths, strict=True):
                click.echo(f"  - {out_file}: {len(suite.test_cases)} tests")
            if resource_path:
                click.echo(f"  - {resource_path}: shared variables resource")
            return

        output_root.mkdir(parents=True, exist_ok=True)

        build_cache = None
        build_signature = None
        cached_manifest = {}
        next_manifest_entries: dict[str, dict[str, str]] = {}

        if should_use_split_cache(input_format, input_path, resolved_split_mode_enum != SplitMode.SINGLE):
            build_cache = BuildCache()
            build_signature = build_cache.compute_build_signature(
                input_path,
                BuildOptions(
                    environment_name=environment_name,
                    split_by_folder=split,
                    split_mode=resolved_split_mode_enum.value,
                    layout_rules=tuple(
                        [*layout_rules, *[
                            f"{rule.path_prefix}={rule.mode.value}" for rule in config_rules
                        ]]
                    ),
                    base_url_override=base_url,
                    session_name=session_name,
                    input_format=input_format,
                    resource_path=str(resource_path) if resource_path else None,
                ),
            )
            cached_manifest = build_cache.load_manifest(output_root)

        # Generate files
        for suite, plan, out_file in zip(
            suites,
            planned_outputs,
            suite_output_paths,
            strict=True,
        ):

            # Update suite's helper_library to match output file name
            if suite.helper_library:
                suite.helper_library = f"{out_file.stem}_helpers"

            if build_cache is not None and build_signature is not None:
                manifest_key = out_file.relative_to(output_root).as_posix()
                cache_entry = build_cache_entry(build_cache, input_path, plan)
                next_manifest_entries[manifest_key] = cache_entry

                previous_entry = cached_manifest.get("suites", {}).get(manifest_key)
                if (
                    cached_manifest.get("build_signature") == build_signature
                    and previous_entry == cache_entry
                    and out_file.exists()
                ):
                    click.echo(f"Cached: {out_file}")
                    continue

            generator.generate_suite(suite, out_file)
            click.echo(f"Generated: {out_file}")

        if build_cache is not None and build_signature is not None:
            stale_outputs = set(cached_manifest.get("suites", {})) - set(next_manifest_entries)
            for stale_name in sorted(stale_outputs):
                stale_file = output_root / stale_name
                if stale_file.exists():
                    stale_file.unlink()
                    click.echo(f"Removed stale: {stale_file}")
                    remove_empty_output_dirs(stale_file, output_root)
                stale_helper = stale_file.with_name(f"{stale_file.stem}_helpers.py")
                if stale_helper.exists():
                    stale_helper.unlink()
                    click.echo(f"Removed stale: {stale_helper}")
                    remove_empty_output_dirs(stale_helper, output_root)
            build_cache.write_manifest(output_root, build_signature, next_manifest_entries)

        # Generate helper library per suite if needed
        for suite, suite_out_file in zip(
            suites,
            suite_output_paths,
            strict=True,
        ):
            if not suite.helper_library:
                continue

            helper_file = suite_out_file.parent / f"{suite.helper_library}.py"
            suite_helpers = get_helpers_for_suite(mapper, suite)
            generator.generate_helper_library(
                suite_helpers,
                helper_file,
                suite_name=suite.name,
            )
            if suite_helpers:
                click.echo(f"Generated helper: {helper_file}")

        # Generate shared resource file if requested
        if resource_path and shared_resource is not None:
            generator.generate_resource(shared_resource, resource_path)
            click.echo(f"Generated resource: {resource_path}")

        click.echo(f"\nConversion complete: {sum(len(s.test_cases) for s in suites)} test cases")

    except click.ClickException:
        raise
    except ParseError as e:
        logger.error(f"Parse error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
