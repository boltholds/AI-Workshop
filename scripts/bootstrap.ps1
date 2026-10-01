param(
    [string]$Project,
    [string]$ProjectId
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

foreach ($CommandName in @("docker", "uv")) {
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $CommandName"
    }
}

& uv sync
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }

$BootstrapInitArgs = @("--repo-root", $Root)
if ($Project) {
    $BootstrapInitArgs += @("--project", $Project)
}
if ($ProjectId) {
    $BootstrapInitArgs += @("--project-id", $ProjectId)
}
& uv run python -m ai_workshop.bootstrap @BootstrapInitArgs
if ($LASTEXITCODE -ne 0) { throw "bootstrap initialization failed" }

Get-Content (Join-Path $Root ".env.local") | ForEach-Object {
    $Line = $_.Trim()
    if ($Line -and -not $Line.StartsWith("#") -and $Line.Contains("=")) {
        $Parts = $Line.Split("=", 2)
        [Environment]::SetEnvironmentVariable(
            $Parts[0].Trim(),
            $Parts[1].Trim(),
            "Process"
        )
    }
}

New-Item -ItemType Directory -Force -Path ".workshop\logs" | Out-Null
New-Item -ItemType Directory -Force -Path ".workshop\run" | Out-Null

$ComposeRenderArgs = @(
    "run", "ai-workshop", "compose", "render",
    "--projects", "config/projects.local.yaml",
    "--output", ".workshop/compose.projects.yaml"
)
& uv @ComposeRenderArgs
if ($LASTEXITCODE -ne 0) { throw "project compose render failed" }

$DockerBaseArgs = @(
    "compose", "--env-file", ".env.local",
    "-f", "compose.yaml",
    "-f", ".workshop/compose.projects.yaml",
    "up", "-d", "--build", "agent-workspace", "browser"
)
& docker @DockerBaseArgs
if ($LASTEXITCODE -ne 0) { throw "Workshop containers failed to start" }

$GatewayArgs = @(
    "run", "ai-workshop", "gateway",
    "--workspace-url", "http://127.0.0.1:8766",
    "--browser-url", "http://127.0.0.1:8767",
    "--browser-token", $env:AI_WORKSHOP_BROWSER_TOKEN
)

if (Test-Path "config/services.local.yaml") {
    $ServiceRenderArgs = @(
        "run", "ai-workshop", "services", "render",
        "--projects", "config/projects.local.yaml",
        "--services", "config/services.local.yaml",
        "--compose-output", ".workshop/compose.services.yaml",
        "--registry-output", ".workshop/service-registry.yaml"
    )
    & uv @ServiceRenderArgs
    if ($LASTEXITCODE -ne 0) { throw "service compose render failed" }

    $ServiceComposeArgs = @(
        "compose", "--env-file", ".env.local",
        "-p", "ai-workshop-services",
        "-f", ".workshop/compose.services.yaml",
        "up", "-d"
    )
    & docker @ServiceComposeArgs
    if ($LASTEXITCODE -ne 0) { throw "Workshop services failed to start" }

    $GatewayArgs += @("--service-registry", ".workshop/service-registry.yaml")
}

if (Test-Path "config/recovery.local.yaml") {
    $GatewayArgs += @(
        "--recovery-config", "config/recovery.local.yaml",
        "--gateway-state", ".workshop/state",
        "--projects", "config/projects.local.yaml"
    )
}

$PidPath = ".workshop\run\gateway.pid"
if (Test-Path $PidPath) {
    $ExistingPid = Get-Content $PidPath -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ExistingPid -and $ExistingPid -match "^[0-9]+$") {
        $ExistingProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $ExistingPid" -ErrorAction SilentlyContinue
        if ($ExistingProcess -and $ExistingProcess.CommandLine -match "ai-workshop\s+gateway") {
            Stop-Process -Id ([int]$ExistingPid) -Force
            Wait-Process -Id ([int]$ExistingPid) -Timeout 5 -ErrorAction SilentlyContinue
        }
        elseif ($ExistingProcess) {
            Write-Warning "Ignoring stale gateway PID file; PID $ExistingPid is not AI Workshop gateway."
        }
    }
    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
}

# Starts: uv run ai-workshop gateway
$Stdout = Join-Path $Root ".workshop\logs\gateway.out.log"
$Stderr = Join-Path $Root ".workshop\logs\gateway.err.log"
$Process = Start-Process -FilePath "uv" -ArgumentList $GatewayArgs -WorkingDirectory $Root -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr -WindowStyle Hidden -PassThru
Set-Content -Path $PidPath -Value $Process.Id -Encoding ascii

for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    # Health: uv run ai-workshop doctor
    $DoctorArgs = @(
        "run", "ai-workshop", "doctor",
        "--projects", "config/projects.local.yaml",
        "--workspace-url", "http://127.0.0.1:8766",
        "--gateway-host", "127.0.0.1",
        "--gateway-port", "8765",
        "--browser-url", "http://127.0.0.1:8767"
    )
    & uv @DoctorArgs *> $null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "AI Workshop is ready."
        Write-Host "MCP endpoint: http://127.0.0.1:8765/mcp"
        Write-Host "Gateway logs: $Root\.workshop\logs"
        exit 0
    }
    Start-Sleep -Seconds 1
}

throw "AI Workshop did not become healthy. Check .workshop\logs."
