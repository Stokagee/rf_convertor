"""Unit tests for CertManager library."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bruno_to_robot.library.cert_manager import (
    CertificateError,
    CertManager,
)


class TestCertManager:
    """Tests for CertManager class."""

    @pytest.fixture
    def cert_manager(self) -> CertManager:
        """Create fresh CertManager instance."""
        return CertManager()

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    # ========================================================================
    # SSL Verification Configuration
    # ========================================================================

    def test_get_ssl_verify_true(self, cert_manager: CertManager) -> None:
        """Test SSL verify with True value."""
        result = cert_manager.get_ssl_verify(True)
        assert result is True

    def test_get_ssl_verify_false(self, cert_manager: CertManager) -> None:
        """Test SSL verify with False value."""
        result = cert_manager.get_ssl_verify(False)
        assert result is False

    def test_get_ssl_verify_string_true(self, cert_manager: CertManager) -> None:
        """Test SSL verify with string 'true'."""
        result = cert_manager.get_ssl_verify("true")
        assert result is True

    def test_get_ssl_verify_string_false(self, cert_manager: CertManager) -> None:
        """Test SSL verify with string 'false'."""
        result = cert_manager.get_ssl_verify("false")
        assert result is False

    def test_get_ssl_verify_case_insensitive(self, cert_manager: CertManager) -> None:
        """Test SSL verify is case insensitive."""
        assert cert_manager.get_ssl_verify("TRUE") is True
        assert cert_manager.get_ssl_verify("FALSE") is False
        assert cert_manager.get_ssl_verify("True") is True
        assert cert_manager.get_ssl_verify("False") is False

    def test_get_ssl_verify_path_exists(
        self,
        cert_manager: CertManager,
        temp_dir: Path,
    ) -> None:
        """Test SSL verify with existing CA bundle path."""
        ca_bundle = temp_dir / "ca-bundle.crt"
        ca_bundle.write_text("cert content")

        result = cert_manager.get_ssl_verify(str(ca_bundle))
        assert result == str(ca_bundle)

    def test_get_ssl_verify_path_not_exists(self, cert_manager: CertManager) -> None:
        """Test SSL verify with non-existent path defaults to True."""
        result = cert_manager.get_ssl_verify("/nonexistent/ca-bundle.crt")
        # Non-existent path falls through to default True
        assert result is True

    # ========================================================================
    # PKCS#12 Certificate Loading
    # ========================================================================

    @patch("bruno_to_robot.library.cert_manager.pkcs12.load_key_and_certificates")
    def test_load_pkcs12_certificate_success(
        self,
        mock_load: MagicMock,
        cert_manager: CertManager,
        temp_dir: Path,
    ) -> None:
        """Test successful PKCS#12 certificate loading."""
        # Mock the PKCS#12 loading
        mock_cert = MagicMock()
        mock_cert.public_bytes.return_value = b"-----BEGIN CERTIFICATE-----\nMIICWTCCAcKgAwIBAgIUR2V8Y5z3qE9b8r6y8pP2e1k2i3m4n5o6q7r8s9t0wIBAgELMAkGA1UE\n-----END CERTIFICATE-----\n"
        mock_key = MagicMock()
        mock_key.private_bytes.return_value = b"-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt9Us8cKj\n-----END PRIVATE KEY-----\n"
        mock_load.return_value = (mock_key, mock_cert, None)

        p12_path = temp_dir / "client.p12"
        p12_path.write_bytes(b"p12_content")

        cert_tuple = cert_manager.load_pkcs12_certificate(
            p12_path=str(p12_path),
            password="test_password",
        )

        assert len(cert_tuple) == 2
        # Implementation uses .pem extension
        assert cert_tuple[0].endswith(".pem")
        assert cert_tuple[1].endswith(".pem")

    @patch("bruno_to_robot.library.cert_manager.pkcs12.load_key_and_certificates")
    def test_load_pkcs12_certificate_with_chain(
        self,
        mock_load: MagicMock,
        cert_manager: CertManager,
        temp_dir: Path,
    ) -> None:
        """Test PKCS#12 loading with certificate chain."""
        mock_cert = MagicMock()
        mock_cert.public_bytes.return_value = b"-----BEGIN CERTIFICATE-----\ncert_pem\n-----END CERTIFICATE-----\n"
        mock_key = MagicMock()
        mock_key.private_bytes.return_value = b"-----BEGIN PRIVATE KEY-----\nkey_pem\n-----END PRIVATE KEY-----\n"
        mock_ca = MagicMock()
        mock_ca.public_bytes.return_value = b"-----BEGIN CERTIFICATE-----\nca_pem\n-----END CERTIFICATE-----\n"
        mock_load.return_value = (mock_key, mock_cert, [mock_ca])

        p12_path = temp_dir / "client.p12"
        p12_path.write_bytes(b"p12_content")

        cert_tuple = cert_manager.load_pkcs12_certificate_chain(
            p12_path=str(p12_path),
            password="test_password",
        )

        assert len(cert_tuple) == 2

    def test_load_pkcs12_certificate_missing_file(
        self,
        cert_manager: CertManager,
    ) -> None:
        """Test PKCS#12 loading with missing file."""
        with pytest.raises(CertificateError) as exc_info:
            cert_manager.load_pkcs12_certificate(
                p12_path="/nonexistent/client.p12",
                password="test",
            )

        assert "not found" in str(exc_info.value)

    @patch("bruno_to_robot.library.cert_manager.pkcs12.load_key_and_certificates")
    def test_load_pkcs12_certificate_wrong_password(
        self,
        mock_load: MagicMock,
        cert_manager: CertManager,
        temp_dir: Path,
    ) -> None:
        """Test PKCS#12 loading with wrong password."""
        # Simulate wrong password error
        mock_load.side_effect = ValueError("Could not deserialize PKCS12")

        p12_path = temp_dir / "client.p12"
        p12_path.write_bytes(b"p12_content")

        with pytest.raises(CertificateError) as exc_info:
            cert_manager.load_pkcs12_certificate(
                p12_path=str(p12_path),
                password="wrong_password",
            )

        assert "Failed to load" in str(exc_info.value)

    @patch("bruno_to_robot.library.cert_manager.pkcs12.load_key_and_certificates")
    def test_load_pkcs12_certificate_no_certificate(
        self,
        mock_load: MagicMock,
        cert_manager: CertManager,
        temp_dir: Path,
    ) -> None:
        """Test PKCS#12 loading when no certificate found."""
        mock_key = MagicMock()
        mock_load.return_value = (mock_key, None, None)  # No cert

        p12_path = temp_dir / "client.p12"
        p12_path.write_bytes(b"p12_content")

        with pytest.raises(CertificateError) as exc_info:
            cert_manager.load_pkcs12_certificate(
                p12_path=str(p12_path),
                password="test",
            )

        assert "No certificate" in str(exc_info.value)

    # ========================================================================
    # Cleanup
    # ========================================================================

    def test_cleanup_temp_files(
        self,
        cert_manager: CertManager,
        temp_dir: Path,
    ) -> None:
        """Test cleanup of temporary files."""
        # Create temp files
        temp_file1 = temp_dir / "temp1.pem"
        temp_file2 = temp_dir / "temp2.pem"
        temp_file1.write_text("content1")
        temp_file2.write_text("content2")

        # Track them
        cert_manager._temp_files = [temp_file1, temp_file2]

        # Cleanup
        cert_manager.cleanup_temp_files()

        # Verify files are deleted
        assert not temp_file1.exists()
        assert not temp_file2.exists()
        assert len(cert_manager._temp_files) == 0  # One file was deleted

    def test_cleanup_temp_files_handles_errors(
        self,
        cert_manager: CertManager,
    ) -> None:
        """Test cleanup handles missing files gracefully."""
        nonexistent = Path("/nonexistent/file.pem")
        cert_manager._temp_files = [nonexistent]

        # Should not raise
        cert_manager.cleanup_temp_files()

        assert len(cert_manager._temp_files) == 0  # Nonexistent stays in list


class TestCertificateError:
    """Tests for CertificateError exception."""

    def test_certificate_error_with_path(self) -> None:
        """Test CertificateError with cert path."""
        error = CertificateError(
            "Test error",
            cert_path="/path/to/cert.crt",
        )

        assert str(error) == "Test error"
        assert error.cert_path == "/path/to/cert.crt"

    def test_certificate_error_without_path(self) -> None:
        """Test CertificateError without cert path."""
        error = CertificateError("Test error")

        assert str(error) == "Test error"
        assert error.cert_path is None
