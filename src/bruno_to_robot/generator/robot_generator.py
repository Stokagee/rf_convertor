"""Generate Robot Framework .robot files from RobotSuite models."""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from bruno_to_robot.models.robot import RobotResource, RobotSuite

logger = logging.getLogger(__name__)


class RobotGenerator:
    """Generates .robot files from RobotSuite models using Jinja2 templates."""

    def __init__(self, template_dir: str | Path | None = None):
        """Initialize generator with template directory.

        Args:
            template_dir: Path to Jinja2 templates. If None, uses package templates.
        """
        if template_dir is None:
            template_dir = Path(__file__).parent.parent / "templates"

        self.template_dir = Path(template_dir)
        self.env = self._create_jinja_env()

    def _create_jinja_env(self) -> Environment:
        """Create Jinja2 environment with Robot Framework-specific settings."""
        env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(enabled_extensions=("robot.jinja",)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        # Add custom filters
        env.filters["robot_indent"] = self._robot_indent
        env.filters["robot_escape"] = self._robot_escape

        return env

    @staticmethod
    def _robot_indent(text: str, level: int = 1) -> str:
        """Indent text with Robot Framework indentation (4 spaces per level)."""
        indent = "    " * level
        return "\n".join(f"{indent}{line}" if line.strip() else line for line in text.split("\n"))

    @staticmethod
    def _robot_escape(text: str) -> str:
        """Escape special Robot Framework characters."""
        # Escape backslashes first
        text = text.replace("\\", "\\\\")
        # Escape dollar signs that aren't part of variable syntax
        # This is a simplified escape - full escape would need more context
        return text

    def generate_suite(self, suite: RobotSuite, output_path: str | Path) -> None:
        """Generate a .robot file from a RobotSuite.

        Args:
            suite: RobotSuite model to generate
            output_path: Path to output .robot file
        """
        template = self.env.get_template("test_suite.robot.jinja")

        content = template.render(
            suite=suite,
            sorted=sorted,  # Pass sorted function for idempotency
        )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if file exists and content is identical (idempotency)
        if output_path.exists():
            existing = output_path.read_text(encoding="utf-8")
            if existing == content:
                logger.info(f"No changes to {output_path}")
                return

        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Generated {output_path}")

    def generate_resource(
        self,
        resource: RobotResource,
        output_path: str | Path,
    ) -> None:
        """Generate a resource file from a RobotResource.

        Args:
            resource: RobotResource model to generate
            output_path: Path to output .robot resource file
        """
        template = self.env.get_template("resource.robot.jinja")

        content = template.render(resource=resource)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Generated resource {output_path}")

    def generate_empty(self, output_path: str | Path, name: str = "Empty Suite") -> None:
        """Generate an empty .robot file with minimal structure.

        Useful for testing or as a starting point.
        """
        suite = RobotSuite(name=name)
        self.generate_suite(suite, output_path)
