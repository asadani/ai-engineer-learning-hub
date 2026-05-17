# Precision, Recall, F1 Score & AI Metrics

**Principal-level interview prep notes** — tailored for a 16+ year engineering leader with deep expertise in Python, AWS, AI/ML, and distributed systems.

Generated: 2026-03-22

---

## Contents

| # | File | Words | Focus |
|---|------|-------|-------|
| 1 | [High-Level Overview](1_High_Level_Overview.md) | 868 | Metric landscape taxonomy, eval pyramid, Goodhart's Law, metric selection hierarchy |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | 1,993 | Full formulas + Python code: confusion matrix, Precision, Recall, F1, F-beta, MCC, AUC-ROC, AUC-PR, NDCG, MRR, BLEU, ROUGE, BERTScore, Perplexity, ECE, Pass@k |
| 3 | [Products & Tools](3_Products_Tools.md) | 857 | scikit-learn, TorchMetrics, HuggingFace `evaluate`, RAGAS, DeepEval, MLflow, W&B, Evidently AI, SageMaker Model Monitor |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | 1,095 | Accuracy vs F1 vs MCC, AUC-ROC vs AUC-PR, BLEU/ROUGE vs BERTScore vs LLM-judge, micro/macro/weighted averaging, calibration vs discrimination |
| 5 | [Use Cases](5_Use_Cases.md) | 1,198 | Medical diagnosis, fraud detection, IR/search, MT + summarization, LLM fine-tuning eval, recommender systems, production drift detection |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | 911 | Metric selection decision tree, bootstrap CI, McNemar's test, confusion matrix analysis, leakage in CV, fairness metrics |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | 1,021 | Universal metric checklist tables by task type, rolling window monitor, logging schema, CI evaluation gate, domain reference card |
| 8 | [Interview Questions](8_Interview_Questions.md) | 5,590 | 16 tiered Q&As: L5 (metric fundamentals), L6 (system design), L7+ (architecture, Goodhart's Law, fairness, multi-agent eval, org influence) |

**Total: ~13,533 words**

---

## Key Themes

### The Metric Selection Hierarchy
1. Define the task type (classification / ranking / NLG / regression)
2. Assess class balance and cost asymmetry
3. Choose threshold-agnostic metrics for model comparison (AUC-PR, AUC-ROC, MCC)
4. Choose operating-point metrics for deployment (precision, recall, F1 at threshold)
5. Layer on calibration (ECE) for probability-using systems
6. Add domain-specific metrics (dollar-weighted recall, NDCG, faithfulness)

### Critical Distinctions
- **AUC-ROC vs AUC-PR**: Use AUC-PR for imbalanced data — AUC-ROC flatters weak models when TN >> TP
- **Macro vs Weighted F1**: Macro treats classes equally; weighted hides minority class failures — always report per-class F1 for important classes
- **Calibration vs Discrimination**: Independent properties — a well-ranking model can have systematically wrong probabilities
- **BLEU/ROUGE vs BERTScore**: n-gram overlap fails on synonyms; BERTScore handles semantics but misses hallucinations
- **Goodhart's Law**: Every metric that becomes a target gets gamed — use multi-metric dashboards with business outcome correlation

### Production Monitoring Design
- Log every prediction with `trace_id`; join ground truth labels asynchronously
- Rolling window monitors (500–1000 samples) with alert thresholds
- KS test for distribution shift detection
- CI gate: compare new model to champion on same eval set with bootstrap CI
- Fairness metrics (`equalized_odds_difference`, `demographic_parity_difference`) on every model promotion

### GenAI / LLM Era Additions
- **Faithfulness** (RAGAS): is every claim grounded in retrieved context?
- **Hallucination rate**: LLM-judge on sampled output — most important new metric
- **Format compliance**: fraction of responses that parse correctly — a 10% failure rate kills downstream pipelines
- **Refusal accuracy**: for safety-critical systems — must be > 99.9%
- **Pass@k**: for code generation — fraction of problems solved with k samples

---

## Quick Reference: Metric by Domain

| Domain | Primary | Avoid |
|--------|---------|-------|
| Medical diagnosis | Recall @ fixed threshold | Accuracy |
| Fraud detection | AUC-PR, Dollar-weighted recall | Accuracy, AUC-ROC alone |
| Spam filter | Precision (F0.5) | Accuracy |
| Search / IR | NDCG@10 | Accuracy |
| Machine translation | COMET, BERTScore | Raw BLEU |
| Summarization | BERTScore + SummaC | ROUGE-1 alone |
| Code generation | Pass@1 | BLEU |
| RAG Q&A | Faithfulness + Answer Relevance | ROUGE |
| LLM safety | Refusal accuracy | N/A |
| Tabular (imbalanced) | AUC-PR, MCC | Accuracy, AUC-ROC alone |


---

!!! info "Official Sources & Further Reading"

    - [scikit-learn — Model evaluation: metrics](https://scikit-learn.org/stable/modules/model_evaluation.html)
    - [Google — ML Crash Course: Accuracy, precision, recall](https://developers.google.com/machine-learning/crash-course/classification/accuracy-precision-recall)
    - [scikit-learn — Precision-Recall example](https://scikit-learn.org/stable/auto_examples/model_selection/plot_precision_recall.html)
    - [Wikipedia — F-score](https://en.wikipedia.org/wiki/F-score)


!!! tip "Related Topics"

    - [MLOps](../mlops/)
    - [Evals in AI](../evals-in-ai/)
    - [LLM Observability & LLMOps](../llm-observability-llmops/)
    - [AI Safety & Guardrails](../ai-safety-guardrails/)
