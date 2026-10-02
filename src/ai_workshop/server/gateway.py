from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_workshop.credentials.store import CredentialStore
from ai_workshop.gateway.server import build_server
from ai_workshop.git.destructive import GitDestructiveService
from ai_workshop.git.service import GitRepositoryService
from ai_workshop.projects.store import ProjectStore
from ai_workshop.server.config import ServerModeConfig
from ai_workshop.server.storage import ServerStorage


@dataclass(frozen=True, slots=True)
class ServerGatewayRuntime:
    server: object
    projects: ProjectStore
    credentials: CredentialStore
    git: GitRepositoryService
    destructive_git: GitDestructiveService


def build_server_gateway_runtime(
    config: ServerModeConfig,
    *,
    state_root: Path,
) -> ServerGatewayRuntime:
    state_root = Path(state_root)
    state_root.mkdir(parents=True, exist_ok=True)

    storage = ServerStorage(config.storage_root)
    projects = ProjectStore(
        storage=storage,
        state_path=state_root / "projects.json",
    )
    credentials = CredentialStore(
        state_path=state_root / "credentials.json",
        secret_root=state_root / "credentials",
        forbidden_roots=(storage.root,),
    )
    git = GitRepositoryService(projects, credentials)
    destructive_git = GitDestructiveService(git)

    server = build_server(
        None,
        token=None,
        project_service=projects,
        git_service=git,
        git_destructive_service=destructive_git,
    )
    return ServerGatewayRuntime(
        server=server,
        projects=projects,
        credentials=credentials,
        git=git,
        destructive_git=destructive_git,
    )


def run_server_gateway(
    config: ServerModeConfig,
    *,
    state_root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    runtime = build_server_gateway_runtime(
        config,
        state_root=state_root,
    )
    runtime.server.run(
        transport="streamable-http",
        host=host,
        port=port,
        json_response=True,
        stateless_http=True,
    )
