"""Spot-check the most recent session for a patient.

Usage: python backend/py/scripts/check_session.py [patient_id]
Defaults to p_eleanor.
"""
from __future__ import annotations

import json
import sys
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


def main() -> int:
    patient_id = sys.argv[1] if len(sys.argv) > 1 else "p_eleanor"
    with snowflake_io.cursor() as cur:
        cur.execute(
            """
            SELECT session_id, started_at, ended_at, duration_seconds, primary_task,
                   LENGTH(transcript) AS transcript_len
              FROM sessions
             WHERE patient_id = %s
             ORDER BY ended_at DESC
             LIMIT 1
            """,
            (patient_id,),
        )
        row = cur.fetchone()
        if not row:
            print(f"  (no sessions for {patient_id})")
            return 1
        session_id = row[0]
        print("most recent session:")
        print(f"  session_id    : {session_id}")
        print(f"  started_at    : {row[1]}")
        print(f"  ended_at      : {row[2]}")
        print(f"  duration_secs : {row[3]}")
        print(f"  primary_task  : {row[4]}")
        print(f"  transcript_len: {row[5]}")

        cur.execute(
            """
            SELECT speaker, utterance, created_at
              FROM interactions
             WHERE session_id = %s
             ORDER BY created_at
            """,
            (session_id,),
        )
        interactions = cur.fetchall()
        print(f"\ninteractions ({len(interactions)}):")
        for speaker, utt, ts in interactions:
            preview = utt if len(utt) <= 90 else utt[:87] + "…"
            print(f"  [{ts}] {speaker}: {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
