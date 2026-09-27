"""AutonomousTask 收缩为纯定时器：存量宏类行 → recurring ProjectTask 幂等迁移。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

import app.models.planning  # noqa: F401
import app.models.project  # noqa: F401
from app.models.project import ProjectTask
from app.models.scheduler import AutonomousTask


@pytest.fixture
async def _db(monkeypatch):
    from tests.unit.db_stub import stub_db_for_loop

    engine = create_async_engine("sqlite+aiosqlite://")
    factory = stub_db_for_loop(monkeypatch, engine)
    async with factory() as session:
        await session.run_sync(
            lambda sess: AutonomousTask.__table__.create(
                sess.get_bind(), checkfirst=True
            )
        )
        await session.run_sync(
            lambda sess: ProjectTask.__table__.create(
                sess.get_bind(), checkfirst=True
            )
        )
    yield factory
    await engine.dispose()


async def _add_macro_row(macro_id: int = 7, trigger: str = "0 9 * * *") -> int:
    from app.infrastructure.database import session_scope

    async with session_scope() as session:
        row = AutonomousTask(
            intent_description="每天抓取闲鱼新发商品",
            project_id=1,
            macro_id=macro_id,
            params_template={"keyword": "显卡"},
            trigger_spec=trigger,
            is_active=True,
        )
        session.add(row)
        await session.flush()
        return row.id


class TestLegacyMacroConversion:
    async def test_macro_row_converted_to_recurring_project_task(self, _db):
        from app.infrastructure.scheduler.service import SchedulerService
        row_id = await _add_macro_row()
        converted = await SchedulerService.convert_legacy_macro_rows()
        assert converted == 1

        # 新工作项：recurring + trigger 透传 + 宏引用在 description
        rows = await TaskQueueServiceListHelper.all_project_tasks()
        assert len(rows) == 1
        t = rows[0]
        assert t.type == "recurring"
        assert t.trigger_spec == "0 9 * * *"
        assert t.source == "user"
        assert "#7" in t.description
        assert t.category == "macro"

        # 原行墓碑化：不再被 tick 扫描
        from app.infrastructure.database import session_scope

        async with session_scope() as session:
            row = await session.get(AutonomousTask, row_id)
            assert row.is_active is False

    async def test_conversion_is_idempotent(self, _db):
        from app.infrastructure.scheduler.service import SchedulerService

        await _add_macro_row()
        assert await SchedulerService.convert_legacy_macro_rows() == 1
        assert await SchedulerService.convert_legacy_macro_rows() == 0

        rows = await TaskQueueServiceListHelper.all_project_tasks()
        assert len(rows) == 1  # 不重复建任务（dedup_key 兜底）

    async def test_duty_rows_untouched(self, _db):
        """值守轮巡行（无 macro_id）不参与迁移。"""
        from app.infrastructure.database import session_scope
        from app.infrastructure.scheduler.service import SchedulerService

        async with session_scope() as session:
            session.add(
                AutonomousTask(
                    intent_description="duty poll",
                    project_id=1,
                    params_template={"duty_channel": "mcp_message", "kind": "kf"},
                    trigger_spec="interval:60",
                    is_active=True,
                )
            )
        assert await SchedulerService.convert_legacy_macro_rows() == 0


class TaskQueueServiceListHelper:
    @staticmethod
    async def all_project_tasks() -> list[ProjectTask]:
        from sqlalchemy import select

        from app.infrastructure.database import session_scope

        async with session_scope() as session:
            rows = (
                (await session.execute(select(ProjectTask))).scalars().all()
            )
            return list(rows)


    async def test_member_id_carried(self, _db):
        from app.infrastructure.database import session_scope
        from app.infrastructure.scheduler.service import SchedulerService

        async with session_scope() as session:
            row = AutonomousTask(
                intent_description="owner-bound macro",
                project_id=1,
                member_id=9,
                macro_id=3,
                trigger_spec="interval:60",
                is_active=True,
            )
            session.add(row)

        await SchedulerService.convert_legacy_macro_rows()
        rows = await TaskQueueServiceListHelper.all_project_tasks()
        assert len(rows) == 1
        assert rows[0].member_id == 9

    async def test_missing_project_defaults_to_zero(self, _db):
        from app.infrastructure.database import session_scope
        from app.infrastructure.scheduler.service import SchedulerService

        async with session_scope() as session:
            session.add(
                AutonomousTask(
                    intent_description="no project",
                    macro_id=4,
                    trigger_spec="interval:60",
                    is_active=True,
                )
            )

        await SchedulerService.convert_legacy_macro_rows()
        rows = await TaskQueueServiceListHelper.all_project_tasks()
        assert rows[0].project_id == 0
