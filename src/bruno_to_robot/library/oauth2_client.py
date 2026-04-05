"""OAuth2Library for Robot Framework - Token Management.

This module provides OAuth 2.0 token management for Robot Framework tests.
Supports Client Credentials, Resource Owner Password, Authorization Code (with PKCE),
and Client Assertion (JWT Bearer) flows.

Usage in Robot Framework:
    Library    bruno_to_robot.library.oauth2_client.OAuth2Client    AS    OAuth2

    ${token}=    Get Client Credentials Token
    ...    token_url=https://auth.example.com/oauth/token
    ...    client_id=my_client
    ...    client_secret=my_secret
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urlparse, parse_qs

import requests

if TYPE_CHECKING:
    from collections.abc import Mapping


class TokenExpiredError(Exception):
    """Token has expired and needs refresh."""

    def __init__(self, message: str = "Token expired", session_alias: str = "default") -> None:
        super().__init__(message)
        self.session_alias = session_alias


class OAuth2Error(Exception):
    """Base OAuth2 error."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass
class TokenInfo:
    """OAuth2 token information."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: str | None = None
    scope: str | None = None
    obtained_at: float = field(default_factory=time.time)

    @property
    def expires_at(self) -> float:
        """Calculate expiration timestamp with 60s buffer."""
        return self.obtained_at + self.expires_in - 60

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return time.time() >= self.expires_at

    @property
    def authorization_header(self) -> str:
        """Get Authorization header value."""
        return f"{self.token_type} {self.access_token}"


class OAuth2Client:
    """OAuth2 client for token management in Robot Framework tests.

    This class can be used as a Robot Framework library.

    Example Robot Framework usage:
        *** Settings ***
        Library    bruno_to_robot.library.oauth2_client.OAuth2Client    AS    OAuth

        *** Variables ***
        ${TOKEN_URL}    https://auth.example.com/oauth/token
        ${CLIENT_ID}    %{CLIENT_ID}
        ${CLIENT_SECRET}    %{CLIENT_SECRET}

        *** Keywords ***
        Get Access Token
            ${token}=    OAuth.Get Client Credentials Token
            ...    token_url=${TOKEN_URL}
            ...    client_id=${CLIENT_ID}
            ...    client_secret=${CLIENT_SECRET}
            [Return]    ${token}
    """

    ROBOT_LIBRARY_SCOPE = "SUITE"
    ROBOT_LIBRARY_DOC_FORMAT = "ROBOT"

    def __init__(self) -> None:
        """Initialize OAuth2 client."""
        self._tokens: dict[str, TokenInfo] = {}
        self._sessions: dict[str, requests.Session] = {}

    # ========================================================================
    # Client Credentials Flow
    # ========================================================================

    def get_client_credentials_token(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str | None = None,
        session_alias: str = "default",
        timeout: int = 30,
        extra_params: Mapping[str, str] | None = None,
    ) -> str:
        """Get token using OAuth2 client_credentials flow.

        This is the most common flow for service-to-service authentication.

        Args:
            token_url: OAuth2 token endpoint URL
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            scope: Optional OAuth2 scope
            session_alias: Alias for storing the token (default: "default")
            timeout: Request timeout in seconds
            extra_params: Additional parameters to include in token request

        Returns:
            Access token string

        Robot Framework Example:
            ${token}=    Get Client Credentials Token
            ...    token_url=https://auth.example.com/oauth/token
            ...    client_id=my_client
            ...    client_secret=my_secret
            ...    scope=api:read api:write
        """
        # Validate required parameters
        if not token_url:
            raise OAuth2Error("TOKEN_URL is not set. Please configure OAuth2 token endpoint.")
        if not client_id:
            raise OAuth2Error("CLIENT_ID is not set. Please configure OAuth2 client ID.")
        if not client_secret:
            raise OAuth2Error("CLIENT_SECRET is not set. Please configure OAuth2 client secret.")

        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }

        if scope:
            data["scope"] = scope

        if extra_params:
            data.update(extra_params)

        resp = requests.post(token_url, data=data, timeout=timeout)
        self._handle_token_error(resp)

        token_data = resp.json()
        token = TokenInfo(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token"),
            scope=token_data.get("scope"),
        )
        self._tokens[session_alias] = token
        return token.access_token

    # ========================================================================
    # Resource Owner Password Flow
    # ========================================================================

    def get_password_token(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        scope: str | None = None,
        session_alias: str = "default",
        timeout: int = 30,
    ) -> str:
        """Get token using OAuth2 resource owner password credentials flow.

        Note: This flow is deprecated in OAuth 2.1 but still widely used.

        Args:
            token_url: OAuth2 token endpoint URL
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            username: Resource owner username
            password: Resource owner password
            scope: Optional OAuth2 scope
            session_alias: Alias for storing the token
            timeout: Request timeout in seconds

        Returns:
            Access token string
        """
        # Validate required parameters
        if not token_url:
            raise OAuth2Error("TOKEN_URL is not set. Please configure OAuth2 token endpoint.")
        if not client_id:
            raise OAuth2Error("CLIENT_ID is not set. Please configure OAuth2 client ID.")
        if not username:
            raise OAuth2Error("OAUTH_USERNAME is not set. Please configure resource owner username.")
        if not password:
            raise OAuth2Error("OAUTH_PASSWORD is not set. Please configure resource owner password.")

        data: dict[str, str] = {
            "grant_type": "password",
            "client_id": client_id,
            "client_secret": client_secret,
            "username": username,
            "password": password,
        }

        if scope:
            data["scope"] = scope

        resp = requests.post(token_url, data=data, timeout=timeout)
        self._handle_token_error(resp)

        token_data = resp.json()
        token = TokenInfo(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token"),
            scope=token_data.get("scope"),
        )
        self._tokens[session_alias] = token
        return token.access_token

    # ========================================================================
    # Authorization Code Flow
    # ========================================================================

    def get_authorization_url(
        self,
        authorization_url: str,
        client_id: str,
        redirect_uri: str,
        scope: str | None = None,
        state: str | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str = "S256",
    ) -> str:
        """Generate authorization URL for authorization code flow.

        Use this to get the URL to redirect the user for authorization.

        Args:
            authorization_url: OAuth2 authorization endpoint URL
            client_id: OAuth2 client ID
            redirect_uri: Callback URL after authorization
            scope: Optional OAuth2 scope
            state: Optional state parameter for CSRF protection
            code_challenge: PKCE code challenge (if using PKCE)
            code_challenge_method: PKCE challenge method (S256 or plain)

        Returns:
            Authorization URL string

        Robot Framework Example:
            ${auth_url}=    Get Authorization URL
            ...    authorization_url=https://auth.example.com/oauth/authorize
            ...    client_id=my_client
            ...    redirect_uri=http://localhost:3000/callback
            Log    Navigate to: ${auth_url}
        """
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        }

        if scope:
            params["scope"] = scope

        if state:
            params["state"] = state

        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method

        return f"{authorization_url}?{urlencode(params)}"

    def get_authorization_code_token(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
        session_alias: str = "default",
        timeout: int = 30,
    ) -> str:
        """Exchange authorization code for access token.

        Args:
            token_url: OAuth2 token endpoint URL
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            code: Authorization code from callback
            redirect_uri: Same redirect URI used in authorization request
            session_alias: Alias for storing the token
            timeout: Request timeout in seconds

        Returns:
            Access token string
        """
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        resp = requests.post(token_url, data=data, timeout=timeout)
        self._handle_token_error(resp)

        token_data = resp.json()
        token = TokenInfo(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token"),
            scope=token_data.get("scope"),
        )
        self._tokens[session_alias] = token
        return token.access_token

    # ========================================================================
    # PKCE Support
    # ========================================================================

    def generate_pkce_verifier(self, length: int = 64) -> str:
        """Generate PKCE code_verifier.

        The code_verifier is a cryptographically random string using the
        unreserved characters [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"

        Args:
            length: Length of the verifier (43-128 characters, default: 64)

        Returns:
            PKCE code_verifier string

        Robot Framework Example:
            ${verifier}=    Generate PKCE Verifier
            Set Suite Variable    ${CODE_VERIFIER}    ${verifier}
        """
        if length < 43:
            length = 43
        elif length > 128:
            length = 128

        return secrets.token_urlsafe(length)[:length]

    def generate_pkce_challenge(
        self,
        verifier: str,
        method: str = "S256",
    ) -> str:
        """Generate PKCE code_challenge from code_verifier.

        Args:
            verifier: PKCE code_verifier
            method: Challenge method - "S256" (recommended) or "plain"

        Returns:
            PKCE code_challenge string

        Robot Framework Example:
            ${challenge}=    Generate PKCE Challenge    ${verifier}    S256
        """
        if method.upper() == "S256":
            digest = hashlib.sha256(verifier.encode()).digest()
            return base64.urlsafe_b64encode(digest).decode().rstrip("=")
        return verifier  # plain

    def get_pkce_token(
        self,
        token_url: str,
        client_id: str,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        client_secret: str | None = None,
        session_alias: str = "default",
        timeout: int = 30,
    ) -> str:
        """Exchange authorization code with PKCE for access token.

        Args:
            token_url: OAuth2 token endpoint URL
            client_id: OAuth2 client ID
            code: Authorization code from callback
            code_verifier: PKCE code_verifier used to generate challenge
            redirect_uri: Same redirect URI used in authorization request
            client_secret: Optional client secret (for confidential clients)
            session_alias: Alias for storing the token
            timeout: Request timeout in seconds

        Returns:
            Access token string

        Robot Framework Example:
            ${token}=    Get PKCE Token
            ...    token_url=https://auth.example.com/oauth/token
            ...    client_id=my_public_client
            ...    code=${AUTH_CODE}
            ...    code_verifier=${CODE_VERIFIER}
            ...    redirect_uri=http://localhost:3000/callback
        """
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
        }

        if client_secret:
            data["client_secret"] = client_secret

        resp = requests.post(token_url, data=data, timeout=timeout)
        self._handle_token_error(resp)

        token_data = resp.json()
        token = TokenInfo(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token"),
            scope=token_data.get("scope"),
        )
        self._tokens[session_alias] = token
        return token.access_token

    # ========================================================================
    # Client Assertion (JWT Bearer)
    # ========================================================================

    def get_token_with_assertion(
        self,
        token_url: str,
        client_id: str,
        client_assertion: str,
        client_assertion_type: str = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        scope: str | None = None,
        session_alias: str = "default",
        timeout: int = 30,
    ) -> str:
        """Get token using client_assertion (JWT).

        Used for private_key_jwt or client_secret_jwt authentication methods.
        The client_assertion should be a signed JWT.

        Args:
            token_url: OAuth2 token endpoint URL
            client_id: OAuth2 client ID
            client_assertion: Signed JWT assertion
            client_assertion_type: Assertion type URI
            scope: Optional OAuth2 scope
            session_alias: Alias for storing the token
            timeout: Request timeout in seconds

        Returns:
            Access token string
        """
        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_assertion_type": client_assertion_type,
            "client_assertion": client_assertion,
        }

        if scope:
            data["scope"] = scope

        resp = requests.post(token_url, data=data, timeout=timeout)
        self._handle_token_error(resp)

        token_data = resp.json()
        token = TokenInfo(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token"),
            scope=token_data.get("scope"),
        )
        self._tokens[session_alias] = token
        return token.access_token

    # ========================================================================
    # Token Exchange
    # ========================================================================

    def exchange_token(
        self,
        token_url: str,
        subject_token: str,
        subject_token_type: str,
        client_id: str,
        client_secret: str | None = None,
        audience: str | None = None,
        scope: str | None = None,
        requested_token_type: str | None = None,
        session_alias: str = "default",
        timeout: int = 30,
    ) -> str:
        """Exchange one token for another (Token Exchange / On-Behalf-Of).

        RFC 8693 OAuth 2.0 Token Exchange.

        Args:
            token_url: OAuth2 token endpoint URL
            subject_token: The token to exchange
            subject_token_type: Type of subject token (e.g., urn:ietf:params:oauth:token-type:access_token)
            client_id: OAuth2 client ID
            client_secret: Optional client secret
            audience: Target audience for the new token
            scope: Optional OAuth2 scope
            requested_token_type: Type of token to request
            session_alias: Alias for storing the token
            timeout: Request timeout in seconds

        Returns:
            New access token string
        """
        data: dict[str, str] = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": subject_token,
            "subject_token_type": subject_token_type,
            "client_id": client_id,
        }

        if client_secret:
            data["client_secret"] = client_secret

        if audience:
            data["audience"] = audience

        if scope:
            data["scope"] = scope

        if requested_token_type:
            data["requested_token_type"] = requested_token_type

        resp = requests.post(token_url, data=data, timeout=timeout)
        self._handle_token_error(resp)

        token_data = resp.json()
        token = TokenInfo(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token"),
            scope=token_data.get("scope"),
        )
        self._tokens[session_alias] = token
        return token.access_token

    # ========================================================================
    # Token Refresh
    # ========================================================================

    def refresh_token(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        scope: str | None = None,
        session_alias: str = "default",
        timeout: int = 30,
    ) -> str:
        """Refresh access token using refresh_token.

        Args:
            token_url: OAuth2 token endpoint URL
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            refresh_token: Refresh token obtained during initial auth
            scope: Optional OAuth2 scope (must be subset of original scope)
            session_alias: Alias for storing the token
            timeout: Request timeout in seconds

        Returns:
            New access token string
        """
        # Validate required parameters
        if not token_url:
            raise OAuth2Error("TOKEN_URL is not set. Please configure OAuth2 token endpoint.")
        if not client_id:
            raise OAuth2Error("CLIENT_ID is not set. Please configure OAuth2 client ID.")
        if not refresh_token:
            raise OAuth2Error("REFRESH_TOKEN is not set. Please authenticate first to obtain a refresh token.")

        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        if scope:
            data["scope"] = scope

        resp = requests.post(token_url, data=data, timeout=timeout)
        self._handle_token_error(resp)

        token_data = resp.json()
        token = TokenInfo(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token", refresh_token),
            scope=token_data.get("scope"),
        )
        self._tokens[session_alias] = token
        return token.access_token

    # ========================================================================
    # Token Management
    # ========================================================================

    def get_stored_token(self, session_alias: str = "default") -> TokenInfo | None:
        """Get stored token information.

        Args:
            session_alias: Token session alias

        Returns:
            TokenInfo or None if not found
        """
        return self._tokens.get(session_alias)

    def get_access_token(self, session_alias: str = "default") -> str:
        """Get access token string from storage.

        Args:
            session_alias: Token session alias

        Returns:
            Access token string

        Raises:
            ValueError: If no token is stored for the alias
        """
        token = self._tokens.get(session_alias)
        if not token:
            raise ValueError(f"No token stored for session '{session_alias}'")
        return token.access_token

    def get_authorization_header(self, session_alias: str = "default") -> str:
        """Get Authorization header value.

        Args:
            session_alias: Token session alias

        Returns:
            Authorization header value (e.g., "Bearer eyJhbG...")

        Robot Framework Example:
            ${auth_header}=    Get Authorization Header
            Set To Dictionary    ${headers}    Authorization=${auth_header}
        """
        token = self._tokens.get(session_alias)
        if not token:
            raise ValueError(f"No token stored for session '{session_alias}'")
        return token.authorization_header

    def get_refresh_token(self, session_alias: str = "default") -> str | None:
        """Get refresh token from storage.

        Args:
            session_alias: Token session alias

        Returns:
            Refresh token string or None if not available

        Robot Framework Example:
            ${refresh}=    Get Refresh Token
            Run Keyword If    ${refresh}    Store Refresh Token
        """
        token = self._tokens.get(session_alias)
        return token.refresh_token if token else None

    def is_token_expired(self, session_alias: str = "default") -> bool:
        """Check if stored token is expired.

        Args:
            session_alias: Token session alias

        Returns:
            True if token is expired or not found

        Robot Framework Example:
            ${expired}=    Is Token Expired
            Run Keyword If    ${expired}    Refresh Access Token
        """
        token = self._tokens.get(session_alias)
        return token.is_expired if token else True

    def get_token_expiry(self, session_alias: str = "default") -> float | None:
        """Get token expiration timestamp.

        Args:
            session_alias: Token session alias

        Returns:
            Unix timestamp of expiration (with 60s buffer), or None
        """
        token = self._tokens.get(session_alias)
        return token.expires_at if token else None

    def get_token_remaining_seconds(self, session_alias: str = "default") -> int:
        """Get remaining seconds until token expires.

        Args:
            session_alias: Token session alias

        Returns:
            Seconds until expiration (negative if expired)
        """
        token = self._tokens.get(session_alias)
        if not token:
            return 0
        remaining = token.expires_at - time.time()
        return max(0, int(remaining))

    def clear_token(self, session_alias: str = "default") -> None:
        """Clear stored token.

        Args:
            session_alias: Token session alias
        """
        self._tokens.pop(session_alias, None)

    def clear_all_tokens(self) -> None:
        """Clear all stored tokens."""
        self._tokens.clear()

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def parse_callback_url(self, callback_url: str) -> dict[str, str]:
        """Parse OAuth2 callback URL to extract code and state.

        Args:
            callback_url: Full callback URL with query parameters

        Returns:
            Dictionary with parsed parameters (code, state, error, etc.)

        Robot Framework Example:
            ${params}=    Parse Callback URL    ${callback_url}
            ${code}=    Set Variable    ${params}[code]
        """
        parsed = urlparse(callback_url)
        params = dict(parse_qs(parsed.query))

        # Flatten single-value lists
        return {k: v[0] if len(v) == 1 else v for k, v in params.items()}

    def _handle_token_error(self, response: requests.Response) -> None:
        """Handle OAuth2 error responses.

        Args:
            response: HTTP response object

        Raises:
            OAuth2Error: If response indicates an error
        """
        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_code = error_data.get("error", "unknown_error")
                error_desc = error_data.get("error_description", response.text)
                raise OAuth2Error(
                    f"OAuth2 error: {error_code} - {error_desc}",
                    error_code=error_code,
                )
            except ValueError:
                raise OAuth2Error(
                    f"OAuth2 request failed with status {response.status_code}: {response.text}"
                ) from None
