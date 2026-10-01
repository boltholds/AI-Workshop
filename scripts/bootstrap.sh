#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT=""
PROJECT_ID=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/bootstrap.sh --project /path/to/project [--project-id name]

On later runs, --project is optional when config/projects.local.yaml already exists.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="$2"
      shift 2
      ;;
    --project-id)
      PROJECT_ID="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

for command_name in docker uv; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name" >&2
    exit 127
  fi
done

cd "$ROOT"
uv sync

bootstrap_args=(--repo-root "$ROOT")
if [[ -n "$PROJECT" ]]; then
  bootstrap_args+=(--project "$PROJECT")
fi
if [[ -n "$PROJECT_ID" ]]; then
  bootstrap_args+=(--project-id "$PROJECT_ID")
fi
uv run python -m ai_workshop.bootstrap "${bootstrap_args[@]}"

while IFS='=' read -r key value || [[ -n "${key:-}" ]]; do
  case "$key" in
    AI_WORKSHOP_*)
      value="${value%
if [[ "$(uname -s)" == "Linux" ]]; then
  export AI_WORKSHOP_UID="${AI_WORKSHOP_UID:-$(id -u)}"
  export AI_WORKSHOP_GID="${AI_WORKSHOP_GID:-$(id -g)}"
fi

mkdir -p .workshop/logs .workshop/run

uv run ai-workshop compose render   --projects config/projects.local.yaml   --output .workshop/compose.projects.yaml

docker compose --env-file .env.local   -f compose.yaml   -f .workshop/compose.projects.yaml   up -d --build agent-workspace browser

service_registry_args=()
if [[ -f config/services.local.yaml ]]; then
  uv run ai-workshop services render     --projects config/projects.local.yaml     --services config/services.local.yaml     --compose-output .workshop/compose.services.yaml     --registry-output .workshop/service-registry.yaml

  docker compose --env-file .env.local     -p ai-workshop-services     -f .workshop/compose.services.yaml     up -d

  service_registry_args=(--service-registry .workshop/service-registry.yaml)
fi

recovery_args=()
if [[ -f config/recovery.local.yaml ]]; then
  recovery_args=(
    --recovery-config config/recovery.local.yaml
    --gateway-state .workshop/state
    --projects config/projects.local.yaml
  )
fi

gateway_pid_file=".workshop/run/gateway.pid"
gateway_log=".workshop/logs/gateway.log"

if [[ -f "$gateway_pid_file" ]]; then
  old_pid="$(cat "$gateway_pid_file" 2>/dev/null || true)"
  if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
    old_command="$(ps -p "$old_pid" -o command= 2>/dev/null || true)"
    if [[ "$old_command" == *"ai-workshop gateway"* ]]; then
      kill "$old_pid"
      for _ in $(seq 1 50); do
        if ! kill -0 "$old_pid" 2>/dev/null; then
          break
        fi
        sleep 0.1
      done
      if kill -0 "$old_pid" 2>/dev/null; then
        echo "Tracked gateway did not stop cleanly: PID $old_pid" >&2
        exit 1
      fi
    else
      echo "Ignoring stale gateway PID file; PID $old_pid is not AI Workshop gateway." >&2
    fi
  fi
  rm -f "$gateway_pid_file"
fi

nohup uv run ai-workshop gateway \
  --workspace-url http://127.0.0.1:8766 \
  --browser-url http://127.0.0.1:8767 \
  --browser-token "$AI_WORKSHOP_BROWSER_TOKEN" \
  "${service_registry_args[@]}" \
  "${recovery_args[@]}" \
  >"$gateway_log" 2>&1 &
echo "$!" > "$gateway_pid_file"

for _ in $(seq 1 30); do
  if uv run ai-workshop doctor       --projects config/projects.local.yaml       --workspace-url http://127.0.0.1:8766       --gateway-host 127.0.0.1       --gateway-port 8765       --browser-url http://127.0.0.1:8767 >/dev/null; then
    echo "AI Workshop is ready."
    echo "MCP endpoint: http://127.0.0.1:8765/mcp"
    echo "Gateway log: $ROOT/$gateway_log"
    exit 0
  fi
  sleep 1
done

echo "AI Workshop did not become healthy. Gateway log:" >&2
tail -n 100 "$gateway_log" 2>/dev/null || true
exit 1
\r'}"
      export "$key=$value"
      ;;
  esac
done < "$ROOT/.env.local"

if [[ "$(uname -s)" == "Linux" ]]; then
  export AI_WORKSHOP_UID="${AI_WORKSHOP_UID:-$(id -u)}"
  export AI_WORKSHOP_GID="${AI_WORKSHOP_GID:-$(id -g)}"
fi

mkdir -p .workshop/logs .workshop/run

uv run ai-workshop compose render   --projects config/projects.local.yaml   --output .workshop/compose.projects.yaml

docker compose --env-file .env.local   -f compose.yaml   -f .workshop/compose.projects.yaml   up -d --build agent-workspace browser

service_registry_args=()
if [[ -f config/services.local.yaml ]]; then
  uv run ai-workshop services render     --projects config/projects.local.yaml     --services config/services.local.yaml     --compose-output .workshop/compose.services.yaml     --registry-output .workshop/service-registry.yaml

  docker compose --env-file .env.local     -p ai-workshop-services     -f .workshop/compose.services.yaml     up -d

  service_registry_args=(--service-registry .workshop/service-registry.yaml)
fi

recovery_args=()
if [[ -f config/recovery.local.yaml ]]; then
  recovery_args=(
    --recovery-config config/recovery.local.yaml
    --gateway-state .workshop/state
    --projects config/projects.local.yaml
  )
fi

gateway_pid_file=".workshop/run/gateway.pid"
gateway_log=".workshop/logs/gateway.log"
gateway_running=false
if [[ -f "$gateway_pid_file" ]]; then
  old_pid="$(cat "$gateway_pid_file" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    gateway_running=true
  fi
fi

if [[ "$gateway_running" == false ]]; then
  nohup uv run ai-workshop gateway     --workspace-url http://127.0.0.1:8766     --browser-url http://127.0.0.1:8767     --browser-token "$AI_WORKSHOP_BROWSER_TOKEN"     "${service_registry_args[@]}"     "${recovery_args[@]}"     >"$gateway_log" 2>&1 &
  echo "$!" > "$gateway_pid_file"
fi

for _ in $(seq 1 30); do
  if uv run ai-workshop doctor       --projects config/projects.local.yaml       --workspace-url http://127.0.0.1:8766       --gateway-host 127.0.0.1       --gateway-port 8765       --browser-url http://127.0.0.1:8767 >/dev/null; then
    echo "AI Workshop is ready."
    echo "MCP endpoint: http://127.0.0.1:8765/mcp"
    echo "Gateway log: $ROOT/$gateway_log"
    exit 0
  fi
  sleep 1
done

echo "AI Workshop did not become healthy. Gateway log:" >&2
tail -n 100 "$gateway_log" 2>/dev/null || true
exit 1
