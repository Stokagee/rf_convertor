"""CLI entry point for bruno-to-robot converter."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from bruno_to_robot import __version__
from bruno_to_robot.generator.robot_generator import RobotGenerator
from bruno_to_robot.mapper.request_mapper import RequestMapper
from bruno_to_robot.parser.json_parser import JsonParser
from bruno_to_robot.parser.yaml_parser import ParseError, YamlParser

logger = logging.getLogger(__name__)


def detect_format(path: Path) -> str:
    """Detect file format from extension."""
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return "yaml"
    elif suffix == ".json":
        return "json"
    else:
        raise click.ClickException(f"Unsupported file format: {suffix}")


@click.command()
@click.version_option(version=__version__)
@click.option(
    "-i",
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to Bruno collection file (YAML or JSON)",
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
    type=click.Choice(["json", "yaml"]),
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
    "--split/--no-split",
    default=False,
    help="Split into multiple .robot files per folder",
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
    split: bool,
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
        parser = YamlParser() if input_format == "yaml" else JsonParser()
        collection = parser.parse_file(input_path)
        logger.info(f"Parsed collection: {collection.name} ({len(collection.requests)} requests)")

        # Override base URL if provided
        if base_url:
            collection.base_url = base_url

        # Map to Robot model
        mapper = RequestMapper(session_name=session_name)
        suites = mapper.map_collection(collection, split_by_folder=split)

        logger.info(f"Generated {len(suites)} suite(s)")

        # Generate output
        generator = RobotGenerator()

        if dry_run:
            click.echo("Dry run - would generate:")
            for suite in suites:
                if output_path.is_dir() or split or len(suites) > 1:
                    out_file = output_path / f"{suite.name.lower().replace(' ', '_')}.robot"
                else:
                    out_file = output_path
                click.echo(f"  - {out_file}: {len(suite.test_cases)} tests")
            return

        # Ensure output directory exists
        if output_path.suffix != ".robot":
            output_path.mkdir(parents=True, exist_ok=True)

        # Generate files
        for suite in suites:
            if output_path.is_dir() or split or len(suites) > 1:
                out_file = output_path / f"{suite.name.lower().replace(' ', '_')}.robot"
            else:
                out_file = output_path

            generator.generate_suite(suite, out_file)
            click.echo(f"Generated: {out_file}")

        # Generate resource file if requested
        if resource_path:
            from bruno_to_robot.models.robot import RobotResource

            # Collect all variables from all suites
            all_vars = {}
            for suite in suites:
                for var in suite.variables:
                    if var.name not in all_vars:
                        all_vars[var.name] = var

            resource = RobotResource(
                name="Shared Variables",
                variables=list(all_vars.values()),
            )
            generator.generate_resource(resource, resource_path)
            click.echo(f"Generated resource: {resource_path}")

        click.echo(f"\nConversion complete: {sum(len(s.test_cases) for s in suites)} test cases")

    except ParseError as e:
        logger.error(f"Parse error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
