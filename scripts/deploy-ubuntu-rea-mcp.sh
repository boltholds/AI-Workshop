#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:---preflight}"
[[ "$MODE" == --preflight || "$MODE" == --apply ]] || { echo 'Usage: --preflight|--apply' >&2; exit 2; }
cd "$ROOT"
ENV_FILE="$ROOT/deploy/server/.env"
[[ -f "$ENV_FILE" ]] || { echo 'Existing deploy/server/.env is required.' >&2; exit 1; }
for cmd in docker python3 openssl; do command -v "$cmd" >/dev/null; done
base=(docker compose --env-file "$ENV_FILE" -f deploy/server/compose.yaml -f deploy/server/compose.analysis.yaml)
full=("${base[@]}" -f deploy/server/compose.rea.yaml)
gateway="$("${base[@]}" ps -q gateway)"
[[ -n "$gateway" ]] || { echo 'Existing WAI gateway is required.' >&2; exit 1; }
umask 077
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
"${base[@]}" config --format json > "$staging/previous.json"
docker inspect "$gateway" > "$staging/gateway.json"
old_image="$(docker inspect --format '{{.Image}}' "$gateway")"
[[ "$old_image" =~ ^sha256:[a-f0-9]{64}$ ]] || exit 1
docker image inspect "$old_image" > "$staging/image.json"
smoke_url="$(python3 scripts/rea-rollout-config.py "$staging/previous.json" "$staging/gateway.json" "$staging/image.json" "$staging/rollback.json")"
project_name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$staging/previous.json")"
existing_rea="$(docker ps -aq --filter "label=com.docker.compose.project=$project_name" --filter label=com.docker.compose.service=rea-mcp)"
[[ -z "$existing_rea" ]] || { echo 'REA container already exists; this helper performs first installation only.' >&2; exit 1; }
( export AI_WORKSHOP_REA_TOKEN=preflight-placeholder; "${full[@]}" config --format json ) > "$staging/candidate.json"
python3 - "$staging/candidate.json" <<'PY'
import json, pathlib, sys
cfg=json.load(open(sys.argv[1]))
for volume in cfg['services']['rea-mcp']['volumes']:
    if volume['type']=='bind' and not pathlib.Path(volume['source']).is_dir():
        raise SystemExit('Required REA bind directory missing: '+volume['source'])
PY
if [[ "$MODE" == --preflight ]]; then
  echo "Preflight passed. Gateway smoke endpoint: $smoke_url"
  echo 'Apply installs REA 6.4.0 and updates only the gateway; other services remain running.'
  exit 0
fi
chmod 600 "$ENV_FILE"
if ! grep -q '^AI_WORKSHOP_REA_TOKEN=' "$ENV_FILE"; then
  (umask 077; printf '\nAI_WORKSHOP_REA_TOKEN=%s\n' "$(openssl rand -hex 32)" >> "$ENV_FILE")
fi
"${full[@]}" config --quiet
backup="$(mktemp -d "$ROOT/.workshop-rea-rollback.XXXXXXXX")"
cp "$staging/gateway.json" "$backup/gateway-before.json"
cp "$staging/rollback.json" "$backup/compose-before.json"
rollback_image="ai-workshop-gateway-rollback:${old_image#sha256:}"
docker image tag "$old_image" "$rollback_image"
[[ "$(docker image inspect --format '{{.Id}}' "$rollback_image")" == "$old_image" ]] || exit 1
rollback() {
  echo "Restoring verified prior gateway config and image; private metadata: $backup" >&2
  if ! docker compose -f "$backup/compose-before.json" up -d --no-deps --no-build --pull never --wait --wait-timeout 120 gateway; then
    echo "Rollback failed; leaving REA and private recovery metadata intact: $backup" >&2
    return 1
  fi
  "${full[@]}" rm -sf rea-mcp
}
"${full[@]}" build rea-mcp gateway
if ! "${full[@]}" up -d --no-deps --no-build --wait --wait-timeout 120 rea-mcp; then
  "${full[@]}" rm -sf rea-mcp
  exit 1
fi
trap 'rollback; exit 130' INT TERM
if ! "${full[@]}" up -d --no-deps --no-build --wait --wait-timeout 120 gateway; then
  rollback; exit 1
fi
if ! python3 scripts/mcp-rea-smoke.py --url "$smoke_url"; then
  "${full[@]}" logs --no-color --tail 200 gateway rea-mcp > "$backup/rollout-failure.log" 2>&1 || true
  rollback; exit 1
fi
trap - INT TERM
echo "REA MCP rollout succeeded. Rollback metadata: $backup"
"${full[@]}" ps gateway rea-mcp
