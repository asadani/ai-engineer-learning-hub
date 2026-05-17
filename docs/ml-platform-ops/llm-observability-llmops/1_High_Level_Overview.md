# High-Level Overview

## What It Is

**LLM observability** is the practice of capturing, structuring, and analyzing the runtime behavior of LLM applications — every prompt, completion, tool call, retrieval, token count, latency, cost, and quality signal — so you can debug, control cost, detect regressions, and prove reliability. **LLMOps** is the broader operational discipline around it: prompt/version lifecycle, online evaluation, deployment, rollback, and incident response for non-deterministic AI systems.

## LLMOps vs MLOps (the distinction interviewers probe)

| | MLOps | LLMOps |
|---|---|---|
| Unit | A trained model | A non-deterministic *application* (prompts, tools, agents) |
| Core failure | Data/concept drift, accuracy decay | Bad trajectory, hallucination, tool misuse, cost blowup, prompt regression |
| Ground truth | Eventually available (labels) | Usually absent at request time |
| Telemetry | Feature/prediction distributions | Hierarchical traces + token/cost + online eval |
| Change unit | Retrained model | Prompt/model/tool version |

LLMOps is not MLOps with a new logo: the system is stochastic, multi-step, and label-poor. (See *MLOps* and *Evals in AI* for the adjacent disciplines.)

## The Core Problem It Solves

An LLM app fails in ways traditional APM can't see: it returns a *confident wrong answer* with HTTP 200, takes a bizarre 14-step agent path, silently 5×'s token cost after a prompt tweak, or regresses when the provider updates the model. Request logs don't explain *why*. Observability makes the model's decision process inspectable and measurable.

## The Pillars

1. **Tracing** — hierarchical spans: session → request → LLM call(s) → tool/retrieval calls, with I/O, tokens, latency, model/prompt version at each node.
2. **Cost & token telemetry** — per request and attributed to feature/user/prompt-version; cost is a first-class SLO.
3. **Online evaluation** — sampled quality scoring in production (LLM-as-judge, heuristics, user feedback) because there's no label at request time.
4. **Quality & drift monitoring** — track scores, refusal/hallucination rates, latency, and provider-side model changes over time.
5. **Governance** — PII redaction, access control, prompt-version binding, audit.

## The 2026 Inflection: OpenTelemetry GenAI Semantic Conventions

Historically Langfuse, Helicone, LangSmith each used incompatible proprietary trace formats → vendor lock-in. The OTel GenAI SIG standardized span names and attributes for LLM calls, agent steps, vector queries, token usage, and cost. As of 2026, `gen_ai.client` spans are **stable**; `gen_ai.agent` spans are **experimental**. Datadog, New Relic, Dynatrace, Langfuse, and Phoenix consume them natively, so OTel-instrumented code reports to any backend without SDK changes. This is the single most important structural change in the space — instrument to the standard, not to a vendor.

## Where It Sits

Observability wraps every other layer: it traces prompt engineering (which version ran), RAG (what was retrieved), agents/protocols (which tools/A2A tasks), reasoning models (thinking-token cost), and feeds evals. It is the nervous system of a production AI system.
