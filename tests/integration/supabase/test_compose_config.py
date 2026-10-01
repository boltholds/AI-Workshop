from pathlib import Path

import yaml


def test_supabase_override_only_attaches_api_gateway_to_workshop_network():
    path = Path("infrastructure/supabase/workshop.override.yaml")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "api-gw" in doc["services"]
    assert "ai-workshop" in doc["services"]["api-gw"]["networks"]
    assert doc["networks"]["ai-workshop"] == {"external": True}
    assert "/var/run/docker.sock" not in path.read_text(encoding="utf-8")
