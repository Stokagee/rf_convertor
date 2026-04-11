"""Unit tests for direct Bruno `.bru` parsing."""

from pathlib import Path

import pytest

from bruno_to_robot.parser.bru_parser import BruParser
from bruno_to_robot.parser.yaml_parser import ParseError


class TestBruParser:
    """Tests for parsing Bruno request files and Bruno collection directories."""

    def test_parse_single_bru_file_returns_single_request_collection(
        self,
        bru_single_request_path: Path,
    ):
        """A single `.bru` file should map to a single-request collection."""
        parser = BruParser()

        collection = parser.parse_path(bru_single_request_path)

        assert collection.name == "Get Health"
        assert len(collection.requests) == 1

        request = collection.requests[0]
        assert request.name == "Get Health"
        assert request.http.method.value == "GET"
        assert request.http.url == "https://api.example.com/health"
        assert request.http.headers == {"Accept": "application/json"}
        assert request.http.params == {"verbose": "true"}

    def test_parse_bru_directory_preserves_folder_structure(
        self,
        bru_collection_dir: Path,
    ):
        """A Bruno directory should become the same nested internal collection model."""
        parser = BruParser(environment_name="test_client")

        collection = parser.parse_path(bru_collection_dir)

        assert collection.name == "Paymont Bruno Collection"
        assert collection.base_url == "https://client.example.com"
        assert [request.name for request in collection.requests] == ["Health Check"]
        assert [folder.name for folder in collection.folders] == ["Flows"]

        flows_folder = collection.folders[0]
        assert flows_folder.path == "Flows"
        assert [folder.name for folder in flows_folder.folders] == ["Client API Flow"]

        client_api_folder = flows_folder.folders[0]
        assert client_api_folder.path == "Flows/Client API Flow"
        assert [request.name for request in client_api_folder.requests] == [
            "Get OAuth2 Token",
            "List Customers",
        ]

        token_request = client_api_folder.requests[0]
        assert token_request.path == "Flows/Client API Flow/Get OAuth2 Token.bru"
        assert token_request.http.method.value == "POST"
        assert token_request.http.url == "{{baseUrl}}/oauth/token"
        assert token_request.http.headers == {"Content-Type": "application/json"}
        assert token_request.http.auth is not None
        assert token_request.http.auth.type.value == "bearer"
        assert token_request.http.auth.token == "{{access_token}}"
        assert token_request.http.body is not None
        assert token_request.http.body.type.value == "json"
        assert "client_credentials" in str(token_request.http.body.data)

        list_customers = client_api_folder.requests[1]
        assert list_customers.path == "Flows/Client API Flow/List Customers.bru"
        assert list_customers.http.params == {"size": "20"}

    def test_parse_bru_directory_ignores_non_bru_files(
        self,
        bru_collection_dir: Path,
    ):
        """Only `.bru` request files should become requests."""
        parser = BruParser(environment_name="test_client")

        collection = parser.parse_path(bru_collection_dir)
        all_request_names = [request.name for request in collection.requests]
        all_request_names.extend(
            request.name
            for folder in collection.folders
            for nested in folder.folders
            for request in nested.requests
        )

        assert "README" not in all_request_names
        assert len(all_request_names) == 3

    def test_parse_bru_directory_raises_for_unknown_environment(
        self,
        bru_collection_dir: Path,
    ):
        """Unknown Bruno env names should fail fast instead of silently falling back."""
        parser = BruParser(environment_name="missing-env")

        with pytest.raises(ParseError):
            parser.parse_path(bru_collection_dir)

    def test_parse_single_bru_file_raises_for_missing_url(
        self,
        tmp_path: Path,
    ):
        """A Bruno request without `url` should fail fast instead of generating a broken request."""
        parser = BruParser()
        request_path = tmp_path / "Missing Url.bru"
        request_path.write_text(
            """meta {
  name: Missing Url
  type: http
  seq: 1
}

get {
}
""",
            encoding="utf-8",
        )

        with pytest.raises(ParseError, match="url"):
            parser.parse_path(request_path)

    def test_parse_bru_directory_raises_when_no_requests_are_found(
        self,
        tmp_path: Path,
    ):
        """A Bruno directory without any request files should fail fast."""
        parser = BruParser()
        empty_collection = tmp_path / "empty-collection"
        empty_collection.mkdir()
        (empty_collection / "bruno.json").write_text('{"name":"Empty"}', encoding="utf-8")

        with pytest.raises(ParseError, match="No Bruno requests found"):
            parser.parse_path(empty_collection)

    def test_parse_bru_directory_error_mentions_problem_file(
        self,
        tmp_path: Path,
    ):
        """Parse errors inside a Bruno directory should include the file path for debugging."""
        parser = BruParser()
        collection_dir = tmp_path / "broken-collection"
        collection_dir.mkdir()
        request_path = collection_dir / "Broken Request.bru"
        request_path.write_text(
            """meta {
  name: Broken Request
  type: http
  seq: 1
}

get {
  url: https://api.example.com
""",
            encoding="utf-8",
        )

        with pytest.raises(ParseError) as exc_info:
            parser.parse_path(collection_dir)

        assert str(request_path) in str(exc_info.value)

    def test_parse_bru_directory_supports_collection_and_folder_metadata_files(
        self,
        bru_native_collection_dir: Path,
    ):
        """Native Bruno `collection.bru` and `folder.bru` files should be handled."""
        parser = BruParser(environment_name="test_client")

        collection = parser.parse_path(bru_native_collection_dir)

        assert collection.base_url == "https://client.example.com"
        assert {var.name: var.value for var in collection.variables} == {
            "baseUrl": "https://client.example.com",
            "apiVersion": "v1",
            "access_token": "client-token",
        }
        assert [folder.name for folder in collection.folders] == ["User Management"]
        assert collection.folders[0].path == "users"
        assert [request.name for request in collection.folders[0].requests] == ["Get User"]

    def test_parse_single_bru_file_rejects_unsupported_script_sections(
        self,
        tmp_path: Path,
    ):
        """Direct `.bru` parsing should fail loudly for unsupported script blocks."""
        parser = BruParser()
        request_path = tmp_path / "Scripted Request.bru"
        request_path.write_text(
            """meta {
  name: Scripted Request
  type: http
  seq: 1
}

get {
  url: https://api.example.com/scripted
}

script:pre-request {
  console.log('before request');
}
""",
            encoding="utf-8",
        )

        with pytest.raises(ParseError, match="Unsupported Bruno sections"):
            parser.parse_path(request_path)

    def test_parse_single_bru_file_supports_json_body_with_braces_inside_strings(
        self,
        tmp_path: Path,
    ):
        """Braces inside JSON string literals must not break `.bru` block parsing."""
        parser = BruParser()
        request_path = tmp_path / "Templated Body.bru"
        request_path.write_text(
            """meta {
  name: Templated Body
  type: http
  seq: 1
}

post {
  url: https://api.example.com/templates
}

body:json {
  {
    "template": "Hello {customer}",
    "payload": {
      "message": "Value with } and { braces"
    }
  }
}
""",
            encoding="utf-8",
        )

        collection = parser.parse_path(request_path)

        request = collection.requests[0]
        assert request.http.body is not None
        assert request.http.body.type.value == "json"
        assert '"template": "Hello {customer}"' in str(request.http.body.data)
        assert '"message": "Value with } and { braces"' in str(request.http.body.data)

    def test_parse_single_bru_file_supports_docs_with_braces_inside_strings(
        self,
        tmp_path: Path,
    ):
        """Braces inside docs text must not terminate the block early."""
        parser = BruParser()
        request_path = tmp_path / "Documented Request.bru"
        request_path.write_text(
            """meta {
  name: Documented Request
  type: http
  seq: 1
}

get {
  url: https://api.example.com/docs
}

docs {
  Example payload: {"message": "Hello {customer}"}
}
""",
            encoding="utf-8",
        )

        collection = parser.parse_path(request_path)

        request = collection.requests[0]
        assert request.docs is not None
        assert 'Example payload: {"message": "Hello {customer}"}' in request.docs

    def test_parse_native_collection_rejects_unsupported_collection_level_sections(
        self,
        tmp_path: Path,
    ):
        """Collection-level sections with request semantics should fail fast in MVP mode."""
        parser = BruParser()
        collection_dir = tmp_path / "native-collection"
        collection_dir.mkdir()
        (collection_dir / "collection.bru").write_text(
            """vars:pre-request {
  baseUrl: https://api.example.com
}

headers {
  Accept: application/json
}
""",
            encoding="utf-8",
        )
        users_dir = collection_dir / "users"
        users_dir.mkdir()
        (users_dir / "Get User.bru").write_text(
            """meta {
  name: Get User
  type: http
  seq: 1
}

get {
  url: https://api.example.com/users/1
}
""",
            encoding="utf-8",
        )

        with pytest.raises(ParseError, match="Unsupported collection sections"):
            parser.parse_path(collection_dir)

    def test_parse_native_collection_rejects_unsupported_folder_metadata_sections(
        self,
        tmp_path: Path,
    ):
        """Folder metadata outside `meta {}` should fail fast in MVP mode."""
        parser = BruParser()
        collection_dir = tmp_path / "native-collection"
        users_dir = collection_dir / "users"
        users_dir.mkdir(parents=True)
        (users_dir / "folder.bru").write_text(
            """meta {
  name: Users
}

headers {
  Accept: application/json
}
""",
            encoding="utf-8",
        )
        (users_dir / "Get User.bru").write_text(
            """meta {
  name: Get User
  type: http
  seq: 1
}

get {
  url: https://api.example.com/users/1
}
""",
            encoding="utf-8",
        )

        with pytest.raises(ParseError, match="Unsupported folder sections"):
            parser.parse_path(collection_dir)

    def test_parse_native_collection_rejects_unsupported_environment_sections(
        self,
        tmp_path: Path,
    ):
        """Environment files outside `vars {}` should fail fast in MVP mode."""
        parser = BruParser(environment_name="test_client")
        collection_dir = tmp_path / "native-collection"
        users_dir = collection_dir / "users"
        env_dir = collection_dir / "environments"
        users_dir.mkdir(parents=True)
        env_dir.mkdir()
        (env_dir / "test_client.bru").write_text(
            """vars {
  baseUrl: https://client.example.com
}

headers {
  Accept: application/json
}
""",
            encoding="utf-8",
        )
        (users_dir / "Get User.bru").write_text(
            """meta {
  name: Get User
  type: http
  seq: 1
}

get {
  url: https://api.example.com/users/1
}
""",
            encoding="utf-8",
        )

        with pytest.raises(ParseError, match="Unsupported environment sections"):
            parser.parse_path(collection_dir)

    def test_parse_native_collection_ignores_disabled_environment_variables(
        self,
        tmp_path: Path,
    ):
        """Disabled native Bruno env vars should not override applied variables."""
        parser = BruParser(environment_name="test_client")
        collection_dir = tmp_path / "native-collection"
        users_dir = collection_dir / "users"
        env_dir = collection_dir / "environments"
        users_dir.mkdir(parents=True)
        env_dir.mkdir()
        (collection_dir / "collection.bru").write_text(
            """vars:pre-request {
  baseUrl: https://collection.example.com
  apiVersion: v1
}
""",
            encoding="utf-8",
        )
        (env_dir / "test_client.bru").write_text(
            """vars {
  ~baseUrl: https://disabled.example.com
  access_token: client-token
}
""",
            encoding="utf-8",
        )
        (users_dir / "Get User.bru").write_text(
            """meta {
  name: Get User
  type: http
  seq: 1
}

get {
  url: {{baseUrl}}/users/1
}
""",
            encoding="utf-8",
        )

        collection = parser.parse_path(collection_dir)

        assert collection.base_url == "https://collection.example.com"
        assert {var.name: var.value for var in collection.variables} == {
            "baseUrl": "https://collection.example.com",
            "apiVersion": "v1",
            "access_token": "client-token",
        }

    def test_parse_native_collection_rejects_local_environment_variables(
        self,
        tmp_path: Path,
    ):
        """Local native Bruno env vars should fail fast because MVP cannot represent them safely."""
        parser = BruParser(environment_name="test_client")
        collection_dir = tmp_path / "native-collection"
        users_dir = collection_dir / "users"
        env_dir = collection_dir / "environments"
        users_dir.mkdir(parents=True)
        env_dir.mkdir()
        (env_dir / "test_client.bru").write_text(
            """vars {
  baseUrl: https://client.example.com
  @temporaryToken: generated-token
}
""",
            encoding="utf-8",
        )
        (users_dir / "Get User.bru").write_text(
            """meta {
  name: Get User
  type: http
  seq: 1
}

get {
  url: https://api.example.com/users/1
}
""",
            encoding="utf-8",
        )

        with pytest.raises(ParseError, match="Unsupported local Bruno variable"):
            parser.parse_path(collection_dir)
