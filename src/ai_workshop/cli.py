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

    services = commands.add_parser("services")
    services_commands = services.add_subparsers(dest="services_command", required=True)
    services_render = services_commands.add_parser("render")
    services_render.add_argument("--projects", type=Path, required=True)
    services_render.add_argument("--services", type=Path, required=True)
    services_render.add_argument("--compose-output", type=Path, required=True)
    services_render.add_argument("--registry-output", type=Path, required=True)

    workspace = commands.add_parser("workspace")
    workspace.add_argument("--projects", type=Path, required=True)
    workspace.add_argument("--host", default="0.0.0.0")
    workspace.add_argument("--port", type=int, default=8766)
    workspace.add_argument("--token", default=os.getenv("AI_WORKSHOP_WORKSPACE_TOKEN"))
    workspace.add_argument(
        "--state",
        type=Path,
        default=Path(os.environ["AI_WORKSHOP_STATE_ROOT"])
        if os.getenv("AI_WORKSHOP_STATE_ROOT")
        else None,
    )

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
    gateway.add_argument(
        "--recovery-config",
        type=Path,
        default=Path(os.environ["AI_WORKSHOP_RECOVERY_CONFIG"])
        if os.getenv("AI_WORKSHOP_RECOVERY_CONFIG")
        else None,
    )
    gateway.add_argument(
        "--gateway-state",
        type=Path,
        default=Path(os.getenv("AI_WORKSHOP_GATEWAY_STATE_ROOT", ".workshop/state")),
    )
    gateway.add_argument(
        "--projects",
        type=Path,
        default=Path(os.getenv("AI_WORKSHOP_PROJECTS", "config/projects.local.yaml")),
    )

    commands.add_parser("run-host")

    server = commands.add_parser("server")
    server_commands = server.add_subparsers(dest="server_command", required=True)

    server_serve = server_commands.add_parser("serve")
    server_serve.add_argument("--config", type=Path, required=True)
    server_serve.add_argument("--state-root", type=Path, default=Path("/state"))
    server_serve.add_argument("--host", default="0.0.0.0")
    server_serve.add_argument("--port", type=int, default=8770)

    server_doctor = server_commands.add_parser("doctor")
    server_doctor.add_argument("--config", type=Path, required=True)
    server_doctor.add_argument("--state-root", type=Path, default=Path("/state"))

    browser = commands.add_parser("browser")
    browser.add_argument("--profile", type=Path, default=Path("/data/browser-profile"))
    browser.add_argument("--artifacts", type=Path, default=Path("/data/artifacts"))
    browser.add_argument("--host", default="0.0.0.0")
    browser.add_argument("--port", type=int, default=8767)
    browser.add_argument("--token", default=os.getenv("AI_WORKSHOP_BROWSER_TOKEN"))

    doctor = commands.add_parser("doctor")
    doctor.add_argument(
        "--projects",
        type=Path,
        default=Path(os.getenv("AI_WORKSHOP_PROJECTS", "config/projects.local.yaml")),
    )
    doctor.add_argument(
        "--workspace-url",
        default=os.getenv("AI_WORKSHOP_WORKSPACE_URL", "http://127.0.0.1:8766"),
    )
    doctor.add_argument(
        "--gateway-host",
        default=os.getenv("AI_WORKSHOP_MCP_HOST", "127.0.0.1"),
    )
    doctor.add_argument(
        "--gateway-port",
        type=int,
        default=int(os.getenv("AI_WORKSHOP_MCP_PORT", "8765")),
    )
    doctor.add_argument("--browser-url", default=os.getenv("AI_WORKSHOP_BROWSER_URL"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "compose" and args.compose_command == "render":
        config = WorkshopConfig.load(args.projects)
        render_project_override(config, args.output)
        return 0
    if args.command == "services" and args.services_command == "render":
        from ai_workshop.services.config import ServiceConfig
        from ai_workshop.services.render import render_service_override

        projects = WorkshopConfig.load(args.projects)
        services_config = ServiceConfig.load(args.services)
        render_service_override(
            services_config,
            projects,
            compose_path=args.compose_output,
            registry_path=args.registry_output,
        )
        return 0
    if args.command == "workspace":
        import uvicorn
        from ai_workshop.workspace.app import create_app

        if not args.token:
            raise SystemExit("AI_WORKSHOP_WORKSPACE_TOKEN or --token is required")
        config = WorkshopConfig.load(args.projects)
        uvicorn.run(
            create_app(
                config,
                workspace_token=args.token,
                state_root=args.state,
            ),
            host=args.host,
            port=args.port,
        )
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

        state_snapshot_service = None
        reset_service = None
        if args.recovery_config is not None:
            from ai_workshop.recovery.config import (
                RecoveryConfig,
                build_recovery_runtime,
            )

            recovery_runtime = build_recovery_runtime(
                RecoveryConfig.load(args.recovery_config),
                state_root=args.gateway_state,
                projects=WorkshopConfig.load(args.projects),
            )
            state_snapshot_service = recovery_runtime.state_service
            reset_service = recovery_runtime.reset_service

        run_gateway(
            args.workspace_url,
            token=args.workspace_token,
            host=args.host,
            port=args.port,
            browser_url=args.browser_url,
            browser_token=args.browser_token,
            service_controller=service_controller,
            state_snapshot_service=state_snapshot_service,
            reset_service=reset_service,
        )
        return 0
    if args.command == "run-host":
        import threading

        threading.Event().wait()
        return 0

    if args.command == "server":
        import json
        from dataclasses import asdict

        from ai_workshop.server.config import ServerModeConfig

        config = ServerModeConfig.load(args.config)
        if args.server_command == "serve":
            import uvicorn
            from ai_workshop.server.app import create_server_app

            uvicorn.run(
                create_server_app(
                    config,
                    state_root=args.state_root,
                ),
                host=args.host,
                port=args.port,
            )
            return 0

        if args.server_command == "doctor":
            from ai_workshop.server.doctor import build_server_doctor

            report = build_server_doctor(config).run()
            print(json.dumps(
                {
                    "healthy": report.healthy,
                    "exit_code": report.exit_code,
                    "checks": [asdict(item) for item in report.checks],
                },
                indent=2,
                sort_keys=True,
            ))
            return report.exit_code

    if args.command == "doctor":
        import json
        from dataclasses import asdict
        from ai_workshop.doctor import (
            CheckSpec,
            Doctor,
            docker_check,
            http_health_check,
            project_paths_check,
            tcp_check,
        )

        checks = []
        try:
            project_config = WorkshopConfig.load(args.projects)
            checks.append(project_paths_check(project_config))
        except Exception:
            checks.append(CheckSpec(
                "projects",
                required=True,
                probe=lambda: (False, "project configuration is unavailable"),
                remediation="create or fix the projects configuration",
            ))
        checks.append(docker_check())
        checks.append(http_health_check(
            "workspace",
            args.workspace_url,
            required=True,
            remediation="start agent-workspace",
        ))
        checks.append(tcp_check(
            "gateway",
            args.gateway_host,
            args.gateway_port,
            required=True,
            remediation="start ai-workshop gateway",
        ))
        if args.browser_url:
            checks.append(http_health_check(
                "browser",
                args.browser_url,
                required=False,
                remediation="start browser service",
            ))
        report = Doctor(checks).run()
        print(json.dumps(
            {
                "healthy": report.healthy,
                "exit_code": report.exit_code,
                "checks": [asdict(item) for item in report.checks],
            },
            indent=2,
            sort_keys=True,
        ))
        return report.exit_code
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
