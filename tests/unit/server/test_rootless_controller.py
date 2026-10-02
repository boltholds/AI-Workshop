from __future__ import annotations

import inspect
from pathlib import Path, PurePosixPath

import pytest

from ai_workshop.server.models import (
    RuntimeEndpoint,
    RuntimeEnvironmentVariable,
    RuntimeMount,
    RuntimeWorkloadSpec,
    RuntimeWorkloadState,
)
from ai_workshop.server.network import NetworkGrant, NetworkGrantPurpose
from ai_workshop.server.rootless import (
    DEFAULT_RUNTIME_SOCKET,
    RootlessDockerController,
    RuntimeCommandResult,
)


class NoEndpointRegistry:
    def __init__(self):
        self.released: list[str] = []

    def allocate(self, workload_id: str, container_port: int) -> RuntimeEndpoint:
        return RuntimeEndpoint(
            workload_id=workload_id,
            host="rootless-runtime",
            host_port=41000 + container_port % 100,
            container_port=container_port,
        )

    def require(self, workload_id: str, container_port: int) -> RuntimeEndpoint:
        return self.allocate(workload_id, container_port)

    def release(self, workload_id: str) -> None:
        self.released.append(workload_id)


class AllowNetworkPolicy:
    def allowed_networks(self, workload: RuntimeWorkloadSpec):
        return ()


class AllowPolicy:
    def validate(self, spec: RuntimeWorkloadSpec) -> None:
        return None


class RejectPolicy:
    def validate(self, spec: RuntimeWorkloadSpec) -> None:
        raise ValueError("policy rejected")


class CapturingExecutor:
    def __init__(self):
        self.calls: list[tuple[list[str], float]] = []
        self.next = RuntimeCommandResult(exit_code=0, stdout="", stderr="")

    def run(self, argv: list[str], *, timeout_seconds: float) -> RuntimeCommandResult:
        self.calls.append((list(argv), timeout_seconds))
        return self.next


def controller():
    executor = CapturingExecutor()
    return RootlessDockerController(
        policy=AllowPolicy(),
        network_policy=AllowNetworkPolicy(),
        endpoint_registry=NoEndpointRegistry(),
        executor=executor,
    ), executor


def test_create_uses_private_rootless_socket_and_fixed_argv():
    ctl, executor = controller()
    spec = RuntimeWorkloadSpec(
        workload_id="run-123",
        image="python:3.12-slim",
        command=("python", "-V"),
    )

    status = ctl.create(spec)

    argv, _ = executor.calls[-1]
    assert argv == [
        "docker",
        "--host",
        f"unix://{DEFAULT_RUNTIME_SOCKET}",
        "create",
        "--name",
        "run-123",
        "--",
        "python:3.12-slim",
        "python",
        "-V",
    ]
    assert status.state is RuntimeWorkloadState.CREATED


def test_environment_value_cannot_inject_docker_arguments():
    ctl, executor = controller()
    spec = RuntimeWorkloadSpec(
        workload_id="run-123",
        image="python:3.12-slim",
        environment=(
            RuntimeEnvironmentVariable(name="PAYLOAD", value="--privileged"),
        ),
    )

    ctl.create(spec)

    argv, _ = executor.calls[-1]
    assert argv[argv.index("--env") + 1] == "PAYLOAD=--privileged"
    assert argv.count("--privileged") == 0


def test_runtime_models_reject_image_cli_fragment():
    with pytest.raises(ValueError):
        RuntimeWorkloadSpec(
            workload_id="run-123",
            image="--privileged",
        )


def test_controller_lifecycle_commands_are_fixed():
    ctl, executor = controller()

    ctl.start("run-123")
    assert executor.calls[-1][0][-2:] == ["start", "run-123"]

    ctl.stop("run-123")
    assert executor.calls[-1][0][-2:] == ["stop", "run-123"]

    ctl.remove("run-123")
    assert executor.calls[-1][0][-3:] == ["rm", "--", "run-123"]


def test_status_and_logs_use_bounded_commands():
    ctl, executor = controller()
    executor.next = RuntimeCommandResult(exit_code=0, stdout="running\n", stderr="")
    status = ctl.status("run-123")
    assert status.state is RuntimeWorkloadState.RUNNING
    assert executor.calls[-1][0][-4:] == [
        "--format",
        "{{.State.Status}}",
        "--",
        "run-123",
    ]

    executor.next = RuntimeCommandResult(exit_code=0, stdout="line 1\n", stderr="")
    assert ctl.logs("run-123", tail=25) == "line 1\n"
    assert executor.calls[-1][0][-5:] == [
        "logs",
        "--tail",
        "25",
        "--",
        "run-123",
    ]


def test_controller_does_not_expose_raw_docker_argument_parameters():
    for method_name in ("create", "start", "stop", "remove", "status", "logs"):
        parameters = inspect.signature(getattr(RootlessDockerController, method_name)).parameters
        forbidden = {"argv", "args", "options", "docker_args", "raw_args"}
        assert forbidden.isdisjoint(parameters)


def test_create_validates_policy_before_runtime_execution():
    executor = CapturingExecutor()
    ctl = RootlessDockerController(
        policy=RejectPolicy(),
        network_policy=AllowNetworkPolicy(),
        endpoint_registry=NoEndpointRegistry(),
        executor=executor,
    )

    with pytest.raises(ValueError, match="policy rejected"):
        ctl.create(
            RuntimeWorkloadSpec(
                workload_id="run-123",
                image="python:3.12-slim",
            )
        )

    assert executor.calls == []


class PrivateNetworkPolicy:
    def allowed_networks(self, workload: RuntimeWorkloadSpec):
        return (
            NetworkGrant(
                network_name="ai-workshop-agent-runs",
                purpose=NetworkGrantPurpose.PRIVATE,
                internal=True,
            ),
        )


def test_create_consumes_network_grants_from_policy():
    executor = CapturingExecutor()
    ctl = RootlessDockerController(
        policy=AllowPolicy(),
        network_policy=PrivateNetworkPolicy(),
        endpoint_registry=NoEndpointRegistry(),
        executor=executor,
    )

    ctl.create(
        RuntimeWorkloadSpec(
            workload_id="run-123",
            image="python:3.12-slim",
        )
    )

    argv, _ = executor.calls[-1]
    assert argv[argv.index("--network") + 1] == "ai-workshop-agent-runs"


def test_create_allocates_private_endpoint_for_declared_container_port():
    executor = CapturingExecutor()
    endpoints = NoEndpointRegistry()
    ctl = RootlessDockerController(
        policy=AllowPolicy(),
        network_policy=AllowNetworkPolicy(),
        endpoint_registry=endpoints,
        executor=executor,
    )

    ctl.create(
        RuntimeWorkloadSpec(
            workload_id="service-1",
            image="nginx:latest",
            container_ports=(8080,),
        )
    )

    argv, _ = executor.calls[-1]
    assert argv[argv.index("--publish") + 1] == "41080:8080"
    assert ctl.publish_private_endpoint("service-1", 8080).host == "rootless-runtime"


def test_remove_releases_private_endpoints():
    executor = CapturingExecutor()
    endpoints = NoEndpointRegistry()
    ctl = RootlessDockerController(
        policy=AllowPolicy(),
        network_policy=AllowNetworkPolicy(),
        endpoint_registry=endpoints,
        executor=executor,
    )

    ctl.remove("service-1")

    assert endpoints.released == ["service-1"]


def test_controller_can_explicitly_ensure_image():
    ctl, executor = controller()

    ctl.ensure_image("alpine:3.22")

    assert executor.calls[-1][0] == [
        "docker",
        "--host",
        f"unix://{DEFAULT_RUNTIME_SOCKET}",
        "pull",
        "--",
        "alpine:3.22",
    ]


def test_create_renders_validated_runtime_mount(tmp_path: Path):
    executor = CapturingExecutor()
    ctl = RootlessDockerController(
        policy=AllowPolicy(),
        network_policy=AllowNetworkPolicy(),
        endpoint_registry=NoEndpointRegistry(),
        executor=executor,
    )
    source = (tmp_path / "workspace").resolve()
    source.mkdir()

    ctl.create(
        RuntimeWorkloadSpec(
            workload_id="run-123",
            image="python:3.12-slim",
            mounts=(
                RuntimeMount(
                    source=source,
                    target=PurePosixPath("/workspace/project"),
                    read_only=True,
                ),
            ),
        )
    )

    argv, _ = executor.calls[-1]
    mount_value = argv[argv.index("--mount") + 1]
    assert f"src={source}" in mount_value
    assert "dst=/workspace/project" in mount_value
    assert "readonly" in mount_value


class MissingThenSuccessExecutor(CapturingExecutor):
    def __init__(self):
        super().__init__()
        self.results = [
            RuntimeCommandResult(exit_code=1, stdout="", stderr="not found"),
            RuntimeCommandResult(exit_code=0, stdout="", stderr=""),
            RuntimeCommandResult(exit_code=0, stdout="", stderr=""),
        ]

    def run(self, argv: list[str], *, timeout_seconds: float) -> RuntimeCommandResult:
        self.calls.append((list(argv), timeout_seconds))
        return self.results.pop(0)


def test_create_ensures_private_network_is_internal_before_container():
    executor = MissingThenSuccessExecutor()
    ctl = RootlessDockerController(
        policy=AllowPolicy(),
        network_policy=PrivateNetworkPolicy(),
        endpoint_registry=NoEndpointRegistry(),
        executor=executor,
    )

    ctl.create(
        RuntimeWorkloadSpec(
            workload_id="run-123",
            image="python:3.12-slim",
        )
    )

    assert executor.calls[0][0][-4:] == [
        "network",
        "inspect",
        "--",
        "ai-workshop-agent-runs",
    ]
    assert executor.calls[1][0][-5:] == [
        "network",
        "create",
        "--internal",
        "--",
        "ai-workshop-agent-runs",
    ]
