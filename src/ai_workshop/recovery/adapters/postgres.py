from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Protocol

from ai_workshop.recovery.env import safe_subprocess_env


@dataclass(frozen=True, slots=True)
class PostgresTarget:
    host: str
    port: int
    database: str
    user: str
    password: str | None = None


class PostgresExecutor(Protocol):
    def run(self, argv: list[str], *, env: dict[str, str]) -> None: ...


class SubprocessPostgresExecutor:
    def run(self, argv: list[str], *, env: dict[str, str]) -> None:
        result = subprocess.run(
            argv,
            env=env,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("PostgreSQL state operation failed")


class PostgresAdapter:
    def __init__(
        self,
        targets: dict[str, PostgresTarget],
        *,
        executor: PostgresExecutor | None = None,
    ):
        self.targets = dict(targets)
        self.executor = executor or SubprocessPostgresExecutor()

    def snapshot(self, target_id: str, destination: Path) -> None:
        target = self._target(target_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            "pg_dump",
            "--format=custom",
            "--file", str(destination),
            "--host", target.host,
            "--port", str(target.port),
            "--username", target.user,
            target.database,
        ]
        self.executor.run(argv, env=self._env(target))

    def restore(self, target_id: str, artifact: Path) -> None:
        target = self._target(target_id)
        argv = [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--host", target.host,
            "--port", str(target.port),
            "--username", target.user,
            "--dbname", target.database,
            str(artifact),
        ]
        self.executor.run(argv, env=self._env(target))

    def _target(self, target_id: str) -> PostgresTarget:
        target = self.targets.get(target_id)
        if target is None:
            raise KeyError(f"unknown PostgreSQL target: {target_id}")
        return target

    @staticmethod
    def _env(target: PostgresTarget) -> dict[str, str]:
        extra: dict[str, str] = {}
        if target.password is not None:
            extra["PGPASSWORD"] = target.password
        return safe_subprocess_env(extra)
