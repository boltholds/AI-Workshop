from ai_workshop.cli import build_parser


def test_cli_exposes_compose_workspace_and_gateway_commands():
    parser = build_parser()
    assert parser.parse_args(["compose", "render", "--projects", "p.yaml", "--output", "o.yaml"]).command == "compose"
    assert parser.parse_args(["workspace", "--projects", "p.yaml"]).command == "workspace"
    args = parser.parse_args(["gateway", "--workspace-url", "http://127.0.0.1:8766"])
    assert args.command == "gateway"
    assert args.host == "127.0.0.1"
    assert args.port == 8765
