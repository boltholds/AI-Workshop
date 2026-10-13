from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel
class CountResult(BaseModel):
    count: int
    label: str
server = MCPServer('fixture')
counter = 0
@server.tool()
def count(label: str) -> CountResult:
    global counter
    counter += 1
    return CountResult(count=counter, label=label)
@server.tool()
def fail() -> dict:
    raise ValueError('fixture failure')
server.run(transport='stdio')
