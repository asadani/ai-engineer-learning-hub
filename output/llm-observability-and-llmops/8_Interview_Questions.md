# Interview Questions & Scenarios

## L5 — Foundations

**Q1. How is LLMOps different from MLOps?**
MLOps operates a trained model and watches data/concept drift against eventually-available labels. LLMOps operates a *non-deterministic application* — prompts, tools, agents — whose failures are bad trajectories, hallucination, tool misuse, cost blowups, and prompt regressions, usually with **no ground truth at request time**. Telemetry differs: hierarchical traces + token/cost attribution + online evaluation, not feature/prediction distributions.

**Q2. Why isn't standard APM enough for an LLM app?**
APM sees HTTP 200 and latency; it cannot see that the answer was confidently wrong, that the agent took a 14-step detour, or that token cost 5×'d after a prompt tweak. You need a hierarchical trace (session→request→LLM/tool/retrieval spans) with I/O, tokens, and quality signals to answer *why*.

**Q3. What changed with OpenTelemetry GenAI conventions in 2026?**
They standardized span names/attributes (`gen_ai.*`, `gen_ai.agent.*`) so tracing is portable: instrument once, send to Langfuse/Phoenix/Datadog/New Relic/Dynatrace with no SDK change. `gen_ai.client` spans are stable; agent spans are experimental — use `OTEL_SEMCONV_STABILITY_OPT_IN` for safe migration. It ended proprietary-format lock-in.

## L6 — Design & Tradeoffs

**Q4. Design observability for a multi-step agent platform.**
OTel GenAI instrumentation: session→request root with feature/user/prompt-version/model; `gen_ai.client` spans (tokens, finish, latency); `execute_tool` spans (args/result redacted); retrieval spans (query, chunk ids/scores); agent spans (step, state). Tail-based sampling (keep all errors/slow/flagged, sample full I/O). Always-on guardrail checks + sampled LLM-judge + user feedback as trace-attached scores. Dashboards + SLO alerts on quality/cost/latency/safety; PII redaction at the export boundary.

**Q5. There's no label in production — how do you monitor quality?**
Manufacture signal: (1) always-on heuristics (schema validity, refusal, PII, groundedness); (2) sampled LLM-as-judge with a calibrated rubric and bias controls; (3) implicit user feedback (thumbs/edits/retries/abandonment), often the strongest proxy. Attach all as telemetry; alert on trends segmented by prompt/model version. Offline evals still gate releases — online catches the rest.

**Q6. Full capture vs sampling — what do you actually do?**
Capture all lightweight metadata (tokens, latency, versions) always. Tail-sample full prompt/response I/O and LLM-judge evals — but always retain error/slow/flagged traces. This bounds storage/cost while guaranteeing the traces you need for incidents are kept.

## L7+ — Principal

**Q7. Cost suddenly doubled. Use observability to find and fix it.**
Pull cost attributed by feature/user/prompt.version/model. Typical culprits surface immediately: a feature defaulting to a frontier model, a reasoning model's thinking tokens exploding, a prompt that grew, or a retry storm. Fix is targeted — route to a smaller model, cap thinking budget, trim prompt, fix retries — verified by the cost-by-version panel returning to baseline. A blunt global rate limit is the wrong, non-diagnostic response.

**Q8. How do you detect that the hosted model changed under you?**
Key quality metrics and behavioral checks to `gen_ai.request.model`/version and trend them. A provider-side update shows as a dated step-change in judge score, refusal rate, latency, or output shape — an alert, not a mystery. Mitigation: pin/version where possible, re-run offline evals, and roll forward deliberately. Without model-version-keyed monitoring this is an unexplained incident.

**Q9. Justify OTel-native instrumentation over a best-of-breed vendor SDK.**
Vendor SDKs create re-instrumentation cost and lock-in when you outgrow or consolidate them. OTel GenAI conventions make the backend swappable (OSS Phoenix/Langfuse today, corporate Datadog tomorrow) with zero code change, and are natively ingested across the ecosystem. You give up a few vendor-unique features for portability and longevity — the right principal-level trade in a fast-moving market. Adopt a vendor *backend*, not a vendor *format*.

## Rapid-Fire

- *Unit of truth for agent debugging?* The hierarchical trace/session.
- *Which GenAI spans are stable in 2026?* `gen_ai.client`; agent spans experimental.
- *No label in prod — quality signal?* Heuristics + sampled judge + user feedback.
- *Sampling strategy of choice?* Tail-based (keep errors/slow/flagged).
- *Instrument to a vendor or a standard?* The standard (OTel GenAI).
