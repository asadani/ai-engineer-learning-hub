# Use Cases & Real-World Applications

## 1. Internal Tool Gateway (MCP)

A platform team exposes company systems (data warehouse, ticketing, feature flags, deploy API) as MCP servers behind a single **MCP gateway** with OAuth 2.1 and per-team tool allowlists. Any product team's agent — regardless of framework or model — gets governed access without bespoke integration. Outcome: N×M integrations collapse to N+M; security and audit are centralized.

## 2. Multi-Vendor Agent Mesh (A2A + MCP)

An enterprise's procurement agent delegates a sub-task to a supplier's pricing agent via **A2A** (Agent Card discovery, scoped OAuth, task lifecycle with streaming updates). The supplier's agent internally uses **MCP** to reach its own ERP — opaque to the caller. Outcome: cross-org automation without sharing internal tools or data; clean trust boundary at the A2A edge.

## 3. Enterprise Data Access for an Assistant (MCP resources)

A support assistant reads customer records, KB articles, and recent tickets as MCP **resources** (URI-addressed, application-controlled) while using **tools** only for actions (issue refund, escalate). Separating read-context (resources) from actions (tools) gives a clean least-privilege boundary and makes prompt-injection blast radius smaller.

## 4. IDE / Coding Agent (MCP over stdio)

Cursor/VS Code launch local MCP servers (filesystem, git, test runner, language server) over **stdio** — no network surface, fast, sensitive code stays local. The same server, switched to Streamable HTTP, can later back a hosted reviewer agent unchanged.

## 5. Long-Running Research Delegation (A2A tasks)

An orchestrator submits a "produce a market report" **task** to a specialized research agent. The task runs for minutes; the orchestrator subscribes to streaming progress and receives a push notification on completion. The `input-required` state lets the research agent ask a clarifying question mid-task. Outcome: durable, resumable delegation instead of brittle synchronous calls.

## 6. Tool Reuse Across Models (MCP portability)

The same `inventory` MCP server serves a Claude-based ops agent, a GPT-based analytics agent, and a local open-model batch job. Switching the underlying model changes nothing about the tool layer — the protocol decouples capability from model choice, which is the core ROI in a fast-moving model market.

## Pattern Summary

| Need | Protocol pattern |
|---|---|
| Govern many tools for many agents | MCP servers + gateway |
| Cross-org / cross-vendor collaboration | A2A (agents) over MCP (their tools) |
| Read context vs take action | MCP resources vs MCP tools |
| Local, sensitive, fast | MCP over stdio |
| Minutes-long, resumable work | A2A tasks + streaming/push |
| Model independence | Any MCP-compliant client |
