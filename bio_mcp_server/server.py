"""
server.py  —  Bio MCP server, Day 2 (TEACHING EDITION)
=======================================================

This file is written to teach you how to AUTHOR an MCP tool, not just to run.
The comments explain *why each piece is written the way it is*. Read it top to
bottom and it walks you through the same six stages you'd write it in:

    Stage 1  Runnable shell        -> FastMCP instance + entry point
    Stage 2  Tool interface        -> @mcp.tool, signature, docstring-as-prompt
    Stage 3  Typed return schema   -> Pydantic models => structuredContent
    Stage 4  Tool body             -> esearch (IDs) then efetch (content)
    Stage 5  Errors as data        -> structured error results, not exceptions
    Stage 6  Parser helper         -> isolated + unit-testable

AUTHORING PRINCIPLE: write outside-in. Shell first, then the tool's INTERFACE
(signature + docstring + return type), then the logic. The interface is what the
model sees and what your downstream skill consumes, so design it before any code.
"""

import xml.etree.ElementTree as ET

import httpx                                  # async HTTP client (ships with mcp)
from pydantic import BaseModel, Field         # typed return -> output schema
from mcp.server.fastmcp import FastMCP        # high-level MCP server


# ── STAGE 1: the runnable shell ───────────────────────────────────────────────
# Create the server object first. The string is the server name clients see in
# the manifest. At this point (before any tool) the server already boots — get
# that working before you add logic, so a boot failure is never tangled up with
# a logic bug.
mcp = FastMCP("bio-mcp-server")

# Module constants. NCBI asks every caller to identify itself with `tool`+`email`;
# it's how they reach you before throttling. Set CONTACT_EMAIL to your real one.
NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL_NAME = "bio-mcp-server"
CONTACT_EMAIL = "parichit@example.com"        # <-- change me
HTTP_TIMEOUT = 20.0


# ── STAGE 3: the typed return schema ──────────────────────────────────────────
# (Defined above the tool because the tool's signature references it.)
#
# WHY TYPED RETURNS, NOT `-> dict`:
#   FastMCP builds the tool's OUTPUT SCHEMA from the return annotation. A bare
#   `dict` carries no schema, so results arrive as a JSON string in a text block
#   and `structuredContent` is null. A Pydantic model makes the server advertise
#   a real output schema and deliver typed `structuredContent` — the clean
#   channel your Weekend-1 agent skill will consume. These models do double duty:
#   they validate what you return AND become the schema clients rely on.
class Article(BaseModel):
    """One PubMed record, trimmed to what a downstream consumer needs."""
    pmid: str | None = Field(description="PubMed ID")
    title: str
    abstract: str
    url: str | None = Field(description="Canonical pubmed.ncbi.nlm.nih.gov link")


class PubMedResult(BaseModel):
    """
    The tool's return contract. Note the `status` field: a discriminated result
    lets the agent branch on what happened ('no_results' vs 'error' vs 'ok')
    instead of guessing from an empty list.
    """
    status: str = Field(description='"ok" | "no_results" | "error"')
    count: int = Field(description="Number of articles returned")
    articles: list[Article] = Field(default_factory=list)
    message: str | None = Field(default=None,
                                description="Explanation when status is no_results/error")


# ── STAGE 2: the tool interface  +  STAGE 4-5: the body ───────────────────────
@mcp.tool()                                   # registers fn; reads hints + docstring
async def search_pubmed(query: str, max_results: int = 5) -> PubMedResult:
    """
    Search PubMed for biomedical literature and return titles, abstracts, and PMIDs.

    THE DOCSTRING IS PROMPT ENGINEERING. Everything below is read by the model to
    decide whether to call this tool. Two halves:
      * Positive triggers — when TO use it.
      * Negative boundaries — when NOT to (point at the sibling tools by name).
    Writing the boundaries before those tools exist is what stops the model from
    grabbing the wrong tool later.

    Use this tool when the user asks about published research, papers, prior work,
    evidence, or the scientific literature on a biological/biomedical topic
    (e.g. "what is known about beta cell heterogeneity"). Do NOT use it to retrieve
    experimental single-cell expression data (that is query_cellxgene) or
    protein-level annotations (that is lookup_uniprot).

    Args:                                     # Arg descriptions also reach the model.
        query: A free-text PubMed query. Standard PubMed syntax works
               (AND/OR, [MeSH], field tags).
        max_results: Maximum articles to return (clamped to 1-20, default 5).
    """
    # NOTE on `async def`: this tool does network I/O. MCP runs tools on an event
    # loop; async keeps the server responsive while waiting on NCBI. Use async for
    # any tool that calls out to the network.

    # Clamp the arg so a bad value can never dump a huge payload into context.
    max_results = max(1, min(int(max_results), 20))
    common = {"db": "pubmed", "tool": TOOL_NAME, "email": CONTACT_EMAIL}

    # STAGE 5: the whole body is wrapped so failures become DATA, not crashes.
    # An agent can reason about a returned {status:"error"}; a raw exception just
    # kills the turn. Catch the specific things a network API does wrong.
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # STAGE 4, call 1 — esearch returns matching PMIDs (JSON is simplest).
            r = await client.get(f"{NCBI_BASE}/esearch.fcgi",
                                  params={**common, "term": query,
                                          "retmax": max_results, "retmode": "json"})
            r.raise_for_status()              # turn 4xx/5xx into HTTPStatusError
            ids = r.json().get("esearchresult", {}).get("idlist", [])

            # A genuine "nothing matched" is NOT an error — give it its own status
            # so the agent doesn't confuse "no papers" with "the tool broke".
            if not ids:
                return PubMedResult(status="no_results", count=0,
                                    message=f"No PubMed articles found for query: {query!r}")

            # STAGE 4, call 2 — efetch returns the actual titles + abstracts.
            # Only XML carries abstract text, so we fetch XML and parse it.
            r = await client.get(f"{NCBI_BASE}/efetch.fcgi",
                                  params={**common, "id": ",".join(ids),
                                          "rettype": "abstract", "retmode": "xml"})
            r.raise_for_status()
            articles = _parse_pubmed_xml(r.text)

        # The tool is an ADAPTER: it queries the API in the API's shape (IDs, then
        # content) but returns data in OUR shape (PubMedResult).
        return PubMedResult(status="ok", count=len(articles), articles=articles)

    except httpx.HTTPStatusError as e:
        # 429 = rate limited. NCBI allows ~3 req/s without an API key; name the
        # specific case so the agent knows retrying (not rephrasing) is the fix.
        if e.response.status_code == 429:
            return PubMedResult(status="error", count=0,
                                message="PubMed rate limit hit (HTTP 429). Wait a few "
                                        "seconds and retry, or set an NCBI API key.")
        return PubMedResult(status="error", count=0,
                            message=f"PubMed returned HTTP {e.response.status_code}.")
    except (httpx.TimeoutException, httpx.RequestError) as e:
        return PubMedResult(status="error", count=0,
                            message=f"Network error contacting PubMed: {type(e).__name__}.")


# ── STAGE 6: the parser, kept separate so it's testable without the network ───
def _parse_pubmed_xml(xml_text: str) -> list[Article]:
    """
    Pull pmid / title / abstract out of an efetch XML response.

    Why a separate function? Network code and parsing code fail for different
    reasons. Isolating the parser lets test_parser.py feed it a saved XML string
    and assert on the output with zero network calls (see file 3).

    The one real subtlety: PubMed abstracts are often STRUCTURED — several
    <AbstractText Label="BACKGROUND">...</AbstractText> nodes. We join them and
    keep the labels so the abstract reads sensibly.
    """
    root = ET.fromstring(xml_text)
    out: list[Article] = []
    for art in root.findall(".//PubmedArticle"):
        pmid_el = art.find(".//MedlineCitation/PMID")
        pmid = pmid_el.text if pmid_el is not None else None

        # .itertext() flattens any inline markup (e.g. <i> in titles) to plain text.
        title_el = art.find(".//Article/ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else "(no title)"

        parts = []
        for ab in art.findall(".//Abstract/AbstractText"):
            label, text = ab.get("Label"), "".join(ab.itertext()).strip()
            parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(parts) if parts else "(no abstract available)"

        out.append(Article(pmid=pmid, title=title, abstract=abstract,
                           url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None))
    return out


# ── STAGE 1 (continued): the entry point ──────────────────────────────────────
if __name__ == "__main__":
    # transport="streamable-http" is the CURRENT standard remote transport
    # (it replaced legacy SSE). Serves on http://127.0.0.1:8000/mcp by default.
    # Swap to "stdio" only for a local subprocess client like Claude Desktop.
    mcp.run(transport="streamable-http")