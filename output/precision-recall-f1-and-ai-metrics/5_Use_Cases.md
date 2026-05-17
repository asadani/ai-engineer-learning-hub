# Use Cases & Real-World Applications

## 1. Medical Diagnosis (Maximizing Recall / Minimizing FN)

**Context**: A model screening mammograms for breast cancer. Missing a tumor (FN) is life-threatening; a false alarm (FP) leads to unnecessary biopsy — uncomfortable but recoverable.

**Primary metric**: Recall (sensitivity) at a fixed high threshold, e.g., recall ≥ 0.97.
**Secondary metric**: Precision (affects the number of unnecessary biopsies), AUC-PR.
**Never use**: Accuracy (class imbalance is extreme — 99%+ of mammograms are benign).

```python
from sklearn.metrics import classification_report, roc_curve
import numpy as np

# Operating point selection: find threshold where recall >= 0.97
fpr, tpr, thresholds = roc_curve(y_true, y_scores)
viable_thresholds = thresholds[tpr >= 0.97]
if len(viable_thresholds) > 0:
    # Among viable thresholds, pick the one with highest precision
    operating_threshold = viable_thresholds[-1]  # lowest FPR at recall ≥ 0.97
else:
    operating_threshold = 0.1  # fallback

y_pred_clinical = (y_scores >= operating_threshold).astype(int)
print(f"Operating threshold: {operating_threshold:.3f}")
print(classification_report(y_true, y_pred_clinical))
```

**Key lesson**: The threshold is a business/clinical decision, not a model decision. The model produces scores; the threshold is set by the acceptable false-negative rate dictated by clinical risk tolerance.

---

## 2. Fraud Detection (Precision-Recall Tradeoff at Scale)

**Context**: A payments company detecting fraudulent transactions. The positive class (fraud) is ~0.1–1% of transactions. Two failure modes:
- FN (missed fraud): financial loss + regulatory risk
- FP (blocked legitimate transaction): customer friction, chargebacks, revenue loss

**Metrics matrix**:
- **AUC-PR**: primary model quality metric (imbalanced, must evaluate on positive class)
- **Precision@90% recall**: how many legitimate transactions are blocked to catch 90% of fraud?
- **Dollar-weighted precision/recall**: weight FPs and FNs by transaction amount, not count

```python
import numpy as np

def dollar_weighted_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    amounts: np.ndarray,
) -> dict:
    """Weight false positives and negatives by transaction amount."""
    tp_dollars = amounts[(y_true == 1) & (y_pred == 1)].sum()
    fn_dollars = amounts[(y_true == 1) & (y_pred == 0)].sum()  # fraud missed
    fp_dollars = amounts[(y_true == 0) & (y_pred == 1)].sum()  # legit blocked

    dollar_recall = tp_dollars / (tp_dollars + fn_dollars)
    dollar_precision = tp_dollars / (tp_dollars + fp_dollars)

    return {
        "dollar_recall": dollar_recall,    # % of fraud value caught
        "dollar_precision": dollar_precision,  # % of flagged transactions that are fraud
        "fraud_dollars_missed": fn_dollars,
        "legitimate_dollars_blocked": fp_dollars,
    }
```

**Production reality**: At Stripe/Adyen scale, 0.1% false positive rate means thousands of legitimate transactions blocked per hour. Dollar-weighted recall is reported to risk teams; count-weighted recall is reported to ML teams.

---

## 3. Information Retrieval / Search Ranking (NDCG, MRR)

**Context**: A search engine or internal knowledge base retrieval system. Not just "did we retrieve the right document?" but "did we rank it appropriately?"

```python
import numpy as np
from sklearn.metrics import ndcg_score

# Multi-query NDCG evaluation
def evaluate_retrieval_system(
    queries: list[str],
    retrieval_fn,
    relevance_labels: dict,  # {query: {doc_id: relevance_score}}
    k: int = 10,
) -> dict:
    ndcg_scores, mrr_scores, hit_rates = [], [], []

    for query in queries:
        retrieved_docs = retrieval_fn(query, k=k)
        labels = relevance_labels.get(query, {})

        # NDCG@k
        ideal_relevances = sorted(labels.values(), reverse=True)[:k]
        actual_relevances = [labels.get(doc_id, 0) for doc_id in retrieved_docs[:k]]

        if sum(ideal_relevances) > 0:
            ndcg = ndcg_score(
                [ideal_relevances + [0] * (k - len(ideal_relevances))],
                [actual_relevances + [0] * (k - len(actual_relevances))],
                k=k,
            )
            ndcg_scores.append(ndcg)

        # MRR@k
        for rank, doc_id in enumerate(retrieved_docs[:k], 1):
            if labels.get(doc_id, 0) > 0:  # any relevant doc
                mrr_scores.append(1.0 / rank)
                break
        else:
            mrr_scores.append(0.0)

        # Hit Rate@k
        hit_rates.append(
            int(any(labels.get(doc_id, 0) > 0 for doc_id in retrieved_docs[:k]))
        )

    return {
        "ndcg@k": np.mean(ndcg_scores) if ndcg_scores else 0.0,
        "mrr@k": np.mean(mrr_scores),
        "hit_rate@k": np.mean(hit_rates),
        "k": k,
    }
```

**Metric choice by scenario**:
- Single correct answer (FAQ lookup): MRR — measures if the right answer is near the top
- Graded relevance (product search, web search): NDCG — measures ranking quality with graduated relevance levels
- Binary relevance, any hit is success (knowledge base): Hit Rate@K

---

## 4. NLG Evaluation: Translation and Summarization

**Translation pipeline (English → French)**:

```python
import evaluate

# Evaluation suite for MT
sacrebleu = evaluate.load("sacrebleu")
comet = evaluate.load("comet")
bertscore = evaluate.load("bertscore")

predictions = [translated_sentence_1, translated_sentence_2, ...]
references = [[reference_1], [reference_2], ...]  # list of refs per source

bleu_result = sacrebleu.compute(predictions=predictions, references=references)
# BLEU: 25–35 is acceptable for MT; 40+ is strong

bert_result = bertscore.compute(predictions=predictions, references=[r[0] for r in references], lang="fr")
# BERTScore F1 > 0.90 is strong

# COMET (best MT metric as of 2026, uses neural model trained on human rankings)
comet_result = comet.compute(
    sources=source_sentences,
    predictions=predictions,
    references=[r[0] for r in references],
)
# COMET score > 0.85 is strong; human correlation ≈ 0.92
```

**Summarization metrics hierarchy**:
1. **ROUGE-2 recall**: is the content covered? (primary for extractive summarization)
2. **BERTScore F1**: semantic quality (primary for abstractive)
3. **SummaC / QuestEval**: factual consistency (critical — summaries can be fluent but factually wrong)
4. **LLM-as-judge**: overall quality, coherence, conciseness

---

## 5. LLM Fine-Tuning Evaluation

**Context**: Fine-tuning a model for a classification or extraction task. Standard classification metrics apply, but with LLM-specific concerns.

```python
# Instruction-following accuracy: does the model output the expected format?
def parse_classification_response(response: str, valid_labels: set) -> str | None:
    """Extract label from LLM response. Returns None if format invalid."""
    response_lower = response.strip().lower()
    for label in valid_labels:
        if label.lower() in response_lower:
            return label
    return None  # format failure

def evaluate_llm_classifier(model, eval_dataset, valid_labels):
    predictions, targets, format_failures = [], [], 0

    for item in eval_dataset:
        response = model.generate(item["prompt"])
        pred = parse_classification_response(response, valid_labels)
        if pred is None:
            format_failures += 1
            continue
        predictions.append(pred)
        targets.append(item["label"])

    from sklearn.metrics import classification_report
    return {
        "format_failure_rate": format_failures / len(eval_dataset),
        "classification_report": classification_report(targets, predictions),
        "f1_macro": f1_score(targets, predictions, average="macro"),
    }
```

**Critical metric for LLMs**: `format_failure_rate` — the fraction of responses that don't conform to the expected output format. A fine-tuned model with 0% format failures and F1=0.80 is better than one with 10% format failures and nominal F1=0.88 (because 10% of responses are unusable).

---

## 6. Recommendation Systems (NDCG, Coverage, Diversity)

```python
def evaluate_recommender(
    user_ids: list,
    recommended_items: dict,  # user_id -> list[item_id]
    purchased_items: dict,    # user_id -> list[item_id] (ground truth)
    catalog_size: int,
    k: int = 10,
) -> dict:
    precisions_at_k, recalls_at_k, ndcg_at_k = [], [], []
    all_recommended = set()

    for user_id in user_ids:
        recs = recommended_items.get(user_id, [])[:k]
        relevant = set(purchased_items.get(user_id, []))
        all_recommended.update(recs)

        hits = len(set(recs) & relevant)
        precisions_at_k.append(hits / k if recs else 0.0)
        recalls_at_k.append(hits / len(relevant) if relevant else 0.0)

        # Binary NDCG: relevance is 0 or 1
        relevance_vec = [1 if item in relevant else 0 for item in recs]
        ideal_vec = sorted(relevance_vec, reverse=True)
        ndcg_val = ndcg_score([ideal_vec + [0]*(k-len(ideal_vec))],
                               [relevance_vec + [0]*(k-len(relevance_vec))], k=k)
        ndcg_at_k.append(ndcg_val)

    return {
        f"precision@{k}": np.mean(precisions_at_k),
        f"recall@{k}": np.mean(recalls_at_k),
        f"ndcg@{k}": np.mean(ndcg_at_k),
        "catalog_coverage": len(all_recommended) / catalog_size,  # diversity
    }
```

**Beyond accuracy**: Catalog coverage (are all items getting recommended, or just popular ones?), diversity (intra-list diversity — are the k recommendations varied?), and novelty (are recommendations surprising vs. obvious?). These are critical for business health but invisible to precision/recall.

---

## 7. Production Metric Monitoring (Drift Detection)

```python
from scipy import stats

def detect_metric_drift(
    baseline_scores: list[float],
    current_scores: list[float],
    metric_name: str,
    significance_level: float = 0.05,
) -> dict:
    """KS test for distribution shift in a metric over time."""
    ks_stat, p_value = stats.ks_2samp(baseline_scores, current_scores)
    mean_delta = np.mean(current_scores) - np.mean(baseline_scores)
    pct_change = (mean_delta / np.mean(baseline_scores)) * 100

    return {
        "metric": metric_name,
        "baseline_mean": np.mean(baseline_scores),
        "current_mean": np.mean(current_scores),
        "mean_delta": mean_delta,
        "pct_change": pct_change,
        "ks_statistic": ks_stat,
        "p_value": p_value,
        "drift_detected": p_value < significance_level,
        "severity": "critical" if abs(pct_change) > 10 else "warning" if abs(pct_change) > 5 else "ok",
    }
```
