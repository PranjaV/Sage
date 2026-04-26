"""Cortex Analyst REST client.

Sage's caregiver dashboard sends a natural-language question; Cortex Analyst
returns a SQL statement grounded in our semantic model. We then execute the
SQL ourselves and summarize the result row(s) into one human sentence.

Auth: re-uses the active snowflake-connector session token. No extra creds.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from sage import snowflake_io

log = logging.getLogger("sage.cortex")

SEMANTIC_MODEL_FILE = os.getenv(
    "SAGE_SEMANTIC_MODEL_FILE",
    "@SAGE_DB.CORE.SAGE_STAGE/cortex/cortex_semantic.yaml",
)


def _account_host() -> str:
    """Build the REST host from SNOWFLAKE_ACCOUNT (e.g. xy12345.us-east-1)."""
    account = os.environ["SNOWFLAKE_ACCOUNT"]
    # Snowsight account locators don't carry .snowflakecomputing.com — add it.
    if ".snowflakecomputing.com" in account:
        return f"https://{account}"
    return f"https://{account}.snowflakecomputing.com"


def ask(question: str) -> dict[str, Any]:
    """Call Cortex Analyst, execute the returned SQL, and return everything.

    Output:
      {
        question, sql, rows: [...], answer_text, raw_message,
      }
    """
    payload = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": question}]},
        ],
        "semantic_model_file": SEMANTIC_MODEL_FILE,
    }

    # Use the connector's session token directly to avoid juggling OAuth.
    conn = snowflake_io._connect()  # short-lived, closed below
    try:
        token = conn.rest.token  # type: ignore[attr-defined]
        url = f"{_account_host()}/api/v2/cortex/analyst/message"
        headers = {
            "Authorization": f'Snowflake Token="{token}"',
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    sql, message_text = _extract_sql_and_text(data)
    rows: list[dict[str, Any]] = []
    if sql:
        rows = _run_sql(sql)
    answer = _compose_answer(question, sql, rows, message_text)

    return {
        "question": question,
        "sql": sql,
        "rows": rows,
        "answer_text": answer,
        "raw_message": message_text,
    }


def _extract_sql_and_text(data: dict[str, Any]) -> tuple[str, str]:
    """Cortex returns a message with content blocks of types 'text' and 'sql'."""
    msg = data.get("message") or {}
    content = msg.get("content") or []
    sql = ""
    text_parts: list[str] = []
    for block in content:
        btype = block.get("type")
        if btype == "sql":
            sql = (block.get("statement") or block.get("sql") or "").strip()
        elif btype == "text":
            text_parts.append(block.get("text") or "")
        elif btype == "suggestions":
            # surface suggestions to the caller as plain text
            for s in block.get("suggestions") or []:
                text_parts.append(f"(suggestion) {s}")
    return sql, "\n".join(p for p in text_parts if p)


def _run_sql(sql: str) -> list[dict[str, Any]]:
    """Execute the Cortex-generated SQL and return rows as dicts.

    Cortex Analyst guarantees the SQL is read-only against the semantic
    model's tables, but we still apply a simple LIMIT cap below."""
    capped = sql if " LIMIT " in sql.upper() else f"{sql.rstrip().rstrip(';')}\nLIMIT 200"
    with snowflake_io.cursor() as cur:
        cur.execute(capped)
        cols = [c[0].lower() for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _compose_answer(question: str, sql: str, rows: list[dict[str, Any]], message_text: str) -> str:
    """Turn rows into one short caregiver-friendly sentence using gpt-4.1-mini."""
    if not rows and not message_text:
        return "I couldn't find any matching sessions for that question yet."

    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are summarizing analytics for a caregiver. Write ONE plain sentence "
                        "(max 25 words). Use only the numbers in the rows. Never use clinical "
                        "language (no 'diagnosis', 'decline', 'impairment', 'dementia')."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": question,
                            "rows": rows[:20],
                            "cortex_text": message_text,
                        }
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=120,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as err:
        log.warning("answer summarization failed: %s", err)
        if rows:
            return f"Returned {len(rows)} row(s). First row: {rows[0]}"
        return message_text or "No answer available."
