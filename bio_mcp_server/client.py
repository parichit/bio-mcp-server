"""
client.py  —  A real MCP client over Streamable HTTP, Day 2 (TEACHING EDITION)
==============================================================================

This is the OTHER half of MCP. File 1's server advertised tools; this client
actually connects over the wire and calls them, exercising the full protocol
the Day-1 in-process `call_tool` shortcut skipped (handshake, manifest fetch,
serialization). If this runs, your server genuinely speaks MCP.

THE ONE BIG IDEA — a client is two nested layers:

    streamablehttp_client(url)   TRANSPORT: owns the HTTP connection + byte streams
            └── ClientSession    PROTOCOL : turns those bytes into MCP messages

They nest as two `async with` blocks (session inside transport) because the
session needs live streams to exist, and inner-then-outer teardown is the
correct cleanup order. Built outside-in, same as the server:

    Stage 1  async skeleton      -> asyncio.run(main())
    Stage 2  open transport      -> streamablehttp_client -> (read, write, _)
    Stage 3  open session+init   -> ClientSession, then initialize() handshake
    Stage 4  discover            -> list_tools() (the manifest)
    Stage 5  invoke + read       -> call_tool(), then isError/structuredContent/content
"""

import asyncio
import json

from mcp import ClientSession                          # PROTOCOL layer
from mcp.client.streamable_http import streamablehttp_client  # TRANSPORT layer


# Must match where server.py serves. FastMCP's streamable-http default is
# host 127.0.0.1, port 8000, path /mcp.
SERVER_URL = "http://127.0.0.1:8000/mcp"


# ── STAGE 1: the async skeleton ───────────────────────────────────────────────
# Every client call is awaited, so the body lives in an async function that
# asyncio.run() drives. There is no synchronous MCP client API — embrace async.
async def main():

    # ── STAGE 2: open the TRANSPORT (outer layer) ─────────────────────────────
    # Entering this context manager opens the HTTP connection and yields three
    # things:
    #   read  — incoming byte stream (server -> client)
    #   write — outgoing byte stream (client -> server)
    #   _     — a getter for the session id; needed only for stateful servers,
    #           so we discard it with `_`.
    # You never touch read/write directly — the session layer does. `async with`
    # guarantees the connection closes even if something below raises.
    async with streamablehttp_client(SERVER_URL) as (read, write, _):

        # ── STAGE 3: open the SESSION (inner layer) + handshake ───────────────
        # ClientSession speaks JSON-RPC over the streams. It is nested INSIDE the
        # transport block because it needs those live streams. initialize() is the
        # capability-negotiation handshake — the MCP equivalent of a TCP handshake.
        # NOTHING (list_tools, call_tool) works before it.
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ── STAGE 4: discover what the server offers ──────────────────────
            # list_tools() returns the manifest — the same definitions the server
            # advertised. A real LLM client reads exactly this to decide what it
            # can call. (The tools live under the `.tools` attribute of the result.)
            tools = await session.list_tools()
            print("Tools advertised by server:")
            for t in tools.tools:
                print(f"  - {t.name}")

            # ── STAGE 5: invoke a tool + read the result correctly ────────────
            # call_tool(name, arguments_dict) runs the tool over the wire.
            print("\nCalling search_pubmed over the wire...")
            res = await session.call_tool(
                "search_pubmed",
                {"query": "nanopore biosensing for peptide classification", "max_results": 3},
            )

            # The result object exposes three things worth knowing:
            #   res.isError           protocol-level failure flag
            #   res.structuredContent the TYPED dict — populated ONLY because the
            #                         server tool returns a Pydantic model (file 1,
            #                         Stage 3). This is what your skill consumes.
            #   res.content           list of content blocks an LLM reads as text
            print("  isError:", res.isError)
            print("  structuredContent:", json.dumps(res.structuredContent, indent=2))


if __name__ == "__main__":
    asyncio.run(main())