import json
import sys
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from tools.repository import ROOT

class ToolClient:
    async def __aenter__(self):
        self.client = Client(PythonStdioTransport(ROOT / "mcp_server.py", python_cmd=sys.executable, cwd=str(ROOT)))
        await self.client.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self.client.__aexit__(*args)

    async def catalog(self):
        return [{"name": t.name, "description": t.description, "parameters": t.input_schema}
                for t in await self.client.list_tools()]

    async def call(self, name, arguments):
        result = await self.client.call_tool(name, arguments)
        if result.data is not None:
            return result.data
        return json.loads(result.content[0].text)
