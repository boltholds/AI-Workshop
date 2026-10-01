from __future__ import annotations

from pathlib import Path

import yaml

from ai_workshop.config import WorkshopConfig
from ai_workshop.services.config import BuildSource, ServiceConfig
from ai_workshop.workspace.paths import PathPolicy


_ALLOWED_OPERATIONS = ["status", "logs", "restart", "rebuild", "up"]


def render_service_override(
    services: ServiceConfig,
    projects: WorkshopConfig,
    *,
    compose_path: Path,
    registry_path: Path,
) -> tuple[Path, Path]:
    services.validate(projects)
    policy = PathPolicy(projects, host_paths=True)
    compose_path = compose_path.resolve()
    registry_path = registry_path.resolve()
    compose_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    rendered_services: dict[str, dict[str, object]] = {}
    rendered_volumes: dict[str, dict[str, str]] = {}
    registry_services: dict[str, dict[str, object]] = {}

    for service_id in sorted(services.services):
        spec = services.services[service_id]
        rendered: dict[str, object] = {"networks": ["ai-workshop"]}

        if isinstance(spec.source, BuildSource):
            context = policy.resolve(spec.source.project_id, spec.source.context)
            build: dict[str, str] = {"context": str(context)}
            if spec.source.dockerfile is not None:
                build["dockerfile"] = spec.source.dockerfile
            rendered["build"] = build
        else:
            rendered["image"] = spec.source.image

        if spec.command is not None:
            rendered["command"] = spec.command

        if spec.environment:
            rendered["environment"] = dict(spec.environment)

        if spec.env_files:
            workshop_root = compose_path.parent.parent.resolve()
            secrets_root = (workshop_root / ".workshop" / "secrets").resolve()
            env_files: list[str] = []
            for value in spec.env_files:
                resolved = (workshop_root / value).resolve()
                try:
                    resolved.relative_to(secrets_root)
                except ValueError as exc:
                    raise ValueError("env file resolves outside .workshop/secrets") from exc
                env_files.append(str(resolved))
            rendered["env_file"] = env_files

        published_ports = [
            f"{port.host_ip}:{port.host}:{port.container}"
            for port in spec.ports
            if port.host is not None
        ]
        if published_ports:
            rendered["ports"] = published_ports

        if spec.depends_on:
            rendered["depends_on"] = list(spec.depends_on)

        if spec.healthcheck is not None:
            rendered["healthcheck"] = {
                "test": ["CMD", *spec.healthcheck.command],
                "interval": spec.healthcheck.interval,
                "timeout": spec.healthcheck.timeout,
                "retries": spec.healthcheck.retries,
            }

        volume_mounts: list[str] = []
        for volume in spec.volumes:
            key = f"{service_id}-{volume.name}"
            volume_mounts.append(f"{key}:{volume.target}")
            rendered_volumes[key] = {"name": f"ai-workshop-{key}"}
        if volume_mounts:
            rendered["volumes"] = volume_mounts

        rendered_services[service_id] = rendered
        registry_services[service_id] = {
            "compose_project": "ai-workshop-services",
            "working_dir": str(compose_path.parent.parent.resolve()),
            "compose_files": [str(compose_path)],
            "compose_service": service_id,
            "allowed_operations": list(_ALLOWED_OPERATIONS),
        }

    document: dict[str, object] = {
        "services": rendered_services,
        "networks": {"ai-workshop": {"external": True}},
    }
    if rendered_volumes:
        document["volumes"] = rendered_volumes

    compose_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    registry_profiles = {
        profile_id: list(profile.services)
        for profile_id, profile in sorted(services.profiles.items())
    }
    registry_path.write_text(
        yaml.safe_dump(
            {"profiles": registry_profiles, "services": registry_services},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return compose_path, registry_path
