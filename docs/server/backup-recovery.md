# Server Mode backup and recovery

Server recovery is domain-scoped. Use the recovery MCP surface to list domains, preview/create snapshots, preview restores, request a short-lived confirmation token, and execute the restore.

Canonical Git-managed projects use Git-aware snapshots. Retained run workspaces are bound to run, project and commit identity. Identity/config backups are checksum-versioned and exclude configured secret/CA roots. MCP registry recovery restores metadata only and forces registrations to STOPPED.

Optional Forgejo backups are written atomically. A failed backup leaves the last successful artifact intact and writes redacted failure diagnostics.

There is no global "wipe all" recovery operation. Reset scopes are explicit and protect project roots, credential state and CA private state.
