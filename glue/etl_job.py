"""
FreightFlow historical CSV → Parquet ETL (AWS Glue / PySpark).

Implements the 6 operations from Schema Spec §8 in order:

  1. Drop rows where actual_delivery is blank but status = 'DELIVERED'
  2. Drop rows where customer_email is malformed (no '@' or empty)
  3. Drop rows where actual_delivery < shipment_date
  4. Drop rows where weight_kg <= 0 or pieces <= 0
  5. Normalize mixed date formats (ISO and US MM/DD/YYYY) to ISO across
     shipment_date, estimated_delivery, actual_delivery
  6. Add computed column delay_days = (actual_delivery - estimated_delivery)
     in days, NULL if either side is NULL

Output schema matches Schema Spec §2.

Run with bucket names as job parameters — they are NOT hardcoded:

    --input_bucket  the bucket holding freightflow-historical.csv
    --output_bucket the bucket to write cleaned Parquet to (under cleaned/)
"""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)


INPUT_SCHEMA = StructType([
    StructField('tracking_number', StringType(), True),
    StructField('shipment_date', StringType(), True),
    StructField('estimated_delivery', StringType(), True),
    StructField('actual_delivery', StringType(), True),
    StructField('origin_city', StringType(), True),
    StructField('destination_city', StringType(), True),
    StructField('weight_kg', DoubleType(), True),
    StructField('pieces', IntegerType(), True),
    StructField('status', StringType(), True),
    StructField('customer_email', StringType(), True),
    StructField('driver_employee_id', StringType(), True),
    StructField('route_code', StringType(), True),
    StructField('carrier_tracking_number', StringType(), True),
    StructField('delivery_notes', StringType(), True),
])


def parse_mixed_date(col):
    """Parse a column whose values are either YYYY-MM-DD or MM/DD/YYYY.

    coalesce returns the first non-null, so the ISO format wins when both
    formats parse (rare). Returns NULL when neither parses.
    """
    return F.coalesce(
        F.to_date(col, 'yyyy-MM-dd'),
        F.to_date(col, 'MM/dd/yyyy'),
    )


def main():
    args = getResolvedOptions(
        sys.argv, ['JOB_NAME', 'input_bucket', 'output_bucket']
    )
    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args['JOB_NAME'], args)

    input_path = f"s3://{args['input_bucket']}/freightflow-historical.csv"
    output_path = f"s3://{args['output_bucket']}/cleaned/"

    df = (
        spark.read
        .option('header', 'true')
        .schema(INPUT_SCHEMA)
        .csv(input_path)
    )

    # --- 1. Drop rows where actual_delivery is blank but status = DELIVERED
    df = df.filter(
        ~(
            (F.col('status') == 'DELIVERED')
            & ((F.col('actual_delivery').isNull()) | (F.trim(F.col('actual_delivery')) == ''))
        )
    )

    # --- 2. Drop rows where customer_email is malformed
    email = F.trim(F.col('customer_email'))
    df = df.filter(
        email.isNotNull() & (email != '') & email.contains('@')
    )

    # --- 5. Normalize date columns (done before #3 because #3 needs dates)
    df = (
        df
        .withColumn('shipment_date', parse_mixed_date(F.col('shipment_date')))
        .withColumn('estimated_delivery', parse_mixed_date(F.col('estimated_delivery')))
        .withColumn('actual_delivery', parse_mixed_date(F.col('actual_delivery')))
    )

    # --- 3. Drop rows where actual_delivery < shipment_date
    df = df.filter(
        F.col('actual_delivery').isNull()
        | (F.col('actual_delivery') >= F.col('shipment_date'))
    )

    # --- 4. Drop rows where weight_kg <= 0 or pieces <= 0
    df = df.filter(
        (F.col('weight_kg') > 0) & (F.col('pieces') > 0)
    )

    # --- 6. Computed delay_days column
    df = df.withColumn(
        'delay_days',
        F.when(
            F.col('actual_delivery').isNotNull() & F.col('estimated_delivery').isNotNull(),
            F.datediff(F.col('actual_delivery'), F.col('estimated_delivery')),
        ).otherwise(F.lit(None).cast('int')),
    )

    # Project final column order to match Schema Spec §2 exactly.
    output_columns = [
        'tracking_number', 'shipment_date', 'estimated_delivery', 'actual_delivery',
        'origin_city', 'destination_city', 'weight_kg', 'pieces', 'status',
        'customer_email', 'driver_employee_id', 'route_code',
        'carrier_tracking_number', 'delivery_notes', 'delay_days',
    ]
    df = df.select(*output_columns)

    (
        df.write
        .mode('overwrite')
        .option('compression', 'snappy')
        .parquet(output_path)
    )

    job.commit()


if __name__ == '__main__':
    main()
