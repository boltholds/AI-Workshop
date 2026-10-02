from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_workshop.certificates.models import (
    IssuedCertificate,
    validate_dns_hostname,
)


class AcmeCertificateMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    certificate_pem: bytes = Field(min_length=1)
    private_key_pem: bytes = Field(min_length=1, repr=False)
    not_after: datetime

    @field_validator("not_after")
    @classmethod
    def expiry_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ACME certificate expiry must be timezone-aware")
        return value


class AcmeProvider(Protocol):
    def issue(self, hostname: str) -> AcmeCertificateMaterial: ...


class AcmeCertificateService:
    def __init__(
        self,
        *,
        state_root: Path,
        provider_id: str,
        providers: Mapping[str, AcmeProvider],
        clock: Callable[[], datetime] | None = None,
        renewal_window: timedelta = timedelta(days=7),
    ):
        if renewal_window <= timedelta(0):
            raise ValueError("renewal window must be positive")
        provider = providers.get(provider_id)
        if provider is None:
            raise ValueError(f"unknown ACME provider: {provider_id}")

        self.state_root = Path(state_root).expanduser().resolve()
        self.provider_id = provider_id
        self.provider = provider
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.renewal_window = renewal_window
        self.certificates_root = self.state_root / "certificates"
        self.metadata_path = self.state_root / "state.json"

        self.state_root.mkdir(parents=True, exist_ok=True)
        self._chmod(self.state_root, 0o700)
        self.certificates_root.mkdir(parents=True, exist_ok=True)
        self._chmod(self.certificates_root, 0o700)
        self._issued_state: dict[str, datetime] = {}
        self._load()

    def issue(self, hostname: str) -> IssuedCertificate:
        hostname = validate_dns_hostname(hostname)
        current = self._current(hostname)
        if (
            current is not None
            and current.not_after > self._now() + self.renewal_window
        ):
            return current
        return self._issue_from_provider(hostname)

    def renew_due(self) -> list[IssuedCertificate]:
        now = self._now()
        due = [
            hostname
            for hostname, not_after in sorted(self._issued_state.items())
            if not_after <= now + self.renewal_window
        ]
        return [
            self._issue_from_provider(hostname)
            for hostname in due
        ]

    def export_trust_certificate(self) -> bytes:
        raise ValueError(
            "ACME certificates rely on public trust; no local trust anchor exists"
        )

    def _issue_from_provider(
        self,
        hostname: str,
    ) -> IssuedCertificate:
        material = self.provider.issue(hostname)
        if material.not_after <= self._now():
            raise ValueError("ACME provider returned an expired certificate")

        cert_path, key_path = self._paths(hostname)
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        self._chmod(cert_path.parent, 0o700)

        previous_expiry = self._issued_state.get(hostname)
        try:
            self._atomic_write(
                key_path,
                material.private_key_pem,
                0o600,
            )
            self._atomic_write(
                cert_path,
                material.certificate_pem,
                0o644,
            )
            self._issued_state[hostname] = material.not_after.astimezone(
                timezone.utc
            )
            self._persist()
        except Exception:
            if previous_expiry is None:
                self._issued_state.pop(hostname, None)
            else:
                self._issued_state[hostname] = previous_expiry
            raise

        return IssuedCertificate(
            hostname=hostname,
            certificate_path=cert_path,
            private_key_path=key_path,
            not_after=material.not_after,
        )

    def _current(
        self,
        hostname: str,
    ) -> IssuedCertificate | None:
        not_after = self._issued_state.get(hostname)
        if not_after is None:
            return None
        cert_path, key_path = self._paths(hostname)
        if not cert_path.is_file() or not key_path.is_file():
            raise ValueError(
                f"incomplete ACME certificate state for {hostname}"
            )
        return IssuedCertificate(
            hostname=hostname,
            certificate_path=cert_path,
            private_key_path=key_path,
            not_after=not_after,
        )

    def _paths(self, hostname: str) -> tuple[Path, Path]:
        directory = (self.certificates_root / hostname).resolve()
        try:
            directory.relative_to(self.certificates_root)
        except ValueError as exc:
            raise ValueError(
                "ACME hostname path escapes certificate state"
            ) from exc
        return directory / "cert.pem", directory / "key.pem"

    def _load(self) -> None:
        if not self.metadata_path.exists():
            return
        payload = json.loads(
            self.metadata_path.read_text(encoding="utf-8")
        )
        if payload.get("version") != 1:
            raise ValueError("unsupported ACME certificate state version")
        if payload.get("provider_id") != self.provider_id:
            raise ValueError("ACME provider does not match persisted state")

        raw = payload.get("certificates", {})
        if not isinstance(raw, dict):
            raise ValueError("ACME certificate state must be an object")
        for hostname, value in raw.items():
            normalized = validate_dns_hostname(str(hostname))
            expiry = datetime.fromisoformat(str(value))
            if expiry.tzinfo is None or expiry.utcoffset() is None:
                raise ValueError("ACME certificate expiry must be timezone-aware")
            self._issued_state[normalized] = expiry.astimezone(timezone.utc)

    def _persist(self) -> None:
        payload = {
            "version": 1,
            "provider_id": self.provider_id,
            "certificates": {
                hostname: expiry.isoformat()
                for hostname, expiry in sorted(self._issued_state.items())
            },
        }
        temporary = self.metadata_path.with_suffix(
            self.metadata_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._chmod(temporary, 0o600)
        temporary.replace(self.metadata_path)
        self._chmod(self.metadata_path, 0o600)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ACME clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _atomic_write(path: Path, data: bytes, mode: int) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        AcmeCertificateService._chmod(temporary, mode)
        temporary.replace(path)
        AcmeCertificateService._chmod(path, mode)

    @staticmethod
    def _chmod(path: Path, mode: int) -> None:
        try:
            path.chmod(mode)
        except OSError:
            pass
