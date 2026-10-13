#!/usr/bin/env bash
set -Eeuo pipefail

# Add the analysis worker and replace ONLY the MCP gateway.
# Does not recreate server-control, ingress, browser or orphan rootless-runtime.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/deploy/server/compose.yaml"
OVERLAY="$ROOT/deploy/server/compose.analysis.yaml"
ENV_FILE="$ROOT/deploy/server/.env"
MODE="${1:---preflight}"
BACKUP_BASE='/var/backups/ai-workshop'

if (( EUID != 0 )); then
  echo 'Run as root on the Ubuntu AI Workshop host.' >&2
  exit 1
fi
if [[ "$MODE" != '--preflight' && "$MODE" != '--apply' ]]; then
  echo 'Usage: bash scripts/deploy-ubuntu-analysis-worker.sh [--preflight|--apply]' >&2
  exit 2
fi
for command in docker git python3; do
  command -v "$command" >/dev/null || { echo "Missing: $command" >&2; exit 1; }
done
docker compose version >/dev/null
[[ -f "$BASE" && -f "$OVERLAY" && -f "$ENV_FILE" ]] || {
  echo 'Missing WAI Compose base/overlay or private deployment .env.' >&2
  exit 1
}
cd "$ROOT"

# Avoid accidental changes from an outdated checkout.
if ! git cat-file -e HEAD:deploy/server/compose.analysis.yaml 2>/dev/null; then
  echo 'The analysis overlay is not present in the current Git commit.' >&2
  exit 1
fi
gateway_container="$(docker compose --env-file "$ENV_FILE" -f "$BASE" ps -q gateway)"
[[ -n "$gateway_container" ]] || {
  echo 'An existing running gateway was not found; refusing an unverified fresh deployment.' >&2
  exit 1
}
old_gateway_image="$(docker inspect --format '{{.Image}}' "$gateway_container")"
[[ "$old_gateway_image" =~ ^sha256:[a-f0-9]{64}$ ]] || {
  echo 'Could not capture the current gateway image for rollback.' >&2
  exit 1
}
old_gateway_state="$(docker inspect --format '{{.State.Status}}' "$gateway_container")"
[[ "$old_gateway_state" == running ]] || {
  echo 'Gateway is not running; inspect the existing deployment first.' >&2
  exit 1
}

echo 'Current gateway image captured; no container changes have been made.'
echo "Current Git revision: $(git rev-parse --short HEAD)"
echo "Host Ghidra analyzer: /opt/ai-workshop/ghidra/support/analyzeHeadless"
if [[ -x /opt/ai-workshop/ghidra/support/analyzeHeadless ]]; then
  echo 'Ghidra: present'
else
  echo 'Ghidra: missing (install via scripts/install-ghidra-pinned.sh before --apply)'
fi
echo 'Existing services (including any orphaned legacy runtime):'
docker ps --format 'table {{.Names}}\t{{.Status}}'

# Validate the opt-in Compose model, without echoing its tokens to stdout.
(
  export AI_WORKSHOP_ANALYSIS_TOKEN='preflight-only-token-not-used-for-deployment'
  docker compose --env-file "$ENV_FILE" -f "$BASE" -f "$OVERLAY" config --quiet
)

# Ensure the updated gateway will see the SAME host data directory as the old
# gateway. This is critical when legacy deployments used custom bind mounts.
existing_storage="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/ai-workshop/storage"}}{{.Source}}{{end}}{{end}}' "$gateway_container")"
expected_storage="$(
  (
    export AI_WORKSHOP_ANALYSIS_TOKEN='preflight-only-token-not-used-for-deployment'
    docker compose --env-file "$ENV_FILE" -f "$BASE" -f "$OVERLAY" config --format json
  ) | python3 -c 'import json,sys; x=json.load(sys.stdin); v=[i["source"] for i in x["services"]["gateway"]["volumes"] if i["target"]=="/var/lib/ai-workshop/storage"]; print(v[0] if len(v)==1 else "")'
)"
if [[ -z "$existing_storage" || -z "$expected_storage" ||
      "$(readlink -f "$existing_storage")" != "$(readlink -f "$expected_storage")" ]]; then
  echo 'Existing gateway storage mount differs from the candidate rollout; refusing changes.' >&2
  exit 1
fi

if [[ "$MODE" == '--preflight' ]]; then
  echo 'Preflight succeeded. --apply will back up state and update only gateway + analysis-worker.'
  exit 0
fi

[[ -x /opt/ai-workshop/ghidra/support/analyzeHeadless ]] || {
  echo 'Ghidra is required before enabling the full worker.' >&2
  exit 1
}
command -v openssl >/dev/null || { echo 'Missing openssl' >&2; exit 1; }

# The private browser token and any existing config are preserved unchanged.
chmod 600 "$ENV_FILE"
if ! grep -q '^AI_WORKSHOP_ANALYSIS_TOKEN=' "$ENV_FILE"; then
  (umask 077; printf '\nAI_WORKSHOP_ANALYSIS_TOKEN=%s\n' "$(openssl rand -hex 32)" >> "$ENV_FILE")
  echo 'Generated a new analysis worker token in the existing private .env.'
else
  grep -q '^AI_WORKSHOP_ANALYSIS_TOKEN=.' "$ENV_FILE" || {
    echo 'Empty analysis token in .env; refusing to proceed.' >&2
    exit 1
  }
fi

umask 077
install -d -m 700 "$BACKUP_BASE"
backup_dir="$(mktemp -d "$BACKUP_BASE/analysis-rollout-XXXXXXXX")"
echo "Private rollback metadata: $backup_dir"
cp --preserve=mode,timestamps "$ENV_FILE" "$backup_dir/deploy.env"
git rev-parse HEAD > "$backup_dir/git-revision.txt"
docker ps -a > "$backup_dir/containers-before.txt"
docker volume ls > "$backup_dir/volumes-before.txt"
docker inspect "$gateway_container" > "$backup_dir/gateway-before.json"
docker compose --env-file "$ENV_FILE" -f "$BASE" config > "$backup_dir/base-compose-before.yaml"
docker compose --env-file "$ENV_FILE" -f "$BASE" -f "$OVERLAY" config > "$backup_dir/analysis-compose-after.yaml"
printf '%s\n' "$old_gateway_image" > "$backup_dir/previous-gateway-image.txt"

# Preserve actual contents of the existing gateway state volume before replacing
# the gateway; never detach or delete this or any other existing volume.
state_volume="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/state"}}{{.Name}}{{end}}{{end}}' "$gateway_container")"
if [[ ! "$state_volume" =~ ^[a-zA-Z0-9_.-]+$ ]]; then
  echo 'Could not identify a named state volume; aborting before updating services.' >&2
  exit 1
fi
echo "Creating a read-only backup of the existing gateway state volume: $state_volume"
docker run --rm --network none --read-only \
  --mount "type=volume,source=$state_volume,target=/from,readonly" \
  --mount "type=bind,source=$backup_dir,target=/to" \
  alpine:3.22 sh -c 'tar -C /from -czf /to/gateway-state.tar.gz .'
test -s "$backup_dir/gateway-state.tar.gz" || {
  echo 'State backup was not created; refusing deployment.' >&2
  exit 1
}

compose() {
  docker compose --env-file "$ENV_FILE" -f "$BASE" -f "$OVERLAY" "$@"
}
rollback_gateway() {
  echo 'Rolling back the gateway to its original image (other services untouched)...' >&2
  cat > "$backup_dir/gateway-rollback.yaml" <<EOF
services:
  gateway:
    image: $old_gateway_image
EOF
  docker compose --env-file "$ENV_FILE" \
    -f "$BASE" -f "$backup_dir/gateway-rollback.yaml" \
    up -d --no-deps --no-build gateway || true
}
wait_healthy() {
  local service="$1" container status index
  container="$(compose ps -q "$service")"
  [[ -n "$container" ]] || return 1
  for (( index=0; index<90; index++ )); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")"
    if [[ "$status" == healthy ]]; then return 0; fi
    if [[ "$status" == unhealthy || "$status" == exited || "$status" == dead ]]; then
      return 1
    fi
    sleep 2
  done
  return 1
}

echo 'Building only gateway + analysis-worker images...'
compose build gateway analysis-worker
echo 'Starting new worker; existing gateway is still running...'
compose up -d --no-deps --no-build analysis-worker
if ! wait_healthy analysis-worker; then
  echo 'Analysis worker did not become healthy; gateway was not modified.' >&2
  compose logs --tail=60 analysis-worker >&2
  exit 1
fi

echo 'Recreating only the gateway (not other WAI services)...'
if ! compose up -d --no-deps --no-build gateway; then
  rollback_gateway
  exit 1
fi
if ! wait_healthy gateway; then
  echo 'Updated gateway failed health check.' >&2
  rollback_gateway
  exit 1
fi
if ! python3 scripts/mcp-analysis-smoke.py; then
  echo 'MCP analysis tools were not found; rolling back gateway.' >&2
  rollback_gateway
  exit 1
fi

echo 'Rollout succeeded. Existing rootless-runtime and other services were left untouched.'
echo "Rollback information: $backup_dir"
compose ps gateway analysis-worker
