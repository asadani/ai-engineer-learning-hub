# Measurement & Evaluation

## What "Good" Means

A well-observed LLM system can answer, for any request: **what did it do, why, how long, how much did it cost, and is quality trending down?** — with traces and metrics, not speculation.

## What to Trace (minimum viable)

Per request, a hierarchical trace with:
- Root: session id, user/tenant, feature, prompt name+version, model+version.
- `gen_ai.client` spans: input/output (redacted), input/output tokens, finish reason, latency, temperature.
- Tool spans (`execute_tool`): tool name, args/result (redacted), success, latency.
- Retrieval spans: query, returned chunk ids/scores (for RAG debugging).
- Agent spans: agent name/id, step index, state transitions.

If you can't reconstruct the decision path from the trace, you haven't traced enough.

## Online Evaluation Design

Production has no request-time label, so manufacture quality signal:

1. **Heuristics/guardrails (100%)** — schema validity, refusal/abstain detection, PII/toxicity scan, groundedness check.
2. **LLM-as-judge (sampled)** — rubric scoring (faithfulness, helpfulness, policy) on a representative sample; calibrate against human labels; control position/verbosity bias.
3. **Implicit user feedback (100% where available)** — thumbs, edits, retries, abandonment; often the best real-world quality proxy.

Feed all three back as telemetry attached to traces so quality is queryable alongside cost/latency.

## Drift & Regression

- **Quality drift** — judge score / feedback trend by prompt and model version.
- **Provider drift** — behavior change keyed to `gen_ai.request.model`.
- **Cost/latency drift** — tokens and p95 by version (catches silent prompt bloat / model swaps).
- **Distribution drift** — input mix shifting away from your eval set's coverage.

## Method

1. Instrument to OTel GenAI conventions (stability opt-in for safe migration).
2. Bind every trace to feature/user/prompt-version/model.
3. Always-on heuristics + sampled judge + user feedback as trace-attached scores.
4. Tail-based sampling for full I/O (keep all errors/slow/flagged).
5. Offline eval gate in CI (see *Evals in AI*); online eval for drift.
6. Dashboards + SLO alerts on quality, cost, latency, safety.

## Anti-Patterns

- Logs/APM only (no trace tree) — undebuggable agents.
- No online eval — silent quality/provider regressions.
- Uncalibrated judge — corrupted quality metric.
- Full-capture everything — cost blowup; or sample-everything — lose the trace you need (use tail sampling).
- PII unredacted in traces — compliance incident.
