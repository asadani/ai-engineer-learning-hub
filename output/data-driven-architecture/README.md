# Data-Driven Architecture

Principal-level interview prep notes on event-driven systems, streaming pipelines, data lakehouses, CDC, event sourcing, CQRS, data mesh, and the modern data stack.

---

## Contents

| # | File | Words | Focus |
|---|------|-------|-------|
| 1 | [High Level Overview](1_High_Level_Overview.md) | 1,163 | Lambda vs Kappa, event sourcing, CQRS, data mesh, OLTP vs OLAP, modern data stack, vocabulary |
| 2 | [Key Technical Concepts](2_Key_Technical_Concepts.md) | 1,975 | CDC (Debezium), event sourcing (DynamoDB event store), CQRS projections, Kafka (producer/consumer/schema registry), Flink stream processing, Medallion architecture (Bronze/Silver/Gold), data contracts, schema evolution |
| 3 | [Products & Tools](3_Products_Tools.md) | 1,350 | MSK/Kafka, Kinesis, Spark/Glue, Delta Lake/Iceberg, dbt, Glue Data Catalog/Athena, tool selection guide |
| 4 | [Tradeoffs & Comparisons](4_Tradeoffs_Comparisons.md) | 1,533 | Lambda vs Kappa, data warehouse vs lake vs lakehouse, event-driven vs request-driven, batch vs streaming, data mesh vs centralized, storage formats, exactly-once semantics, Kinesis vs MSK |
| 5 | [Use Cases](5_Use_Cases.md) | 1,506 | Real-time e-commerce analytics, event-sourced order management, data mesh platform, CDC-powered inventory, data contract enforcement |
| 6 | [Measurement & Evaluation](6_Measurement_Evaluation.md) | 1,108 | Freshness measurement, pipeline reliability, data quality evaluation, end-to-end latency tracing |
| 7 | [What to Measure & How](7_What_to_Measure_How.md) | 1,413 | Metrics tables (freshness/pipeline/quality/streaming/serving), CloudWatch instrumentation, alerting YAML |
| 8 | [Interview Questions](8_Interview_Questions.md) | 3,419 | 10 tiered Q&As (L5/L6/L7+) with model answers |

**Total: ~13,467 words**

---

## Key Themes

### 1. Architecture is Driven by Access Patterns
Before choosing any storage or processing technology, answer: what queries will consumers run? What latency do they need? What volume? The answers determine the architecture. A real-time dashboard and a monthly BI report have fundamentally different requirements — they need different storage (Redis vs Redshift) and different pipelines (Flink vs Glue), even if they consume the same source data.

### 2. The Event Log Is the Source of Truth
In mature data architectures, the immutable event log (Kafka topic or event store) is the authoritative record. Everything downstream — OLAP tables, read models, ML features, dashboards — is a derived view of that log. This enables replay, audit trails, and multiple projections from the same events.

### 3. Lambda vs Kappa: Modern Systems Choose Kappa
Lambda's dual-path complexity (separate batch and streaming codebases) is rarely justified with modern streaming tools. Flink and Spark Structured Streaming provide exactly-once semantics, event-time windowing, and stateful processing. New architectures should default to Kappa unless strong batch-only requirements exist.

### 4. Data Contracts Prevent Silent Breakage at Scale
Without formal contracts, data pipelines are implicit agreements embedded in code. At scale (50+ teams), unmanaged schema changes cause cascade failures across unknown consumers. Contracts + schema registry enforce backward compatibility technically; contract-as-code (YAML in git with code owners) enforces it organizationally.

### 5. The Small Files Problem is Invisible Until It's Critical
Streaming ingestion, high-cardinality partitioning, and MERGE operations all create file proliferation in data lakes. Query performance degrades silently by 2–5% per month. The fix: Delta OPTIMIZE + ZORDER, Firehose buffering, and monitoring median file size as a pipeline health metric.

---

## Architecture Pattern Quick Reference

| Pattern | Key Benefit | Key Cost | Use When |
|---------|------------|---------|---------|
| **Lambda** | Batch correctness + streaming freshness | Two codebases diverge | Legacy batch systems exist |
| **Kappa** | Single codebase, simpler mental model | Needs Kafka long retention for replay | Greenfield, streaming-first |
| **Event Sourcing** | Audit trail, time travel, replay | No direct queries, snapshot complexity | Regulatory, CQRS, audit-heavy domains |
| **CQRS** | Optimized read models per consumer | Eventual consistency, projection management | High read/write pattern divergence |
| **Medallion (Bronze→Silver→Gold)** | Progressive data quality, clear ownership | Three-layer latency overhead | Data lakes with multiple consumer types |
| **Data Mesh** | Scales with org, domain ownership | Requires platform + org maturity | > 20 teams, bottlenecked data team |
| **CDC** | Real-time data extraction without polling | Operational DB dependency, delete handling | DB → streaming, inventory sync, audit |

---

## AWS Services Reference

| Component | Service | Key Config |
|-----------|---------|-----------|
| Event streaming | **MSK** (Kafka) | `kafka.m5.2xlarge`, 3 AZs, TLS |
| Lightweight streaming | **Kinesis Data Streams** | 1 MB/s per shard, pay per shard-hour |
| S3 delivery | **Kinesis Firehose** | Buffer: 128MB / 15 min, Parquet conversion |
| Managed CDC | **DMS** (Database Migration Service) | CDC mode → Kinesis or MSK |
| Batch ETL | **AWS Glue** | G.1X DPUs, Delta Lake support |
| Serverless SQL | **Athena** | $5/TB scanned; use partitions + columnar |
| Data warehouse | **Redshift** | RA3 nodes (storage separate from compute), WLM |
| Managed Flink | **Kinesis Data Analytics** | Managed Apache Flink, auto-scaling |
| Data catalog | **Glue Data Catalog** | Crawlers, schema versioning, Athena integration |
| Stream processing | **Lambda** (< 15 min) | Kinesis/MSK trigger, max 10MB payload |

---

## Critical Interview Distinctions

**Data drift vs schema drift:** Data drift = the distribution of values in a field shifts (e.g., transaction amounts inflate). Schema drift = the structure of the data changes (a field is added, removed, or type-changed). Schema drift is caught by the schema registry; data drift is caught by statistical monitoring.

**Event time vs processing time:** Event time = when the event occurred in the real world (embedded in the payload). Processing time = when the event arrives at the processing system. For analytics, always use event time. Processing-time aggregations produce incorrect results when there's lag or reprocessing.

**At-least-once + idempotent = effectively exactly-once:** True exactly-once (Kafka transactions) has overhead and isn't needed in most cases. An idempotent consumer (checks if it already processed an event_id before processing) achieves the same result at lower cost.

**Partition key vs sort key vs partition column:** Kafka partition key = determines which Kafka partition a message goes to (routing for ordering). DynamoDB partition key = hash key for distributing data across nodes. Delta Lake/Parquet partition column = directory-based data organization for query pruning. These are three different concepts that happen to share the word "partition."

**Compaction vs VACUUM:** In Delta Lake, OPTIMIZE = compaction (merge small files into large files for faster reads). VACUUM = cleanup (delete old data files no longer referenced by the transaction log). Both are needed but serve different purposes.
