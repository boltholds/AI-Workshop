from __future__ import annotations


def _agent_payload(agent) -> dict[str, object]:
    return {
        "agent_id": agent.agent_id,
        "principal_id": agent.principal_id,
        "display_name": agent.display_name,
        "owner_principal_id": agent.owner_principal_id,
        "lifetime": agent.lifetime.value,
        "status": agent.status.value,
        "created_at": agent.created_at.isoformat(),
        "archived_at": (
            agent.archived_at.isoformat()
            if agent.archived_at is not None
            else None
        ),
    }


def register_agent_tools(server, agents, authorization, principal_resolver) -> None:
    def actor() -> str:
        principal_id = principal_resolver.current_principal_id()
        if not principal_id:
            raise RuntimeError("AUTHENTICATION_REQUIRED")
        return principal_id

    def safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except (KeyError, ValueError, PermissionError) as exc:
            raise RuntimeError(str(exc).strip("'")) from None
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("AGENT_OPERATION_FAILED: agent operation failed") from None

    @server.tool()
    def agents_list() -> list[dict[str, object]]:
        principal_id = actor()
        safe(authorization.require, principal_id, "agents.read", None)
        return [_agent_payload(item) for item in safe(agents.list)]

    @server.tool()
    def agents_get(agent_id: str) -> dict[str, object]:
        principal_id = actor()
        safe(authorization.require, principal_id, "agents.read", None)
        return _agent_payload(safe(agents.get, agent_id))

    @server.tool()
    def agents_create_persistent(
        agent_id: str,
        display_name: str,
    ) -> dict[str, object]:
        principal_id = actor()
        safe(authorization.require, principal_id, "agents.manage", None)
        return _agent_payload(
            safe(
                agents.create_persistent,
                agent_id,
                display_name=display_name,
                owner_principal_id=principal_id,
            )
        )

    @server.tool()
    def agents_create_ephemeral(
        agent_id: str,
        display_name: str,
    ) -> dict[str, object]:
        principal_id = actor()
        safe(authorization.require, principal_id, "agents.manage", None)
        return _agent_payload(
            safe(
                agents.create_ephemeral,
                agent_id,
                display_name=display_name,
                owner_principal_id=principal_id,
            )
        )

    @server.tool()
    def agents_archive(agent_id: str) -> dict[str, object]:
        principal_id = actor()
        safe(authorization.require, principal_id, "agents.manage", None)
        return _agent_payload(safe(agents.archive, agent_id))
