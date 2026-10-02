from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def test_offline_profile_has_no_required_public_dependencies():
    config = yaml.safe_load(
        (ROOT / "deploy/server/offline.example.yaml").read_text()
    )

    assert config["mode"] == "offline"
    assert config["public_dependencies"] == {
        "oidc": False,
        "public_forge": False,
        "acme": False,
    }
    assert config["tls"]["provider"] == "local-ca"
    assert config["forge"]["embedded_forgejo"] is True
    assert config["network"]["require_public_internet"] is False
    assert config["images"]["policy"] == "preloaded"
