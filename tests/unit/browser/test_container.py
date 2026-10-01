from pathlib import Path

from ai_workshop.cli import build_parser

ROOT = Path(__file__).parents[3]


def test_browser_container_is_non_root_and_has_chromium_ffmpeg() -> None:
    dockerfile = (ROOT / "browser/Dockerfile").read_text(encoding="utf-8")
    assert "chromium" in dockerfile
    assert "ffmpeg" in dockerfile
    assert "USER workshop" in dockerfile


def test_cli_has_browser_serve_command() -> None:
    args = build_parser().parse_args(["browser", "serve", "--profile", "/data/profile"])
    assert args.command == "browser"
    assert args.browser_command == "serve"
    assert str(args.profile) == "/data/profile"
