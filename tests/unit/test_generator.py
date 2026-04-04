"""Unit tests for Robot Framework generator."""

import pytest

from bruno_to_robot.generator.robot_generator import RobotGenerator
from bruno_to_robot.models.robot import RobotStep, RobotSuite, RobotTestCase, RobotVariable


class TestRobotGenerator:
    """Tests for RobotGenerator."""

    @pytest.fixture
    def generator(self, tmp_path) -> RobotGenerator:
        """Create a RobotGenerator with temp templates."""
        # Create temp templates directory
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        # Write minimal template
        template_content = """*** Settings ***
Library           RequestsLibrary

*** Variables ***
{%- for var in suite.get_sorted_variables() %}
{{ var.to_robot_line() }}
{%- endfor %}

*** Test Cases ***
{%- for tc in suite.get_sorted_test_cases() %}

{{ tc.name }}
{%- for step in tc.steps %}
    {{ step.to_robot_line() }}
{%- endfor %}
{%- endfor %}
"""
        (templates_dir / "test_suite.robot.jinja").write_text(template_content)

        return RobotGenerator(template_dir=templates_dir)

    def test_generate_empty_suite(self, generator: RobotGenerator, tmp_path):
        """Generate an empty suite."""
        suite = RobotSuite(name="Empty Suite")
        output = tmp_path / "empty.robot"

        generator.generate_suite(suite, output)

        assert output.exists()
        content = output.read_text()
        assert "*** Settings ***" in content
        assert "*** Test Cases ***" in content

    def test_generate_suite_with_test_case(
        self,
        generator: RobotGenerator,
        tmp_path,
    ):
        """Generate suite with a test case."""
        suite = RobotSuite(
            name="Test Suite",
            test_cases=[
                RobotTestCase(
                    name="First Test",
                    steps=[
                        RobotStep(keyword="Log", args=["Hello"]),
                    ],
                ),
            ],
        )
        output = tmp_path / "test.robot"

        generator.generate_suite(suite, output)

        content = output.read_text()
        assert "First Test" in content
        assert "Log" in content
        assert "Hello" in content

    def test_generate_suite_with_variables(
        self,
        generator: RobotGenerator,
        tmp_path,
    ):
        """Generate suite with variables."""
        suite = RobotSuite(
            name="Variables Suite",
            variables=[
                RobotVariable(name="BASE_URL", value="https://api.example.com"),
                RobotVariable(name="API_KEY", value="secret", comment="From env"),
            ],
        )
        output = tmp_path / "vars.robot"

        generator.generate_suite(suite, output)

        content = output.read_text()
        assert "*** Variables ***" in content
        assert "BASE_URL" in content
        assert "API_KEY" in content

    def test_generate_is_idempotent(self, generator: RobotGenerator, tmp_path):
        """Same input should produce identical output."""
        suite = RobotSuite(
            name="Idempotency Test",
            test_cases=[
                RobotTestCase(
                    name="Test A",
                    steps=[RobotStep(keyword="Log", args=["A"])],
                ),
                RobotTestCase(
                    name="Test B",
                    steps=[RobotStep(keyword="Log", args=["B"])],
                ),
            ],
        )
        output = tmp_path / "idempotent.robot"

        # Generate twice
        generator.generate_suite(suite, output)
        first_content = output.read_text()

        generator.generate_suite(suite, output)
        second_content = output.read_text()

        assert first_content == second_content

    def test_generate_creates_parent_directories(
        self,
        generator: RobotGenerator,
        tmp_path,
    ):
        """Output should create parent directories if needed."""
        suite = RobotSuite(name="Nested Suite")
        output = tmp_path / "deeply" / "nested" / "path" / "test.robot"

        generator.generate_suite(suite, output)

        assert output.exists()

    def test_test_cases_sorted_by_name(self, generator: RobotGenerator, tmp_path):
        """Test cases should be sorted for idempotency."""
        suite = RobotSuite(
            name="Sorted Suite",
            test_cases=[
                RobotTestCase(
                    name="Zebra Test",
                    steps=[RobotStep(keyword="Log", args=["Z"])],
                ),
                RobotTestCase(
                    name="Alpha Test",
                    steps=[RobotStep(keyword="Log", args=["A"])],
                ),
            ],
        )
        output = tmp_path / "sorted.robot"

        generator.generate_suite(suite, output)
        content = output.read_text()

        # Alpha should come before Zebra
        alpha_pos = content.find("Alpha Test")
        zebra_pos = content.find("Zebra Test")
        assert alpha_pos < zebra_pos

    def test_variables_sorted_by_name(self, generator: RobotGenerator, tmp_path):
        """Variables should be sorted for idempotency."""
        suite = RobotSuite(
            name="Sorted Vars",
            variables=[
                RobotVariable(name="ZEBRA", value="z"),
                RobotVariable(name="ALPHA", value="a"),
            ],
        )
        output = tmp_path / "sorted_vars.robot"

        generator.generate_suite(suite, output)
        content = output.read_text()

        # ALPHA should come before ZEBRA
        alpha_pos = content.find("ALPHA")
        zebra_pos = content.find("ZEBRA")
        assert alpha_pos < zebra_pos
