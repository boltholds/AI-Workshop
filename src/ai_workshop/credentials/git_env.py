from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import stat
import tempfile

from ai_workshop.credentials.models import (
    CredentialProfile,
    HttpsTokenCredentialProfile,
    SshCredentialProfile,
)


_ASKPASS_SCRIPT = """#!/bin/sh
case "$1" in
  *Username*|*username*) printf '%s\\n' "$AI_WORKSHOP_GIT_USERNAME" ;;
  *) printf '%s\\n' "$AI_WORKSHOP_GIT_TOKEN" ;;
esac
"""


class GitCredentialContext:
    def __init__(
        self,
        profile: CredentialProfile,
        secret_path: Path,
    ):
        self.profile = profile
        self.secret_path = Path(secret_path)
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._secret: str | None = None
        self.private_material_path: Path | None = None
        self._askpass_path: Path | None = None

    def __enter__(self) -> "GitCredentialContext":
        self._temporary = tempfile.TemporaryDirectory(prefix="ai-workshop-git-")
        root = Path(self._temporary.name)
        self._secret = self.secret_path.read_text(encoding="utf-8")

        if isinstance(self.profile, SshCredentialProfile):
            private_key = root / "id_key"
            shutil.copyfile(self.secret_path, private_key)
            private_key.chmod(stat.S_IRUSR | stat.S_IWUSR)
            self.private_material_path = private_key
        elif isinstance(self.profile, HttpsTokenCredentialProfile):
            askpass = root / "git-askpass.sh"
            askpass.write_text(_ASKPASS_SCRIPT, encoding="utf-8")
            askpass.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            self._askpass_path = askpass
        else:
            raise TypeError("unsupported credential profile")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.private_material_path = None
        self._askpass_path = None
        self._secret = None
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None

    def environment(self) -> dict[str, str]:
        if self._temporary is None or self._secret is None:
            raise RuntimeError("Git credential context is not active")

        env = {"GIT_TERMINAL_PROMPT": "0"}
        if isinstance(self.profile, SshCredentialProfile):
            assert self.private_material_path is not None
            key_path = shlex.quote(str(self.private_material_path))
            env["GIT_SSH_COMMAND"] = (
                f"ssh -i {key_path} -o IdentitiesOnly=yes -o BatchMode=yes "
                "-o StrictHostKeyChecking=yes"
            )
        elif isinstance(self.profile, HttpsTokenCredentialProfile):
            assert self._askpass_path is not None
            env["GIT_ASKPASS"] = str(self._askpass_path)
            env["AI_WORKSHOP_GIT_USERNAME"] = self.profile.username
            env["AI_WORKSHOP_GIT_TOKEN"] = self._secret
        return env

    def redact(self, value: str) -> str:
        if self._secret:
            return value.replace(self._secret, "[REDACTED]")
        return value
