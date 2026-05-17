# Key Technical Concepts

## 1. Feature Stores

A feature store is the central infrastructure component that solves training-serving skew and feature reuse. It has two layers:

**Offline store** (batch, for training): S3 + Parquet, Redshift, or Delta Lake. Stores historical feature values with timestamps for point-in-time correct joins.

**Online store** (low-latency, for serving): DynamoDB, Redis, or Cassandra. Stores the latest feature values, retrieved in < 10ms at inference time.

```python
# Feast feature store example
from feast import FeatureStore, Entity, Feature, FeatureView, ValueType, FileSource
from feast.types import Float64, Int64, String
import pandas as pd
from datetime import timedelta

store = FeatureStore(repo_path="feature_repo/")

# Define entity (the primary key that features are keyed on)
customer = Entity(name="customer_id", value_type=ValueType.INT64)

# Define feature view (a group of related features)
customer_features = FeatureView(
    name="customer_stats",
    entities=[customer],
    ttl=timedelta(days=30),
    features=[
        Feature(name="total_purchases_30d", dtype=Float64),
        Feature(name="avg_order_value", dtype=Float64),
        Feature(name="days_since_last_purchase", dtype=Int64),
        Feature(name="preferred_category", dtype=String),
    ],
    source=FileSource(path="data/customer_features.parquet", timestamp_field="event_timestamp"),
)

# At training time: point-in-time correct historical join
entity_df = pd.DataFrame({
    "customer_id": [1001, 1002, 1003],
    "event_timestamp": ["2025-01-01", "2025-01-15", "2025-02-01"],  # label timestamps
})
training_data = store.get_historical_features(
    entity_df=entity_df,
    features=["customer_stats:total_purchases_30d", "customer_stats:avg_order_value"],
).to_df()

# At serving time: real-time feature retrieval (< 10ms from online store)
online_features = store.get_online_features(
    features=["customer_stats:total_purchases_30d", "customer_stats:avg_order_value"],
    entity_rows=[{"customer_id": 1001}],
).to_dict()
```

**The point-in-time join problem:** Training data is labeled with timestamps (e.g., "customer churned on Jan 15"). To avoid label leakage, you must join features as they existed *at* Jan 15, not today's values. Feature stores handle this automatically; ad-hoc SQL joins often don't.

---

## 2. Experiment Tracking

Every training run should be logged: hyperparameters, metrics, artifacts, environment. Without this, you cannot reproduce, compare, or debug models.

```python
import mlflow
import mlflow.sklearn
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score
import pandas as pd

mlflow.set_experiment("fraud-detection-v3")

with mlflow.start_run(run_name="gbm-hyperopt-trial-42"):
    # Log all hyperparameters
    params = {
        "n_estimators": 500,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "min_samples_leaf": 50,
        "class_weight": "balanced",
    }
    mlflow.log_params(params)

    # Log environment
    mlflow.log_param("python_version", "3.11")
    mlflow.log_param("sklearn_version", "1.4.0")
    mlflow.log_param("training_data_version", "s3://ml-data/fraud/v20250301")
    mlflow.log_param("training_rows", 5_230_000)

    # Train
    model = GradientBoostingClassifier(**params)
    model.fit(X_train, y_train)

    # Log all metrics
    y_pred_proba = model.predict_proba(X_val)[:, 1]
    mlflow.log_metrics({
        "val_auc_roc": roc_auc_score(y_val, y_pred_proba),
        "val_auc_pr": average_precision_score(y_val, y_pred_proba),
        "val_precision_at_95_recall": precision_at_recall(y_val, y_pred_proba, 0.95),
        "train_samples": len(X_train),
        "positive_rate_train": y_train.mean(),
    })

    # Log model artifact with signature
    signature = mlflow.models.infer_signature(X_train, model.predict_proba(X_train))
    mlflow.sklearn.log_model(
        model,
        artifact_path="model",
        signature=signature,
        input_example=X_train.iloc[:5],
        registered_model_name="fraud-detector",
    )

    # Log feature importance as artifact
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 8))
    pd.Series(model.feature_importances_, index=X_train.columns).sort_values().plot.barh(ax=ax)
    mlflow.log_figure(fig, "feature_importance.png")
```

---

## 3. Model Registry and Lifecycle Management

The model registry is the source of truth for which model version is in which environment:

```python
from mlflow.tracking import MlflowClient

client = MlflowClient()

# Transition model through lifecycle stages
def promote_to_staging(run_id: str, model_name: str, version: int):
    client.transition_model_version_stage(
        name=model_name,
        version=version,
        stage="Staging",
        archive_existing_versions=False,  # keep old staging version for comparison
    )
    client.set_model_version_tag(model_name, version, "promoted_by", "ci-pipeline")
    client.set_model_version_tag(model_name, version, "run_id", run_id)

def promote_to_production(model_name: str, version: int, approver: str):
    # Archive current production version
    current_prod = client.get_latest_versions(model_name, stages=["Production"])
    for mv in current_prod:
        client.transition_model_version_stage(
            name=model_name, version=mv.version, stage="Archived"
        )

    client.transition_model_version_stage(
        name=model_name, version=version, stage="Production"
    )
    client.set_model_version_tag(model_name, version, "approved_by", approver)
    client.set_model_version_tag(model_name, version, "promoted_at",
                                  datetime.utcnow().isoformat())

# Load the production model for serving
def load_production_model(model_name: str):
    return mlflow.pyfunc.load_model(f"models:/{model_name}/Production")

# SageMaker Model Registry (AWS-native alternative)
import boto3
sm = boto3.client("sagemaker")

sm.update_model_package(
    ModelPackageArn="arn:aws:sagemaker:us-east-1:123456789:model-package/fraud-detector/5",
    ModelApprovalStatus="Approved",  # Pending | Rejected | Approved
    ApprovalDescription="Validated against Jan holdout set. AUC-PR 0.87 vs 0.83 baseline.",
)
```

---

## 4. CI/CD for Machine Learning

ML CI/CD differs from software CI/CD: you're validating data and model quality, not just code correctness.

```yaml
# .github/workflows/ml_pipeline.yaml
name: ML Training Pipeline

on:
  push:
    paths:
      - 'src/models/**'
      - 'src/features/**'
  schedule:
    - cron: '0 2 * * 1'  # retrain every Monday 2 AM

jobs:
  validate-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run data validation
        run: python scripts/validate_data.py --date ${{ github.event.inputs.date || 'latest' }}
        # Fails if: schema mismatch, > 5% nulls, distribution shift detected

  train-and-evaluate:
    needs: validate-data
    runs-on: [self-hosted, gpu]
    steps:
      - name: Launch SageMaker Training Job
        run: |
          python scripts/launch_training.py \
            --config configs/fraud_v3.yaml \
            --data-version $DATA_VERSION \
            --experiment-name "ci-${{ github.sha[:7] }}"

      - name: Evaluate against holdout
        run: python scripts/evaluate.py --run-id $MLFLOW_RUN_ID

      - name: Quality gate check
        run: python scripts/quality_gate.py --min-auc-pr 0.85 --max-regression 0.02

  register-model:
    needs: train-and-evaluate
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Register to staging
        run: python scripts/register_model.py --stage Staging

  shadow-test:
    needs: register-model
    steps:
      - name: Run shadow deployment (24h)
        run: python scripts/shadow_deploy.py --duration 24h --sample-rate 0.1

      - name: Compare shadow vs production metrics
        run: python scripts/compare_shadow.py --threshold 0.98  # new model must be >= 98% as good
```

```python
# scripts/quality_gate.py
import mlflow
import sys

def quality_gate(run_id: str, min_auc_pr: float = 0.85, max_regression: float = 0.02) -> bool:
    client = mlflow.tracking.MlflowClient()
    run = client.get_run(run_id)
    metrics = run.data.metrics

    # Absolute quality check
    if metrics["val_auc_pr"] < min_auc_pr:
        print(f"FAIL: val_auc_pr={metrics['val_auc_pr']:.3f} < threshold {min_auc_pr}")
        return False

    # Regression check: must not be worse than production
    prod_model = load_production_model("fraud-detector")
    prod_metrics = get_production_metrics("fraud-detector")
    if metrics["val_auc_pr"] < prod_metrics["auc_pr"] * (1 - max_regression):
        print(f"FAIL: regression detected. New: {metrics['val_auc_pr']:.3f}, Prod: {prod_metrics['auc_pr']:.3f}")
        return False

    # Slice checks: model must not regress on protected groups
    slice_results = evaluate_slices(run_id)
    for group, auc in slice_results.items():
        if auc < 0.80:
            print(f"FAIL: slice {group} AUC {auc:.3f} below minimum 0.80")
            return False

    print(f"PASS: AUC-PR {metrics['val_auc_pr']:.3f}, all gates passed")
    return True

if __name__ == "__main__":
    passed = quality_gate(run_id=sys.argv[1])
    sys.exit(0 if passed else 1)
```

---

## 5. Data Versioning and Lineage

```python
# DVC (Data Version Control) — git-like versioning for datasets
# dvc.yaml defines the pipeline DAG

stages:
  prepare:
    cmd: python src/prepare.py
    deps:
      - src/prepare.py
      - data/raw/transactions.csv
    outs:
      - data/processed/features.parquet
    params:
      - prepare.lookback_days
      - prepare.min_transactions

  train:
    cmd: python src/train.py
    deps:
      - src/train.py
      - data/processed/features.parquet
    outs:
      - models/fraud_model.pkl
    metrics:
      - metrics/eval.json:
          cache: false

# Track dataset version in code
import subprocess
import json

def get_data_version(data_path: str) -> str:
    """Get DVC-tracked version hash for a dataset."""
    result = subprocess.run(
        ["dvc", "status", data_path, "--json"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout).get("hash", "unknown")

# Log data version in every training run
mlflow.log_param("data_version", get_data_version("data/processed/features.parquet"))
mlflow.log_param("data_commit", subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip())
```

---

## 6. Model Monitoring and Drift Detection

```python
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, ClassificationPreset
from evidently.metrics import *
import pandas as pd

class ModelMonitor:
    def __init__(self, reference_data: pd.DataFrame, reference_predictions: pd.Series):
        self.reference_data = reference_data
        self.reference_predictions = reference_predictions

    def run_drift_check(
        self,
        current_data: pd.DataFrame,
        current_predictions: pd.Series,
        current_labels: pd.Series | None = None,
    ) -> dict:
        report = Report(metrics=[
            DataDriftPreset(drift_share=0.3),  # alert if > 30% of features drift
            ColumnDriftMetric(column_name="transaction_amount"),
            ColumnDriftMetric(column_name="merchant_category"),
        ])

        report.run(
            reference_data=self.reference_data.assign(target=self.reference_predictions),
            current_data=current_data.assign(target=current_predictions),
        )
        results = report.as_dict()

        # Extract actionable signals
        drift_detected = results["metrics"][0]["result"]["dataset_drift"]
        drifted_features = [
            m["result"]["column_name"]
            for m in results["metrics"]
            if m["result"].get("drift_detected")
        ]

        return {
            "dataset_drift": drift_detected,
            "drifted_features": drifted_features,
            "drift_share": results["metrics"][0]["result"]["share_of_drifted_columns"],
        }

    def run_performance_check(
        self,
        current_predictions: pd.Series,
        current_labels: pd.Series,
        threshold_auc_pr: float = 0.80,
    ) -> dict:
        """Check model performance when labels are available."""
        from sklearn.metrics import average_precision_score, roc_auc_score
        auc_pr = average_precision_score(current_labels, current_predictions)
        auc_roc = roc_auc_score(current_labels, current_predictions)
        return {
            "auc_pr": auc_pr,
            "auc_roc": auc_roc,
            "performance_ok": auc_pr >= threshold_auc_pr,
        }

# Statistical drift tests
from scipy.stats import ks_2samp, chi2_contingency
import numpy as np

def detect_drift_ks(reference: np.ndarray, current: np.ndarray, alpha: float = 0.05) -> dict:
    """Kolmogorov-Smirnov test for continuous feature drift."""
    stat, p_value = ks_2samp(reference, current)
    return {"drift_detected": p_value < alpha, "ks_stat": stat, "p_value": p_value}

def detect_drift_psi(reference: np.ndarray, current: np.ndarray, buckets: int = 10) -> dict:
    """Population Stability Index — industry standard in credit/fraud."""
    # PSI < 0.1: no drift; 0.1-0.2: slight drift; > 0.2: significant drift
    min_val, max_val = min(reference.min(), current.min()), max(reference.max(), current.max())
    bins = np.linspace(min_val, max_val, buckets + 1)
    ref_pct = np.histogram(reference, bins=bins)[0] / len(reference) + 1e-6
    cur_pct = np.histogram(current, bins=bins)[0] / len(current) + 1e-6
    psi = np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct))
    return {"psi": psi, "drift_level": "none" if psi < 0.1 else "slight" if psi < 0.2 else "significant"}
```

---

## 7. Serving Infrastructure

```python
# BentoML — framework-agnostic model serving
import bentoml
from bentoml.io import JSON, NumpyNdarray
import numpy as np

# Save model to BentoML store
model_ref = bentoml.sklearn.save_model(
    "fraud_detector",
    trained_model,
    signatures={"predict_proba": {"batchable": True, "batch_dim": 0}},
    metadata={"mlflow_run_id": run_id, "training_date": "2025-03-01"},
)

# Define a service
svc = bentoml.Service("fraud_detection", runners=[bentoml.sklearn.get("fraud_detector:latest").to_runner()])

@svc.api(input=JSON(), output=JSON())
async def predict(request: dict) -> dict:
    features = np.array([[
        request["transaction_amount"],
        request["merchant_category_encoded"],
        request["customer_age_days"],
        request["hour_of_day"],
    ]])
    prob = await svc.runners["fraud_detector"].predict_proba.async_run(features)
    return {
        "fraud_probability": float(prob[0][1]),
        "is_fraud": bool(prob[0][1] > 0.5),
        "model_version": bentoml.sklearn.get("fraud_detector:latest").tag.version,
    }

# SageMaker real-time endpoint
import boto3
sm_client = boto3.client("sagemaker")

sm_client.create_endpoint_config(
    EndpointConfigName="fraud-detector-v3",
    ProductionVariants=[
        {
            "VariantName": "primary",
            "ModelName": "fraud-detector-v3",
            "InitialInstanceCount": 2,
            "InstanceType": "ml.m5.xlarge",
            "InitialVariantWeight": 0.9,  # 90% traffic
        },
        {
            "VariantName": "challenger",  # A/B test new model
            "ModelName": "fraud-detector-v4",
            "InitialInstanceCount": 1,
            "InstanceType": "ml.m5.xlarge",
            "InitialVariantWeight": 0.1,  # 10% traffic
        },
    ],
    DataCaptureConfig={
        "EnableCapture": True,
        "InitialSamplingPercentage": 100,  # capture all predictions for monitoring
        "DestinationS3Uri": "s3://ml-monitoring/fraud-detector/",
        "CaptureOptions": [{"CaptureMode": "Input"}, {"CaptureMode": "Output"}],
    },
)
```

---

## 8. Automated Retraining Pipelines

```python
# SageMaker Pipeline for end-to-end automated retraining
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.steps import ProcessingStep, TrainingStep, ConditionStep
from sagemaker.workflow.conditions import ConditionGreaterThanOrEqualTo
from sagemaker.workflow.functions import JsonGet

from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.sklearn import SKLearn

processor = SKLearnProcessor(
    framework_version="1.4",
    instance_type="ml.m5.xlarge",
    instance_count=1,
    role=role,
)

# Step 1: Validate data
data_validation_step = ProcessingStep(
    name="ValidateData",
    processor=processor,
    code="scripts/validate_data.py",
    inputs=[ProcessingInput(source=s3_data_uri, destination="/opt/ml/processing/input")],
    outputs=[ProcessingOutput(source="/opt/ml/processing/output", destination=s3_validated_uri)],
)

# Step 2: Feature engineering
feature_eng_step = ProcessingStep(
    name="FeatureEngineering",
    processor=processor,
    code="scripts/feature_engineering.py",
    depends_on=[data_validation_step],
)

# Step 3: Train
estimator = SKLearn(
    entry_point="scripts/train.py",
    framework_version="1.4",
    instance_type="ml.m5.4xlarge",
    instance_count=1,
    role=role,
    use_spot_instances=True,
    max_wait=7200,
    checkpoint_s3_uri=f"s3://ml-checkpoints/fraud-detector/",
)
training_step = TrainingStep(
    name="TrainModel",
    estimator=estimator,
    inputs={"train": TrainingInput(feature_eng_step.properties.ProcessingOutputConfig.Outputs["train"].S3Output.S3Uri)},
    depends_on=[feature_eng_step],
)

# Step 4: Evaluate — conditional register
evaluation_step = ProcessingStep(
    name="EvaluateModel",
    processor=processor,
    code="scripts/evaluate.py",
    property_files=[PropertyFile(name="evaluation", output_name="evaluation", path="evaluation.json")],
    depends_on=[training_step],
)

# Step 5: Quality gate — only register if AUC-PR > 0.85
register_step = RegisterModel(
    name="RegisterModel",
    estimator=estimator,
    model_data=training_step.properties.ModelArtifacts.S3ModelArtifacts,
    content_types=["application/json"],
    response_types=["application/json"],
    approval_status="PendingManualApproval",  # human review before prod
)
condition_step = ConditionStep(
    name="QualityGate",
    conditions=[
        ConditionGreaterThanOrEqualTo(
            left=JsonGet(step_name=evaluation_step.name, property_file="evaluation", json_path="auc_pr"),
            right=0.85,
        )
    ],
    if_steps=[register_step],
    else_steps=[],  # no-op: don't register failing model
)

pipeline = Pipeline(
    name="FraudDetectorRetraining",
    steps=[data_validation_step, feature_eng_step, training_step, evaluation_step, condition_step],
    sagemaker_session=sess,
)
pipeline.upsert(role_arn=role)

# Trigger: scheduled (weekly) or event-based (drift alert → Lambda → pipeline.start())
pipeline.start(execution_display_name=f"retrain-{datetime.date.today()}")
```

---

## 9. Online Learning vs. Batch Retraining

**Batch retraining (most common):**
- Train on accumulated data on a schedule (daily, weekly)
- Simple to implement, easy to validate before deployment
- Latency: data → model update in hours to days
- Best for: most ML tasks where distribution shifts slowly

**Online learning (stream-based):**
- Model updates incrementally with each new example
- Complex: need to handle concept drift, catastrophic forgetting, noisy labels
- Latency: data → model update in minutes
- Best for: real-time personalization, rapidly evolving fraud patterns, news recommendation

```python
# River: online learning library for streaming ML
from river import linear_model, preprocessing, metrics, stream

model = preprocessing.StandardScaler() | linear_model.LogisticRegression()
metric = metrics.ROCAUC()

# Simulated streaming pipeline
for x, y in stream.iter_csv("transactions_stream.csv", target="is_fraud"):
    # Predict before updating (prequential evaluation)
    y_pred = model.predict_proba_one(x)[True]
    metric.update(y, y_pred)

    # Update model with new example
    model.learn_one(x, y)

    # Detect concept drift
    if drift_detector.update(y_pred != (y_pred > 0.5)):
        print(f"Drift detected at example {i}")
        # Reset or notify
```
