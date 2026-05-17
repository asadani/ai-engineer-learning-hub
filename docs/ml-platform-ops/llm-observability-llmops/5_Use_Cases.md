# Use Cases & Real-World Applications

## 1. Debugging a Misbehaving Agent

An agent gives a wrong answer via a weird path. With session→request→span traces you replay the exact tool calls, arguments, retrieved chunks, and intermediate LLM outputs, and localize the failing step (bad tool selection? poisoned retrieval? lost-in-the-middle?). Outcome: root cause in minutes, not a guessing game over logs.

## 2. Cost Control / FinOps for AI

Spend doubles overnight. Cost attribution (per feature/user/prompt-version/model) shows a feature defaulted to a frontier model, or a reasoning model's thinking tokens exploded, or a prompt grew 5×. Outcome: targeted fix (route to a smaller model, cap thinking budget, trim prompt) instead of a blunt rate limit. (See *Cost Optimization*.)

## 3. Catching a Prompt Regression in CI + Prod

A prompt edit passes locally but regresses an edge segment. Offline eval gate catches most; online eval (sampled LLM-judge + user-feedback delta) catches the rest within hours, bound to `prompt.version` for instant rollback by label. Outcome: bounded blast radius on prompt changes.

## 4. Detecting Provider-Side Model Drift

A hosted model is updated by the provider; behavior shifts silently. Tracking quality scores and behavior by `gen_ai.request.model` over time turns this from a mystery incident into a dated regression alert. Outcome: detection and mitigation (pin/version, re-evaluate) before users escalate.

## 5. Incident Response

A spike in failures/latency. Tail-sampled error traces + dashboards (success, latency p95, judge score, cost) localize whether it's a tool outage, retrieval degradation, model latency, or a bad deploy. Outcome: MTTR measured in minutes; postmortem grounded in traces.

## 6. Multi-Backend Portability

Start on open-source Phoenix/Langfuse; later consolidate into the org's Datadog. Because instrumentation uses OTel GenAI conventions, the backend swap requires no code change. Outcome: no re-instrumentation tax, no lock-in.

## Pattern Summary

| Need | Capability |
|---|---|
| Root-cause an agent | Hierarchical session/trace replay |
| Control spend | Per-dimension cost attribution |
| Safe prompt/model changes | Offline gate + online eval + version binding |
| Catch provider drift | Quality-by-model-version monitoring |
| Fast incident response | Tail sampling + SLO dashboards |
| No lock-in | OTel GenAI instrumentation |
