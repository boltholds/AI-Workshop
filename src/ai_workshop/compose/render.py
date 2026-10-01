from __future__ import annotations

from pathlib import Path

import yaml

from ai_workshop.config import WorkshopConfig


def render_project_override(config: WorkshopConfig, output: Path) -> Path:
    volumes = []
    for project_id in sorted(config.projects):
        project = config.projects[project_id]
        volumes.append(
            {
                "type": "bind",
                "source": str(project.host),
                "target": project.container.as_posix(),
                "read_only": project.mode == "ro",
            }
        )
    document = {"services": {"agent-workspace": {"volumes": volumes}}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return output
