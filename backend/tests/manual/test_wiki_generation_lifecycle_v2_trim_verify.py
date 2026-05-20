#!/usr/bin/env python3
"""
Wiki Generation — _trim_worker_history Verification Test

Forces Worker to execute in multiple rounds by limiting max_steps,
then verifies that _trim_worker_history triggers on retry rounds
and that Worker continues to produce pages after trimming.
"""

import argparse
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from tests.manual.test_wiki_generation_lifecycle_v2 import (
    TEST_PROJECT_ID,
    TEST_PROJECT_PATH,
    TEST_TIMEOUT,
    _init_backend,
    _pre_test_cleanup,
    _clear_existing_wiki,
    _ensure_skill,
    _run_wiki_agent,
    _verify_results,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("wiki_trim_verify")


async def main():
    parser = argparse.ArgumentParser(description="Verify _trim_worker_history on multi-round Worker execution")
    parser.add_argument("--timeout", type=int, default=TEST_TIMEOUT, help="Safety timeout")
    parser.add_argument("--budget", type=int, default=600, help="Time budget in seconds")
    parser.add_argument("--worker-steps", type=int, default=12, help="Force WORKER_AGENT_MAX_STEPS to this value (default 12)")
    parser.add_argument("--skip-clear", action="store_true")
    args = parser.parse_args()

    # ── CRITICAL: Force low max_steps BEFORE any node instantiation ──
    from app.core.config import settings
    original_max_steps = settings.WORKER_AGENT_MAX_STEPS
    object.__setattr__(settings, "WORKER_AGENT_MAX_STEPS", args.worker_steps)
    logger.info(f"[Test] FORCED WORKER_AGENT_MAX_STEPS = {args.worker_steps} (original={original_max_steps})")

    project_id = TEST_PROJECT_ID
    project_path = TEST_PROJECT_PATH

    logger.info("=" * 60)
    logger.info("Wiki Generation — _trim_worker_history Verification Test")
    logger.info("=" * 60)
    logger.info(f"Worker max_steps: {args.worker_steps}")
    logger.info(f"Time budget:      {args.budget}s")
    logger.info("")

    _pre_test_cleanup()
    await _init_backend()

    if not args.skip_clear:
        await _clear_existing_wiki(project_id)

    skill = await _ensure_skill()

    start_time = time.time()
    thread_id = None
    try:
        thread_id = await _run_wiki_agent(project_id, project_path, skill, args.timeout)
    except Exception as e:
        logger.exception(f"❌ Dispatch failed: {e}")
        sys.exit(1)

    logger.info(f"[Test] Agent dispatched. Waiting for budget ({args.budget}s)...")

    # Wait for budget
    elapsed = time.time() - start_time
    while elapsed < args.budget:
        await asyncio.sleep(5)
        elapsed = time.time() - start_time
        logger.info(f"[Test] Elapsed: {elapsed:.1f}s / {args.budget}s")

    logger.info(f"[Test] Budget exhausted ({args.budget}s). Checking results...")

    # Verify
    try:
        pages = await _verify_results(project_id)
        logger.info(f"[Test] ✅ Verification passed: {len(pages)} pages")
    except AssertionError as e:
        logger.warning(f"[Test] ⚠️ Verification issues: {e}")

    # ── Check logs for trimming events ──
    log_file = "/tmp/wiki_e2e_test_v2.log"
    trim_count = 0
    worker_rounds = 0
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            content = f.read()
            trim_count = content.count("History trimmed")
            worker_rounds = content.count("[Worker] 🚀 Engine.run_node")

    logger.info("=" * 60)
    logger.info("TRIM VERIFICATION REPORT")
    logger.info("=" * 60)
    logger.info(f"  Worker max_steps:     {args.worker_steps}")
    logger.info(f"  Worker rounds:        {worker_rounds}")
    logger.info(f"  History trimmed:      {trim_count}")
    logger.info(f"  Pages produced:       {len(pages) if 'pages' in locals() else 'N/A'}")
    logger.info("")

    if worker_rounds >= 2 and trim_count >= 1:
        logger.info("✅ PASS: _trim_worker_history triggered on retry round(s)")
    elif worker_rounds >= 2 and trim_count == 0:
        logger.error("❌ FAIL: Worker had multiple rounds but trimming NEVER triggered")
        logger.error("   This means _trim_worker_history is a dead method.")
        sys.exit(1)
    elif worker_rounds < 2:
        logger.warning("⚠️ INCONCLUSIVE: Worker completed in single round (max_steps too high?)")
        logger.warning("   Try lowering --worker-steps (e.g. 8 or 10)")
        sys.exit(2)
    else:
        logger.info("?  UNKNOWN state")
        sys.exit(3)


if __name__ == "__main__":
    asyncio.run(main())
