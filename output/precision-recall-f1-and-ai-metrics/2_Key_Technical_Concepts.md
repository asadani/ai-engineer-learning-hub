# Key Technical Concepts

## The Confusion Matrix — Foundation of Everything

For binary classification, all threshold-based metrics derive from the confusion matrix:

```
                    PREDICTED
                  Positive  Negative
ACTUAL Positive │   TP    │   FN   │  ← all actual positives
       Negative │   FP    │   TN   │  ← all actual negatives
```

- **TP** (True Positive): correctly predicted positive
- **TN** (True Negative): correctly predicted negative
- **FP** (False Positive): predicted positive, actually negative — Type I error
- **FN** (False Negative): predicted negative, actually positive — Type II error

```python
import numpy as np
from sklearn.metrics import confusion_matrix, classification_report

y_true = [1, 0, 1, 1, 0, 1, 0, 0, 1, 0]
y_pred = [1, 0, 1, 0, 0, 1, 1, 0, 1, 0]

cm = confusion_matrix(y_true, y_pred)
# array([[4, 1],    ← TN=4, FP=1
#        [1, 4]])   ← FN=1, TP=4
tn, fp, fn, tp = cm.ravel()
```

---

## Precision

> Of everything I called positive, what fraction actually was positive?

$$\text{Precision} = \frac{TP}{TP + FP}$$

```python
precision = tp / (tp + fp)  # = 4 / (4 + 1) = 0.80
```

**When precision matters**: Any task where a false alarm has high cost.
- Content moderation: falsely removing legitimate content (false positive) harms users
- Email spam filter: marking a legitimate email as spam (FP) is costly
- Medical: falsely diagnosing a healthy patient with cancer → unnecessary treatment

**Precision = 1.0** means every positive prediction is correct. Achievable trivially by predicting positive only for the single highest-confidence example — but at the cost of missing everything else.

---

## Recall (Sensitivity / True Positive Rate)

> Of all actual positives in the dataset, what fraction did I find?

$$\text{Recall} = \frac{TP}{TP + FN}$$

```python
recall = tp / (tp + fn)  # = 4 / (4 + 1) = 0.80
```

**When recall matters**: Any task where missing a positive is catastrophically costly.
- Cancer screening: missing a tumor (FN) is fatal
- Fraud detection: missing a fraudulent transaction (FN) means financial loss
- Security: missing an intrusion (FN) means breach
- RAG context_recall: missing relevant documents means the answer will be incomplete

**Recall = 1.0** means every actual positive was found. Achievable trivially by predicting everything as positive — but precision collapses to base rate.

---

## The Precision-Recall Tradeoff

Precision and recall are in fundamental tension. As you lower the classification threshold (predict positive more aggressively), recall increases but precision falls.

```python
import matplotlib.pyplot as plt
from sklearn.metrics import precision_recall_curve
from sklearn.datasets import make_classification
from sklearn.linear_model import LogisticRegression

X, y = make_classification(n_samples=1000, n_classes=2, weights=[0.9, 0.1])
model = LogisticRegression().fit(X, y)
y_scores = model.predict_proba(X)[:, 1]

precisions, recalls, thresholds = precision_recall_curve(y, y_scores)
# Plot to find operating point: where do you want to trade off?
```

**Operating point selection**: Business requirement defines it.
- "Never miss a fraud case (recall ≥ 0.99), accept some false alarms" → set threshold where recall ≥ 0.99
- "Only flag cases we're 90% sure about (precision ≥ 0.90)" → set threshold where precision ≥ 0.90

---

## F1 Score

> Harmonic mean of precision and recall — penalizes extreme imbalance between the two.

$$F1 = 2 \cdot \frac{\text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}} = \frac{2 \cdot TP}{2 \cdot TP + FP + FN}$$

```python
from sklearn.metrics import f1_score
f1 = f1_score(y_true, y_pred)  # binary default

# Why harmonic mean, not arithmetic mean?
# Precision=1.0, Recall=0.0 → arithmetic mean = 0.5 (misleadingly high)
# Harmonic mean = 0.0 → correctly reflects useless model
```

**F-beta score** — weighted variant when recall matters more than precision:

$$F_\beta = (1 + \beta^2) \cdot \frac{\text{Precision} \cdot \text{Recall}}{\beta^2 \cdot \text{Precision} + \text{Recall}}$$

- β = 0.5: precision weighted 2x more than recall (penalize false alarms)
- β = 2.0: recall weighted 2x more (penalize missed positives — medical, security)

```python
from sklearn.metrics import fbeta_score
f2 = fbeta_score(y_true, y_pred, beta=2.0)  # recall-weighted
f05 = fbeta_score(y_true, y_pred, beta=0.5)  # precision-weighted
```

---

## Multiclass Averaging

In multiclass problems, precision, recall, and F1 must be aggregated across classes.

| Averaging | How | When to Use |
|-----------|-----|-------------|
| **Macro** | Unweighted mean across classes | Equal importance to all classes, regardless of size |
| **Weighted** | Mean weighted by class support | Reflect production class distribution |
| **Micro** | Pool all TPs, FPs, FNs globally, then compute | Dominated by majority class; similar to accuracy on balanced data |

```python
from sklearn.metrics import classification_report

y_true_mc = [0, 1, 2, 0, 1, 2, 0, 2]
y_pred_mc = [0, 1, 1, 0, 2, 2, 0, 2]

print(classification_report(y_true_mc, y_pred_mc,
                             target_names=["cat", "dog", "bird"]))
# Reports precision, recall, F1 per class + macro/weighted averages

f1_macro    = f1_score(y_true_mc, y_pred_mc, average="macro")
f1_weighted = f1_score(y_true_mc, y_pred_mc, average="weighted")
f1_micro    = f1_score(y_true_mc, y_pred_mc, average="micro")
```

**Critical**: On imbalanced multiclass, weighted F1 can look good while the minority class is completely ignored. Always report per-class F1 for imbalanced problems.

---

## Matthews Correlation Coefficient (MCC)

> The most informative single metric for binary classification. Accounts for all four quadrants of the confusion matrix.

$$MCC = \frac{TP \cdot TN - FP \cdot FN}{\sqrt{(TP+FP)(TP+FN)(TN+FP)(TN+FN)}}$$

- Range: −1 to +1. MCC = +1: perfect predictions. MCC = 0: no better than random. MCC = −1: perfectly inverted.
- **Unlike F1**, MCC is symmetric — it gives equal weight to both classes and all four confusion matrix cells.
- Particularly important for imbalanced binary classification where F1 can be misleadingly high.

```python
from sklearn.metrics import matthews_corrcoef
mcc = matthews_corrcoef(y_true, y_pred)
```

---

## AUC-ROC (Area Under the ROC Curve)

**ROC curve**: plots TPR (recall) vs. FPR (false positive rate = FP/(FP+TN)) at all classification thresholds.

$$\text{AUC-ROC} = P(\text{score}_{positive} > \text{score}_{negative})$$

- Interpretation: probability that the model ranks a random positive higher than a random negative
- Range: 0.5 (random) to 1.0 (perfect)
- **Threshold-independent**: measures discriminative ability, not performance at a specific threshold

```python
from sklearn.metrics import roc_auc_score, roc_curve

auc_roc = roc_auc_score(y_true, y_scores)
fpr, tpr, thresholds = roc_curve(y_true, y_scores)
```

**Limitation on imbalanced data**: AUC-ROC can be misleadingly optimistic. A model with AUC-ROC = 0.95 on a 1:100 imbalanced dataset may still have terrible precision on the positive class.

---

## AUC-PR (Area Under the Precision-Recall Curve)

Plots precision vs. recall at all thresholds. **More informative than AUC-ROC for imbalanced datasets** because it focuses on the positive (minority) class.

- Random classifier baseline = class prevalence (e.g., 0.01 for 1% positive rate)
- AUC-PR = 0.01 means no better than random; AUC-PR = 1.0 means perfect

```python
from sklearn.metrics import average_precision_score

auc_pr = average_precision_score(y_true, y_scores)  # = AUC-PR (= AP)
```

**Rule of thumb**: On datasets with class imbalance > 10:1, always report AUC-PR alongside AUC-ROC. AUC-ROC can look good (0.95) while AUC-PR is poor (0.30).

---

## Regression Metrics

```python
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import numpy as np

y_true_reg = [3.0, 5.0, 2.5, 7.0]
y_pred_reg = [2.5, 5.0, 4.0, 6.5]

mae  = mean_absolute_error(y_true_reg, y_pred_reg)   # mean |y - ŷ|
mse  = mean_squared_error(y_true_reg, y_pred_reg)    # mean (y - ŷ)²
rmse = np.sqrt(mse)                                   # same units as y
r2   = r2_score(y_true_reg, y_pred_reg)              # 1 - SS_res/SS_tot
```

| Metric | Formula | Outlier Sensitivity | Interpretability |
|--------|---------|--------------------|--------------------|
| **MAE** | mean\|y − ŷ\| | Low | Same units as y |
| **MSE** | mean(y − ŷ)² | High (squares errors) | Squared units |
| **RMSE** | √MSE | High | Same units as y |
| **MAPE** | mean\|(y−ŷ)/y\| | Medium | % of actual value |
| **R²** | 1 − SS_res/SS_tot | Medium | Proportion variance explained |

**Huber Loss**: combines MAE (robust to outliers) and MSE (smooth gradient near 0). Preferred for regression when outliers are present.

---

## Ranking Metrics (Information Retrieval)

### NDCG (Normalized Discounted Cumulative Gain)

Measures ranking quality, giving more credit for relevant results ranked higher.

$$DCG@K = \sum_{i=1}^{K} \frac{rel_i}{\log_2(i+1)}$$
$$NDCG@K = \frac{DCG@K}{IDCG@K}$$ (normalized by ideal ranking)

```python
from sklearn.metrics import ndcg_score
import numpy as np

# true_relevance[i][j] = relevance of doc j for query i
true_relevance = np.array([[3, 2, 3, 0, 1, 2]])
scores = np.array([[3.0, 2.5, 2.8, 0.1, 1.2, 2.1]])  # model scores
ndcg = ndcg_score(true_relevance, scores, k=5)
```

### MRR (Mean Reciprocal Rank)

For tasks where there is one correct answer, MRR = mean of 1/rank of the first correct result.

$$MRR = \frac{1}{|Q|}\sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$$

```python
def mrr_at_k(results: list[list[bool]], k: int = 10) -> float:
    reciprocal_ranks = []
    for query_results in results:
        for rank, is_relevant in enumerate(query_results[:k], start=1):
            if is_relevant:
                reciprocal_ranks.append(1.0 / rank)
                break
        else:
            reciprocal_ranks.append(0.0)
    return sum(reciprocal_ranks) / len(reciprocal_ranks)
```

---

## NLG Metrics (Text Generation)

### BLEU (Bilingual Evaluation Understudy)

Measures n-gram precision of prediction vs. reference. Commonly used for machine translation.

$$BLEU = BP \cdot \exp\left(\sum_{n=1}^{N} w_n \log p_n\right)$$

where BP = brevity penalty, $p_n$ = n-gram precision at order n.

**Critical limitations**: no recall component; synonym blindness; doesn't capture meaning.

### ROUGE (Recall-Oriented Understudy for Gisting Evaluation)

Used for summarization. Three variants:
- **ROUGE-1**: unigram overlap (word-level recall)
- **ROUGE-2**: bigram overlap (phrase-level recall)
- **ROUGE-L**: longest common subsequence (structure-aware)

```python
from rouge_score import rouge_scorer

scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
scores = scorer.score(
    target="The cat sat on the mat",
    prediction="A cat was sitting on the mat"
)
# RougeScore(precision=0.71, recall=0.71, fmeasure=0.71) for rouge1
```

### BERTScore

Uses contextual BERT embeddings to compute semantic similarity between tokens.

$$P_{BERT} = \frac{1}{|\hat{y}|}\sum_{\hat{y}_j \in \hat{y}} \max_{y_i \in y} \cos(\hat{y}_j, y_i)$$

```python
from bert_score import score as bert_score

P, R, F1 = bert_score(
    cands=["The cat sat on the mat"],
    refs=["A cat was sitting on the mat"],
    lang="en",
    model_type="microsoft/deberta-xlarge-mnli",  # best model for English
)
# F1 ≈ 0.93 (captures semantic equivalence BLEU misses)
```

BERTScore correlates significantly better with human judgments than BLEU or ROUGE, especially for paraphrastic equivalence.

---

## Perplexity (Language Models)

Perplexity measures how well a language model predicts a test corpus. Lower = better.

$$PPL = \exp\left(-\frac{1}{N}\sum_{i=1}^{N} \log P(w_i | w_{<i})\right)$$

Intuition: perplexity of K means the model is as uncertain as if choosing uniformly among K options at each token.

```python
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

def compute_perplexity(model, tokenizer, text: str) -> float:
    inputs = tokenizer(text, return_tensors="pt")
    with torch.no_grad():
        loss = model(**inputs, labels=inputs["input_ids"]).loss
    return torch.exp(loss).item()

# GPT-2 on clean English: PPL ≈ 20–30
# LLaMA-3-70B on clean English: PPL ≈ 3–6
# Random token model: PPL ≈ vocabulary_size (50K+)
```

**Limitation**: perplexity is only meaningful on the distribution the model was trained on, and it doesn't capture factual accuracy or helpfulness.

---

## Calibration

A well-calibrated model's predicted probability matches the actual frequency of that class.

**Expected Calibration Error (ECE)**:

$$ECE = \sum_{m=1}^{M} \frac{|B_m|}{n} \left|\text{acc}(B_m) - \text{conf}(B_m)\right|$$

```python
from sklearn.calibration import calibration_curve

fraction_of_positives, mean_predicted = calibration_curve(
    y_true, y_proba, n_bins=10
)
# Plot: x = mean predicted probability, y = actual fraction positive
# Perfect calibration: diagonal line

# ECE: weighted average deviation from perfect calibration
def ece(y_true, y_proba, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    ece_val = 0
    for i in range(n_bins):
        mask = (y_proba >= bins[i]) & (y_proba < bins[i + 1])
        if mask.sum() == 0:
            continue
        bin_acc = y_true[mask].mean()
        bin_conf = y_proba[mask].mean()
        ece_val += mask.sum() / len(y_true) * abs(bin_acc - bin_conf)
    return ece_val
```

A model with high AUC-ROC but poor calibration ranks correctly but gives miscalibrated probabilities — downstream systems using the probability (risk scoring, decision thresholds) will be wrong.

---

## Pass@k (Code Generation)

For code generation tasks: the probability that at least one of k generated solutions passes all unit tests.

$$\text{Pass@k} = 1 - \frac{\binom{n-c}{k}}{\binom{n}{k}}$$

where n = total samples generated, c = samples that pass.

```python
import numpy as np
from math import comb

def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimator of pass@k."""
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)

# Generate 20 solutions, 5 pass unit tests
pass_at_1  = pass_at_k(n=20, c=5, k=1)   # ≈ 0.25
pass_at_10 = pass_at_k(n=20, c=5, k=10)  # ≈ 0.83
```

HumanEval benchmark reports Pass@1 (one attempt), Pass@10, Pass@100. Frontier models (2026): claude-opus-4 ~90% pass@1, GPT-4o ~85% pass@1 on HumanEval.
