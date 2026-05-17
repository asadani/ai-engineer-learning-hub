# Use Cases & Real-World Applications

## 1. Real-Time Fraud Detection Pipeline

**Context**: Financial services company, 50M transactions/day, 200ms SLA for fraud score, model must stay fresh as fraud patterns shift weekly.

### Architecture

```
Kafka (transaction stream)
    │
    ▼
Flink Feature Enrichment (< 50ms)
    │ compute: velocity features, historical aggregates
    ▼
SageMaker Feature Store (online)
    │ customer_tx_count_1h, merchant_risk_score, device_fingerprint_age
    ▼
SageMaker Endpoint (fraud-detector:v12)
    │ LightGBM, < 30ms inference, P99 < 80ms
    ▼
Decision Engine (rule overlay + ML score)
    │
    ▼
Kafka (decision stream)
    │
    ├──► Authorization (approve/decline/step-up)
    └──► S3 Data Lake (predictions + features for monitoring)

Monitoring Stack:
    S3 predictions → Evidently (hourly drift check) → CloudWatch → SNS → PagerDuty
    Chargebacks (60-day lag) → Performance evaluation → Retrain trigger
```

### Key Design Decisions

```python
# 1. Feature computation split: real-time vs batch
# Real-time (Flink, freshness < 1 min): transaction velocity, session features
# Batch (Spark daily, materialized to online store): customer lifetime features

from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.functions import MapFunction

class VelocityFeatureComputer(MapFunction):
    def __init__(self, redis_client):
        self.redis = redis_client

    def map(self, transaction):
        cust_id = transaction.customer_id
        pipe = self.redis.pipeline()
        # Sliding window counts using Redis ZADD + ZRANGEBYSCORE
        pipe.zadd(f"tx:{cust_id}", {transaction.tx_id: transaction.timestamp})
        pipe.zremrangebyscore(f"tx:{cust_id}", 0, transaction.timestamp - 3600)  # 1h window
        pipe.zcard(f"tx:{cust_id}")
        _, _, count_1h = pipe.execute()
        return {**transaction.__dict__, "tx_count_1h": count_1h}

# 2. Model serving with automatic fallback
import boto3
import json

runtime = boto3.client("sagemaker-runtime")

def get_fraud_score(features: dict, timeout_ms: int = 150) -> float:
    try:
        response = runtime.invoke_endpoint(
            EndpointName="fraud-detector-v12",
            ContentType="application/json",
            Body=json.dumps(features),
            TargetVariant="primary",  # route to production variant
        )
        result = json.loads(response["Body"].read())
        return result["fraud_probability"]
    except runtime.exceptions.ModelError:
        # Fall back to rule-based score on model error
        return rule_based_fallback_score(features)
    except TimeoutError:
        # Use cached score if available (Redis TTL=30min)
        return cached_score_or_default(features["customer_id"])
```

### Monitoring for Label-Delayed Tasks

```python
import pandas as pd
from datetime import datetime, timedelta

def run_fraud_monitoring(
    predictions_date: datetime,
    chargebacks_df: pd.DataFrame,  # arrives 60-90 days later
    features_df: pd.DataFrame,
) -> dict:
    # Input distribution monitoring (daily, no labels needed)
    drift_results = run_drift_check(
        reference=training_features,
        current=features_df,
        categorical_features=["merchant_category", "payment_method"],
        numeric_features=["amount", "tx_count_1h", "days_since_last_tx"],
    )

    # Output distribution monitoring (daily, no labels needed)
    score_psi = compute_psi(
        reference=training_predictions["score"],
        current=daily_predictions["score"],
    )

    # Performance monitoring (lagged by 60-90 days, but authoritative)
    if chargebacks_df is not None:
        joined = daily_predictions.merge(chargebacks_df, on="tx_id", how="left")
        joined["actual_fraud"] = joined["chargeback_amount"].notna()
        performance = {
            "auc_pr": average_precision_score(joined["actual_fraud"], joined["fraud_score"]),
            "precision_at_top_5pct": precision_at_top_k(joined, k_pct=0.05),
            "fraud_catch_rate_at_manual_review_cap": recall_at_precision(joined, min_precision=0.30),
        }
        return {**drift_results, "score_psi": score_psi, **performance}

    return {**drift_results, "score_psi": score_psi}
```

---

## 2. NLP Model Retraining Pipeline for Customer Support

**Context**: A customer support classifier routes tickets to 40+ teams. Language evolves — new products, new issue types. Model trained in January becomes stale by April.

### Pipeline Design

```python
# Metaflow pipeline for weekly retraining
from metaflow import FlowSpec, step, Parameter, card, resources
import pandas as pd

class SupportClassifierFlow(FlowSpec):
    data_lookback_days = Parameter("lookback_days", default=90)

    @step
    def start(self):
        self.cutoff_date = (datetime.now() - timedelta(days=self.data_lookback_days)).date()
        self.next(self.fetch_training_data)

    @step
    def fetch_training_data(self):
        # Pull labeled tickets from Redshift
        # Use agent-labeled tickets (human QA sample) + model-labeled (soft labels)
        self.tickets_df = query_redshift(f"""
            SELECT ticket_text, team_label, confidence, label_source
            FROM support_tickets
            WHERE created_at >= '{self.cutoff_date}'
              AND label_source IN ('human', 'high_confidence_model')
              AND confidence > 0.85
        """)
        print(f"Loaded {len(self.tickets_df)} training examples")
        self.next(self.validate_data)

    @step
    def validate_data(self):
        # Check label distribution (alert if any team has < 100 examples)
        dist = self.tickets_df["team_label"].value_counts()
        low_coverage_teams = dist[dist < 100].index.tolist()
        if low_coverage_teams:
            print(f"WARNING: Low coverage for teams: {low_coverage_teams}")
            # Fall back to oversampling or exclude from training
        self.next(self.finetune_model)

    @resources(memory=32000, cpu=8, gpu=1)
    @step
    def finetune_model(self):
        from transformers import DistilBertForSequenceClassification, Trainer, TrainingArguments
        import mlflow

        with mlflow.start_run(experiment_id=self.experiment_id):
            mlflow.log_params({
                "model_type": "distilbert-base-uncased",
                "num_labels": 40,
                "lookback_days": self.data_lookback_days,
                "training_examples": len(self.tickets_df),
            })

            model = DistilBertForSequenceClassification.from_pretrained(
                "distilbert-base-uncased", num_labels=40
            )
            # Training args with evaluation and early stopping
            args = TrainingArguments(
                output_dir="./results",
                num_train_epochs=5,
                per_device_train_batch_size=32,
                evaluation_strategy="epoch",
                load_best_model_at_end=True,
                metric_for_best_model="macro_f1",
            )
            trainer = Trainer(model=model, args=args, ...)
            trainer.train()

            self.val_metrics = trainer.evaluate()
            mlflow.log_metrics(self.val_metrics)
            self.run_id = mlflow.active_run().info.run_id

        self.next(self.evaluate_slices)

    @step
    def evaluate_slices(self):
        # Evaluate per-team to catch regressions on low-volume teams
        self.slice_metrics = {}
        for team in self.tickets_df["team_label"].unique():
            team_df = self.val_df[self.val_df["team_label"] == team]
            self.slice_metrics[team] = compute_metrics(team_df)

        # Flag teams with < 0.80 F1
        struggling_teams = {k: v for k, v in self.slice_metrics.items() if v["f1"] < 0.80}
        if struggling_teams:
            send_alert(f"Model regression on teams: {struggling_teams}")
        self.next(self.quality_gate)

    @step
    def quality_gate(self):
        macro_f1 = self.val_metrics["eval_macro_f1"]
        if macro_f1 < 0.82:
            print(f"FAIL: macro F1 {macro_f1:.3f} below threshold 0.82. Aborting promotion.")
            self.promote = False
        else:
            self.promote = True
        self.next(self.register)

    @step
    def register(self):
        if self.promote:
            mlflow.register_model(f"runs:/{self.run_id}/model", "support-classifier")
            print("Model registered to staging")
        self.next(self.end)

    @step
    def end(self):
        print(f"Pipeline complete. Promoted: {self.promote}")

if __name__ == "__main__":
    SupportClassifierFlow()
```

---

## 3. Recommendation System MLOps

**Context**: E-commerce platform, collaborative filtering model, 10M users, retrained daily. Users complain about stale recommendations after catalog changes.

### Feature Freshness Architecture

```python
# Problem: item features (price, availability, category) change frequently
# Solution: hot item features in Redis, user features in SageMaker Feature Store

import redis
import boto3
import json
import numpy as np

redis_client = redis.Redis(host="redis.internal", port=6379)
sm_featurestore = boto3.client("sagemaker-featurestore-runtime")

def get_recommendation_features(user_id: int, candidate_item_ids: list[int]) -> dict:
    # User features: updated daily (purchase history, preference vectors)
    user_features = sm_featurestore.get_record(
        FeatureGroupName="user-behavior-features",
        RecordIdentifierValueAsString=str(user_id),
    )["Record"]

    # Item features: updated in real-time on catalog events (Kafka → Lambda → Redis)
    item_features = {}
    pipe = redis_client.pipeline()
    for item_id in candidate_item_ids:
        pipe.hgetall(f"item:{item_id}")
    item_data = pipe.execute()

    for item_id, data in zip(candidate_item_ids, item_data):
        if data:
            item_features[item_id] = {k.decode(): v.decode() for k, v in data.items()}
        else:
            item_features[item_id] = get_item_features_from_db(item_id)  # cache miss fallback

    return {"user": user_features, "items": item_features}

# Item feature update on catalog change (Lambda triggered by DynamoDB Streams)
def update_item_features_in_redis(event):
    for record in event["Records"]:
        if record["eventName"] in ("INSERT", "MODIFY"):
            item = record["dynamodb"]["NewImage"]
            item_id = item["item_id"]["S"]
            redis_client.hset(f"item:{item_id}", mapping={
                "price": item["price"]["N"],
                "availability": item["in_stock"]["BOOL"],
                "category": item["category"]["S"],
                "discount_pct": item.get("discount_pct", {}).get("N", "0"),
            })
            redis_client.expire(f"item:{item_id}", 86400)  # 24h TTL
```

### A/B Testing Model Variants

```python
# SageMaker production variants for model A/B testing
import boto3

sm = boto3.client("sagemaker")

# Deploy two model variants (90/10 split)
sm.update_endpoint_weights_and_capacities(
    EndpointName="recommendations-endpoint",
    DesiredWeightsAndCapacities=[
        {"VariantName": "collaborative-filter-v8", "DesiredWeight": 0.90},
        {"VariantName": "two-tower-neural-v1", "DesiredWeight": 0.10},
    ],
)

# After 48h, query CloudWatch for per-variant business metrics
cw = boto3.client("cloudwatch")
metrics = cw.get_metric_statistics(
    Namespace="Recommendations",
    MetricName="CTR",  # click-through rate — business metric, not ML metric
    Dimensions=[{"Name": "ModelVariant", "Value": "two-tower-neural-v1"}],
    StartTime=datetime.utcnow() - timedelta(hours=48),
    EndTime=datetime.utcnow(),
    Period=3600,
    Statistics=["Average"],
)

# Statistical significance test before declaring winner
from scipy.stats import chi2_contingency
def is_significant(clicks_a, views_a, clicks_b, views_b, alpha=0.05) -> bool:
    contingency = [[clicks_a, views_a - clicks_a], [clicks_b, views_b - clicks_b]]
    _, p_value, _, _ = chi2_contingency(contingency)
    return p_value < alpha
```

---

## 4. MLOps for LLM Applications

**Context**: A company deploys a fine-tuned LLM for contract analysis. The model must be versioned, monitored for quality drift, and retrained quarterly as legal language evolves.

### Version Control for LLM Artifacts

```python
# Track fine-tuned LLM versions in MLflow with custom metadata
import mlflow

with mlflow.start_run(run_name="contract-llm-v3-qlora"):
    mlflow.log_params({
        "base_model": "meta-llama/Llama-3.1-8B-Instruct",
        "fine_tuning_method": "qlora",
        "lora_rank": 16,
        "training_data_version": "contracts-v20250301",
        "training_examples": 45_000,
        "dpo_rounds": 1,
    })

    # Log task-specific metrics
    mlflow.log_metrics({
        "extraction_f1_parties": 0.97,
        "extraction_f1_dates": 0.96,
        "risk_classification_accuracy": 0.91,
        "hallucination_rate": 0.02,  # from LLM-judge eval
        "human_preference_rate": 0.84,  # win rate vs baseline
    })

    # Log adapter weights (not full model)
    mlflow.log_artifact("adapter_model/", artifact_path="lora_adapter")
    mlflow.log_artifact("eval_results.json")
```

### LLM Output Monitoring

```python
from anthropic import Anthropic
import json, re

judge_client = Anthropic()

JUDGE_PROMPT = """Evaluate this contract analysis response.

Contract snippet: {contract}
Analysis response: {response}

Check for:
1. Hallucinated facts not present in the contract (score 0-3: 0=severe, 3=none)
2. Missing critical parties or dates (score 0-3)
3. Risk classification accuracy (score 0-3)

Output JSON: {{"hallucination": N, "completeness": N, "accuracy": N, "pass": true|false}}
Pass = all scores >= 2"""

def monitor_llm_output(contract: str, model_response: str) -> dict:
    judge_response = judge_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": JUDGE_PROMPT.format(contract=contract[:2000], response=model_response),
        }],
    )
    scores = json.loads(judge_response.content[0].text)

    # Emit to CloudWatch for trending
    import boto3
    cw = boto3.client("cloudwatch")
    cw.put_metric_data(
        Namespace="LLM/ContractAnalysis",
        MetricData=[
            {"MetricName": "HallucinationScore", "Value": scores["hallucination"], "Unit": "None"},
            {"MetricName": "CompletenessScore", "Value": scores["completeness"], "Unit": "None"},
            {"MetricName": "PassRate", "Value": 1 if scores["pass"] else 0, "Unit": "Count"},
        ],
    )
    return scores
```

---

## 5. Regulatory Model Governance (FDIC / SR 11-7 Compliance)

**Context**: A bank's credit scoring model must satisfy SR 11-7 model risk management guidance: full documentation, periodic validation, back-testing, and audit trails.

### Governance Automation

```python
# Model documentation auto-generated from MLflow metadata
def generate_model_card(model_name: str, version: int) -> dict:
    client = mlflow.tracking.MlflowClient()
    mv = client.get_model_version(model_name, version)
    run = client.get_run(mv.run_id)

    return {
        "model_name": model_name,
        "version": version,
        "intended_use": "Consumer credit scoring — approve/decline decision",
        "training_data": {
            "source": run.data.params["training_data_source"],
            "date_range": run.data.params["training_date_range"],
            "size": run.data.params["training_rows"],
        },
        "performance": {
            "gini_coefficient": run.data.metrics["gini"],
            "ks_statistic": run.data.metrics["ks_stat"],
            "auc_roc": run.data.metrics["auc_roc"],
        },
        "fairness_analysis": {
            "demographic_parity_difference": run.data.metrics["demographic_parity_diff"],
            "equalized_odds_difference": run.data.metrics["equalized_odds_diff"],
            "disparate_impact_ratio": run.data.metrics["disparate_impact_ratio"],
        },
        "approved_by": mv.tags.get("approved_by"),
        "approved_at": mv.tags.get("promoted_at"),
        "next_validation_due": mv.tags.get("next_validation_date"),
        "run_id": mv.run_id,
        "git_commit": run.data.params.get("git_commit"),
    }

# Automated back-testing for regulatory review
def run_regulatory_backtest(
    model_name: str,
    version: int,
    holdout_period: str,  # "Q4-2024"
) -> dict:
    """Run model against holdout data from a historical period."""
    holdout_data = load_holdout_dataset(holdout_period)
    model = mlflow.pyfunc.load_model(f"models:/{model_name}/{version}")

    predictions = model.predict(holdout_data.features)
    return {
        "holdout_period": holdout_period,
        "gini": compute_gini(holdout_data.labels, predictions),
        "ks_stat": compute_ks(holdout_data.labels, predictions),
        "psi_vs_training": compute_psi(training_scores, predictions),
        "approval_rate": (predictions > decision_threshold).mean(),
        "default_rate_by_score_band": compute_by_score_band(holdout_data.labels, predictions),
    }
```
