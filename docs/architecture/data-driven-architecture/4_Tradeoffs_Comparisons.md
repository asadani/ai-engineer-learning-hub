# Tradeoffs & Comparisons

## Lambda vs Kappa Architecture

| Dimension | Lambda | Kappa |
|-----------|--------|-------|
| **Processing paths** | Two: batch (correctness) + speed (latency) | One: streaming only |
| **Correctness** | High — batch layer eventually corrects | High — but requires log replay for corrections |
| **Latency** | Low (speed layer), high for batch corrections | Low for all data |
| **Complexity** | High — two codebases must produce identical results | Lower — one codebase |
| **Reprocessing** | Trivial — just re-run batch layer | Requires Kafka long retention + replay |
| **Late data handling** | Batch layer handles it naturally | Requires watermarks and allowed lateness |
| **Technology** | Kafka + Flink (speed) + Spark (batch) | Kafka + Flink only |
| **When to use** | Legacy batch workloads exist; team split on paradigms | Greenfield; streaming-first org; homogeneous tools |

**The Lambda complexity trap:** The theoretical elegance of Lambda breaks down operationally. Two separate codebases (one Spark SQL, one Flink) for the same business logic diverge over time. When batch disagrees with streaming, debugging is hard. Most teams that implement Lambda eventually migrate to Kappa.

**The Kappa replay problem:** Kappa requires replaying the full event log for backfills or corrections. If you have 5 years of order history and Kafka's retention is 7 days, you have an S3 cold storage replay problem. Solution: cold-path replay from S3 (as a finite Kafka stream), or hybrid: Kafka for hot data + S3 for replay.

---

## Data Warehouse vs Data Lake vs Data Lakehouse

| Dimension | Data Warehouse | Data Lake | Data Lakehouse |
|-----------|---------------|-----------|---------------|
| **Storage** | Proprietary (Redshift blocks) | S3 / GCS (Parquet, JSON, anything) | S3 + open table format (Delta/Iceberg) |
| **Cost** | High (compute + storage bundled) | Low (S3 is cheap) | Medium (compute separate from storage) |
| **Schema** | Schema-on-write (strict) | Schema-on-read (flexible) | Schema-on-write + schema evolution |
| **ACID** | Yes | No | Yes (Delta/Iceberg) |
| **Query performance** | High (MPP, columnar) | Variable (Athena + file size matters) | High (OPTIMIZE + file compaction) |
| **ML/Data Science** | Poor (hard to extract large datasets) | Excellent (direct file access) | Excellent (same) |
| **Governance** | Strong (column-level security) | Weak (file-level only) | Strong (table-level + row-level with Unity Catalog) |
| **Examples** | Redshift, Snowflake, BigQuery | S3 + Athena | Delta Lake, Apache Iceberg + Athena/Trino |
| **Use when** | BI/reporting, SQL-only consumers, strong governance needed | Raw data storage, ML, diverse formats | Best of both: ACID + cheap storage + multi-engine |

**The 2025 recommendation:** For most new architectures, the data lakehouse pattern (S3 + Delta Lake/Iceberg + Trino/Athena) offers the best ROI. A dedicated data warehouse (Redshift/Snowflake) makes sense when you have heavy concurrent BI workloads requiring WLM (workload management) or when compliance requires a fully governed RDBMS-like system.

---

## Event-Driven vs Request-Driven Architecture

| Dimension | Request-Driven (REST/gRPC) | Event-Driven (Kafka/Kinesis) |
|-----------|--------------------------|------------------------------|
| **Coupling** | Tight (producer knows consumer) | Loose (producer knows topic, not consumer) |
| **Availability** | Consumer must be up for transaction | Producer continues even if consumer is down |
| **Latency** | Low (synchronous response) | Higher (async delivery + processing) |
| **Transactions** | Easy (HTTP 200 = success) | Hard (at-least-once + idempotent consumer) |
| **Fan-out** | Hard (producer must call N consumers) | Easy (N consumers subscribe to same topic) |
| **Reprocessing** | Impossible (request is gone) | Easy (replay from offset) |
| **Debugging** | Easy (request-response trace) | Harder (trace across multiple consumers) |
| **Use when** | User waits for response, low fan-out | Async workflows, high fan-out, audit trail needed |

**The hybrid pattern (most production systems use this):**
- Synchronous API for: user-facing responses, payment processing, anything requiring immediate confirmation
- Async events for: notifications, downstream analytics, cache invalidation, audit logs, ML feature computation

---

## Batch vs Streaming: Choosing the Right Tool

| Factor | Batch | Streaming |
|--------|-------|-----------|
| **Acceptable latency** | Hours to days | Seconds to minutes |
| **Data volume** | Any | Best < 10 GB/s sustained without specialized infra |
| **Computation complexity** | Any (full sort, global joins) | Limited (state must fit in memory or RocksDB) |
| **Correctness requirements** | High (re-run on failures) | Harder (exactly-once is complex) |
| **Team skills** | SQL / Spark | Flink / streaming SQL |
| **Late data** | Natural — include it in next batch | Requires watermarks, out-of-order handling |
| **Cost** | Lower (run once per period) | Higher (always-on infrastructure) |

**Decision heuristic:**
- If your stakeholders say "last night's data is fine" → batch
- If they say "within the hour" → micro-batch (Spark Structured Streaming, 1-5 min windows)
- If they say "within seconds" → true streaming (Flink, Kinesis Analytics)
- If they say "real-time" but actually mean "within 1 hour" → micro-batch is sufficient and much cheaper

---

## Data Mesh vs Centralized Data Engineering

| Dimension | Centralized (Data Team) | Data Mesh |
|-----------|------------------------|-----------|
| **Data ownership** | Central team | Domain teams |
| **Pipeline ownership** | Central team builds all pipelines | Domain teams build and own their data products |
| **Quality accountability** | Central team | Domain team (they produce it, they own it) |
| **Bottleneck** | Central team is the bottleneck at scale | Decentralized, scales with org |
| **Standards** | Easy to enforce (one team) | Hard (requires platform + governance layer) |
| **Discovery** | Easy (one catalog) | Requires federated catalog + data product standards |
| **When it works** | < 10 teams, < 20 data products | > 20 teams, rapid domain growth |
| **Organizational maturity needed** | Low | High (domains must be empowered, accountable) |

**The data mesh fallacy:** Many companies adopt data mesh terminology without the organizational change. Domain teams are told to own their data products but don't have the skills or time to operate data infrastructure. Result: distributed mess, not data mesh. Data mesh requires: domain teams with data engineering skills OR a very good self-service platform that abstracts complexity.

---

## Storage Format Comparison

| Format | Encoding | Splittable | Schema | Compression | Use When |
|--------|---------|-----------|--------|-------------|---------|
| **CSV** | Row, text | Yes (by newline) | No | Poor | Interchange, small data, human-readable |
| **JSON** | Row, text | Yes | No | Poor | APIs, semi-structured |
| **Avro** | Row, binary | Yes (with block marker) | Yes (embedded) | Good | Kafka messages, schema evolution, row-level access |
| **Parquet** | Column, binary | Yes | Yes | Excellent | Analytics, OLAP, Spark/Athena |
| **ORC** | Column, binary | Yes | Yes | Excellent | Hive-heavy environments |
| **Delta Lake** | Parquet + transaction log | Yes | Yes | Excellent | ACID on S3, upserts, time travel |
| **Iceberg** | Parquet/ORC + manifest | Yes | Yes | Excellent | Multi-engine, hidden partitioning |

**Rule of thumb:** Avro for messages in flight (Kafka). Parquet for analytical storage (S3, Redshift Spectrum). Delta Lake/Iceberg when you need ACID on S3.

---

## Exactly-Once Semantics: The Tradeoff Spectrum

| Guarantee | How | Overhead | Suitable For |
|-----------|-----|---------|-------------|
| **At-most-once** | Fire and forget | None | Metrics, telemetry (loss acceptable) |
| **At-least-once** | Ack after processing, retry on failure | Low | Most use cases with idempotent consumers |
| **Effectively exactly-once** | At-least-once + idempotent consumer | Low-medium | Preferred in practice |
| **Exactly-once (transactional)** | Kafka transactions + transactional producer | High | Financial transactions, double-counted revenue |

**At-least-once + idempotent = "effectively exactly-once" in practice:**
```python
# Idempotent consumer: safe to process same message twice
def process_order_event(event: dict):
    order_id = event["order_id"]
    event_id = event["event_id"]

    # Check if already processed (using event_id as idempotency key)
    existing = dynamodb.get_item(
        TableName="processed_events",
        Key={"event_id": {"S": event_id}},
    )
    if existing.get("Item"):
        return  # already processed, skip

    # Process the event
    update_order_status(order_id, event["status"])

    # Mark as processed (conditional write for race condition safety)
    dynamodb.put_item(
        TableName="processed_events",
        Item={"event_id": {"S": event_id}, "processed_at": {"S": datetime.utcnow().isoformat()}},
        ConditionExpression="attribute_not_exists(event_id)",
    )
```

---

## Kinesis vs MSK (Kafka) Decision Matrix

| Factor | Choose Kinesis | Choose MSK/Kafka |
|--------|--------------|-----------------|
| AWS-only ecosystem | ✅ Native IAM, Lambda, Firehose integration | ⚠️ Works but extra config |
| < 1 MB/s per shard throughput | ✅ Simple, managed | ⚠️ Over-engineered |
| > 10 MB/s sustained | ⚠️ Expensive (shards cost ~$11/mo each) | ✅ More cost-effective |
| Multi-cloud | ❌ AWS-only | ✅ |
| Long retention (> 7 days) | ✅ Extended retention option | ✅ Configurable |
| Consumer group flexibility | ❌ (shard-based, not group-based) | ✅ Consumer groups |
| Schema registry | ❌ (must add manually via Glue SR) | ✅ Confluent Schema Registry |
| Replay from beginning | ✅ (7 days standard, up to 365 days) | ✅ (configurable retention) |
| Operational complexity | Low | Medium |
