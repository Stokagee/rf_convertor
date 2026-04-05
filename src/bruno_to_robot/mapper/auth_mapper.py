"""Map Bruno authentication to Robot Framework session configuration."""

from __future__ import annotations

from bruno_to_robot.models.bruno import (
    AuthType,
    BrunoAuth,
    BrunoOAuth2Config,
    OAuth2Flow,
)
from bruno_to_robot.models.robot import RobotStep, RobotVariable


class AuthMapper:
    """Maps Bruno authentication types to Robot Framework session setup."""

    def map_auth(self, auth: BrunoAuth | None, session_name: str = "api") -> list[RobotStep]:
        """Map Bruno auth to Robot session creation steps.

        Args:
            auth: Bruno auth configuration
            session_name: Name of the session alias

        Returns:
            List of RobotSteps for session creation
        """
        if not auth or auth.type == AuthType.NONE:
            return [self._create_basic_session(session_name)]

        if auth.type == AuthType.BASIC:
            return self._map_basic_auth(auth, session_name)
        elif auth.type == AuthType.BEARER:
            return self._map_bearer_auth(auth, session_name)
        elif auth.type == AuthType.API_KEY:
            return self._map_api_key_auth(auth, session_name)
        elif auth.type == AuthType.OAUTH2:
            return self._map_oauth2_auth(auth, session_name)
        elif auth.type == AuthType.CERT:
            return self._map_cert_auth(auth, session_name)
        elif auth.type == AuthType.INHERIT:
            # Will be handled at collection level
            return [self._create_basic_session(session_name)]

        return [self._create_basic_session(session_name)]

    def _create_basic_session(
        self,
        session_name: str,
        **kwargs: str,
    ) -> RobotStep:
        """Create basic session without auth."""
        args = [session_name, "${BASE_URL}"]

        for key, value in kwargs.items():
                args.append(f"{key}={value}")

        return RobotStep(
            keyword="Create Session",
            args=args,
        )

    def _map_basic_auth(self, auth: BrunoAuth, session_name: str) -> list[RobotStep]:
        """Map Basic authentication."""
        # Use variables for credentials (never hardcode)
        username = auth.username or "${USERNAME}"
        password = auth.password or "${PASSWORD}"

        return [
            RobotStep(
                keyword="Create Session",
                args=[
                    session_name,
                    "${BASE_URL}",
                    f"auth={{{username}:{password}}}",
                ],
            ),
        ]

    def _map_bearer_auth(self, auth: BrunoAuth, session_name: str) -> list[RobotStep]:
        """Map Bearer token authentication."""
        token = auth.token or "${BEARER_TOKEN}"

        return [
            RobotStep(
                keyword="Create Session",
                args=[session_name, "${BASE_URL}"],
            ),
            RobotStep(
                keyword="Set To Dictionary",
                args=["${DEFAULT_HEADERS}", "Authorization", f"'Bearer {token}'"],
            ),
        ]

    def _map_api_key_auth(self, auth: BrunoAuth, session_name: str) -> list[RobotStep]:
        """Map API Key authentication."""
        api_key = auth.api_key or "${API_KEY}"
        key_name = auth.api_key_name or "X-API-Key"
        location = auth.api_key_location or "header"

        steps = [
            RobotStep(
                keyword="Create Session",
                args=[session_name, "${BASE_URL}"],
            ),
        ]

        if location == "header":
            steps.append(
                RobotStep(
                    keyword="Set To Dictionary",
                    args=["${DEFAULT_HEADERS}", f"'{key_name}'", f"'{api_key}'"],
                )
            )
        # Note: query param API keys are handled per-request

        return steps

    def _map_oauth2_auth(self, auth: BrunoAuth, session_name: str) -> list[RobotStep]:
        """Map OAuth 2.0 authentication based on flow type.

        Generates keywords for:
        - Client Credentials flow
        - Resource Owner Password flow
        - Authorization Code flow (with optional PKCE)
        - Client Assertion (JWT Bearer)
        """
        if not auth.oauth2:
            # Fallback: generate placeholder for manual token
            return self._map_oauth2_placeholder(session_name)

        oauth2 = auth.oauth2
        flow = oauth2.flow

        if flow == OAuth2Flow.CLIENT_CREDENTIALS:
            return self._map_client_credentials(oauth2, session_name)
        elif flow == OAuth2Flow.PASSWORD:
            return self._map_password_flow(oauth2, session_name)
        elif flow == OAuth2Flow.AUTHORIZATION_CODE:
            if oauth2.pkce_enabled:
                return self._map_pkce_flow(oauth2, session_name)
            return self._map_auth_code_flow(oauth2, session_name)

        return self._map_oauth2_placeholder(session_name)

    def _map_client_credentials(
        self,
        oauth2: BrunoOAuth2Config,
        session_name: str,
    ) -> list[RobotStep]:
        """Generate Client Credentials flow keywords."""
        return [
            RobotStep(
                keyword="Get Client Credentials Token",
                args=[session_name],
                assign="${access_token}",
            ),
            RobotStep(
                keyword="Set To Dictionary",
                args=["${DEFAULT_HEADERS}", "Authorization", "'Bearer ${access_token}'"],
            ),
            RobotStep(
                keyword="Create Session",
                args=[session_name, "${BASE_URL}", "headers=${DEFAULT_HEADERS}"],
            ),
        ]

    def _map_password_flow(
        self,
        oauth2: BrunoOAuth2Config,
        session_name: str,
    ) -> list[RobotStep]:
        """Generate Resource Owner Password flow keywords."""
        return [
            RobotStep(
                keyword="Get Password Token",
                args=[session_name],
                assign="${access_token}",
            ),
            RobotStep(
                keyword="Set To Dictionary",
                args=["${DEFAULT_HEADERS}", "Authorization", "'Bearer ${access_token}'"],
            ),
            RobotStep(
                keyword="Create Session",
                args=[session_name, "${BASE_URL}", "headers=${DEFAULT_HEADERS}"],
            ),
        ]

    def _map_auth_code_flow(
        self,
        oauth2: BrunoOAuth2Config,
        session_name: str,
    ) -> list[RobotStep]:
        """Generate Authorization Code flow keywords (without PKCE)."""
        return [
            RobotStep(
                keyword="Log",
                args=["Manual step: Get authorization code from callback"],
                comment="User must obtain auth code manually",
            ),
            RobotStep(
                keyword="Get Authorization Code Token",
                args=[session_name, "${AUTH_CODE}"],
                assign="${access_token}",
            ),
            RobotStep(
                keyword="Set To Dictionary",
                args=["${DEFAULT_HEADERS}", "Authorization", "'Bearer ${access_token}'"],
            ),
            RobotStep(
                keyword="Create Session",
                args=[session_name, "${BASE_URL}", "headers=${DEFAULT_HEADERS}"],
            ),
        ]

    def _map_pkce_flow(
        self,
        oauth2: BrunoOAuth2Config,
        session_name: str,
    ) -> list[RobotStep]:
        """Generate PKCE flow keywords."""
        return [
            RobotStep(
                keyword="Generate PKCE Verifier",
                assign="${code_verifier}",
            ),
            RobotStep(
                keyword="Generate PKCE Challenge",
                args=["${code_verifier}"],
                assign="${code_challenge}",
            ),
            RobotStep(
                keyword="Log",
                args=["Manual step: Navigate to auth URL with code_challenge"],
                comment="Get auth code from authorization endpoint",
            ),
            RobotStep(
                keyword="Get PKCE Token",
                args=[session_name, "${AUTH_CODE}", "${code_verifier}"],
                assign="${access_token}",
            ),
            RobotStep(
                keyword="Set To Dictionary",
                args=["${DEFAULT_HEADERS}", "Authorization", "'Bearer ${access_token}'"],
            ),
            RobotStep(
                keyword="Create Session",
                args=[session_name, "${BASE_URL}", "headers=${DEFAULT_HEADERS}"],
            ),
        ]

    def _map_oauth2_placeholder(self, session_name: str) -> list[RobotStep]:
        """Generate placeholder for OAuth2 (fallback)."""
        return [
            RobotStep(
                keyword="Create Session",
                args=[session_name, "${BASE_URL}"],
            ),
            RobotStep(
                keyword="Get OAuth Token",
                args=[session_name],
                assign="${token}",
                comment="TODO: Implement OAuth2 token retrieval keyword",
            ),
            RobotStep(
                keyword="Set To Dictionary",
                args=["${DEFAULT_HEADERS}", "Authorization", "'Bearer ${token}'"],
            ),
        ]

    def _map_cert_auth(self, auth: BrunoAuth, session_name: str) -> list[RobotStep]:
        """Map client certificate authentication with PKCS#12 support."""
        cert_path = auth.cert_path or "${CERT_PATH}"
        key_path = auth.key_path or "${KEY_PATH}"
        key_password = auth.key_password or "${KEY_PASSWORD}"
        ca_bundle = auth.ca_bundle_path or "${SSL_VERIFY}"

        # Check if PKCS#12
        if cert_path.endswith((".p12", ".pfx")) or (cert_path == "${CERT_PATH}" and "${CERT_PATH}".endswith((".p12", ".pfx"))):
            return [
                RobotStep(
                    keyword="Load PKCS12 Certificate",
                    args=[cert_path, key_password],
                    assign="${cert_tuple}",
                ),
                RobotStep(
                    keyword="Create Session",
                    args=[
                        session_name,
                        "${BASE_URL}",
                        "cert=${cert_tuple}",
                        f"verify={ca_bundle}",
                    ],
                ),
            ]

        # PEM format
        return [
            RobotStep(
                keyword="Create Session",
                args=[
                    session_name,
                "${BASE_URL}",
                    f"cert=({cert_path}, {key_path})",
                    f"verify={ca_bundle}",
                ],
            ),
        ]

    def get_auth_variables(self, auth: BrunoAuth | None) -> list[RobotVariable]:
        """Get variables needed for authentication.

        Returns placeholder variables for secrets.
        """
        if not auth:
            return []

        variables = []

        if auth.type == AuthType.BASIC:
            if not auth.username:
                variables.append(
                    RobotVariable(
                        name="USERNAME",
                        value=None,
                        comment="Set via environment or variable file",
                    )
                )
            if not auth.password:
                variables.append(
                    RobotVariable(
                        name="PASSWORD",
                        value=None,
                        comment="Secret - set via environment",
                    )
                )

        elif auth.type == AuthType.BEARER:
            if not auth.token:
                variables.append(
                    RobotVariable(
                        name="BEARER_TOKEN",
                        value=None,
                        comment="Secret - set via environment",
                    )
                )

        elif auth.type == AuthType.API_KEY:
            if not auth.api_key:
                variables.append(
                    RobotVariable(
                        name="API_KEY",
                        value=None,
                        comment="Secret - set via environment",
                    )
                )

        elif auth.type == AuthType.OAUTH2:
            variables.extend(self._get_oauth2_variables(auth))

        elif auth.type == AuthType.CERT:
            if not auth.cert_path:
                variables.append(
                    RobotVariable(
                        name="CERT_PATH",
                        value=None,
                        comment="Path to client certificate",
                    )
                )
            if not auth.key_path:
                variables.append(
                    RobotVariable(
                        name="KEY_PATH",
                        value=None,
                        comment="Path to private key",
                    )
                )
            if auth.key_password:
                variables.append(
                    RobotVariable(
                        name="KEY_PASSWORD",
                        value=None,
                        comment="Password for key/PKCS12",
                    )
                )

            # SSL verify configuration
            variables.append(
                RobotVariable(
                    name="SSL_VERIFY",
                    value="${TRUE}",
                    comment="Path to CA bundle or True/False",
                )
            )

        return variables

    def _get_oauth2_variables(self, auth: BrunoAuth) -> list[RobotVariable]:
        """Get variables needed for OAuth2 authentication."""
        if not auth.oauth2:
                return [
                    RobotVariable(
                        name="ACCESS_TOKEN",
                        value=None,
                        comment="OAuth2 token - obtain via flow",
                    ),
                ]

        oauth2 = auth.oauth2

        # Skip OAuth2 variables if config is not properly set up
        if not self._is_oauth2_configured(oauth2):
            logger.info("OAuth2 config has empty values - returning minimal token variable")
            return [
                RobotVariable(
                    name="ACCESS_TOKEN",
                    value=None,
                    comment="OAuth2 token - obtain via flow",
                ),
            ]

        credentials = oauth2.credentials
        variables = []

        # Token endpoint
        if oauth2.access_token_url:
            variables.append(
                RobotVariable(
                    name="TOKEN_URL",
                    value=oauth2.access_token_url,
                )
            )
        else:
            variables.append(
                RobotVariable(
                    name="TOKEN_URL",
                    value=None,
                    comment="OAuth2 token endpoint - set via environment",
                )
            )

        # Client credentials
        if credentials.client_id:
            variables.append(
                RobotVariable(
                    name="CLIENT_ID",
                    value=credentials.client_id,
                )
            )
        else:
            variables.append(
                RobotVariable(
                    name="CLIENT_ID",
                    value=None,
                    comment="OAuth2 client ID",
                )
            )

        if credentials.client_secret:
            # Don't expose secret, use env var reference
            variables.append(
                RobotVariable(
                    name="CLIENT_SECRET",
                    value="%{CLIENT_SECRET}",
                    comment="Secret - set via environment",
                )
            )
        else:
            variables.append(
                RobotVariable(
                    name="CLIENT_SECRET",
                    value=None,
                    comment="Secret - set via environment",
                )
            )

        # Scope
        if oauth2.scope:
            variables.append(
                RobotVariable(
                    name="OAUTH_SCOPE",
                    value=oauth2.scope,
                )
            )

        # Flow-specific variables
        if oauth2.flow == OAuth2Flow.PASSWORD:
            variables.extend([
                RobotVariable(
                    name="OAUTH_USERNAME",
                    value=oauth2.username or "%{OAUTH_USERNAME}",
                    comment="Resource owner username",
                ),
                RobotVariable(
                    name="OAUTH_PASSWORD",
                    value="%{OAUTH_PASSWORD}",
                    comment="Secret - set via environment",
                ),
            ])

        elif oauth2.flow == OAuth2Flow.AUTHORIZATION_CODE:
            # Always add REDIRECT_URI for authorization code flow
            variables.append(
                RobotVariable(
                    name="REDIRECT_URI",
                    value=oauth2.callback_url or None,
                    comment="OAuth2 callback URL - set via environment or here" if not oauth2.callback_url else None,
                )
            )
            if oauth2.authorization_url:
                variables.append(
                    RobotVariable(
                        name="AUTH_URL",
                        value=oauth2.authorization_url,
                    )
                )

            if oauth2.pkce_enabled:
                variables.extend([
                    RobotVariable(
                        name="CODE_VERIFIER",
                        value=None,
                        comment="Generated at runtime for PKCE",
                    ),
                    RobotVariable(
                        name="CODE_CHALLENGE",
                        value=None,
                        comment="Generated at runtime for PKCE",
                    ),
                ])

            variables.extend([
                RobotVariable(
                    name="AUTH_CODE",
                    value=None,
                    comment="Authorization code from callback",
                ),
            ])

        # Refresh token support
        if oauth2.refresh_token_url:
            variables.append(
                RobotVariable(
                    name="REFRESH_TOKEN_URL",
                    value=oauth2.refresh_token_url,
                )
            )

        # Token management variables (runtime)
        variables.extend([
            RobotVariable(
                name="ACCESS_TOKEN",
                value=None,
                comment="Obtained at runtime",
            ),
            RobotVariable(
                name="REFRESH_TOKEN",
                value=None,
                comment="Obtained at runtime",
            ),
            RobotVariable(
                name="TOKEN_EXPIRY",
                value=None,
                comment="Unix timestamp",
            ),
        ])

        # Client assertion (JWT Bearer)
        if oauth2.client_assertion_type:
            variables.extend([
                RobotVariable(
                    name="CLIENT_ASSERTION",
                    value=oauth2.client_assertion or "%{CLIENT_ASSERTION}",
                    comment="JWT assertion for authentication",
                ),
            ])
            if oauth2.private_key_path:
                variables.append(
                    RobotVariable(
                        name="PRIVATE_KEY_PATH",
                        value=oauth2.private_key_path,
                        comment="Path to private key for signing JWT",
                    )
                )

        return variables

    def _is_oauth2_configured(self, oauth2: BrunoOAuth2Config) -> bool:
        """Check if OAuth2 has actual configuration values (not just empty placeholders).

        Returns True if at least token_url and client_id are set.
        """
        # Check if we have the minimum required configuration
        has_token_url = bool(oauth2.access_token_url and oauth2.access_token_url.strip())
        has_client_id = bool(oauth2.credentials.client_id and oauth2.credentials.client_id.strip())

        # For password flow, also need username
        if oauth2.flow == OAuth2Flow.PASSWORD:
            has_username = bool(oauth2.username and oauth2.username.strip())
            return has_token_url and has_client_id and has_username

        return has_token_url and has_client_id

    def get_oauth2_keywords(self, auth: BrunoAuth | None) -> dict[str, list[RobotStep]]:
        """Get custom keywords needed for OAuth2 flows.

        These keywords will be added to the *** Keywords *** section.
        """
        if not auth or auth.type != AuthType.OAUTH2 or not auth.oauth2:
                return {}

        oauth2 = auth.oauth2

        # Skip OAuth2 keywords if config is not properly set up
        if not self._is_oauth2_configured(oauth2):
            logger.info("OAuth2 config has empty values - skipping OAuth2 keywords generation")
            return {}

        keywords = {}

        # Common token validation keyword
        keywords["Ensure Valid Token"] = [
            RobotStep(
                keyword="Run Keyword And Return Status",
                args=["Token Is Expired"],
                assign="${expired}",
            ),
            RobotStep(
                keyword="Run Keyword If",
                args=["${expired}", "Refresh Access Token"],
            ),
            RobotStep(
                keyword="RETURN",
                args=["${ACCESS_TOKEN}"],
            ),
        ]

        # Token expiry check - use library method
        keywords["Token Is Expired"] = [
            RobotStep(
                keyword="OAuth2.Is Token Expired",
                args=[],
                assign="${expired}",
            ),
            RobotStep(
                keyword="RETURN",
                args=["${expired}"],
            ),
        ]

        # Flow-specific keywords
        if oauth2.flow == OAuth2Flow.CLIENT_CREDENTIALS:
            keywords["Get Client Credentials Token"] = self._build_client_credentials_keyword(oauth2)
            keywords["Refresh Access Token"] = keywords["Get Client Credentials Token"]

        elif oauth2.flow == OAuth2Flow.PASSWORD:
            keywords["Get Password Token"] = self._build_password_keyword(oauth2)
            keywords["Refresh Access Token"] = keywords["Get Password Token"]

        elif oauth2.flow == OAuth2Flow.AUTHORIZATION_CODE:
            if oauth2.pkce_enabled:
                keywords["Generate PKCE Verifier"] = self._build_pkce_verifier_keyword()
                keywords["Generate PKCE Challenge"] = self._build_pkce_challenge_keyword()
                keywords["Get PKCE Token"] = self._build_pkce_token_keyword(oauth2)
                keywords["Refresh Access Token"] = [
                    RobotStep(
                        keyword="Log",
                        args=["PKCE flow does not support refresh - re-authenticate"],
                    ),
                ]
            else:
                keywords["Get Authorization Code Token"] = self._build_auth_code_keyword(oauth2)
                keywords["Refresh Access Token"] = self._build_refresh_token_keyword(oauth2)

        return keywords

    def _build_client_credentials_keyword(self, oauth2: BrunoOAuth2Config) -> list[RobotStep]:
        """Build Client Credentials token keyword."""
        args = [
            "token_url=${TOKEN_URL}",
            "client_id=${CLIENT_ID}",
            "client_secret=${CLIENT_SECRET}",
        ]
        if oauth2.scope:
            args.append("scope=${OAUTH_SCOPE}")

        return [
            RobotStep(
                keyword="OAuth2.Get Client Credentials Token",
                args=args,
                assign="${token}",
            ),
            RobotStep(
                keyword="Set Suite Variable",
                args=["${ACCESS_TOKEN}", "${token}"],
            ),
            RobotStep(
                keyword="${refresh}=    OAuth2.Get Refresh Token",
                args=[],
                comment="Get refresh token if available",
            ),
            RobotStep(
                keyword="Run Keyword If",
                args=["${refresh}", "Set Suite Variable", "${REFRESH_TOKEN}", "${refresh}"],
            ),
            RobotStep(
                keyword="RETURN",
                args=["${token}"],
            ),
        ]

    def _build_password_keyword(self, oauth2: BrunoOAuth2Config) -> list[RobotStep]:
        """Build Resource Owner Password token keyword."""
        args = [
            "token_url=${TOKEN_URL}",
            "client_id=${CLIENT_ID}",
            "client_secret=${CLIENT_SECRET}",
            "username=${OAUTH_USERNAME}",
            "password=${OAUTH_PASSWORD}",
        ]
        if oauth2.scope:
            args.append("scope=${OAUTH_SCOPE}")

        return [
            RobotStep(
                keyword="OAuth2.Get Password Token",
                args=args,
                assign="${token}",
            ),
            RobotStep(
                keyword="Set Suite Variable",
                args=["${ACCESS_TOKEN}", "${token}"],
            ),
            RobotStep(
                keyword="${refresh}=    OAuth2.Get Refresh Token",
                args=[],
                comment="Get refresh token if available",
            ),
            RobotStep(
                keyword="Run Keyword If",
                args=["${refresh}", "Set Suite Variable", "${REFRESH_TOKEN}", "${refresh}"],
            ),
            RobotStep(
                keyword="RETURN",
                args=["${token}"],
            ),
        ]

    def _build_auth_code_keyword(self, oauth2: BrunoOAuth2Config) -> list[RobotStep]:
        """Build Authorization Code token keyword."""
        return [
            RobotStep(
                keyword="OAuth2.Get Authorization Code Token",
                args=[
                    "token_url=${TOKEN_URL}",
                    "client_id=${CLIENT_ID}",
                    "client_secret=${CLIENT_SECRET}",
                    "code=${AUTH_CODE}",
                    "redirect_uri=${REDIRECT_URI}",
                ],
                assign="${token}",
            ),
            RobotStep(
                keyword="Set Suite Variable",
                args=["${ACCESS_TOKEN}", "${token}"],
            ),
            RobotStep(
                keyword="${refresh}=    OAuth2.Get Refresh Token",
                args=[],
                comment="Get refresh token if available",
            ),
            RobotStep(
                keyword="Run Keyword If",
                args=["${refresh}", "Set Suite Variable", "${REFRESH_TOKEN}", "${refresh}"],
            ),
            RobotStep(
                keyword="RETURN",
                args=["${token}"],
            ),
        ]

    def _build_pkce_verifier_keyword(self) -> list[RobotStep]:
        """Build PKCE code verifier generation keyword."""
        return [
            RobotStep(
                keyword="OAuth2.Generate PKCE Verifier",
                assign="${verifier}",
            ),
            RobotStep(
                keyword="Set Suite Variable",
                args=["${CODE_VERIFIER}", "${verifier}"],
            ),
            RobotStep(
                keyword="RETURN",
                args=["${verifier}"],
            ),
        ]

    def _build_pkce_challenge_keyword(self) -> list[RobotStep]:
        """Build PKCE code challenge generation keyword."""
        return [
            RobotStep(
                keyword="OAuth2.Generate PKCE Challenge",
                args=["${CODE_VERIFIER}"],
                assign="${challenge}",
            ),
            RobotStep(
                keyword="Set Suite Variable",
                args=["${CODE_CHALLENGE}", "${challenge}"],
            ),
            RobotStep(
                keyword="RETURN",
                args=["${challenge}"],
            ),
        ]

    def _build_pkce_token_keyword(self, oauth2: BrunoOAuth2Config) -> list[RobotStep]:
        """Build PKCE token exchange keyword."""
        args = [
            "token_url=${TOKEN_URL}",
            "client_id=${CLIENT_ID}",
            "code=${AUTH_CODE}",
            "code_verifier=${CODE_VERIFIER}",
            "redirect_uri=${REDIRECT_URI}",
        ]
        if oauth2.credentials.client_secret:
            args.append("client_secret=${CLIENT_SECRET}")

        return [
            RobotStep(
                keyword="OAuth2.Get PKCE Token",
                args=args,
                assign="${token}",
            ),
            RobotStep(
                keyword="Set Suite Variable",
                args=["${ACCESS_TOKEN}", "${token}"],
            ),
            RobotStep(
                keyword="${refresh}=    OAuth2.Get Refresh Token",
                args=[],
                comment="Get refresh token if available",
            ),
            RobotStep(
                keyword="Run Keyword If",
                args=["${refresh}", "Set Suite Variable", "${REFRESH_TOKEN}", "${refresh}"],
            ),
            RobotStep(
                keyword="RETURN",
                args=["${token}"],
            ),
        ]

    def _build_refresh_token_keyword(self, oauth2: BrunoOAuth2Config) -> list[RobotStep]:
        """Build refresh token keyword."""
        return [
            RobotStep(
                keyword="OAuth2.Refresh Token",
                args=[
                    "token_url=${TOKEN_URL}",
                    "client_id=${CLIENT_ID}",
                    "client_secret=${CLIENT_SECRET}",
                    "refresh_token=${REFRESH_TOKEN}",
                ],
                assign="${token}",
            ),
            RobotStep(
                keyword="Set Suite Variable",
                args=["${ACCESS_TOKEN}", "${token}"],
            ),
            RobotStep(
                keyword="${new_refresh}=    OAuth2.Get Refresh Token",
                args=[],
                comment="Get new refresh token if rotated",
            ),
            RobotStep(
                keyword="Run Keyword If",
                args=["${new_refresh}", "Set Suite Variable", "${REFRESH_TOKEN}", "${new_refresh}"],
            ),
            RobotStep(
                keyword="RETURN",
                args=["${token}"],
            ),
        ]
