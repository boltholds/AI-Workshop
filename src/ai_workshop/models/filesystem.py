from __future__ import annotations

from pydantic import BaseModel


class FileEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int | None = None


class SearchMatch(BaseModel):
    path: str
    line: int
    text: str
