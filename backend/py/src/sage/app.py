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
from sage.graph import run_turn  # noqa: E402
from sage.models import TurnRequest, TurnResponse  # noqa: E402

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
    )
