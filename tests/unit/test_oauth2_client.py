"""Unit tests for OAuth2Client library."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from bruno_to_robot.library.oauth2_client import (
    OAuth2Client,
    OAuth2Error,
    TokenExpiredError,
    TokenInfo,
)


class TestTokenInfo:
    """Tests for TokenInfo dataclass."""

    def test_token_info_defaults(self) -> None:
        """Test default values for TokenInfo."""
        token = TokenInfo(access_token="test_token")

        assert token.access_token == "test_token"
        assert token.token_type == "Bearer"
        assert token.expires_in == 3600
        assert token.refresh_token is None
        assert token.scope is None
        assert token.obtained_at > 0

    def test_token_info_expires_at(self) -> None:
        """Test expires_at calculation with 60s buffer."""
        now = time.time()
        token = TokenInfo(
            access_token="test",
            expires_in=3600,
            obtained_at=now,
        )

        expected_expiry = now + 3600 - 60
        assert abs(token.expires_at - expected_expiry) < 0.1

    def test_token_info_is_expired_false(self) -> None:
        """Test is_expired returns False for fresh token."""
        token = TokenInfo(
            access_token="test",
            expires_in=3600,
            obtained_at=time.time(),
        )

        assert token.is_expired is False

    def test_token_info_is_expired_true(self) -> None:
        """Test is_expired returns True for expired token."""
        token = TokenInfo(
            access_token="test",
            expires_in=60,  # Less than 60s buffer
            obtained_at=time.time(),
        )

        # Should be expired because of 60s buffer
        assert token.is_expired is True

    def test_authorization_header(self) -> None:
        """Test Authorization header generation."""
        token = TokenInfo(
            access_token="abc123",
            token_type="Bearer",
        )

        assert token.authorization_header == "Bearer abc123"

    def test_authorization_header_custom_type(self) -> None:
        """Test Authorization header with custom token type."""
        token = TokenInfo(
            access_token="abc123",
            token_type="MAC",
        )

        assert token.authorization_header == "MAC abc123"


class TestOAuth2Client:
    """Tests for OAuth2Client class."""

    @pytest.fixture
    def client(self) -> OAuth2Client:
        """Create fresh OAuth2Client instance."""
        return OAuth2Client()

    # ========================================================================
    # Client Credentials Flow
    # ========================================================================

    @patch("bruno_to_robot.library.oauth2_client.requests.post")
    def test_get_client_credentials_token_success(
        self,
        mock_post: MagicMock,
        client: OAuth2Client,
    ) -> None:
        """Test successful client credentials token retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        token = client.get_client_credentials_token(
            token_url="https://auth.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
        )

        assert token == "test_access_token"

        # Verify request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["data"]["grant_type"] == "client_credentials"
        assert call_args[1]["data"]["client_id"] == "test_client"
        assert call_args[1]["data"]["client_secret"] == "test_secret"

    @patch("bruno_to_robot.library.oauth2_client.requests.post")
    def test_get_client_credentials_token_with_scope(
        self,
        mock_post: MagicMock,
        client: OAuth2Client,
    ) -> None:
        """Test client credentials with scope parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "token123"}
        mock_post.return_value = mock_response

        token = client.get_client_credentials_token(
            token_url="https://auth.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
            scope="read write",
        )

        assert token == "token123"
        call_data = mock_post.call_args[1]["data"]
        assert call_data["scope"] == "read write"

    @patch("bruno_to_robot.library.oauth2_client.requests.post")
    def test_get_client_credentials_token_error(
        self,
        mock_post: MagicMock,
        client: OAuth2Client,
    ) -> None:
        """Test client credentials with error response."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "error": "invalid_client",
            "error_description": "Client authentication failed",
        }
        mock_post.return_value = mock_response

        with pytest.raises(OAuth2Error) as exc_info:
            client.get_client_credentials_token(
                token_url="https://auth.example.com/oauth/token",
                client_id="bad_client",
                client_secret="bad_secret",
            )

        assert "invalid_client" in str(exc_info.value)
        assert exc_info.value.error_code == "invalid_client"

    # ========================================================================
    # Password Flow
    # ========================================================================

    @patch("bruno_to_robot.library.oauth2_client.requests.post")
    def test_get_password_token_success(
        self,
        mock_post: MagicMock,
        client: OAuth2Client,
    ) -> None:
        """Test successful password flow token retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "password_token",
            "refresh_token": "refresh_123",
            "expires_in": 1800,
        }
        mock_post.return_value = mock_response

        token = client.get_password_token(
            token_url="https://auth.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
            username="testuser",
            password="testpass",
        )

        assert token == "password_token"

        # Verify request
        call_data = mock_post.call_args[1]["data"]
        assert call_data["grant_type"] == "password"
        assert call_data["username"] == "testuser"
        assert call_data["password"] == "testpass"

    # ========================================================================
    # PKCE Support
    # ========================================================================

    def test_generate_pkce_verifier(self, client: OAuth2Client) -> None:
        """Test PKCE code_verifier generation."""
        verifier = client.generate_pkce_verifier()

        assert len(verifier) >= 43
        assert len(verifier) <= 128
        # Should only contain unreserved characters
        import re
        assert re.match(r"^[A-Za-z0-9\-._~]+$", verifier)

    def test_generate_pkce_verifier_custom_length(self, client: OAuth2Client) -> None:
        """Test PKCE verifier with custom length."""
        verifier = client.generate_pkce_verifier(length=50)
        assert len(verifier) == 50

    def test_generate_pkce_verifier_min_length(self, client: OAuth2Client) -> None:
        """Test PKCE verifier respects minimum length."""
        verifier = client.generate_pkce_verifier(length=10)
        assert len(verifier) == 43  # Should be clamped to min

    def test_generate_pkce_verifier_max_length(self, client: OAuth2Client) -> None:
        """Test PKCE verifier respects maximum length."""
        verifier = client.generate_pkce_verifier(length=200)
        assert len(verifier) == 128  # Should be clamped to max

    def test_generate_pkce_challenge_s256(self, client: OAuth2Client) -> None:
        """Test PKCE code_challenge generation with S256."""
        verifier = "dBjftJeZ4CVP-mB92K27uhbUuwRUb18S-wwGl2K9VQ"
        challenge = client.generate_pkce_challenge(verifier, method="S256")

        # Verify it's base64url encoded and different from verifier
        assert challenge != verifier
        # Should be base64url encoded (no padding)
        import re
        assert re.match(r"^[A-Za-z0-9\-_]+$", challenge)

    def test_generate_pkce_challenge_plain(self, client: OAuth2Client) -> None:
        """Test PKCE code_challenge with plain method."""
        verifier = "test_verifier_123"
        challenge = client.generate_pkce_challenge(verifier, method="plain")

        assert challenge == verifier

    @patch("bruno_to_robot.library.oauth2_client.requests.post")
    def test_get_pkce_token_success(
        self,
        mock_post: MagicMock,
        client: OAuth2Client,
    ) -> None:
        """Test PKCE token exchange."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "pkce_token",
            "refresh_token": "refresh_pkce",
        }
        mock_post.return_value = mock_response

        token = client.get_pkce_token(
            token_url="https://auth.example.com/oauth/token",
            client_id="pkce_client",
            code="auth_code_123",
            code_verifier="verifier_abc",
            redirect_uri="http://localhost:3000/callback",
        )

        assert token == "pkce_token"

        call_data = mock_post.call_args[1]["data"]
        assert call_data["code_verifier"] == "verifier_abc"
        assert call_data["code"] == "auth_code_123"

    # ========================================================================
    # Token Refresh
    # ========================================================================

    @patch("bruno_to_robot.library.oauth2_client.requests.post")
    def test_refresh_token_success(
        self,
        mock_post: MagicMock,
        client: OAuth2Client,
    ) -> None:
        """Test token refresh."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        token = client.refresh_token(
            token_url="https://auth.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
            refresh_token="old_refresh_token",
        )

        assert token == "new_access_token"

        call_data = mock_post.call_args[1]["data"]
        assert call_data["grant_type"] == "refresh_token"
        assert call_data["refresh_token"] == "old_refresh_token"

    # ========================================================================
    # Token Management
    # ========================================================================

    def test_get_stored_token(self, client: OAuth2Client) -> None:
        """Test retrieving stored token."""
        # Store a token manually
        client._tokens["test_session"] = TokenInfo(access_token="stored_token")

        token = client.get_stored_token("test_session")
        assert token is not None
        assert token.access_token == "stored_token"

    def test_get_stored_token_not_found(self, client: OAuth2Client) -> None:
        """Test retrieving non-existent token."""
        token = client.get_stored_token("nonexistent")
        assert token is None

    def test_get_access_token(self, client: OAuth2Client) -> None:
        """Test getting access token string."""
        client._tokens["default"] = TokenInfo(access_token="my_token")

        token = client.get_access_token("default")
        assert token == "my_token"

    def test_get_access_token_not_found(self, client: OAuth2Client) -> None:
        """Test getting access token when not stored."""
        with pytest.raises(ValueError, match="No token stored"):
            client.get_access_token("nonexistent")

    def test_get_authorization_header(self, client: OAuth2Client) -> None:
        """Test getting Authorization header value."""
        client._tokens["default"] = TokenInfo(access_token="my_token")

        header = client.get_authorization_header("default")
        assert header == "Bearer my_token"

    def test_is_token_expired_no_token(self, client: OAuth2Client) -> None:
        """Test is_token_expired when no token stored."""
        assert client.is_token_expired("nonexistent") is True

    def test_is_token_expired_fresh_token(self, client: OAuth2Client) -> None:
        """Test is_token_expired with fresh token."""
        client._tokens["default"] = TokenInfo(
            access_token="fresh",
            expires_in=3600,
            obtained_at=time.time(),
        )

        assert client.is_token_expired("default") is False

    def test_is_token_expired_old_token(self, client: OAuth2Client) -> None:
        """Test is_token_expired with expired token."""
        client._tokens["default"] = TokenInfo(
            access_token="old",
            expires_in=60,
            obtained_at=time.time() - 120,  # Expired 2 minutes ago
        )

        assert client.is_token_expired("default") is True

    def test_get_token_remaining_seconds(self, client: OAuth2Client) -> None:
        """Test getting remaining seconds until expiry."""
        client._tokens["default"] = TokenInfo(
            access_token="test",
            expires_in=3600,
            obtained_at=time.time(),
        )

        remaining = client.get_token_remaining_seconds("default")
        # Should be close to 3600 - 60 = 3540
        assert remaining > 3500
        assert remaining <= 3540

    def test_get_token_remaining_seconds_no_token(self, client: OAuth2Client) -> None:
        """Test remaining seconds when no token."""
        remaining = client.get_token_remaining_seconds("nonexistent")
        assert remaining == 0

    def test_clear_token(self, client: OAuth2Client) -> None:
        """Test clearing stored token."""
        client._tokens["default"] = TokenInfo(access_token="test")
        assert "default" in client._tokens

        client.clear_token("default")
        assert "default" not in client._tokens

    def test_clear_all_tokens(self, client: OAuth2Client) -> None:
        """Test clearing all stored tokens."""
        client._tokens["session1"] = TokenInfo(access_token="token1")
        client._tokens["session2"] = TokenInfo(access_token="token2")

        client.clear_all_tokens()
        assert len(client._tokens) == 0

    # ========================================================================
    # Client Assertion (JWT Bearer)
    # ========================================================================

    @patch("bruno_to_robot.library.oauth2_client.requests.post")
    def test_get_token_with_assertion(
        self,
        mock_post: MagicMock,
        client: OAuth2Client,
    ) -> None:
        """Test token retrieval with client assertion."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "assertion_token"}
        mock_post.return_value = mock_response

        token = client.get_token_with_assertion(
            token_url="https://auth.example.com/oauth/token",
            client_id="jwt_client",
            client_assertion="eyJhbGciOiJSUzI1NiIs...",
        )

        assert token == "assertion_token"

        call_data = mock_post.call_args[1]["data"]
        assert "client_assertion" in call_data
        assert "client_assertion_type" in call_data

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def test_parse_callback_url(self, client: OAuth2Client) -> None:
        """Test parsing OAuth2 callback URL."""
        callback_url = "http://localhost:3000/callback?code=abc123&state=xyz789"

        params = client.parse_callback_url(callback_url)

        assert params["code"] == "abc123"
        assert params["state"] == "xyz789"

    def test_parse_callback_url_with_error(self, client: OAuth2Client) -> None:
        """Test parsing callback URL with error parameter."""
        callback_url = "http://localhost:3000/callback?error=access_denied&error_description=User+denied"

        params = client.parse_callback_url(callback_url)

        assert params["error"] == "access_denied"
        assert params["error_description"] == "User denied"


class TestOAuth2Error:
    """Tests for OAuth2Error exception."""

    def test_oauth2_error_with_code(self) -> None:
        """Test OAuth2Error with error code."""
        error = OAuth2Error("Test error", error_code="test_error")

        assert str(error) == "Test error"
        assert error.error_code == "test_error"

    def test_oauth2_error_without_code(self) -> None:
        """Test OAuth2Error without error code."""
        error = OAuth2Error("Test error")

        assert str(error) == "Test error"
        assert error.error_code is None


class TestTokenExpiredError:
    """Tests for TokenExpiredError exception."""

    def test_token_expired_error_default(self) -> None:
        """Test TokenExpiredError with default message."""
        error = TokenExpiredError()

        assert "expired" in str(error).lower()
        assert error.session_alias == "default"

    def test_token_expired_error_custom(self) -> None:
        """Test TokenExpiredError with custom message."""
        error = TokenExpiredError(
            message="Custom expiry message",
            session_alias="custom_session",
        )

        assert "Custom expiry message" in str(error)
        assert error.session_alias == "custom_session"
