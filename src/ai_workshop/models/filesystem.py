from pydantic import BaseModel


class FileReadResult(BaseModel):
    path: str
    content: str


class SearchMatch(BaseModel):
    path: str
    line: int
    text: str
