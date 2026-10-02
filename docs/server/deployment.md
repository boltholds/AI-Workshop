# Autonomous Server Mode deployment

Server Mode is packaged in `deploy/server/compose.yaml`. This guide starts from a clean Linux host and takes the deployment through bootstrap, startup, validation, persistence checks, LAN/offline configuration, upgrade, backup, and shutdown.

The required outer services are:

- `rootless-runtime` — the nested Docker runtime used for AgentRuns, MCP runtimes, and project services;
- `server-control` — the autonomous Server Mode control plane;
- `browser` — the persistent Chromium/browser diagnostics runtime;
- `ingress` — the only outer service allowed to publish a host port.

The host Docker socket is never mounted into AI Workshop. The nested runtime socket is shared only between `rootless-runtime` and `server-control`.

## 1. Host requirements

The recommended target is a recent 64-bit Linux distribution with systemd and cgroup v2. Ubuntu 24.04 LTS or a current Debian release are good defaults.

Install:

- Git;
- Docker Engine;
- Docker Compose v2 plugin;
- Python 3.12 or newer;
- `uv` for the bootstrap CLI/test environment.

Check the host:

```bash
git --version
docker --version
docker compose version
python3 --version
uv --version
```

Your user must be able to run Docker commands. Verify before continuing:

```bash
docker info
```

Server Mode runs a rootless nested Docker daemon. On hardened hosts, unprivileged user namespaces must be available. These checks are useful:

```bash
sysctl kernel.unprivileged_userns_clone 2>/dev/null || true
sysctl kernel.apparmor_restrict_unprivileged_userns 2>/dev/null || true
sysctl user.max_user_namespaces 2>/dev/null || true
```

On hosts where these values are restricted, configure the host according to the distribution's rootless-container guidance before starting AI Workshop. Do not disable security controls blindly on a production host.

## 2. Clone AI Workshop

Choose a persistent installation directory:

```bash
sudo mkdir -p /opt/ai-workshop
sudo chown "$USER":"$USER" /opt/ai-workshop
git clone https://github.com/boltholds/AI-Workshop.git /opt/ai-workshop
cd /opt/ai-workshop
```

For a pinned deployment, check out the release tag or exact commit you intend to operate rather than following `main` automatically.

## 3. Install the host-side bootstrap environment

Create the Python environment:

```bash
cd /opt/ai-workshop
uv sync
```

Confirm the CLI imports correctly:

```bash
uv run ai-workshop --help
```

The autonomous services themselves run in containers; this host environment is used for bootstrap, validation, upgrades, and operator commands.

## 4. Choose the persistent bootstrap location

By default the bootstrap helper creates:

```text
.workshop-server/
├── storage/
│   ├── projects/
│   └── runs/
├── state/
│   ├── bootstrap.json
│   └── secrets/
│       ├── browser-token
│       ├── workspace-token
│       └── service-token
└── ca/
    ├── ca-key.pem
    ├── ca-cert.pem
    └── certificates/
```

For a production server, use explicit absolute paths instead of relying on the repository working directory:

```bash
export AI_WORKSHOP_STORAGE_ROOT=/var/lib/ai-workshop/storage
export AI_WORKSHOP_STATE_ROOT=/var/lib/ai-workshop/state
export AI_WORKSHOP_CA_ROOT=/var/lib/ai-workshop/ca
export AI_WORKSHOP_FIRST_ADMIN_ID=admin
```

Create the parent directory with restricted ownership if necessary:

```bash
sudo mkdir -p /var/lib/ai-workshop
sudo chown "$USER":"$USER" /var/lib/ai-workshop
chmod 700 /var/lib/ai-workshop
```

Do not place these directories inside a project checkout or a directory exposed to AgentRuns.

## 5. Bootstrap Server Mode

Run:

```bash
cd /opt/ai-workshop

AI_WORKSHOP_STORAGE_ROOT=/var/lib/ai-workshop/storage \
AI_WORKSHOP_STATE_ROOT=/var/lib/ai-workshop/state \
AI_WORKSHOP_CA_ROOT=/var/lib/ai-workshop/ca \
AI_WORKSHOP_FIRST_ADMIN_ID=admin \
uv run ./scripts/server-bootstrap.sh
```

If your shell does not execute the script directly:

```bash
uv run sh ./scripts/server-bootstrap.sh
```

Bootstrap creates Workshop-owned storage, the local certificate authority, generated service tokens, and the first bootstrap-state record.

It is intentionally idempotent. Re-running the same command:

- does not rotate the local CA;
- does not rotate an existing browser/workspace/service token;
- completes missing state after a partially failed first run;
- rejects a different first-admin identity against an existing bootstrap state.

Never delete the CA key or token files just to "retry" bootstrap. Fix the underlying error and run bootstrap again.

## 6. Verify bootstrap state

Check that the expected files exist:

```bash
test -f /var/lib/ai-workshop/state/bootstrap.json
test -f /var/lib/ai-workshop/state/secrets/browser-token
test -f /var/lib/ai-workshop/state/secrets/workspace-token
test -f /var/lib/ai-workshop/state/secrets/service-token
test -f /var/lib/ai-workshop/ca/ca-cert.pem
test -f /var/lib/ai-workshop/ca/ca-key.pem
```

Check permissions:

```bash
ls -la /var/lib/ai-workshop/state/secrets
ls -la /var/lib/ai-workshop/ca
```

The generated token files and CA private key are private operator state. Do not commit them, copy them into a project repository, or expose them through MCP/file tools.

## 7. Create the deployment environment file

Start from the example:

```bash
cd /opt/ai-workshop
cp deploy/server/.env.example deploy/server/.env
```

Populate the browser token generated by bootstrap:

```bash
BROWSER_TOKEN="$(cat /var/lib/ai-workshop/state/secrets/browser-token)"

cat > deploy/server/.env <<EOF
AI_WORKSHOP_HTTPS_BIND=127.0.0.1:8443
AI_WORKSHOP_BROWSER_TOKEN=$BROWSER_TOKEN
EOF

chmod 600 deploy/server/.env
unset BROWSER_TOKEN
```

For the initial deployment, keep `AI_WORKSHOP_HTTPS_BIND` on loopback. Do not expose it to the LAN or Internet until authentication/TLS routing for the intended hostname has been configured and verified.

The current Compose file consumes `AI_WORKSHOP_BROWSER_TOKEN` through Compose interpolation. Because `deploy/server/.env` sits next to the Compose file, supported Compose implementations load it as the project `.env` automatically when no explicit `--env-file` is supplied. Bootstrap-generated token files are not automatically imported into Compose, so creating this `.env` file is still required.

If your Compose implementation does not load the adjacent project `.env`, export it into the shell explicitly before running Compose:

```bash
set -a
. deploy/server/.env
set +a
docker compose -f deploy/server/compose.yaml up -d --build
```

You can inspect the installed implementation with `docker compose version`. Modern Docker Compose supports `--env-file`, but the zero-to-running path intentionally does not require that option.

## 8. Review the Server Mode configuration

The default runtime configuration is:

```yaml
storage_root: /srv/ai-workshop
private_endpoint_host: rootless-runtime
private_endpoint_start_port: 41000
private_endpoint_end_port: 41999
```

It lives at:

```text
deploy/server/config/server.yaml
```

Normally the private endpoint range should not be published on the outer host.

Validate the complete Compose model before starting anything:

```bash
cd /opt/ai-workshop
docker compose \
  -f deploy/server/compose.yaml \
  config > /tmp/ai-workshop-server-compose.yaml
```

Security sanity checks:

```bash
! grep -R "/var/run/docker.sock" deploy/server

python3 - <<'PY'
from pathlib import Path
import yaml

compose = yaml.safe_load(Path("deploy/server/compose.yaml").read_text())
consumers = set()
published = set()

for name, service in compose["services"].items():
    for volume in service.get("volumes", []):
        if "server-runtime-socket" in str(volume):
            consumers.add(name)
    if service.get("ports"):
        published.add(name)

assert consumers == {"rootless-runtime", "server-control"}, consumers
assert published == {"ingress"}, published
print("deployment trust-boundary checks: OK")
PY
```

## 9. Build and start Server Mode

From the repository root:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  up -d --build
```

Check status:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  ps
```

All required services should move to running/healthy state.

## 10. Inspect startup logs

If a service does not become healthy:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  logs --tail=200
```

Per-service examples:

```bash
docker compose -f deploy/server/compose.yaml logs --tail=200 rootless-runtime
docker compose -f deploy/server/compose.yaml logs --tail=200 server-control
docker compose -f deploy/server/compose.yaml logs --tail=200 browser
docker compose -f deploy/server/compose.yaml logs --tail=200 ingress
```

Do not solve a nested-runtime problem by mounting `/var/run/docker.sock` into a container.

## 11. Run the Server Mode doctor

The control plane contains the operator doctor command:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  exec -T server-control \
  ai-workshop server doctor \
    --config /config/server.yaml \
    --state-root /state
```

A healthy result has:

```json
{
  "healthy": true,
  "exit_code": 0
}
```

Treat a non-zero doctor result as a failed deployment even if `docker compose ps` says the container is running.

## 12. Verify the nested rootless runtime

From the control plane:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  exec -T server-control \
  docker --host unix:///run/ai-workshop-runtime/1000/docker.sock info
```

Then verify the host socket is absent:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  exec -T server-control \
  sh -lc 'test ! -S /var/run/docker.sock'
```

This distinction is central to Server Mode: the control plane talks to the Workshop-owned nested runtime, never to the host Docker daemon.

## 13. Verify persistent domains

The outer deployment uses named volumes for:

- nested runtime data;
- Workshop server storage;
- control-plane state;
- local CA state;
- browser profile;
- browser artifacts.

List them:

```bash
docker volume ls | grep ai-workshop
```

Restart the outer services without deleting volumes:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  restart
```

Run the doctor again. Projects, identities, browser profile, nested runtime state, and other persistent domains must survive the restart.

Do not use `docker compose down -v` on a server whose state you intend to keep.

## 14. Local CA trust

Bootstrap creates the local CA certificate at:

```text
/var/lib/ai-workshop/ca/ca-cert.pem
```

Only the public CA certificate should be distributed to trusted operator/client machines. Never distribute `ca-key.pem`.

On Debian/Ubuntu, one way to trust the CA system-wide is:

```bash
sudo cp /var/lib/ai-workshop/ca/ca-cert.pem \
  /usr/local/share/ca-certificates/ai-workshop-local-ca.crt
sudo update-ca-certificates
```

For browsers or managed clients with their own trust store, import the public CA certificate into that trust store.

Trust the CA only on machines that are intended to trust this AI Workshop installation.

## 15. LAN binding

The safe default is loopback:

```text
AI_WORKSHOP_HTTPS_BIND=127.0.0.1:8443
```

For a private LAN deployment, change only the ingress bind, for example:

```bash
AI_WORKSHOP_HTTPS_BIND=0.0.0.0:8443
```

Then recreate the ingress service:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  up -d ingress
```

Before binding to `0.0.0.0`:

1. confirm the intended ingress route requires authentication;
2. confirm the expected certificate/hostname is configured;
3. install the local CA on clients;
4. restrict the host firewall to the trusted LAN/VPN;
5. verify no control-plane or nested-runtime port is separately published.

## 16. Offline / air-gapped LAN mode

Use:

```text
deploy/server/offline.example.yaml
```

The offline profile specifies:

- local CA instead of mandatory ACME;
- no required public OIDC provider;
- no required public forge;
- optional embedded Forgejo;
- no required public Internet access after images are present;
- preloaded image policy.

Before disconnecting the host, pre-pull/build every required outer and nested image while connected.

At minimum:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  pull --ignore-buildable

docker compose \
  -f deploy/server/compose.yaml \
  build
```

If embedded Forgejo or additional MCP/project-service images are needed, preload those images as well.

Offline mode does not make remote GitHub/GitLab operations available without network access. Use embedded Forgejo or other LAN-local services for fully disconnected operation.

## 17. Optional embedded Forgejo

The optional Forgejo deployment is documented in:

```text
docs/server/forges.md
config/forgejo.example.yaml
infrastructure/forgejo/compose.yaml
```

Its data volumes are intentionally persistent. Disabling the service must not be treated as permission to delete repositories.

Keep Forgejo backup/recovery separate from ordinary service disable/remove operations.

## 18. First project and credentials

After the core Server Mode deployment is healthy, register Git-managed projects through the Server Mode project/Git interfaces rather than bind-mounting arbitrary host directories into AgentRuns.

Credential profiles should be created through the credential boundary. Do not mount the operator's `~/.ssh` into Server Mode.

For forge integrations, bind a project to a named GitHub, GitLab, or Forgejo profile. See:

```text
docs/server/forges.md
```

## 19. Dynamic MCP runtimes

Dynamic MCP registrations can use managed:

- HTTP;
- stdio;
- container transports.

Stdio MCP servers are never launched as unrestricted host subprocesses. Container MCP servers use the nested RuntimeController and do not receive the nested runtime socket.

Run-scoped MCP registrations are removed with their AgentRun, including failed-run reconciliation.

The stable upstream MCP surface remains:

```text
mcp.servers_list
mcp.server_get
mcp.tools_list
mcp.tool_call
mcp.resources_list
mcp.resource_read
mcp.prompts_list
mcp.prompt_get
```

## 20. Backup before upgrades

Use the scoped Server Mode recovery domains before an upgrade that changes persisted state.

The recovery flow is:

```text
list domain
→ preview snapshot
→ create snapshot
→ preview restore when needed
→ prepare restore
→ receive short-lived confirmation token
→ restore
```

There is no global implicit "wipe everything" operation.

Ordinary identity/config backups exclude configured secret and CA-private roots. MCP registry recovery restores metadata with servers stopped. Forgejo backups are atomic and preserve the last good artifact after a failed attempt.

See:

```text
docs/server/backup-recovery.md
```

## 21. Upgrade an existing installation

From the repository:

```bash
cd /opt/ai-workshop

git fetch --all --tags
git checkout <new-release-or-commit>
uv sync
```

Re-run bootstrap with the same roots and same first-admin ID:

```bash
AI_WORKSHOP_STORAGE_ROOT=/var/lib/ai-workshop/storage \
AI_WORKSHOP_STATE_ROOT=/var/lib/ai-workshop/state \
AI_WORKSHOP_CA_ROOT=/var/lib/ai-workshop/ca \
AI_WORKSHOP_FIRST_ADMIN_ID=admin \
uv run sh ./scripts/server-bootstrap.sh
```

Validate Compose:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  config >/dev/null
```

Rebuild/recreate without deleting named volumes:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  up -d --build
```

Finally rerun `ai-workshop server doctor`.

## 22. Normal stop, restart, and removal

Stop services while preserving all named volumes:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  stop
```

Start them again:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  start
```

Recreate containers while preserving volumes:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  down

docker compose \
  -f deploy/server/compose.yaml \
  up -d
```

Do not add `-v` unless the explicit goal is to destroy Compose-managed persistent volumes.

## 23. Disaster-recovery warning

The following are destructive and should not be part of normal deployment maintenance:

```bash
docker compose -f deploy/server/compose.yaml down -v
docker volume rm <ai-workshop-volume>
rm -rf /var/lib/ai-workshop
```

Before any intentional destructive operation:

1. identify the exact recovery domain;
2. create/verify the backup;
3. confirm the artifact exists outside the state being destroyed;
4. record the intended destructive scope;
5. proceed only with the specific resource that must be removed.

## 24. Troubleshooting checklist

If Server Mode does not start from a clean host, check in this order:

1. `docker info` works for the operator user;
2. Docker Compose v2 is installed;
3. rootless user namespaces are permitted by the host;
4. `uv sync` succeeds;
5. bootstrap succeeds without changing the first-admin ID;
6. `deploy/server/.env` contains the bootstrap-generated browser token;
7. `docker compose ... config` succeeds;
8. `rootless-runtime` becomes healthy;
9. `server-control` becomes healthy;
10. `ai-workshop server doctor` returns exit code 0;
11. browser health is green;
12. ingress is the only service with a published host port;
13. no service contains `/var/run/docker.sock`;
14. persistent named volumes have not been accidentally deleted.

Useful commands:

```bash
docker compose -f deploy/server/compose.yaml ps
docker compose -f deploy/server/compose.yaml logs --tail=200
docker compose -f deploy/server/compose.yaml logs --tail=200 rootless-runtime
docker compose -f deploy/server/compose.yaml logs --tail=200 server-control
docker volume ls | grep ai-workshop
```

## 25. Minimal copy/paste path

For an Ubuntu/Debian host where Docker, Git, Python 3.12+, and uv are already installed:

```bash
git clone https://github.com/boltholds/AI-Workshop.git /opt/ai-workshop
cd /opt/ai-workshop
uv sync

sudo mkdir -p /var/lib/ai-workshop
sudo chown "$USER":"$USER" /var/lib/ai-workshop
chmod 700 /var/lib/ai-workshop

export AI_WORKSHOP_STORAGE_ROOT=/var/lib/ai-workshop/storage
export AI_WORKSHOP_STATE_ROOT=/var/lib/ai-workshop/state
export AI_WORKSHOP_CA_ROOT=/var/lib/ai-workshop/ca
export AI_WORKSHOP_FIRST_ADMIN_ID=admin

uv run sh ./scripts/server-bootstrap.sh

cp deploy/server/.env.example deploy/server/.env
BROWSER_TOKEN="$(cat /var/lib/ai-workshop/state/secrets/browser-token)"
cat > deploy/server/.env <<EOF
AI_WORKSHOP_HTTPS_BIND=127.0.0.1:8443
AI_WORKSHOP_BROWSER_TOKEN=$BROWSER_TOKEN
EOF
chmod 600 deploy/server/.env
unset BROWSER_TOKEN

docker compose \
  -f deploy/server/compose.yaml \
  config >/dev/null

docker compose \
  -f deploy/server/compose.yaml \
  up -d --build

docker compose \
  -f deploy/server/compose.yaml \
  exec -T server-control \
  ai-workshop server doctor \
    --config /config/server.yaml \
    --state-root /state
```

If the final doctor command reports `healthy: true`, the autonomous core deployment is running and the next operator tasks are to configure trusted ingress routes, project/credential/forge bindings, and any optional MCP/service profiles.
