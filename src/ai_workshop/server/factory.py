from __future__ import annotations

from pathlib import Path

from ai_workshop.server.config import ServerModeConfig
from ai_workshop.server.endpoints import PrivateEndpointRegistry
from ai_workshop.server.network import RuntimeNetworkPolicy
from ai_workshop.server.policy import RuntimePolicy
from ai_workshop.server.rootless import RootlessDockerController, RuntimeExecutor
from ai_workshop.server.storage import ServerStorage


def build_runtime_controller(
    config: ServerModeConfig,
    *,
    state_root: Path,
    executor: RuntimeExecutor | None = None,
) -> RootlessDockerController:
    state_root = Path(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    storage = ServerStorage(config.storage_root)
    endpoints = PrivateEndpointRegistry(
        host=config.private_endpoint_host,
        start_port=config.private_endpoint_start_port,
        end_port=config.private_endpoint_end_port,
        state_path=state_root / "runtime-endpoints.json",
    )
    return RootlessDockerController(
        policy=RuntimePolicy(storage),
        network_policy=RuntimeNetworkPolicy(),
        endpoint_registry=endpoints,
        executor=executor,
    )
