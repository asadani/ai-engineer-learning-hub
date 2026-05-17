# Measurement & Evaluation

## What "Good" Means

A good prompt has a **high, stable pass rate on a held-out, labeled set representative of real inputs** — not a good demo. "It works" must mean a measured number.

## Evaluation Dimensions

### 1. Task Quality
Use the metric that matches the task: exact-match/field-F1 (extraction), precision/recall/F1 (classification), faithfulness/groundedness (RAG synthesis), rubric score via calibrated LLM-judge (open-ended). See *Precision, Recall, F1 & AI Metrics* and *Evals in AI*.

### 2. Prompt Sensitivity / Robustness
Re-run the eval across paraphrases of the prompt, reordered few-shot examples, and shifted input distributions. Report variance, not just the mean. A prompt that scores 0.92 once but 0.78 on a paraphrase is not production-ready.

### 3. Format Compliance
Fraction of outputs that satisfy the schema/contract without repair. With constrained output this should be ~100%; anything less indicates a decoding or contract problem.

### 4. Safety Behavior
Refusal correctness (refuses what it should, doesn't over-refuse), injection resistance for prompts that ingest untrusted text, and abstain-path correctness ("unknown → null/needs_human").

### 5. Cost / Latency
Tokens (esp. few-shot and reasoning/thinking tokens) and latency per successful task — a slightly lower-quality, far cheaper prompt is often the right production choice.

## Method

1. **Build a labeled dataset** from real inputs (include hard/edge/adversarial cases), held out from iteration.
2. **Define the metric up front** (task-appropriate, automatic where possible; calibrated LLM-judge otherwise).
3. **Iterate against the set**, not the playground; track every prompt version's score.
4. **Regression-gate in CI**: a prompt change that drops the suite below threshold blocks deploy.
5. **Sensitivity sweep** before shipping high-stakes prompts.
6. **Monitor in production** (sampled outputs scored offline) for drift.

## Anti-Patterns

- "Looks good in the playground" as the bar.
- Iterating on the same examples you evaluate on (overfitting the prompt).
- Reporting a single number with no sensitivity/variance.
- No CI regression gate → silent quality regressions on prompt edits.
- Judge prompt itself unevaluated → corrupted metrics.
