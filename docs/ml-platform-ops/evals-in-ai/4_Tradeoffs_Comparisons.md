# Tradeoffs & Comparisons

## Human Eval vs. LLM-as-Judge vs. Rule-Based

The most consequential eval design decision.

| Dimension | Human Eval | LLM-as-Judge | Rule-Based / Metrics |
|-----------|-----------|--------------|---------------------|
| **Reliability** | Gold standard | High if calibrated (85–90% agreement) | Deterministic; limited coverage |
| **Cost** | $1–20/annotation | $0.001–0.01/eval | Near-zero |
| **Speed** | Days–weeks | Seconds | Milliseconds |
| **Scale** | Hundreds–thousands | Millions | Unlimited |
| **Subjectivity** | High (needs guidelines) | Medium (bias-prone without calibration) | None |
| **Coverage** | Any dimension | Any dimension | Only measurable properties |
| **Reproducibility** | Low (inter-annotator variance) | Medium (temperature + model drift) | Perfect |
| **Best for** | Final quality gate, calibrating LLM judges | Production sampling, A/B testing, CI | Exact match, schema, safety filters |

**Production recommendation**: Use all three in layers. Rule-based as the first gate (schema valid, no PII leaked, no toxicity). LLM-as-judge for quality on a 5–10% sample of production traffic. Human eval quarterly on a stratified 200-sample dataset to recalibrate the LLM judge and detect drift.

---

## Offline Evals vs. Online Evals

| Dimension | Offline (Pre-deploy) | Online (Production Sampling) |
|-----------|---------------------|------------------------------|
| **Timing** | Before deployment | Continuously in production |
| **Coverage** | Eval dataset only | Real user queries |
| **Distribution** | May not match production | Exact production distribution |
| **Ground truth** | Available (labeled) | Usually unavailable (implicit signals only) |
| **Latency tolerance** | High (batch job) | Low (sampling, async eval) |
| **Signal for** | Regression prevention | Quality drift detection |
| **False security risk** | High (overfits to eval set) | Low |

**The key insight**: Offline evals protect against known regressions; online evals catch unknown distribution shifts. Both are required. A system that scores 0.92 RAGAS faithfulness on the offline eval set but 0.61 in production is a failure of the offline dataset, not the eval methodology.

---

## Reference-Based vs. Reference-Free: When Each Is Valid

| Scenario | Reference-Based | Reference-Free |
|----------|----------------|----------------|
| SQL generation | ✅ (execute both, compare results) | ❌ |
| Code generation | ✅ (unit tests pass/fail) | ❌ |
| Factoid Q&A | ✅ (exact or semantic match) | ❌ |
| Customer support response | ❌ (many valid responses) | ✅ (LLM-as-judge on helpfulness) |
| Document summarization | Partial (ROUGE is weak) | ✅ (faithfulness, coverage) |
| RAG answer | Partial (if reference exists) | ✅ (RAGAS metrics) |
| Creative writing | ❌ | ✅ (coherence, style rubric) |

**ROUGE/BLEU criticism**: These metrics measure n-gram overlap, not meaning. A response that uses synonyms throughout scores low on ROUGE despite being semantically equivalent. For modern LLM evaluation, BERTScore (semantic) or LLM-as-judge is almost always preferred over ROUGE/BLEU except as a cheap fast filter.

---

## Pointwise vs. Pairwise Evaluation

| Dimension | Pointwise (1–5 scale) | Pairwise (A vs. B) |
|-----------|----------------------|--------------------|
| **Use case** | Absolute quality monitoring | Comparative A/B (model selection, prompt A/B) |
| **Reliability** | Lower (scale interpretation varies) | Higher (relative judgment is easier) |
| **Scalability** | O(n) | O(n²) for all pairs; O(n) for specific comparisons |
| **Trend tracking** | Yes | No (no absolute score) |
| **LLM bias** | Verbosity bias | Position bias (swap and average to mitigate) |
| **Best for** | Monitoring quality over time | Choosing between two systems |

**Elo ratings** (from Chatbot Arena) are a pairwise approach at scale — each match updates ratings, producing a total ordering without needing n² comparisons.

---

## Single-Metric vs. Multi-Metric Evals

A single number hiding multiple dimensions is dangerous.

**Example**: Average faithfulness of 0.82 might mean:
- 90% of answers are perfectly faithful, 10% are completely hallucinated (bimodal distribution)
- All answers are mediocre at 0.82 (uniform distribution)
- These require completely different interventions

```python
import numpy as np

def eval_distribution_analysis(scores: list[float]) -> dict:
    arr = np.array(scores)
    return {
        "mean": arr.mean(),
        "median": np.median(arr),
        "std": arr.std(),
        "p10": np.percentile(arr, 10),
        "p25": np.percentile(arr, 25),
        "p75": np.percentile(arr, 75),
        "p90": np.percentile(arr, 90),
        "fraction_below_0.5": (arr < 0.5).mean(),   # fraction of failures
        "fraction_above_0.9": (arr > 0.9).mean(),   # fraction of excellent
    }
```

**Multi-metric evaluation**: Report all relevant dimensions (faithfulness, relevance, coherence, latency) separately. Define a **minimum acceptable threshold** per metric — a system must pass all thresholds, not just achieve a high average.

---

## Benchmark Saturation and Gaming

As LLMs improve, static benchmarks saturate — scores converge near the ceiling and discrimination disappears.

| Benchmark | Status (2026) | Notes |
|-----------|--------------|-------|
| MMLU | Saturated | Top models all >85%; contamination concerns |
| HellaSwag | Saturated | >95% for frontier models |
| HumanEval | Near-saturated | Top models >90% on original set |
| GPQA | Active | Hard enough to still discriminate |
| LiveCodeBench | Active | New problems monthly; contamination-resistant |
| MATH | Near-saturated | GPT-4o >90%; harder subsets still discriminate |

**Contamination**: Training data overlap with benchmark test sets inflates scores. Signs: model scores near-perfect on benchmark but fails similar novel questions. Mitigation: use dynamic benchmarks (new problems per evaluation), hold-out custom eval sets, test on release dates of benchmarks published after model training cutoff.

**Teaching to the test**: Models fine-tuned on benchmark formats may score well without genuine capability improvement. Internal task-specific evals (not shared publicly) are more reliable signals for production quality.

---

## Eval Cost vs. Frequency Tradeoffs

| Eval Type | Cost per Run | Recommended Frequency |
|-----------|-------------|----------------------|
| Rule-based unit tests (behavioral) | Near-zero | Every commit (CI) |
| LLM-as-judge on 100-query golden set | ~$0.10 | Every PR, every prompt change |
| LLM-as-judge on 1000-query golden set | ~$1 | Weekly, or on significant releases |
| Human eval (200 annotations, MTurk) | ~$200–500 | Monthly or quarterly |
| Full HELM-style benchmark | ~$50–200 | Quarterly, model upgrades only |
| Production sampling (5% of traffic) | ~$0.001/query | Continuous |

**Budget allocation principle**: spend proportionally to signal value. LLM-as-judge on a well-constructed 1000-question set costs $1 and provides more actionable signal than a $500 human eval run on a poorly constructed 200-question set.
