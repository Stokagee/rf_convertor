"""Unit tests for selecting a single Bruno environment during parsing."""

import pytest

from bruno_to_robot.parser.yaml_parser import ParseError, YamlParser


class TestYamlParserEnvironmentSelection:
    """Tests for choosing one environment from Bruno OpenCollection exports."""

    def test_parse_uses_first_environment_by_default(
        self,
        bruno_export_multi_env_fixture: str,
    ):
        """Parser should keep backward-compatible default selection."""
        parser = YamlParser()

        collection = parser.parse(bruno_export_multi_env_fixture)

        assert collection.base_url == "https://dev.example.com"
        assert {variable.name for variable in collection.variables} == {
            "baseUrl",
            "username",
        }

    def test_parse_can_select_named_environment(
        self,
        bruno_export_multi_env_fixture: str,
    ):
        """Parser should expose variables only from the requested environment."""
        parser = YamlParser(environment_name="test_client")

        collection = parser.parse(bruno_export_multi_env_fixture)

        assert collection.base_url == "https://client.example.com"
        assert {variable.name for variable in collection.variables} == {
            "baseUrl",
            "baseUrlInternal",
            "accessToken",
            "clientCert",
        }

    def test_parse_raises_for_unknown_environment(
        self,
        bruno_export_multi_env_fixture: str,
    ):
        """Unknown environment names should fail fast with a parse error."""
        parser = YamlParser(environment_name="missing-env")

        with pytest.raises(ParseError, match="missing-env"):
            parser.parse(bruno_export_multi_env_fixture)

    def test_parse_skips_disabled_variables_from_selected_environment(self):
        """Disabled OpenCollection env vars should not be applied."""
        parser = YamlParser(environment_name="test_client")

        collection = parser.parse(
            """
name: Demo Collection
config:
  environments:
    - name: test_client
      variables:
        - name: baseUrl
          value: https://disabled.example.com
          enabled: false
        - name: apiKey
          value: client-secret
"""
        )

        assert collection.base_url is None
        assert {variable.name for variable in collection.variables} == {"apiKey"}
