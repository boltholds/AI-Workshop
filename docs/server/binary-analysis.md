# Isolated binary inspection in AI Workshop Server Mode

The optional binary analysis extension exposes these tools:

| Tool | Behavior |
| --- | --- |
| filesystem_read | Read UTF-8 text (max 1 MiB) in a registered project |
| filesystem_write | Atomic UTF-8 write (max 1 MiB) in a registered project |
| shell_exec | Allowlisted read-only binary inspection |
| binary_analyze | Queue Ghidra Headless PE analysis |
| analysis_get_results | Retrieve job status and function metadata |
| cargo_test | Run offline and locked Rust tests |

**This extension is for projects and binaries you are authorized to inspect.**
None of these tools is exposed by default in Server Mode. All six become
available when the optional analysis overlay is explicitly enabled; its gateway
environment opts in to project file access and configures the worker URL/token.

## Isolation

The gateway never runs user-selected commands or receives a Docker socket for
analysis. The optional analysis worker:

- runs as unprivileged UID 10001 with all Linux capabilities dropped;
- mounts the registered project checkout directory read-only;
- has no mount of Workshop state, host SSH, credentials or Docker socket;
- communicates over a private, non-published Docker network;
- has CPU, memory and PID resource limits;
- limits shell_exec to file, readelf, objdump, nm, strings and sha256sum;
- runs Cargo with --offline --locked and a temporary build target directory.

Cargo build scripts and tests can execute arbitrary project code inside the worker.
Use trusted Rust repositories only. Container isolation reduces risk but does not
guarantee immunity against native-tool or kernel vulnerabilities.

Neither binary samples nor Ghidra results are automatically pushed to GitHub.

## Ubuntu setup

Obtain Ghidra from an official release, verify its requirements, and extract it
so the executable is located at:

    /opt/ai-workshop/ghidra/support/analyzeHeadless

If Ghidra is absent, the worker stays healthy but binary_analyze reports that
its headless analyzer is not installed.

**Do not upgrade or recreate an existing WAI deployment without a backup and
a compatibility review.** The base Compose file may change between versions.

Configure a random worker token in the private file deploy/server/.env:

    cd /opt/ai-workshop
    printf 'AI_WORKSHOP_ANALYSIS_TOKEN=%s\n' "$(openssl rand -hex 32)" >> deploy/server/.env
    chmod 600 deploy/server/.env

Configure AI_WORKSHOP_GHIDRA_ROOT and AI_WORKSHOP_STORAGE_ROOT when using
non-default paths. The analysis worker's Ghidra and project mounts are read-only.

Validate the combined Compose configuration:

    docker compose -f deploy/server/compose.yaml \
      -f deploy/server/compose.analysis.yaml config

After reviewing the model and service compatibility, start the optional worker
and recreate the gateway:

    docker compose -f deploy/server/compose.yaml \
      -f deploy/server/compose.analysis.yaml up -d --build analysis-worker gateway

Check its status:

    docker compose -f deploy/server/compose.yaml \
      -f deploy/server/compose.analysis.yaml ps

Refresh tool discovery in the ChatGPT developer-mode app after deployment.

## Usage

Register the research project through WAI before calling the analysis tools.
Place PE samples in a private untracked location within the registered project;
never commit third-party binaries without permission.

    shell_exec(project_id="research", argv=["file", "samples/kernel.dll"])
    shell_exec(project_id="research", argv=["objdump", "-p", "samples/kernel.dll"])
    binary_analyze(project_id="research", path="samples/kernel.dll")
    analysis_get_results(project_id="research", analysis_id="ID_FROM_RESULT")
    cargo_test(project_id="rustsolid", manifest_path="Cargo.toml")

The analysis result includes its SHA-256, status, and a bounded Ghidra-derived
function summary. It does not claim to recover original source code.

Cargo operates offline; dependencies must already be cached or vendored, and
a missing dependency produces a normal Cargo error. Network access is not
automatically enabled to repair failed builds.

## Restrictions

- shell_exec is not a general terminal. Only read-only binary inspection
  commands and explicitly allowlisted arguments are accepted.
- Ghidra jobs are queued in memory, while their result metadata is persisted.
  Interrupted jobs must be started again after a worker restart.
- Worker output is bounded to 256 KiB, and CPU execution is time-limited.
- PE inputs must have DOS and PE signatures.
- Windows remains necessary for debugging Shapr3D dynamically.
- Evaluate third-party licensing before analyzing proprietary DLLs. Keep
  RustSolid code independent of any protected third-party implementation.
