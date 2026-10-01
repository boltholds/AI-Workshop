from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import shutil
import time
from typing import Callable

from ai_workshop.models.recovery import ConfirmationToken, ResetPlan, ResetResult


class ResetService:
    def __init__(
        self,
        *,
        cache_paths: list[Path],
        browser_artifact_paths: list[Path],
        state_resetters: dict[str, Callable[[], None]],
        infrastructure_resetter: Callable[[], None] | None,
        project_roots: list[Path],
        clock: Callable[[], float] | None = None,
    ):
        self.cache_paths = [Path(path).resolve() for path in cache_paths]
        self.browser_artifact_paths = [
            Path(path).resolve() for path in browser_artifact_paths
        ]
        self.state_resetters = dict(state_resetters)
        self.infrastructure_resetter = infrastructure_resetter
        self.project_roots = [Path(path).resolve() for path in project_roots]
        self.clock = clock or time.monotonic
        self._confirmations: dict[str, ConfirmationToken] = {}
        self._validate_reset_paths()

    def plan(self, scope: str) -> ResetPlan:
        if scope == "cache":
            paths = self.cache_paths
            actions = ["clear:cache"]
        elif scope == "browser-artifacts":
            paths = self.browser_artifact_paths
            actions = ["clear:browser-artifacts"]
        elif scope.startswith("state:"):
            state_id = scope.partition(":")[2]
            if not state_id or state_id not in self.state_resetters:
                raise ValueError("unsupported reset scope")
            paths = []
            actions = [f"state:{state_id}"]
        elif scope == "infrastructure":
            if self.infrastructure_resetter is None:
                raise ValueError("unsupported reset scope")
            paths = []
            actions = ["infrastructure"]
        else:
            raise ValueError("unsupported reset scope")

        path_strings = [str(path) for path in paths]
        digest = self._digest(scope, path_strings, actions)
        return ResetPlan(
            scope=scope,
            filesystem_paths=path_strings,
            actions=actions,
            digest=digest,
        )

    def prepare(self, plan: ResetPlan, *, ttl_seconds: float = 300.0) -> ConfirmationToken:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._validate_plan(plan)
        token = secrets.token_urlsafe(32)
        confirmation = ConfirmationToken(
            token=token,
            snapshot_id=f"reset:{plan.scope}",
            preview_digest=plan.digest,
            expires_at=self.clock() + ttl_seconds,
        )
        self._confirmations[token] = confirmation
        return confirmation

    def execute(self, plan: ResetPlan, token: str) -> ResetResult:
        self._validate_plan(plan)
        confirmation = self._confirmations.get(token)
        if confirmation is None:
            raise PermissionError("valid reset confirmation required")
        if confirmation.snapshot_id != f"reset:{plan.scope}":
            raise PermissionError("valid reset confirmation required")
        if self.clock() > confirmation.expires_at:
            self._confirmations.pop(token, None)
            raise PermissionError("reset confirmation expired")
        if confirmation.preview_digest != plan.digest:
            self._confirmations.pop(token, None)
            raise PermissionError("reset plan changed since confirmation")
        self._confirmations.pop(token, None)

        if plan.scope == "cache":
            for path in self.cache_paths:
                self._clear_directory(path)
        elif plan.scope == "browser-artifacts":
            for path in self.browser_artifact_paths:
                self._clear_directory(path)
        elif plan.scope.startswith("state:"):
            state_id = plan.scope.partition(":")[2]
            self.state_resetters[state_id]()
        elif plan.scope == "infrastructure":
            assert self.infrastructure_resetter is not None
            self.infrastructure_resetter()
        return ResetResult(scope=plan.scope)

    def _validate_plan(self, plan: ResetPlan) -> None:
        expected = self.plan(plan.scope)
        if (
            plan.filesystem_paths != expected.filesystem_paths
            or plan.actions != expected.actions
            or plan.digest != expected.digest
        ):
            raise ValueError("reset plan does not match configured scope")

    def _validate_reset_paths(self) -> None:
        for reset_path in self.cache_paths + self.browser_artifact_paths:
            for project_root in self.project_roots:
                if self._overlap(reset_path, project_root):
                    raise ValueError("reset path overlaps project root")

    @staticmethod
    def _overlap(left: Path, right: Path) -> bool:
        if left == right:
            return True
        try:
            left.relative_to(right)
            return True
        except ValueError:
            pass
        try:
            right.relative_to(left)
            return True
        except ValueError:
            return False

    @staticmethod
    def _clear_directory(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        for child in path.iterdir():
            if child.is_symlink() or child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)

    @staticmethod
    def _digest(scope: str, paths: list[str], actions: list[str]) -> str:
        return hashlib.sha256(
            json.dumps(
                {"scope": scope, "paths": paths, "actions": actions},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
