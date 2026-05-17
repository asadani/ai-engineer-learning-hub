# Products & Tools

## LLM-Native Observability Platforms

| Tool | Strengths | Notes |
|---|---|---|
| **Langfuse** | Open-source, tracing + prompt mgmt + evals; OTel GenAI-compliant | Self-host or cloud; strong all-rounder |
| **Arize Phoenix** | Open-source, OTel-native (OpenInference); tracing + evals; grew significantly in 2026 | Portable; pairs with Arize AX for scale |
| **LangSmith** | Deep LangChain/LangGraph integration; datasets + evals | Best if you're in the LangChain stack |
| **Helicone / Traceloop / Portkey** | Gateway-style logging, caching, cost | Proxy-based capture, low code change |

## Standards / Instrumentation Libraries

| Tool | Role |
|---|---|
| **OpenTelemetry GenAI semantic conventions** | The standard `gen_ai.*` span/attribute vocabulary |
| **OpenInference** | OTel-based LLM/agent span convention (Phoenix ecosystem) |
| OpenLLMetry / OTel auto-instrumentation | Drop-in instrumentation emitting GenAI spans |

## General APM (now GenAI-aware)

| Tool | Role |
|---|---|
| **Datadog / New Relic / Dynatrace** | Native GenAI semconv support — OTel-instrumented agents report with no SDK change; unify with infra/APM |

## Adjacent

- **Prompt management** — Langfuse/LangSmith (bind traces to prompt versions; see *Prompt Engineering*).
- **Eval frameworks** — RAGAS, UK AISI Inspect, OpenAI Evals for the offline gate (see *Evals in AI*).

## Selection Guidance

- Want portability / no lock-in → instrument with **OTel GenAI conventions**; pick any compliant backend.
- Open-source, self-hosted, all-in-one → **Langfuse** or **Phoenix**.
- Deep LangChain/LangGraph app → **LangSmith**.
- Already standardized on Datadog/New Relic/Dynatrace → use their native GenAI support; don't add a silo.
- Minimal code change, gateway pattern → Helicone/Portkey/Traceloop.
- Principle: **instrument to the standard, choose the backend second** — the 2026 conventions make the backend swappable.
