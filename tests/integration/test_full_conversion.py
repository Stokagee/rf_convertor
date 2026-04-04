"""Integration tests for full conversion pipeline."""

from pathlib import Path

import pytest

from bruno_to_robot.generator.robot_generator import RobotGenerator
from bruno_to_robot.mapper.request_mapper import RequestMapper
from bruno_to_robot.parser.yaml_parser import YamlParser


class TestFullConversion:
    """End-to-end conversion tests."""

    @pytest.fixture
    def templates_dir(self, tmp_path: Path) -> Path:
        """Create templates directory with proper templates."""
        templates = tmp_path / "templates"
        templates.mkdir()

        # Main suite template
        suite_template = """*** Settings ***
Library           RequestsLibrary
{%- if suite.settings.get("resource") %}
Resource          {{ suite.settings["resource"] }}
{%- endif %}

*** Variables ***
{%- for var in suite.get_sorted_variables() %}
{{ var.to_robot_line() }}
{%- endfor %}

*** Test Cases ***
{%- for tc in suite.get_sorted_test_cases() %}

{{ tc.name }}
{%- if tc.documentation %}
    [Documentation]    {{ tc.documentation }}
{%- endif %}
{%- if tc.tags %}
    [Tags]    {{ tc.get_sorted_tags() | join('    ') }}
{%- endif %}
{%- for step in tc.steps %}
    {{ step.to_robot_line() }}
{%- endfor %}
{%- endfor %}
"""
        (templates / "test_suite.robot.jinja").write_text(suite_template)

        return templates

    def test_convert_simple_get(
        self,
        simple_get_fixture: str,
        templates_dir: Path,
        tmp_path: Path,
    ):
        """Convert simple GET request to valid .robot file."""
        # Parse
        parser = YamlParser()
        collection = parser.parse(simple_get_fixture)

        # Map
        mapper = RequestMapper(session_name="api")
        suites = mapper.map_collection(collection, split_by_folder=False)

        # Generate
        generator = RobotGenerator(template_dir=templates_dir)
        output = tmp_path / "get_test.robot"
        generator.generate_suite(suites[0], output)

        # Verify
        assert output.exists()
        content = output.read_text()

        # Basic structure
        assert "*** Settings ***" in content
        assert "*** Variables ***" in content
        assert "*** Test Cases ***" in content

        # Test case exists
        assert "Get Users" in content

        # Request keyword
        assert "GET On Session" in content
        assert "api" in content

    def test_convert_simple_post(
        self,
        simple_post_fixture: str,
        templates_dir: Path,
        tmp_path: Path,
    ):
        """Convert POST request with body and assertions."""
        parser = YamlParser()
        collection = parser.parse(simple_post_fixture)

        mapper = RequestMapper(session_name="api")
        suites = mapper.map_collection(collection, split_by_folder=False)

        generator = RobotGenerator(template_dir=templates_dir)
        output = tmp_path / "post_test.robot"
        generator.generate_suite(suites[0], output)

        content = output.read_text()

        # POST keyword
        assert "POST On Session" in content

        # JSON body
        assert "json=" in content.lower()

        # Assertion for status code
        assert "Should Be Equal" in content or "status_code" in content

    def test_convert_full_collection(
        self,
        collection_fixture: str,
        templates_dir: Path,
        tmp_path: Path,
    ):
        """Convert full collection with folders."""
        parser = YamlParser()
        collection = parser.parse(collection_fixture)

        mapper = RequestMapper(session_name="api")
        suites = mapper.map_collection(collection, split_by_folder=True)

        generator = RobotGenerator(template_dir=templates_dir)

        # Generate all suites
        for suite in suites:
            output = tmp_path / f"{suite.name.lower().replace(' ', '_')}.robot"
            generator.generate_suite(suite, output)

        # Verify multiple files created
        robot_files = list(tmp_path.glob("*.robot"))
        assert len(robot_files) >= 2

        # Each file should have valid structure
        for rf in robot_files:
            content = rf.read_text()
            assert "*** Settings ***" in content
            assert "*** Test Cases ***" in content

    def test_robot_syntax_valid(
        self,
        simple_get_fixture: str,
        templates_dir: Path,
        tmp_path: Path,
    ):
        """Generated .robot should have valid syntax (basic check)."""
        parser = YamlParser()
        collection = parser.parse(simple_get_fixture)

        mapper = RequestMapper()
        suites = mapper.map_collection(collection)

        generator = RobotGenerator(template_dir=templates_dir)
        output = tmp_path / "syntax_test.robot"
        generator.generate_suite(suites[0], output)

        content = output.read_text()

        # Basic syntax checks
        lines = content.split("\n")

        # Should start with section header
        assert any(line.startswith("*** ") for line in lines)

        # Section headers should be properly formatted
        for line in lines:
            if line.startswith("***"):
                assert line.endswith("***") or line.rstrip().endswith("***")

        # No empty section content (except for empty suite)
        # Indentation should be consistent (4 spaces)
        for line in lines:
            if line and not line.startswith("***") and line[0] == " ":
                # Count leading spaces - should be multiple of 4
                leading = len(line) - len(line.lstrip())
                assert leading % 4 == 0, f"Bad indentation: {line!r}"
