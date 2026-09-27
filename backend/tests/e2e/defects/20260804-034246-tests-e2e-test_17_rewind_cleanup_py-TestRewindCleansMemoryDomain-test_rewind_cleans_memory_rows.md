# E2E 缺陷报告：test_rewind_cleans_memory_rows

- **测试 ID**: `tests/e2e/test_17_rewind_cleanup.py::TestRewindCleansMemoryDomain::test_rewind_cleans_memory_rows`
- **发现时间**: 2026-08-04T03:42:46.148940
- **状态**: ✅ 已修复（2026-08-04T05:50 复跑 3 passed, 1 xpassed → 移除 xfail 后 1 passed）

## 根因（三层错配）

`app/core/memory/event/subscribers.py` `MemoryRewind._delete_memories`：

1. **过滤键错误（数据丢失风险）**: `filters={"run_id": run_id}` — `MemoryIndex` 无 `run_id` 列（实为 `source_run_id`，models/memory.py:41），`_db_search` 的 `hasattr` 检查（file_engine.py:660）静默丢弃该键 → 返回全部记忆（limit 100）→ 若 member_id 匹配上会**误删无关记忆**。
2. **member_id 错配**: `search_memories` 默认 `member_id=0`（manager.py:454）→ SQL 过滤 `member_id == 0`；但 remember 工具写入 `member_id=ctx.member_id=1`（app/core/memory/tools.py:86,112）。两个 bug 互相掩盖，导致 rewind 既删不掉目标行（测试实际观察到的失败）。
3. **source_message_id 语义错误**: remember 工具把 `str(run_id)` 存入 `source_message_id`（tools.py:116）而非消息 UUID，使按消息 ID 清理的循环永远无法命中 remember 记忆（harvest 路径则不写该字段）。

## 修复内容

`app/core/memory/event/subscribers.py` `_delete_memories`：
- `filters={"run_id": ...}` → `filters={"source_run_id": ...}`（真实列名）
- 两处搜索均传 `member_id=None`，清理不再被默认 member_id=0 范围限制

## 验证

- 复跑 `test_17_rewind_cleanup.py`：3 passed + 1 xpassed（原 XFAIL 用例）
- 移除 xfail 标记后复跑：1 passed（含"不误删无关记忆"断言）
- 服务重启后生效（bin/evo stop && bin/evo start）

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤（修复前）

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_17_rewind_cleanup.py::TestRewindCleansMemoryDomain::test_rewind_cleans_memory_rows -v`
