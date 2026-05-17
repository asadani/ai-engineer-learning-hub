# What to Measure & How

## Universal Metric Checklist by Task Type

### Binary Classification

| Metric | Type | Target (domain-dependent) | Collection Method |
|--------|------|--------------------------|-------------------|
| **AUC-PR** | Gauge (0–1) | > 0.70 for imbalanced | `average_precision_score` |
| **AUC-ROC** | Gauge (0–1) | > 0.85 | `roc_auc_score` |
| **MCC** | Gauge (−1 to +1) | > 0.60 | `matthews_corrcoef` |
| **F1 at operating threshold** | Gauge (0–1) | ≥ domain requirement | `f1_score` |
| **Precision at operating threshold** | Gauge (0–1) | ≥ domain requirement | `precision_score` |
| **Recall at operating threshold** | Gauge (0–1) | ≥ domain requirement | `recall_score` |
| **ECE** | Gauge (0–1) | < 0.05 | Calibration curve |
| **False Positive Rate** | Gauge (0–1) | < domain threshold | `fp/(fp+tn)` |
| **Inference latency p99** | Histogram (ms) | < SLO | Trace per prediction |

### Multiclass Classification

| Metric | Type | Target | Collection Method |
|--------|------|--------|-------------------|
| **F1 macro** | Gauge | > 0.80 | `f1_score(average='macro')` |
| **F1 per class (minority classes)** | Gauge | > 0.70 | `f1_score(average=None)` |
| **Balanced accuracy** | Gauge | > 0.80 | `balanced_accuracy_score` |
| **Per-class confusion matrix** | Matrix | Review weekly | `confusion_matrix` |

### Ranking / Retrieval

| Metric | Type | Target | Collection Method |
|--------|------|--------|-------------------|
| **NDCG@10** | Gauge | > 0.75 | Offline eval against labels |
| **MRR@10** | Gauge | > 0.70 | Offline eval |
| **Hit Rate@5** | Gauge | > 0.85 | Offline eval |
| **Mean retrieval latency** | Histogram | p99 < 50ms | Trace |

### GenAI / LLM Pipeline

| Metric | Type | Target | Collection Method |
|--------|------|--------|-------------------|
| **Faithfulness** | Gauge | > 0.85 | RAGAS / LLM-judge |
| **Answer relevance** | Gauge | > 0.80 | RAGAS / LLM-judge |
| **Context precision** | Gauge | > 0.70 | RAGAS |
| **BERTScore F1** | Gauge | > 0.88 | `bert_score` library |
| **Format compliance rate** | Gauge | > 0.99 | Schema validation |
| **Refusal accuracy** | Gauge | > 0.99 | Safety test suite |
| **Hallucination rate** | Gauge | < 0.05 | LLM-judge on sample |
| **E2E latency p99** | Histogram | < 3000ms | Distributed trace |
| **Cost per query (USD)** | Gauge | < budget | Token count × price |

---

## Metric Monitoring Pipeline

```python
import time
from dataclasses import dataclass, field
from collections import deque
from typing import Callable
import numpy as np

@dataclass
class MetricMonitor:
    """Rolling window metric monitor with alerting."""
    name: str
    window_size: int = 1000
    alert_threshold: float = 0.0
    alert_direction: str = "below"  # "below" or "above"
    _values: deque = field(default_factory=deque)
    _alert_fn: Callable = None

    def record(self, value: float) -> None:
        self._values.append(value)
        if len(self._values) > self.window_size:
            self._values.popleft()
        self._check_alert()

    def _check_alert(self) -> None:
        if len(self._values) < 50:  # need minimum samples
            return
        rolling_mean = np.mean(self._values)
        if self.alert_direction == "below" and rolling_mean < self.alert_threshold:
            if self._alert_fn:
                self._alert_fn(self.name, rolling_mean, self.alert_threshold)
        elif self.alert_direction == "above" and rolling_mean > self.alert_threshold:
            if self._alert_fn:
                self._alert_fn(self.name, rolling_mean, self.alert_threshold)

    @property
    def stats(self) -> dict:
        if not self._values:
            return {}
        arr = np.array(self._values)
        return {
            "mean": arr.mean(), "std": arr.std(),
            "p10": np.percentile(arr, 10), "p50": np.percentile(arr, 50),
            "p90": np.percentile(arr, 90), "n": len(arr),
        }

# Usage in production
faithfulness_monitor = MetricMonitor(
    name="faithfulness",
    window_size=500,
    alert_threshold=0.80,
    alert_direction="below",
    _alert_fn=lambda name, val, thresh: pagerduty.alert(f"{name}={val:.3f} < {thresh}"),
)
```

---

## Metric Logging Schema

Every prediction in production should emit a structured log record enabling offline metric computation:

```json
{
    "trace_id": "abc-123",
    "timestamp": "2026-03-22T10:00:00Z",
    "model_version": "v2.4.1",
    "task_type": "binary_classification",

    "input": {"text_length": 342, "language": "en", "category": "fraud_check"},
    "prediction": {"label": 1, "probability": 0.89, "latency_ms": 23},
    "ground_truth": {"label": null},  // populated async when label arrives

    "metrics": {
        "prediction_confidence": 0.89,
        "inference_latency_ms": 23
    },

    "model": {
        "name": "fraud_detector_v3",
        "threshold": 0.75,
        "features_used": 47
    }
}
```

Ground truth labels often arrive asynchronously (fraud confirmed hours/days later). Join on `trace_id` to retroactively compute precision, recall, F1 from logged predictions + labels.

---

## Metric Computation in CI

```python
# scripts/evaluate_model.py
import argparse
import json
import numpy as np
from pathlib import Path
from sklearn.metrics import (
    classification_report, roc_auc_score,
    average_precision_score, matthews_corrcoef,
)

def run_evaluation(
    model_path: str,
    eval_data_path: str,
    baseline_path: str,
    regression_threshold: float = 0.97,
) -> int:
    """Returns 0 (pass) or 1 (fail) for CI gate."""
    model = load_model(model_path)
    eval_data = load_dataset(eval_data_path)
    baseline = json.loads(Path(baseline_path).read_text())

    y_true = eval_data["labels"]
    y_scores = model.predict_proba(eval_data["features"])[:, 1]
    y_pred = (y_scores >= model.threshold).astype(int)

    metrics = {
        "auc_roc": roc_auc_score(y_true, y_scores),
        "auc_pr": average_precision_score(y_true, y_scores),
        "mcc": matthews_corrcoef(y_true, y_pred),
        "f1": classification_report(y_true, y_pred, output_dict=True)["1"]["f1-score"],
        "precision": classification_report(y_true, y_pred, output_dict=True)["1"]["precision"],
        "recall": classification_report(y_true, y_pred, output_dict=True)["1"]["recall"],
    }

    regressions = []
    for metric, value in metrics.items():
        if metric in baseline:
            ratio = value / baseline[metric]
            if ratio < regression_threshold:
                regressions.append(
                    f"REGRESSION: {metric}={value:.4f} < {regression_threshold*100:.0f}% of baseline {baseline[metric]:.4f}"
                )

    if regressions:
        print("\n".join(regressions))
        return 1

    print(f"All metrics within {regression_threshold*100:.0f}% of baseline. Current: {metrics}")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--eval-data", required=True)
    parser.add_argument("--baseline", required=True)
    args = parser.parse_args()
    exit(run_evaluation(args.model, args.eval_data, args.baseline))
```

---

## Domain-Specific Metric Reference Card

| Domain | Primary Metric | Secondary Metrics | Avoid |
|--------|---------------|------------------|-------|
| **Medical diagnosis** | Recall @ fixed threshold | Precision, AUC-PR, ECE | Accuracy |
| **Fraud detection** | AUC-PR, Dollar-weighted recall | Precision@90%recall | Accuracy |
| **Spam filter** | Precision (F0.5) | Recall, AUC-ROC | Accuracy |
| **Search/IR** | NDCG@10 | MRR@10, Hit Rate@K | Accuracy |
| **Machine translation** | COMET (2026) | BERTScore, SacreBLEU | Raw BLEU |
| **Summarization** | BERTScore + SummaC | ROUGE-2 recall | ROUGE-1 alone |
| **Code generation** | Pass@1 (or Pass@k) | Compilation rate | BLEU |
| **RAG Q&A** | Faithfulness + Answer Relevance | Context Precision | ROUGE |
| **LLM safety** | Refusal accuracy (FN rate) | False positive rate | N/A |
| **Recommendation** | NDCG@K | Diversity, Coverage | Accuracy |
| **Tabular classification (balanced)** | AUC-ROC, F1 | MCC | Raw accuracy |
| **Tabular classification (imbalanced)** | AUC-PR, MCC | F1 per class | Accuracy, AUC-ROC alone |
| **Regression** | MAE (interpretable) | RMSE, R² | MSE alone |
