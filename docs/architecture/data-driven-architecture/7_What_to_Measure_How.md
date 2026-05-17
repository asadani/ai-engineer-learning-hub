# What to Measure & How

## Data Freshness Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Table last write age** | Minutes since last write to table | < SLA (e.g., 60 min) | > 2× SLA | Delta history().timestamp |
| **Latest event time lag** | Now - max(event_time) in table | < SLA + 30 min buffer | > SLA + 1h | SELECT MAX(event_time) query |
| **Kafka consumer lag (messages)** | End offset - committed offset | < 10k (streaming) | > 100k | kafka.consumer.group.lag |
| **Kafka consumer lag (time)** | Estimated time to catch up | < 30s | > 5 min | Lag × avg msg rate |
| **Firehose buffer age** | Time data sits in Firehose buffer | < buffer interval | > 2× buffer | Firehose DataFreshness metric |
| **Partition arrival delay** | Hours until today's partition appears | < 2h (T+2h) | > 4h | S3 object listing |
| **CDC replication lag** | Lag between source DB write and Kafka topic | < 5s | > 60s | Debezium metrics / DMS CloudWatch |

## Pipeline Reliability Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Pipeline success rate** | % of triggered runs that succeed | > 98% | < 95% | Airflow / Glue job history |
| **Pipeline duration p50** | Median run time | Baseline | > 1.5× baseline | Job start/end timestamps |
| **Pipeline duration p99** | 99th pct run time | < SLA window | > SLA window | Job start/end timestamps |
| **SLA breach rate** | % of runs that finish after deadline | < 1% | > 3% | Finish time vs deadline |
| **Failed step distribution** | Which steps fail most often | Track | Any step > 10% fail rate | Step-level status logs |
| **Retry rate** | % of tasks that required retry | < 5% | > 15% | Airflow task instance retry count |
| **Data volume anomaly** | Row count vs rolling 30-day avg | Within ±20% | Z-score > 3σ | Row count per run |
| **Missing partition rate** | Partitions not written by expected time | 0% | > 0% | S3 partition existence check |

## Data Quality Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Null rate per column** | % null values by column | Per contract (<1%) | > 5× contract threshold | Column statistics |
| **Duplicate rate** | % duplicate primary keys | < 0.01% | > 0.1% | COUNT vs COUNT DISTINCT |
| **Out-of-range rate** | Values outside expected bounds | < 0.01% | > 0.1% | Range checks in GX / dbt |
| **Schema violation count** | Wrong types, unexpected nulls | 0 | > 0 | Schema validation |
| **Gold metric drift** | Day-over-day change in key business metrics | < 15% | > 30% | Aggregate comparison |
| **Contract pass rate** | % of data products passing their contract | > 99% | < 95% | Data contract enforcement |
| **Referential integrity** | FK mismatches between related tables | 0% | > 0% | JOIN-based checks |
| **Timeliness of quality check** | Age of last quality check run | < 2h | > 6h | Quality check run timestamps |

## Streaming / Kafka Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Consumer lag (per group)** | Messages behind for each consumer group | < 10k | > 100k | JMX / CloudWatch MSK |
| **Producer throughput (bytes/s)** | Write throughput to brokers | Within capacity | > 80% shard/partition limit | Producer metrics |
| **Consumer throughput (msgs/s)** | Read throughput per consumer group | Match production rate | Consumption < production > 5 min | Consumer metrics |
| **Under-replicated partitions** | Partitions not fully replicated | 0 | > 0 | ZooKeeper / CloudWatch MSK |
| **Leader election rate** | Frequency of partition leader changes | < 1/hour | > 5/hour | Kafka controller metrics |
| **Broker disk usage %** | Disk utilization per broker | < 70% | > 85% | CloudWatch/JMX |
| **Schema registry errors** | Failed schema registrations/lookups | 0 | > 0 | Schema registry metrics |
| **DLQ (dead letter queue) depth** | Messages in DLQ (unprocessable) | 0 | > 0 | DLQ topic consumer lag |

## Serving Layer Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Query latency p50 (OLAP)** | Median analytical query time | < 5s | > 30s | Redshift/Athena query history |
| **Query latency p99 (OLAP)** | 99th pct analytical query | < 60s | > 5 min | Query history |
| **Athena scan per query (TB)** | Data scanned per Athena query | < 1 TB | > 5 TB | Athena query stats |
| **Cache hit rate (Redis)** | % of requests served from cache | > 90% | < 70% | Redis INFO keyspace_hits |
| **Redis latency p99** | 99th pct Redis GET/SET latency | < 5ms | > 20ms | Redis SLOWLOG |
| **Redshift slot utilization** | WLM slot usage vs capacity | < 80% | > 90% | Redshift system tables |
| **Concurrency limit hit rate** | Queries queued due to WLM limits | < 5% | > 20% | Redshift WLM metrics |

---

## Instrumentation Implementation

```python
import boto3
import time
from dataclasses import dataclass, field

cw = boto3.client("cloudwatch", region_name="us-east-1")

def emit_pipeline_metrics(
    pipeline_name: str,
    run_id: str,
    status: str,
    duration_s: float,
    rows_written: int,
    sla_breach: bool,
):
    dims = [{"Name": "Pipeline", "Value": pipeline_name}]
    cw.put_metric_data(
        Namespace="DataArchitecture/Pipelines",
        MetricData=[
            {"MetricName": "RunSuccess",    "Value": 1 if status == "success" else 0, "Unit": "Count",   "Dimensions": dims},
            {"MetricName": "DurationSeconds","Value": duration_s,                      "Unit": "Seconds", "Dimensions": dims},
            {"MetricName": "RowsWritten",   "Value": rows_written,                    "Unit": "Count",   "Dimensions": dims},
            {"MetricName": "SLABreach",     "Value": int(sla_breach),                 "Unit": "Count",   "Dimensions": dims},
        ],
    )

def emit_freshness_metrics(table_name: str, lag_minutes: float, freshness_ok: bool):
    dims = [{"Name": "Table", "Value": table_name}]
    cw.put_metric_data(
        Namespace="DataArchitecture/Freshness",
        MetricData=[
            {"MetricName": "LagMinutes",  "Value": lag_minutes,       "Unit": "None",  "Dimensions": dims},
            {"MetricName": "FreshnessOK", "Value": int(freshness_ok), "Unit": "Count", "Dimensions": dims},
        ],
    )

def emit_quality_metrics(table_name: str, quality_result: dict):
    dims = [{"Name": "Table", "Value": table_name}]
    cw.put_metric_data(
        Namespace="DataArchitecture/Quality",
        MetricData=[
            {"MetricName": "QualityPassed",     "Value": int(quality_result["passed"]),              "Unit": "Count", "Dimensions": dims},
            {"MetricName": "TotalRows",         "Value": quality_result.get("total_rows", 0),         "Unit": "Count", "Dimensions": dims},
            {"MetricName": "DuplicateRate",     "Value": quality_result.get("duplicate_rate", 0),     "Unit": "None",  "Dimensions": dims},
            {"MetricName": "ContractViolations","Value": len(quality_result.get("failures", [])),      "Unit": "Count", "Dimensions": dims},
        ],
    )
```

---

## Alerting Policy

```yaml
alerts:

  # Freshness — data staleness
  - name: TableFreshnessSLABreach
    metric: LagMinutes
    namespace: DataArchitecture/Freshness
    threshold: 90          # > 90 minutes old
    comparison: GreaterThanThreshold
    period: 300            # 5-minute evaluation
    severity: critical
    action: pagerduty
    message: "Table {dimensions.Table} is {value:.0f} minutes stale — SLA breach. Check pipeline."

  - name: KafkaConsumerLagHigh
    metric: kafka.consumer.group.lag
    threshold: 100000      # 100k messages behind
    period: 300
    severity: warning
    action: slack
    message: "Consumer group {group} is {value:,} messages behind. Processing may be stuck."

  # Pipeline reliability
  - name: PipelineFailure
    metric: RunSuccess
    statistic: Average
    threshold: 0.95        # success rate below 95%
    period: 3600           # 1-hour window
    severity: critical
    action: pagerduty
    message: "Pipeline {dimensions.Pipeline} success rate {value:.0%} below 95%"

  - name: PipelineSLABreach
    metric: SLABreach
    statistic: Sum
    threshold: 1           # any SLA breach
    period: 86400
    severity: warning
    action: slack
    message: "Pipeline {dimensions.Pipeline} missed its SLA window. Check run duration trends."

  - name: MissingPartition
    # Custom Lambda check: runs hourly, verifies today's partition exists
    condition: s3_partition_exists(table, today) == False
    time_after_expected: 2h
    severity: critical
    action: pagerduty
    message: "Expected partition for {table} at {date} not found. Upstream pipeline may have failed."

  # Data quality
  - name: DataContractViolation
    metric: ContractViolations
    statistic: Sum
    threshold: 1
    period: 3600
    severity: warning
    action: slack + jira
    message: "Data contract violations detected on {dimensions.Table}. Review quality report."

  - name: GoldMetricAnomaly
    metric: DailyRevenueChange
    # Alert if today's total revenue deviates > 30% from 7-day average
    condition: abs(today_revenue - avg_7d_revenue) / avg_7d_revenue > 0.30
    severity: critical
    action: pagerduty + data_eng_lead
    message: "Daily revenue in gold layer is {pct_change:.0%} from 7-day average. Possible data quality issue."

  # Kafka health
  - name: UnderReplicatedPartitions
    metric: kafka.server.ReplicaManager.UnderReplicatedPartitions
    threshold: 0
    comparison: GreaterThanThreshold
    severity: critical
    action: pagerduty
    message: "Kafka under-replicated partitions detected: {value}. Risk of data loss."

  - name: BrokerDiskUsageHigh
    metric: KafkaDataLogsDiskUsed
    threshold: 85          # 85% of disk
    severity: warning
    action: slack
    message: "Kafka broker disk at {value:.0f}%. Reduce retention or add storage."
```
