#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AI_WORKSHOP_TUNNEL_PROFILE:-ai-workshop}"
MCP_URL="${AI_WORKSHOP_MCP_URL:-http://127.0.0.1:8765/mcp}"
INITIALIZE=false

usage() {
  cat <<'EOF'
Usage:
  CONTROL_PLANE_API_KEY=... AI_WORKSHOP_TUNNEL_ID=tunnel_... bash scripts/tunnel.sh --init

Later runs:
  CONTROL_PLANE_API_KEY=... bash scripts/tunnel.sh

Options:
  --init          Initialize the named tunnel-client profile first.
  --profile NAME  Profile name (default: ai-workshop).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --init)
      INITIALIZE=true
      shift
      ;;
    --profile)
      PROFILE="$2"
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

if ! command -v tunnel-client >/dev/null 2>&1; then
  echo "tunnel-client is not installed." >&2
  echo "Download the latest release from Platform tunnel settings or https://github.com/openai/tunnel-client/releases/latest" >&2
  exit 127
fi

if [[ -z "${CONTROL_PLANE_API_KEY:-}" ]]; then
  echo "CONTROL_PLANE_API_KEY is required." >&2
  exit 64
fi

if [[ "$INITIALIZE" == true ]]; then
  if [[ -z "${AI_WORKSHOP_TUNNEL_ID:-}" ]]; then
    echo "AI_WORKSHOP_TUNNEL_ID is required with --init." >&2
    exit 64
  fi
  tunnel-client init     --profile "$PROFILE"     --tunnel-id "$AI_WORKSHOP_TUNNEL_ID"     --mcp-server-url "$MCP_URL"
fi

tunnel-client doctor --profile "$PROFILE" --explain
exec tunnel-client run --profile "$PROFILE"
