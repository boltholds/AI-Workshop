from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_shell_bootstrap_uses_local_env_and_loopback_gateway():
    text = read("scripts/bootstrap.sh")
    assert "uv sync" in text
    assert "python -m ai_workshop.bootstrap" in text
    assert "--env-file .env.local" in text
    assert "127.0.0.1:8766" in text
    assert "127.0.0.1:8767" in text
    assert "ai-workshop gateway" in text
    assert "ai-workshop doctor" in text
    assert "/var/run/docker.sock" not in text


def test_powershell_bootstrap_uses_local_env_and_loopback_gateway():
    text = read("scripts/bootstrap.ps1")
    assert "uv sync" in text
    assert "python -m ai_workshop.bootstrap" in text
    assert "--env-file" in text and ".env.local" in text
    assert "127.0.0.1:8766" in text
    assert "127.0.0.1:8767" in text
    assert "ai-workshop gateway" in text
    assert "ai-workshop doctor" in text
    assert "/var/run/docker.sock" not in text


def test_tunnel_helpers_use_secure_mcp_tunnel_client():
    shell = read("scripts/tunnel.sh")
    powershell = read("scripts/tunnel.ps1")
    for text in (shell, powershell):
        assert "tunnel-client" in text
        assert "CONTROL_PLANE_API_KEY" in text
        assert "AI_WORKSHOP_TUNNEL_ID" in text
        assert "http://127.0.0.1:8765/mcp" in text
        assert "doctor" in text
        assert "run" in text


def test_chatgpt_setup_docs_keep_workshop_private():
    text = read("docs/chatgpt-setup.md")
    assert "Secure MCP Tunnel" in text
    assert "http://127.0.0.1:8765/mcp" in text
    assert "CONTROL_PLANE_API_KEY" in text
    assert "AI_WORKSHOP_TUNNEL_ID" in text
    assert "Business" in text
    assert "Enterprise" in text
    assert "Edu" in text
    assert "Pro" in text
    assert "public internet" in text.lower()


def test_bootstrap_local_secrets_and_configs_are_gitignored():
    text = read(".gitignore")
    assert ".env.local" in text
    assert "config/projects.local.yaml" in text
    assert "config/services.local.yaml" in text
    assert "config/recovery.local.yaml" in text


def test_shell_bootstrap_does_not_execute_env_file():
    text = read("scripts/bootstrap.sh")
    assert "source \"$ROOT/.env.local\"" not in text
    assert "AI_WORKSHOP_*" in text
