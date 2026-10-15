from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from ai_workshop.analysis.project_files import ProjectFileService
from ai_workshop.credentials.store import CredentialStore
from ai_workshop.gateway.analysis_client import AnalysisClient
from ai_workshop.gateway.cargo_prefetch_client import CargoPrefetchClient
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
    project_files_enabled = os.environ.get("AI_WORKSHOP_ENABLE_PROJECT_FILES", "0") == "1"
    files = ProjectFileService(projects) if project_files_enabled else None

    analysis_url = os.environ.get("AI_WORKSHOP_ANALYSIS_URL")
    analysis_token = os.environ.get("AI_WORKSHOP_ANALYSIS_TOKEN")
    if bool(analysis_url) != bool(analysis_token):
        raise ValueError("analysis worker URL and token must be configured together")
    if analysis_url and not project_files_enabled:
        raise ValueError("analysis worker requires explicit project-file tool enablement")
    analysis = AnalysisClient(analysis_url, token=analysis_token) if analysis_url and analysis_token else None

    prefetch_url = os.environ.get("AI_WORKSHOP_CARGO_PREFETCH_URL")
    prefetch_token = os.environ.get("AI_WORKSHOP_CARGO_PREFETCH_TOKEN")
    if bool(prefetch_url) != bool(prefetch_token):
        raise ValueError("Cargo prefetch URL and token must be configured together")
    if prefetch_url and (not project_files_enabled or analysis is None):
        raise ValueError("Cargo prefetch requires project files and the offline analysis worker")
    prefetch = (
        CargoPrefetchClient(prefetch_url, token=prefetch_token)
        if prefetch_url and prefetch_token else None
    )

    rea_url = os.environ.get("AI_WORKSHOP_REA_URL")
    rea_token = os.environ.get("AI_WORKSHOP_REA_TOKEN")
    if bool(rea_url) != bool(rea_token):
        raise ValueError("REA URL and token must be configured together")
    rea_proxy = None
    principal = None
    if rea_url and rea_token:
        from ai_workshop.rea.gateway import ServerOperator, build_rea_proxy
        rea_proxy = build_rea_proxy(rea_url, rea_token, state_root)
        principal = ServerOperator()

    server = build_server(
        None,
        token=None,
        project_service=projects,
        git_service=git,
        git_destructive_service=destructive_git,
        credential_service=credentials,
        project_files_service=files,
        analysis_service=analysis,
        cargo_prefetch_service=prefetch,
        mcp_proxy_service=rea_proxy,
        principal_resolver=principal,
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
