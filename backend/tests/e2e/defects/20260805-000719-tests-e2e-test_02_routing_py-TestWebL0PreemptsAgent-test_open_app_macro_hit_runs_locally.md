# E2E 缺陷报告：test_open_app_macro_hit_runs_locally

- **测试 ID**: `tests/e2e/test_02_routing.py::TestWebL0PreemptsAgent::test_open_app_macro_hit_runs_locally`
- **发现时间**: 2026-08-05T00:07:19.638826
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_02_routing.py:528: in test_open_app_macro_hit_runs_locally
    assert body["status"] == "done", (
E   AssertionError: L0 命中宏应本地执行 done，实际 {'status': 'queued', 'thread_id': 'e2e-7015d66d6d204b49', 'message_id': 'b8542cc3-a2be-4287-b402-a4e0ecee2021'}
E   assert 'queued' == 'done'
E     
E     - done
E     + queued
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_02_routing.py::TestWebL0PreemptsAgent::test_open_app_macro_hit_runs_locally -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
