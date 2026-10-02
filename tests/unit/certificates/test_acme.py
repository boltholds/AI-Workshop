from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_workshop.certificates.acme import (
    AcmeCertificateMaterial,
    AcmeCertificateService,
)


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


class FakeProvider:
    def __init__(self, clock: Clock, label: str):
        self.clock = clock
        self.label = label
        self.calls: list[str] = []

    def issue(self, hostname: str) -> AcmeCertificateMaterial:
        self.calls.append(hostname)
        return AcmeCertificateMaterial(
            certificate_pem=f"CERT:{self.label}:{hostname}".encode(),
            private_key_pem=f"KEY:{self.label}:{hostname}".encode(),
            not_after=self.clock.value + timedelta(days=30),
        )


def test_acme_selects_named_provider(tmp_path: Path):
    clock = Clock()
    one = FakeProvider(clock, "one")
    two = FakeProvider(clock, "two")
    service = AcmeCertificateService(
        state_root=tmp_path / "acme",
        provider_id="two",
        providers={"one": one, "two": two},
        clock=clock,
    )

    issued = service.issue("app.example.com")

    assert one.calls == []
    assert two.calls == ["app.example.com"]
    assert issued.certificate_path.read_bytes() == b"CERT:two:app.example.com"
    assert issued.private_key_path.read_bytes() == b"KEY:two:app.example.com"


def test_acme_unknown_provider_is_rejected(tmp_path: Path):
    clock = Clock()

    with pytest.raises(ValueError, match="provider"):
        AcmeCertificateService(
            state_root=tmp_path / "acme",
            provider_id="missing",
            providers={"one": FakeProvider(clock, "one")},
            clock=clock,
        )


def test_acme_issue_reuses_certificate_not_due_for_renewal(tmp_path: Path):
    clock = Clock()
    provider = FakeProvider(clock, "one")
    service = AcmeCertificateService(
        state_root=tmp_path / "acme",
        provider_id="one",
        providers={"one": provider},
        clock=clock,
        renewal_window=timedelta(days=7),
    )

    first = service.issue("app.example.com")
    second = service.issue("app.example.com")

    assert first == second
    assert provider.calls == ["app.example.com"]


def test_acme_renew_due_renews_only_expiring_certificates(tmp_path: Path):
    clock = Clock()
    provider = FakeProvider(clock, "one")
    service = AcmeCertificateService(
        state_root=tmp_path / "acme",
        provider_id="one",
        providers={"one": provider},
        clock=clock,
        renewal_window=timedelta(days=7),
    )
    service.issue("app.example.com")
    service.issue("api.example.com")
    assert provider.calls == ["app.example.com", "api.example.com"]

    clock.value += timedelta(days=24)
    renewed = service.renew_due()

    assert {item.hostname for item in renewed} == {
        "app.example.com",
        "api.example.com",
    }
    assert provider.calls == [
        "app.example.com",
        "api.example.com",
        "api.example.com",
        "app.example.com",
    ] or provider.calls == [
        "app.example.com",
        "api.example.com",
        "app.example.com",
        "api.example.com",
    ]


def test_acme_state_survives_reload_and_tracks_renewal(tmp_path: Path):
    clock = Clock()
    provider = FakeProvider(clock, "one")
    state_root = tmp_path / "acme"
    service = AcmeCertificateService(
        state_root=state_root,
        provider_id="one",
        providers={"one": provider},
        clock=clock,
    )
    issued = service.issue("app.example.com")

    reloaded = AcmeCertificateService(
        state_root=state_root,
        provider_id="one",
        providers={"one": provider},
        clock=clock,
    )

    assert reloaded.issue("app.example.com") == issued
    assert provider.calls == ["app.example.com"]


def test_acme_has_no_private_local_trust_anchor_to_export(tmp_path: Path):
    clock = Clock()
    service = AcmeCertificateService(
        state_root=tmp_path / "acme",
        provider_id="one",
        providers={"one": FakeProvider(clock, "one")},
        clock=clock,
    )

    with pytest.raises(ValueError, match="public trust"):
        service.export_trust_certificate()
