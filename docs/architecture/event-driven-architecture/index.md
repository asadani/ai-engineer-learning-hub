# Event-Driven Architecture

Principal-level interview prep notes on event-driven systems, messaging patterns, sagas, choreography vs orchestration, AWS messaging services, and production observability for event-driven microservices.

---

## Contents

| # | File | Words | Focus |
|---|------|-------|-------|
| 1 | [High Level Overview](1_High_Level_Overview.md) | ~950 | Events vs commands vs queries, three EDA patterns, topology diagram, why/why not EDA, EDA vs REST, vocabulary |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | ~2,100 | Outbox pattern, idempotent consumers (DynamoDB), choreography saga, orchestration saga (Step Functions), EventBridge, DLQ, circuit breaker, Temporal.io, event storming |
| 3 | [Products & Tools](3_Products_Tools.md) | ~1,450 | SQS (standard vs FIFO), SNS fan-out, EventBridge (rules, Pipes, Scheduler), Kinesis, Kafka/MSK, RabbitMQ, Temporal vs Step Functions comparison |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | ~1,600 | Choreography vs orchestration, EventBridge vs SNS vs SQS vs Kafka, at-least-once vs exactly-once, event notification vs state transfer, saga vs 2PC, push vs pull |
| 5 | [Use Cases](5_Use_Cases.md) | ~1,700 | Order saga (Temporal orchestration + choreography side effects), profile fan-out (SNS → SQS), async video transcoding (heartbeat pattern), real-time notifications (frequency cap, quiet hours), event tap ingestion (Kafka Connect) |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | ~1,300 | Consumer lag measurement, end-to-end latency tracing, saga completion rates, DLQ health evaluation, idempotency violation detection, EventBridge delivery metrics |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | ~1,500 | Metrics tables (consumer health/delivery latency/saga/idempotency/infrastructure), CloudWatch instrumentation code, alerting YAML |
| 8 | [Interview Questions](8_Interview_Questions.md) | ~3,600 | 9 tiered Q&As: L5 (idempotency implementation, outbox pattern, choreography vs orchestration), L6 (schema strategy for 50 teams, consumer lag diagnosis, monolith migration), L7+ (eventual consistency for finance stakeholders, 7-year audit system, event catalog) |

**Total: ~14,200 words**

---

## Key Themes

### 1. Idempotency Is Not Optional

At-least-once delivery is the default guarantee of every major message broker. This means your consumers will see duplicates. Idempotency is not a nice-to-have — it's the foundational correctness requirement. The DynamoDB conditional write pattern (`attribute_not_exists(pk)`) is the most portable implementation; PostgreSQL unique constraints work within a single DB; natural idempotency (operations that are safe to repeat) is always preferred when achievable.

### 2. Orchestrate the Critical Path, Choreograph the Side Effects

The choreography vs orchestration debate is a false choice. Mature systems use both. The rule: orchestrate workflows that require compensation (anything involving money, inventory, or irreversible actions). Choreograph side effects (analytics, notifications, audit trails) where each consumer fails and retries independently without affecting the others.

### 3. The Outbox Pattern Is the Correct Way to Write + Publish

Any pattern that writes to a database and then publishes to a message broker in separate, non-atomic operations is wrong. The write can succeed and the publish can fail. The outbox pattern (atomic DB + outbox write in one transaction; separate publisher reads and publishes) is the production-correct approach. Debezium-based CDC on the outbox table gives you near-zero latency; polling publisher is simpler to operate.

### 4. Consumer Lag Is the Primary Health Signal

In a synchronous system, latency is the health signal. In an event-driven system, consumer lag is. Lag = 0: healthy. Lag growing monotonically: consumer is stuck. Lag stable at N: consumer under-provisioned. DLQ depth > 0: events are failing. These signals replace the request-response metrics you'd use elsewhere and need explicit instrumentation.

### 5. Events as Products, Not Implementation Details

At scale (50+ services), unmanaged event schemas are a liability. Teams change their events without knowing who depends on them. The solution: schema registry + compatibility enforcement + event catalog with ownership metadata. Events are an API surface. They need the same backward-compatibility discipline as REST APIs, with the same organizational processes (deprecation notices, versioned topics, contract tests).

---

## Pattern Selection Quick Reference

| Pattern | Use When | Avoid When |
|---------|----------|-----------|
| **Choreography** | Simple linear workflows, additive fan-out, teams want full autonomy | Complex branching, compensation needed, need single execution view |
| **Orchestration** | Multi-step sagas with compensation, regulatory audit, complex branching | Simple notifications, adding new consumers frequently |
| **Outbox pattern** | Any time you write to DB and need to publish an event | Never skip this — naive write-then-publish is always wrong |
| **Event notification** | Consumers need current state, privacy concerns in events | Consumer SLA can't tolerate additional round-trip to producer |
| **Event-carried state** | Full consumer decoupling, producer is a bottleneck | Large payloads with PII, schema changes affect many consumers |
| **Saga (choreography)** | Simple sequential steps, team autonomy critical | Compensation logic, complex business rules, audit requirements |
| **Saga (orchestration)** | Financial transactions, multi-service atomic operations | Adding new saga participants frequently |
| **DLQ** | Always — any SQS queue or Kafka consumer | Never omit a DLQ |
| **Circuit breaker** | Downstream service has reliability issues | Low-volume, non-critical paths |

---

## AWS Messaging Services Quick Reference

| Service | Model | Ordering | Replay | Max Size | When to Use |
|---------|-------|---------|--------|----------|-------------|
| **SQS Standard** | Queue (one consumer) | Best-effort | No | 256 KB | Async work queue, buffer, decoupling |
| **SQS FIFO** | Queue (one consumer) | Strict | No | 256 KB | Financial transactions, ordered processing |
| **SNS** | Pub-sub (broadcast) | No | No | 256 KB | Fan-out to multiple consumers |
| **EventBridge** | Event bus (content routing) | No | Archive only | 256 KB | AWS service integration, complex routing rules |
| **Kinesis** | Stream (N consumers) | Per-shard | 7–365 days | 1 MB | Ordered streaming, replay, multi-consumer |
| **MSK (Kafka)** | Stream (N consumer groups) | Per-partition | Configurable | 1 MB+ | High throughput, Kafka ecosystem, long retention |
| **Step Functions Standard** | Workflow orchestration | N/A | N/A | 256 KB | Business workflows, AWS service orchestration |
| **Temporal** | Workflow orchestration | N/A | N/A | N/A | Complex business logic, developer-owned workflows |

---

## Critical Interview Distinctions

**At-least-once vs exactly-once:** At-least-once = broker guarantees delivery, may duplicate. Exactly-once = Kafka transactions or idempotent consumer. For most workloads: at-least-once + idempotent consumer = effectively exactly-once at lower cost than true exactly-once.

**Choreography vs orchestration:** Not a technology choice — an architectural philosophy. Choreography = implicit distributed process. Orchestration = explicit centralized process. Use both in the same system for different responsibilities.

**Event time vs processing time:** Event time = when the business event occurred (embedded in payload). Processing time = when the consumer received the message. For any analytics or auditing, always use event time. Processing-time reasoning breaks during lag/reprocessing.

**Topic vs queue:** Topic (Kafka/Kinesis/SNS): N consumer groups each see every message. Queue (SQS): competing consumers — each message delivered to exactly one consumer. Confusing SNS fan-out behavior (N queues, one message each) with true pub-sub is a common mistake.

**Saga compensation vs rollback:** Database rollback is atomic and synchronous. Saga compensation is a business-level undo: publish a new event, call a refund API, update a status. It can fail. It can take time. The business must define what "acceptable" looks like when compensation also fails.

**Push vs pull delivery:** SQS and Kafka are pull (consumer polls). SNS and EventBridge are push (broker delivers). Lambda-triggered SQS is logically push from the function's perspective but pull under the hood. The distinction matters for backpressure: pull consumers naturally throttle themselves; push consumers must handle any rate the broker delivers.


---

!!! info "Official Sources & Further Reading"

    - [Martin Fowler — What do you mean by Event-Driven?](https://martinfowler.com/articles/201701-event-driven.html)
    - [AWS — Event-driven architecture](https://aws.amazon.com/event-driven-architecture/)
    - [microservices.io — Saga pattern](https://microservices.io/patterns/data/saga.html)
    - [Confluent — Event-driven architecture](https://www.confluent.io/learn/event-driven-architecture/)


!!! tip "Related Topics"

    - [Data-Driven Architecture](../data-driven-architecture/)
    - [Agentic Design Patterns](../../agents-orchestration/agentic-design-patterns/)
