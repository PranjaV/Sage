"""Snowflake persistence helpers.

Connection is opened per call — short-lived, reliable, hackathon-safe.
The bridge stays up for the full demo; we just don't want a stale TCP
session blowing up if the laptop goes to sleep mid-rehearsal.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import snowflake.connector
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(REPO_ROOT / ".env")

log = logging.getLogger("sage.snowflake_io")


def _connect():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        role=os.environ["SNOWFLAKE_ROLE"],
        client_session_keep_alive=False,
    )


@contextmanager
def cursor():
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()
    finally:
        conn.close()


# ─── reads ────────────────────────────────────────────────────────────────────


def get_patient(patient_id: str) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute(
            """
            SELECT patient_id, name, age, caregiver_name, baseline_score, consent_status
              FROM patients
             WHERE patient_id = %s
            """,
            (patient_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "patient_id": row[0],
        "name": row[1],
        "age": row[2],
        "caregiver_name": row[3],
        "baseline_score": row[4],
        "consent_status": row[5],
    }


def get_profile(patient_id: str) -> dict[str, Any] | None:
    """Return the patient profile with all VARIANT fields parsed back to dicts/lists."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT patient_id, doctors, appointments, pharmacy, address, common_items
              FROM patient_profile
             WHERE patient_id = %s
            """,
            (patient_id,),
        )
        row = cur.fetchone()
    if not row:
        return None

    def _parse(val):
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return val
        try:
            return json.loads(val)
        except (TypeError, ValueError):
            return val

    return {
        "patient_id": row[0],
        "doctors": _parse(row[1]),
        "appointments": _parse(row[2]),
        "pharmacy": _parse(row[3]),
        "address": _parse(row[4]),
        "common_items": _parse(row[5]),
    }


def list_recent_sessions(patient_id: str, limit: int = 30) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute(
            """
            SELECT session_id, started_at, ended_at, duration_seconds, primary_task
              FROM sessions
             WHERE patient_id = %s
             ORDER BY started_at DESC
             LIMIT %s
            """,
            (patient_id, limit),
        )
        rows = cur.fetchall()
    return [
        {
            "session_id": r[0],
            "started_at": r[1].isoformat() if r[1] else None,
            "ended_at": r[2].isoformat() if r[2] else None,
            "duration_seconds": r[3],
            "primary_task": r[4],
        }
        for r in rows
    ]


# ─── writes ───────────────────────────────────────────────────────────────────


def upsert_patient(patient: dict[str, Any]) -> None:
    with cursor() as cur:
        cur.execute(
            "DELETE FROM patients WHERE patient_id = %s",
            (patient["patient_id"],),
        )
        cur.execute(
            """
            INSERT INTO patients (patient_id, name, age, caregiver_name, baseline_score, consent_status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                patient["patient_id"],
                patient["name"],
                patient["age"],
                patient["caregiver_name"],
                patient["baseline_score"],
                patient.get("consent_status", "active"),
            ),
        )


def upsert_profile(profile: dict[str, Any]) -> None:
    """VARIANT columns need PARSE_JSON; bind JSON strings via %s."""
    pid = profile["patient_id"]
    with cursor() as cur:
        cur.execute("DELETE FROM patient_profile WHERE patient_id = %s", (pid,))
        cur.execute(
            """
            INSERT INTO patient_profile (patient_id, doctors, appointments, pharmacy, address, common_items)
            SELECT %s, PARSE_JSON(%s), PARSE_JSON(%s), PARSE_JSON(%s), PARSE_JSON(%s), PARSE_JSON(%s)
            """,
            (
                pid,
                json.dumps(profile.get("doctors") or []),
                json.dumps(profile.get("appointments") or []),
                json.dumps(profile.get("pharmacy") or {}),
                json.dumps(profile.get("address") or {}),
                json.dumps(profile.get("common_items") or []),
            ),
        )


def write_session(
    session_id: str,
    patient_id: str,
    started_at: datetime,
    ended_at: datetime,
    transcript: str,
    primary_task: str | None = None,
) -> None:
    duration = max(0, int((ended_at - started_at).total_seconds()))
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO sessions
              (session_id, patient_id, started_at, ended_at, transcript, duration_seconds, primary_task)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                patient_id,
                started_at.replace(tzinfo=None),
                ended_at.replace(tzinfo=None),
                transcript,
                duration,
                primary_task,
            ),
        )


def write_interactions(session_id: str, items: Iterable[dict[str, Any]]) -> int:
    """Bulk insert interactions. `items` = [{interaction_id?, speaker, utterance, ts}]."""
    rows = []
    for it in items:
        ts = it.get("ts")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts is None:
            ts = datetime.now(timezone.utc)
        rows.append(
            (
                it.get("interaction_id") or _uuid(),
                session_id,
                it["speaker"],
                it["utterance"],
                ts.replace(tzinfo=None),
            )
        )
    if not rows:
        return 0
    with cursor() as cur:
        cur.executemany(
            """
            INSERT INTO interactions (interaction_id, session_id, speaker, utterance, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            rows,
        )
    return len(rows)


def write_analysis(analysis: dict[str, Any]) -> None:
    """analysis matches PRD §8 shape."""
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO cognitive_analyses
              (analysis_id, session_id, patient_id, overall_score, severity, baseline_delta,
               metrics, flagged_phrases, summary, analyzed_at)
            SELECT %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s), %s, %s
            """,
            (
                analysis.get("analysis_id") or _uuid(),
                analysis["session_id"],
                analysis["patient_id"],
                int(analysis["overall_score"]),
                analysis.get("severity", "watch"),
                int(analysis.get("baseline_delta", 0)),
                json.dumps(analysis.get("metrics") or {}),
                json.dumps(analysis.get("flagged_phrases") or []),
                analysis.get("summary", ""),
                (analysis.get("analyzed_at") or datetime.now(timezone.utc)).replace(tzinfo=None),
            ),
        )


def _uuid() -> str:
    import uuid

    return uuid.uuid4().hex
