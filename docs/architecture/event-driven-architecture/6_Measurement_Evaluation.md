# Measurement & Evaluation

## What "Healthy" Looks Like in an Event-Driven System

Unlike request-response systems where a 200 OK means the operation completed, event-driven systems need explicit health signals. The event was published — but was it consumed? Did it process correctly? Is the consumer keeping up? These are different questions from "did the API return 200."

**The health pyramid for EDA:**
```
Business process completion rate  ← highest-level signal
Saga completion / DLQ depth       ← workflow health
Consumer lag / processing rate    ← throughput health
Broker health (replication, disk) ← infrastructure health
```

---

## Consumer Lag: The Core EDA Health Signal

Consumer lag = how far behind a consumer is from the latest messages in the broker. Lag = 0 means the consumer is keeping up in real-time. Lag = 1M means the consumer is 1 million messages behind the producers.

**What lag tells you:**

| Lag Trend | Interpretation |
|-----------|----------------|
| Stable at 0 | Healthy — consumer processes as fast as producers write |
| Stable at N (non-zero) | Consumer running but not keeping up — under-provisioned or slow |
| Increasing monotonically | Consumer is stuck or crashed — investigate immediately |
| Spiky then recovers | Batch processing or bursty load — may be acceptable |
| Drops then climbs | Consumer restarts but can't sustain — memory leak or logic error |

```python
import boto3
from confluent_kafka.admin import AdminClient

def get_kafka_consumer_lag(
    bootstrap_servers: str,
    consumer_group: str,
    topic: str,
) -> dict[str, int]:
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})

    # Get current committed offsets for the consumer group
    committed = admin.list_consumer_group_offsets(consumer_group)

    # Get latest offsets (high watermarks) for the topic
    metadata = admin.list_topics(topic)
    partitions = metadata.topics[topic].partitions

    lag_by_partition = {}
    for partition_id in partitions:
        tp = TopicPartition(topic, partition_id)
        committed_offset = committed[tp].offset if tp in committed else 0
        _, high_watermark = consumer.get_watermark_offsets(tp)
        lag = max(0, high_watermark - committed_offset)
        lag_by_partition[partition_id] = lag

    return {
        "total_lag": sum(lag_by_partition.values()),
        "partition_lag": lag_by_partition,
        "max_partition_lag": max(lag_by_partition.values()),
    }

# For MSK (Managed Kafka): use CloudWatch metric
# Namespace: AWS/Kafka
# Metric: SumOffsetLag (per consumer group + topic)
def check_msk_consumer_lag(cluster_name: str, consumer_group: str, topic: str) -> float:
    cw = boto3.client("cloudwatch")
    resp = cw.get_metric_statistics(
        Namespace="AWS/Kafka",
        MetricName="SumOffsetLag",
        Dimensions=[
            {"Name": "Cluster Name", "Value": cluster_name},
            {"Name": "Consumer Group", "Value": consumer_group},
            {"Name": "Topic", "Value": topic},
        ],
        StartTime=datetime.now() - timedelta(minutes=5),
        EndTime=datetime.now(),
        Period=60,
        Statistics=["Maximum"],
    )
    datapoints = resp.get("Datapoints", [])
    return datapoints[-1]["Maximum"] if datapoints else 0.0
```

**Converting lag to time:** `lag_time_seconds = total_lag / consumption_rate_per_second`. A lag of 100,000 messages at 10,000 messages/second = 10 seconds behind. The same lag at 100 messages/second = ~17 minutes behind — totally different urgency.

---

## Event Processing Latency

End-to-end event latency = time from event occurrence to consumer processing completion. This has multiple segments:

```
Event occurs → Producer publishes → Broker stores → Consumer receives → Consumer processes → Action complete
     ↑               ↑                   ↑                ↑                  ↑
  event_time    publish_latency    broker_latency    poll_latency      processing_time
```

**Measuring end-to-end:**

```python
import time
from dataclasses import dataclass

@dataclass
class EventLatencyTracer:
    event_id: str
    event_time: float      # when event actually occurred (business time)
    publish_time: float    # when producer called broker.publish()
    received_time: float   # when consumer received message from broker
    processed_time: float  # when consumer finished processing

    @property
    def publish_latency_ms(self) -> float:
        return (self.publish_time - self.event_time) * 1000

    @property
    def broker_latency_ms(self) -> float:
        return (self.received_time - self.publish_time) * 1000

    @property
    def processing_latency_ms(self) -> float:
        return (self.processed_time - self.received_time) * 1000

    @property
    def total_latency_ms(self) -> float:
        return (self.processed_time - self.event_time) * 1000

# Producer: embed timestamps in event payload
def publish_event(event: dict) -> None:
    event["_meta"] = {
        "event_id": event["event_id"],
        "event_time": event["occurred_at"],
        "publish_time": time.time(),
    }
    producer.produce(topic, value=json.dumps(event))

# Consumer: measure on receive
def consume_event(message) -> None:
    received_time = time.time()
    event = json.loads(message.value())
    meta = event.get("_meta", {})

    # Process the event
    process(event)
    processed_time = time.time()

    # Emit latency metrics
    if "publish_time" in meta:
        total_latency_ms = (processed_time - float(meta["event_time"])) * 1000
        cw.put_metric_data(
            Namespace="EDA/EventLatency",
            MetricData=[{
                "MetricName": "EndToEndLatencyMs",
                "Value": total_latency_ms,
                "Unit": "Milliseconds",
                "Dimensions": [
                    {"Name": "EventType", "Value": event["event_type"]},
                    {"Name": "Consumer", "Value": CONSUMER_NAME},
                ],
            }],
        )
```

**Latency budget allocation (typical e-commerce event):**

| Segment | Budget | Alert if > |
|---------|--------|-----------|
| Producer → Broker | < 10 ms | 100 ms |
| Broker replication | < 50 ms | 500 ms |
| Consumer poll cycle | < 100 ms | 1 s |
| Business logic processing | < 200 ms | 2 s |
| **Total end-to-end** | **< 500 ms** | **5 s** |

---

## Saga Completion Rate

For orchestrated workflows, track the success/failure distribution of business processes.

```python
@dataclass
class SagaMetrics:
    saga_type: str              # "OrderProcessing", "UserOnboarding"
    execution_id: str
    started_at: datetime
    completed_at: datetime | None
    terminal_state: str         # COMPLETED, FAILED, TIMED_OUT
    failed_step: str | None     # "process_payment", "reserve_inventory"
    compensation_succeeded: bool | None

def record_saga_completion(metrics: SagaMetrics) -> None:
    duration_s = (metrics.completed_at - metrics.started_at).total_seconds()
    dims = [{"Name": "SagaType", "Value": metrics.saga_type}]

    cw.put_metric_data(
        Namespace="EDA/Sagas",
        MetricData=[
            {
                "MetricName": "SagaCompleted",
                "Value": 1 if metrics.terminal_state == "COMPLETED" else 0,
                "Unit": "Count", "Dimensions": dims,
            },
            {
                "MetricName": "SagaFailed",
                "Value": 1 if metrics.terminal_state == "FAILED" else 0,
                "Unit": "Count", "Dimensions": dims,
            },
            {
                "MetricName": "SagaDurationSeconds",
                "Value": duration_s,
                "Unit": "Seconds", "Dimensions": dims,
            },
            {
                "MetricName": "CompensationFailed",
                "Value": 1 if metrics.compensation_succeeded == False else 0,
                "Unit": "Count", "Dimensions": dims,
            },
        ],
    )

# Saga health dashboard queries:
# Success rate = SagaCompleted / (SagaCompleted + SagaFailed)
# Compensation success rate = CompensationSucceeded / SagaFailed
# Stuck sagas = workflows running > 3x median duration (check Temporal UI or Step Functions console)
```

**The compensation failure alarm is critical.** If payment was charged but inventory reservation failed, and then the refund also fails — you have a real money problem. `CompensationFailed > 0` must page immediately.

---

## DLQ Depth: The System Toxicity Signal

Messages in the DLQ are events that failed processing N times and cannot be retried automatically. DLQ depth is a direct measure of messages that were lost from the happy path.

```python
def get_dlq_depth(dlq_url: str) -> int:
    resp = sqs.get_queue_attributes(
        QueueUrl=dlq_url,
        AttributeNames=["ApproximateNumberOfMessages"],
    )
    return int(resp["Attributes"]["ApproximateNumberOfMessages"])

def evaluate_dlq_health(dlq_url: str, dlq_name: str) -> dict:
    depth = get_dlq_depth(dlq_url)

    # Sample DLQ messages to categorize failure types
    failure_types = {}
    if depth > 0:
        messages = sqs.receive_message(
            QueueUrl=dlq_url,
            MaxNumberOfMessages=min(10, depth),
            AttributeNames=["ApproximateFirstReceiveTimestamp", "ApproximateReceiveCount"],
        ).get("Messages", [])

        for msg in messages:
            body = json.loads(msg["Body"])
            error_type = body.get("_error_type", "unknown")
            failure_types[error_type] = failure_types.get(error_type, 0) + 1

    return {
        "depth": depth,
        "failure_types": failure_types,
        "oldest_message_age_hours": get_oldest_message_age(messages) if depth > 0 else 0,
        "status": "critical" if depth > 0 else "healthy",
    }
```

**DLQ investigation runbook:**
1. Check failure_types distribution: schema validation errors (schema change), business logic errors (invalid state), infrastructure errors (downstream service down)
2. For schema errors: check if a producer deployed a breaking schema change
3. For infrastructure errors: check if downstream service recovered; replay after recovery
4. For business logic errors: fix the consumer code, redeploy, then replay

---

## Idempotency Violation Detection

If your consumers are supposed to be idempotent but aren't, you'll see duplicate side effects (double emails, double charges). Detect via:

```python
def check_idempotency_violations(table_name: str, time_window_hours: int = 24) -> dict:
    """
    Check if any event_ids were processed more than once.
    Requires consumers to log each processed event_id to an audit table.
    """
    dynamodb = boto3.resource("dynamodb")
    audit_table = dynamodb.Table(f"{table_name}-processing-audit")

    # Scan for duplicate event_ids (this is a diagnostic query, not in hot path)
    response = audit_table.scan(
        FilterExpression=Attr("processed_at").gte(
            (datetime.now() - timedelta(hours=time_window_hours)).isoformat()
        )
    )

    event_id_counts = {}
    for item in response["Items"]:
        eid = item["event_id"]
        event_id_counts[eid] = event_id_counts.get(eid, 0) + 1

    violations = {eid: count for eid, count in event_id_counts.items() if count > 1}
    return {
        "total_processed": len(event_id_counts),
        "violations": len(violations),
        "violation_rate": len(violations) / max(len(event_id_counts), 1),
        "sample_violations": list(violations.items())[:5],
    }
```

**Target:** Idempotency violation rate = 0%. Any non-zero rate requires investigation into the idempotency implementation.

---

## EventBridge / SNS Delivery Metrics

For push-based delivery, track delivery success rates from the AWS side:

```python
# EventBridge delivery metrics (CloudWatch)
eventbridge_metrics = [
    "MatchedEvents",       # events that matched at least one rule
    "TriggeredRules",      # rules triggered
    "FailedInvocations",   # target invocations that failed
    "DeadLetterInvocations", # events sent to DLQ
]

# SNS delivery metrics
sns_metrics = [
    "NumberOfMessagesPublished",
    "NumberOfNotificationsDelivered",
    "NumberOfNotificationsFailed",
    "NumberOfNotificationsRedrivenToDlq",
]

def get_sns_delivery_rate(topic_arn: str) -> float:
    period = 3600  # 1 hour
    published = get_metric("NumberOfMessagesPublished", topic_arn, period)
    delivered = get_metric("NumberOfNotificationsDelivered", topic_arn, period)
    if published == 0:
        return 1.0
    return delivered / published  # target: > 0.999
```
