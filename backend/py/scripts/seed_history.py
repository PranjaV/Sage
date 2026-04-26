"""Seed 30 days of synthetic sessions for the caregiver dashboard trend chart.

For each day from -30 to -1, this writes:
  - one row in `sessions` (with started_at / duration / primary_task)
  - the patient's utterances into `interactions`
  - the result of running the deterministic cognitive_score over them into
    `cognitive_analyses` (with a short, non-clinical summary)

Scores drift gently downward across the month and there's one outlier dip
roughly five days ago — that's what makes the chart interesting in the demo.

Run after migrate.py + seed.py:
    python backend/py/scripts/seed_history.py
"""
from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend" / "py" / "src"))

from sage import snowflake_io  # noqa: E402
from sage.cognitive_score import score_session  # noqa: E402

PATIENT_ID = "p_eleanor"
PATIENT_NAME = "Eleanor"

# ─── transcript pool ──────────────────────────────────────────────────────────
# Six base transcripts. Each is a list of (speaker, utterance) pairs. Patient
# utterances drive scoring; assistant lines are kept for realism.

NORMAL_A = [
    ("patient", "Hi Sage, good morning."),
    ("assistant", "Good morning, Eleanor. What can I help you with today?"),
    ("patient", "Um, could you find me a new weekly pill organizer, the seven-day kind?"),
    ("assistant", "Of course. I'll take a look right now."),
    ("patient", "Last week's calendar was wonderful, thank you."),
    ("patient", "And, um, please send the receipt to Sarah."),
]

NORMAL_B = [
    ("patient", "Good morning, Sage."),
    ("assistant", "Good morning. How are you feeling today?"),
    ("patient", "I'd like to find a large-print calendar for the kitchen, like the one I had."),
    ("assistant", "I can do that. One moment."),
    ("patient", "Um, and could you remind me about Thursday?"),
    ("patient", "Thank you for finding it. That's the thing I was thinking of."),
]

NORMAL_C = [
    ("patient", "Hi there."),
    ("assistant", "Hello. What would you like to do?"),
    ("patient", "Um, could you find me a magnifying reader, the one that I had before?"),
    ("assistant", "Yes. I'll order one like the previous."),
    ("patient", "Let me think... yes, that's the right one."),
    ("patient", "Thank you, Sage."),
]

MILD_A = [
    ("patient", "Hi Sage."),
    ("assistant", "Hello, Eleanor."),
    ("patient", "Could you find me a pill organizer?"),
    ("assistant", "Sure. Tell me which kind."),
    ("patient", "Um, let me think, the one that I usually get."),
    ("patient", "What's it called, the thing I take with my pills?"),
    ("patient", "Could you find me a pill organizer?"),
]

MILD_B = [
    ("patient", "Good morning."),
    ("assistant", "Good morning. What's on your mind?"),
    ("patient", "Um, I need the thingy, you know, the one for my pills."),
    ("assistant", "The weekly pill organizer?"),
    ("patient", "Yes, that one. The one that I always get."),
    ("patient", "Um, when is my appointment again?"),
    ("patient", "I need the thingy for my pills."),
]

CLEAR_A = [
    ("patient", "I need... the thingy."),
    ("assistant", "Tell me a little more."),
    ("patient", "It's the one that I take in the morning."),
    ("assistant", "The pill organizer?"),
    ("patient", "Um, where was I again?"),
    ("patient", "I need... the thingy."),
]

POOL = {
    "normal_a": NORMAL_A,
    "normal_b": NORMAL_B,
    "normal_c": NORMAL_C,
    "mild_a": MILD_A,
    "mild_b": MILD_B,
    "clear_a": CLEAR_A,
}

# Day-by-day pattern. Index 0 = 30 days ago, index 29 = 1 day ago.
# We want a gentle drift down, normal → mild, with a clear outlier at day -5.
PATTERN = [
    "normal_a", "normal_b", "normal_a", "normal_c", "normal_b",  # -30 .. -26
    "normal_a", "normal_c", "normal_b", "normal_a", "normal_c",  # -25 .. -21
    "normal_b", "normal_c", "normal_b", "mild_a", "normal_c",    # -20 .. -16
    "mild_a", "normal_b", "mild_a", "mild_b", "normal_c",        # -15 .. -11
    "mild_a", "normal_c", "mild_b", "mild_a", "mild_b",          # -10 .. -6
    "clear_a",                                                   # -5 outlier
    "mild_a", "mild_b", "mild_a", "mild_b",                      # -4 .. -1
]
assert len(PATTERN) == 30


PRIMARY_TASKS = [
    "browser: weekly pill organizer",
    "browser: large-print calendar",
    "browser: magnifying reader",
    "memory: appointment lookup",
    "memory: pharmacy lookup",
    "smalltalk: morning check-in",
]


def _vary(line: str, rng: random.Random) -> str:
    """Tiny per-day phrasing variation. Keeps token sets distinct enough that
    the repetition heuristic doesn't merge across sessions."""
    swaps = [
        ("Hi Sage", "Hello Sage"),
        ("Good morning", "Morning"),
        ("Thank you", "Thanks"),
        ("Could you find me", "Could you get me"),
        ("a pill organizer", "a 7-day pill organizer"),
    ]
    if rng.random() < 0.4:
        before, after = rng.choice(swaps)
        if before in line:
            line = line.replace(before, after)
    return line


def _build_session(day_index: int, key: str, rng: random.Random) -> dict:
    base = POOL[key]
    interactions: list[dict] = []
    days_ago = 30 - day_index
    started_at = datetime.now(timezone.utc).replace(
        hour=9, minute=rng.randint(5, 55), second=0, microsecond=0
    ) - timedelta(days=days_ago)
    duration = rng.randint(45, 180)
    ended_at = started_at + timedelta(seconds=duration)

    # Spread utterances across the session window.
    for j, (speaker, text) in enumerate(base):
        ts = started_at + timedelta(seconds=int(duration * (j + 1) / (len(base) + 1)))
        interactions.append(
            {
                "interaction_id": uuid.uuid4().hex,
                "speaker": speaker,
                "utterance": _vary(text, rng),
                "ts": ts,
            }
        )

    transcript_text = "\n".join(f"[{it['speaker']}] {it['utterance']}" for it in interactions)
    primary_task = rng.choice(PRIMARY_TASKS) if "normal" in key else (
        "browser: weekly pill organizer" if "mild" in key else "memory: appointment lookup"
    )
    session_id = f"{PATIENT_ID}:hist_{started_at.strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"

    return {
        "session_id": session_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration": duration,
        "primary_task": primary_task,
        "transcript_text": transcript_text,
        "interactions": interactions,
        "key": key,
    }


def _summary_for(score: int, severity: str, day_index: int, name: str) -> str:
    """Synthetic, deterministic summary so we don't burn 30 LLM calls on seed."""
    if severity == "ok":
        return (
            f"{name} chatted comfortably and finished the task without trouble. "
            "Tone was warm and present throughout."
        )
    if severity == "watch":
        return (
            f"{name} completed the session with a couple of small pauses while finding the right words. "
            "Nothing of concern; consider sharing a calm chat tomorrow."
        )
    if severity == "attention":
        return (
            f"{name} repeated a request and used vague descriptions a few times this session. "
            "A short, gentle conversation with familiar topics could help."
        )
    return (
        f"{name} had a quieter session today. "
        "A brief, easy chat about a familiar memory may be a kind next step."
    )


def main() -> int:
    if not snowflake_io.get_patient(PATIENT_ID):
        print(f"✗ patient {PATIENT_ID} not seeded — run seed.py first", file=sys.stderr)
        return 1

    rng = random.Random(20260425)
    rows = []
    for i, key in enumerate(PATTERN):
        sess = _build_session(i, key, rng)
        rows.append(sess)

    # Write each session + interactions + analysis. Kept synchronous so any
    # error surfaces immediately; the seed is a one-time job.
    for idx, s in enumerate(rows):
        days_ago = 30 - idx
        snowflake_io.write_session(
            session_id=s["session_id"],
            patient_id=PATIENT_ID,
            started_at=s["started_at"],
            ended_at=s["ended_at"],
            transcript=s["transcript_text"],
            primary_task=s["primary_task"],
        )
        snowflake_io.write_interactions(s["session_id"], s["interactions"])

        score = score_session(
            s["interactions"],
            baseline_score=82,
            patient_id=PATIENT_ID,
            session_id=s["session_id"],
        )
        analysis = {
            "analysis_id": uuid.uuid4().hex,
            "session_id": s["session_id"],
            "patient_id": PATIENT_ID,
            "overall_score": score["overall_score"],
            "severity": score["severity"],
            "baseline_delta": score["baseline_delta"],
            "metrics": score["metrics"],
            "flagged_phrases": score["flagged_phrases"],
            "summary": _summary_for(score["overall_score"], score["severity"], days_ago, PATIENT_NAME),
            "analyzed_at": s["ended_at"],
        }
        snowflake_io.write_analysis(analysis)
        print(
            f"  d-{days_ago:02d} {s['key']:<8} "
            f"score={score['overall_score']:>3} severity={score['severity']:<10} "
            f"task={s['primary_task']}"
        )

    print(f"✓ seeded {len(rows)} historical sessions for {PATIENT_ID}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
