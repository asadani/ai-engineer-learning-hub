# Measurement & Evaluation

## What "Good" Means

A protocol integration is healthy when tool/agent calls **succeed reliably, quickly, and safely**, and when the schema the model sees is good enough that it calls the right tool with the right arguments.

## Evaluation Dimensions

### 1. Tool-Call Correctness
- **Tool-selection accuracy** — did the model pick the right MCP tool for the intent?
- **Argument validity** — fraction of calls passing the tool's JSON Schema on first attempt.
- **Outcome success** — call returned a usable result vs error/empty.
Evaluate with a labeled set of intents → expected tool + args; this is a classification + extraction eval (see *Evals in AI*).

### 2. Protocol Conformance
- Initialize/capability handshake correct; graceful degradation when a capability is absent.
- JSON-RPC error semantics correct (proper error objects, no silent failures).
- A2A task state machine respected (`submitted→working→completed/…`), cancellation honored.
Run a conformance suite against every server/agent before it ships and in CI.

### 3. Latency
- Handshake + `tools/list` overhead (one-time per session).
- Per-call round-trip (stdio vs HTTP differ materially).
- A2A task time-to-first-update and time-to-completion for long tasks.

### 4. Security Posture
- Tool descriptions/resources scanned for injection payloads.
- OAuth scopes minimal and enforced; token lifetime bounded.
- Irreversible tools gated by human approval; audit log complete.
- Confused-deputy tests for A2A→MCP chains (identity propagated, scope not widened).

### 5. Robustness
- Behavior under server unavailability, partial results, timeouts, malformed responses.
- Dynamic list-change notifications handled (tools appearing/disappearing).

## Method

1. **Golden suite** of representative tasks with expected tool/agent trajectories.
2. **Trajectory eval** (LLM-as-judge + deterministic checks) over the call sequence, not just the final answer — the right answer reached via a wrong/unsafe path is a failure.
3. **Conformance harness** in CI for every protocol endpoint.
4. **Red-team set** of injected tool descriptions and adversarial resources.
5. **Load test** the transport (HTTP servers especially) at expected concurrency.

## Anti-Patterns

- Measuring only end-task success and ignoring the call path.
- No conformance gate → silent breakage when a server changes its schema.
- Treating latency of the handshake and per-call as the same budget.
- No injection/red-team evaluation for remote servers.
