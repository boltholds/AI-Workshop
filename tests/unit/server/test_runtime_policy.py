from pathlib import Path, PurePosixPath

import pytest

from ai_workshop.server.models import (
    RuntimeDeviceMapping,
    RuntimeMount,
    RuntimeNetworkNamespace,
    RuntimePidNamespace,
    RuntimeWorkloadSpec,
)
from ai_workshop.server.policy import RuntimePolicy
from ai_workshop.server.rootless import DEFAULT_RUNTIME_SOCKET
from ai_workshop.server.storage import ServerStorage


def policy(tmp_path: Path) -> tuple[RuntimePolicy, ServerStorage]:
    storage = ServerStorage(tmp_path / "server-state")
    return RuntimePolicy(storage), storage


def test_policy_accepts_mount_inside_server_run_storage(tmp_path: Path):
    runtime_policy, storage = policy(tmp_path)
    source = storage.resolve_run_path("run-1", "workspace")
    source.mkdir(parents=True)

    runtime_policy.validate(
        RuntimeWorkloadSpec(
            workload_id="run-1",
            image="python:3.12-slim",
            mounts=(
                RuntimeMount(
                    source=source,
                    target=PurePosixPath("/workspace/project"),
                ),
            ),
            container_ports=(8080,),
        )
    )


def test_policy_rejects_privileged_workload(tmp_path: Path):
    runtime_policy, _ = policy(tmp_path)

    with pytest.raises(ValueError, match="privileged"):
        runtime_policy.validate(
            RuntimeWorkloadSpec(
                workload_id="run-1",
                image="python:3.12-slim",
                privileged=True,
            )
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pid_namespace", RuntimePidNamespace.HOST),
        ("network_namespace", RuntimeNetworkNamespace.HOST),
    ],
)
def test_policy_rejects_host_namespaces(tmp_path: Path, field: str, value):
    runtime_policy, _ = policy(tmp_path)
    kwargs = {field: value}

    with pytest.raises(ValueError, match="host"):
        runtime_policy.validate(
            RuntimeWorkloadSpec(
                workload_id="run-1",
                image="python:3.12-slim",
                **kwargs,
            )
        )


def test_nested_spec_rejects_runtime_socket_mount(tmp_path: Path):
    runtime_policy, _ = policy(tmp_path)

    with pytest.raises(ValueError, match="runtime socket"):
        runtime_policy.validate(
            RuntimeWorkloadSpec(
                workload_id="run-1",
                image="python:3.12-slim",
                mounts=(
                    RuntimeMount(
                        source=Path(DEFAULT_RUNTIME_SOCKET),
                        target=PurePosixPath("/run/docker.sock"),
                    ),
                ),
            )
        )


def test_policy_rejects_mount_outside_server_storage(tmp_path: Path):
    runtime_policy, _ = policy(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(ValueError, match="storage"):
        runtime_policy.validate(
            RuntimeWorkloadSpec(
                workload_id="run-1",
                image="python:3.12-slim",
                mounts=(
                    RuntimeMount(
                        source=outside,
                        target=PurePosixPath("/workspace/outside"),
                    ),
                ),
            )
        )


def test_policy_rejects_device_mappings(tmp_path: Path):
    runtime_policy, _ = policy(tmp_path)

    with pytest.raises(ValueError, match="device"):
        runtime_policy.validate(
            RuntimeWorkloadSpec(
                workload_id="run-1",
                image="python:3.12-slim",
                devices=(
                    RuntimeDeviceMapping(
                        source=Path("/dev/null"),
                        target=PurePosixPath("/dev/null"),
                    ),
                ),
            )
        )


def test_policy_rejects_duplicate_container_ports(tmp_path: Path):
    runtime_policy, _ = policy(tmp_path)

    with pytest.raises(ValueError, match="duplicate"):
        runtime_policy.validate(
            RuntimeWorkloadSpec(
                workload_id="run-1",
                image="python:3.12-slim",
                container_ports=(8080, 8080),
            )
        )


def test_agent_run_rejects_mount_from_other_server_storage(tmp_path: Path):
    runtime_policy, storage = policy(tmp_path)
    other_run = storage.resolve_run_path("run-2", "workspace")
    other_run.mkdir(parents=True)

    with pytest.raises(ValueError, match="assigned workload storage"):
        runtime_policy.validate(
            RuntimeWorkloadSpec(
                workload_id="run-1",
                image="python:3.12-slim",
                mounts=(
                    RuntimeMount(
                        source=other_run,
                        target=PurePosixPath("/workspace/project"),
                    ),
                ),
            )
        )


def test_project_service_rejects_canonical_project_store_mount(tmp_path: Path):
    runtime_policy, storage = policy(tmp_path)
    project = storage.project_root("project-1")

    with pytest.raises(ValueError, match="assigned workload storage"):
        runtime_policy.validate(
            RuntimeWorkloadSpec(
                workload_id="service-1",
                image="nginx:latest",
                kind="project-service",
                mounts=(
                    RuntimeMount(
                        source=project,
                        target=PurePosixPath("/workspace/project"),
                    ),
                ),
            )
        )
