"""YAML parser for Bruno OpenCollection format."""

from __future__ import annotations

import logging

import yaml

from bruno_to_robot.models.bruno import (
    AuthType,
    BrunoAuth,
    BrunoBody,
    BrunoCollection,
    BrunoFolder,
    BrunoHttp,
    BrunoRequest,
    BrunoRuntime,
    BrunoScript,
    BrunoSettings,
    BrunoVariable,
    HttpMethod,
)

from .base import BaseParser

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Raised when parsing fails."""

    pass


class YamlParser(BaseParser):
    """Parser for OpenCollection YAML format."""

    def parse(self, content: str) -> BrunoCollection:
        """Parse YAML content into BrunoCollection.

        Handles both single-request files and full collection files.
        """
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise ParseError(f"Invalid YAML: {e}") from e

        if data is None:
            raise ParseError("Empty YAML content")

        return self._parse_collection(data)

    def _parse_collection(self, data: dict) -> BrunoCollection:
        """Parse collection data structure."""
        # Detect format: single request vs collection
        if "http" in data and "items" not in data:
            # Single request file (has http but no items)
            return self._parse_single_request(data)

        # Full collection
        name = data.get("name", data.get("info", {}).get("name", "Bruno Collection"))
        version = data.get("version", "1.0")

        # Extract variables from config.environments[0].variables or top-level
        variables = self._extract_variables(data)
        auth = self._parse_auth(data.get("auth", {}))
        base_url = self._extract_base_url(data)

        folders = self._parse_folders(data.get("folders", []))
        # Support both 'requests' and 'items' keys
        requests_data = data.get("requests", data.get("items", []))
        requests = self._parse_requests(requests_data)

        return BrunoCollection(
            name=name,
            version=version,
            variables=variables,
            auth=auth,
            base_url=base_url,
            folders=folders,
            requests=requests,
        )

    def _extract_variables(self, data: dict) -> list[BrunoVariable]:
        """Extract variables from various locations in Bruno collection."""
        # Try config.environments[0].variables first
        config = data.get("config", {})
        environments = config.get("environments", [])
        if environments:
            env_vars = environments[0].get("variables", [])
            if env_vars:
                return self._parse_variables(env_vars)

        # Fall back to top-level variables
        return self._parse_variables(data.get("variables", {}))

    def _extract_base_url(self, data: dict) -> str | None:
        """Extract base URL from collection."""
        # Check for base_url variable
        for var in self._extract_variables(data):
            if var.name in ("base_url", "baseUrl", "BASE_URL"):
                return str(var.value) if var.value else None

        # Check direct keys
        return data.get("baseUrl") or data.get("base_url")

    def _parse_single_request(self, data: dict) -> BrunoCollection:
        """Parse a single request file into a collection."""
        request = self._parse_request_item(data)

        return BrunoCollection(
            name=request.name,
            requests=[request],
        )

    def _parse_request_item(self, data: dict) -> BrunoRequest:
        """Parse a single request from OpenCollection format."""
        info = data.get("info", {})
        http = data.get("http", {})

        name = info.get("name", data.get("name", "Unnamed Request"))
        seq = info.get("seq", 1)

        # Parse HTTP configuration
        method = HttpMethod(http.get("method", "GET").upper())
        url = http.get("url", "")

        body = self._parse_body(http.get("body", {}))
        auth = self._parse_auth_type(http.get("auth", "inherit"))
        headers = self._parse_headers(http.get("headers", []))
        params = self._parse_params(http.get("params", []))

        bruno_http = BrunoHttp(
            method=method,
            url=url,
            body=body,
            auth=auth,
            headers=headers,
            params=params,
        )

        # Parse scripts
        runtime = self._parse_runtime(data.get("runtime", {}))
        settings = self._parse_settings(data.get("settings", {}))

        # Extract docs/description (at item level, not inside info)
        docs = data.get("docs") or data.get("description")

        return BrunoRequest(
            name=name,
            seq=seq,
            http=bruno_http,
            docs=docs,
            runtime=runtime,
            settings=settings,
        )

    def _parse_auth_type(self, auth: str | dict) -> AuthType:
        """Parse auth type from string or dict."""
        if isinstance(auth, str):
            return AuthType(auth) if auth else AuthType.INHERIT
        if isinstance(auth, dict):
            auth_type = auth.get("type", "inherit")
            return AuthType(auth_type) if auth_type else AuthType.INHERIT
        return AuthType.INHERIT

    def _parse_headers(self, headers_data: list | dict) -> dict[str, str]:
        """Parse headers from list or dict format.

        Supports:
        - List of {name, value} objects: [{name: "Content-Type", value: "application/json"}]
        - Dict format: {"Content-Type": "application/json"}
        """
        if not headers_data:
            return {}

        if isinstance(headers_data, dict):
            return headers_data

        if isinstance(headers_data, list):
            headers = {}
            for item in headers_data:
                if isinstance(item, dict):
                    name = item.get("name", "")
                    value = item.get("value", "")
                    if name:
                        headers[name] = value
                elif isinstance(item, list) and len(item) >= 2:
                    # Handle ["name", "value"] format
                    headers[item[0]] = item[1]
            return headers

        return {}

    def _parse_params(self, params_data: list | dict) -> dict[str, str]:
        """Parse query params from list or dict format.

        Supports:
        - List of {name, value} objects
        - Dict format
        """
        if not params_data:
            return {}

        if isinstance(params_data, dict):
            return params_data

        if isinstance(params_data, list):
            params = {}
            for item in params_data:
                if isinstance(item, dict):
                    name = item.get("name", "")
                    value = item.get("value", "")
                    if name:
                        params[name] = value
            return params

        return {}

    def _parse_body(self, body_data: dict | str | None) -> BrunoBody | None:
        """Parse request body configuration."""
        if body_data is None or body_data == "none":
            return None

        if isinstance(body_data, str):
            # Raw body string
            return BrunoBody(type="text", raw=body_data)

        body_type = body_data.get("type", "none")

        if body_type == "none":
            return None

        # Normalize body type
        body_type_normalized = self._normalize_body_type(body_type)

        # Parse data content - handle list format [{name, value}]
        data_content = body_data.get("data") or body_data.get("raw")
        if isinstance(data_content, list):
            data_content = self._parse_body_data_list(data_content)

        return BrunoBody(
            type=body_type_normalized,
            data=data_content,
            raw=body_data.get("raw"),
        )

    def _normalize_body_type(self, body_type: str) -> str:
        """Normalize body type to match BodyType enum."""
        # Map variations to canonical types
        type_mapping = {
            "form-urlencoded": "form",
            "urlencoded": "form",
            "json": "json",
            "text": "text",
            "xml": "xml",
            "form": "form",
            "multipart": "multipart",
            "graphql": "graphql",
        }
        return type_mapping.get(body_type.lower(), body_type.lower())

    def _parse_body_data_list(self, data_list: list) -> dict[str, str]:
        """Parse body data from list of {name, value} objects."""
        result = {}
        for item in data_list:
            if isinstance(item, dict):
                name = item.get("name", "")
                value = item.get("value", "")
                if name:
                    result[name] = value
        return result

    def _parse_runtime(self, runtime_data: dict) -> BrunoRuntime | None:
        """Parse runtime scripts."""
        scripts_data = runtime_data.get("scripts", [])

        if not scripts_data:
            return None

        scripts = []
        for script in scripts_data:
            scripts.append(
                BrunoScript(
                    type=script.get("type", "tests"),
                    code=script.get("code", ""),
                    enabled=script.get("enabled", True),
                )
            )

        return BrunoRuntime(scripts=scripts)

    def _parse_settings(self, settings_data: dict) -> BrunoSettings | None:
        """Parse request settings."""
        if not settings_data:
            return None

        return BrunoSettings(
            encode_url=settings_data.get("encodeUrl", True),
            timeout=settings_data.get("timeout"),
        )

    def _parse_auth(self, auth_data: dict | str) -> BrunoAuth | None:
        """Parse authentication configuration."""
        if not auth_data or auth_data == "none":
            return None

        if isinstance(auth_data, str):
            return BrunoAuth(type=AuthType(auth_data))

        return BrunoAuth(
            type=AuthType(auth_data.get("type", "none")),
            username=auth_data.get("username"),
            password=auth_data.get("password"),
            token=auth_data.get("token"),
            api_key=auth_data.get("apiKey") or auth_data.get("api_key"),
            api_key_name=auth_data.get("keyName") or auth_data.get("key_name"),
            api_key_location=auth_data.get("keyLocation")
            or auth_data.get("key_location"),
            cert_path=auth_data.get("cert") or auth_data.get("cert_path"),
            key_path=auth_data.get("key") or auth_data.get("key_path"),
        )

    def _parse_variables(
        self, vars_data: dict | list
    ) -> list[BrunoVariable]:
        """Parse collection variables."""
        if not vars_data:
            return []

        variables = []

        if isinstance(vars_data, dict):
            for name, value in vars_data.items():
                if isinstance(value, dict):
                    variables.append(
                        BrunoVariable(
                            name=name,
                            value=value.get("value"),
                            secret=value.get("secret", False),
                            enabled=value.get("enabled", True),
                        )
                    )
                else:
                    variables.append(BrunoVariable(name=name, value=value))
        else:
            for var in vars_data:
                variables.append(
                    BrunoVariable(
                        name=var.get("name"),
                        value=var.get("value"),
                        secret=var.get("secret", False),
                        enabled=var.get("enabled", True),
                    )
                )

        return variables

    def _parse_folders(self, folders_data: list) -> list[BrunoFolder]:
        """Parse folder structure."""
        folders = []

        for folder in folders_data:
            folders.append(
                BrunoFolder(
                    name=folder.get("name", "Unnamed Folder"),
                    path=folder.get("path", ""),
                    requests=self._parse_requests(folder.get("requests", [])),
                    folders=self._parse_folders(folder.get("folders", [])),
                    variables=self._parse_variables(folder.get("variables", {})),
                )
            )

        return folders

    def _parse_requests(self, requests_data: list) -> list[BrunoRequest]:
        """Parse list of requests."""
        return [self._parse_request_item(req) for req in requests_data]
