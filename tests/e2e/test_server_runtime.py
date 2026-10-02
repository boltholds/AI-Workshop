from __future__ import annotations

from pathlib import Path
import sys
import time

from ai_workshop.server.config import ServerModeConfig
from ai_workshop.server.factory import build_runtime_controller
from ai_workshop.server.models import (
    RuntimeWorkloadKind,
    RuntimeWorkloadSpec,
    RuntimeWorkloadState,
)


CONFIG = Path("/config/server.yaml")
STATE = Path("/state")
WORKLOAD_ID = "server-runtime-smoke"


def runtime():
    return build_runtime_controller(
        ServerModeConfig.load(CONFIG),
        state_root=STATE,
    )


def wait_for_state(controller, expected: RuntimeWorkloadState, timeout: float = 20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = controller.status(WORKLOAD_ID)
        if status.state is expected:
            return status
        time.sleep(0.2)
    raise AssertionError(
        f"workload did not reach {expected.value}: "
        f"{controller.status(WORKLOAD_ID).state.value}"
    )


def phase_one() -> None:
    config = ServerModeConfig.load(CONFIG)
    controller = runtime()
    controller.ensure_image("alpine:3.22")
    controller.create(
        RuntimeWorkloadSpec(
            workload_id=WORKLOAD_ID,
            image="alpine:3.22",
            kind=RuntimeWorkloadKind.PROJECT_SERVICE,
            command=("sh", "-c", "echo server-runtime-ok; sleep 120"),
            container_ports=(8080,),
        )
    )
    controller.start(WORKLOAD_ID)
    wait_for_state(controller, RuntimeWorkloadState.RUNNING)
    endpoint = controller.publish_private_endpoint(WORKLOAD_ID, 8080)
    assert endpoint.host == "rootless-runtime"
    assert 41000 <= endpoint.host_port <= 41999
    (config.storage_root / "server-runtime-marker.txt").write_text(
        str(endpoint.host_port),
        encoding="utf-8",
    )


def phase_two() -> None:
    config = ServerModeConfig.load(CONFIG)
    controller = runtime()
    status = controller.status(WORKLOAD_ID)
    assert status.state is RuntimeWorkloadState.RUNNING
    endpoint = controller.publish_private_endpoint(WORKLOAD_ID, 8080)
    marker = config.storage_root / "server-runtime-marker.txt"
    assert marker.read_text(encoding="utf-8") == str(endpoint.host_port)
    assert "server-runtime-ok" in controller.logs(WORKLOAD_ID, tail=20)
    controller.stop(WORKLOAD_ID)
    controller.remove(WORKLOAD_ID)
    assert marker.is_file()


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    if phase == "phase-one":
        phase_one()
    elif phase == "phase-two":
        phase_two()
    else:
        raise SystemExit("expected phase-one or phase-two")
