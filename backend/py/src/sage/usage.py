"""Token + dollar accounting for Sage's LLM and TTS calls.

Pricing here is approximate (list prices as of late 2025) and only meant for
on-the-fly demo cost awareness — not billing. We track per-session and
also a global running total so the bridge can print a quick line at the
end of every session.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any

log = logging.getLogger("sage.usage")

# $/1K tokens — input, output. Update as published prices shift.
LLM_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4.1": (0.0030, 0.0120),
    "gpt-4.1-mini": (0.0004, 0.0016),
    "gpt-4o-mini-transcribe": (0.0001, 0.0004),
    "gpt-5-mini": (0.0003, 0.0012),
}
DEFAULT_LLM_PRICE = (0.0010, 0.0040)

# ElevenLabs Flash v2.5 list rate. OpenAI gpt-4o-mini-tts is ~$15/1M chars.
TTS_RATES: dict[str, float] = {
    "elevenlabs": 0.000165,
    "openai": 0.000015,
}


def _price_for(model: str) -> tuple[float, float]:
    return LLM_PRICES.get(model, DEFAULT_LLM_PRICE)


_lock = threading.Lock()
_session_totals: dict[str, dict[str, float]] = defaultdict(
    lambda: {"in": 0.0, "out": 0.0, "dollars": 0.0, "tts_chars": 0.0, "tts_dollars": 0.0}
)
_global = {"in": 0.0, "out": 0.0, "dollars": 0.0, "tts_chars": 0.0, "tts_dollars": 0.0}


def record_llm(model: str, in_tokens: int, out_tokens: int, *, session_id: str | None = None) -> float:
    p_in, p_out = _price_for(model)
    dollars = (in_tokens / 1000.0) * p_in + (out_tokens / 1000.0) * p_out
    with _lock:
        _global["in"] += in_tokens
        _global["out"] += out_tokens
        _global["dollars"] += dollars
        if session_id:
            t = _session_totals[session_id]
            t["in"] += in_tokens
            t["out"] += out_tokens
            t["dollars"] += dollars
    log.info(
        "[usage] model=%s in=%d out=%d $=%.4f session=%s",
        model,
        in_tokens,
        out_tokens,
        dollars,
        session_id or "-",
    )
    return dollars


def record_tts(engine: str, chars: int, *, session_id: str | None = None) -> float:
    rate = TTS_RATES.get(engine, TTS_RATES["elevenlabs"])
    dollars = chars * rate
    with _lock:
        _global["tts_chars"] += chars
        _global["tts_dollars"] += dollars
        if session_id:
            t = _session_totals[session_id]
            t["tts_chars"] += chars
            t["tts_dollars"] += dollars
    log.info(
        "[usage] tts=%s chars=%d $=%.4f session=%s",
        engine,
        chars,
        dollars,
        session_id or "-",
    )
    return dollars


def record_from_openai_response(model: str, resp: Any, *, session_id: str | None = None) -> float:
    """Pull token counts off an OpenAI ChatCompletion response and record."""
    usage = getattr(resp, "usage", None)
    if usage is None:
        return 0.0
    in_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    out_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    return record_llm(model, in_tokens, out_tokens, session_id=session_id)


def session_totals(session_id: str) -> dict[str, float]:
    with _lock:
        return dict(_session_totals.get(session_id, {"in": 0, "out": 0, "dollars": 0, "tts_chars": 0, "tts_dollars": 0}))


def pop_session_totals(session_id: str) -> dict[str, float]:
    with _lock:
        return _session_totals.pop(session_id, {"in": 0, "out": 0, "dollars": 0, "tts_chars": 0, "tts_dollars": 0})


def global_totals() -> dict[str, float]:
    with _lock:
        return dict(_global)
