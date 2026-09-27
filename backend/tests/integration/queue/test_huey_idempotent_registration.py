"""Verify Huey task registration is idempotent across re-imports."""

from __future__ import annotations

import importlib


def test_reimport_shared_task_is_idempotent():
    """Re-importing a module decorated with @shared_task must not raise.

    Previously, a second import of ``app.core.engine.tasks`` would trigger:
    ``ValueError: Attempting to register a task with the same identifier as
    existing task. "app.core.engine.tasks.engine_persist_file_operation"``.
    """
    from app.core.engine import tasks

    assert tasks.persist_file_operation_task

    reloaded = importlib.reload(tasks)
    assert reloaded.persist_file_operation_task


def test_import_file_tools_after_tasks_does_not_raise():
    """Importing app.domain.tools.files after tasks are registered must work.

    This is the exact chain that caused the test-collection conflict:
    ``app.domain.tools.files`` imports ``delete_file``, which imports
    ``persist_file_operation_task`` from ``app.core.engine.tasks``.
    """
    from app.core.engine import tasks
    from app.core.file.tools import delete_file

    assert tasks.persist_file_operation_task
    assert delete_file.name == "delete_file"
