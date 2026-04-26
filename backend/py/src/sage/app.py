"""FastAPI orchestrator on localhost:7777. Filled in at B10."""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Sage Orchestrator", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"ok": True}
