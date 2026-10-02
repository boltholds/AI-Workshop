from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import stat

from ai_workshop.certificates.local_ca import LocalCertificateAuthority
from ai_workshop.server.storage import ServerStorage


class ServerBootstrap:
    def __init__(
        self,
        *,
        storage_root: Path,
        state_root: Path,
        ca_root: Path,
        first_admin_id: str = "admin",
    ):
        self.storage_root = Path(storage_root).resolve()
        self.state_root = Path(state_root).resolve()
        self.ca_root = Path(ca_root).resolve()
        self.first_admin_id = first_admin_id

    def initialize(self) -> dict[str, object]:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.ca_root.mkdir(parents=True, exist_ok=True)

        ServerStorage(self.storage_root)
        ca = LocalCertificateAuthority(state_root=self.ca_root)

        secrets_root = self.state_root / "secrets"
        secrets_root.mkdir(parents=True, exist_ok=True)
        self._chmod(secrets_root, 0o700)

        browser_token = self._ensure_secret(
            secrets_root / "browser-token",
        )
        workspace_token = self._ensure_secret(
            secrets_root / "workspace-token",
        )
        service_token = self._ensure_secret(
            secrets_root / "service-token",
        )

        bootstrap_state = self.state_root / "bootstrap.json"
        state = self._load_state(bootstrap_state)
        if not state:
            state = {
                "version": 1,
                "first_admin_id": self.first_admin_id,
                "initialized": True,
            }
            self._atomic_json(bootstrap_state, state)
        else:
            if state.get("version") != 1:
                raise ValueError("unsupported server bootstrap state version")
            if state.get("first_admin_id") != self.first_admin_id:
                raise ValueError("server bootstrap admin identity mismatch")

        return {
            "initialized": True,
            "first_admin_id": self.first_admin_id,
            "ca_certificate": str(ca.ca_certificate_path),
            "browser_token_file": str(secrets_root / "browser-token"),
            "workspace_token_file": str(secrets_root / "workspace-token"),
            "service_token_file": str(secrets_root / "service-token"),
            "tokens": {
                "browser": browser_token,
                "workspace": workspace_token,
                "service": service_token,
            },
        }

    def _ensure_secret(self, path: Path) -> str:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if not value:
                raise ValueError("bootstrap secret file is empty")
            self._chmod(path, 0o600)
            return value

        value = secrets.token_urlsafe(48)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(value + "\n", encoding="utf-8")
        self._chmod(temporary, 0o600)
        temporary.replace(path)
        self._chmod(path, 0o600)
        return value

    @staticmethod
    def _load_state(path: Path) -> dict[str, object]:
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid server bootstrap state")
        return payload

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    @staticmethod
    def _chmod(path: Path, mode: int) -> None:
        try:
            os.chmod(path, mode)
        except OSError:
            pass
