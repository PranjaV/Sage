"""Post-session cognitive analysis.

Two pieces:
  1. `generate_summary` — gpt-5-mini turns raw metrics into a short, calm,
     non-clinical caregiver-facing paragraph + 1–2 gentle follow-ups.
  2. `analyze_session` — the full pipeline: deterministic score + LLM
     summary + Snowflake write + bridge ping. Called from /session/end.

The summary prompt is deliberately strict about language. Sage is not a
clinician and the caregiver UI must never imply otherwise.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from openai import OpenAI

from sage import snowflake_io, usage as usage_log
from sage.cognitive_score import score_session

log = logging.getLogger("sage.cognitive")

SUMMARY_MODEL = "gpt-5-mini"
BRIDGE_URL = os.getenv("BRIDGE_URL", "http://localhost:3001")

_openai_client: OpenAI | None = None


def _client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai_client


SUMMARY_SYSTEM = """You are writing a caregiver-facing summary of a voice session with {patient_name}.

Hard rules:
- Calm, factual, non-clinical. 2–3 sentences max.
- NEVER use these words: diagnosis, dementia, impairment, decline, deterioration, cognitive disorder, Alzheimer, monitoring, screening.
- Do not infer a medical condition. Describe observed conversation patterns only.
- End with one suggested gentle follow-up (e.g. "ask about the appointment again tomorrow", "share the highlight at dinner").
- Never invent details that are not in the transcript or metrics.

Return ONLY a JSON object:
{{"session_summary": "<2-3 sentences>", "suggested_exercises": ["<short suggestion>", "<optional second>"]}}"""


def generate_summary(
    transcript_text: str,
    metrics: dict[str, Any],
    flagged_phrases: list[dict[str, Any]],
    patient_name: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Return {session_summary, suggested_exercises} from gpt-5-mini.

    On any failure, returns a safe default so the pipeline can still write
    the deterministic score to Snowflake."""
    excerpt = (transcript_text or "")[:600]
    user_payload = {
        "patient_name": patient_name,
        "metrics": metrics,
        "flagged_phrases": [fp.get("text") for fp in flagged_phrases][:6],
        "transcript_excerpt": excerpt,
    }

    try:
        resp = _client().chat.completions.create(
            model=SUMMARY_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM.format(patient_name=patient_name)},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
        )
    except Exception as err:
        log.warning("gpt-5-mini summary failed: %s — using fallback", err)
        return _fallback_summary(metrics, patient_name)

    usage_log.record_from_openai_response(SUMMARY_MODEL, resp, session_id=session_id)

    raw = (resp.choices[0].message.content or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("gpt-5-mini returned non-JSON — falling back. raw=%r", raw[:200])
        return _fallback_summary(metrics, patient_name)

    summary = (data.get("session_summary") or "").strip()
    exercises = data.get("suggested_exercises") or []
    if not isinstance(exercises, list):
        exercises = [str(exercises)]
    exercises = [str(e).strip() for e in exercises if str(e).strip()][:2]

    if not summary:
        return _fallback_summary(metrics, patient_name)

    return {"session_summary": summary, "suggested_exercises": exercises}


def _fallback_summary(metrics: dict[str, Any], patient_name: str) -> dict[str, Any]:
    return {
        "session_summary": (
            f"{patient_name} completed the session. "
            f"We logged {metrics.get('patient_utterance_count', 0)} patient utterances "
            "and saved the transcript for review."
        ),
        "suggested_exercises": ["Check in with a short conversation tomorrow."],
    }


# ─── orchestration entry point ────────────────────────────────────────────────


def analyze_session(
    *,
    session_id: str,
    patient_id: str,
    interactions: list[dict[str, Any]],
    transcript_text: str,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> dict[str, Any]:
    """Run the full post-session analysis and persist it.

    Returns the analysis dict so the caller can log/forward. Never raises —
    failures are logged and a fallback record is still produced so the
    caregiver dashboard always has something to render."""
    patient = snowflake_io.get_patient(patient_id) or {}
    baseline = patient.get("baseline_score")
    patient_name = patient.get("name") or patient_id

    score = score_session(
        interactions,
        baseline_score=baseline,
        patient_id=patient_id,
        session_id=session_id,
    )

    summary = generate_summary(
        transcript_text=transcript_text,
        metrics=score["metrics"],
        flagged_phrases=score["flagged_phrases"],
        patient_name=patient_name,
        session_id=session_id,
    )

    analysis = {
        "session_id": session_id,
        "patient_id": patient_id,
        "overall_score": score["overall_score"],
        "severity": score["severity"],
        "baseline_delta": score["baseline_delta"],
        "metrics": score["metrics"],
        "flagged_phrases": score["flagged_phrases"],
        "summary": summary["session_summary"],
        "suggested_exercises": summary["suggested_exercises"],
        "analyzed_at": datetime.now(timezone.utc),
    }

    try:
        snowflake_io.write_analysis(analysis)
    except Exception as err:
        log.exception("write_analysis failed: %s — falling back to disk", err)
        _disk_backup(analysis, err)

    log.info(
        "[cognitive] score=%d severity=%s session=%s patient=%s",
        analysis["overall_score"],
        analysis["severity"],
        session_id,
        patient_id,
    )

    _notify_bridge(
        session_id=session_id,
        score=analysis["overall_score"],
        severity=analysis["severity"],
    )

    # Pop and forward per-session usage so the bridge can announce it once.
    session_cost = usage_log.pop_session_totals(session_id)
    _notify_session_cost(session_id, session_cost)

    # `analyzed_at` is a datetime — make the return JSON-friendly.
    out = dict(analysis)
    out["analyzed_at"] = analysis["analyzed_at"].isoformat()
    out["cost"] = session_cost
    return out


def _notify_bridge(*, session_id: str, score: int, severity: str) -> None:
    try:
        httpx.post(
            f"{BRIDGE_URL}/internal/analysis-ready",
            json={"session_id": session_id, "score": score, "severity": severity},
            timeout=2.0,
        )
    except Exception as err:
        log.debug("analysis-ready ping failed (%s) — bridge may be offline", err)


def _notify_session_cost(session_id: str, totals: dict[str, float]) -> None:
    if not totals:
        return
    try:
        httpx.post(
            f"{BRIDGE_URL}/internal/session-cost",
            json={"session_id": session_id, **totals},
            timeout=2.0,
        )
    except Exception as err:
        log.debug("session-cost ping failed (%s) — bridge may be offline", err)


def _disk_backup(analysis: dict[str, Any], err: Exception) -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[5]
    out_dir = repo_root / "out" / "failed-writes"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(analysis)
    payload["analyzed_at"] = payload["analyzed_at"].isoformat()
    payload["_error"] = str(err)
    (out_dir / f"{analysis['session_id'].replace(':', '_')}.analysis.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
