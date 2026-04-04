"""Unit tests for request mapper."""

import pytest

from bruno_to_robot.mapper.request_mapper import RequestMapper
from bruno_to_robot.parser.yaml_parser import YamlParser


class TestRequestMapper:
    """Tests for RequestMapper."""

    @pytest.fixture
    def mapper(self) -> RequestMapper:
        """Create a RequestMapper instance."""
        return RequestMapper(session_name="test_api")

    def test_map_simple_get(self, simple_get_fixture: str, mapper: RequestMapper):
        """Map a simple GET request."""
        parser = YamlParser()
        collection = parser.parse(simple_get_fixture)

        suites = mapper.map_collection(collection, split_by_folder=False)

        assert len(suites) == 1
        suite = suites[0]
        assert len(suite.test_cases) == 1

        tc = suite.test_cases[0]
        assert tc.name == "Get Users"
        assert len(tc.steps) >= 1

        # First step should be the request
        request_step = tc.steps[0]
        assert "GET On Session" in request_step.keyword
        assert "test_api" in request_step.args

    def test_map_simple_post(self, simple_post_fixture: str, mapper: RequestMapper):
        """Map a POST request with body."""
        parser = YamlParser()
        collection = parser.parse(simple_post_fixture)

        suites = mapper.map_collection(collection, split_by_folder=False)
        tc = suites[0].test_cases[0]

        request_step = tc.steps[0]
        assert "POST On Session" in request_step.keyword

        # Should have body argument
        body_arg = next((a for a in request_step.args if a.startswith("json=")), None)
        assert body_arg is not None

    def test_map_collection_with_folders(
        self,
        collection_fixture: str,
        mapper: RequestMapper,
    ):
        """Map collection with folders to separate suites."""
        parser = YamlParser()
        collection = parser.parse(collection_fixture)

        suites = mapper.map_collection(collection, split_by_folder=True)

        # Should have suites for each folder + root
        assert len(suites) >= 2

        # All suites should have test cases
        for suite in suites:
            assert len(suite.test_cases) >= 1

    def test_map_extracts_variables(
        self,
        collection_fixture: str,
        mapper: RequestMapper,
    ):
        """Variables should be extracted to RobotVariables."""
        parser = YamlParser()
        collection = parser.parse(collection_fixture)

        suites = mapper.map_collection(collection, split_by_folder=False)
        suite = suites[0]

        # Should have BASE_URL variable
        base_url_var = next(
            (v for v in suite.variables if v.name == "BASE_URL"),
            None,
        )
        assert base_url_var is not None

    def test_map_generates_tags(
        self,
        collection_fixture: str,
        mapper: RequestMapper,
    ):
        """Test cases should have appropriate tags."""
        parser = YamlParser()
        collection = parser.parse(collection_fixture)

        suites = mapper.map_collection(collection, split_by_folder=False)

        for suite in suites:
            for tc in suite.test_cases:
                assert "api" in tc.tags
                # Should have method tag
                method_tags = {"get", "post", "put", "delete", "patch"}
                assert any(tag in method_tags for tag in tc.tags)

    def test_map_sanitizes_names(self, simple_get_fixture: str, mapper: RequestMapper):
        """Test case names should be sanitized."""
        parser = YamlParser()
        collection = parser.parse(simple_get_fixture)

        suites = mapper.map_collection(collection, split_by_folder=False)

        for suite in suites:
            for tc in suite.test_cases:
                # Should not contain special characters
                assert all(c.isalnum() or c.isspace() for c in tc.name)

    def test_map_generates_assertion_steps(
        self,
        simple_post_fixture: str,
        mapper: RequestMapper,
    ):
        """Assertion scripts should be converted to Robot steps."""
        parser = YamlParser()
        collection = parser.parse(simple_post_fixture)

        suites = mapper.map_collection(collection, split_by_folder=False)
        tc = suites[0].test_cases[0]

        # Should have assertion step(s)
        assertion_keywords = {"Should Be Equal", "Should Be True", "Should Contain"}
        has_assertion = any(
            any(kw in step.keyword for kw in assertion_keywords)
            for step in tc.steps
        )
        assert has_assertion or len(tc.steps) > 1  # Either assertion or multiple steps
