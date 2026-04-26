"""Upload the Cortex Analyst semantic model YAML to a Snowflake stage.

Stage: @SAGE_DB.CORE.SAGE_STAGE/cortex/cortex_semantic.yaml

Run after migrate.py + seed.py:
    python backend/py/scripts/upload_cortex_model.py
"""
from __future__ import annotations

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

YAML_PATH = REPO_ROOT / "backend" / "py" / "scripts" / "cortex_semantic.yaml"
STAGE = "SAGE_STAGE"
STAGE_PATH = "cortex"


def main() -> int:
    if not YAML_PATH.exists():
        print(f"✗ semantic model not found at {YAML_PATH}", file=sys.stderr)
        return 1

    posix_path = YAML_PATH.resolve().as_posix()

    with snowflake_io.cursor() as cur:
        cur.execute(f"CREATE STAGE IF NOT EXISTS {STAGE}")
        # PUT requires a file:// URI; on Windows this looks like file:///C:/...
        put_cmd = (
            f"PUT 'file:///{posix_path}' @{STAGE}/{STAGE_PATH}/ "
            "AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        )
        cur.execute(put_cmd)
        for row in cur.fetchall():
            print("  ", row)

        cur.execute(f"LIST @{STAGE}/{STAGE_PATH}/")
        files = cur.fetchall()
        for f in files:
            print(f"  staged: {f[0]} ({f[1]} bytes)")

    print(f"✓ uploaded {YAML_PATH.name} → @{STAGE}/{STAGE_PATH}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
