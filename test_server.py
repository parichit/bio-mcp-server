# test_server.py — no Inspector, no Node, no browser
import asyncio
from bio_mcp_server.server import mcp

async def smoke_test():
    tools = await mcp.list_tools()                    # the "manifest"
    print("Registered tools:", [t.name for t in tools])

    # mcp >=1.x: call_tool returns (content_blocks, structured_result)
    content, structured = await mcp.call_tool("echo", {"text": "hi"})
    print("echo ->", structured["result"])            # -> Echo: hi

    content, structured = await mcp.call_tool("add", {"a": 3.0, "b": 4.0})
    print("add  ->", structured["result"])            # -> 7.0

if __name__ == "__main__":
    asyncio.run(smoke_test())