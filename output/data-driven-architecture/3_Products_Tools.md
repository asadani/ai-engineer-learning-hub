# Products & Tools

## Apache Kafka / Amazon MSK

The de facto standard for event streaming. MSK is managed Kafka on AWS — eliminates broker management while keeping the full Kafka API.

```python
# MSK (Amazon Managed Streaming for Kafka) cluster config
import boto3

kafka_client = boto3.client("kafka", region_name="us-east-1")

# Create MSK cluster
response = kafka_client.create_cluster_v2(
    ClusterName="production-events",
    Provisioned={
        "BrokerNodeGroupInfo": {
            "InstanceType": "kafka.m5.2xlarge",  # 8 vCPU, 32GB RAM per broker
            "ClientSubnets": ["subnet-abc123", "subnet-def456", "subnet-ghi789"],
            "StorageInfo": {"EbsStorageInfo": {"VolumeSize": 1000}},  # 1TB per broker
        },
        "NumberOfBrokerNodes": 3,    # 3 AZs for HA
        "KafkaVersion": "3.6.0",
        "EncryptionInfo": {
            "EncryptionInTransit": {"ClientBroker": "TLS", "InCluster": True},
        },
        "EnhancedMonitoring": "PER_TOPIC_PER_BROKER",
    },
)

# MSK Serverless: pay per usage, auto-scales, zero broker management
# Limit: 200 MB/s throughput, not all Kafka features
response = kafka_client.create_cluster_v2(
    ClusterName="dev-events-serverless",
    Serverless={
        "VpcConfigs": [{"SubnetIds": ["subnet-abc123"], "SecurityGroupIds": ["sg-123"]}],
        "ClientAuthentication": {"Sasl": {"Iam": {"Enabled": True}}},
    },
)

# Kafka sizing rules of thumb:
# 1 kafka.m5.2xlarge broker: ~200 MB/s sustained throughput, 500 MB/s peak
# For 1 GB/s ingestion: 5-6 brokers + 20% headroom
# Retention: 1 TB/broker × 3 brokers × 7-day retention → max ~1 TB/day throughput
# Partitions: 1 partition per consumer thread for max parallelism
```

**MSK vs self-managed Kafka vs Confluent Cloud:**

| Dimension | Self-managed Kafka | MSK | MSK Serverless | Confluent Cloud |
|-----------|------------------|-----|---------------|----------------|
| Ops overhead | High | Low | Minimal | Minimal |
| Cost | Infra only | 25% over EC2 | Pay per use | Most expensive |
| Features | Full | Full | Limited | Full + extras |
| Schema registry | Manual | Manual | N/A | Managed |
| AWS integration | Manual | Native (IAM, VPC) | Native | Good but cross-cloud |

---

## Amazon Kinesis

AWS-native streaming that integrates natively with Lambda, Firehose, and Analytics. Simpler than Kafka for AWS-only architectures.

```python
import boto3
import json, base64, time

kinesis = boto3.client("kinesis", region_name="us-east-1")

# Kinesis Data Streams: managed shards, real-time
kinesis.put_record(
    StreamName="order-events",
    Data=json.dumps({"order_id": "ORD-001", "status": "placed", "total": 99.99}),
    PartitionKey="ORD-001",  # hashed to determine shard; same key → same shard → ordered
)

# Batch writes (up to 500 records per call, up to 5MB total)
records = [
    {"Data": json.dumps(event), "PartitionKey": event["order_id"]}
    for event in events
]
kinesis.put_records(StreamName="order-events", Records=records)

# Kinesis Firehose: S3/Redshift delivery with auto-buffering, no consumer management
firehose = boto3.client("firehose", region_name="us-east-1")
firehose.create_delivery_stream(
    DeliveryStreamName="orders-to-s3",
    S3DestinationConfiguration={
        "RoleARN": "arn:aws:iam::123456789:role/FirehoseRole",
        "BucketARN": "arn:aws:s3:::my-datalake",
        "Prefix": "bronze/orders/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/",
        "BufferingHints": {
            "SizeInMBs": 128,    # buffer 128MB before writing to S3
            "IntervalInSeconds": 300,  # or flush every 5 min
        },
        "CompressionFormat": "SNAPPY",
        "DataFormatConversionConfiguration": {
            "Enabled": True,
            # Auto-convert JSON → Parquet on delivery (schema from Glue Data Catalog)
            "OutputFormatConfiguration": {"Serializer": {"ParquetSerDe": {}}},
            "SchemaConfiguration": {
                "DatabaseName": "orders_db",
                "TableName": "orders",
                "RoleARN": "arn:aws:iam::123456789:role/FirehoseRole",
            },
        },
    },
)

# Kinesis Data Analytics (managed Flink)
# Kinesis limits: 1 MB/s write per shard, 2 MB/s read per shard
# Scaling: add shards (resharding) — manual or via auto-scaling trigger
```

---

## Apache Spark / AWS Glue

Batch and micro-batch processing at scale. Glue is managed Spark on AWS with auto-scaling and native Glue Data Catalog integration.

```python
# AWS Glue Spark job
import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from delta.tables import DeltaTable

args = getResolvedOptions(sys.argv, ["JOB_NAME", "source_date"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

# Read from Glue Data Catalog (auto-discovered schema, S3 partitioned data)
bronze_df = glueContext.create_dynamic_frame.from_catalog(
    database="bronze_db",
    table_name="orders",
    push_down_predicate=f"date_partition = '{args['source_date']}'",
    transformation_ctx="bronze_orders",
).toDF()

# Transform
silver_df = (bronze_df
    .withColumn("total_amount", F.col("total_amount").cast("decimal(10,2)"))
    .where(F.col("order_id").isNotNull())
    .dropDuplicates(["order_id", "event_type"])
)

# Write to Silver with Delta Lake
silver_df.write.format("delta") \
    .mode("append") \
    .partitionBy("date_partition") \
    .save("s3://my-datalake/silver/orders/")

job.commit()

# Glue job configuration:
# G.1X: 4 vCPU, 16GB RAM per DPU — good for most ETL
# G.2X: 8 vCPU, 32GB RAM — memory-intensive joins/shuffles
# Auto-scaling: Glue 3.0+ supports dynamic executor scaling
# Cost: $0.44/DPU-hour (G.1X), $0.88/DPU-hour (G.2X)
```

---

## Delta Lake / Apache Iceberg

Open table formats that bring ACID transactions, schema evolution, and time travel to data lakes on S3.

```python
from delta.tables import DeltaTable
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .getOrCreate()

TABLE_PATH = "s3://my-datalake/gold/orders/"

# MERGE (upsert): idempotent reprocessing
DeltaTable.forPath(spark, TABLE_PATH) \
    .alias("target") \
    .merge(updates_df.alias("source"), "target.order_id = source.order_id") \
    .whenMatchedUpdateAll() \
    .whenNotMatchedInsertAll() \
    .whenNotMatchedBySourceDelete()  # delete rows no longer in source (for SCD Type 1) \
    .execute()

# Time travel: read data as of a point in time
historical_df = spark.read.format("delta") \
    .option("timestampAsOf", "2025-01-01 00:00:00") \
    .load(TABLE_PATH)

# Or by version number
historical_df = spark.read.format("delta") \
    .option("versionAsOf", 42) \
    .load(TABLE_PATH)

# Vacuum: remove old files (default 7-day retention)
DeltaTable.forPath(spark, TABLE_PATH).vacuum(retentionHours=168)

# OPTIMIZE: compact small files (the small file problem)
DeltaTable.forPath(spark, TABLE_PATH).optimize().executeCompaction()

# Z-ORDER: co-locate related data for query skipping
DeltaTable.forPath(spark, TABLE_PATH).optimize().executeZOrderBy("customer_id", "date_partition")
```

**Delta Lake vs Apache Iceberg:**

| Dimension | Delta Lake | Apache Iceberg |
|-----------|-----------|---------------|
| Origin | Databricks (open-sourced) | Netflix (open-sourced to Apache) |
| AWS integration | Works on S3; Glue Catalog via manifest | Native AWS S3 Tables, Glue integration |
| Multi-engine | Spark, Presto, Trino, Athena | Spark, Trino, Flink, Athena, Hive |
| Hidden partitioning | No (must specify partition columns) | Yes (partition pruning without rewriting queries) |
| AWS preference | Widely used | AWS S3 Tables uses Iceberg natively |

---

## dbt (Data Build Tool)

SQL-first transformation framework. Manages dependency ordering, testing, documentation, and lineage for SQL transformations.

```sql
-- models/silver/orders.sql
{{ config(
    materialized='incremental',
    unique_key='order_id',
    partition_by={'field': 'date_partition', 'data_type': 'date'},
    cluster_by=['merchant_id'],
    on_schema_change='sync_all_columns'
) }}

WITH source AS (
    SELECT *
    FROM {{ source('bronze', 'orders') }}
    WHERE date_partition = '{{ var("run_date") }}'
      AND order_id IS NOT NULL
),

deduped AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY event_time DESC) AS rn
    FROM source
),

final AS (
    SELECT
        order_id,
        customer_id,
        merchant_id,
        CAST(total_amount AS DECIMAL(10,2)) AS total_amount,
        CAST(event_time AS TIMESTAMP) AS event_time,
        date_partition,
        CURRENT_TIMESTAMP AS silver_processed_at
    FROM deduped
    WHERE rn = 1
)

SELECT * FROM final

{% if is_incremental() %}
WHERE date_partition >= (SELECT MAX(date_partition) FROM {{ this }})
{% endif %}
```

```yaml
# schema.yml — data quality tests baked into the model
models:
  - name: orders
    description: "Cleaned, deduplicated order events"
    columns:
      - name: order_id
        description: "Unique order identifier"
        tests:
          - unique
          - not_null
      - name: total_amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1000000
      - name: status
        tests:
          - accepted_values:
              values: ['placed', 'confirmed', 'shipped', 'delivered', 'cancelled']
```

---

## AWS Glue Data Catalog

Central metadata repository. Integrates with S3, Redshift, RDS, and most Glue/Athena/EMR workflows.

```python
import boto3

glue = boto3.client("glue", region_name="us-east-1")

# Create/update table metadata (usually auto-discovered via Glue Crawlers)
glue.create_table(
    DatabaseName="silver_db",
    TableInput={
        "Name": "orders",
        "StorageDescriptor": {
            "Columns": [
                {"Name": "order_id",     "Type": "string"},
                {"Name": "customer_id",  "Type": "string"},
                {"Name": "total_amount", "Type": "decimal(10,2)"},
                {"Name": "event_time",   "Type": "timestamp"},
            ],
            "Location": "s3://my-datalake/silver/orders/",
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"},
        },
        "PartitionKeys": [{"Name": "date_partition", "Type": "date"}],
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": "parquet",
            "delta.minReaderVersion": "1",  # Delta Lake table marker
        },
    },
)

# Query with Athena (serverless SQL on S3)
athena = boto3.client("athena", region_name="us-east-1")
response = athena.start_query_execution(
    QueryString="SELECT merchant_id, SUM(total_amount) FROM silver_db.orders WHERE date_partition = '2025-03-01' GROUP BY 1",
    QueryExecutionContext={"Database": "silver_db"},
    ResultConfiguration={"OutputLocation": "s3://athena-results/"},
    WorkGroup="primary",
)
# Athena pricing: $5/TB scanned (use partitioning + column pruning to reduce scanned data)
```

---

## Tool Selection Guide

| Need | AWS-native | Open Source | Managed |
|------|-----------|------------|---------|
| Event streaming | Kinesis | **Kafka / MSK** | Confluent |
| Batch ETL | Glue | Spark | Databricks |
| Stream processing | Kinesis Analytics (Flink) | **Flink** / Spark SS | Confluent Flink |
| CDC | DMS | **Debezium** | Fivetran |
| Table format | — | **Delta Lake / Iceberg** | Databricks / AWS S3 Tables |
| SQL transformations | — | **dbt** | dbt Cloud |
| Data catalog | Glue Data Catalog | Apache Atlas | Alation, Collibra |
| Pipeline orchestration | MWAA (Airflow) | **Airflow** / Dagster | Prefect, Astronomer |
| Batch connectors | Glue | **Airbyte** | Fivetran |
| Query engine | Athena | Trino / Presto | Starburst |
