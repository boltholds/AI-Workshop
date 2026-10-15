"""Opt-in authenticated networked Cargo dependency prefetch service.

This service shares neither WAI control credentials nor Docker socket. It only
prepares read-only source snapshots and writable Cargo cache/lock volumes.
Actual build scripts and tests run later, offline, in the analysis worker.
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path
import re
import subprocess
from threading import Lock
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ai_workshop.analysis.cargo_cache import (
    dependency_fingerprint,
    manifest_relative_path,
    validate_project_id,
)
from ai_workshop.analysis.cargo_prefetch import prefetch


class PrefetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1, max_length=128)
    manifest_path: str = Field(default="Cargo.toml", min_length=10, max_length=512)


def create_cargo_prefetch_app(
    *,
    token: str,
    projects_root: Path,
    cache_root: Path,
    locks_root: Path,
    preparer: Callable[..., Path] = prefetch,
) -> FastAPI:
    if not token or len(token) < 16:
        raise ValueError("cargo prefetch token must contain at least 16 characters")

    projects_root = Path(projects_root)
    cache_root = Path(cache_root)
    locks_root = Path(locks_root)
    one_request = Lock()
    app = FastAPI(
        title="AI Workshop Cargo Prefetch",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        if request.url.path.startswith("/v1/"):
            expected = "Bearer " + token
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied, expected):
                return JSONResponse(status_code=401, content={"error": "unauthorized"})
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/cargo/prefetch")
    def prepare(request: PrefetchRequest):
        try:
            validate_project_id(request.project_id)
            manifest_relative_path(request.manifest_path)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_project_or_manifest"},
            )
        if not one_request.acquire(blocking=False):
            return JSONResponse(status_code=429, content={"error": "prefetch_busy"})
        try:
            preparer(
                request.project_id,
                request.manifest_path,
                projects_root=projects_root,
                cache_root=cache_root,
                locks_root=locks_root,
            )
            project = projects_root / request.project_id
            fingerprint = dependency_fingerprint(project, request.manifest_path)
            if re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
                raise ValueError("invalid dependency fingerprint")
            return {
                "prepared": True,
                "project_id": request.project_id,
                "manifest_path": request.manifest_path,
                "dependency_fingerprint": fingerprint,
            }
        except (ValueError, PermissionError, FileNotFoundError):
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_or_unavailable_cargo_project"},
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            # Do not leak fetched registry URLs, paths, credentials, or stderr.
            return JSONResponse(
                status_code=502,
                content={"error": "cargo_prefetch_failed"},
            )
        except Exception:
            return JSONResponse(
                status_code=502,
                content={"error": "cargo_prefetch_failed"},
            )
        finally:
            one_request.release()

    return app


def load_app() -> FastAPI:
    return create_cargo_prefetch_app(
        token=os.environ["AI_WORKSHOP_CARGO_PREFETCH_TOKEN"],
        projects_root=Path(
            os.environ.get("AI_WORKSHOP_PROJECTS_ROOT", "/workspace/projects")
        ),
        cache_root=Path(
            os.environ.get("AI_WORKSHOP_CARGO_CACHE_ROOT", "/cargo-cache")
        ),
        locks_root=Path(
            os.environ.get("AI_WORKSHOP_CARGO_LOCKS_ROOT", "/cargo-lockfiles")
        ),
    )
