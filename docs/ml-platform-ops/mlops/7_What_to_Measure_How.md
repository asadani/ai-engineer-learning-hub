# What to Measure & How

## Data Quality Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Null rate per column** | % of null values per feature | < 1% (non-nullable) | > 5% | Pandas profiler / Great Expectations |
| **Out-of-range rate** | % of values outside expected bounds | < 0.1% | > 1% | Schema validation at ingestion |
| **Schema violation count** | Fields with wrong type or format | 0 | > 0 | Schema registry + Avro/Protobuf |
| **Row count vs baseline** | Absolute count vs rolling 30d avg | Within ±15% | Z-score > 3σ | COUNT(*) on arrival |
| **Duplicate rate** | % of duplicate primary keys | < 0.01% | > 0.1% | COUNT DISTINCT / COUNT |
| **Freshness lag** | Time since last data update | < 1h (streaming) | > 2h | Max(event_timestamp) - now() |
| **Feature completeness** | % of required features non-null at serving | > 99% | < 95% | Online store lookup audit |

## Data Drift Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **PSI (numeric)** | Population Stability Index vs training dist | < 0.10 | > 0.20 | Binned histogram comparison |
| **KS statistic** | Kolmogorov-Smirnov test statistic | p-value > 0.05 | p-value < 0.01 | scipy.stats.ks_2samp |
| **Jensen-Shannon divergence (categorical)** | Distribution distance [0,1] | < 0.05 | > 0.10 | scipy.spatial.distance.jensenshannon |
| **Chi-squared p-value** | Statistical test for categorical shift | > 0.05 | < 0.01 | chi2_contingency |
| **Dataset drift share** | % of features with detected drift | < 10% | > 30% | Evidently / SageMaker Monitor |
| **New category rate** | Categories in prod not seen in training | 0% | > 0% | Set difference: prod cats - train cats |
| **Prediction distribution PSI** | PSI on model output scores | < 0.10 | > 0.20 | Same as feature PSI |

## Model Performance Metrics

| Metric | Definition | Target | Alert | Requires Labels? |
|--------|-----------|--------|-------|-----------------|
| **AUC-ROC** | Area under ROC curve | > baseline | < baseline × 0.97 | Yes |
| **AUC-PR** | Area under precision-recall curve (preferred for imbalanced) | > baseline | < baseline × 0.97 | Yes |
| **Precision at k%** | Precision at top-k% scored positive | > baseline | < baseline × 0.95 | Yes |
| **Recall at decision threshold** | True positive rate at operating point | > SLA | < SLA × 0.95 | Yes |
| **PSI on scores** | Distribution shift of output scores | < 0.10 | > 0.20 | No (proxy metric) |
| **Prediction flip rate** | % of cases where score changes > 0.1 vs champion | < 20% | > 40% | No |
| **Calibration error (ECE)** | Expected calibration error | < 0.03 | > 0.08 | Yes |
| **Slice metric disparity** | Max AUC delta across protected groups | < 0.05 | > 0.10 | Yes |

## Serving Infrastructure Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Inference latency p50** | Median prediction time | < 50ms | > 100ms | SageMaker CloudWatch |
| **Inference latency p99** | 99th pct prediction time | < 200ms | > 500ms | SageMaker CloudWatch |
| **Endpoint availability** | % of requests successfully served | > 99.9% | < 99.5% | CloudWatch 5xx rate |
| **Throughput (RPS)** | Requests per second | Within capacity | > 80% capacity | CloudWatch InvocationsPerInstance |
| **CPU/GPU utilization** | Instance utilization | 40–70% | > 85% or < 20% | CloudWatch |
| **Memory utilization** | RAM used / total | < 80% | > 90% | CloudWatch |
| **Model load time** | Time to first prediction after cold start | < 30s | > 120s | Custom metric |
| **Feature retrieval latency** | Online store lookup time | < 10ms | > 30ms | Feature store SDK |

## Pipeline Health Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Pipeline success rate** | Successful runs / total triggered | > 95% | < 90% | Pipeline execution logs |
| **Pipeline duration** | Wall clock time for full pipeline | Baseline | > 2× baseline | Start/end timestamps |
| **Quality gate pass rate** | Runs where model passed eval gate | > 80% | < 60% | Quality gate logs |
| **Model registration rate** | Pipelines that produced a registered model | > 80% | < 60% | Model registry |
| **Time to production** | Trigger → production deployment | < 4h | > 24h | Trigger timestamp → deploy timestamp |
| **Retraining frequency** | How often retraining is triggered | Per schedule | Missed scheduled run | Scheduler metrics |
| **Data freshness at training** | Age of newest training data | < 24h | > 48h | Max(training data timestamp) |

---

## Instrumentation Implementation

```python
import boto3
import time
import json
from dataclasses import dataclass, asdict
from typing import Optional
import uuid

cw = boto3.client("cloudwatch", region_name="us-east-1")

@dataclass
class PredictionRecord:
    record_id: str
    model_name: str
    model_version: str
    timestamp: float
    feature_values: dict
    prediction_score: float
    prediction_label: str
    latency_ms: float
    data_source: str          # "online_store" | "real_time" | "cache"
    cache_hit: bool

@dataclass
class MonitoringWindow:
    model_name: str
    window_start: float
    window_end: float
    prediction_count: int
    avg_score: float
    score_std: float
    p50_latency_ms: float
    p99_latency_ms: float
    error_rate: float
    feature_psi: dict         # {feature_name: psi_value}
    drift_detected: bool

def emit_prediction_to_cloudwatch(record: PredictionRecord):
    dims = [
        {"Name": "ModelName", "Value": record.model_name},
        {"Name": "ModelVersion", "Value": record.model_version},
    ]
    cw.put_metric_data(
        Namespace="MLOps/Predictions",
        MetricData=[
            {"MetricName": "PredictionScore",   "Value": record.prediction_score,  "Unit": "None",         "Dimensions": dims},
            {"MetricName": "InferenceLatencyMs","Value": record.latency_ms,        "Unit": "Milliseconds", "Dimensions": dims},
            {"MetricName": "CacheHit",          "Value": int(record.cache_hit),    "Unit": "Count",        "Dimensions": dims},
        ],
    )

def emit_drift_metrics(model_name: str, version: str, drift_results: dict):
    dims = [{"Name": "ModelName", "Value": model_name}, {"Name": "ModelVersion", "Value": version}]
    metric_data = [
        {"MetricName": "DatasetDrift",   "Value": int(drift_results["dataset_drift"]),    "Unit": "Count",       "Dimensions": dims},
        {"MetricName": "DriftedFeatures","Value": drift_results["drifted_count"],          "Unit": "Count",       "Dimensions": dims},
        {"MetricName": "DriftShare",     "Value": drift_results["drift_share"],            "Unit": "None",        "Dimensions": dims},
    ]
    for feature, psi in drift_results.get("psi_by_feature", {}).items():
        feat_dims = dims + [{"Name": "Feature", "Value": feature}]
        metric_data.append({"MetricName": "FeaturePSI", "Value": psi, "Unit": "None", "Dimensions": feat_dims})
    cw.put_metric_data(Namespace="MLOps/Drift", MetricData=metric_data)

def emit_performance_metrics(model_name: str, version: str, perf: dict, slice_metrics: dict):
    dims = [{"Name": "ModelName", "Value": model_name}, {"Name": "ModelVersion", "Value": version}]
    cw.put_metric_data(
        Namespace="MLOps/Performance",
        MetricData=[
            {"MetricName": "AUCPR",          "Value": perf["auc_pr"],       "Unit": "None", "Dimensions": dims},
            {"MetricName": "AUCROC",         "Value": perf["auc_roc"],      "Unit": "None", "Dimensions": dims},
            {"MetricName": "CalibrationECE", "Value": perf.get("ece", 0),   "Unit": "None", "Dimensions": dims},
        ],
    )
    # Emit per-slice metrics for fairness monitoring
    for group, metrics in slice_metrics.items():
        if group.startswith("_"):
            continue
        slice_dims = dims + [{"Name": "Slice", "Value": str(group)}]
        cw.put_metric_data(
            Namespace="MLOps/Fairness",
            MetricData=[{"MetricName": "SliceAUCPR", "Value": metrics["auc_pr"], "Unit": "None", "Dimensions": slice_dims}],
        )
```

---

## Alerting Policy

```yaml
# CloudWatch / PagerDuty alerting rules for production ML systems

alerts:

  # Data quality — upstream pipeline failure
  - name: DataRowCountAnomaly
    condition: row_count_z_score > 3.0 or row_count_z_score < -3.0
    severity: critical
    action: pagerduty
    message: "Data row count anomaly: Z-score {value:.1f}. Upstream pipeline may have failed."

  - name: HighNullRate
    condition: null_rate > 0.05
    severity: warning
    action: slack
    message: "Column {feature} null rate {value:.1%} exceeds 5% threshold"

  # Feature drift — leading indicator of model degradation
  - name: DatasetDriftDetected
    condition: drift_share > 0.30
    severity: warning
    action: slack + jira_ticket
    message: "{drifted_features} of features drifted. Consider retraining."

  - name: HighPSIOnCriticalFeature
    condition: feature_psi[critical_features] > 0.20
    severity: critical
    action: pagerduty
    message: "Critical feature {feature} PSI={value:.3f} — significant distribution shift. Immediate review required."

  # Model performance — lagging indicator (requires labels)
  - name: ModelPerformanceDegradation
    condition: auc_pr < baseline_auc_pr * 0.97
    severity: critical
    action: pagerduty
    message: "Model AUC-PR dropped from {baseline:.3f} to {value:.3f}. Investigate and consider rollback."

  - name: FairnessDisparity
    condition: slice_auc_pr_disparity > 0.10
    severity: warning
    action: slack + compliance_team
    message: "Fairness alert: AUC-PR disparity {value:.3f} across groups exceeds 0.10"

  # Serving health — immediate operational issues
  - name: HighInferenceLatency
    condition: latency_p99_ms > 500
    period: 5m
    severity: critical
    action: pagerduty
    message: "P99 inference latency {value:.0f}ms exceeds 500ms SLA"

  - name: HighEndpointErrorRate
    condition: error_rate_5m > 0.01
    severity: critical
    action: pagerduty
    message: "Endpoint error rate {value:.1%} — potential model serving failure"

  # Pipeline health
  - name: PipelineFailure
    condition: pipeline_success_rate_24h < 0.90
    severity: warning
    action: slack
    message: "ML pipeline success rate {value:.0%} below 90% in last 24h"

  - name: ScheduledRetrainingMissed
    condition: hours_since_last_retrain > expected_interval_hours * 1.5
    severity: warning
    action: slack
    message: "Scheduled retraining not triggered in {value:.0f} hours — check scheduler"
```
