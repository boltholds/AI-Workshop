from __future__ import annotations

from pathlib import Path

import yaml

from ai_workshop.config import WorkshopConfig


def render_project_override(config: WorkshopConfig, output: Path) -> Path:
    volumes = [
        {
            "type": "bind",
            "source": str(project.host),
            "target": str(project.container),
            "read_only": project.mode == "ro",
        }
        for project in config.projects
    ]
    document = {"services": {"agent-workspace": {"volumes": volumes}}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return output
