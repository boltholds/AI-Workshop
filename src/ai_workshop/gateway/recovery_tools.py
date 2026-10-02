from __future__ import annotations

from ai_workshop.gateway.errors import GatewayError


def register_recovery_tools(
    server,
    workspace_client,
    *,
    state_service=None,
    reset_service=None,
    server_recovery_registry=None,
) -> None:
    def workspace_safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except GatewayError as exc:
            raise RuntimeError(f"{exc.code}: {exc.message}") from None

    @server.tool()
    def workspace_snapshot_create(project_id: str) -> dict[str, object]:
        return workspace_safe(workspace_client.snapshot_create, project_id)

    @server.tool()
    def workspace_snapshot_preview_restore(snapshot_id: str) -> dict[str, object]:
        return workspace_safe(workspace_client.snapshot_preview_restore, snapshot_id)

    @server.tool()
    def workspace_snapshot_prepare_restore(
        snapshot_id: str,
        ttl_seconds: float = 300.0,
    ) -> dict[str, object]:
        return workspace_safe(
            workspace_client.snapshot_prepare_restore,
            snapshot_id,
            ttl_seconds,
        )

    @server.tool()
    def workspace_snapshot_restore(
        snapshot_id: str,
        confirmation_token: str,
    ) -> dict[str, object]:
        return workspace_safe(
            workspace_client.snapshot_restore,
            snapshot_id,
            confirmation_token,
        )

    if state_service is not None:
        def state_safe(callable_, *args, **kwargs):
            try:
                return callable_(*args, **kwargs)
            except (KeyError, ValueError, PermissionError) as exc:
                raise RuntimeError(str(exc).strip("'")) from None
            except Exception:
                raise RuntimeError("STATE_RECOVERY_FAILED: state recovery failed") from None

        @server.tool()
        def state_snapshot_create(
            adapter_id: str,
            target_id: str,
        ) -> dict[str, object]:
            return state_safe(
                state_service.create,
                adapter_id,
                target_id,
            ).model_dump()

        @server.tool()
        def state_snapshot_prepare_restore(
            snapshot_id: str,
            ttl_seconds: float = 300.0,
        ) -> dict[str, object]:
            return state_safe(
                state_service.prepare_restore,
                snapshot_id,
                ttl_seconds=ttl_seconds,
            ).model_dump()

        @server.tool()
        def state_snapshot_restore(
            snapshot_id: str,
            confirmation_token: str,
        ) -> dict[str, object]:
            return state_safe(
                state_service.restore,
                snapshot_id,
                confirmation_token,
            ).model_dump()

    if reset_service is not None:
        @server.tool()
        def reset_preview(scope: str) -> dict[str, object]:
            plan = reset_service.plan(scope)
            return {
                "scope": plan.scope,
                "actions": plan.actions,
                "digest": plan.digest,
            }

        @server.tool()
        def reset_prepare(
            scope: str,
            ttl_seconds: float = 300.0,
        ) -> dict[str, object]:
            plan = reset_service.plan(scope)
            return reset_service.prepare(
                plan,
                ttl_seconds=ttl_seconds,
            ).model_dump()

        @server.tool()
        def reset_execute(
            scope: str,
            confirmation_token: str,
        ) -> dict[str, object]:
            plan = reset_service.plan(scope)
            return reset_service.execute(
                plan,
                confirmation_token,
            ).model_dump()


    if server_recovery_registry is not None:
        def server_recovery_safe(callable_, *args, **kwargs):
            try:
                return callable_(*args, **kwargs)
            except (KeyError, ValueError, PermissionError) as exc:
                raise RuntimeError(str(exc).strip("'")) from None
            except RuntimeError:
                raise
            except Exception:
                raise RuntimeError(
                    "SERVER_RECOVERY_FAILED: server recovery operation failed"
                ) from None

        @server.tool()
        def server_recovery_domains() -> list[str]:
            return server_recovery_registry.list()

        @server.tool()
        def server_recovery_snapshot_preview(
            domain_id: str,
            target_id: str,
        ) -> dict[str, object]:
            domain = server_recovery_safe(
                server_recovery_registry.require,
                domain_id,
            )
            return server_recovery_safe(
                domain.preview_snapshot,
                target_id,
            )

        @server.tool()
        def server_recovery_snapshot_create(
            domain_id: str,
            target_id: str,
        ) -> dict[str, object]:
            domain = server_recovery_safe(
                server_recovery_registry.require,
                domain_id,
            )
            return server_recovery_safe(
                domain.snapshot,
                target_id,
            )

        @server.tool()
        def server_recovery_restore_preview(
            domain_id: str,
            snapshot_id: str,
        ) -> dict[str, object]:
            domain = server_recovery_safe(
                server_recovery_registry.require,
                domain_id,
            )
            return server_recovery_safe(
                domain.preview_restore,
                snapshot_id,
            )

        @server.tool()
        def server_recovery_restore_prepare(
            domain_id: str,
            snapshot_id: str,
            ttl_seconds: float = 300.0,
        ) -> dict[str, object]:
            domain = server_recovery_safe(
                server_recovery_registry.require,
                domain_id,
            )
            prepare = getattr(domain, "prepare_restore", None)
            if prepare is None:
                raise RuntimeError(
                    "SERVER_RECOVERY_PREPARE_UNSUPPORTED"
                )
            return server_recovery_safe(
                prepare,
                snapshot_id,
                ttl_seconds=ttl_seconds,
            ).model_dump()

        @server.tool()
        def server_recovery_restore(
            domain_id: str,
            snapshot_id: str,
            confirmation_token: str,
        ) -> dict[str, object]:
            domain = server_recovery_safe(
                server_recovery_registry.require,
                domain_id,
            )
            return server_recovery_safe(
                domain.restore,
                snapshot_id,
                confirmation_token,
            )
