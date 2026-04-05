"""CertLibrary for Robot Framework - mTLS Certificate Management.

This module provides certificate management for mutual TLS (mTLS) authentication
in Robot Framework tests. Supports PEM and PKCS#12 certificate formats.

Usage in Robot Framework:
    Library    bruno_to_robot.library.cert_manager.CertManager    AS    Cert

    # For PEM certificates
    ${cert_tuple}=    Load PEM Certificate
    ...    cert_path=/path/to/client.crt
    ...    key_path=/path/to/client.key
    Create Session    api    ${BASE_URL}    cert=${cert_tuple}

    # For PKCS#12 certificates
    ${cert_tuple}=    Load PKCS12 Certificate
    ...    p12_path=/path/to/client.p12
    ...    password=${P12_PASSWORD}
    Create Session    api    ${BASE_URL}    cert=${cert_tuple}
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

if TYPE_CHECKING:
    from collections.abc import Sequence


class CertificateError(Exception):
    """Certificate-related error."""

    def __init__(self, message: str, cert_path: str | None = None) -> None:
        super().__init__(message)
        self.cert_path = cert_path


class CertManager:
    """Certificate management for mTLS in Robot Framework tests.

    This class can be used as a Robot Framework library.

    Example Robot Framework usage:
        *** Settings ***
        Library    bruno_to_robot.library.cert_manager.CertManager    AS    Cert

        *** Variables ***
        ${CERT_PATH}    %{CERT_PATH}
        ${KEY_PATH}    %{KEY_PATH}
        ${KEY_PASSWORD}    %{KEY_PASSWORD}

        *** Keywords ***
        Create MTLS Session
            ${cert}=    Load PEM Certificate
            ...    cert_path=${CERT_PATH}
            ...    key_path=${KEY_PATH}
            ...    password=${KEY_PASSWORD}
            Create Session    api    ${BASE_URL}    cert=${cert}    verify=${SSL_VERIFY}
    """

    ROBOT_LIBRARY_SCOPE = "SUITE"
    ROBOT_LIBRARY_DOC_FORMAT = "ROBOT"

    def __init__(self) -> None:
        """Initialize certificate manager."""
        self._temp_files: list[Path] = []

    # ========================================================================
    # PEM Certificate Loading
    # ========================================================================

    def load_pem_certificate(
        self,
        cert_path: str,
        key_path: str,
        password: str | None = None,
    ) -> tuple[str, str]:
        """Load PEM format certificate and private key.

        Validates that both files exist and returns paths in a format
        suitable for RequestsLibrary's cert parameter.

        Args:
            cert_path: Path to PEM certificate file (.crt or .pem)
            key_path: Path to PEM private key file (.key or .pem)
            password: Optional password for encrypted private key

        Returns:
            Tuple of (cert_path, key_path) for use with cert= parameter

        Raises:
            CertificateError: If files don't exist or are invalid

        Robot Framework Example:
            ${cert}=    Load PEM Certificate
            ...    cert_path=/path/to/client.crt
            ...    key_path=/path/to/client.key
            Create Session    api    ${BASE_URL}    cert=${cert}
        """
        cert_file = Path(cert_path)
        key_file = Path(key_path)

        if not cert_file.exists():
            raise CertificateError(
                f"Certificate file not found: {cert_path}",
                cert_path=cert_path,
            )

        if not key_file.exists():
            raise CertificateError(
                f"Private key file not found: {key_path}",
                cert_path=key_path,
            )

        # Validate PEM format
        try:
            cert_content = cert_file.read_bytes()
            x509.load_pem_x509_certificate(cert_content)
        except Exception as e:
            raise CertificateError(
                f"Invalid certificate format (expected PEM): {e}",
                cert_path=cert_path,
            ) from e

        # Validate key format (optional password check)
        try:
            key_content = key_file.read_bytes()
            serialization.load_pem_private_key(
                key_content,
                password=password.encode() if password else None,
            )
        except Exception as e:
            if password:
                raise CertificateError(
                    f"Invalid private key or wrong password: {e}",
                    cert_path=key_path,
                ) from e
            # Key might not be encrypted
            pass

        return (cert_path, key_path)

    def load_pem_certificate_chain(
        self,
        cert_path: str,
        key_path: str,
        chain_paths: str | Sequence[str] | None = None,
        password: str | None = None,
    ) -> tuple[str, str]:
        """Load PEM certificate with chain.

        Combines client certificate with intermediate CA certificates
        into a single certificate file.

        Args:
            cert_path: Path to client certificate
            key_path: Path to private key
            chain_paths: Path(s) to intermediate CA certificates
            password: Optional password for encrypted private key

        Returns:
            Tuple of (combined_cert_path, key_path)

        Robot Framework Example:
            ${cert}=    Load PEM Certificate Chain
            ...    cert_path=/path/to/client.crt
            ...    key_path=/path/to/client.key
            ...    chain_paths=/path/to/intermediate.crt
        """
        # Validate and load main certificate
        cert_tuple = self.load_pem_certificate(cert_path, key_path, password)

        if not chain_paths:
            return cert_tuple

        # Normalize chain_paths to list
        if isinstance(chain_paths, str):
            chain_list = [chain_paths]
        else:
            chain_list = list(chain_paths)

        # Read all certificates
        cert_content = Path(cert_path).read_bytes()
        for chain_path in chain_list:
            chain_file = Path(chain_path)
            if chain_file.exists():
                cert_content += b"\n" + chain_file.read_bytes()

        # Write combined certificate to temp file
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".crt",
            delete=False,
        ) as temp_cert:
            temp_cert.write(cert_content)
            temp_cert_path = temp_cert.name

        self._temp_files.append(Path(temp_cert_path))
        return (temp_cert_path, key_path)

    # ========================================================================
    # PKCS#12 Certificate Loading
    # ========================================================================

    def load_pkcs12_certificate(
        self,
        p12_path: str,
        password: str | None = None,
        output_dir: str | None = None,
    ) -> tuple[str, str]:
        """Load and convert PKCS#12 certificate to PEM format.

        Extracts certificate and private key from PKCS#12 file (.p12 or .pfx)
        and converts to PEM format for use with RequestsLibrary.

        Args:
            p12_path: Path to PKCS#12 file (.p12 or .pfx)
            password: Password for the PKCS#12 file (may be empty string for no password)
            output_dir: Directory to write PEM files (default: temp directory)

        Returns:
            Tuple of (cert_path, key_path) in PEM format

        Raises:
            CertificateError: If file doesn't exist, is invalid, or password is wrong

        Robot Framework Example:
            ${cert}=    Load PKCS12 Certificate
            ...    p12_path=/path/to/client.p12
            ...    password=${P12_PASSWORD}
            Create Session    api    ${BASE_URL}    cert=${cert}
        """
        p12_file = Path(p12_path)

        if not p12_file.exists():
            raise CertificateError(
                f"PKCS#12 file not found: {p12_path}",
                cert_path=p12_path,
            )

        try:
            p12_data = p12_file.read_bytes()

            # Load PKCS#12
            private_key, certificate, chain = pkcs12.load_key_and_certificates(
                p12_data,
                password.encode() if password else None,
            )

            if not certificate:
                raise CertificateError(
                    "No certificate found in PKCS#12 file",
                    cert_path=p12_path,
                )

            if not private_key:
                raise CertificateError(
                    "No private key found in PKCS#12 file",
                    cert_path=p12_path,
                )

            # Determine output directory
            if output_dir:
                out_dir = Path(output_dir)
                out_dir.mkdir(parents=True, exist_ok=True)
            else:
                out_dir = Path(tempfile.gettempdir())

            # Generate output filenames
            base_name = p12_file.stem
            cert_out = out_dir / f"{base_name}_cert.pem"
            key_out = out_dir / f"{base_name}_key.pem"

            # Write certificate
            cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
            cert_out.write_bytes(cert_pem)

            # Write private key (unencrypted)
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
            key_out.write_bytes(key_pem)

            # Track temp files for cleanup
            if not output_dir:
                self._temp_files.extend([cert_out, key_out])

            return (str(cert_out), str(key_out))

        except CertificateError:
            raise
        except Exception as e:
            raise CertificateError(
                f"Failed to load PKCS#12 certificate: {e}",
                cert_path=p12_path,
            ) from e

    def load_pkcs12_certificate_chain(
        self,
        p12_path: str,
        password: str | None = None,
        output_dir: str | None = None,
    ) -> tuple[str, str]:
        """Load PKCS#12 certificate with chain included in single cert file.

        Similar to load_pkcs12_certificate but includes any CA certificates
        from the PKCS#12 file in the output certificate file.

        Args:
            p12_path: Path to PKCS#12 file
            password: Password for the PKCS#12 file
            output_dir: Directory to write PEM files

        Returns:
            Tuple of (cert_path, key_path) in PEM format
        """
        p12_file = Path(p12_path)

        if not p12_file.exists():
            raise CertificateError(
                f"PKCS#12 file not found: {p12_path}",
                cert_path=p12_path,
            )

        try:
            p12_data = p12_file.read_bytes()

            # Load PKCS#12
            private_key, certificate, chain = pkcs12.load_key_and_certificates(
                p12_data,
                password.encode() if password else None,
            )

            if not certificate or not private_key:
                raise CertificateError(
                    "Missing certificate or key in PKCS#12 file",
                    cert_path=p12_path,
                )

            # Determine output directory
            if output_dir:
                out_dir = Path(output_dir)
                out_dir.mkdir(parents=True, exist_ok=True)
            else:
                out_dir = Path(tempfile.gettempdir())

            base_name = p12_file.stem
            cert_out = out_dir / f"{base_name}_chain.pem"
            key_out = out_dir / f"{base_name}_key.pem"

            # Write certificate + chain
            cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
            if chain:
                for ca_cert in chain:
                    cert_pem += ca_cert.public_bytes(serialization.Encoding.PEM)
            cert_out.write_bytes(cert_pem)

            # Write private key
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
            key_out.write_bytes(key_pem)

            if not output_dir:
                self._temp_files.extend([cert_out, key_out])

            return (str(cert_out), str(key_out))

        except CertificateError:
            raise
        except Exception as e:
            raise CertificateError(
                f"Failed to load PKCS#12 certificate: {e}",
                cert_path=p12_path,
            ) from e

    # ========================================================================
    # SSL Verification Configuration
    # ========================================================================

    def get_ssl_verify(
        self,
        verify: str | bool,
        ca_bundle_path: str | None = None,
    ) -> str | bool:
        """Determine SSL verify setting for requests.

        Converts string values to boolean or returns CA bundle path.

        Args:
            verify: Verification setting - "true", "false", bool, or path
            ca_bundle_path: Optional path to CA bundle file

        Returns:
            True, False, or path to CA bundle

        Robot Framework Example:
            ${verify}=    Get SSL Verify    %{SSL_VERIFY=true}
            Create Session    api    ${BASE_URL}    verify=${verify}
        """
        if isinstance(verify, bool):
            return verify

        if isinstance(verify, str):
            verify_lower = verify.lower().strip()

            if verify_lower == "true":
                return True
            if verify_lower == "false":
                return False

            # Assume it's a path
            verify_path = Path(verify)
            if verify_path.exists():
                return verify

        # Check CA bundle
        if ca_bundle_path:
            ca_path = Path(ca_bundle_path)
            if ca_path.exists():
                return str(ca_path)

        # Default to True for security
        return True

    def validate_ca_bundle(self, ca_bundle_path: str) -> bool:
        """Validate CA bundle file exists and contains valid certificates.

        Args:
            ca_bundle_path: Path to CA bundle file

        Returns:
            True if valid

        Raises:
            CertificateError: If file is invalid
        """
        ca_file = Path(ca_bundle_path)

        if not ca_file.exists():
            raise CertificateError(
                f"CA bundle file not found: {ca_bundle_path}",
                cert_path=ca_bundle_path,
            )

        try:
            content = ca_file.read_text()
            # Check for PEM format certificates
            if "-----BEGIN CERTIFICATE-----" not in content:
                raise CertificateError(
                    f"CA bundle does not contain PEM certificates: {ca_bundle_path}",
                    cert_path=ca_bundle_path,
                )
            return True
        except CertificateError:
            raise
        except Exception as e:
            raise CertificateError(
                f"Failed to validate CA bundle: {e}",
                cert_path=ca_bundle_path,
            ) from e

    # ========================================================================
    # Certificate Information
    # ========================================================================

    def get_certificate_info(self, cert_path: str) -> dict:
        """Get information about a certificate.

        Args:
            cert_path: Path to certificate file (PEM or DER)

        Returns:
            Dictionary with certificate details (subject, issuer, expiry, etc.)

        Robot Framework Example:
            ${info}=    Get Certificate Info    /path/to/cert.pem
            Log    Certificate expires: ${info}[not_valid_after]
        """
        cert_file = Path(cert_path)

        if not cert_file.exists():
            raise CertificateError(
                f"Certificate file not found: {cert_path}",
                cert_path=cert_path,
            )

        try:
            content = cert_file.read_bytes()

            # Try PEM first
            try:
                cert = x509.load_pem_x509_certificate(content)
            except Exception:
                # Try DER
                cert = x509.load_der_x509_certificate(content)

            return {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "serial_number": str(cert.serial_number),
                "not_valid_before": cert.not_valid_before_utc.isoformat(),
                "not_valid_after": cert.not_valid_after_utc.isoformat(),
                "is_ca": self._is_ca_certificate(cert),
                "signature_algorithm": cert.signature_algorithm_oid._name,
            }

        except CertificateError:
            raise
        except Exception as e:
            raise CertificateError(
                f"Failed to read certificate: {e}",
                cert_path=cert_path,
            ) from e

    def is_certificate_expired(self, cert_path: str) -> bool:
        """Check if certificate is expired.

        Args:
            cert_path: Path to certificate file

        Returns:
            True if certificate is expired

        Robot Framework Example:
            ${expired}=    Is Certificate Expired    /path/to/cert.pem
            Should Not Be True    ${expired}    Certificate is expired!
        """
        info = self.get_certificate_info(cert_path)
        from datetime import datetime, timezone

        expiry = datetime.fromisoformat(info["not_valid_after"].replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > expiry

    def _is_ca_certificate(self, cert: x509.Certificate) -> bool:
        """Check if certificate is a CA certificate."""
        try:
            basic_constraints = cert.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.BASIC_CONSTRAINTS
            )
            return basic_constraints.value.ca
        except x509.ExtensionNotFound:
            return False

    # ========================================================================
    # Cleanup
    # ========================================================================

    def cleanup_temp_files(self) -> None:
        """Remove temporary certificate files.

        Call this in Suite Teardown to clean up converted PKCS#12 files.

        Robot Framework Example:
            [Suite Teardown]    Cleanup Temp Files
        """
        for temp_file in self._temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass  # Ignore cleanup errors
        self._temp_files.clear()

    def __del__(self) -> None:
        """Cleanup on deletion."""
        self.cleanup_temp_files()
