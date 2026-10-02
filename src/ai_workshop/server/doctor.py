from __future__ import annotations

from pathlib import Path

from ai_workshop.doctor import CheckSpec, Doctor
from ai_workshop.server.config import ServerModeConfig
from ai_workshop.server.rootless import (
    RuntimeCommandResult,
    RuntimeExecutor,
    SubprocessRuntimeExecutor,
)
from ai_workshop.server.runtime import DEFAULT_RUNTIME_SOCKET


def build_server_doctor(
    config: ServerModeConfig,
    *,
    executor: RuntimeExecutor | None = None,
) -> Doctor:
    runtime_executor = executor or SubprocessRuntimeExecutor()

    def storage_probe() -> tuple[bool, str]:
        root = config.storage_root
        root.mkdir(parents=True, exist_ok=True)
        marker = root / ".ai-workshop-doctor"
        try:
            marker.write_text("ok", encoding="utf-8")
            marker.unlink()
        except OSError:
            return False, "server storage is not writable"
        return True, "server storage is writable"

    def socket_probe() -> tuple[bool, str]:
        socket_path = Path(DEFAULT_RUNTIME_SOCKET)
        if not socket_path.exists():
            return False, "rootless runtime socket is unavailable"
        return True, "rootless runtime socket exists"

    def engine_probe() -> tuple[bool, str]:
        result: RuntimeCommandResult = runtime_executor.run(
            [
                "docker",
                "--host",
                f"unix://{DEFAULT_RUNTIME_SOCKET}",
                "info",
                "--format",
                "{{.ServerVersion}}",
            ],
            timeout_seconds=5.0,
        )
        if result.exit_code != 0:
            return False, "rootless runtime engine is unavailable"
        version = result.stdout.strip()
        return True, f"rootless runtime engine {version or 'ready'}"

    return Doctor(
        [
            CheckSpec(
                "server-storage",
                required=True,
                probe=storage_probe,
                remediation="check the server-storage volume",
            ),
            CheckSpec(
                "rootless-socket",
                required=True,
                probe=socket_probe,
                remediation="start the rootless-runtime service",
            ),
            CheckSpec(
                "rootless-engine",
                required=True,
                probe=engine_probe,
                remediation="inspect rootless-runtime logs",
            ),
        ]
    )
