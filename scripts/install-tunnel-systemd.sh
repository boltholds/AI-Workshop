#!/usr/bin/env bash
set -Eeuo pipefail

# Install a persistent systemd unit without exposing the API key in process args.
if (( EUID != 0 )); then
  echo 'Run as root on the Ubuntu WAI host.' >&2
  exit 1
fi
PROFILE='/root/.config/tunnel-client/ai-workshop-server.yaml'
ENV_DIR='/etc/ai-workshop'
ENV_FILE="$ENV_DIR/tunnel.env"
UNIT='/etc/systemd/system/ai-workshop-tunnel.service'

[[ -f "$PROFILE" ]] || { echo "Missing tunnel profile: $PROFILE" >&2; exit 1; }
TUNNEL_BIN="$(command -v tunnel-client || true)"
[[ -n "$TUNNEL_BIN" && -x "$TUNNEL_BIN" ]] || {
  echo 'tunnel-client executable was not found in root PATH.' >&2
  exit 1
}
TUNNEL_BIN="$(readlink -f "$TUNNEL_BIN")"
install -d -m 700 "$ENV_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  KEY="${CONTROL_PLANE_API_KEY:-}"
  if [[ -z "$KEY" ]]; then
    if [[ ! -t 0 ]]; then
      echo 'No API key is configured; run interactively or set CONTROL_PLANE_API_KEY.' >&2
      exit 1
    fi
    read -rsp 'OpenAI tunnel runtime key: ' KEY
    echo
  fi
  if [[ -z "$KEY" || "$KEY" == *$'\n'* || "$KEY" == *$'\r'* || "$KEY" == *' '* ]]; then
    echo 'Invalid or empty API key.' >&2
    exit 1
  fi
  (umask 077; printf 'CONTROL_PLANE_API_KEY=%s\n' "$KEY" > "$ENV_FILE")
  unset KEY
fi
chmod 600 "$ENV_FILE"

if [[ ! -e "$UNIT" ]]; then
  cat > "$UNIT" <<EOF
[Unit]
Description=AI Workshop OpenAI MCP Tunnel
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=simple
User=root
Environment=HOME=/root
EnvironmentFile=$ENV_FILE
WorkingDirectory=/opt/ai-workshop
ExecStart=$TUNNEL_BIN run --profile ai-workshop-server
Restart=always
RestartSec=5
StartLimitIntervalSec=0
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
else
  echo "Existing systemd unit preserved: $UNIT"
fi

systemctl daemon-reload
systemctl enable ai-workshop-tunnel.service >/dev/null

if systemctl is-active --quiet ai-workshop-tunnel.service; then
  echo 'Tunnel is already running as a systemd service.'
  systemctl --no-pager --full status ai-workshop-tunnel.service | head -n 14
  exit 0
fi

# A manually started tunnel commonly holds localhost:8080.
if command -v ss >/dev/null && ss -H -lnt '( sport = :8080 )' | grep -q .; then
  echo 'Another process already listens on port 8080.' >&2
  echo 'Stop the foreground tunnel (Ctrl+C), then run:' >&2
  echo '  systemctl start ai-workshop-tunnel' >&2
  echo 'The service is already enabled for future reboots.' >&2
  exit 0
fi

systemctl start ai-workshop-tunnel.service
systemctl is-active --quiet ai-workshop-tunnel.service || {
  journalctl -u ai-workshop-tunnel -n 25 --no-pager >&2
  exit 1
}
echo 'Tunnel is active and enabled for boot.'
systemctl --no-pager --full status ai-workshop-tunnel.service | head -n 14
