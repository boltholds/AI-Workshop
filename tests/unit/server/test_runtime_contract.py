from pathlib import Path
from typing import get_type_hints

import pytest

from ai_workshop.server.models import (
    RuntimeEndpoint,
    RuntimeWorkloadSpec,
    RuntimeWorkloadState,
    RuntimeWorkloadStatus,
)
from ai_workshop.server.runtime import RuntimeController


@pytest.mark.parametrize(
    "value",
    ["--privileged", "../escape", "name/child", "/absolute"],
)
def test_runtime_models_reject_cli_fragment_identifiers(value: str):
    with pytest.raises(ValueError):
        RuntimeWorkloadSpec(
            workload_id=value,
            image="python:3.12-slim",
        )


def test_runtime_workload_models_are_typed():
    spec = RuntimeWorkloadSpec(
        workload_id="run-123",
        image="python:3.12-slim",
        command=("python", "-V"),
    )
    status = RuntimeWorkloadStatus(
        workload_id="run-123",
        state=RuntimeWorkloadState.RUNNING,
    )
    endpoint = RuntimeEndpoint(
        workload_id="run-123",
        host="127.0.0.1",
        host_port=40123,
        container_port=8080,
    )

    assert spec.command == ("python", "-V")
    assert status.state is RuntimeWorkloadState.RUNNING
    assert endpoint.container_port == 8080


def test_runtime_controller_protocol_defines_bounded_lifecycle_surface():
    expected = {
        "create",
        "start",
        "stop",
        "remove",
        "status",
        "logs",
        "publish_private_endpoint",
    }

    assert expected <= set(RuntimeController.__dict__)
    assert get_type_hints(RuntimeController.create)["spec"] is RuntimeWorkloadSpec
