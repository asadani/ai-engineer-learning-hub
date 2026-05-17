# High-Level Overview

## What AI Evals Are

Evals (evaluations) are systematic methods for measuring the quality, safety, and behavior of AI systems — particularly language models, RAG pipelines, agents, and other generative AI applications. They are the AI equivalent of software testing: a structured feedback loop that tells you whether your system is working correctly, improving, or regressing.

Unlike traditional software tests where behavior is deterministic and outputs are exact-match verifiable, LLM outputs are probabilistic, context-sensitive, and often evaluated on subjective dimensions (helpfulness, fluency, groundedness). This makes eval design substantially harder — and more important.

**Core purpose of evals**:
1. **Model selection**: which foundation model (or fine-tune) best fits your use case
2. **Regression detection**: did a prompt change, model upgrade, or retrieval change break something
3. **Production monitoring**: are live user interactions meeting quality thresholds
4. **Safety and alignment**: does the system behave correctly at the boundaries of intended use
5. **Comparative benchmarking**: how does your system compare to a baseline or competitor

## The Eval Problem Is Harder Than It Looks

A survey of production GenAI failures (2023–2025) shows the overwhelming majority were detectable with evals — but weren't caught because eval infrastructure wasn't in place. The common failure mode: teams ship a RAG or agent feature with a qualitative "it looks good" review, discover regressions in production, and have no systematic way to trace the root cause.

The fundamental challenge: **there is no ground truth for "good"** in most open-ended generation tasks. "Correct" for a legal clause summary is not the same as "correct" for a customer support answer. Eval design requires explicit operationalization of quality for each task.

## Taxonomy of Evals

```
                        EVAL TYPES
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
     OFFLINE              ONLINE           HUMAN
   (pre-deploy)        (production)       (labeling)
          │
    ┌─────┴──────┐
    ▼            ▼
Automated      LLM-as-Judge
(rule-based,   (GPT-4o/Claude
 exact-match,   as evaluator)
 embedding)
```

| Type | When | Latency | Cost | Reliability |
|------|------|---------|------|-------------|
| **Exact-match / rule-based** | Offline + online | μs | Near-zero | Deterministic |
| **Embedding similarity** | Offline + online | ms | Low | High for semantic |
| **LLM-as-judge** | Offline + sampled online | 200ms–2s | Medium | High if calibrated |
| **Human evaluation** | Offline, periodic | Days–weeks | High | Gold standard |
| **Behavioral / adversarial** | Offline | Varies | Medium | Task-specific |

## The Eval Pyramid

Borrowed from software testing, adapted for AI:

```
         ▲ Human preference studies (most expensive, most authoritative)
        ╱ ╲
       ╱   ╲  LLM-as-judge (automated, scalable, semi-reliable)
      ╱─────╲
     ╱       ╲  Metric-based evals (BLEU, ROUGE, BERTScore, RAGAS)
    ╱─────────╲
   ╱           ╲  Unit-level tests (exact-match, regex, schema validation)
  ╱─────────────╲ (most automated, cheapest, least coverage)
```

Run unit-level tests on every deployment. Run metric-based evals on every significant change. Run LLM-as-judge on a representative sample continuously. Run human evals quarterly or for major releases.

## 2025–2026 Landscape Shift

Three major shifts define the current eval landscape:

1. **LLM-as-judge became mainstream**: GPT-4o and Claude as evaluators achieve >85% agreement with human raters on most tasks. The cost is now tractable. Most production teams use LLM-as-judge as their primary quality signal.

2. **Agent evals became a first-class problem**: Single-turn Q&A evals are well-understood. Multi-step agent trajectories — planning, tool use, error recovery — are still an open research problem. Frameworks like LangSmith, Braintrust, and AgentEval are early.

3. **Online evals (production monitoring) replaced offline benchmarks** as the primary signal for teams with real user traffic. Offline benchmark performance is a weak predictor of production quality for task-specific applications.

## Why Evals Fail in Practice

1. **Eval dataset doesn't match production distribution** — golden datasets sampled at launch, never updated as user behavior shifts
2. **LLM-as-judge prompt not calibrated** — judge gives high scores to fluent but wrong answers (sycophancy bias)
3. **Metrics not operationalized** — "quality" is measured but never defined; scores don't map to user outcomes
4. **No baseline** — scores are measured but there's no baseline to compare against, so regressions are invisible
5. **Evals run manually, not in CI/CD** — eval results accumulate in spreadsheets, not in automated gates
