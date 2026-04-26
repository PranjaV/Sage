"""FastAPI orchestrator on localhost:7777."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# backend/py/src/sage/app.py → parents[4] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(REPO_ROOT / ".env")

# Imports that need env vars at module load come AFTER load_dotenv.
from sage import snowflake_io  # noqa: E402
from sage.graph import run_turn  # noqa: E402
from sage.models import (  # noqa: E402
    CaregiverAskRequest,
    CaregiverAskResponse,
    SessionEndRequest,
    SessionEndResponse,
    TurnRequest,
    TurnResponse,
)
from sage.nodes.cognitive import analyze_session  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("sage.app")

app = FastAPI(title="Sage Orchestrator", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/turn", response_model=TurnResponse)
async def turn(req: TurnRequest) -> TurnResponse:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    log.info("turn session=%s text=%r", req.session_id, req.text[:80])
    try:
        result = run_turn(req.session_id, req.text)
    except Exception as err:  # surface, do not crash the bridge
        log.exception("turn failed: %s", err)
        raise HTTPException(status_code=500, detail=str(err)) from err
    return TurnResponse(
        response_text=result["response_text"],
        trace=result["trace"],
        intent=result.get("intent"),
        payload_goal=result.get("payload_goal"),
    )


@app.post("/session/end", response_model=SessionEndResponse)
async def session_end(req: SessionEndRequest) -> SessionEndResponse:
    """Persist a finished session to Snowflake. Cognitive analysis is stubbed
    here and lit up in B16 — for now we just log "queued" so the bridge can
    move on without blocking the demo."""
    duration = max(0, int((req.ended_at - req.started_at).total_seconds()))
    transcript_text = "\n".join(f"[{i.speaker}] {i.utterance}" for i in req.interactions)
    log.info(
        "session:end %s patient=%s interactions=%d duration=%ds task=%s",
        req.session_id,
        req.patient_id,
        len(req.interactions),
        duration,
        req.primary_task,
    )
    try:
        snowflake_io.write_session(
            session_id=req.session_id,
            patient_id=req.patient_id,
            started_at=req.started_at,
            ended_at=req.ended_at,
            transcript=transcript_text,
            primary_task=req.primary_task,
        )
        written = snowflake_io.write_interactions(
            req.session_id,
            [i.model_dump() for i in req.interactions],
        )
    except Exception as err:
        log.exception("session:end persistence failed: %s", err)
        raise HTTPException(status_code=500, detail=f"snowflake write failed: {err}") from err

    # Run cognitive analysis synchronously — it's fast (≤ a few seconds) and the
    # caregiver dashboard wants the row before it polls.
    try:
        analysis = analyze_session(
            session_id=req.session_id,
            patient_id=req.patient_id,
            interactions=[i.model_dump() for i in req.interactions],
            transcript_text=transcript_text,
            started_at=req.started_at,
            ended_at=req.ended_at,
        )
    except Exception as err:  # never crash the bridge over a summary failure
        log.exception("cognitive analysis failed: %s", err)
        analysis = {"status": "failed", "error": str(err)}

    return SessionEndResponse(
        session_id=req.session_id,
        persisted=True,
        duration_seconds=duration,
        interactions_written=written,
        cognitive_analysis=analysis,
    )


@app.post("/caregiver/ask", response_model=CaregiverAskResponse)
async def caregiver_ask(req: CaregiverAskRequest) -> CaregiverAskResponse:
    """Cortex Analyst answers a natural-language question about a patient.

    Returns the generated SQL, executed rows, and a one-sentence summary."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    from sage import cortex_analyst  # local import keeps cold-start small

    try:
        result = cortex_analyst.ask(req.question)
    except Exception as err:
        log.exception("cortex_analyst.ask failed: %s", err)
        raise HTTPException(status_code=502, detail=f"cortex analyst error: {err}") from err

    return CaregiverAskResponse(
        question=result["question"],
        sql=result.get("sql") or "",
        rows=result.get("rows") or [],
        answer_text=result.get("answer_text") or "",
    )


# ─── caregiver dashboard reads ────────────────────────────────────────────────


@app.get("/caregiver/overview")
async def caregiver_overview(patient_id: str = Query(..., min_length=1)) -> dict:
    """Top-of-dashboard summary: patient identity + latest score + latest session."""
    patient = snowflake_io.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"patient not found: {patient_id}")
    latest_analysis = snowflake_io.get_latest_analysis(patient_id)
    recent_sessions = snowflake_io.list_sessions_with_scores(patient_id, limit=1)
    latest_session = recent_sessions[0] if recent_sessions else None
    return {
        "patient": patient,
        "latest_session": latest_session,
        "latest_score": latest_analysis["overall_score"] if latest_analysis else None,
        "severity": latest_analysis["severity"] if latest_analysis else None,
        "baseline_delta": latest_analysis["baseline_delta"] if latest_analysis else None,
        "summary": latest_analysis["summary"] if latest_analysis else None,
        "analyzed_at": latest_analysis["analyzed_at"] if latest_analysis else None,
    }


@app.get("/caregiver/trend")
async def caregiver_trend(
    patient_id: str = Query(..., min_length=1),
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Daily score points (oldest → newest) for the trend chart."""
    points = snowflake_io.get_trend(patient_id, days=days)
    return {"patient_id": patient_id, "days": days, "points": points}


@app.get("/caregiver/sessions")
async def caregiver_sessions(
    patient_id: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
) -> dict:
    """Recent sessions with score + severity for the dashboard list."""
    sessions = snowflake_io.list_sessions_with_scores(patient_id, limit=limit)
    return {"patient_id": patient_id, "sessions": sessions}


@app.get("/caregiver/transcript")
async def caregiver_transcript(session_id: str = Query(..., min_length=1)) -> dict:
    """Full transcript + flagged phrases for a single session."""
    detail = snowflake_io.get_session_transcript(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    return detail
