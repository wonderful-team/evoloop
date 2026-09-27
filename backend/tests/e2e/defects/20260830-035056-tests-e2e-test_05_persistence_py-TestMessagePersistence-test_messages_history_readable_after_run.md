# E2E 缺陷报告：test_messages_history_readable_after_run

- **测试 ID**: `tests/e2e/test_05_persistence.py::TestMessagePersistence::test_messages_history_readable_after_run`
- **发现时间**: 2026-08-30T03:50:56.718619
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_05_persistence.py:85: in test_messages_history_readable_after_run
    assert body.get("total_count", 0) >= 2, (
E   AssertionError: 真实运行后应至少包含 human+ai 消息，total_count=1
E   assert 1 >= 2
E    +  where 1 = <built-in method get of dict object at 0x1616add80>('total_count', 0)
E    +    where <built-in method get of dict object at 0x1616add80> = {'data': [{'category': '', 'changeset_count': 0, 'changeset_files': None, 'checkpoint_id': None, ...}], 'first_id': 'c108b9fe-774e-49ea-a4a5-aeabda0e79df', 'has_more': False, 'last_id': 'c108b9fe-774e-49ea-a4a5-aeabda0e79df', ...}.get
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_05_persistence.py::TestMessagePersistence::test_messages_history_readable_after_run -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
