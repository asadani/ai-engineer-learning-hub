# High-Level Overview

## What It Is

A **reasoning model** (a.k.a. Large Reasoning Model, LRM) is an LLM trained to spend deliberate intermediate computation — an extended chain of thought — *before* committing to an answer. **Inference-time compute** (test-time compute) is the underlying paradigm: allocate more computation when the model generates its answer, not only during pre-training, to dramatically improve performance on hard math, code, science, and logic.

## The Paradigm Shift

Classic scaling improved models by adding training compute and data. Reasoning models add a second axis: **think longer at inference**. A model that produces a long internal reasoning trace, self-checks, and backtracks can solve problems a same-size standard model cannot — by trading latency and tokens for accuracy at answer time. This is the central idea behind OpenAI's o1/o3, DeepSeek-R1, and Anthropic-style extended thinking.

## The 2026 Landscape

- **OpenAI o-series (o1 → o3)** — frontier reasoning; o3 set new marks on ARC-AGI, math, code, science. Reasoning trace is **opaque** (users see that it thinks, not the full trace) — a deliberate safety/IP choice.
- **DeepSeek-R1** — open-weight (MIT), **visible** chain-of-thought in `<think>` tags; matched o1-level reasoning; proved reasoning can emerge from pure RL.
- **Extended-thinking models (e.g., Claude 3.7-style)** — *hybrid*: developer-controllable thinking budget, instant vs deep on demand.
- **Open reasoning ecosystem** — distilled small reasoners (R1-Distill-Qwen, etc.) bring reasoning to commodity hardware.

## The Core Problem It Solves

Standard next-token models are weak at multi-step problems requiring planning, verification, and backtracking — they commit early and can't easily recover. Reasoning models internalize "work it out, check, revise" so accuracy on hard tasks rises substantially without a bigger base model.

## The Catch (why this is a principal-level topic)

1. **Cost/latency**: thinking tokens are generated and billed; a reasoning answer can cost and take 5–50× a standard one.
2. **The test-time-compute paradox**: more thinking is not monotonically better — beyond a point, accuracy can *decline* (overthinking, compounding intermediate errors). Thinking budget is a tuned parameter.
3. **Opacity**: opaque traces (o-series) limit debuggability; visible traces (R1) help but lengthen context.
4. **Misuse**: applying a reasoning model to simple tasks wastes money and adds latency for no quality gain.

## Where It Sits

Reasoning models are a model *class*, not a separate stack. They interact with: prompt engineering (don't hand-author CoT — see *Prompt Engineering*), fine-tuning (RLVR/distillation — see *Fine-Tuning LLMs*), serving (disaggregation for long decode — see *LLM Serving & Inference*), cost (thinking-token economics — see *Cost Optimization*), and evals (contamination-resistant reasoning benchmarks — see *Evals in AI*).
