from __future__ import annotations

from ai_workshop.forge.models import ForgeRepositoryRef
from ai_workshop.forge.http import ForgeHttpError


def register_forge_tools(server, forge, principal_resolver) -> None:
    def actor() -> str:
        principal_id = principal_resolver.current_principal_id()
        if not principal_id:
            raise RuntimeError("AUTHENTICATION_REQUIRED")
        return principal_id

    def safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except ForgeHttpError as exc:
            raise RuntimeError(f"{exc.code}: {exc.message}") from None
        except (KeyError, ValueError, PermissionError) as exc:
            raise RuntimeError(str(exc).strip("'")) from None
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("FORGE_OPERATION_FAILED: forge operation failed") from None

    @server.tool()
    def forge_repository_get(project_id: str) -> dict[str, object]:
        return safe(forge.repository_get, actor(), project_id).model_dump(mode="json")

    @server.tool()
    def forge_pull_requests(project_id: str) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in safe(forge.pull_request_list, actor(), project_id)]

    @server.tool()
    def forge_pull_request_create(project_id: str, title: str, source_branch: str, target_branch: str, body: str = "") -> dict[str, object]:
        return safe(
            forge.pull_request_create,
            actor(),
            project_id,
            title=title,
            source_branch=source_branch,
            target_branch=target_branch,
            body=body,
        ).model_dump(mode="json")

    @server.tool()
    def forge_pull_request_merge(project_id: str, repository_owner: str, repository_name: str, number: int) -> dict[str, object]:
        repository = ForgeRepositoryRef(owner=repository_owner, name=repository_name)
        return safe(forge.pull_request_merge, actor(), project_id, repository, number).model_dump(mode="json")

    @server.tool()
    def forge_issues(project_id: str) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in safe(forge.issue_list, actor(), project_id)]

    @server.tool()
    def forge_issue_create(project_id: str, title: str, body: str = "") -> dict[str, object]:
        return safe(forge.issue_create, actor(), project_id, title=title, body=body).model_dump(mode="json")

    @server.tool()
    def forge_releases(project_id: str) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in safe(forge.release_list, actor(), project_id)]

    @server.tool()
    def forge_release_create(project_id: str, tag: str, name: str, body: str = "") -> dict[str, object]:
        return safe(forge.release_create, actor(), project_id, tag=tag, name=name, body=body).model_dump(mode="json")

    @server.tool()
    def forge_repository_delete_prepare(project_id: str, ttl_seconds: float = 300.0) -> dict[str, object]:
        return safe(forge.prepare_repository_delete, actor(), project_id, ttl_seconds=ttl_seconds).model_dump(mode="json")

    @server.tool()
    def forge_repository_delete(project_id: str, confirmation_token: str) -> dict[str, bool]:
        safe(forge.repository_delete, actor(), project_id, confirmation_token)
        return {"ok": True}
