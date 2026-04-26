"""Golden-transcript tests for the deterministic scoring engine.

We don't pin exact scores — only severity bands. Drifting a few points is
fine; landing in the wrong bucket is a regression."""
from __future__ import annotations

from sage.cognitive_score import score_session, severity_for


def _patient(*utterances: str) -> list[dict]:
    return [{"speaker": "patient", "utterance": u} for u in utterances]


# ─── transcripts ──────────────────────────────────────────────────────────────


NORMAL = _patient(
    "Hi Sage, I'd like to order a new weekly pill organizer please.",
    "My old one cracked yesterday when I dropped it on the kitchen counter.",
    "Could you find one with seven compartments and large labels?",
    "Thank you, that sounds wonderful.",
)

MILD_CONCERN = _patient(
    "I need to get a pill organizer.",
    "Um, my pharmacy... is the one that is on Maple.",
    "Let me think... what's the thing I was going to say?",
    "I need to get a pill organizer.",
)

CLEAR_CONCERN = _patient(
    "I need... the thingy.",
    "It's the one that I take in the morning.",
    "Um, where was I? I need an organizer.",
    "I need... the thingy.",
)


# ─── tests ────────────────────────────────────────────────────────────────────


def test_normal_lands_in_ok_band():
    out = score_session(NORMAL, baseline_score=82, patient_id="p_eleanor", session_id="t_normal")
    assert out["overall_score"] >= 85, out
    assert out["severity"] == "ok"
    assert out["metrics"]["repetition_count"] == 0
    assert out["metrics"]["word_finding_count"] == 0
    assert out["flagged_phrases"] == []


def test_mild_concern_lands_in_watch_band():
    out = score_session(MILD_CONCERN, baseline_score=82, patient_id="p_eleanor", session_id="t_mild")
    assert 70 <= out["overall_score"] <= 84, out
    assert out["severity"] == "watch"
    # It should pick up the duplicated utterance and at least one circumlocution.
    assert out["metrics"]["repetition_count"] >= 1
    assert out["metrics"]["word_finding_count"] >= 1
    assert out["metrics"]["hesitation_count"] >= 2


def test_clear_concern_lands_in_attention_band():
    out = score_session(CLEAR_CONCERN, baseline_score=82, patient_id="p_eleanor", session_id="t_clear")
    assert 50 <= out["overall_score"] <= 69, out
    assert out["severity"] == "attention"
    assert out["metrics"]["repetition_count"] >= 1
    assert out["metrics"]["word_finding_count"] >= 2
    # All flagged phrases must appear verbatim in the source utterances.
    sources = [it["utterance"].lower() for it in CLEAR_CONCERN]
    for fp in out["flagged_phrases"]:
        assert any(fp["text"].lower() in s for s in sources), fp


def test_baseline_delta_uses_patient_baseline():
    out = score_session(NORMAL, baseline_score=82)
    assert out["baseline_delta"] == out["overall_score"] - 82


def test_severity_bands():
    assert severity_for(100) == "ok"
    assert severity_for(85) == "ok"
    assert severity_for(84) == "watch"
    assert severity_for(70) == "watch"
    assert severity_for(69) == "attention"
    assert severity_for(50) == "attention"
    assert severity_for(49) == "follow-up"
    assert severity_for(0) == "follow-up"


def test_ignores_non_patient_speakers():
    transcript = [
        {"speaker": "patient", "utterance": "Hi Sage."},
        {"speaker": "assistant", "utterance": "uh um uh um the thing the thingy what's it called"},
        {"speaker": "patient", "utterance": "I'd like a pill organizer please."},
    ]
    out = score_session(transcript)
    assert out["metrics"]["hesitation_count"] == 0
    assert out["metrics"]["word_finding_count"] == 0
    assert out["flagged_phrases"] == []
