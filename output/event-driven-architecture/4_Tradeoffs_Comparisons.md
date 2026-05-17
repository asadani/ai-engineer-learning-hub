# Tradeoffs & Comparisons

## Choreography vs Orchestration

The central architectural decision in event-driven distributed transactions.

### Choreography

Services react to each other's events. No central coordinator. Each service knows what to do when it sees a specific event.

```
OrderPlaced → PaymentService processes → PaymentProcessed
PaymentProcessed → InventoryService reserves → InventoryReserved
InventoryReserved → ShippingService creates → ShipmentCreated
```

**Strengths:**
- True decoupling — services don't know about each other, only about events
- Easy to add new participants without changing existing services
- Natural fit for simple, linear workflows
- Each service is independently deployable and testable

**Weaknesses:**
- **Implicit business process** — the workflow is emergent, not explicit. To understand the full flow, you must read all the services.
- **Distributed debugging** — "where is my order?" requires checking 4 different services' logs
- **Compensation complexity** — if ShipmentCreated fails, who knows to refund the payment? Every service must handle compensation events, leading to complex error topologies
- **Cycle risk** — event A triggers B which triggers A (infinite loop). Requires careful event naming discipline.

### Orchestration

A central coordinator (workflow engine) explicitly directs each step. Services expose action endpoints/activities; the orchestrator decides what runs when.

```
OrderOrchestrator:
    → call PaymentService.processPayment()
    → if success: call InventoryService.reserveInventory()
    → if success: call ShippingService.createShipment()
    → if any fail: call CompensationService.refund()
```

**Strengths:**
- **Explicit business process** — the workflow is a single readable artifact (Step Functions ASL, Temporal workflow code)
- **Centralized observability** — one execution history showing every step, duration, and failure
- **Simple compensation** — the orchestrator knows what succeeded and calls compensating actions in reverse order
- **Easier to change** — modify the workflow in one place; services just need to expose their actions

**Weaknesses:**
- **Orchestrator coupling** — the orchestrator must know about all participants. Adding a new step requires changing the orchestrator.
- **Single point of operational complexity** — the orchestrator is a critical service that must be highly available
- **Potentially weaker decoupling** — if the orchestrator calls services directly (not via events), services become dependent on the orchestrator's availability

### The Hybrid (Production Reality)

Most mature systems use both:

```
OrderService (Orchestrator via Temporal/Step Functions)
    → PaymentService (publishes PaymentProcessed event for other consumers)
    → InventoryService (publishes InventoryReserved for warehouse systems)
    → ShippingService (publishes ShipmentCreated for customer notifications)

Customer notifications, analytics, audit logs → subscribe to events (choreography)
The core transaction → orchestrated
```

**Rule of thumb:** Orchestrate the critical path (the thing that must succeed or roll back atomically). Choreograph the side effects (analytics, notifications, audit).

---

## EventBridge vs SNS vs SQS vs Kafka

| Dimension | SQS | SNS | EventBridge | Kafka/MSK |
|-----------|-----|-----|-------------|-----------|
| **Model** | Queue (one consumer per message) | Topic (fan-out broadcast) | Event bus (content routing) | Log (N consumer groups, replay) |
| **Message routing** | None (single queue) | Topic subscription | Content-based rules (JSON path) | Consumer group offset |
| **Ordering** | FIFO queues (per message group) | None | None | Per-partition |
| **Replay** | No (deleted after consume) | No | Limited (archive + replay) | Yes (7 days default, up to 365) |
| **Retention** | Up to 14 days | None | None (archive optional) | Configurable (unlimited with S3) |
| **Max message** | 256 KB | 256 KB | 256 KB | 1 MB (default, configurable) |
| **Throughput** | Near-unlimited | Near-unlimited | 10k/s soft limit | Multi-GB/s |
| **Consumer independence** | One consumer per message | All subscribers get copy | All matching targets | Independent consumer groups |
| **Schema enforcement** | No | No | Optional (schema registry) | Yes (Confluent/AWS Schema Registry) |
| **Operational complexity** | Low | Low | Low | High (brokers, ZK/KRaft, replication) |
| **Cost model** | Per-request + data | Per-request + data | Per-event + invocation | Instance-based (MSK) |
| **Use when** | Async work queue, buffer | Fan-out notification | AWS service integration, complex routing | High-throughput, replay, Kafka ecosystem |

**Decision tree:**
```
Need replay of past events?
    YES → Kafka (MSK or self-managed)
    NO → continue

Need complex content-based routing (JSON path matching)?
    YES → EventBridge
    NO → continue

Need fan-out (one event → multiple independent consumers)?
    YES → SNS → SQS (with per-consumer queue)
    NO → SQS (single consumer)
```

---

## At-Least-Once vs Exactly-Once

### At-Least-Once (Most Systems)

The broker guarantees every message is delivered, but may deliver it multiple times (network timeout → producer retries → duplicate delivery).

```
Producer sends → Broker acknowledges → Producer may not receive ACK
→ Producer retries → Broker delivers again → Duplicate
```

**Making at-least-once safe:** Idempotent consumers. If processing the same event twice produces the same result, at-least-once == effectively exactly-once.

```python
# Idempotent consumer pattern
def handle_payment(event: dict):
    event_id = event["event_id"]

    # Check if already processed (DynamoDB conditional write)
    try:
        table.put_item(
            Item={"pk": event_id, "processed_at": datetime.now().isoformat()},
            ConditionExpression="attribute_not_exists(pk)",
        )
    except ConditionalCheckFailedException:
        return  # Already processed, skip

    # Safe to process — this is the first time
    process_payment(event)
```

**Not idempotent by nature (requires careful design):**
- Sending emails / push notifications (send twice → duplicate notification)
- Financial debits (charge twice → customer complaint)
- Inventory decrement (decrement twice → negative inventory)
- Outbox inserts (insert twice → duplicate records)

**Pattern for non-idempotent operations:**
1. Check idempotency key before acting
2. Act
3. Store idempotency key with TTL
4. Return (don't re-execute if key already exists)

### Exactly-Once (Kafka Transactions)

Kafka's producer transactions + consumer offset commits in a single atomic operation. Producer sets `transactional.id`, consumer sets `isolation.level=read_committed`.

```python
from confluent_kafka import Producer

producer = Producer({
    "bootstrap.servers": "broker:9092",
    "transactional.id": "order-processor-1",
    "enable.idempotence": True,
})

producer.init_transactions()

try:
    producer.begin_transaction()
    producer.produce("processed-orders", key=order_id, value=result)
    producer.send_offsets_to_transaction(
        offsets, consumer_group_metadata  # atomic: consume + produce in one tx
    )
    producer.commit_transaction()
except Exception:
    producer.abort_transaction()
```

**Cost:** ~20-30% throughput reduction vs at-least-once. Adds latency. **Rarely necessary** — at-least-once + idempotent consumer achieves the same safety at lower cost for most workloads. Use Kafka transactions when: you're transforming events from one topic to another and cannot tolerate duplicate outputs even with idempotent design.

---

## Event Notification vs Event-Carried State Transfer

| Dimension | Event Notification | Event-Carried State Transfer |
|-----------|-------------------|------------------------------|
| **Payload** | Minimal (just the ID) | Full state snapshot |
| **Consumer coupling** | Must call producer to get data | Fully decoupled |
| **Event size** | Small (< 1 KB) | Large (1 KB – 1 MB) |
| **Producer availability** | Consumer fails if producer is down | Consumer works independently |
| **Data freshness** | Always fresh (consumer fetches current state) | Snapshot at event time (could be stale if consumer delays) |
| **Schema coupling** | Loose (consumer defines what to fetch) | Tight (schema changes ripple to all consumers) |
| **PII/sensitivity risk** | Low (producer controls what's exposed) | High (all data in the event) |
| **Network overhead** | High (N consumers × M events = N*M fetches) | Low (one write, N reads from broker) |
| **Debugging** | Harder (what state was it at event time?) | Easier (state is in the event) |

**Production guidance:**
- Start with event notification for simplicity
- Move to event-carried state when consumer-to-producer call latency hurts SLAs, or producer becomes a fan-out bottleneck
- Always redact PII before putting state in events (or encrypt field-level)
- Never put secrets (API keys, tokens) in events

---

## Saga vs 2PC (Two-Phase Commit)

### 2PC (What We Don't Do in EDA)

```
Coordinator → PREPARE to all participants
All participants lock resources, respond READY
Coordinator → COMMIT (or ROLLBACK)
All participants release locks
```

**Why 2PC fails at scale:**
- Requires synchronous coordination across all services — O(N) latency
- Blocking locks held during coordinator communication — availability collapses if coordinator fails mid-commit
- Doesn't cross organizational boundaries (can't 2PC between your DB and Stripe's DB)
- Works great within a single database (Postgres SERIALIZABLE) — never at service boundaries

### Saga Pattern

```
T1 → T2 → T3 (all succeed) ✓
T1 → T2 → T3 fails → C3 → C2 → C1 (compensating transactions)
```

Each step is a local transaction. On failure, compensating transactions undo completed steps. **No locks held between steps** — other operations can proceed concurrently.

**The consistency gap:** Between step T1 succeeding and C1 executing, the system is in an inconsistent state. Other reads may see partial results. Solutions:
- **Semantic lock:** Set an `AWAITING_CONFIRMATION` flag on records while saga is in progress. Other code treats flagged records differently.
- **Optimistic UI:** Show "processing" states to users during the consistency window.
- **Careful ordering:** Put the most likely-to-fail steps first (payment before inventory, since payment fails more often).

---

## Push vs Pull Consumer Models

### Push (EventBridge, SNS, Kinesis → Lambda trigger)

Broker delivers events to consumer. Consumer doesn't poll.

- **Pro:** Low latency (event delivered immediately), simpler consumer code
- **Con:** Consumer must handle any throughput the broker sends; no built-in backpressure; consumer must scale fast enough or throttle will cause retries

### Pull (SQS, Kafka consumer, Kinesis KCL)

Consumer polls for events on its own schedule.

- **Pro:** Natural backpressure — consumer only takes what it can handle; consumer controls its own scaling
- **Con:** Polling introduces latency (long polling reduces this); idle consumers waste resources polling empty queues

**Production pattern:** Use SQS with Lambda trigger (managed push) — AWS Lambda pulls from SQS and delivers batches to your function. The Lambda service handles the polling loop, concurrency scaling, and backpressure automatically. You get push semantics (no polling code) with pull safety (Lambda controls its polling rate).

---

## When NOT to Use EDA

**Use synchronous REST/gRPC instead when:**

1. **User is waiting for the response.** Checkout → "Was my order placed?" requires an answer. You can still use events internally, but the user-facing API should be synchronous.

2. **You need strong consistency.** "Show me my current balance" must reflect the latest transaction. Async processing creates consistency windows that are confusing for financial reads.

3. **Simple CRUD with one consumer.** A single service reading its own data doesn't benefit from a broker. Direct database writes are simpler, faster, and cheaper.

4. **Low volume, simple operations.** Adding Kafka for 10 events/day is over-engineering. SQS or even a polling job may be more appropriate.

5. **You can't afford eventual consistency.** Some domains (medical, financial) require explicit acknowledgment before proceeding. Eventual consistency + compensation is a business decision, not just a technical one.
