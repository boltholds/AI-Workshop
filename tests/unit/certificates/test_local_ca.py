from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec

from ai_workshop.certificates.local_ca import LocalCertificateAuthority


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def service(
    tmp_path: Path,
    *,
    clock: Clock | None = None,
    leaf_lifetime: timedelta = timedelta(days=30),
    renewal_window: timedelta = timedelta(days=7),
) -> LocalCertificateAuthority:
    return LocalCertificateAuthority(
        state_root=tmp_path / "pki",
        clock=clock or Clock(datetime(2026, 10, 2, tzinfo=timezone.utc)),
        leaf_lifetime=leaf_lifetime,
        renewal_window=renewal_window,
    )


def load_cert(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def test_local_ca_persists_ca_and_issues_hostname_certificate(tmp_path: Path):
    ca = service(tmp_path)

    issued = ca.issue("app.workshop.local")

    ca_cert = load_cert(ca.ca_certificate_path)
    leaf = load_cert(issued.certificate_path)
    san = leaf.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value
    assert san.get_values_for_type(x509.DNSName) == ["app.workshop.local"]
    assert leaf.issuer == ca_cert.subject
    ca_cert.public_key().verify(
        leaf.signature,
        leaf.tbs_certificate_bytes,
        ec.ECDSA(leaf.signature_hash_algorithm),
    )
    assert issued.private_key_path.is_file()
    assert issued.certificate_path.is_file()


def test_ca_private_key_has_owner_only_permissions(tmp_path: Path):
    ca = service(tmp_path)

    mode = os.stat(ca.ca_private_key_path).st_mode & 0o777

    assert mode == 0o600


def test_ca_export_returns_public_certificate_only(tmp_path: Path):
    ca = service(tmp_path)

    exported = ca.export_trust_certificate()

    assert b"BEGIN CERTIFICATE" in exported
    assert b"PRIVATE KEY" not in exported
    assert ca.ca_private_key_path.read_bytes() not in exported


def test_issue_rejects_non_dns_hostname(tmp_path: Path):
    ca = service(tmp_path)

    for hostname in ("localhost", "127.0.0.1", "*.workshop.local", "bad/name"):
        with pytest.raises(ValueError, match="hostname"):
            ca.issue(hostname)


def test_issue_reuses_certificate_until_renewal_window(tmp_path: Path):
    clock = Clock(datetime(2026, 10, 2, tzinfo=timezone.utc))
    ca = service(
        tmp_path,
        clock=clock,
        leaf_lifetime=timedelta(days=10),
        renewal_window=timedelta(days=3),
    )

    first = ca.issue("app.workshop.local")
    first_serial = load_cert(first.certificate_path).serial_number

    clock.value += timedelta(days=5)
    second = ca.issue("app.workshop.local")

    assert load_cert(second.certificate_path).serial_number == first_serial


def test_renew_due_reissues_only_due_certificates(tmp_path: Path):
    clock = Clock(datetime(2026, 10, 2, tzinfo=timezone.utc))
    ca = service(
        tmp_path,
        clock=clock,
        leaf_lifetime=timedelta(days=10),
        renewal_window=timedelta(days=3),
    )
    due = ca.issue("due.workshop.local")
    stable = ca.issue("stable.workshop.local")
    due_serial = load_cert(due.certificate_path).serial_number
    stable_serial = load_cert(stable.certificate_path).serial_number

    clock.value += timedelta(days=8)
    renewed = ca.renew_due()

    assert [item.hostname for item in renewed] == [
        "due.workshop.local",
        "stable.workshop.local",
    ]
    assert load_cert(due.certificate_path).serial_number != due_serial
    assert load_cert(stable.certificate_path).serial_number != stable_serial


def test_ca_state_survives_service_restart(tmp_path: Path):
    first = service(tmp_path)
    fingerprint = load_cert(first.ca_certificate_path).fingerprint(
        __import__("cryptography").hazmat.primitives.hashes.SHA256()
    )

    second = service(tmp_path)
    reloaded = load_cert(second.ca_certificate_path).fingerprint(
        __import__("cryptography").hazmat.primitives.hashes.SHA256()
    )

    assert reloaded == fingerprint
