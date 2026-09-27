# E2E 缺陷报告：test_run_end_persisted_activity

- **测试 ID**: `tests/e2e/test_03_engine.py::TestRealAgentRun::test_run_end_persisted_activity`
- **发现时间**: 2026-08-29T04:57:40.941592
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
.venv/lib/python3.11/site-packages/pytest_asyncio/plugin.py:440: in runtest
    super().runtest()
.venv/lib/python3.11/site-packages/pytest_asyncio/plugin.py:906: in inner
    _loop.run_until_complete(task)
../../../../.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/asyncio/base_events.py:641: in run_until_complete
    self.run_forever()
../../../../.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/asyncio/base_events.py:608: in run_forever
    self._run_once()
../../../../.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/asyncio/base_events.py:1898: in _run_once
    event_list = self._selector.select(timeout)
../../../../.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/selectors.py:566: in select
    kev_list = self._selector.control(None, max_ev, timeout)
E   Failed: Timeout (>120.0s) from pytest-timeout.
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_03_engine.py::TestRealAgentRun::test_run_end_persisted_activity -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
