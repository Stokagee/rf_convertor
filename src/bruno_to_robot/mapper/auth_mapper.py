"""Map Bruno authentication to Robot Framework session configuration."""

from __future__ import annotations

from typing import Any

from bruno_to_robot.models.bruno import AuthType, BrunoAuth
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

    def _create_basic_session(self, session_name: str, **kwargs) -> RobotStep:
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
        """Map OAuth 2.0 authentication.

        Note: Full OAuth flow requires custom keyword implementation.
        This creates a placeholder for token management.
        """
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
        """Map client certificate authentication."""
        cert_path = auth.cert_path or "${CERT_PATH}"
        key_path = auth.key_path or "${KEY_PATH}"

        return [
            RobotStep(
                keyword="Create Session",
                args=[
                    session_name,
                    "${BASE_URL}",
                    f"cert=({cert_path}, {key_path})",
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
                        comment="Path to client key",
                    )
                )

        elif auth.type == AuthType.OAUTH2:
            variables.extend(
                [
                    RobotVariable(
                        name="OAUTH_TOKEN_URL",
                        value=None,
                        comment="OAuth2 token endpoint",
                    ),
                    RobotVariable(
                        name="OAUTH_CLIENT_ID",
                        value=None,
                        comment="OAuth2 client ID",
                    ),
                    RobotVariable(
                        name="OAUTH_CLIENT_SECRET",
                        value=None,
                        comment="Secret - set via environment",
                    ),
                ]
            )

        return variables
