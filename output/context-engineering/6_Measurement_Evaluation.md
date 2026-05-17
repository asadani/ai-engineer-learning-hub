# Measurement & Evaluation

## What "Good" Means

Good context engineering maximizes **task success per token**: the model gets what it needs (high recall of critical info), little of what it doesn't (high context precision), at the lowest token/latency cost, stably across long horizons.

## Evaluation Dimensions

### 1. Context Precision / Recall
Borrow RAG metrics: of the context provided, what fraction was relevant (precision); of the information needed, what fraction was present (recall). **RAGAS** operationalizes context precision/recall and faithfulness. Low precision → curation problem; low recall → selection/retrieval problem.

### 2. Recall Under Length (lost-in-the-middle test)
Inject a known fact at varying positions (start/middle/end) across increasing context lengths; measure retrieval accuracy by position. This quantifies your placement strategy and where degradation begins.

### 3. Task Success vs Token Budget
Plot task success against context size for a strategy. The goal is the knee of the curve — minimum tokens at acceptable quality — not maximum tokens. Compare strategies (truncate / summarize / retrieve / compress) on the same task suite.

### 4. Long-Horizon Stability
For agents: success rate as a function of turn count. A strategy that's fine at 10 turns and collapses at 80 has a compaction/memory failure. Measure where success degrades and whether compaction events cause regressions.

### 5. Compaction Fidelity
After a compaction event, does the agent still know the goal, constraints, and prior decisions? Probe with targeted questions post-compaction; track "post-compaction regression" rate.

## Method

1. **Golden tasks** with known required facts and expected outcomes.
2. **Position sweep** for lost-in-the-middle characterization.
3. **Strategy A/Bs** (truncate vs summarize vs retrieve vs compress) on identical suites — judge task success + tokens, never tokens alone.
4. **Long-run simulations** (50–300 turns) measuring success vs turn and post-compaction probes.
5. **RAGAS** for the retrieval/context-precision component.

## Anti-Patterns

- Optimizing token reduction without re-measuring task success.
- Evaluating only short conversations (hides compaction failures).
- No position/length characterization (blind to lost-in-the-middle).
- Treating a passing demo as evidence of long-horizon stability.
