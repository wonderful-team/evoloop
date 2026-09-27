"""DB 并发读写压力测试（验证 QueuePool 耗尽与修复效果）。

用法：
    uv run python scripts/db_pool_rw_stress.py
    uv run python scripts/db_pool_rw_stress.py --workers 100 --ops 20 --slow-ratio 0.2

默认使用临时 SQLite 文件库 + WAL，模拟生产同构配置。
"""

import argparse
import asyncio
import logging
import os
import random
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

# 必须在 import app 之前设置（pydantic-settings 启动时读取）
_STRESS_TEMP_DIR = Path(tempfile.mkdtemp(prefix="evoloop_db_stress_"))
os.environ["EMBEDDED_MODE"] = "true"
os.environ["SQLITE_PATH"] = str(_STRESS_TEMP_DIR / "stress.db")
os.environ["SQLITE_DB_PATH"] = os.environ["SQLITE_PATH"]
os.environ["DB_ECHO_POOL"] = "false"
os.environ["DB_SLOW_CHECKOUT_THRESHOLD"] = "0.5"

# 默认小池 + 短超时，让问题容易暴露；可用环境变量覆盖
os.environ.setdefault("DB_POOL_SIZE", "5")
os.environ.setdefault("DB_MAX_OVERFLOW", "10")
os.environ.setdefault("DB_POOL_TIMEOUT", "5")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("db_pool_rw_stress")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column  # noqa: E402


class StressBase(DeclarativeBase):
    pass


class StressCounter(StressBase):
    __tablename__ = "stress_counter"
    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[float] = mapped_column(default=0.0)


async def setup() -> None:
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.infrastructure.database.sql.database import Base as AppBase

    await db_resource_manager.initialize(create_tables=False)

    engine = db_resource_manager.engine
    assert engine is not None
    async with engine.begin() as conn:
        await conn.run_sync(StressBase.metadata.create_all)
        await conn.run_sync(AppBase.metadata.create_all)
        await conn.execute(sa.delete(StressCounter).where(StressCounter.id == 1))
        stmt = sa.insert(StressCounter).values(id=1, value=0, updated_at=0)
        await conn.execute(stmt)

    logger.info("DB ready at %s", os.environ["SQLITE_PATH"])


async def cleanup() -> None:
    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.shutdown()
    import shutil

    shutil.rmtree(_STRESS_TEMP_DIR, ignore_errors=True)


async def worker(
    _worker_id: int,
    ops: int,
    slow_ratio: float,
    slow_sleep: float,
    slow_outside: bool,
    stats: dict,
    semaphore: asyncio.Semaphore,
) -> None:
    from app.infrastructure.database.sql.database import session_scope

    for _ in range(ops):
        async with semaphore:
            op = "write" if random.random() < 0.5 else "read"
            is_slow = random.random() < slow_ratio
            start = time.monotonic()
            try:
                async with session_scope() as session:
                    if op == "write":
                        result = await session.execute(
                            sa.select(StressCounter.value).where(StressCounter.id == 1)
                        )
                        value = result.scalar_one()
                        await session.execute(
                            sa.update(StressCounter)
                            .where(StressCounter.id == 1)
                            .values(value=value + 1, updated_at=time.time())
                        )
                    else:
                        await session.execute(sa.select(StressCounter).where(StressCounter.id == 1))

                    if is_slow and not slow_outside:
                        await asyncio.sleep(slow_sleep)

                if is_slow and slow_outside:
                    await asyncio.sleep(slow_sleep)

                stats["ok"] += 1
                stats["by_op_ok"][op] += 1
            except Exception as exc:
                stats["fail"] += 1
                stats["by_error"][type(exc).__name__] += 1
                stats["by_op_fail"][op] += 1
                # 不要把错误刷到日志 flood，最后汇总
            finally:
                duration_ms = int((time.monotonic() - start) * 1000)
                stats["durations_ms"].append(duration_ms)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--ops", type=int, default=10)
    parser.add_argument("--slow-ratio", type=float, default=0.1)
    parser.add_argument("--slow-sleep", type=float, default=2.0)
    parser.add_argument(
        "--slow-outside", action="store_true", help="把 sleep 放到 session 外，验证短事务即可避免池耗尽"
    )
    parser.add_argument("--max-concurrent", type=int, default=0, help="0 = 等于 workers")
    args = parser.parse_args()

    try:
        await setup()

        from app.infrastructure.database.resource_manager import db_resource_manager

        concurrent = args.max_concurrent or args.workers
        semaphore = asyncio.Semaphore(concurrent)
        stats: dict = {
            "ok": 0,
            "fail": 0,
            "by_op_ok": Counter(),
            "by_op_fail": Counter(),
            "by_error": Counter(),
            "durations_ms": [],
        }

        logger.info(
            "Starting stress: workers=%d ops=%d concurrent=%d slow_ratio=%.2f slow_sleep=%.1f slow_outside=%s pool=%s/%s timeout=%s",
            args.workers,
            args.ops,
            concurrent,
            args.slow_ratio,
            args.slow_sleep,
            args.slow_outside,
            os.environ.get("DB_POOL_SIZE"),
            os.environ.get("DB_MAX_OVERFLOW"),
            os.environ.get("DB_POOL_TIMEOUT"),
        )

        overall_start = time.monotonic()
        tasks = [
            asyncio.create_task(worker(i, args.ops, args.slow_ratio, args.slow_sleep, args.slow_outside, stats, semaphore))
            for i in range(args.workers)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        overall_duration = time.monotonic() - overall_start

        # 最终池状态
        pool_status = db_resource_manager.pool_status()

        durations = stats["durations_ms"]
        durations.sort()
        total = stats["ok"] + stats["fail"]
        logger.info("=" * 60)
        logger.info("Stress completed: total_ops=%d ok=%d fail=%d duration=%.2fs", total, stats["ok"], stats["fail"], overall_duration)
        logger.info("Throughput: %.1f ops/s", total / overall_duration if overall_duration > 0 else 0)
        logger.info("OK by op: %s", dict(stats["by_op_ok"]))
        logger.info("Fail by op: %s", dict(stats["by_op_fail"]))
        logger.info("Errors: %s", dict(stats["by_error"]))
        if durations:
            logger.info(
                "Latency ms: p50=%d p95=%d p99=%d max=%d",
                durations[len(durations) // 2],
                durations[int(len(durations) * 0.95)],
                durations[int(len(durations) * 0.99)],
                durations[-1],
            )
        logger.info("Final pool status: %s", pool_status)
        logger.info("=" * 60)

        return 0 if stats["fail"] == 0 else 1
    finally:
        await cleanup()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
