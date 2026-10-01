from ai_workshop.cli import build_parser

def test_cli_exposes_compose_workspace_and_gateway_commands():
    parser=build_parser()
    assert parser.parse_args(["compose","render","--projects","p.yaml","--output","o.yaml"]).command=="compose"
    assert parser.parse_args(["workspace","--projects","p.yaml"]).command=="workspace"
    args=parser.parse_args(["gateway","--workspace-url","http://127.0.0.1:8766"]); assert args.host=="127.0.0.1"

def test_cli_exposes_browser_service_and_gateway_browser_url():
    parser=build_parser()
    assert parser.parse_args(["browser","--profile","/tmp/p","--artifacts","/tmp/a"]).port==8767
    assert parser.parse_args(["gateway","--browser-url","http://127.0.0.1:8767"]).browser_url=="http://127.0.0.1:8767"
