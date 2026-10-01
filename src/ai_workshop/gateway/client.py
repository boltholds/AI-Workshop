from __future__ import annotations

from typing import Any

import httpx

from ai_workshop.gateway.errors import sanitize_workspace_error


class WorkspaceClient:
    def __init__(self, base_url: str, *, token: str, transport: httpx.BaseTransport | None = None, timeout: float = 60.0):
        if not token:
            raise ValueError("workspace token must not be empty")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            transport=transport,
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            from ai_workshop.gateway.errors import GatewayError
            raise GatewayError("WORKSPACE_UNAVAILABLE", "Workspace service could not be reached") from exc
        if response.is_error:
            raise sanitize_workspace_error(response)
        return response.json()

    def projects(self) -> list[str]:
        return list(self._request("GET", "/v1/projects")["projects"])

    def file_list(self, project_id: str, path: str = ".") -> list[str]:
        return list(self._request("GET", "/v1/files/list", params={"project_id": project_id, "path": path})["entries"])

    def file_read(self, project_id: str, path: str) -> str:
        return str(self._request("POST", "/v1/files/read", json={"project_id": project_id, "path": path})["content"])

    def file_write(self, project_id: str, path: str, content: str) -> None:
        self._request("POST", "/v1/files/write", json={"project_id": project_id, "path": path, "content": content})

    def file_patch(self, project_id: str, path: str, old: str, new: str, occurrence: int | None = None) -> None:
        self._request("POST", "/v1/files/patch", json={"project_id": project_id, "path": path, "old": old, "new": new, "occurrence": occurrence})

    def file_search(self, project_id: str, needle: str, path: str = ".") -> list[dict[str, Any]]:
        return list(self._request("POST", "/v1/files/search", json={"project_id": project_id, "needle": needle, "path": path})["matches"])

    def shell_exec(self, project_id: str, argv: list[str], *, cwd: str = ".", env: dict[str, str] | None = None, timeout_seconds: float = 60.0) -> dict[str, Any]:
        return self._request("POST", "/v1/shell/exec", json={"project_id": project_id, "argv": argv, "cwd": cwd, "env": env or {}, "timeout_seconds": timeout_seconds})

    def shell_cancel(self, run_id: str) -> bool:
        return bool(self._request("POST", "/v1/shell/cancel", json={"run_id": run_id})["cancelled"])

    def git_status(self, project_id: str) -> str:
        return str(self._request("GET", "/v1/git/status", params={"project_id": project_id})["porcelain"])

    def git_diff(self, project_id: str, *, staged: bool = False) -> str:
        return str(self._request("GET", "/v1/git/diff", params={"project_id": project_id, "staged": staged})["diff"])
