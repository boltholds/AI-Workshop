from __future__ import annotations

import argparse
from pathlib import Path
import re
import secrets
import shutil

import yaml


_DEFAULT_ENV = {
    "AI_WORKSHOP_PROJECTS": "config/projects.local.yaml",
    "AI_WORKSHOP_WORKSPACE_URL": "http://127.0.0.1:8766",
    "AI_WORKSHOP_MCP_HOST": "127.0.0.1",
    "AI_WORKSHOP_MCP_PORT": "8765",
    "AI_WORKSHOP_BROWSER_URL": "http://127.0.0.1:8767",
    "AI_WORKSHOP_RECOVERY_CONFIG": "config/recovery.local.yaml",
}


def _random_token() -> str:
    return secrets.token_hex(32)


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def ensure_env_file(path: Path) -> dict[str, str]:
    path = Path(path)
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    values = _parse_env(existing_text)

    additions: list[tuple[str, str]] = []
    for key, default in _DEFAULT_ENV.items():
        if not values.get(key):
            values[key] = default
            additions.append((key, default))

    for key in ("AI_WORKSHOP_WORKSPACE_TOKEN", "AI_WORKSHOP_BROWSER_TOKEN"):
        if not values.get(key):
            value = _random_token()
            values[key] = value
            additions.append((key, value))

    if not path.exists() or additions:
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = existing_text
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix and additions:
            prefix += "\n"
        suffix = "".join(f"{key}={value}\n" for key, value in additions)
        path.write_text(prefix + suffix, encoding="utf-8")
    return values


def _project_id_from_path(project_path: Path) -> str:
    raw = project_path.name.strip()
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-.")
    if not value:
        value = "project"
    return value.lower()


def _validate_project_id(project_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", project_id):
        raise ValueError("project id must contain only letters, digits, dot, underscore, or dash")
    return project_id


def ensure_project_config(
    path: Path,
    project_path: Path | None,
    *,
    project_id: str | None = None,
) -> bool:
    path = Path(path)
    if path.exists():
        return False
    if project_path is None:
        raise ValueError("project path is required on the first bootstrap run")

    project_path = Path(project_path).expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise ValueError(f"project path does not exist or is not a directory: {project_path}")

    resolved_id = _validate_project_id(project_id or _project_id_from_path(project_path))
    payload = {
        "projects": {
            resolved_id: {
                "host": str(project_path),
                "container": f"/workspace/{resolved_id}",
                "mode": "rw",
            }
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return True


def ensure_recovery_config(path: Path, example_path: Path) -> bool:
    path = Path(path)
    if path.exists():
        return False
    example_path = Path(example_path)
    if not example_path.is_file():
        raise FileNotFoundError(f"recovery example not found: {example_path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example_path, path)
    return True


def initialize_local(
    repo_root: Path,
    *,
    project_path: Path | None,
    project_id: str | None = None,
) -> dict[str, object]:
    repo_root = Path(repo_root).resolve()
    env_path = repo_root / ".env.local"
    projects_path = repo_root / "config" / "projects.local.yaml"
    recovery_path = repo_root / "config" / "recovery.local.yaml"
    recovery_example = repo_root / "config" / "recovery.example.yaml"

    env = ensure_env_file(env_path)
    project_created = ensure_project_config(
        projects_path,
        project_path,
        project_id=project_id,
    )
    recovery_created = ensure_recovery_config(recovery_path, recovery_example)
    return {
        "env_path": str(env_path),
        "projects_path": str(projects_path),
        "recovery_path": str(recovery_path),
        "project_created": project_created,
        "recovery_created": recovery_created,
        "env": env,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ai_workshop.bootstrap")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--project", type=Path)
    parser.add_argument("--project-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = initialize_local(
        args.repo_root,
        project_path=args.project,
        project_id=args.project_id,
    )
    print(f"Local environment: {result['env_path']}")
    print(f"Projects config: {result['projects_path']}")
    print(f"Recovery config: {result['recovery_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
