# Products & Tools

## Core Computation Libraries

### scikit-learn `metrics`

The de facto standard for classical ML metrics in Python. Every metric covered in Section 2 is implemented here.

```python
from sklearn.metrics import (
    # Classification
    accuracy_score, balanced_accuracy_score,
    precision_score, recall_score, f1_score, fbeta_score,
    classification_report, confusion_matrix,
    roc_auc_score, average_precision_score,
    matthews_corrcoef, cohen_kappa_score,
    roc_curve, precision_recall_curve,
    # Regression
    mean_absolute_error, mean_squared_error, r2_score,
    mean_absolute_percentage_error, explained_variance_score,
    # Multilabel
    hamming_loss, jaccard_score,
)

# Comprehensive evaluation in one call
report = classification_report(
    y_true, y_pred,
    target_names=class_names,
    output_dict=True,    # returns dict for programmatic access
    zero_division=0,     # suppress warnings for absent classes
)
```

**Important**: `average_precision_score` = AUC-PR (not the same as precision@1). The name is confusing but the implementation is correct.

### TorchMetrics

GPU-accelerated, training-loop-friendly metrics for PyTorch. Handles batched updates and accumulation across batches — critical for large datasets where you can't compute metrics on all data at once.

```python
import torchmetrics
import torch

# Stateful metric: update batch-by-batch, compute at epoch end
precision = torchmetrics.Precision(task="binary", threshold=0.5)
recall = torchmetrics.Recall(task="binary", threshold=0.5)
f1 = torchmetrics.F1Score(task="binary")
auroc = torchmetrics.AUROC(task="binary")

# MetricCollection: compute many metrics simultaneously
metrics = torchmetrics.MetricCollection({
    "precision": torchmetrics.Precision(task="binary"),
    "recall": torchmetrics.Recall(task="binary"),
    "f1": torchmetrics.F1Score(task="binary"),
    "auroc": torchmetrics.AUROC(task="binary"),
})

for batch_preds, batch_targets in dataloader:
    metrics.update(batch_preds, batch_targets)

results = metrics.compute()  # {'precision': 0.82, 'recall': 0.79, ...}
metrics.reset()
```

**Why TorchMetrics over scikit-learn during training**: scikit-learn requires materializing all predictions before computing — memory-intensive for large datasets. TorchMetrics accumulates statistics incrementally.

---

## NLG Evaluation

### Hugging Face `evaluate`

Unified interface for NLG and NLU metrics. Loads metrics from the HuggingFace Hub, supports custom metrics.

```python
import evaluate

# ROUGE
rouge = evaluate.load("rouge")
results = rouge.compute(
    predictions=["The cat sat on the mat"],
    references=["A cat was on the mat"],
    use_stemmer=True,
)
# {'rouge1': 0.727, 'rouge2': 0.400, 'rougeL': 0.727, 'rougeLsum': 0.727}

# BLEU
bleu = evaluate.load("bleu")
results = bleu.compute(
    predictions=["The cat sat on the mat"],
    references=[["A cat was on the mat"]],  # list of references per prediction
)

# BERTScore
bertscore = evaluate.load("bertscore")
results = bertscore.compute(
    predictions=["The cat sat on the mat"],
    references=["A cat was on the mat"],
    lang="en",
    model_type="microsoft/deberta-xlarge-mnli",
)
# {'precision': [0.927], 'recall': [0.927], 'f1': [0.927], 'hashcode': '...'}

# SacreBLEU (standardized BLEU for MT)
sacrebleu = evaluate.load("sacrebleu")
results = sacrebleu.compute(
    predictions=["The cat sat on the mat"],
    references=[["A cat was on the mat"]],
)
```

### `bert_score` library (direct)

```python
from bert_score import score, BERTScorer

# Batch scoring
P, R, F1 = score(
    cands=predictions,
    refs=references,
    lang="en",
    model_type="microsoft/deberta-xlarge-mnli",  # best English model
    batch_size=64,
    device="cuda",
    verbose=True,
)

# Reusable scorer (avoid reloading model)
scorer = BERTScorer(lang="en", rescale_with_baseline=True)
P, R, F1 = scorer.score(predictions, references)
```

---

## GenAI / RAG Evaluation

### RAGAS

```python
from ragas import evaluate
from ragas.metrics import (
    faithfulness,           # groundedness
    answer_relevance,       # does answer address the question
    context_precision,      # signal-to-noise in retrieved context
    context_recall,         # coverage of relevant information
    answer_correctness,     # overall correctness vs ground truth
    answer_similarity,      # semantic similarity to reference
)
from ragas.metrics.critique import (
    harmfulness,            # safety metric
    coherence,
    conciseness,
)
from datasets import Dataset

dataset = Dataset.from_dict({
    "question": questions,
    "answer": answers,
    "contexts": contexts,           # list[list[str]] per question
    "ground_truth": ground_truths,  # optional
})
results = evaluate(dataset, metrics=[faithfulness, answer_relevance, context_precision])
```

### DeepEval

```python
from deepeval.metrics import (
    GEval,
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    HallucinationMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    SummarizationMetric,
    ToxicityMetric,
    BiasMetric,
)
from deepeval.test_case import LLMTestCase

test_case = LLMTestCase(
    input="What is the policy for returns?",
    actual_output=system_response,
    expected_output=ground_truth,
    retrieval_context=retrieved_chunks,
)

faithfulness_metric = FaithfulnessMetric(threshold=0.7, model="gpt-4o-mini")
faithfulness_metric.measure(test_case)
print(faithfulness_metric.score, faithfulness_metric.reason)
```

---

## Experiment Tracking & Metric Dashboards

### MLflow

```python
import mlflow

with mlflow.start_run(run_name="bert_classifier_v3"):
    mlflow.log_params({
        "model": "bert-base-uncased",
        "learning_rate": 2e-5,
        "batch_size": 32,
        "epochs": 3,
    })
    mlflow.log_metrics({
        "val_f1_macro": 0.847,
        "val_auc_roc": 0.923,
        "val_auc_pr": 0.711,
        "val_mcc": 0.789,
        "test_f1_macro": 0.831,
    })
    mlflow.sklearn.log_model(model, "model")
```

### Weights & Biases

```python
import wandb

wandb.init(project="intent-classifier", name="bert-v3-run5")

# Log per-step metrics during training
for epoch, metrics in training_loop():
    wandb.log({
        "epoch": epoch,
        "train/loss": metrics["loss"],
        "val/f1_macro": metrics["f1"],
        "val/precision": metrics["precision"],
        "val/recall": metrics["recall"],
        "val/auc_roc": metrics["auc_roc"],
    })

# Log confusion matrix as artifact
wandb.log({"confusion_matrix": wandb.plot.confusion_matrix(
    probs=None,
    y_true=y_true,
    preds=y_pred,
    class_names=class_names,
)})
```

---

## Production Monitoring / Drift Detection

### Evidently AI

```python
from evidently.report import Report
from evidently.metric_preset import ClassificationPreset, DataDriftPreset
from evidently.metrics import (
    ClassificationQualityMetric,
    ClassificationClassBalance,
    ClassificationConfusionMatrix,
)

# Compare current production metrics to reference (training) period
report = Report(metrics=[
    ClassificationPreset(),
    DataDriftPreset(),
])
report.run(
    reference_data=training_df,   # baseline
    current_data=production_df,   # last 7 days of production
)
report.save_html("metric_drift_report.html")
```

### Amazon SageMaker Model Monitor

```python
import boto3
from sagemaker.model_monitor import DataCaptureConfig, ModelQualityMonitor

# Configure data capture on endpoint
data_capture = DataCaptureConfig(
    enable_capture=True,
    sampling_percentage=20,
    destination_s3_uri="s3://my-bucket/captures/",
)

# Schedule quality monitor
monitor = ModelQualityMonitor(role=role, sagemaker_session=session)
monitor.suggest_baseline(
    baseline_dataset="s3://my-bucket/baseline/",
    dataset_format={"csv": {"header": True}},
    problem_type="BinaryClassification",
    ground_truth_attribute="label",
)
monitor.create_monitoring_schedule(
    monitor_schedule_name="intent-classifier-quality",
    endpoint_input=endpoint_name,
    ground_truth_input="s3://my-bucket/ground-truth/",
    problem_type="BinaryClassification",
    output_s3_uri="s3://my-bucket/monitor-output/",
    schedule_cron_expression="cron(0 * ? * * *)",  # hourly
    constraints=monitor.suggested_constraints(),
)
```

---

## Specialized Tools by Domain

| Domain | Tool | Key Metrics |
|--------|------|-------------|
| **NLP / NLU** | `seqeval` | Entity-level F1 for NER; sequence labeling |
| **MT evaluation** | `sacrebleu` | Standardized BLEU, chrF, TER |
| **Code generation** | `bigcode-evaluation-harness` | Pass@k, MBPP, HumanEval |
| **Summarization** | `summac`, `questeval` | Factual consistency beyond ROUGE |
| **Safety** | `detoxify`, `perspective-api` | Toxicity, identity attack, insult scores |
| **Embeddings** | `MTEB` | 56 tasks; recall@k, MRR |
| **Calibration** | `netcal` | ECE, MCE, reliability diagrams |
| **Fairness** | `fairlearn`, `aif360` | Demographic parity, equalized odds |
