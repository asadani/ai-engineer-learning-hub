# Tradeoffs & Comparisons

## MCP vs A2A vs Plain Function Calling

| Dimension | Plain function calling | MCP | A2A |
|---|---|---|---|
| Boundary | In-process | Agent ↔ tool/data | Agent ↔ agent |
| Reuse across clients | None (bespoke) | High (one server, many clients) | High (one agent, many callers) |
| Discovery | Hard-coded | `tools/list` handshake | Agent Card |
| Best for | 1 agent, few private fns | Portable tools/data access | Cross-team/vendor delegation |
| Overhead | Lowest | Process/HTTP + handshake | HTTP + task lifecycle |

Rule: stay with plain function calling only when there is exactly one agent, the functions are private to that codebase, and reuse is implausible. The moment a second consumer appears, MCP pays for itself.

## stdio vs Streamable HTTP (MCP transport)

| | stdio | Streamable HTTP |
|---|---|---|
| Deployment | Local child process | Remote HTTPS service |
| Concurrency | One client | Many clients, horizontal scale |
| Auth | Process boundary | OAuth 2.1, enterprise IdP |
| Latency | Lowest | Network-bound |
| Use when | Desktop/IDE, dev, sensitive local data | Shared/enterprise/production servers |

Default local = stdio; default production/shared = Streamable HTTP.

## Single-Agent (MCP only) vs Multi-Agent (A2A)

Adding A2A adds a coordination surface and failure modes (partial failure, distributed state, trust). Use the **minimal viable topology**: a single agent with many MCP tools beats a multi-agent A2A mesh until a single agent genuinely cannot own the task (different ownership, different trust domains, independent scaling, or specialization that doesn't fit one context). Multi-agent for its own sake multiplies the compounding-error problem.

## Adopt vs Build

| | Adopt MCP/A2A | Build bespoke glue |
|---|---|---|
| Time-to-first-integration | Hours (SDK) | Days–weeks |
| Portability | Across all compliant clients | None |
| Lock-in | Low (open standard) | High |
| Control of wire format | Low | Total |
| 2026 default | ✅ | Only for unusual constraints |

## Local Tools vs Remote MCP Servers (security)

Remote servers externalize execution and widen the attack surface (indirect prompt injection via tool descriptions/resources, confused-deputy via chained A2A→MCP, token theft). Gains: central governance, reuse, audit. Mitigate with gateways, scoped OAuth, allowlists, and human approval on irreversible tools — don't avoid remote servers, govern them.

## Common Failure Modes

- **Over-decomposition** into many A2A agents → latency, cost, error compounding.
- **Treating tool descriptions as trusted** → injection.
- **No capability negotiation** → brittle clients that assume features.
- **Long-running work over request/response** instead of A2A tasks → timeouts, lost state.
- **Hand-rolled JSON-RPC** → conformance and security bugs the SDKs already solved.
