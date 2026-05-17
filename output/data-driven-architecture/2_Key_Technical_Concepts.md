# Key Technical Concepts

## 1. Change Data Capture (CDC)

CDC extracts row-level changes from a database's transaction log and publishes them as events. It's the primary mechanism for moving data out of OLTP databases without polling.

```python
# Debezium connector config for PostgreSQL CDC → Kafka
# Debezium reads the PostgreSQL WAL (Write-Ahead Log) directly
# zero application-level changes to the source system

DEBEZIUM_CONNECTOR_CONFIG = {
    "name": "orders-cdc-connector",
    "config": {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "plugin.name": "pgoutput",          # PostgreSQL 10+ logical replication
        "database.hostname": "prod-postgres.internal",
        "database.port": "5432",
        "database.user": "debezium",        # needs REPLICATION privilege
        "database.password": "${DB_PASSWORD}",
        "database.dbname": "ecommerce",
        "table.include.list": "public.orders,public.order_items",
        "publication.autocreate.mode": "filtered",
        "slot.name": "debezium_orders_slot",
        # Topic naming: {server}.{schema}.{table}
        "topic.prefix": "prod",
        # Kafka output
        "transforms": "unwrap",
        "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
        "transforms.unwrap.add.fields": "op,ts_ms,source.db,source.table",
        "key.converter": "io.confluent.kafka.serializers.KafkaAvroSerializer",
        "value.converter": "io.confluent.kafka.serializers.KafkaAvroSerializer",
        "schema.registry.url": "http://schema-registry:8081",
    }
}

# Resulting Kafka event structure:
# Topic: prod.public.orders
# Key:   {"order_id": 12345}
# Value: {
#   "order_id": 12345,
#   "customer_id": 678,
#   "total_amount": 99.99,
#   "status": "shipped",
#   "__op": "u",           # c=create, u=update, d=delete, r=read/snapshot
#   "__ts_ms": 1711929600000,
#   "__source_table": "orders"
# }
```

**CDC vs polling-based ETL:**
- Polling: `SELECT * FROM orders WHERE updated_at > last_run`. Misses deletes, requires `updated_at` column, doesn't capture intermediate states between polls.
- CDC: captures every change including deletes, at the row level, in order, with sub-second lag.

**AWS equivalent:** DMS (Database Migration Service) with Change Data Capture mode → Kinesis or MSK. Or EventBridge Pipes from DynamoDB Streams for DynamoDB sources.

---

## 2. Event Sourcing

```python
import uuid, time, json
from dataclasses import dataclass, field
from typing import Any
import boto3

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
kinesis = boto3.client("kinesis", region_name="us-east-1")

@dataclass
class DomainEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    aggregate_id: str = ""
    aggregate_type: str = ""
    event_type: str = ""
    event_version: int = 1
    occurred_at: float = field(default_factory=time.time)
    data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

class EventStore:
    """Append-only event store backed by DynamoDB."""

    def __init__(self, table_name: str, stream_name: str):
        self.table = dynamodb.Table(table_name)
        self.stream_name = stream_name

    def append(
        self,
        aggregate_id: str,
        events: list[DomainEvent],
        expected_version: int,  # optimistic concurrency control
    ) -> int:
        """Append events to an aggregate's stream. Returns new version."""
        for i, event in enumerate(events):
            new_version = expected_version + i + 1
            try:
                self.table.put_item(
                    Item={
                        "aggregate_id": aggregate_id,            # partition key
                        "version": new_version,                  # sort key
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "aggregate_type": event.aggregate_type,
                        "occurred_at": str(event.occurred_at),
                        "data": json.dumps(event.data),
                        "metadata": json.dumps(event.metadata),
                    },
                    ConditionExpression="attribute_not_exists(version)",  # optimistic lock
                )
            except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                raise ConcurrencyException(f"Version {new_version} already exists for {aggregate_id}")

            # Publish to Kinesis for downstream projections
            kinesis.put_record(
                StreamName=self.stream_name,
                Data=json.dumps({**event.__dict__, "version": new_version}),
                PartitionKey=aggregate_id,  # same partition key → ordered per aggregate
            )
        return expected_version + len(events)

    def load(self, aggregate_id: str, to_version: int | None = None) -> list[DomainEvent]:
        """Load all events for an aggregate (optionally up to a version)."""
        kwargs = {
            "KeyConditionExpression": "aggregate_id = :aid",
            "ExpressionAttributeValues": {":aid": aggregate_id},
        }
        if to_version:
            kwargs["KeyConditionExpression"] += " AND version <= :v"
            kwargs["ExpressionAttributeValues"][":v"] = to_version

        response = self.table.query(**kwargs)
        return [
            DomainEvent(
                event_id=item["event_id"],
                aggregate_id=item["aggregate_id"],
                aggregate_type=item["aggregate_type"],
                event_type=item["event_type"],
                occurred_at=float(item["occurred_at"]),
                data=json.loads(item["data"]),
            )
            for item in response["Items"]
        ]

# Domain aggregate using event sourcing
class Order:
    def __init__(self):
        self.order_id = None
        self.customer_id = None
        self.items = []
        self.total = 0.0
        self.status = None
        self.version = 0
        self._uncommitted_events: list[DomainEvent] = []

    def place(self, order_id: str, customer_id: str, items: list[dict]) -> "Order":
        event = DomainEvent(
            aggregate_id=order_id, aggregate_type="Order",
            event_type="OrderPlaced",
            data={"order_id": order_id, "customer_id": customer_id, "items": items},
        )
        self._apply(event)
        self._uncommitted_events.append(event)
        return self

    def ship(self) -> "Order":
        if self.status != "confirmed":
            raise ValueError(f"Cannot ship order in status {self.status}")
        event = DomainEvent(
            aggregate_id=self.order_id, aggregate_type="Order",
            event_type="OrderShipped",
            data={"order_id": self.order_id},
        )
        self._apply(event)
        self._uncommitted_events.append(event)
        return self

    def _apply(self, event: DomainEvent):
        """Apply event to current state — the only place state is mutated."""
        if event.event_type == "OrderPlaced":
            self.order_id = event.data["order_id"]
            self.customer_id = event.data["customer_id"]
            self.items = event.data["items"]
            self.status = "placed"
        elif event.event_type == "OrderShipped":
            self.status = "shipped"
        self.version += 1

    @classmethod
    def reconstitute(cls, events: list[DomainEvent]) -> "Order":
        """Rebuild aggregate state by replaying events."""
        order = cls()
        for event in events:
            order._apply(event)
        return order
```

---

## 3. CQRS: Read Model Projections

```python
import boto3
import json

kinesis = boto3.client("kinesis", region_name="us-east-1")
dynamodb = boto3.resource("dynamodb")
es_client = boto3.client("opensearch")

class OrderProjectionBuilder:
    """Subscribes to order events and builds multiple read models."""

    def __init__(self):
        self.dynamo_table = dynamodb.Table("order-read-model")
        self.analytics_table = dynamodb.Table("order-analytics")

    def handle_event(self, event: dict):
        event_type = event["event_type"]
        handler = getattr(self, f"on_{event_type.lower()}", None)
        if handler:
            handler(event)

    def on_orderplaced(self, event: dict):
        data = event["data"]
        # Write model 1: DynamoDB for O(1) order lookup by order_id
        self.dynamo_table.put_item(Item={
            "order_id": data["order_id"],
            "customer_id": data["customer_id"],
            "status": "placed",
            "items": data["items"],
            "total": sum(item["price"] * item["qty"] for item in data["items"]),
            "placed_at": event["occurred_at"],
        })

        # Write model 2: Customer order index (GSI or separate table)
        self.dynamo_table.put_item(Item={
            "pk": f"CUSTOMER#{data['customer_id']}",
            "sk": f"ORDER#{data['order_id']}",
            "order_id": data["order_id"],
            "status": "placed",
            "placed_at": event["occurred_at"],
        })

    def on_ordershipped(self, event: dict):
        data = event["data"]
        # Update existing read model
        self.dynamo_table.update_item(
            Key={"order_id": data["order_id"]},
            UpdateExpression="SET #s = :status, shipped_at = :ts",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": "shipped", ":ts": event["occurred_at"]},
        )
```

**The CQRS advantage:** Each read model is optimized for its specific query pattern. DynamoDB for fast single-order lookup. A separate Redshift table for "revenue by customer segment last 30 days." Both built from the same event stream.

---

## 4. Apache Kafka: The Central Nervous System

```python
from confluent_kafka import Producer, Consumer, KafkaError
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
import json

# Producer with schema registry (schema-on-write enforcement)
schema_registry_client = SchemaRegistryClient({"url": "http://schema-registry:8081"})

ORDER_SCHEMA = """
{
  "type": "record",
  "name": "Order",
  "namespace": "com.mycompany.orders",
  "fields": [
    {"name": "order_id", "type": "string"},
    {"name": "customer_id", "type": "string"},
    {"name": "total_amount", "type": "double"},
    {"name": "status", "type": "string"},
    {"name": "event_time_ms", "type": "long"}
  ]
}
"""

avro_serializer = AvroSerializer(schema_registry_client, ORDER_SCHEMA)

producer = Producer({
    "bootstrap.servers": "kafka:9092",
    "acks": "all",            # wait for all ISR replicas to ack (durability)
    "enable.idempotence": True,  # exactly-once at producer level
    "compression.type": "snappy",
    "batch.size": 65536,      # 64KB batch before sending
    "linger.ms": 5,           # wait 5ms to batch more messages
    "retries": 3,
    "max.in.flight.requests.per.connection": 5,
})

def produce_order_event(order: dict):
    producer.produce(
        topic="orders.events",
        key=order["order_id"].encode(),  # keyed by order_id → same partition → ordered per order
        value=avro_serializer(order, None),
        on_delivery=lambda err, msg: (
            print(f"Delivered to partition {msg.partition()} offset {msg.offset()}")
            if not err else print(f"Delivery failed: {err}")
        ),
    )

# Consumer with consumer group (horizontal scaling)
consumer = Consumer({
    "bootstrap.servers": "kafka:9092",
    "group.id": "order-projection-builder",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,  # manual commit for at-least-once with idempotent processing
    "max.poll.interval.ms": 300000,
    "session.timeout.ms": 30000,
})
consumer.subscribe(["orders.events"])

avro_deserializer = AvroDeserializer(schema_registry_client)

def consume_and_process():
    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            raise Exception(f"Consumer error: {msg.error()}")

        order = avro_deserializer(msg.value(), None)
        process_order_event(order)     # idempotent processing
        consumer.commit(message=msg)  # commit only after successful processing
```

**Kafka key concepts:**
- **Partitions:** Unit of parallelism. Messages with the same key go to the same partition → ordering guaranteed per key. Add partitions to scale consumers.
- **Consumer groups:** Each partition consumed by exactly one consumer in the group. Scale consumers = scale partitions.
- **Retention:** Kafka retains messages for the configured period (default 7 days, can be infinite with compaction or long retention). This enables replay.
- **Compaction:** Keeps only the latest message per key. Turns Kafka into a key-value store — useful for CDC topics where you want "current state" of each record.

---

## 5. Stream Processing with Apache Flink

```python
# PyFlink: stateful stream processing with exactly-once semantics
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer
from pyflink.common import WatermarkStrategy, Duration, Types
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.common.watermark_strategy import TimestampAssigner
import json

env = StreamExecutionEnvironment.get_execution_environment()
env.set_parallelism(4)
env.enable_checkpointing(60_000)  # checkpoint every 60s (fault tolerance)
env.get_checkpoint_config().set_checkpoint_storage_uri("s3://my-flink-checkpoints/")

# Source: Kafka with event-time semantics
kafka_source = (KafkaSource.builder()
    .set_bootstrap_servers("kafka:9092")
    .set_topics("orders.events")
    .set_group_id("flink-revenue-aggregator")
    .set_starting_offsets(KafkaOffsetsInitializer.earliest())
    .set_value_only_deserializer(SimpleStringSchema())
    .build()
)

# Watermark strategy: allow up to 30 seconds of late data
watermark_strategy = (WatermarkStrategy
    .for_bounded_out_of_orderness(Duration.of_seconds(30))
    .with_timestamp_assigner(
        # Extract event time from the message payload
        lambda event, _: json.loads(event)["event_time_ms"]
    )
)

stream = env.from_source(kafka_source, watermark_strategy, "Kafka Orders")

# Windowed aggregation: 1-minute tumbling windows, keyed by merchant
revenue_by_merchant = (stream
    .map(lambda e: json.loads(e))
    .key_by(lambda e: e["merchant_id"])                         # partition by merchant
    .window(TumblingEventTimeWindows.of(Time.minutes(1)))       # 1-min event-time windows
    .aggregate(RevenueAggregator())                             # sum revenue per window
    .add_sink(KafkaSink(topic="merchant.revenue.1min"))
)

# Exactly-once end-to-end: Flink checkpoint + Kafka transactional producer
# Flink's KafkaSink with EXACTLY_ONCE semantic uses Kafka transactions internally

env.execute("Revenue Aggregation Pipeline")
```

**Flink vs Spark Structured Streaming:**
- **Flink:** True stream processing, sub-second latency, native event-time, stateful with RocksDB backend, exactly-once
- **Spark SS:** Micro-batch (default ~1s intervals), SQL-friendly, unified batch+streaming API, easier for most data engineers
- **Rule of thumb:** Use Flink for < 1s latency requirements or complex stateful operations. Use Spark SS for 1s–5min latency tolerances and teams already in the Spark ecosystem.

---

## 6. The Medallion Architecture (Bronze/Silver/Gold)

```python
# AWS Glue / PySpark implementation of Medallion layers
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from delta.tables import DeltaTable

spark = SparkSession.builder \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .getOrCreate()

S3_BASE = "s3://my-datalake"

# BRONZE: Raw ingestion — preserve exactly what arrived, no transformation
# Written by ingestion pipeline (Kafka → S3 via Kinesis Firehose or Kafka S3 Sink)
# Schema: {raw_payload: string, ingested_at: timestamp, source: string, partition: date}

# SILVER: Validated, cleaned, typed, deduplicated
def bronze_to_silver(date: str):
    bronze_df = spark.read.format("delta").load(f"{S3_BASE}/bronze/orders/")

    silver_df = (bronze_df
        .where(F.col("ingested_at").cast("date") == date)
        # Parse JSON raw payload
        .withColumn("parsed", F.from_json("raw_payload", ORDER_SCHEMA))
        .select("parsed.*", "ingested_at", "source")
        # Type casting and validation
        .withColumn("order_id", F.col("order_id").cast("string"))
        .withColumn("total_amount", F.col("total_amount").cast("decimal(10,2)"))
        .withColumn("event_time", F.to_timestamp("event_time_ms" / 1000))
        # Drop rows with null primary key (data quality gate)
        .where(F.col("order_id").isNotNull())
        # Deduplication: keep latest version of each order_id per day
        .dropDuplicates(["order_id", "event_type"])
        # Add standard metadata columns
        .withColumn("silver_processed_at", F.current_timestamp())
        .withColumn("date_partition", F.to_date("event_time"))
    )

    # Write to Silver (Delta Lake for ACID, schema enforcement, time travel)
    silver_df.write.format("delta") \
        .mode("append") \
        .partitionBy("date_partition") \
        .option("mergeSchema", "false") \
        .save(f"{S3_BASE}/silver/orders/")

# GOLD: Business-level aggregates, optimized for consumption
def silver_to_gold_daily_revenue(date: str):
    silver_df = spark.read.format("delta") \
        .load(f"{S3_BASE}/silver/orders/") \
        .where(F.col("date_partition") == date)

    gold_df = (silver_df
        .where(F.col("event_type") == "OrderPlaced")
        .groupBy("date_partition", "merchant_id", "category")
        .agg(
            F.sum("total_amount").alias("gross_revenue"),
            F.count("order_id").alias("order_count"),
            F.avg("total_amount").alias("avg_order_value"),
            F.countDistinct("customer_id").alias("unique_customers"),
        )
        .withColumn("gold_processed_at", F.current_timestamp())
    )

    # MERGE (upsert) — idempotent, handles reruns
    if DeltaTable.isDeltaTable(spark, f"{S3_BASE}/gold/daily_revenue/"):
        DeltaTable.forPath(spark, f"{S3_BASE}/gold/daily_revenue/") \
            .alias("existing") \
            .merge(gold_df.alias("updates"),
                   "existing.date_partition = updates.date_partition AND "
                   "existing.merchant_id = updates.merchant_id AND "
                   "existing.category = updates.category") \
            .whenMatchedUpdateAll() \
            .whenNotMatchedInsertAll() \
            .execute()
    else:
        gold_df.write.format("delta") \
            .mode("overwrite") \
            .partitionBy("date_partition") \
            .save(f"{S3_BASE}/gold/daily_revenue/")
```

---

## 7. Data Contracts

A data contract is a formal agreement between data producer and consumer. It specifies schema, SLAs, semantics, and ownership. Prevents silent breaking changes.

```yaml
# data_contract.yaml — stored in git, versioned
apiVersion: 1.0.0
id: com.mycompany.orders.v2
name: Orders Events Contract
version: 2.1.0
description: Order lifecycle events from the order management service

owner:
  team: order-platform
  slack: "#order-platform-oncall"
  email: order-platform@mycompany.com

schema:
  format: avro
  registry: https://schema-registry.internal
  subject: orders.events-value

sla:
  availability: 99.9%
  freshness: "< 30 seconds from event occurrence"
  completeness: "< 0.01% message loss"
  schema_stability: "backward compatible changes only; 30-day notice for breaking changes"

semantics:
  order_id: "Globally unique order identifier. Immutable once assigned."
  event_time_ms: "UTC epoch milliseconds when the event occurred in the source system, not ingestion time"
  total_amount: "Sum of all line items including tax, excluding shipping. May differ from payment_amount."
  status: "Enum: placed | confirmed | shipped | delivered | cancelled | refunded"

quality:
  null_rate_order_id: "Must be 0%"
  null_rate_total_amount: "Must be < 0.001%"
  expected_daily_volume: "1M - 5M events/day"
  duplicate_rate: "< 0.01%"

consumers:
  - name: analytics-pipeline
    team: data-engineering
    usage: "Bronze ingestion, daily revenue reporting"
  - name: fraud-detection
    team: risk
    usage: "Real-time fraud scoring feature pipeline"
  - name: fulfillment-service
    team: logistics
    usage: "Order routing to warehouse"
```

---

## 8. Schema Registry and Evolution

```python
from confluent_kafka.schema_registry import SchemaRegistryClient, Schema
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer

client = SchemaRegistryClient({"url": "http://schema-registry:8081"})

# Register schema (or evolve existing)
schema_str = """
{
  "type": "record",
  "name": "Order",
  "namespace": "com.mycompany",
  "fields": [
    {"name": "order_id",    "type": "string"},
    {"name": "customer_id", "type": "string"},
    {"name": "total_amount","type": "double"},
    {"name": "currency",    "type": "string", "default": "USD"}  # NEW: backward compatible (has default)
  ]
}
"""

schema_id = client.register_schema(
    subject_name="orders.events-value",
    schema=Schema(schema_str, schema_type="AVRO"),
)

# Schema compatibility modes:
# BACKWARD: New schema can read data produced by old schema (add fields with defaults, delete optional fields)
# FORWARD:  Old schema can read data produced by new schema (delete fields with defaults, add optional fields)
# FULL:     Both BACKWARD and FORWARD
# NONE:     No compatibility check (dangerous in production)

# Set global compatibility
client.set_compatibility(level="BACKWARD")
# Or per-subject:
client.set_compatibility(subject_name="orders.events-value", level="FULL")
```
