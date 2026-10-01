from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from ai_workshop.gateway.errors import WorkspaceGatewayError


class WorkspaceClient:
    def __init__(self, base_url: str, *, http: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(base_url=self.base_url, timeout=130.0)
        self._owns_http = http is None

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise WorkspaceGatewayError("WORKSPACE_UNAVAILABLE", "workspace service unavailable") from exc
        if response.is_error:
            code = "WORKSPACE_ERROR"
            message = "workspace request failed"
            try:
                body = response.json()
                error = body.get("error", {})
                code = str(error.get("code", code))
                message = str(error.get("message", message))
            except Exception:
                pass
            raise WorkspaceGatewayError(code, message, status_code=response.status_code)
        return response.json()

    async def projects(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/v1/projects")

    async def filesystem_list(self, project_id: str, path: str = ".") -> list[dict[str, Any]]:
        return await self._request("POST", "/v1/files/list", json={"project_id": project_id, "path": path})

    async def filesystem_read(self, project_id: str, path: str, max_bytes: int = 1_048_576) -> dict[str, Any]:
        return await self._request("POST", "/v1/files/read", json={"project_id": project_id, "path": path, "max_bytes": max_bytes})

    async def filesystem_write(self, project_id: str, path: str, content: str) -> dict[str, Any]:
        return await self._request("POST", "/v1/files/write", json={"project_id": project_id, "path": path, "content": content})

    async def filesystem_patch(self, project_id: str, path: str, expected: str, replacement: str, occurrence: int | None = None) -> dict[str, Any]:
        return await self._request("POST", "/v1/files/patch", json={"project_id": project_id, "path": path, "expected": expected, "replacement": replacement, "occurrence": occurrence})

    async def filesystem_search(self, project_id: str, query: str, path: str = ".") -> list[dict[str, Any]]:
        return await self._request("POST", "/v1/files/search", json={"project_id": project_id, "query": query, "path": path})

    async def shell_exec(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/v1/shell/exec", json=payload)

    async def shell_cancel(self, run_id: UUID | str) -> dict[str, Any]:
        return await self._request("POST", "/v1/shell/cancel", json={"run_id": str(run_id)})

    async def git_status(self, project_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/git/status/{project_id}")

    async def git_diff(self, project_id: str, staged: bool = False) -> dict[str, Any]:
        return await self._request("GET", f"/v1/git/diff/{project_id}", params={"staged": staged})
