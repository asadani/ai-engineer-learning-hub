# Measurement & Evaluation

## What You're Measuring in Data Architecture

Four distinct measurement targets:

1. **Data freshness** — How old is the data consumers are reading?
2. **Data quality** — Is the data complete, valid, and semantically correct?
3. **Pipeline reliability** — Are the ingestion and transformation pipelines running successfully?
4. **Serving performance** — Are consumers getting data fast enough?

Each requires different instrumentation and has different response actions when it degrades.

---

## Data Freshness Evaluation

```python
import boto3
from datetime import datetime, timezone
import pandas as pd

cw = boto3.client("cloudwatch", region_name="us-east-1")

def measure_table_freshness(
    table_path: str,
    partition_col: str = "date_partition",
    timestamp_col: str = "silver_processed_at",
) -> dict:
    """Measure how stale the latest data in a Delta Lake table is."""
    from delta.tables import DeltaTable

    spark = get_spark_session()
    dt = DeltaTable.forPath(spark, table_path)

    # Check Delta log for last write time (accurate without scanning data)
    last_commit = dt.history(1).select("timestamp").first()["timestamp"]
    age_minutes = (datetime.now(timezone.utc) - last_commit.replace(tzinfo=timezone.utc)).total_seconds() / 60

    # Also check the latest event timestamp in the data (event time, not processing time)
    latest_event = spark.read.format("delta").load(table_path) \
        .agg({"event_time": "max"}).collect()[0][0]
    event_lag_minutes = (datetime.now(timezone.utc) - latest_event.replace(tzinfo=timezone.utc)).total_seconds() / 60

    return {
        "table": table_path,
        "last_write_age_minutes": age_minutes,
        "latest_event_lag_minutes": event_lag_minutes,
        "freshness_ok": age_minutes < 90,  # SLA: data no older than 90 minutes
    }

def measure_kafka_consumer_lag(
    bootstrap_servers: str,
    group_id: str,
    topics: list[str],
) -> dict:
    """Measure how far behind a consumer group is from the head of the Kafka topic."""
    from confluent_kafka.admin import AdminClient
    from confluent_kafka import Consumer, TopicPartition

    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    consumer = Consumer({
        "bootstrap.servers": bootstrap_servers,
        "group.id": f"{group_id}-lag-checker",
    })

    lag_by_topic = {}
    for topic in topics:
        # Get committed offsets for the consumer group
        metadata = admin.list_consumer_group_offsets([group_id])
        committed = {tp.partition: offset.offset for tp, offset in
                     metadata[group_id].topic_partitions.items() if tp.topic == topic}

        # Get end offsets (head of the partition)
        partitions = consumer.list_topics(topic).topics[topic].partitions
        tps = [TopicPartition(topic, p) for p in partitions.keys()]
        end_offsets = consumer.get_watermark_offsets(tps[0])

        total_lag = sum(
            end_offsets[1] - committed.get(tp.partition, 0)
            for tp in tps
        )
        lag_by_topic[topic] = {
            "total_lag_messages": total_lag,
            "lag_critical": total_lag > 100_000,  # alert threshold
        }

    return lag_by_topic

def emit_freshness_metrics(table_name: str, freshness_result: dict):
    dims = [{"Name": "Table", "Value": table_name}]
    cw.put_metric_data(
        Namespace="DataArchitecture/Freshness",
        MetricData=[
            {"MetricName": "LastWriteAgeMinutes",    "Value": freshness_result["last_write_age_minutes"],     "Unit": "None", "Dimensions": dims},
            {"MetricName": "LatestEventLagMinutes",  "Value": freshness_result["latest_event_lag_minutes"],   "Unit": "None", "Dimensions": dims},
            {"MetricName": "FreshnessOK",            "Value": int(freshness_result["freshness_ok"]),          "Unit": "Count","Dimensions": dims},
        ],
    )
```

---

## Pipeline Reliability Evaluation

```python
from dataclasses import dataclass
from enum import Enum
import time

class PipelineStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"
    SKIPPED = "skipped"

@dataclass
class PipelineRunRecord:
    pipeline_name: str
    run_id: str
    triggered_by: str       # "schedule" | "event" | "manual"
    start_time: float
    end_time: float | None
    status: PipelineStatus
    rows_ingested: int | None
    rows_written: int | None
    input_bytes: int | None
    output_bytes: int | None
    error_message: str | None
    steps: list[dict]       # [{step_name, status, duration_s, rows_processed}]

def evaluate_pipeline_health(
    pipeline_name: str,
    lookback_hours: int = 24,
) -> dict:
    """Pull pipeline run history and compute reliability metrics."""
    runs = fetch_pipeline_runs(pipeline_name, lookback_hours=lookback_hours)

    if not runs:
        return {"error": "No runs found in lookback window"}

    success_runs = [r for r in runs if r.status == PipelineStatus.SUCCESS]
    failed_runs = [r for r in runs if r.status == PipelineStatus.FAILED]

    durations = [(r.end_time - r.start_time) / 60 for r in success_runs if r.end_time]

    return {
        "total_runs": len(runs),
        "success_rate": len(success_runs) / len(runs),
        "failure_rate": len(failed_runs) / len(runs),
        "mean_duration_minutes": sum(durations) / len(durations) if durations else None,
        "p99_duration_minutes": sorted(durations)[int(0.99 * len(durations))] if durations else None,
        "last_success": max((r.start_time for r in success_runs), default=None),
        "last_failure": max((r.start_time for r in failed_runs), default=None),
        "total_rows_written": sum(r.rows_written or 0 for r in success_runs),
        "common_failure_steps": _analyze_failure_steps(failed_runs),
        "sla_breach": (time.time() - max((r.start_time for r in success_runs), default=0)) > 3 * 3600,  # no success in 3h
    }

def _analyze_failure_steps(failed_runs: list[PipelineRunRecord]) -> dict:
    step_failures = {}
    for run in failed_runs:
        for step in run.steps:
            if step["status"] == "failed":
                step_name = step["step_name"]
                step_failures[step_name] = step_failures.get(step_name, 0) + 1
    return dict(sorted(step_failures.items(), key=lambda x: x[1], reverse=True))
```

---

## Data Quality Evaluation

```python
import great_expectations as gx
from pyspark.sql import DataFrame
import numpy as np

class DataQualityEvaluator:
    """Multi-level data quality checks for Medallion layers."""

    def evaluate_bronze(self, df: DataFrame, expected_daily_rows: tuple[int, int]) -> dict:
        """Bronze: structural checks only — don't reject raw data."""
        results = {}

        # Row count sanity (upstream pipeline health proxy)
        row_count = df.count()
        min_rows, max_rows = expected_daily_rows
        results["row_count"] = {
            "value": row_count,
            "in_expected_range": min_rows <= row_count <= max_rows,
            "severity": "warning",  # bronze failures are warnings, not errors
        }

        # Schema check: required columns present
        required_cols = ["raw_payload", "ingested_at", "source"]
        missing = [c for c in required_cols if c not in df.columns]
        results["schema"] = {"missing_columns": missing, "passed": len(missing) == 0}

        return results

    def evaluate_silver(self, df: DataFrame, schema_config: dict) -> dict:
        """Silver: full quality validation — reject or quarantine bad rows."""
        from pyspark.sql import functions as F

        results = {}
        total_rows = df.count()

        for col, rules in schema_config.items():
            col_result = {"column": col, "checks": {}}

            # Null check
            null_count = df.filter(F.col(col).isNull()).count()
            null_rate = null_count / total_rows
            col_result["checks"]["null_rate"] = {
                "value": null_rate,
                "threshold": rules.get("max_null_rate", 0.01),
                "passed": null_rate <= rules.get("max_null_rate", 0.01),
            }

            # Range check for numeric columns
            if "min" in rules or "max" in rules:
                out_of_range = 0
                if "min" in rules:
                    out_of_range += df.filter(F.col(col) < rules["min"]).count()
                if "max" in rules:
                    out_of_range += df.filter(F.col(col) > rules["max"]).count()
                col_result["checks"]["range"] = {
                    "out_of_range_count": out_of_range,
                    "passed": out_of_range == 0,
                }

            results[col] = col_result

        # Deduplication check
        pk_cols = schema_config.get("_primary_key", [])
        if pk_cols:
            unique_count = df.dropDuplicates(pk_cols).count()
            dup_rate = (total_rows - unique_count) / total_rows
            results["_deduplication"] = {
                "duplicate_rate": dup_rate,
                "passed": dup_rate < 0.001,
            }

        all_passed = all(
            all(check["passed"] for check in col_result["checks"].values())
            for col_result in results.values()
            if isinstance(col_result, dict) and "checks" in col_result
        )
        return {"passed": all_passed, "details": results, "total_rows": total_rows}

    def evaluate_gold(self, df: DataFrame, reference_df: DataFrame, key_metrics: list[str]) -> dict:
        """Gold: business-level validation — compare against reference or expectations."""
        from pyspark.sql import functions as F

        results = {}
        for metric in key_metrics:
            current_val = df.agg(F.sum(metric)).collect()[0][0]
            reference_val = reference_df.agg(F.sum(metric)).collect()[0][0]

            pct_change = abs(current_val - reference_val) / (reference_val + 1e-9)
            results[metric] = {
                "current": current_val,
                "reference": reference_val,
                "pct_change": pct_change,
                "passed": pct_change < 0.15,  # alert if metric changes > 15% day-over-day
            }
        return results
```

---

## End-to-End Latency Measurement

```python
import time, uuid

class DataPipelineTracer:
    """Track end-to-end latency from event production to serving layer."""

    def emit_with_trace(self, producer, topic: str, payload: dict):
        """Inject trace timestamp into event at production time."""
        trace_id = str(uuid.uuid4())
        payload["_trace_id"] = trace_id
        payload["_produced_at_ms"] = int(time.time() * 1000)

        producer.produce(topic=topic, key=payload.get("order_id"), value=json.dumps(payload))
        return trace_id

    def record_stage_arrival(self, trace_id: str, stage: str):
        """Record when an event reaches each pipeline stage."""
        now_ms = int(time.time() * 1000)
        # Store in DynamoDB trace table
        dynamodb.Table("pipeline-traces").update_item(
            Key={"trace_id": trace_id},
            UpdateExpression=f"SET stage_{stage}_arrived_at = :ts",
            ExpressionAttributeValues={":ts": now_ms},
        )

    def compute_stage_latencies(self, trace_id: str) -> dict:
        record = dynamodb.Table("pipeline-traces").get_item(Key={"trace_id": trace_id})["Item"]
        produced_at = record["stage_produced_arrived_at"]
        return {
            "kafka_ingest_ms": record.get("stage_kafka_arrived_at", 0) - produced_at,
            "bronze_write_ms": record.get("stage_bronze_arrived_at", 0) - produced_at,
            "silver_transform_ms": record.get("stage_silver_arrived_at", 0) - produced_at,
            "serving_ready_ms": record.get("stage_serving_arrived_at", 0) - produced_at,
        }
```
