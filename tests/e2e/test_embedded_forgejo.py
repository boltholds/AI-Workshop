from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_embedded_forgejo_is_optional_and_not_host_published():
    compose = yaml.safe_load((ROOT / "infrastructure/forgejo/compose.yaml").read_text())
    service = compose["services"]["forgejo"]

    assert "ports" not in service
    assert service["networks"] == ["server-control"]
    assert "forgejo-data:/var/lib/gitea" in service["volumes"]


def test_disable_forgejo_preserves_data():
    compose = yaml.safe_load((ROOT / "infrastructure/forgejo/compose.yaml").read_text())

    assert compose["volumes"]["forgejo-data"]["name"] == "ai-workshop-forgejo-data"
    assert compose["volumes"]["forgejo-config"]["name"] == "ai-workshop-forgejo-config"


def test_embedded_profile_uses_internal_http_only():
    config = yaml.safe_load((ROOT / "config/forgejo.example.yaml").read_text())
    profile = config["profile"]

    assert profile["provider"] == "forgejo"
    assert profile["base_url"] == "http://forgejo:3000"
    assert profile["transport_security"] == "internal-http"
