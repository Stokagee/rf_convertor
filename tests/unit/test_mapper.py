"""Unit tests for request mapper."""

import pytest

from bruno_to_robot.mapper.request_mapper import RequestMapper
from bruno_to_robot.models.bruno import (
    BrunoCollection,
    BrunoFolder,
    BrunoHttp,
    BrunoRequest,
    BrunoVariable,
)
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
        assert "alias=test_api" in request_step.args
        assert "url=/users" in request_step.args
        assert "expected_status=anything" in request_step.args

    def test_map_simple_post(self, simple_post_fixture: str, mapper: RequestMapper):
        """Map a POST request with body."""
        parser = YamlParser()
        collection = parser.parse(simple_post_fixture)

        suites = mapper.map_collection(collection, split_by_folder=False)
        tc = suites[0].test_cases[0]

        # Find the request step (should be POST On Session)
        request_step = next((s for s in tc.steps if "On Session" in s.keyword), None)
        assert request_step is not None
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

    def test_map_single_suite_includes_nested_folder_requests(
        self,
        bruno_export_fixture: str,
        mapper: RequestMapper,
    ):
        """Single-suite mapping should include requests nested in child folders."""
        parser = YamlParser()
        collection = parser.parse(bruno_export_fixture)

        suites = mapper.map_collection(collection, split_by_folder=False)

        assert len(suites) == 1
        assert [tc.name for tc in suites[0].test_cases] == [
            "Health Check",
            "Get Oauth2 Token",
            "List Customers",
        ]

    def test_map_skips_disabled_collection_variables(self, mapper: RequestMapper):
        """Disabled variables must not be emitted into generated Robot suites."""
        collection = BrunoCollection(
            name="Disabled Vars",
            variables=[
                BrunoVariable(name="baseUrl", value="https://enabled.example.com", enabled=True),
                BrunoVariable(name="apiKey", value="secret-value", enabled=False),
            ],
            base_url="https://enabled.example.com",
            requests=[
                BrunoRequest(
                    name="Health",
                    http=BrunoHttp(method="GET", url="https://enabled.example.com/health"),
                )
            ],
        )

        suites = mapper.map_collection(collection, split_by_folder=False)

        variable_names = {variable.name for variable in suites[0].variables}
        assert "BASE_URL" in variable_names
        assert "APIKEY" not in variable_names

    def test_map_request_suite_creates_single_test_case_for_selected_request(
        self,
        bruno_export_fixture: str,
        mapper: RequestMapper,
    ):
        """Request-level suite mapping should isolate one request into one suite."""
        parser = YamlParser()
        collection = parser.parse(bruno_export_fixture)
        target_folder = collection.folders[0].folders[0]
        target_request = target_folder.requests[0]

        suite = mapper.map_request_suite(
            collection,
            request=target_request,
            folder=target_folder,
        )

        assert suite.name == "Get Oauth2 Token"
        assert [tc.name for tc in suite.test_cases] == ["Get Oauth2 Token"]
        assert suite.settings["suite_setup"] == "Create All Sessions"

    def test_map_flow_suite_preserves_input_request_order(self, mapper: RequestMapper):
        """Flow suite mapping should preserve the provided request order."""
        collection = BrunoCollection(
            name="Ordered Flow",
            base_url="https://api.example.com",
        )
        flow_folder = BrunoFolder(
            name="Client Flow",
            path="Scenario Batch/Client Flow",
            requests=[
                BrunoRequest(
                    name="Z Step",
                    seq=2,
                    http=BrunoHttp(method="GET", url="https://api.example.com/z"),
                    path="Scenario Batch/Client Flow/02 Z Step.bru",
                ),
                BrunoRequest(
                    name="A Step",
                    seq=1,
                    http=BrunoHttp(method="GET", url="https://api.example.com/a"),
                    path="Scenario Batch/Client Flow/01 A Step.bru",
                ),
            ],
        )
        collection.folders.append(flow_folder)

        mapper.prepare_collection(collection)
        suite = mapper.map_flow_suite(
            collection,
            requests=[flow_folder.requests[1], flow_folder.requests[0]],
            folder=flow_folder,
        )

        assert suite.name == "Client Flow"
        assert suite.preserve_test_order is True
        assert [tc.name for tc in suite.get_sorted_test_cases()] == ["A Step", "Z Step"]
