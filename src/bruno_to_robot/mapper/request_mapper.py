"""Map Bruno requests to Robot Framework test cases."""

from __future__ import annotations

import logging
import re
from typing import Any

from bruno_to_robot.models.bruno import (
    AuthType,
    BrunoAuth,
    BrunoBody,
    BrunoBody,
    BrunoCollection,
    BrunoFolder,
    BrunoHttp,
    BrunoRequest,
    BodyType,
    HttpMethod,
)
from bruno_to_robot.models.robot import RobotStep, RobotSuite, RobotTestCase, RobotVariable

logger = logging.getLogger(__name__)


class RequestMapper:
    """Maps Bruno requests to Robot Framework test cases."""

    # HTTP method to RequestsLibrary keyword mapping
    METHOD_KEYWORDS = {
        HttpMethod.GET: "GET On Session",
        HttpMethod.POST: "POST On Session",
        HttpMethod.PUT: "PUT On Session",
        HttpMethod.PATCH: "PATCH On Session",
        HttpMethod.DELETE: "DELETE On Session",
        HttpMethod.HEAD: "HEAD On Session",
        HttpMethod.OPTIONS: "OPTIONS On Session",
    }

    def __init__(
        self,
        session_name: str = "api",
        default_headers: dict[str, str] | None = None,
    ):
        self.session_name = session_name
        self.default_headers = default_headers or {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def map_collection(
        self,
        collection: BrunoCollection,
        split_by_folder: bool = True,
    ) -> list[RobotSuite]:
        """Map entire Bruno collection to Robot suites.

        Args:
            collection: Bruno collection model
            split_by_folder: If True, create separate suite per folder

        Returns:
            List of RobotSuite models
        """
        suites = []

        if split_by_folder and collection.folders:
            # Create suite per folder
            for folder in collection.folders:
                suite = self._map_folder(collection, folder)
                suites.append(suite)

            # Root-level requests as separate suite
            if collection.requests:
                root_suite = self._map_root_requests(collection)
                suites.append(root_suite)
        else:
            # Single suite for entire collection
            suite = self._map_single_suite(collection)
            suites.append(suite)

        return suites

    def _map_single_suite(self, collection: BrunoCollection) -> RobotSuite:
        """Map entire collection to single suite."""
        variables = self._extract_variables(collection)
        test_cases = []

        # Map root requests
        for request in collection.requests:
            tc = self._map_request(request, collection)
            test_cases.append(tc)

        # Map folder requests
        for folder in collection.folders:
            for request in folder.requests:
                tc = self._map_request(request, collection, folder)
                test_cases.append(tc)

        return RobotSuite(
            name=self._sanitize_name(collection.name),
            variables=variables,
            test_cases=test_cases,
        )

    def _map_folder(
        self,
        collection: BrunoCollection,
        folder: BrunoFolder,
    ) -> RobotSuite:
        """Map a single folder to a Robot suite."""
        variables = self._extract_variables(collection)
        test_cases = []

        for request in folder.requests:
            tc = self._map_request(request, collection, folder)
            test_cases.append(tc)

        # Recursively handle nested folders
        for nested in folder.folders:
            nested_suite = self._map_folder(collection, nested)
            test_cases.extend(nested_suite.test_cases)

        return RobotSuite(
            name=self._sanitize_name(folder.name),
            variables=variables,
            test_cases=test_cases,
        )

    def _map_root_requests(self, collection: BrunoCollection) -> RobotSuite:
        """Map root-level requests to a suite."""
        variables = self._extract_variables(collection)
        test_cases = []

        for request in collection.requests:
            tc = self._map_request(request, collection)
            test_cases.append(tc)

        return RobotSuite(
            name=self._sanitize_name(collection.name),
            variables=variables,
            test_cases=test_cases,
        )

    def _map_request(
        self,
        request: BrunoRequest,
        collection: BrunoCollection,
        folder: BrunoFolder | None = None,
    ) -> RobotTestCase:
        """Map single Bruno request to Robot test case."""
        steps = []
        http = request.http

        # Build request step
        request_step = self._build_request_step(http, collection)
        steps.append(request_step)

        # Build assertion steps
        assertion_steps = self._build_assertion_steps(request)
        steps.extend(assertion_steps)

        # Extract tags
        tags = self._extract_tags(request, folder)

        return RobotTestCase(
            name=self._sanitize_name(request.name),
            tags=tags,
            steps=steps,
            documentation=f"Converted from Bruno request: {request.name}",
        )

    def _build_request_step(
        self,
        http: BrunoHttp,
        collection: BrunoCollection,
    ) -> RobotStep:
        """Build the main request step."""
        keyword = self.METHOD_KEYWORDS.get(http.method, "GET On Session")

        args = [
            self.session_name,  # session alias
            self._extract_path(http.url, collection.base_url),  # endpoint
        ]

        # Add body
        if http.body and http.body.type != BodyType.NONE:
            body_arg = self._format_body(http.body)
            if body_arg:
                args.append(body_arg)

        # Add headers
        headers = {**self.default_headers, **http.headers}
        if headers:
            headers_str = self._format_headers(headers)
            args.append(f"headers={headers_str}")

        # Add query params
        if http.params:
            params_str = self._format_params(http.params)
            args.append(f"params={params_str}")

        return RobotStep(
            keyword=keyword,
            args=args,
            assign="${resp}",
        )

    def _format_body(self, body: BrunoBody) -> str:
        """Format body for Robot keyword argument."""
        if body.type == BodyType.JSON:
            # JSON body
            if isinstance(body.data, dict):
                # Convert to Robot dict syntax
                items = [f"{k}={repr(v)}" for k, v in body.data.items()]
                return f"json={{{', '.join(items)}}}"
            elif isinstance(body.data, str):
                return f"json={body.data}"
        elif body.type == BodyType.TEXT:
            return f"data={repr(body.raw or body.data)}"
        elif body.type == BodyType.FORM:
            return f"data={repr(body.data)}"
        elif body.type == BodyType.MULTIPART:
            return f"files={repr(body.data)}"

        return ""

    def _format_headers(self, headers: dict[str, str]) -> str:
        """Format headers dict for Robot."""
        items = [f"{k}={v}" for k, v in sorted(headers.items())]
        return f"&{{{', '.join(items)}}}"

    def _format_params(self, params: dict[str, str]) -> str:
        """Format query params for Robot."""
        items = [f"{k}={v}" for k, v in sorted(params.items())]
        return f"&{{{', '.join(items)}}}"

    def _extract_path(self, url: str, base_url: str | None) -> str:
        """Extract path from URL, removing base URL if present."""
        if not url:
            return "/"

        if base_url and url.startswith(base_url):
            path = url[len(base_url) :]
            return path if path else "/"

        # If URL is absolute, extract path
        if "://" in url:
            # Parse URL and extract path
            parts = url.split("://", 1)[-1].split("/", 1)
            if len(parts) > 1:
                return "/" + parts[1]
            return "/"

        return url

    def _build_assertion_steps(self, request: BrunoRequest) -> list[RobotStep]:
        """Build assertion steps from Bruno test scripts."""
        steps = []

        if not request.runtime or not request.runtime.scripts:
            # Default: check status code is 2xx
            steps.append(
                RobotStep(
                    keyword="Should Be True",
                    args=["${resp.status_code} < 400", "Check for 2xx/3xx status"],
                )
            )
            return steps

        for script in request.runtime.scripts:
            if script.type == "tests":
                parsed = self._parse_chai_assertions(script.code)
                steps.extend(parsed)

        return steps

    def _parse_chai_assertions(self, code: str) -> list[RobotStep]:
        """Parse Chai-style assertions from Bruno script.

        Supports basic patterns:
        - expect(res.status).to.equal(200)
        - expect(res.body.id).to.exist
        - expect(res.body.name).to.equal("value")
        """
        steps = []

        # Pattern: expect(res.status).to.equal(N)
        status_pattern = r"expect\s*\(\s*res\.status\s*\)\s*\.\s*to\s*\.\s*equal\s*\(\s*(\d+)\s*\)"
        for match in re.finditer(status_pattern, code):
            status_code = match.group(1)
            steps.append(
                RobotStep(
                    keyword="Should Be Equal As Integers",
                    args=["${resp.status_code}", status_code],
                )
            )

        # Pattern: expect(res.body.prop).to.equal("value")
        body_equal_pattern = r"expect\s*\(\s*res\.body\.(\w+)\s*\)\s*\.\s*to\s*\.\s*equal\s*\(\s*['\"]([^'\"]*)['\"]\s*\)"
        for match in re.finditer(body_equal_pattern, code):
            prop = match.group(1)
            value = match.group(2)
            steps.append(
                RobotStep(
                    keyword="Should Be Equal",
                    args=[f"${{resp.json()['{prop}']}}", f"'{value}'"],
                )
            )

        # Pattern: expect(res.body.prop).to.exist
        exist_pattern = r"expect\s*\(\s*res\.body\.(\w+)\s*\)\s*\.\s*to\s*\.\s*exist\s*\)?"
        for match in re.finditer(exist_pattern, code):
            prop = match.group(1)
            steps.append(
                RobotStep(
                    keyword="Dictionary Should Contain Key",
                    args=["${resp.json()}", f"'{prop}'"],
                )
            )

        # If no patterns matched, add comment
        if not steps:
            steps.append(
                RobotStep(
                    keyword="Log",
                    args=["TODO: Manual conversion of assertion script needed"],
                    comment=f"Original: {code[:50]}...",
                )
            )

        return steps

    def _extract_variables(
        self,
        collection: BrunoCollection,
    ) -> list[RobotVariable]:
        """Extract variables from collection."""
        variables = []

        # Base URL
        if collection.base_url:
            variables.append(
                RobotVariable(
                    name="BASE_URL",
                    value=collection.base_url,
                )
            )

        # Collection variables
        for var in collection.variables:
            rf_name = self._bruno_var_to_robot(var.name)
            value = var.value

            if var.secret:
                # Don't expose secrets - use env var reference
                value = f"%{{{rf_name}}}"

            variables.append(
                RobotVariable(
                    name=rf_name,
                    value=value,
                    comment="Secret - set via environment" if var.secret else None,
                )
            )

        # Default headers as dict variable
        variables.append(
            RobotVariable(
                name="DEFAULT_HEADERS",
                value=self.default_headers,
                is_dict=True,
            )
        )

        return variables

    def _bruno_var_to_robot(self, name: str) -> str:
        """Convert Bruno variable name to Robot format.

        {{baseUrl}} → BASE_URL
        {{api_key}} → API_KEY
        """
        # Remove {{ }} if present
        clean = name.strip("{}")
        # Convert to UPPER_SNAKE_CASE
        return clean.upper().replace("-", "_")

    def _extract_tags(
        self,
        request: BrunoRequest,
        folder: BrunoFolder | None,
    ) -> list[str]:
        """Extract tags for test case."""
        tags = ["api"]

        if folder:
            tags.append(self._sanitize_tag(folder.name))

        # Add method tag
        tags.append(request.http.method.value.lower())

        return tags

    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for Robot Framework test case."""
        # Replace special chars with spaces
        clean = re.sub(r"[^a-zA-Z0-9_\s]", " ", name)
        # Collapse multiple spaces
        clean = re.sub(r"\s+", " ", clean).strip()
        # Title case
        return clean.title() if clean else "Unnamed"

    def _sanitize_tag(self, name: str) -> str:
        """Sanitize name for tag."""
        return re.sub(r"[^a-zA-Z0-9_-]", "_", name).lower()
