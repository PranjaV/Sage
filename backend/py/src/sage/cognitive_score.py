"""Deterministic cognitive-signal scoring over a session transcript.

This module is intentionally explainable. Every signal is a small, auditable
function over the patient's utterances; the final score is a transparent
linear combination. Anything fuzzy (the borderline topic-drift call) is the
only place we let an LLM weigh in, and only as a tiebreaker.

Output shape matches PRD §8 — see `score_session`.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Iterable

log = logging.getLogger("sage.cognitive_score")

# ─── tokenization ─────────────────────────────────────────────────────────────

_WORD_RE = re.compile(r"\b[a-zA-Z']+\b")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

HESITATION_TOKENS = {"uh", "um", "umm", "uhh", "er", "erm", "hmm", "mm"}
HESITATION_PHRASES = ("let me think", "let's see", "give me a sec", "give me a second")
ELLIPSIS_RE = re.compile(r"\.{3,}|…")

# Circumlocution / word-finding patterns. Order matters: longer, more
# specific phrases first so we don't double-count overlapping spans.
WORD_FINDING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("the_one_that", re.compile(r"\bthe one (that|which)\b[^.!?]*", re.IGNORECASE)),
    ("whats_it_called", re.compile(r"\bwhat'?s it called\b", re.IGNORECASE)),
    ("you_know_what", re.compile(r"\byou know what (i mean|i'm talking about)\b", re.IGNORECASE)),
    ("the_thingy", re.compile(r"\bthe (thing|thingy|whatchamacallit|doohickey|gizmo)\b", re.IGNORECASE)),
    ("that_thing_for", re.compile(r"\bthat thing (for|with|where)\b[^.!?]*", re.IGNORECASE)),
)

# Light coordination tokens we treat as "real" connectors so a drift heuristic
# doesn't mark normal conversational shifts.
CONJUNCTIONS = {
    "and", "but", "or", "so", "because", "though", "although", "however",
    "meanwhile", "then", "since", "while", "yet",
}


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text)]


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(text or "") if p and p.strip()]
    return parts


def _patient_utterances(interactions: Iterable[dict[str, Any]]) -> list[str]:
    return [
        (it.get("utterance") or "").strip()
        for it in interactions
        if (it.get("speaker") or "").lower() == "patient" and (it.get("utterance") or "").strip()
    ]


# ─── individual signals ───────────────────────────────────────────────────────


def lexical_diversity(utterances: list[str]) -> float:
    """Type-token ratio over patient utterances combined.

    Returns 0.0 for empty input. We deliberately don't subtract stopwords —
    older adults often lean on common words and that's not a deficit signal."""
    blob = " ".join(utterances)
    toks = _tokens(blob)
    if not toks:
        return 0.0
    return round(len(set(toks)) / len(toks), 4)


def repetition_count(utterances: list[str], threshold: float = 0.8) -> int:
    """Count of patient utterances ≥`threshold` Jaccard-similar to any prior
    patient utterance in the same session. The first instance never counts;
    only the repeat does."""
    prior_token_sets: list[set[str]] = []
    repeats = 0
    for u in utterances:
        toks = set(_tokens(u))
        if len(toks) < 3:  # too short to call a repeat reliably
            prior_token_sets.append(toks)
            continue
        for prev in prior_token_sets:
            if not prev:
                continue
            inter = len(toks & prev)
            union = len(toks | prev)
            if union and inter / union >= threshold:
                repeats += 1
                break
        prior_token_sets.append(toks)
    return repeats


def hesitation_count(utterances: list[str]) -> int:
    n = 0
    for u in utterances:
        toks = _tokens(u)
        n += sum(1 for t in toks if t in HESITATION_TOKENS)
        low = u.lower()
        n += sum(low.count(p) for p in HESITATION_PHRASES)
        n += len(ELLIPSIS_RE.findall(u))
    return n


def topic_drift_count(utterances: list[str]) -> int:
    """Rough heuristic: within each utterance, count sentence boundaries where
    the next sentence starts with a fresh subject and verb but no conjunction.

    Cheap and intentionally conservative. We only flag transitions that look
    abrupt: capitalized pronoun/noun start AND no leading connector."""
    drifts = 0
    for u in utterances:
        sents = _sentences(u)
        if len(sents) < 2:
            continue
        for prev, nxt in zip(sents, sents[1:]):
            head = nxt.split(maxsplit=1)
            if not head:
                continue
            first = head[0].lower().strip(",;:")
            if first in CONJUNCTIONS:
                continue
            # crude: a fresh sentence with its own subject is a candidate
            if re.match(r"^(i|we|you|he|she|they|the|my|our|that|this)\b", first):
                drifts += 1
    return drifts


def word_finding_phrases(utterances: list[str]) -> list[dict[str, Any]]:
    """Return the verbatim spans matched by circumlocution patterns.

    We never invent a phrase — the `text` field is sliced directly from the
    utterance. A phrase is omitted if it doesn't match verbatim."""
    found: list[dict[str, Any]] = []
    for idx, u in enumerate(utterances):
        seen_spans: list[tuple[int, int]] = []
        for label, pattern in WORD_FINDING_PATTERNS:
            for m in pattern.finditer(u):
                span = (m.start(), m.end())
                if any(s[0] <= span[0] < s[1] or s[0] < span[1] <= s[1] for s in seen_spans):
                    continue
                seen_spans.append(span)
                found.append(
                    {
                        "kind": label,
                        "text": u[m.start() : m.end()],
                        "utterance_index": idx,
                    }
                )
    return found


# ─── composite score ──────────────────────────────────────────────────────────


SEVERITY_BANDS = (
    (85, "ok"),
    (70, "watch"),
    (50, "attention"),
    (0, "follow-up"),
)


def severity_for(score: int) -> str:
    for floor, label in SEVERITY_BANDS:
        if score >= floor:
            return label
    return "follow-up"


def score_session(
    interactions: list[dict[str, Any]],
    *,
    baseline_score: int | None = None,
    patient_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Score a session using only patient utterances.

    Returns a dict matching PRD §8:
      { session_id, patient_id, overall_score, severity, baseline_delta,
        metrics: { lexical_diversity, repetition_count, hesitation_count,
                   topic_drift_count, word_finding_count, patient_utterance_count },
        flagged_phrases: [{kind, text, utterance_index}] }
    """
    utts = _patient_utterances(interactions)

    ld = lexical_diversity(utts)
    rep = repetition_count(utts)
    hes = hesitation_count(utts)
    drift = topic_drift_count(utts)
    wf_phrases = word_finding_phrases(utts)
    wf_count = len(wf_phrases)

    base = 100
    base -= 4 * rep
    base -= 2 * hes
    base -= 5 * drift
    base -= 6 * wf_count
    if ld > 0.65:
        base += 5

    score = max(0, min(100, int(round(base))))
    sev = severity_for(score)
    delta = score - baseline_score if baseline_score is not None else 0

    metrics = {
        "lexical_diversity": ld,
        "repetition_count": rep,
        "hesitation_count": hes,
        "topic_drift_count": drift,
        "word_finding_count": wf_count,
        "patient_utterance_count": len(utts),
    }

    return {
        "session_id": session_id,
        "patient_id": patient_id,
        "overall_score": score,
        "severity": sev,
        "baseline_delta": int(delta),
        "metrics": metrics,
        "flagged_phrases": wf_phrases,
    }


# ─── optional LLM tiebreaker for ambiguous drift ──────────────────────────────


def _llm_drift_tiebreaker(utterances: list[str]) -> int | None:
    """Used only when the heuristic returns an ambiguous count. Off by default."""
    if os.getenv("SAGE_DRIFT_TIEBREAKER") != "1":
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        joined = "\n".join(f"- {u}" for u in utterances)
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Count abrupt topic shifts in these utterances. Reply with JSON {\"drift\": <int>}.",
                },
                {"role": "user", "content": joined},
            ],
            response_format={"type": "json_object"},
        )
        import json as _json

        data = _json.loads(resp.choices[0].message.content or "{}")
        return int(data.get("drift", 0))
    except Exception as err:
        log.debug("llm drift tiebreaker skipped: %s", err)
        return None
