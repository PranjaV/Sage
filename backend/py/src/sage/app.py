"""FastAPI orchestrator on localhost:7777."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# backend/py/src/sage/app.py → parents[4] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(REPO_ROOT / ".env")

# Imports that need env vars at module load come AFTER load_dotenv.
from sage import snowflake_io  # noqa: E402
from sage.graph import run_turn  # noqa: E402
from sage.models import (  # noqa: E402
    SessionEndRequest,
    SessionEndResponse,
    TurnRequest,
    TurnResponse,
)

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

    log.info("[cognitive] analysis queued for %s (B16 will fill this in)", req.session_id)
    return SessionEndResponse(
        session_id=req.session_id,
        persisted=True,
        duration_seconds=duration,
        interactions_written=written,
        cognitive_analysis={"status": "queued"},
    )
