"""Map Bruno requests to Robot Framework test cases."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from bruno_to_robot.models.bruno import (
    BodyType,
    BrunoBody,
    BrunoCollection,
    BrunoFolder,
    BrunoHttp,
    BrunoRequest,
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

    # Session aliases for different URL patterns
    SESSION_ALIASES = {
        "api": "BASE_URL",
        "auth": "AUTH_URL",
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
        # Will be populated during mapping
        self.url_sessions: dict[str, str] = {}  # base_url -> session_alias

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
        # Detect all base URLs from variables and requests
        self._detect_url_sessions(collection)

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

    def _detect_url_sessions(self, collection: BrunoCollection) -> None:
        """Detect all unique base URLs and assign session aliases."""
        # Reset sessions for fresh detection
        self.url_sessions = {}

        # Extract URL variables from collection
        url_vars = {}
        for var in collection.variables:
            var_lower = var.name.lower()
            if "url" in var_lower and var.value:
                url_vars[var.name.upper()] = str(var.value)

        # Map known URL patterns to session aliases
        # Use self.session_name as the primary session alias
        if "BASE_URL" in url_vars:
            self.url_sessions[url_vars["BASE_URL"]] = self.session_name
        if "AUTH_URL" in url_vars:
            self.url_sessions[url_vars["AUTH_URL"]] = "auth"

        # Also check collection.base_url
        if collection.base_url:
            self.url_sessions[collection.base_url] = self.session_name

        # Scan all requests for unique base URLs
        all_requests = list(collection.requests)
        for folder in collection.folders:
            all_requests.extend(self._collect_folder_requests(folder))

        first_unknown = True
        for request in all_requests:
            url = request.http.url
            if url and "://" in url:
                base = self._extract_base_from_url(url)

                # Check if URL starts with any known variable URL
                matched = False
                for var_url, alias in list(self.url_sessions.items()):
                    if url.startswith(var_url):
                        matched = True
                        break

                if not matched and base and base not in self.url_sessions:
                    # First unknown base uses primary session name
                    if first_unknown:
                        self.url_sessions[base] = self.session_name
                        first_unknown = False
                    else:
                        # Generate a session alias for subsequent bases
                        alias = self._generate_session_alias(base)
                        self.url_sessions[base] = alias

    def _collect_folder_requests(self, folder: BrunoFolder) -> list[BrunoRequest]:
        """Recursively collect all requests from folder."""
        requests = list(folder.requests)
        for nested in folder.folders:
            requests.extend(self._collect_folder_requests(nested))
        return requests

    def _extract_base_from_url(self, url: str) -> str | None:
        """Extract base URL (scheme + host + port) from full URL."""
        if "://" not in url:
            return None
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _generate_session_alias(self, base_url: str) -> str:
        """Generate a session alias from base URL."""
        parsed = urlparse(base_url)
        # Use port or domain as alias
        if parsed.port:
            return f"srv_{parsed.port}"
        # Use domain without TLD
        domain = parsed.hostname or "unknown"
        parts = domain.split(".")
        return parts[0] if parts else "srv"

    def _get_session_for_url(self, url: str) -> tuple[str, str]:
        """Get session alias and relative path for a URL.

        Returns:
            Tuple of (session_alias, relative_path)
        """
        if not url:
            return (self.session_name, "/")

        # If URL is already relative
        if "://" not in url:
            return (self.session_name, url if url.startswith("/") else f"/{url}")

        # Extract base URL
        base = self._extract_base_from_url(url)
        if base and base in self.url_sessions:
            alias = self.url_sessions[base]
            path = url[len(base):] or "/"
            return (alias, path)

        # Unknown base URL - use default session
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return (self.session_name, path)

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

        # Generate keywords for all detected sessions
        keywords = self._generate_session_keywords()

        # Settings for suite setup/teardown
        settings = {
            "suite_setup": "Create All Sessions",
            "suite_teardown": "Delete All Sessions",
        }

        return RobotSuite(
            name=self._sanitize_name(collection.name),
            variables=variables,
            test_cases=test_cases,
            keywords=keywords,
            settings=settings,
        )

    def _generate_session_keywords(self) -> dict[str, list[RobotStep]]:
        """Generate keywords for session management."""
        keywords = {}

        # Track unique aliases to avoid duplicates
        seen_aliases = set()

        # Generate individual session creation keywords
        for base_url, alias in sorted(self.url_sessions.items(), key=lambda x: x[1]):
            if alias in seen_aliases:
                continue
            seen_aliases.add(alias)

            var_name = self._get_url_variable_for_alias(alias)
            keyword_name = f"Create {alias.title()} Session"
            keywords[keyword_name] = [
                RobotStep(
                    keyword="Create Session",
                    args=[
                        f"alias={alias}",
                        f"url=${{{var_name}}}",
                        "verify=${TRUE}",
                    ],
                )
            ]

        # Generate Create All Sessions keyword
        all_session_steps = []
        seen_aliases = set()
        for base_url, alias in sorted(self.url_sessions.items(), key=lambda x: x[1]):
            if alias in seen_aliases:
                continue
            seen_aliases.add(alias)

            var_name = self._get_url_variable_for_alias(alias)
            all_session_steps.append(
                RobotStep(
                    keyword="Create Session",
                    args=[
                        f"alias={alias}",
                        f"url=${{{var_name}}}",
                        "verify=${TRUE}",
                    ],
                )
            )
        keywords["Create All Sessions"] = all_session_steps

        return keywords

    def _get_url_variable_for_alias(self, alias: str) -> str:
        """Get the URL variable name for a session alias."""
        alias_to_var = {
            "api": "BASE_URL",
            "auth": "AUTH_URL",
        }
        return alias_to_var.get(alias, f"{alias.upper()}_URL")

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

        # Generate keywords for all detected sessions
        keywords = self._generate_session_keywords()

        # Settings for suite setup/teardown
        settings = {
            "suite_setup": "Create All Sessions",
            "suite_teardown": "Delete All Sessions",
        }

        return RobotSuite(
            name=self._sanitize_name(folder.name),
            variables=variables,
            test_cases=test_cases,
            keywords=keywords,
            settings=settings,
        )

    def _map_root_requests(self, collection: BrunoCollection) -> RobotSuite:
        """Map root-level requests to a suite."""
        variables = self._extract_variables(collection)
        test_cases = []

        for request in collection.requests:
            tc = self._map_request(request, collection)
            test_cases.append(tc)

        # Generate keywords for all detected sessions
        keywords = self._generate_session_keywords()

        # Settings for suite setup/teardown
        settings = {
            "suite_setup": "Create All Sessions",
            "suite_teardown": "Delete All Sessions",
        }

        return RobotSuite(
            name=self._sanitize_name(collection.name),
            variables=variables,
            test_cases=test_cases,
            keywords=keywords,
            settings=settings,
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

        # Build request steps (may include Create Dictionary for headers)
        request_steps = self._build_request_step(http, collection)
        steps.extend(request_steps)

        # Build assertion steps
        assertion_steps = self._build_assertion_steps(request)
        steps.extend(assertion_steps)

        # Extract tags
        tags = self._extract_tags(request, folder)

        # Use docs from Bruno request, or fall back to generic message
        documentation = request.docs or f"Converted from Bruno request: {request.name}"

        return RobotTestCase(
            name=self._sanitize_name(request.name),
            tags=tags,
            steps=steps,
            documentation=documentation,
        )

    def _build_request_step(
        self,
        http: BrunoHttp,
        collection: BrunoCollection,
    ) -> list[RobotStep]:
        """Build request step(s) including header setup if needed.

        Returns a list of steps:
        - Optional: Create Dictionary step for form data
        - Optional: Create Dictionary step for custom headers
        - Main request step
        """
        steps = []
        keyword = self.METHOD_KEYWORDS.get(http.method, "GET On Session")

        # Determine the correct session alias based on URL
        session_alias, url_path = self._get_session_for_url(http.url)

        # If collection has base_url and URL matches, use relative path
        if collection.base_url and http.url.startswith(collection.base_url):
            url_path = self._extract_path(http.url, collection.base_url)

        # Handle form-urlencoded body - create dictionary first
        body_ref = None
        if http.body and http.body.type == BodyType.FORM:
            if isinstance(http.body.data, dict):
                form_dict = {}
                for key, value in sorted(http.body.data.items()):
                    # Replace hardcoded values with variable references
                    if self._is_secret_form_field(key, value) and hasattr(self, "_form_var_map"):
                        var_ref = self._get_form_variable(key, value)
                        if var_ref:
                            form_dict[key] = var_ref
                        else:
                            form_dict[key] = value
                    else:
                        form_dict[key] = value

                dict_args = [f"{k}={v}" for k, v in sorted(form_dict.items())]
                steps.append(RobotStep(
                    keyword="Create Dictionary",
                    args=dict_args,
                    assign="${form_data}",
                ))
                body_ref = "data=${form_data}"

        # Handle custom headers - create dictionary
        headers_ref = "${DEFAULT_HEADERS}"
        if http.headers:
            # Merge default headers with request-specific headers
            merged_headers = {**self.default_headers}
            for key, value in http.headers.items():
                # Replace hardcoded Bearer tokens with variable references
                if key.lower() == "authorization" and value.startswith("Bearer "):
                    token_value = value[7:]  # Remove "Bearer " prefix
                    token_var = self._get_token_variable(token_value)
                    if token_var:
                        merged_headers[key] = f"Bearer {token_var}"
                    else:
                        # Token not extracted as variable, keep as-is
                        merged_headers[key] = value
                # Replace other secret header values with variables
                elif self._is_secret_header(key, value) and hasattr(self, "_header_var_map"):
                    var_ref = self._get_header_variable(key, value)
                    if var_ref:
                        merged_headers[key] = var_ref
                    else:
                        merged_headers[key] = value
                else:
                    merged_headers[key] = value

            dict_args = [f"{k}={v}" for k, v in sorted(merged_headers.items())]
            steps.append(RobotStep(
                keyword="Create Dictionary",
                args=dict_args,
                assign="${headers}",
            ))
            headers_ref = "${headers}"

        # Build main request args
        args = [
            f"alias={session_alias}",
            f"url={url_path}",
        ]

        # Add body
        if body_ref:
            args.append(body_ref)
        elif http.body and http.body.type != BodyType.NONE:
            body_arg = self._format_body(http.body)
            if body_arg:
                args.append(body_arg)

        # Add headers reference
        args.append(f"headers={headers_ref}")

        # Add query params
        if http.params:
            params_str = self._format_params(http.params)
            args.append(f"params={params_str}")

        # Add expected_status to allow any status code (we'll assert afterwards)
        args.append("expected_status=anything")

        steps.append(RobotStep(
            keyword=keyword,
            args=args,
            assign="${resp}",
        ))

        return steps

    def _format_body(self, body: BrunoBody) -> str | None:
        """Format body for Robot keyword argument."""
        import json

        if body.type == BodyType.JSON:
            # JSON body - ensure single line
            if isinstance(body.data, dict):
                json_str = json.dumps(body.data, separators=(",", ":"))
                return f"json={json_str}"
            elif isinstance(body.data, str):
                try:
                    parsed = json.loads(body.data)
                    json_str = json.dumps(parsed, separators=(",", ":"))
                    return f"json={json_str}"
                except (json.JSONDecodeError, ValueError):
                    return f"json={body.data}"
            elif body.raw:
                try:
                    parsed = json.loads(body.raw)
                    json_str = json.dumps(parsed, separators=(",", ":"))
                    return f"json={json_str}"
                except (json.JSONDecodeError, ValueError):
                    return f"json={body.raw}"
        elif body.type == BodyType.TEXT:
            return f"data={repr(body.raw or body.data)}"
        elif body.type == BodyType.FORM:
            # Form data is handled via Create Dictionary in _build_request_step
            return None
        elif body.type == BodyType.MULTIPART:
            return f"files={repr(body.data)}"

        return None

    def _format_headers(self, headers: dict[str, str]) -> str:
        """Format headers for Robot Framework.

        Returns a dictionary variable reference or creates inline dictionary.
        """
        # Create dictionary items in Robot format
        items = [f"{k}={v}" for k, v in sorted(headers.items())]
        # Use &{} syntax to create dictionary inline
        return f"&{{{ '    '.join(items) }}}"

    def _format_params(self, params: dict[str, str]) -> str:
        """Format query params for Robot."""
        items = [f"{k}={v}" for k, v in sorted(params.items())]
        return f"&{{{', '.join(items)}}}"

    def _extract_path(self, url: str, base_url: str | None) -> str:
        """Extract path from URL, removing base URL if present.

        Handles cases where:
        - URL starts with base_url
        - URL has different host but same path prefix
        - URL is already a relative path
        """
        if not url:
            return "/"

        # If URL is relative, use as-is
        if not url.startswith(("http://", "https://")):
            return url if url.startswith("/") else f"/{url}"

        # Try exact base_url match first
        if base_url and url.startswith(base_url):
            path = url[len(base_url) :]
            return path if path else "/"

        # Extract path from absolute URL
        if "://" in url:
            # Parse URL and extract path
            parts = url.split("://", 1)[-1].split("/", 1)
            if len(parts) > 1:
                path = "/" + parts[1]

                # Try to strip common base path from collection
                if base_url:
                    # Extract path portion from base_url
                    base_path = self._get_path_from_url(base_url)
                    if base_path and path.startswith(base_path):
                        remaining = path[len(base_path) :]
                        return remaining if remaining else "/"

                return path
            return "/"

        return url

    def _get_path_from_url(self, url: str) -> str:
        """Extract just the path portion from a URL."""
        if not url:
            return ""

        if "://" in url:
            parts = url.split("://", 1)[-1].split("/", 1)
            return "/" + parts[1] if len(parts) > 1 else ""

        return url if url.startswith("/") else f"/{url}"

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
        seen_names = set()

        # Base URL
        if collection.base_url:
            variables.append(
                RobotVariable(
                    name="BASE_URL",
                    value=collection.base_url,
                )
            )
            seen_names.add("BASE_URL")

        # Extract Bearer tokens from all requests
        token_vars = self._extract_bearer_tokens(collection)
        for var in token_vars:
            if var.name not in seen_names:
                variables.append(var)
                seen_names.add(var.name)

        # Collection variables (skip base_url as it's already added)
        for var in collection.variables:
            rf_name = self._bruno_var_to_robot(var.name)

            # Skip base_url variants - already added above
            if rf_name.upper() in ("BASE_URL", "BASEURL"):
                continue

            # Skip duplicates
            if rf_name in seen_names:
                continue
            seen_names.add(rf_name)

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

        # Generate URL variables for detected sessions that don't have variables
        for base_url, alias in self.url_sessions.items():
            var_name = self._get_url_variable_for_alias(alias)
            if var_name not in seen_names:
                variables.append(
                    RobotVariable(
                        name=var_name,
                        value=base_url,
                    )
                )
                seen_names.add(var_name)

        # Default headers as dict variable
        variables.append(
            RobotVariable(
                name="DEFAULT_HEADERS",
                value=self.default_headers,
                is_dict=True,
            )
        )

        return variables

    def _extract_bearer_tokens(
        self, collection: BrunoCollection
    ) -> list[RobotVariable]:
        """Extract ALL hardcoded values from requests and create variables.

        Returns list of variables to add to suite variables.
        """
        all_vars = []
        seen_values = set()

        # Initialize all extraction maps
        if not hasattr(self, "_token_var_map"):
            self._token_var_map = {}
        if not hasattr(self, "_header_var_map"):
            self._header_var_map = {}
        if not hasattr(self, "_form_var_map"):
            self._form_var_map = {}

        # Collect all requests
        all_requests = list(collection.requests)
        for folder in collection.folders:
            all_requests.extend(self._collect_folder_requests(folder))

        # Counters for different value types
        token_counter = 1
        header_counter = 1
        form_counter = 1

        for request in all_requests:
            if not request.http:
                continue

            http = request.http

            # 1. Extract Bearer tokens from headers
            if http.headers:
                for key, value in http.headers.items():
                    if key.lower() == "authorization" and value.startswith("Bearer "):
                        token_value = value[7:]  # Remove "Bearer " prefix
                        if token_value and token_value not in seen_values and not token_value.startswith("${"):
                            seen_values.add(token_value)
                            var_name = f"AUTH_TOKEN_{token_counter}"
                            token_counter += 1
                            all_vars.append(
                                RobotVariable(
                                    name=var_name,
                                    value=None,  # Don't expose the value
                                    comment="Auth token - set via environment or OAuth2",
                                )
                            )
                            self._token_var_map[token_value] = var_name

                    # 2. Extract other header values that look like secrets/tokens
                    elif self._is_secret_header(key, value):
                        if value and value not in seen_values and not value.startswith("${"):
                            seen_values.add(value)
                            var_name = self._make_header_var_name(key, header_counter)
                            header_counter += 1
                            all_vars.append(
                                RobotVariable(
                                    name=var_name,
                                    value=None,  # Don't expose the value
                                    comment=f"Header value - set manually",
                                )
                            )
                            if not hasattr(self, "_header_var_map"):
                                self._header_var_map = {}
                            self._header_var_map[(key, value)] = var_name

            # 3. Extract form data values
            if http.body and http.body.type == BodyType.FORM and isinstance(http.body.data, dict):
                for key, value in http.body.data.items():
                    if value and isinstance(value, str) and value not in seen_values and not value.startswith("${"):
                        # Check if it looks like a secret or important value
                        if self._is_secret_form_field(key, value):
                            seen_values.add(value)
                            var_name = self._make_form_var_name(key, form_counter)
                            form_counter += 1
                            all_vars.append(
                                RobotVariable(
                                    name=var_name,
                                    value=None,  # Don't expose the value
                                    comment=f"Form field - set manually",
                                )
                            )
                            if not hasattr(self, "_form_var_map"):
                                self._form_var_map = {}
                            self._form_var_map[(key, value)] = var_name

        return all_vars

    def _is_secret_header(self, key: str, value: str) -> bool:
        """Check if header value should be extracted as variable."""
        secret_patterns = [
            "token", "secret", "key", "auth", "password", "csrf"
        ]
        key_lower = key.lower()

        # Check if header name suggests it's a secret
        for pattern in secret_patterns:
            if pattern in key_lower:
                return True

        # Check if value looks like a token/hash
        if len(value) > 20 and all(c.isalnum() or c in "-_" for c in value):
            return True

        return False

    def _is_secret_form_field(self, key: str, value: str) -> bool:
        """Check if form field should be extracted as variable."""
        # Always extract these fields
        extract_fields = [
            "client_id", "client_secret", "code", "code_verifier",
            "redirect_uri", "username", "password", "grant_type"
        ]
        key_lower = key.lower()

        for field in extract_fields:
            if field in key_lower:
                return True

        # Extract long values that look like tokens
        if len(value) > 20 and all(c.isalnum() or c in "-_:" for c in value):
            return True

        return False

    def _make_header_var_name(self, key: str, counter: int) -> str:
        """Create a variable name for a header value."""
        # Convert header name to variable name
        clean = key.upper().replace("-", "_").replace(" ", "_")
        return f"{clean}_{counter}"

    def _make_form_var_name(self, key: str, counter: int) -> str:
        """Create a variable name for a form field."""
        # Convert field name to variable name
        clean = key.upper().replace("-", "_").replace(" ", "_")
        return f"{clean}_{counter}"

    def _get_token_variable(self, token_value: str) -> str | None:
        """Get variable name for a token value.

        Returns variable reference like ${AUTH_TOKEN_1} or None if not found.
        """
        if hasattr(self, "_token_var_map") and token_value in self._token_var_map:
            return f"${{{self._token_var_map[token_value]}}}"
        return None

    def _get_header_variable(self, key: str, value: str) -> str | None:
        """Get variable reference for a header value.

        Returns variable reference like ${X_CSRF_TOKEN_1} or None if not found.
        """
        if hasattr(self, "_header_var_map"):
            var_name = self._header_var_map.get((key, value))
            if var_name:
                return f"${{{var_name}}}"
        return None

    def _get_form_variable(self, key: str, value: str) -> str | None:
        """Get variable reference for a form field value.

        Returns variable reference like ${CLIENT_ID_1} or None if not found.
        """
        if hasattr(self, "_form_var_map"):
            var_name = self._form_var_map.get((key, value))
            if var_name:
                return f"${{{var_name}}}"
        return None

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
