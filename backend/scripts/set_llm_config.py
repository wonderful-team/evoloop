"""Write global LLM config into SystemConfigService (local sqlite).

Reads values from ENV (never hard-codes secrets) and upserts the four keys the
LLM factory / dispatch read at runtime (LLM_PROVIDER, LLM_BASE_URL, LLM_MODEL,
LLM_API_KEY). The embedded DB lives at ~/.evoloop/database/backend.db (local,
gitignored). `get_value` reads the DB on every call, so changes take effect on
the next dispatch without restarting the backend.

Usage:
    LLM_PROVIDER=kimi LLM_BASE_URL=https://... LLM_MODEL=... LLM_API_KEY=sk-... \
        python scripts/set_llm_config.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path.home() / ".evoloop" / "database" / "backend.db"
KEYS = ["LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"]
# SQLModel default table name for `SystemConfig` is the lower-cased class name
# (`systemconfig`, NO underscore). Writing to `system_config` silently lands in
# a different table that the ORM never reads.
TABLE = "systemconfig"


def _mask(secret: str) -> str:
    if len(secret) <= 12:
        return "***"
    return f"{secret[:8]}…{secret[-4:]}"


def main() -> int:
    vals = {k: os.environ.get(k) for k in KEYS}
    missing = [k for k, v in vals.items() if not v]
    if missing:
        print(f"missing env vars: {missing}", file=sys.stderr)
        return 2

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    # Drop the mistakenly-named table from an earlier buggy run, if present.
    con.execute("DROP TABLE IF EXISTS system_config")
    con.execute(
        f"CREATE TABLE IF NOT EXISTS {TABLE} "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL, description TEXT)"
    )
    for k in KEYS:
        con.execute(
            f"INSERT OR REPLACE INTO {TABLE}(key, value) VALUES(?, ?)",
            (k, vals[k]),
        )
    con.commit()

    print(f"wrote {len(KEYS)} keys to {DB_PATH} (table `{TABLE}`):")
    for k in KEYS:
        row = con.execute(f'SELECT value FROM {TABLE} WHERE key=?', (k,)).fetchone()
        v = row[0] if row else None
        print(f"  {k} = {_mask(v) if k == 'LLM_API_KEY' and v else v}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
