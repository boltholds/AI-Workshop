from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ai_workshop.server.models import (
    RuntimeOutboundAccess,
    RuntimeWorkloadKind,
    RuntimeWorkloadSpec,
)


class NetworkGrantPurpose(StrEnum):
    PRIVATE = "private"
    EGRESS = "egress"
    INGRESS = "ingress"


class NetworkGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    network_name: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    )
    purpose: NetworkGrantPurpose
    internal: bool


class RuntimeNetworkPolicyProtocol(Protocol):
    def allowed_networks(
        self,
        workload: RuntimeWorkloadSpec,
    ) -> tuple[NetworkGrant, ...]: ...


_PRIVATE_NETWORKS = {
    RuntimeWorkloadKind.AGENT_RUN: "ai-workshop-agent-runs",
    RuntimeWorkloadKind.MCP: "ai-workshop-mcp-runtimes",
    RuntimeWorkloadKind.PROJECT_SERVICE: "ai-workshop-project-services",
    RuntimeWorkloadKind.INFRASTRUCTURE: "ai-workshop-infrastructure",
}


class RuntimeNetworkPolicy:
    def __init__(
        self,
        *,
        allowed_outbound_kinds: frozenset[RuntimeWorkloadKind] = frozenset(),
    ):
        self.allowed_outbound_kinds = allowed_outbound_kinds

    def allowed_networks(
        self,
        workload: RuntimeWorkloadSpec,
    ) -> tuple[NetworkGrant, ...]:
        grants = [
            NetworkGrant(
                network_name=_PRIVATE_NETWORKS[workload.kind],
                purpose=NetworkGrantPurpose.PRIVATE,
                internal=True,
            )
        ]
        if workload.outbound is RuntimeOutboundAccess.INTERNET:
            if workload.kind not in self.allowed_outbound_kinds:
                raise ValueError(
                    f"outbound internet access is not allowed for {workload.kind.value}"
                )
            grants.append(
                NetworkGrant(
                    network_name="ai-workshop-egress",
                    purpose=NetworkGrantPurpose.EGRESS,
                    internal=False,
                )
            )
        return tuple(grants)
