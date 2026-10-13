from __future__ import annotations


def register_project_workspace_tools(server, files, analysis) -> None:
    """Project-only file IO and opt-in isolated binary inspection tools."""

    def safe(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (KeyError, ValueError, PermissionError) as exc:
            raise RuntimeError(str(exc).strip("'")) from None
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError('WORKSPACE_OPERATION_FAILED') from None

    @server.tool()
    def filesystem_read(project_id: str, path: str) -> str:
        return safe(files.read, project_id, path)

    @server.tool()
    def filesystem_write(project_id: str, path: str, content: str) -> dict[str, bool]:
        return safe(files.write, project_id, path, content)

    if analysis is None:
        return

    @server.tool()
    def shell_exec(project_id: str, argv: list[str], timeout_seconds: float = 30) -> dict[str, object]:
        """Allowlisted read-only PE inspection tools in an isolated container."""
        safe(files._root, project_id)
        return safe(analysis.shell_exec, project_id, argv, timeout_seconds)

    @server.tool()
    def binary_analyze(project_id: str, path: str) -> dict[str, object]:
        safe(files._root, project_id)
        return safe(analysis.binary_analyze, project_id, path)

    @server.tool()
    def analysis_get_results(project_id: str, analysis_id: str) -> dict[str, object]:
        safe(files._root, project_id)
        return safe(analysis.analysis_get_results, project_id, analysis_id)

    @server.tool()
    def cargo_test(project_id: str, manifest_path: str = 'Cargo.toml', timeout_seconds: float = 300) -> dict[str, object]:
        safe(files._root, project_id)
        return safe(analysis.cargo_test, project_id, manifest_path, timeout_seconds)
