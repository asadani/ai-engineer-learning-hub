# Agent Protocols: MCP & A2A

Principal-level interview prep notes on the two protocols that standardize the agent stack in 2026 — **MCP** (Model Context Protocol, agent↔tool/data) and **A2A** (Agent-to-Agent, agent↔agent coordination) — covering the wire format, primitives, transports, security, and architecture decisions.

Generated: 2026-05-17 (web-grounded)

---

## Contents

| # | File | Focus |
|---|------|-------|
| 1 | [High-Level Overview](1_High_Level_Overview.md) | Why protocols emerged, the two layers, adoption reality, when to use each |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | JSON-RPC 2.0, MCP primitives (tools/resources/prompts), transports (stdio, Streamable HTTP), A2A Agent Cards, tasks, OAuth 2.1 |
| 3 | [Products & Tools](3_Products_Tools.md) | MCP SDKs, registries, A2A SDK, gateways, runtimes, the protocol ecosystem (ACP/UCP) |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | MCP vs A2A vs plain function calling, stdio vs HTTP, single-agent vs multi-agent, build vs adopt |
| 5 | [Use Cases](5_Use_Cases.md) | Internal tool gateway, multi-vendor agent mesh, enterprise data access, IDE agents |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | Tool-call success, protocol conformance, latency budget, security posture |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | Metrics tables, OTel GenAI spans for tool calls, alerting |
| 8 | [Interview Questions](8_Interview_Questions.md) | Tiered Q&As (L5/L6/L7+) with model answers |

---

## Key Themes

### 1. Two Layers, Not Competitors
MCP standardizes how an agent reaches **tools and data** (vertical integration); A2A standardizes how agents **talk to other agents** across organizational boundaries (horizontal integration). They are complementary — a production system typically uses both: A2A between agents, each agent using MCP to reach its tools.

### 2. The "USB-C for AI" Win Is Real
By 2026 MCP is effectively the default agent↔tool interface (~97M installs by March 2026, 10,000+ community servers, supported by Claude, ChatGPT, Cursor, VS Code). A2A reached a stable v1.0 under the Linux Foundation with 150+ supporting organizations. Protocol literacy is now a baseline skill, not a specialization.

### 3. It's Just JSON-RPC 2.0 — the Value Is the Schema
Neither protocol invents a new wire format. The leverage is a **shared schema and capability-negotiation handshake**, which makes a tool written once portable across every compliant client. Understand the handshake and you understand the protocol.

### 4. Security Moves to the Protocol Boundary
Remote MCP servers and A2A endpoints externalize your tools. OAuth 2.1, least-privilege tool scopes, prompt-injection-aware tool descriptions, and human approval on irreversible actions are protocol-boundary concerns — not application afterthoughts.

### 5. Adopt Before You Build
The correct default in 2026 is to expose tools as MCP servers and agents as A2A endpoints rather than inventing bespoke integration. Custom glue is now the expensive, lock-in path.


!!! tip "Related Topics"

    - [Agentic Design Patterns](../agentic-design-patterns/)
    - [Context Engineering](../context-engineering/)
    - [Prompt Engineering](../prompt-engineering/)
    - [Event-Driven Architecture](../../architecture/event-driven-architecture/)
