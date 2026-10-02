from __future__ import annotations

from typing import Protocol

from ai_workshop.certificates.models import IssuedCertificate


class CertificateService(Protocol):
    def issue(self, hostname: str) -> IssuedCertificate: ...

    def renew_due(self) -> list[IssuedCertificate]: ...

    def export_trust_certificate(self) -> bytes: ...
