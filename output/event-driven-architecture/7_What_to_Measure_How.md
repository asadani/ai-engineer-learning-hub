# What to Measure & How

## Consumer & Broker Health Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Consumer group lag (messages)** | End offset − committed offset per group | < 10k (streaming) | > 100k | JMX / CloudWatch MSK `SumOffsetLag` |
| **Consumer group lag (seconds)** | Lag converted to estimated catch-up time | < 30s | > 5 min | Lag ÷ consumption rate |
| **Consumer throughput (msg/s)** | Messages processed per second per consumer | Match production rate | Consumption < production × 0.9 for > 5 min | Consumer metrics |
| **Producer throughput (bytes/s)** | Write throughput to brokers | Within capacity limit | > 80% partition limit | Producer / CloudWatch |
| **Under-replicated partitions** | Partitions not fully replicated across ISR | 0 | > 0 | ZooKeeper / MSK `UnderReplicatedPartitions` |
| **Leader election rate** | Frequency of partition leader changes | < 1/hour | > 5/hour | Kafka controller metrics |
| **Broker disk utilization %** | Disk used per broker | < 70% | > 85% | CloudWatch / JMX |
| **Schema registry errors** | Failed schema registrations or deserializations | 0 | > 0 | Schema registry API metrics |
| **DLQ depth (messages)** | Messages in dead letter queue | 0 | > 0 | SQS `ApproximateNumberOfMessages` |
| **DLQ message age (hours)** | How long messages have sat in DLQ | < 1 hour | > 24 hours | SQS `ApproximateAgeOfOldestMessage` |

## Event Delivery & Latency Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **End-to-end event latency p50** | Median time from event occurrence to consumer action | < 500ms | > 5s | Custom (event_time → processed_time) |
| **End-to-end event latency p99** | 99th pct event processing time | < 5s | > 30s | Custom embedded timestamps |
| **Publish-to-broker latency** | Producer → broker ACK time | < 10ms | > 100ms | Producer `produce` duration |
| **SQS visibility timeout extensions** | How often consumers extend visibility | < 5% of messages | > 20% | Custom counter |
| **SNS delivery rate** | `Delivered / Published` | > 99.9% | < 99% | CloudWatch `NumberOfNotificationsDelivered` |
| **EventBridge failed invocations** | Target invocation failures | 0 | > 0 | CloudWatch `FailedInvocations` |
| **EventBridge DLQ invocations** | Events sent to EB DLQ | 0 | > 0 | CloudWatch `DeadLetterInvocations` |
| **SQS message age at delivery** | Age of message when consumer first receives it | < 2× message interval | > SLA | SQS `ApproximateAgeOfOldestMessage` |

## Saga / Workflow Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Saga success rate** | `Completed / (Completed + Failed)` | > 99% | < 95% | Temporal metrics / Step Functions history |
| **Saga p50 duration** | Median workflow completion time | Baseline | > 1.5× baseline | Workflow start/end timestamps |
| **Saga p99 duration** | 99th pct completion time | < SLA | > SLA | Workflow start/end timestamps |
| **Compensation triggered rate** | % of sagas requiring compensation | < 1% | > 5% | Compensation activity execution count |
| **Compensation failure rate** | % of compensation activities that fail | 0% | > 0% | Compensation activity failure count |
| **Stuck workflows** | Running workflows > 3× median duration | 0 | > 0 | Temporal UI / Step Functions executions |
| **Temporal task queue backlog** | Unstarted activities in task queue | < 100 | > 1,000 | Temporal metrics `task_queue_depth` |
| **Step Functions throttle rate** | StartExecution calls throttled | 0 | > 0 | CloudWatch `ExecutionThrottled` |

## Idempotency & Correctness Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **Duplicate processing rate** | % of event_ids processed more than once | 0% | > 0% | Audit table scan for duplicate event_ids |
| **Idempotency key collision rate** | Conditional write failures / total attempts | < 0.1% (expected from retries) | > 1% | DynamoDB `ConditionalCheckFailedRequests` |
| **Out-of-order event rate** | Events processed out of expected sequence | 0% for ordered consumers | > 0.01% | Sequence number gap detection |
| **Missing event rate** | Expected events not received within window | 0% | > 0% | Event correlation checks |
| **Poison pill rate** | Messages deserialization/schema failures | 0% | > 0% | Consumer parse error counter |

## Infrastructure Health Metrics

| Metric | Definition | Target | Alert | Collection Method |
|--------|-----------|--------|-------|------------------|
| **MSK broker CPU %** | CPU utilization per broker | < 60% | > 80% | CloudWatch `CpuUser` |
| **MSK network throughput %** | Network utilization vs capacity | < 70% | > 85% | CloudWatch `NetworkTxPackets` |
| **SQS queue depth (non-DLQ)** | Messages waiting to be processed | < 10k | > 100k | `ApproximateNumberOfMessages` |
| **SQS inflight messages** | Messages currently being processed | < MaxConcurrency × 0.8 | > MaxConcurrency | `ApproximateNumberOfMessagesNotVisible` |
| **EventBridge event rate** | Events/second on custom bus | < 10k/s (default limit) | > 8k/s | CloudWatch `MatchedEvents` |
| **Kinesis iterator age** | Milliseconds behind the latest record | < 1000ms | > 60000ms | `GetRecords.IteratorAgeMilliseconds` |
| **Kinesis write throttle events** | PutRecord/PutRecords throttle | 0 | > 0 | CloudWatch `WriteProvisionedThroughputExceeded` |

---

## Instrumentation Implementation

```python
import boto3
import time
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

cw = boto3.client("cloudwatch", region_name="us-east-1")

def emit_consumer_metrics(
    consumer_name: str,
    event_type: str,
    success: bool,
    processing_ms: float,
    end_to_end_ms: float | None = None,
    duplicate: bool = False,
) -> None:
    dims = [
        {"Name": "Consumer", "Value": consumer_name},
        {"Name": "EventType", "Value": event_type},
    ]
    data = [
        {"MetricName": "EventProcessed",    "Value": 1 if success else 0,  "Unit": "Count",        "Dimensions": dims},
        {"MetricName": "EventFailed",        "Value": 0 if success else 1,  "Unit": "Count",        "Dimensions": dims},
        {"MetricName": "ProcessingLatencyMs","Value": processing_ms,         "Unit": "Milliseconds", "Dimensions": dims},
        {"MetricName": "DuplicateEvent",     "Value": int(duplicate),        "Unit": "Count",        "Dimensions": dims},
    ]
    if end_to_end_ms is not None:
        data.append({
            "MetricName": "EndToEndLatencyMs",
            "Value": end_to_end_ms,
            "Unit": "Milliseconds",
            "Dimensions": dims,
        })
    cw.put_metric_data(Namespace="EDA/Consumers", MetricData=data)

def emit_saga_metrics(
    saga_type: str,
    terminal_state: str,        # COMPLETED, FAILED, TIMED_OUT
    duration_s: float,
    compensation_triggered: bool = False,
    compensation_succeeded: bool | None = None,
) -> None:
    dims = [{"Name": "SagaType", "Value": saga_type}]
    cw.put_metric_data(
        Namespace="EDA/Sagas",
        MetricData=[
            {"MetricName": "SagaCompleted",           "Value": 1 if terminal_state == "COMPLETED" else 0, "Unit": "Count", "Dimensions": dims},
            {"MetricName": "SagaFailed",              "Value": 1 if terminal_state == "FAILED" else 0,    "Unit": "Count", "Dimensions": dims},
            {"MetricName": "SagaDurationSeconds",     "Value": duration_s,                                 "Unit": "Seconds","Dimensions": dims},
            {"MetricName": "CompensationTriggered",   "Value": int(compensation_triggered),                "Unit": "Count", "Dimensions": dims},
            {"MetricName": "CompensationFailed",      "Value": 1 if compensation_succeeded == False else 0,"Unit": "Count", "Dimensions": dims},
        ],
    )

def emit_dlq_metrics(queue_name: str, depth: int, oldest_age_hours: float) -> None:
    dims = [{"Name": "Queue", "Value": queue_name}]
    cw.put_metric_data(
        Namespace="EDA/DLQ",
        MetricData=[
            {"MetricName": "DLQDepth",          "Value": depth,             "Unit": "Count",   "Dimensions": dims},
            {"MetricName": "OldestMessageHours","Value": oldest_age_hours,  "Unit": "None",    "Dimensions": dims},
        ],
    )
```

---

## Alerting Policy

```yaml
alerts:

  # Consumer lag — the primary EDA health signal
  - name: ConsumerLagCritical
    metric: SumOffsetLag
    namespace: AWS/Kafka
    dimensions:
      ConsumerGroup: "{{ consumer_group }}"
      Topic: "{{ topic }}"
    threshold: 100000        # 100k messages behind
    comparison: GreaterThanThreshold
    period: 300
    severity: critical
    action: pagerduty
    message: "Consumer group {ConsumerGroup} is {value:,} messages behind on {Topic}. Check for consumer crash or slow processing."

  - name: ConsumerLagWarning
    metric: SumOffsetLag
    namespace: AWS/Kafka
    threshold: 10000         # 10k messages — early warning
    period: 300
    severity: warning
    action: slack
    message: "Consumer group {ConsumerGroup} lag is {value:,}. Monitor for growth."

  # DLQ — every message here is a failure
  - name: DLQNonEmpty
    metric: ApproximateNumberOfMessages
    namespace: AWS/SQS
    dimensions:
      QueueName: "{{ queue_name }}-dlq"
    threshold: 0
    comparison: GreaterThanThreshold
    period: 60               # check every minute
    severity: critical
    action: pagerduty + slack
    message: "DLQ {QueueName}-dlq has {value} messages. Events are failing processing. Immediate investigation required."

  # Saga health — compensation failures are money problems
  - name: SagaCompensationFailed
    metric: CompensationFailed
    namespace: EDA/Sagas
    statistic: Sum
    threshold: 1             # any compensation failure is critical
    period: 300
    severity: critical
    action: pagerduty + engineering-lead
    message: "Saga compensation failed for {SagaType}. Manual intervention may be required to resolve inconsistent state."

  - name: SagaSuccessRateLow
    metric: SagaCompleted
    namespace: EDA/Sagas
    # Alert when success rate drops below 95% over a 15-minute window
    statistic: Average
    threshold: 0.95
    comparison: LessThanThreshold
    period: 900
    severity: warning
    action: slack
    message: "Saga {SagaType} success rate is {value:.0%}. Normal failures or systemic issue — check."

  # End-to-end latency
  - name: EventLatencyHigh
    metric: EndToEndLatencyMs
    namespace: EDA/Consumers
    statistic: p99
    threshold: 5000          # 5 seconds p99
    period: 300
    severity: warning
    action: slack
    message: "Event {EventType} p99 end-to-end latency is {value:.0f}ms for {Consumer}. Check consumer processing time and broker lag."

  # Broker health
  - name: KafkaUnderReplicatedPartitions
    metric: UnderReplicatedPartitions
    namespace: AWS/Kafka
    threshold: 0
    comparison: GreaterThanThreshold
    period: 60
    severity: critical
    action: pagerduty
    message: "Kafka has {value} under-replicated partitions. Risk of data loss if broker fails now."

  - name: KafkaBrokerDiskHigh
    metric: KafkaDataLogsDiskUsed
    namespace: AWS/Kafka
    threshold: 85            # 85% disk used
    period: 300
    severity: warning
    action: slack
    message: "Kafka broker disk at {value:.0f}%. Reduce retention policy or add broker storage."

  # EventBridge delivery failures
  - name: EventBridgeDeliveryFailure
    metric: FailedInvocations
    namespace: AWS/Events
    statistic: Sum
    threshold: 1
    period: 300
    severity: warning
    action: slack
    message: "EventBridge target invocations failing: {value} in last 5 minutes. Check target service health."

  - name: EventBridgeDLQGrowth
    metric: DeadLetterInvocations
    namespace: AWS/Events
    statistic: Sum
    threshold: 1
    period: 300
    severity: critical
    action: pagerduty
    message: "EventBridge events going to DLQ: {value}. Events are being lost. Check target and DLQ."

  # Kinesis iterator age — equivalent to Kafka consumer lag
  - name: KinesisIteratorAgeHigh
    metric: GetRecords.IteratorAgeMilliseconds
    namespace: AWS/Kinesis
    statistic: Maximum
    threshold: 60000         # 60 seconds behind
    period: 300
    severity: critical
    action: pagerduty
    message: "Kinesis consumer is {value/1000:.0f}s behind on {StreamName}. May be stuck."
```
