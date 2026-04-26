"""Seed Sage's demo patient — Eleanor Hayes — and her structured profile."""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Path setup so `import sage.snowflake_io` works without an editable install.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend" / "py" / "src"))

from sage import snowflake_io  # noqa: E402


PATIENT = {
    "patient_id": "p_eleanor",
    "name": "Eleanor Hayes",
    "age": 78,
    "caregiver_name": "Sarah Hayes",
    "baseline_score": 82,
    "consent_status": "active",
}

PROFILE = {
    "patient_id": "p_eleanor",
    "doctors": [
        {"name": "Dr. Mehta", "specialty": "cardiology", "phone": "555-0102"},
    ],
    "appointments": [
        {"doctor": "Dr. Mehta", "when": "Thursday 9:00am", "address": "450 Maple Ave"},
    ],
    "pharmacy": {"name": "CVS Maple", "address": "410 Maple Ave"},
    "address": {"street": "12 Oak Lane", "city": "Boston", "state": "MA"},
    "common_items": [
        "weekly pill organizer 7 day",
        "large-print calendar",
        "magnifying reader",
    ],
}


def main() -> int:
    snowflake_io.upsert_patient(PATIENT)
    snowflake_io.upsert_profile(PROFILE)

    # Read-back sanity check.
    patient = snowflake_io.get_patient("p_eleanor")
    profile = snowflake_io.get_profile("p_eleanor")
    if not patient or not profile:
        print("✗ seed: read-back failed", file=sys.stderr)
        return 1
    print(f"  patient: {patient['name']} (baseline={patient['baseline_score']})")
    print(f"  doctors: {profile['doctors']}")
    print(f"  appointments: {profile['appointments']}")
    print(f"  common_items: {profile['common_items']}")
    print("✓ seeded p_eleanor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
