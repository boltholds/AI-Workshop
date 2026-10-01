from __future__ import annotations

import argparse
from pathlib import Path

from ai_workshop.compose.render import render_project_override
from ai_workshop.config import WorkshopConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-workshop")
    sub = parser.add_subparsers(dest="command", required=True)

    compose = sub.add_parser("compose")
    compose_sub = compose.add_subparsers(dest="compose_command", required=True)
    render = compose_sub.add_parser("render")
    render.add_argument("--projects", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)

    workspace = sub.add_parser("workspace")
    workspace_sub = workspace.add_subparsers(dest="workspace_command", required=True)
    serve = workspace_sub.add_parser("serve")
    serve.add_argument("--config", type=Path, required=True)
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8766)

    gateway = sub.add_parser("gateway")
    gateway.add_argument("--workspace-url", default="http://127.0.0.1:8766")
    gateway.add_argument("--host", default="127.0.0.1")
    gateway.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "compose" and args.compose_command == "render":
        render_project_override(WorkshopConfig.load(args.projects), args.output)
        return 0
    if args.command == "workspace" and args.workspace_command == "serve":
        import uvicorn
        from ai_workshop.workspace.app import create_workspace_app

        app = create_workspace_app(WorkshopConfig.load(args.config))
        uvicorn.run(app, host=args.host, port=args.port)
        return 0
    if args.command == "gateway":
        from ai_workshop.gateway.client import WorkspaceClient
        from ai_workshop.gateway.server import build_mcp_server

        mcp = build_mcp_server(WorkspaceClient(args.workspace_url))
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            stateless_http=True,
            json_response=True,
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
