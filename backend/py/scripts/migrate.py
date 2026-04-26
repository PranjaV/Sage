"""Run migrate.sql against the configured Snowflake account.

Usage: python backend/py/scripts/migrate.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import snowflake.connector

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

SQL_PATH = Path(__file__).with_name("migrate.sql")


def split_statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def main() -> int:
    statements = split_statements(SQL_PATH.read_text(encoding="utf-8"))
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        role=os.environ["SNOWFLAKE_ROLE"],
    )
    try:
        cur = conn.cursor()
        try:
            for stmt in statements:
                first_line = stmt.splitlines()[0][:60]
                print(f"  {first_line} …")
                cur.execute(stmt)
        finally:
            cur.close()
    finally:
        conn.close()
    print(f"✓ migrate.sql applied ({len(statements)} statements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
