# Interview Questions

## L5 Questions (Senior SDE — solid EDA fundamentals)

---

### Q1: Why must event consumers be idempotent, and how do you implement it?

**The core issue:** Most message brokers (SQS, Kafka, SNS, EventBridge) guarantee at-least-once delivery — they will never drop a message, but they may deliver it multiple times. This happens when: a consumer crashes after processing but before deleting the message; a network timeout causes the producer to retry; a rebalance causes a Kafka partition to be reassigned mid-processing.

If your consumer isn't idempotent, you get: duplicate emails sent to customers, double charges on payment APIs, inventory decremented twice leaving negative stock.

**Implementation — three patterns:**

**1. Natural idempotency (preferred):** Design operations so that executing them N times has the same result as once. `SET balance = 100.00` is idempotent; `SET balance = balance - 10.00` is not. `INSERT ... ON CONFLICT DO NOTHING` is idempotent; `INSERT ...` is not.

**2. Idempotency key with conditional write (DynamoDB):**
```python
def handle_payment_event(event: dict) -> None:
    event_id = event["event_id"]

    # Conditional write: succeeds only if event_id hasn't been seen
    try:
        table.put_item(
            Item={
                "pk": f"processed:{event_id}",
                "processed_at": datetime.now().isoformat(),
                "ttl": int(time.time()) + 86400 * 7,  # 7-day TTL
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        log.info(f"Skipping duplicate event {event_id}")
        return  # idempotency check passed — skip

    # Only reaches here on first processing
    charge_payment(event["amount"], event["card_token"])
```

**3. Database unique constraint (PostgreSQL):**
```sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

-- On each event:
INSERT INTO processed_events (event_id) VALUES (:event_id)
ON CONFLICT (event_id) DO NOTHING
RETURNING event_id;
-- If no row returned, this is a duplicate — skip processing
```

**Gotcha:** The idempotency check and the side effect must be atomic, or you have a race condition between the check and the act. DynamoDB conditional write is atomic. PostgreSQL: do both in a single transaction.

---

### Q2: Explain the outbox pattern. Why is it needed?

**The problem it solves:** You want to update your database AND publish an event, and you need both to succeed or neither to succeed. The naive approach — update DB then publish to Kafka — has a failure window: DB commits, then your process crashes before publishing. The event is lost. Data is inconsistent.

**Why you can't use distributed transactions:** Kafka doesn't support 2PC with your database. Even if it did, it would create tight coupling and reduce throughput.

**The outbox pattern:**

```python
# Step 1: Atomic write to DB + outbox (same transaction)
def place_order(order: dict) -> str:
    order_id = str(uuid4())
    with db.transaction():
        db.execute(
            "INSERT INTO orders (id, customer_id, total, status) VALUES (%s, %s, %s, %s)",
            (order_id, order["customer_id"], order["total"], "PENDING")
        )
        db.execute(
            """INSERT INTO outbox_events
               (event_id, event_type, aggregate_id, payload, created_at, published)
               VALUES (%s, %s, %s, %s, NOW(), FALSE)""",
            (str(uuid4()), "OrderPlaced", order_id, json.dumps(order))
        )
    return order_id  # returns immediately, no Kafka call

# Step 2: Outbox publisher (separate process or Lambda scheduled every 1s)
def publish_outbox_events():
    rows = db.execute(
        "SELECT * FROM outbox_events WHERE published = FALSE ORDER BY created_at LIMIT 100"
    ).fetchall()

    for row in rows:
        kafka_producer.produce(
            topic=f"events.{row['event_type'].lower()}",
            key=row['aggregate_id'],
            value=row['payload'],
        )
        kafka_producer.flush()
        db.execute(
            "UPDATE outbox_events SET published = TRUE, published_at = NOW() WHERE event_id = %s",
            (row['event_id'],)
        )
```

**Two variants:**
- **Polling publisher** (shown above): Simple, adds latency (~1s polling interval). Works everywhere.
- **CDC-based**: Debezium watches the outbox table's WAL changes, publishes directly. Near-zero latency, more infrastructure.

**Common mistake:** Marking the outbox event published before Kafka ACKs it. If Kafka call fails, the event is silently lost. Always mark published only after a successful flush.

---

### Q3: What's the difference between choreography and orchestration? When do you use each?

**Choreography:** Services react to each other's events. No central coordinator. `OrderPlaced` → PaymentService handles it → publishes `PaymentProcessed` → InventoryService handles it → etc.

**Orchestration:** A central workflow engine explicitly directs each step. The orchestrator calls PaymentService, waits, calls InventoryService, waits, handles failures.

**When choreography wins:**
- Simple, linear workflows (A → B → C with no branching)
- Teams strongly want to own their service end-to-end
- The process is additive (new participants just subscribe to existing events)
- Temporal coupling would cause organizational friction

**When orchestration wins:**
- Complex branching logic (if payment fails, refund; if inventory fails, hold payment for 24h)
- You need to see the full workflow state in one place ("where is my order?")
- Compensation is required (orchestrator knows exactly what to roll back)
- The workflow crosses organizational boundaries (legal for auditors to see one execution trace)

**My default:** Orchestrate the critical path (the transaction that must succeed atomically). Choreograph the side effects (analytics, notifications, audit logs that can fail and retry independently). The pattern is not either/or — mature systems use both.

---

## L6 Questions (Principal-Adjacent — architectural depth)

---

### Q4: Design the event schema strategy for a system with 50 producer teams. How do you prevent breaking changes from cascading?

**The problem at scale:** Team A changes their `OrderPlaced` event schema (renames a field, changes a type). Downstream teams B, C, D, E all consume that event. Without enforcement, B–E break silently the next time they try to deserialize a message.

**Solution: Schema Registry + Compatibility Enforcement**

```
Producer → Schema Registry (check compatibility) → Kafka topic
Consumer ← Schema Registry (fetch schema by ID embedded in message) ←
```

**Compatibility modes (choose based on your consumer update cadence):**
- `BACKWARD`: New schema can read old data. Consumers can upgrade first, then producers.
- `FORWARD`: Old schema can read new data. Producers can upgrade first, then consumers.
- `FULL`: Both. Safest. Most restrictive. Requires additive-only changes with defaults.

**Allowed under FULL_TRANSITIVE:**
- Add optional field with default value → safe
- Rename field → NOT safe (old consumers expect old name)
- Remove field → NOT safe (consumers that depend on it break)
- Change field type → almost never safe

**For breaking changes: use versioned topics or envelope with version field:**
```json
{
    "schema_version": 2,
    "event_type": "OrderPlaced",
    "occurred_at": "2025-03-22T10:00:00Z",
    "payload": { ... }
}
```

**Organizational enforcement:**
```yaml
# .github/workflows/schema-check.yml
on:
  pull_request:
    paths: ['events/**/*.avsc', 'events/**/*.json']

jobs:
  schema-compatibility:
    steps:
      - name: Check schema compatibility
        run: |
          for schema in $(git diff --name-only HEAD~1 -- 'events/**'); do
            curl -X POST https://schema-registry/compatibility/subjects/$SUBJECT/versions/latest \
              -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
              -d "{\"schema\": $(cat $schema)}" \
              | jq -e '.is_compatible == true'
          done
```

**The two-track approach:**
1. **Producer breaking change process**: Create `order-events-v2` topic. Run v1 and v2 in parallel. Consumers migrate over 4-week window. Deprecate v1 after all consumers confirmed migrated.
2. **Schema governance**: Schema changes go through a review process (similar to API changes). Contract tests in CI catch consumer breakage before deployment.

---

### Q5: Walk me through diagnosing a consumer that's falling behind — consumer lag is growing on one Kafka partition.

**The systematic approach:**

**Step 1: Characterize the lag**
```bash
# Is lag growing uniformly or on one partition?
kafka-consumer-groups.sh --bootstrap-server broker:9092 \
  --describe --group shipping-service

GROUP           TOPIC       PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
shipping-service order-events 0        50,000,000       50,000,100    100    ← healthy
shipping-service order-events 1        49,999,000       50,100,000  101,000  ← problem partition
shipping-service order-events 2        50,001,000       50,001,050     50    ← healthy
```
One partition is problematic. This points to: a poison pill message on that partition, a slow key (all heavy orders hash to the same partition), or a worker processing partition 1 is resource-constrained.

**Step 2: Check if consumer is running**
- Is the consumer group active? Any recent rebalances?
- Lambda concurrency limit hit? ECS task OOM killed?

**Step 3: Identify the blocking message**
```python
# Read the messages around the committed offset on partition 1
consumer = KafkaConsumer(
    bootstrap_servers=BROKERS,
    auto_offset_reset="earliest",
)
consumer.assign([TopicPartition("order-events", 1)])
consumer.seek(TopicPartition("order-events", 1), 49_999_000)

for msg in consumer:
    try:
        payload = json.loads(msg.value)
        process(payload)
    except Exception as e:
        print(f"Failing message at offset {msg.offset}: {e}")
        print(f"Message: {msg.value}")
        break
```

**Step 4: Resolution paths**

| Root Cause | Fix |
|------------|-----|
| Poison pill (undeserializable message) | Skip offset manually (`consumer.seek(partition, offset+1)`); add to DLQ |
| Slow processing for specific message type | Add timeout + DLQ; optimize processing |
| Consumer OOM on large message | Fix memory, add message size check |
| Hot partition (one key getting all traffic) | Repartition topic with better key strategy |
| Consumer replicas too few | Scale consumer group (add instances) |
| Downstream service slow (DB, external API) | Add timeout, circuit breaker |

**Step 5: Prevent recurrence**
- Add partition-level lag monitoring (alert on per-partition lag, not just total)
- Schema validation at consume time with DLQ for parse failures
- Consumer processing timeout with DLQ fallback
- Message size limits at producer (reject large messages early)

---

### Q6: You're asked to move a monolith's checkout flow to microservices with EDA. How do you approach the migration without big-bang risk?

**The Strangler Fig + Event Spine pattern:**

**Phase 1: Event tap without changing the monolith**
Deploy Debezium to capture all checkout-related DB table changes as events on Kafka. No monolith changes. New downstream services start consuming these events and building their read models in parallel with the monolith.

**Phase 2: Shadow mode**
New Payment microservice processes payment events alongside the monolith. Results are compared (shadow testing) but not acted on. Discrepancies are logged. Run for 2–4 weeks until shadow service agrees with monolith on 99.9%+ of events.

**Phase 3: Dual write**
Monolith continues to handle checkout. After checkout, it publishes an `OrderPlaced` event (add event publishing to monolith — minimal change). New services start consuming the event. Monolith still does the fan-out work (email, inventory). Validate downstream services are correctly handling events.

**Phase 4: Traffic cut**
Route a small % of checkout traffic to the new service. Increase incrementally. Use feature flag to control %.

**Phase 5: Monolith hollowing**
Remove checkout logic from monolith, one capability at a time, once new services have proven themselves in production.

**What you don't do:** Freeze the monolith codebase, spend 6 months building all microservices, then do a big-bang cutover. This is how migrations fail.

---

## L7+ Questions (Principal — systemic and organizational scale)

---

### Q7: How do you handle eventual consistency in an EDA system that your business stakeholders insist must be "consistent"?

**Reframing the conversation:** "Consistent" means different things depending on context. When a user places an order and sees "Order confirmed" — do they need to see correct inventory count updated immediately? Usually no. Do they need to know their payment succeeded? Absolutely.

**The spectrum of consistency requirements:**

| User action | Consistency requirement | Solution |
|-------------|------------------------|---------|
| "Was my order placed?" | Strong — must know immediately | Synchronous payment API + optimistic order creation |
| "How much inventory is left?" | Eventual is fine — 5s lag acceptable | Async consumer updates inventory read model |
| "What's my account balance?" | Strong — financial read | Read from source of truth DB, not derived read model |
| "Did my shipment update?" | Eventual — 30s acceptable | EDA, consumer updates shipping status |

**Techniques for handling eventual consistency in the UI:**
1. **Optimistic updates:** Show the state the user expects to see after their action completes, before it actually completes. Reconcile asynchronously. Revert with user-friendly message if the background operation fails.

2. **Read-your-writes consistency:** After a write, route the user's subsequent reads to the same replica that received the write (or read from the event log for their session). Prevents "I just updated my name and it still shows the old one."

3. **Semantic lock:** Show a "Processing..." state with a spinner when the operation is in-flight. Only show the final state after the async processing completes (poll or WebSocket).

4. **Consistency SLA in the contract:** Make explicit: "Inventory counts are consistent within 10 seconds of an order." This is a design decision, not a bug.

**For stakeholders:** The question isn't "can we avoid eventual consistency?" — it's "what's the acceptable consistency window for each user-visible operation?" Work backward from user experience requirements to technical constraints, not the other way around.

---

### Q8: Design an event-driven audit system for a financial services company with regulatory requirements (e.g., need to reproduce any system state as of a given timestamp, retain events for 7 years).

**Requirements translation:**
- Reproduce state as of any past timestamp → Event sourcing (state as a projection of events)
- 7-year retention → Immutable event log with cold storage tiering
- Regulatory audit → Tamper-evident storage, access logging, chain of custody

**Architecture:**

```
Financial Events → Kafka (7-day hot retention)
                → Kafka Connect → S3 (Bronze, raw JSON, 7-year retention)
                → Kafka Connect → S3 (Avro with schema version, for reproducible deserialization)

Audit Query → Athena on S3 (full history)
            → DynamoDB (current state projection, last 90 days)
            → ElasticSearch (event text search)
```

**Tamper evidence:**
```python
def store_audit_event(event: dict) -> str:
    # Hash chaining: each event includes hash of previous event
    # Makes it detectable if any event is deleted or modified
    event_id = str(uuid4())
    previous_hash = get_latest_event_hash()

    event_with_chain = {
        **event,
        "event_id": event_id,
        "previous_event_hash": previous_hash,
        "event_hash": hashlib.sha256(
            (previous_hash + json.dumps(event, sort_keys=True)).encode()
        ).hexdigest(),
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write to S3 with object lock (WORM — Write Once Read Many)
    s3.put_object(
        Bucket="audit-events-archive",
        Key=f"events/{event['occurred_at'][:10]}/{event_id}.json",
        Body=json.dumps(event_with_chain).encode(),
        ObjectLockMode="COMPLIANCE",
        ObjectLockRetainUntilDate=datetime.now(timezone.utc) + timedelta(days=365*7),
    )

    return event_id
```

**State reproduction query:**
```python
def reconstruct_account_state(account_id: str, as_of: datetime) -> dict:
    """Replay all events for an account up to a given timestamp."""
    events = query_events(
        filter={"account_id": account_id},
        max_timestamp=as_of,
        order="asc",
    )

    state = {}
    for event in events:
        state = apply_event(state, event)

    return {
        "account_id": account_id,
        "reconstructed_at": as_of.isoformat(),
        "state": state,
        "event_count": len(events),
    }
```

**Storage tiering for 7-year retention:**
- Days 0–7: Kafka (hot, immediate replay)
- Days 7–90: S3 Standard (queryable via Athena)
- Days 90–365: S3 Standard-IA (infrequent access, cheaper)
- Year 1–7: S3 Glacier Instant Retrieval (regulatory archive, 99% cheaper than Standard)
- S3 Object Lock COMPLIANCE mode: cannot be deleted even by account root during retention period

---

### Q9: How do you build a self-service event catalog for 100+ microservices, and what makes producers treat their events as a first-class product?

**The problem:** At 100 services, no one knows what events exist, what they contain, who produces them, or whether they're safe to consume. Events become undiscovered coupling — services are consumed in ways the producer never intended.

**Event catalog requirements:**
1. **Discovery:** "Does an event exist for X?" — searchable by domain, event type, field
2. **Schema:** What does the event contain? Current + historical versions
3. **Ownership:** Who owns this event? Who to contact when it breaks?
4. **Consumers:** Who depends on this event? (helps producers assess blast radius of changes)
5. **SLA:** What delivery guarantees does the producer offer?

**Implementation: Schema Registry + internal portal:**
```yaml
# event-catalog/events/order-placed.yaml
# Checked into git, owned by order-team
event_type: OrderPlaced
version: "2.1"
domain: orders
owner_team: order-platform
owner_slack: "#order-platform"
bus: kafka
topic: order-events
partition_key: order_id
retention: 7d
delivery_guarantee: at-least-once

description: |
  Published when a customer successfully places an order.
  Consumer note: process idempotently — may receive duplicates.

schema:
  $ref: "./schemas/order-placed-v2.avsc"

sla:
  publish_latency_p99: 100ms
  availability: 99.9%

consumers:
  - team: shipping-platform
    service: fulfillment-service
    contact: "#shipping-eng"
  - team: analytics
    service: revenue-pipeline
    contact: "#data-eng"

changelog:
  - version: "2.1"
    date: "2025-02-01"
    change: "Added `customer_tier` field (optional, defaults to 'standard')"
    backward_compatible: true
  - version: "2.0"
    date: "2024-11-01"
    change: "Changed `total` from string to float"
    backward_compatible: false
    migration_guide: "consumers/order-placed-v2-migration.md"
```

**Making producers treat events as products:**
1. **Consumer SLA → producer responsibility:** If consumers depend on OrderPlaced p99 latency < 500ms, that becomes the producer's SLA. Monitored, alerted, included in on-call runbook.
2. **Deprecation process:** Producers must give consumers 90-day notice before breaking changes. Cannot delete a topic while registered consumers exist.
3. **Schema contract testing:** Consumers write contract tests (PactFlow or custom) that run against producer staging. Producer CI fails if a schema change breaks any registered consumer contract.
4. **Event catalog completeness as a platform metric:** Teams are measured on keeping their catalog entries current. Stale entries or undocumented events fail platform health checks.
