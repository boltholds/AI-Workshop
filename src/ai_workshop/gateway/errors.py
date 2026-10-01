from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class GatewayError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def sanitize_workspace_error(response: httpx.Response) -> GatewayError:
    if response.status_code >= 500:
        return GatewayError("WORKSPACE_UNAVAILABLE", "Workspace service could not complete the request")
    try:
        body = response.json()
        error = body.get("error", {})
        code = str(error.get("code") or "WORKSPACE_ERROR")
        message = str(error.get("message") or "Workspace request failed")
    except Exception:
        code = "WORKSPACE_ERROR"
        message = "Workspace request failed"
    if "Traceback" in message:
        message = "Workspace request failed"
    return GatewayError(code, message)
