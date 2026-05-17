# Interview Questions & Model Answers

## L5 — Senior Engineer

---

**Q1: What is the difference between a data lake, data warehouse, and data lakehouse? When do you use each?**

**A:**

**Data warehouse** (Redshift, Snowflake, BigQuery): proprietary columnar storage, schema-on-write, strong ACID guarantees, optimized for SQL analytical queries. High cost because compute and storage are bundled. Governance is strong — column-level security, row-level policies. Weakness: expensive to store raw data, hard to access from ML/Python without extraction.

**Data lake** (S3 + Athena/Parquet): cheap object storage, any format, schema-on-read. Very flexible for ML and data science — read Parquet directly with Spark, pandas, whatever. Weakness: no ACID, no upserts (overwrite entire partition), no versioning, governance is file-level only.

**Data lakehouse** (S3 + Delta Lake/Iceberg + query engine): combines cheap object storage with ACID transactions, schema enforcement, upserts (MERGE), and time travel — all on top of open file formats. You get data lake economics (cheap S3) with warehouse capabilities (ACID, governance). The query engine (Athena, Trino, Spark) is separate, so you can choose the best tool per query.

**When to use each:**
- Data warehouse only: BI-heavy org, SQL-only team, heavy concurrent query workloads requiring WLM, regulatory requirements that demand a governed RDBMS
- Data lake only: you need raw data preservation, highly exploratory ML work, extremely high write volume where schema flexibility matters
- Data lakehouse: almost every greenfield architecture in 2025. Best of both. The separation of storage from compute is the key insight.

---

**Q2: Explain Kafka's partition and consumer group model. How does it enable both ordering guarantees and horizontal scaling?**

**A:** Kafka's model is elegant: a topic is divided into N partitions. Within a partition, messages are strictly ordered by offset. Across partitions, there is no ordering guarantee.

**Producer side:** You choose a partition key (e.g., `order_id`). Kafka hashes the key to determine which partition receives the message. All messages for `order_id=123` go to the same partition, so they're ordered relative to each other. Messages for different order IDs may go to different partitions.

**Consumer side:** A consumer group is a logical subscriber. Each partition is assigned to exactly one consumer within the group. So if you have 10 partitions and 10 consumers, each consumer handles one partition. If you have 5 consumers, each handles 2 partitions. More consumers than partitions: some consumers are idle.

**The scaling model:** Add partitions to increase parallelism. Each additional partition can be handled by an additional consumer thread/pod. The practical limit on partitions: Kafka performance degrades for topics with > 10,000 partitions per broker.

**Ordering within a key + parallelism across keys:** This is the central design. If you need all events for a user ordered, use `user_id` as the partition key. Different users' events process in parallel. You get ordering where it matters (within an entity) and parallelism where it doesn't (across entities).

**The trap:** If you partition by an imbalanced key (e.g., `country_code` with 80% of traffic from "US"), one partition becomes a hot partition. Other consumers sit idle. Always check cardinality and distribution of your partition key.

---

**Q3: What is event sourcing, when would you use it, and what are the operational challenges?**

**A:** Event sourcing stores the history of what happened as an append-only log of events, rather than storing the current state. Current state is derived by replaying events. Instead of `UPDATE orders SET status='shipped'`, you append `OrderShipped(order_id, ts, tracking_number)`.

**When to use it:**
- Audit trail is a hard requirement (financial, healthcare, regulatory)
- You need time travel (what was the order state at 3pm last Tuesday?)
- Multiple downstream systems need different projections of the same data (CQRS)
- Domain events are meaningful to the business (not just implementation details)

**When NOT to use it:**
- Simple CRUD with no audit requirements — massive complexity for no gain
- High-write, low-event-meaning systems (metrics, logs, counters)
- Teams without the DDD knowledge to properly define aggregate boundaries

**Operational challenges:**

1. **Snapshot management:** An Order with 10,000 events can't replay all of them on every request. Solution: periodic snapshots (store aggregate state at version N, replay from N+1). Adds complexity to the load path.

2. **Schema evolution:** Events are immutable. If you need to change the `OrderPlaced` schema, you can't modify past events. Solution: event upcasting (apply transformation when reading old events), or version the event types (`OrderPlacedV2`).

3. **Querying:** You can't `SELECT * FROM orders WHERE status='pending'`. Current state isn't stored anywhere. Solution: maintain read-model projections (CQRS). Every query goes to the projection, not the event store.

4. **Eventual consistency:** Projections are built asynchronously from events. After writing a command, there's a delay before the projection reflects the change. Handle this in the UI (optimistic UI updates, loading states).

---

**Q4: Explain the Lambda architecture, its appeal, and why many teams migrate away from it.**

**A:** Lambda architecture runs two parallel paths: a batch layer (correctness) and a speed layer (low latency). The batch layer processes complete historical data and produces correct results, but slowly. The speed layer processes recent data and produces approximate results quickly. A serving layer merges both.

**The appeal:** It solves a real problem. Streaming systems in 2011 (when Lambda was coined) were hard to make correct — no exactly-once, no easy windowing, hard to reprocess. Running a nightly Hadoop job for correctness + a Storm job for freshness seemed like a reasonable tradeoff.

**Why teams migrate away:**
1. **Two codebases for the same logic.** The batch job and the streaming job compute the same metrics. They're written in different languages (Spark SQL vs Storm Java), by different teams, and diverge over time. Silent discrepancies between batch and streaming results are hard to detect.
2. **Merge logic is non-trivial.** At query time, merging batch (correct, stale) and speed layer (approximate, fresh) results requires careful deduplication. If a user's click appears in both layers, you count it once or twice?
3. **Modern streaming solved the original problem.** Flink, Kafka Streams, and Spark Structured Streaming all support exactly-once, event-time windowing, and stateful processing. The speed layer's limitations no longer justify running two paths.
4. **Replay for corrections.** With Kafka's configurable log retention and Kappa architecture, you replay the stream from the beginning to "redo" batch processing. One codebase handles both.

**My recommendation:** Don't design a new system as Lambda. If you're maintaining an existing Lambda system, assess whether Kappa migration is feasible — it often is, and the ongoing maintenance cost reduction is significant.

---

## L6 — Staff Engineer

---

**Q5: Design a data platform for a logistics company with 1,000 warehouses, 10 million package scans per day, and requirements for real-time package tracking, daily operational reporting, and ML-based delivery time prediction.**

**A:** Three distinct access patterns drive three distinct architectural components. I'd build them separately with a shared data foundation.

**Foundation: event streaming backbone**
All package scan events flow through MSK (Kafka). Partition key: `package_id`. This ensures all scans for a package are ordered and go to the same partition. 10M scans/day ≈ 115 scans/second — very manageable with 20 partitions on a `kafka.m5.large` cluster.

**Component 1: Real-time package tracking (< 5s latency)**
Flink job subscribes to scan events, maintains stateful per-package tracking (last location, current carrier, estimated delivery). State backend: RocksDB (handles millions of in-flight packages). Output: Redis hash `package:{id}` → current state. Serving API queries Redis, not Kafka or S3. This path is self-contained — even if the analytical pipeline is down, tracking works.

**Component 2: Daily operational reporting (T+1 latency acceptable)**
Kinesis Firehose delivers scan events to S3 as Parquet (bronze). Nightly Glue Spark job runs the Bronze → Silver → Gold medallion pipeline. Gold tables in Redshift: packages_delivered_daily, warehouse_throughput_daily, carrier_performance, exception_rates. BI team queries Redshift. dbt manages transformations with data quality tests.

**Component 3: ML delivery time prediction**
Feature pipeline (another Flink job): computes features from scan stream — scan velocity, current carrier, origin/destination pair, weather conditions (external enrichment). Materializes to SageMaker Feature Store (online store for serving, offline store for training). Training: weekly batch on 90 days of historical scans + actual delivery times. Model served via SageMaker endpoint, queried at scan time to update estimated delivery.

**The architectural decision I'd emphasize:** Don't put the real-time tracking on the same Flink job as the feature pipeline. Different SLAs (tracking: < 5s; features: < 1 min), different state management requirements, different teams owning them. Separation enables independent scaling and deployment.

**Data contract:** Define a schema for the scan event in the Confluent Schema Registry. All three components are consumers — any breaking schema change by the logistics ops team would break all three simultaneously. The contract enforces backward compatibility and gives consumers 30-day notice for breaking changes.

---

**Q6: What is a data contract, why does it matter at scale, and how do you enforce it in practice?**

**A:** A data contract is a formal agreement between a data producer and its consumers specifying: schema (field names, types, required vs optional), quality SLAs (null rates, row count bounds, freshness), semantic meaning (what does `total_amount` mean — does it include tax?), and ownership (who to contact when something breaks).

**Why it matters at scale:**
Without contracts, data pipelines are implicit agreements embedded in code. Producer changes a field from `string` to `integer`? Consumers silently break. A column gets renamed? All downstream dbt models fail at 2 AM. At 5 teams, this is annoying. At 50 teams and 300 downstream consumers, it's catastrophic — you have no idea who consumes which data and what will break.

The real cost isn't the individual breakage — it's the trust erosion. After three unexplained pipeline failures, the ML team builds their own data extraction and the data platform team has lost a consumer.

**Enforcement in practice (three layers):**

1. **Schema registry (technical enforcement at write time):** All Kafka producers register their schema in Confluent Schema Registry. Backward compatibility is enforced — a new schema that breaks compatibility is rejected at registration time, before any consumer is affected. This is zero-cost enforcement.

2. **Data quality checks (enforcement at pipeline boundary):** Great Expectations or dbt tests run as part of the Silver pipeline. Any data that violates the contract's quality rules (null rate, out-of-range values, duplicate rate) fails the pipeline — or routes violating records to a quarantine bucket with an alert. The contract specifies the thresholds; the pipeline enforces them automatically.

3. **Semantic validation and governance (enforcement at deployment):** A data contract is code (YAML in git). Changes to contracts are PRs. Consumer teams are code-owners of contracts they depend on — they must review and approve changes. This creates a human review gate for semantic changes that technical enforcement can't catch (renaming a field without changing its type).

**The organization change that makes it work:** Data contracts only work if breaking them has consequences — SLA tracking, incident attribution, team OKRs that include data quality. Without accountability, teams evolve schemas freely and contracts become shelfware.

---

**Q7: You're running a Kafka-based event streaming pipeline. A consumer group falls 50 million messages behind. Walk me through your diagnosis and remediation.**

**A:** 50M messages of lag means the consumer is either down or processing far too slowly. I'd diagnose in layers:

**Step 1: Is the consumer running?** Check if consumer pods/processes are alive and healthy. 50M lag on a stopped consumer group is expected — just restart and wait for catch-up. If it's running, proceed.

**Step 2: What's the processing rate?** Compare: production rate (messages/second published to topic) vs consumption rate (messages/second committed by consumer group). If production > consumption, the consumer can never catch up even running at full speed — it's structurally undersized.

**Step 3: What's the actual consumption rate?**
- Check CPU and memory on consumer nodes (compute-bound?)
- Check external dependencies: if the consumer writes to DynamoDB and DynamoDB is throttling, that's the bottleneck
- Check thread utilization: Kafka consumers must poll frequently or the broker declares them dead and triggers rebalance. Check `max.poll.interval.ms` vs actual processing time.

**Step 4: Is this a partition imbalance?** Check per-partition lag. If 2 of 20 partitions are at 45M lag each and the rest are fine, there may be hot partitions (high-cardinality key skew) or partition assignment bias (those 2 partitions are assigned to a slow/dead consumer).

**Remediation options:**

- **Scale out consumers:** Add more consumer instances (up to the number of partitions). If already at partition count, add partitions first (resharding).
- **Fix the bottleneck:** If DynamoDB is throttling, increase capacity or batch writes. If CPU-bound, scale up instance size.
- **Reduce processing cost:** If each message triggers a synchronous external call, switch to batching (process 1,000 messages per external call instead of 1 message per call).
- **Parallel catch-up strategy:** For non-order-sensitive workloads, temporarily spin up additional consumer groups to process the backlog in parallel, then merge results.
- **Triage:** If this consumer feeds a live dashboard (real-time use case) and is 2 hours behind, consider skipping ahead to the latest offset and accepting the data gap — better to show current data than 2-hour-old data with a rapidly closing lag.

**Prevention:** Alert on consumer lag > 10k messages (5-minute alert). At 10k you can investigate; at 50M you're in crisis mode.

---

## L7+ — Principal Engineer

---

**Q8: You're designing the data architecture for a company moving from 5 to 50 product teams over the next 2 years. The current centralized data team is already a bottleneck. What's your architectural strategy?**

**A:** This is a data mesh problem, and I'd solve it with a phased approach that accounts for organizational readiness.

**The core tension:** Data mesh is the right long-term answer — federate ownership to domain teams, each responsible for their data products. But data mesh requires organizational maturity that most companies don't have: domain teams with data engineering skills, clear domain boundaries, and accountability for data quality. Forcing data mesh on immature domains creates a distributed mess.

**Phase 1: Build the platform (months 1–6), not the mesh**

Before federating anything, the central team builds a self-service data platform so that domain teams can operate data pipelines without needing data engineering expertise. This means:
- Terraform modules for standard data pipeline patterns (Kafka topic → Bronze → Silver → Gold)
- Reusable CI/CD pipeline templates (GitHub Actions) that wire up quality checks, alerting, and lineage automatically
- A data product SDK that abstracts the underlying infra — teams write a schema + transformation + SLA; the platform handles Glue jobs, monitoring, catalog registration

The central team's job is to build the platform, not all the pipelines.

**Phase 2: Pilot with 3 ready domains (months 4–9)**

Identify 3 domains with: clear boundaries, team ownership, and at least one engineer who understands data infrastructure. Have them build data products using the platform. Support them heavily. Document the friction points. Fix the platform based on real usage.

Don't federate 50 teams simultaneously. You'll create 50 different failure modes and no one to fix them.

**Phase 3: Federate progressively based on readiness (months 9–24)**

Use a readiness rubric: does the domain have a dedicated data engineer? Do they have monitoring for their pipelines? Have they passed a production readiness review? Domains that meet the bar own their pipelines. Domains that don't, get a supported model: central team builds the pipeline, domain team owns the schema and SLA.

**What stays central:**
- Schema registry (enforcing compatibility across all producers)
- Data catalog (centralized discovery, even if ownership is federated)
- Compliance and governance (PII classification, data access policies can't be federated)
- Incident response for platform infrastructure (not for domain data quality — that's the domain team's SLA)
- Inter-domain join patterns (when Payment's data and Identity's data need to be joined, someone needs to own the contract between them)

**The metric for success:** Time from "domain team wants a new data product" to "product is available for consumption" should decrease from months to days. If it doesn't, the platform isn't actually self-service.

---

**Q9: Debate: "All data pipelines should be stream-first; batch processing is legacy thinking."**

**A:** This is an overcorrection. The nuanced answer:

**Where the claim holds:**
For systems built today with requirements for < 1-hour data freshness, streaming-first is the right default. The Kappa architecture simplifies the mental model — one codebase, one paradigm. Modern streaming (Flink, Kafka Streams, Spark Structured Streaming) handles exactly-once, event-time windowing, and stateful processing well. And you can replay a bounded stream for "batch" semantics without maintaining separate batch infrastructure.

**Where the claim fails:**

*Total cost of ownership:* A Flink cluster or Kinesis Analytics application runs 24/7. A Glue Spark job runs once per hour and costs nothing when idle. For a pipeline with 2-hour acceptable latency, batch is 10–20× cheaper. Stream-first thinking applied universally inflates infrastructure costs significantly.

*Problem complexity:* Some computations are inherently global — "rank all products by revenue last 30 days" requires a full sort across all products. Streaming allows incremental approximation; batch allows exact computation with full data. For regulatory reporting that must be exact (not approximate), batch is the correct tool.

*Operational simplicity:* Most data engineering teams are more fluent in Spark SQL than Flink. "Streaming" Spark (Structured Streaming) closes the gap, but there's still a real skill gap between batch SQL and stateful streaming. Deploying streaming incorrectly (wrong watermarks, missing late data handling) is worse than batch — it silently produces wrong results.

*The correctness trap:* Streaming with late data requires a decision: how long do you wait for late events before closing a window? If you set your watermark at 30 seconds and a scan arrives 45 seconds late, you miss it. Batch, run daily, gets all events.

**My actual answer:** Design systems by SLA, not ideology. Latency < 1 min → streaming. Latency 1 min–1 hour → micro-batch (Spark SS with 1–5 minute intervals). Latency > 1 hour → batch. For most reporting, analytics, and ML training pipelines at typical companies: batch or micro-batch is correct. Streaming is correct for real-time user-facing features, operational monitoring, and event-driven microservices.

---

**Q10: What is the "small files problem" in data lakes, and how do you solve it comprehensively at each layer of the architecture?**

**A:** The small files problem: S3 + Parquet performs optimally with files in the 128MB–1GB range. When files are small (< 10MB), query engines spend more time on file listing and metadata operations than on actual data processing. A table with 10,000 files of 1MB each is slower to query than the same data in 10 files of 1GB each — even though the data volume is identical.

**Root causes:**

1. **Streaming ingestion writes one file per micro-batch.** Spark Structured Streaming or Kafka S3 Sink writes a file every 30 seconds → 2,880 files per day per topic.
2. **Upserts create residual small files.** Delta Lake MERGE operations don't rewrite the entire partition — they write new small files for changed records and leave old files in place until VACUUM.
3. **High-cardinality partitioning.** Partitioning by `(date, merchant_id, category)` creates thousands of partitions, each with tiny files.

**Solutions at each layer:**

**Bronze (ingestion):** Configure Firehose/Kafka sink with larger buffers. Kinesis Firehose: set `BufferingHints.SizeInMBs=128` and `IntervalInSeconds=900`. This buffers 128MB or 15 minutes before writing, whichever comes first. Don't partition Bronze by more than date — finer partitioning creates file explosion at ingestion speed.

**Silver (transformation):** Run file compaction after Silver write. Delta Lake `OPTIMIZE` command merges small files into target file size (default 1GB). Run this as the last step of the Silver job or on a separate schedule. For Iceberg: `rewriteDataFiles()`.

```python
# After Silver job completes
DeltaTable.forPath(spark, silver_path).optimize().executeCompaction()
```

**Gold (serving):** Run `OPTIMIZE ... ZORDER BY (customer_id)` on Gold tables. Z-ordering co-locates related data in the same files, enabling data skipping (query reads only files that might contain the target rows). For a query `WHERE customer_id = '12345'`, with Z-order on `customer_id`, the engine reads < 1% of files instead of all files.

**Kafka S3 Sink (streaming path):** Use the `rotate.interval.ms` and `rotate.schedule.interval.ms` settings to buffer longer before writing. A file-per-minute is 1,440 small files per day; a file-per-15-minutes is 96 files. Consider a separate compaction job that runs hourly and merges the streaming mini-files.

**The meta-solution:** Monitor file size distribution in production tables as a routine health check. Alert when median file size drops below 50MB. Treat it as a pipeline reliability issue, not a performance curiosity. A table whose query performance is degrading by 2% per month due to file proliferation will eventually become unusable — and the compaction debt is hard to pay down retroactively on petabyte-scale tables.
