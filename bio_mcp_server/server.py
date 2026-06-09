# ── bio_mcp_server/server.py ──────────────────────────────────────────────────
#
# Minimal MCP server — Day 1 checkpoint.
# Uses FastMCP: the high-level interface that handles all protocol boilerplate.
# ─────────────────────────────────────────────────────────────────────────────

from mcp.server.fastmcp import FastMCP          # High-level server class
                                                # Handles: capability negotiation,
                                                # tool registration, JSON schema
                                                # generation, error wrapping.

# ── 1. Create the server instance ────────────────────────────────────────────
# The string is the server's name — clients see this in the manifest.
mcp = FastMCP("bio-mcp-server")


# ── 2. Define a trivial tool ──────────────────────────────────────────────────
# The @mcp.tool() decorator does three things:
#   a) Registers the function as a callable tool
#   b) Reads the type hints to auto-generate the JSON parameter schema
#   c) Uses the docstring as the tool's description (what the LLM reads)
#
# CRITICAL PRINCIPLE: the docstring IS the tool description the model uses to
# decide when and how to call this function. Write it as prompt engineering,
# not just developer documentation.

@mcp.tool()
def echo(text: str) -> str:
    """
    Echo back the provided text. Use this tool to confirm the server is
    running and the client–server connection is working.

    Args:
        text: Any string to echo back.

    Returns:
        The same string prefixed with 'Echo: '.
    """
    return f"Echo: {text}"


@mcp.tool()
def add(a: float, b: float) -> float:
    """
    Add two numbers together. Use this to verify that typed numeric
    parameters are correctly passed through the MCP protocol.

    Args:
        a: First number.
        b: Second number.

    Returns:
        The sum a + b.
    """
    return a + b


# ── 3. Entry point ────────────────────────────────────────────────────────────
# mcp.run() starts the server using stdio transport by default.
# stdio means: Claude (or the inspector) launches this as a subprocess
# and communicates over stdin/stdout using JSON-RPC.
# For production hosting, you'd swap this for an SSE (HTTP) transport.

if __name__ == "__main__":
    mcp.run()