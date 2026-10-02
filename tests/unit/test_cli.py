from ai_workshop.cli import build_parser


def test_cli_exposes_compose_workspace_and_gateway_commands():
    parser = build_parser()
    assert parser.parse_args(["compose", "render", "--projects", "p.yaml", "--output", "o.yaml"]).command == "compose"
    assert parser.parse_args(["workspace", "--projects", "p.yaml"]).command == "workspace"
    args = parser.parse_args(["gateway", "--workspace-url", "http://127.0.0.1:8766"])
    assert args.command == "gateway"
    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_cli_exposes_browser_and_browser_gateway_options():
    parser = build_parser()
    browser = parser.parse_args(["browser", "--token", "secret"])
    assert browser.command == "browser"
    assert browser.port == 8767
    gateway = parser.parse_args([
        "gateway", "--workspace-token", "workspace",
        "--browser-url", "http://127.0.0.1:8767",
        "--browser-token", "browser",
    ])
    assert gateway.browser_url == "http://127.0.0.1:8767"
    assert gateway.browser_token == "browser"


def test_gateway_accepts_optional_service_registry():
    parser = build_parser()
    args = parser.parse_args([
        "gateway",
        "--workspace-url", "http://127.0.0.1:8766",
        "--service-registry", ".workshop/service-registry.yaml",
    ])
    assert str(args.service_registry) == ".workshop/service-registry.yaml"


def test_cli_exposes_service_profile_rendering():
    parser = build_parser()
    args = parser.parse_args([
        "services", "render",
        "--projects", "config/projects.local.yaml",
        "--services", "config/services.local.yaml",
        "--compose-output", ".workshop/compose.services.yaml",
        "--registry-output", ".workshop/service-registry.yaml",
    ])
    assert args.command == "services"
    assert args.services_command == "render"


def test_cli_exposes_server_serve_and_doctor_commands():
    parser = build_parser()

    serve = parser.parse_args([
        "server", "serve",
        "--config", "config/server.yaml",
    ])
    assert serve.command == "server"
    assert serve.server_command == "serve"

    doctor = parser.parse_args([
        "server", "doctor",
        "--config", "config/server.yaml",
    ])
    assert doctor.command == "server"
    assert doctor.server_command == "doctor"


def test_cli_accepts_run_host_command():
    from ai_workshop.cli import build_parser

    args = build_parser().parse_args(["run-host"])

    assert args.command == "run-host"
