from __future__ import annotations

from ai_workshop.projects.models import ExternalProject, GitManagedProject


def _project_payload(project) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_id": project.project_id,
        "kind": project.kind.value,
    }
    if isinstance(project, GitManagedProject):
        payload["remote_url"] = project.remote_url
    elif isinstance(project, ExternalProject):
        payload["external"] = True
    return payload


def register_project_tools(server, projects) -> None:
    def safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except (KeyError, ValueError) as exc:
            raise RuntimeError(str(exc).strip("'")) from None
        except Exception:
            raise RuntimeError("PROJECT_OPERATION_FAILED: project operation failed") from None

    @server.tool()
    def projects_list() -> list[dict[str, object]]:
        return [_project_payload(item) for item in safe(projects.list)]

    @server.tool()
    def projects_get(project_id: str) -> dict[str, object]:
        return _project_payload(safe(projects.get, project_id))

    @server.tool()
    def projects_remove_registration(project_id: str) -> dict[str, bool]:
        safe(projects.remove_registration, project_id)
        return {"ok": True}
