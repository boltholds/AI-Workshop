from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel


class ConsoleEvent(BaseModel):
    level: str
    text: str
    timestamp: datetime


class NetworkEvent(BaseModel):
    method: str
    url: str
    resource_type: str
    timestamp: datetime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
