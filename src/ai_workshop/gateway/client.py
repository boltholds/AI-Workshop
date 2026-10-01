from __future__ import annotations

from typing import Any

import httpx

from ai_workshop.gateway.errors import GatewayError, sanitize_workspace_error


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
            raise GatewayError("WORKSPACE_UNAVAILABLE", "Workspace service could not be reached") from exc
        if response.is_error:
            raise sanitize_workspace_error(response)
        try:
            body = response.json()
        except Exception as exc:
            raise GatewayError("WORKSPACE_PROTOCOL_ERROR", "Workspace response was invalid") from exc
        if not isinstance(body, dict):
            raise GatewayError("WORKSPACE_PROTOCOL_ERROR", "Workspace response was invalid")
        return body

    @staticmethod
    def _required(body: dict[str, Any], field: str) -> Any:
        if field not in body:
            raise GatewayError("WORKSPACE_PROTOCOL_ERROR", "Workspace response was invalid")
        return body[field]

    def projects(self) -> list[str]:
        body = self._request("GET", "/v1/projects")
        return list(self._required(body, "projects"))

    def file_list(self, project_id: str, path: str = ".") -> list[str]:
        body = self._request("GET", "/v1/files/list", params={"project_id": project_id, "path": path})
        return list(self._required(body, "entries"))

    def file_read(self, project_id: str, path: str) -> str:
        body = self._request("POST", "/v1/files/read", json={"project_id": project_id, "path": path})
        return str(self._required(body, "content"))

    def file_write(self, project_id: str, path: str, content: str) -> None:
        self._request("POST", "/v1/files/write", json={"project_id": project_id, "path": path, "content": content})

    def file_patch(self, project_id: str, path: str, old: str, new: str, occurrence: int | None = None) -> None:
        self._request("POST", "/v1/files/patch", json={"project_id": project_id, "path": path, "old": old, "new": new, "occurrence": occurrence})

    def file_search(self, project_id: str, needle: str, path: str = ".") -> list[dict[str, Any]]:
        body = self._request("POST", "/v1/files/search", json={"project_id": project_id, "needle": needle, "path": path})
        return list(self._required(body, "matches"))

    def shell_exec(self, project_id: str, argv: list[str], *, cwd: str = ".", env: dict[str, str] | None = None, timeout_seconds: float = 60.0) -> dict[str, Any]:
        return self._request("POST", "/v1/shell/exec", json={"project_id": project_id, "argv": argv, "cwd": cwd, "env": env or {}, "timeout_seconds": timeout_seconds})

    def shell_cancel(self, run_id: str) -> bool:
        body = self._request("POST", "/v1/shell/cancel", json={"run_id": run_id})
        return bool(self._required(body, "cancelled"))

    def git_status(self, project_id: str) -> str:
        body = self._request("GET", "/v1/git/status", params={"project_id": project_id})
        return str(self._required(body, "porcelain"))

    def git_diff(self, project_id: str, *, staged: bool = False) -> str:
        body = self._request("GET", "/v1/git/diff", params={"project_id": project_id, "staged": staged})
        return str(self._required(body, "diff"))

    def snapshot_create(self, project_id: str) -> dict[str, Any]:
        body = self._request(
            "POST",
            "/v1/recovery/snapshots",
            json={"project_id": project_id},
        )
        return dict(self._required(body, "snapshot"))

    def snapshot_preview_restore(self, snapshot_id: str) -> dict[str, Any]:
        body = self._request(
            "GET",
            f"/v1/recovery/snapshots/{snapshot_id}/restore-preview",
        )
        return dict(self._required(body, "preview"))

    def snapshot_prepare_restore(
        self,
        snapshot_id: str,
        ttl_seconds: float = 300.0,
    ) -> dict[str, Any]:
        body = self._request(
            "POST",
            f"/v1/recovery/snapshots/{snapshot_id}/restore-prepare",
            json={"ttl_seconds": ttl_seconds},
        )
        return dict(self._required(body, "confirmation"))

    def snapshot_restore(
        self,
        snapshot_id: str,
        confirmation_token: str,
    ) -> dict[str, Any]:
        body = self._request(
            "POST",
            f"/v1/recovery/snapshots/{snapshot_id}/restore",
            json={"confirmation_token": confirmation_token},
        )
        return dict(self._required(body, "result"))
