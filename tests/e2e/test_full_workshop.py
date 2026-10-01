from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from mcp import Client


def unwrap(result):
    assert not result.is_error, str(result.content)
    structured = result.structured_content
    if structured is not None:
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return None


async def call(client: Client, name: str, arguments: dict):
    return unwrap(await client.call_tool(name, arguments))


async def workflow() -> None:
    project = Path(os.environ["AI_WORKSHOP_E2E_PROJECT"])
    outside = Path(os.environ["AI_WORKSHOP_E2E_OUTSIDE"])
    outside_before = hashlib.sha256(outside.read_bytes()).hexdigest()
    original_html = (project / "index.html").read_text(encoding="utf-8")

    async with Client("http://127.0.0.1:8765/mcp") as client:
        snapshot = await call(
            client,
            "workspace_snapshot_create",
            {"project_id": "sample"},
        )
        snapshot_id = snapshot["snapshot_id"]

        await call(
            client,
            "filesystem_patch",
            {
                "project_id": "sample",
                "path": "index.html",
                "old": "<title>Sample v1</title>",
                "new": "<title>Sample v2</title>",
            },
        )
        tests = await call(
            client,
            "shell_exec",
            {
                "project_id": "sample",
                "argv": ["python", "-m", "unittest", "-v", "test_app.py"],
            },
        )
        assert tests["exit_code"] == 0, tests

        await call(client, "services_rebuild", {"service_id": "sample-app"})
        ready = await call(
            client,
            "shell_exec",
            {
                "project_id": "sample",
                "argv": [
                    "python",
                    "-c",
                    (
                        "import time,urllib.request\n"
                        "deadline=time.time()+20\n"
                        "while True:\n"
                        "    try:\n"
                        "        body=urllib.request.urlopen('http://sample-app:8080',timeout=1).read().decode()\n"
                        "        break\n"
                        "    except Exception:\n"
                        "        assert time.time()<deadline\n"
                        "        time.sleep(.2)\n"
                        "print(body)"
                    ),
                ],
                "timeout_seconds": 25,
            },
        )
        assert ready["exit_code"] == 0, ready
        assert "Sample v2" in ready["stdout"]

        navigated = await call(
            client,
            "browser_navigate",
            {"url": "http://sample-app:8080"},
        )
        assert "sample-app:8080" in navigated

        screenshot = await client.call_tool(
            "browser_screenshot",
            {"mode": "page"},
        )
        assert not screenshot.is_error

        session_id = await call(client, "browser_record_start", {"mode": "page"})
        await call(
            client,
            "browser_click",
            {"selector": "#move", "session_id": session_id},
        )
        await call(
            client,
            "shell_exec",
            {
                "project_id": "sample",
                "argv": ["python", "-c", "import time; time.sleep(1)"],
            },
        )
        recording = await call(
            client,
            "browser_record_stop",
            {"session_id": session_id},
        )
        assert recording["media_type"] == "video/webm"

        diagnostics = await call(
            client,
            "browser_capture_diagnostics",
            {
                "session_id": session_id,
                "variants": "both",
                "legend": True,
                "sensitivity": "auto",
                "max_fps": 8,
            },
        )
        artifact_names = {
            Path(item["path"]).name
            for item in diagnostics["artifacts"]
        }
        assert {
            "recording.webm",
            "composite-neutral.png",
            "composite-time-gradient.png",
            "metadata.json",
        } <= artifact_names

        network = await call(client, "browser_network", {})
        http_hosts = {
            urlparse(event["url"]).hostname
            for event in network
            if event.get("url", "").startswith(("http://", "https://"))
        }
        assert http_hosts <= {"sample-app"}

        diff = await call(
            client,
            "git_diff",
            {"project_id": "sample", "staged": False},
        )
        assert "Sample v2" in diff

        preview = await call(
            client,
            "workspace_snapshot_preview_restore",
            {"snapshot_id": snapshot_id},
        )
        assert "index.html" in preview["reset_paths"]
        confirmation = await call(
            client,
            "workspace_snapshot_prepare_restore",
            {"snapshot_id": snapshot_id, "ttl_seconds": 300},
        )
        restored = await call(
            client,
            "workspace_snapshot_restore",
            {
                "snapshot_id": snapshot_id,
                "confirmation_token": confirmation["token"],
            },
        )
        assert restored["restored"] is True

        restored_diff = await call(
            client,
            "git_diff",
            {"project_id": "sample", "staged": False},
        )
        assert restored_diff == ""

        await call(client, "services_rebuild", {"service_id": "sample-app"})
        restored_page = await call(
            client,
            "shell_exec",
            {
                "project_id": "sample",
                "argv": [
                    "python",
                    "-c",
                    (
                        "import time,urllib.request\n"
                        "deadline=time.time()+20\n"
                        "while True:\n"
                        "    try:\n"
                        "        body=urllib.request.urlopen('http://sample-app:8080',timeout=1).read().decode()\n"
                        "        break\n"
                        "    except Exception:\n"
                        "        assert time.time()<deadline\n"
                        "        time.sleep(.2)\n"
                        "print(body)"
                    ),
                ],
                "timeout_seconds": 25,
            },
        )
        assert restored_page["exit_code"] == 0, restored_page
        assert "Sample v1" in restored_page["stdout"]

    assert (project / "index.html").read_text(encoding="utf-8") == original_html
    assert hashlib.sha256(outside.read_bytes()).hexdigest() == outside_before


def test_full_workshop_mcp_workflow():
    asyncio.run(asyncio.wait_for(workflow(), timeout=180))
