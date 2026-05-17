# Use Cases & Real-World Applications

## 1. Real-Time E-Commerce Analytics Platform

**Context**: A marketplace generates 5M order events/day. Business requires: live GMV dashboard (< 30s lag), merchant analytics (T+1), fraud scoring (< 200ms), and ML feature pipelines. Multiple teams consuming the same order events.

### Architecture

```
Order Service (OLTP: Aurora PostgreSQL)
    │
    ├── Debezium CDC → MSK "orders.cdc.events" (all inserts/updates/deletes)
    │
    └── Application events → MSK "orders.domain.events" (semantic events: OrderPlaced, OrderShipped)

MSK Topics → Fan-out consumers:

    ├── Flink Job: Revenue Aggregation
    │   └── 30-second tumbling windows → Kinesis → ElastiCache Redis → Live Dashboard
    │
    ├── Kinesis Firehose: Bronze ingestion
    │   └── S3 s3://datalake/bronze/orders/ (Parquet, partitioned by hour)
    │
    ├── Flink Job: Fraud Feature Pipeline
    │   └── Velocity features → SageMaker Feature Store (online) → Fraud Model Endpoint
    │
    └── Glue Spark: Nightly Medallion Pipeline
        ├── Bronze → Silver (clean, deduplicate, type-cast)
        └── Silver → Gold (merchant revenue, customer cohorts, product performance)
```

### Key Design Decisions

```python
# Decision 1: Two Kafka topics — CDC + Domain events
# CDC topic: raw database changes (include deletes, all fields)
# Domain events: semantic events with business meaning (OrderPlaced includes computed fields)
# Don't conflate them — CDC is operational; domain events are business API

# Decision 2: Separate write path for live dashboard vs analytics
# Live dashboard (ElastiCache): pre-aggregated, fast reads, bounded staleness acceptable (30s)
# Analytics (S3 + Redshift): full fidelity, correct aggregation, T+1 latency acceptable

# Real-time revenue aggregator in Flink
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.window import SlidingEventTimeWindows
from pyflink.common import Time

env = StreamExecutionEnvironment.get_execution_environment()
env.enable_checkpointing(30_000)  # 30s checkpoint interval

def build_live_dashboard_pipeline(env):
    orders = (env
        .add_source(kafka_source("orders.domain.events"))
        .map(parse_order_event)
        .filter(lambda e: e["event_type"] == "OrderPlaced")
        .assign_timestamps_and_watermarks(
            WatermarkStrategy.for_bounded_out_of_orderness(Duration.of_seconds(10))
            .with_timestamp_assigner(lambda e, _: e["event_time_ms"])
        )
    )

    # 30-second tumbling windows for live GMV
    live_gmv = (orders
        .key_by(lambda e: e["merchant_id"])
        .window(TumblingEventTimeWindows.of(Time.seconds(30)))
        .aggregate(SumAggregator("total_amount"))
        .add_sink(redis_sink("gmv:merchant:{key}"))
    )

    # 5-minute sliding windows for rolling revenue trend
    trend = (orders
        .window(SlidingEventTimeWindows.of(Time.minutes(5), Time.seconds(30)))
        .aggregate(SumAggregator("total_amount"))
        .add_sink(redis_sink("gmv:global:5m_rolling"))
    )
```

---

## 2. Event-Sourced Order Management System

**Context**: A B2B order management system requires a complete audit trail (regulatory requirement), the ability to replay state for bug fixes, and multiple downstream views of order data.

```python
# Domain model: Order aggregate with event sourcing
from dataclasses import dataclass, field
import boto3, json, uuid, time

event_store = EventStore(table_name="order-events", stream_name="order-events-stream")

@dataclass
class OrderItem:
    product_id: str
    quantity: int
    unit_price: float

class OrderService:
    """Application service orchestrating order domain operations."""

    def place_order(self, customer_id: str, items: list[OrderItem]) -> str:
        order_id = str(uuid.uuid4())
        event = DomainEvent(
            aggregate_id=order_id,
            aggregate_type="Order",
            event_type="OrderPlaced",
            data={
                "order_id": order_id,
                "customer_id": customer_id,
                "items": [{"product_id": i.product_id, "qty": i.quantity, "price": i.unit_price} for i in items],
                "total_amount": sum(i.quantity * i.unit_price for i in items),
                "currency": "USD",
            },
        )
        event_store.append(order_id, [event], expected_version=0)
        return order_id

    def ship_order(self, order_id: str, tracking_number: str):
        # Load current state by replaying events
        events = event_store.load(order_id)
        order = Order.reconstitute(events)

        if order.status not in ("confirmed", "payment_received"):
            raise ValueError(f"Cannot ship order in status: {order.status}")

        event = DomainEvent(
            aggregate_id=order_id,
            aggregate_type="Order",
            event_type="OrderShipped",
            data={"order_id": order_id, "tracking_number": tracking_number},
        )
        event_store.append(order_id, [event], expected_version=order.version)

    def get_order_timeline(self, order_id: str) -> list[dict]:
        """Audit trail: full history of everything that happened to an order."""
        events = event_store.load(order_id)
        return [
            {
                "event": e.event_type,
                "at": e.occurred_at,
                "data": e.data,
                "version": i + 1,
            }
            for i, e in enumerate(events)
        ]

    def get_order_as_of(self, order_id: str, as_of_version: int) -> "Order":
        """Time travel: what was the order state at version N?"""
        events = event_store.load(order_id, to_version=as_of_version)
        return Order.reconstitute(events)

# Downstream read model: Lambda triggered by Kinesis (order events stream)
def build_read_models(event: dict, context):
    """Projections builder — maintains multiple read models from the same event stream."""
    order_id = event["aggregate_id"]
    event_type = event["event_type"]
    data = event["data"]

    if event_type == "OrderPlaced":
        # Read model 1: DynamoDB for O(1) order detail lookup
        dynamo_table.put_item(Item={
            "pk": f"ORDER#{order_id}",
            "sk": "DETAIL",
            "status": "placed",
            "customer_id": data["customer_id"],
            "total_amount": str(data["total_amount"]),
            "placed_at": str(event["occurred_at"]),
        })
        # Read model 2: Customer orders index
        dynamo_table.put_item(Item={
            "pk": f"CUSTOMER#{data['customer_id']}",
            "sk": f"ORDER#{order_id}#{event['occurred_at']}",
            "order_id": order_id,
            "status": "placed",
        })
        # Read model 3: Analytics (Firehose → S3)
        firehose.put_record(
            DeliveryStreamName="orders-analytics",
            Record={"Data": json.dumps({**data, "event_type": event_type}).encode()},
        )
```

---

## 3. Data Mesh Implementation for a Multi-Domain Platform

**Context**: A fintech company with 15 product teams (payments, lending, identity, risk, treasury, etc.). Central data team is a bottleneck. Moving to data mesh.

### Platform Layer (Central Team Responsibility)

```python
# Central platform: infrastructure primitives that domain teams use
# NOT: the central team owns domain data pipelines

class DataMeshPlatform:
    """Self-service platform for domain data products."""

    def provision_data_product(
        self,
        domain: str,
        product_name: str,
        schema: dict,
        owner_email: str,
        sla: dict,
    ) -> dict:
        """
        Provision infrastructure for a new data product:
        - S3 prefix with appropriate IAM policies
        - Glue Data Catalog database
        - CloudWatch dashboard template
        - Data quality monitoring baseline
        """
        bucket_prefix = f"s3://data-mesh/{domain}/{product_name}/"

        # Create isolated IAM role for this data product's pipeline
        iam = boto3.client("iam")
        role_arn = iam.create_role(
            RoleName=f"data-product-{domain}-{product_name}",
            AssumeRolePolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": [...]}),
        )["Role"]["Arn"]

        # Create Glue database for this domain's data products
        glue = boto3.client("glue")
        glue.create_database(DatabaseInput={
            "Name": f"{domain}_{product_name}",
            "Description": f"Data product: {product_name} owned by {domain}",
            "Parameters": {
                "owner": owner_email,
                "freshness_sla": sla["freshness"],
                "availability_sla": sla["availability"],
            },
        })

        # Register in central data catalog (discovery)
        self.register_in_catalog({
            "domain": domain,
            "product": product_name,
            "owner": owner_email,
            "schema": schema,
            "location": bucket_prefix,
            "sla": sla,
        })

        return {"s3_prefix": bucket_prefix, "role_arn": role_arn, "database": f"{domain}_{product_name}"}
```

### Domain Team: Payments Data Product

```python
# Payments team owns this pipeline — not the central data team
# They use the platform's self-service primitives

class PaymentsDataProduct:
    """Payments domain: transaction_facts data product."""

    PRODUCT_SPEC = {
        "domain": "payments",
        "product": "transaction_facts",
        "owner": "payments-platform@mycompany.com",
        "sla": {"freshness": "< 1 hour", "availability": "99.5%"},
    }

    def run_pipeline(self, date: str):
        # Payments team ingests from their own OLTP database
        raw_df = spark.read.jdbc(
            url="jdbc:postgresql://payments-db.internal/payments",
            table=f"(SELECT * FROM transactions WHERE date = '{date}') t",
            properties={"user": "pipeline", "password": os.environ["DB_PASSWORD"]},
        )

        # Apply data product standards (enforced by platform SDK)
        clean_df = (raw_df
            .where(F.col("transaction_id").isNotNull())
            .withColumn("_product_version", F.lit("2.1.0"))
            .withColumn("_produced_at", F.current_timestamp())
            .withColumn("_domain", F.lit("payments"))
        )

        # Write to their data product location (isolated S3 prefix)
        clean_df.write.format("delta") \
            .mode("append") \
            .partitionBy("date_partition") \
            .save("s3://data-mesh/payments/transaction_facts/")

        # Publish data product event (for catalog freshness tracking)
        self.publish_freshness_event(date, record_count=clean_df.count())
```

---

## 4. CDC-Powered Real-Time Inventory System

**Context**: Retail company with 500k SKUs. Inventory updates from 1,000 warehouses. Downstream systems need sub-second inventory visibility. Cannot query central inventory DB at scale.

```python
# Inventory CDC pipeline:
# PostgreSQL inventory_db → Debezium → Kafka → Redis (serving) + S3 (analytics)

import redis
import json

redis_client = redis.Redis(host="inventory-cache.internal", port=6379)

class InventoryProjection:
    """Maintains real-time inventory cache from CDC events."""

    def handle_cdc_event(self, cdc_event: dict):
        op = cdc_event.get("__op")  # c=insert, u=update, d=delete, r=snapshot
        record = cdc_event  # Debezium "unwrap" transform gives us flat record

        if op in ("c", "u", "r"):
            sku_id = record["sku_id"]
            warehouse_id = record["warehouse_id"]
            quantity = record["quantity_on_hand"]
            reserved = record["quantity_reserved"]

            # Update per-warehouse inventory in Redis hash
            redis_client.hset(
                f"inventory:{sku_id}",
                mapping={
                    f"warehouse:{warehouse_id}:on_hand": quantity,
                    f"warehouse:{warehouse_id}:reserved": reserved,
                    f"warehouse:{warehouse_id}:available": quantity - reserved,
                    f"warehouse:{warehouse_id}:updated_at": record["updated_at"],
                },
            )

            # Update total available inventory (Redis atomic increment)
            # Use Lua script for atomic read-modify-write
            redis_client.eval("""
                local key = KEYS[1]
                local sku = ARGV[1]
                local new_available = tonumber(ARGV[2])
                local old_available = tonumber(redis.call('hget', key, 'total_available') or '0')
                -- ...recompute total from all warehouse values
            """, 1, f"inventory_totals:{sku_id}", sku_id, quantity - reserved)

        elif op == "d":
            # Warehouse inventory record deleted — zero it out
            sku_id = record["sku_id"]
            warehouse_id = record["warehouse_id"]
            redis_client.hdel(f"inventory:{sku_id}", f"warehouse:{warehouse_id}:on_hand")

    def get_available_inventory(self, sku_id: str, warehouse_ids: list[str] | None = None) -> dict:
        """Serve inventory queries from Redis — O(1), < 5ms."""
        all_fields = redis_client.hgetall(f"inventory:{sku_id}")
        inventory = {}
        for field, value in all_fields.items():
            parts = field.decode().split(":")
            if len(parts) == 3 and parts[2] == "available":
                wh_id = parts[1]
                if warehouse_ids is None or wh_id in warehouse_ids:
                    inventory[wh_id] = int(value)
        return inventory
```

---

## 5. Data Contract Enforcement Pipeline

**Context**: Payments team changed a field type from `string` to `integer`. Downstream ML pipeline silently failed. Building a contract enforcement system to prevent this.

```python
# Schema Registry + contract validation as part of the data pipeline

import json
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.error import SchemaRegistryError
import great_expectations as gx

class DataContractEnforcer:
    def __init__(self, schema_registry_url: str):
        self.sr = SchemaRegistryClient({"url": schema_registry_url})

    def validate_schema_compatibility(self, subject: str, new_schema: str) -> dict:
        """Validate that new schema is backward compatible before deployment."""
        try:
            is_compatible = self.sr.test_compatibility(
                subject_name=subject,
                schema=Schema(new_schema, "AVRO"),
            )
            return {"compatible": is_compatible, "subject": subject}
        except SchemaRegistryError as e:
            return {"compatible": False, "error": str(e)}

    def validate_data_against_contract(
        self,
        df,
        contract: dict,
    ) -> dict:
        """Validate a dataframe against a data contract's quality rules."""
        context = gx.get_context()
        failures = []

        # Check null rates
        for col, rules in contract.get("quality", {}).get("columns", {}).items():
            null_rate = df.filter(df[col].isNull()).count() / df.count()
            max_null = rules.get("max_null_rate", 0.01)
            if null_rate > max_null:
                failures.append({
                    "check": f"null_rate_{col}",
                    "expected": f"< {max_null:.1%}",
                    "actual": f"{null_rate:.1%}",
                })

        # Check row count within expected range
        row_count = df.count()
        expected_min = contract.get("quality", {}).get("expected_daily_min_rows", 0)
        expected_max = contract.get("quality", {}).get("expected_daily_max_rows", float("inf"))
        if not (expected_min <= row_count <= expected_max):
            failures.append({
                "check": "row_count",
                "expected": f"{expected_min:,} - {expected_max:,}",
                "actual": f"{row_count:,}",
            })

        result = {"passed": len(failures) == 0, "failures": failures}
        if failures:
            # Publish contract violation event
            self.publish_violation_event(contract["id"], failures)
            # Optionally: route violating data to quarantine bucket
        return result

# Block pipeline on contract violations (quality gate in Airflow DAG)
@task
def validate_and_fail(date: str):
    df = load_bronze_data(date)
    contract = load_contract("com.mycompany.payments.transactions.v2")
    result = DataContractEnforcer(SCHEMA_REGISTRY_URL).validate_data_against_contract(df, contract)
    if not result["passed"]:
        raise AirflowException(f"Data contract violations: {result['failures']}")
    return {"rows_validated": df.count()}
```
