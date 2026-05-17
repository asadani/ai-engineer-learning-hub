# LLM Observability & LLMOps

Principal-level interview prep notes on operating LLM applications in production — tracing, token/cost telemetry, online evals, and the **OpenTelemetry GenAI semantic conventions** that standardized the space in 2026.

Generated: 2026-05-17 (web-grounded)

---

## Contents

| # | File | Focus |
|---|------|-------|
| 1 | [High-Level Overview](1_High_Level_Overview.md) | LLMOps vs MLOps, why LLM apps need their own observability, the pillars |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | Traces/spans, OTel GenAI semconv, sessions, online vs offline eval, PII, cost attribution |
| 3 | [Products & Tools](3_Products_Tools.md) | Langfuse, Arize Phoenix, LangSmith, OpenInference, APM vendors |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | OTel-native vs proprietary, sampling, online vs offline eval, build vs buy |
| 5 | [Use Cases](5_Use_Cases.md) | Agent debugging, cost control, quality regression, incident response |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | What to trace, online eval design, drift |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | Metrics, OTel instrumentation, alerting, dashboards |
| 8 | [Interview Questions](8_Interview_Questions.md) | Tiered Q&As (L5/L6/L7+) with model answers |

---

## Key Themes

### 1. LLMOps Is Not MLOps Reskinned
MLOps watches a model's metrics. LLMOps watches a *non-deterministic application*: prompt versions, tool calls, agent trajectories, token cost, latency, and output quality with no ground-truth label at request time. Different failure surfaces, different telemetry.

### 2. The Trace Is the Unit of Truth
You cannot debug an agent from logs. You need a hierarchical trace: session → request → LLM spans → tool/retrieval spans, with inputs, outputs, tokens, and latency at each node. "Why did it do that?" is a trace question.

### 3. OpenTelemetry GenAI Conventions Ended the Lock-In (2026)
Langfuse, Phoenix, LangSmith, Datadog, New Relic, Dynatrace now speak the OTel **GenAI semantic conventions** (`gen_ai.*`, `gen_ai.agent.*`). Instrument once with OTel; switch backends without re-instrumenting. `gen_ai.client` spans are stable; agent spans are still experimental.

### 4. Quality Has No Free Label — Run Online Evals
Production has no ground truth at request time. LLMOps adds *online evaluation*: sampled LLM-as-judge scoring, user feedback, and heuristic checks, fed back as first-class telemetry.

### 5. Cost & PII Are Day-One Concerns
Token cost is a primary SLO; attribute it per feature/user/prompt-version. Prompts/outputs are PII-bearing; redaction and access control belong in the tracing layer, not bolted on later.
