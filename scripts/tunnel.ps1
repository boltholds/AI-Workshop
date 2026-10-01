param(
    [switch]$Init,
    [string]$Profile = $(if ($env:AI_WORKSHOP_TUNNEL_PROFILE) { $env:AI_WORKSHOP_TUNNEL_PROFILE } else { "ai-workshop" })
)

$ErrorActionPreference = "Stop"
$McpUrl = if ($env:AI_WORKSHOP_MCP_URL) { $env:AI_WORKSHOP_MCP_URL } else { "http://127.0.0.1:8765/mcp" }

if (-not (Get-Command "tunnel-client" -ErrorAction SilentlyContinue)) {
    throw "tunnel-client is not installed. Download the latest release from Platform tunnel settings or https://github.com/openai/tunnel-client/releases/latest"
}
if (-not $env:CONTROL_PLANE_API_KEY) {
    throw "CONTROL_PLANE_API_KEY is required."
}

if ($Init) {
    if (-not $env:AI_WORKSHOP_TUNNEL_ID) {
        throw "AI_WORKSHOP_TUNNEL_ID is required with -Init."
    }
    $InitArgs = @(
        "init",
        "--profile", $Profile,
        "--tunnel-id", $env:AI_WORKSHOP_TUNNEL_ID,
        "--mcp-server-url", $McpUrl
    )
    & tunnel-client @InitArgs
    if ($LASTEXITCODE -ne 0) { throw "tunnel-client init failed" }
}

$DoctorArgs = @("doctor", "--profile", $Profile, "--explain")
& tunnel-client @DoctorArgs
if ($LASTEXITCODE -ne 0) { throw "tunnel-client doctor failed" }

$RunArgs = @("run", "--profile", $Profile)
& tunnel-client @RunArgs
exit $LASTEXITCODE
