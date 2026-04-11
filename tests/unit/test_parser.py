"""Unit tests for Bruno parsers."""

import pytest

from bruno_to_robot.parser.yaml_parser import ParseError, YamlParser
from bruno_to_robot.parser.json_parser import JsonParser


class TestYamlParser:
    """Tests for YamlParser."""

    def test_parse_simple_get(self, simple_get_fixture: str):
        """Parse a simple GET request."""
        parser = YamlParser()
        collection = parser.parse(simple_get_fixture)

        assert collection.name == "Get Users"
        assert len(collection.requests) == 1

        request = collection.requests[0]
        assert request.name == "Get Users"
        assert request.http.method.value == "GET"
        assert request.http.url == "https://api.example.com/users"

    def test_parse_simple_post(self, simple_post_fixture: str):
        """Parse a simple POST request with body."""
        parser = YamlParser()
        collection = parser.parse(simple_post_fixture)

        request = collection.requests[0]
        assert request.http.method.value == "POST"
        assert request.http.body is not None
        assert request.http.body.type.value == "json"
        assert "John Doe" in str(request.http.body.data)

    def test_parse_collection(self, collection_fixture: str):
        """Parse a full collection with folders."""
        parser = YamlParser()
        collection = parser.parse(collection_fixture)

        assert collection.name == "Sample API Collection"
        assert collection.base_url == "https://api.example.com"
        assert len(collection.folders) == 2
        assert len(collection.requests) == 1  # Root level request

        # Check Users folder
        users_folder = next(f for f in collection.folders if f.name == "Users")
        assert len(users_folder.requests) == 2

    def test_parse_empty_content_raises_error(self):
        """Empty content should raise ParseError."""
        parser = YamlParser()
        with pytest.raises(ParseError):
            parser.parse("")

    def test_parse_invalid_yaml_raises_error(self):
        """Invalid YAML should raise ParseError."""
        parser = YamlParser()
        # Use truly invalid YAML (unmatched brackets)
        with pytest.raises(ParseError):
            parser.parse("[unclosed\n  - broken")

    def test_parse_extracts_variables(self, collection_fixture: str):
        """Variables should be extracted from collection."""
        parser = YamlParser()
        collection = parser.parse(collection_fixture)

        assert len(collection.variables) >= 1
        base_url_var = next((v for v in collection.variables if v.name == "baseUrl"), None)
        assert base_url_var is not None
        assert base_url_var.value == "https://api.example.com"

    def test_parse_normalizes_multipart_form_body_type(self):
        """Bruno `multipart-form` should normalize to the internal multipart body type."""
        parser = YamlParser()
        content = """
        info:
          name: Upload File
          type: http
          seq: 1
        http:
          method: POST
          url: https://api.example.com/upload
          body:
            type: multipart-form
            data:
              - name: file
                value: ./document.pdf
        """

        collection = parser.parse(content)

        body = collection.requests[0].http.body
        assert body is not None
        assert body.type.value == "multipart"


class TestJsonParser:
    """Tests for JsonParser."""

    def test_parse_simple_json(self):
        """Parse a simple JSON request."""
        parser = JsonParser()
        json_content = """
        {
            "info": {"name": "Test Request", "type": "http", "seq": 1},
            "http": {
                "method": "GET",
                "url": "https://api.example.com/test"
            }
        }
        """
        collection = parser.parse(json_content)

        assert collection.name == "Test Request"
        assert len(collection.requests) == 1
        assert collection.requests[0].http.method.value == "GET"

    def test_parse_invalid_json_raises_error(self):
        """Invalid JSON should raise ParseError."""
        parser = JsonParser()
        with pytest.raises(ParseError):
            parser.parse("{not valid json}")
