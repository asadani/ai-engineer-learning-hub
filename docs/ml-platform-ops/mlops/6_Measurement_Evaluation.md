# Measurement & Evaluation

## What You're Actually Measuring in MLOps

MLOps monitoring has four distinct measurement targets that are often conflated:

1. **Data quality** — Is the input data clean and within expected bounds?
2. **Data/feature drift** — Has the distribution of inputs shifted vs training?
3. **Model performance** — Is the model making correct predictions? (requires labels)
4. **System health** — Is the serving infrastructure reliable, fast, and available?

These require different data sources, different statistical tools, and different response actions.

---

## Data Quality Evaluation

```python
import pandas as pd
import numpy as np
from dataclasses import dataclass

@dataclass
class DataQualityReport:
    column: str
    null_rate: float
    out_of_range_rate: float
    schema_violations: int
    row_count: int
    passed: bool
    issues: list[str]

def evaluate_data_quality(
    df: pd.DataFrame,
    schema: dict,  # {col: {"type": str, "min": float, "max": float, "nullable": bool}}
    max_null_rate: float = 0.05,
) -> list[DataQualityReport]:
    reports = []
    for col, rules in schema.items():
        issues = []
        null_rate = df[col].isna().mean()
        if null_rate > max_null_rate and not rules.get("nullable", True):
            issues.append(f"null_rate={null_rate:.1%} > max {max_null_rate:.1%}")

        out_of_range = 0
        if "min" in rules and pd.api.types.is_numeric_dtype(df[col]):
            out_of_range += (df[col] < rules["min"]).sum()
        if "max" in rules and pd.api.types.is_numeric_dtype(df[col]):
            out_of_range += (df[col] > rules["max"]).sum()
        out_of_range_rate = out_of_range / len(df)
        if out_of_range_rate > 0.01:
            issues.append(f"out_of_range={out_of_range_rate:.1%}")

        # Type check
        expected_type = rules.get("type")
        if expected_type and str(df[col].dtype) != expected_type:
            issues.append(f"type_mismatch: expected {expected_type}, got {df[col].dtype}")

        reports.append(DataQualityReport(
            column=col, null_rate=null_rate,
            out_of_range_rate=out_of_range_rate, schema_violations=len(issues),
            row_count=len(df), passed=len(issues) == 0, issues=issues,
        ))
    return reports

# Row count anomaly detection (catch upstream pipeline failures)
def check_row_count_anomaly(
    current_count: int,
    historical_counts: list[int],
    sigma_threshold: float = 3.0,
) -> dict:
    mean = np.mean(historical_counts)
    std = np.std(historical_counts)
    z_score = (current_count - mean) / (std + 1e-9)
    return {
        "current": current_count,
        "mean": mean,
        "z_score": z_score,
        "anomaly": abs(z_score) > sigma_threshold,
        "pct_change_from_mean": (current_count - mean) / mean,
    }
```

---

## Drift Detection: Statistical Tests

```python
import numpy as np
from scipy.stats import ks_2samp, chi2_contingency
from scipy.spatial.distance import jensenshannon

def run_full_drift_analysis(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    numeric_features: list[str],
    categorical_features: list[str],
    alpha: float = 0.05,
) -> dict:
    results = {}

    # Numeric features: KS test + PSI
    for col in numeric_features:
        ref_vals = reference[col].dropna().values
        cur_vals = current[col].dropna().values

        # KS test
        ks_stat, ks_p = ks_2samp(ref_vals, cur_vals)

        # PSI
        bins = np.percentile(ref_vals, np.linspace(0, 100, 11))
        bins[0] -= 0.001; bins[-1] += 0.001  # edge correction
        ref_pct = np.histogram(ref_vals, bins=bins)[0] / len(ref_vals) + 1e-6
        cur_pct = np.histogram(cur_vals, bins=bins)[0] / len(cur_vals) + 1e-6
        psi = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))

        results[col] = {
            "type": "numeric",
            "ks_statistic": ks_stat,
            "ks_p_value": ks_p,
            "psi": psi,
            "drift_detected": ks_p < alpha or psi > 0.2,
            "drift_severity": "none" if psi < 0.1 else "slight" if psi < 0.2 else "significant",
        }

    # Categorical features: chi-squared + Jensen-Shannon divergence
    for col in categorical_features:
        ref_dist = reference[col].value_counts(normalize=True)
        cur_dist = current[col].value_counts(normalize=True)
        all_cats = set(ref_dist.index) | set(cur_dist.index)

        ref_probs = np.array([ref_dist.get(c, 0) for c in all_cats])
        cur_probs = np.array([cur_dist.get(c, 0) for c in all_cats])
        ref_probs = ref_probs / ref_probs.sum()
        cur_probs = cur_probs / cur_probs.sum()

        js_div = float(jensenshannon(ref_probs, cur_probs))

        # Chi-squared test (on counts, not proportions)
        ref_counts = (ref_probs * len(reference)).astype(int)
        cur_counts = (cur_probs * len(current)).astype(int)
        _, chi2_p, _, _ = chi2_contingency([ref_counts, cur_counts])

        # New categories in current (not in reference) — always flag
        new_categories = set(cur_dist.index) - set(ref_dist.index)

        results[col] = {
            "type": "categorical",
            "js_divergence": js_div,
            "chi2_p_value": chi2_p,
            "new_categories": list(new_categories),
            "drift_detected": chi2_p < alpha or js_div > 0.1 or bool(new_categories),
        }

    # Summary
    drifted_features = [k for k, v in results.items() if v["drift_detected"]]
    return {
        "feature_results": results,
        "drifted_count": len(drifted_features),
        "drifted_features": drifted_features,
        "drift_share": len(drifted_features) / (len(numeric_features) + len(categorical_features)),
        "dataset_drift": len(drifted_features) / (len(numeric_features) + len(categorical_features)) > 0.3,
    }
```

---

## Model Performance Evaluation (with Labels)

```python
from sklearn.metrics import (
    average_precision_score, roc_auc_score, precision_recall_curve,
    confusion_matrix, classification_report
)

def evaluate_model_performance(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    threshold: float = 0.5,
    decision_thresholds: dict | None = None,  # custom operating points
) -> dict:
    y_pred = (y_scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

    # Core metrics
    metrics = {
        "auc_roc": roc_auc_score(y_true, y_scores),
        "auc_pr": average_precision_score(y_true, y_scores),
        "precision": tp / (tp + fp) if (tp + fp) > 0 else 0,
        "recall": tp / (tp + fn) if (tp + fn) > 0 else 0,
        "specificity": tn / (tn + fp) if (tn + fp) > 0 else 0,
        "prevalence": y_true.mean(),
        "positive_rate": y_pred.mean(),
    }

    # Operating point metrics (business-driven)
    if decision_thresholds:
        for name, threshold in decision_thresholds.items():
            preds = (y_scores >= threshold).astype(int)
            tn_, fp_, fn_, tp_ = confusion_matrix(y_true, preds).ravel()
            metrics[f"precision_at_{name}"] = tp_ / (tp_ + fp_) if (tp_ + fp_) > 0 else 0
            metrics[f"recall_at_{name}"] = tp_ / (tp_ + fn_) if (tp_ + fn_) > 0 else 0

    return metrics

# Slice evaluation — critical for fairness and regulatory compliance
def evaluate_by_slice(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    slice_labels: pd.Series,  # demographic group, geographic region, etc.
) -> dict:
    slice_metrics = {}
    for group in slice_labels.unique():
        mask = slice_labels == group
        if mask.sum() < 50:  # skip tiny slices (noisy)
            continue
        slice_metrics[str(group)] = {
            "n": int(mask.sum()),
            "auc_pr": average_precision_score(y_true[mask], y_scores[mask]),
            "positive_rate": float(y_true[mask].mean()),
        }

    # Fairness: max disparity across groups
    auc_prs = [v["auc_pr"] for v in slice_metrics.values()]
    slice_metrics["_summary"] = {
        "min_auc_pr": min(auc_prs),
        "max_auc_pr": max(auc_prs),
        "disparity": max(auc_prs) - min(auc_prs),
    }
    return slice_metrics
```

---

## Production Monitoring Evaluation Framework

```python
import boto3
import time
from dataclasses import dataclass

cw = boto3.client("cloudwatch", region_name="us-east-1")

@dataclass
class MonitoringEvent:
    model_name: str
    model_version: str
    timestamp: float
    input_features: dict
    prediction_score: float
    prediction_label: str
    latency_ms: float
    actual_label: str | None = None  # filled in later when labels arrive

def emit_prediction_metrics(event: MonitoringEvent):
    dims = [
        {"Name": "ModelName", "Value": event.model_name},
        {"Name": "ModelVersion", "Value": event.model_version},
    ]
    cw.put_metric_data(
        Namespace="MLOps/Predictions",
        MetricData=[
            {"MetricName": "PredictionScore", "Value": event.prediction_score,
             "Unit": "None", "Dimensions": dims},
            {"MetricName": "InferenceLatencyMs", "Value": event.latency_ms,
             "Unit": "Milliseconds", "Dimensions": dims},
            {"MetricName": "RequestCount", "Value": 1,
             "Unit": "Count", "Dimensions": dims},
        ],
    )

def emit_performance_metrics(model_name: str, version: str, metrics: dict):
    dims = [{"Name": "ModelName", "Value": model_name}, {"Name": "ModelVersion", "Value": version}]
    cw.put_metric_data(
        Namespace="MLOps/Performance",
        MetricData=[
            {"MetricName": m_name, "Value": m_val, "Unit": "None", "Dimensions": dims}
            for m_name, m_val in metrics.items()
        ],
    )

# SageMaker Model Monitor — managed drift detection
sm = boto3.client("sagemaker")

sm.create_monitoring_schedule(
    MonitoringScheduleName="fraud-detector-drift-monitor",
    MonitoringScheduleConfig={
        "ScheduleConfig": {"ScheduleExpression": "cron(0 * ? * * *)"},  # hourly
        "MonitoringJobDefinition": {
            "MonitoringInputs": [{
                "EndpointInput": {
                    "EndpointName": "fraud-detector-v12",
                    "LocalPath": "/opt/ml/processing/input/endpoint",
                    "S3DataDistributionType": "FullyReplicated",
                    "S3InputMode": "File",
                },
            }],
            "MonitoringOutputConfig": {
                "MonitoringOutputs": [{
                    "S3Output": {
                        "S3Uri": "s3://ml-monitoring/fraud-detector/output",
                        "LocalPath": "/opt/ml/processing/output",
                        "S3UploadMode": "EndOfJob",
                    }
                }]
            },
            "MonitoringResources": {"ClusterConfig": {"InstanceCount": 1, "InstanceType": "ml.m5.large", "VolumeSizeInGB": 20}},
            "MonitoringAppSpecification": {"ImageUri": "156813124566.dkr.ecr.us-east-1.amazonaws.com/sagemaker-model-monitor-analyzer:latest"},
            "BaselineConfig": {
                "ConstraintsResource": {"S3Uri": "s3://ml-monitoring/fraud-detector/baseline/constraints.json"},
                "StatisticsResource": {"S3Uri": "s3://ml-monitoring/fraud-detector/baseline/statistics.json"},
            },
        },
    },
)
```

---

## Pipeline Health Evaluation

```python
# Track ML pipeline reliability as a first-class metric
from dataclasses import dataclass
from enum import Enum

class PipelineStepStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class PipelineRun:
    run_id: str
    pipeline_name: str
    trigger: str  # "scheduled" | "drift_alert" | "manual"
    started_at: float
    finished_at: float | None
    steps: list[dict]  # [{name, status, duration_s, error}]
    model_registered: bool
    quality_gate_passed: bool

def emit_pipeline_metrics(run: PipelineRun):
    """Track pipeline reliability to catch infrastructure issues early."""
    duration_s = (run.finished_at or time.time()) - run.started_at
    failed_steps = [s for s in run.steps if s["status"] == PipelineStepStatus.FAILED]

    dims = [{"Name": "Pipeline", "Value": run.pipeline_name}]
    cw.put_metric_data(
        Namespace="MLOps/Pipelines",
        MetricData=[
            {"MetricName": "RunDurationSeconds", "Value": duration_s, "Unit": "Seconds", "Dimensions": dims},
            {"MetricName": "RunSuccess", "Value": 1 if not failed_steps else 0, "Unit": "Count", "Dimensions": dims},
            {"MetricName": "ModelRegistered", "Value": 1 if run.model_registered else 0, "Unit": "Count", "Dimensions": dims},
            {"MetricName": "QualityGatePassed", "Value": 1 if run.quality_gate_passed else 0, "Unit": "Count", "Dimensions": dims},
            {"MetricName": "StepFailureCount", "Value": len(failed_steps), "Unit": "Count", "Dimensions": dims},
        ],
    )
```
