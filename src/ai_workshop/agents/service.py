from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Protocol

from ai_workshop.agents.models import (
    AgentIdentity,
    AgentLifetime,
    AgentStatus,
    DelegationGrant,
)
from ai_workshop.authz.models import PermissionSet
from ai_workshop.identity.models import AgentPrincipal
from ai_workshop.identity.protocol import PrincipalService


class RunPermissionSource(Protocol):
    def effective_permissions_for_run(self, run_id: str) -> PermissionSet: ...


class AgentService:
    def __init__(
        self,
        principals: PrincipalService,
        *,
        state_path: Path,
    ):
        self.principals = principals
        self.state_path = Path(state_path)
        self._lock = threading.RLock()
        self._agents: dict[str, AgentIdentity] = {}
        self._load()

    def create_persistent(
        self,
        agent_id: str,
        *,
        display_name: str,
        owner_principal_id: str,
    ) -> AgentIdentity:
        return self._create(
            agent_id,
            display_name=display_name,
            owner_principal_id=owner_principal_id,
            lifetime=AgentLifetime.PERSISTENT,
        )

    def create_ephemeral(
        self,
        agent_id: str,
        *,
        display_name: str,
        owner_principal_id: str,
    ) -> AgentIdentity:
        return self._create(
            agent_id,
            display_name=display_name,
            owner_principal_id=owner_principal_id,
            lifetime=AgentLifetime.EPHEMERAL,
        )

    def get(self, agent_id: str) -> AgentIdentity:
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                raise KeyError(f"unknown agent: {agent_id}")
            return agent

    def list(self, *, include_archived: bool = False) -> list[AgentIdentity]:
        with self._lock:
            agents = [self._agents[key] for key in sorted(self._agents)]
        if include_archived:
            return agents
        return [
            agent for agent in agents
            if agent.status is AgentStatus.ACTIVE
        ]

    def archive(self, agent_id: str) -> AgentIdentity:
        with self._lock:
            agent = self.get(agent_id)
            if agent.status is AgentStatus.ARCHIVED:
                return agent
            archived = agent.model_copy(
                update={
                    "status": AgentStatus.ARCHIVED,
                    "archived_at": datetime.now(timezone.utc),
                }
            )
            self._agents[agent_id] = archived
            try:
                self._persist()
            except Exception:
                self._agents[agent_id] = agent
                raise
            return archived

    def _create(
        self,
        agent_id: str,
        *,
        display_name: str,
        owner_principal_id: str,
        lifetime: AgentLifetime,
    ) -> AgentIdentity:
        with self._lock:
            self.principals.get(owner_principal_id)
            if agent_id in self._agents:
                raise ValueError(f"agent already exists: {agent_id}")

            principal = AgentPrincipal(
                principal_id=agent_id,
                display_name=display_name,
            )
            self.principals.create(principal)
            agent = AgentIdentity(
                agent_id=agent_id,
                principal_id=principal.principal_id,
                display_name=display_name,
                owner_principal_id=owner_principal_id,
                lifetime=lifetime,
            )
            self._agents[agent_id] = agent
            try:
                self._persist()
            except Exception:
                self._agents.pop(agent_id, None)
                raise
            return agent

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported agent store version")
        for raw in payload.get("agents", []):
            agent = AgentIdentity.model_validate(raw)
            if agent.agent_id in self._agents:
                raise ValueError("duplicate agent identity")
            principal = self.principals.get(agent.principal_id)
            if not isinstance(principal, AgentPrincipal):
                raise ValueError("agent identity principal is not an agent principal")
            if principal.display_name != agent.display_name:
                raise ValueError("agent identity does not match principal")
            self.principals.get(agent.owner_principal_id)
            self._agents[agent.agent_id] = agent

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "agents": [
                self._agents[key].model_dump(mode="json")
                for key in sorted(self._agents)
            ],
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)


class DelegationService:
    def __init__(
        self,
        agents: AgentService,
        run_permissions: RunPermissionSource,
    ):
        self.agents = agents
        self.run_permissions = run_permissions

    def delegate(
        self,
        parent_run_id: str,
        child_agent_id: str,
        requested_permissions: frozenset[str],
    ) -> DelegationGrant:
        if not requested_permissions:
            raise ValueError("delegation requires at least one permission")
        child = self.agents.get(child_agent_id)
        if child.status is AgentStatus.ARCHIVED:
            raise ValueError("cannot delegate to archived agent")

        parent = self.run_permissions.effective_permissions_for_run(
            parent_run_id
        )
        if not requested_permissions.issubset(parent.permissions):
            raise PermissionError(
                "delegated permissions exceed parent run permissions"
            )
        return DelegationGrant(
            parent_run_id=parent_run_id,
            parent_principal_id=parent.principal_id,
            child_agent_id=child_agent_id,
            project_id=parent.project_id,
            permissions=requested_permissions,
        )
