# Use Cases

## Use Case 1: E-Commerce Order Processing Saga

**Problem:** Order placement touches payment, inventory, fraud detection, and shipping — each in separate microservices. A synchronous chain fails if any service is down. A direct API fan-out creates tight coupling.

**Architecture: Orchestrated Saga via Temporal**

```
Customer → OrderService (synchronous REST) → Temporal Workflow (async)
```

```python
@workflow.defn
class OrderProcessingWorkflow:
    @workflow.run
    async def run(self, order: dict) -> dict:
        order_id = order["order_id"]
        completed_steps = []

        try:
            # Step 1: Fraud check (fail fast if high risk)
            fraud_result = await workflow.execute_activity(
                run_fraud_check,
                args=[order],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            if fraud_result["risk_score"] > 0.85:
                raise ApplicationError("HighFraudRisk", fraud_result["risk_score"])

            # Step 2: Payment — most expensive compensation, so do second
            payment = await workflow.execute_activity(
                process_payment,
                args=[order_id, order["amount"], order["payment_method"]],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    non_retryable_error_types=["InsufficientFunds", "CardDeclined"],
                ),
            )
            completed_steps.append(("payment", payment["transaction_id"]))

            # Step 3: Reserve inventory
            reservation = await workflow.execute_activity(
                reserve_inventory,
                args=[order_id, order["items"]],
                start_to_close_timeout=timedelta(seconds=20),
            )
            completed_steps.append(("inventory", reservation["reservation_id"]))

            # Step 4: Create shipment (3PL integration — slow)
            shipment = await workflow.execute_activity(
                create_shipment,
                args=[order_id, order["shipping_address"]],
                schedule_to_close_timeout=timedelta(minutes=30),  # 3PL can be slow
                heartbeat_timeout=timedelta(minutes=5),            # detect stuck activities
            )

            # Publish success event — choreography consumers handle the rest
            await workflow.execute_activity(
                publish_event,
                args=[{
                    "event_type": "OrderConfirmed",
                    "order_id": order_id,
                    "shipment_tracking": shipment["tracking_number"],
                }],
            )
            return {"status": "confirmed", "tracking": shipment["tracking_number"]}

        except Exception as e:
            # Compensate in reverse order
            for step, step_id in reversed(completed_steps):
                if step == "payment":
                    await workflow.execute_activity(
                        refund_payment,
                        args=[step_id],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=5),
                    )
                elif step == "inventory":
                    await workflow.execute_activity(
                        release_inventory_reservation,
                        args=[step_id],
                    )
            raise
```

**Consumer services (choreography for side effects):**
```
OrderConfirmed event →
    EmailService (sends confirmation)
    NotificationService (push notification)
    AnalyticsService (revenue attribution)
    LoyaltyService (award points)
```

**Result:** Core transaction (payment + inventory + shipping) is orchestrated with full compensation. Side effects (email, analytics, loyalty) are choreographed — adding a new side effect requires zero changes to existing services.

---

## Use Case 2: Microservices Fan-Out Without Coupling

**Problem:** A user updates their profile (name, email, avatar). Four services need to know: recommendations (personalization), search (indexing), billing (invoice name), and notifications (email delivery). Current architecture makes direct REST calls — a billing service outage fails the profile update.

**Before (bad — synchronous fan-out):**
```python
def update_profile(user_id: str, changes: dict):
    db.update(user_id, changes)
    recommendations.update(user_id, changes)  # what if this is down?
    search_index.update(user_id, changes)
    billing.update(user_id, changes)
    notifications.update(user_id, changes)
    # Any failure → rollback or partial update → inconsistent state
```

**After (EDA — SNS fan-out pattern):**

```
ProfileService → SNS "user-events" topic
    ├── SQS "recommendations-user-events" → Recommendations Lambda
    ├── SQS "search-user-events" → Search indexer
    ├── SQS "billing-user-events" → Billing service
    └── SQS "notifications-user-events" → Notification service
```

```python
def update_profile(user_id: str, changes: dict):
    # Outbox pattern: atomic DB write + event
    with db.transaction():
        db.update(user_id, changes)
        outbox.insert({
            "event_type": "UserProfileUpdated",
            "user_id": user_id,
            "changes": changes,
            "occurred_at": datetime.now().isoformat(),
        })
    # Outbox publisher polls and sends to SNS
    # Returns immediately — profile update is committed

# Each downstream service processes independently:
def recommendations_consumer(event: dict):
    # User not found? Update when they next interact — eventually consistent
    try:
        update_recommendation_context(event["user_id"], event["changes"])
    except UserNotFoundError:
        pass  # Will sync on next request

def billing_consumer(event: dict):
    # Billing is critical — process with idempotency key
    if "name" in event["changes"] or "email" in event["changes"]:
        billing_db.update_customer(
            event["user_id"],
            name=event["changes"].get("name"),
            email=event["changes"].get("email"),
            idempotency_key=event["event_id"],
        )
```

**Operational wins:**
- Billing outage → messages queue in SQS → processed when billing recovers → user sees consistent billing name (eventually)
- Adding a new downstream consumer (e.g., fraud detection needs updated emails) requires no ProfileService changes — just subscribe to the SNS topic
- Per-consumer DLQ: billing failures don't affect search indexing

---

## Use Case 3: Async Job Processing Pipeline

**Problem:** Users submit video transcoding jobs. Each job takes 5–60 minutes. Synchronous API times out. The UI must show progress. Spiky load (Monday morning batch upload) must be absorbed without scaling the API tier.

**Architecture:**

```
User → API Gateway → Lambda (submit job) → SQS job queue
                   ← job_id (immediate response)

SQS → EC2/ECS Spot workers (pull, process, heartbeat)
Workers → DynamoDB (job status updates)
Workers → EventBridge (job completed/failed events)

User polls GET /jobs/{id} → DynamoDB (status, progress %)
Or: EventBridge → API Gateway WebSocket connection → browser push
```

```python
# Submit: synchronous, fast
def submit_transcoding_job(request):
    job_id = str(uuid4())

    # Create job record
    dynamodb.put_item(
        TableName="transcoding-jobs",
        Item={
            "job_id": job_id,
            "status": "QUEUED",
            "submitted_at": datetime.now().isoformat(),
            "user_id": request["user_id"],
            "source_s3_uri": request["source_uri"],
        }
    )

    # Enqueue
    sqs.send_message(
        QueueUrl=JOB_QUEUE_URL,
        MessageBody=json.dumps({"job_id": job_id, "source_uri": request["source_uri"]}),
        MessageGroupId=request["user_id"],  # FIFO: fair ordering per user
        MessageDeduplicationId=job_id,
    )

    return {"job_id": job_id, "status": "queued"}

# Worker: long-running, reports progress
def process_job(job: dict):
    job_id = job["job_id"]

    try:
        # Update status to PROCESSING
        update_job_status(job_id, "PROCESSING", progress=0)

        # Extend visibility timeout during processing (heartbeat pattern)
        receipt_handle = job["receipt_handle"]

        for i, chunk in enumerate(transcode_chunks(job["source_uri"])):
            process_chunk(chunk)
            progress = int((i + 1) / total_chunks * 100)

            # Heartbeat: extend visibility timeout before it expires
            if i % 10 == 0:
                sqs.change_message_visibility(
                    QueueUrl=JOB_QUEUE_URL,
                    ReceiptHandle=receipt_handle,
                    VisibilityTimeout=300,  # extend by 5 more minutes
                )
                update_job_status(job_id, "PROCESSING", progress=progress)

        output_uri = upload_result(job_id)
        update_job_status(job_id, "COMPLETED", progress=100, output_uri=output_uri)

        # Publish completion event — other systems react
        publish_event({
            "event_type": "TranscodingCompleted",
            "job_id": job_id,
            "output_uri": output_uri,
            "user_id": job["user_id"],
        })

        sqs.delete_message(QueueUrl=JOB_QUEUE_URL, ReceiptHandle=receipt_handle)

    except Exception as e:
        update_job_status(job_id, "FAILED", error=str(e))
        # Don't delete — let it go to DLQ after maxReceiveCount retries
        raise
```

**Scaling pattern:** SQS queue depth drives Auto Scaling of Spot instance fleet. Queue depth > 100 → scale up. Queue depth == 0 → scale down to 0. API tier scales independently (no video processing happening there).

---

## Use Case 4: Real-Time Notification System

**Problem:** 50 million users. Notifications come from multiple sources: order updates (from order service), promotional events (from marketing), system alerts (from infrastructure). Push to mobile, email, in-app. Different delivery channels have different latency requirements: push in < 1s, email in < 5s, in-app in < 500ms.

**Architecture:**

```
Order Service    ──┐
Marketing        ──┼──→ EventBridge Bus → SQS "notification-routing" → Notification Router
Infrastructure   ──┘

Notification Router:
    Read user preferences (channel priority, quiet hours, frequency cap)
    → In-App Channel SQS → Redis Pub/Sub → WebSocket connections
    → Push Channel SQS → APNs/FCM workers
    → Email Channel SQS → SendGrid/SES workers
```

```python
# Notification Router — runs on each EventBridge event
def route_notification(event: dict) -> None:
    notification = parse_notification(event)
    user_id = notification["user_id"]

    # Get user preferences (cached in Redis, 5 min TTL)
    prefs = get_user_preferences(user_id)

    # Frequency cap: max 5 non-critical notifications per hour
    if notification["priority"] != "critical":
        if is_frequency_capped(user_id, window_minutes=60, max_count=5):
            log.info(f"Frequency capped {user_id} for {notification['type']}")
            return

    # Quiet hours check
    if is_quiet_hours(prefs["timezone"], prefs["quiet_hours"]):
        if notification["priority"] == "low":
            schedule_for_morning(notification, prefs["timezone"])
            return

    # Route to appropriate channels based on preference + priority
    channels = determine_channels(notification["priority"], prefs["channels"])

    for channel in channels:
        channel_queue = CHANNEL_QUEUES[channel]
        sqs.send_message(
            QueueUrl=channel_queue,
            MessageBody=json.dumps({
                **notification,
                "channel": channel,
                "routed_at": datetime.now().isoformat(),
            }),
        )

    # Record for frequency capping
    increment_notification_count(user_id, notification["type"])

# In-App delivery: Redis Pub/Sub for real-time
def deliver_inapp(notification: dict) -> None:
    user_id = notification["user_id"]

    # Store in notification inbox (DynamoDB, TTL 30 days)
    store_notification(notification)

    # Publish to Redis channel if user is online (WebSocket connected)
    redis_channel = f"notifications:{user_id}"
    if redis.publish(redis_channel, json.dumps(notification)) == 0:
        # No subscribers — user is offline. Notification stored in inbox for next login.
        pass
```

**Delivery guarantees:**
- **In-app:** At-least-once via Redis pub/sub + inbox store. Idempotent: dedup by notification_id on client.
- **Push (APNs/FCM):** At-least-once with provider-side dedup. `apns-collapse-id` for collapsing duplicate pushes.
- **Email:** At-most-once acceptable (users don't want duplicate emails). Send with idempotency key to SendGrid.

---

## Use Case 5: Event-Driven Data Ingestion Pipeline

**Problem:** 200 microservices each emit domain events to Kafka. The data science team needs these events in S3 (raw) and Redshift (aggregated) for analytics. Adding ingestion logic to each service would be non-scalable.

**Architecture: Event Tap Pattern**

```
Services → Kafka topics (owned by each service team)
    ↓ (read-only tap — no service changes required)
Kafka Connect (S3 Sink Connector) → S3 raw data lake (Bronze layer)
    ↓
Lambda (Firehose delivery stream) → S3 Parquet (Silver layer)
    ↓
Glue/dbt → Redshift / Athena (Gold layer)
```

```python
# Kafka Connect S3 Sink Connector config (deployed via Kafka Connect REST API)
connector_config = {
    "name": "s3-sink-all-topics",
    "config": {
        "connector.class": "io.confluent.connect.s3.S3SinkConnector",
        "tasks.max": "8",
        "topics.regex": ".*",               # tap all topics
        "s3.region": "us-east-1",
        "s3.bucket.name": "data-lake-raw",
        "s3.part.size": "67108864",         # 64 MB parts
        "flush.size": "10000",              # flush every 10k records
        "rotate.interval.ms": "300000",     # or every 5 minutes
        "storage.class": "io.confluent.connect.s3.storage.S3Storage",
        "format.class": "io.confluent.connect.s3.format.json.JsonFormat",
        "partitioner.class": "io.confluent.connect.storage.partitioner.TimeBasedPartitioner",
        "path.format": "'year'=YYYY/'month'=MM/'day'=dd/'hour'=HH",
        "locale": "en_US",
        "timezone": "UTC",
        "timestamp.extractor": "RecordField",
        "timestamp.field": "occurred_at",   # use event time, not processing time
        "schema.compatibility": "FULL",
    }
}

# EventBridge Pipe: Kinesis → filter → enrich → SQS (for services using Kinesis instead of Kafka)
pipe_config = {
    "Source": kinesis_arn,
    "SourceParameters": {
        "KinesisStreamParameters": {"StartingPosition": "LATEST", "BatchSize": 100},
        "FilterCriteria": {
            "Filters": [
                {"Pattern": '{"data": {"event_type": [{"prefix": "Order"}]}}'}
            ]
        },
    },
    "Enrichment": enrichment_lambda_arn,  # add correlation IDs, normalize schemas
    "Target": analytics_sqs_arn,
}
```

**Schema evolution handling:** When Service A adds a new field to their event schema:
- Bronze layer (raw JSON): automatically stores new field — no pipeline changes
- Silver layer (Parquet): schema auto-evolves (Delta Lake `mergeSchema=true` or Iceberg schema evolution)
- Gold layer (aggregates): dbt model only breaks if it references the changed/removed field — explicit break, not silent

This is the correct failure mode: your analytics breaks visibly at the schema assertion point, not silently downstream.
