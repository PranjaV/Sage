"""B2 - Verify Snowflake connection + write + read."""
from __future__ import annotations

import io
import os
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv
import snowflake.connector

# Windows default cp1252 cannot encode the check glyph; force UTF-8 output.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

REQUIRED = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
    "SNOWFLAKE_ROLE",
]
missing = [k for k in REQUIRED if not os.getenv(k)]
if missing:
    print(f"✗ missing env: {', '.join(missing)}")
    sys.exit(1)


def main() -> int:
    conn = None
    cur = None
    try:
        conn = snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            password=os.environ["SNOWFLAKE_PASSWORD"],
            warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
            database=os.environ["SNOWFLAKE_DATABASE"],
            schema=os.environ["SNOWFLAKE_SCHEMA"],
            role=os.environ["SNOWFLAKE_ROLE"],
            client_session_keep_alive=False,
        )
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS sage_smoke_test "
            "(id INT, note STRING, ts TIMESTAMP_NTZ)"
        )
        cur.execute(
            "INSERT INTO sage_smoke_test (id, note, ts) "
            "SELECT 1, 'hello sage', CURRENT_TIMESTAMP"
        )
        cur.execute("SELECT id, note, ts FROM sage_smoke_test WHERE id = 1")
        row = cur.fetchone()
        print(f"  row: {row}")
        cur.execute("DROP TABLE IF EXISTS sage_smoke_test")
        print("✓ Snowflake round-trip ok")
        return 0
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
