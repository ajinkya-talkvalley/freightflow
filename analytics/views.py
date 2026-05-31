"""
Historical analytics view — runs canned Athena queries against the cleaned
Parquet output produced by the Glue ETL job.
"""
from django.shortcuts import render

from ai_assistant.views import validate_select_only

from .athena_client import (
    AthenaNotConfigured,
    AthenaQueryError,
    is_configured,
    run_query,
)

# Canned queries students can pick from. Names map to descriptions; values
# are the SQL strings. Adjust the table name to match your Glue catalog.
CANNED_QUERIES = {
    'top_routes_by_volume': (
        'Top 10 origin→destination routes by shipment count',
        """
        SELECT origin_city, destination_city, COUNT(*) AS shipments
        FROM shipments
        GROUP BY origin_city, destination_city
        ORDER BY shipments DESC
        LIMIT 10
        """,
    ),
    'delays_by_city': (
        'Average delay (days) per origin city — delivered shipments only',
        """
        SELECT origin_city, AVG(delay_days) AS avg_delay_days, COUNT(*) AS shipments
        FROM shipments
        WHERE status = 'DELIVERED' AND delay_days IS NOT NULL
        GROUP BY origin_city
        ORDER BY avg_delay_days DESC
        """,
    ),
    'driver_volume': (
        'Top 10 drivers by total shipments handled',
        """
        SELECT driver_employee_id, COUNT(*) AS shipments
        FROM shipments
        GROUP BY driver_employee_id
        ORDER BY shipments DESC
        LIMIT 10
        """,
    ),
}


def historical(request):
    context = {
        'configured': is_configured(),
        'canned': [(k, label) for k, (label, _) in CANNED_QUERIES.items()],
        'selected': None,
        'sql': None,
        'columns': None,
        'rows': None,
        'error': None,
    }

    if not context['configured']:
        return render(request, 'analytics/historical.html', context)

    selected = request.GET.get('q')
    if selected and selected in CANNED_QUERIES:
        label, sql = CANNED_QUERIES[selected]
        try:
            sql_clean = validate_select_only(sql)
            columns, rows = run_query(sql_clean, timeout_seconds=30)
            context.update({
                'selected': selected,
                'sql': sql_clean,
                'columns': columns,
                'rows': rows,
            })
        except (AthenaNotConfigured, AthenaQueryError, TimeoutError, ValueError) as exc:
            context['error'] = str(exc)
            context['selected'] = selected
            context['sql'] = sql

    return render(request, 'analytics/historical.html', context)
