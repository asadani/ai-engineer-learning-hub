# High-Level Overview

## What It Is

An **agent protocol** is a standardized contract for how an AI agent connects to the things it needs. In 2026 two protocols dominate:

- **MCP (Model Context Protocol)** — an open JSON-RPC standard, introduced by Anthropic in late 2024, that gives an LLM application one uniform way to call **tools**, read **resources**, and use reusable **prompts** from any compliant server. It is the *agent↔tool/data* layer.
- **A2A (Agent-to-Agent)** — an open standard (donated to the Linux Foundation; stable **v1.0** in 2026) for agents to discover, delegate to, and coordinate with **other agents**, including across organizational and vendor boundaries. It is the *agent↔agent* layer.

## The Core Problem They Solve

Before protocols, every agent↔tool and agent↔agent integration was bespoke. N agents × M tools = N×M custom adapters, each with its own auth, schema, and error handling. Swapping a model or a vendor meant rewriting glue. This is the same integration explosion that USB, ODBC, and LSP solved in their domains — MCP is frequently called "USB-C for AI tools."

The protocols collapse N×M into N+M: a tool exposes **one** MCP server; any compliant agent can use it. An agent exposes **one** A2A endpoint; any other agent can delegate to it.

## The Two Layers

```
        ┌─────────────┐   A2A (agent ↔ agent)   ┌─────────────┐
        │  Agent  A    │ ◄──────────────────────►│  Agent  B    │
        │ (your org)   │   tasks, messages,       │ (vendor)     │
        └──────┬───────┘   Agent Cards            └──────┬───────┘
               │ MCP (agent ↔ tool/data)                 │ MCP
        ┌──────▼───────┐                          ┌──────▼───────┐
        │ MCP servers  │  tools / resources /     │ MCP servers  │
        │ (DB, files,  │  prompts                 │ (CRM, APIs)  │
        │  APIs)       │                          │              │
        └──────────────┘                          └──────────────┘
```

MCP is vertical (depth: one agent reaching its capabilities). A2A is horizontal (breadth: many agents collaborating). They are explicitly **complementary, not competing** — both are Linux Foundation projects and are designed to interoperate.

## Adoption Reality (2026)

- **MCP**: ~97M installs by March 2026; 10,000+ community servers; native support in Claude, ChatGPT, Cursor, VS Code; a majority of enterprise AI teams report at least one MCP-backed agent in production.
- **A2A**: v1.0 stable spec under the Linux Foundation; 150+ supporting organizations; integrations across Google, Microsoft, and AWS; production deployments in supply chain, financial services, insurance, and IT ops.

The takeaway for a principal engineer: in 2026, *not* using these protocols is the decision that needs justification.

## When to Use Each

| Situation | Use |
|---|---|
| Agent needs database/API/file access | **MCP** |
| Reusing a tool across many agents/clients | **MCP** |
| Delegating a sub-task to another team's/vendor's agent | **A2A** |
| Orchestrating specialized agents that each own tools | **A2A** (agents) + **MCP** (their tools) |
| A single agent, a few private functions, one codebase | Plain function/tool calling may be enough |

## Where It Sits in the Stack

Agent protocols are infrastructure, below frameworks (LangGraph, CrewAI) and above raw model APIs. A framework *uses* MCP to load tools; an orchestration platform *uses* A2A to route work. Treating them as a stable substrate — like HTTP — is the correct mental model.
