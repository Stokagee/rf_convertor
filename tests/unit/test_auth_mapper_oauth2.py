"""Unit tests for AuthMapper OAuth2 functionality."""

from __future__ import annotations

import pytest

from bruno_to_robot.mapper.auth_mapper import AuthMapper
from bruno_to_robot.models.bruno import (
    AuthType,
    BrunoAuth,
    BrunoOAuth2Config,
    OAuth2Credentials,
    OAuth2Flow,
    OAuth2Settings,
    OAuth2TokenConfig,
)
from bruno_to_robot.models.robot import RobotStep, RobotVariable


class TestAuthMapperOAuth2:
    """Tests for OAuth2 authentication mapping."""

    @pytest.fixture
    def mapper(self) -> AuthMapper:
        """Create fresh AuthMapper instance."""
        return AuthMapper()

    # ========================================================================
    # OAuth2 Flow Detection
    # ========================================================================

    def test_map_oauth2_client_credentials(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping client credentials flow."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.CLIENT_CREDENTIALS,
                access_token_url="https://auth.example.com/oauth/token",
                credentials=OAuth2Credentials(
                    client_id="test_client",
                    client_secret="test_secret",
                ),
            ),
        )

        steps = mapper.map_auth(auth, session_name="api")

        assert len(steps) >= 2
        # Should have token retrieval and session creation
        assert any("token" in s.keyword.lower() for s in steps)

    def test_map_oauth2_password_flow(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping password flow."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.PASSWORD,
                access_token_url="https://auth.example.com/oauth/token",
                credentials=OAuth2Credentials(
                    client_id="test_client",
                    client_secret="test_secret",
                ),
                username="testuser",
                password="testpass",
            ),
        )

        steps = mapper.map_auth(auth, session_name="api")

        assert len(steps) >= 2
        assert any("token" in s.keyword.lower() or "password" in s.keyword.lower() for s in steps)

    def test_map_oauth2_authorization_code(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping authorization code flow."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.AUTHORIZATION_CODE,
                authorization_url="https://auth.example.com/oauth/authorize",
                access_token_url="https://auth.example.com/oauth/token",
                callback_url="http://localhost:3000/callback",
                credentials=OAuth2Credentials(
                    client_id="test_client",
                    client_secret="test_secret",
                ),
            ),
        )

        steps = mapper.map_auth(auth, session_name="api")

        assert len(steps) >= 2
        # Should have auth code exchange
        assert any("auth" in s.keyword.lower() or "code" in s.keyword.lower() for s in steps)

    def test_map_oauth2_pkce_flow(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping PKCE flow."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.AUTHORIZATION_CODE,
                pkce_enabled=True,
                authorization_url="https://auth.example.com/oauth/authorize",
                access_token_url="https://auth.example.com/oauth/token",
                callback_url="http://localhost:3000/callback",
                credentials=OAuth2Credentials(
                    client_id="pkce_client",
                ),
            ),
        )

        steps = mapper.map_auth(auth, session_name="api")

        assert len(steps) >= 2
        # Should have PKCE-related steps
        step_keywords = " ".join(s.keyword.lower() for s in steps)
        assert "pkce" in step_keywords or "verifier" in step_keywords or "challenge" in step_keywords

    def test_map_oauth2_without_config_fallback(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test OAuth2 without config falls back to placeholder."""
        auth = BrunoAuth(type=AuthType.OAUTH2)

        steps = mapper.map_auth(auth, session_name="api")

        # Should still return some steps (placeholder)
        assert len(steps) >= 1

    # ========================================================================
    # Variables Extraction
    # ========================================================================

    def test_get_auth_variables_client_credentials(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test extracting variables for client credentials flow."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.CLIENT_CREDENTIALS,
                access_token_url="https://auth.example.com/oauth/token",
                credentials=OAuth2Credentials(
                    client_id="test_client",
                    client_secret="test_secret",
                ),
                scope="read write",
            ),
        )

        variables = mapper.get_auth_variables(auth)

        var_names = [v.name for v in variables]
        assert "TOKEN_URL" in var_names
        assert "CLIENT_ID" in var_names
        assert "CLIENT_SECRET" in var_names
        assert "OAUTH_SCOPE" in var_names
        assert "ACCESS_TOKEN" in var_names

    def test_get_auth_variables_password_flow(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test extracting variables for password flow."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.PASSWORD,
                access_token_url="https://auth.example.com/oauth/token",
                credentials=OAuth2Credentials(
                    client_id="test_client",
                ),
                username="testuser",
            ),
        )

        variables = mapper.get_auth_variables(auth)

        var_names = [v.name for v in variables]
        assert "OAUTH_USERNAME" in var_names
        assert "OAUTH_PASSWORD" in var_names

    def test_get_auth_variables_auth_code_flow(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test extracting variables for authorization code flow."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.AUTHORIZATION_CODE,
                authorization_url="https://auth.example.com/oauth/authorize",
                access_token_url="https://auth.example.com/oauth/token",
                callback_url="http://localhost:3000/callback",
                credentials=OAuth2Credentials(
                    client_id="test_client",
                ),
            ),
        )

        variables = mapper.get_auth_variables(auth)

        var_names = [v.name for v in variables]
        assert "AUTH_URL" in var_names
        assert "REDIRECT_URI" in var_names
        assert "AUTH_CODE" in var_names

    def test_get_auth_variables_pkce(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test extracting variables for PKCE flow."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.AUTHORIZATION_CODE,
                pkce_enabled=True,
                access_token_url="https://auth.example.com/oauth/token",
                callback_url="http://localhost:3000/callback",
                credentials=OAuth2Credentials(
                    client_id="pkce_client",
                ),
            ),
        )

        variables = mapper.get_auth_variables(auth)

        var_names = [v.name for v in variables]
        assert "CODE_VERIFIER" in var_names
        assert "CODE_CHALLENGE" in var_names

    def test_get_auth_variables_no_oauth2(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test extracting variables when no OAuth2 config."""
        auth = BrunoAuth(type=AuthType.BEARER, token="test_token")

        variables = mapper.get_auth_variables(auth)

        # Should return empty list for bearer auth (handled elsewhere)
        var_names = [v.name for v in variables]
        assert "OAUTH2" not in " ".join(var_names)

    def test_get_auth_variables_secret_masking(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test that secrets are properly masked."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.CLIENT_CREDENTIALS,
                access_token_url="https://auth.example.com/oauth/token",
                credentials=OAuth2Credentials(
                    client_id="test_client",
                    client_secret="super_secret_value",
                ),
            ),
        )

        variables = mapper.get_auth_variables(auth)

        for var in variables:
            if var.name == "CLIENT_SECRET":
                # Should use env var reference, not hardcoded value
                assert "super_secret" not in str(var.value)
                assert "%" in str(var.value) or var.value is None

    # ========================================================================
    # OAuth2 Keywords Generation
    # ========================================================================

    def test_get_oauth2_keywords_client_credentials(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test generating keywords for client credentials."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.CLIENT_CREDENTIALS,
                access_token_url="https://auth.example.com/oauth/token",
                credentials=OAuth2Credentials(
                    client_id="test_client",
                    client_secret="test_secret",
                ),
            ),
        )

        keywords = mapper.get_oauth2_keywords(auth)

        assert "Get Client Credentials Token" in keywords
        assert "Ensure Valid Token" in keywords
        assert "Token Is Expired" in keywords

    def test_get_oauth2_keywords_password(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test generating keywords for password flow."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.PASSWORD,
                access_token_url="https://auth.example.com/oauth/token",
                credentials=OAuth2Credentials(
                    client_id="test_client",
                ),
                username="testuser",
            ),
        )

        keywords = mapper.get_oauth2_keywords(auth)

        assert "Get Password Token" in keywords

    def test_get_oauth2_keywords_pkce(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test generating keywords for PKCE flow."""
        auth = BrunoAuth(
            type=AuthType.OAUTH2,
            oauth2=BrunoOAuth2Config(
                flow=OAuth2Flow.AUTHORIZATION_CODE,
                pkce_enabled=True,
                access_token_url="https://auth.example.com/oauth/token",
                callback_url="http://localhost:3000/callback",
                credentials=OAuth2Credentials(
                    client_id="pkce_client",
                ),
            ),
        )

        keywords = mapper.get_oauth2_keywords(auth)

        assert "Generate PKCE Verifier" in keywords
        assert "Generate PKCE Challenge" in keywords
        assert "Get PKCE Token" in keywords

    def test_get_oauth2_keywords_no_auth(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test generating keywords when no OAuth2 auth."""
        keywords = mapper.get_oauth2_keywords(None)
        assert keywords == {}

        auth = BrunoAuth(type=AuthType.BEARER)
        keywords = mapper.get_oauth2_keywords(auth)
        assert keywords == {}

    # ========================================================================
    # mTLS/Certificate Auth
    # ========================================================================

    def test_map_cert_auth_pem(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping PEM certificate auth."""
        auth = BrunoAuth(
            type=AuthType.CERT,
            cert_path="/path/to/client.crt",
            key_path="/path/to/client.key",
        )

        steps = mapper.map_auth(auth, session_name="api")

        assert len(steps) >= 1
        assert any("Session" in s.keyword for s in steps)

    def test_map_cert_auth_pkcs12(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping PKCS#12 certificate auth."""
        auth = BrunoAuth(
            type=AuthType.CERT,
            cert_path="/path/to/client.p12",
            key_password="p12_password",
        )

        steps = mapper.map_auth(auth, session_name="api")

        assert len(steps) >= 1
        # Should have PKCS12 loading step
        step_keywords = " ".join(s.keyword for s in steps)
        assert "PKCS12" in step_keywords or "p12" in step_keywords.lower()

    def test_get_auth_variables_cert(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test extracting variables for certificate auth."""
        auth = BrunoAuth(
            type=AuthType.CERT,
            key_password="secret_password",
            ca_bundle_path="/path/to/ca.pem",
        )

        variables = mapper.get_auth_variables(auth)

        var_names = [v.name for v in variables]
        assert "CERT_PATH" in var_names
        assert "KEY_PATH" in var_names
        assert "KEY_PASSWORD" in var_names
        assert "SSL_VERIFY" in var_names

    # ========================================================================
    # Other Auth Types
    # ========================================================================

    def test_map_basic_auth(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping basic authentication."""
        auth = BrunoAuth(
            type=AuthType.BASIC,
            username="user",
            password="pass",
        )

        steps = mapper.map_auth(auth, session_name="api")

        assert len(steps) >= 1
        assert any("auth=" in str(s.args) for s in steps)

    def test_map_bearer_auth(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping bearer token authentication."""
        auth = BrunoAuth(
            type=AuthType.BEARER,
            token="test_token_123",
        )

        steps = mapper.map_auth(auth, session_name="api")

        assert len(steps) >= 2
        assert any("Authorization" in str(s.args) for s in steps)

    def test_map_api_key_auth_header(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping API key authentication in header."""
        auth = BrunoAuth(
            type=AuthType.API_KEY,
            api_key="api_key_123",
            api_key_name="X-API-Key",
            api_key_location="header",
        )

        steps = mapper.map_auth(auth, session_name="api")

        assert len(steps) >= 2
        assert any("X-API-Key" in str(s.args) for s in steps)

    def test_map_inherit_auth(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping inherit auth (should create basic session)."""
        auth = BrunoAuth(type=AuthType.INHERIT)

        steps = mapper.map_auth(auth, session_name="api")

        assert len(steps) >= 1
        assert steps[0].keyword == "Create Session"

    def test_map_none_auth(
        self,
        mapper: AuthMapper,
    ) -> None:
        """Test mapping no authentication."""
        steps = mapper.map_auth(None, session_name="api")

        assert len(steps) >= 1
        assert steps[0].keyword == "Create Session"


class TestOAuth2ConfigModels:
    """Tests for OAuth2 configuration models."""

    def test_oauth2_credentials_defaults(self) -> None:
        """Test OAuth2Credentials default values."""
        creds = OAuth2Credentials()

        assert creds.client_id is None
        assert creds.client_secret is None
        assert creds.placement == "body"

    def test_oauth2_settings_defaults(self) -> None:
        """Test OAuth2Settings default values."""
        settings = OAuth2Settings()

        assert settings.auto_fetch_token is True
        assert settings.auto_refresh_token is True  # Per requirements

    def test_bruno_oauth2_config_defaults(self) -> None:
        """Test BrunoOAuth2Config default values."""
        config = BrunoOAuth2Config()

        assert config.flow == OAuth2Flow.CLIENT_CREDENTIALS
        assert config.pkce_enabled is False
        assert config.credentials is not None

    def test_bruno_oauth2_config_pkce(self) -> None:
        """Test BrunoOAuth2Config with PKCE enabled."""
        config = BrunoOAuth2Config(
            flow=OAuth2Flow.AUTHORIZATION_CODE,
            pkce_enabled=True,
            code_verifier="test_verifier",
            code_challenge="test_challenge",
        )

        assert config.pkce_enabled is True
        assert config.code_verifier == "test_verifier"
        assert config.code_challenge == "test_challenge"
