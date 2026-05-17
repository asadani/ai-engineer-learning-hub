# Key Technical Concepts

## The Shared Foundation: JSON-RPC 2.0

Both MCP and A2A use **JSON-RPC 2.0** messages (requests, responses, notifications) over a transport. There is no novel wire format — the value is the **shared schema** and a **capability-negotiation handshake**. A request is `{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{...}}`; a notification omits `id` and expects no reply.

## MCP: The Three Primitives

A server declares which primitives it supports during initialization, plus whether it emits dynamic list-change notifications.

1. **Tools** — model-invocable functions with a JSON Schema input (`tools/list`, `tools/call`). Example: `query_database`, `send_email`. The model decides when to call them.
2. **Resources** — readable data identified by URI (`resources/list`, `resources/read`). Example: a file, a record, a log. Application- or user-controlled, not model-invoked.
3. **Prompts** — parameterized prompt templates the server offers (`prompts/list`, `prompts/get`), surfaced to users as reusable workflows (e.g., a slash command).

Distinguishing tools (model-triggered actions) from resources (context to read) from prompts (user-triggered workflows) is the single most tested MCP concept.

### The MCP Handshake

```
client → initialize        (protocolVersion, client capabilities)
server → initialize result (server capabilities: tools? resources? prompts?)
client → notifications/initialized
client → tools/list        → server returns tool schemas
client → tools/call        → server executes, returns content blocks
```

Capability negotiation means a client only uses what the server advertises; unknown features degrade gracefully.

## MCP Transports

- **stdio** — the server runs as a local child process; messages flow over stdin/stdout pipes. Default for local/desktop integrations. Zero network surface, simplest auth (process boundary).
- **Streamable HTTP** — the server exposes an HTTPS endpoint; supports many concurrent clients, horizontal scaling, and enterprise auth (**OAuth 2.1**). The standard for remote, production servers. (Replaced the earlier HTTP+SSE transport.)

Both carry identical JSON-RPC, so a tool is portable between local and remote deployments without code change.

## A2A: Core Concepts

A2A treats a remote agent as an opaque service you delegate to (you do **not** see its tools or chain-of-thought — only inputs and outputs).

- **Agent Card** — a JSON descriptor (commonly at `/.well-known/agent-card.json`) advertising the agent's identity, skills, endpoint, auth requirements, and supported modalities. This is the discovery primitive (analogous to MCP's `tools/list`, but for *agents*).
- **Task** — a unit of delegated work with a lifecycle: `submitted → working → input-required → completed | failed | canceled`. Tasks are long-lived and resumable; A2A is built for work that takes minutes, not just request/response.
- **Message / Part** — messages carry typed **parts** (text, file, structured data), enabling multimodal exchange between agents.
- **Streaming & push** — clients can stream task updates (SSE) or register webhooks for push notifications on long-running tasks.

A2A **v1.0** added multi-protocol support, enterprise-grade multi-tenancy, modernized security flows, and a defined migration path for early adopters.

## Security Model

The protocol boundary is a trust boundary:

- **OAuth 2.1** for remote MCP servers and A2A endpoints; scoped tokens per tool/skill.
- **Least-privilege tool scopes** — expose the minimum capability; separate read vs write servers.
- **Prompt-injection-aware tool descriptions** — tool descriptions and resource contents are untrusted input that the model reads; a malicious server can attempt indirect prompt injection. Sanitize, constrain, and never auto-execute irreversible tools.
- **Human-in-the-loop** on irreversible actions remains mandatory regardless of protocol.
- **Confused-deputy risk**: an agent calling another agent (A2A) that calls tools (MCP) can launder privilege — propagate identity, don't widen scope.

## The Mental Model

MCP = "give one agent portable access to many capabilities." A2A = "let many agents delegate to each other safely." Both = JSON-RPC + a schema + a capability handshake + an auth story. Everything else is an SDK detail.
