"""
Thin Athena client used by both the analytics views and the AI assistant.

Synchronous in-view: start_query_execution → poll get_query_execution
every 500ms → get_query_results on SUCCEEDED. Enforces a 30-second
timeout by calling stop_query_execution and raising TimeoutError.
"""
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings


class AthenaNotConfigured(RuntimeError):
    pass


class AthenaQueryError(RuntimeError):
    pass


def is_configured():
    return bool(settings.ATHENA_DATABASE and settings.ATHENA_OUTPUT_LOCATION)


def run_query(sql, timeout_seconds=30, max_results=1000):
    """Run a SQL query against Athena and return (columns, rows).

    `rows` is a list of lists of strings (Athena returns everything as
    strings in the API). The caller is responsible for parsing types.
    """
    if not is_configured():
        raise AthenaNotConfigured(
            'ATHENA_DATABASE and ATHENA_OUTPUT_LOCATION must be set in .env'
        )

    client = boto3.client('athena', region_name=settings.AWS_REGION)

    start_kwargs = {
        'QueryString': sql,
        'QueryExecutionContext': {'Database': settings.ATHENA_DATABASE},
        'ResultConfiguration': {'OutputLocation': settings.ATHENA_OUTPUT_LOCATION},
    }
    if settings.ATHENA_WORKGROUP:
        start_kwargs['WorkGroup'] = settings.ATHENA_WORKGROUP

    try:
        execution = client.start_query_execution(**start_kwargs)
    except (BotoCoreError, ClientError) as exc:
        raise AthenaQueryError(f'start_query_execution failed: {exc}') from exc

    query_id = execution['QueryExecutionId']
    deadline = time.monotonic() + timeout_seconds

    while True:
        try:
            status = client.get_query_execution(QueryExecutionId=query_id)
        except (BotoCoreError, ClientError) as exc:
            raise AthenaQueryError(f'get_query_execution failed: {exc}') from exc

        state = status['QueryExecution']['Status']['State']
        if state == 'SUCCEEDED':
            break
        if state in ('FAILED', 'CANCELLED'):
            reason = status['QueryExecution']['Status'].get('StateChangeReason', state)
            raise AthenaQueryError(f'Athena query {state.lower()}: {reason}')

        if time.monotonic() >= deadline:
            try:
                client.stop_query_execution(QueryExecutionId=query_id)
            except (BotoCoreError, ClientError):
                pass
            raise TimeoutError(f'Athena query exceeded {timeout_seconds}s timeout')

        time.sleep(0.5)

    try:
        result = client.get_query_results(QueryExecutionId=query_id, MaxResults=max_results)
    except (BotoCoreError, ClientError) as exc:
        raise AthenaQueryError(f'get_query_results failed: {exc}') from exc

    rows = result['ResultSet']['Rows']
    if not rows:
        return [], []
    columns = [c.get('VarCharValue', '') for c in rows[0]['Data']]
    data = [
        [c.get('VarCharValue', '') for c in r['Data']]
        for r in rows[1:]
    ]
    return columns, data
