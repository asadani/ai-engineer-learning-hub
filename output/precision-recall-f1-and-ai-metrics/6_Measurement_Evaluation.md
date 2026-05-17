# Measurement & Evaluation

## How to Choose the Right Metric

The single most important eval design decision. A structured decision tree:

```
Step 1: What is the output type?
  ├── Categorical label         → Classification metrics
  ├── Continuous value          → Regression metrics
  ├── Ranked list               → Ranking / IR metrics
  ├── Generated text            → NLG metrics
  └── Agent task outcome        → Task success rate + trajectory metrics

Step 2 (Classification): Is the data balanced?
  ├── Yes (classes within 2x)   → Accuracy, F1-macro, AUC-ROC
  └── No (imbalance > 5:1)      → MCC, AUC-PR, F1-positive-class, per-class F1

Step 3: What is the relative cost of FP vs FN?
  ├── FN much worse (medical, security)   → Recall, F2, optimize at high-recall point
  ├── FP much worse (content moderation)  → Precision, F0.5
  └── Roughly equal                       → F1, MCC

Step 4: Need probability outputs or just labels?
  ├── Need probabilities (risk scoring, calibration)  → AUC-ROC + ECE
  └── Need binary decisions only                      → F1, MCC at chosen threshold

Step 5 (NLG): Do you have a reference?
  ├── Yes + exact/semantic matching needed → BERTScore, ROUGE, BLEU
  ├── Yes + factual correctness            → COMET, QuestEval, SummaC
  └── No reference / open-ended           → LLM-as-judge, human eval
```

---

## Statistical Significance of Metric Differences

A difference of 0.82 vs 0.80 F1 may or may not be meaningful depending on sample size and variance.

```python
from scipy import stats
import numpy as np

def compare_classifiers(
    y_true: np.ndarray,
    scores_a: np.ndarray,  # probabilities from model A
    scores_b: np.ndarray,  # probabilities from model B
    n_bootstrap: int = 10_000,
    confidence_level: float = 0.95,
) -> dict:
    """Bootstrap confidence intervals for metric comparison."""

    def compute_metric(y_t, s):
        from sklearn.metrics import roc_auc_score
        return roc_auc_score(y_t, s)

    observed_diff = compute_metric(y_true, scores_a) - compute_metric(y_true, scores_b)

    # Bootstrap: resample with replacement and measure diff distribution
    bootstrap_diffs = []
    n = len(y_true)
    rng = np.random.default_rng(42)
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        diff = compute_metric(y_true[idx], scores_a[idx]) - compute_metric(y_true[idx], scores_b[idx])
        bootstrap_diffs.append(diff)

    alpha = (1 - confidence_level) / 2
    ci_lower = np.percentile(bootstrap_diffs, alpha * 100)
    ci_upper = np.percentile(bootstrap_diffs, (1 - alpha) * 100)

    # p-value: proportion of bootstrap diffs on wrong side of zero
    p_value = np.mean(np.array(bootstrap_diffs) <= 0) if observed_diff > 0 else np.mean(np.array(bootstrap_diffs) >= 0)

    return {
        "observed_diff": observed_diff,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "significant": ci_lower > 0 or ci_upper < 0,  # CI doesn't contain 0
        "p_value": p_value,
        "n_bootstrap": n_bootstrap,
    }

# Also useful: McNemar's test for paired classifier comparison
from statsmodels.stats.contingency_tables import mcnemar

def mcnemar_test(pred_a: np.ndarray, pred_b: np.ndarray, y_true: np.ndarray) -> dict:
    """Test if two classifiers differ significantly."""
    correct_a = pred_a == y_true
    correct_b = pred_b == y_true

    b = np.sum(correct_a & ~correct_b)  # A right, B wrong
    c = np.sum(~correct_a & correct_b)  # A wrong, B right

    result = mcnemar([[0, b], [c, 0]], exact=False, correction=True)
    return {"statistic": result.statistic, "p_value": result.pvalue, "significant": result.pvalue < 0.05}
```

---

## Confusion Matrix Analysis Patterns

Beyond the summary metrics, the raw confusion matrix reveals actionable patterns.

```python
import pandas as pd
import numpy as np
from sklearn.metrics import confusion_matrix

def analyze_confusion_matrix(y_true, y_pred, class_names):
    cm = confusion_matrix(y_true, y_pred)
    cm_df = pd.DataFrame(cm, index=class_names, columns=class_names)

    # Per-class error analysis
    per_class = {}
    for i, cls in enumerate(class_names):
        total = cm[i].sum()
        correct = cm[i, i]
        per_class[cls] = {
            "precision": cm[i, i] / cm[:, i].sum() if cm[:, i].sum() > 0 else 0,
            "recall": correct / total if total > 0 else 0,
            "most_confused_with": class_names[np.argsort(cm[i])[::-1][1]],
            "confusion_rate": (total - correct) / total if total > 0 else 0,
        }
    return cm_df, per_class

# The `most_confused_with` is the most actionable output:
# If 'dog' is most confused with 'wolf', add more distinguishing examples to training
```

---

## Metric Computation Correctness Pitfalls

### Leakage in Cross-Validation

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score

# WRONG: scaling before split leaks test statistics into training
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)  # ← uses test set mean/std during CV!
scores = cross_val_score(model, X_scaled, y, cv=5, scoring="f1")

# CORRECT: include preprocessing inside the pipeline
pipeline = Pipeline([
    ("scaler", StandardScaler()),
    ("classifier", model),
])
scores = cross_val_score(pipeline, X, y, cv=5, scoring="f1")
# Now scaler is fit only on training fold
```

### Averaging Order Matters for NDCG

```python
# WRONG: average NDCG computed as NDCG(averaged relevances)
# CORRECT: compute NDCG per query, then average

ndcg_per_query = [ndcg_score([true_rel[i]], [pred_scores[i]], k=10) for i in range(len(queries))]
mean_ndcg = np.mean(ndcg_per_query)  # correct

# NOT: ndcg_score(all_true_relevances, all_scores, k=10)  # averages wrong
```

### Macro vs. Weighted F1 Pitfall

```python
# Often people report "F1" without specifying the averaging method
# When reading papers/reports: ALWAYS check what averaging was used
# When reporting: ALWAYS specify

report_correctly = {
    "f1_macro": f1_score(y_true, y_pred, average="macro"),
    "f1_weighted": f1_score(y_true, y_pred, average="weighted"),
    "f1_positive_class": f1_score(y_true, y_pred, average="binary"),  # binary only
    "per_class_f1": dict(zip(class_names, f1_score(y_true, y_pred, average=None))),
}
```

---

## Fairness Metrics

An increasingly important dimension: a model may have good aggregate metrics but poor performance for specific subgroups.

```python
from fairlearn.metrics import demographic_parity_difference, equalized_odds_difference

# Demographic parity: P(ŷ=1 | group=A) ≈ P(ŷ=1 | group=B)
dp_diff = demographic_parity_difference(y_true, y_pred, sensitive_features=group_labels)
# 0.0 = perfect parity; ± 0.1 = small disparity; ± 0.2+ = significant

# Equalized odds: TPR and FPR equal across groups
eo_diff = equalized_odds_difference(y_true, y_pred, sensitive_features=group_labels)

# Per-group breakdown
from sklearn.metrics import classification_report
for group in ["group_A", "group_B"]:
    mask = group_labels == group
    print(f"\nGroup: {group}")
    print(classification_report(y_true[mask], y_pred[mask]))
```

**In the GenAI era**: fairness metrics extend to measuring whether LLMs exhibit stereotyping, differential toxicity by group, and disparate performance across demographic groups. BBQ (Bias Benchmark for QA) and WinoBias are standard datasets.
