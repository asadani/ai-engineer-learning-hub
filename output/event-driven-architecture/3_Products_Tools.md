# Products & Tools

## AWS Messaging Services

### Amazon SQS (Simple Queue Service)

The workhorse of async messaging on AWS. Point-to-point queue semantics: one message, one consumer.

**Two queue types:**

| | Standard Queue | FIFO Queue |
|--|----------------|-----------|
| **Throughput** | Unlimited (soft: 120k in-flight) | 3,000 msg/s with batching, 300 without |
| **Ordering** | Best-effort | Strict per message group |
| **Delivery** | At-least-once (duplicates possible) | Exactly-once processing |
| **Deduplication** | Not provided | 5-minute dedup window via dedup ID |
| **Use when** | High volume, idempotent consumers | Financial transactions, inventory updates |

**Critical configuration:**

```python
import boto3

sqs = boto3.client("sqs", region_name="us-east-1")

# Create standard queue with DLQ
dlq = sqs.create_queue(
    QueueName="order-events-dlq",
    Attributes={"MessageRetentionPeriod": "1209600"},  # 14 days
)
dlq_arn = sqs.get_queue_attributes(
    QueueUrl=dlq["QueueUrl"], AttributeNames=["QueueArn"]
)["Attributes"]["QueueArn"]

queue = sqs.create_queue(
    QueueName="order-events",
    Attributes={
        "VisibilityTimeout": "30",         # processing window — must be > Lambda timeout
        "MessageRetentionPeriod": "86400", # 1 day
        "ReceiveMessageWaitTimeSeconds": "20",  # long polling — saves cost, reduces empty receives
        "RedrivePolicy": json.dumps({
            "maxReceiveCount": "3",        # 3 failures → DLQ
            "deadLetterTargetArn": dlq_arn,
        }),
    },
)

# Consume with long polling
def process_messages(queue_url: str):
    while True:
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,        # batch up to 10
            WaitTimeSeconds=20,            # long poll
            AttributeNames=["ApproximateReceiveCount"],
        )
        for msg in resp.get("Messages", []):
            try:
                payload = json.loads(msg["Body"])
                handle_event(payload)
                sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )
            except Exception as e:
                # Don't delete — let visibility timeout expire → retry
                log.error(f"Failed to process {msg['MessageId']}: {e}")
```

**Visibility timeout pitfall:** If your Lambda/consumer takes 25s and timeout is 30s, a crash at 28s means the message re-appears and gets processed again. Set `VisibilityTimeout` to at least 3× the expected processing time.

---

### Amazon SNS (Simple Notification Service)

Fan-out pub-sub. One publish → N subscribers. Subscribers can be SQS queues, Lambda, HTTP/S endpoints, email, SMS.

**The canonical pattern: SNS → SQS fan-out**

```
OrderPlaced SNS Topic
    ├── → Shipping SQS Queue → Shipping Lambda
    ├── → Inventory SQS Queue → Inventory Lambda
    └── → Analytics SQS Queue → Analytics Lambda
```

Why not SNS → Lambda directly? SQS provides:
- Buffering when Lambda is throttled
- DLQ support
- Visibility timeout for retry
- Batching for cost reduction

```python
sns = boto3.client("sns")

# Publish with message attributes for filtering
sns.publish(
    TopicArn="arn:aws:sns:us-east-1:123456789:order-events",
    Message=json.dumps({
        "event_type": "OrderPlaced",
        "order_id": "ORD-123",
        "customer_tier": "premium",
        "total": 599.99,
    }),
    MessageAttributes={
        "event_type": {"DataType": "String", "StringValue": "OrderPlaced"},
        "customer_tier": {"DataType": "String", "StringValue": "premium"},
    },
)

# Subscribe SQS with filter policy (only high-value orders)
sns.subscribe(
    TopicArn="arn:aws:sns:us-east-1:123456789:order-events",
    Protocol="sqs",
    Endpoint=high_value_queue_arn,
    Attributes={
        "FilterPolicy": json.dumps({
            "event_type": ["OrderPlaced"],
            "customer_tier": ["premium", "enterprise"],
        }),
        "FilterPolicyScope": "MessageAttributes",
    },
)
```

**SNS message ordering:** Standard topics don't guarantee order. SNS FIFO topics do — but only with SQS FIFO subscribers.

---

### Amazon EventBridge

The most capable event routing service on AWS. Not a queue — a serverless event bus with content-based routing.

**Key differentiator:** EventBridge understands event content. Rules can match on nested JSON fields, prefix matching, numeric ranges, anything-but patterns, and IP address CIDR ranges. SQS/SNS filter on message attributes only.

**Three bus types:**
- **Default bus:** AWS service events (EC2 state changes, S3 events, CodePipeline)
- **Custom bus:** Your application events
- **Partner bus:** Third-party SaaS events (Datadog, Shopify, Zendesk)

```python
events = boto3.client("events")

# Put events to custom bus
events.put_events(
    Entries=[
        {
            "Source": "com.mycompany.orders",
            "DetailType": "OrderPlaced",
            "Detail": json.dumps({
                "orderId": "ORD-123",
                "customerId": "CUST-456",
                "total": 599.99,
                "items": [{"sku": "ABC", "qty": 2}],
            }),
            "EventBusName": "my-app-bus",
        }
    ]
)
```

**EventBridge rule — content-based routing:**
```json
{
    "source": ["com.mycompany.orders"],
    "detail-type": ["OrderPlaced"],
    "detail": {
        "total": [{"numeric": [">=", 500]}],
        "items": {
            "sku": [{"prefix": "PREMIUM-"}]
        }
    }
}
```

**EventBridge Pipes — point-to-point with enrichment:**
```
Kinesis Stream → (filter) → Lambda enricher → EventBridge Bus → SQS Target
```
Pipes replaces the boilerplate polling/batching/filtering Lambda you'd otherwise write.

```python
pipes = boto3.client("pipes")
pipes.create_pipe(
    Name="order-enrichment-pipe",
    RoleArn=role_arn,
    Source=kinesis_stream_arn,
    SourceParameters={
        "KinesisStreamParameters": {
            "StartingPosition": "LATEST",
            "BatchSize": 10,
        },
        "FilterCriteria": {
            "Filters": [{"Pattern": '{"data": {"eventType": ["OrderPlaced"]}}'}]
        },
    },
    Enrichment=enrichment_lambda_arn,
    Target=target_sqs_arn,
)
```

**EventBridge Scheduler:** Cron and rate-based event generation. Replaces CloudWatch Events scheduled rules. Supports one-time schedules (fire once at specific time), timezone-aware scheduling, and flexible time windows (deliver within a 15-minute window to reduce thundering herd).

---

### Amazon Kinesis Data Streams

When you need ordered, replayable, high-throughput event streaming — and don't need full Kafka.

```
Kinesis vs SQS decision:
- Need ordering within a partition key?      → Kinesis
- Need replay (reprocess past events)?       → Kinesis
- Need to scale consumers independently?     → Kinesis (multiple KCL apps)
- Just need reliable async work queue?       → SQS (cheaper, simpler)
- Need fan-out to N consumers?               → Kinesis (multiple consumer apps) or SNS+SQS
```

**Key limits:** 1 MB/s write per shard, 2 MB/s read per shard per consumer (5 reads/s). Enhanced fan-out: 2 MB/s per consumer per shard (dedicated throughput via HTTP/2 push).

```python
kinesis = boto3.client("kinesis")

# Write — partition key determines shard assignment
kinesis.put_record(
    StreamName="order-events",
    Data=json.dumps(event).encode(),
    PartitionKey=event["order_id"],  # all events for same order → same shard → ordered
)

# Read with KCL or manually
resp = kinesis.get_records(ShardIterator=shard_iterator, Limit=100)
for record in resp["Records"]:
    payload = json.loads(record["Data"])
    process(payload)
next_iterator = resp["NextShardIterator"]
```

---

### Apache Kafka / Amazon MSK

When Kinesis isn't enough: multi-TB/day throughput, complex consumer topologies, 7-day+ retention, cross-region replication, or existing Kafka ecosystem.

**Kafka's EDA superpowers:**
- **Consumer groups:** Multiple independent consumers read the same topic. Each group tracks its own offset. Add a new analytics consumer without any producer changes.
- **Log compaction:** Keep only the latest value per key. Useful for event-carried state transfer where you need current state, not full history.
- **Exactly-once semantics:** Kafka transactions (producer idempotency + consumer offset commit in one transaction) for financial-grade processing.
- **Kafka Streams / ksqlDB:** Stream processing directly on Kafka, no separate Flink cluster.

```python
from confluent_kafka import Producer, Consumer

# Producer with idempotency
producer = Producer({
    "bootstrap.servers": "broker1:9092,broker2:9092,broker3:9092",
    "enable.idempotence": True,         # exactly-once producer semantics
    "acks": "all",                      # wait for all ISR to acknowledge
    "compression.type": "snappy",
    "linger.ms": 5,                     # batch for 5ms to improve throughput
})

producer.produce(
    topic="order-events",
    key=order_id.encode(),
    value=json.dumps(event).encode(),
    on_delivery=lambda err, msg: log.error(err) if err else None,
)
producer.flush()

# Consumer group
consumer = Consumer({
    "bootstrap.servers": "broker1:9092",
    "group.id": "shipping-service",     # consumer group — offset tracked per group
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,        # manual commit after processing
})
consumer.subscribe(["order-events"])

while True:
    msg = consumer.poll(timeout=1.0)
    if msg and not msg.error():
        process(json.loads(msg.value()))
        consumer.commit(asynchronous=False)  # commit only after successful processing
```

**MSK vs self-managed Kafka:** MSK handles broker provisioning, OS patching, ZooKeeper (or KRaft), and CloudWatch integration. You still manage: topic creation, ACLs, schema registry, connector management, consumer group monitoring. MSK Serverless removes capacity planning but costs more per MB and has throughput limits.

---

### RabbitMQ / Amazon MQ

For teams migrating from AMQP systems or needing complex routing without full Kafka.

**AMQP exchange types:**
- **Direct:** Route by exact routing key. `order.placed` → Shipping queue.
- **Fanout:** Broadcast to all bound queues. One message → all consumers.
- **Topic:** Pattern matching. `order.#` matches `order.placed`, `order.shipped`, `order.cancelled`.
- **Headers:** Route by message headers (rarely used).

```python
import pika

connection = pika.BlockingConnection(
    pika.ConnectionParameters("rabbitmq.internal")
)
channel = connection.channel()

# Topic exchange setup
channel.exchange_declare(exchange="order-events", exchange_type="topic", durable=True)
channel.queue_declare(queue="shipping-queue", durable=True)
channel.queue_bind(
    exchange="order-events",
    queue="shipping-queue",
    routing_key="order.placed.*",  # matches order.placed.standard, order.placed.express
)

# Publish
channel.basic_publish(
    exchange="order-events",
    routing_key="order.placed.express",
    body=json.dumps(event).encode(),
    properties=pika.BasicProperties(delivery_mode=2),  # persistent
)
```

**When to use RabbitMQ over SQS/SNS:** Complex routing logic, AMQP protocol requirement, request-reply pattern (correlation IDs + reply queues), priority queues, or message TTL with dead-lettering. **Don't use** for high-throughput streaming (use Kafka) or simple fan-out (use SNS).

---

### Temporal.io

Workflow orchestration engine for durable, long-running business processes. Think Step Functions but developer-centric and open-source.

**Core model:**
- **Workflow:** Python/Go/Java function that runs durably. State is checkpointed automatically. Can sleep for months. Survives worker restarts.
- **Activity:** Side-effecting operation (API call, DB write). Retried independently on failure.
- **Signal:** External input that a running workflow can receive (e.g., "payment approved").
- **Query:** Read current workflow state without side effects.

```python
import asyncio
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

@activity.defn
async def charge_payment(order_id: str, amount: float) -> str:
    # Retried automatically on failure. Must be idempotent.
    result = await payment_gateway.charge(order_id, amount)
    return result.transaction_id

@activity.defn
async def fulfill_order(order_id: str) -> None:
    await warehouse_api.create_fulfillment(order_id)

@activity.defn
async def refund_payment(transaction_id: str) -> None:
    await payment_gateway.refund(transaction_id)

@workflow.defn
class OrderWorkflow:
    @workflow.run
    async def run(self, order_id: str, amount: float) -> str:
        transaction_id = None
        try:
            # Activities run with retry policies, timeouts, heartbeating
            transaction_id = await workflow.execute_activity(
                charge_payment,
                args=[order_id, amount],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            await workflow.execute_activity(
                fulfill_order,
                args=[order_id],
                start_to_close_timeout=timedelta(minutes=5),
            )
            return "completed"
        except Exception as e:
            # Compensating transaction
            if transaction_id:
                await workflow.execute_activity(
                    refund_payment,
                    args=[transaction_id],
                    start_to_close_timeout=timedelta(seconds=30),
                )
            raise

# Start workflow — durable from this point
client = await Client.connect("temporal.internal:7233")
handle = await client.start_workflow(
    OrderWorkflow.run,
    args=["ORD-123", 99.99],
    id=f"order-{order_id}",          # deterministic ID → deduplication
    task_queue="orders",
)
```

**Temporal vs Step Functions:**

| | Temporal | Step Functions |
|--|----------|---------------|
| **Code** | Native code (Python/Go/Java) | ASL JSON state machine |
| **Hosting** | Self-hosted or Temporal Cloud | Fully managed AWS |
| **Long waits** | Sleep for months in workflow code | `waitForTaskToken` callback pattern |
| **Testing** | Unit-testable Python | Hard to test ASL locally |
| **Cost** | Fixed cluster cost | Per-state-transition ($0.025/1k) |
| **Signals** | First-class (`.signal()`) | External task token pattern |
| **Replay** | First-class history replay | Execution history (limited) |
| **Use when** | Complex logic, developer-owned workflows | Simple state machines, AWS-native stack |

---

### AWS Step Functions

AWS-native orchestration. Excellent for workflows that integrate many AWS services without custom code.

```json
{
    "Comment": "Order processing with compensation",
    "StartAt": "ProcessPayment",
    "States": {
        "ProcessPayment": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
                "FunctionName": "process-payment",
                "Payload.$": "$"
            },
            "Retry": [{"ErrorEquals": ["Lambda.ServiceException"], "IntervalSeconds": 2, "MaxAttempts": 3}],
            "Catch": [{"ErrorEquals": ["PaymentFailed"], "Next": "OrderFailed"}],
            "Next": "ReserveInventory"
        },
        "ReserveInventory": {
            "Type": "Task",
            "Resource": "arn:aws:states:::dynamodb:updateItem",
            "Parameters": {
                "TableName": "inventory",
                "Key": {"sku": {"S.$": "$.sku"}},
                "UpdateExpression": "SET reserved = reserved + :qty",
                "ExpressionAttributeValues": {":qty": {"N.$": "States.JsonToString($.quantity)"}}
            },
            "Catch": [{"ErrorEquals": ["InsufficientInventory"], "Next": "RefundPayment"}],
            "Next": "OrderComplete"
        },
        "RefundPayment": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {"FunctionName": "refund-payment", "Payload.$": "$"},
            "Next": "OrderFailed"
        },
        "OrderComplete": {"Type": "Succeed"},
        "OrderFailed": {"Type": "Fail", "Error": "OrderProcessingFailed"}
    }
}
```

**Express Workflows** (< 5 min, high throughput, at-least-once) vs **Standard Workflows** (up to 1 year, exactly-once, full audit trail). Use Express for real-time event processing, Standard for business-critical transactions.

---

## Tool Selection Guide

```
What's your primary need?

Simple async work queue
    → SQS Standard (with DLQ)

Fan-out (one event → many consumers)
    → SNS → SQS (with per-subscriber DLQ)

Content-based routing / AWS service integration
    → EventBridge (custom bus + rules)

High-throughput ordered streaming / replay
    Throughput < 1 GB/s and team prefers managed → Kinesis
    Throughput > 1 GB/s or need Kafka ecosystem  → MSK (Kafka)

Complex routing, AMQP migration
    → RabbitMQ / Amazon MQ

Long-running durable workflows (minutes to months)
    Team owns infrastructure / complex logic → Temporal
    AWS-native / simpler state machines      → Step Functions

Real-time stream processing
    → Kinesis Data Analytics (managed Flink) or MSK + Flink
```

---

## AWS Services Quick Reference

| Service | Type | Max Message | Retention | Ordering | Throughput |
|---------|------|-------------|-----------|---------|-----------|
| **SQS Standard** | Queue | 256 KB | 14 days | Best-effort | Near-unlimited |
| **SQS FIFO** | Queue | 256 KB | 14 days | Strict | 3,000 msg/s |
| **SNS** | Pub-sub | 256 KB | None (fire-forget) | No | Near-unlimited |
| **EventBridge** | Event bus | 256 KB | None (fire-forget) | No | 10,000 events/s default |
| **Kinesis** | Stream | 1 MB | 7 days (365 extended) | Per-shard | 1 MB/s per shard write |
| **MSK (Kafka)** | Stream | 1 MB (configurable) | Configurable | Per-partition | Multi-GB/s |
| **Step Functions Standard** | Orchestration | 256 KB | 90 days history | N/A | 2,000 starts/s |
| **Step Functions Express** | Orchestration | 256 KB | 90 days | N/A | 100,000 starts/s |
