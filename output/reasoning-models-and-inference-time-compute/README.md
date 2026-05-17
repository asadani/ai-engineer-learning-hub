# Reasoning Models & Inference-Time Compute

Principal-level interview prep notes on the 2025–26 reasoning-model shift — test-time compute, RLVR (DeepSeek-R1-style), extended/visible thinking, reasoning distillation, and the cost/latency economics that come with them.

Generated: 2026-05-17 (web-grounded)

---

## Contents

| # | File | Focus |
|---|------|-------|
| 1 | [High-Level Overview](1_High_Level_Overview.md) | What reasoning models are, the test-time-compute paradigm, the 2026 landscape |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | RLVR/GRPO, R1 training recipe, thinking budgets, opaque vs visible CoT, distillation, the compute paradox |
| 3 | [Products & Tools](3_Products_Tools.md) | o-series, DeepSeek-R1 family, extended thinking, open reasoning models, training stacks |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | Reasoning vs standard, RL vs distillation, more-compute-helps vs hurts, hosted vs open |
| 5 | [Use Cases](5_Use_Cases.md) | Math/code/science, agents, routing, when NOT to use reasoning |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | Reasoning evals, contamination, compute-vs-accuracy curves |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | Thinking-token cost, accuracy/latency, instrumentation |
| 8 | [Interview Questions](8_Interview_Questions.md) | Tiered Q&As (L5/L6/L7+) with model answers |

---

## Key Themes

### 1. Compute Moved From Training to Inference
The breakthrough: spend more compute *when answering* (longer chains of thought), not only during training. This is the core idea behind OpenAI o1/o3, DeepSeek-R1, and extended-thinking models.

### 2. Reasoning Can Emerge From Pure RL (DeepSeek-R1)
R1 showed chain-of-thought, self-correction, and step decomposition can emerge from **reinforcement learning with verifiable rewards (RLVR)** on a base model — no supervised CoT data required — then polished with SFT. It is open-weight (MIT) and matched o1-level reasoning.

### 3. Distillation Beats RL for Deployment Economics
Distilling R1's reasoning into small models (e.g., R1-Distill-Qwen) achieves strong reasoning at ~1/10 the GPU hours of RL — the practical path to affordable reasoning.

### 4. More Inference Compute Is Not Monotonically Better
The "test-time compute paradox": beyond a point, more thinking can *reduce* accuracy (overthinking, error accumulation). Thinking budget is a tunable parameter, not "more is better."

### 5. Reasoning Has a Cost Model of Its Own
Thinking tokens are billed and dominate spend/latency; opaque traces complicate debugging. Reserve reasoning models for tasks that need them; route everything else to standard models.
