# Interview Questions & Scenarios

## L5 — Foundations

**Q1. What is inference-time (test-time) compute and why did it matter?**
Allocating more computation when the model *answers* — longer chain-of-thought, sampling+selection, search — rather than only at training time. It mattered because spending tokens to deliberate substitutes for a larger base model on hard math/code/science/logic; it's the core idea behind o1/o3, DeepSeek-R1, and extended-thinking models.

**Q2. What did DeepSeek-R1 demonstrate?**
That reasoning (chain-of-thought, self-correction, step decomposition) can **emerge from pure reinforcement learning with verifiable rewards** on a base model — no supervised CoT data — then be polished with a small SFT pass. It matched o1-level reasoning, is open-weight (MIT), and exposes a visible `<think>` trace, proving reasoning is an RL-elicitable base-model capability.

**Q3. Reasoning model vs standard model — when each?**
Reasoning: hard multi-step math/code/science/planning where accuracy lift justifies 5–50× cost/latency. Standard: extraction, classification, chat, retrieval-grounded Q&A, latency-critical paths — most production traffic. Default standard; escalate on measured need.

## L6 — Design & Tradeoffs

**Q4. Explain the test-time-compute paradox and its engineering implication.**
More inference compute is not monotonically better — beyond a problem-dependent point, longer reasoning can *reduce* accuracy (overthinking simple problems, error accumulation, abandoning a correct interim answer). Implication: thinking budget is a tuned parameter. You produce an accuracy-vs-compute curve per task class and operate at the knee, not the max — and you alert on rising thinking tokens without accuracy gain.

**Q5. RLVR vs distillation for shipping a reasoning capability.**
RLVR/GRPO *creates* reasoning capability and can exceed any teacher, but is compute-expensive. Distillation (SFT a small model on a big reasoner's traces) reaches ~teacher quality at ~1/10 the GPU hours and is empirically better than running RL directly on a small model. Principal answer: RL to build the capability once (large), distill to deploy it economically (small).

**Q6. Design a cost-efficient deployment that needs reasoning only on hard queries.**
Difficulty-based routing: a cheap classifier (or confidence/verifier signal) sends easy traffic to a standard model and the hard tail to a reasoning model (or escalates on low confidence / verifier failure). Tune thinking budget via the accuracy-vs-compute curve; attribute reasoning tokens in telemetry; alert on escalation-rate and blended cost. This delivers reasoning-level accuracy on the tail at a fraction of all-reasoning cost.

## L7+ — Principal

**Q7. A team reports their reasoning model "isn't better" than the old model and costs 20×. Diagnose.**
Check: (a) Is the task actually reasoning-bound? If it's extraction/classification, no lift is expected — wrong tool. (b) Thinking budget — too low underperforms; too high overthinks. Produce the accuracy-vs-compute curve. (c) Prompting — hand-authored CoT/heavy few-shot can derail reasoning models; use goal/constraints only. (d) Eval contamination masking real differences. The likely outcome: route reasoning to the hard subset only, tune budget to the knee — turning "20× for nothing" into "targeted lift at controlled cost."

**Q8. How do you trust reasoning benchmark numbers?**
Skeptically. Reasoning benchmarks leak into training data, inflating scores. Require a standard-model baseline on the *same* suite for lift attribution, evaluate on fresh/contamination-resistant tasks (ARC-AGI-style novelty, dated private sets), rotate sets, and weight your own held-out tasks over public leaderboards. A headline score without a baseline and contamination control is marketing, not evidence.

**Q9. Opaque vs visible reasoning traces — operational implications?**
Opaque (o-series): can't debug or distill from the trace, but it can't leak unsafe intermediate content and is anti-distillation; you evaluate final-answer correctness + calibration only. Visible (R1): debuggable and distillable, but consumes context/tokens and can surface unsafe interim text needing guardrails. Choose per need: regulated/debuggable/on-prem → visible (R1); frontier accuracy with opacity acceptable → o-series. Either way, instrument reasoning tokens as a first-class cost metric.

## Rapid-Fire

- *Second scaling axis?* Test-time compute (think longer at inference).
- *R1's training signal?* Verifiable rewards (RLVR), via GRPO.
- *Cheaper: RL or distillation to deploy?* Distillation (~1/10 GPU hours).
- *More thinking always better?* No — humped curve (the paradox).
- *Prompt a reasoning model how?* Goal/constraints/output; no hand-written CoT.
- *Main cost driver?* Thinking/reasoning tokens.
