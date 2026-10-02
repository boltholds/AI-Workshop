# Autonomous Server Mode deployment

Server Mode is packaged in `deploy/server/compose.yaml`. This guide starts from a clean Linux host and takes the deployment through bootstrap, startup, validation, persistence checks, LAN/offline configuration, upgrade, backup, and shutdown.

The production deployment uses a dedicated systemd-managed rootless Docker daemon owned by the `ai-workshop-runtime` host user. The outer Compose deployment contains:

- `server-control` — the autonomous Server Mode control plane;
- `browser` — the persistent Chromium/browser diagnostics runtime;
- `ingress` — the only outer service allowed to publish a host port.

The host rootful Docker socket is never mounted into AI Workshop. `server-control` receives only the dedicated rootless socket, normally `/run/user/1000/docker.sock`, bind-mounted inside the container as `/run/ai-workshop-runtime/1000/docker.sock`.

The repository-level `compose.server.yaml` keeps the older DIND-rootless backend for CI/dev acceptance only; it is not the production runtime boundary.

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

The production runtime configuration is:

```yaml
storage_root: /var/lib/ai-workshop/storage
private_endpoint_host: host.docker.internal
private_endpoint_start_port: 41000
private_endpoint_end_port: 41999
```

The storage path is intentionally the same host path that the rootless Docker daemon sees. This is required for AgentRun/project-service bind mounts created by the host-managed runtime.

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

All outer services should move to running/healthy state. The dedicated rootless runtime is a host systemd user service and is checked separately with `systemctl --user status docker` or through `ai-workshop server doctor`.

## 10. Inspect startup logs

If a service does not become healthy:

```bash
docker compose \
  -f deploy/server/compose.yaml \
  logs --tail=200
```

Per-service examples:

```bash
docker compose -f deploy/server/compose.yaml logs --tail=200 server-control
docker compose -f deploy/server/compose.yaml logs --tail=200 browser
docker compose -f deploy/server/compose.yaml logs --tail=200 ingress
```

For the host-managed runtime:

```bash
machinectl shell ai-workshop-runtime@
systemctl --user status docker --no-pager -l
journalctl --user -u docker -n 100 --no-pager
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

## 12. Verify the host-managed rootless runtime

On the host, the dedicated runtime should report cgroup v2 with the systemd driver:

```bash
machinectl shell ai-workshop-runtime@
export DOCKER_HOST=unix:///run/user/1000/docker.sock
docker info | grep -i -E 'Cgroup Driver|Cgroup Version|rootless'
```

Expected:

```text
Cgroup Driver: systemd
Cgroup Version: 2
```

Verify actual resource enforcement:

```bash
docker run --rm --memory 128m --cpus 0.5 alpine:latest \
  sh -c 'cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/cpu.max'
```

Expected:

```text
134217728
50000 100000
```

From the control plane:

```bash
docker-compose \
  -f deploy/server/compose.yaml \
  exec -T server-control \
  docker --host unix:///run/ai-workshop-runtime/1000/docker.sock info
```

Then verify the host rootful socket is absent:

```bash
docker-compose \
  -f deploy/server/compose.yaml \
  exec -T server-control \
  sh -lc 'test ! -S /var/run/docker.sock'
```

This distinction is central to Server Mode: the control plane talks only to the dedicated rootless daemon, never to the host rootful Docker daemon.

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


## Production rootless runtime setup

Create a dedicated host user:

```bash
adduser --disabled-password --gecos "" ai-workshop-runtime
apt install -y uidmap slirp4netns fuse-overlayfs systemd-container
```

Confirm subordinate IDs:

```bash
grep '^ai-workshop-runtime:' /etc/subuid
grep '^ai-workshop-runtime:' /etc/subgid
```

Configure systemd delegation:

```bash
mkdir -p /etc/systemd/system/user@.service.d
cat >/etc/systemd/system/user@.service.d/delegate.conf <<'EOF'
[Service]
Delegate=cpu cpuset io memory pids
EOF
systemctl daemon-reload
loginctl enable-linger ai-workshop-runtime
```

Install rootless Docker from a real user systemd session:

```bash
machinectl shell ai-workshop-runtime@
dockerd-rootless-setuptool.sh install
```

On Ubuntu hosts where the default detached network namespace fails during Docker bridge/NAT initialization, add the compatibility override that was validated on production:

```bash
mkdir -p ~/.config/systemd/user/docker.service.d
cat > ~/.config/systemd/user/docker.service.d/override.conf <<'EOF'
[Service]
Environment="DOCKERD_ROOTLESS_ROOTLESSKIT_NET=slirp4netns"
Environment="DOCKERD_ROOTLESS_ROOTLESSKIT_PORT_DRIVER=builtin"
Environment="DOCKERD_ROOTLESS_ROOTLESSKIT_DETACH_NETNS=false"
EOF

systemctl --user daemon-reload
systemctl --user reset-failed docker.service
systemctl --user restart docker.service
```

Verify:

```bash
export DOCKER_HOST=unix:///run/user/1000/docker.sock
docker run --rm alpine:latest echo ROOTLESS_OK
docker info | grep -i -E 'Cgroup Driver|Cgroup Version'
```

For the production Compose deployment, `deploy/server/.env` should include:

```env
AI_WORKSHOP_RUNTIME_SOCKET=/run/user/1000/docker.sock
AI_WORKSHOP_STORAGE_ROOT=/var/lib/ai-workshop/storage
```

Ensure the runtime user can access Workshop storage:

```bash
chown -R ai-workshop-runtime:ai-workshop-runtime /var/lib/ai-workshop/storage
```

The rootless runtime publishes controller-issued private endpoint ports from `41000` through `41999` on the host. Restrict that range at the host firewall to trusted local/container traffic; do not expose it to the public Internet.


## Migrating from containerized DIND runtime

Installations created with the earlier production Compose used a `rootless-runtime` DIND service plus the `server-storage` named volume. Migrate that storage before starting the host-managed runtime deployment.

Stop the old outer deployment without deleting volumes:

```bash
cd /opt/ai-workshop
docker-compose -f deploy/server/compose.yaml down
```

Find the old storage volume:

```bash
docker volume ls --format '{{.Name}}' | grep 'server-storage'
```

For the default Compose project name it is normally `server_server-storage`. Create the new host storage and copy the old volume:

```bash
mkdir -p /var/lib/ai-workshop/storage

docker run --rm \
  -v server_server-storage:/from:ro \
  -v /var/lib/ai-workshop/storage:/to \
  alpine:latest \
  sh -c 'cp -a /from/. /to/'
```

Do not delete the old named volume yet. Keep it as rollback material until the new runtime has passed doctor and workload tests.

Give the dedicated rootless runtime user access to the workload storage:

```bash
chown -R ai-workshop-runtime:ai-workshop-runtime \
  /var/lib/ai-workshop/storage
chmod 700 /var/lib/ai-workshop/storage
```

Update `deploy/server/.env`:

```env
AI_WORKSHOP_RUNTIME_SOCKET=/run/user/1000/docker.sock
AI_WORKSHOP_STORAGE_ROOT=/var/lib/ai-workshop/storage
```

Then recreate the outer deployment from the new manifest:

```bash
docker-compose -f deploy/server/compose.yaml up -d --build
```

The production Compose no longer starts a `rootless-runtime` container. `server-control` receives only the dedicated host-managed rootless socket.

Verify the control plane:

```bash
docker-compose -f deploy/server/compose.yaml exec -T server-control \
  ai-workshop server doctor \
    --config /config/server.yaml \
    --state-root /state
```

Verify the socket visible inside the control plane belongs to the rootless runtime:

```bash
docker-compose -f deploy/server/compose.yaml exec -T server-control \
  docker --host unix:///run/ai-workshop-runtime/1000/docker.sock info
```

Finally verify controller endpoint reachability from the outer control plane:

```bash
docker-compose -f deploy/server/compose.yaml exec -T server-control \
  docker --host unix:///run/ai-workshop-runtime/1000/docker.sock \
  run -d --rm --name ai-workshop-endpoint-smoke \
  -p 41000:8080 alpine:latest \
  sh -c 'mkdir -p /www; echo ENDPOINT_OK >/www/index.html; httpd -f -p 8080 -h /www'

docker-compose -f deploy/server/compose.yaml exec -T server-control \
  python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:41000', timeout=5).read().decode().strip())"

docker-compose -f deploy/server/compose.yaml exec -T server-control \
  docker --host unix:///run/ai-workshop-runtime/1000/docker.sock \
  rm -f ai-workshop-endpoint-smoke
```

The expected HTTP result is `ENDPOINT_OK`.

Rootless-published private endpoint ports `41000-41999` are host listeners used by the control plane through `host.docker.internal`. Restrict this range with the host firewall so it is not reachable from public interfaces.
