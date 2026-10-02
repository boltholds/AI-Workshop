from __future__ import annotations

from ai_workshop.git.service import GitRepositoryError


def _project_payload(project) -> dict[str, object]:
    return {
        "project_id": project.project_id,
        "kind": project.kind.value,
        "remote_url": project.remote_url,
    }


def register_git_tools(server, git, destructive=None) -> None:
    def safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except GitRepositoryError as exc:
            raise RuntimeError(f"{exc.code}: {exc.message}") from None
        except (KeyError, ValueError, PermissionError) as exc:
            raise RuntimeError(str(exc).strip("'")) from None
        except Exception:
            raise RuntimeError("GIT_OPERATION_FAILED: Git operation failed") from None

    @server.tool()
    def git_clone(
        project_id: str,
        remote_url: str,
        credential_id: str | None = None,
    ) -> dict[str, object]:
        project = safe(
            git.clone,
            project_id,
            remote_url,
            credential_id=credential_id,
        )
        return _project_payload(project)

    @server.tool()
    def git_status(project_id: str) -> dict[str, object]:
        return safe(git.status, project_id).model_dump()

    @server.tool()
    def git_diff(project_id: str, staged: bool = False) -> str:
        return safe(git.diff, project_id, staged=staged)

    @server.tool()
    def git_fetch(
        project_id: str,
        remote: str = "origin",
        credential_id: str | None = None,
    ) -> dict[str, bool]:
        safe(git.fetch, project_id, remote=remote, credential_id=credential_id)
        return {"ok": True}

    @server.tool()
    def git_pull(
        project_id: str,
        branch: str,
        remote: str = "origin",
        credential_id: str | None = None,
    ) -> dict[str, bool]:
        safe(
            git.pull,
            project_id,
            remote=remote,
            branch=branch,
            credential_id=credential_id,
        )
        return {"ok": True}

    @server.tool()
    def git_add(project_id: str, relative_paths: list[str]) -> dict[str, bool]:
        safe(git.add, project_id, relative_paths)
        return {"ok": True}

    @server.tool()
    def git_commit(project_id: str, message: str) -> dict[str, object]:
        return safe(git.commit, project_id, message).model_dump()

    @server.tool()
    def git_log(project_id: str, limit: int = 20) -> list[dict[str, object]]:
        return [item.model_dump() for item in safe(git.log, project_id, limit=limit)]

    @server.tool()
    def git_branch_list(project_id: str) -> list[str]:
        return safe(git.branch_list, project_id)

    @server.tool()
    def git_branch_create(project_id: str, branch: str) -> dict[str, bool]:
        safe(git.branch_create, project_id, branch)
        return {"ok": True}

    @server.tool()
    def git_switch(project_id: str, branch: str) -> dict[str, bool]:
        safe(git.switch, project_id, branch)
        return {"ok": True}

    @server.tool()
    def git_checkout(project_id: str, ref: str) -> dict[str, bool]:
        safe(git.checkout, project_id, ref)
        return {"ok": True}

    @server.tool()
    def git_remote_list(project_id: str) -> dict[str, str]:
        return safe(git.remote_list, project_id)

    @server.tool()
    def git_remote_set(
        project_id: str,
        name: str,
        remote_url: str,
    ) -> dict[str, bool]:
        safe(git.remote_set, project_id, name, remote_url)
        return {"ok": True}

    @server.tool()
    def git_stash(
        project_id: str,
        message: str = "AI Workshop stash",
    ) -> dict[str, bool]:
        safe(git.stash, project_id, message=message)
        return {"ok": True}

    @server.tool()
    def git_tag(project_id: str, tag: str) -> dict[str, bool]:
        safe(git.tag, project_id, tag)
        return {"ok": True}

    @server.tool()
    def git_push(
        project_id: str,
        branch: str,
        remote: str = "origin",
        credential_id: str | None = None,
    ) -> dict[str, bool]:
        safe(
            git.push,
            project_id,
            remote=remote,
            branch=branch,
            credential_id=credential_id,
        )
        return {"ok": True}

    @server.tool()
    def git_merge(project_id: str, ref: str) -> dict[str, bool]:
        safe(git.merge, project_id, ref)
        return {"ok": True}

    @server.tool()
    def git_rebase(project_id: str, ref: str) -> dict[str, bool]:
        safe(git.rebase, project_id, ref)
        return {"ok": True}

    @server.tool()
    def git_rebase_continue(project_id: str) -> dict[str, bool]:
        safe(git.rebase_continue, project_id)
        return {"ok": True}

    @server.tool()
    def git_rebase_abort(project_id: str) -> dict[str, bool]:
        safe(git.rebase_abort, project_id)
        return {"ok": True}

    @server.tool()
    def git_cherry_pick(project_id: str, ref: str) -> dict[str, bool]:
        safe(git.cherry_pick, project_id, ref)
        return {"ok": True}

    if destructive is not None:
        @server.tool()
        def git_hard_reset_preview(
            project_id: str,
            target: str,
        ) -> dict[str, object]:
            return safe(
                destructive.preview_hard_reset,
                project_id,
                target,
            ).model_dump(mode="json")

        @server.tool()
        def git_hard_reset_prepare(
            project_id: str,
            target: str,
            ttl_seconds: float = 300.0,
        ) -> dict[str, object]:
            preview = safe(destructive.preview_hard_reset, project_id, target)
            return safe(
                destructive.prepare,
                preview,
                ttl_seconds=ttl_seconds,
            ).model_dump()

        @server.tool()
        def git_hard_reset(
            project_id: str,
            target: str,
            confirmation_token: str,
        ) -> dict[str, object]:
            return safe(
                destructive.hard_reset,
                project_id,
                target,
                confirmation_token,
            ).model_dump(mode="json")

        @server.tool()
        def git_force_push_preview(
            project_id: str,
            branch: str,
            remote: str = "origin",
        ) -> dict[str, object]:
            return safe(
                destructive.preview_force_push,
                project_id,
                remote=remote,
                branch=branch,
            ).model_dump(mode="json")

        @server.tool()
        def git_force_push_prepare(
            project_id: str,
            branch: str,
            remote: str = "origin",
            ttl_seconds: float = 300.0,
        ) -> dict[str, object]:
            preview = safe(
                destructive.preview_force_push,
                project_id,
                remote=remote,
                branch=branch,
            )
            return safe(
                destructive.prepare,
                preview,
                ttl_seconds=ttl_seconds,
            ).model_dump()

        @server.tool()
        def git_force_push(
            project_id: str,
            branch: str,
            confirmation_token: str,
            remote: str = "origin",
            credential_id: str | None = None,
        ) -> dict[str, object]:
            return safe(
                destructive.force_push,
                project_id,
                remote=remote,
                branch=branch,
                confirmation_token=confirmation_token,
                credential_id=credential_id,
            ).model_dump(mode="json")
