# Key Technical Concepts

## Test-Time / Inference-Time Compute

Allocate more compute at answer time to raise accuracy. Forms: longer chain-of-thought (sequential deliberation), sampling many candidates and selecting (parallel — best-of-N, self-consistency, verifier/reward-model reranking), and search (tree-of-thought style). The unifying claim: for hard problems, *spending tokens to think* substitutes for a larger model.

## RLVR — Reinforcement Learning with Verifiable Rewards

Train the model to reason by rewarding **verifiably correct outcomes** (math answer checks, unit tests pass) rather than human preference. **GRPO** (Group Relative Policy Optimization, used by DeepSeek-R1) estimates advantage from a *group* of sampled completions per prompt — no separate value/critic network — making large-scale RL on reasoning practical. (Cross-reference *Fine-Tuning LLMs* for GRPO vs PPO/DPO.)

## The DeepSeek-R1 Recipe (worth knowing precisely)

1. **Pure RL on the base model** (R1-Zero): rewarding correctness, chain-of-thought, self-reflection, and step decomposition **emerged spontaneously** — no supervised CoT data.
2. **Cold-start SFT + RL** (R1): a small curated reasoning SFT pass improved readability/consistency, then further RL. Result: o1-level reasoning, open weights (MIT), visible `<think>` traces.
Significance: reasoning is an RL-elicitable capability of the base model, not solely a data-distillation artifact.

## Reasoning Distillation

Generate high-quality reasoning traces from a large reasoner (e.g., R1-0528 671B) and SFT a small model on them. Distilled small models (R1-Distill-Qwen-8B, etc.) achieve strong reasoning at **~1/10 the GPU hours of RL** — empirically distillation > running RL directly on the small model. This is the deployment-economics path: train reasoning once (big), serve it cheap (small).

## Thinking Budget

A controllable cap on reasoning tokens before the model must answer (extended-thinking models expose this; effort levels low/med/high on others). It's the primary cost/latency/accuracy dial: too low → underthinks hard problems; too high → cost blowup and overthinking. Tune per task class; don't leave at max.

## Opaque vs Visible Reasoning

- **Opaque** (o-series): the full trace is hidden (safety, anti-distillation, UX). You see a summary/that-it-thought. Harder to debug; can't be used as supervision.
- **Visible** (R1, `<think>`): the trace is in the output — debuggable, distillable, but consumes context/tokens and can leak unsafe intermediate content.

## The Test-Time-Compute Paradox

More inference compute is **not monotonically better**. Beyond a problem-dependent point, longer reasoning can *reduce* accuracy: overthinking simple problems, accumulating errors across a long chain, or talking itself out of a correct answer. Implication: scaling thinking is a tunable, evaluated decision per task — not "crank it up."

## Reasoning vs Agents

Reasoning is *internal* deliberation within one model call; agentic loops are *external* multi-step tool use. They compose: a reasoning model is often the controller of an agent. But internal reasoning ≠ agency — and the compounding-error logic applies to long external loops, not the internal trace.

## The Through-Line

Move compute to inference (think longer) → elicit it cheaply via RLVR/GRPO and distillation → expose it as a tunable thinking budget → respect the paradox (more ≠ better) → pay for it in tokens/latency/opacity, so use reasoning models *only* where the task needs them.
