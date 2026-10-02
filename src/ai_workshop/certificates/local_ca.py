from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from ai_workshop.certificates.models import (
    IssuedCertificate,
    validate_dns_hostname,
)


class LocalCertificateAuthority:
    def __init__(
        self,
        *,
        state_root: Path,
        clock: Callable[[], datetime] | None = None,
        ca_lifetime: timedelta = timedelta(days=3650),
        leaf_lifetime: timedelta = timedelta(days=30),
        renewal_window: timedelta = timedelta(days=7),
    ):
        if ca_lifetime <= timedelta(days=1):
            raise ValueError("CA lifetime must exceed one day")
        if leaf_lifetime <= timedelta(hours=1):
            raise ValueError("leaf lifetime must exceed one hour")
        if renewal_window <= timedelta(0) or renewal_window >= leaf_lifetime:
            raise ValueError("renewal window must be positive and shorter than leaf lifetime")

        self.state_root = Path(state_root).expanduser().resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.ca_lifetime = ca_lifetime
        self.leaf_lifetime = leaf_lifetime
        self.renewal_window = renewal_window
        self.ca_private_key_path = self.state_root / "ca-key.pem"
        self.ca_certificate_path = self.state_root / "ca-cert.pem"
        self.certificates_root = self.state_root / "certificates"

        self.state_root.mkdir(parents=True, exist_ok=True)
        self._chmod(self.state_root, 0o700)
        self.certificates_root.mkdir(parents=True, exist_ok=True)
        self._chmod(self.certificates_root, 0o700)
        self._ensure_ca()

    def issue(self, hostname: str) -> IssuedCertificate:
        return self._issue(hostname, force=False)

    def renew_due(self) -> list[IssuedCertificate]:
        now = self._now()
        renewed: list[IssuedCertificate] = []
        if not self.certificates_root.exists():
            return renewed

        for directory in sorted(
            (item for item in self.certificates_root.iterdir() if item.is_dir()),
            key=lambda item: item.name,
        ):
            hostname = validate_dns_hostname(directory.name)
            cert_path, key_path = self._leaf_paths(hostname)
            if not cert_path.is_file() or not key_path.is_file():
                raise ValueError(f"incomplete certificate state for {hostname}")
            cert = self._load_certificate(cert_path)
            if cert.not_valid_after_utc <= now + self.renewal_window:
                renewed.append(self._issue(hostname, force=True))
        return renewed

    def export_trust_certificate(self) -> bytes:
        return self.ca_certificate_path.read_bytes()

    def _issue(self, hostname: str, *, force: bool) -> IssuedCertificate:
        hostname = validate_dns_hostname(hostname)
        cert_path, key_path = self._leaf_paths(hostname)
        directory = cert_path.parent
        directory.mkdir(parents=True, exist_ok=True)
        self._chmod(directory, 0o700)

        if cert_path.exists() != key_path.exists():
            raise ValueError(f"incomplete certificate state for {hostname}")
        if cert_path.is_file() and key_path.is_file() and not force:
            existing = self._load_certificate(cert_path)
            self._validate_leaf(existing, hostname)
            if existing.not_valid_after_utc > self._now() + self.renewal_window:
                return self._issued(hostname, cert_path, key_path, existing)

        ca_key = self._load_private_key(self.ca_private_key_path)
        ca_cert = self._load_certificate(self.ca_certificate_path)
        now = self._now()
        not_after = min(
            now + self.leaf_lifetime,
            ca_cert.not_valid_after_utc - timedelta(minutes=1),
        )
        if not_after <= now:
            raise ValueError("local CA has expired")

        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, hostname)]
        )
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(not_after)
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(hostname)]),
                critical=False,
            )
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=True,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )

        self._atomic_write(
            key_path,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
            0o600,
        )
        self._atomic_write(
            cert_path,
            certificate.public_bytes(serialization.Encoding.PEM),
            0o644,
        )
        return self._issued(hostname, cert_path, key_path, certificate)

    def _ensure_ca(self) -> None:
        key_exists = self.ca_private_key_path.exists()
        cert_exists = self.ca_certificate_path.exists()
        if key_exists != cert_exists:
            raise ValueError("incomplete local CA state")
        if key_exists:
            key = self._load_private_key(self.ca_private_key_path)
            cert = self._load_certificate(self.ca_certificate_path)
            if key.public_key().public_numbers() != cert.public_key().public_numbers():
                raise ValueError("local CA key does not match certificate")
            constraints = cert.extensions.get_extension_for_class(
                x509.BasicConstraints
            ).value
            if not constraints.ca:
                raise ValueError("local CA certificate is not a CA")
            self._chmod(self.ca_private_key_path, 0o600)
            return

        now = self._now()
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "AI Workshop Local CA")]
        )
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + self.ca_lifetime)
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        self._atomic_write(
            self.ca_private_key_path,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
            0o600,
        )
        self._atomic_write(
            self.ca_certificate_path,
            certificate.public_bytes(serialization.Encoding.PEM),
            0o644,
        )

    def _validate_leaf(self, cert: x509.Certificate, hostname: str) -> None:
        ca_cert = self._load_certificate(self.ca_certificate_path)
        if cert.issuer != ca_cert.subject:
            raise ValueError("leaf certificate issuer does not match local CA")
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        if san.get_values_for_type(x509.DNSName) != [hostname]:
            raise ValueError("leaf certificate hostname mismatch")

    def _leaf_paths(self, hostname: str) -> tuple[Path, Path]:
        directory = (self.certificates_root / hostname).resolve()
        try:
            directory.relative_to(self.certificates_root)
        except ValueError as exc:
            raise ValueError("hostname certificate path escapes PKI state") from exc
        return directory / "cert.pem", directory / "key.pem"

    @staticmethod
    def _load_certificate(path: Path) -> x509.Certificate:
        return x509.load_pem_x509_certificate(path.read_bytes())

    @staticmethod
    def _load_private_key(path: Path):
        return serialization.load_pem_private_key(path.read_bytes(), password=None)

    @staticmethod
    def _issued(
        hostname: str,
        cert_path: Path,
        key_path: Path,
        certificate: x509.Certificate,
    ) -> IssuedCertificate:
        return IssuedCertificate(
            hostname=hostname,
            certificate_path=cert_path.resolve(),
            private_key_path=key_path.resolve(),
            not_after=certificate.not_valid_after_utc,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("certificate clock must return timezone-aware datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _atomic_write(path: Path, data: bytes, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        LocalCertificateAuthority._chmod(temporary, mode)
        temporary.replace(path)
        LocalCertificateAuthority._chmod(path, mode)

    @staticmethod
    def _chmod(path: Path, mode: int) -> None:
        try:
            path.chmod(mode)
        except OSError:
            pass
