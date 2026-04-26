"""Snowflake persistence helpers.

Connection is opened per call — short-lived, reliable, hackathon-safe.
The bridge stays up for the full demo; we just don't want a stale TCP
session blowing up if the laptop goes to sleep mid-rehearsal.
"""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

import snowflake.connector
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(REPO_ROOT / ".env")

log = logging.getLogger("sage.snowflake_io")

T = TypeVar("T")


def _retry(label: str, fn: Callable[[], T], *, attempts: int = 2, backoff_ms: int = 500) -> T:
    """Tiny retry wrapper for write paths. Two attempts is enough — anything
    beyond that and the network is genuinely down; we'll fall back to disk."""
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as err:  # noqa: BLE001 — re-raised below
            last_err = err
            log.warning("snowflake.%s attempt %d/%d failed: %s", label, i, attempts, err)
            if i < attempts:
                time.sleep(backoff_ms / 1000.0)
    assert last_err is not None
    raise last_err


def _disk_backup(label: str, payload: dict[str, Any]) -> Path:
    """Last-ditch JSON dump so a finished session is never lost on the floor."""
    out_dir = REPO_ROOT / "out" / "failed-writes"
    out_dir.mkdir(parents=True, exist_ok=True)
    sid = (payload.get("session_id") or payload.get("analysis_id") or "unknown").replace(":", "_")
    path = out_dir / f"{sid}.{label}.json"
    path.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
    log.error("snowflake.%s — wrote disk backup: %s", label, path)
    return path


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


def get_latest_analysis(patient_id: str) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute(
            """
            SELECT analysis_id, session_id, overall_score, severity, baseline_delta,
                   metrics, flagged_phrases, summary, analyzed_at
              FROM cognitive_analyses
             WHERE patient_id = %s
             ORDER BY analyzed_at DESC
             LIMIT 1
            """,
            (patient_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "analysis_id": row[0],
        "session_id": row[1],
        "overall_score": row[2],
        "severity": row[3],
        "baseline_delta": row[4],
        "metrics": _parse_variant(row[5]),
        "flagged_phrases": _parse_variant(row[6]),
        "summary": row[7],
        "analyzed_at": row[8].isoformat() if row[8] else None,
    }


def get_trend(patient_id: str, days: int = 30) -> list[dict[str, Any]]:
    """Return ordered (oldest → newest) score points for charting."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT analyzed_at, overall_score, severity, session_id
              FROM cognitive_analyses
             WHERE patient_id = %s
               AND analyzed_at >= DATEADD(day, -%s, CURRENT_TIMESTAMP())
             ORDER BY analyzed_at ASC
            """,
            (patient_id, int(days)),
        )
        rows = cur.fetchall()
    return [
        {
            "date": r[0].isoformat() if r[0] else None,
            "score": r[1],
            "severity": r[2],
            "session_id": r[3],
        }
        for r in rows
    ]


def list_sessions_with_scores(patient_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Sessions joined with their cognitive analysis for the dashboard list."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT s.session_id, s.started_at, s.duration_seconds, s.primary_task,
                   a.overall_score, a.severity
              FROM sessions s
              LEFT JOIN cognitive_analyses a
                ON a.session_id = s.session_id
             WHERE s.patient_id = %s
             ORDER BY s.started_at DESC
             LIMIT %s
            """,
            (patient_id, int(limit)),
        )
        rows = cur.fetchall()
    return [
        {
            "session_id": r[0],
            "started_at": r[1].isoformat() if r[1] else None,
            "duration_seconds": r[2],
            "primary_task": r[3],
            "score": r[4],
            "severity": r[5],
        }
        for r in rows
    ]


def get_session_transcript(session_id: str) -> dict[str, Any] | None:
    """Return interactions + analysis flagged_phrases for the transcript view."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT session_id, patient_id, started_at, ended_at, primary_task
              FROM sessions
             WHERE session_id = %s
            """,
            (session_id,),
        )
        sess_row = cur.fetchone()
        if not sess_row:
            return None

        cur.execute(
            """
            SELECT speaker, utterance, created_at
              FROM interactions
             WHERE session_id = %s
             ORDER BY created_at ASC
            """,
            (session_id,),
        )
        i_rows = cur.fetchall()

        cur.execute(
            """
            SELECT overall_score, severity, baseline_delta, summary, flagged_phrases
              FROM cognitive_analyses
             WHERE session_id = %s
             ORDER BY analyzed_at DESC
             LIMIT 1
            """,
            (session_id,),
        )
        a_row = cur.fetchone()

    transcript = [
        {
            "speaker": r[0],
            "utterance": r[1],
            "ts": r[2].isoformat() if r[2] else None,
        }
        for r in i_rows
    ]
    analysis = None
    if a_row:
        analysis = {
            "overall_score": a_row[0],
            "severity": a_row[1],
            "baseline_delta": a_row[2],
            "summary": a_row[3],
            "flagged_phrases": _parse_variant(a_row[4]) or [],
        }

    return {
        "session_id": sess_row[0],
        "patient_id": sess_row[1],
        "started_at": sess_row[2].isoformat() if sess_row[2] else None,
        "ended_at": sess_row[3].isoformat() if sess_row[3] else None,
        "primary_task": sess_row[4],
        "transcript": transcript,
        "flagged_phrases": (analysis or {}).get("flagged_phrases", []),
        "analysis": analysis,
    }


def _parse_variant(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (TypeError, ValueError):
        return val


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

    def _do() -> None:
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

    try:
        _retry("write_session", _do)
    except Exception:
        _disk_backup(
            "session",
            {
                "session_id": session_id,
                "patient_id": patient_id,
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "transcript": transcript,
                "duration_seconds": duration,
                "primary_task": primary_task,
            },
        )
        raise


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
    analysis_id = analysis.get("analysis_id") or _uuid()
    analyzed_at = analysis.get("analyzed_at") or datetime.now(timezone.utc)
    if isinstance(analyzed_at, str):
        analyzed_at = datetime.fromisoformat(analyzed_at.replace("Z", "+00:00"))

    def _do() -> None:
        with cursor() as cur:
            cur.execute(
                """
                INSERT INTO cognitive_analyses
                  (analysis_id, session_id, patient_id, overall_score, severity, baseline_delta,
                   metrics, flagged_phrases, summary, analyzed_at)
                SELECT %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s), %s, %s
                """,
                (
                    analysis_id,
                    analysis["session_id"],
                    analysis["patient_id"],
                    int(analysis["overall_score"]),
                    analysis.get("severity", "watch"),
                    int(analysis.get("baseline_delta", 0)),
                    json.dumps(analysis.get("metrics") or {}),
                    json.dumps(analysis.get("flagged_phrases") or []),
                    analysis.get("summary", ""),
                    analyzed_at.replace(tzinfo=None),
                ),
            )

    try:
        _retry("write_analysis", _do)
    except Exception:
        _disk_backup(
            "analysis",
            {
                **{k: v for k, v in analysis.items() if k != "analyzed_at"},
                "analysis_id": analysis_id,
                "analyzed_at": analyzed_at.isoformat(),
            },
        )
        raise


def _uuid() -> str:
    import uuid

    return uuid.uuid4().hex
