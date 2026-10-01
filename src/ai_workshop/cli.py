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
    workspace.add_argument("--token", default=os.getenv("AI_WORKSHOP_WORKSPACE_TOKEN"))

    gateway = commands.add_parser("gateway")
    gateway.add_argument("--workspace-url", default=os.getenv("AI_WORKSHOP_WORKSPACE_URL", "http://127.0.0.1:8766"))
    gateway.add_argument("--host", default=os.getenv("AI_WORKSHOP_MCP_HOST", "127.0.0.1"))
    gateway.add_argument("--port", type=int, default=int(os.getenv("AI_WORKSHOP_MCP_PORT", "8765")))
    gateway.add_argument("--workspace-token", default=os.getenv("AI_WORKSHOP_WORKSPACE_TOKEN"))
    gateway.add_argument("--browser-url", default=os.getenv("AI_WORKSHOP_BROWSER_URL"))
    gateway.add_argument("--browser-token", default=os.getenv("AI_WORKSHOP_BROWSER_TOKEN"))
    gateway.add_argument(
        "--service-registry",
        type=Path,
        default=Path(os.environ["AI_WORKSHOP_SERVICE_REGISTRY"])
        if os.getenv("AI_WORKSHOP_SERVICE_REGISTRY")
        else None,
    )

    browser = commands.add_parser("browser")
    browser.add_argument("--profile", type=Path, default=Path("/data/browser-profile"))
    browser.add_argument("--artifacts", type=Path, default=Path("/data/artifacts"))
    browser.add_argument("--host", default="0.0.0.0")
    browser.add_argument("--port", type=int, default=8767)
    browser.add_argument("--token", default=os.getenv("AI_WORKSHOP_BROWSER_TOKEN"))
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

        if not args.token:
            raise SystemExit("AI_WORKSHOP_WORKSPACE_TOKEN or --token is required")
        config = WorkshopConfig.load(args.projects)
        uvicorn.run(create_app(config, workspace_token=args.token), host=args.host, port=args.port)
        return 0
    if args.command == "gateway":
        from ai_workshop.gateway.server import run_gateway

        if not args.workspace_token:
            raise SystemExit("AI_WORKSHOP_WORKSPACE_TOKEN or --workspace-token is required")
        if args.browser_url and not args.browser_token:
            raise SystemExit("AI_WORKSHOP_BROWSER_TOKEN or --browser-token is required when browser is configured")
        service_controller = None
        if args.service_registry is not None:
            from ai_workshop.controller.registry import ServiceRegistry
            from ai_workshop.controller.runner import ComposeController

            service_controller = ComposeController(ServiceRegistry.load(args.service_registry))

        run_gateway(
            args.workspace_url,
            token=args.workspace_token,
            host=args.host,
            port=args.port,
            browser_url=args.browser_url,
            browser_token=args.browser_token,
            service_controller=service_controller,
        )
        return 0
    if args.command == "browser":
        import uvicorn
        from ai_workshop.browser.app import create_browser_app

        if not args.token:
            raise SystemExit("AI_WORKSHOP_BROWSER_TOKEN or --token is required")
        uvicorn.run(
            create_browser_app(args.profile, args.artifacts, browser_token=args.token),
            host=args.host,
            port=args.port,
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
