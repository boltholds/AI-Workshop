from __future__ import annotations

import os

from ai_workshop.git.service import GitRepositoryService


def test_git_subprocess_environment_does_not_inherit_unrelated_secrets(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
    monkeypatch.setenv("GIT_ASKPASS", "/tmp/untrusted-askpass")
    monkeypatch.setenv("AI_WORKSHOP_WORKSPACE_TOKEN", "workshop-secret")

    env = GitRepositoryService._subprocess_environment(None)

    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "SSH_AUTH_SOCK" not in env
    assert env["GIT_ASKPASS"] != "/tmp/untrusted-askpass"
    assert "AI_WORKSHOP_WORKSPACE_TOKEN" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert "PATH" in env


def test_git_subprocess_without_named_ssh_credential_disables_default_identities():
    env = GitRepositoryService._subprocess_environment(None)

    command = env["GIT_SSH_COMMAND"]
    assert "IdentitiesOnly=yes" in command
    assert "BatchMode=yes" in command
    assert os.devnull in command
