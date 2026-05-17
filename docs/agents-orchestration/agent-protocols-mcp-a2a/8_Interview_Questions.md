# Interview Questions & Scenarios

## L5 — Foundations

**Q1. What problem do MCP and A2A solve, and how do they differ?**
They solve the N×M integration explosion. MCP standardizes *agent↔tool/data* access (one server, many clients); A2A standardizes *agent↔agent* delegation across org/vendor boundaries (one Agent Card, many callers). They are complementary layers, not competitors — a system typically uses A2A between agents and MCP within each agent. Both are JSON-RPC 2.0 with a capability handshake.

**Q2. Explain MCP's three primitives.**
*Tools* = model-invocable functions (actions; `tools/call`). *Resources* = readable, URI-addressed data the application/user supplies as context (`resources/read`, not model-triggered). *Prompts* = reusable, parameterized prompt templates surfaced to users. The key distinction: tools = model-driven actions, resources = context to read, prompts = user-driven workflows.

**Q3. stdio vs Streamable HTTP — when each?**
stdio: local child process, one client, process-boundary auth, lowest latency — IDEs, desktop, sensitive local data. Streamable HTTP: remote HTTPS, many clients, horizontal scale, OAuth 2.1 — shared/enterprise/production. Same JSON-RPC, so tools are portable between them.

## L6 — Design & Tradeoffs

**Q4. Design a governed tool platform for 30 product teams.**
Expose company systems as MCP servers (read vs write split). Put an **MCP gateway** in front: OAuth 2.1, per-team tool allowlists, rate limiting, central audit, injection scanning of tool descriptions/resources. Conformance suite in CI per server. Teams' agents (any framework/model) consume via the gateway. This collapses N×M to N+M, centralizes security, and decouples tools from model choice.

**Q5. When would you NOT introduce A2A multi-agent?**
When one agent with many MCP tools can own the task. A2A adds a distributed-systems surface: partial failure, distributed state, trust boundaries, latency, and compounding error (p^N across steps). Introduce A2A only for genuine cross-ownership, independent scaling/trust domains, or specialization that can't fit one context. Minimal viable topology first.

**Q6. A remote MCP server is in the request path. What are the security risks and mitigations?**
Risks: indirect prompt injection via tool descriptions/resources (untrusted text the model reads), confused-deputy in A2A→MCP chains, token theft, over-broad scopes. Mitigations: OAuth 2.1 with least-privilege scoped tokens, gateway allowlists, injection scanning, redacted logging, human approval on irreversible tools, identity propagation (not scope widening) across agent hops.

## L7+ — Principal

**Q7. Justify adopting these protocols vs your existing bespoke integrations to a skeptical staff eng.**
Bespoke glue is N×M, lock-in, and a per-model rewrite cost in a market where models change quarterly. MCP/A2A are open Linux Foundation standards with overwhelming 2026 adoption (MCP ~97M installs, 10k+ servers; A2A v1.0, 150+ orgs, cloud-native). Adopting decouples capability from model, makes tools portable, and moves security to a governable boundary. The risk is *not* adopting: continued integration tax and lock-in. Migrate incrementally — wrap existing tools as MCP servers behind a gateway, no big bang.

**Q8. How do you evaluate an agent-protocol integration beyond "did it answer correctly"?**
Trajectory evaluation: judge the *call path* (tool selection accuracy, argument validity, conformance to the JSON-RPC/A2A state machine, safety of the sequence), not just the final answer — a correct answer via an unsafe/irreversible path is a failure. Add a conformance harness in CI, a red-team set of injected tool descriptions, and load tests on HTTP transports. Trace with OTel GenAI conventions for portability.

**Q9. Walk through what happens, message by message, when a Claude client connects to a remote MCP server and calls a tool.**
`initialize` (client offers protocol version + capabilities) → server returns its capabilities (tools/resources/prompts, dynamic-list support) → `notifications/initialized` → `tools/list` (server returns JSON-Schema tool defs) → model selects a tool → `tools/call` with validated args → server executes under the OAuth scope → returns content blocks → client feeds result back to the model. Capability negotiation ensures the client only uses advertised features and degrades gracefully otherwise.

## Rapid-Fire

- *Is MCP a new wire format?* No — JSON-RPC 2.0; the value is the schema + handshake.
- *Do you see another agent's tools over A2A?* No — A2A agents are opaque; you exchange tasks/messages, not tool lists.
- *Which transport replaced HTTP+SSE in MCP?* Streamable HTTP.
- *Where is an A2A Agent Card typically served?* `/.well-known/agent-card.json`.
- *One-line MCP vs A2A?* MCP = agent→tools; A2A = agent→agent.
