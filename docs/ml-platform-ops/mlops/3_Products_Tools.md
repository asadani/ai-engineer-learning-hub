# Products & Tools

## Experiment Tracking

### MLflow (open-source standard)

```python
import mlflow
import mlflow.sklearn

mlflow.set_tracking_uri("http://mlflow.internal:5000")
mlflow.set_experiment("churn-prediction")

with mlflow.start_run():
    mlflow.log_params({"model": "xgboost", "n_estimators": 300, "max_depth": 5})
    mlflow.log_metrics({"auc_pr": 0.83, "auc_roc": 0.91})
    mlflow.sklearn.log_model(model, "model", registered_model_name="churn-predictor")

# Query runs programmatically
runs = mlflow.search_runs(
    experiment_names=["churn-prediction"],
    filter_string="metrics.auc_pr > 0.80",
    order_by=["metrics.auc_pr DESC"],
)
```

**Strengths:** Self-hostable, language-agnostic, mature model registry, integrates with SageMaker
**Weaknesses:** UI is basic, no built-in hyperparameter optimization, collaborative features limited

### Weights & Biases (W&B)

```python
import wandb

wandb.init(
    project="fraud-detection",
    entity="my-team",
    config={"model": "lightgbm", "n_estimators": 500},
    tags=["production-candidate", "q1-2025"],
)
wandb.log({"train_loss": loss, "val_auc": auc, "epoch": epoch})
wandb.log({"roc_curve": wandb.plot.roc_curve(y_true, y_scores, labels=["legit", "fraud"])})
wandb.finish()

# W&B Sweeps: hyperparameter optimization
sweep_config = {
    "method": "bayes",
    "metric": {"name": "val_auc_pr", "goal": "maximize"},
    "parameters": {
        "learning_rate": {"distribution": "log_uniform_values", "min": 1e-4, "max": 1e-1},
        "n_estimators": {"values": [100, 200, 500, 1000]},
        "max_depth": {"values": [3, 5, 7, 9]},
    },
}
sweep_id = wandb.sweep(sweep_config, project="fraud-detection")
wandb.agent(sweep_id, function=train_and_evaluate, count=50)
```

**Strengths:** Beautiful UI, team collaboration, hyperparameter sweeps (Bayesian), artifact tracking, hosted
**Weaknesses:** Cost at scale ($0/mo free → $50+/mo for teams), data leaves your infra (if not self-hosting)

---

## Data Versioning

### DVC (Data Version Control)

```bash
# Initialize DVC in a git repo
dvc init

# Track a large dataset (stores in S3, commits hash to git)
dvc add data/transactions_2025.parquet
git add data/transactions_2025.parquet.dvc .gitignore
git commit -m "Add March 2025 transaction data"

# Push data to S3 remote
dvc remote add -d s3remote s3://ml-data-bucket/dvc-cache
dvc push

# Reproduce full pipeline (smart caching: only re-runs changed stages)
dvc repro

# Compare metrics across commits
dvc metrics show
dvc metrics diff HEAD~3
```

**Strengths:** Git-native workflow, pipeline DAG with `dvc.yaml`, remote storage (S3/GCS/Azure)
**Weaknesses:** Adds complexity to git workflow, large teams find merge conflicts on `.dvc` files painful

---

## Feature Stores

### Feast (open-source)

```python
# feast/feature_repo/features.py
from feast import Entity, FeatureView, Field, FileSource, ValueType
from feast.types import Float64, Int64

customer = Entity(name="customer_id", value_type=ValueType.INT64, description="Customer ID")

customer_features = FeatureView(
    name="customer_behavior",
    entities=[customer],
    schema=[
        Field(name="tx_count_7d", dtype=Int64),
        Field(name="tx_amount_avg_7d", dtype=Float64),
        Field(name="distinct_merchants_7d", dtype=Int64),
    ],
    source=FileSource(path="data/customer_features.parquet", timestamp_field="event_timestamp"),
    online=True,
)
```

```bash
feast apply          # register features
feast materialize-incremental $(date -u +"%Y-%m-%dT%H:%M:%S")  # sync offline → online store
```

**Strengths:** True offline/online separation, point-in-time joins, pluggable backends (Redis, DynamoDB, Bigtable)
**Weaknesses:** No built-in feature transformation at serving time, operational overhead to run

### Tecton (managed)

Tecton is a commercial feature platform with built-in streaming feature pipelines. Key differentiator: you define feature transformations once, Tecton handles both batch (for training) and real-time (for serving) execution.

```python
from tecton import batch_feature_view, stream_feature_view, Aggregate
from tecton.types import Float64, Int64

@batch_feature_view(
    sources=[transactions],
    entities=[customer],
    mode="spark",
    aggregation_interval="1d",
    feature_start_time=datetime(2024, 1, 1),
)
def customer_tx_stats(transactions):
    return transactions.groupby("customer_id").agg(
        tx_count_7d=Aggregate(input_col="tx_id", function="count", time_window="7d"),
        tx_amount_sum_7d=Aggregate(input_col="amount", function="sum", time_window="7d"),
    )

# Same feature definition automatically serves real-time features
features = tecton.get_online_features(
    feature_service="fraud_detection_features",
    join_keys={"customer_id": 12345},
)
```

**Use Tecton when:** You need streaming feature pipelines, your team lacks infra bandwidth to operate Feast, or you have complex feature transformation logic.

---

## Pipeline Orchestration

### SageMaker Pipelines (AWS-native)

Best choice when your team is AWS-native and wants managed infrastructure. Tightly integrated with SageMaker training, processing, and model registry.

```python
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.steps import ProcessingStep, TrainingStep

# Steps defined as code (see Key Technical Concepts for full example)
pipeline = Pipeline(name="FraudRetraining", steps=[...])
pipeline.upsert(role_arn=role)

# Trigger via EventBridge rule or manually
pipeline.start()

# Monitor execution
for step in pipeline.describe()["PipelineExecutionSteps"]:
    print(f"{step['StepName']}: {step['StepStatus']}")
```

### Apache Airflow (general-purpose)

Best choice when you already run Airflow for data pipelines and want ML pipelines in the same DAG framework.

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.sagemaker import (
    SageMakerTrainingOperator, SageMakerEndpointOperator
)
from datetime import datetime, timedelta

with DAG(
    "fraud_model_retraining",
    schedule_interval="0 2 * * 1",  # Mondays at 2 AM
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
) as dag:

    validate = PythonOperator(task_id="validate_data", python_callable=run_data_validation)

    train = SageMakerTrainingOperator(
        task_id="train_model",
        config=training_config,
        wait_for_completion=True,
        print_log=True,
    )

    evaluate = PythonOperator(task_id="evaluate_model", python_callable=run_evaluation)

    promote = PythonOperator(
        task_id="promote_to_staging",
        python_callable=promote_model_to_staging,
        trigger_rule="all_success",
    )

    validate >> train >> evaluate >> promote
```

### Metaflow (Netflix-origin, Outerbounds-maintained)

Designed specifically for ML — native support for branching experiments, versioned artifacts per step, and compute escalation (local → cloud).

```python
from metaflow import FlowSpec, step, card, Parameter, S3, resources

class FraudTrainingFlow(FlowSpec):
    data_date = Parameter("data_date", default="2025-03-01")

    @step
    def start(self):
        print(f"Starting training for data through {self.data_date}")
        self.next(self.validate_data)

    @step
    def validate_data(self):
        import great_expectations as gx
        context = gx.get_context()
        results = context.run_checkpoint(checkpoint_name="fraud_data_checkpoint")
        assert results.success, "Data validation failed"
        self.next(self.engineer_features)

    @resources(memory=32000, cpu=8)
    @step
    def engineer_features(self):
        self.feature_df = compute_features(self.data_date)
        self.next(self.train_lightgbm, self.train_xgboost)  # parallel branches

    @resources(memory=16000, cpu=4)
    @step
    def train_lightgbm(self):
        self.model, self.metrics = train_lgbm(self.feature_df)
        self.next(self.join_models)

    @resources(memory=16000, cpu=4)
    @step
    def train_xgboost(self):
        self.model, self.metrics = train_xgb(self.feature_df)
        self.next(self.join_models)

    @step
    def join_models(self, inputs):
        best = max(inputs, key=lambda i: i.metrics["auc_pr"])
        self.best_model = best.model
        self.best_metrics = best.metrics
        self.next(self.register)

    @step
    def register(self):
        mlflow.sklearn.log_model(self.best_model, "model", registered_model_name="fraud-detector")
        self.next(self.end)

    @step
    def end(self):
        print(f"Best model AUC-PR: {self.best_metrics['auc_pr']:.3f}")

if __name__ == "__main__":
    FraudTrainingFlow()
```

---

## Model Monitoring

### Evidently AI (open-source)

```python
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, ClassificationPreset
from evidently.test_suite import TestSuite
from evidently.test_preset import DataQualityTestPreset, DataDriftTestPreset

# Report: visual dashboard
report = Report(metrics=[DataDriftPreset(), ClassificationPreset()])
report.run(reference_data=train_df, current_data=prod_df)
report.save_html("monitoring_report.html")

# Test suite: pass/fail checks for CI
tests = TestSuite(tests=[
    DataDriftTestPreset(stattest_threshold=0.05),
    DataQualityTestPreset(),
    TestShareOfDriftedColumns(lt=0.3),
])
tests.run(reference_data=train_df, current_data=prod_df)
assert tests.as_dict()["summary"]["all_passed"]
```

### Arize AI (managed)

Cloud-native ML observability with embedding drift (important for LLM monitoring), data quality, and model performance tracking. Integrates with SageMaker Data Capture.

```python
import arize.pandas.logger as arize

arize_client = arize.Client(space_key=SPACE_KEY, api_key=API_KEY)

arize_client.log(
    dataframe=predictions_df,
    schema=arize.Schema(
        prediction_id_column_name="prediction_id",
        timestamp_column_name="prediction_ts",
        prediction_label_column_name="fraud_prediction",
        actual_label_column_name="fraud_actual",
        feature_column_names=FEATURE_COLS,
        shap_values_column_names={col: f"shap_{col}" for col in FEATURE_COLS},
    ),
    model_id="fraud-detector",
    model_version="v3.1",
    model_type=arize.ModelTypes.BINARY_CLASSIFICATION,
    environment=arize.Environments.PRODUCTION,
)
```

---

## Data Quality

### Great Expectations

```python
import great_expectations as gx

context = gx.get_context()
data_source = context.sources.add_pandas("transactions")
data_asset = data_source.add_dataframe_asset("jan_2025_transactions")

# Define expectations (tests for data quality)
batch_request = data_asset.build_batch_request(dataframe=transactions_df)
validator = context.get_validator(batch_request=batch_request)

validator.expect_column_values_to_not_be_null("transaction_id")
validator.expect_column_values_to_be_between("amount", min_value=0, max_value=100_000)
validator.expect_column_values_to_be_in_set("currency", ["USD", "EUR", "GBP"])
validator.expect_column_pair_values_a_to_be_greater_than_b("transaction_ts", "account_open_ts")
validator.expect_table_row_count_to_be_between(min_value=100_000, max_value=10_000_000)

# Validate
results = validator.validate()
assert results.success, f"Data validation failed: {results.statistics}"
```

---

## Tool Selection Summary

| Category | AWS-native | Self-hosted open-source | Managed SaaS |
|----------|-----------|------------------------|-------------|
| **Experiment tracking** | SageMaker Experiments | MLflow | W&B |
| **Data versioning** | S3 + DVC | DVC | — |
| **Feature store** | SageMaker Feature Store | Feast | Tecton, Hopsworks |
| **Pipeline orchestration** | SageMaker Pipelines | Airflow, Metaflow, Kubeflow | Prefect Cloud |
| **Model registry** | SageMaker Model Registry | MLflow Registry | W&B Model Registry |
| **Model serving** | SageMaker Endpoints | BentoML, vLLM | Seldon, Cortex |
| **Monitoring/drift** | SageMaker Model Monitor | Evidently | Arize, WhyLabs |
| **Data quality** | AWS Glue Data Quality | Great Expectations, Deequ | Monte Carlo |
