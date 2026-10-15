"""Typed gateway client for the separately networked Cargo prefetch sidecar."""
from __future__ import annotations

import re

import httpx


class CargoPrefetchClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token or len(token) < 16:
            raise ValueError("cargo prefetch token is missing or too short")
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": "Bearer " + token},
            timeout=1800,
            transport=transport,
        )

    def prepare(
        self,
        project_id: str,
        manifest_path: str = "Cargo.toml",
    ) -> dict[str, object]:
        try:
            response = self._http.post(
                "/v1/cargo/prefetch",
                json={"project_id": project_id, "manifest_path": manifest_path},
            )
        except httpx.HTTPError:
            raise RuntimeError(
                "CARGO_PREFETCH_UNAVAILABLE: prefetch sidecar is not responding"
            ) from None

        if response.status_code == 429:
            raise RuntimeError("CARGO_PREFETCH_BUSY: another project is being prepared")
        if response.status_code == 400:
            raise ValueError("Invalid or unavailable Cargo project/manifest")
        if response.status_code == 401:
            raise RuntimeError("CARGO_PREFETCH_UNAUTHORIZED: check sidecar credentials")
        if response.status_code != 200:
            raise RuntimeError(
                "CARGO_PREFETCH_FAILED: isolated dependency preparation failed"
            )
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError("CARGO_PREFETCH_INVALID_RESPONSE") from None
        if (
            not isinstance(result, dict)
            or result.get("prepared") is not True
            or result.get("project_id") != project_id
            or result.get("manifest_path") != manifest_path
            or not isinstance(result.get("dependency_fingerprint"), str)
            or re.fullmatch(r"[0-9a-f]{64}", result["dependency_fingerprint"]) is None
        ):
            raise RuntimeError("CARGO_PREFETCH_INVALID_RESPONSE")
        return {
            "prepared": True,
            "project_id": project_id,
            "manifest_path": manifest_path,
            "dependency_fingerprint": result["dependency_fingerprint"],
        }
