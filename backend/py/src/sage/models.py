"""Pydantic schemas for orchestrator IO."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TurnRequest(BaseModel):
    session_id: str
    text: str


class TurnResponse(BaseModel):
    response_text: str
    trace: list[dict] = Field(default_factory=list)
    intent: str | None = None
    payload_goal: str | None = None


class Interaction(BaseModel):
    speaker: str
    utterance: str
    ts: str | None = None


class SessionEndRequest(BaseModel):
    session_id: str
    patient_id: str
    started_at: datetime
    ended_at: datetime
    interactions: list[Interaction] = Field(default_factory=list)
    primary_task: str | None = None


class SessionEndResponse(BaseModel):
    session_id: str
    persisted: bool
    duration_seconds: int
    interactions_written: int
    cognitive_analysis: dict[str, Any] = Field(default_factory=dict)
