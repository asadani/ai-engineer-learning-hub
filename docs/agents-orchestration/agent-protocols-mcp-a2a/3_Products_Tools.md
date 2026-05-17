# Products & Tools

## MCP Implementations

| Tool | Role | Notes |
|---|---|---|
| **modelcontextprotocol/python-sdk** | Official Python SDK (servers + clients) | `FastMCP` decorator API; reference implementation |
| **TypeScript SDK** | Official TS/JS SDK | First-class for editor/browser clients |
| **MCP server registry** | Discovery of public servers | Grew from ~1,200 (Q1 2025) to 9,400+ (Apr 2026) |
| **Claude / ChatGPT / Cursor / VS Code** | First-party MCP clients | Native tool/resource consumption |
| **Reference servers** | filesystem, git, fetch, postgres, etc. | Maintained exemplars to copy patterns from |

A typical Python MCP server:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("inventory")

@mcp.tool()
def get_stock(sku: str) -> int:
    """Return units in stock for a SKU."""
    return db.lookup(sku)

if __name__ == "__main__":
    mcp.run()            # stdio by default; mcp.run(transport="streamable-http") for remote
```

## A2A Implementations

| Tool | Role |
|---|---|
| **A2A Protocol (Linux Foundation)** | Spec, conformance, Agent Card schema |
| **a2a-python / a2a SDKs** | Build A2A servers (expose an agent) and clients (delegate to one) |
| **Cloud integrations** | Google, Microsoft, AWS agent platforms speak A2A natively |

## Gateways, Runtimes & Adjacent

- **MCP gateways / proxies** — aggregate many MCP servers behind one endpoint, add authn/z, audit, rate limiting, and tool-allowlisting (the API-gateway pattern for tools).
- **Agent frameworks** — LangGraph, CrewAI, AutoGen, the OpenAI Agents SDK, Strands all consume MCP tools and increasingly expose/consume A2A.
- **Observability** — Langfuse, Arize Phoenix, LangSmith trace MCP tool calls and A2A tasks (see *LLM Observability & LLMOps*).

## The Broader Protocol Ecosystem (2026)

MCP and A2A are the dominant pair, but the space includes:

- **ACP (Agent Communication Protocol)** — alternative agent-interop effort; some convergence with A2A.
- **UCP / agent-payment & identity protocols** — emerging standards for agent commerce and verifiable agent identity.

For interviews, anchor on MCP (tool layer) and A2A (agent layer) as the standards that won; treat the rest as ecosystem context, not core knowledge.

## Selection Guidance

- Building a tool/data integration → ship an **MCP server** (official SDK, Streamable HTTP for remote).
- Exposing an agent for others to delegate to → publish an **A2A Agent Card** + endpoint.
- Many internal MCP servers → put a **gateway** in front for auth, audit, and allowlisting.
- Don't hand-roll JSON-RPC — use the official SDKs; conformance and security flows are the hard part.
