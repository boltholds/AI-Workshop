# Debugging a project in AI Workshop

This workflow applies to any mounted project and any optional service profile.

## 1. Check the sandbox

Run:

```bash
ai-workshop doctor
```

Required core checks must be healthy before starting. Optional components such as the browser or a persistence adapter may be reported separately.

## 2. Snapshot the project before mutation

Create a project snapshot through MCP:

```text
workspace_snapshot_create(project_id)
```

A project snapshot records the current Git identity, HEAD/branch, staged and unstaged binary patches, untracked files, and file hashes. It is designed to preserve a worktree that was already dirty before the agent started.

For stateful services, use the corresponding persistence adapter separately:

```text
state_snapshot_create(adapter_id, target_id)
```

Project snapshots and service-state snapshots are intentionally independent.

## 3. Reproduce the issue

Use the normal Workshop tools:

- filesystem and search tools to inspect source;
- shell tools to run tests, builds, or development commands;
- service tools to start/rebuild only registered services;
- browser tools to navigate, inspect console/network state, and interact with the UI.

For dynamic UI problems, explicitly request browser recording and temporal diagnostics. The recording can produce WebM plus neutral/time-gradient PNG composites and structured JSON metadata.

## 4. Make the smallest change and verify it

Edit the mounted project through filesystem tools, then run the project's own tests/build commands.

Use Git inspection tools to review the exact diff before deciding to keep the change.

## 5. Keep or restore

If the change is correct, leave the project in its new state and continue normal Git workflow.

If the experiment should be discarded:

1. call `workspace_snapshot_preview_restore(snapshot_id)`;
2. inspect the reset/delete/restore paths;
3. call `workspace_snapshot_prepare_restore(snapshot_id)`;
4. use the returned one-time confirmation token with `workspace_snapshot_restore`.

Restore tokens are short-lived and bound to the preview digest. If the worktree changes after confirmation, the token is rejected and a new preview is required.

Persistent service state uses the equivalent adapter-specific confirmation flow.

## Safety boundary

Recovery is scoped to configured project roots and Workshop-owned state. Reset operations do not include host projects implicitly. There is no generic "wipe projects" reset command.

AI Workshop does not require any particular framework, database, language, or application architecture. Project-specific stacks are expressed through mounted projects, service profiles, and optional adapters.
