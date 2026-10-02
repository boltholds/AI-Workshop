# Autonomous Server Mode deployment

Server Mode is packaged in `deploy/server/compose.yaml`. The required outer services are the rootless nested runtime, server control plane, browser runtime, and the authenticated ingress boundary.

## Bootstrap

Run the bootstrap helper before the first deployment:

```bash
./scripts/server-bootstrap.sh
docker compose -f deploy/server/compose.yaml up -d --build
```

PowerShell environments can use `scripts/server-bootstrap.ps1`.

Bootstrap is idempotent. Re-running it preserves the existing local CA and generated service tokens, while completing missing storage/state created by an interrupted earlier run.

## Persistence

Named volumes retain nested runtime state, Workshop-owned project/run storage, control-plane state, the local CA, browser profile, and browser artifacts. Restarting outer services must not recreate these domains.

Only the ingress service publishes a host port. The nested runtime socket is shared only between the rootless runtime and server-control service. The host Docker socket is never mounted.

## Upgrade

Pull the new source/images, keep the named volumes, run bootstrap again, then recreate the outer deployment. Backup selected recovery domains before destructive upgrades.
