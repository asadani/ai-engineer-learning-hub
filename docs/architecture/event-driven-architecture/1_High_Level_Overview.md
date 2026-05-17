# Event-Driven Architecture

## What It Is

Event-driven architecture (EDA) is a software design pattern where components communicate by producing and consuming events rather than making direct synchronous calls. The producer doesn't know — or care — who consumes the event. The consumer doesn't know — or care — who produced it. They're coupled only through the event schema and the message broker that carries it.

This is categorically different from the data-driven architecture topic (which covers analytical pipelines, lakehouses, CDC). EDA is about how **services talk to each other** in a distributed system.

---

## Events vs Commands vs Queries

These three message types are often conflated. They have fundamentally different semantics:

| Type | Direction | Semantics | Naming convention | Example |
|------|-----------|-----------|------------------|---------|
| **Event** | Broadcast to anyone | "Something happened." Fire and forget. Producer has no expectation of response. | Past tense noun: `OrderPlaced`, `PaymentFailed` | `OrderPlaced { order_id, customer_id, total }` |
| **Command** | Directed at one receiver | "Do this thing." Producer expects the receiver to act. May expect a response. | Imperative verb: `PlaceOrder`, `ProcessPayment` | `ProcessPayment { order_id, amount, card_token }` |
| **Query** | Request-response | "Tell me X." Synchronous by nature. | Question or `Get*`: `GetOrderStatus` | `GetOrderStatus { order_id }` → `{ status: "shipped" }` |

**Why the distinction matters:** Events are the building blocks of EDA. Commands are appropriate for targeted work that must execute exactly once. Mixing them in a single message bus leads to design confusion — an event consumer assuming it's the only receiver of what is actually a command.

---

## The Core EDA Topology

```
                        ┌─────────────┐
                        │  Producer   │
                        │  (Service A)│
                        └──────┬──────┘
                               │ publishes event
                               ▼
                        ┌─────────────┐
                        │   Message   │
                        │   Broker    │
                        │ (Kafka/SQS/ │
                        │ EventBridge)│
                        └──────┬──────┘
                               │ delivers to subscribers
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        ┌────────────┐  ┌────────────┐  ┌────────────┐
        │ Consumer A │  │ Consumer B │  │ Consumer C │
        │ (Shipping) │  │ (Inventory)│  │ (Analytics)│
        └────────────┘  └────────────┘  └────────────┘
```

The producer is unaware of Consumer A, B, or C. New consumers can be added without changing the producer. This is the central promise of EDA: **temporal and spatial decoupling**.

---

## Three EDA Patterns

### 1. Event Notification
The event carries minimal data — just enough to signal that something happened. Consumers fetch the full state themselves.

```json
// Event notification: "go look it up"
{ "type": "OrderPlaced", "order_id": "ORD-123", "occurred_at": "2025-03-22T10:00:00Z" }
// Consumer calls Order Service GET /orders/ORD-123 to get details
```

**Pro:** Events are small, producers don't expose sensitive data
**Con:** Consumers must make additional calls; producer must be available at consumption time

### 2. Event-Carried State Transfer
The event carries all the data the consumer needs — no callback to the producer required.

```json
// Event-carried state transfer: "here's everything you need"
{
  "type": "OrderPlaced",
  "order_id": "ORD-123",
  "customer_id": "CUST-456",
  "items": [{"sku": "ABC", "qty": 2, "price": 29.99}],
  "shipping_address": { "street": "123 Main St", "city": "NYC", "zip": "10001" },
  "total_amount": 59.98,
  "occurred_at": "2025-03-22T10:00:00Z"
}
// Consumer doesn't need to call anyone
```

**Pro:** Full decoupling — consumer works even if producer is down
**Con:** Events are large; schema changes in the state ripple to all consumers; potential PII/sensitivity in the event payload

### 3. Event Sourcing (as EDA)
Events are the system of record. State is a derived projection. Covered in depth in Data-Driven Architecture — the key point here is that event sourcing + EDA naturally compose.

---

## Why EDA?

**Decoupling:** Services don't know about each other. You can add, remove, or replace consumers without touching the producer. This is critical for large orgs where teams own independent services.

**Resilience:** If a consumer is down, events queue up. When it recovers, it processes the backlog. With synchronous REST calls, a downstream failure propagates upstream instantly.

**Scalability:** Event consumers scale independently. Add Shipping service replicas without touching Payment service.

**Auditability:** The event log is a complete history of what happened. Invaluable for debugging, compliance, and replay.

**Fan-out:** One event, N consumers. Adding analytics, notifications, or ML feature pipelines to an existing flow requires no changes to the producer.

---

## Why NOT EDA (The Costs)

**Debugging complexity:** A synchronous HTTP call has a clear request/response trace. An event flows through broker → consumer A → consumer B → dead letter queue. Distributed tracing is essential but adds operational overhead.

**Eventual consistency:** After an event is published, consumers process it asynchronously. There's a window where the system is in an inconsistent state. Applications must handle this gracefully (optimistic UI updates, consistency windows in SLAs).

**At-least-once delivery is the default:** Most message brokers guarantee delivery but may deliver duplicates. Consumers must be idempotent. This is non-trivial for side-effecting operations.

**Operational complexity:** Message brokers, dead letter queues, consumer lag monitoring, schema registries — EDA adds infrastructure you must operate.

**Testing difficulty:** Testing an event-driven flow end-to-end requires either a full broker environment or sophisticated mocking.

---

## EDA vs REST/RPC

| Dimension | REST/gRPC (synchronous) | EDA (asynchronous) |
|-----------|------------------------|-------------------|
| **Coupling** | Tight (caller knows callee URL/contract) | Loose (coupled only through event schema) |
| **Response** | Immediate (caller waits) | None (fire and forget) |
| **Failure propagation** | Upstream caller fails if downstream fails | Downstream failure doesn't affect producer |
| **Fan-out** | Hard (caller must call N services) | Easy (N consumers subscribe) |
| **Tracing** | Easy (request-response trace) | Hard (distributed trace across broker + consumers) |
| **Transactions** | Easy with synchronous patterns | Hard (sagas required) |
| **When to use** | User waits for response, need immediate confirmation | Async workflows, fan-out, audit, resilience |

**The hybrid system (most production systems):** Synchronous REST/gRPC for user-facing responses and read queries. Events for background work, notifications, data propagation, and inter-service workflows.

---

## Key Vocabulary

| Term | Definition |
|------|-----------|
| **Event** | Immutable record of something that happened in the past |
| **Message broker** | Infrastructure that routes events from producers to consumers |
| **Topic / Queue** | Topic: pub-sub (multiple consumers see every message). Queue: work queue (one consumer per message). |
| **Dead Letter Queue (DLQ)** | Destination for messages that couldn't be processed after N retries |
| **Idempotency** | Processing the same event N times produces the same result as processing it once |
| **Saga** | Pattern for managing distributed transactions across multiple services via events |
| **Choreography** | Services react to each other's events with no central coordinator |
| **Orchestration** | A central coordinator (workflow engine) tells services what to do |
| **Outbox pattern** | Atomically write to DB and event table in the same transaction; separate process publishes events |
| **Consumer group** | Multiple instances of the same consumer sharing the processing load |
| **Backpressure** | Mechanism for a consumer to signal it's overwhelmed and slow down producers |
| **Event schema** | Contract defining the structure of an event (Avro, JSON Schema, Protobuf) |
| **Competing consumers** | Multiple consumer instances reading from the same queue for horizontal scaling |
