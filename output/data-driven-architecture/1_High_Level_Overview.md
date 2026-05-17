# Data-Driven Architecture

## What It Actually Means

"Data-driven architecture" is overloaded. In practice it covers two distinct ideas that are often conflated:

1. **Data as the primary interface between systems** — systems communicate by producing and consuming data streams or events rather than calling each other's APIs directly. Decoupling via data.

2. **Architecture decisions informed by data** — the shape of your storage, compute, and serving layers is determined by your data's characteristics: volume, velocity, variety, and query patterns.

A principal engineer must be fluent in both meanings and know which one is relevant in a given context.

---

## The Data Architecture Landscape

```
                        DATA SOURCES
                   ┌────────────────────┐
    Operational DBs │  Kafka / Kinesis   │ IoT / Events / Clickstream
         (OLTP)     └────────┬───────────┘
                             │
              ┌──────────────┴──────────────┐
              │                              │
        BATCH PATH                   STREAMING PATH
   (hours to days lag)              (seconds to minutes lag)
              │                              │
     S3 Data Lake                    Flink / Spark Structured Streaming
   (raw, immutable)                  Kafka Streams / Kinesis Analytics
              │                              │
              └──────────────┬──────────────┘
                             │
                    STORAGE / SERVING LAYER
              ┌──────────────────────────────┐
              │  Data Lakehouse              │
              │  (Delta Lake / Apache Iceberg)│
              │  Redshift / Snowflake         │
              │  (OLAP queries)               │
              └──────────────────────────────┘
                             │
              ┌──────────────────────────────┐
              │  Consumption Layer           │
              │  BI / Analytics (Tableau)    │
              │  ML Training (SageMaker)     │
              │  APIs / Microservices        │
              │  Operational Dashboards      │
              └──────────────────────────────┘
```

---

## The Five Foundational Patterns

### 1. Lambda Architecture
Two parallel processing paths: a batch layer for correctness + a speed layer for low latency. Results merged at query time.

**The problem it solves:** Real-time data has errors and late arrivals. Batch data is correct but slow. Lambda runs both and serves the union.

**The problem it creates:** You maintain two code paths (one batch, one streaming) that must produce identical results. Divergence bugs are common and hard to detect.

### 2. Kappa Architecture
Single processing path: everything is a stream. Batch jobs are just streams with a finite source. Reprocessing is done by replaying the log from offset 0.

**The problem it solves:** Lambda's dual-path complexity. One codebase, one paradigm.

**The tradeoff:** Reprocessing historical data requires a retention-capable log (Kafka with long retention) and streaming infrastructure that can handle backfill throughput.

### 3. Event Sourcing
System state is derived from an immutable append-only log of events. You store what happened, not what the current state is. Current state is computed by replaying events.

**Example:** Instead of storing `account.balance = 1000`, store `AccountOpened(500)`, `DepositMade(700)`, `WithdrawalMade(200)`. Balance = 500 + 700 - 200 = 1000.

**Power:** Complete audit trail, replay to any point in time, derive multiple projections from the same events.

### 4. CQRS (Command Query Responsibility Segregation)
Separate the write model (commands) from the read model (queries). Commands mutate state; queries read from an optimized projection. Typically combined with event sourcing.

**Example:** Order service writes to event store → projections service subscribes to events → builds optimized read models in DynamoDB (for UI), Elasticsearch (for search), Redshift (for analytics) from the same event stream.

### 5. Data Mesh
Treat data as a product. Federate data ownership to domain teams. Each domain owns its data products: the pipelines, quality, contracts, and documentation. A central platform team provides infrastructure (storage, cataloging, governance) but not data ownership.

**Contrast with centralized data warehouse:** One team owns all data engineering; other teams are consumers. Bottleneck at scale.

---

## OLTP vs OLAP vs HTAP

| Dimension | OLTP | OLAP | HTAP |
|-----------|------|------|------|
| **Purpose** | Transactional (read/write individual rows) | Analytical (read/aggregate many rows) | Both on same system |
| **Query pattern** | Point lookup, small writes | Full table scan, aggregations |  Mixed |
| **Optimization** | Row store, indexes, ACID | Column store, compression, MPP | Tiered storage |
| **Latency** | Milliseconds | Seconds to minutes | Mixed SLOs |
| **Scale** | Vertical or sharded | Horizontal MPP | Complex |
| **Examples** | PostgreSQL, DynamoDB, Aurora | Redshift, Snowflake, BigQuery | TiDB, SingleStore, Spanner |
| **AWS native** | RDS, DynamoDB, Aurora | Redshift, Athena | Aurora + Redshift Federated |

**The fundamental rule:** Don't run analytics queries on OLTP databases. A `SELECT COUNT(*) WHERE ...` on production RDS that does a full table scan will degrade latency for your transactional users. This is why the replication/ETL/ELT layer exists.

---

## The Modern Data Stack (2025)

```
┌──────────────────────────────────────────────────────────┐
│ Ingestion         │  Kafka / Kinesis (streaming)          │
│                   │  Fivetran / Airbyte (batch connectors)│
│                   │  Debezium (CDC from databases)        │
├──────────────────────────────────────────────────────────┤
│ Storage           │  S3 (raw data lake — immutable)       │
│                   │  Delta Lake / Iceberg (lakehouse)     │
│                   │  Redshift / Snowflake (warehouse)     │
├──────────────────────────────────────────────────────────┤
│ Processing        │  Apache Spark (batch)                  │
│                   │  Apache Flink (streaming)              │
│                   │  AWS Glue (managed Spark)             │
│                   │  dbt (SQL transformation)             │
├──────────────────────────────────────────────────────────┤
│ Orchestration     │  Apache Airflow / MWAA                │
│                   │  Prefect / Dagster                    │
├──────────────────────────────────────────────────────────┤
│ Catalog/Governance│  AWS Glue Data Catalog                │
│                   │  Apache Atlas / Unity Catalog         │
│                   │  Great Expectations (quality)         │
├──────────────────────────────────────────────────────────┤
│ Consumption       │  Tableau / QuickSight (BI)            │
│                   │  SageMaker (ML)                       │
│                   │  Redshift / Athena (ad-hoc SQL)       │
└──────────────────────────────────────────────────────────┘
```

---

## When Each Pattern Applies

| Situation | Pattern |
|-----------|---------|
| Audit trail required, time-travel queries | Event sourcing |
| Read and write have very different access patterns | CQRS |
| Need both real-time and batch analytics, can maintain two codebases | Lambda |
| Streaming-first org, want simple mental model | Kappa |
| Large org (> 20 teams), data quality and ownership fragmented | Data mesh |
| Need analytics on operational data without impact | ETL/ELT to data warehouse |
| Sub-second analytics on streaming data | Kappa + stream-table join |
| Historical replay and reprocessing needed | Event log (Kafka long retention) |

---

## Key Vocabulary

| Term | Definition |
|------|-----------|
| **CDC (Change Data Capture)** | Captures row-level changes from a database (insert/update/delete) as events |
| **Schema registry** | Central store for event/message schemas with versioning and compatibility enforcement |
| **Data contract** | Explicit agreement between data producer and consumer: schema, SLAs, semantics |
| **Data catalog** | Searchable inventory of all data assets: tables, schemas, lineage, ownership |
| **Data lineage** | Traceable path from raw source → every downstream transformation → final dataset |
| **Idempotent consumer** | Can receive the same message multiple times without producing incorrect results |
| **At-least-once delivery** | Message delivery guarantee that may produce duplicates (most streaming systems) |
| **Exactly-once semantics** | No duplicates, no loss — requires transactional writes or deduplication |
| **Medallion architecture** | Bronze (raw) → Silver (validated, cleaned) → Gold (aggregated, business-ready) |
| **Data lakehouse** | Combines data lake (cheap storage) with data warehouse (ACID, schema, query engine) |
| **Late data** | Events that arrive after the expected window has closed |
| **Watermark** | A progress indicator in stream processing that tracks how far behind real-time the stream is |
