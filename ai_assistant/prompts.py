"""
Bedrock prompt template (Schema Spec §6.5).

NOTE: This passes the **Athena** schema (Schema Spec §2) — not the Django
schema. The historical Parquet output has `delay_days` and uses
`driver_employee_id` / `route_code` rather than FK IDs.
"""

SCHEMA_CONTEXT = """\
You are a SQL generator. Generate ONLY a SELECT query (no INSERT, UPDATE, DELETE, DROP).
Table: shipments
Columns:
  tracking_number (string)
  shipment_date (date)
  estimated_delivery (date)
  actual_delivery (date, nullable)
  origin_city (string)
  destination_city (string)
  weight_kg (double)
  pieces (int)
  status (string: PENDING, PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED, DELAYED, CANCELLED)
  customer_email (string)
  driver_employee_id (string)
  route_code (string)
  carrier_tracking_number (string)
  delivery_notes (string)
  delay_days (int)
"""


def build_user_prompt(question: str) -> str:
    return (
        f"{SCHEMA_CONTEXT}\n"
        f"Question: {question}\n\n"
        "Reply with only the SQL — no commentary, no markdown fences."
    )
