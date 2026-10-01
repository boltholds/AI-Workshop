from __future__ import annotations

import argparse
import os
from pathlib import Path

from ai_workshop.compose.render import render_project_override
from ai_workshop.config import WorkshopConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-workshop")
    commands = parser.add_subparsers(dest="command", required=True)

    compose = commands.add_parser("compose")
    compose_commands = compose.add_subparsers(dest="compose_command", required=True)
    render = compose_commands.add_parser("render")
    render.add_argument("--projects", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)

    workspace = commands.add_parser("workspace")
    workspace.add_argument("--projects", type=Path, required=True)
    workspace.add_argument("--host", default="0.0.0.0")
    workspace.add_argument("--port", type=int, default=8766)

    gateway = commands.add_parser("gateway")
    gateway.add_argument("--workspace-url", default=os.getenv("AI_WORKSHOP_WORKSPACE_URL", "http://127.0.0.1:8766"))
    gateway.add_argument("--host", default=os.getenv("AI_WORKSHOP_MCP_HOST", "127.0.0.1"))
    gateway.add_argument("--port", type=int, default=int(os.getenv("AI_WORKSHOP_MCP_PORT", "8765")))
    gateway.add_argument("--browser-url", default=os.getenv("AI_WORKSHOP_BROWSER_URL"))

    browser = commands.add_parser("browser")
    browser.add_argument("--profile", type=Path, default=Path("/data/browser-profile"))
    browser.add_argument("--artifacts", type=Path, default=Path("/data/artifacts"))
    browser.add_argument("--host", default="0.0.0.0")
    browser.add_argument("--port", type=int, default=8767)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "compose" and args.compose_command == "render":
        config = WorkshopConfig.load(args.projects)
        render_project_override(config, args.output)
        return 0
    if args.command == "workspace":
        import uvicorn
        from ai_workshop.workspace.app import create_app

        config = WorkshopConfig.load(args.projects)
        uvicorn.run(create_app(config), host=args.host, port=args.port)
        return 0
    if args.command == "gateway":
        from ai_workshop.gateway.server import run_gateway

        run_gateway(args.workspace_url, host=args.host, port=args.port, browser_url=args.browser_url)
        return 0
    if args.command == "browser":
        import uvicorn
        from ai_workshop.browser.app import create_browser_app
        uvicorn.run(create_browser_app(args.profile, args.artifacts), host=args.host, port=args.port)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
