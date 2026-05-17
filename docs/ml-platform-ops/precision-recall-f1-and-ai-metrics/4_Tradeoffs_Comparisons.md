# Tradeoffs & Comparisons

## Accuracy vs. F1 vs. MCC: When Each Is Appropriate

| Metric | Valid When | Misleading When |
|--------|-----------|----------------|
| **Accuracy** | Dataset is balanced (classes within 2x of each other) | Imbalanced data (99% negative → 99% accuracy by always predicting negative) |
| **F1 (macro)** | All classes matter equally; imbalanced data | Some classes are much more important than others |
| **F1 (weighted)** | Reflecting overall system performance with class frequency | Small classes are critical but underweighted |
| **MCC** | Best single metric for imbalanced binary classification | Never misleading — use it by default for binary |
| **AUC-ROC** | Evaluating discriminative ability, threshold-agnostic | Highly imbalanced data (can look good while PR-AUC is terrible) |
| **AUC-PR** | Imbalanced data, focus on positive (minority) class | Balanced data (less informative than AUC-ROC) |

```python
# Illustrating the danger of accuracy on imbalanced data
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, matthews_corrcoef

# Scenario: 1000 samples, 10 positives (1% prevalence — fraud detection)
y_true = np.array([1]*10 + [0]*990)
y_pred_naive = np.zeros(1000, dtype=int)  # "always predict negative"

print(f"Accuracy:  {accuracy_score(y_true, y_pred_naive):.3f}")   # 0.990 — deceptively high
print(f"F1 macro:  {f1_score(y_true, y_pred_naive, average='macro'):.3f}")  # 0.495 — reveals problem
print(f"MCC:       {matthews_corrcoef(y_true, y_pred_naive):.3f}")           # 0.000 — no predictive value
```

---

## F1 vs. F-beta: Choosing the Right Beta

| Scenario | Recommended | Beta |
|----------|------------|------|
| Equal cost of FP and FN | F1 | β = 1.0 |
| Missing a positive is catastrophic (cancer, fraud) | F2 | β = 2.0 |
| False alarms are very costly (user-facing content removal) | F0.5 | β = 0.5 |
| Security intrusion detection | F2 or F3 | β ≥ 2.0 |
| Email spam filter (false positive = lost email) | F0.5 | β < 1.0 |

---

## AUC-ROC vs. AUC-PR: The Imbalanced Data Choice

This is one of the most common interview questions and most common production mistakes.

```python
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier

# Scenario A: balanced dataset
X_bal, y_bal = make_classification(n_samples=1000, weights=[0.5, 0.5])
model_bal = RandomForestClassifier().fit(X_bal, y_bal)
scores_bal = model_bal.predict_proba(X_bal)[:, 1]

# Scenario B: severely imbalanced (1% positive)
X_imb, y_imb = make_classification(n_samples=1000, weights=[0.99, 0.01])
model_imb = RandomForestClassifier().fit(X_imb, y_imb)
scores_imb = model_imb.predict_proba(X_imb)[:, 1]

# Even a mediocre model on imbalanced data can have high AUC-ROC
print(f"Imbalanced AUC-ROC: {roc_auc_score(y_imb, scores_imb):.3f}")  # could be 0.95
print(f"Imbalanced AUC-PR:  {average_precision_score(y_imb, scores_imb):.3f}")  # much lower
```

**Why**: AUC-ROC's FPR denominator is (FP + TN) — with 990 negatives, even 100 false positives give FPR = 100/990 ≈ 0.10, which looks fine on the ROC curve. AUC-PR's denominator for precision is (TP + FP) — 100 FPs on 10 positives means precision = 10/110 = 0.09. The PR curve exposes the real problem.

---

## BLEU / ROUGE vs. BERTScore vs. LLM-as-Judge

| Dimension | BLEU | ROUGE-L | BERTScore | LLM-as-Judge |
|-----------|------|---------|-----------|--------------|
| **Speed** | Milliseconds | Milliseconds | Seconds (GPU) | Seconds–minutes |
| **Cost** | Free | Free | GPU inference | LLM API cost |
| **Semantic sensitivity** | None | None | High | Highest |
| **Reference required** | Yes | Yes | Yes | No (reference-free possible) |
| **Human correlation** | Low (0.3–0.5) | Low-Medium | High (0.7–0.85) | Very high (0.85–0.92) |
| **Synonym handling** | Fails | Fails | Excellent | Excellent |
| **Good for** | MT baselines, CI smoke tests | Summarization baselines | NLG quality, A/B testing | Final quality gate, nuanced eval |

**Empirical finding** (Kocmi et al., 2023 — WMT metric shared task): For translation evaluation, COMET and BLEURT outperform BLEU significantly in correlation with human judgments. BLEU should be treated as a fast sanity check, not a quality measure.

---

## Micro vs. Macro vs. Weighted Averaging: A Decision Framework

```python
# Example: 3-class classifier, very imbalanced
# Class A: 800 samples, F1=0.90 (easy, majority)
# Class B: 150 samples, F1=0.75 (medium)
# Class C: 50 samples,  F1=0.40 (hard, minority — the important class)

from sklearn.metrics import f1_score

f1_macro    = (0.90 + 0.75 + 0.40) / 3  # = 0.683 — treats classes equally
f1_weighted = (0.90*800 + 0.75*150 + 0.40*50) / 1000  # = 0.848 — dominated by class A
f1_micro    ≈ 0.84  # similar to weighted for these numbers

# The right choice:
# - If class C is the critical class (rare disease): report class C F1 separately (= 0.40)
# - If all classes matter equally: macro (= 0.683)
# - If overall system performance matters: weighted (= 0.848)
# NEVER just report "F1 = 0.848" without specifying averaging method
```

---

## Perplexity Limitations

| Scenario | Perplexity Useful? | Why |
|----------|--------------------|-----|
| Comparing two models on same test set | Yes | Lower PPL = better language model |
| Comparing models on different distributions | No | Incomparable across test sets |
| Measuring factual accuracy | No | Low PPL model can confidently hallucinate |
| Measuring instruction following | No | PPL doesn't capture alignment |
| Pre-training data quality filtering | Yes | Filter high-PPL documents from training |

---

## Single Metric vs. Multi-Metric Evaluation

The persistent temptation to reduce everything to one number is statistically dangerous.

```python
# Bad: single metric hides model behavior
model_a_metrics = {"f1": 0.85, "precision": 0.95, "recall": 0.77}  # precise but misses cases
model_b_metrics = {"f1": 0.85, "precision": 0.78, "recall": 0.93}  # misses fewer, more alarms

# These look identical on F1 but have very different production behavior:
# Model A: good for auto-action (high precision), bad for discovery
# Model B: good for discovery (high recall), bad for auto-action
```

**Recommendation**: Define a minimum acceptable threshold per metric for your use case. A model must satisfy ALL thresholds — not achieve a high average. Example:
- Fraud detection: precision ≥ 0.80 AND recall ≥ 0.95 AND latency ≤ 50ms
- Content moderation: precision ≥ 0.95 AND recall ≥ 0.90 AND false_positive_rate ≤ 0.02

---

## Calibration vs. Discrimination

These are independent properties:

- **Discrimination** (AUC-ROC): does the model correctly rank positives above negatives?
- **Calibration** (ECE): do the predicted probabilities match actual frequencies?

A model can be well-discriminating but poorly calibrated (ranks correctly, but says "95% probability" when true probability is 70%). Critical in risk-scoring, loan decisions, clinical tools.

```python
from sklearn.calibration import CalibratedClassifierCV

# Platt scaling (logistic regression calibration)
calibrated_model = CalibratedClassifierCV(base_model, cv=5, method="sigmoid")
calibrated_model.fit(X_train, y_train)

# Isotonic regression calibration (non-parametric, better for more data)
calibrated_model_iso = CalibratedClassifierCV(base_model, cv=5, method="isotonic")
```
