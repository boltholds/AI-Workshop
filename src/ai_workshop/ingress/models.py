from __future__ import annotations

from enum import StrEnum
from ipaddress import ip_address
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_workshop.server.models import RuntimeEndpoint


_ROUTE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class IngressAuthPolicy(StrEnum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"


class IngressRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route_id: str = Field(min_length=1, pattern=_ROUTE_ID_PATTERN)
    hostname: str = Field(min_length=1, max_length=253)
    endpoint: RuntimeEndpoint
    auth_policy: IngressAuthPolicy = IngressAuthPolicy.PUBLIC
    required_scope: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z][A-Za-z0-9_.:-]*$",
    )

    @field_validator("hostname")
    @classmethod
    def normalize_hostname(cls, value: str) -> str:
        hostname = value.strip().lower()
        if hostname != value.strip().lower():
            raise ValueError("invalid hostname")
        if any(char in hostname for char in (":", "/", "*", "_")):
            raise ValueError("invalid hostname")
        try:
            ip_address(hostname)
        except ValueError:
            pass
        else:
            raise ValueError("hostname must not be an IP address")

        labels = hostname.split(".")
        if len(labels) < 2 or any(not label for label in labels):
            raise ValueError("hostname must be a qualified DNS name")
        if any(_HOST_LABEL.fullmatch(label) is None for label in labels):
            raise ValueError("invalid hostname")
        return hostname
