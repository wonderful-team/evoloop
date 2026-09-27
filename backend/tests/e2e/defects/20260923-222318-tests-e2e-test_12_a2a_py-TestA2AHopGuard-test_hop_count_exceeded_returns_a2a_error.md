# E2E 缺陷报告：test_hop_count_exceeded_returns_a2a_error

- **测试 ID**: `tests/e2e/test_12_a2a.py::TestA2AHopGuard::test_hop_count_exceeded_returns_a2a_error`
- **发现时间**: 2026-09-23T22:23:18.804396
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_12_a2a.py:615: in test_hop_count_exceeded_returns_a2a_error
    await a2a_mock_gateway.inject_task(child_task_id, over_hop_task)
tests/e2e/test_12_a2a.py:299: in inject_task
    resp.raise_for_status()
.venv/lib/python3.12/site-packages/httpx/_models.py:829: in raise_for_status
    raise HTTPStatusError(message, request=request, response=self)
E   httpx.HTTPStatusError: Client error '403 Forbidden' for url 'http://127.0.0.1:20160/api/v1/devices/evo_24b93a4aa2db4a26acca6b68107a1087/command'
E   For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_12_a2a.py::TestA2AHopGuard::test_hop_count_exceeded_returns_a2a_error -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
