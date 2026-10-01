from __future__ import annotations

import os


_CONTROL_SECRET_NAMES = {
    "AI_WORKSHOP_WORKSPACE_TOKEN",
    "AI_WORKSHOP_BROWSER_TOKEN",
    "AI_WORKSHOP_MCP_TOKEN",
}


def safe_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for name in _CONTROL_SECRET_NAMES:
        env.pop(name, None)
    if extra:
        env.update(extra)
    return env
