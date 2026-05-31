"""
AI assistant view — calls Bedrock to translate a natural-language question
into SQL, validates the SQL as SELECT-only, executes it against Athena.
"""
import json
import re

import boto3
import sqlparse
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.shortcuts import render

from analytics.athena_client import (
    AthenaNotConfigured,
    AthenaQueryError,
    is_configured as athena_configured,
    run_query,
)

from .prompts import build_user_prompt


# -- SQL safety gate ---------------------------------------------------------
# sqlparse handles structural validation; the regex denylist catches anything
# that slips past (e.g. comment-stripped reserved words). Comments are
# stripped before the regex runs so /* DROP */ cannot smuggle keywords.
FORBIDDEN = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|MERGE|CALL|USE|MSCK)\b',
    re.IGNORECASE,
)


def validate_select_only(sql: str) -> str:
    """Raise ValueError unless `sql` is a single SELECT/WITH statement."""
    if not sql or not sql.strip():
        raise ValueError('empty SQL')
    cleaned = sqlparse.format(sql, strip_comments=True).strip().rstrip(';').strip()
    parsed = sqlparse.parse(cleaned)
    if len(parsed) != 1:
        raise ValueError('exactly one statement required')
    first = parsed[0].token_first(skip_cm=True)
    if first is None or first.normalized.upper() not in ('SELECT', 'WITH'):
        raise ValueError('only SELECT/WITH statements are permitted')
    if FORBIDDEN.search(cleaned):
        raise ValueError('forbidden keyword detected')
    if ';' in cleaned:
        raise ValueError('statement chaining is not permitted')
    return cleaned


# -- Bedrock call ------------------------------------------------------------
def bedrock_configured():
    return bool(settings.BEDROCK_MODEL_ID and settings.BEDROCK_REGION)


def _strip_sql_fences(text: str) -> str:
    """Remove ```sql ... ``` fencing if the model added it."""
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```[a-zA-Z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
    return text.strip()


def generate_sql(question: str) -> str:
    """Call Bedrock (Claude messages API) and return the model's SQL text."""
    client = boto3.client('bedrock-runtime', region_name=settings.BEDROCK_REGION)
    body = {
        'anthropic_version': 'bedrock-2023-05-31',
        'max_tokens': 512,
        'messages': [
            {'role': 'user', 'content': build_user_prompt(question)},
        ],
    }
    response = client.invoke_model(
        modelId=settings.BEDROCK_MODEL_ID,
        contentType='application/json',
        accept='application/json',
        body=json.dumps(body),
    )
    payload = json.loads(response['body'].read())
    # Claude messages API returns content as a list of blocks.
    blocks = payload.get('content', [])
    text_parts = [b.get('text', '') for b in blocks if b.get('type') == 'text']
    return _strip_sql_fences('\n'.join(text_parts))


# -- View --------------------------------------------------------------------
def assistant(request):
    context = {
        'bedrock_ready': bedrock_configured(),
        'athena_ready': athena_configured(),
        'question': '',
        'sql': None,
        'columns': None,
        'rows': None,
        'error': None,
    }

    if not context['bedrock_ready']:
        context['error'] = (
            'Bedrock not configured. Set BEDROCK_MODEL_ID and BEDROCK_REGION in .env.'
        )
        return render(request, 'ai_assistant/assistant.html', context)

    if request.method == 'POST':
        question = (request.POST.get('question') or '').strip()
        context['question'] = question
        if not question:
            context['error'] = 'Please enter a question.'
        else:
            try:
                raw_sql = generate_sql(question)
                sql_clean = validate_select_only(raw_sql)
                context['sql'] = sql_clean
                if context['athena_ready']:
                    columns, rows = run_query(sql_clean, timeout_seconds=30)
                    context['columns'] = columns
                    context['rows'] = rows
                else:
                    context['error'] = (
                        'Athena not configured — generated SQL only. '
                        'Set ATHENA_DATABASE and ATHENA_OUTPUT_LOCATION to execute.'
                    )
            except ValueError as exc:
                context['error'] = f'Generated SQL rejected: {exc}'
            except (BotoCoreError, ClientError) as exc:
                context['error'] = f'Bedrock call failed: {exc}'
            except (AthenaNotConfigured, AthenaQueryError, TimeoutError) as exc:
                context['error'] = f'Athena query failed: {exc}'

    return render(request, 'ai_assistant/assistant.html', context)
