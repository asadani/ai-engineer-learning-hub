# Key Technical Concepts

## 1. The Outbox Pattern

The single most important reliability pattern in EDA. Solves the dual-write problem: how do you atomically write to your database AND publish an event? If you write to the DB and then the process crashes before publishing the event, the event is lost. If you publish the event first and the DB write fails, you have an event for a thing that didn't happen.

**The wrong approach:**
```python
# WRONG: non-atomic — event can be lost if process crashes between these two lines
def place_order(order: Order):
    db.insert(orders_table, order)          # DB write succeeds
    kafka.produce("orders.events", order)   # crash here → event lost
```

**The Outbox Pattern:**
```python
# CORRECT: write to DB and outbox table in the same transaction
import psycopg2
import json
from datetime import datetime

def place_order(order: dict) -> str:
    """Atomically create order and stage event in outbox."""
    with db.transaction() as tx:
        # 1. Write the order (domain state)
        tx.execute(
            "INSERT INTO orders (order_id, customer_id, total, status) VALUES (%s, %s, %s, %s)",
            (order["order_id"], order["customer_id"], order["total"], "placed"),
        )
        # 2. Write the event to the outbox table (same transaction)
        tx.execute(
            """INSERT INTO outbox_events
               (event_id, aggregate_type, aggregate_id, event_type, payload, created_at, published)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                str(uuid.uuid4()), "Order", order["order_id"], "OrderPlaced",
                json.dumps(order), datetime.utcnow(), False,
            ),
        )
    return order["order_id"]

# Separate polling publisher (can be a background thread or sidecar)
class OutboxPublisher:
    def __init__(self, db, producer, poll_interval_s: float = 1.0):
        self.db = db
        self.producer = producer
        self.poll_interval_s = poll_interval_s

    def run(self):
        while True:
            events = self.db.execute(
                "SELECT * FROM outbox_events WHERE published = FALSE ORDER BY created_at LIMIT 100"
            ).fetchall()

            for event in events:
                try:
                    self.producer.produce(
                        topic=f"{event.aggregate_type.lower()}.events",
                        key=event.aggregate_id,
                        value=event.payload,
                        headers={"event_type": event.event_type, "event_id": event.event_id},
                    )
                    self.producer.flush()
                    self.db.execute(
                        "UPDATE outbox_events SET published = TRUE, published_at = %s WHERE event_id = %s",
                        (datetime.utcnow(), event.event_id),
                    )
                except Exception as e:
                    # Log failure — will retry on next poll
                    log.error(f"Failed to publish {event.event_id}: {e}")

            time.sleep(self.poll_interval_s)
```

**Alternative: CDC-based outbox.** Instead of a polling publisher, Debezium watches the `outbox_events` table and publishes changes to Kafka automatically. Zero polling overhead, sub-second latency. This is the production-recommended approach.

---

## 2. Idempotent Consumers

With at-least-once delivery, your consumer will receive the same event more than once. Every consumer must handle this without creating duplicate side effects.

```python
import boto3
from datetime import datetime, timedelta
import hashlib

dynamodb = boto3.resource("dynamodb")
idempotency_table = dynamodb.Table("processed-events")

class IdempotentEventHandler:
    def __init__(self, ttl_hours: int = 48):
        self.ttl_hours = ttl_hours

    def is_already_processed(self, event_id: str) -> bool:
        response = idempotency_table.get_item(Key={"event_id": event_id})
        return "Item" in response

    def mark_processed(self, event_id: str, result: dict):
        ttl = int((datetime.utcnow() + timedelta(hours=self.ttl_hours)).timestamp())
        idempotency_table.put_item(Item={
            "event_id": event_id,
            "processed_at": datetime.utcnow().isoformat(),
            "result": str(result),
            "ttl": ttl,  # DynamoDB TTL auto-deletes old entries
        })

    def handle(self, event: dict, handler_fn):
        event_id = event.get("event_id") or self.derive_event_id(event)

        if self.is_already_processed(event_id):
            return {"status": "already_processed", "event_id": event_id}

        # Process the event
        result = handler_fn(event)

        # Idempotently mark as processed
        # Use conditional write to handle race conditions (two concurrent consumers)
        try:
            idempotency_table.put_item(
                Item={"event_id": event_id, "processed_at": datetime.utcnow().isoformat()},
                ConditionExpression="attribute_not_exists(event_id)",  # only write if not exists
            )
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            # Another instance processed it first — that's fine
            return {"status": "concurrent_dedup", "event_id": event_id}

        return result

    def derive_event_id(self, event: dict) -> str:
        """Derive deterministic ID from event content when no event_id is provided."""
        content = json.dumps(event, sort_keys=True).encode()
        return hashlib.sha256(content).hexdigest()

# Usage
handler = IdempotentEventHandler()

def process_order_placed(event: dict) -> dict:
    def _do_work(e):
        # Create shipment, notify warehouse, etc.
        shipment_id = create_shipment(e["order_id"], e["shipping_address"])
        return {"shipment_id": shipment_id}

    return handler.handle(event, _do_work)
```

---

## 3. Saga Pattern: Managing Distributed Transactions

A saga is a sequence of local transactions across multiple services, coordinated via events. Each step publishes an event that triggers the next step. If any step fails, compensating transactions roll back prior steps.

### Choreography Saga

```python
# No central coordinator — services react to each other's events

# Order Service publishes OrderPlaced
# Payment Service listens for OrderPlaced, processes payment, publishes PaymentProcessed or PaymentFailed
# Inventory Service listens for PaymentProcessed, reserves stock, publishes StockReserved or StockInsufficient
# Shipping Service listens for StockReserved, creates shipment, publishes ShipmentCreated
# If PaymentFailed → Order Service listens, cancels order, publishes OrderCancelled

class PaymentService:
    def handle_order_placed(self, event: dict):
        order_id = event["order_id"]
        try:
            charge_result = stripe.charge(
                amount=event["total_amount"],
                currency="usd",
                source=event["payment_token"],
                idempotency_key=f"order-{order_id}",  # Stripe idempotency key
            )
            self.publish("payment.events", {
                "event_type": "PaymentProcessed",
                "order_id": order_id,
                "charge_id": charge_result.id,
                "amount": event["total_amount"],
            })
        except stripe.error.CardError as e:
            self.publish("payment.events", {
                "event_type": "PaymentFailed",
                "order_id": order_id,
                "reason": str(e),
            })

class InventoryService:
    def handle_payment_processed(self, event: dict):
        order_id = event["order_id"]
        order = self.fetch_order(order_id)  # fetch from Order Service or local projection
        try:
            for item in order["items"]:
                self.reserve_stock(item["sku"], item["qty"], order_id)
            self.publish("inventory.events", {
                "event_type": "StockReserved",
                "order_id": order_id,
                "reservation_ids": self.get_reservation_ids(order_id),
            })
        except InsufficientStockError as e:
            # Compensating transaction: trigger payment refund
            self.publish("inventory.events", {
                "event_type": "StockReservationFailed",
                "order_id": order_id,
                "reason": str(e),
            })

    def handle_order_cancelled(self, event: dict):
        """Compensating transaction: release reserved stock."""
        self.release_reservations(event["order_id"])
```

### Orchestration Saga (AWS Step Functions)

```python
import boto3
import json

sfn = boto3.client("stepfunctions", region_name="us-east-1")

# State machine definition (JSON or CDK)
ORDER_SAGA_DEFINITION = {
    "Comment": "Order processing saga with compensations",
    "StartAt": "ProcessPayment",
    "States": {
        "ProcessPayment": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123456789:function:process-payment",
            "Catch": [{
                "ErrorEquals": ["PaymentFailed"],
                "Next": "CancelOrder",
                "ResultPath": "$.error",
            }],
            "Next": "ReserveStock",
        },
        "ReserveStock": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123456789:function:reserve-stock",
            "Catch": [{
                "ErrorEquals": ["StockInsufficient"],
                "Next": "RefundPayment",
                "ResultPath": "$.error",
            }],
            "Next": "CreateShipment",
        },
        "CreateShipment": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123456789:function:create-shipment",
            "Next": "OrderComplete",
        },
        # Compensating states
        "RefundPayment": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123456789:function:refund-payment",
            "Next": "CancelOrder",
        },
        "CancelOrder": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123456789:function:cancel-order",
            "Next": "OrderFailed",
        },
        "OrderComplete": {"Type": "Succeed"},
        "OrderFailed": {"Type": "Fail", "Error": "OrderFailed"},
    },
}

def start_order_saga(order: dict) -> str:
    response = sfn.start_execution(
        stateMachineArn="arn:aws:states:us-east-1:123456789:stateMachine:OrderProcessingSaga",
        name=f"order-{order['order_id']}",  # unique execution name = idempotency key
        input=json.dumps(order),
    )
    return response["executionArn"]
```

---

## 4. Amazon EventBridge

EventBridge is AWS's managed event bus. Key differentiator: content-based routing — you filter events by their content (field values) without writing code.

```python
import boto3
import json
from datetime import datetime

events = boto3.client("events", region_name="us-east-1")

# Publish an event to EventBridge
def publish_order_event(event_type: str, order: dict):
    events.put_events(Entries=[{
        "Source": "com.mycompany.order-service",
        "DetailType": event_type,  # e.g., "OrderPlaced", "OrderShipped"
        "Detail": json.dumps({
            **order,
            "occurred_at": datetime.utcnow().isoformat(),
        }),
        "EventBusName": "MyAppEventBus",
        "Time": datetime.utcnow(),
    }])

# EventBridge Rule: content-based routing
# Route high-value orders to priority processing queue
PRIORITY_ORDER_RULE = {
    "Name": "HighValueOrderRule",
    "EventBusName": "MyAppEventBus",
    "EventPattern": json.dumps({
        "source": ["com.mycompany.order-service"],
        "detail-type": ["OrderPlaced"],
        "detail": {
            "total_amount": [{"numeric": [">=", 1000]}],  # orders >= $1000
            "customer_tier": ["premium", "enterprise"],
        },
    }),
    "Targets": [{
        "Id": "PriorityFulfillmentQueue",
        "Arn": "arn:aws:sqs:us-east-1:123456789:priority-fulfillment.fifo",
    }],
}

# EventBridge Pipes: connect source → filter → enrich → target without code
# Kinesis stream → filter → Lambda enrichment → SQS
PIPE_CONFIG = {
    "Name": "OrderEnrichmentPipe",
    "Source": "arn:aws:kinesis:us-east-1:123456789:stream/order-events",
    "SourceParameters": {
        "KinesisStreamParameters": {"StartingPosition": "LATEST", "BatchSize": 10},
        "FilterCriteria": {
            "Filters": [{"Pattern": json.dumps({"data": {"event_type": ["OrderPlaced"]}})}]
        },
    },
    "Enrichment": "arn:aws:lambda:us-east-1:123456789:function:enrich-order",
    "Target": "arn:aws:sqs:us-east-1:123456789:fulfillment-queue",
}
```

**EventBridge vs SNS vs SQS vs Kafka — the selection guide:**
- **EventBridge:** Content-based routing, AWS service integration (CloudTrail → EventBridge → Lambda is native), managed schema registry, multi-account event buses. Limit: 10k events/sec per bus.
- **SNS:** Simple pub-sub fan-out, HTTP/SQS/Lambda targets. No content filtering beyond subscription filter policies (field exists/value). Best for simple fan-out to N destinations.
- **SQS:** Queue-based work distribution (competing consumers), DLQ native, visibility timeout. Best for worker pools. Not pub-sub — one consumer per message.
- **Kafka/MSK:** High-throughput (millions/sec), log retention, consumer group replay, complex routing. Best for high-volume, stream processing, multi-consumer with independent offsets.

---

## 5. Dead Letter Queues (DLQ)

```python
import boto3
import json
from datetime import datetime

sqs = boto3.client("sqs", region_name="us-east-1")
cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

# Create main queue with DLQ
dlq_url = sqs.create_queue(
    QueueName="order-processing-dlq",
    Attributes={
        "MessageRetentionPeriod": str(14 * 24 * 3600),  # 14-day retention
        "VisibilityTimeout": "30",
    },
)["QueueUrl"]

dlq_arn = sqs.get_queue_attributes(
    QueueUrl=dlq_url, AttributeNames=["QueueArn"]
)["Attributes"]["QueueArn"]

main_queue_url = sqs.create_queue(
    QueueName="order-processing",
    Attributes={
        "VisibilityTimeout": "300",    # 5-minute processing window per message
        "MessageRetentionPeriod": str(4 * 24 * 3600),  # 4-day retention
        "RedrivePolicy": json.dumps({
            "deadLetterTargetArn": dlq_arn,
            "maxReceiveCount": "3",  # send to DLQ after 3 failed attempts
        }),
    },
)["QueueUrl"]

# DLQ monitoring: alert on any DLQ message
cloudwatch.put_metric_alarm(
    AlarmName="OrderProcessingDLQNotEmpty",
    MetricName="ApproximateNumberOfMessagesVisible",
    Namespace="AWS/SQS",
    Dimensions=[{"Name": "QueueName", "Value": "order-processing-dlq"}],
    Statistic="Sum",
    Period=60,
    EvaluationPeriods=1,
    Threshold=1,
    ComparisonOperator="GreaterThanOrEqualToThreshold",
    AlarmActions=["arn:aws:sns:us-east-1:123456789:on-call-alerts"],
    TreatMissingData="notBreaching",
)

# DLQ replay: reprocess failed messages after fixing the bug
def replay_dlq(dlq_url: str, target_queue_url: str, batch_size: int = 10):
    """Move messages from DLQ back to main queue for reprocessing."""
    replayed = 0
    while True:
        response = sqs.receive_message(
            QueueUrl=dlq_url,
            MaxNumberOfMessages=min(batch_size, 10),
            WaitTimeSeconds=5,
        )
        messages = response.get("Messages", [])
        if not messages:
            break

        for msg in messages:
            # Optionally add metadata before replaying
            body = json.loads(msg["Body"])
            body["_replayed_from_dlq"] = datetime.utcnow().isoformat()
            body["_dlq_replay_count"] = body.get("_dlq_replay_count", 0) + 1

            sqs.send_message(QueueUrl=target_queue_url, MessageBody=json.dumps(body))
            sqs.delete_message(QueueUrl=dlq_url, ReceiptHandle=msg["ReceiptHandle"])
            replayed += 1

    return replayed
```

---

## 6. Circuit Breaker for Event Consumers

```python
import time
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — reject all calls
    HALF_OPEN = "half_open" # Testing if downstream recovered

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        reset_timeout_s: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.reset_timeout_s = reset_timeout_s
        self.failure_count = 0
        self.success_count = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time = 0.0

    def call(self, fn, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.reset_timeout_s:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                raise CircuitOpenError("Circuit is OPEN — downstream service unavailable")

        try:
            result = fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        else:
            self.failure_count = 0

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

# Apply to event consumer calling a downstream service
payment_circuit = CircuitBreaker(failure_threshold=5, reset_timeout_s=30)

def handle_order_event(event: dict):
    try:
        result = payment_circuit.call(payment_service.charge, event["payment_token"], event["total"])
        publish_event("PaymentProcessed", {**event, "charge_id": result.id})
    except CircuitOpenError:
        # Don't ACK the message — it stays in queue for retry
        # Or: route to DLQ for manual intervention
        route_to_dlq(event, reason="payment_service_circuit_open")
```

---

## 7. Temporal.io: Durable Workflow Orchestration

Temporal is a workflow engine built for EDA — workflows are code, durable across failures, with automatic retry and compensation.

```python
import asyncio
from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
from datetime import timedelta

# Activities: individual steps that can fail and be retried
@activity.defn
async def process_payment(order_id: str, amount: float, token: str) -> str:
    """Each activity has automatic retry with exponential backoff."""
    charge = await stripe_client.charge(amount=amount, source=token,
                                        idempotency_key=f"order-{order_id}")
    return charge.id

@activity.defn
async def reserve_inventory(order_id: str, items: list[dict]) -> list[str]:
    reservation_ids = []
    for item in items:
        rid = await inventory_service.reserve(item["sku"], item["qty"], order_id)
        reservation_ids.append(rid)
    return reservation_ids

@activity.defn
async def release_inventory(reservation_ids: list[str]):
    """Compensating activity — runs on failure."""
    for rid in reservation_ids:
        await inventory_service.release(rid)

@activity.defn
async def refund_payment(charge_id: str):
    await stripe_client.refund(charge_id)

# Workflow: durable across process failures, restarts resume from last checkpoint
@workflow.defn
class OrderProcessingWorkflow:
    @workflow.run
    async def run(self, order: dict) -> dict:
        charge_id = None
        reservation_ids = []

        # Step 1: Process payment (retry up to 3 times, timeout 30s)
        try:
            charge_id = await workflow.execute_activity(
                process_payment,
                args=[order["order_id"], order["total"], order["payment_token"]],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception as e:
            return {"status": "failed", "reason": f"payment_failed: {e}"}

        # Step 2: Reserve inventory (with compensation if it fails)
        try:
            reservation_ids = await workflow.execute_activity(
                reserve_inventory,
                args=[order["order_id"], order["items"]],
                start_to_close_timeout=timedelta(minutes=2),
            )
        except Exception as e:
            # Compensate: refund the payment
            await workflow.execute_activity(refund_payment, args=[charge_id])
            return {"status": "failed", "reason": f"inventory_failed: {e}"}

        # Step 3: Wait for human approval if order > $10,000
        if order["total"] > 10_000:
            approval = await workflow.wait_for_signal("fraud_review_complete", timeout=timedelta(hours=24))
            if not approval["approved"]:
                await workflow.execute_activity(release_inventory, args=[reservation_ids])
                await workflow.execute_activity(refund_payment, args=[charge_id])
                return {"status": "failed", "reason": "fraud_review_rejected"}

        return {"status": "success", "charge_id": charge_id, "reservation_ids": reservation_ids}

# Start a workflow execution
async def main():
    client = await Client.connect("localhost:7233")
    result = await client.execute_workflow(
        OrderProcessingWorkflow.run,
        order_data,
        id=f"order-{order_id}",           # unique ID = idempotency key
        task_queue="order-processing",
        execution_timeout=timedelta(hours=1),
    )
```

---

## 8. Event Storming (Design Technique)

Event storming is a collaborative workshop technique for discovering domain events, commands, aggregates, and bounded contexts — before writing any code.

**The workshop artifacts (sticky notes on a wall/board):**

```
Orange  = Domain events    (OrderPlaced, PaymentFailed, StockReserved)
Blue    = Commands         (PlaceOrder, ProcessPayment, ReserveStock)
Yellow  = Aggregates       (Order, Payment, Inventory)
Pink    = External systems (Stripe, Warehouse API, Email provider)
Purple  = Policies         ("When PaymentFailed, notify customer")
Green   = Read models      (Order status view, Customer dashboard)
```

**The flow:**
1. Capture all domain events (orange) — "what happens in the business?"
2. Identify commands that trigger events (blue)
3. Group related commands + events around aggregates (yellow)
4. Identify external systems (pink) and policies (purple)
5. Draw boundaries — these become your service/bounded context boundaries

**Why this matters for architecture:** The events you discover in Event Storming become your Kafka topic structure. The aggregates become your services. The policies become your event consumers. Starting with the domain model, not the technology, produces better-bounded services.
