"""YAML parser for Bruno OpenCollection format."""

from __future__ import annotations

import logging

import yaml

from bruno_to_robot.models.bruno import (
    AuthType,
    BrunoAuth,
    BrunoBody,
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
        if "http" in data or "info" in data:
            # Single request file
            return self._parse_single_request(data)

        # Full collection
        name = data.get("name", "Bruno Collection")
        version = data.get("version", "1.0")

        variables = self._parse_variables(data.get("variables", {}))
        auth = self._parse_auth(data.get("auth", {}))
        base_url = data.get("baseUrl") or data.get("base_url")

        folders = self._parse_folders(data.get("folders", []))
        requests = self._parse_requests(data.get("requests", []))

        return BrunoCollection(
            name=name,
            version=version,
            variables=variables,
            auth=auth,
            base_url=base_url,
            folders=folders,
            requests=requests,
        )

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
        auth = http.get("auth", "inherit")
        headers = http.get("headers", {})
        params = http.get("params", {})

        bruno_http = BrunoHttp(
            method=method,
            url=url,
            body=body,
            auth=AuthType(auth) if isinstance(auth, str) else AuthType.INHERIT,
            headers=headers,
            params=params,
        )

        # Parse scripts
        runtime = self._parse_runtime(data.get("runtime", {}))
        settings = self._parse_settings(data.get("settings", {}))

        return BrunoRequest(
            name=name,
            seq=seq,
            http=bruno_http,
            runtime=runtime,
            settings=settings,
        )

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

        data_content = body_data.get("data") or body_data.get("raw")

        return BrunoBody(
            type=body_type,
            data=data_content,
            raw=body_data.get("raw"),
        )

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
