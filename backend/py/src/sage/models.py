"""Pydantic schemas for orchestrator IO. Filled in alongside B10."""
from __future__ import annotations

from pydantic import BaseModel


class TurnRequest(BaseModel):
    session_id: str
    text: str


class TurnResponse(BaseModel):
    response_text: str
    trace: list[dict] = []
