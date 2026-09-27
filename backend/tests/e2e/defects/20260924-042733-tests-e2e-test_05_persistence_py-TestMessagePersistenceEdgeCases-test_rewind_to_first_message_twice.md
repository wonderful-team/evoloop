# E2E 缺陷报告：test_rewind_to_first_message_twice

- **测试 ID**: `tests/e2e/test_05_persistence.py::TestMessagePersistenceEdgeCases::test_rewind_to_first_message_twice`
- **发现时间**: 2026-09-24T04:27:33.157726
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_05_persistence.py:184: in test_rewind_to_first_message_twice
    assert resp2.status_code == 200, resp2.text
E   AssertionError: {"success":false,"code":"HTTP_404","message":"Target message not found","detail":"Target message not found"}
E   assert 404 == 200
E    +  where 404 = <Response [404 Not Found]>.status_code
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_05_persistence.py::TestMessagePersistenceEdgeCases::test_rewind_to_first_message_twice -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
