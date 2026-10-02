from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def validate_dns_hostname(value: str) -> str:
    hostname = value.strip().lower()
    if hostname != value.strip().lower():
        raise ValueError("invalid hostname")
    if any(char in hostname for char in (":", "/", "*", "_")):
        raise ValueError("invalid hostname")
    labels = hostname.split(".")
    if len(labels) < 2 or any(not label for label in labels):
        raise ValueError("invalid hostname")
    if any(_HOST_LABEL.fullmatch(label) is None for label in labels):
        raise ValueError("invalid hostname")
    return hostname


class IssuedCertificate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hostname: str = Field(min_length=1, max_length=253)
    certificate_path: Path
    private_key_path: Path
    not_after: datetime

    @field_validator("hostname")
    @classmethod
    def hostname_is_dns_name(cls, value: str) -> str:
        return validate_dns_hostname(value)

    @field_validator("certificate_path", "private_key_path")
    @classmethod
    def paths_are_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("certificate paths must be absolute")
        return value
