# Key Technical Concepts

## Traces, Spans, Sessions

- **Span** — one unit of work (an LLM call, a tool call, a retrieval) with start/end, status, and attributes (model, tokens, latency, I/O).
- **Trace** — the tree of spans for one request (e.g., agent request → 4 LLM spans + 3 tool spans + 2 retrieval spans).
- **Session** — a sequence of traces for one user conversation/agent run; the right granularity for multi-turn debugging and long-horizon analysis.

You cannot debug a multi-step agent from flat logs — the hierarchical trace is the unit of truth.

## OpenTelemetry GenAI Semantic Conventions

A standard vocabulary so traces are portable:

- **`gen_ai.client` span** (stable) — one per LLM round-trip. Attributes: `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`, `gen_ai.request.temperature`.
- **`gen_ai.agent` span** (experimental) — one per agent invocation: `gen_ai.agent.name`, `gen_ai.agent.id`, `gen_ai.agent.description`.
- **Tool / vector spans** — `execute_tool` with `gen_ai.tool.name`; vector-query spans for retrieval.
- **Stability opt-in** — `OTEL_SEMCONV_STABILITY_OPT_IN` enables dual-emission of legacy + new attribute names during the experimental→stable transition (production migration safety).

Instrument once to these conventions; backends (Langfuse, Phoenix, Datadog, New Relic, Dynatrace) ingest natively.

## OpenInference

A complementary OTel-based convention (from the Phoenix ecosystem) for LLM/agent spans; widely supported and interoperable with the GenAI conventions. Practically: both are OTel; pick what your instrumentation libraries emit and ensure the backend speaks it.

## Online vs Offline Evaluation

| | Offline (pre-deploy) | Online (production) |
|---|---|---|
| Data | Curated golden set | Live sampled traffic |
| Label | Known | Absent → judge/heuristic/user feedback |
| Purpose | Gate releases | Detect drift/regression in the wild |

LLMOps requires **both**: offline evals gate prompt/model changes (see *Evals in AI*); online evals catch what the golden set didn't and provider-side model shifts.

## Online Evaluation Signals

- **LLM-as-judge** on sampled traces (faithfulness, helpfulness, policy) — cheap, scalable, but biased; calibrate and sample.
- **Heuristics/guardrail checks** — schema validity, refusal detection, PII leakage, toxicity, groundedness.
- **Implicit user feedback** — thumbs, edits, retries, abandonment (often the strongest real-world quality proxy).

## Cost Attribution

Token cost must be attributable: tag every trace with `feature`, `user/tenant`, `prompt.version`, `model`. This surfaces the classic wins — a feature silently using a frontier model where a small one suffices, a prompt that grew 5×, or runaway thinking-token cost on a reasoning model.

## PII & Governance in the Trace Layer

Prompts and outputs frequently contain PII. Redact or hash sensitive fields *before* export, enforce access control and retention on trace data, and never log raw secrets. This is a tracing-layer responsibility — retrofitting it after an incident is the common, expensive mistake.

## Provider-Side Drift

A hosted model can change under you (silent updates, deprecations). Pin/track `gen_ai.request.model` and version; monitor quality and behavior over time so a provider change is detected as a regression, not a mystery incident.

## The Through-Line

Structured hierarchical traces (OTel GenAI) + per-trace cost attribution + online eval signals + PII-safe governance = the ability to answer "what did it do, why, how much did it cost, and is it getting worse?" — which is the whole job.
