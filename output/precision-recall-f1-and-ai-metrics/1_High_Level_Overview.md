# High-Level Overview

## Why Metrics Are the Foundation of AI Engineering

In traditional software, correctness is binary — the function either returns the right value or it doesn't. In AI systems, correctness is probabilistic and task-dependent. A model that is 95% accurate on a fraud detection task might still be unusable if the remaining 5% represents all legitimate transactions being blocked. Metrics operationalize "good enough" for each specific task, and choosing the wrong metric — or optimizing a proxy metric instead of the true objective — is one of the most common sources of production AI failure.

The principle: **metrics are not just measurements — they are the specification of what the model is being trained and evaluated to do.** A model optimized for accuracy on an imbalanced dataset learns to predict the majority class always. A model optimized for BLEU score in translation learns to output high n-gram overlap, not necessarily meaning. The metric defines the behavior.

---

## The Metric Landscape

Metrics stratify cleanly by task type and era:

```
CLASSICAL ML METRICS
├── Classification
│   ├── Threshold-based: Accuracy, Precision, Recall, F1, MCC
│   └── Threshold-free: AUC-ROC, AUC-PR
├── Regression
│   └── MAE, MSE, RMSE, MAPE, R², Huber Loss
├── Ranking / IR
│   └── NDCG, MAP, MRR, Hit Rate@K, Precision@K
└── Clustering
    └── Silhouette, ARI, NMI

GENERATIVE AI ERA METRICS
├── Text Generation (overlap-based)
│   └── BLEU, ROUGE-{1,2,L}, METEOR, CIDEr
├── Semantic / Embedding-based
│   └── BERTScore, MoverScore, BLEURT
├── LLM-specific
│   └── Perplexity, Token Accuracy, Pass@k (code)
├── RAG Pipeline
│   └── Faithfulness, Answer Relevance, Context Precision, Context Recall
├── Safety & Alignment
│   └── Toxicity Rate, Refusal Accuracy, Stereotype Score
└── Human-preference
    └── Win Rate, Elo Rating, Thumbs Up/Down Rate
```

---

## The Metric Selection Hierarchy

Before choosing any metric, answer these questions in order:

1. **What is the task output type?** — Classification → confusion matrix metrics; generation → overlap or semantic metrics; ranking → IR metrics
2. **Is the dataset balanced?** — Imbalanced → never use accuracy; use F1, AUC-PR, or MCC
3. **What are the costs of each error type?** — High cost of false negatives (cancer, fraud) → optimize recall; high cost of false positives (content moderation, auto-approvals) → optimize precision
4. **Is there a ground truth?** — Yes → reference-based metrics; No → reference-free (LLM-as-judge, human eval)
5. **Does the model output a score/probability?** — Yes → threshold-free metrics (AUC); output is binary → threshold-based metrics (F1, precision, recall)

---

## Evolution From Classical to GenAI Metrics

| Era | Paradigm | Primary Metrics | Failure Mode |
|-----|---------|----------------|-------------|
| Classical ML (pre-2017) | Tabular, structured | Accuracy, F1, AUC-ROC | Imbalanced class blindness |
| Deep Learning / NLP (2017–2020) | Sequence models | BLEU, ROUGE, Perplexity | n-gram overlap ≠ meaning |
| Transformers / LLMs (2020–2023) | Foundation models | BERTScore, Pass@k, Human preference | Semantic metrics still not meaning-preserving |
| GenAI / RAG / Agents (2023–2026) | Generative pipelines | RAGAS metrics, LLM-as-judge, Task success rate | Evaluator bias, benchmark saturation |

Each era's metrics were designed for the failure modes of their time. The persistent challenge: **no single metric captures all dimensions of quality**, and the metric that is easiest to compute is rarely the metric that best reflects user value.

---

## Goodhart's Law in AI Metrics

> "When a measure becomes a target, it ceases to be a good measure." — Goodhart's Law

Concrete AI manifestations:
- **Optimizing accuracy on imbalanced data**: model learns to predict majority class, achieving 99% accuracy while never detecting the minority class
- **Optimizing BLEU in translation**: models learn to copy source language n-grams, producing high BLEU scores on poor translations
- **Optimizing for click-through rate** in recommendation: model promotes sensational content over genuinely useful content
- **Optimizing faithfulness alone in RAG**: model learns to produce answers that are technically grounded in the context but avoid answering the actual question (high faithfulness, low relevance)

The mitigation: **multi-metric evaluation** with metrics that are hard to simultaneously game, combined with periodic human evaluation as a ground truth anchor.

---

## Key Intuitions Before the Math

| Metric | One-line Intuition | Ask When |
|--------|-------------------|----------|
| **Precision** | Of all positives I predicted, how many were actually positive? | Cost of a false alarm is high |
| **Recall** | Of all actual positives, how many did I find? | Cost of missing something is high |
| **F1** | Harmonic mean of precision and recall | Both matter equally |
| **AUC-ROC** | How well does the model separate classes at all thresholds? | Evaluating discriminative ability |
| **AUC-PR** | How well does the model perform on the positive class, at all thresholds? | Highly imbalanced datasets |
| **MCC** | How well does the model perform accounting for all 4 quadrants? | Balanced summary for binary classification |
| **NDCG** | How well are the most relevant results ranked highest? | Ranking, search, recommendations |
| **BERTScore** | Are the semantics of the prediction and reference similar? | NLG evaluation beyond word overlap |
| **Perplexity** | How surprised is the model by the test data? | Language model quality, pre-training |
