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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "compose" and args.compose_command == "render":
        render_project_override(WorkshopConfig.load(args.projects), args.output)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
