"""Verify a newly synthesized flywheel skill by executing its macro directly.

This script loads the most recent pending_review flywheel macro for
"macos_increase_system_volume" and runs it through MacroEngine with a small
increment, then reports whether the AppleScript executed successfully.

    .venv/bin/python tests/manual/verify_flywheel_skill.py
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.execution.macro.schemas import MacroScript
from app.core.execution.macro.engine import MacroEngine


async def main():
    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    # Load the newest pending-review flywheel macro for volume up
    from app.infrastructure.database import session_scope
    from sqlalchemy import select
    from app.models.macro import Macro

    async with session_scope() as db:
        stmt = (
            select(Macro)
            .where(Macro.name == "macos_increase_system_volume")
            .order_by(Macro.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        macro = result.scalar_one_or_none()

    if macro is None:
        print("No flywheel macro found for macos_increase_system_volume")
        return

    print(f"Loaded macro #{macro.id} ({macro.status}) fallback_skill={macro.fallback_skill_id}")
    script = MacroScript.from_yaml(macro.macro_script)
    print(f"Macro has {len(script.steps)} steps")

    # Use a tiny increment to avoid surprising volume jumps; max=100
    params = {"increment": 1, "max_volume": 100, "_macro_id": macro.id, "_macro_name": macro.name}
    extracted: dict = {}

    try:
        ok, msg, data = await MacroEngine.execute(
            thread_id=f"verify-{macro.id}",
            script=script,
            params=params,
            extracted_data=extracted,
        )
    except Exception as e:
        ok = False
        msg = f"exception: {type(e).__name__}: {e}"

    print(f"\nVerification result: {'OK' if ok else 'FAIL'}")
    print(f"Message: {msg}")
    print(f"Extracted data: {data}")

    if ok:
        print("\nFlywheel macro executed successfully. The generated data is functional.")
    else:
        print("\nFlywheel macro failed to execute. See message above.")


if __name__ == "__main__":
    asyncio.run(main())
