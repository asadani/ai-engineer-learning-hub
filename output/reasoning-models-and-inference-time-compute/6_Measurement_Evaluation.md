# Measurement & Evaluation

## What "Good" Means

A reasoning deployment is good when it delivers the **accuracy lift the task needs at a justified thinking-token cost and latency**, on **contamination-resistant** evaluations — and when easy work is not paying reasoning overhead.

## Core Dimensions

### 1. Task Accuracy (vs a standard-model baseline)
Always measure reasoning against a standard-model baseline on the *same* suite. The question is not "is it good" but "is the accuracy lift worth the cost/latency for this task." No lift → don't use a reasoning model.

### 2. Accuracy-vs-Compute Curve
Sweep thinking budget / effort and plot accuracy vs reasoning tokens. Expect a hump (the test-time-compute paradox): find the budget at the knee, not the max. This curve is the central artifact for tuning a reasoning deployment.

### 3. Contamination Resistance
Reasoning benchmarks leak into training data, inflating scores. Prefer fresh/held-out and contamination-resistant sets (e.g., ARC-AGI-style novel tasks, dated private evals). Treat headline benchmark numbers skeptically; evaluate on your own fresh tasks.

### 4. Cost & Latency
Thinking tokens dominate. Measure cost and p95 latency *per successful task*, and the blended cost under your routing policy — the metric that actually governs viability.

### 5. Reasoning Quality (where visible)
For visible-trace models, optionally judge trace validity (sound steps, no unfaithful reasoning). For opaque models you can only evaluate final-answer correctness + calibration.

### 6. Overthinking / Calibration
Track cases where more thinking lowered accuracy or where the model abandoned a correct interim answer. Measure confidence calibration to drive routing/abstention.

## Method

1. Fixed suite with a **standard-model baseline** for lift attribution.
2. **Thinking-budget sweep** → accuracy-vs-compute curve → pick operating budget.
3. **Fresh/contamination-resistant** evaluation sets; rotate them.
4. Cost & latency **per successful task**, plus blended cost under routing.
5. For agents: reasoning-as-planner trajectory eval (see *Evals in AI*, *Agentic Design Patterns*).
6. Gate model/budget changes in CI on accuracy *and* cost.

## Anti-Patterns

- Reporting benchmark accuracy without a standard-model baseline (no lift attribution).
- Trusting public reasoning leaderboards (contamination).
- Max thinking budget without the accuracy-vs-compute curve (overthinking + cost).
- Ignoring cost/latency per successful task (the real viability metric).
- Evaluating only final answers when the trace is visible and debuggable.
